import logging
import time

log = logging.getLogger(__name__)


class SensorError(RuntimeError):
    """Raised whenever a sensor read fails for any reason."""


class BME680Sensor:
    """Wrapper for the Pimoroni bme680 Python library."""

    def __init__(self) -> None:
        try:
            import bme680  # type: ignore[import]
        except ImportError as exc:
            raise SensorError(
                "bme680 library not found. "
                "Install with: sudo apt install python3-bme680"
            ) from exc

        try:
            self._sensor = bme680.BME680(bme680.I2C_ADDR_PRIMARY)
        except Exception:
            try:
                self._sensor = bme680.BME680(bme680.I2C_ADDR_SECONDARY)
            except Exception as exc:
                raise SensorError(
                    f"BME680 init failed at both I2C addresses: {exc}"
                ) from exc

        # Recommended oversampling / filter settings (Bosch application note)
        self._sensor.set_humidity_oversample(bme680.OS_2X)
        self._sensor.set_pressure_oversample(bme680.OS_4X)
        self._sensor.set_temperature_oversample(bme680.OS_8X)
        self._sensor.set_filter(bme680.FILTER_SIZE_3)

        log.info("BME680 initialised.")

    def read(self) -> dict:
        try:
            deadline = time.monotonic() + 5.0
            while not self._sensor.get_sensor_data():
                if time.monotonic() >= deadline:
                    raise SensorError("BME680 did not produce data within 5 s.")
                time.sleep(0.1)

            return {
                "temperature": round(self._sensor.data.temperature, 2),
                "humidity": round(self._sensor.data.humidity, 2),
                "pressure": round(self._sensor.data.pressure, 2),
            }
        except SensorError:
            raise
        except Exception as exc:
            raise SensorError(f"BME680 read error: {exc}") from exc


class MHZ19Sensor:
    """Wrapper for the mh-z19 Python library."""

    def __init__(self, port: str = "/dev/ttyAMA0") -> None:
        try:
            import mh_z19  # type: ignore[import]
        except ImportError as exc:
            raise SensorError(
                "mh-z19 library not found. Install with: pip install mh-z19"
            ) from exc

        self._mh_z19 = mh_z19
        self._mh_z19.set_serialdevice(port)
        log.info("MH-Z19 configured on %s.", port)

    def read(self) -> dict:
        try:
            result = self._mh_z19.read()
        except Exception as exc:
            raise SensorError(f"MH-Z19 read error: {exc}") from exc

        if not result or "co2" not in result:
            raise SensorError("MH-Z19 read failed: no data returned.")

        co2_ppm = result["co2"]

        if co2_ppm < 400 or co2_ppm > 5000:
            log.warning("MH-Z19 CO2 value %d ppm is outside the expected range.", co2_ppm)

        return {
            "carbon_dioxide": co2_ppm,
        }
