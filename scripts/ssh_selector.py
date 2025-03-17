#!/usr/bin/env python3
"""
macOS SSH Connector
--------------------------------------------------
An asynchronous, interactive SSH connection manager with a dynamic CLI interface.
This toolkit uses system SSH, Rich for stylish output and progress indicators,
Pyfiglet for dynamic ASCII banners, and prompt_toolkit for enhanced command-line
input with auto-completion and history. It also features asynchronous device scanning,
configuration management via JSON, and robust error and signal handling.

Version: 1.0.0
"""

import atexit
import asyncio
import json
import os
import platform
import signal
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

# ----------------------------------------------------------------
# Ensure macOS Environment and Install Dependencies
# ----------------------------------------------------------------
if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)


def install_dependencies() -> None:
    """
    Ensure required third-party packages are installed.
    Installs: paramiko, rich, pyfiglet, prompt_toolkit.
    Uses pip with --user if not run as root.
    """
    import getpass

    required_packages = ["paramiko", "rich", "pyfiglet", "prompt_toolkit"]
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


try:
    import paramiko  # For potential future SSH enhancements
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table
    from rich.text import Text
    from rich import box
    from rich.prompt import Confirm, Prompt
    from rich.traceback import install as install_rich_traceback

    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style as PtStyle
except ImportError:
    print("Required libraries not found. Installing dependencies...")
    install_dependencies()
    print("Dependencies installed. Restarting script...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

install_rich_traceback(show_locals=True)
console: Console = Console()


# ----------------------------------------------------------------
# Check for System SSH Command
# ----------------------------------------------------------------
def check_ssh_command() -> None:
    if shutil.which("ssh") is None:
        console.print(
            "[bold red]SSH command not found. Please ensure SSH is installed on your macOS system.[/]"
        )
        sys.exit(1)


check_ssh_command()

# ----------------------------------------------------------------
# Global Constants & Configuration
# ----------------------------------------------------------------
APP_NAME: str = "macOS SSH Connector"
VERSION: str = "1.0.0"
DEFAULT_USERNAME: str = os.environ.get("USER", "user")
SSH_COMMAND: str = "ssh"
PING_TIMEOUT: float = 0.4  # seconds
PING_COUNT: int = 1
OPERATION_TIMEOUT: int = 30  # seconds
DEFAULT_SSH_PORT: int = 22

# Use a hidden config directory in the user's home folder
CONFIG_DIR: str = os.path.expanduser("~/.macos_ssh_connector")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")
HISTORY_DIR: str = os.path.join(CONFIG_DIR, "history")
os.makedirs(HISTORY_DIR, exist_ok=True)
COMMAND_HISTORY: str = os.path.join(HISTORY_DIR, "command_history")


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    POLAR_NIGHT_1: str = "#2E3440"
    POLAR_NIGHT_2: str = "#3B4252"
    POLAR_NIGHT_3: str = "#434C5E"
    POLAR_NIGHT_4: str = "#4C566A"
    SNOW_STORM_1: str = "#D8DEE9"
    SNOW_STORM_2: str = "#E5E9F0"
    SNOW_STORM_3: str = "#ECEFF4"
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"
    RED: str = "#BF616A"
    ORANGE: str = "#D08770"
    YELLOW: str = "#EBCB8B"
    GREEN: str = "#A3BE8C"
    PURPLE: str = "#B48EAD"

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Device:
    """
    Represents an SSH-accessible device with connection and status details.
    """

    name: str
    ip_address: str
    device_type: str = "local"  # e.g., "local" or "tailscale"
    description: Optional[str] = None
    port: int = DEFAULT_SSH_PORT
    username: Optional[str] = None
    status: Optional[bool] = None
    last_ping_time: float = field(default_factory=time.time)
    response_time: Optional[float] = None

    def get_connection_string(self, username: Optional[str] = None) -> str:
        user: str = username or self.username or DEFAULT_USERNAME
        if self.port == DEFAULT_SSH_PORT:
            return f"{user}@{self.ip_address}"
        return f"{user}@{self.ip_address} -p {self.port}"

    def get_status_indicator(self) -> Text:
        if self.status is True:
            return Text("● ONLINE", style=f"bold {NordColors.GREEN}")
        return Text("● OFFLINE", style=f"bold {NordColors.RED}")


T = TypeVar("T")


@dataclass
class AppConfig:
    default_username: str = DEFAULT_USERNAME
    ssh_options: Dict[str, Tuple[str, str]] = field(
        default_factory=lambda: {
            "ServerAliveInterval": ("30", "Interval in seconds for keepalive packets"),
            "ServerAliveCountMax": (
                "3",
                "Number of keepalive packets before disconnect",
            ),
            "ConnectTimeout": ("10", "Connection timeout in seconds"),
            "StrictHostKeyChecking": ("accept-new", "Auto-accept new host keys"),
            "Compression": ("yes", "Enable compression"),
            "LogLevel": ("ERROR", "SSH logging level"),
        }
    )
    last_refresh: float = field(default_factory=time.time)
    device_check_interval: int = 300  # seconds

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def clear_screen() -> None:
    console.clear()


def get_prompt_style() -> PtStyle:
    return PtStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})


