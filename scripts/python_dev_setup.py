#!/usr/bin/env python3

import atexit
import getpass
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pyfiglet
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich.traceback import install as install_rich_traceback

install_rich_traceback(show_locals=True)

VERSION = "2.3.1-macos"
APP_NAME = "PyDev Setup"
APP_SUBTITLE = "macOS Development Environment"
DEFAULT_TIMEOUT = 3600
PYTHON_BUILD_TIMEOUT = 7200
ORIGINAL_USER = getpass.getuser()
HOME_DIR = os.path.expanduser("~")
BREW_CMD = "brew"
PYENV_SHIMS = os.path.join(HOME_DIR, ".pyenv", "shims")

SYSTEM_DEPENDENCIES = [
    "openssl", "readline", "sqlite3", "xz", "zlib", "git", "curl", "wget"
]

PIPX_TOOLS = [
    "black", "isort", "flake8", "mypy", "pytest", "pre-commit", "ipython",
    "cookiecutter", "pylint", "sphinx", "httpie", "ruff", "yt-dlp", "bandit",
    "pipenv", "pip-audit", "nox", "awscli", "dvc", "uv", "pyupgrade",
    "watchfiles", "bump2version"
]

TOOL_DESCRIPTIONS = {
    "black": "Code formatter that adheres to PEP 8",
    "isort": "Import statement organizer",
    "flake8": "Style guide enforcement tool",
    "mypy": "Static type checker",
    "pytest": "Testing framework",
    "pre-commit": "Git hook manager",
    "ipython": "Enhanced interactive Python shell",
    "cookiecutter": "Project template renderer",
    "pylint": "Code analysis tool",
    "sphinx": "Documentation generator",
    "httpie": "Command-line HTTP client",
    "ruff": "Fast Python linter",
    "yt-dlp": "Advanced video downloader",
    "bandit": "Security linter",
    "pipenv": "Virtual environment & dependency management",
    "pip-audit": "Scans for vulnerable dependencies",
    "nox": "Automation tool for testing",
    "awscli": "Official AWS CLI",
    "dvc": "Data version control for ML projects",
    "uv": "Unified package manager (Rust-based)",
    "pyupgrade": "Upgrades Python syntax",
    "watchfiles": "File change monitor",
    "bump2version": "Automates version bumping",
}


class NordColors:
    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"

    @classmethod
    def get_frost_gradient(cls, steps=4):
        return [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4][:steps]

    @classmethod
    def get_progress_columns(cls):
        return [
            SpinnerColumn(spinner_name="dots", style=f"bold {cls.FROST_1}"),
            TextColumn(f"[bold {cls.FROST_2}]{{task.description}}[/]"),
            BarColumn(bar_width=40, style=cls.FROST_4, complete_style=cls.FROST_2),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
        ]


console = Console()


def create_header():
    try:
        fig = pyfiglet.Figlet(font="slant", width=60)
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = APP_NAME

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient()
    styled_text = ""

    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
    styled_text = border + "\n" + styled_text + border

    return Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(text, style=NordColors.FROST_2, prefix="•"):
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message):
    print_message(message, NordColors.RED, "✗")


def print_success(message):
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message):
    print_message(message, NordColors.YELLOW, "⚠")


def print_step(message):
    print_message(message, NordColors.FROST_3, "➜")


def run_command(
        cmd,
        shell=False,
        check=True,
        capture_output=True,
        timeout=DEFAULT_TIMEOUT,
        env=None
):
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    print_message(
        f"Running: {cmd_str[:80]}{'...' if len(cmd_str) > 80 else ''}",
        NordColors.SNOW_STORM_1,
        "→",
    )
    result = subprocess.run(
        cmd,
        shell=shell,
        check=check,
        text=True,
        capture_output=capture_output,
        timeout=timeout,
        env=env or os.environ.copy(),
    )
    return result


def append_to_shell_rc(shell_rc, content):
    if os.path.exists(shell_rc):
        with open(shell_rc, "r") as f:
            current = f.read()
        if "pyenv init" not in current:
            with open(shell_rc, "a") as f:
                f.write(content)
            print_success(f"Added pyenv initialization to {shell_rc}.")


