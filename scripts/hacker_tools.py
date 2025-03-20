#!/usr/bin/env python3

import os
import sys
import time
import json
import signal
import shutil
import subprocess
import atexit
import platform
import re
from dataclasses import dataclass, field
from typing import List, Optional, Any, Tuple, Dict, Union, Set
from datetime import datetime
from enum import Enum, auto

if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)


def install_dependencies():
    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "requests"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER"))
    try:
        if os.geteuid() != 0:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user"] + required_packages)
        else:
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"] + required_packages)
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


def check_homebrew():
    if shutil.which("brew") is None:
        print("Homebrew is not installed. Please install Homebrew from https://brew.sh and rerun this script.")
        return False
    return True


try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn,
        TimeRemainingColumn, TransferSpeedColumn, MofNCompleteColumn
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from rich.box import ROUNDED, HEAVY
    from rich.style import Style
    from rich.align import Align
    from rich.live import Live
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

APP_NAME = "PenMac"
APP_SUBTITLE = "macOS Penetration Testing Toolkit"
VERSION = "1.0.0"
HOME_DIR = os.path.expanduser("~")
CONFIG_DIR = os.path.join(HOME_DIR, ".penmac")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LOG_FILE = os.path.join(CONFIG_DIR, "install_log.json")
DEFAULT_TIMEOUT = 600
PYTHON_BUILD_TIMEOUT = 3600

# Execution environment
BREW_CMD = shutil.which("brew") or "/opt/homebrew/bin/brew"
PIP_CMD = shutil.which("pip") or shutil.which("pip3") or "/usr/bin/pip3"
CURRENT_USER = os.environ.get("SUDO_USER", os.environ.get("USER"))


class ToolCategory(Enum):
    NETWORK = auto()
    WEB = auto()
    FORENSICS = auto()
    CRYPTO = auto()
    RECON = auto()
    EXPLOITATION = auto()
    UTILITIES = auto()
    PASSWORD = auto()
    MOBILE = auto()
    REVERSE = auto()


class InstallMethod(Enum):
    BREW = auto()
    BREW_CASK = auto()
    PIP = auto()
    GIT = auto()
    CURL = auto()
    CUSTOM = auto()


@dataclass
class Tool:
    name: str
    category: ToolCategory
    description: str
    install_methods: List[Tuple[InstallMethod, str]]
    dependencies: List[str] = field(default_factory=list)
    post_install: List[str] = field(default_factory=list)
    installed: bool = False
    alternative_names: List[str] = field(default_factory=list)
    homepage: str = ""
    mac_compatible: bool = True
    is_core: bool = False


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


@dataclass
class AppConfig:
    installed_tools: List[str] = field(default_factory=list)
    last_update: str = ""
    selected_categories: List[str] = field(default_factory=list)
    custom_brew_prefix: str = ""
    use_sudo: bool = False
    verbose_output: bool = False

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
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
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
            padding=(1, 2)
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


def log_installation_result(tool_name, success, method, message=""):
    try:
        ensure_config_directory()
        log_entry = {
            "tool": tool_name,
            "success": success,
            "method": method,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }

        log_data = []
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r") as f:
                    log_data = json.load(f)
            except json.JSONDecodeError:
                log_data = []

        log_data.append(log_entry)

        with open(LOG_FILE, "w") as f:
            json.dump(log_data, f, indent=2)
    except Exception as e:
        print_error(f"Failed to log installation result: {e}")


def run_command(
        cmd,
        shell=False,
        check=True,
        capture_output=True,
        timeout=DEFAULT_TIMEOUT,
        verbose=False,
        env=None,
        use_sudo=False,
        show_progress=True  # Add parameter to control progress display
):
    try:
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        if use_sudo and os.geteuid() != 0 and not cmd_str.startswith("sudo"):
            if isinstance(cmd, list):
                cmd = ["sudo"] + cmd
            else:
                cmd = f"sudo {cmd}"

        if verbose:
            print_step(f"Executing: {cmd_str}")

        # Avoid nested progress displays by skipping progress display when requested
        if show_progress:
            with Progress(
                    SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
                    TextColumn(f"[bold {NordColors.FROST_2}]Running command..."),
                    console=console
            ) as progress:
                task = progress.add_task("", total=None)
                result = subprocess.run(
                    cmd,
                    shell=shell,
                    check=check,
                    text=True,
                    capture_output=capture_output,
                    timeout=timeout,
                    env=env or os.environ.copy()
                )
        else:
            # Run without progress display to avoid conflicts
            result = subprocess.run(
                cmd,
                shell=shell,
                check=check,
                text=True,
                capture_output=capture_output,
                timeout=timeout,
                env=env or os.environ.copy()
            )

        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {cmd_str}")
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


def install_homebrew():
    if check_homebrew():
        print_success("Homebrew is already installed.")
        return True

    print_step("Installing Homebrew...")
    try:
        # Install Homebrew using the official method
        install_script = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        result = run_command(install_script, shell=True, check=False)

        if result.returncode != 0:
            print_error("Failed to install Homebrew. Please install it manually from https://brew.sh")
            return False

        # Update PATH for this session
        for path in ["/usr/local/bin", "/opt/homebrew/bin"]:
            if path not in os.environ["PATH"] and os.path.exists(path):
                os.environ["PATH"] = f"{path}:{os.environ['PATH']}"

        # Verify installation
        if shutil.which("brew") is None:
            print_error("Homebrew installed but 'brew' command not found in PATH.")
            print_warning("You may need to restart your terminal for the PATH changes to take effect.")
            return False

        print_success("Homebrew installed successfully.")
        return True
    except Exception as e:
        print_error(f"Failed to install Homebrew: {e}")
        return False


def update_homebrew():
    if not check_homebrew():
        print_error("Homebrew is not installed.")
        return False

    try:
        print_step("Updating Homebrew...")
        # Try to update Homebrew, but continue if it fails
        try:
            run_command([BREW_CMD, "update"], check=True)
            print_success("Homebrew updated successfully.")
        except subprocess.CalledProcessError:
            print_warning("Homebrew update failed. Continuing without update.")
        return True
    except Exception as e:
        print_warning(f"Failed to update Homebrew: {e}. Continuing without update.")
        return True  # Return True to continue with installation


def install_brew_package(tool_name, cask=False, verbose=False, use_sudo=False, show_progress=True):
    if not check_homebrew():
        print_error("Homebrew is not installed.")
        return False

    try:
        # Check if the package is already installed
        result = run_command(
            [BREW_CMD, "list", tool_name],
            check=False,
            verbose=verbose,
            show_progress=False  # Don't show progress for checks
        )

        if result.returncode == 0:
            print_success(f"{tool_name} is already installed via Homebrew.")
            return True

        # Install the package
        cmd = [BREW_CMD, "install"]
        if cask:
            cmd.append("--cask")
        cmd.append(tool_name)

        print_step(f"Installing {tool_name} via Homebrew{' (cask)' if cask else ''}...")

        # For GUI applications like Wireshark, use direct subprocess call to avoid live display issues
        if tool_name in ["wireshark", "burp-suite", "ghidra", "autopsy"]:
            result = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                check=False
            )
            if result.returncode == 0:
                print_success(f"{tool_name} installed successfully via Homebrew.")
                return True
            else:
                print_error(f"Failed to install {tool_name} via Homebrew.")
                if verbose:
                    if result.stdout:
                        console.print(f"[dim]Output: {result.stdout.strip()}[/dim]")
                    if result.stderr:
                        console.print(f"[bold {NordColors.RED}]Error: {result.stderr.strip()}[/]")
                return False
        else:
            # Normal installation with optional progress display
            result = run_command(cmd, check=False, verbose=verbose, use_sudo=use_sudo, show_progress=show_progress)

        if result.returncode == 0:
            print_success(f"{tool_name} installed successfully via Homebrew.")
            return True
        else:
            print_error(f"Failed to install {tool_name} via Homebrew.")
            if "No available formula" in result.stderr or "No casks found" in result.stderr:
                print_warning(f"Package {tool_name} not found in Homebrew. It may have been renamed or removed.")
            return False
    except Exception as e:
        print_error(f"Error installing {tool_name} via Homebrew: {e}")
        return False


