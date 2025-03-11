#!/usr/bin/env python3
"""
Automated Nord-Themed Hello World
--------------------------------------------------

A streamlined terminal application that automatically displays a stylish
'Hello, World!' demonstration using a dynamic ASCII art header, a spinner,
and a styled panel. This script auto-installs required packages as needed
(using the standard local user on Linux/macOS when run as root) and supports
Linux, macOS, and Windows.

Version: 2.0.0
"""

import sys
import time
import signal
import atexit
import os
import subprocess
import platform

# ----------------------------------------------------------------
# OS Detection
# ----------------------------------------------------------------
CURRENT_OS = platform.system().lower()
# For Linux and macOS, if running as root we may want to run pip install commands
# as the original user using the SUDO_USER environment variable.
IS_ROOT = False
if CURRENT_OS in ["linux", "darwin"]:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        IS_ROOT = True


# ----------------------------------------------------------------
# Package Installation Helper Functions
# ----------------------------------------------------------------
def install_package(package: str) -> None:
    """
    Install the given package using pip. On Linux/macOS, if running as root,
    attempt to install as the standard user via SUDO_USER if available.
    """
    if CURRENT_OS in ["linux", "darwin"]:
        if IS_ROOT:
            sudo_user = os.environ.get("SUDO_USER")
            if sudo_user:
                # Run pip install as the original user
                cmd = f"su - {sudo_user} -c 'pip install {package}'"
            else:
                # Fallback to installing with --user flag
                cmd = f"pip install --user {package}"
        else:
            cmd = f"pip install {package}"
    else:
        # Windows (or any other OS)
        cmd = f"pip install {package}"
    print(f"Installing missing package: {package}\nRunning command: {cmd}")
    subprocess.check_call(cmd, shell=True)


def ensure_package_installed(package: str) -> None:
    """
    Attempt to import the package and install it if not found.
    """
    try:
        __import__(package)
    except ImportError:
        install_package(package)
        # Try to import again after installation
        __import__(package)


# Ensure required packages are installed.
ensure_package_installed("rich")
ensure_package_installed("pyfiglet")

# Now import the required modules.
import pyfiglet
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.align import Align
from rich.style import Style
from rich.traceback import install as install_rich_traceback

install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION = "2.0.0"
APP_NAME = "Hello World"
APP_SUBTITLE = "Nord-Themed Terminal Art"
DISPLAY_TEXT = "Hello, World!"
SPINNER_DURATION = 2.0


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    POLAR_NIGHT_1 = "#2E3440"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    SNOW_STORM_1 = "#D8DEE9"


# ----------------------------------------------------------------
# Create a Rich Console
# ----------------------------------------------------------------
console = Console()


# ----------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------
def create_header(text: str = APP_NAME) -> Panel:
    """
    Create an ASCII art header using Pyfiglet with Nord-themed styling.
    Uses the "slant" font.
    """
    fig = pyfiglet.Figlet(font="slant", width=60)
    ascii_art = fig.renderText(text)
    styled_text = ""
    for line in ascii_art.splitlines():
        styled_text += f"[bold {NordColors.FROST_2}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    full_text = f"{border}\n{styled_text}{border}"
    header_panel = Panel(
        Align.center(full_text),
        border_style=Style(color=NordColors.POLAR_NIGHT_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_1}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )
    return header_panel


def display_spinner(message: str, duration: float) -> None:
    """
    Display a spinner with the given message for a set duration.
    """
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_2}"),
        TextColumn(f"[{NordColors.SNOW_STORM_1}]{message}[/]"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        start_time = time.time()
        while time.time() - start_time < duration:
            time.sleep(0.1)


def display_panel(message: str, style: str = NordColors.FROST_2) -> None:
    """
    Display a message in a styled Rich panel.
    """
    panel = Panel(
        Align.center(message),
        border_style=Style(color=style),
        padding=(1, 2),
    )
    console.print(panel)


def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    console.print("[bold]Cleaning up resources...[/]")


def signal_handler(sig, frame) -> None:
    """Handle termination signals gracefully."""
    console.print(f"[bold {NordColors.FROST_3}]Process interrupted by signal {sig}[/]")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Application Flow
# ----------------------------------------------------------------
def main() -> None:
    console.clear()
    console.print(create_header())
    display_spinner("Initializing...", SPINNER_DURATION)
    # Use generic closing tag "[/]" to end styling
    display_panel(f"[bold {NordColors.FROST_2}]{DISPLAY_TEXT}[/]", NordColors.FROST_2)
    time.sleep(2)


if __name__ == "__main__":
    main()
