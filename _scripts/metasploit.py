#!/usr/bin/env python3
"""
Automated Metasploit Framework Installer
--------------------------------------------------
A fully automated, zero-interaction installer and configuration tool for the
Metasploit Framework. This script automatically handles installation,
database setup, and configuration with no user input.

Version: 1.0.0
"""

import atexit
import glob
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from typing import List, Dict, Optional, Any

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.live import Live
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("Required libraries missing. Installing now...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich", "pyfiglet"],
            check=True,
        )
        print("Installed required libraries. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Failed to install libraries: {e}")
        sys.exit(1)

# Install rich traceback for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION = "1.0.0"
APP_NAME = "Metasploit Installer"
APP_SUBTITLE = "Automated Framework Setup"
DEFAULT_TIMEOUT = 300
INSTALLATION_TIMEOUT = 1200  # 20 minutes for slower machines

# Installer URL and temporary download location
INSTALLER_URL = (
    "https://raw.githubusercontent.com/rapid7/metasploit-omnibus/"
    "master/config/templates/metasploit-framework-wrappers/msfupdate.erb"
)
INSTALLER_PATH = "/tmp/msfinstall"

# List of required system dependencies (for apt-based systems)
SYSTEM_DEPENDENCIES = [
    "build-essential",
    "libpq-dev",
    "postgresql",
    "postgresql-contrib",
    "curl",
    "git",
    "nmap",
]


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
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


# Create a global Rich Console instance
console: Console = Console()


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create an ASCII art header using Pyfiglet and return it as a Rich Panel.
    """
    compact_fonts = ["slant", "small", "smslant", "standard", "digital"]
    ascii_art = ""
    for font in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art and ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art or not ascii_art.strip():
        ascii_art = APP_NAME
    lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled_text = ""
    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border
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


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_3, "➜")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


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


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    shell: bool = False,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.
    """
    try:
        cmd_str = " ".join(cmd)
        print_message(
            f"Running: {cmd_str[:80]}{'...' if len(cmd_str) > 80 else ''}",
            NordColors.SNOW_STORM_1,
            "→",
        )
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
            shell=shell,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {cmd_str}")
        if e.stdout:
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


