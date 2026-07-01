import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Engine, Index, create_engine, select
from sqlalchemy.event import listen
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # BME680
    temperature: Mapped[float | None] = mapped_column(default=None)
    humidity: Mapped[float | None] = mapped_column(default=None)
    pressure: Mapped[float | None] = mapped_column(default=None)
    gas_resistance: Mapped[float | None] = mapped_column(default=None)
    iaq: Mapped[float | None] = mapped_column(default=None)

    # MH-Z19
    carbon_dioxide: Mapped[int | None] = mapped_column(default=None)
    mhz_temperature: Mapped[float | None] = mapped_column(default=None)

    # Timestamps
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        Index("idx_unsubmitted", "submitted_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "pressure": self.pressure,
            "gas_resistance": self.gas_resistance,
            "iaq": self.iaq,
            "carbon_dioxide": self.carbon_dioxide,
            "mhz_temperature": self.mhz_temperature,
            "measured_at": self.measured_at.isoformat() if self.measured_at else None,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<SensorReading id={self.id} measured_at={self.measured_at} "
            f"co2={self.carbon_dioxide} temp={self.temperature}>"
        )


def _set_sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    """Runs on every new connection — pragmas are per-connection in SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    def __init__(self, db_path: Path | str) -> None:
        url = f"sqlite:///{db_path}"
        self._engine: Engine = create_engine(url, echo=False)
        listen(self._engine, "connect", _set_sqlite_pragmas)
        self._Session = sessionmaker(bind=self._engine)
        log.debug("Database engine created: %s", url)

    def initialize(self) -> None:
        Base.metadata.create_all(self._engine)
        log.info("Database schema verified / created.")

    def close(self) -> None:
        self._engine.dispose()
        log.debug("Database engine disposed.")

    def insert_reading(self, data: dict, measured_at: datetime) -> int:
        reading = SensorReading(
            measured_at=measured_at,
            temperature=data.get("temperature"),
            humidity=data.get("humidity"),
            pressure=data.get("pressure"),
            gas_resistance=data.get("gas_resistance"),
            iaq=data.get("iaq"),
            carbon_dioxide=data.get("carbon_dioxide"),
            mhz_temperature=data.get("mhz_temperature"),
        )
        with self._Session() as session:
            session.add(reading)
            session.commit()
            session.refresh(reading)
            return reading.id

    def mark_sent(self, row_id: int) -> None:
        with self._Session() as session:
            reading = session.get(SensorReading, row_id)
            if reading:
                reading.submitted_at = datetime.now(timezone.utc)
                session.commit()

    def get_unsent_readings(self, limit: int = 50) -> list[dict]:
        stmt = (
            select(SensorReading)
            .where(SensorReading.submitted_at.is_(None))
            .order_by(SensorReading.measured_at.asc())
            .limit(limit)
        )
        with self._Session() as session:
            rows = session.scalars(stmt).all()
            return [r.to_dict() for r in rows]
