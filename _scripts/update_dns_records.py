#!/usr/bin/env python3
"""
Enhanced Unattended DNS Records Updater
--------------------------------------------------
An automated terminal application for updating Cloudflare DNS A records
with your current public IP address. The script:
  • Displays a stylish ASCII banner at startup via Pyfiglet.
  • Runs fully unattended with no interactive menus.
  • Retrieves your public IP from fallback services.
  • Fetches Cloudflare DNS A records and updates any records whose IP
    does not match the current public IP.
  • Uses Rich for spinners, progress bars, panels, and styled text.
  • Logs all actions to both console and a system log file.

Requirements:
  • Root privileges
  • Environment variables CF_API_TOKEN and CF_ZONE_ID must be set.
  • Python libraries: rich, pyfiglet
Version: 1.0.0
"""

import atexit
import json
import logging
import os
import re
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional, Tuple
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("Missing required libraries. Please install with: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback for enhanced error reporting.
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
VERSION: str = "1.0.0"
APP_NAME: str = "DNS Updater"
APP_SUBTITLE: str = "Cloudflare DNS Automation"
LOG_FILE: str = "/var/log/dns_updater.log"
REQUEST_TIMEOUT: float = 10.0  # seconds

# Cloudflare API credentials (must be set in the environment)
CF_API_TOKEN: Optional[str] = os.environ.get("CF_API_TOKEN")
CF_ZONE_ID: Optional[str] = os.environ.get("CF_ZONE_ID")

# Fallback services for public IP retrieval
IP_SERVICES: List[str] = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
    "https://ipinfo.io/ip",
    "https://icanhazip.com",
]


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming."""

    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"


# ----------------------------------------------------------------
# Console Initialization
# ----------------------------------------------------------------
console: Console = Console()


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class DNSRecord:
    """Dataclass representing a DNS record."""

    id: str
    name: str
    type: str
    content: str
    proxied: bool = False
    updated: bool = field(default=False, init=False)

    def __str__(self) -> str:
        return f"{self.name} ({self.type}): {self.content}"


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging() -> None:
    """Configure logging for both console and file output."""
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    # Remove pre-existing handlers.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler with secure permissions
    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        console.print(
            f"[bold {NordColors.YELLOW}]Warning:[/] Failed to set up log file {LOG_FILE}: {e}"
        )


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Cleanup tasks before exit."""
    console.print(f"[bold {NordColors.FROST_3}]Performing cleanup before exit...[/]")
    logging.info("Cleanup tasks completed.")


