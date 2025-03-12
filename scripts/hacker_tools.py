#!/usr/bin/env python3
"""
Unattended Security Tools Installer for macOS
--------------------------------------------------
A fully automated system configuration tool that installs and configures
security, analysis, development, and intrusion detection tools on macOS.
This script runs completely unattended with no interactive menu or prompts.

Usage:
  Run with sudo if required: sudo python3 security_installer.py

Version: 1.0.0
"""

import os
import sys
import subprocess
import time
import logging
import glob
import signal
import atexit
import json
import platform
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any

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
    from rich.logging import RichHandler
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Installing required dependencies...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich", "pyfiglet"],
            check=True,
            capture_output=True,
        )
        print("Dependencies installed. Please run the script again.")
    except subprocess.SubprocessError:
        print("Failed to install dependencies. Please install manually with:")
        print("pip install rich pyfiglet")
    sys.exit(1)

install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION: str = "1.0.0"
APP_NAME: str = "Unattended Security Tools Installer"
APP_SUBTITLE: str = "Automated macOS Security Configuration via Homebrew"

# For macOS, use a log directory in the user's home directory.
DEFAULT_LOG_DIR = Path.home() / "security_setup_logs"
DEFAULT_REPORT_DIR = DEFAULT_LOG_DIR / "reports"
OPERATION_TIMEOUT: int = 600  # 10 minutes timeout for long operations


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


# ----------------------------------------------------------------
# Security Tools Categories
# ----------------------------------------------------------------
# Note: Not all these packages are available on macOS/Homebrew.
SECURITY_TOOLS: Dict[str, List[str]] = {
    "Network Analysis": [
        "wireshark",
        "nmap",
        "tcpdump",
        "netcat",
        "iftop",
        "ettercap",
        "dsniff",
        "termshark",
        "masscan",
        "arp-scan",
        "darkstat",
    ],
    "Vulnerability Assessment": ["nikto", "sqlmap", "dirb", "gobuster", "whatweb"],
    "Forensics": ["sleuthkit", "testdisk", "foremost", "scalpel", "photorec"],
    "System Hardening": ["lynis", "rkhunter", "chkrootkit", "aide", "clamav"],
    "Password & Crypto": ["john", "hashcat", "hydra", "medusa", "gnupg", "ccrypt"],
    "Wireless Security": ["aircrack-ng", "wifite", "reaver", "pixiewps"],
    "Development Tools": [
        "git",
        "gdb",
        "cmake",
        "meson",
        "python3",
        "radare2",
        "binwalk",
    ],
    "Container Security": ["docker", "docker-compose", "podman"],
    "Malware Analysis": ["clamav", "yara", "ssdeep", "radare2"],
    "Privacy & Anonymity": ["tor", "torbrowser-launcher", "openvpn", "wireguard-tools"],
}

# ----------------------------------------------------------------
# Create a Rich Console
# ----------------------------------------------------------------
console: Console = Console()


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def setup_logging(log_dir: Path, verbose: bool = False) -> logging.Logger:
    log_dir.mkdir(exist_ok=True, parents=True)
    log_file = (
        log_dir / f"security_setup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True, level=log_level),
            logging.FileHandler(log_file),
        ],
    )
    logger = logging.getLogger("security_setup")
    logger.info(f"Logging initialized. Log file: {log_file}")
    return logger


def create_header() -> Panel:
    fonts = ["small", "slant", "digital", "chunky", "standard"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=80)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = APP_NAME
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "━" * 80 + "[/]"
    styled_text = border + "\n" + styled_text + border
    return Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_1}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_2}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(
    text: str,
    style: str = NordColors.FROST_2,
    prefix: str = "•",
    logger: Optional[logging.Logger] = None,
) -> None:
    console.print(f"[{style}]{prefix} {text}[/{style}]")
    if logger:
        if style == NordColors.RED:
            logger.error(f"{prefix} {text}")
        elif style == NordColors.YELLOW:
            logger.warning(f"{prefix} {text}")
        else:
            logger.info(f"{prefix} {text}")


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


