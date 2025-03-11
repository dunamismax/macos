#!/usr/bin/env python3
"""
Enhanced VM Manager
--------------------------------------------------

A comprehensive virtual machine management utility for KVM/libvirt with robust error handling,
real‑time progress tracking, and a beautiful Nord‑themed interface.

Features:
  • List, create, start, stop, and delete virtual machines
  • Manage VM snapshots (list, create, revert, delete)
  • Real‑time VM status monitoring and detailed VM info
  • Interactive, menu‑driven interface using Rich and Pyfiglet
  • Cross‑platform logging and cleanup

Usage:
  Run the script with root privileges (sudo) and follow the interactive prompts.

Version: 2.0.0
"""

import atexit
import datetime
import logging
import os
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, List, Optional

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.style import Style
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.columns import Columns
    import shutil
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
HOSTNAME: str = socket.gethostname()
APP_NAME: str = "VM Manager"
APP_SUBTITLE: str = "KVM/Libvirt Management Tool"
VERSION: str = "2.0.0"

# Directories and Files
LOG_FILE: str = "/var/log/vm_manager.log"
VM_IMAGE_DIR: str = "/var/lib/libvirt/images"
ISO_DIR: str = "/var/lib/libvirt/boot"
SNAPSHOT_DIR: str = "/var/lib/libvirt/snapshots"
DEFAULT_LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()

# Default VM Settings
DEFAULT_VCPUS: int = 2
DEFAULT_RAM_MB: int = 2048
DEFAULT_DISK_GB: int = 20
DEFAULT_OS_VARIANT: str = "ubuntu22.04"

# UI Settings
TERM_WIDTH: int = min(shutil.get_terminal_size().columns, 100)
OPERATION_TIMEOUT: int = 300  # seconds

# Default network XML for libvirt
DEFAULT_NETWORK_XML: str = """<network>
  <name>default</name>
  <forward mode='nat'/>
  <bridge name='virbr0' stp='on' delay='0'/>
  <ip address='192.168.122.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='192.168.122.2' end='192.168.122.254'/>
    </dhcp>
  </ip>
</network>
"""


# ----------------------------------------------------------------
# Nord-Themed Colors & Console Setup
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

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


console: Console = Console(theme=None, width=TERM_WIDTH, highlight=False)


# ----------------------------------------------------------------
# Helper Functions: UI & Logging
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Generate a dynamic ASCII art header using Pyfiglet with a Nord gradient.
    """
    fonts = ["slant", "small", "smslant", "mini", "digital"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = f"{APP_NAME}"
    # Build gradient text
    lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled = ""
    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        styled += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled = f"{border}\n{styled}{border}"
    return Panel(
        Text.from_markup(styled),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_info(text: str) -> None:
    print_message(text, NordColors.FROST_3, "ℹ")


def print_success(text: str) -> None:
    print_message(text, NordColors.GREEN, "✓")


def print_warning(text: str) -> None:
    print_message(text, NordColors.YELLOW, "⚠")


def print_error(text: str) -> None:
    print_message(text, NordColors.RED, "✗")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def display_section_title(title: str) -> None:
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.FROST_2}]{border}[/bold {NordColors.FROST_2}]")
    console.print(
        f"[bold {NordColors.FROST_2}]  {title.center(TERM_WIDTH - 4)}[/bold {NordColors.FROST_2}]"
    )
    console.print(f"[bold {NordColors.FROST_2}]{border}[/bold {NordColors.FROST_2}]\n")


def setup_logging() -> None:
    """Configure logging with both console and rotating file handlers."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO))
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
        print_info(f"Logging to {LOG_FILE}")
    except Exception as e:
        print_warning(f"Could not set up log file: {e}")
        logging.warning(f"Log file error: {e}")


def cleanup() -> None:
    print_message("Cleaning up...", NordColors.FROST_3)
    logging.info("Cleanup tasks executed.")


def signal_handler(sig: int, frame: Any) -> None:
    sig_name = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"signal {sig}"
    )
    print_warning(f"Process interrupted by {sig_name}")
    logging.warning(f"Interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    command: List[str],
    capture_output: bool = False,
    check: bool = True,
    timeout: int = OPERATION_TIMEOUT,
) -> str:
    """
    Execute a shell command and return its stdout (if capture_output is True).
    """
    cmd_str = " ".join(shlex.quote(arg) for arg in command)
    logging.debug(f"Executing: {cmd_str}")
    try:
        result = subprocess.run(
            command,
            capture_output=capture_output,
            text=True,
            check=check,
            timeout=timeout,
        )
        if capture_output and result.stdout:
            logging.debug(f"Output: {result.stdout.strip()}")
        return result.stdout if capture_output else ""
    except subprocess.TimeoutExpired:
        logging.error(f"Command timed out: {cmd_str}")
        print_error(f"Command timed out after {timeout}s: {cmd_str}")
        raise
    except subprocess.CalledProcessError as e:
        err = e.stderr.strip() if e.stderr else "No error output"
        logging.error(f"Command failed ({e.returncode}): {cmd_str}\nError: {err}")
        print_error(f"Command failed: {cmd_str}")
        if check:
            raise
        return ""


