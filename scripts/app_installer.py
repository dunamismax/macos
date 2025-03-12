#!/usr/bin/env python3
"""
macOS Package Installer
--------------------------------------------------
A fully interactive, menu-driven installer that installs a list
of system packages using Homebrew and GUI applications using Homebrew Cask.
This script is designed for macOS. It uses Homebrew (with sudo as needed)
to install CLI packages and Homebrew Cask for GUI applications.

Features:
  • Interactive, menu-driven interface with dynamic ASCII banners.
  • Homebrew package installation with real-time progress tracking.
  • Cask application installation with progress spinners.
  • Custom package selection and group-based installation options.
  • System information display and package management.
  • Nord-themed color styling throughout the application.
  • Robust error handling and macOS–optimized behavior.

Version: 2.0.0
"""

import atexit
import os
import sys
import time
import socket
import getpass
import signal
import subprocess
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import List, Set, Optional, Dict, Any


# ----------------------------------------------------------------
# Dependency Check and Installation
# ----------------------------------------------------------------
def install_dependencies():
    """
    Install required Python dependencies using pip.
    Required packages:
      - paramiko
      - rich
      - pyfiglet
      - prompt_toolkit
    """
    required_packages = ["paramiko", "rich", "pyfiglet", "prompt_toolkit"]
    user = os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
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


def check_homebrew():
    """Ensure Homebrew is installed on macOS."""
    if shutil.which("brew") is None:
        print(
            "Homebrew is not installed. Please install Homebrew from https://brew.sh/ and rerun this script."
        )
        sys.exit(1)


# Attempt to import dependencies; install if missing
try:
    import paramiko
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
        TimeElapsedColumn,
        TimeRemainingColumn,
        BarColumn,
        TaskProgressColumn,
    )
    from rich.live import Live
    from rich.align import Align
    from rich.style import Style
    from rich.columns import Columns
    from rich.traceback import install as install_rich_traceback

    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PtStyle

