#!/usr/bin/env python3

import os
import sys
import time
import json
import signal
import shutil
import subprocess
import atexit
import urllib.parse
import platform
from dataclasses import dataclass, field
from typing import List, Optional, Any, Tuple, Dict, Union
from datetime import datetime

if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)


def install_dependencies():
    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "requests"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER"))
    try:
        if os.geteuid() != 0:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--user"] + required_packages
            )
        else:
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"]
                + required_packages
            )
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


def check_homebrew():
    if shutil.which("brew") is None:
        print(
            "Homebrew is not installed. Please install Homebrew from https://brew.sh and rerun this script."
        )
        sys.exit(1)


try:
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
        TransferSpeedColumn,
        MofNCompleteColumn,
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from rich.box import ROUNDED, HEAVY
    from rich.style import Style
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style as PTStyle
    import requests
except ImportError:
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)

install_rich_traceback(show_locals=True)
console = Console()

APP_NAME = "Metasploit Installer"
VERSION = "1.1.0"
DEFAULT_TIMEOUT = 300
INSTALLATION_TIMEOUT = 1200
CONFIG_DIR = os.path.expanduser("~/.msf_installer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")

INSTALLER_URL = "https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb"
INSTALLER_PATH = "/tmp/msfinstall"

SYSTEM_DEPENDENCIES = [
    "postgresql",
    "curl",
    "git",
    "nmap",
]


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

    @classmethod
    def get_polar_gradient(cls, steps=4):
        return [
            cls.POLAR_NIGHT_1,
            cls.POLAR_NIGHT_2,
            cls.POLAR_NIGHT_3,
            cls.POLAR_NIGHT_4,
        ][:steps]

    @classmethod
    def get_progress_columns(cls):
        return [
            SpinnerColumn(spinner_name="dots", style=f"bold {cls.FROST_1}"),
            TextColumn(f"[bold {cls.FROST_2}]{{task.description}}[/]"),
            BarColumn(
                bar_width=None,
                style=cls.POLAR_NIGHT_3,
                complete_style=cls.FROST_2,
                finished_style=cls.GREEN,
            ),
            TaskProgressColumn(style=cls.SNOW_STORM_1),
            TimeRemainingColumn(compact=True),
        ]


@dataclass
class AppConfig:
    last_install_date: str = ""
    system_info: Dict[str, str] = field(default_factory=dict)
    msf_path: str = ""

    def save(self):
        ensure_config_directory()
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.__dict__, f, indent=2)
        except Exception as e:
            print_error(f"Failed to save configuration: {e}")

    @classmethod
    def load(cls):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                return cls(**data)
        except Exception as e:
            print_error(f"Failed to load configuration: {e}")
        return cls()


def clear_screen():
    console.clear()


def create_header():
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)

    fonts = ["slant", "small_slant", "standard", "big", "digital", "small"]
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
    frost_colors = NordColors.get_frost_gradient(min(len(ascii_lines), 4))

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = frost_colors[i % len(frost_colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"

    border_style = NordColors.FROST_3
    border_char = "═"
    border_line = f"[{border_style}]{border_char * (adjusted_width - 8)}[/]"

    styled_text = border_line + "\n" + styled_text + border_line

    panel = Panel(
        Text.from_markup(styled_text),
        border_style=NordColors.FROST_1,
        box=NordColors.NORD_BOX,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_3}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]macOS Metasploit Framework Installer[/]",
        subtitle_align="center",
    )

    return panel


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


def print_step(message):
    print_message(message, NordColors.INFO, "→")


def print_info(message):
    print_message(message, NordColors.INFO, "ℹ")


def display_panel(title, message, style=NordColors.INFO):
    if isinstance(style, str):
        panel = Panel(
            Text.from_markup(message),
            title=title,
            border_style=style,
            box=NordColors.NORD_BOX,
            padding=(1, 2),
        )
    else:
        panel = Panel(
            Text(message),
            title=title,
            border_style=style,
            box=NordColors.NORD_BOX,
            padding=(1, 2),
        )
    console.print(panel)


