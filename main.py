#!/usr/bin/env python3
"""Enviro Node — cron-driven, one read/store/ship cycle per run."""

import fcntl
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.api_client import ApiClient
from src.config import Config
from src.database import Database
from src.sensors import BME680Sensor, MHZ19Sensor, SensorError

log = logging.getLogger("main")


def configure_logging() -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.handlers.RotatingFileHandler(
                Config.LOG_FILE,
                maxBytes=Config.LOG_MAX_BYTES,
                backupCount=Config.LOG_BACKUP_COUNT,
            ),
        ],
    )


def collect_and_store(bme: BME680Sensor, mhz: MHZ19Sensor, db: Database) -> None:
    """Skips storage only if both sensors fail."""
    recorded_at = datetime.now(timezone.utc)
    bme_data, mhz_data = None, None

    try:
        bme_data = bme.read()
        log.debug("BME680: %s", bme_data)
    except SensorError as exc:
        log.error("BME680 read failed: %s", exc)

    try:
        mhz_data = mhz.read()
        log.debug("MH-Z19: %s", mhz_data)
    except SensorError as exc:
        log.error("MH-Z19 read failed: %s", exc)

    if bme_data is None and mhz_data is None:
        log.warning("Both sensors failed – nothing stored.")
        return

    reading = {**(bme_data or {}), **(mhz_data or {})}
    row_id = db.insert_reading(reading, recorded_at=recorded_at)
    log.info("Stored reading id=%d  data=%s", row_id, reading)


def ship_pending(db: Database, api: ApiClient) -> None:
    """Bails after API_MAX_CONSECUTIVE_FAILURES so a downed API doesn't cause us
    to fire the whole batch and log every failure individually."""
    pending = db.get_unsent_readings(limit=Config.API_BATCH_SIZE)
    if not pending:
        log.debug("No unsent readings.")
        return

    log.info("Shipping %d pending reading(s) to API.", len(pending))
    consecutive_failures = 0
    for row in pending:
        try:
            api.send_reading(row)
            db.mark_sent(row["id"])
            consecutive_failures = 0
            log.debug("Sent reading id=%d", row["id"])
        except Exception as exc:  # noqa: BLE001
            consecutive_failures += 1
            log.warning("Failed to send reading id=%d: %s", row["id"], exc)
            if consecutive_failures >= Config.API_MAX_CONSECUTIVE_FAILURES:
                log.warning(
                    "Aborting ship loop after %d consecutive failures – will retry next run.",
                    consecutive_failures,
                )
                return


def acquire_lock(lock_path: Path):
    """Returns the open file handle on success — caller must keep it alive,
    since closing the fd releases the lock. Returns None if another instance holds it."""
    fp = open(lock_path, "w")
    try:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fp.close()
        return None
    return fp


def main() -> None:
    configure_logging()

    lock_fp = acquire_lock(Config.LOCK_FILE)
    if lock_fp is None:
        log.warning("Another instance is already running – exiting.")
        return

    log.info("=== Sensor run starting ===")

    db = Database(Config.DB_PATH)
    db.initialize()

    bme = BME680Sensor()
    mhz = MHZ19Sensor(Config.MHZ19_SERIAL_PORT)
    api = ApiClient(Config.API_BASE_URL, Config.API_BEARER_TOKEN, Config.NODE_UUID)

    collect_and_store(bme, mhz, db)
    ship_pending(db, api)

    db.close()
    log.info("=== Sensor run complete ===")


if __name__ == "__main__":
    main()