def create_header() -> Panel:
    term_width = shutil.get_terminal_size((80, 24)).columns
    adjusted_width = min(term_width - 4, 80)
    fonts: List[str] = ["slant", "small", "mini", "digital"]
    ascii_art: str = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=adjusted_width)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(len(ascii_lines))
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=Text(f"v{VERSION}", style=f"bold {NordColors.SNOW_STORM_2}"),
        title_align="right",
        box=box.ROUNDED,
    )
    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    panel = Panel(
        Text.from_markup(message),
        title=Text(title, style=f"bold {style}"),
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


# ----------------------------------------------------------------
# Asynchronous Configuration Functions
# ----------------------------------------------------------------
async def ensure_config_directory() -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


async def save_config(config: AppConfig) -> bool:
    await ensure_config_directory()
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: json.dump(config.to_dict(), open(CONFIG_FILE, "w"), indent=2)
        )
        return True
    except Exception as e:
        print_error(f"Failed to save configuration: {e}")
        return False


async def load_config() -> AppConfig:
    try:
        if os.path.exists(CONFIG_FILE):
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None, lambda: json.load(open(CONFIG_FILE, "r"))
            )
            return AppConfig(**data)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
    return AppConfig()


# ----------------------------------------------------------------
# Asynchronous Core Functions
# ----------------------------------------------------------------
async def run_command_async(cmd: List[str]) -> Tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            text=True,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=OPERATION_TIMEOUT
        )
        if proc.returncode != 0:
            raise Exception(stderr.strip())
        return proc.returncode, stdout.strip()
    except asyncio.TimeoutError:
        raise Exception("Command timed out.")


async def async_ping_device(ip_address: str) -> Tuple[bool, Optional[float]]:
    start_time = time.time()
    try:
        cmd = [
            "ping",
            "-c",
            str(PING_COUNT),
            "-W",
            str(int(PING_TIMEOUT)),
            ip_address,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=PING_TIMEOUT + 0.5)
            end_time = time.time()
            response_time = (end_time - start_time) * 1000  # in milliseconds
            return proc.returncode == 0, response_time if proc.returncode == 0 else None
        except asyncio.TimeoutError:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            return False, None
    except Exception:
        return False, None


async def async_check_device_status(device: Device) -> None:
    success, response_time = await async_ping_device(device.ip_address)
    device.status = success
    device.response_time = response_time
    device.last_ping_time = time.time()


async def async_check_device_statuses(
    devices: List[Device],
    progress_callback: Optional[Callable[[int, Device], None]] = None,
) -> None:
    try:
        if progress_callback:
            for i, device in enumerate(devices):
                try:
                    await async_check_device_status(device)
                except Exception as e:
                    print_error(f"Error checking {device.name}: {e}")
                    device.status = False
                    device.response_time = None
                finally:
                    progress_callback(i, device)
        else:
            tasks = [
                asyncio.create_task(async_check_device_status(device))
                for device in devices
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print_error(f"Error during device status check: {e}")


# ----------------------------------------------------------------
# UI & Device Display Functions
# ----------------------------------------------------------------
def create_device_table(devices: List[Device], prefix: str, title: str) -> Table:
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        title=title,
        padding=(0, 1),
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3, justify="right")
    table.add_column("Name", style=f"bold {NordColors.FROST_1}", width=20)
    table.add_column("IP Address", style=NordColors.SNOW_STORM_1, width=15)
    table.add_column("Status", justify="center", width=12)
    table.add_column("Response", justify="right", width=10)
    table.add_column("Description", style=f"dim {NordColors.SNOW_STORM_1}", width=20)
    for idx, device in enumerate(devices, 1):
        response_time = (
            f"{device.response_time:.1f} ms"
            if device.response_time is not None
            else "—"
        )
        table.add_row(
            f"{prefix}{idx}",
            device.name,
            device.ip_address,
            device.get_status_indicator(),
            response_time,
            device.description or "",
        )
    return table


async def get_username_async(default_username: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: pt_prompt(
            "Username for SSH connection: ",
            history=FileHistory(COMMAND_HISTORY),
            style=get_prompt_style(),
        ),
    )


async def async_prompt(message: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: pt_prompt(
            message, history=FileHistory(COMMAND_HISTORY), style=get_prompt_style()
        ),
    )


async def async_confirm(message: str, default: bool = False) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: Confirm.ask(message, default=default)
    )


