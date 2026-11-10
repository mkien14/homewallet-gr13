"""Prepare/inspect/remove isolated schemas for unmodified scheduled job CLIs.

Runs only with the existing bootstrap admin task. Provider endpoints and
subscription keys stay inside RDS; no credentials or email bodies are logged.
"""

import argparse
import hashlib
import json
import re
import traceback
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


TABLES = ('users', 'households', 'household_members', 'categories', 'transactions',
          'budgets', 'budget_lines', 'recurring_bills', 'notifications',
          'push_subscriptions', 'alert_state', 'job_runs')


def emit(event, **fields):
    print(json.dumps(dict(event=event, at_utc=datetime.now(timezone.utc).isoformat(),
                          **fields), default=str), flush=True)


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def query(db, sql, args=None):
    with db.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def execute(db, sql, args=None):
    with db.cursor() as cur:
        cur.execute(sql, args)


def scope(db, schema, run):
    marker = query(db, f'SELECT run_id FROM `{schema}`._chi43_scope')
    require(marker == [{'run_id': run}], 'fixture_scope_mismatch')


def prepare(db, args):
    require(args.recipient and '@' in args.recipient, 'recipient_required')
    require(query(db, 'SELECT id FROM homewallet.users WHERE id=16'), 'controlled_user_missing')
    sub = query(db, "SELECT id FROM homewallet.push_subscriptions WHERE id=6 AND user_id=16 AND status='ACTIVE'")
    require(len(sub) == 1, 'controlled_subscription_6_not_active')
    today = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    start = today - timedelta(days=today.weekday() + 7)
    require(start.month == today.month, 'fixture_week_month_boundary_requires_review')
    due = today + timedelta(days=2)
    for locale in ('vi', 'en'):
        schema = f'chi43_send_{args.run_id}_{locale}'
        require(not query(db, 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (schema,)),
                'fixture_schema_already_exists')
        execute(db, f'CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        execute(db, f'CREATE TABLE `{schema}`._chi43_scope (run_id VARCHAR(12) PRIMARY KEY)')
        execute(db, f'INSERT INTO `{schema}`._chi43_scope VALUES (%s)', (args.run_id,))
        db.commit()
        for table in TABLES:
            execute(db, f'CREATE TABLE `{schema}`.`{table}` LIKE homewallet.`{table}`')
        execute(db, f'INSERT INTO `{schema}`.users (id,cognito_sub,email,display_name,preferred_locale) '
                'VALUES (16,%s,%s,%s,%s)', (f'chi43-send-{args.run_id}-{locale}', args.recipient, 'CHI43 synthetic member', locale))
        execute(db, f'INSERT INTO `{schema}`.households (id,name,owner_user_id,invite_code) VALUES (1,%s,16,%s)',
                (f'CHI43 E2E {args.run_id} {locale}', 'TEST' + args.run_id))
        execute(db, f"INSERT INTO `{schema}`.household_members (household_id,user_id,role) VALUES (1,16,'owner')")
        execute(db, f"INSERT INTO `{schema}`.categories (id,household_id,name,is_fixed) VALUES (1,1,'CHI43 synthetic category',0)")
        execute(db, f"INSERT INTO `{schema}`.budgets (id,household_id,period,income_estimate,savings_goal,source,status) "
                "VALUES (1,1,%s,1000000,0,'MANUAL','ACTIVE')", (today.strftime('%Y-%m'),))
        execute(db, f'INSERT INTO `{schema}`.budget_lines (budget_id,category_id,amount) VALUES (1,1,1000000)')
        execute(db, f'INSERT INTO `{schema}`.recurring_bills '
                '(id,household_id,name,category_id,due_day,expected_amount,remind_days_before,active) '
                'VALUES (1,1,%s,1,%s,100000,2,1)', (f'CHI43 acceptance {args.run_id}', due.day))
        for day, amount in ((start + timedelta(days=1), 600000), (start + timedelta(days=2), 300000)):
            execute(db, f'INSERT INTO `{schema}`.transactions '
                    '(household_id,member_id,occurred_on,total_amount,category_id,status,source,note) '
                    "VALUES (1,16,%s,%s,1,'CONFIRMED','MANUAL','CHI43 synthetic only')", (day, amount))
        execute(db, f'INSERT INTO `{schema}`.push_subscriptions '
                '(id,user_id,endpoint,endpoint_hash,p256dh,auth,status) '
                "SELECT id,user_id,endpoint,endpoint_hash,p256dh,auth,status FROM homewallet.push_subscriptions "
                "WHERE id=6 AND user_id=16 AND status='ACTIVE'")
        db.commit()
        execute(db, f"GRANT SELECT,INSERT,UPDATE,DELETE ON `{schema}`.* TO 'hw_runtime'@'%'")
        emit('CHI43_SEND_FIXTURE_READY', schema=schema, locale=locale, period_key=today,
             report_week=start, recipient_sha256=hashlib.sha256(args.recipient.encode()).hexdigest(),
             source_subscription_id=6, source_user_id=16)


def inspect(db, args):
    for locale in ('vi', 'en'):
        schema = f'chi43_send_{args.run_id}_{locale}'
        scope(db, schema, args.run_id)
        runs = query(db, f'SELECT job_name,period_key,status FROM `{schema}`.job_runs ORDER BY job_name')
        notes = query(db, f'SELECT id,user_id,type,event_key,read_at FROM `{schema}`.notifications ORDER BY id')
        alerts = query(db, f'SELECT threshold,sent_at FROM `{schema}`.alert_state')
        emit('CHI43_SEND_FIXTURE_STATE', schema=schema, locale=locale,
             job_runs=runs, notifications=notes, alerts=alerts)


def cleanup(db, args):
    for locale in ('vi', 'en'):
        schema = f'chi43_send_{args.run_id}_{locale}'
        if not query(db, 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (schema,)):
            emit('CHI43_SEND_SCHEMA_ABSENT', schema=schema)
            continue
        scope(db, schema, args.run_id)
        grants = query(db, 'SELECT PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES '
                       'WHERE TABLE_SCHEMA=%s AND GRANTEE=%s', (schema, "'hw_runtime'@'%'"))
        if grants:
            execute(db, f"REVOKE SELECT,INSERT,UPDATE,DELETE ON `{schema}`.* FROM 'hw_runtime'@'%'")
        execute(db, f'DROP DATABASE `{schema}`')
        require(not query(db, 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (schema,)),
                'fixture_schema_cleanup_failed')
        emit('CHI43_SEND_SCHEMA_REMOVED', schema=schema, runtime_grants_removed=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=('prepare', 'inspect', 'cleanup'))
    p.add_argument('--run-id', required=True)
    p.add_argument('--recipient')
    args = p.parse_args()
    require(re.fullmatch('[a-f0-9]{12}', args.run_id), 'invalid_run_id')
    from app.config import load_config
    from app.db import connect
    config = load_config()
    require(config['DB_USER'] != 'hw_runtime', 'bootstrap_admin_required')
    db = connect(config)
    try:
        globals()[args.mode](db, args)
        return 0
    except Exception as exc:
        db.rollback()
        reason = str(exc) if type(exc) is RuntimeError else None
        emit('CHI43_SEND_FIXTURE_FAILED', mode=args.mode, error_type=type(exc).__name__,
             reason=reason, database_error_code=exc.args[0] if exc.args and isinstance(exc.args[0], int) else None,
             trace=[{'function':x.name,'line':x.lineno} for x in traceback.extract_tb(exc.__traceback__)][-5:])
        return 1
    finally:
        db.close()


if __name__ == '__main__':
    raise SystemExit(main())
