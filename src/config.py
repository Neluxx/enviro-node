import os
from pathlib import Path

from dotenv import load_dotenv

_BASE_DIR = Path(__file__).resolve().parent.parent

# Load <project_root>/.env before Config reads any vars.
# Existing shell env vars win over file values.
load_dotenv(_BASE_DIR / ".env")


class Config:
    BASE_DIR = _BASE_DIR
    DATA_DIR = BASE_DIR / "data"
    DB_PATH = DATA_DIR / "sensor_data.db"
    LOG_FILE = DATA_DIR / "sensor_logger.log"
    LOCK_FILE = DATA_DIR / "main.lock"

    LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", "1000000"))  # 1 MB
    LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))

    NODE_UUID: str = os.getenv("NODE_UUID", "")

    MHZ19_SERIAL_PORT: str = os.getenv("MHZ19_PORT", "/dev/ttyAMA0")

    API_BASE_URL: str = os.getenv("API_BASE_URL", "https://api.example.com")
    API_KEY: str = os.getenv("API_KEY", "")
    API_TIMEOUT_SECONDS: int = int(os.getenv("API_TIMEOUT", "15"))
    API_BATCH_SIZE: int = int(os.getenv("API_BATCH_SIZE", "50"))
    API_MAX_CONSECUTIVE_FAILURES: int = int(os.getenv("API_MAX_FAILURES", "3"))
