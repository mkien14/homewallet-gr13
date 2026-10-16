import pymysql
import pymysql.cursors
from flask import current_app, g


def get_db():
    if "db" not in g:
        c = current_app.config
        kw = dict(
            host=c["DB_HOST"], port=c["DB_PORT"], user=c["DB_USER"],
            password=c["DB_PASSWORD"], database=c["DB_NAME"],
            charset="utf8mb4", autocommit=False,
            cursorclass=pymysql.cursors.DictCursor, connect_timeout=5,
        )
        if c.get("DB_SSL_CA"):  # trên AWS: TLS có xác thực chứng chỉ
            kw.update(ssl_ca=c["DB_SSL_CA"], ssl_verify_cert=True, ssl_verify_identity=True)
        g.db = pymysql.connect(**kw)
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()