def install_pip_package(tool_name, verbose=False, use_sudo=False):
    try:
        # Check if pip is available
        pip_cmd = PIP_CMD
        if not pip_cmd:
            print_error("pip command not found.")
            return False

        print_step(f"Installing {tool_name} via pip...")
        cmd = [pip_cmd, "install", "--upgrade", tool_name]

        result = run_command(cmd, check=False, verbose=verbose, use_sudo=use_sudo)

        if result.returncode == 0:
            print_success(f"{tool_name} installed successfully via pip.")
            return True
        else:
            print_error(f"Failed to install {tool_name} via pip.")
            return False
    except Exception as e:
        print_error(f"Error installing {tool_name} via pip: {e}")
        return False


def install_pipx_package(tool_name, verbose=False):
    try:
        # Check if pipx is available
        pipx_cmd = shutil.which("pipx")
        if not pipx_cmd:
            print_step("Installing pipx...")
            if install_brew_package("pipx", verbose=verbose):
                pipx_cmd = shutil.which("pipx")
                run_command([pipx_cmd, "ensurepath"], check=False, verbose=verbose)
            else:
                print_error("Failed to install pipx.")
                return False

        print_step(f"Installing {tool_name} via pipx...")
        result = run_command([pipx_cmd, "install", tool_name], check=False, verbose=verbose)

        if result.returncode == 0:
            print_success(f"{tool_name} installed successfully via pipx.")
            return True
        else:
            print_error(f"Failed to install {tool_name} via pipx.")
            return False
    except Exception as e:
        print_error(f"Error installing {tool_name} via pipx: {e}")
        return False


def install_git_repo(repo_url, tool_name, install_cmd=None, verbose=False):
    try:
        # Check if git is available
        git_cmd = shutil.which("git")
        if not git_cmd:
            print_error("git command not found.")
            return False

        # Create a temp directory for cloning
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix=f"{tool_name}-")

        print_step(f"Cloning {tool_name} repository...")
        clone_result = run_command(
            [git_cmd, "clone", repo_url, temp_dir],
            check=False,
            verbose=verbose
        )

        if clone_result.returncode != 0:
            print_error(f"Failed to clone {tool_name} repository.")
            return False

        if install_cmd:
            print_step(f"Running install command for {tool_name}...")
            os.chdir(temp_dir)
            if isinstance(install_cmd, list):
                for cmd in install_cmd:
                    result = run_command(cmd, shell=True, check=False, verbose=verbose)
                    if result.returncode != 0:
                        print_error(f"Install command failed: {cmd}")
                        return False
            else:
                result = run_command(install_cmd, shell=True, check=False, verbose=verbose)
                if result.returncode != 0:
                    print_error(f"Install command failed: {install_cmd}")
                    return False

        print_success(f"{tool_name} installed successfully via git.")
        return True
    except Exception as e:
        print_error(f"Error installing {tool_name} via git: {e}")
        return False
    finally:
        # Clean up
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


def install_tool(tool, verbose=False, use_sudo=False, show_progress=True):
    print_step(f"Installing {tool.name}...")

    if tool.installed:
        print_success(f"{tool.name} is already installed.")
        return True

    # Install dependencies first
    for dep in tool.dependencies:
        print_step(f"Installing dependency: {dep}")
        install_brew_package(dep, verbose=verbose, use_sudo=use_sudo, show_progress=False)

    success = False

    # Try each installation method in order
    for method, param in tool.install_methods:
        try:
            if method == InstallMethod.BREW:
                if install_brew_package(param, verbose=verbose, use_sudo=use_sudo, show_progress=show_progress):
                    success = True
                    break
            elif method == InstallMethod.BREW_CASK:
                if install_brew_package(param, cask=True, verbose=verbose, use_sudo=use_sudo,
                                        show_progress=show_progress):
                    success = True
                    break
            elif method == InstallMethod.PIP:
                if install_pip_package(param, verbose=verbose, use_sudo=use_sudo):
                    success = True
                    break
            elif method == InstallMethod.GIT:
                install_cmd = None
                if isinstance(param, tuple) and len(param) == 2:
                    repo_url, install_cmd = param
                else:
                    repo_url = param
                if install_git_repo(repo_url, tool.name, install_cmd, verbose=verbose):
                    success = True
                    break
            elif method == InstallMethod.CUSTOM:
                print_step(f"Running custom installation for {tool.name}...")
                result = run_command(param, shell=True, check=False, verbose=verbose, use_sudo=use_sudo,
                                     show_progress=show_progress)
                if result.returncode == 0:
                    success = True
                    break
        except Exception as e:
            print_warning(f"Installation method failed: {method.name}. Error: {e}")
            continue

    if success:
        # Run post-installation commands
        for cmd in tool.post_install:
            try:
                print_step(f"Running post-installation command for {tool.name}...")
                run_command(cmd, shell=True, check=False, verbose=verbose, use_sudo=use_sudo)
            except Exception as e:
                print_warning(f"Post-installation command failed: {e}")

        print_success(f"{tool.name} installed successfully.")
        tool.installed = True
        log_installation_result(tool.name, True, method.name)

        # Update config
        config = AppConfig.load()
        if tool.name not in config.installed_tools:
            config.installed_tools.append(tool.name)
            config.save()

        return True
    else:
        print_error(f"Failed to install {tool.name} after trying all installation methods.")
        log_installation_result(tool.name, False, "ALL", "All installation methods failed")
        return False


