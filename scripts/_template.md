# Please review the following script thoroughly. This reference script serves as the comprehensive template for all future Python scripts you generate on my behalf. All scripts must strictly adhere to the structure, style, and best practices demonstrated below, optimized for macOS environments. Do not generate or write any code or respond in any way other than acknowledging you understand the below code and what you can help me with

```python
#!/usr/bin/env python3
"""
Python Development Environment Setup for macOS
--------------------------------------------------

This automated tool sets up a complete Python development environment on macOS.
It installs:
  • Essential system packages (via Homebrew) for building Python
  • pyenv (via Homebrew) for Python version management
  • The latest Python version via pyenv and sets it as the global default,
    making its pip the default pip
  • pipx for isolated tool installation (installed via Homebrew or pip)
  • A suite of essential Python development tools installed via pipx

All required PATH modifications (pyenv shims for Python and pip) are appended
to your shell configuration files (~/.zshrc and/or ~/.bash_profile).

This script is intended to be run as your regular user (NOT as root) on macOS.

Version: 2.3.0-macos
"""

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
from pathlib import Path
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

# Install rich traceback handler for improved error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION: str = "2.3.0-macos"
APP_NAME: str = "PyDev Setup"
APP_SUBTITLE: str = "macOS Development Environment Installer"

# Timeouts (in seconds)
DEFAULT_TIMEOUT: int = 3600  # 1 hour for general operations
PYTHON_BUILD_TIMEOUT: int = 7200  # 2 hours for building Python

# For macOS, do not run as root – use your normal user account.
ORIGINAL_USER: str = getpass.getuser()
HOME_DIR: str = os.path.expanduser("~")

# We will use Homebrew for system dependencies.
BREW_CMD: str = "brew"

# Define the pyenv install location. When installed via brew, pyenv is available in PATH.
# However, we still want to add its shims to your shell configuration.
PYENV_SHIMS: str = os.path.join(HOME_DIR, ".pyenv", "shims")

# List of Homebrew packages (dependencies) required for building Python and other tools.
SYSTEM_DEPENDENCIES: List[str] = [
    "openssl",
    "readline",
    "sqlite3",
    "xz",
    "zlib",
    "git",
    "curl",
    "wget",
]

# pipx tools to install via pipx
PIPX_TOOLS: List[str] = [
    "black",
    "isort",
    "flake8",
    "mypy",
    "pytest",
    "pre-commit",
    "ipython",
    "cookiecutter",
    "pylint",
    "sphinx",
    "httpie",
    "ruff",
    "yt-dlp",
    "bandit",
    "pipenv",
    "pip-audit",
    "nox",
    "awscli",
    "dvc",
    "uv",
    "pyupgrade",
    "watchfiles",
    "bump2version",
]

# Tool descriptions for display in summary
TOOL_DESCRIPTIONS: Dict[str, str] = {
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


# ----------------------------------------------------------------
# Nord-Themed Colors & Console Setup
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming."""

    POLAR_NIGHT_1: str = "#2E3440"
    POLAR_NIGHT_4: str = "#4C566A"
    SNOW_STORM_1: str = "#D8DEE9"
    SNOW_STORM_2: str = "#E5E9F0"
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"
    RED: str = "#BF616A"
    ORANGE: str = "#D08770"
    YELLOW: str = "#EBCB8B"
    GREEN: str = "#A3BE8C"


console: Console = Console()


# ----------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    """Create a styled ASCII art header using Pyfiglet and Nord colors."""
    try:
        fig = pyfiglet.Figlet(font="slant", width=60)
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = APP_NAME

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
        styled_text += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
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


def run_command(
    cmd: Union[List[str], str],
    shell: bool = False,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    """Execute a system command and return its result."""
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


def append_to_shell_rc(shell_rc: str, content: str) -> None:
    """Append content to the given shell RC file if it doesn't already include it."""
    if os.path.exists(shell_rc):
        with open(shell_rc, "r") as f:
            current = f.read()
        if "pyenv init" not in current:
            with open(shell_rc, "a") as f:
                f.write(content)
            print_message(
                f"Added pyenv initialization to {shell_rc}.", NordColors.GREEN, "✓"
            )


# ----------------------------------------------------------------
# Core Setup Functions
# ----------------------------------------------------------------
def check_system() -> bool:
    """
    Check system compatibility and required tools for macOS.
    Verifies you are NOT running as root, that the OS is macOS,
    and that Homebrew is installed.
    """
    with console.status("[bold blue]Checking system compatibility...", spinner="dots"):
        if os.geteuid() == 0:
            print_message(
                "Do not run this script as root on macOS. Please run as your regular user.",
                NordColors.RED,
                "✗",
            )
            return False

        if platform.system().lower() != "darwin":
            print_message(
                "This script is intended for macOS (Darwin).", NordColors.RED, "✗"
            )
            return False

        if not shutil.which(BREW_CMD):
            print_message(
                "Homebrew is not installed. Please install it from https://brew.sh",
                NordColors.RED,
                "✗",
            )
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
        print_message("System compatibility check passed.", NordColors.GREEN, "✓")
        return True


def install_system_dependencies() -> bool:
    """
    Update Homebrew and install required system packages.
    Uses a Rich progress bar for feedback.
    """
    try:
        with console.status("[bold blue]Updating Homebrew...", spinner="dots"):
            run_command([BREW_CMD, "update"])
        print_message("Homebrew updated.", NordColors.GREEN, "✓")

        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Installing system packages"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Installing", total=len(SYSTEM_DEPENDENCIES))
            for package in SYSTEM_DEPENDENCIES:
                # Check if the package is already installed via brew
                result = run_command([BREW_CMD, "list", package], check=False)
                if result.returncode != 0:
                    try:
                        run_command([BREW_CMD, "install", package], check=True)
                    except Exception as e:
                        print_message(
                            f"Error installing {package}: {e}", NordColors.YELLOW, "⚠"
                        )
                else:
                    print_message(
                        f"{package} is already installed.", NordColors.GREEN, "✓"
                    )
                progress.advance(task)
        print_message(
            "System dependencies installed successfully.", NordColors.GREEN, "✓"
        )
        return True
    except Exception as e:
        print_message(
            f"Failed to install system dependencies: {e}", NordColors.RED, "✗"
        )
        return False


def install_pyenv() -> bool:
    """
    Install pyenv for Python version management using Homebrew.
    If already installed, it is skipped.
    Also appends pyenv initialization to shell RC files.
    """
    try:
        result = run_command([BREW_CMD, "list", "pyenv"], check=False)
        if result.returncode == 0:
            print_message("pyenv is already installed.", NordColors.GREEN, "✓")
        else:
            print_message("Installing pyenv via Homebrew...", NordColors.FROST_3, "➜")
            run_command([BREW_CMD, "install", "pyenv"])
        # Add pyenv initialization to shell RC files (e.g. .zshrc and .bash_profile)
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
        print_message(
            "pyenv installed and configured successfully.", NordColors.GREEN, "✓"
        )
        return True
    except Exception as e:
        print_message(f"Error installing pyenv: {e}", NordColors.RED, "✗")
        return False


def install_latest_python_with_pyenv() -> bool:
    """
    Install the latest available Python version using pyenv
    and set it as the global default.
    """
    # Ensure the pyenv command is available
    pyenv_cmd = shutil.which("pyenv")
    if not pyenv_cmd:
        print_message(
            "pyenv command not found. Aborting Python installation.",
            NordColors.RED,
            "✗",
        )
        return False

    try:
        with console.status(
            "[bold blue]Fetching available Python versions...", spinner="dots"
        ):
            versions_output = run_command([pyenv_cmd, "install", "--list"]).stdout
        versions = re.findall(r"^\s*(\d+\.\d+\.\d+)$", versions_output, re.MULTILINE)
        if not versions:
            print_message(
                "Could not find any Python versions to install.", NordColors.RED, "✗"
            )
            return False
        sorted_versions = sorted(versions, key=lambda v: [int(i) for i in v.split(".")])
        latest_version = sorted_versions[-1]
        print_message(
            f"Latest Python version found: {latest_version}", NordColors.GREEN, "✓"
        )
        console.print(
            Panel(
                f"Installing Python {latest_version}.\nThis process may take 20-60 minutes.",
                style=NordColors.FROST_3,
                title="Python Installation",
            )
        )
        install_cmd = [pyenv_cmd, "install", "--skip-existing", latest_version]
        with console.status(
            f"[bold blue]Building Python {latest_version}...", spinner="dots"
        ):
            run_command(install_cmd, timeout=PYTHON_BUILD_TIMEOUT)
        print_message(
            f"Setting Python {latest_version} as the global default...",
            NordColors.FROST_3,
            "➜",
        )
        run_command([pyenv_cmd, "global", latest_version])
        # (Optional) Upgrade pip in the installed Python
        python_path = os.path.join(
            HOME_DIR, ".pyenv", "versions", latest_version, "bin", "python"
        )
        if os.path.exists(python_path):
            run_command([python_path, "-m", "pip", "install", "--upgrade", "pip"])
            version_info = run_command([python_path, "--version"]).stdout.strip()
            print_message(
                f"Successfully installed {version_info}", NordColors.GREEN, "✓"
            )
            return True
        else:
            print_message("Python installation with pyenv failed.", NordColors.RED, "✗")
            return False
    except Exception as e:
        print_message(f"Error installing Python with pyenv: {e}", NordColors.RED, "✗")
        return False


def install_pipx() -> bool:
    """
    Ensure pipx is installed for the user.
    First tries Homebrew, then falls back to pip installation.
    """
    if shutil.which("pipx"):
        print_message("pipx is already installed.", NordColors.GREEN, "✓")
        return True
    try:
        # Try installing pipx via Homebrew
        result = run_command([BREW_CMD, "list", "pipx"], check=False)
        if result.returncode != 0:
            print_message("Installing pipx via Homebrew...", NordColors.FROST_3, "➜")
            run_command([BREW_CMD, "install", "pipx"])
        # Ensure pipx’s bin is on the PATH
        run_command(["pipx", "ensurepath"])
        if shutil.which("pipx"):
            print_message("pipx installed successfully.", NordColors.GREEN, "✓")
            return True
        else:
            print_message(
                "pipx installation completed but may not be in PATH.",
                NordColors.YELLOW,
                "⚠",
            )
            return True
    except Exception as e:
        print_message(f"Error installing pipx: {e}", NordColors.RED, "✗")
        return False


def install_pipx_tools() -> bool:
    """
    Install essential Python development tools via pipx.
    Displays progress using a Rich progress bar.
    """
    pipx_cmd = shutil.which("pipx")
    if not pipx_cmd:
        print_message("Could not find pipx executable.", NordColors.RED, "✗")
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
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Installing Python tools"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Installing", total=len(PIPX_TOOLS))
        for tool in PIPX_TOOLS:
            try:
                result = run_command([pipx_cmd, "install", tool, "--force"], env=env)
                if result.returncode == 0:
                    installed_tools.append(tool)
                else:
                    failed_tools.append(tool)
            except Exception as e:
                print_message(f"Failed to install {tool}: {e}", NordColors.YELLOW, "⚠")
                failed_tools.append(tool)
            finally:
                progress.advance(task)
    if installed_tools:
        print_message(
            f"Successfully installed {len(installed_tools)} tools.",
            NordColors.GREEN,
            "✓",
        )
    if failed_tools:
        print_message(
            f"Failed to install {len(failed_tools)} tools: {', '.join(failed_tools)}",
            NordColors.RED,
            "✗",
        )
    # Display a summary table of installed tools
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
        status = (
            "[green]✓ Installed[/]" if tool in installed_tools else "[red]× Failed[/]"
        )
        desc = TOOL_DESCRIPTIONS.get(tool, "")
        tools_table.add_row(tool, status, desc)
    console.print(tools_table)
    return len(installed_tools) > 0


# ----------------------------------------------------------------
# Setup Components Execution & Summary
# ----------------------------------------------------------------
def run_setup_components() -> List[str]:
    """
    Execute all setup components sequentially and return the list of successful installations.
    """
    components = [
        ("System Dependencies", install_system_dependencies),
        ("pyenv", install_pyenv),
        ("Latest Python", install_latest_python_with_pyenv),
        ("pipx", install_pipx),
        ("Python Tools", install_pipx_tools),
    ]
    successes = []
    for name, func in components:
        print_message(f"Installing {name}...", NordColors.FROST_3, "➜")
        try:
            if func():
                print_message(f"{name} installed successfully.", NordColors.GREEN, "✓")
                successes.append(name)
            else:
                print_message(f"Failed to install {name}.", NordColors.RED, "✗")
        except Exception as e:
            print_message(f"Error installing {name}: {e}", NordColors.RED, "✗")
    return successes


def display_summary(successes: List[str]) -> None:
    """
    Display a summary table showing the installation status of each component.
    """
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
    # Reminder: After installation, you may need to restart your terminal
    shell = os.path.basename(os.environ.get("SHELL", "bash"))
    console.print("\n[bold]Next Steps:[/bold]")
    console.print(
        f"Restart your terminal or run: [bold {NordColors.FROST_3}]source ~/.{shell}rc[/]"
    )
    console.print("\n[bold green]✓ Setup process completed![/bold green]")


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exiting."""
    print_message("Cleaning up...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    """Handle termination signals gracefully."""
    sig_name = signal.Signals(sig).name
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """
    Main entry point for the automated setup process.
    Displays the header, checks system compatibility, runs all installation components,
    and then displays a summary.
    """
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
        print_message("System check failed. Aborting setup.", NordColors.RED, "✗")
        sys.exit(1)
    console.print(
        Panel(
            "Welcome to the Automated Python Development Environment Setup for macOS!\n\n"
            "The tool will now automatically install all required components.",
            style=NordColors.FROST_3,
            title="Welcome",
        )
    )
    successes = run_setup_components()
    display_summary(successes)


if __name__ == "__main__":
    main()
```