def check_system():
    with console.status("[bold blue]Checking system compatibility...", spinner="dots"):
        if os.geteuid() == 0:
            print_error("Do not run this script as root on macOS. Please run as your regular user.")
            return False

        if platform.system().lower() != "darwin":
            print_error("This script is intended for macOS (Darwin).")
            return False

        if not shutil.which(BREW_CMD):
            print_error("Homebrew is not installed. Please install it from https://brew.sh")
            return False

        table = Table(
            show_header=False, box=None, border_style=NordColors.FROST_3, padding=(0, 2)
        )
        table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        table.add_column("Value", style=NordColors.SNOW_STORM_1)
        table.add_row("Python Version", platform.python_version())
        table.add_row("Operating System", platform.platform())
        table.add_row("Running as", ORIGINAL_USER)
        table.add_row("User Home Directory", HOME_DIR)

        console.print(
            Panel(
                table,
                title="[bold]System Information[/bold]",
                border_style=NordColors.FROST_1,
                padding=(1, 2),
            )
        )
        print_success("System compatibility check passed.")
        return True


def install_system_dependencies():
    try:
        with console.status("[bold blue]Updating Homebrew...", spinner="dots"):
            run_command([BREW_CMD, "update"])
        print_success("Homebrew updated.")

        with Progress(*NordColors.get_progress_columns(), console=console) as progress:
            task = progress.add_task("Installing", total=len(SYSTEM_DEPENDENCIES))
            for package in SYSTEM_DEPENDENCIES:
                result = run_command([BREW_CMD, "list", package], check=False)
                if result.returncode != 0:
                    try:
                        run_command([BREW_CMD, "install", package], check=True)
                    except Exception as e:
                        print_warning(f"Error installing {package}: {e}")
                else:
                    print_success(f"{package} is already installed.")
                progress.advance(task)

        print_success("System dependencies installed successfully.")
        return True
    except Exception as e:
        print_error(f"Failed to install system dependencies: {e}")
        return False


def install_pyenv():
    try:
        result = run_command([BREW_CMD, "list", "pyenv"], check=False)
        if result.returncode == 0:
            print_success("pyenv is already installed.")
        else:
            print_step("Installing pyenv via Homebrew...")
            run_command([BREW_CMD, "install", "pyenv"])

        pyenv_init = (
            "\n# pyenv initialization\n"
            'export PYENV_ROOT="$HOME/.pyenv"\n'
            'export PATH="$PYENV_ROOT/bin:$PATH"\n'
            "if command -v pyenv 1>/dev/null 2>&1; then\n"
            '  eval "$(pyenv init --path)"\n'
            '  eval "$(pyenv init -)"\n'
            "fi\n"
        )

        shell_rc_files = [
            os.path.join(HOME_DIR, ".zshrc"),
            os.path.join(HOME_DIR, ".bash_profile"),
        ]

        for rc in shell_rc_files:
            append_to_shell_rc(rc, pyenv_init)

        print_success("pyenv installed and configured successfully.")
        return True
    except Exception as e:
        print_error(f"Error installing pyenv: {e}")
        return False


def install_latest_python_with_pyenv():
    pyenv_cmd = shutil.which("pyenv")
    if not pyenv_cmd:
        print_error("pyenv command not found. Aborting Python installation.")
        return False

    try:
        with console.status("[bold blue]Fetching available Python versions...", spinner="dots"):
            versions_output = run_command([pyenv_cmd, "install", "--list"]).stdout

        versions = re.findall(r"^\s*(\d+\.\d+\.\d+)$", versions_output, re.MULTILINE)
        if not versions:
            print_error("Could not find any Python versions to install.")
            return False

        sorted_versions = sorted(versions, key=lambda v: [int(i) for i in v.split(".")])
        latest_version = sorted_versions[-1]
        print_success(f"Latest Python version found: {latest_version}")

        console.print(
            Panel(
                f"Installing Python {latest_version}.\nThis process may take 20-60 minutes.",
                style=NordColors.FROST_3,
                title="Python Installation",
            )
        )

        install_cmd = [pyenv_cmd, "install", "--skip-existing", latest_version]
        with console.status(f"[bold blue]Building Python {latest_version}...", spinner="dots"):
            run_command(install_cmd, timeout=PYTHON_BUILD_TIMEOUT)

        print_step(f"Setting Python {latest_version} as the global default...")
        run_command([pyenv_cmd, "global", latest_version])

        python_path = os.path.join(HOME_DIR, ".pyenv", "versions", latest_version, "bin", "python")
        if os.path.exists(python_path):
            run_command([python_path, "-m", "pip", "install", "--upgrade", "pip"])
            version_info = run_command([python_path, "--version"]).stdout.strip()
            print_success(f"Successfully installed {version_info}")
            return True
        else:
            print_error("Python installation with pyenv failed.")
            return False
    except Exception as e:
        print_error(f"Error installing Python with pyenv: {e}")
        return False