def signal_handler(sig: int, frame: Any) -> None:
    """Gracefully handle termination signals."""
    sig_name = (
        getattr(signal, "Signals", lambda s: s)(sig).name
        if hasattr(signal, "Signals")
        else f"signal {sig}"
    )
    console.print(f"[bold {NordColors.YELLOW}]Interrupted by {sig_name}[/]")
    logging.error(f"Interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Prerequisite Checks
# ----------------------------------------------------------------
def check_dependencies() -> None:
    """Ensure required libraries are available."""
    try:
        import rich  # Already imported
        import pyfiglet
    except ImportError as e:
        console.print(f"[bold {NordColors.RED}]Missing dependency:[/] {e}")
        sys.exit(1)


def check_root() -> None:
    """Ensure the script is executed with root privileges."""
    if os.geteuid() != 0:
        console.print(
            f"[bold {NordColors.RED}]Error:[/] This script must be run as root."
        )
        sys.exit(1)


def validate_config() -> None:
    """Validate that necessary environment variables are set."""
    if not CF_API_TOKEN:
        console.print(
            f"[bold {NordColors.RED}]Error:[/] 'CF_API_TOKEN' environment variable not set."
        )
        sys.exit(1)
    if not CF_ZONE_ID:
        console.print(
            f"[bold {NordColors.RED}]Error:[/] 'CF_ZONE_ID' environment variable not set."
        )
        sys.exit(1)


# ----------------------------------------------------------------
# UI Components
# ----------------------------------------------------------------
def create_header() -> Panel:
    """Create an ASCII art header using Pyfiglet with Nord styling."""
    fonts = ["slant", "small", "smslant", "digital", "standard"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=80)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = APP_NAME

    # Apply a Nord color gradient
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled_lines = []
    for i, line in enumerate(ascii_art.splitlines()):
        color = colors[i % len(colors)]
        styled_lines.append(f"[bold {color}]{line}[/]")
    banner = "\n".join(styled_lines)
    border = f"[{NordColors.FROST_3}]{'━' * 50}[/]"
    content = f"{border}\n{banner}\n{border}"
    return Panel(
        Text.from_markup(content),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a styled message panel."""
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def create_records_table(records: List[DNSRecord], title: str) -> Table:
    """Generate a table displaying DNS record statuses."""
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]{title}[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )
    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("Type", style=f"{NordColors.FROST_3}", justify="center", width=8)
    table.add_column("IP Address", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column(
        "Proxied", style=f"{NordColors.FROST_4}", justify="center", width=10
    )
    table.add_column("Status", justify="center", width=12)

    for record in records:
        status = (
            Text("● UPDATED", style=f"bold {NordColors.GREEN}")
            if record.updated
            else Text("● UNCHANGED", style=f"dim {NordColors.POLAR_NIGHT_4}")
        )
        proxied = "Yes" if record.proxied else "No"
        table.add_row(record.name, record.type, record.content, proxied, status)
    return table


# ----------------------------------------------------------------
# Network Functions
# ----------------------------------------------------------------
def get_public_ip() -> str:
    """
    Retrieve the current public IP address from fallback services.
    Exits if no valid IP is found.
    """
    with Progress(
        SpinnerColumn(style=NordColors.FROST_2),
        TextColumn("[bold blue]Retrieving public IP address..."),
        console=console,
    ) as progress:
        progress.add_task("fetch", total=None)
        for service in IP_SERVICES:
            try:
                logging.debug(f"Attempting to retrieve IP from {service}")
                req = Request(service)
                with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                    ip = response.read().decode().strip()
                    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                        console.print(
                            f"[bold {NordColors.GREEN}]Public IP detected:[/] {ip}"
                        )
                        logging.info(f"Public IP from {service}: {ip}")
                        return ip
                    else:
                        logging.warning(f"Invalid IP format from {service}: {ip}")
            except Exception as err:
                logging.warning(f"Error fetching IP from {service}: {err}")
    console.print(
        f"[bold {NordColors.RED}]Error:[/] Failed to retrieve public IP from all services."
    )
    logging.error("Unable to retrieve public IP from fallback services.")
    sys.exit(1)


def fetch_dns_records() -> List[DNSRecord]:
    """
    Fetch all DNS A records from Cloudflare.
    Exits if API response is unexpected or fails.
    """
    with Progress(
        SpinnerColumn(style=NordColors.FROST_2),
        TextColumn("[bold blue]Fetching DNS records from Cloudflare..."),
        console=console,
    ) as progress:
        progress.add_task("fetch", total=None)
        url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records?type=A"
        headers = {
            "Authorization": f"Bearer {CF_API_TOKEN}",
            "Content-Type": "application/json",
        }
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                data = json.loads(response.read().decode())
                if "result" not in data:
                    console.print(
                        f"[bold {NordColors.RED}]Error:[/] Unexpected Cloudflare API response format."
                    )
                    logging.error("Cloudflare API response missing 'result'.")
                    sys.exit(1)
                records = []
                for rec in data["result"]:
                    if rec.get("type") == "A":
                        records.append(
                            DNSRecord(
                                id=rec.get("id"),
                                name=rec.get("name"),
                                type=rec.get("type"),
                                content=rec.get("content"),
                                proxied=rec.get("proxied", False),
                            )
                        )
                return records
        except Exception as err:
            console.print(
                f"[bold {NordColors.RED}]Error:[/] Failed to fetch DNS records: {err}"
            )
            logging.error(f"Error fetching DNS records: {err}")
            sys.exit(1)


def update_dns_record(record: DNSRecord, new_ip: str) -> bool:
    """
    Update a single DNS A record with the new IP address.
    Returns True if successful, otherwise False.
    """
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records/{record.id}"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "type": "A",
        "name": record.name,
        "content": new_ip,
        "ttl": 1,
        "proxied": record.proxied,
    }
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="PUT")
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            result = json.loads(response.read().decode())
            if not result.get("success"):
                errors = ", ".join(
                    err.get("message", "Unknown error")
                    for err in result.get("errors", [])
                )
                console.print(
                    f"[bold {NordColors.YELLOW}]Warning:[/] Failed to update '{record.name}': {errors}"
                )
                logging.warning(f"Update failed for '{record.name}': {errors}")
                return False
            console.print(
                f"[bold {NordColors.GREEN}]Updated:[/] DNS record '{record.name}'"
            )
            logging.info(f"Record '{record.name}' updated successfully.")
            record.content = new_ip
            record.updated = True
            return True
    except Exception as err:
        console.print(
            f"[bold {NordColors.YELLOW}]Warning:[/] Error updating '{record.name}': {err}"
        )
        logging.warning(f"Exception updating record '{record.name}': {err}")
        return False


# ----------------------------------------------------------------
# Main DNS Update Process
# ----------------------------------------------------------------
def update_cloudflare_dns() -> Tuple[int, int]:
    """
    Perform the full update process:
      1. Retrieve current public IP.
      2. Fetch DNS A records from Cloudflare.
      3. Update records that do not match the current IP.
    Returns a tuple (number of updates, number of errors).
    """
    process_title = "Cloudflare DNS Update Process"
    display_panel(
        "Starting automated DNS update process. All A records will be set to your current public IP.",
        style=NordColors.FROST_3,
        title=process_title,
    )
    logging.info("DNS update process initiated.")

    current_ip = get_public_ip()
    logging.info(f"Current public IP: {current_ip}")

    records = fetch_dns_records()
    logging.info(f"Fetched {len(records)} DNS A records from Cloudflare.")

    updates = 0
    errors = 0

    if not records:
        console.print(f"[bold {NordColors.YELLOW}]Warning:[/] No DNS records found.")
        logging.warning("No DNS records to update.")
        return 0, 0

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold {0}]{{task.description}}".format(NordColors.FROST_2)),
        BarColumn(complete_style=NordColors.GREEN),
        TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.completed}}/{{task.total}}"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Updating DNS records...", total=len(records))
        for record in records:
            progress.update(task, description=f"Processing '{record.name}'")
            if record.content != current_ip:
                logging.info(
                    f"Updating '{record.name}': {record.content} -> {current_ip}"
                )
                if update_dns_record(record, current_ip):
                    updates += 1
                else:
                    errors += 1
            else:
                logging.debug(
                    f"No update needed for '{record.name}' (IP: {record.content})"
                )
            progress.advance(task, advance=1)

    # Display summary
    if errors:
        console.print(
            f"[bold {NordColors.YELLOW}]Completed:[/] {updates} update(s) with {errors} error(s)."
        )
        logging.warning(
            f"Update completed with {errors} error(s) and {updates} update(s)."
        )
    elif updates:
        console.print(
            f"[bold {NordColors.GREEN}]Success:[/] {updates} record(s) updated."
        )
        logging.info(f"Update successful with {updates} record(s) updated.")
    else:
        console.print(
            f"[bold {NordColors.GREEN}]No changes:[/] All DNS records are up-to-date."
        )
        logging.info("No DNS records required updating.")

    # Show final records status table
    console.print(create_records_table(records, "DNS Records Status"))
    return updates, errors


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main function: validate, initialize, and execute the DNS update process."""
    console.clear()
    console.print(create_header())

    init_panel = Panel(
        Text.from_markup(
            f"[{NordColors.SNOW_STORM_1}]Initializing DNS Updater v{VERSION}[/]"
        ),
        border_style=Style(color=NordColors.FROST_3),
        title=f"[bold {NordColors.FROST_2}]System Initialization[/]",
        subtitle=f"[{NordColors.SNOW_STORM_1}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]",
        subtitle_align="right",
        padding=(1, 2),
    )
    console.print(init_panel)

    with Progress(
        SpinnerColumn(style=NordColors.FROST_2),
        TextColumn("[bold blue]Initializing system..."),
        console=console,
    ) as progress:
        progress.add_task("init", total=None)
        setup_logging()
        check_dependencies()
        check_root()
        validate_config()
        time.sleep(0.5)

    console.print(f"[bold {NordColors.GREEN}]Initialization complete![/]")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 60)
    logging.info(f"DNS UPDATE STARTED AT {now}")
    logging.info("=" * 60)

    update_cloudflare_dns()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 60)
    logging.info(f"DNS UPDATE COMPLETED AT {now}")
    logging.info("=" * 60)
    display_panel(
        "DNS update process completed.",
        style=NordColors.GREEN,
        title="Process Complete",
    )


if __name__ == "__main__":
    main()