def get_tool_list():
    """Define and return a list of tools for penetration testing on macOS."""
    tools = [
        # NETWORK TOOLS
        Tool(
            name="nmap",
            category=ToolCategory.NETWORK,
            description="Network mapper and port scanner",
            install_methods=[
                (InstallMethod.BREW, "nmap"),
            ],
            homepage="https://nmap.org",
            is_core=True
        ),
        Tool(
            name="wireshark",
            category=ToolCategory.NETWORK,
            description="Network protocol analyzer",
            install_methods=[
                (InstallMethod.CUSTOM, "brew install --cask wireshark"),
                (InstallMethod.BREW_CASK, "wireshark"),
            ],
            post_install=[
                "echo 'Wireshark installed. You may need to run it from Applications folder.'",
            ],
            homepage="https://www.wireshark.org"
        ),
        Tool(
            name="netcat",
            category=ToolCategory.NETWORK,
            description="Network utility for reading/writing network connections",
            install_methods=[
                (InstallMethod.BREW, "netcat"),
            ],
            homepage="https://nc110.sourceforge.io/"
        ),
        Tool(
            name="masscan",
            category=ToolCategory.NETWORK,
            description="TCP port scanner, faster than nmap",
            install_methods=[
                (InstallMethod.BREW, "masscan"),
            ],
            homepage="https://github.com/robertdavidgraham/masscan"
        ),
        Tool(
            name="bettercap",
            category=ToolCategory.NETWORK,
            description="Network attack and monitoring framework",
            install_methods=[
                (InstallMethod.BREW, "bettercap"),
            ],
            homepage="https://www.bettercap.org/"
        ),
        Tool(
            name="aircrack-ng",
            category=ToolCategory.NETWORK,
            description="WiFi security auditing tools suite",
            install_methods=[
                (InstallMethod.BREW, "aircrack-ng"),
            ],
            homepage="https://www.aircrack-ng.org/"
        ),
        Tool(
            name="tcpdump",
            category=ToolCategory.NETWORK,
            description="Command-line packet analyzer",
            install_methods=[
                (InstallMethod.BREW, "tcpdump"),
            ],
            homepage="https://www.tcpdump.org/"
        ),
        Tool(
            name="kismet",
            category=ToolCategory.NETWORK,
            description="Wireless network detector and sniffer",
            install_methods=[
                (InstallMethod.BREW, "kismet"),
            ],
            homepage="https://www.kismetwireless.net/"
        ),
        Tool(
            name="mitmproxy",
            category=ToolCategory.WEB,
            description="Interactive HTTPS proxy",
            install_methods=[
                (InstallMethod.BREW, "mitmproxy"),
                (InstallMethod.PIP, "mitmproxy"),
            ],
            homepage="https://mitmproxy.org/"
        ),

        # WEB TOOLS
        Tool(
            name="burpsuite",
            category=ToolCategory.WEB,
            description="Web vulnerability scanner and proxy",
            install_methods=[
                (InstallMethod.BREW_CASK, "burp-suite"),
            ],
            homepage="https://portswigger.net/burp"
        ),
        Tool(
            name="sqlmap",
            category=ToolCategory.WEB,
            description="Automatic SQL injection tool",
            install_methods=[
                (InstallMethod.BREW, "sqlmap"),
                (InstallMethod.PIP, "sqlmap"),
            ],
            homepage="https://sqlmap.org/"
        ),
        Tool(
            name="owasp-zap",
            category=ToolCategory.WEB,
            description="Open Web Application Security Project Zed Attack Proxy",
            install_methods=[
                (InstallMethod.BREW_CASK, "zap"),
            ],
            homepage="https://www.zaproxy.org/"
        ),
        Tool(
            name="wpscan",
            category=ToolCategory.WEB,
            description="WordPress security scanner",
            install_methods=[
                (InstallMethod.BREW, "wpscan"),
            ],
            homepage="https://wpscan.org/"
        ),
        Tool(
            name="nikto",
            category=ToolCategory.WEB,
            description="Web server scanner",
            install_methods=[
                (InstallMethod.BREW, "nikto"),
            ],
            homepage="https://cirt.net/Nikto2"
        ),
        Tool(
            name="ffuf",
            category=ToolCategory.WEB,
            description="Fast web fuzzer",
            install_methods=[
                (InstallMethod.BREW, "ffuf"),
            ],
            homepage="https://github.com/ffuf/ffuf"
        ),
        Tool(
            name="gobuster",
            category=ToolCategory.WEB,
            description="Directory/file & DNS busting tool",
            install_methods=[
                (InstallMethod.BREW, "gobuster"),
            ],
            homepage="https://github.com/OJ/gobuster"
        ),

        # FORENSIC TOOLS
        Tool(
            name="autopsy",
            category=ToolCategory.FORENSICS,
            description="Digital forensics platform",
            install_methods=[
                (InstallMethod.BREW_CASK, "autopsy"),
            ],
            homepage="https://www.sleuthkit.org/autopsy/"
        ),
        Tool(
            name="volatility",
            category=ToolCategory.FORENSICS,
            description="Memory forensics framework",
            install_methods=[
                (InstallMethod.PIP, "volatility3"),
            ],
            homepage="https://www.volatilityfoundation.org/"
        ),
        Tool(
            name="sleuthkit",
            category=ToolCategory.FORENSICS,
            description="Library and collection of command line tools for digital forensics",
            install_methods=[
                (InstallMethod.BREW, "sleuthkit"),
            ],
            homepage="https://www.sleuthkit.org/sleuthkit/"
        ),
        Tool(
            name="binwalk",
            category=ToolCategory.FORENSICS,
            description="Firmware analysis tool",
            install_methods=[
                (InstallMethod.BREW, "binwalk"),
                (InstallMethod.PIP, "binwalk"),
            ],
            homepage="https://github.com/ReFirmLabs/binwalk"
        ),
        Tool(
            name="foremost",
            category=ToolCategory.FORENSICS,
            description="File carving tool",
            install_methods=[
                (InstallMethod.BREW, "foremost"),
            ],
            homepage="http://foremost.sourceforge.net/"
        ),
        Tool(
            name="scalpel",
            category=ToolCategory.FORENSICS,
            description="Fast file carver",
            install_methods=[
                (InstallMethod.BREW, "scalpel"),
            ],
            homepage="https://github.com/sleuthkit/scalpel"
        ),

        # CRYPTO TOOLS
        Tool(
            name="hashcat",
            category=ToolCategory.CRYPTO,
            description="Advanced password recovery utility",
            install_methods=[
                (InstallMethod.BREW, "hashcat"),
            ],
            homepage="https://hashcat.net/"
        ),
        Tool(
            name="john",
            category=ToolCategory.CRYPTO,
            description="John the Ripper password cracker",
            install_methods=[
                (InstallMethod.BREW, "john-jumbo"),
            ],
            homepage="https://www.openwall.com/john/"
        ),
        Tool(
            name="openssl",
            category=ToolCategory.CRYPTO,
            description="SSL/TLS toolkit",
            install_methods=[
                (InstallMethod.BREW, "openssl"),
            ],
            homepage="https://www.openssl.org/"
        ),
        Tool(
            name="sslscan",
            category=ToolCategory.CRYPTO,
            description="SSL/TLS scanner",
            install_methods=[
                (InstallMethod.BREW, "sslscan"),
            ],
            homepage="https://github.com/rbsec/sslscan"
        ),

        # RECONNAISSANCE TOOLS
        Tool(
            name="amass",
            category=ToolCategory.RECON,
            description="In-depth Attack Surface Mapping and Asset Discovery",
            install_methods=[
                (InstallMethod.BREW, "amass"),
            ],
            homepage="https://github.com/OWASP/Amass"
        ),
        Tool(
            name="subfinder",
            category=ToolCategory.RECON,
            description="Subdomain discovery tool",
            install_methods=[
                (InstallMethod.BREW, "subfinder"),
            ],
            homepage="https://github.com/projectdiscovery/subfinder"
        ),
        Tool(
            name="nuclei",
            category=ToolCategory.RECON,
            description="Template-based vulnerability scanner",
            install_methods=[
                (InstallMethod.BREW, "nuclei"),
            ],
            homepage="https://github.com/projectdiscovery/nuclei"
        ),
        Tool(
            name="theharvester",
            category=ToolCategory.RECON,
            description="E-mail, subdomain and name harvester",
            install_methods=[
                (InstallMethod.BREW, "theharvester"),
                (InstallMethod.PIP, "theharvester"),
            ],
            homepage="https://github.com/laramies/theHarvester"
        ),
        Tool(
            name="osquery",
            category=ToolCategory.RECON,
            description="SQL powered operating system instrumentation and analytics",
            install_methods=[
                (InstallMethod.BREW, "osquery"),
            ],
            homepage="https://osquery.io/"
        ),
        Tool(
            name="spiderfoot",
            category=ToolCategory.RECON,
            description="Advanced OSINT framework",
            install_methods=[
                (InstallMethod.PIP, "spiderfoot"),
                (InstallMethod.GIT, "https://github.com/smicallef/spiderfoot.git"),
            ],
            homepage="https://www.spiderfoot.net/"
        ),

        # EXPLOITATION TOOLS
        Tool(
            name="metasploit",
            category=ToolCategory.EXPLOITATION,
            description="Penetration testing framework",
            install_methods=[
                (InstallMethod.BREW, "metasploit"),
            ],
            homepage="https://www.metasploit.com/"
        ),
        Tool(
            name="commix",
            category=ToolCategory.EXPLOITATION,
            description="Command injection exploiter",
            install_methods=[
                (InstallMethod.GIT, "https://github.com/commixproject/commix.git"),
            ],
            homepage="https://github.com/commixproject/commix"
        ),
        Tool(
            name="hydra",
            category=ToolCategory.EXPLOITATION,
            description="Login brute-force tool",
            install_methods=[
                (InstallMethod.BREW, "hydra"),
            ],
            homepage="https://github.com/vanhauser-thc/thc-hydra"
        ),

        # UTILITIES
        Tool(
            name="docker",
            category=ToolCategory.UTILITIES,
            description="Containerization platform",
            install_methods=[
                (InstallMethod.BREW_CASK, "docker"),
            ],
            homepage="https://www.docker.com/"
        ),
        Tool(
            name="git",
            category=ToolCategory.UTILITIES,
            description="Distributed version control system",
            install_methods=[
                (InstallMethod.BREW, "git"),
            ],
            homepage="https://git-scm.com/"
        ),
        Tool(
            name="python3",
            category=ToolCategory.UTILITIES,
            description="Python programming language",
            install_methods=[
                (InstallMethod.BREW, "python"),
            ],
            homepage="https://www.python.org/"
        ),
        Tool(
            name="go",
            category=ToolCategory.UTILITIES,
            description="Go programming language",
            install_methods=[
                (InstallMethod.BREW, "go"),
            ],
            homepage="https://golang.org/"
        ),
        Tool(
            name="rust",
            category=ToolCategory.UTILITIES,
            description="Rust programming language",
            install_methods=[
                (InstallMethod.BREW, "rust"),
            ],
            homepage="https://www.rust-lang.org/"
        ),
        Tool(
            name="tor",
            category=ToolCategory.UTILITIES,
            description="Onion router for anonymous communication",
            install_methods=[
                (InstallMethod.BREW, "tor"),
            ],
            homepage="https://www.torproject.org/"
        ),
        Tool(
            name="tor-browser",
            category=ToolCategory.UTILITIES,
            description="Web browser for accessing Tor network",
            install_methods=[
                (InstallMethod.BREW_CASK, "tor-browser"),
            ],
            homepage="https://www.torproject.org/download/"
        ),
        Tool(
            name="iterm2",
            category=ToolCategory.UTILITIES,
            description="Terminal emulator for macOS",
            install_methods=[
                (InstallMethod.BREW_CASK, "iterm2"),
            ],
            homepage="https://iterm2.com/"
        ),
        Tool(
            name="vim",
            category=ToolCategory.UTILITIES,
            description="Improved vi text editor",
            install_methods=[
                (InstallMethod.BREW, "vim"),
            ],
            homepage="https://www.vim.org/"
        ),

        # PASSWORD TOOLS
        Tool(
            name="cracklib",
            category=ToolCategory.PASSWORD,
            description="Password checking library",
            install_methods=[
                (InstallMethod.BREW, "cracklib"),
            ],
            homepage="https://github.com/cracklib/cracklib"
        ),
        Tool(
            name="pwgen",
            category=ToolCategory.PASSWORD,
            description="Password generator",
            install_methods=[
                (InstallMethod.BREW, "pwgen"),
            ],
            homepage="https://sourceforge.net/projects/pwgen/"
        ),
        Tool(
            name="1password-cli",
            category=ToolCategory.PASSWORD,
            description="1Password command line tool",
            install_methods=[
                (InstallMethod.BREW, "1password-cli"),
            ],
            homepage="https://1password.com/downloads/command-line/"
        ),

        # MOBILE TOOLS
        Tool(
            name="apktool",
            category=ToolCategory.MOBILE,
            description="Tool for reverse engineering Android apk files",
            install_methods=[
                (InstallMethod.BREW, "apktool"),
            ],
            homepage="https://ibotpeaches.github.io/Apktool/"
        ),
        Tool(
            name="jadx",
            category=ToolCategory.MOBILE,
            description="Dex to Java decompiler",
            install_methods=[
                (InstallMethod.BREW, "jadx"),
            ],
            homepage="https://github.com/skylot/jadx"
        ),
        Tool(
            name="adb",
            category=ToolCategory.MOBILE,
            description="Android Debug Bridge",
            install_methods=[
                (InstallMethod.BREW, "android-platform-tools"),
            ],
            homepage="https://developer.android.com/studio/command-line/adb"
        ),

        # REVERSE ENGINEERING TOOLS
        Tool(
            name="radare2",
            category=ToolCategory.REVERSE,
            description="Reverse engineering framework",
            install_methods=[
                (InstallMethod.BREW, "radare2"),
            ],
            homepage="https://rada.re/r/"
        ),
        Tool(
            name="ghidra",
            category=ToolCategory.REVERSE,
            description="Software reverse engineering framework",
            install_methods=[
                (InstallMethod.BREW_CASK, "ghidra"),
            ],
            homepage="https://ghidra-sre.org/"
        ),
        Tool(
            name="gdb",
            category=ToolCategory.REVERSE,
            description="GNU Debugger",
            install_methods=[
                (InstallMethod.BREW, "gdb"),
            ],
            homepage="https://www.gnu.org/software/gdb/"
        ),
        Tool(
            name="lldb",
            category=ToolCategory.REVERSE,
            description="LLVM debugger",
            install_methods=[
                (InstallMethod.BREW, "llvm"),
            ],
            post_install=["ln -s /usr/local/opt/llvm/bin/lldb /usr/local/bin/lldb 2>/dev/null || true"],
            homepage="https://lldb.llvm.org/"
        ),
        Tool(
            name="hopper",
            category=ToolCategory.REVERSE,
            description="Reverse engineering tool for macOS",
            install_methods=[
                (InstallMethod.BREW_CASK, "hopper-disassembler"),
            ],
            homepage="https://www.hopperapp.com/"
        ),
    ]

    return tools


