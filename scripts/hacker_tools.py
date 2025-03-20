#!/usr/bin/env python3

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
from typing import List, Dict, Optional, Tuple, Any, Union
from dataclasses import dataclass, field

if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)


def install_dependencies():
    required_packages = ["rich", "pyfiglet"]
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user"] + required_packages)
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn,
        TimeRemainingColumn, TransferSpeedColumn, MofNCompleteColumn
    )
    from rich.align import Align
    from rich.style import Style
    from rich.logging import RichHandler
    from rich.traceback import install as install_rich_traceback
    from rich.box import ROUNDED
except ImportError:
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)

install_rich_traceback(show_locals=True)
console = Console()

VERSION = "1.1.0"
APP_NAME = "Security Tools Installer"
APP_SUBTITLE = "macOS Security Configuration Suite"
DEFAULT_LOG_DIR = Path.home() / "security_setup_logs"
DEFAULT_REPORT_DIR = DEFAULT_LOG_DIR / "reports"
OPERATION_TIMEOUT = 600


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
        return [cls.POLAR_NIGHT_1, cls.POLAR_NIGHT_2, cls.POLAR_NIGHT_3, cls.POLAR_NIGHT_4][:steps]

    @classmethod
    def get_progress_columns(cls):
        return [
            SpinnerColumn(spinner_name="dots", style=f"bold {cls.FROST_1}"),
            TextColumn(f"[bold {cls.FROST_2}]{{task.description}}[/]"),
            BarColumn(bar_width=None, style=cls.POLAR_NIGHT_3, complete_style=cls.FROST_2, finished_style=cls.GREEN),
            TaskProgressColumn(style=cls.SNOW_STORM_1),
            MofNCompleteColumn(),
            TimeRemainingColumn(compact=True),
        ]


SECURITY_TOOLS = {
    "Network Analysis": [
        "wireshark", "nmap", "tcpdump", "netcat", "iftop", "ettercap",
        "termshark", "masscan", "arp-scan", "darkstat"
    ],
    "Vulnerability Assessment": ["nikto", "sqlmap", "gobuster", "whatweb"],
    "Forensics": ["sleuthkit", "testdisk", "foremost", "photorec"],
    "System Hardening": ["lynis", "rkhunter", "chkrootkit", "aide", "clamav"],
    "Password & Crypto": ["john", "hashcat", "hydra", "medusa", "gnupg", "ccrypt"],
    "Wireless Security": ["aircrack-ng", "reaver", "pixiewps"],
    "Development Tools": ["git", "gdb", "cmake", "meson", "python3", "radare2", "binwalk"],
    "Container Security": ["docker", "docker-compose", "podman"],
    "Malware Analysis": ["clamav", "yara", "ssdeep", "radare2"],
    "Privacy & Anonymity": ["tor", "torbrowser-launcher", "openvpn", "wireguard-tools"],
}

BREW_PACKAGE_TYPE = {
    "docker": "cask",
    "wireshark": "cask",
    "torbrowser-launcher": "cask",
    "scalpel": "skip",
    "whatweb": "skip",
    "dsniff": "skip",
    "photorec": "skip",
    "dirb": "skip",
    "wifite": "skip",
}


@dataclass
class InstallationStats:
    start_time: datetime = field(default_factory=datetime.now)
    successful_packages: List[str] = field(default_factory=list)
    failed_packages: List[str] = field(default_factory=list)
    skipped_packages: List[str] = field(default_factory=list)
    end_time: Optional[datetime] = None

    @property
    def elapsed_time(self) -> str:
        end = self.end_time or datetime.now()
        seconds = (end - self.start_time).total_seconds()
        minutes, seconds = divmod(seconds, 60)
        return f"{int(minutes)}m {int(seconds)}s"


def setup_logging(log_dir: Path, verbose: bool = False) -> logging.Logger:
    log_dir.mkdir(exist_ok=True, parents=True)
    log_file = log_dir / f"security_setup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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

    return Panel(
        Text.from_markup(styled_text),
        border_style=NordColors.FROST_1,
        box=NordColors.NORD_BOX,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_3}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(message: str, style=NordColors.INFO, prefix="•", logger=None):
    if isinstance(style, str):
        console.print(f"[{style}]{prefix} {message}[/{style}]")
    else:
        console.print(f"{prefix} {message}", style=style)

    if logger:
        if style == NordColors.RED:
            logger.error(f"{prefix} {message}")
        elif style == NordColors.YELLOW:
            logger.warning(f"{prefix} {message}")
        else:
            logger.info(f"{prefix} {message}")