def install_pipx():
    if shutil.which("pipx"):
        print_success("pipx is already installed.")
        return True
    try:
        result = run_command([BREW_CMD, "list", "pipx"], check=False)
        if result.returncode != 0:
            print_step("Installing pipx via Homebrew...")
            run_command([BREW_CMD, "install", "pipx"])

        run_command(["pipx", "ensurepath"])
        if shutil.which("pipx"):
            print_success("pipx installed successfully.")
            return True
        else:
            print_warning("pipx installation completed but may not be in PATH.")
            return True
    except Exception as e:
        print_error(f"Error installing pipx: {e}")
        return False


def install_pipx_tools():
    pipx_cmd = shutil.which("pipx")
    if not pipx_cmd:
        print_error("Could not find pipx executable.")
        return False

    console.print(
        Panel(
            f"Automatically installing {len(PIPX_TOOLS)} Python development tools.",
            style=NordColors.FROST_3,
            title="Development Tools",
        )
    )

    env = os.environ.copy()
    installed_tools = []
    failed_tools = []

    with Progress(*NordColors.get_progress_columns(), console=console) as progress:
        task = progress.add_task("Installing", total=len(PIPX_TOOLS))
        for tool in PIPX_TOOLS:
            try:
                result = run_command([pipx_cmd, "install", tool, "--force"], env=env)
                if result.returncode == 0:
                    installed_tools.append(tool)
                else:
                    failed_tools.append(tool)
            except Exception as e:
                print_warning(f"Failed to install {tool}: {e}")
                failed_tools.append(tool)
            finally:
                progress.advance(task)

    if installed_tools:
        print_success(f"Successfully installed {len(installed_tools)} tools.")
    if failed_tools:
        print_warning(f"Failed to install {len(failed_tools)} tools: {', '.join(failed_tools)}")

    tools_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title=f"[bold {NordColors.FROST_2}]Installed Python Tools[/]",
        title_justify="center",
    )

    tools_table.add_column("Tool", style=f"bold {NordColors.FROST_2}")
    tools_table.add_column("Status", style=NordColors.SNOW_STORM_1)
    tools_table.add_column("Description", style=NordColors.SNOW_STORM_1)

    for tool in PIPX_TOOLS:
        status = "[green]✓ Installed[/]" if tool in installed_tools else "[red]× Failed[/]"
        desc = TOOL_DESCRIPTIONS.get(tool, "")
        tools_table.add_row(tool, status, desc)

    console.print(tools_table)
    return len(installed_tools) > 0


def run_setup_components():
    components = [
        ("System Dependencies", install_system_dependencies),
        ("pyenv", install_pyenv),
        ("Latest Python", install_latest_python_with_pyenv),
        ("pipx", install_pipx),
        ("Python Tools", install_pipx_tools),
    ]

    successes = []
    for name, func in components:
        print_step(f"Installing {name}...")
        try:
            if func():
                print_success(f"{name} installed successfully.")
                successes.append(name)
            else:
                print_error(f"Failed to install {name}.")
        except Exception as e:
            print_error(f"Error installing {name}: {e}")

    return successes


def display_summary(successes):
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title="[bold]Setup Summary[/]",
        title_style=f"bold {NordColors.FROST_2}",
        title_justify="center",
        expand=True,
    )

    table.add_column("Component", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", style=NordColors.SNOW_STORM_1)

    components = [
        "System Dependencies",
        "pyenv",
        "Latest Python",
        "pipx",
        "Python Tools",
    ]

    for comp in components:
        status = "[green]✓ Installed[/]" if comp in successes else "[red]× Failed[/]"
        table.add_row(comp, status)

    console.print("\n")
    console.print(Panel(table, border_style=NordColors.FROST_1, padding=(1, 2)))

    shell = os.path.basename(os.environ.get("SHELL", "bash"))
    console.print("\n[bold]Next Steps:[/bold]")
    console.print(f"Restart your terminal or run: [bold {NordColors.FROST_3}]source ~/.{shell}rc[/]")
    console.print("\n[bold green]✓ Setup process completed![/bold green]")


def cleanup():
    print_message("Cleaning up...", NordColors.FROST_3)


def signal_handler(sig, frame):
    sig_name = signal.Signals(sig).name
    print_warning(f"Process interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


def main():
    console.print("\n")
    console.print(create_header())

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hostname = platform.node()

    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | [{NordColors.SNOW_STORM_1}]Host: {hostname}[/]"
        )
    )

    console.print("\n")

    if not check_system():
        print_error("System check failed. Aborting setup.")
        sys.exit(1)

    console.print(
        Panel(
            "Setting up a complete Python development environment for macOS.",
            style=NordColors.FROST_3,
            title="Welcome",
        )
    )

    successes = run_setup_components()
    display_summary(successes)


if __name__ == "__main__":
    main()