def create_menu_table(title, options):
    table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        title=title,
        border_style=NordColors.FROST_3,
        padding=(0, 1),
        expand=True,
    )

    table.add_column("#", style=NordColors.ACCENT, width=3, justify="right")
    table.add_column("Option", style=NordColors.FROST_1)
    table.add_column("Description", style=NordColors.SNOW_STORM_1)

    for opt in options:
        table.add_row(*opt)

    return table


def ensure_config_directory():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


def run_command(
    cmd, check=True, timeout=DEFAULT_TIMEOUT, verbose=False, env=None, shell=False
):
    try:
        if verbose:
            print_step(f"Executing: {' '.join(cmd)}")

        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Running command..."),
            console=console,
        ) as progress:
            task = progress.add_task("", total=None)
            result = subprocess.run(
                cmd,
                check=check,
                text=True,
                capture_output=True,
                timeout=timeout,
                env=env or os.environ.copy(),
                shell=shell,
            )

        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if verbose and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


def check_command_available(command):
    return shutil.which(command) is not None


def cleanup():
    print_message("Cleaning up temporary files...", NordColors.FROST_3)
    if os.path.exists(INSTALLER_PATH):
        try:
            os.remove(INSTALLER_PATH)
            print_success(f"Removed temporary installer at {INSTALLER_PATH}")
        except Exception as e:
            print_warning(f"Failed to remove temporary installer: {e}")

    config = AppConfig.load()
    config.save()


def signal_handler(sig, frame):
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


def check_system():
    print_step("Checking system compatibility...")

    if not check_command_available("brew"):
        print_error(
            "Homebrew is not installed. Please install Homebrew from https://brew.sh/ and rerun the script."
        )
        return False

    table = Table(
        show_header=False, box=ROUNDED, border_style=NordColors.FROST_3, padding=(0, 2)
    )

    table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)
    table.add_row("Python Version", platform.python_version())
    table.add_row("OS", platform.platform())
    table.add_row("Architecture", platform.machine())

    console.print(
        Panel(
            table,
            title="[bold]System Information[/bold]",
            border_style=NordColors.FROST_1,
            padding=(1, 2),
            box=ROUNDED,
        )
    )

    required_tools = ["curl", "git"]
    missing_tools = [
        tool for tool in required_tools if not check_command_available(tool)
    ]

    if missing_tools:
        print_error(f"Missing required tools: {', '.join(missing_tools)}")
        print_step("Installing missing tools via Homebrew...")
        try:
            run_command(["brew", "update"])
            run_command(["brew", "install"] + missing_tools)
            print_success("Required tools installed.")
        except Exception as e:
            print_error(f"Failed to install required tools: {e}")
            return False
    else:
        print_success("All required tools are available.")

    return True


def install_system_dependencies():
    print_step("Installing system dependencies via Homebrew...")

    try:
        run_command(["brew", "update"])

        with Progress(*NordColors.get_progress_columns(), console=console) as progress:
            task = progress.add_task(
                "Installing dependencies", total=len(SYSTEM_DEPENDENCIES)
            )

            for pkg in SYSTEM_DEPENDENCIES:
                try:
                    progress.update(task, description=f"Installing {pkg}")
                    run_command(["brew", "install", pkg], check=False)
                    progress.advance(task)
                except Exception as e:
                    print_warning(f"Failed to install {pkg}: {e}")
                    progress.advance(task)

        print_success("System dependencies installed.")
        return True

    except Exception as e:
        print_error(f"Failed to install system dependencies: {e}")
        return False


def download_metasploit_installer():
    print_step("Downloading Metasploit installer...")

    try:
        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Downloading installer..."),
            console=console,
        ) as progress:
            task = progress.add_task("", total=None)
            run_command(["curl", "-sSL", INSTALLER_URL, "-o", INSTALLER_PATH])

        if os.path.exists(INSTALLER_PATH):
            os.chmod(INSTALLER_PATH, 0o755)
            print_success("Installer downloaded and made executable.")
            return True
        else:
            print_error("Failed to download installer.")
            return False

    except Exception as e:
        print_error(f"Error downloading installer: {e}")
        return False


