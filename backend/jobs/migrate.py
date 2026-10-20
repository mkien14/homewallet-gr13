import pathlib
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import load_config
from app.db import connect


MIG = pathlib.Path(__file__).resolve().parent.parent / "db" / "migrations"


def statements(sql):
    sql = re.sub(r"--[^\n]*", "", sql)
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def main():
    conn = connect(load_config(), database=False)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "CREATE DATABASE IF NOT EXISTS homewallet "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute("USE homewallet")
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version VARCHAR(100) PRIMARY KEY, "
                "applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            cursor.execute("SELECT version FROM schema_migrations")
            done = {row["version"] for row in cursor.fetchall()}
            cursor.execute("SHOW TABLES LIKE 'users'")
            if not done and cursor.fetchone():
                cursor.execute(
                    "INSERT INTO schema_migrations (version) VALUES ('001_init.sql')"
                )
                done.add("001_init.sql")
                conn.commit()
            for migration in sorted(MIG.glob("*.sql")):
                if migration.name in done:
                    continue
                for statement in statements(migration.read_text(encoding="utf-8-sig")):
                    cursor.execute(statement)
                cursor.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (migration.name,),
                )
                conn.commit()
                print("đã áp dụng", migration.name)
        print("Xong.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