def get_category_tools(tools, category):
    """Return tools that belong to the specified category."""
    return [tool for tool in tools if tool.category == category]


def cleanup():
    try:
        config = AppConfig.load()
        config.last_update = datetime.now().isoformat()
        config.save()
        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


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


def show_tool_details(tool_name, tools):
    """Show detailed information about a specific tool."""
    clear_screen()
    console.print(create_header())

    tool = next((t for t in tools if t.name.lower() == tool_name.lower()), None)
    if not tool:
        print_error(f"Tool '{tool_name}' not found.")
        Prompt.ask("Press Enter to return to the main menu")
        return

    details = [
        f"Name: [bold]{tool.name}[/]",
        f"Category: [bold]{tool.category.name}[/]",
        f"Description: {tool.description}",
        f"Homepage: [link={tool.homepage}]{tool.homepage}[/link]",
        f"Installation Methods: {', '.join([method.name for method, _ in tool.install_methods])}",
        f"Status: {'[green]Installed[/]' if tool.installed else '[yellow]Not installed[/]'}"
    ]

    if tool.dependencies:
        details.append(f"Dependencies: {', '.join(tool.dependencies)}")

    if tool.alternative_names:
        details.append(f"Alternative Names: {', '.join(tool.alternative_names)}")

    display_panel(
        f"Tool Details: {tool.name}",
        "\n".join(details),
        NordColors.FROST_2
    )

    options = [
        ("1", f"{'Reinstall' if tool.installed else 'Install'} {tool.name}",
         f"{'Reinstall' if tool.installed else 'Install'} this tool"),
        ("2", "Return to Tool List", "Go back to the tool list")
    ]

    console.print(create_menu_table("Options", options))
    choice = Prompt.ask("Select option", choices=["1", "2"], default="2")

    if choice == "1":
        verbose = Confirm.ask("Enable verbose output?", default=False)
        use_sudo = Confirm.ask("Use sudo for installation?", default=False)
        install_tool(tool, verbose=verbose, use_sudo=use_sudo)
        Prompt.ask("Press Enter to continue")


