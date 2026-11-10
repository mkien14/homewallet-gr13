"""Exercise isolated Cognito email flows; codes/passwords stay in memory.

--simulator records send acceptance only, never inbox/code-confirmation PASS.
For complete cases run interactively with a controlled mailbox and enter each
code privately in the terminal. Temporary users are deleted even on Ctrl+C.
"""

import argparse
import getpass
import hashlib
import json
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3


def now():
    return datetime.now(timezone.utc).isoformat()


def password():
    return 'Chi43!aA7' + secrets.token_urlsafe(24)


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


class Runner:
    def __init__(self,args,result,environment):
        self.args,self.result,self.env=args,result,environment
        self.session=boto3.Session(region_name=environment['region'])
        require(self.session.client('sts').get_caller_identity()['Account']==environment['account'],'wrong_account')
        require(self.session.client('sesv2').get_account()['ProductionAccessEnabled'],'ses_production_access_required')
        self.c=self.session.client('cognito-idp')
        pool=self.c.describe_user_pool(UserPoolId=environment['user_pool_id'])['UserPool']
        require(pool.get('UserPoolTags',{}).get('Purpose')=='chi43-isolated-email-acceptance','not_acceptance_pool')
        require(pool['LambdaConfig']['CustomMessage']==environment['custom_message_lambda'],'lambda_changed')
        self.pool,self.client=pool['Id'],environment['client_id']
        self.recipient='success@simulator.amazonses.com' if args.simulator else args.recipient
        require(self.recipient and '@' in self.recipient,'controlled_mailbox_required')
        self.users=[]
        result['recipient_sha256']=hashlib.sha256(self.recipient.encode()).hexdigest()
        self.lm=self.session.client('lambda')
        self.config=self.lm.get_function_configuration(FunctionName=environment['custom_message_lambda'])
        result['lambda_code_sha256']=self.config['CodeSha256']
        self.start_ms=int(time.time()*1000)

    def api(self,case,operation,**kwargs):
        response=getattr(self.c,operation)(**kwargs)
        metadata=response['ResponseMetadata']
        entry={'case':case,'operation':operation,'http_status':metadata['HTTPStatusCode'],
               'aws_request_id':metadata['RequestId'],'at_utc':now()}
        delivery=response.get('CodeDeliveryDetails') or {}
        if delivery:
            entry['delivery_medium']=delivery.get('DeliveryMedium')
        self.result['api'].append(entry)
        print(json.dumps(entry),flush=True)
        time.sleep(1.2)
        return response

    def check_mail(self,case,locale,subject):
        if self.args.simulator:
            return
        print(f'\n{case}: kiem tra thu moi, locale={locale}, subject={subject}',flush=True)
        answer=input('Subject/body dung ngon ngu, khong con placeholder? [y/N]: ').strip().lower()
        require(answer=='y','mail_content_not_confirmed_'+case)

    def signup(self,case,locale,*,resend=False):
        username='chi43-'+self.result['run_id']+'-'+case.lower()
        pw=password()
        self.users.append(username)
        recipient=('success+'+username+'@simulator.amazonses.com') if self.args.simulator else self.recipient
        attrs=[{'Name':'email','Value':recipient}]
        if locale:
            attrs.append({'Name':'custom:preferred_locale','Value':locale})
        self.api(case,'sign_up',ClientId=self.client,Username=username,Password=pw,UserAttributes=attrs)
        effective=locale or 'vi'
        self.check_mail(case,effective,'HomeWallet - '+('Verify your account' if effective=='en' else 'Xác minh tài khoản'))
        if resend:
            self.api(case,'resend_confirmation_code',ClientId=self.client,Username=username)
            self.check_mail(case,effective,'HomeWallet - '+('New verification code' if effective=='en' else 'Mã xác minh mới'))
        if self.args.simulator:
            self.api(case+'_fixture_setup','admin_confirm_sign_up',UserPoolId=self.pool,Username=username)
            self.api(case+'_fixture_setup','admin_update_user_attributes',UserPoolId=self.pool,Username=username,
                     UserAttributes=[{'Name':'email_verified','Value':'true'}])
            self.result['cases'][case]='PARTIAL_SEND_ACCEPTED_SIMULATOR_NO_RECEIVED_CODE'
        else:
            code=getpass.getpass(case+' - nhap ma trong email moi nhat (an): ')
            self.api(case,'confirm_sign_up',ClientId=self.client,Username=username,ConfirmationCode=code)
            del code
            self.result['cases'][case]='PASS'
        self.login(case,username,pw)
        return username,pw

    def login(self,case,username,pw):
        response=self.api(case,'initiate_auth',ClientId=self.client,AuthFlow='USER_PASSWORD_AUTH',
                          AuthParameters={'USERNAME':username,'PASSWORD':pw})
        require('AuthenticationResult' in response,'login_failed_'+case)
        return response['AuthenticationResult']['AccessToken']

    def forgot(self,case,locale,username,pw):
        self.api(case,'forgot_password',ClientId=self.client,Username=username)
        self.check_mail(case,locale,'HomeWallet - '+('Reset your password' if locale=='en' else 'Đặt lại mật khẩu'))
        if self.args.simulator:
            self.result['cases'][case]='PARTIAL_SEND_ACCEPTED_SIMULATOR_NO_RECEIVED_CODE'
            return pw
        code=getpass.getpass(case+' - nhap ma reset (an): ')
        changed=password()
        self.api(case,'confirm_forgot_password',ClientId=self.client,Username=username,ConfirmationCode=code,Password=changed)
        del code
        self.login(case,username,changed)
        self.result['cases'][case]='PASS'
        return changed

    def run(self):
        users={}
        for locale,signup,resend,forgot in [('vi','CM01','CM03','CM05'),('en','CM02','CM04','CM06')]:
            username,pw=self.signup(signup,locale)
            self.signup(resend,locale,resend=True)
            pw=self.forgot(forgot,locale,username,pw)
            users[locale]=(username,pw)
        self.signup('CM07',None)
        username,pw=users['vi']
        for case,locale in [('CM08','en'),('CM09','vi')]:
            self.api(case,'admin_update_user_attributes',UserPoolId=self.pool,Username=username,
                     UserAttributes=[{'Name':'custom:preferred_locale','Value':locale}])
            pw=self.forgot(case,locale,username,pw)
        users['vi']=(username,pw)
        self.result['cases']['CM15']='PARTIAL_INVITATION_SEND_ACCEPTED_NO_TEMP_PASSWORD_LOGIN'
        for locale in ('vi','en'):
            case='CM15_'+locale
            invitation='chi43-'+self.result['run_id']+'-cm15-'+locale
            self.users.append(invitation)
            self.api(case,'admin_create_user',UserPoolId=self.pool,Username=invitation,
                     DesiredDeliveryMediums=['EMAIL'],UserAttributes=[{'Name':'email','Value':('success+'+invitation+'@simulator.amazonses.com') if self.args.simulator else self.recipient},
                     {'Name':'email_verified','Value':'true'},{'Name':'custom:preferred_locale','Value':locale}])
            if not self.args.simulator:
                print(case+': username trong thu phai la '+invitation,flush=True)
                self.check_mail(case,locale,'HomeWallet - '+('HomeWallet invitation' if locale=='en' else 'Lời mời HomeWallet'))
                temporary=getpass.getpass(case+' - nhap mat khau tam trong thu (an): ')
                response=self.api(case,'initiate_auth',ClientId=self.client,AuthFlow='USER_PASSWORD_AUTH',
                                  AuthParameters={'USERNAME':invitation,'PASSWORD':temporary})
                del temporary
                require(response.get('ChallengeName')=='NEW_PASSWORD_REQUIRED','invitation_challenge_missing')
                permanent=password()
                self.api(case,'respond_to_auth_challenge',ClientId=self.client,ChallengeName='NEW_PASSWORD_REQUIRED',
                         Session=response['Session'],ChallengeResponses={'USERNAME':invitation,'NEW_PASSWORD':permanent})
                self.login(case,invitation,permanent)
                self.result['cases'][case]='PASS'
        if not self.args.simulator:
            self.result['cases']['CM15']='PASS'
        self.result['cases']['CM16']='NOT_RUN_SECOND_CONTROLLED_MAILBOX_REQUIRED'
        if self.args.second_recipient and not self.args.simulator:
            require(self.args.second_recipient!=self.recipient,'changed_email_must_differ')
            for locale in ('vi','en'):
                case='CM16_'+locale
                username,pw=users[locale]
                token=self.login(case,username,pw)
                self.api(case,'update_user_attributes',AccessToken=token,
                         UserAttributes=[{'Name':'email','Value':self.args.second_recipient}])
                self.check_mail(case,locale,'HomeWallet - '+('Verify your account information' if locale=='en' else 'Xác minh thông tin tài khoản'))
                code=getpass.getpass(case+' - nhap ma gui toi dia chi email moi (an): ')
                self.api(case,'verify_user_attribute',AccessToken=token,AttributeName='email',Code=code)
                del code
                user=self.api(case,'get_user',AccessToken=token)
                attrs={x['Name']:x['Value'] for x in user['UserAttributes']}
                require(attrs.get('email')==self.args.second_recipient and attrs.get('email_verified')=='true',
                        'changed_email_not_verified')
                self.result['cases'][case]='PASS'
            self.result['cases']['CM16']='PASS'

    def cleanup(self):
        deleted=0
        for username in self.users:
            require(username.startswith('chi43-'+self.result['run_id']+'-'),'cleanup_scope_mismatch')
            try:
                self.c.admin_delete_user(UserPoolId=self.pool,Username=username)
                deleted+=1
            except self.c.exceptions.UserNotFoundException:
                pass
        self.result['temporary_users_created_or_attempted']=len(self.users)
        self.result['temporary_users_deleted']=deleted
        self.result['cleanup']='PASS'

    def logs(self):
        time.sleep(8)
        group=self.config.get('LoggingConfig',{}).get('LogGroup') or '/aws/lambda/'+self.config['FunctionName']
        logs=self.session.client('logs')
        end=int(time.time()*1000)
        counts={'total':0,'start':0,'application_lines':0}
        request_ids=[]
        for page in logs.get_paginator('filter_log_events').paginate(logGroupName=group,startTime=self.start_ms,endTime=end):
            for event in page.get('events',[]):
                message=event['message'].strip()
                counts['total']+=1
                if message.startswith('START RequestId:'):
                    counts['start']+=1
                    request_ids.append(message.split()[2])
                if not message.startswith(('START RequestId:','END RequestId:','REPORT RequestId:','INIT_START','INIT_REPORT')):
                    counts['application_lines']+=1
        self.result['lambda_log_review']={'log_group':group,'start_ms':self.start_ms,'end_ms':end,
             'counts':counts,'invocation_request_ids':request_ids,
             'scope':'Controlled email-request window; shared stateless Lambda, no per-trigger payload logging'}
        self.result['cases']['CM14']='PASS_CONTROLLED_EMAIL_TRIGGER_WINDOW' if counts['start']>0 and counts['application_lines']==0 else 'PARTIAL_LOG_REVIEW'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--environment',default='docs/acceptance/43-email-e2e-environment-20261110.json')
    p.add_argument('--recipient')
    p.add_argument('--second-recipient',help='Second controlled address for changed-email verification, CM16')
    p.add_argument('--simulator',action='store_true')
    p.add_argument('--output',required=True)
    args=p.parse_args()
    require(bool(args.recipient)!=args.simulator,'select_controlled_recipient_or_simulator')
    env=json.loads(Path(args.environment).read_text(encoding='utf-8'))
    result={'run_id':uuid.uuid4().hex[:12],'started_at_utc':now(),'user_pool_id':env['user_pool_id'],
            'recipient_type':'ses_mailbox_simulator' if args.simulator else 'controlled_mailbox',
            'api':[],'cases':{},'status':'RUNNING'}
    runner=None
    try:
        runner=Runner(args,result,env)
        runner.run()
        result['status']='PARTIAL_SIMULATOR_SEND_ACCEPTANCE' if args.simulator else 'COMPLETED_INTERACTIVE_CORE_CASES'
    except (Exception,KeyboardInterrupt) as exc:
        result['status']='FAILED_OR_INTERRUPTED'
        result['error_type']=type(exc).__name__
        if hasattr(exc,'response'):
            result['aws_error_code']=exc.response.get('Error',{}).get('Code')
            if result['aws_error_code']=='LimitExceededException':
                message=exc.response.get('Error',{}).get('Message','')
                result['aws_error_message']=re.sub(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}',
                                                   '[redacted-email]',message,flags=re.I)[:500]
        if type(exc) is RuntimeError:
            result['reason']=str(exc)
    finally:
        if runner:
            try:
                runner.cleanup()
            except Exception as exc:
                result['cleanup']='FAILED'
                result['cleanup_error_type']=type(exc).__name__
            try:
                runner.logs()
            except Exception as exc:
                result['log_review_error_type']=type(exc).__name__
        result['finished_at_utc']=now()
        Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':result['status'],'cases':result['cases'],'cleanup':result.get('cleanup'),'output':args.output}),flush=True)
    return 0 if result['status'] in ('PARTIAL_SIMULATOR_SEND_ACCEPTANCE','COMPLETED_INTERACTIVE_CORE_CASES') and result.get('cleanup')=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
