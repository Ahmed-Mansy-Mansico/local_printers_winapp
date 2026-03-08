"""
Local Printers Windows App – Socket.IO client.

Connects to a Frappe/ERPNext site via Socket.IO, listens for
'sales_invoice_submitted' events that carry pre-rendered HTML,
and silently prints each job to the designated local printer.
"""

import json
import sys
import logging
from threading import Thread

import socketio
import requests
import win32print

from printer_handlers import print_jobs

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Socket.IO client
# ---------------------------------------------------------------------------
sio = socketio.Client(reconnection=True, reconnection_delay=5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_config(config_path: str) -> dict:
    """Load configuration from a JSON file."""
    try:
        with open(config_path, "r") as fh:
            data = json.load(fh)
        log.info("Configuration loaded from %s", config_path)
        return data
    except FileNotFoundError:
        sys.exit(f"Configuration file {config_path} not found.")
    except json.JSONDecodeError as exc:
        sys.exit(f"Invalid JSON in config file: {exc}")


def get_local_printers() -> list[str]:
    """Return names of locally-installed printers."""
    return [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)]


def send_printers_to_server(printers: list[str], cfg: dict):
    """Register local printer names on the Frappe server."""
    headers = {
        "Authorization": f"token {cfg['API_KEY']}:{cfg['API_SECRET']}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            f"{cfg['FRAPPE_SOCKET_URL']}/api/method/local_printers.utils.save_printers_data",
            json={"printers": printers},
            headers=headers,
            timeout=30,
        )
        if resp.ok:
            log.info("Printers data sent to server.")
        else:
            log.warning("Failed to send printers (%s): %s", resp.status_code, resp.text)
    except requests.RequestException as exc:
        log.error("Error sending printers to server: %s", exc)


def fetch_session_cookies(cfg: dict) -> str | None:
    """Log in and return a cookie header string."""
    try:
        resp = requests.post(cfg["LOGIN_URL"], data=cfg["AUTH_DATA"], timeout=30)
        resp.raise_for_status()
        cookie_header = "; ".join(f"{k}={v}" for k, v in resp.cookies.items())
        log.info("Login successful.")
        return cookie_header
    except requests.RequestException as exc:
        log.error("Login failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Socket.IO event handlers
# ---------------------------------------------------------------------------
@sio.event
def connect():
    log.info("Connected to server.")
    printers = get_local_printers()
    log.info("Local printers: %s", printers)
    send_printers_to_server(printers, config_data)


@sio.event
def connect_error(data):
    log.error("Connection error: %s", data)


@sio.event
def disconnect():
    log.warning("Disconnected from server.")


@sio.on("sales_invoice_submitted")
def handle_sales_invoice_submitted(data):
    """
    Receive a list of print-job dicts from the server.
    Each dict contains:
      - html          : fully-rendered, ready-to-print HTML
      - printer       : target printer name
      - printer_ip    : (optional) network printer IP
      - invoice_name  : Sales Invoice name (for logging)
      - is_cashier    : whether this is the cashier copy
      - print_format  : name of the print format used
    """
    if not data:
        log.warning("Received empty print data, ignoring.")
        return

    first = data[0] if isinstance(data, list) else data
    invoice = first.get("invoice_name", "unknown")
    count = len(data) if isinstance(data, list) else 1
    log.info("Received %d print job(s) for invoice %s", count, invoice)

    print_jobs(data, config_data)


# ---------------------------------------------------------------------------
# Connection logic
# ---------------------------------------------------------------------------
def run_socketio_client(cfg: dict):
    """Connect to the Frappe realtime server."""
    cookie_header = fetch_session_cookies(cfg)
    if not cookie_header:
        log.error("Cannot connect without valid session cookies.")
        return

    headers = {"Cookie": cookie_header}
    try:
        sio.connect(
            cfg["FRAPPE_SOCKET_URL"],
            headers=headers,
            transports=["websocket"],
        )
        sio.wait()
    except Exception as exc:
        log.error("Socket.IO connection error: %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    config_path = "config.json"
    config_data = load_config(config_path)

    # Single thread – connect and listen
    Thread(target=run_socketio_client, args=(config_data,), daemon=True).start()

    # Keep main thread alive
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down…")
        sio.disconnect()
