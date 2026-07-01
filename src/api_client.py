import json
import logging
import urllib.error
import urllib.request

from src.config import Config

log = logging.getLogger(__name__)


class ApiClient:
    """Send sensor readings to the enviro-hub REST API (POST /api/v1/sensor-data)."""

    def __init__(self, base_url: str, api_token: str, node_uuid: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._node_uuid = node_uuid
        self._timeout = Config.API_TIMEOUT_SECONDS

        if not api_token:
            log.warning("API_BEARER_TOKEN is not set – requests will be sent without authentication.")
        if not node_uuid:
            log.warning("NODE_UUID is not set – readings cannot be attributed to a node.")
        if not self._base_url.startswith("https://"):
            log.warning("API_BASE_URL is not HTTPS – bearer token will be sent in cleartext.")

    def _build_payload(self, reading: dict) -> dict:
        """Selects the fields enviro-hub's StoreSensorDataRequest contract expects,
        dropping node-local bookkeeping (id, submitted_at, gas_resistance, iaq, mhz_temperature)."""
        pressure = reading.get("pressure")
        return {
            "node_uuid": self._node_uuid,
            "temperature": reading.get("temperature"),
            "humidity": reading.get("humidity"),
            "pressure": round(pressure) if pressure is not None else None,
            "carbon_dioxide": reading.get("carbon_dioxide"),
            "measured_at": reading.get("measured_at"),
        }

    def send_reading(self, reading: dict) -> None:
        """Raises RuntimeError on any HTTP or network failure so the caller can decide
        whether to retry."""
        url = f"{self._base_url}/api/v1/sensor-data"
        payload_dict = self._build_payload(reading)
        payload = json.dumps(payload_dict, default=str).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_token}",
                "User-Agent": "enviro-node/1.0",
            },
        )

        log.debug("POST %s  payload=%s", url, payload_dict)

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                log.debug("API response %d", resp.status)
        except urllib.error.HTTPError as exc:
            body = exc.read(256).decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} from API ({url}): {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error reaching API ({url}): {exc.reason}") from exc