def print_error(message, logger=None):
    print_message(message, NordColors.ERROR, "✗", logger)


def print_success(message, logger=None):
    print_message(message, NordColors.SUCCESS, "✓", logger)


def print_warning(message, logger=None):
    print_message(message, NordColors.WARNING, "⚠", logger)


def print_info(message, logger=None):
    print_message(message, NordColors.INFO, "ℹ", logger)


def display_panel(message: str, style=NordColors.INFO, title=None):
    if isinstance(style, str):
        panel = Panel(
            Text.from_markup(f"[bold {style}]{message}[/]"),
            border_style=style,
            box=NordColors.NORD_BOX,
            padding=(1, 2),
            title=f"[bold {style}]{title}[/]" if title else None,
        )
    else:
        panel = Panel(
            Text(message),
            title=title,
            border_style=style,
            box=NordColors.NORD_BOX,
            padding=(1, 2)
        )
    console.print(panel)


def cleanup(logger=None):
    print_message("Cleaning up temporary resources...", NordColors.FROST_3, logger=logger)
    for temp_file in glob.glob("/tmp/security_setup_*"):
        try:
            os.remove(temp_file)
            if logger:
                logger.debug(f"Removed temporary file: {temp_file}")
        except OSError:
            if logger:
                logger.debug(f"Failed to remove temporary file: {temp_file}")


def signal_handler(sig, frame, logger=None):
    try:
        sig_name = signal.Signals(sig).name
    except Exception:
        sig_name = f"Signal {sig}"
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠", logger=logger)
    cleanup(logger)
    sys.exit(128 + sig)