def show_tools_by_category(category, tools):
    """Show and allow installation of tools in a specific category."""
    clear_screen()
    console.print(create_header())

    category_tools = get_category_tools(tools, category)

    if not category_tools:
        print_warning(f"No tools found in category: {category.name}")
        Prompt.ask("Press Enter to return to the main menu")
        return

    display_panel(
        f"{category.name} Tools",
        f"There are {len(category_tools)} tools in this category.",
        NordColors.FROST_2
    )

    tool_table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        border_style=NordColors.FROST_3,
        padding=(0, 1),
        expand=True,
    )

    tool_table.add_column("#", style=NordColors.ACCENT, width=3, justify="right")
    tool_table.add_column("Name", style=NordColors.FROST_1)
    tool_table.add_column("Description", style=NordColors.SNOW_STORM_1)
    tool_table.add_column("Status", style=NordColors.FROST_3)

    for i, tool in enumerate(category_tools, 1):
        status = "[green]Installed[/]" if tool.installed else "[yellow]Not installed[/]"
        tool_table.add_row(str(i), tool.name, tool.description, status)

    console.print(tool_table)

    options = [
        ("I", "Install All", f"Install all {category.name} tools"),
        ("S", "Install Selected", "Install specific tools"),
        ("D", "Tool Details", "View details of a specific tool"),
        ("B", "Back", "Return to category list")
    ]

    console.print(create_menu_table("Options", options))
    choice = Prompt.ask("Select option", choices=["I", "S", "D", "B"], default="B")

    if choice == "I":
        verbose = Confirm.ask("Enable verbose output?", default=False)
        use_sudo = Confirm.ask("Use sudo for installation if needed?", default=False)

        # Use the helper function to install all tools in this category
        installed_count = install_multiple_tools(category_tools, verbose=verbose, use_sudo=use_sudo)

        print_success(
            f"Completed installation of {installed_count} out of {len(category_tools)} {category.name} tools.")
        Prompt.ask("Press Enter to continue")

    elif choice == "S":
        tool_nums = Prompt.ask(
            "Enter tool numbers to install (comma-separated, e.g., 1,3,5)",
            default="",
        )

        if tool_nums:
            tool_nums = [int(num.strip()) for num in tool_nums.split(",") if num.strip().isdigit()]
            selected_tools = [category_tools[num - 1] for num in tool_nums if 1 <= num <= len(category_tools)]

            if not selected_tools:
                print_warning("No valid tools selected.")
                Prompt.ask("Press Enter to continue")
                return

            verbose = Confirm.ask("Enable verbose output?", default=False)
            use_sudo = Confirm.ask("Use sudo for installation if needed?", default=False)

            # Use the helper function to install selected tools
            installed_count = install_multiple_tools(selected_tools, verbose=verbose, use_sudo=use_sudo)

            print_success(f"Completed installation of {installed_count} out of {len(selected_tools)} selected tools.")
            Prompt.ask("Press Enter to continue")

    elif choice == "D":
        tool_num = Prompt.ask(
            "Enter tool number to view details",
            default="1",
        )

        try:
            tool_num = int(tool_num)
            if 1 <= tool_num <= len(category_tools):
                show_tool_details(category_tools[tool_num - 1].name, tools)
            else:
                print_warning(f"Invalid tool number: {tool_num}")
                Prompt.ask("Press Enter to continue")
        except ValueError:
            print_warning(f"Invalid tool number: {tool_num}")
            Prompt.ask("Press Enter to continue")


def category_menu(tools):
    """Show and navigate categories of penetration testing tools."""
    while True:
        clear_screen()
        console.print(create_header())

        display_panel(
            "Tool Categories",
            "Choose a category to browse and install tools.",
            NordColors.FROST_2
        )

        categories = sorted([(cat, cat.name, sum(1 for t in tools if t.category == cat))
                             for cat in set(t.category for t in tools)],
                            key=lambda x: x[1])

        options = []
        for i, (cat, name, count) in enumerate(categories, 1):
            options.append((str(i), name, f"{count} tools"))

        options.append(("A", "All Tools", f"{len(tools)} tools"))
        options.append(("C", "Core Tools", f"{sum(1 for t in tools if t.is_core)} essential tools"))
        options.append(("S", "Search", "Search for specific tools"))
        options.append(("B", "Back", "Return to main menu"))

        console.print(create_menu_table("Categories", options))

        choice = Prompt.ask(
            "Select category",
            choices=[opt[0] for opt in options],
            default="B"
        )

        if choice == "B":
            break
        elif choice == "A":
            show_all_tools(tools)
        elif choice == "C":
            show_core_tools(tools)
        elif choice == "S":
            search_tools(tools)
        else:
            try:
                category = categories[int(choice) - 1][0]
                show_tools_by_category(category, tools)
            except (ValueError, IndexError):
                print_error("Invalid selection.")
                Prompt.ask("Press Enter to continue")