# ----------------------------------------------------------------
# VM Management Helpers
# ----------------------------------------------------------------
def check_root() -> bool:
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        print_info("Please run with: sudo python3 vm_manager.py")
        return False
    print_success("Running with root privileges.")
    return True


def check_dependencies() -> bool:
    required_cmds = ["virsh", "qemu-img", "virt-install"]
    missing = []
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Checking dependencies..."),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task("Checking", total=len(required_cmds))
        for cmd in required_cmds:
            progress.advance(task)
            if not shutil.which(cmd):
                missing.append(cmd)
    if missing:
        print_error(f"Missing dependencies: {', '.join(missing)}")
        print_info(
            "Please install the required packages (e.g., sudo apt install libvirt-clients libvirt-daemon-system virtinst qemu-utils)"
        )
        return False
    print_success("All required dependencies are available.")
    return True


def ensure_default_network() -> bool:
    with console.status(
        f"[bold {NordColors.FROST_3}]Checking virtual network status...", spinner="dots"
    ):
        try:
            net_list = run_command(["virsh", "net-list", "--all"], capture_output=True)
            if "default" in net_list:
                if "active" in net_list and "inactive" not in net_list:
                    print_success("Default network is active.")
                    return True
                else:
                    print_info("Default network exists but is inactive. Starting it...")
                    run_command(["virsh", "net-start", "default"])
                    run_command(["virsh", "net-autostart", "default"])
                    print_success("Default network started and set to autostart.")
                    return True
            else:
                print_info("Default network does not exist. Creating it...")
                fd, xml_path = tempfile.mkstemp(suffix=".xml")
                try:
                    with os.fdopen(fd, "w") as f:
                        f.write(DEFAULT_NETWORK_XML)
                    run_command(["virsh", "net-define", xml_path])
                    run_command(["virsh", "net-start", "default"])
                    run_command(["virsh", "net-autostart", "default"])
                    print_success("Default network created and activated.")
                    return True
                finally:
                    if os.path.exists(xml_path):
                        os.unlink(xml_path)
        except Exception as e:
            logging.error(f"Network setup error: {e}")
            print_error(f"Failed to configure default network: {e}")
            return False


def get_vm_list() -> List[Any]:
    """
    Retrieve a list of VMs via 'virsh list --all'.
    Returns a list of objects with id, name, and state.
    """
    try:
        # Ensure network is active
        net_output = run_command(
            ["virsh", "net-list", "--all"], capture_output=True, check=False
        )
        if "inactive" in net_output.lower() and "default" in net_output:
            ensure_default_network()
        output = run_command(["virsh", "list", "--all"], capture_output=True)
        vms = []
        lines = output.strip().splitlines()
        try:
            sep_index = next(
                i for i, line in enumerate(lines) if line.lstrip().startswith("---")
            )
        except StopIteration:
            sep_index = 1
        for line in lines[sep_index + 1 :]:
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    vm = {
                        "id": parts[0],
                        "name": parts[1],
                        "state": " ".join(parts[2:]),
                    }
                    vms.append(vm)
        return vms
    except Exception as e:
        logging.error(f"VM list error: {e}")
        print_error(f"Failed to retrieve VM list: {e}")
        return []


def get_vm_snapshots(vm_name: str) -> List[Any]:
    try:
        output = run_command(
            ["virsh", "snapshot-list", vm_name], capture_output=True, check=False
        )
        if not output or "failed" in output.lower():
            return []
        snaps = []
        lines = output.strip().splitlines()
        data = [
            line
            for line in lines
            if line.strip()
            and not line.startswith("Name")
            and not line.startswith("----")
        ]
        for line in data:
            parts = line.split()
            snap = {
                "name": parts[0],
                "creation_time": " ".join(parts[1:3]) if len(parts) > 2 else "",
                "state": parts[3] if len(parts) > 3 else "",
            }
            snaps.append(snap)
        return snaps
    except Exception as e:
        logging.error(f"Snapshot list error for VM '{vm_name}': {e}")
        print_error(f"Failed to retrieve snapshots for VM '{vm_name}': {e}")
        return []


