import json
import logging
import urllib.error
import urllib.request

from src.config import Config

log = logging.getLogger(__name__)


class ApiClient:
    """Send sensor readings to a REST API endpoint."""

    def __init__(self, base_url: str, api_key: str, node_uuid: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._node_uuid = node_uuid
        self._timeout = Config.API_TIMEOUT_SECONDS

        if not api_key:
            log.warning("API_KEY is not set – requests will be sent without authentication.")
        if not node_uuid:
            log.warning("NODE_UUID is not set – readings cannot be attributed to a node.")
        if not self._base_url.startswith("https://"):
            log.warning("API_BASE_URL is not HTTPS – API key will be sent in cleartext.")

    def send_reading(self, reading: dict) -> None:
        """Raises RuntimeError on any HTTP or network failure so the caller can decide
        whether to retry."""
        url = f"{self._base_url}/readings"
        payload = json.dumps({"node_uuid": self._node_uuid, **reading}, default=str).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Api-Key": self._api_key,
                "User-Agent": "enviro-node/1.0",
            },
        )

        log.debug("POST %s  payload=%s", url, reading)

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                log.debug("API response %d", resp.status)
        except urllib.error.HTTPError as exc:
            body = exc.read(256).decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} from API ({url}): {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error reaching API ({url}): {exc.reason}") from exc