def install_multiple_tools(tools_to_install, verbose=False, use_sudo=False):
    """Helper function to install multiple tools with proper handling of progress displays."""
    installed_count = 0

    # First, handle all non-GUI tools with a single progress bar
    regular_tools = [t for t in tools_to_install if
                     t.name not in ["wireshark", "burp-suite", "ghidra", "autopsy", "hopper-disassembler", "zap"]]
    gui_tools = [t for t in tools_to_install if
                 t.name in ["wireshark", "burp-suite", "ghidra", "autopsy", "hopper-disassembler", "zap"]]

    if regular_tools:
        with Progress(*NordColors.get_progress_columns(), console=console) as progress:
            install_task = progress.add_task("Installing tools", total=len(regular_tools))

            for tool in regular_tools:
                progress.update(install_task, description=f"Installing {tool.name}...")
                # Install without inner progress displays
                if install_tool(tool, verbose=verbose, use_sudo=use_sudo, show_progress=False):
                    installed_count += 1
                progress.advance(install_task)

    # Handle GUI tools separately, one by one
    if gui_tools:
        print_step(f"Installing {len(gui_tools)} GUI applications (these require special handling)...")
        for tool in gui_tools:
            print_step(f"Installing {tool.name}...")
            # Allow progress display for GUI tools when installed individually
            if install_tool(tool, verbose=verbose, use_sudo=use_sudo):
                installed_count += 1
            # Add a small delay between installations
            time.sleep(1)

    return installed_count


def show_all_tools(tools):
    """Show and allow installation of all available tools."""
    clear_screen()
    console.print(create_header())

    display_panel(
        "All Tools",
        f"There are {len(tools)} tools available for macOS.",
        NordColors.FROST_2
    )

    # Group tools by category
    tools_by_category = {}
    for tool in tools:
        if tool.category not in tools_by_category:
            tools_by_category[tool.category] = []
        tools_by_category[tool.category].append(tool)

    # Sort categories by name
    sorted_categories = sorted(tools_by_category.keys(), key=lambda c: c.name)

    for category in sorted_categories:
        category_tools = tools_by_category[category]

        category_table = Table(
            show_header=True,
            header_style=NordColors.HEADER,
            box=ROUNDED,
            border_style=NordColors.FROST_3,
            title=f"[bold {NordColors.FROST_1}]{category.name} Tools[/]",
            padding=(0, 1),
            expand=True,
        )

        category_table.add_column("Name", style=NordColors.FROST_1)
        category_table.add_column("Description", style=NordColors.SNOW_STORM_1)
        category_table.add_column("Status", style=NordColors.FROST_3, width=12)

        for tool in sorted(category_tools, key=lambda t: t.name):
            status = "[green]Installed[/]" if tool.installed else "[yellow]Not installed[/]"
            category_table.add_row(tool.name, tool.description, status)

        console.print(category_table)
        console.print("\n")

    options = [
        ("I", "Install All", "Install all available tools"),
        ("C", "Install by Category", "Install tools by category"),
        ("S", "Search", "Search for specific tools"),
        ("B", "Back", "Return to category menu")
    ]

    console.print(create_menu_table("Options", options))
    choice = Prompt.ask("Select option", choices=["I", "C", "S", "B"], default="B")

    if choice == "I":
        if Confirm.ask("This will install all available tools. This may take a long time. Continue?", default=False):
            verbose = Confirm.ask("Enable verbose output?", default=False)
            use_sudo = Confirm.ask("Use sudo for installation if needed?", default=False)

            # Use the helper function to install all tools
            installed_count = install_multiple_tools(tools, verbose=verbose, use_sudo=use_sudo)

            print_success(f"Completed installation of {installed_count} out of {len(tools)} tools.")
            Prompt.ask("Press Enter to continue")
    elif choice == "C":
        category_menu(tools)
    elif choice == "S":
        search_tools(tools)


def show_core_tools(tools):
    """Show and allow installation of core/essential tools."""
    clear_screen()
    console.print(create_header())

    core_tools = [tool for tool in tools if tool.is_core]

    if not core_tools:
        print_warning("No core tools defined.")
        Prompt.ask("Press Enter to return to the category menu")
        return

    display_panel(
        "Core Tools",
        f"There are {len(core_tools)} essential tools for penetration testing.",
        NordColors.FROST_2
    )

    tool_table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        border_style=NordColors.FROST_3,
        padding=(0, 1),
        expand=True,
    )

    tool_table.add_column("#", style=NordColors.ACCENT, width=3, justify="right")
    tool_table.add_column("Name", style=NordColors.FROST_1)
    tool_table.add_column("Category", style=NordColors.FROST_3)
    tool_table.add_column("Description", style=NordColors.SNOW_STORM_1)
    tool_table.add_column("Status", style=NordColors.FROST_3)

    for i, tool in enumerate(sorted(core_tools, key=lambda t: t.name), 1):
        status = "[green]Installed[/]" if tool.installed else "[yellow]Not installed[/]"
        tool_table.add_row(str(i), tool.name, tool.category.name, tool.description, status)

    console.print(tool_table)

    options = [
        ("I", "Install All Core Tools", "Install all essential tools"),
        ("S", "Install Selected", "Install specific tools"),
        ("B", "Back", "Return to category menu")
    ]

    console.print(create_menu_table("Options", options))
    choice = Prompt.ask("Select option", choices=["I", "S", "B"], default="B")

    if choice == "I":
        verbose = Confirm.ask("Enable verbose output?", default=False)
        use_sudo = Confirm.ask("Use sudo for installation if needed?", default=False)

        # Use the helper function to install core tools
        installed_count = install_multiple_tools(core_tools, verbose=verbose, use_sudo=use_sudo)

        print_success(f"Completed installation of {installed_count} out of {len(core_tools)} core tools.")
        Prompt.ask("Press Enter to continue")

    elif choice == "S":
        tool_nums = Prompt.ask(
            "Enter tool numbers to install (comma-separated, e.g., 1,3,5)",
            default="",
        )

        if tool_nums:
            tool_nums = [int(num.strip()) for num in tool_nums.split(",") if num.strip().isdigit()]
            selected_tools = [core_tools[num - 1] for num in tool_nums if 1 <= num <= len(core_tools)]

            if not selected_tools:
                print_warning("No valid tools selected.")
                Prompt.ask("Press Enter to continue")
                return

            verbose = Confirm.ask("Enable verbose output?", default=False)
            use_sudo = Confirm.ask("Use sudo for installation if needed?", default=False)

            # Use the helper function to install selected tools
            installed_count = install_multiple_tools(selected_tools, verbose=verbose, use_sudo=use_sudo)

            print_success(f"Completed installation of {installed_count} out of {len(selected_tools)} selected tools.")
            Prompt.ask("Press Enter to continue")


