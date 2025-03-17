#!/usr/bin/env python3
"""
Hello World App for macOS with Pyfiglet
---------------------------------------
This script is a simple Hello World application for macOS that uses Pyfiglet to generate
an ASCII art banner with the text "Hello World!" in the slant font. It follows the guidelines
for dependency management, macOS-specific checks, and a polished CLI interface using Rich and
Prompt Toolkit.
"""

import atexit
import getpass
import os
import platform
import shutil
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

# Dependency Imports with Fallback Installation
# -----------------------------------------------
# We require: pyfiglet, rich, prompt_toolkit
REQUIRED_PYTHON_PACKAGES = ["pyfiglet", "rich", "prompt_toolkit"]


def install_missing_packages() -> None:
    """Check for and install required Python packages if missing."""
    for package in REQUIRED_PYTHON_PACKAGES:
        try:
            __import__(package)
        except ImportError:
            print(f"Package '{package}' not found. Installing via pip...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package], check=True
            )


install_missing_packages()

import pyfiglet
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.text import Text
from rich.traceback import install as install_rich_traceback

# Install Rich traceback handler for improved error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Constants & Configuration for macOS
# ----------------------------------------------------------------
APP_NAME: str = "Hello World App"
APP_VERSION: str = "1.0.0-macos"
ORIGINAL_USER: str = getpass.getuser()
HOME_DIR: str = os.path.expanduser("~")
BREW_CMD: str = "brew"  # Homebrew command

# Set up the Rich console
console: Console = Console()


# ----------------------------------------------------------------
# Nord-Themed Colors (Optional Customization)
# ----------------------------------------------------------------
class NordColors:
    POLAR_NIGHT_1: str = "#2E3440"
    SNOW_STORM_1: str = "#D8DEE9"
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"
    RED: str = "#BF616A"
    GREEN: str = "#A3BE8C"
    YELLOW: str = "#EBCB8B"


# ----------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------
def run_command(
    cmd: list, shell: bool = False, check: bool = True, timeout: int = 60
) -> subprocess.CompletedProcess:
    """
    Executes a command and returns the CompletedProcess instance.
    """
    cmd_str = " ".join(cmd)
    console.print(f"[bold {NordColors.FROST_3}]Running:[/] {cmd_str}")
    result = subprocess.run(
        cmd, shell=shell, check=check, capture_output=True, text=True, timeout=timeout
    )
    return result


def check_system() -> bool:
    """
    Performs macOS system checks:
      - Ensure the script is NOT run as root.
      - Ensure the operating system is macOS.
      - Check for Homebrew installation.
    """
    if os.geteuid() == 0:
        console.print(
            f"[bold {NordColors.RED}]Do not run this script as root. Please run as your normal user.[/]"
        )
        return False
    if platform.system().lower() != "darwin":
        console.print(
            f"[bold {NordColors.RED}]This script is intended for macOS (Darwin) only.[/]"
        )
        return False
    if not shutil.which(BREW_CMD):
        console.print(
            f"[bold {NordColors.RED}]Homebrew is not installed. Please install it from https://brew.sh[/]"
        )
        return False
    # Display basic system info
    sys_info = f"User: {ORIGINAL_USER} | OS: {platform.platform()} | Home: {HOME_DIR}"
    console.print(
        Panel(
            sys_info, title="[bold]System Information[/bold]", style=NordColors.FROST_2
        )
    )
    return True


def create_ascii_banner(text: str, font: str = "slant") -> Panel:
    """
    Create an ASCII art banner using Pyfiglet and wrap it in a Rich Panel.
    """
    try:
        fig = pyfiglet.Figlet(font=font)
        ascii_art = fig.renderText(text)
    except Exception:
        ascii_art = text
    # Stylize ASCII art using Rich markup
    styled_art = f"[bold {NordColors.FROST_1}]{ascii_art}[/]"
    panel = Panel(
        styled_art,
        border_style=NordColors.FROST_3,
        title=f"[bold]{APP_NAME}[/]",
        subtitle=f"v{APP_VERSION}",
        padding=(1, 2),
    )
    return panel


def cleanup() -> None:
    """Cleanup tasks before exiting."""
    console.print(f"[bold {NordColors.FROST_2}]Cleaning up...[/]")


def signal_handler(sig, frame) -> None:
    """
    Gracefully handle termination signals like SIGINT and SIGTERM.
    """
    console.print(
        f"[bold {NordColors.YELLOW}]Received signal {signal.Signals(sig).name}. Exiting...[/]"
    )
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Application Logic
# ----------------------------------------------------------------
def main() -> None:
    """
    Main function for the Hello World application.
    Performs system checks, displays an ASCII art banner, and prints "Hello World!".
    """
    console.print("\n")
    # Display header/banner
    banner = create_ascii_banner("Hello World!")
    console.print(banner)

    # Display current time and basic info
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    info = Align.center(
        f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/]", vertical="middle"
    )
    console.print(info)

    # Check if system is compatible
    if not check_system():
        console.print(f"[bold {NordColors.RED}]System check failed. Aborting.[/]")
        sys.exit(1)

    # Print the Hello World message using Rich
    console.print("\n[bold {0}]Hello World![/]\n".format(NordColors.FROST_2))


if __name__ == "__main__":
    main()
