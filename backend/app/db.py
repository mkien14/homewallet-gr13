import pymysql
import pymysql.cursors
from flask import current_app, g


def connect(config, *, database=True):
    options = {
        "host": config["DB_HOST"],
        "port": config["DB_PORT"],
        "user": config["DB_USER"],
        "password": config["DB_PASSWORD"],
        "charset": "utf8mb4",
        "autocommit": False,
        "cursorclass": pymysql.cursors.DictCursor,
        "connect_timeout": 5,
    }
    if database and config.get("DB_NAME"):
        options["database"] = config["DB_NAME"]
    if config.get("DB_SSL_CA"):
        options.update(
            ssl_ca=config["DB_SSL_CA"],
            ssl_verify_cert=True,
            ssl_verify_identity=True,
        )
    return pymysql.connect(**options)


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config)
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()