def select_vm(
    prompt_text: str = "Select a VM by number (or 'q' to cancel): ",
) -> Optional[str]:
    vms = get_vm_list()
    if not vms:
        print_info("No VMs available.")
        return None
    display_section_title("Available Virtual Machines")
    table = Table(show_header=True, header_style=f"bold {NordColors.FROST_1}", box=None)
    table.add_column(
        "No.", style=f"bold {NordColors.FROST_4}", justify="right", width=5
    )
    table.add_column("Name", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("State", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("ID", style=f"{NordColors.SNOW_STORM_1}")
    for idx, vm in enumerate(vms, start=1):
        state = vm["state"].lower()
        if "running" in state:
            state_text = f"[bold {NordColors.GREEN}]RUNNING[/]"
        elif "paused" in state:
            state_text = f"[bold {NordColors.YELLOW}]PAUSED[/]"
        elif "shut off" in state:
            state_text = f"[bold {NordColors.RED}]STOPPED[/]"
        else:
            state_text = f"[dim {NordColors.POLAR_NIGHT_4}]? {vm['state'].upper()}[/]"
        table.add_row(str(idx), vm["name"], state_text, vm["id"])
    console.print(
        Panel(table, border_style=Style(color=NordColors.FROST_3), padding=(1, 2))
    )
    while True:
        choice = Prompt.ask(f"[bold {NordColors.PURPLE}]{prompt_text}[/]").strip()
        if choice.lower() == "q":
            return None
        try:
            num = int(choice)
            if 1 <= num <= len(vms):
                return vms[num - 1]["name"]
            else:
                print_error("Invalid selection number.")
        except ValueError:
            print_error("Please enter a valid number.")


def select_snapshot(
    vm_name: str, prompt_text: str = "Select a snapshot by number (or 'q' to cancel): "
) -> Optional[str]:
    snaps = get_vm_snapshots(vm_name)
    if not snaps:
        print_info(f"No snapshots found for VM '{vm_name}'.")
        return None
    display_section_title(f"Snapshots for VM: {vm_name}")
    table = Table(show_header=True, header_style=f"bold {NordColors.FROST_1}", box=None)
    table.add_column(
        "No.", style=f"bold {NordColors.FROST_4}", justify="right", width=5
    )
    table.add_column("Name", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Creation Time", style=f"{NordColors.FROST_3}")
    table.add_column("State", style=f"{NordColors.SNOW_STORM_1}")
    for idx, snap in enumerate(snaps, start=1):
        table.add_row(
            str(idx), snap["name"], snap["creation_time"], snap["state"] or ""
        )
    console.print(
        Panel(table, border_style=Style(color=NordColors.FROST_3), padding=(1, 2))
    )
    while True:
        choice = Prompt.ask(f"[bold {NordColors.PURPLE}]{prompt_text}[/]").strip()
        if choice.lower() == "q":
            return None
        try:
            num = int(choice)
            if 1 <= num <= len(snaps):
                return snaps[num - 1]["name"]
            else:
                print_error("Invalid selection number.")
        except ValueError:
            print_error("Please enter a valid number.")


def confirm_action(message: str) -> bool:
    return Confirm.ask(f"[bold {NordColors.PURPLE}]{message}[/]")


# ----------------------------------------------------------------
# VM Management Functions
# ----------------------------------------------------------------
def list_vms() -> None:
    console.clear()
    console.print(create_header())
    display_section_title("Virtual Machine List")
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_3}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Retrieving VM information..."),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Retrieving", total=None)
        vms = get_vm_list()
    if not vms:
        display_panel(
            "No virtual machines found", style=NordColors.FROST_3, title="VM List"
        )
        return
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=None,
        expand=True,
    )
    table.add_column(
        "No.", style=f"bold {NordColors.FROST_4}", justify="right", width=5
    )
    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("State", justify="center")
    table.add_column("ID", style=f"{NordColors.SNOW_STORM_1}")
    for idx, vm in enumerate(vms, start=1):
        state = vm["state"].lower()
        if "running" in state:
            state_text = Text("● RUNNING", style=f"bold {NordColors.GREEN}")
        elif "paused" in state:
            state_text = Text("◐ PAUSED", style=f"bold {NordColors.YELLOW}")
        elif "shut off" in state:
            state_text = Text("○ STOPPED", style=f"bold {NordColors.RED}")
        else:
            state_text = Text(
                f"? {vm['state'].upper()}", style=f"dim {NordColors.POLAR_NIGHT_4}"
            )
        table.add_row(str(idx), vm["name"], state_text, vm["id"])
    panel = Panel(table, border_style=Style(color=NordColors.FROST_3), padding=(1, 2))
    console.print(panel)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]Last updated: {current_time}[/] | "
            f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
        )
    )


