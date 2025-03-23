#!/usr/bin/env python3

import atexit
import os
import platform
import shutil
import signal
import subprocess
import sys
from datetime import datetime


def install_dependencies():
    required_packages = ["pyfiglet", "rich", "prompt_toolkit"]
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--user", package]
                )
            except subprocess.CalledProcessError as e:
                print(f"Failed to install {package}: {e}")
                sys.exit(1)


install_dependencies()

import pyfiglet
from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.text import Text
from rich.traceback import install as install_rich_traceback

install_rich_traceback(show_locals=True)
console = Console()

APP_NAME = "Hello World App"
APP_VERSION = "1.0.0"


class NordColors:
    POLAR_NIGHT_1 = "#2E3440"
    SNOW_STORM_1 = "#D8DEE9"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    GREEN = "#A3BE8C"
    YELLOW = "#EBCB8B"


def check_system():
    if platform.system() != "Darwin":
        console.print(
            f"[bold {NordColors.RED}]This script is tailored for macOS. Exiting.[/]"
        )
        sys.exit(1)

    if os.geteuid() == 0:
        console.print(
            f"[bold {NordColors.RED}]Do not run this script as root. Please run as your normal user.[/]"
        )
        sys.exit(1)

    if shutil.which("brew") is None:
        console.print(
            f"[bold {NordColors.YELLOW}]Homebrew is not installed. Some features may not work.[/]"
        )

    user = os.environ.get("USER", "Unknown")
    home_dir = os.path.expanduser("~")
    sys_info = f"User: {user} | OS: {platform.platform()} | Home: {home_dir}"
    console.print(
        Panel(
            sys_info, title="[bold]System Information[/bold]", style=NordColors.FROST_2
        )
    )
    return True


def create_banner(text, font="slant"):
    try:
        fig = pyfiglet.Figlet(font=font)
        ascii_art = fig.renderText(text)
    except Exception:
        ascii_art = text

    styled_art = f"[bold {NordColors.FROST_1}]{ascii_art}[/]"
    panel = Panel(
        styled_art,
        border_style=NordColors.FROST_3,
        title=f"[bold]{APP_NAME}[/]",
        subtitle=f"v{APP_VERSION}",
        padding=(1, 2),
    )
    return panel


def cleanup():
    console.print(f"[bold {NordColors.FROST_2}]Cleaning up...[/]")


def signal_handler(sig, frame):
    try:
        sig_name = signal.Signals(sig).name
        console.print(
            f"[bold {NordColors.YELLOW}]Received signal {sig_name}. Exiting...[/]"
        )
    except Exception:
        console.print(
            f"[bold {NordColors.YELLOW}]Process interrupted by signal {sig}. Exiting...[/]"
        )
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


def main():
    console.print("\n")
    banner = create_banner("Hello World!")
    console.print(banner)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(
        f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/]", justify="center"
    )

    check_system()

    console.print(f"\n[bold {NordColors.FROST_2}]Hello World![/]\n")


if __name__ == "__main__":
    main()