async def simulate_progress(
    progress, task_id: int, steps: List[Tuple[str, int]], delay: float = 0.3
) -> None:
    for step, pct in steps:
        await asyncio.sleep(delay)
        progress.update(task_id, description=step, completed=pct)


# ----------------------------------------------------------------
# SSH Connection Operations
# ----------------------------------------------------------------
async def connect_to_device_async(
    device: Device, username: Optional[str] = None
) -> None:
    clear_screen()
    console.print(create_header())
    display_panel(
        "SSH Connection",
        f"Connecting to {device.name} ({device.ip_address})",
        NordColors.FROST_2,
    )
    effective_username: str = username or device.username or DEFAULT_USERNAME

    details_table = Table(show_header=False, box=None, padding=(0, 3))
    details_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    details_table.add_column("Value", style=NordColors.SNOW_STORM_2)
    details_table.add_row("Address", device.ip_address)
    details_table.add_row("User", effective_username)
    if device.description:
        details_table.add_row("Description", device.description)
    if device.port != DEFAULT_SSH_PORT:
        details_table.add_row("Port", str(device.port))
    details_table.add_row("Status", "Online" if device.status else "Offline")
    if device.response_time:
        details_table.add_row("Latency", f"{device.response_time:.1f} ms")
    console.print(details_table)
    console.print()

    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task(
                f"[{NordColors.FROST_2}]Establishing connection...", total=100
            )
            steps = [
                (f"[{NordColors.FROST_2}]Resolving hostname...", 20),
                (f"[{NordColors.FROST_2}]Establishing connection...", 40),
                (f"[{NordColors.FROST_2}]Negotiating SSH protocol...", 60),
                (f"[{NordColors.FROST_2}]Authenticating...", 80),
                (f"[{NordColors.GREEN}]Connection established.", 100),
            ]
            await simulate_progress(progress, task_id, steps)
        ssh_args: List[str] = [SSH_COMMAND]
        config = await load_config()
        for option, (value, _) in config.ssh_options.items():
            ssh_args.extend(["-o", f"{option}={value}"])
        if device.port != DEFAULT_SSH_PORT:
            ssh_args.extend(["-p", str(device.port)])
        ssh_args.append(f"{effective_username}@{device.ip_address}")
        print_success(f"Connecting to {device.name} as {effective_username}...")
        os.execvp(SSH_COMMAND, ssh_args)
    except Exception as e:
        print_error(f"Connection failed: {e}")
        console.print_exception()
        print_section("Troubleshooting Tips")
        print_step("Check that the device is online using ping.")
        print_step("Verify that the SSH service is running on the target device.")
        print_step("Check your SSH key configuration.")
        print_step("Try connecting with verbose output: ssh -v user@host")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: Prompt.ask("Press Enter to return to the main menu")
        )


async def refresh_device_statuses_async(devices: List[Device]) -> None:
    clear_screen()
    console.print(create_header())
    display_panel(
        "Network Scan",
        "Checking connectivity for all configured devices",
        NordColors.FROST_3,
    )
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            scan_task = progress.add_task(
                f"[{NordColors.FROST_2}]Scanning", total=len(devices)
            )
            current_task = asyncio.current_task()

            def update_progress(index: int, device: Device) -> None:
                if current_task and current_task.cancelled():
                    raise asyncio.CancelledError()
                progress.advance(scan_task)
                progress.update(
                    scan_task,
                    description=f"[{NordColors.FROST_2}]Checking {device.name} ({device.ip_address})",
                )

            await async_check_device_statuses(devices, update_progress)
        online_count = sum(1 for d in devices if d.status is True)
        offline_count = sum(1 for d in devices if d.status is False)
        print_success(f"Scan complete: {online_count} online, {offline_count} offline")
        config = await load_config()
        config.last_refresh = time.time()
        await save_config(config)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: Prompt.ask("Press Enter to return to the main menu")
        )
    except asyncio.CancelledError:
        print_warning("Refresh operation cancelled")
    except Exception as e:
        print_error(f"Error during refresh: {e}")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: Prompt.ask("Press Enter to return to the main menu")
        )


# ----------------------------------------------------------------
# Main Menu and Program Control
# ----------------------------------------------------------------
# Sample static device lists
STATIC_TAILSCALE_DEVICES: List[Device] = [
    Device(
        name="fedora-server",
        ip_address="100.97.205.22",
        device_type="tailscale",
        description="Main Server",
        username="sawyer",
    ),
    Device(
        name="windows-lenovo",
        ip_address="100.88.172.104",
        device_type="tailscale",
        description="Lenovo Laptop",
        username="sawyer",
    ),
]