def create_vm() -> None:
    console.clear()
    console.print(create_header())
    display_section_title("Create New Virtual Machine")
    if not ensure_default_network():
        display_panel(
            "Cannot create VM without an active network",
            style=NordColors.RED,
            title="Network Error",
        )
        return
    default_name = f"vm-{int(time.time()) % 10000}"
    vm_name = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Enter VM name (default: {default_name}):[/]",
        default=default_name,
    )
    # Sanitize VM name
    vm_name = "".join(c for c in vm_name if c.isalnum() or c in "-_")
    if not vm_name:
        print_error("Invalid VM name")
        return
    display_section_title("VM Resource Specifications")
    try:
        vcpus = IntPrompt.ask(
            f"[bold {NordColors.PURPLE}]Number of vCPUs (default: {DEFAULT_VCPUS}):[/]",
            default=DEFAULT_VCPUS,
        )
        ram = IntPrompt.ask(
            f"[bold {NordColors.PURPLE}]RAM in MB (default: {DEFAULT_RAM_MB}):[/]",
            default=DEFAULT_RAM_MB,
        )
        disk_size = IntPrompt.ask(
            f"[bold {NordColors.PURPLE}]Disk size in GB (default: {DEFAULT_DISK_GB}):[/]",
            default=DEFAULT_DISK_GB,
        )
    except Exception:
        print_error("vCPUs, RAM, and disk size must be numbers")
        return
    if vcpus < 1 or ram < 512 or disk_size < 1:
        print_error(
            "Invalid resource specifications. (vCPUs>=1, RAM>=512MB, Disk>=1GB)"
        )
        return
    disk_image = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
    if os.path.exists(disk_image):
        print_error(
            f"Disk image '{disk_image}' already exists. Choose a different VM name."
        )
        return
    display_section_title("Installation Media")
    print_info("Select the installation method:")
    console.print(f"[{NordColors.SNOW_STORM_1}]1. Use existing ISO file[/]")
    console.print(f"[{NordColors.SNOW_STORM_1}]2. Cancel VM creation[/]")
    media_choice = Prompt.ask(f"[bold {NordColors.PURPLE}]Enter your choice (1-2):[/]")
    if media_choice != "1":
        print_info("VM creation cancelled")
        return
    iso_path = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Enter full path to the ISO file:[/]"
    ).strip()
    if not os.path.isfile(iso_path):
        print_error("ISO file not found")
        print_info(f"The file '{iso_path}' does not exist or is not accessible")
        return
    os.makedirs(VM_IMAGE_DIR, exist_ok=True)
    display_section_title("Creating VM Disk Image")
    print_info(f"Creating {disk_size}GB disk image at {disk_image}")
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Creating disk image..."),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        console=console,
    ) as progress:
        disk_task = progress.add_task("Creating", total=100)
        progress.update(disk_task, completed=10)
        try:
            run_command(
                ["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"]
            )
            progress.update(disk_task, completed=100)
            print_success("Disk image created successfully")
        except Exception as e:
            print_error(f"Failed to create disk image: {e}")
            return
    display_section_title("Creating Virtual Machine")
    print_info(f"Creating VM '{vm_name}' with {vcpus} vCPUs and {ram}MB RAM")
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Creating virtual machine..."),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        console=console,
    ) as progress:
        vm_task = progress.add_task("Creating", total=100)
        progress.update(vm_task, completed=10)
        virt_install_cmd = [
            "virt-install",
            "--name",
            vm_name,
            "--ram",
            str(ram),
            "--vcpus",
            str(vcpus),
            "--disk",
            f"path={disk_image},size={disk_size},format=qcow2",
            "--cdrom",
            iso_path,
            "--os-variant",
            DEFAULT_OS_VARIANT,
            "--network",
            "default",
            "--graphics",
            "vnc",
            "--noautoconsole",
        ]
        progress.update(vm_task, completed=30)
        try:
            run_command(virt_install_cmd)
            progress.update(vm_task, completed=100)
            print_success(f"VM '{vm_name}' created successfully")
            print_info("To connect to the console, use:")
            console.print(f"  [bold {NordColors.FROST_3}]virsh console {vm_name}[/]")
            print_info("Or use a VNC viewer to connect")
        except Exception as e:
            print_error(f"Failed to create VM '{vm_name}': {e}")
            print_info("Cleaning up failed VM creation...")
            try:
                run_command(
                    ["virsh", "undefine", vm_name, "--remove-all-storage"], check=False
                )
                print_info("Cleanup completed")
            except Exception as ce:
                print_warning(f"Incomplete cleanup: {ce}")
            return


