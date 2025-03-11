#!/usr/bin/env python3
"""
Unattended Security Tools Installer
--------------------------------------------------
A fully automated system configuration tool that installs and configures
security, analysis, development, and intrusion detection tools on Ubuntu.
This script runs completely unattended with no interactive menu or prompts.

Usage:
  Run with sudo: sudo python3 security_installer.py

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

# Install Rich traceback handler for improved error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION: str = "1.0.0"
APP_NAME: str = "Unattended Security Tools Installer"
APP_SUBTITLE: str = "Automated System Security Configuration"

DEFAULT_LOG_DIR = Path("/var/log/security_setup")
DEFAULT_REPORT_DIR = Path("/var/log/security_setup/reports")
OPERATION_TIMEOUT: int = 600  # 10 minutes timeout for long operations


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    POLAR_NIGHT_1 = "#2E3440"  # Dark background
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade
    SNOW_STORM_1 = "#D8DEE9"  # Dark text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue
    RED = "#BF616A"  # Red
    ORANGE = "#D08770"  # Orange
    YELLOW = "#EBCB8B"  # Yellow
    GREEN = "#A3BE8C"  # Green


# ----------------------------------------------------------------
# Security Tools Categories & Problematic Packages
# ----------------------------------------------------------------
SECURITY_TOOLS: Dict[str, List[str]] = {
    "Network Analysis": [
        "wireshark",
        "nmap",
        "tcpdump",
        "netcat-openbsd",
        "nethogs",
        "iftop",
        "ettercap-graphical",
        "dsniff",
        "netsniff-ng",
        "termshark",
        "ntopng",
        "zabbix-server-mysql",
        "prometheus",
        "bettercap",
        "p0f",
        "masscan",
        "arpwatch",
        "darkstat",
    ],
    "Vulnerability Assessment": [
        "nikto",
        "wapiti",
        "sqlmap",
        "dirb",
        "gobuster",
        "whatweb",
        "openvas",
    ],
    "Forensics": [
        "autopsy",
        "sleuthkit",
        "dc3dd",
        "testdisk",
        "foremost",
        "scalpel",
        "recoverjpeg",
        "extundelete",
        "xmount",
        "guymager",
        "plaso",
    ],
    "System Hardening": [
        "lynis",
        "rkhunter",
        "chkrootkit",
        "aide",
        "ufw",
        "fail2ban",
        "auditd",
        "apparmor",
        "firejail",
        "clamav",
        "crowdsec",
        "yubikey-manager",
        "policycoreutils",
    ],
    "Password & Crypto": [
        "john",
        "hashcat",
        "hydra",
        "medusa",
        "ophcrack",
        "fcrackzip",
        "gnupg",
        "cryptsetup",
        "yubikey-personalization",
        "keepassxc",
        "pass",
        "keychain",
        "ccrypt",
    ],
    "Wireless Security": [
        "aircrack-ng",
        "wifite",
        "hostapd",
        "reaver",
        "bully",
        "pixiewps",
        "mdk4",
        "bluez-tools",
        "btscanner",
        "horst",
        "wavemon",
        "cowpatty",
    ],
    "Development Tools": [
        "build-essential",
        "git",
        "gdb",
        "lldb",
        "cmake",
        "meson",
        "python3-pip",
        "python3-venv",
        "radare2",
        "apktool",
        "binwalk",
        "patchelf",
        "elfutils",
    ],
    "Container Security": [
        "docker.io",
        "docker-compose",
        "podman",
    ],
    "Malware Analysis": [
        "clamav",
        "yara",
        "pev",
        "ssdeep",
        "inetsim",
        "radare2",
    ],
    "Privacy & Anonymity": [
        "tor",
        "torbrowser-launcher",
        "privoxy",
        "proxychains4",
        "macchanger",
        "bleachbit",
        "mat2",
        "keepassxc",
        "openvpn",
        "wireguard",
        "onionshare",
    ],
}

PROBLEMATIC_PACKAGES: Dict[str, Dict[str, Any]] = {
    "samhain": {
        "service": "samhain.service",
        "config_dirs": ["/etc/samhain", "/var/lib/samhain"],
        "force_remove": True,
    },
    "ettercap-graphical": {
        "service": "ettercap.service",
        "config_dirs": ["/etc/ettercap"],
        "force_remove": False,
    },
    "openvas": {
        "service": "openvas.service",
        "config_dirs": ["/etc/openvas"],
        "force_remove": False,
    },
}

# ----------------------------------------------------------------
# Create a Rich Console
# ----------------------------------------------------------------
console: Console = Console()


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def setup_logging(log_dir: Path, verbose: bool = False) -> logging.Logger:
    """
    Set up logging using RichHandler and file logging.

    Args:
        log_dir: Directory to store log files.
        verbose: Enable debug output if True.

    Returns:
        Configured logger.
    """
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
    """
    Create an ASCII art header with gradient styling using Pyfiglet and Nord colors.

    Returns:
        A Rich Panel containing the header.
    """
    compact_fonts = ["small", "slant", "digital", "chunky", "standard"]
    ascii_art = ""
    for font in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=80)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = "Unattended Security Tools Installer"

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
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 80 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    return Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(
    text: str,
    style: str = NordColors.FROST_2,
    prefix: str = "•",
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Print a styled message and log it if a logger is provided.
    """
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
    """
    Display a message inside a styled panel.
    """
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def cleanup(logger: Optional[logging.Logger] = None) -> None:
    """
    Cleanup temporary resources.
    """
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
    """
    Handle termination signals gracefully.
    """
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
    """
    Execute a system command and return its CompletedProcess.
    """
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
# System Setup Class
# ----------------------------------------------------------------
class SystemSetup:
    """Handles package management operations and service configuration."""

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
        """Return True if the script is running as root."""
        return os.geteuid() == 0

    def get_target_packages(self) -> List[str]:
        """
        Return the list of unique packages to install from all categories.
        """
        all_packages = {pkg for tools in SECURITY_TOOLS.values() for pkg in tools}
        return list(all_packages)

    def log_operation(
        self, message: str, level: str = "info", prefix: str = "•"
    ) -> None:
        """
        Log a message with the appropriate styling.
        """
        style_map = {
            "info": NordColors.FROST_2,
            "warning": NordColors.YELLOW,
            "error": NordColors.RED,
            "success": NordColors.GREEN,
        }
        print_message(
            message, style_map.get(level, NordColors.FROST_2), prefix, self.logger
        )

    def remove_problematic_package(self, package_name: str) -> bool:
        """
        Remove a problematic package if needed.
        """
        if self.simulate:
            self.log_operation(f"Simulating removal of {package_name}")
            return True

        pkg_info = PROBLEMATIC_PACKAGES.get(package_name)
        if not pkg_info:
            return True

        try:
            if pkg_info.get("service"):
                self.log_operation(
                    f"Stopping service {pkg_info['service']} for {package_name}..."
                )
                subprocess.run(
                    ["systemctl", "stop", pkg_info["service"]],
                    check=False,
                    stderr=subprocess.DEVNULL,
                )
            self.log_operation(f"Terminating processes for {package_name}...")
            subprocess.run(
                ["killall", "-9", package_name], check=False, stderr=subprocess.DEVNULL
            )
            self.log_operation(f"Removing package {package_name}...")
            commands = [
                ["apt-get", "remove", "-y", package_name],
                ["apt-get", "purge", "-y", package_name],
                ["dpkg", "--remove", "--force-all", package_name],
                ["dpkg", "--purge", "--force-all", package_name],
            ]
            for cmd in commands:
                try:
                    subprocess.run(cmd, check=False, stderr=subprocess.PIPE)
                except subprocess.SubprocessError:
                    continue
            if pkg_info.get("config_dirs"):
                for directory in pkg_info["config_dirs"]:
                    if Path(directory).exists():
                        self.log_operation(f"Removing directory {directory}...")
                        subprocess.run(["rm", "-rf", directory], check=False)
            # Optionally clean package status file if force_remove is True
            if pkg_info.get("force_remove"):
                status_file = "/var/lib/dpkg/status"
                temp_file = "/var/lib/dpkg/status.tmp"
                self.log_operation("Cleaning package status file...")
                with open(status_file, "r") as fin, open(temp_file, "w") as fout:
                    skip_block = False
                    for line in fin:
                        if line.startswith(f"Package: {package_name}"):
                            skip_block = True
                            continue
                        if skip_block and line.startswith("Package:"):
                            skip_block = False
                        if not skip_block:
                            fout.write(line)
                os.rename(temp_file, status_file)
            self.log_operation(
                f"Package {package_name} removed successfully", "success", "✓"
            )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error removing {package_name}: {e}")
            return False

    def cleanup_package_system(self) -> bool:
        """
        Clean up the package management system.
        """
        try:
            if self.simulate:
                self.log_operation("Simulating package system cleanup...", "warning")
                time.sleep(1)
                return True

            apt_conf_path = "/etc/apt/apt.conf.d/"
            invalid_files = glob.glob(f"{apt_conf_path}/*.bak.*")
            if invalid_files:
                self.log_operation(
                    f"Removing {len(invalid_files)} invalid backup files..."
                )
                for file in invalid_files:
                    try:
                        os.remove(file)
                    except OSError as e:
                        if self.logger:
                            self.logger.error(f"Failed to remove {file}: {e}")
            else:
                self.log_operation("No invalid backup files found")
            for package in PROBLEMATIC_PACKAGES:
                self.log_operation(f"Checking problematic package: {package}")
                self.remove_problematic_package(package)
            self.log_operation("Configuring pending package installations...")
            run_command(["dpkg", "--configure", "-a"], logger=self.logger)
            pkg_manager = "nala" if Path("/usr/bin/nala").exists() else "apt"
            self.log_operation(f"Cleaning package cache with {pkg_manager}...")
            run_command([pkg_manager, "clean"], logger=self.logger)
            self.log_operation(f"Removing unused packages with {pkg_manager}...")
            run_command([pkg_manager, "autoremove", "-y"], logger=self.logger)
            self.log_operation("Package system cleanup completed", "success", "✓")
            return True
        except subprocess.CalledProcessError as e:
            if self.logger:
                self.logger.error(f"Cleanup failed: {e}")
            return False

    def setup_package_manager(self) -> bool:
        """
        Set up and update the package manager.
        """
        try:
            if self.simulate:
                self.log_operation("Simulating package manager setup...", "warning")
                time.sleep(1)
                return True

            if not Path("/usr/bin/nala").exists():
                self.log_operation("Installing nala package manager...")
                run_command(["apt", "update"], logger=self.logger)
                run_command(["apt", "install", "nala", "-y"], logger=self.logger)
                self.log_operation("Nala installed successfully", "success", "✓")
            pkg_manager = "nala" if Path("/usr/bin/nala").exists() else "apt"
            self.log_operation(f"Updating package lists with {pkg_manager}...")
            run_command([pkg_manager, "update"], logger=self.logger)
            self.log_operation(f"Upgrading packages with {pkg_manager}...")
            run_command([pkg_manager, "upgrade", "-y"], logger=self.logger)
            self.log_operation("Package manager setup completed", "success", "✓")
            return True
        except subprocess.CalledProcessError as e:
            if self.logger:
                self.logger.error(f"Package manager setup failed: {e}")
            return False

    def install_packages(
        self, packages: List[str], progress_callback=None, skip_failed: bool = True
    ) -> Tuple[bool, List[str]]:
        """
        Install the provided list of packages.
        """
        try:
            if self.simulate:
                self.log_operation(
                    f"Simulating installation of {len(packages)} packages", "warning"
                )
                time.sleep(2)
                return True, []
            pkg_manager = "nala" if Path("/usr/bin/nala").exists() else "apt"
            install_cmd = [pkg_manager, "install", "-y", "--no-install-recommends"]
            env = os.environ.copy()
            env["DEBIAN_FRONTEND"] = "noninteractive"
            failed_packages = []
            chunk_size = 15
            for i in range(0, len(packages), chunk_size):
                chunk = packages[i : i + chunk_size]
                desc = f"Installing packages {i + 1}-{min(i + chunk_size, len(packages))} of {len(packages)}"
                if progress_callback:
                    progress_callback(desc, i, len(packages))
                else:
                    self.log_operation(desc)
                try:
                    run_command(install_cmd + chunk, env=env, logger=self.logger)
                    self.successful_packages.extend(chunk)
                except subprocess.CalledProcessError as e:
                    self.log_operation("Retrying individual packages...", "warning")
                    for package in chunk:
                        if package not in self.successful_packages:
                            try:
                                run_command(
                                    install_cmd + [package], env=env, logger=self.logger
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
        """
        Configure and enable installed services.
        """
        try:
            if self.simulate:
                self.log_operation("Simulating service configuration...", "warning")
                time.sleep(1)
                return True

            services_to_configure = {
                "ufw": {
                    "enable": True,
                    "commands": [
                        ["ufw", "default", "deny", "incoming"],
                        ["ufw", "default", "allow", "outgoing"],
                        ["ufw", "allow", "ssh"],
                        ["ufw", "--force", "enable"],
                    ],
                },
                "fail2ban": {"enable": True, "commands": []},
                "clamav-freshclam": {
                    "enable": True,
                    "commands": [
                        ["systemctl", "stop", "clamav-freshclam"],
                        ["freshclam"],
                    ],
                },
                "apparmor": {"enable": True, "commands": []},
                "auditd": {"enable": True, "commands": []},
            }
            for service, config in services_to_configure.items():
                if self._check_if_installed(service):
                    self.log_operation(f"Configuring {service}...")
                    for cmd in config.get("commands", []):
                        try:
                            run_command(cmd, check=False, logger=self.logger)
                        except Exception as e:
                            self.log_operation(
                                f"Command failed for {service}: {e}", "warning", "⚠"
                            )
                    if config.get("enable", False):
                        try:
                            self.log_operation(f"Enabling and starting {service}...")
                            run_command(
                                ["systemctl", "enable", service],
                                check=False,
                                logger=self.logger,
                            )
                            run_command(
                                ["systemctl", "restart", service],
                                check=False,
                                logger=self.logger,
                            )
                        except Exception as e:
                            self.log_operation(
                                f"Failed to enable/start {service}: {e}", "warning", "⚠"
                            )
                else:
                    if self.logger:
                        self.logger.debug(
                            f"{service} not installed; skipping configuration"
                        )
            self.log_operation("Service configuration completed", "success", "✓")
            return True
        except Exception as e:
            self.log_operation(f"Service configuration failed: {e}", "error", "✗")
            if self.logger:
                self.logger.exception("Service configuration failed")
            return False

    def _check_if_installed(self, package: str) -> bool:
        """
        Check if a package is installed via dpkg.
        """
        try:
            result = run_command(
                ["dpkg", "-l", package],
                check=False,
                capture_output=True,
                logger=self.logger,
            )
            return "ii" in result.stdout and package in result.stdout
        except Exception:
            return False

    def save_installation_report(self, report_dir: Path) -> str:
        """
        Save a JSON and human-readable installation report.
        """
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
# Main Application Function (Fully Automated)
# ----------------------------------------------------------------
def main() -> None:
    """
    Main function that runs all installation steps automatically without user interaction.
    """
    simulate = False
    verbose = False
    skip_failed = True
    selected_categories = None  # Install all categories
    report_dir = DEFAULT_REPORT_DIR
    log_dir = DEFAULT_LOG_DIR

    logger = setup_logging(log_dir, verbose)

    # Register signal and cleanup handlers
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, logger))
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, logger))
    atexit.register(lambda: cleanup(logger))

    if not SystemSetup.check_root():
        display_panel(
            "[bold]This script requires root privileges.[/]\nRun with sudo: [bold cyan]sudo python3 security_installer.py[/]",
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

    setup = SystemSetup(
        simulate=simulate,
        verbose=verbose,
        logger=logger,
    )

    # Display informational installation plan
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
            description=f"[{NordColors.FROST_2}]Cleaning package system",
            completed=0,
        )
        progress.update(
            sub_task,
            visible=True,
            completed=0,
            description=f"[{NordColors.FROST_2}]Cleaning package system",
        )
        if not setup.cleanup_package_system():
            print_message(
                "Package system cleanup failed; continuing as requested...",
                NordColors.YELLOW,
                "⚠",
                logger,
            )
        progress.update(main_task, completed=20)
        progress.update(sub_task, completed=100)

        # Step 2: Setup package manager
        progress.update(
            main_task,
            description=f"[{NordColors.FROST_2}]Setting up package manager",
            completed=20,
        )
        progress.update(
            sub_task,
            completed=0,
            description=f"[{NordColors.FROST_2}]Setting up package manager",
        )
        if not setup.setup_package_manager():
            print_message(
                "Package manager setup failed; continuing as requested...",
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

        # Step 4: Configure installed services
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