except ImportError:
    print("Required libraries not found. Installing dependencies...")
    install_dependencies()
    print("Dependencies installed. Restarting script...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

install_rich_traceback(show_locals=True)
check_homebrew()

console: Console = Console()

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
HOSTNAME: str = socket.gethostname()
DEFAULT_USERNAME: str = (
    os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
)
VERSION: str = "2.0.0"
APP_NAME: str = "macOS Package Installer"
APP_SUBTITLE: str = "Advanced Homebrew & Cask Package Manager"

# Configure history and configuration directories
HISTORY_DIR = os.path.expanduser("~/.macos_pkg_installer")
os.makedirs(HISTORY_DIR, exist_ok=True)
COMMAND_HISTORY = os.path.join(HISTORY_DIR, "command_history")
PACKAGE_HISTORY = os.path.join(HISTORY_DIR, "package_history")
PACKAGE_LISTS_DIR = os.path.join(HISTORY_DIR, "package_lists")
os.makedirs(PACKAGE_LISTS_DIR, exist_ok=True)
for history_file in [COMMAND_HISTORY, PACKAGE_HISTORY]:
    if not os.path.exists(history_file):
        with open(history_file, "w") as f:
            pass


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


# ----------------------------------------------------------------
# Package Categories and Data Structures
# ----------------------------------------------------------------
class PackageType(Enum):
    BREW = auto()
    CASK = auto()


@dataclass
class PackageCategory:
    name: str
    description: str
    packages: List[str]
    package_type: PackageType
    selected: bool = True


@dataclass
class InstallationState:
    selected_brew_packages: Set[str] = field(default_factory=set)
    selected_cask_apps: Set[str] = field(default_factory=set)
    installation_complete: bool = False
    last_installed: Optional[datetime] = None
    error_packages: List[str] = field(default_factory=list)


install_state = InstallationState()

# ----------------------------------------------------------------
# Package Lists
# ----------------------------------------------------------------
# These lists have been adapted to use Homebrew package names.
BREW_CATEGORIES = [
    PackageCategory(
        name="shells_editors",
        description="Shells and Text Editors",
        packages=["bash", "vim", "nano", "screen", "tmux", "neovim", "emacs", "micro"],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="system_monitoring",
        description="System Monitoring Tools",
        packages=["htop", "btop", "tree", "iftop", "mtr", "glances", "dstat", "bpytop"],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="network_security",
        description="Network and Security Tools",
        packages=[
            "git",
            "openssh",
            "curl",
            "wget",
            "rsync",
            "nmap",
            "tcpdump",
            "wireshark",
            "netcat",
        ],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="core_utilities",
        description="Core System Utilities",
        packages=[
            "python3",
            "python3-pip",
            "ca-certificates",
            "gnupg",
            "pinentry",
            "keepassxc",
        ],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="development_tools",
        description="Development Tools",
        packages=["gcc", "make", "cmake", "ninja", "meson", "pkg-config"],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="enhanced_shells",
        description="Enhanced Shells and Utilities",
        packages=[
            "zsh",
            "fzf",
            "bat",
            "ripgrep",
            "ncdu",
            "fd",
            "exa",
            "lsd",
            "autojump",
            "direnv",
            "zoxide",
            "pv",
        ],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="containers_dev",
        description="Containers and Development",
        packages=["docker", "docker-compose", "podman", "node", "npm", "yarn"],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="debug_utilities",
        description="Debugging Utilities",
        packages=[
            "valgrind",
            "tig",
            "colordiff",
            "the_silver_searcher",
            "lsof",
            "socat",
        ],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="multimedia",
        description="Multimedia Tools",
        packages=["ffmpeg", "imagemagick"],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="database",
        description="Database Clients",
        packages=["mariadb", "postgresql", "sqlite", "redis"],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="virtualization",
        description="Virtualization Tools",
        packages=["qemu", "vagrant"],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="compression",
        description="File Compression and Archiving",
        packages=["p7zip", "unrar", "zip", "unzip", "tar", "lz4"],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="terminal_tools",
        description="Terminal Multiplexers and Tools",
        packages=["byobu", "kitty"],
        package_type=PackageType.BREW,
    ),
    PackageCategory(
        name="extras",
        description="Extras and Goodies",
        packages=["neofetch", "yt-dlp", "cmatrix", "tldr"],
        package_type=PackageType.BREW,
    ),
]

CASK_CATEGORIES = [
    PackageCategory(
        name="internet",
        description="Internet Applications",
        packages=["firefox", "thunderbird", "chromium", "tor-browser"],
        package_type=PackageType.CASK,
    ),
    PackageCategory(
        name="communication",
        description="Communication Apps",
        packages=["discord", "signal", "telegram-desktop", "slack", "zoom-us"],
        package_type=PackageType.CASK,
    ),
    PackageCategory(
        name="multimedia",
        description="Multimedia Applications",
        packages=["spotify", "vlc", "obs", "plex"],
        package_type=PackageType.CASK,
    ),
    PackageCategory(
        name="graphics",
        description="Graphics and Design",
        packages=["blender", "gimp", "inkscape", "krita"],
        package_type=PackageType.CASK,
    ),
    PackageCategory(
        name="gaming",
        description="Gaming",
        packages=["steam"],
        package_type=PackageType.CASK,
    ),
    PackageCategory(
        name="productivity",
        description="Productivity",
        packages=["obsidian", "libreoffice", "calibre", "onlyoffice", "okular"],
        package_type=PackageType.CASK,
    ),
    PackageCategory(
        name="system",
        description="System Tools",
        packages=["iterm2", "visual-studio-code"],
        package_type=PackageType.CASK,
    ),
    PackageCategory(
        name="utilities",
        description="Utilities",
        packages=["bitwarden", "filezilla", "postman"],
        package_type=PackageType.CASK,
    ),
]


# ----------------------------------------------------------------
# Enhanced Spinner Progress Manager
# ----------------------------------------------------------------
class SpinnerProgressManager:
    def __init__(self, title: str = "", auto_refresh: bool = True):
        self.title = title
        self.progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TextColumn("[{task.fields[status]}]"),
            TimeElapsedColumn(),
            TextColumn("[{task.fields[eta]}]"),
            auto_refresh=auto_refresh,
            console=console,
        )
        self.live = None
        self.tasks = {}
        self.start_times = {}
        self.is_started = False

    def start(self):
        if not self.is_started:
            self.live = Live(self.progress, console=console, refresh_per_second=10)
            self.live.start()
            self.is_started = True

    def stop(self):
        if self.is_started and self.live:
            self.live.stop()
            self.is_started = False

    def add_task(self, description: str, total_size: Optional[int] = None) -> str:
        task_id = f"task_{len(self.tasks)}"
        self.start_times[task_id] = time.time()
        self.tasks[task_id] = self.progress.add_task(
            description,
            status=f"[{NordColors.FROST_3}]Starting...",
            eta="Calculating...",
        )
        return task_id

    def update_task(self, task_id: str, status: str, completed: Optional[int] = None):
        if task_id not in self.tasks:
            return
        task = self.tasks[task_id]
        self.progress.update(task, status=status)
        if completed is not None:
            elapsed = time.time() - self.start_times[task_id]
            if completed > 0:
                total_time = elapsed * 100 / completed
                remaining = total_time - elapsed
                eta_str = f"[{NordColors.FROST_4}]ETA: {format_time(remaining)}"
            else:
                eta_str = f"[{NordColors.FROST_4}]Calculating..."
            status_with_percentage = (
                f"[{NordColors.FROST_3}]{status} [{NordColors.GREEN}]{completed}%[/]"
            )
            self.progress.update(task, status=status_with_percentage, eta=eta_str)

    def complete_task(self, task_id: str, success: bool = True):
        if task_id not in self.tasks:
            return
        task = self.tasks[task_id]
        status_color = NordColors.GREEN if success else NordColors.RED
        status_text = "COMPLETED" if success else "FAILED"
        elapsed = time.time() - self.start_times[task_id]
        elapsed_str = format_time(elapsed)
        status_msg = f"[bold {status_color}]{status_text}[/] in {elapsed_str}"
        self.progress.update(task, status=status_msg, eta="")


