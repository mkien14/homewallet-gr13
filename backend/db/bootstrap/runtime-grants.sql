-- Bootstrap only. Run after hw_runtime has been created.
-- Shared runtime account for API, worker and jobs.
-- Review against application SQL before rollout.

GRANT SELECT, INSERT, UPDATE
ON homewallet.users TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE
ON homewallet.households TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, DELETE
ON homewallet.household_members TO 'hw_runtime'@'%';

GRANT SELECT, DELETE
ON homewallet.categories TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE
ON homewallet.receipts TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE
ON homewallet.transactions TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, DELETE
ON homewallet.transaction_items TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE
ON homewallet.budgets TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, DELETE
ON homewallet.budget_lines TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE
ON homewallet.recurring_bills TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, UPDATE
ON homewallet.alert_state TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, UPDATE
ON homewallet.job_runs TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, UPDATE
ON homewallet.notifications TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE
ON homewallet.push_subscriptions TO 'hw_runtime'@'%';

GRANT INSERT
ON homewallet.audit_logs TO 'hw_runtime'@'%';

GRANT SELECT, INSERT, UPDATE
ON homewallet.community_posts TO 'hw_runtime'@'%';
