#!/usr/bin/env python3

import atexit
import json
import logging
import os
import platform
import re
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)


def install_dependencies():
    required_packages = ["rich", "pyfiglet", "requests"]
    try:
        if os.geteuid() != 0:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user"] + required_packages)
        else:
            import subprocess
            user = os.environ.get("SUDO_USER", os.environ.get("USER"))
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"] + required_packages)
    except Exception as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn,
        TimeRemainingColumn
    )
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from rich.style import Style
    import requests
except ImportError:
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)

install_rich_traceback(show_locals=True)
console = Console()

VERSION = "1.1.0"
APP_NAME = "DNS Updater"
APP_SUBTITLE = "Cloudflare DNS Automation"
LOG_FILE = "/var/log/dns_updater.log"
CONFIG_DIR = os.path.expanduser("~/.cf_dns_updater")
REQUEST_TIMEOUT = 15.0

CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_ZONE_ID = os.environ.get("CF_ZONE_ID")

IP_SERVICES = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
    "https://ipinfo.io/ip",
    "https://icanhazip.com",
]


class NordColors:
    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    SNOW_STORM_3 = "#ECEFF4"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"

    SUCCESS = Style(color=GREEN, bold=True)
    ERROR = Style(color=RED, bold=True)
    WARNING = Style(color=YELLOW, bold=True)
    INFO = Style(color=FROST_2, bold=True)
    HEADER = Style(color=FROST_1, bold=True)
    SUBHEADER = Style(color=FROST_3, bold=True)
    ACCENT = Style(color=FROST_4, bold=True)

    @classmethod
    def get_frost_gradient(cls, steps=4):
        return [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4][:steps]

    @classmethod
    def get_polar_gradient(cls, steps=4):
        return [cls.POLAR_NIGHT_1, cls.POLAR_NIGHT_2, cls.POLAR_NIGHT_3, cls.POLAR_NIGHT_4][:steps]

    @classmethod
    def get_progress_columns(cls):
        return [
            SpinnerColumn(spinner_name="dots", style=f"bold {cls.FROST_1}"),
            TextColumn(f"[bold {cls.FROST_2}]{{task.description}}[/]"),
            BarColumn(bar_width=None, style=cls.POLAR_NIGHT_3, complete_style=cls.FROST_2, finished_style=cls.GREEN),
            TaskProgressColumn(style=cls.SNOW_STORM_1),
            TimeRemainingColumn(compact=True),
        ]


@dataclass
class DNSRecord:
    id: str
    name: str
    type: str
    content: str
    proxied: bool = False
    updated: bool = field(default=False, init=False)

    def __str__(self) -> str:
        return f"{self.name} ({self.type}): {self.content}"


def ensure_config_directory():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


def setup_logging():
    log_dir = os.path.dirname(LOG_FILE)
    try:
        os.makedirs(log_dir, exist_ok=True)
    except PermissionError:
        console.print(f"[bold {NordColors.YELLOW}]Warning:[/] Cannot create log directory, logging to console only")
        return False

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
        return True
    except Exception as e:
        console.print(f"[bold {NordColors.YELLOW}]Warning:[/] Failed to set up log file: {e}")
        return False


def cleanup():
    logging.info("Cleanup tasks completed.")