def cleanup(logger: Optional[logging.Logger] = None) -> None:
    print_message(
        "Cleaning up temporary resources...", NordColors.FROST_3, logger=logger
    )
    for temp_file in glob.glob("/tmp/security_setup_*"):
        try:
            os.remove(temp_file)
            if logger:
                logger.debug(f"Removed temporary file: {temp_file}")
        except OSError:
            if logger:
                logger.debug(f"Failed to remove temporary file: {temp_file}")


def signal_handler(
    sig: int, frame: Any, logger: Optional[logging.Logger] = None
) -> None:
    try:
        sig_name = signal.Signals(sig).name
    except Exception:
        sig_name = f"Signal {sig}"
    print_message(
        f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠", logger=logger
    )
    cleanup(logger)
    sys.exit(128 + sig)


def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
    logger: Optional[logging.Logger] = None,
) -> subprocess.CompletedProcess:
    cmd_str = " ".join(cmd)
    if logger:
        logger.debug(f"Executing command: {cmd_str}")
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        if logger and result.stdout and len(result.stdout) < 1000:
            logger.debug(f"Command output: {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        print_message(f"Command failed: {cmd_str}", NordColors.RED, "✗", logger=logger)
        if logger:
            logger.error(
                f"Command error output: {e.stderr.strip() if e.stderr else ''}"
            )
        raise
    except subprocess.TimeoutExpired:
        print_message(
            f"Command timed out after {timeout} seconds: {cmd_str}",
            NordColors.RED,
            "✗",
            logger=logger,
        )
        if logger:
            logger.error(f"Timeout expired for command: {cmd_str}")
        raise
    except Exception as e:
        print_message(
            f"Error executing command: {cmd_str} - {e}",
            NordColors.RED,
            "✗",
            logger=logger,
        )
        if logger:
            logger.exception(f"Error executing command: {cmd_str}")
        raise


# ----------------------------------------------------------------
# System Setup Class (macOS using Homebrew)
# ----------------------------------------------------------------
class SystemSetup:
    """Handles Homebrew-based package management and service configuration on macOS."""

    def __init__(
        self,
        simulate: bool = False,
        verbose: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        self.simulate = simulate
        self.verbose = verbose
        self.logger = logger
        self.failed_packages: List[str] = []
        self.successful_packages: List[str] = []
        self.skipped_packages: List[str] = []
        self.start_time = datetime.now()

    @staticmethod
    def check_root() -> bool:
        # Homebrew installations typically do not require root on macOS.
        return True

    def get_target_packages(self) -> List[str]:
        all_packages = {pkg for tools in SECURITY_TOOLS.values() for pkg in tools}
        return list(all_packages)

    def log_operation(
        self, message: str, level: str = "info", prefix: str = "•"
    ) -> None:
        style_map = {
            "info": NordColors.FROST_2,
            "warning": NordColors.YELLOW,
            "error": NordColors.RED,
            "success": NordColors.GREEN,
        }
        print_message(
            message, style_map.get(level, NordColors.FROST_2), prefix, self.logger
        )

    def cleanup_package_system(self) -> bool:
        try:
            if self.simulate:
                self.log_operation("Simulating Homebrew cleanup...", "warning")
                time.sleep(1)
                return True
            self.log_operation("Running 'brew cleanup'...")
            run_command(["brew", "cleanup"], logger=self.logger)
            self.log_operation("Homebrew cleanup completed", "success", "✓")
            return True
        except subprocess.CalledProcessError as e:
            if self.logger:
                self.logger.error(f"Cleanup failed: {e}")
            return False

    def setup_package_manager(self) -> bool:
        try:
            if self.simulate:
                self.log_operation("Simulating Homebrew update/upgrade...", "warning")
                time.sleep(1)
                return True
            # Ensure Homebrew is installed
            if shutil.which("brew") is None:
                self.log_operation(
                    "Homebrew is not installed. Please install Homebrew from https://brew.sh",
                    "error",
                    "✗",
                )
                sys.exit(1)
            self.log_operation("Updating Homebrew...")
            run_command(["brew", "update"], logger=self.logger)
            self.log_operation("Upgrading installed formulae...")
            run_command(["brew", "upgrade"], logger=self.logger)
            self.log_operation("Homebrew update and upgrade completed", "success", "✓")
            return True
        except subprocess.CalledProcessError as e:
            if self.logger:
                self.logger.error(f"Package manager setup failed: {e}")
            return False

    def install_packages(
        self, packages: List[str], progress_callback=None, skip_failed: bool = True
    ) -> Tuple[bool, List[str]]:
        try:
            if self.simulate:
                self.log_operation(
                    f"Simulating installation of {len(packages)} packages", "warning"
                )
                time.sleep(2)
                return True, []
            failed_packages = []
            chunk_size = 10
            for i in range(0, len(packages), chunk_size):
                chunk = packages[i : i + chunk_size]
                desc = f"Installing packages {i + 1}-{min(i + chunk_size, len(packages))} of {len(packages)}"
                if progress_callback:
                    progress_callback(desc, i, len(packages))
                else:
                    self.log_operation(desc)
                try:
                    run_command(["brew", "install"] + chunk, logger=self.logger)
                    self.successful_packages.extend(chunk)
                except subprocess.CalledProcessError:
                    self.log_operation("Retrying individual packages...", "warning")
                    for package in chunk:
                        if package not in self.successful_packages:
                            try:
                                run_command(
                                    ["brew", "install", package], logger=self.logger
                                )
                                self.successful_packages.append(package)
                            except subprocess.CalledProcessError:
                                failed_packages.append(package)
                                if self.logger:
                                    self.logger.error(f"Failed to install: {package}")
            if failed_packages:
                self.failed_packages = failed_packages
                if skip_failed:
                    self.log_operation(
                        f"Completed with {len(failed_packages)} failures, continuing...",
                        "warning",
                        "⚠",
                    )
                    return True, failed_packages
                else:
                    self.log_operation(
                        f"Installation failed for {len(failed_packages)} packages",
                        "error",
                        "✗",
                    )
                    return False, failed_packages
            self.log_operation(
                f"Successfully installed {len(self.successful_packages)} packages",
                "success",
                "✓",
            )
            return True, []
        except Exception as e:
            if self.logger:
                self.logger.exception("Installation failed")
            self.failed_packages = packages
            self.log_operation(f"Installation failed: {e}", "error", "✗")
            return False, packages

    def configure_installed_services(self) -> bool:
        try:
            if self.simulate:
                self.log_operation("Simulating service configuration...", "warning")
                time.sleep(1)
                return True
            # Most Homebrew-installed CLI tools do not require further service configuration on macOS.
            self.log_operation(
                "No additional service configuration required on macOS", "info"
            )
            return True
        except Exception as e:
            self.log_operation(f"Service configuration failed: {e}", "error", "✗")
            if self.logger:
                self.logger.exception("Service configuration failed")
            return False

    def _check_if_installed(self, package: str) -> bool:
        try:
            result = run_command(
                ["brew", "list", "--formula", package],
                check=False,
                capture_output=True,
                logger=self.logger,
            )
            return package in result.stdout
        except Exception:
            return False

    def save_installation_report(self, report_dir: Path) -> str:
        report_dir.mkdir(exist_ok=True, parents=True)
        elapsed = datetime.now() - self.start_time
        elapsed_str = f"{int(elapsed.total_seconds() // 60)}m {int(elapsed.total_seconds() % 60)}s"
        system_info = {
            "hostname": platform.node(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
        }
        report = {
            "timestamp": datetime.now().isoformat(),
            "system_info": system_info,
            "duration": elapsed_str,
            "successful_packages": sorted(self.successful_packages),
            "failed_packages": sorted(self.failed_packages),
            "skipped_packages": sorted(self.skipped_packages),
            "simulation_mode": self.simulate,
            "total_packages_attempted": len(self.successful_packages)
            + len(self.failed_packages)
            + len(self.skipped_packages),
        }
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"installation_report_{timestamp}.json"
        report_txt = report_dir / f"installation_report_{timestamp}.txt"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
        with open(report_txt, "w") as f:
            f.write("Security Tools Installation Report\n")
            f.write("================================\n\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Duration: {elapsed_str}\n")
            f.write(f"Simulation Mode: {'Yes' if self.simulate else 'No'}\n\n")
            f.write("System Information:\n")
            for key, value in system_info.items():
                f.write(f"  {key}: {value}\n")
            f.write("\nInstallation Summary:\n")
            f.write(
                f"  Successfully installed: {len(self.successful_packages)} packages\n"
            )
            f.write(f"  Failed packages: {len(self.failed_packages)}\n")
            f.write(f"  Skipped: {len(self.skipped_packages)}\n")
            f.write(f"  Total attempted: {report['total_packages_attempted']}\n\n")
            if self.failed_packages:
                f.write("Failed Packages:\n")
                for pkg in sorted(self.failed_packages):
                    f.write(f"  - {pkg}\n")
        self.log_operation(f"Installation report saved to {report_file}", "info")
        return str(report_file)


# ----------------------------------------------------------------
# Main Application Function (Fully Automated for macOS)
# ----------------------------------------------------------------
def main() -> None:
    simulate = False
    verbose = False
    skip_failed = True
    report_dir = DEFAULT_REPORT_DIR
    log_dir = DEFAULT_LOG_DIR

    logger = setup_logging(log_dir, verbose)

    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, logger))
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, logger))
    atexit.register(lambda: cleanup(logger))

    # Homebrew installations on macOS do not require root; however, ensure brew is installed.
    if shutil.which("brew") is None:
        display_panel(
            "[bold]Homebrew is not installed.[/]\nPlease install Homebrew from [bold cyan]https://brew.sh[/]",
            style=NordColors.RED,
            title="Error",
        )
        sys.exit(1)

    console.clear()
    console.print(create_header())
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time} | Host: {platform.node()}[/]"
        )
    )
    console.print()

    setup = SystemSetup(simulate=simulate, verbose=verbose, logger=logger)

    # Display installation plan
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        border_style=NordColors.FROST_3,
    )
    table.add_column("Category", style=f"bold {NordColors.FROST_2}")
    table.add_column("Number of Tools", style=NordColors.SNOW_STORM_1)
    for category, tools in SECURITY_TOOLS.items():
        table.add_row(category, str(len(tools)))
    console.print(
        Panel(
            table, title="[bold]Installation Plan[/]", border_style=NordColors.FROST_2
        )
    )
    console.print(
        f"Installing [bold {NordColors.FROST_1}]{len(set(pkg for tools in SECURITY_TOOLS.values() for pkg in tools))}[/] unique packages from all {len(SECURITY_TOOLS)} categories"
    )
    console.print()

    # Use a single Progress instance for all operations
    with Progress(
        SpinnerColumn(style=f"{NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        main_task = progress.add_task("[cyan]Overall Progress", total=100)
        sub_task = progress.add_task("Initializing...", total=100, visible=False)

        # Step 1: Cleanup package system
        progress.update(
            main_task,
            description=f"[{NordColors.FROST_2}]Cleaning Homebrew cache",
            completed=0,
        )
        progress.update(
            sub_task,
            visible=True,
            completed=0,
            description=f"[{NordColors.FROST_2}]Cleaning Homebrew cache",
        )
        if not setup.cleanup_package_system():
            print_message(
                "Homebrew cleanup failed; continuing as requested...",
                NordColors.YELLOW,
                "⚠",
                logger,
            )
        progress.update(main_task, completed=20)
        progress.update(sub_task, completed=100)

        # Step 2: Setup package manager
        progress.update(
            main_task,
            description=f"[{NordColors.FROST_2}]Updating Homebrew",
            completed=20,
        )
        progress.update(
            sub_task,
            completed=0,
            description=f"[{NordColors.FROST_2}]Updating Homebrew",
        )
        if not setup.setup_package_manager():
            print_message(
                "Homebrew update/upgrade failed; continuing as requested...",
                NordColors.YELLOW,
                "⚠",
                logger,
            )
        progress.update(main_task, completed=40)
        progress.update(sub_task, completed=100)

        # Step 3: Install security tools
        progress.update(
            main_task,
            description=f"[{NordColors.FROST_2}]Installing security tools",
            completed=40,
        )
        progress.update(
            sub_task,
            completed=0,
            description=f"[{NordColors.FROST_2}]Installing security tools",
        )
        target_packages = setup.get_target_packages()

        def update_progress(desc, current, total):
            percent = min(100, int((current / total) * 100))
            progress.update(
                sub_task, description=f"[{NordColors.FROST_2}]{desc}", completed=percent
            )

        success, failed = setup.install_packages(
            target_packages, progress_callback=update_progress, skip_failed=skip_failed
        )
        if failed and not skip_failed and not simulate:
            display_panel(
                f"[bold]Failed to install {len(failed)} packages[/]\nFailed: {', '.join(failed[:10])}{'...' if len(failed) > 10 else ''}",
                style=NordColors.RED,
                title="Installation Error",
            )
            sys.exit(1)
        elif failed:
            progress.update(
                main_task,
                description=f"[{NordColors.YELLOW}]Some packages failed",
                completed=80,
            )
        else:
            progress.update(
                main_task,
                description=f"[{NordColors.GREEN}]Packages installed successfully",
                completed=80,
            )
        progress.update(sub_task, completed=100)

        # Step 4: Configure installed services (if applicable)
        progress.update(
            main_task,
            description=f"[{NordColors.FROST_2}]Configuring services",
            completed=80,
        )
        progress.update(
            sub_task,
            completed=0,
            description=f"[{NordColors.FROST_2}]Configuring services",
        )
        setup.configure_installed_services()
        progress.update(sub_task, completed=100)
        progress.update(
            main_task,
            description=f"[{NordColors.GREEN}]Installation completed",
            completed=100,
        )
        progress.update(sub_task, visible=False)

    report_file = setup.save_installation_report(report_dir)
    console.print()
    if setup.failed_packages:
        console.print(
            Panel(
                f"[bold]Installation completed with some failures[/]\n\n"
                f"Successfully installed: {len(setup.successful_packages)} packages\n"
                f"Failed packages: {len(setup.failed_packages)}\n\n"
                f"Failed: {', '.join(setup.failed_packages[:10])}{'...' if len(setup.failed_packages) > 10 else ''}",
                title="[bold yellow]Installation Summary[/]",
                border_style=NordColors.YELLOW,
            )
        )
    else:
        console.print(
            Panel(
                f"[bold]Installation completed successfully![/]\n\n"
                f"Installed: {len(setup.successful_packages)} security tools",
                title="[bold green]Installation Complete[/]",
                border_style=NordColors.GREEN,
            )
        )
    log_files = list(DEFAULT_LOG_DIR.glob("security_setup_*.log"))
    latest_log = max(log_files, key=lambda p: p.stat().st_mtime) if log_files else None
    if latest_log:
        console.print(f"\nDetailed logs available at: [bold]{latest_log}[/]")
        console.print(f"Installation report saved to: [bold]{report_file}[/]")
    finish_time = datetime.now()
    elapsed = finish_time - setup.start_time
    console.print(
        f"\nTotal installation time: [bold]{int(elapsed.total_seconds() // 60)} minutes, {int(elapsed.total_seconds() % 60)} seconds[/]"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        display_panel(
            "Operation cancelled by user", style=NordColors.YELLOW, title="Cancelled"
        )
        sys.exit(130)
    except Exception as e:
        display_panel(f"Unhandled error: {e}", style=NordColors.RED, title="Error")
        console.print_exception()
        sys.exit(1)
