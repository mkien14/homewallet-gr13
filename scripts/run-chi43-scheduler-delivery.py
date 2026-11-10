"""Run real one-time Scheduler -> deployed jobs -> SES/push in isolated schemas.

Uses unmodified hw-jobs:3 CLIs, roles and network. The three recurring schedules
stay disabled. Default SES recipient is the AWS success mailbox simulator.
"""

import argparse
import ast
import base64
import copy
import hashlib
import json
import lzma
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3


REGION = 'ap-southeast-1'
ACCOUNT = '179923444714'
GROUP = 'homewallet-dev-jobs'
CLUSTER = 'homewallet'
TASK = 'arn:aws:ecs:ap-southeast-1:179923444714:task-definition/hw-jobs:3'
KINDS = {'weekly': ['python', '-m', 'jobs.weekly_report'],
         'reminder': ['python', '-m', 'jobs.recurring_alerts', 'reminders'],
         'budget': ['python', '-m', 'jobs.recurring_alerts', 'budget-alerts']}


def now():
    return datetime.now(timezone.utc)


def emit(event, **fields):
    print(json.dumps(dict(event=event, at_utc=now().isoformat(), **fields), default=str), flush=True)


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


class Runner:
    def __init__(self, result):
        self.result = result
        self.session = boto3.Session(region_name=REGION)
        require(self.session.client('sts').get_caller_identity()['Account'] == ACCOUNT, 'wrong_aws_account')
        self.ecs = self.session.client('ecs')
        self.scheduler = self.session.client('scheduler')
        self.logs = self.session.client('logs')
        self.original = {}
        for name in ('hw-weekly-report', 'hw-recurring-reminders', 'hw-budget-alerts'):
            schedule = self.scheduler.get_schedule(Name=name, GroupName=GROUP)
            require(schedule['State'] == 'DISABLED', 'recurring_schedule_not_disabled')
            require(schedule['Target']['EcsParameters']['TaskDefinitionArn'] == TASK, 'unexpected_jobs_revision')
            self.original[name] = schedule
        self.template = self.original['hw-budget-alerts']['Target']
        network = self.template['EcsParameters']['NetworkConfiguration']['awsvpcConfiguration']
        self.network = {'awsvpcConfiguration': {'subnets':network['Subnets'],
                        'securityGroups':network['SecurityGroups'],
                        'assignPublicIp':network['AssignPublicIp']}}
        source = Path(__file__).with_name('chi43-scheduler-fixture.py').read_bytes()
        tree = ast.parse(source)
        if isinstance(tree.body[0], ast.Expr):
            tree.body.pop(0)
        payload = ast.unparse(tree).encode()
        self.boot = "import base64,lzma;exec(lzma.decompress(base64.b64decode('" + base64.b64encode(lzma.compress(payload, preset=9)).decode() + "')))"
        result['fixture_source_sha256'] = hashlib.sha256(source).hexdigest()
        result['fixture_payload_sha256'] = hashlib.sha256(payload).hexdigest()
        result['recurring_schedules_before'] = {k:v['State'] for k,v in self.original.items()}
        td = self.ecs.describe_task_definition(taskDefinition=TASK)['taskDefinition']
        result['jobs_image'] = td['containerDefinitions'][0]['image']
        result['task_role'] = td['taskRoleArn']
        result['execution_role'] = td['executionRoleArn']

    def collect(self, task, group, prefix, container):
        record = {'task_arn':task['taskArn'], 'task_definition':task['taskDefinitionArn'],
                  'group':task.get('group'), 'exit_code':task['containers'][0].get('exitCode'),
                  'image_digest':task['containers'][0].get('imageDigest'),
                  'log_group':group, 'log_stream':f"{prefix}/{container}/{task['taskArn'].rsplit('/',1)[1]}"}
        events = []
        for _ in range(6):
            try:
                messages = self.logs.get_log_events(logGroupName=group, logStreamName=record['log_stream'], startFromHead=True)['events']
                for m in messages:
                    try:
                        event = json.loads(m['message'])
                    except ValueError:
                        continue
                    # Never retain generic exception text or request/provider payloads.
                    if str(event.get('event','')).startswith('CHI43_'):
                        events.append(event)
                    elif event.get('event') in ('scheduled_job_finished','scheduled_job_skipped','push_delivery_summary',
                                               'weekly_report_sent','weekly_report_skipped','weekly_report_failed',
                                               'budget_alert_failed','recurring_reminder_failed'):
                        events.append({k:v for k,v in event.items() if k not in ('aws_error_message',)})
                if events:
                    break
            except self.logs.exceptions.ResourceNotFoundException:
                pass
            time.sleep(2)
        record['events'] = events
        return record

    def admin(self, mode, recipient):
        command = ['python','-c',self.boot,mode,'--run-id',self.result['run_id']]
        if mode == 'prepare':
            command += ['--recipient',recipient]
        overrides = {'containerOverrides':[{'name':'bootstrap','command':command}]}
        require(len(json.dumps(overrides)) < 8192, 'ecs_override_too_large')
        response = self.ecs.run_task(cluster=CLUSTER,taskDefinition='hw-db-runtime-bootstrap:2',
            launchType='FARGATE',count=1,networkConfiguration=self.network,overrides=overrides,
            startedBy='chi43-send-'+mode,clientToken=str(uuid.uuid4()))
        require(not response.get('failures') and len(response.get('tasks',[])) == 1, 'bootstrap_launch_failed')
        arn = response['tasks'][0]['taskArn']
        self.result['admin_tasks'].append({'mode':mode,'task_arn':arn,'status':'STARTED'})
        record = self.result['admin_tasks'][-1]
        emit('CHI43_BOOTSTRAP_STARTED', mode=mode, task_arn=arn)
        deadline = time.monotonic()+300
        while time.monotonic() < deadline:
            task = self.ecs.describe_tasks(cluster=CLUSTER,tasks=[arn])['tasks'][0]
            if task['lastStatus']=='STOPPED':
                record.update(self.collect(task,'/ecs/hw-db-runtime-bootstrap','bootstrap','bootstrap'))
                emit('CHI43_BOOTSTRAP_FINISHED',mode=mode,exit_code=record['exit_code'],events=record['events'])
                require(record['exit_code']==0,'bootstrap_'+mode+'_failed')
                return record
            time.sleep(5)
        self.ecs.stop_task(cluster=CLUSTER,task=arn,reason='CHI43 bounded bootstrap timeout')
        raise RuntimeError('bootstrap_timeout')

    def schedule(self):
        for i,(kind,command) in enumerate(KINDS.items()):
            name = f"chi43-{self.result['run_id']}-{kind}"
            group = name
            target = copy.deepcopy(self.template)
            target['EcsParameters']['Group'] = group
            target['RetryPolicy'] = {'MaximumEventAgeInSeconds':60,'MaximumRetryAttempts':0}
            # Each locale has its own database. Repeat every CLI to verify claims
            # suppress additional sends. No mocks or altered job selectors.
            commands = []
            for locale in ('vi','en'):
                schema = f"chi43_send_{self.result['run_id']}_{locale}"
                call = f"DB_NAME={schema} " + ' '.join(command)
                commands += [call, 'sleep 2', call, 'sleep 2']
            shell = ' && '.join(commands)
            target['Input'] = json.dumps({'containerOverrides':[{'name':'jobs','command':['sh','-c',shell]}]})
            fire = now()+timedelta(seconds=100+i*65)
            expression = 'at('+fire.strftime('%Y-%m-%dT%H:%M:%S')+')'
            response = self.scheduler.create_schedule(Name=name,GroupName=GROUP,State='ENABLED',
                ScheduleExpression=expression,ScheduleExpressionTimezone='UTC',
                FlexibleTimeWindow={'Mode':'OFF'},ActionAfterCompletion='NONE',
                Target=target,ClientToken=str(uuid.uuid4()),Description='CHI43 isolated acceptance; temporary one-time delivery')
            record = {'name':name,'arn':response['ScheduleArn'],'ecs_group':group,
                      'expression':expression,'commands':commands,'task_definition':TASK,'kind':kind}
            self.result['one_time_schedules'].append(record)
            emit('CHI43_ONE_TIME_SCHEDULE_CREATED', name=name, expression=expression)

    def wait_scheduled(self):
        deadline = time.monotonic()+600
        groups = {x['ecs_group']:x for x in self.result['one_time_schedules']}
        found = {}
        last_progress = 0
        while time.monotonic()<deadline:
            arns = set()
            for status in ('RUNNING','STOPPED'):
                pages = self.ecs.get_paginator('list_tasks').paginate(cluster=CLUSTER,family='hw-jobs',desiredStatus=status)
                for page in pages:
                    arns.update(page['taskArns'])
            tasks = []
            arns = list(arns)
            for offset in range(0,len(arns),100):
                tasks += self.ecs.describe_tasks(cluster=CLUSTER,tasks=arns[offset:offset+100])['tasks']
            for task in tasks:
                group = task.get('group')
                if group not in groups:
                    continue
                require(task['taskDefinitionArn']==TASK,'unexpected_scheduled_revision')
                if task['lastStatus']=='STOPPED' and task['taskArn'] not in found:
                    record = self.collect(task,'/ecs/hw-jobs','scheduled','jobs')
                    record['kind'] = groups[group]['kind']
                    found[task['taskArn']] = record
                    self.result['scheduled_tasks'].append(record)
                    emit('CHI43_SCHEDULED_TASK_FINISHED',kind=record['kind'],task_arn=record['task_arn'],
                         exit_code=record['exit_code'],events=record['events'])
            if len(found)==len(groups):
                require(all(x['exit_code']==0 for x in found.values()),'scheduled_job_failed')
                return
            if time.monotonic()-last_progress>30:
                emit('CHI43_SCHEDULER_WAIT', completed=len(found), expected=len(groups))
                last_progress=time.monotonic()
            time.sleep(8)
        raise RuntimeError('scheduler_delivery_timeout')

    def cleanup_schedules(self):
        for schedule in self.result['one_time_schedules']:
            try:
                self.scheduler.delete_schedule(Name=schedule['name'],GroupName=GROUP)
                schedule['deleted']=True
            except self.scheduler.exceptions.ResourceNotFoundException:
                schedule['deleted']=True
        groups={x['ecs_group'] for x in self.result['one_time_schedules']}
        tasks=self.ecs.list_tasks(cluster=CLUSTER,family='hw-jobs',desiredStatus='RUNNING')['taskArns']
        if tasks:
            for task in self.ecs.describe_tasks(cluster=CLUSTER,tasks=tasks)['tasks']:
                if task.get('group') in groups:
                    self.ecs.stop_task(cluster=CLUSTER,task=task['taskArn'],reason='CHI43 acceptance cleanup')
                    self.ecs.get_waiter('tasks_stopped').wait(cluster=CLUSTER,tasks=[task['taskArn']],WaiterConfig={'Delay':5,'MaxAttempts':36})
        states={name:self.scheduler.get_schedule(Name=name,GroupName=GROUP)['State'] for name in self.original}
        self.result['recurring_schedules_after']=states
        require(all(v=='DISABLED' for v in states.values()),'recurring_schedule_state_changed')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recipient', default='success@simulator.amazonses.com')
    p.add_argument('--mailbox-control-confirmed',action='store_true')
    p.add_argument('--output',required=True)
    args=p.parse_args()
    result={'run_id':uuid.uuid4().hex[:12],'started_at_utc':now().isoformat(),
            'account':ACCOUNT,'region':REGION,'admin_tasks':[], 'one_time_schedules':[],
            'scheduled_tasks':[],'recipient_type':'ses_mailbox_simulator' if args.recipient.endswith('@simulator.amazonses.com') else 'controlled_mailbox',
            'recipient_sha256':hashlib.sha256(args.recipient.encode()).hexdigest(),
            'inbox_receipt':'NOT_PROVEN','device_receipt':'PENDING_USER_CONFIRMATION'}
    runner=None
    prepared=False
    output=Path(args.output)
    try:
        simulator=args.recipient=='success@simulator.amazonses.com'
        require(simulator or args.mailbox_control_confirmed,'mailbox_control_confirmation_required')
        if not simulator:
            verified=boto3.client('sesv2',region_name=REGION).get_email_identity(EmailIdentity=args.recipient)
            require(verified.get('VerifiedForSendingStatus'),'recipient_not_verified_for_sandbox')
        runner=Runner(result)
        prepared=True  # cleanup also covers partially prepared schemas
        runner.admin('prepare',args.recipient)
        runner.schedule()
        runner.wait_scheduled()
        inspection=runner.admin('inspect',args.recipient)
        states=[x for x in inspection['events'] if x['event']=='CHI43_SEND_FIXTURE_STATE']
        require(len(states)==2,'fixture_inspection_missing')
        for state in states:
            require(len(state['job_runs'])==3 and all(x['status']=='SUCCEEDED' for x in state['job_runs']), 'job_claims_not_succeeded')
            require(len(state['notifications'])==2 and len(state['alerts'])==1,'notification_dedup_failed')
        summaries=[event for task in result['scheduled_tasks'] for event in task['events'] if event['event']=='push_delivery_summary']
        require(len(summaries)==4 and all(x.get('sent')==1 and x.get('failed')==0 and x.get('expired')==0 for x in summaries),'push_delivery_unconfirmed')
        result['status']='PASS_SCHEDULER_CLI_SES_ACCEPTANCE_AND_PUSH_PROVIDER'
        result['expected_ses_messages']=6
        result['push_provider_accepted']=4
    except Exception as exc:
        result['status']='FAILED'
        result['error_type']=type(exc).__name__
        if type(exc) is RuntimeError:
            result['reason']=str(exc)
        if hasattr(exc,'response'):
            result['aws_error_code']=exc.response.get('Error',{}).get('Code')
        emit('CHI43_DELIVERY_FAILED',status=result['status'],reason=result.get('reason'),error_type=result['error_type'],aws_error_code=result.get('aws_error_code'))
    finally:
        if runner:
            try:
                runner.cleanup_schedules()
                if prepared:
                    runner.admin('cleanup',args.recipient)
                result['cleanup']='PASS'
            except Exception as exc:
                result['cleanup']='FAILED'
                result['cleanup_error_type']=type(exc).__name__
                if type(exc) is RuntimeError:
                    result['cleanup_reason']=str(exc)
        result['finished_at_utc']=now().isoformat()
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        emit('CHI43_DELIVERY_RESULT',status=result['status'],cleanup=result.get('cleanup'),output=str(output))
    return 0 if result.get('status','').startswith('PASS_') and result.get('cleanup')=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
