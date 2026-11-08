# Dev runtime database credentials rollout (#32)

The rollout uses two Terraform applies so application tasks keep working while
the restricted MySQL account is created:

1. `enable_db_runtime_setup=true`, `use_db_runtime_credentials=false` creates
   the runtime secret and bootstrap task. API, worker, and jobs continue using
   the current database secret. The separate migration execution role retains
   access to the admin database secret.
2. After the bootstrap task succeeds and the grants are reviewed,
   `use_db_runtime_credentials=true` changes API, worker, and jobs to the
   `hw_runtime` username/password fields. Their shared execution role loses
   access to the admin database secret. The migration execution role keeps it.

After phase 2 was accepted on dev, both variables default to `true` so later
Terraform plans preserve the deployed runtime secret and credentials. Override
them explicitly for the staged rollout in a new environment. Terraform
validation rejects using runtime credentials before runtime setup is enabled.

## Phase 1: prepare and bootstrap

1. Confirm the latest migrations are applied and RDS is available.
2. Review a Terraform plan with `enable_db_runtime_setup=true` and
   `use_db_runtime_credentials=false`. The plan must preserve the existing DB
   and admin secret, keep service task definitions on the admin secret, and add
   the runtime bootstrap resources and separate migration execution role.
3. Apply the reviewed plan. Terraform creates `hw/dev/db-runtime` without a
   secret value. Set its JSON secret value in Secrets Manager to the exact
   schema below, using a unique password of at least 24 characters:

   ```json
   {
     "username": "hw_runtime",
     "password": "<unique password of at least 24 characters>"
   }
   ```

   Do not put the password in Terraform variables, shell history, logs, or chat.
4. Run the `hw-db-runtime-bootstrap` ECS task once in the private/app network,
   using the task definition created by phase 1. It reads the admin DB secret
   and the runtime secret, creates `hw_runtime` if absent, verifies the runtime
   credentials over TLS, and applies only the reviewed statements in
   `backend/db/bootstrap/runtime-grants.sql`.
5. Require stopped exit code `0` and the success log. If the user already
   exists, the task verifies the supplied password and does not reset it. On
   failure, keep services on the existing DB secret and investigate before
   retrying.

## Phase 2: switch application tasks

1. Keep `enable_db_runtime_setup=true`; set
   `use_db_runtime_credentials=true`.
2. Review the new plan. API, worker, and jobs must reference the runtime
   secret's `username` and `password` JSON keys. The compute execution role
   must no longer read the admin DB secret. Migration/bootstrap execution roles
   must retain only the access needed for their separate tasks.
3. Apply the reviewed plan and deploy the matching API/worker image through
   Deploy Dev. Verify API health, worker stability, and one controlled jobs
   task before declaring the rollout complete.
4. Verify grants read-only as the database administrator. Runtime must not
   have DDL privileges or access to `schema_migrations`.

## Rollback

Set `use_db_runtime_credentials=false`, review the plan, and apply to return
API, worker, and jobs to the existing DB secret. Keep
`enable_db_runtime_setup=true` and preserve the runtime account/secret for
investigation. Do not rotate or delete the runtime password/account as part of
rollback. The Terraform secret has `prevent_destroy` enabled.
