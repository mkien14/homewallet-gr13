"""Shared database claim/finish helpers for scheduled jobs."""

import pymysql

RUNNING_STALE_AFTER_SECONDS = 1800


def claim_job_run(db, job_name, period_key):
    """Claim a job key once, allowing failed or stale attempts to be retried."""
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO job_runs (job_name, period_key, status) "
                "VALUES (%s, %s, 'RUNNING')",
                (job_name, period_key),
            )
        db.commit()
        return True
    except pymysql.err.IntegrityError as exc:
        db.rollback()
        if not exc.args or exc.args[0] != 1062:
            raise

    with db.cursor() as cur:
        cur.execute(
            "SELECT status, TIMESTAMPDIFF(SECOND, started_at, CURRENT_TIMESTAMP) AS age "
            "FROM job_runs WHERE job_name = %s AND period_key = %s FOR UPDATE",
            (job_name, period_key),
        )
        existing = cur.fetchone()
        if existing is None:
            db.rollback()
            return claim_job_run(db, job_name, period_key)
        if existing["status"] == "SUCCEEDED" or (
            existing["status"] == "RUNNING"
            and existing["age"] < RUNNING_STALE_AFTER_SECONDS
        ):
            db.commit()
            return False
        cur.execute(
            "UPDATE job_runs SET status = 'RUNNING', started_at = CURRENT_TIMESTAMP "
            "WHERE job_name = %s AND period_key = %s",
            (job_name, period_key),
        )
    db.commit()
    return True


def finish_job_run(db, job_name, period_key, status):
    """Persist a terminal state for a claimed job key."""
    if status not in {"SUCCEEDED", "FAILED"}:
        raise ValueError("job status must be SUCCEEDED or FAILED")
    try:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE job_runs SET status = %s "
                "WHERE job_name = %s AND period_key = %s",
                (status, job_name, period_key),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