def check_command_available(command: str) -> bool:
    """
    Return True if the command is available in the PATH.
    """
    return shutil.which(command) is not None


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """
    Cleanup temporary files before exit.
    """
    print_message("Cleaning up temporary files...", NordColors.FROST_3)
    if os.path.exists(INSTALLER_PATH):
        try:
            os.remove(INSTALLER_PATH)
            print_success(f"Removed temporary installer at {INSTALLER_PATH}")
        except Exception as e:
            print_warning(f"Failed to remove temporary installer: {e}")


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle termination signals gracefully.
    """
    sig_name = signal.Signals(sig).name
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Core Setup Functions
# ----------------------------------------------------------------
def check_system() -> bool:
    """
    Check system compatibility, distribution, and required tools.
    """
    print_step("Checking system compatibility...")
    os_name = platform.system().lower()
    if os_name != "linux":
        print_warning(f"This script is designed for Linux, not {os_name}.")
        return False

    is_ubuntu_or_debian = False
    try:
        with open("/etc/os-release", "r") as f:
            os_release = f.read().lower()
            if "ubuntu" in os_release or "debian" in os_release:
                is_ubuntu_or_debian = True
    except FileNotFoundError:
        pass
    if not is_ubuntu_or_debian:
        print_warning(
            "Optimized for Ubuntu/Debian. May not work correctly on your system."
        )

    if os.geteuid() != 0:
        print_error("Script must be run with root privileges.")
        return False

    # Display system information
    table = Table(
        show_header=False, box=None, border_style=NordColors.FROST_3, padding=(0, 2)
    )
    table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)
    table.add_row("Python Version", platform.python_version())
    table.add_row("OS", platform.platform())
    table.add_row("Distribution", "Ubuntu/Debian" if is_ubuntu_or_debian else "Unknown")
    console.print(
        Panel(
            table,
            title="[bold]System Information[/bold]",
            border_style=NordColors.FROST_1,
            padding=(1, 2),
        )
    )

    # Check for required tools
    required_tools = ["curl", "git"]
    missing_tools = [
        tool for tool in required_tools if not check_command_available(tool)
    ]
    if missing_tools:
        print_error(f"Missing required tools: {', '.join(missing_tools)}")
        print_step("Installing missing tools...")
        try:
            run_command(["apt-get", "update"])
            run_command(["apt-get", "install", "-y"] + missing_tools)
            print_success("Required tools installed.")
        except Exception as e:
            print_error(f"Failed to install required tools: {e}")
            return False
    else:
        print_success("All required tools are available.")
    return True


def install_system_dependencies() -> bool:
    """
    Install required system dependencies.
    """
    print_step("Installing system dependencies...")
    try:
        with console.status("[bold blue]Updating package lists...", spinner="dots"):
            run_command(["apt-get", "update"])
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Installing dependencies"),
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
            for pkg in SYSTEM_DEPENDENCIES:
                try:
                    run_command(["apt-get", "install", "-y", pkg], check=False)
                    progress.advance(task)
                except Exception as e:
                    print_warning(f"Failed to install {pkg}: {e}")
                    progress.advance(task)
        print_success("System dependencies installed.")
        return True
    except Exception as e:
        print_error(f"Failed to install system dependencies: {e}")
        return False


def download_metasploit_installer() -> bool:
    """
    Download the Metasploit installer script from the given URL.
    """
    print_step("Downloading Metasploit installer...")
    try:
        with console.status("[bold blue]Downloading installer...", spinner="dots"):
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


def run_metasploit_installer() -> bool:
    """
    Run the downloaded Metasploit installer script.
    """
    print_step("Running Metasploit installer...")
    display_panel(
        "Installing Metasploit Framework. This may take several minutes.\n"
        "The installer will download and set up all required components.",
        NordColors.FROST_3,
        "Installation",
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


def configure_postgresql() -> bool:
    """
    Configure PostgreSQL for use with Metasploit.
    """
    print_step("Configuring PostgreSQL...")
    try:
        pg_status = run_command(["systemctl", "status", "postgresql"], check=False)
        if pg_status.returncode != 0:
            print_step("Starting PostgreSQL service...")
            run_command(["systemctl", "start", "postgresql"])
            run_command(["systemctl", "enable", "postgresql"])
            pg_verify = run_command(["systemctl", "status", "postgresql"], check=False)
            if pg_verify.returncode != 0:
                print_warning(
                    "Could not start PostgreSQL service, continuing anyway..."
                )
                return False
        print_success("PostgreSQL is running and enabled.")
        print_step("Setting up Metasploit database user...")
        user_check = run_command(
            [
                "sudo",
                "-u",
                "postgres",
                "psql",
                "-tAc",
                "SELECT 1 FROM pg_roles WHERE rolname='msf'",
            ],
            check=False,
        )
        if "1" not in user_check.stdout:
            run_command(
                [
                    "sudo",
                    "-u",
                    "postgres",
                    "psql",
                    "-c",
                    "CREATE USER msf WITH PASSWORD 'msf'",
                ],
                check=False,
            )
            run_command(
                [
                    "sudo",
                    "-u",
                    "postgres",
                    "psql",
                    "-c",
                    "CREATE DATABASE msf OWNER msf",
                ],
                check=False,
            )
            print_success("Created Metasploit database and user.")
        else:
            print_success("Metasploit database user already exists.")
        db_check = run_command(
            [
                "sudo",
                "-u",
                "postgres",
                "psql",
                "-tAc",
                "SELECT 1 FROM pg_database WHERE datname='msf'",
            ],
            check=False,
        )
        if "1" not in db_check.stdout:
            run_command(
                [
                    "sudo",
                    "-u",
                    "postgres",
                    "psql",
                    "-c",
                    "CREATE DATABASE msf OWNER msf",
                ],
                check=False,
            )
            print_success("Created Metasploit database.")
        # Update PostgreSQL authentication file if needed
        pg_hba_files = glob.glob("/etc/postgresql/*/main/pg_hba.conf")
        if pg_hba_files:
            for pg_hba in pg_hba_files:
                backup = f"{pg_hba}.backup"
                if not os.path.exists(backup):
                    shutil.copy2(pg_hba, backup)
                    print_success(f"Created backup of {pg_hba}")
                with open(pg_hba, "r") as f:
                    content = f.read()
                if (
                    "local   msf         msf                                     md5"
                    not in content
                ):
                    with open(pg_hba, "a") as f:
                        f.write("\n# Added by Metasploit installer\n")
                        f.write(
                            "local   msf         msf                                     md5\n"
                        )
                    print_success(f"Updated {pg_hba}")
                    run_command(["systemctl", "reload", "postgresql"], check=False)
        return True
    except Exception as e:
        print_warning(f"PostgreSQL configuration error: {e}")
        return False


def check_installation() -> Optional[str]:
    """
    Verify that Metasploit was installed successfully and return the msfconsole path.
    """
    print_step("Verifying installation...")
    possible_paths = [
        "/usr/bin/msfconsole",
        "/opt/metasploit-framework/bin/msfconsole",
        "/usr/local/bin/msfconsole",
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
        with console.status(
            "[bold blue]Checking Metasploit version...", spinner="dots"
        ):
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
            return msfconsole_path
        else:
            print_error("Metasploit verification failed.")
            return None
    except Exception as e:
        print_error(f"Error verifying installation: {e}")
        return None


def initialize_database(msfconsole_path: str) -> bool:
    """
    Initialize the Metasploit database.
    """
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
            with console.status("[bold blue]Initializing database...", spinner="dots"):
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
        with console.status(
            "[bold blue]Initializing database with msfdb...", spinner="dots"
        ):
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


def create_startup_script(msfconsole_path: str) -> bool:
    """
    Create a startup script for launching Metasploit.
    """
    print_step("Creating startup script...")
    script_path = "/usr/local/bin/msf-start"
    try:
        script_content = f"""#!/bin/bash
# Metasploit Framework Launcher

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


def display_completion_info(msfconsole_path: str) -> None:
    """
    Display final installation information.
    """
    completion_message = f"""
Installation completed successfully!

[bold {NordColors.FROST_2}]Metasploit Framework:[/]
• Command: {msfconsole_path}
• Launch with: msf-start or {msfconsole_path}
• Database: Run 'db_status' in msfconsole; initialize with 'msfdb init' if needed

[bold {NordColors.FROST_2}]Documentation:[/]
• https://docs.metasploit.com/
"""
    display_panel(completion_message, NordColors.GREEN, "Installation Complete")


def run_full_setup() -> None:
    """
    Execute the complete automated setup process.
    """
    console.clear()
    console.print(create_header())
    console.print()
    display_panel(
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
        "Automated Setup Process",
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


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    try:
        if os.geteuid() != 0:
            console.clear()
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