def start_vm() -> None:
    console.clear()
    console.print(create_header())
    display_section_title("Start Virtual Machine")
    if not ensure_default_network():
        display_panel(
            "Network is not ready. VMs may lack connectivity.",
            style=NordColors.YELLOW,
            title="Network Warning",
        )
    vm_name = select_vm("Select a VM to start (or 'q' to cancel):")
    if not vm_name:
        print_info("Operation cancelled")
        return
    try:
        state = run_command(["virsh", "domstate", vm_name], capture_output=True).lower()
        if "running" in state:
            print_warning(f"VM '{vm_name}' is already running")
            return
        print_info(f"Starting VM '{vm_name}'...")
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Starting VM '{vm_name}'..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            console=console,
        ) as progress:
            start_task = progress.add_task("Starting", total=100)
            progress.update(start_task, completed=10)
            run_command(["virsh", "start", vm_name])
            for i in range(10, 100, 10):
                time.sleep(0.5)
                progress.update(start_task, completed=i)
            progress.update(start_task, completed=100)
        print_success(f"VM '{vm_name}' started successfully")
        time.sleep(1)
        state = (
            run_command(["virsh", "domstate", vm_name], capture_output=True)
            .strip()
            .lower()
        )
        if "running" in state:
            try:
                ip_info = run_command(
                    ["virsh", "domifaddr", vm_name], capture_output=True, check=False
                )
                if "ipv4" in ip_info.lower():
                    print_info("Network information:")
                    console.print(f"  [bold {NordColors.FROST_3}]{ip_info.strip()}[/]")
            except Exception:
                print_info("VM started but network information is not yet available")
    except Exception as e:
        print_error(f"Error starting VM '{vm_name}': {e}")


def stop_vm() -> None:
    console.clear()
    console.print(create_header())
    display_section_title("Stop Virtual Machine")
    vm_name = select_vm("Select a VM to stop (or 'q' to cancel):")
    if not vm_name:
        print_info("Operation cancelled")
        return
    state = run_command(["virsh", "domstate", vm_name], capture_output=True).lower()
    if "shut off" in state:
        print_warning(f"VM '{vm_name}' is already stopped")
        return
    if not confirm_action(f"Are you sure you want to stop VM '{vm_name}'?"):
        print_info("Operation cancelled")
        return
    try:
        print_info(f"Sending shutdown signal to VM '{vm_name}'...")
        run_command(["virsh", "shutdown", vm_name])
        shutdown_time = 30
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Waiting for VM to shut down..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn("[{task.percentage:>3.0f}%]"),
            console=console,
        ) as progress:
            shutdown_task = progress.add_task("Shutting down", total=shutdown_time)
            for i in range(shutdown_time):
                time.sleep(1)
                progress.update(shutdown_task, completed=i + 1)
                current = run_command(
                    ["virsh", "domstate", vm_name], capture_output=True, check=False
                ).lower()
                if "shut off" in current:
                    progress.update(shutdown_task, completed=shutdown_time)
                    print_success("VM shut down gracefully")
                    return
        print_warning("VM did not shut down gracefully within the timeout period")
        if confirm_action("Force VM to stop?"):
            with console.status(
                f"[bold {NordColors.FROST_3}]Forcing VM to stop...", spinner="dots"
            ):
                run_command(["virsh", "destroy", vm_name])
            print_success(f"VM '{vm_name}' forcefully stopped")
        else:
            print_info("VM shutdown aborted. The VM is still running.")
    except Exception as e:
        print_error(f"Error stopping VM '{vm_name}': {e}")