# ----------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------
def format_time(seconds: float) -> str:
    if seconds < 1:
        return "less than a second"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {int(seconds)}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m"


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)
    fonts = ["slant", "big", "digital", "standard", "small"]
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
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"
    border = f"[{NordColors.FROST_3}]{'━' * (adjusted_width - 6)}[/]"
    styled_text = border + "\n" + styled_text + border
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
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


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def print_section(title: str) -> None:
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")
    console.print()


def show_help() -> None:
    help_text = f"""
[bold]Available Commands:[/]

[bold {NordColors.FROST_2}]1-9, A-C, 0[/]:   Menu selection numbers
[bold {NordColors.FROST_2}]Tab[/]:         Auto-complete package names
[bold {NordColors.FROST_2}]Up/Down[/]:     Navigate command history
[bold {NordColors.FROST_2}]Ctrl+C[/]:      Cancel current operation
[bold {NordColors.FROST_2}]h[/]:           Show this help screen
"""
    console.print(
        Panel(
            Text.from_markup(help_text),
            title=f"[bold {NordColors.FROST_1}]Help & Commands[/]",
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )
    )


def get_prompt_style() -> PtStyle:
    return PtStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})


def wait_for_key() -> None:
    pt_prompt(
        "Press Enter to continue...",
        style=PtStyle.from_dict({"prompt": f"{NordColors.FROST_2}"}),
    )


# ----------------------------------------------------------------
# System Information and Status Functions
# ----------------------------------------------------------------
def get_macos_version() -> str:
    """Get the current macOS version."""
    try:
        version = subprocess.check_output(
            ["sw_vers", "-productVersion"], universal_newlines=True
        ).strip()
        return f"macOS {version}"
    except Exception:
        return "macOS (version unknown)"


def get_system_info() -> Dict[str, str]:
    info = {
        "Hostname": HOSTNAME,
        "User": DEFAULT_USERNAME,
        "OS": get_macos_version(),
        "Kernel": os.uname().release,
        "Architecture": os.uname().machine,
    }
    try:
        brew_version = subprocess.check_output(
            ["brew", "--version"], universal_newlines=True
        ).splitlines()[0]
        info["Homebrew Version"] = brew_version
    except Exception:
        info["Homebrew Version"] = "Not found"
    return info


def display_system_info() -> None:
    system_info = get_system_info()
    table = Table(
        title="System Information",
        show_header=False,
        expand=False,
        border_style=NordColors.FROST_3,
    )
    table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)
    for key, value in system_info.items():
        table.add_row(key, value)
    console.print(
        Panel(
            table,
            title="System Information",
            border_style=Style(color=NordColors.FROST_1),
        )
    )


# ----------------------------------------------------------------
# Package Management Functions
# ----------------------------------------------------------------
def get_all_brew_packages() -> List[str]:
    all_packages = []
    for category in BREW_CATEGORIES:
        if category.selected:
            all_packages.extend(category.packages)
    return all_packages


def get_all_cask_apps() -> List[str]:
    all_apps = []
    for category in CASK_CATEGORIES:
        if category.selected:
            all_apps.extend(category.packages)
    return all_apps


def update_selected_packages() -> None:
    install_state.selected_brew_packages = set(get_all_brew_packages())
    install_state.selected_cask_apps = set(get_all_cask_apps())


