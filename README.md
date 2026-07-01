# Enviro Node

Reads a **BME680** (temperature, humidity, pressure, gas resistance) and
an **MH-Z19** (CO₂) sensor, stores readings in a local **SQLite**
database via SQLAlchemy, then ships them to a configurable REST API.

Designed to be triggered by **cron**.

---

## Hardware wiring

### BME680 → Raspberry Pi (I²C)

| BME680 pin | Pi GPIO header         |
|------------|------------------------|
| VCC        | Pin 1  (3.3 V)         |
| GND        | Pin 6  (GND)           |
| SDA        | Pin 3  (GPIO 2 / SDA1) |
| SCL        | Pin 5  (GPIO 3 / SCL1) |

Verify after boot: `sudo i2cdetect -y 1` → should show address `0x76` or `0x77`.

### MH-Z19 → Raspberry Pi (UART)

| MH-Z19 pin | Pi GPIO header          |
|------------|-------------------------|
| Vin (5 V)  | Pin 2  (5 V)            |
| GND        | Pin 14 (GND)            |
| TXD        | Pin 10 (GPIO 15 / RXD)  |
| RXD        | Pin 8  (GPIO 14 / TXD)  |

Note: MH-Z19 TX → Pi RX and MH-Z19 RX → Pi TX (cross-over).

---

## Setup

### 1. Clone the repo

```bash
sudo git clone https://github.com/Neluxx/enviro-node.git /opt/enviro-node
sudo chown -R $USER:$USER /opt/enviro-node
```

To update later: `cd /opt/enviro-node && git pull`.

### 2. Install dependencies

```bash
sudo apt update
sudo apt install python3 python3-pip python3-serial python3-sqlalchemy python3-dotenv i2c-tools

# python3-bme680 may not be in Bookworm repos — fall back to pip if needed
sudo apt install python3-bme680 || pip3 install --break-system-packages bme680
```

Or install everything with pip:

```bash
pip3 install -r /opt/enviro-node/requirements.txt
```

### 3. Enable I²C and UART

```bash
sudo raspi-config
# Interface Options → I2C → Enable
# Interface Options → Serial Port → disable login shell, enable serial hardware
```

Add your user to the `dialout` group for UART access:
```bash
sudo usermod -aG dialout $USER
# Log out and back in for the group change to take effect
```

### 4. Set secrets

Copy the example env file and edit it:

```bash
cd /opt/enviro-node
cp .env.example .env
nano .env
chmod 640 .env
```

`Config` loads `<project_root>/.env` automatically via `python-dotenv` at
startup — no shell sourcing required.

### 5. Schedule with cron

```bash
crontab -e
```

Add:
```
*/10 * * * * /usr/bin/python3 /opt/enviro-node/main.py
```

---

## Testing manually

```bash
python3 /opt/enviro-node/main.py
```

---

## Configuration

All settings are environment variables. Set them in `<project_root>/.env`.

| Variable             | Default                   | Description                                          |
|----------------------|---------------------------|------------------------------------------------------|
| `API_BASE_URL`       | `https://api.example.com` | Base URL of your REST API (must be HTTPS)            |
| `API_BEARER_TOKEN`   | *(empty)*                 | API authentication token (sent as `Authorization: Bearer`) |
| `NODE_UUID`          | *(empty)*                 | Unique identifier for this node, sent with each row  |
| `MHZ19_PORT`         | `/dev/ttyAMA0`            | UART port for MH-Z19                                 |
| `API_TIMEOUT`        | `15`                      | HTTP request timeout (s)                             |
| `API_BATCH_SIZE`     | `50`                      | Max readings shipped per run                         |
| `API_MAX_FAILURES`   | `3`                       | Bail out after this many consecutive ship failures   |
| `LOG_MAX_BYTES`      | `1000000`                 | Rotate log file when it exceeds this size            |
| `LOG_BACKUP_COUNT`   | `5`                       | Number of rotated log files to keep                  |

---

## API contract

The app POSTs JSON to `<API_BASE_URL>/api/v1/sensor-data`, authenticated with
`Authorization: Bearer <API_BEARER_TOKEN>`. This matches the
[enviro-hub](https://github.com/Neluxx/enviro-hub) `StoreSensorDataRequest` contract.

```json
{
  "node_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "temperature": 22.45,
  "humidity": 48.12,
  "pressure": 1013,
  "carbon_dioxide": 812,
  "measured_at": "2026-05-13T08:00:00+00:00"
}
```

Expected success response: HTTP `201`.
Failed deliveries remain `submitted_at = NULL` in the database and are retried
automatically on the next cron run. After `API_MAX_FAILURES` consecutive
failures within a single run, the loop bails out early to avoid hammering
a downed API.

---

## File layout

```
enviro-node/
├── main.py             # Python entry point
├── requirements.txt
├── README.md
├── data/               # SQLite DB and log files
└── src/
    ├── __init__.py
    ├── config.py       # All settings and environment variables
    ├── database.py     # Database configuration
    ├── sensors.py      # BME680 and MH-Z19 sensors
    └── api_client.py   # API client 
```

---

## Logs

```bash
tail -f /opt/enviro-node/data/sensor_logger.log
```

Log rotation is handled in-process via `RotatingFileHandler`
(`LOG_MAX_BYTES` per file, `LOG_BACKUP_COUNT` rotated files kept).

A `data/main.lock` file prevents overlapping cron runs — if a run is
still in progress when the next tick fires, the second invocation
exits immediately with a warning instead of contending for the UART.

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `BME680 init failed` | `sudo i2cdetect -y 1` — is the sensor detected? Check wiring and that I²C is enabled. |
| `MH-Z19 UART error` | `ls -l /dev/ttyAMA0` — does the port exist? Reboot after `config.txt` changes. |
| `Permission denied /dev/ttyAMA0` | `groups $USER` — ensure `dialout` is listed. Log out and back in after `usermod`. |
| API errors | Check `API_BASE_URL` and `API_BEARER_TOKEN` in `<project_root>/.env`. Unsent readings are retried automatically. |
| Cron not firing | `grep CRON /var/log/syslog` to confirm cron is running. Verify the env file path is correct. |