def delete_vm() -> None:
    console.clear()
    console.print(create_header())
    display_section_title("Delete Virtual Machine")
    vm_name = select_vm("Select a VM to delete (or 'q' to cancel):")
    if not vm_name:
        print_info("Operation cancelled")
        return
    if not confirm_action(
        f"CAUTION: This will permanently delete VM '{vm_name}' and ALL its storage. Continue?"
    ):
        print_info("Deletion cancelled")
        return
    state = run_command(
        ["virsh", "domstate", vm_name], capture_output=True, check=False
    ).lower()
    if "running" in state:
        if not confirm_action(
            f"VM '{vm_name}' is running. Stop it and proceed with deletion?"
        ):
            print_info("Deletion cancelled")
            return
    try:
        if "running" in state:
            print_info(f"Shutting down VM '{vm_name}'...")
            run_command(["virsh", "shutdown", vm_name], check=False)
            time.sleep(5)
            state = run_command(
                ["virsh", "domstate", vm_name], capture_output=True, check=False
            ).lower()
            if "running" in state:
                print_warning("VM did not shut down gracefully, forcing power off...")
                run_command(["virsh", "destroy", vm_name], check=False)
        print_info(f"Deleting VM '{vm_name}' and all its storage...")
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Deleting VM..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            console=console,
        ) as progress:
            delete_task = progress.add_task("Deleting", total=100)
            progress.update(delete_task, completed=30)
            run_command(["virsh", "undefine", vm_name, "--remove-all-storage"])
            progress.update(delete_task, completed=100)
        print_success(f"VM '{vm_name}' deleted successfully")
    except Exception as e:
        print_error(f"Error deleting VM '{vm_name}': {e}")
        logging.error(f"Deletion error: {e}")


def show_vm_info() -> None:
    console.clear()
    console.print(create_header())
    display_section_title("VM Information")
    vm_name = select_vm("Select a VM to show info (or 'q' to cancel):")
    if not vm_name:
        print_info("Operation cancelled")
        return
    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Gathering VM information...", spinner="dots"
        ):
            info = run_command(["virsh", "dominfo", vm_name], capture_output=True)
            net = run_command(
                ["virsh", "domifaddr", vm_name], capture_output=True, check=False
            )
            snapshots = get_vm_snapshots(vm_name)
            storage = run_command(["virsh", "domblklist", vm_name], capture_output=True)
        display_panel(
            f"Information for VM: {vm_name}",
            style=NordColors.FROST_2,
            title="VM Details",
        )
        panels = []
        basic_info = ""
        for line in info.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                basic_info += f"[bold {NordColors.FROST_3}]{key.strip()}:[/] [{NordColors.SNOW_STORM_1}]{value.strip()}[/]\n"
        panels.append(
            Panel(
                Text.from_markup(basic_info),
                title=f"[bold {NordColors.FROST_2}]Basic Information[/]",
                border_style=Style(color=NordColors.FROST_4),
                padding=(1, 2),
            )
        )
        net_content = (
            f"[{NordColors.SNOW_STORM_1}]{net.strip()}[/]"
            if net and "failed" not in net.lower()
            else f"[{NordColors.SNOW_STORM_1}]No network information available[/]"
        )
        panels.append(
            Panel(
                Text.from_markup(net_content),
                title=f"[bold {NordColors.FROST_2}]Network Information[/]",
                border_style=Style(color=NordColors.FROST_4),
                padding=(1, 2),
            )
        )
        snap_content = f"[bold {NordColors.FROST_3}]Total snapshots:[/] [{NordColors.SNOW_STORM_1}]{len(snapshots)}[/]\n\n"
        if snapshots:
            for idx, snap in enumerate(snapshots, 1):
                snap_content += f"[bold {NordColors.FROST_3}]{idx}.[/] [{NordColors.SNOW_STORM_1}]{snap['name']}[/] ([{NordColors.FROST_3}]{snap['creation_time']}[/])\n"
        else:
            snap_content += f"[{NordColors.SNOW_STORM_1}]No snapshots available[/]"
        panels.append(
            Panel(
                Text.from_markup(snap_content),
                title=f"[bold {NordColors.FROST_2}]Snapshots[/]",
                border_style=Style(color=NordColors.FROST_4),
                padding=(1, 2),
            )
        )
        storage_content = ""
        if "Target" in storage:
            lines = storage.splitlines()
            storage_content += f"[bold {NordColors.FROST_3}]{lines[0]}[/]\n[{NordColors.FROST_2}]{lines[1]}[/]\n"
            for line in lines[2:]:
                storage_content += f"[{NordColors.SNOW_STORM_1}]{line}[/]\n"
        else:
            storage_content = f"[{NordColors.SNOW_STORM_1}]{storage}[/]"
        panels.append(
            Panel(
                Text.from_markup(storage_content),
                title=f"[bold {NordColors.FROST_2}]Storage Devices[/]",
                border_style=Style(color=NordColors.FROST_4),
                padding=(1, 2),
            )
        )
        if console.width > 120:
            console.print(Columns(panels))
        else:
            for p in panels:
                console.print(p)
                console.print()
    except Exception as e:
        print_error(f"Error retrieving VM info: {e}")
        logging.error(f"VM info error: {e}")


