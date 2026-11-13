import os
import pathlib
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pymysql

from app.config import load_config
from app.db import connect


GRANTS_FILE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "db"
    / "bootstrap"
    / "runtime-grants.sql"
)


def grant_statements():
    sql = GRANTS_FILE.read_text(encoding="utf-8")
    sql = re.sub(r"--[^\n]*", "", sql)

    statements = [
        statement.strip()
        for statement in sql.split(";")
        if statement.strip()
    ]

    if not statements:
        raise ValueError("Empty grants file")

    pattern = re.compile(
        r"GRANT\s+"
        r"(?:SELECT|INSERT|UPDATE|DELETE)"
        r"(?:\s*,\s*(?:SELECT|INSERT|UPDATE|DELETE))*"
        r"\s+ON\s+homewallet\.([a-z_]+)"
        r"\s+TO\s+'hw_runtime'@'%'",
        re.IGNORECASE,
    )

    result = []

    for statement in statements:
        match = pattern.fullmatch(statement)

        if not match:
            raise ValueError("Unexpected grant statement")

        if match.group(1).lower() == "schema_migrations":
            raise ValueError("Runtime cannot access migration tracking")

        result.append((statement, match.group(1)))

    return result


def runtime_config(admin_config, password):
    config = dict(admin_config)
    config["DB_NAME"] = "homewallet"
    config["DB_USER"] = "hw_runtime"
    config["DB_PASSWORD"] = password
    return config


def main():
    admin_config = load_config()

    if not admin_config.get("DB_SSL_CA"):
        raise ValueError("TLS CA is required")

    if admin_config["DB_USER"] == "hw_runtime":
        raise ValueError("Bootstrap requires a separate admin credential")

    password = os.environ["RUNTIME_DB_PASSWORD"]

    if len(password) < 24:
        raise ValueError("Runtime password must have at least 24 characters")

    grants = grant_statements()
    admin = connect(admin_config)

    try:
        # Check that all required tables exist before changing accounts.
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT TABLE_NAME FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s",
                ("homewallet",),
            )
            tables = {row["TABLE_NAME"] for row in cursor.fetchall()}

            required = {table for _, table in grants}

            if not required.issubset(tables):
                raise ValueError("Required tables are missing; run migrations first")

            cursor.execute(
                "SELECT 1 AS present FROM mysql.user "
                "WHERE User = %s AND Host = %s",
                ("hw_runtime", "%"),
            )
            existed = cursor.fetchone() is not None

            if not existed:
                cursor.execute(
                    "CREATE USER 'hw_runtime'@'%%' "
                    "IDENTIFIED BY %s REQUIRE SSL",
                    (password,),
                )

        config = runtime_config(admin_config, password)

        # Verify the supplied credential before granting privileges.
        # Do not reset the password of an existing account.
        probe = connect(config, database=False)
        probe.close()

        with admin.cursor() as cursor:
            for statement, _ in grants:
                cursor.execute(statement)

        # Verify read access without returning application records.
        probe = connect(config)

        try:
            with probe.cursor() as cursor:
                for table in sorted(required):
                    cursor.execute(
                        f"SELECT 1 FROM `homewallet`.`{table}` LIMIT 0"
                    )
        finally:
            probe.close()

        if existed:
            print(
                "Bootstrap completed for existing account. "
                "Review existing grants before rollout."
            )
        else:
            print("Bootstrap completed for new runtime account.")

        return 0
    finally:
        admin.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except pymysql.MySQLError as error:
        code = error.args[0] if error.args else "unknown"
        print(
            f"Bootstrap failed: database error {code}. "
            "Review configuration; credentials were not printed.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    except (KeyError, ValueError, OSError):
        print(
            "Bootstrap failed: check environment, TLS, grants file "
            "and required tables. Credentials were not printed.",
            file=sys.stderr,
        )
        raise SystemExit(1)