def run_metasploit_installer():
    print_step("Running Metasploit installer...")

    display_panel(
        "Installation",
        "Installing Metasploit Framework. This may take several minutes.\n"
        "The installer will download and set up all required components.",
        NordColors.FROST_3,
    )

    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Installing Metasploit"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Installing", total=None)
            env = os.environ.copy()
            env["DEBIAN_FRONTEND"] = "noninteractive"
            run_command([INSTALLER_PATH], timeout=INSTALLATION_TIMEOUT, env=env)
            progress.update(task, completed=100)

        print_success("Metasploit Framework installed successfully.")
        return True

    except Exception as e:
        print_error(f"Error during Metasploit installation: {e}")
        return False


def configure_postgresql():
    print_step("Configuring PostgreSQL...")

    try:
        pg_status = run_command(["brew", "services", "list"], check=False)

        if "postgresql" not in pg_status.stdout or "started" not in pg_status.stdout:
            print_step("Starting PostgreSQL via Homebrew services...")
            run_command(["brew", "services", "start", "postgresql"])

        print_success("PostgreSQL is running.")

        print_step("Setting up Metasploit database user...")
        user_check = run_command(
            ["psql", "-tAc", "SELECT 1 FROM pg_roles WHERE rolname='msf'"], check=False
        )

        if "1" not in user_check.stdout:
            run_command(
                ["psql", "-c", "CREATE USER msf WITH PASSWORD 'msf'"], check=False
            )
            print_success("Created Metasploit database user.")
        else:
            print_success("Metasploit database user already exists.")

        db_check = run_command(
            ["psql", "-tAc", "SELECT 1 FROM pg_database WHERE datname='msf'"],
            check=False,
        )

        if "1" not in db_check.stdout:
            run_command(["psql", "-c", "CREATE DATABASE msf OWNER msf"], check=False)
            print_success("Created Metasploit database.")

        pg_hba = "/usr/local/var/postgres/pg_hba.conf"

        if os.path.exists(pg_hba):
            backup = f"{pg_hba}.backup"

            if not os.path.exists(backup):
                shutil.copy2(pg_hba, backup)
                print_success(f"Created backup of {pg_hba}")

            with open(pg_hba, "r") as f:
                content = f.read()

            if "local   msf         msf" not in content:
                with open(pg_hba, "a") as f:
                    f.write("\n# Added by Metasploit installer\n")
                    f.write(
                        "local   msf         msf                                     md5\n"
                    )

                print_success(f"Updated {pg_hba}")
                run_command(["brew", "services", "restart", "postgresql"], check=False)

        return True

    except Exception as e:
        print_warning(f"PostgreSQL configuration error: {e}")
        return False


def check_installation():
    print_step("Verifying installation...")

    possible_paths = [
        "/opt/metasploit-framework/bin/msfconsole",
        "/usr/local/bin/msfconsole",
        "/usr/bin/msfconsole",
    ]

    msfconsole_path = None

    for path in possible_paths:
        if os.path.exists(path):
            msfconsole_path = path
            break

    if not msfconsole_path and check_command_available("msfconsole"):
        msfconsole_path = "msfconsole"

    if not msfconsole_path:
        print_error("msfconsole not found. Installation might have failed.")
        return None

    try:
        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Checking Metasploit version..."),
            console=console,
        ) as progress:
            task = progress.add_task("", total=None)
            version_result = run_command([msfconsole_path, "-v"], timeout=30)

        if (
            version_result.returncode == 0
            and "metasploit" in version_result.stdout.lower()
        ):
            version_info = next(
                (
                    line
                    for line in version_result.stdout.strip().splitlines()
                    if "Framework" in line
                ),
                "",
            )

            print_success("Metasploit Framework installed successfully!")
            console.print(f"[{NordColors.FROST_1}]{version_info}[/]")
            console.print(f"[{NordColors.FROST_2}]Location: {msfconsole_path}[/]")

            config = AppConfig.load()
            config.msf_path = msfconsole_path
            config.last_install_date = datetime.now().isoformat()
            config.system_info = {
                "python_version": platform.python_version(),
                "os_version": platform.platform(),
                "architecture": platform.machine(),
            }
            config.save()

            return msfconsole_path
        else:
            print_error("Metasploit verification failed.")
            return None

    except Exception as e:
        print_error(f"Error verifying installation: {e}")
        return None