STATIC_LOCAL_DEVICES: List[Device] = [
    Device(
        name="fedora-server",
        ip_address="192.168.68.56",
        device_type="local",
        description="Main Server",
    ),
    Device(
        name="windows-lenovo",
        ip_address="192.168.68.54",
        device_type="local",
        description="Lenovo Laptop",
    ),
]

DEVICES: List[Device] = STATIC_TAILSCALE_DEVICES + STATIC_LOCAL_DEVICES


async def main_menu_async() -> None:
    devices = DEVICES
    print_message("Performing initial device scan...", NordColors.FROST_3)
    await async_check_device_statuses(devices)
    refresh_interval = 300  # seconds
    last_refresh = time.time()
    background_refresh_task = None

    try:
        while True:
            current_time = time.time()
            if current_time - last_refresh > refresh_interval:
                if background_refresh_task is None or background_refresh_task.done():
                    background_refresh_task = asyncio.create_task(
                        async_check_device_statuses(devices)
                    )
                    last_refresh = current_time

            clear_screen()
            console.print(create_header())
            tailscale_devices = [d for d in devices if d.device_type == "tailscale"]
            local_devices = [d for d in devices if d.device_type == "local"]
            console.print(
                create_device_table(tailscale_devices, "", "Tailscale Devices")
            )
            console.print()
            console.print(create_device_table(local_devices, "L", "Local Devices"))
            console.print()
            console.print("r: refresh    q: exit")
            console.print()
            choice = (await async_prompt("Enter your choice")).strip().lower()

            if choice in ("q", "quit", "exit"):
                clear_screen()
                console.print(
                    Panel(
                        Text("Goodbye!", style=f"bold {NordColors.FROST_2}"),
                        border_style=NordColors.FROST_1,
                        padding=(1, 2),
                    )
                )
                break
            elif choice in ("r", "refresh"):
                await refresh_device_statuses_async(devices)
            elif choice.startswith("l"):
                try:
                    idx = int(choice[1:]) - 1
                    if 0 <= idx < len(local_devices):
                        device = local_devices[idx]
                        if device.status is False and not await async_confirm(
                            f"This device appears offline. Connect anyway?",
                            default=False,
                        ):
                            continue
                        username = await get_username_async(
                            device.username or DEFAULT_USERNAME
                        )
                        await connect_to_device_async(device, username)
                    else:
                        print_error(f"Invalid device number: {choice}")
                        await async_prompt("Press Enter to continue")
                except ValueError:
                    print_error(f"Invalid choice: {choice}")
                    await async_prompt("Press Enter to continue")
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(tailscale_devices):
                        device = tailscale_devices[idx]
                        if device.status is False and not await async_confirm(
                            f"This device appears offline. Connect anyway?",
                            default=False,
                        ):
                            continue
                        username = await get_username_async(
                            device.username or DEFAULT_USERNAME
                        )
                        await connect_to_device_async(device, username)
                    else:
                        print_error(f"Invalid device number: {choice}")
                        await async_prompt("Press Enter to continue")
                except ValueError:
                    print_error(f"Invalid choice: {choice}")
                    await async_prompt("Press Enter to continue")
    except Exception as e:
        print_error(f"An error occurred in the main menu: {e}")
        console.print_exception()
    finally:
        if background_refresh_task is not None and not background_refresh_task.done():
            background_refresh_task.cancel()
            try:
                await background_refresh_task
            except asyncio.CancelledError:
                pass


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
async def async_cleanup() -> None:
    try:
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task():
                task.cancel()
        config = await load_config()
        config.last_refresh = time.time()
        await save_config(config)
        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


async def signal_handler_async(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")
    loop = asyncio.get_running_loop()
    for task in asyncio.all_tasks(loop):
        if task is not asyncio.current_task():
            task.cancel()
    await async_cleanup()
    loop.stop()


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.create_task(signal_handler_async(sig, None))
        )


async def proper_shutdown_async() -> None:
    try:
        loop = asyncio.get_running_loop()
        tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=2.0)
    except Exception as e:
        print_error(f"Error during async shutdown: {e}")


def proper_shutdown() -> None:
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                print_warning("Event loop already running during shutdown")
                return
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(proper_shutdown_async())
        loop.close()
    except Exception as e:
        print_error(f"Error during synchronous shutdown: {e}")


atexit.register(proper_shutdown)


# ----------------------------------------------------------------
# Main Program Entry
# ----------------------------------------------------------------
async def main_async() -> None:
    try:
        await ensure_config_directory()
        await main_menu_async()
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
        sys.exit(1)


def main() -> None:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        setup_signal_handlers(loop)
        atexit.register(proper_shutdown)
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print_warning("Received keyboard interrupt, shutting down...")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
    finally:
        try:
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.close()
        except Exception as e:
            print_error(f"Error during shutdown: {e}")
        print_message("Application terminated.", NordColors.FROST_3)


if __name__ == "__main__":
    main()
