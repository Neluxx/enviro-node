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
        except Exception as exc:
            raise SensorError(f"BME680 init failed: {exc}") from exc

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


_MHZ19_CMD_READ = bytes([0xFF, 0x01, 0x86, 0x00, 0x00, 0x00, 0x00, 0x00, 0x79])
_MHZ19_RESPONSE_LEN = 9


def _mhz19_checksum(packet: bytes) -> int:
    return (~sum(packet[1:8]) + 1) & 0xFF


class MHZ19Sensor:
    """Drive the MH-Z19 over UART using pyserial."""

    def __init__(self, port: str = "/dev/ttyAMA0") -> None:
        try:
            import serial  # type: ignore[import]
        except ImportError as exc:
            raise SensorError(
                "pyserial not found. Install with: sudo apt install python3-serial"
            ) from exc

        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2,
            )
            log.info("MH-Z19 opened on %s.", port)
        except Exception as exc:
            raise SensorError(f"MH-Z19 init failed on {port}: {exc}") from exc

    def read(self) -> dict:
        try:
            self._serial.reset_input_buffer()
            self._serial.write(_MHZ19_CMD_READ)
            self._serial.flush()
            response = self._serial.read(_MHZ19_RESPONSE_LEN)
        except Exception as exc:
            raise SensorError(f"MH-Z19 UART error: {exc}") from exc

        if len(response) != _MHZ19_RESPONSE_LEN:
            raise SensorError(
                f"MH-Z19 short read: expected {_MHZ19_RESPONSE_LEN} bytes, "
                f"got {len(response)}."
            )
        if response[0] != 0xFF or response[1] != 0x86:
            raise SensorError(
                f"MH-Z19 unexpected response header: {response[:2].hex()}"
            )
        if _mhz19_checksum(response) != response[8]:
            raise SensorError("MH-Z19 checksum mismatch.")

        co2_ppm = (response[2] << 8) | response[3]

        if co2_ppm < 400 or co2_ppm > 5000:
            log.warning("MH-Z19 CO2 value %d ppm is outside the expected range.", co2_ppm)

        return {
            "carbon_dioxide": co2_ppm,
        }