# ----------------------------------------------------------------
# Snapshot Management Functions
# ----------------------------------------------------------------
def list_vm_snapshots(vm: Optional[str] = None) -> None:
    console.clear()
    console.print(create_header())
    display_section_title("VM Snapshots")
    if not vm:
        vm = select_vm("Select a VM to list snapshots (or 'q' to cancel):")
        if not vm:
            print_info("Operation cancelled")
            return
    with console.status(
        f"[bold {NordColors.FROST_3}]Retrieving snapshots for VM '{vm}'...",
        spinner="dots",
    ):
        snapshots = get_vm_snapshots(vm)
    if not snapshots:
        display_panel(
            f"No snapshots found for VM '{vm}'",
            style=NordColors.FROST_3,
            title="Snapshot List",
        )
        return
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=None,
        expand=True,
    )
    table.add_column(
        "No.", style=f"bold {NordColors.FROST_4}", justify="right", width=5
    )
    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("Creation Time", style=f"{NordColors.FROST_3}")
    table.add_column("State", style=f"{NordColors.SNOW_STORM_1}")
    for idx, snap in enumerate(snapshots, start=1):
        table.add_row(
            str(idx), snap["name"], snap["creation_time"], snap["state"] or ""
        )
    panel = Panel(table, border_style=Style(color=NordColors.FROST_3), padding=(1, 2))
    console.print(panel)
    console.print()
    print_info("Snapshot Management Tips:")
    console.print(
        f"• [bold {NordColors.FROST_2}]Create snapshot:[/] Use the 'Create Snapshot' option"
    )
    console.print(
        f"• [bold {NordColors.FROST_2}]Revert to snapshot:[/] Use the 'Revert to Snapshot' option"
    )
    console.print(
        f"• [bold {NordColors.FROST_2}]Delete snapshot:[/] Use the 'Delete Snapshot' option"
    )
    input(f"[bold {NordColors.PURPLE}]Press Enter to continue...[/]")


def create_snapshot() -> None:
    console.clear()
    console.print(create_header())
    display_section_title("Create VM Snapshot")
    vm = select_vm("Select a VM to snapshot (or 'q' to cancel):")
    if not vm:
        print_info("Operation cancelled")
        return
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    default_snap = f"{vm}-snap-{timestamp}"
    snap_name = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Enter snapshot name (default: {default_snap}):[/]",
        default=default_snap,
    )
    description = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Enter snapshot description (optional):[/]"
    ).strip()
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    snapshot_xml = f"""<domainsnapshot>
  <name>{snap_name}</name>
  <description>{description}</description>
</domainsnapshot>"""
    fd, xml_path = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(snapshot_xml)
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Creating snapshot..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            console=console,
        ) as progress:
            snap_task = progress.add_task("Creating", total=100)
            progress.update(snap_task, completed=10)
            run_command(["virsh", "snapshot-create", vm, "--xmlfile", xml_path])
            progress.update(snap_task, completed=100)
        print_success(f"Snapshot '{snap_name}' created successfully")
    except Exception as e:
        print_error(f"Failed to create snapshot: {e}")
        logging.error(f"Snapshot creation error: {e}")
    finally:
        if os.path.exists(xml_path):
            os.unlink(xml_path)
    input(f"[bold {NordColors.PURPLE}]Press Enter to continue...[/]")


def revert_to_snapshot() -> None:
    console.clear()
    console.print(create_header())
    display_section_title("Revert VM to Snapshot")
    vm = select_vm("Select a VM to revert (or 'q' to cancel):")
    if not vm:
        print_info("Operation cancelled")
        return
    snap = select_snapshot(vm, "Select a snapshot to revert to (or 'q' to cancel):")
    if not snap:
        print_info("Operation cancelled")
        return
    display_panel(
        "WARNING: Reverting to a snapshot will discard all changes made since the snapshot was taken.",
        style=NordColors.YELLOW,
        title="Data Loss Warning",
    )
    if not confirm_action(f"Confirm revert of VM '{vm}' to snapshot '{snap}'?"):
        print_info("Revert operation cancelled")
        return
    try:
        current_state = run_command(
            ["virsh", "domstate", vm], capture_output=True
        ).strip()
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Reverting to snapshot..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            console=console,
        ) as progress:
            revert_task = progress.add_task("Reverting", total=100)
            progress.update(revert_task, completed=20)
            run_command(["virsh", "snapshot-revert", vm, snap])
            progress.update(revert_task, completed=100)
        print_success(f"VM '{vm}' reverted to snapshot '{snap}' successfully")
        if "running" in current_state.lower():
            if confirm_action("VM was previously running. Start it now?"):
                print_info(f"Starting VM '{vm}'...")
                run_command(["virsh", "start", vm])
                print_success(f"VM '{vm}' started")
    except Exception as e:
        print_error(f"Failed to revert to snapshot: {e}")
        logging.error(f"Snapshot revert error: {e}")
    input(f"[bold {NordColors.PURPLE}]Press Enter to continue...[/]")