def run_command(
        cmd: List[str],
        env=None,
        check=True,
        capture_output=True,
        timeout=OPERATION_TIMEOUT,
        logger=None
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
        print_error(f"Command failed: {cmd_str}", logger)
        if logger:
            logger.error(f"Command error output: {e.stderr.strip() if e.stderr else ''}")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {cmd_str}", logger)
        if logger:
            logger.error(f"Timeout expired for command: {cmd_str}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {cmd_str} - {e}", logger)
        if logger:
            logger.exception(f"Error executing command: {cmd_str}")
        raise


class SecurityInstaller:
    def __init__(self, simulate=False, verbose=False, logger=None):
        self.simulate = simulate
        self.verbose = verbose
        self.logger = logger
        self.stats = InstallationStats()

    def get_target_packages(self) -> List[Tuple[str, str]]:
        packages = []
        for tools in SECURITY_TOOLS.values():
            for pkg in tools:
                pkg_type = BREW_PACKAGE_TYPE.get(pkg, "formula")
                packages.append((pkg, pkg_type))

        unique = {}
        for pkg, typ in packages:
            unique[pkg] = typ
        return list(unique.items())

    def cleanup_package_system(self) -> bool:
        try:
            if self.simulate:
                print_warning("Simulating Homebrew cleanup...", self.logger)
                time.sleep(1)
                return True

            print_info("Running 'brew cleanup'...", self.logger)
            run_command(["brew", "cleanup"], logger=self.logger)
            print_success("Homebrew cleanup completed", self.logger)
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Cleanup failed: {e}")
            return False

    def setup_package_manager(self) -> bool:
        try:
            if self.simulate:
                print_warning("Simulating Homebrew update/upgrade...", self.logger)
                time.sleep(1)
                return True

            if shutil.which("brew") is None:
                print_error("Homebrew is not installed. Please install Homebrew from https://brew.sh", self.logger)
                sys.exit(1)

            print_info("Updating Homebrew...", self.logger)
            run_command(["brew", "update"], logger=self.logger)
            print_info("Upgrading installed formulae...", self.logger)
            run_command(["brew", "upgrade"], logger=self.logger)
            print_success("Homebrew update and upgrade completed", self.logger)
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Package manager setup failed: {e}")
            return False

    def install_packages(self, packages, progress_callback=None, skip_failed=True) -> Tuple[bool, List[str]]:
        try:
            if self.simulate:
                print_warning(f"Simulating installation of {len(packages)} packages", self.logger)
                time.sleep(2)
                return True, []

            failed_packages = []

            formula_packages = [pkg for pkg, typ in packages if typ == "formula"]
            cask_packages = [pkg for pkg, typ in packages if typ == "cask"]
            skip_packages = [pkg for pkg, typ in packages if typ == "skip"]

            for pkg in skip_packages:
                print_warning(f"Skipping unavailable package: {pkg}", self.logger)
                self.stats.skipped_packages.append(pkg)

            chunk_size = 10
            for i in range(0, len(formula_packages), chunk_size):
                chunk = formula_packages[i:i + chunk_size]
                desc = f"Installing formula packages {i + 1}-{min(i + chunk_size, len(formula_packages))} of {len(formula_packages)}"

                if progress_callback:
                    progress_callback(desc, i, len(formula_packages))
                else:
                    print_info(desc, self.logger)

                try:
                    run_command(["brew", "install"] + chunk, logger=self.logger)
                    self.stats.successful_packages.extend(chunk)
                except subprocess.CalledProcessError:
                    print_warning("Retrying individual formula packages...", self.logger)
                    for package in chunk:
                        if package not in self.stats.successful_packages:
                            try:
                                run_command(["brew", "install", package], logger=self.logger)
                                self.stats.successful_packages.append(package)
                            except subprocess.CalledProcessError:
                                failed_packages.append(package)
                                if self.logger:
                                    self.logger.error(f"Failed to install: {package}")

            for i in range(0, len(cask_packages), chunk_size):
                chunk = cask_packages[i:i + chunk_size]
                desc = f"Installing cask packages {i + 1}-{min(i + chunk_size, len(cask_packages))} of {len(cask_packages)}"

                if progress_callback:
                    progress_callback(desc, i, len(cask_packages))
                else:
                    print_info(desc, self.logger)

                try:
                    run_command(["brew", "install", "--cask"] + chunk, logger=self.logger)
                    self.stats.successful_packages.extend(chunk)
                except subprocess.CalledProcessError:
                    print_warning("Retrying individual cask packages...", self.logger)
                    for package in chunk:
                        if package not in self.stats.successful_packages:
                            try:
                                run_command(["brew", "install", "--cask", package], logger=self.logger)
                                self.stats.successful_packages.append(package)
                            except subprocess.CalledProcessError:
                                failed_packages.append(package)
                                if self.logger:
                                    self.logger.error(f"Failed to install: {package}")

            if failed_packages:
                self.stats.failed_packages = failed_packages
                if skip_failed:
                    print_warning(f"Completed with {len(failed_packages)} failures, continuing...", self.logger)
                    return True, failed_packages
                else:
                    print_error(f"Installation failed for {len(failed_packages)} packages", self.logger)
                    return False, failed_packages

            print_success(f"Successfully installed {len(self.stats.successful_packages)} packages", self.logger)
            return True, []
        except Exception as e:
            if self.logger:
                self.logger.exception("Installation failed")
            self.stats.failed_packages = [pkg for pkg, _ in packages]
            print_error(f"Installation failed: {e}", self.logger)
            return False, [pkg for pkg, _ in packages]

    def configure_installed_services(self) -> bool:
        try:
            if self.simulate:
                print_warning("Simulating service configuration...", self.logger)
                time.sleep(1)
                return True

            print_info("No additional service configuration required on macOS", self.logger)
            return True
        except Exception as e:
            print_error(f"Service configuration failed: {e}", self.logger)
            if self.logger:
                self.logger.exception("Service configuration failed")
            return False

    def save_installation_report(self, report_dir: Path) -> str:
        report_dir.mkdir(exist_ok=True, parents=True)
        self.stats.end_time = datetime.now()

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
            "duration": self.stats.elapsed_time,
            "successful_packages": sorted(self.stats.successful_packages),
            "failed_packages": sorted(self.stats.failed_packages),
            "skipped_packages": sorted(self.stats.skipped_packages),
            "simulation_mode": self.simulate,
            "total_packages_attempted": len(self.stats.successful_packages) +
                                        len(self.stats.failed_packages) +
                                        len(self.stats.skipped_packages),
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
            f.write(f"Duration: {self.stats.elapsed_time}\n")
            f.write(f"Simulation Mode: {'Yes' if self.simulate else 'No'}\n\n")
            f.write("System Information:\n")
            for key, value in system_info.items():
                f.write(f"  {key}: {value}\n")
            f.write("\nInstallation Summary:\n")
            f.write(f"  Successfully installed: {len(self.stats.successful_packages)} packages\n")
            f.write(f"  Failed packages: {len(self.stats.failed_packages)}\n")
            f.write(f"  Skipped packages: {len(self.stats.skipped_packages)}\n")
            f.write(f"  Total attempted: {report['total_packages_attempted']}\n\n")
            if self.stats.failed_packages:
                f.write("Failed Packages:\n")
                for pkg in sorted(self.stats.failed_packages):
                    f.write(f"  - {pkg}\n")

        print_info(f"Installation report saved to {report_file}", self.logger)
        return str(report_file)


def main():
    simulate = False
    verbose = False
    skip_failed = True
    report_dir = DEFAULT_REPORT_DIR
    log_dir = DEFAULT_LOG_DIR

    logger = setup_logging(log_dir, verbose)

    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, logger))
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, logger))
    atexit.register(lambda: cleanup(logger))

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

    installer = SecurityInstaller(simulate=simulate, verbose=verbose, logger=logger)

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

    total_unique = len({pkg for tools in SECURITY_TOOLS.values() for pkg in tools})
    console.print(
        f"Installing [bold {NordColors.FROST_1}]{total_unique}[/] unique packages from all {len(SECURITY_TOOLS)} categories"
    )
    console.print()

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
        if not installer.cleanup_package_system():
            print_warning(
                "Homebrew cleanup failed; continuing as requested...",
                logger,
            )
        progress.update(main_task, completed=20)
        progress.update(sub_task, completed=100)

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
        if not installer.setup_package_manager():
            print_warning(
                "Homebrew update/upgrade failed; continuing as requested...",
                logger,
            )
        progress.update(main_task, completed=40)
        progress.update(sub_task, completed=100)

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
        target_packages = installer.get_target_packages()

        def update_progress(desc, current, total):
            percent = min(100, int((current / total) * 100))
            progress.update(
                sub_task, description=f"[{NordColors.FROST_2}]{desc}", completed=percent
            )

        success, failed = installer.install_packages(
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
        installer.configure_installed_services()
        progress.update(sub_task, completed=100)
        progress.update(
            main_task,
            description=f"[{NordColors.GREEN}]Installation completed",
            completed=100,
        )
        progress.update(sub_task, visible=False)

    report_file = installer.save_installation_report(report_dir)
    console.print()
    if installer.stats.failed_packages:
        console.print(
            Panel(
                f"[bold]Installation completed with some failures[/]\n\n"
                f"Successfully installed: {len(installer.stats.successful_packages)} packages\n"
                f"Failed packages: {len(installer.stats.failed_packages)}\n\n"
                f"Failed: {', '.join(installer.stats.failed_packages[:10])}{'...' if len(installer.stats.failed_packages) > 10 else ''}",
                title="[bold yellow]Installation Summary[/]",
                border_style=NordColors.YELLOW,
            )
        )
    else:
        console.print(
            Panel(
                f"[bold]Installation completed successfully![/]\n\n"
                f"Installed: {len(installer.stats.successful_packages)} security tools",
                title="[bold green]Installation Complete[/]",
                border_style=NordColors.GREEN,
            )
        )
    log_files = list(DEFAULT_LOG_DIR.glob("security_setup_*.log"))
    latest_log = max(log_files, key=lambda p: p.stat().st_mtime) if log_files else None
    if latest_log:
        console.print(f"\nDetailed logs available at: [bold]{latest_log}[/]")
        console.print(f"Installation report saved to: [bold]{report_file}[/]")
    console.print(f"\nTotal installation time: [bold]{installer.stats.elapsed_time}[/]")


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