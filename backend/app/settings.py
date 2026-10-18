"""Environment settings, read once from backend/.env."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ledger:ledger@localhost:5432/ledger")
RETELL_API_KEY = os.getenv("RETELL_API_KEY", "")
TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
JEV_MODEL = os.getenv("JEV_MODEL", "jev-1.13.0")
JEV_MIN_CONFIDENCE = float(os.getenv("JEV_MIN_CONFIDENCE", "0.6"))
NURSE_LINE = os.getenv("NURSE_LINE", "+12139940320")
VERIFY_RETELL_SIGNATURE = os.getenv("VERIFY_RETELL_SIGNATURE", "1") != "0"
SUPERVISOR_ENGINE = os.getenv("SUPERVISOR_ENGINE", "1") != "0"