def delete_snapshot() -> None:
    console.clear()
    console.print(create_header())
    display_section_title("Delete VM Snapshot")
    vm = select_vm("Select a VM (or 'q' to cancel):")
    if not vm:
        print_info("Operation cancelled")
        return
    snap = select_snapshot(vm, "Select a snapshot to delete (or 'q' to cancel):")
    if not snap:
        print_info("Operation cancelled")
        return
    if not confirm_action(f"Delete snapshot '{snap}' for VM '{vm}'?"):
        print_info("Deletion cancelled")
        return
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Deleting snapshot..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            console=console,
        ) as progress:
            del_task = progress.add_task("Deleting", total=100)
            progress.update(del_task, completed=20)
            run_command(["virsh", "snapshot-delete", vm, snap])
            progress.update(del_task, completed=100)
        print_success(f"Snapshot '{snap}' deleted successfully")
    except Exception as e:
        print_error(f"Failed to delete snapshot: {e}")
        logging.error(f"Snapshot deletion error: {e}")
    input(f"[bold {NordColors.PURPLE}]Press Enter to continue...[/]")


# ----------------------------------------------------------------
# Menu System
# ----------------------------------------------------------------
def snapshot_management_menu() -> None:
    while True:
        console.clear()
        console.print(create_header())
        display_section_title("Snapshot Management")
        console.print(f"[{NordColors.SNOW_STORM_1}]1. List Snapshots[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]2. Create Snapshot[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]3. Revert to Snapshot[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]4. Delete Snapshot[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]5. Return to Main Menu[/]")
        choice = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Enter your choice (1-5):[/]"
        ).strip()
        if choice == "1":
            list_vm_snapshots()
        elif choice == "2":
            create_snapshot()
        elif choice == "3":
            revert_to_snapshot()
        elif choice == "4":
            delete_snapshot()
        elif choice == "5":
            break
        else:
            print_error("Invalid choice. Please enter a number between 1 and 5.")


def interactive_menu() -> None:
    while True:
        console.clear()
        console.print(create_header())
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )
        display_section_title("Main Menu")
        console.print(f"[{NordColors.SNOW_STORM_1}]1. List VMs[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]2. Create VM[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]3. Start VM[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]4. Stop VM[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]5. Delete VM[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]6. Show VM Info[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]7. Snapshot Management[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]8. Exit[/]")
        choice = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Enter your choice (1-8):[/]"
        ).strip()
        if choice == "1":
            list_vms()
        elif choice == "2":
            create_vm()
        elif choice == "3":
            start_vm()
        elif choice == "4":
            stop_vm()
        elif choice == "5":
            delete_vm()
        elif choice == "6":
            show_vm_info()
        elif choice == "7":
            snapshot_management_menu()
            continue
        elif choice == "8":
            console.clear()
            display_panel(
                "Thank you for using the VM Manager!",
                style=NordColors.FROST_2,
                title="Goodbye",
            )
            break
        else:
            print_error("Invalid choice. Please enter a number between 1 and 8.")
        if choice not in ["7", "8"]:
            Prompt.ask(f"[bold {NordColors.PURPLE}]Press Enter to continue...[/]")


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    try:
        console.clear()
        console.print(create_header())
        console.print(f"Hostname: [bold {NordColors.FROST_3}]{HOSTNAME}[/]")
        console.print(
            f"Date: [bold {NordColors.FROST_3}]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]\n"
        )
        if not check_root():
            sys.exit(1)
        setup_logging()
        logging.info(f"VM Manager v{VERSION} started")
        os.makedirs(ISO_DIR, exist_ok=True)
        os.makedirs(VM_IMAGE_DIR, exist_ok=True)
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        if not check_dependencies():
            logging.error("Missing critical dependencies")
            sys.exit(1)
        interactive_menu()
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        logging.info("Terminated by keyboard interrupt")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logging.exception("Unhandled exception")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
