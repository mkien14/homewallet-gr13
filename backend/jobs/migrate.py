import os
import pathlib
import re
import sys

import pymysql

SCHEMA = pathlib.Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def connect():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        charset="utf8mb4",
        ssl_ca="/etc/ssl/rds-global-bundle.pem",  # xác thực chứng chỉ của RDS
        ssl_verify_cert=True,
        ssl_verify_identity=True,
        connect_timeout=10,
    )


def split_statements(sql):
    sql = re.sub(r"--[^\n]*", "", sql)  # bỏ chú thích
    return [s.strip() for s in sql.split(";") if s.strip()]


def main():
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SHOW STATUS LIKE 'Ssl_cipher'")
        print("TLS:", cur.fetchone())

        cur.execute("SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'homewallet'")
        if cur.fetchone()[0] > 0:
            print("Schema đã tồn tại, bỏ qua.")
            return 0

        for stmt in split_statements(SCHEMA.read_text(encoding="utf-8-sig")):
            cur.execute(stmt)
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'homewallet'")
        tables = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM homewallet.categories")
        cats = cur.fetchone()[0]
        print(f"Xong: {tables} bảng, {cats} danh mục")
    return 0


if __name__ == "__main__":
    sys.exit(main())