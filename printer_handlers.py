"""
Printer handlers – receive pre-rendered HTML from the Frappe server,
convert to PDF via wkhtmltopdf, and silently print via SumatraPDF.
"""

import subprocess
import tempfile
import os
import logging

import pdfkit
import win32print

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


def get_local_printers() -> list[str]:
    """Return names of locally-installed printers."""
    return [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)]


def print_pdf_silent(pdf_path: str, printer_name: str, sumatra_pdf_path: str):
    """Print a PDF file silently using SumatraPDF."""
    command = (
        f'"{sumatra_pdf_path}" -print-to "{printer_name}" '
        f'-print-settings "noscale" "{pdf_path}"'
    )
    log.info("SumatraPDF command: %s", command)
    try:
        subprocess.run(command, shell=True, check=True)
        log.info("Sent %s to printer '%s'.", pdf_path, printer_name)
    except subprocess.CalledProcessError as exc:
        log.error("SumatraPDF failed for '%s': %s", printer_name, exc)
    except Exception as exc:
        log.error("Unexpected error printing PDF: %s", exc)


def html_to_pdf(html: str, wkhtmltopdf_path: str) -> str | None:
    """Convert an HTML string to a temporary PDF file. Returns the PDF path."""
    config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
    pdf_path = tempfile.mktemp(suffix=".pdf")
    options = {
        "no-outline": None,
        "encoding": "utf-8",
        "enable-local-file-access": None,
    }
    try:
        pdfkit.from_string(html, pdf_path, configuration=config, options=options)
        log.info("Generated PDF: %s", pdf_path)
        return pdf_path
    except Exception as exc:
        log.error("wkhtmltopdf failed: %s", exc)
        return None


def print_jobs(jobs: list[dict], config_data: dict) -> list[str]:
    """
    Process a list of print jobs received from the Frappe server.

    Each job dict contains:
      - html          : fully-rendered HTML (ready to print)
      - printer       : target printer system name
      - printer_ip    : (optional) network printer IP
      - invoice_name  : the Sales Invoice name
      - is_cashier    : whether this is the cashier copy
      - print_format  : the Print Format used server-side

    Returns a list of printer names that were printed to.
    """
    wkhtmltopdf_path = config_data["WKHTMLTOPDF"]
    sumatra_pdf_path = config_data.get(
        "SUMATRA_PDF_PATH", r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
    )

    printed_to: list[str] = []

    if not isinstance(jobs, list):
        jobs = [jobs]

    for job in jobs:
        invoice_name = job.get("invoice_name", "unknown")
        printer_name = job.get("printer")
        html = job.get("html")

        if not html:
            log.warning("Job for invoice %s has no HTML, skipping.", invoice_name)
            continue

        if not printer_name:
            log.warning("Job for invoice %s has no printer, skipping.", invoice_name)
            continue

        log.info(
            "Printing invoice %s on '%s' (format: %s)",
            invoice_name,
            printer_name,
            job.get("print_format", "Standard"),
        )

        pdf_path = html_to_pdf(html, wkhtmltopdf_path)
        if pdf_path:
            print_pdf_silent(pdf_path, printer_name, sumatra_pdf_path)
            printed_to.append(printer_name)

            # Clean up temp PDF
            try:
                os.remove(pdf_path)
                log.info("Cleaned up temp PDF: %s", pdf_path)
            except OSError:
                pass

    return printed_to
