#!/usr/bin/env python3
"""
macOS VoIP Toolkit
--------------------------------------------------
A comprehensive, menu‐driven CLI application for VoIP‐related tasks on macOS.
This toolkit includes a SIP Checker (to detect if SIP ALG is enabled on your router),
VoIP network information, a SIP port scanner, and a Bandwidth & QoS Monitor.

Core Libraries & Features:
  • Auto‐installation of required Python packages.
  • macOS–specific configuration using Homebrew for package management.
  • Dynamic Pyfiglet banners rendered with a Nord-themed rainbow using the “slant” font.
  • Robust error handling, signal cleanup, and modular design.

Version: 1.0.0
"""

import os
import sys
import time
import socket
import subprocess
import platform
import signal
import atexit
import getpass
import re
from datetime import datetime
from pathlib import Path

# Ensure we are running on macOS
if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)


# ----------------------------------------------------------------
# Dependency Check and Installation
# ----------------------------------------------------------------
def install_dependencies():
    """
    Ensure required third-party packages are installed.
    Installs:
      - rich
      - pyfiglet
      - prompt_toolkit
    """
    required_packages = ["rich", "pyfiglet", "prompt_toolkit"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER", getpass.getuser()))
    try:
        if os.geteuid() != 0:
            print(f"Installing dependencies for user: {user}")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--user"] + required_packages
            )
        else:
            print(f"Running as sudo. Installing dependencies for user: {user}")
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"]
                + required_packages
            )
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


def shutil_which(cmd):
    """A simple wrapper around shutil.which (compatible with older Python versions)."""
    from shutil import which

    return which(cmd)


def check_homebrew():
    """Ensure Homebrew is installed on macOS."""
    if not shutil_which("brew"):
        print(
            "Homebrew is not installed. Please install Homebrew from https://brew.sh/ and rerun this script."
        )
        sys.exit(1)


# Attempt to import dependencies; if missing, install them.
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PtStyle
except ImportError:
    print("Required libraries not found. Installing dependencies...")
    install_dependencies()
    print("Dependencies installed. Restarting script...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

console: Console = Console()

# ----------------------------------------------------------------
# Global Constants and Paths
# ----------------------------------------------------------------
VERSION = "1.0.0"
APP_NAME = "macOS VoIP Toolkit"
HISTORY_DIR = os.path.expanduser("~/.macos_voip_toolkit")
os.makedirs(HISTORY_DIR, exist_ok=True)
COMMAND_HISTORY = os.path.join(HISTORY_DIR, "command_history")


# ----------------------------------------------------------------
# Banner Rendering Helpers
# ----------------------------------------------------------------
def render_banner(text: str, adjusted_width: int) -> str:
    """
    Render a banner using Pyfiglet with the 'slant' font and a Nord-themed rainbow.
    Returns the rendered text with Rich markup.
    """
    try:
        fig = pyfiglet.Figlet(font="slant", width=adjusted_width)
        ascii_art = fig.renderText(text)
    except Exception:
        ascii_art = text

    # Nord theme colors
    nord_colors = ["#BF616A", "#D08770", "#EBCB8B", "#A3BE8C", "#88C0D0", "#B48EAD"]
    lines = ascii_art.splitlines()
    styled_lines = []
    for i, line in enumerate(lines):
        if line.strip():
            color = nord_colors[i % len(nord_colors)]
            escaped_line = line.replace("[", "\\[").replace("]", "\\]")
            styled_lines.append(f"[bold {color}]{escaped_line}[/]")
    return "\n".join(styled_lines)


def create_main_header() -> Panel:
    """
    Generate the main header banner using Pyfiglet with a Nord-themed rainbow.
    This banner includes the application name, version, and subtitle.
    """
    term_width = os.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 100)
    banner_text = render_banner(APP_NAME, adjusted_width)
    panel = Panel(
        Text.from_markup(banner_text),
        border_style="white",
        padding=(1, 2),
        title=f"[bold white]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold white]VoIP Toolkit[/]",
        subtitle_align="center",
    )
    return panel


def create_submenu_header(title: str) -> Panel:
    """
    Generate a submenu header banner using Pyfiglet with a Nord-themed rainbow.
    The provided title (e.g., 'SIP Checker') is rendered using the same settings as the main header.
    """
    term_width = os.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 100)
    banner_text = render_banner(title, adjusted_width)
    panel = Panel(
        Text.from_markup(banner_text),
        border_style="white",
        padding=(1, 2),
        title=f"[bold white]{title}[/]",
        title_align="right",
        subtitle=f"[bold white]VoIP Toolkit[/]",
        subtitle_align="center",
    )
    return panel


