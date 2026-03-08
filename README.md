
# Local Printers Windows App

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight Windows middleware that receives **pre-rendered print-ready HTML** from Frappe/ERPNext via Socket.IO, converts it to PDF, and silently prints to the designated local printers.

## How It Works

```
ERPNext (Sales Invoice Submit)
  └─► Frappe app renders HTML using chosen Print Format (server-side)
        └─► Socket.IO event → sends { html, printer, invoice_name, … }
              └─► This Windows app receives the event
                    └─► wkhtmltopdf converts HTML → PDF
                          └─► SumatraPDF silently prints to local printer
```

All HTML rendering and template logic lives in the **Frappe app** (`local_printers`).
The Windows app is a thin print client — it only converts HTML to PDF and prints.

## Prerequisites

- Python 3.10+
- Windows OS (uses `win32print`)
- [SumatraPDF](https://www.sumatrapdfreader.org) (silent PDF printing)
- [wkhtmltopdf](https://wkhtmltopdf.org) (HTML → PDF conversion)
- Frappe/ERPNext with the `local_printers` app installed

## Installation

```bash
git clone https://github.com/Ahmed-Mansy-Mansico/local_printers_winapp.git
cd local_printers_winapp
pip install -r requirements.txt
```

## Configuration

Copy `config copy.json` to `config.json` and fill in your values:

```json
{
  "FRAPPE_SOCKET_URL": "https://your-site.com",
  "LOGIN_URL": "https://your-site.com/api/method/login",
  "AUTH_DATA": {
    "usr": "your-username",
    "pwd": "your-password"
  },
  "API_KEY": "your-api-key",
  "API_SECRET": "your-api-secret",
  "WKHTMLTOPDF": "C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe",
  "SUMATRA_PDF_PATH": "C:\\Program Files\\SumatraPDF\\SumatraPDF.exe"
}
```

| Key | Description |
|-----|-------------|
| `FRAPPE_SOCKET_URL` | Your ERPNext site URL |
| `LOGIN_URL` | Login endpoint (usually `{site}/api/method/login`) |
| `AUTH_DATA` | Credentials for Socket.IO session |
| `API_KEY` / `API_SECRET` | API token for printer registration |
| `WKHTMLTOPDF` | Path to `wkhtmltopdf.exe` |
| `SUMATRA_PDF_PATH` | Path to `SumatraPDF.exe` |

## Usage

```bash
python socket_app.py
```

The app will:
1. Load config and log in to your Frappe site
2. Connect via Socket.IO and register local printers
3. Listen for `sales_invoice_submitted` events
4. Convert received HTML to PDF and print silently

## Print Format Setup (Server Side)

In ERPNext, go to **Printer Item Group** and configure:
- **POS Profile** — which POS triggers this printer
- **Printer** — the local printer name (auto-discovered)
- **Print Format** — choose which Print Format to render (Link field)
- **No Letterhead** — skip letterhead if needed
- **Item Groups** — route specific item categories to this printer

The Frappe app renders the full HTML using `frappe.get_print()` with your chosen
Print Format and sends it to this Windows app ready to print.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection failures | Check `config.json` URL and credentials |
| No printers detected | Verify printers are installed locally |
| PDF generation fails | Check wkhtmltopdf path and installation |
| Silent print fails | Check SumatraPDF path and printer name |

## Related Projects

- [local_printers](https://github.com/Ahmed-Mansy-Mansico/local_printers) — Frappe app for ERPNext integration

## License

MIT License