def search_tools(tools):
    """Search for tools by name or description."""
    clear_screen()
    console.print(create_header())

    display_panel(
        "Search Tools",
        "Search for tools by name or description.",
        NordColors.FROST_2
    )

    search_term = Prompt.ask("Enter search term").lower()

    if not search_term:
        print_warning("No search term provided.")
        Prompt.ask("Press Enter to return to the category menu")
        return

    matching_tools = [
        tool for tool in tools
        if search_term in tool.name.lower() or
           search_term in tool.description.lower() or
           any(search_term in alt.lower() for alt in tool.alternative_names)
    ]

    if not matching_tools:
        print_warning(f"No tools found matching '{search_term}'.")
        Prompt.ask("Press Enter to return to the category menu")
        return

    display_panel(
        "Search Results",
        f"Found {len(matching_tools)} tools matching '{search_term}'.",
        NordColors.FROST_2
    )

    tool_table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        border_style=NordColors.FROST_3,
        padding=(0, 1),
        expand=True,
    )

    tool_table.add_column("#", style=NordColors.ACCENT, width=3, justify="right")
    tool_table.add_column("Name", style=NordColors.FROST_1)
    tool_table.add_column("Category", style=NordColors.FROST_3)
    tool_table.add_column("Description", style=NordColors.SNOW_STORM_1)
    tool_table.add_column("Status", style=NordColors.FROST_3)

    for i, tool in enumerate(matching_tools, 1):
        status = "[green]Installed[/]" if tool.installed else "[yellow]Not installed[/]"
        tool_table.add_row(str(i), tool.name, tool.category.name, tool.description, status)

    console.print(tool_table)

    options = [
        ("I", "Install All", f"Install all {len(matching_tools)} matching tools"),
        ("S", "Install Selected", "Install specific tools"),
        ("D", "Tool Details", "View details of a specific tool"),
        ("B", "Back", "Return to category menu")
    ]

    console.print(create_menu_table("Options", options))
    choice = Prompt.ask("Select option", choices=["I", "S", "D", "B"], default="B")

    if choice == "I":
        verbose = Confirm.ask("Enable verbose output?", default=False)
        use_sudo = Confirm.ask("Use sudo for installation if needed?", default=False)

        # Use the helper function to install matching tools
        installed_count = install_multiple_tools(matching_tools, verbose=verbose, use_sudo=use_sudo)

        print_success(f"Completed installation of {installed_count} out of {len(matching_tools)} matching tools.")
        Prompt.ask("Press Enter to continue")

    elif choice == "S":
        tool_nums = Prompt.ask(
            "Enter tool numbers to install (comma-separated, e.g., 1,3,5)",
            default="",
        )

        if tool_nums:
            tool_nums = [int(num.strip()) for num in tool_nums.split(",") if num.strip().isdigit()]
            selected_tools = [matching_tools[num - 1] for num in tool_nums if 1 <= num <= len(matching_tools)]

            if not selected_tools:
                print_warning("No valid tools selected.")
                Prompt.ask("Press Enter to continue")
                return

            verbose = Confirm.ask("Enable verbose output?", default=False)
            use_sudo = Confirm.ask("Use sudo for installation if needed?", default=False)

            # Use the helper function to install selected tools
            installed_count = install_multiple_tools(selected_tools, verbose=verbose, use_sudo=use_sudo)

            print_success(f"Completed installation of {installed_count} out of {len(selected_tools)} selected tools.")
            Prompt.ask("Press Enter to continue")

    elif choice == "D":
        tool_num = Prompt.ask(
            "Enter tool number to view details",
            default="1",
        )

        try:
            tool_num = int(tool_num)
            if 1 <= tool_num <= len(matching_tools):
                show_tool_details(matching_tools[tool_num - 1].name, tools)
            else:
                print_warning(f"Invalid tool number: {tool_num}")
                Prompt.ask("Press Enter to continue")
        except ValueError:
            print_warning(f"Invalid tool number: {tool_num}")
            Prompt.ask("Press Enter to continue")


def check_installed_tools(tools):
    """Check which tools are already installed on the system."""
    print_step("Checking installed tools...")

    with Progress(*NordColors.get_progress_columns(), console=console) as progress:
        check_task = progress.add_task("Checking installed tools", total=len(tools))

        for tool in tools:
            progress.update(check_task, description=f"Checking {tool.name}...")

            for method, param in tool.install_methods:
                try:
                    if method == InstallMethod.BREW or method == InstallMethod.BREW_CASK:
                        # Check if installed via Homebrew
                        result = run_command(
                            [BREW_CMD, "list", param],
                            check=False,
                            capture_output=True
                        )
                        if result.returncode == 0:
                            tool.installed = True
                            break
                    elif method == InstallMethod.PIP:
                        # Check if installed via pip
                        result = run_command(
                            [PIP_CMD, "show", param],
                            check=False,
                            capture_output=True
                        )
                        if result.returncode == 0:
                            tool.installed = True
                            break
                except Exception:
                    # Ignore errors during checks
                    pass

            # Check commands directly
            if not tool.installed and shutil.which(tool.name):
                tool.installed = True

            progress.advance(check_task)

    installed_count = sum(1 for tool in tools if tool.installed)
    print_success(f"Found {installed_count} tools already installed.")

    # Update config with installed tools
    config = AppConfig.load()
    config.installed_tools = [tool.name for tool in tools if tool.installed]
    config.save()


def setup_menu(tools):
    """Show basic setup menu for macOS penetration testing environment."""
    clear_screen()
    console.print(create_header())

    display_panel(
        "Basic Setup",
        "Set up your macOS for penetration testing with these basic steps.",
        NordColors.FROST_2
    )

    # Check if running as root/sudo
    if os.geteuid() == 0:
        display_panel(
            "Warning: Running as Root",
            "You are running this script as root. Some tools may install to root's home directory.",
            NordColors.WARNING
        )

    # Show system information
    table = Table(
        show_header=False,
        box=ROUNDED,
        border_style=NordColors.FROST_3,
        padding=(0, 2)
    )
    table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)
    table.add_row("Python Version", platform.python_version())
    table.add_row("Operating System", platform.platform())
    table.add_row("Running as", CURRENT_USER)
    table.add_row("Home Directory", HOME_DIR)
    table.add_row("Homebrew", "Installed" if check_homebrew() else "Not installed")

    console.print(
        Panel(
            table,
            title="[bold]System Information[/bold]",
            border_style=NordColors.FROST_1,
            padding=(1, 2),
        )
    )

    setup_steps = [
        ("1", "Install Homebrew", "Package manager for macOS", "Required"),
        ("2", "Install Command Line Tools", "Xcode Command Line Tools", "Required"),
        ("3", "Install Core Tools", f"{sum(1 for t in tools if t.is_core)} essential pentesting tools", "Recommended"),
        ("4", "Return to Main Menu", "", "")
    ]

    console.print(create_menu_table("Setup Steps", setup_steps))
    choice = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="4")

    if choice == "1":
        if install_homebrew():
            print_success("Homebrew installed successfully.")
        else:
            print_error("Failed to install Homebrew.")
        Prompt.ask("Press Enter to continue")
        setup_menu(tools)

    elif choice == "2":
        print_step("Installing Xcode Command Line Tools...")

        try:
            result = run_command(
                ["xcode-select", "--install"],
                check=False,
                capture_output=True
            )

            if "already installed" in result.stderr:
                print_success("Xcode Command Line Tools are already installed.")
            elif result.returncode != 0:
                print_warning("Command line tool installation may have been initiated in a dialog box.")
                print_warning("Please complete the installation if prompted, then press Enter to continue.")
            else:
                print_success("Xcode Command Line Tools installation initiated.")
                print_warning(
                    "Please follow the on-screen dialog to complete installation, then press Enter to continue.")
        except Exception as e:
            print_error(f"Error installing Command Line Tools: {e}")

        Prompt.ask("Press Enter when Xcode Command Line Tools installation is complete")
        setup_menu(tools)

    elif choice == "3":
        show_core_tools(tools)
        setup_menu(tools)


