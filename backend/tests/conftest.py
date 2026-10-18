import pytest

from app import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db.reset_connection(str(tmp_path / "test.db"))
    db.conn()
    yield
    db.reset_connection()
