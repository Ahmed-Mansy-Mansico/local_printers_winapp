"""
Local Printers Windows App – Socket.IO client.

Connects to a Frappe/ERPNext site via Socket.IO, listens for
'sales_invoice_submitted' events that carry pre-rendered HTML,
and silently prints each job to the designated local printer.
"""

import json
import sys
import os
import logging
from logging.handlers import RotatingFileHandler
from threading import Thread
from urllib.parse import urlparse

import socketio
import requests
import win32print

from printer_handlers import print_jobs

# ---------------------------------------------------------------------------
# Logging – file + console
# ---------------------------------------------------------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(APP_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

log = logging.getLogger("socket_app")
log.setLevel(logging.DEBUG)

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.DEBUG)
_console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
log.addHandler(_console_handler)

_file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "socket_app.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
log.addHandler(_file_handler)

# ---------------------------------------------------------------------------
# Socket.IO client
# ---------------------------------------------------------------------------
sio = socketio.Client(reconnection=True, reconnection_delay=5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_config(config_path: str) -> dict:
    """Load configuration from a JSON file."""
    print(f"[CONFIG] Loading config from '{config_path}' ...")
    try:
        with open(config_path, "r") as fh:
            data = json.load(fh)
        print(f"[CONFIG] ✅ Configuration loaded successfully.")
        log.info("Configuration loaded from %s", config_path)
        return data
    except FileNotFoundError:
        print(f"[CONFIG] ❌ Config file '{config_path}' NOT FOUND!")
        sys.exit(f"Configuration file {config_path} not found.")
    except json.JSONDecodeError as exc:
        print(f"[CONFIG] ❌ Invalid JSON: {exc}")
        sys.exit(f"Invalid JSON in config file: {exc}")


def get_local_printers() -> list[str]:
    """Return names of locally-installed printers."""
    return [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)]


def send_printers_to_server(printers: list[str], cfg: dict):
    """Register local printer names on the Frappe server."""
    print(f"[SERVER] Sending {len(printers)} printer(s) to server ...")
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
            print(f"[SERVER] ✅ Printers registered on server.")
            log.info("Printers data sent to server.")
        else:
            print(f"[SERVER] ⚠️  Server responded {resp.status_code}: {resp.text}")
            log.warning("Failed to send printers (%s): %s", resp.status_code, resp.text)
    except requests.RequestException as exc:
        print(f"[SERVER] ❌ Error sending printers: {exc}")
        log.error("Error sending printers to server: %s", exc)


def fetch_session_cookies(cfg: dict) -> str | None:
    """Log in and return a cookie header string."""
    print(f"[AUTH] Logging in to {cfg['LOGIN_URL']} ...")
    try:
        resp = requests.post(cfg["LOGIN_URL"], data=cfg["AUTH_DATA"], timeout=30)
        resp.raise_for_status()
        cookie_header = "; ".join(f"{k}={v}" for k, v in resp.cookies.items())
        print(f"[AUTH] ✅ Login successful.")
        log.info("Login successful.")
        return cookie_header
    except requests.RequestException as exc:
        print(f"[AUTH] ❌ Login FAILED: {exc}")
        log.error("Login failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Socket.IO event handlers (registered dynamically with namespace in main)
# ---------------------------------------------------------------------------
def on_connect():
    print(f"\n[SOCKET] ✅ Connected to server!")
    log.info("Connected to server.")
    printers = get_local_printers()
    print(f"[SOCKET] Local printers detected: {printers}")
    log.info("Local printers: %s", printers)
    send_printers_to_server(printers, config_data)
    print(f"[SOCKET] Listening for 'sales_invoice_submitted' events ...\n")


def on_connect_error(data):
    print(f"[SOCKET] ❌ Connection error: {data}")
    log.error("Connection error: %s", data)


def on_disconnect():
    print(f"[SOCKET] ⚠️  Disconnected from server.")
    log.warning("Disconnected from server.")


def handle_sales_invoice_submitted(data):
    """
    Receive a list of print-job dicts from the server.
    Each dict contains:
      - pdf_base64    : base64-encoded PDF (ready to print)
      - printer       : target printer name
      - printer_ip    : (optional) network printer IP
      - invoice_name  : Sales Invoice name (for logging)
      - is_cashier    : whether this is the cashier copy
      - print_format  : name of the print format used
    """
    print(f"\n{'*'*60}")
    print(f"[EVENT] 📨 Received 'sales_invoice_submitted' event from ERP!")
    print(f"{'*'*60}")
    log.info("Received 'sales_invoice_submitted' event.")

    if not data:
        print(f"[EVENT] ⚠️  Data is EMPTY – nothing to print.")
        log.warning("Received empty print data, ignoring.")
        return

    jobs = data if isinstance(data, list) else [data]
    count = len(jobs)
    first = jobs[0]
    invoice = first.get("invoice_name", "unknown")

    print(f"[EVENT] Invoice     : {invoice}")
    print(f"[EVENT] Total jobs  : {count}")
    for j in jobs:
        print(f"[EVENT]   -> printer='{j.get('printer')}' format='{j.get('print_format')}' cashier={j.get('is_cashier')}")
    log.info("Received %d print job(s) for invoice %s", count, invoice)

    printed = print_jobs(data, config_data)
    print(f"[EVENT] Printing complete. Printers used: {printed if printed else 'NONE'}")


# ---------------------------------------------------------------------------
# Connection logic
# ---------------------------------------------------------------------------
def run_socketio_client(cfg: dict):
    """Connect to the Frappe realtime server."""
    cookie_header = fetch_session_cookies(cfg)
    if not cookie_header:
        print(f"[SOCKET] ❌ Cannot connect – no session cookies.")
        log.error("Cannot connect without valid session cookies.")
        return

    print(f"[SOCKET] Connecting to {cfg['FRAPPE_SOCKET_URL']} (namespace: {NAMESPACE}) ...")
    headers = {"Cookie": cookie_header}
    try:
        sio.connect(
            cfg["FRAPPE_SOCKET_URL"],
            headers=headers,
            transports=["websocket"],
            namespaces=[NAMESPACE],
        )
        sio.wait()
    except Exception as exc:
        print(f"[SOCKET] ❌ Connection error: {exc}")
        log.error("Socket.IO connection error: %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  Local Printers App – Starting up")
    print(f"  Logs folder: {LOG_DIR}")
    print(f"{'='*60}\n")

    config_path = "config.json"
    config_data = load_config(config_path)

    # Derive Socket.IO namespace from site URL (Frappe uses /{sitename})
    site_name = urlparse(config_data["FRAPPE_SOCKET_URL"]).hostname
    NAMESPACE = f"/{site_name}"
    print(f"  Socket.IO namespace: {NAMESPACE}")

    # Register event handlers on the site-specific namespace
    sio.on("connect", on_connect, namespace=NAMESPACE)
    sio.on("connect_error", on_connect_error, namespace=NAMESPACE)
    sio.on("disconnect", on_disconnect, namespace=NAMESPACE)
    sio.on("sales_invoice_submitted", handle_sales_invoice_submitted, namespace=NAMESPACE)

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
