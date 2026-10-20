import os, pathlib, re, sys
import pymysql
from app import config  # noqa: F401  (nạp .env khi chạy cục bộ)

MIG = pathlib.Path(__file__).resolve().parent.parent / "db" / "migrations"

def connect():
    kw = dict(host=os.environ["DB_HOST"], port=int(os.getenv("DB_PORT", "3306")),
              user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
              charset="utf8mb4", connect_timeout=10)
    if os.getenv("DB_SSL_CA"):  # trên AWS; cục bộ không có TLS
        kw.update(ssl_ca=os.environ["DB_SSL_CA"], ssl_verify_cert=True, ssl_verify_identity=True)
    return pymysql.connect(**kw)

def statements(sql):
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in sql.split(";") if s.strip()]

def main():
    conn = connect(); cur = conn.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS homewallet CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute("USE homewallet")
    cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version VARCHAR(100) PRIMARY KEY, applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    cur.execute("SELECT version FROM schema_migrations")
    done = {r[0] for r in cur.fetchall()}
    cur.execute("SHOW TABLES LIKE 'users'")
    if not done and cur.fetchone():   # DB cũ đã nạp bằng schema.sql: coi 001 là đã áp dụng
        cur.execute("INSERT INTO schema_migrations (version) VALUES ('001_init.sql')")
        done.add("001_init.sql"); conn.commit()
    for f in sorted(MIG.glob("*.sql")):
        if f.name in done:
            continue
        for stmt in statements(f.read_text(encoding="utf-8-sig")):
            cur.execute(stmt)
        cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.name,))
        conn.commit(); print("đã áp dụng", f.name)
    print("Xong.")
    return 0

if __name__ == "__main__":
    sys.exit(main())