def signal_handler(sig, frame):
    try:
        sig_name = signal.Signals(sig).name
    except (ValueError, AttributeError):
        sig_name = f"signal {sig}"
    console.print(f"[bold {NordColors.YELLOW}]Interrupted by {sig_name}[/]")
    logging.warning(f"Interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + sig)


def clear_screen():
    console.clear()


def print_message(text, style=NordColors.INFO, prefix="•"):
    if isinstance(style, str):
        console.print(f"[{style}]{prefix} {text}[/{style}]")
    else:
        console.print(f"{prefix} {text}", style=style)


def print_error(message):
    print_message(message, NordColors.ERROR, "✗")


def print_success(message):
    print_message(message, NordColors.SUCCESS, "✓")


def print_warning(message):
    print_message(message, NordColors.WARNING, "⚠")


def print_info(message):
    print_message(message, NordColors.INFO, "ℹ")


def display_panel(title, message, style=NordColors.INFO):
    if isinstance(style, str):
        panel = Panel(
            Text.from_markup(message),
            title=title,
            border_style=style,
            padding=(1, 2)
        )
    else:
        panel = Panel(
            Text(message),
            title=title,
            border_style=style,
            padding=(1, 2)
        )
    console.print(panel)


def create_header():
    term_width = os.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)

    fonts = ["slant", "small_slant", "standard", "big", "digital", "small"]
    ascii_art = ""

    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=adjusted_width)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    frost_colors = NordColors.get_frost_gradient(min(len(ascii_lines), 4))

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = frost_colors[i % len(frost_colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"

    border_style = NordColors.FROST_3
    border_char = "═"
    border_line = f"[{border_style}]{border_char * (adjusted_width - 8)}[/]"

    styled_text = border_line + "\n" + styled_text + border_line

    panel = Panel(
        Text.from_markup(styled_text),
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_3}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return panel


def create_records_table(records, title):
    table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        expand=True,
        title=title,
        border_style=NordColors.FROST_3,
        title_justify="center",
    )
    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("Type", style=f"{NordColors.FROST_3}", justify="center", width=8)
    table.add_column("IP Address", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Proxied", style=f"{NordColors.FROST_4}", justify="center", width=10)
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


def check_root():
    if os.geteuid() != 0:
        print_error("This script must be run as root.")
        logging.error("Script executed without root privileges.")
        sys.exit(1)


def validate_config():
    if not CF_API_TOKEN:
        print_error("CF_API_TOKEN environment variable not set.")
        sys.exit(1)
    if not CF_ZONE_ID:
        print_error("CF_ZONE_ID environment variable not set.")
        sys.exit(1)


def get_public_ip():
    with Progress(
            *NordColors.get_progress_columns(),
            console=console,
    ) as progress:
        task = progress.add_task("Retrieving public IP address...", total=None)
        for service in IP_SERVICES:
            try:
                logging.debug(f"Trying IP service: {service}")
                req = Request(service)
                with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                    ip = response.read().decode().strip()
                    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                        print_success(f"Public IP detected: {ip}")
                        logging.info(f"Public IP from {service}: {ip}")
                        return ip
                    else:
                        logging.warning(f"Invalid IP format from {service}: {ip}")
            except Exception as err:
                logging.warning(f"Error fetching IP from {service}: {err}")

    print_error("Failed to retrieve public IP from all services.")
    logging.error("Unable to retrieve public IP from any service.")
    sys.exit(1)


def fetch_dns_records():
    with Progress(
            *NordColors.get_progress_columns(),
            console=console,
    ) as progress:
        task = progress.add_task("Fetching DNS records from Cloudflare...", total=None)
        try:
            url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records?type=A"
            headers = {
                "Authorization": f"Bearer {CF_API_TOKEN}",
                "Content-Type": "application/json",
            }

            try:
                response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, json.JSONDecodeError):
                # Fallback to urllib if requests fails
                req = Request(url, headers=headers)
                with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                    data = json.loads(response.read().decode())

            if not data.get("success", False) or "result" not in data:
                print_error("Unexpected Cloudflare API response format.")
                logging.error("Cloudflare API response missing 'result' or success=false.")
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
            print_error(f"Failed to fetch DNS records: {err}")
            logging.error(f"Error fetching DNS records: {err}")
            sys.exit(1)


def update_dns_record(record, new_ip):
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

    try:
        try:
            response = requests.put(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, json.JSONDecodeError):
            # Fallback to urllib if requests fails
            data = json.dumps(payload).encode("utf-8")
            req = Request(url, data=data, headers=headers, method="PUT")
            with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                result = json.loads(response.read().decode())

        if not result.get("success"):
            errors = ", ".join(
                err.get("message", "Unknown error")
                for err in result.get("errors", [])
            )
            print_warning(f"Failed to update '{record.name}': {errors}")
            logging.warning(f"Update failed for '{record.name}': {errors}")
            return False

        print_success(f"Updated DNS record '{record.name}'")
        logging.info(f"Record '{record.name}' updated successfully.")
        record.content = new_ip
        record.updated = True
        return True
    except Exception as err:
        print_warning(f"Error updating '{record.name}': {err}")
        logging.warning(f"Exception updating record '{record.name}': {err}")
        return False


def update_cloudflare_dns():
    display_panel(
        "Cloudflare DNS Update Process",
        "Starting automated DNS update process. All A records will be set to your current public IP.",
        NordColors.FROST_3,
    )
    logging.info("DNS update process initiated.")

    current_ip = get_public_ip()
    logging.info(f"Current public IP: {current_ip}")

    records = fetch_dns_records()
    logging.info(f"Fetched {len(records)} DNS A records from Cloudflare.")

    updates = 0
    errors = 0

    if not records:
        print_warning("No DNS records found.")
        logging.warning("No DNS records to update.")
        return 0, 0

    with Progress(
            *NordColors.get_progress_columns(),
            console=console,
    ) as progress:
        task = progress.add_task("Updating DNS records...", total=len(records))
        for record in records:
            progress.update(task, description=f"Processing '{record.name}'")
            if record.content != current_ip:
                logging.info(f"Updating '{record.name}': {record.content} -> {current_ip}")
                if update_dns_record(record, current_ip):
                    updates += 1
                else:
                    errors += 1
            else:
                logging.debug(f"No update needed for '{record.name}' (IP: {record.content})")
            progress.advance(task)

    if errors:
        print_warning(f"Completed: {updates} update(s) with {errors} error(s).")
        logging.warning(f"Update completed with {errors} error(s) and {updates} update(s).")
    elif updates:
        print_success(f"Success: {updates} record(s) updated.")
        logging.info(f"Update successful with {updates} record(s) updated.")
    else:
        print_success("No changes: All DNS records are up-to-date.")
        logging.info("No DNS records required updating.")

    console.print(create_records_table(records, "DNS Records Status"))
    return updates, errors


def main():
    clear_screen()
    console.print(create_header())

    init_panel = Panel(
        Text.from_markup(f"[{NordColors.SNOW_STORM_1}]Initializing DNS Updater v{VERSION}[/]"),
        border_style=Style(color=NordColors.FROST_3),
        title=f"[bold {NordColors.FROST_2}]System Initialization[/]",
        subtitle=f"[{NordColors.SNOW_STORM_1}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]",
        subtitle_align="right",
        padding=(1, 2),
    )
    console.print(init_panel)

    with Progress(
            *NordColors.get_progress_columns(),
            console=console,
    ) as progress:
        task = progress.add_task("Initializing system...", total=None)
        ensure_config_directory()
        setup_logging()
        check_root()
        validate_config()
        time.sleep(0.5)

    print_success("Initialization complete!")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 60)
    logging.info(f"DNS UPDATE STARTED AT {now}")
    logging.info("=" * 60)

    try:
        update_cloudflare_dns()
    except Exception as e:
        print_error(f"Unhandled exception: {e}")
        logging.exception("Unhandled exception during DNS update:")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 60)
    logging.info(f"DNS UPDATE COMPLETED AT {now}")
    logging.info("=" * 60)
    display_panel(
        "Process Complete",
        "DNS update process completed.",
        NordColors.GREEN,
    )


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)
    main()