def install_brew_packages() -> None:
    update_selected_packages()
    if not install_state.selected_brew_packages:
        print_warning("No Homebrew packages selected for installation.")
        return
    packages_to_install = list(install_state.selected_brew_packages)
    display_panel(
        f"Installing [bold]{len(packages_to_install)}[/] Homebrew packages...",
        NordColors.PURPLE,
        "Homebrew Installation",
    )
    spinner = SpinnerProgressManager("Homebrew Installation")
    task_id = spinner.add_task(f"Installing {len(packages_to_install)} packages...")
    try:
        spinner.start()
        cmd = ["brew", "install"] + packages_to_install
        spinner.update_task(task_id, "Preparing Homebrew transaction...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )
        installed_count = 0
        error_packages = []
        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if "Installing" in line or "Updating" in line:
                    installed_count += 1
                    package_name = (
                        line.split()[1] if len(line.split()) > 1 else "package"
                    )
                    spinner.update_task(
                        task_id,
                        f"Installing {package_name}",
                        completed=int(installed_count / len(packages_to_install) * 100),
                    )
                if "Error:" in line or "Failed:" in line:
                    error_packages.append(line)
        return_code = process.wait()
        if return_code == 0:
            spinner.complete_task(task_id, True)
            print_success(
                f"Successfully installed {installed_count} Homebrew packages."
            )
            install_state.last_installed = datetime.now()
        else:
            spinner.complete_task(task_id, False)
            print_error(f"Homebrew installation failed with return code {return_code}")
            if error_packages:
                print_error(f"Packages with errors: {', '.join(error_packages)}")
                install_state.error_packages = error_packages
    except Exception as e:
        spinner.complete_task(task_id, False)
        print_error(f"Error during Homebrew installation: {e}")
    finally:
        spinner.stop()


def install_cask_apps() -> None:
    update_selected_packages()
    if not install_state.selected_cask_apps:
        print_warning("No Cask applications selected for installation.")
        return
    apps_to_install = list(install_state.selected_cask_apps)
    display_panel(
        f"Installing [bold]{len(apps_to_install)}[/] Cask applications...",
        NordColors.PURPLE,
        "Cask Installation",
    )
    spinner = SpinnerProgressManager("Cask Installation")
    task_id = spinner.add_task(f"Installing {len(apps_to_install)} applications...")
    try:
        spinner.start()
        cmd = ["brew", "install", "--cask"] + apps_to_install
        spinner.update_task(task_id, "Preparing Cask transaction...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )
        installed_count = 0
        error_apps = []
        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                for app_id in apps_to_install:
                    if app_id in line and ("Installing" in line or "Updating" in line):
                        installed_count += 1
                        spinner.update_task(
                            task_id,
                            f"Installing {app_id}",
                            completed=int(installed_count / len(apps_to_install) * 100),
                        )
                if "error:" in line.lower() or "failed:" in line.lower():
                    error_apps.append(line)
        return_code = process.wait()
        if return_code == 0:
            spinner.complete_task(task_id, True)
            print_success(
                f"Successfully installed {installed_count} Cask applications."
            )
            install_state.last_installed = datetime.now()
        else:
            spinner.complete_task(task_id, False)
            print_error(f"Cask installation failed with return code {return_code}")
            if error_apps:
                print_error(f"Applications with errors: {', '.join(error_apps)}")
                install_state.error_packages.extend(error_apps)
    except Exception as e:
        spinner.complete_task(task_id, False)
        print_error(f"Error during Cask installation: {e}")
    finally:
        spinner.stop()


def install_all() -> None:
    update_selected_packages()
    if install_state.selected_brew_packages:
        install_brew_packages()
    if install_state.selected_cask_apps:
        install_cask_apps()
    install_state.installation_complete = True
    if not install_state.error_packages:
        display_panel(
            "All selected packages and applications have been successfully installed!",
            NordColors.GREEN,
            "Installation Complete",
        )
    else:
        display_panel(
            f"Installation completed with {len(install_state.error_packages)} errors.",
            NordColors.YELLOW,
            "Installation Completed with Warnings",
        )


def manage_brew_categories() -> None:
    while True:
        console.clear()
        console.print(create_header())
        print_section("Homebrew Package Categories")
        table = Table(
            title="Available Homebrew Package Categories",
            show_header=True,
            header_style=f"bold {NordColors.FROST_3}",
            expand=True,
        )
        table.add_column("No.", style="bold", width=4)
        table.add_column("Category", style="bold")
        table.add_column("Description")
        table.add_column("Packages", justify="right")
        table.add_column("Status", style="bold")
        for idx, category in enumerate(BREW_CATEGORIES, start=1):
            status_style = NordColors.GREEN if category.selected else NordColors.RED
            status_text = "SELECTED" if category.selected else "EXCLUDED"
            table.add_row(
                str(idx),
                category.name,
                category.description,
                str(len(category.packages)),
                f"[{status_style}]{status_text}[/]",
            )
        console.print(table)
        console.print()
        console.print(f"[bold {NordColors.PURPLE}]Category Management Options:[/]")
        console.print(
            f"[{NordColors.FROST_2}]1-{len(BREW_CATEGORIES)}[/]: Toggle category selection"
        )
        console.print(f"[{NordColors.FROST_2}]A[/]: Select All Categories")
        console.print(f"[{NordColors.FROST_2}]N[/]: Deselect All Categories")
        console.print(f"[{NordColors.FROST_2}]B[/]: Back to Main Menu")
        console.print()
        choice = pt_prompt(
            "Enter your choice: ",
            history=FileHistory(COMMAND_HISTORY),
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).upper()
        if choice == "B":
            break
        elif choice == "A":
            for category in BREW_CATEGORIES:
                category.selected = True
            print_success("All Homebrew categories selected.")
            time.sleep(1)
        elif choice == "N":
            for category in BREW_CATEGORIES:
                category.selected = False
            print_warning("All Homebrew categories deselected.")
            time.sleep(1)
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(BREW_CATEGORIES):
                    BREW_CATEGORIES[idx].selected = not BREW_CATEGORIES[idx].selected
                    status = (
                        "selected" if BREW_CATEGORIES[idx].selected else "deselected"
                    )
                    print_success(f"Category '{BREW_CATEGORIES[idx].name}' {status}.")
                    time.sleep(0.5)
                else:
                    print_error(f"Invalid selection: {choice}")
                    time.sleep(0.5)
            except ValueError:
                print_error(f"Invalid input: {choice}")
                time.sleep(0.5)
        update_selected_packages()


def manage_cask_categories() -> None:
    while True:
        console.clear()
        console.print(create_header())
        print_section("Cask Application Categories")
        table = Table(
            title="Available Cask Application Categories",
            show_header=True,
            header_style=f"bold {NordColors.FROST_3}",
            expand=True,
        )
        table.add_column("No.", style="bold", width=4)
        table.add_column("Category", style="bold")
        table.add_column("Description")
        table.add_column("Apps", justify="right")
        table.add_column("Status", style="bold")
        for idx, category in enumerate(CASK_CATEGORIES, start=1):
            status_style = NordColors.GREEN if category.selected else NordColors.RED
            status_text = "SELECTED" if category.selected else "EXCLUDED"
            table.add_row(
                str(idx),
                category.name,
                category.description,
                str(len(category.packages)),
                f"[{status_style}]{status_text}[/]",
            )
        console.print(table)
        console.print()
        console.print(f"[bold {NordColors.PURPLE}]Category Management Options:[/]")
        console.print(
            f"[{NordColors.FROST_2}]1-{len(CASK_CATEGORIES)}[/]: Toggle category selection"
        )
        console.print(f"[{NordColors.FROST_2}]A[/]: Select All Categories")
        console.print(f"[{NordColors.FROST_2}]N[/]: Deselect All Categories")
        console.print(f"[{NordColors.FROST_2}]B[/]: Back to Main Menu")
        console.print()
        choice = pt_prompt(
            "Enter your choice: ",
            history=FileHistory(COMMAND_HISTORY),
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).upper()
        if choice == "B":
            break
        elif choice == "A":
            for category in CASK_CATEGORIES:
                category.selected = True
            print_success("All Cask categories selected.")
            time.sleep(1)
        elif choice == "N":
            for category in CASK_CATEGORIES:
                category.selected = False
            print_warning("All Cask categories deselected.")
            time.sleep(1)
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(CASK_CATEGORIES):
                    CASK_CATEGORIES[idx].selected = not CASK_CATEGORIES[idx].selected
                    status = (
                        "selected" if CASK_CATEGORIES[idx].selected else "deselected"
                    )
                    print_success(f"Category '{CASK_CATEGORIES[idx].name}' {status}.")
                    time.sleep(0.5)
                else:
                    print_error(f"Invalid selection: {choice}")
                    time.sleep(0.5)
            except ValueError:
                print_error(f"Invalid input: {choice}")
                time.sleep(0.5)
        update_selected_packages()


def custom_package_selection() -> None:
    while True:
        console.clear()
        console.print(create_header())
        print_section("Custom Package Selection")
        console.print(f"[bold {NordColors.PURPLE}]Package Selection Options:[/]")
        console.print(f"[{NordColors.FROST_2}]1[/]: Manage Homebrew Package Selections")
        console.print(f"[{NordColors.FROST_2}]2[/]: Manage Cask Application Selections")
        console.print(f"[{NordColors.FROST_2}]3[/]: Add Custom Homebrew Package")
        console.print(f"[{NordColors.FROST_2}]4[/]: Add Custom Cask Application")
        console.print(f"[{NordColors.FROST_2}]B[/]: Back to Main Menu")
        console.print()
        choice = pt_prompt(
            "Enter your choice: ",
            history=FileHistory(COMMAND_HISTORY),
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).upper()
        if choice == "B":
            break
        elif choice == "1":
            manage_brew_package_selections()
        elif choice == "2":
            manage_cask_app_selections()
        elif choice == "3":
            add_custom_brew_package()
        elif choice == "4":
            add_custom_cask_app()
        else:
            print_error(f"Invalid selection: {choice}")
            time.sleep(0.5)


def manage_brew_package_selections() -> None:
    update_selected_packages()
    all_packages = []
    for category in BREW_CATEGORIES:
        for package in category.packages:
            all_packages.append(
                (
                    package,
                    category.name,
                    package in install_state.selected_brew_packages,
                )
            )
    all_packages.sort(key=lambda x: x[0])
    while True:
        console.clear()
        console.print(create_header())
        print_section("Homebrew Package Selection")
        page_size = 20
        total_pages = (len(all_packages) + page_size - 1) // page_size
        current_page = 1
        while True:
            console.clear()
            console.print(create_header())
            start_idx = (current_page - 1) * page_size
            end_idx = min(start_idx + page_size, len(all_packages))
            table = Table(
                title=f"Homebrew Packages (Page {current_page}/{total_pages})",
                show_header=True,
                header_style=f"bold {NordColors.FROST_3}",
                expand=True,
            )
            table.add_column("No.", style="bold", width=4)
            table.add_column("Package", style="bold")
            table.add_column("Category")
            table.add_column("Status", style="bold")
            for i, (package, category, selected) in enumerate(
                all_packages[start_idx:end_idx], start=start_idx + 1
            ):
                status_style = NordColors.GREEN if selected else NordColors.RED
                status_text = "SELECTED" if selected else "EXCLUDED"
                table.add_row(
                    str(i), package, category, f"[{status_style}]{status_text}[/]"
                )
            console.print(table)
            console.print()
            console.print(f"[bold {NordColors.PURPLE}]Navigation and Options:[/]")
            console.print(
                f"[{NordColors.FROST_2}]1-{end_idx - start_idx}[/]: Toggle package selection"
            )
            console.print(f"[{NordColors.FROST_2}]N[/]: Next Page")
            console.print(f"[{NordColors.FROST_2}]P[/]: Previous Page")
            console.print(f"[{NordColors.FROST_2}]S[/]: Search Packages")
            console.print(f"[{NordColors.FROST_2}]B[/]: Back to Custom Package Menu")
            console.print()
            choice = pt_prompt(
                "Enter your choice: ",
                history=FileHistory(COMMAND_HISTORY),
                auto_suggest=AutoSuggestFromHistory(),
                style=get_prompt_style(),
            ).upper()
            if choice == "B":
                break
            elif choice == "N":
                if current_page < total_pages:
                    current_page += 1
            elif choice == "P":
                if current_page > 1:
                    current_page -= 1
            elif choice == "S":
                search_term = pt_prompt(
                    "Enter search term: ",
                    history=FileHistory(PACKAGE_HISTORY),
                    auto_suggest=AutoSuggestFromHistory(),
                    style=get_prompt_style(),
                ).lower()
                matching_packages = [
                    (i + 1, package, category, selected)
                    for i, (package, category, selected) in enumerate(all_packages)
                    if search_term in package.lower() or search_term in category.lower()
                ]
                if not matching_packages:
                    print_warning(f"No packages found matching '{search_term}'")
                    time.sleep(1)
                    continue
                search_table = Table(
                    title=f"Search Results for '{search_term}'",
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_3}",
                    expand=True,
                )
                search_table.add_column("No.", style="bold", width=4)
                search_table.add_column("Package", style="bold")
                search_table.add_column("Category")
                search_table.add_column("Status", style="bold")
                for idx, package, category, selected in matching_packages:
                    status_style = NordColors.GREEN if selected else NordColors.RED
                    status_text = "SELECTED" if selected else "EXCLUDED"
                    search_table.add_row(
                        str(idx), package, category, f"[{status_style}]{status_text}[/]"
                    )
                console.print(search_table)
                console.print()
                search_choice = pt_prompt(
                    "Enter package number to toggle selection (or 'C' to cancel): ",
                    history=FileHistory(COMMAND_HISTORY),
                    auto_suggest=AutoSuggestFromHistory(),
                    style=get_prompt_style(),
                ).upper()
                if search_choice == "C":
                    continue
                try:
                    search_idx = int(search_choice) - 1
                    if 0 <= search_idx < len(all_packages):
                        package, category, selected = all_packages[search_idx]
                        all_packages[search_idx] = (package, category, not selected)
                        status = "selected" if not selected else "deselected"
                        print_success(f"Package '{package}' {status}.")
                        time.sleep(0.5)
                    else:
                        print_error(f"Invalid package number: {search_choice}")
                        time.sleep(0.5)
                except ValueError:
                    print_error(f"Invalid input: {search_choice}")
                    time.sleep(0.5)
            else:
                try:
                    idx = int(choice) - 1 + start_idx
                    if 0 <= idx < len(all_packages):
                        package, category, selected = all_packages[idx]
                        all_packages[idx] = (package, category, not selected)
                        status = "selected" if not selected else "deselected"
                        print_success(f"Package '{package}' {status}.")
                        time.sleep(0.5)
                    else:
                        print_error(f"Invalid package number: {choice}")
                        time.sleep(0.5)
                except ValueError:
                    print_error(f"Invalid input: {choice}")
                    time.sleep(0.5)
        selected_packages = {
            package for package, _, selected in all_packages if selected
        }
        install_state.selected_brew_packages = selected_packages
        break


def manage_cask_app_selections() -> None:
    update_selected_packages()
    all_apps = []
    for category in CASK_CATEGORIES:
        for app in category.packages:
            all_apps.append(
                (app, category.name, app in install_state.selected_cask_apps)
            )
    all_apps.sort(key=lambda x: x[0])
    while True:
        console.clear()
        console.print(create_header())
        print_section("Cask Application Selection")
        page_size = 20
        total_pages = (len(all_apps) + page_size - 1) // page_size
        current_page = 1
        while True:
            console.clear()
            console.print(create_header())
            start_idx = (current_page - 1) * page_size
            end_idx = min(start_idx + page_size, len(all_apps))
            table = Table(
                title=f"Cask Applications (Page {current_page}/{total_pages})",
                show_header=True,
                header_style=f"bold {NordColors.FROST_3}",
                expand=True,
            )
            table.add_column("No.", style="bold", width=4)
            table.add_column("Application", style="bold")
            table.add_column("Category")
            table.add_column("Status", style="bold")
            for i, (app, category, selected) in enumerate(
                all_apps[start_idx:end_idx], start=start_idx + 1
            ):
                status_style = NordColors.GREEN if selected else NordColors.RED
                status_text = "SELECTED" if selected else "EXCLUDED"
                table.add_row(
                    str(i), app, category, f"[{status_style}]{status_text}[/]"
                )
            console.print(table)
            console.print()
            console.print(f"[bold {NordColors.PURPLE}]Navigation and Options:[/]")
            console.print(
                f"[{NordColors.FROST_2}]1-{end_idx - start_idx}[/]: Toggle application selection"
            )
            console.print(f"[{NordColors.FROST_2}]N[/]: Next Page")
            console.print(f"[{NordColors.FROST_2}]P[/]: Previous Page")
            console.print(f"[{NordColors.FROST_2}]S[/]: Search Applications")
            console.print(f"[{NordColors.FROST_2}]B[/]: Back to Custom Package Menu")
            console.print()
            choice = pt_prompt(
                "Enter your choice: ",
                history=FileHistory(COMMAND_HISTORY),
                auto_suggest=AutoSuggestFromHistory(),
                style=get_prompt_style(),
            ).upper()
            if choice == "B":
                break
            elif choice == "N":
                if current_page < total_pages:
                    current_page += 1
            elif choice == "P":
                if current_page > 1:
                    current_page -= 1
            elif choice == "S":
                search_term = pt_prompt(
                    "Enter search term: ",
                    history=FileHistory(PACKAGE_HISTORY),
                    auto_suggest=AutoSuggestFromHistory(),
                    style=get_prompt_style(),
                ).lower()
                matching_apps = [
                    (i + 1, app, category, selected)
                    for i, (app, category, selected) in enumerate(all_apps)
                    if search_term in app.lower() or search_term in category.lower()
                ]
                if not matching_apps:
                    print_warning(f"No applications found matching '{search_term}'")
                    time.sleep(1)
                    continue
                search_table = Table(
                    title=f"Search Results for '{search_term}'",
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_3}",
                    expand=True,
                )
                search_table.add_column("No.", style="bold", width=4)
                search_table.add_column("Application", style="bold")
                search_table.add_column("Category")
                search_table.add_column("Status", style="bold")
                for idx, app, category, selected in matching_apps:
                    status_style = NordColors.GREEN if selected else NordColors.RED
                    status_text = "SELECTED" if selected else "EXCLUDED"
                    search_table.add_row(
                        str(idx), app, category, f"[{status_style}]{status_text}[/]"
                    )
                console.print(search_table)
                console.print()
                search_choice = pt_prompt(
                    "Enter application number to toggle selection (or 'C' to cancel): ",
                    history=FileHistory(COMMAND_HISTORY),
                    auto_suggest=AutoSuggestFromHistory(),
                    style=get_prompt_style(),
                ).upper()
                if search_choice == "C":
                    continue
                try:
                    search_idx = int(search_choice) - 1
                    if 0 <= search_idx < len(all_apps):
                        app, category, selected = all_apps[search_idx]
                        all_apps[search_idx] = (app, category, not selected)
                        status = "selected" if not selected else "deselected"
                        print_success(f"Application '{app}' {status}.")
                        time.sleep(0.5)
                    else:
                        print_error(f"Invalid application number: {search_choice}")
                        time.sleep(0.5)
                except ValueError:
                    print_error(f"Invalid input: {search_choice}")
                    time.sleep(0.5)
            else:
                try:
                    idx = int(choice) - 1 + start_idx
                    if 0 <= idx < len(all_apps):
                        app, category, selected = all_apps[idx]
                        all_apps[idx] = (app, category, not selected)
                        status = "selected" if not selected else "deselected"
                        print_success(f"Application '{app}' {status}.")
                        time.sleep(0.5)
                    else:
                        print_error(f"Invalid application number: {choice}")
                        time.sleep(0.5)
                except ValueError:
                    print_error(f"Invalid input: {choice}")
                    time.sleep(0.5)
        selected_apps = {app for app, _, selected in all_apps if selected}
        install_state.selected_cask_apps = selected_apps
        break