# ----------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------
def get_default_gateway() -> str:
    """
    Retrieve the default gateway IP address using 'route -n get default'.
    """
    try:
        result = subprocess.run(
            ["route", "-n", "get", "default"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if "gateway:" in line:
                return line.split("gateway:")[-1].strip()
    except Exception as e:
        console.print(f"[bold red]Error retrieving default gateway: {e}[/]")
    return ""


def get_local_ip() -> str:
    """
    Retrieve the local IP address for interface en0 (typical on macOS).
    """
    try:
        ip = (
            subprocess.check_output(
                ["ipconfig", "getifaddr", "en0"], stderr=subprocess.DEVNULL
            )
            .strip()
            .decode("utf-8")
        )
        return ip
    except Exception:
        return "127.0.0.1"


def get_prompt_style() -> PtStyle:
    return PtStyle.from_dict({"prompt": "bold cyan"})


def wait_for_key() -> None:
    pt_prompt("Press Enter to continue...", style=get_prompt_style())


# ----------------------------------------------------------------
# Spinner Progress Manager (using Rich)
# ----------------------------------------------------------------
class SpinnerProgressManager:
    """Manages Rich spinners with consistent styling."""

    def __init__(self, title: str = ""):
        self.progress = Progress(
            SpinnerColumn(spinner_name="dots", style="bold cyan"),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        )
        self.task = None

    def __enter__(self):
        self.progress.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.progress.stop()

    def add_task(self, description: str, total: int = 100):
        self.task = self.progress.add_task(description, total=total)
        return self.task

    def update(self, completed: int):
        if self.task is not None:
            self.progress.update(self.task, completed=completed)


# ----------------------------------------------------------------
# SIP Checker Functionality
# ----------------------------------------------------------------
def sip_checker() -> None:
    """
    Check the network (default gateway) for SIP ALG behavior.
    A minimal SIP OPTIONS message is sent to UDP port 5060.
    If a SIP response is received, SIP is assumed enabled.
    """
    console.print(create_submenu_header("SIP Checker"))
    gateway = get_default_gateway()
    if not gateway:
        console.print(
            "[bold red]Default gateway not found. Cannot perform SIP check.[/bold red]"
        )
        wait_for_key()
        return
    console.print(f"Default Gateway: [bold]{gateway}[/]")

    # Use dynamic branch and Call-ID values for improved compatibility
    branch = f"z9hG4bK-{int(time.time())}"
    call_id = f"{int(time.time())}@{gateway}"
    sip_msg = (
        f"OPTIONS sip:dummy@{gateway} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {gateway}:5060;branch={branch}\r\n"
        f"Max-Forwards: 70\r\n"
        f"From: <sip:tester@{gateway}>;tag=12345\r\n"
        f"To: <sip:dummy@{gateway}>\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 1 OPTIONS\r\n"
        f"Content-Length: 0\r\n\r\n"
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Increase timeout to allow for network delays (5 seconds)
    sock.settimeout(5)
    try:
        # Send the SIP OPTIONS message to the default gateway
        sock.sendto(sip_msg.encode("utf-8"), (gateway, 5060))

        # Collect responses until the socket times out
        responses = []
        while True:
            try:
                response, addr = sock.recvfrom(2048)
                responses.append((response, addr))
            except socket.timeout:
                break

        if responses:
            # Check each response for a SIP status line
            sip_detected = any(b"SIP/2.0" in resp for resp, _ in responses)
            if sip_detected:
                console.print("[bold red]SIP Enabled[/bold red]")
            else:
                console.print(
                    "[bold yellow]SIP Enabled (response received but unrecognized format)[/bold yellow]"
                )
        else:
            console.print("[bold green]SIP Not Detected[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error during SIP check: {e}[/bold red]")
    finally:
        sock.close()
    wait_for_key()


# ----------------------------------------------------------------
# VoIP Network Information
# ----------------------------------------------------------------
def voip_network_info() -> None:
    """
    Display VoIP-related network information, including:
      • The local IP address.
      • The default gateway.
      • The external (public) IP address.
      • The system hostname.
      • Configured DNS servers.
      • The current Wi-Fi SSID (if connected).
    """
    console.print(create_submenu_header("VoIP Network Info"))

    # Retrieve local network information
    local_ip = get_local_ip()
    gateway = get_default_gateway()

    # Retrieve external IP using an online service
    try:
        external_ip = (
            subprocess.check_output(["curl", "-s", "https://api.ipify.org"])
            .strip()
            .decode("utf-8")
        )
    except Exception:
        external_ip = "Not found"

    # Get system hostname
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "Not found"

    # Retrieve DNS servers from /etc/resolv.conf
    dns_servers = []
    try:
        with open("/etc/resolv.conf", "r") as resolv:
            for line in resolv:
                if line.startswith("nameserver"):
                    parts = line.split()
                    if len(parts) > 1:
                        dns_servers.append(parts[1])
    except Exception:
        dns_servers = ["Not found"]
    dns_servers_str = ", ".join(dns_servers) if dns_servers else "Not found"

    # Attempt to get the current Wi-Fi SSID (only applicable if using Wi-Fi)
    wifi_ssid = "N/A"
    airport_path = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
    if os.path.exists(airport_path):
        try:
            result = subprocess.run(
                [airport_path, "-I"], capture_output=True, text=True, check=True
            )
            for line in result.stdout.splitlines():
                if "SSID:" in line:
                    wifi_ssid = line.split("SSID:")[-1].strip()
                    break
        except Exception:
            wifi_ssid = "Not connected"
    else:
        wifi_ssid = "Unavailable"

    # Build a table to display the collected network information
    info_table = Table(
        title="Network Information", show_header=True, header_style="bold cyan"
    )
    info_table.add_column("Property", style="bold")
    info_table.add_column("Value", style="cyan")
    info_table.add_row("Local IP", local_ip)
    info_table.add_row("Default Gateway", gateway if gateway else "Not found")
    info_table.add_row("External IP", external_ip)
    info_table.add_row("Hostname", hostname)
    info_table.add_row("DNS Servers", dns_servers_str)
    info_table.add_row("Wi-Fi SSID", wifi_ssid)

    console.print(info_table)
    wait_for_key()


# ----------------------------------------------------------------
# SIP Port Scanner
# ----------------------------------------------------------------
def sip_port_scanner() -> None:
    """
    Scan the local subnet for devices with TCP port 5060 (commonly used for SIP).
    This improved version uses parallel scanning for better performance,
    tracks progress with a spinner, and reports the scan duration.
    """
    console.print(create_submenu_header("SIP Port Scanner"))
    local_ip = get_local_ip()
    if local_ip == "127.0.0.1":
        console.print(
            "[bold red]Unable to determine local IP address from en0.[/bold red]"
        )
        wait_for_key()
        return

    subnet_parts = local_ip.split(".")
    subnet_prefix = ".".join(subnet_parts[:3]) + "."
    total_hosts = 254
    console.print(f"Scanning subnet: {subnet_prefix}0/24 on port 5060 (TCP)...")

    found_devices = []
    start_time = time.time()

    # Function to scan a single IP address
    def scan_ip(i: int) -> str:
        target_ip = f"{subnet_prefix}{i}"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            result = s.connect_ex((target_ip, 5060))
            s.close()
            if result == 0:
                return target_ip
        except Exception:
            pass
        return ""

    import concurrent.futures

    with SpinnerProgressManager("Scanning...") as spinner:
        task_id = spinner.add_task("Scanning hosts", total=total_hosts)
        completed = 0
        # Use a thread pool to scan IPs concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(scan_ip, i): i for i in range(1, total_hosts + 1)
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    found_devices.append(result)
                completed += 1
                # Update spinner progress based on number of completed scans
                spinner.update(completed * 100 // total_hosts)

    elapsed_time = time.time() - start_time

    if found_devices:
        # Sort found IP addresses for better readability
        found_devices.sort(key=lambda ip: list(map(int, ip.split("."))))
        table = Table(
            title="SIP Devices Detected", show_header=True, header_style="bold red"
        )
        table.add_column("IP Address", style="bold red")
        for ip in found_devices:
            table.add_row(ip)
        console.print(table)
        console.print(
            f"[bold cyan]Scan completed in {elapsed_time:.2f} seconds.[/bold cyan]"
        )
    else:
        console.print(
            "[bold green]No devices with SIP port 5060 detected.[/bold green]"
        )
        console.print(
            f"[bold cyan]Scan completed in {elapsed_time:.2f} seconds.[/bold cyan]"
        )

    wait_for_key()


# ----------------------------------------------------------------
# Bandwidth & QoS Monitor
# ----------------------------------------------------------------
def bandwidth_qos_monitor() -> None:
    """
    Perform an extensive network test that includes:
      • A ping test to measure average, minimum, maximum, and standard deviation of latency,
        as well as packet loss.
      • A download speed test using curl (download link remains unchanged).
      • Checking the macOS Application Firewall status.
      • Checking PF (Packet Filter) firewall status.
      • Retrieving DSCP configuration via sysctl.
      • A traceroute test to count the number of hops to google.com.
      • A DNS resolution time test for google.com.
      • Reporting the total duration of the tests.
    The results are presented in a formatted summary table.
    """
    console.print(create_submenu_header("BW & QoS Monitor"))

    # Start overall timer for the test suite.
    start_time = time.time()

    # -------------------------------
    # Ping Test
    # -------------------------------
    try:
        ping_cmd = ["ping", "-c", "10", "google.com"]
        result = subprocess.run(ping_cmd, capture_output=True, text=True, check=True)
        ping_output = result.stdout

        # Parse packet loss
        packet_loss_match = re.search(r"(\d+(?:\.\d+)?)% packet loss", ping_output)
        packet_loss = packet_loss_match.group(1) if packet_loss_match else "N/A"

        # Parse latency values (min/avg/max/stddev if available)
        latency_match = re.search(
            r"round-trip.* = ([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+) ms", ping_output
        )
        if latency_match:
            min_latency, avg_latency, max_latency, stddev = latency_match.groups()
        else:
            avg_latency = min_latency = max_latency = stddev = "N/A"
    except Exception:
        avg_latency = min_latency = max_latency = stddev = packet_loss = "Error"

    # -------------------------------
    # Download Speed Test
    # -------------------------------
    try:
        curl_cmd = [
            "curl",
            "-o",
            "/dev/null",
            "-s",
            "-w",
            "%{size_download} %{time_total}",
            "https://nbg1-speed.hetzner.com/100MB.bin",
        ]
        result = subprocess.run(curl_cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip()
        size_download, time_total = output.split()
        size_download = float(size_download)
        time_total = float(time_total)
        speed_mbps = (size_download * 8) / (time_total * 1e6)
        download_speed = f"{speed_mbps:.2f} Mbps"
    except Exception:
        download_speed = "Error"

    # -------------------------------
    # macOS Application Firewall Test
    # -------------------------------
    try:
        fw_cmd = ["socketfilterfw", "--getglobalstate"]
        result = subprocess.run(fw_cmd, capture_output=True, text=True, check=True)
        firewall_state = "Enabled" if "State = 1" in result.stdout else "Disabled"
    except Exception:
        try:
            result = subprocess.run(
                [
                    "defaults",
                    "read",
                    "/Library/Preferences/com.apple.alf",
                    "globalstate",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            state_val = result.stdout.strip()
            firewall_state = "Enabled" if state_val != "0" else "Disabled"
        except Exception:
            firewall_state = "Unknown"

    # -------------------------------
    # PF (Packet Filter) Firewall Test
    # -------------------------------
    try:
        result = subprocess.run(
            ["pfctl", "-s", "info"], capture_output=True, text=True, check=True
        )
        pf_info = result.stdout
        pf_state = "Enabled" if "Status: Enabled" in pf_info else "Disabled"
    except Exception:
        pf_state = "Error"

    # -------------------------------
    # DSCP Configuration Test
    # -------------------------------
    try:
        result = subprocess.run(
            ["sysctl", "net.inet.ip.dscp"], capture_output=True, text=True, check=True
        )
        dscp_output = result.stdout.strip()
        dscp_value = (
            dscp_output.split(":")[-1].strip() if ":" in dscp_output else dscp_output
        )
    except Exception:
        dscp_value = "Not Configured / Error"

    # -------------------------------
    # Traceroute Test (Additional Feature)
    # -------------------------------
    try:
        traceroute_cmd = ["traceroute", "google.com"]
        result = subprocess.run(
            traceroute_cmd, capture_output=True, text=True, check=True
        )
        traceroute_lines = result.stdout.strip().splitlines()
        # Exclude the header line to count the hops
        num_hops = len(traceroute_lines) - 1 if len(traceroute_lines) > 1 else "N/A"
        traceroute_result = f"{num_hops} hops"
    except Exception:
        traceroute_result = "Error"

    # -------------------------------
    # DNS Resolution Test (Additional Feature)
    # -------------------------------
    try:
        dns_start = time.time()
        socket.gethostbyname("google.com")
        dns_end = time.time()
        dns_resolution_time = f"{(dns_end - dns_start) * 1000:.2f} ms"
    except Exception:
        dns_resolution_time = "Error"

    # -------------------------------
    # Calculate Total Test Duration
    # -------------------------------
    total_duration = time.time() - start_time

    # -------------------------------
    # Build and Display the Results Table
    # -------------------------------
    result_table = Table(
        title="Network Test Summary", show_header=True, header_style="bold cyan"
    )
    result_table.add_column("Test", style="bold", justify="left")
    result_table.add_column("Result", style="cyan", justify="right")

    result_table.add_row("Ping (Avg Latency)", f"{avg_latency} ms")
    result_table.add_row("Ping (Min Latency)", f"{min_latency} ms")
    result_table.add_row("Ping (Max Latency)", f"{max_latency} ms")
    result_table.add_row("Ping (Std Dev)", f"{stddev} ms")
    result_table.add_row("Ping (Packet Loss)", f"{packet_loss} %")
    result_table.add_row("Download Speed", download_speed)
    result_table.add_row("App Firewall", firewall_state)
    result_table.add_row("PF Firewall", pf_state)
    result_table.add_row("DSCP Value", dscp_value)
    result_table.add_row("Traceroute", traceroute_result)
    result_table.add_row("DNS Resolution", dns_resolution_time)
    result_table.add_row("Total Test Duration", f"{total_duration:.2f} s")

    console.print(result_table)
    wait_for_key()


# ----------------------------------------------------------------
# Help / About
# ----------------------------------------------------------------
def show_help() -> None:
    """
    Display help and available commands.
    """
    console.print(create_submenu_header("Help"))
    help_text = (
        "[bold cyan]Available Commands:[/]\n\n"
        "[bold cyan]1[/]: SIP Checker (check for SIP ALG on your router)\n"
        "[bold cyan]2[/]: VoIP Network Info (display local IP and default gateway)\n"
        "[bold cyan]3[/]: SIP Port Scanner (scan local subnet for SIP devices)\n"
        "[bold cyan]4[/]: Bandwidth & QoS Monitor (test network latency, bandwidth, firewall, and DSCP settings)\n"
        "[bold cyan]H[/]: Help\n"
        "[bold cyan]0[/]: Exit\n"
    )
    console.print(
        Panel(
            Text.from_markup(help_text),
            title="[bold cyan]Help[/bold cyan]",
            border_style="cyan",
        )
    )
    wait_for_key()


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    console.print("[bold cyan]Cleaning up session resources...[/bold cyan]")


def signal_handler(sig, frame) -> None:
    try:
        sig_name = signal.Signals(sig).name
        console.print(f"[bold yellow]Process interrupted by {sig_name}[/bold yellow]")
    except Exception:
        console.print(f"[bold yellow]Process interrupted by signal {sig}[/bold yellow]")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Menu and Program Control
# ----------------------------------------------------------------
def main_menu() -> None:
    while True:
        console.clear()
        console.print(create_main_header())
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(Align.center(f"[bold cyan]Current Time: {current_time}[/]"))
        console.print()
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Option", style="bold", width=8)
        table.add_column("Description", style="bold cyan")
        menu_options = [
            ("1", "SIP Checker", sip_checker),
            ("2", "VoIP Network Info", voip_network_info),
            ("3", "SIP Port Scanner", sip_port_scanner),
            ("4", "Bandwidth & QoS Monitor", bandwidth_qos_monitor),
            ("H", "Help", show_help),
            ("0", "Exit", None),
        ]
        for option, desc, _ in menu_options:
            table.add_row(option, desc)
        console.print(table)
        choice = pt_prompt(
            "Enter your choice: ",
            history=FileHistory(COMMAND_HISTORY),
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).upper()
        if choice == "0":
            console.print(
                Panel(
                    Text(
                        "Thank you for using the macOS VoIP Toolkit!", style="bold cyan"
                    ),
                    border_style="cyan",
                )
            )
            sys.exit(0)
        else:
            matched = False
            for option, _, func in menu_options:
                if choice == option:
                    matched = True
                    func()
                    break
            if not matched:
                console.print(f"[bold red]Invalid selection: {choice}[/bold red]")
                wait_for_key()


def main() -> None:
    check_homebrew()
    main_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("[bold yellow]Operation cancelled by user[/bold yellow]")
        sys.exit(0)
    except Exception as e:
        console.print_exception()
        console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
        sys.exit(1)
