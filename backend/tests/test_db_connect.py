from app import db


def test_shared_connect_uses_database_settings_and_tls(monkeypatch):
    captured = {}
    sentinel = object()

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(db.pymysql, "connect", fake_connect)
    config = {
        "DB_HOST": "db.example.test",
        "DB_PORT": 3306,
        "DB_USER": "worker",
        "DB_PASSWORD": "test-password",
        "DB_NAME": "homewallet",
        "DB_SSL_CA": "/etc/ssl/ca.pem",
    }

    assert db.connect(config) is sentinel
    assert captured == {
        "host": "db.example.test",
        "port": 3306,
        "user": "worker",
        "password": "test-password",
        "database": "homewallet",
        "charset": "utf8mb4",
        "autocommit": False,
        "cursorclass": db.pymysql.cursors.DictCursor,
        "connect_timeout": 5,
        "ssl_ca": "/etc/ssl/ca.pem",
        "ssl_verify_cert": True,
        "ssl_verify_identity": True,
    }


def test_shared_connect_can_omit_database_for_migrations(monkeypatch):
    captured = {}
    monkeypatch.setattr(db.pymysql, "connect", lambda **kwargs: captured.update(kwargs))

    db.connect({
        "DB_HOST": "localhost",
        "DB_PORT": 3306,
        "DB_USER": "root",
        "DB_PASSWORD": "",
        "DB_NAME": "homewallet",
        "DB_SSL_CA": None,
    }, database=False)

    assert "database" not in captured
