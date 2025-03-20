#!/usr/bin/env python3

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
from dataclasses import dataclass, field
from typing import List, Optional, Any, Tuple, Dict, Union, Callable

if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)


def install_dependencies():
    required_packages = ["rich", "pyfiglet", "prompt_toolkit"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER", getpass.getuser()))
    try:
        if os.geteuid() != 0:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user"] + required_packages)
        else:
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"] + required_packages)
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


def check_homebrew():
    from shutil import which
    if not which("brew"):
        print("Homebrew is not installed. Please install Homebrew from https://brew.sh/ and rerun this script.")
        sys.exit(1)


try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
    from rich.align import Align
    from rich.box import ROUNDED
    from rich.style import Style
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PtStyle
except ImportError:
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)

console = Console()

VERSION = "1.1.0"
APP_NAME = "macOS VoIP Toolkit"
HISTORY_DIR = os.path.expanduser("~/.macos_voip_toolkit")
os.makedirs(HISTORY_DIR, exist_ok=True)
COMMAND_HISTORY = os.path.join(HISTORY_DIR, "command_history")


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


def render_banner(text: str, adjusted_width: int) -> str:
    try:
        fig = pyfiglet.Figlet(font="slant", width=adjusted_width)
        ascii_art = fig.renderText(text)
    except Exception:
        ascii_art = text

    nord_colors = [NordColors.FROST_1, NordColors.FROST_2, NordColors.FROST_3, NordColors.FROST_4,
                   NordColors.GREEN, NordColors.PURPLE]
    lines = ascii_art.splitlines()
    styled_lines = []
    for i, line in enumerate(lines):
        if line.strip():
            color = nord_colors[i % len(nord_colors)]
            escaped_line = line.replace("[", "\\[").replace("]", "\\]")
            styled_lines.append(f"[bold {color}]{escaped_line}[/]")
    return "\n".join(styled_lines)


def create_header(title: str = None) -> Panel:
    term_width = os.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 100)
    text = title or APP_NAME
    banner_text = render_banner(text, adjusted_width)
    return Panel(
        Text.from_markup(banner_text),
        border_style=NordColors.FROST_1,
        box=NordColors.NORD_BOX,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_3}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]VoIP Toolkit[/]",
        subtitle_align="center",
    )


