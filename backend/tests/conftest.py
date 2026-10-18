import os

import psycopg

# Tests run against their own database and post fake Retell requests without signatures.
ADMIN_URL = os.getenv("TEST_ADMIN_DATABASE_URL", "postgresql://ledger:ledger@localhost:5432/ledger")
with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname = 'ledger_test'").fetchone():
        conn.execute("CREATE DATABASE ledger_test")

os.environ["DATABASE_URL"] = ADMIN_URL.rsplit("/", 1)[0] + "/ledger_test"
os.environ["VERIFY_RETELL_SIGNATURE"] = "0"
os.environ["SUPERVISOR_ENGINE"] = "0"
os.environ["TYPESAFE_API_KEY"] = ""  # unit tests never call the real Jev