def add_custom_brew_package() -> None:
    console.clear()
    console.print(create_header())
    print_section("Add Custom Homebrew Package")
    custom_package = pt_prompt(
        "Enter the Homebrew package name to add: ",
        history=FileHistory(PACKAGE_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )
    if not custom_package:
        print_warning("No package name provided, returning to menu.")
        time.sleep(1)
        return
    spinner = SpinnerProgressManager("Package Verification")
    task_id = spinner.add_task(f"Checking if package '{custom_package}' exists...")
    try:
        spinner.start()
        search_cmd = ["brew", "search", custom_package]
        process = subprocess.Popen(
            search_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        stdout, _ = process.communicate()
        if "No formula found" in stdout or process.returncode != 0:
            spinner.complete_task(task_id, False)
            print_warning(
                f"Package '{custom_package}' not found in Homebrew repositories."
            )
            if Confirm.ask(
                f"[bold {NordColors.YELLOW}]Add package anyway?[/]", default=False
            ):
                update_selected_packages()
                install_state.selected_brew_packages.add(custom_package)
                print_success(f"Added '{custom_package}' to the installation list.")
        else:
            spinner.complete_task(task_id, True)
            update_selected_packages()
            install_state.selected_brew_packages.add(custom_package)
            print_success(
                f"Package '{custom_package}' found and added to the installation list."
            )
    except Exception as e:
        spinner.complete_task(task_id, False)
        print_error(f"Error checking package: {e}")
    finally:
        spinner.stop()
        wait_for_key()


def add_custom_cask_app() -> None:
    console.clear()
    console.print(create_header())
    print_section("Add Custom Cask Application")
    custom_app = pt_prompt(
        "Enter the Cask application name to add: ",
        history=FileHistory(PACKAGE_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )
    if not custom_app:
        print_warning("No application name provided, returning to menu.")
        time.sleep(1)
        return
    spinner = SpinnerProgressManager("Application Verification")
    task_id = spinner.add_task(f"Checking if application '{custom_app}' exists...")
    try:
        spinner.start()
        search_cmd = ["brew", "search", "--casks", custom_app]
        process = subprocess.Popen(
            search_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        stdout, _ = process.communicate()
        if not stdout.strip() or process.returncode != 0:
            spinner.complete_task(task_id, False)
            print_warning(
                f"Application '{custom_app}' not found in Homebrew Cask repositories."
            )
            if Confirm.ask(
                f"[bold {NordColors.YELLOW}]Add application anyway?[/]", default=False
            ):
                update_selected_packages()
                install_state.selected_cask_apps.add(custom_app)
                print_success(f"Added '{custom_app}' to the installation list.")
        else:
            spinner.complete_task(task_id, True)
            update_selected_packages()
            install_state.selected_cask_apps.add(custom_app)
            print_success(
                f"Application '{custom_app}' found and added to the installation list."
            )
    except Exception as e:
        spinner.complete_task(task_id, False)
        print_error(f"Error checking application: {e}")
    finally:
        spinner.stop()
        wait_for_key()


def update_system() -> None:
    console.clear()
    console.print(create_header())
    print_section("System Update")
    if not Confirm.ask(
        f"[bold {NordColors.YELLOW}]Do you want to update your system using Homebrew?[/]",
        default=True,
    ):
        print_warning("Update cancelled.")
        time.sleep(1)
        return
    spinner = SpinnerProgressManager("System Update")
    task_id = spinner.add_task("Updating Homebrew packages...")
    try:
        spinner.start()
        spinner.update_task(task_id, "Running: brew update && brew upgrade")
        cmd = ["brew", "update"]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )
        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if line:
                    spinner.update_task(task_id, line)
        process.wait()
        cmd2 = ["brew", "upgrade"]
        process2 = subprocess.Popen(
            cmd2,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )
        if process2.stdout:
            for line in process2.stdout:
                line = line.strip()
                if line:
                    spinner.update_task(task_id, line)
        return_code = process2.wait()
        if return_code == 0:
            spinner.complete_task(task_id, True)
            print_success("System update completed successfully.")
        else:
            spinner.complete_task(task_id, False)
            print_error(f"System update failed with return code {return_code}")
    except Exception as e:
        spinner.complete_task(task_id, False)
        print_error(f"Error during system update: {e}")
    finally:
        spinner.stop()
        wait_for_key()


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    print_message("Cleaning up session resources...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
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
# Main Menu and Program Control
# ----------------------------------------------------------------
def display_status_bar() -> None:
    status_color = (
        NordColors.GREEN if install_state.installation_complete else NordColors.YELLOW
    )
    status_text = "INSTALLED" if install_state.installation_complete else "PENDING"
    brew_count = len(install_state.selected_brew_packages)
    cask_count = len(install_state.selected_cask_apps)
    last_installed_text = (
        f"Last installed: {install_state.last_installed.strftime('%Y-%m-%d %H:%M:%S')}"
        if install_state.last_installed
        else "Not installed yet"
    )
    console.print(
        Panel(
            Text.from_markup(
                f"[bold {status_color}]Status: {status_text}[/] | "
                f"Brew Packages: [bold]{brew_count}[/] | "
                f"Cask Apps: [bold]{cask_count}[/] | "
                f"[dim]{last_installed_text}[/]"
            ),
            border_style=NordColors.FROST_4,
            padding=(0, 2),
        )
    )


def main_menu() -> None:
    menu_options = [
        ("1", "Install Homebrew Packages", install_brew_packages),
        ("2", "Install Cask Applications", install_cask_apps),
        ("3", "Install Both Brew & Cask", install_all),
        ("4", "Manage Homebrew Package Categories", manage_brew_categories),
        ("5", "Manage Cask App Categories", manage_cask_categories),
        ("6", "Custom Package Selection", custom_package_selection),
        ("7", "Update System", update_system),
        ("8", "System Information", display_system_info),
        ("H", "Show Help", show_help),
        ("0", "Exit", lambda: None),
    ]
    while True:
        console.clear()
        console.print(create_header())
        display_status_bar()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | [{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )
        console.print()
        console.print(f"[bold {NordColors.PURPLE}]Main Menu[/]")
        table = Table(
            show_header=True, header_style=f"bold {NordColors.FROST_3}", expand=True
        )
        table.add_column("Option", style="bold", width=8)
        table.add_column("Description", style="bold")
        for option, description, _ in menu_options:
            table.add_row(option, description)
        console.print(table)
        command_history = FileHistory(COMMAND_HISTORY)
        choice = pt_prompt(
            "Enter your choice: ",
            history=command_history,
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).upper()
        if choice == "0":
            console.print()
            console.print(
                Panel(
                    Text(
                        f"Thank you for using the macOS Package Installer!",
                        style=f"bold {NordColors.FROST_2}",
                    ),
                    border_style=Style(color=NordColors.FROST_1),
                    padding=(1, 2),
                )
            )
            sys.exit(0)
        else:
            for option, _, func in menu_options:
                if choice == option:
                    func()
                    wait_for_key()
                    break
            else:
                print_error(f"Invalid selection: {choice}")
                wait_for_key()


def main() -> None:
    update_selected_packages()
    console.clear()
    main_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user")
        cleanup()
        sys.exit(0)
    except Exception as e:
        console.print_exception()
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)