def settings_menu():
    """Show and configure settings for the application."""
    clear_screen()
    console.print(create_header())

    config = AppConfig.load()

    display_panel(
        "Settings",
        "Configure application settings.",
        NordColors.FROST_2
    )

    # Format last update time
    last_update = "Never"
    if config.last_update:
        try:
            update_time = datetime.fromisoformat(config.last_update)
            last_update = update_time.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            last_update = "Invalid date"

    settings_table = Table(
        show_header=False,
        box=ROUNDED,
        border_style=NordColors.FROST_3,
        padding=(0, 2),
        expand=True,
    )

    settings_table.add_column("Setting", style=f"bold {NordColors.FROST_2}")
    settings_table.add_column("Value", style=NordColors.SNOW_STORM_1)

    settings_table.add_row("Last Update", last_update)
    settings_table.add_row("Use Sudo", "Yes" if config.use_sudo else "No")
    settings_table.add_row("Verbose Output", "Yes" if config.verbose_output else "No")
    settings_table.add_row("Installed Tools", str(len(config.installed_tools)))

    console.print(settings_table)

    options = [
        ("1", "Toggle Sudo", f"{'Disable' if config.use_sudo else 'Enable'} sudo for installations"),
        ("2", "Toggle Verbose Output", f"{'Disable' if config.verbose_output else 'Enable'} verbose output"),
        ("3", "View Installation Log", "View the tool installation log"),
        ("4", "Update Homebrew", "Update Homebrew and its formulae"),
        ("5", "Back", "Return to main menu")
    ]

    console.print(create_menu_table("Settings", options))
    choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "5"], default="5")

    if choice == "1":
        config.use_sudo = not config.use_sudo
        config.save()
        print_success(f"Sudo {'enabled' if config.use_sudo else 'disabled'} for installations.")
        Prompt.ask("Press Enter to continue")
        settings_menu()

    elif choice == "2":
        config.verbose_output = not config.verbose_output
        config.save()
        print_success(f"Verbose output {'enabled' if config.verbose_output else 'disabled'}.")
        Prompt.ask("Press Enter to continue")
        settings_menu()

    elif choice == "3":
        view_installation_log()
        settings_menu()

    elif choice == "4":
        update_homebrew()
        Prompt.ask("Press Enter to continue")
        settings_menu()


def view_installation_log():
    """View the tool installation log."""
    clear_screen()
    console.print(create_header())

    if not os.path.exists(LOG_FILE):
        display_panel(
            "Installation Log",
            "No installation log found.",
            NordColors.FROST_2
        )
        Prompt.ask("Press Enter to return to settings menu")
        return

    try:
        with open(LOG_FILE, "r") as f:
            log_data = json.load(f)

        if not log_data:
            display_panel(
                "Installation Log",
                "Installation log is empty.",
                NordColors.FROST_2
            )
            Prompt.ask("Press Enter to return to settings menu")
            return

        log_table = Table(
            show_header=True,
            header_style=NordColors.HEADER,
            box=ROUNDED,
            border_style=NordColors.FROST_3,
            padding=(0, 1),
            expand=True,
        )

        log_table.add_column("Tool", style=NordColors.FROST_1)
        log_table.add_column("Status", style=NordColors.FROST_3)
        log_table.add_column("Method", style=NordColors.FROST_2)
        log_table.add_column("Timestamp", style=NordColors.SNOW_STORM_1)
        log_table.add_column("Message", style=NordColors.SNOW_STORM_1)

        for entry in log_data[:20]:  # Show only the most recent 20 entries
            status = "[green]Success[/]" if entry.get("success") else "[red]Failure[/]"
            timestamp = datetime.fromisoformat(entry.get("timestamp", "")).strftime("%Y-%m-%d %H:%M:%S")

            log_table.add_row(
                entry.get("tool", "Unknown"),
                status,
                entry.get("method", "Unknown"),
                timestamp,
                entry.get("message", "")
            )

        display_panel(
            "Installation Log",
            f"Showing the most recent {min(20, len(log_data))} installation events.",
            NordColors.FROST_2
        )

        console.print(log_table)

        options = [
            ("1", "Clear Log", "Clear the installation log"),
            ("2", "Back", "Return to settings menu")
        ]

        console.print(create_menu_table("Options", options))
        choice = Prompt.ask("Select option", choices=["1", "2"], default="2")

        if choice == "1":
            if Confirm.ask("Are you sure you want to clear the installation log?", default=False):
                with open(LOG_FILE, "w") as f:
                    json.dump([], f)
                print_success("Installation log cleared.")
                Prompt.ask("Press Enter to continue")
    except Exception as e:
        print_error(f"Error reading installation log: {e}")
        Prompt.ask("Press Enter to return to settings menu")


def main_menu():
    """Show main menu and handle user input."""
    # Check if we're running on macOS
    if platform.system() != "Darwin":
        console.print("\n")
        console.print(create_header())
        print_error("This script is designed for macOS only. Exiting.")
        sys.exit(1)

    # Ensure config directory exists
    ensure_config_directory()

    # Get tool list
    tools = get_tool_list()

    # Check which tools are already installed
    check_installed_tools(tools)

    while True:
        clear_screen()
        console.print(create_header())

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hostname = platform.node()

        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {hostname}[/]"
            )
        )

        console.print("\n")

        installed_count = sum(1 for tool in tools if tool.installed)

        display_panel(
            "macOS Penetration Testing Toolkit",
            f"This toolkit helps you install and manage {len(tools)} penetration testing tools on macOS.\n"
            f"Currently {installed_count} tools are installed.",
            NordColors.FROST_2
        )

        main_options = [
            ("1", "Browse Tools", "Browse and install tools by category"),
            ("2", "Basic Setup", "Set up Homebrew and core requirements"),
            ("3", "Settings", "Configure application settings"),
            ("4", "Exit", "Exit the application")
        ]

        console.print(create_menu_table("Main Menu", main_options))

        choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4"], default="1")

        if choice == "1":
            category_menu(tools)
        elif choice == "2":
            setup_menu(tools)
        elif choice == "3":
            settings_menu()
        elif choice == "4":
            clear_screen()
            console.print(
                Panel(
                    Text.from_markup(
                        "[bold]Thank you for using PenMac![/]\n\n"
                        "Your macOS penetration testing toolkit is ready."
                    ),
                    title="Goodbye!",
                    title_align="center",
                    border_style=NordColors.FROST_2,
                    box=HEAVY,
                    padding=(2, 4)
                )
            )
            break


def main():
    try:
        clear_screen()
        console.print(create_header())

        with Progress(
                SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]Starting PenMac..."),
                console=console
        ) as progress:
            task = progress.add_task("", total=100)
            ensure_config_directory()
            progress.update(task, completed=30, description="Checking configuration...")
            progress.update(task, completed=60, description="Verifying environment...")
            progress.update(task, completed=90, description="Loading tools...")
            progress.update(task, completed=100, description="Ready!")
            time.sleep(0.5)

        main_menu()

    except KeyboardInterrupt:
        print_warning("Operation cancelled by user")

    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        if Confirm.ask("Show detailed error information?", default=False):
            console.print_exception(show_locals=True)
        print_step("The application will now exit.")

    finally:
        cleanup()


if __name__ == "__main__":
    main()