def initialize_database(msfconsole_path):
    print_step("Initializing Metasploit database...")

    msfdb_path = os.path.join(os.path.dirname(msfconsole_path), "msfdb")

    if not os.path.exists(msfdb_path) and not check_command_available("msfdb"):
        print_warning(
            "msfdb utility not found. Attempting alternative initialization via msfconsole."
        )

        try:
            resource_path = "/tmp/msf_init.rc"

            with open(resource_path, "w") as f:
                f.write("db_status\nexit\n")

            with Progress(
                SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]Initializing database..."),
                console=console,
            ) as progress:
                task = progress.add_task("", total=None)
                run_command(
                    [msfconsole_path, "-q", "-r", resource_path],
                    check=False,
                    timeout=60,
                )

            if os.path.exists(resource_path):
                os.remove(resource_path)

            print_success("Database initialized via msfconsole.")
            return True

        except Exception as e:
            print_warning(f"Database initialization via msfconsole failed: {e}")
            return False

    try:
        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(
                f"[bold {NordColors.FROST_2}]Initializing database with msfdb..."
            ),
            console=console,
        ) as progress:
            task = progress.add_task("", total=None)
            env = os.environ.copy()
            env["DEBIAN_FRONTEND"] = "noninteractive"
            result = run_command(
                [msfdb_path if os.path.exists(msfdb_path) else "msfdb", "init"],
                check=False,
                env=env,
            )

        if result.returncode == 0:
            print_success("Metasploit database initialized successfully.")
            return True
        else:
            print_warning("Database initialization encountered issues.")
            return False

    except Exception as e:
        print_warning(f"Error initializing database: {e}")
        return False


def create_startup_script(msfconsole_path):
    print_step("Creating startup script...")

    script_path = "/usr/local/bin/msf-start"

    try:
        script_content = f"""#!/bin/bash
echo "Checking Metasploit database status..."
if command -v msfdb &> /dev/null; then
    msfdb status || msfdb init
else
    echo "msfdb not found, starting msfconsole directly"
fi

echo "Starting Metasploit Framework..."
{msfconsole_path} "$@"
"""
        with open(script_path, "w") as f:
            f.write(script_content)

        os.chmod(script_path, 0o755)
        print_success(f"Startup script created at {script_path}")
        return True

    except Exception as e:
        print_warning(f"Failed to create startup script: {e}")
        return False


def display_completion_info(msfconsole_path):
    completion_message = f"""
Installation completed successfully!

[bold {NordColors.FROST_2}]Metasploit Framework:[/]
• Command: {msfconsole_path}
• Launch with: msf-start or {msfconsole_path}
• Database: Run 'db_status' in msfconsole; initialize with 'msfdb init' if needed

[bold {NordColors.FROST_2}]Documentation:[/]
• https://docs.metasploit.com/
"""
    display_panel("Installation Complete", completion_message, NordColors.GREEN)


def run_full_setup():
    clear_screen()
    console.print(create_header())
    console.print()

    display_panel(
        "Automated Setup Process",
        "Automated Metasploit installation in progress.\n\n"
        "Steps:\n"
        "1. System check\n"
        "2. Install system dependencies\n"
        "3. Download installer\n"
        "4. Run installer\n"
        "5. Configure PostgreSQL\n"
        "6. Verify installation\n"
        "7. Initialize database\n"
        "8. Create startup script",
        NordColors.FROST_2,
    )
    console.print()

    if not check_system():
        print_error("System check failed. Exiting.")
        sys.exit(1)

    if not install_system_dependencies():
        print_warning("Some dependencies failed to install. Continuing anyway...")

    if not download_metasploit_installer():
        print_error("Failed to download installer. Exiting.")
        sys.exit(1)

    if not run_metasploit_installer():
        print_error("Metasploit installation failed. Exiting.")
        sys.exit(1)

    configure_postgresql()

    msfconsole_path = check_installation()
    if not msfconsole_path:
        print_error("Metasploit verification failed. Exiting.")
        sys.exit(1)

    initialize_database(msfconsole_path)
    create_startup_script(msfconsole_path)
    display_completion_info(msfconsole_path)


def main():
    try:
        if os.geteuid() != 0:
            clear_screen()
            console.print(create_header())
            console.print()
            print_error("Script must be run with root privileges.")
            sys.exit(1)

        run_full_setup()

    except KeyboardInterrupt:
        console.print()
        print_warning("Process interrupted by user.")
        sys.exit(130)

    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