def get_default_gateway() -> str:
    try:
        result = subprocess.run(
            ["route", "-n", "get", "default"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        for line in result.stdout.splitlines():
            if "gateway:" in line:
                return line.split("gateway:")[-1].strip()
    except Exception as e:
        console.print(f"[bold {NordColors.RED}]Error retrieving default gateway: {e}[/]")
    return ""


def get_local_ip() -> str:
    try:
        ip = subprocess.check_output(["ipconfig", "getifaddr", "en0"], stderr=subprocess.DEVNULL).strip().decode(
            "utf-8")
        return ip
    except Exception:
        return "127.0.0.1"


def get_prompt_style() -> PtStyle:
    return PtStyle.from_dict({"prompt": f"bold {NordColors.FROST_2}"})


def wait_for_key() -> None:
    pt_prompt("Press Enter to continue...", style=get_prompt_style())


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


class SpinnerProgressManager:
    def __init__(self, title: str = ""):
        self.progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(style=NordColors.POLAR_NIGHT_3, complete_style=NordColors.FROST_2,
                      finished_style=NordColors.GREEN),
            TaskProgressColumn(style=NordColors.SNOW_STORM_1),
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


def sip_checker() -> None:
    console.print(create_header("SIP Checker"))
    gateway = get_default_gateway()
    if not gateway:
        console.print(f"[bold {NordColors.RED}]Default gateway not found. Cannot perform SIP check.[/]")
        wait_for_key()
        return
    console.print(f"Default Gateway: [bold]{gateway}[/]")

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
    sock.settimeout(5)
    try:
        sock.sendto(sip_msg.encode("utf-8"), (gateway, 5060))
        responses = []
        try:
            while True:
                response, addr = sock.recvfrom(2048)
                responses.append((response, addr))
        except socket.timeout:
            pass

        if responses:
            sip_detected = any(b"SIP/2.0" in resp for resp, _ in responses)
            if sip_detected:
                console.print(f"[bold {NordColors.RED}]SIP Enabled[/]")
            else:
                console.print(f"[bold {NordColors.YELLOW}]SIP Enabled (response received but unrecognized format)[/]")
        else:
            console.print(f"[bold {NordColors.GREEN}]SIP Not Detected[/]")
    except Exception as e:
        console.print(f"[bold {NordColors.RED}]Error during SIP check: {e}[/]")
    finally:
        sock.close()
    wait_for_key()


def voip_network_info() -> None:
    console.print(create_header("Network Info"))
    local_ip = get_local_ip()
    gateway = get_default_gateway()

    try:
        external_ip = subprocess.check_output(["curl", "-s", "https://api.ipify.org"]).strip().decode("utf-8")
    except Exception:
        external_ip = "Not found"

    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "Not found"

    dns_servers = []
    try:
        with open("/etc/resolv.conf", "r") as resolv:
            for line in resolv:
                if line.startswith("nameserver"):
                    parts = line.split()
                    if len(parts) > 1:
                        dns_servers.append(parts[1])
    except Exception:
        pass
    dns_servers_str = ", ".join(dns_servers) if dns_servers else "Not found"

    wifi_ssid = "N/A"
    airport_path = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
    if os.path.exists(airport_path):
        try:
            result = subprocess.run([airport_path, "-I"], capture_output=True, text=True, check=True)
            for line in result.stdout.splitlines():
                if "SSID:" in line:
                    wifi_ssid = line.split("SSID:")[-1].strip()
                    break
        except Exception:
            wifi_ssid = "Not connected"
    else:
        wifi_ssid = "Unavailable"

    info_table = Table(title="Network Information", show_header=True, header_style=NordColors.HEADER,
                       box=NordColors.NORD_BOX)
    info_table.add_column("Property", style="bold")
    info_table.add_column("Value", style=f"{NordColors.FROST_2}")
    info_table.add_row("Local IP", local_ip)
    info_table.add_row("Default Gateway", gateway if gateway else "Not found")
    info_table.add_row("External IP", external_ip)
    info_table.add_row("Hostname", hostname)
    info_table.add_row("DNS Servers", dns_servers_str)
    info_table.add_row("Wi-Fi SSID", wifi_ssid)

    console.print(info_table)
    wait_for_key()


def sip_port_scanner() -> None:
    console.print(create_header("Port Scanner"))
    local_ip = get_local_ip()
    if local_ip == "127.0.0.1":
        console.print(f"[bold {NordColors.RED}]Unable to determine local IP address from en0.[/]")
        wait_for_key()
        return

    subnet_parts = local_ip.split(".")
    subnet_prefix = ".".join(subnet_parts[:3]) + "."
    total_hosts = 254
    console.print(f"Scanning subnet: {subnet_prefix}0/24 on port 5060 (TCP)...")

    found_devices = []
    start_time = time.time()

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
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(scan_ip, i): i for i in range(1, total_hosts + 1)}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    found_devices.append(result)
                completed += 1
                spinner.update(completed * 100 // total_hosts)

    elapsed_time = time.time() - start_time

    if found_devices:
        found_devices.sort(key=lambda ip: list(map(int, ip.split("."))))
        table = Table(title="SIP Devices Detected", show_header=True, header_style=NordColors.HEADER,
                      box=NordColors.NORD_BOX)
        table.add_column("IP Address", style=f"bold {NordColors.RED}")
        for ip in found_devices:
            table.add_row(ip)
        console.print(table)
    else:
        console.print(f"[bold {NordColors.GREEN}]No devices with SIP port 5060 detected.[/]")

    console.print(f"[bold {NordColors.FROST_2}]Scan completed in {elapsed_time:.2f} seconds.[/]")
    wait_for_key()


def bandwidth_qos_monitor() -> None:
    console.print(create_header("BW & QoS"))
    start_time = time.time()

    try:
        ping_cmd = ["ping", "-c", "10", "google.com"]
        result = subprocess.run(ping_cmd, capture_output=True, text=True, check=True)
        ping_output = result.stdout

        packet_loss_match = re.search(r"(\d+(?:\.\d+)?)% packet loss", ping_output)
        packet_loss = packet_loss_match.group(1) if packet_loss_match else "N/A"

        latency_match = re.search(r"round-trip.* = ([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+) ms", ping_output)
        if latency_match:
            min_latency, avg_latency, max_latency, stddev = latency_match.groups()
        else:
            avg_latency = min_latency = max_latency = stddev = "N/A"
    except Exception:
        avg_latency = min_latency = max_latency = stddev = packet_loss = "Error"

    try:
        curl_cmd = [
            "curl", "-o", "/dev/null", "-s", "-w", "%{size_download} %{time_total}",
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

    try:
        fw_cmd = ["socketfilterfw", "--getglobalstate"]
        result = subprocess.run(fw_cmd, capture_output=True, text=True, check=True)
        firewall_state = "Enabled" if "State = 1" in result.stdout else "Disabled"
    except Exception:
        try:
            result = subprocess.run(
                ["defaults", "read", "/Library/Preferences/com.apple.alf", "globalstate"],
                capture_output=True, text=True, check=True
            )
            state_val = result.stdout.strip()
            firewall_state = "Enabled" if state_val != "0" else "Disabled"
        except Exception:
            firewall_state = "Unknown"

    try:
        result = subprocess.run(["pfctl", "-s", "info"], capture_output=True, text=True, check=True)
        pf_info = result.stdout
        pf_state = "Enabled" if "Status: Enabled" in pf_info else "Disabled"
    except Exception:
        pf_state = "Error"

    try:
        result = subprocess.run(["sysctl", "net.inet.ip.dscp"], capture_output=True, text=True, check=True)
        dscp_output = result.stdout.strip()
        dscp_value = dscp_output.split(":")[-1].strip() if ":" in dscp_output else dscp_output
    except Exception:
        dscp_value = "Not Configured"

    try:
        traceroute_cmd = ["traceroute", "google.com"]
        result = subprocess.run(traceroute_cmd, capture_output=True, text=True, check=True)
        traceroute_lines = result.stdout.strip().splitlines()
        num_hops = len(traceroute_lines) - 1 if len(traceroute_lines) > 1 else "N/A"
        traceroute_result = f"{num_hops} hops"
    except Exception:
        traceroute_result = "Error"

    try:
        dns_start = time.time()
        socket.gethostbyname("google.com")
        dns_end = time.time()
        dns_resolution_time = f"{(dns_end - dns_start) * 1000:.2f} ms"
    except Exception:
        dns_resolution_time = "Error"

    total_duration = time.time() - start_time

    result_table = Table(title="Network Test Summary", show_header=True, header_style=NordColors.HEADER,
                         box=NordColors.NORD_BOX)
    result_table.add_column("Test", style="bold", justify="left")
    result_table.add_column("Result", style=f"{NordColors.FROST_2}", justify="right")

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


def show_help() -> None:
    console.print(create_header("Help"))
    help_text = (
        f"[bold {NordColors.FROST_2}]Available Commands:[/]\n\n"
        f"[bold {NordColors.FROST_2}]1[/]: SIP Checker (check for SIP ALG on your router)\n"
        f"[bold {NordColors.FROST_2}]2[/]: VoIP Network Info (display local IP and default gateway)\n"
        f"[bold {NordColors.FROST_2}]3[/]: SIP Port Scanner (scan local subnet for SIP devices)\n"
        f"[bold {NordColors.FROST_2}]4[/]: Bandwidth & QoS Monitor (test network performance)\n"
        f"[bold {NordColors.FROST_2}]H[/]: Help\n"
        f"[bold {NordColors.FROST_2}]0[/]: Exit\n"
    )
    console.print(
        Panel(
            Text.from_markup(help_text),
            title=f"[bold {NordColors.FROST_2}]Help[/]",
            border_style=NordColors.FROST_1,
            box=NordColors.NORD_BOX,
        )
    )
    wait_for_key()


def cleanup() -> None:
    console.print(f"[bold {NordColors.FROST_2}]Cleaning up session resources...[/]")


def signal_handler(sig, frame) -> None:
    try:
        sig_name = signal.Signals(sig).name
        console.print(f"[bold {NordColors.YELLOW}]Process interrupted by {sig_name}[/]")
    except Exception:
        console.print(f"[bold {NordColors.YELLOW}]Process interrupted by signal {sig}[/]")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


def main_menu() -> None:
    while True:
        console.clear()
        console.print(create_header())
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(Align.center(f"[bold {NordColors.FROST_2}]Current Time: {current_time}[/]"))
        console.print()

        table = Table(show_header=True, header_style=NordColors.HEADER, box=NordColors.NORD_BOX)
        table.add_column("Option", style="bold", width=8)
        table.add_column("Description", style=f"bold {NordColors.FROST_2}")

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
                    Text("Thank you for using the macOS VoIP Toolkit!", style=f"bold {NordColors.FROST_2}"),
                    border_style=NordColors.FROST_1,
                    box=NordColors.NORD_BOX,
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
                console.print(f"[bold {NordColors.RED}]Invalid selection: {choice}[/]")
                wait_for_key()


def main() -> None:
    check_homebrew()
    main_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print(f"[bold {NordColors.YELLOW}]Operation cancelled by user[/]")
        sys.exit(0)
    except Exception as e:
        console.print_exception()
        console.print(f"[bold {NordColors.RED}]An unexpected error occurred: {e}[/]")
        sys.exit(1)