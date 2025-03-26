#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pytube.py: The MacOS YouTube Downloader v1.3.0
A command-line tool for downloading YouTube videos on macOS with quality options.
Improved file detection and error reporting.
"""

import os
import sys
import time
import json
import signal
import shutil
import subprocess
import atexit
import platform
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Union, Tuple
from datetime import datetime

# --- Platform Check ---
if platform.system() != "Darwin":
    print(
        "ERROR: This script is specifically designed for macOS. Exiting.",
        file=sys.stderr,
    )
    sys.exit(1)

# --- Dependency Management ---
_INSTALL_ATTEMPTED = False


def _install_dependencies():
    """Installs required Python packages using pip."""
    global _INSTALL_ATTEMPTED
    if _INSTALL_ATTEMPTED:
        print(
            "ERROR: Dependency installation already attempted without success. Exiting.",
            file=sys.stderr,
        )
        sys.exit(1)
    _INSTALL_ATTEMPTED = True

    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "yt-dlp"]
    print("INFO: Attempting to install missing Python dependencies...")
    user = os.environ.get("SUDO_USER", os.environ.get("USER"))
    try:
        # Construct pip command
        pip_cmd = [sys.executable, "-m", "pip", "install", "--user"] + required_packages

        # Check if running as root (sudo) and adjust command if necessary
        is_sudo = os.geteuid() == 0
        cmd_to_run = pip_cmd
        if is_sudo and user and user != "root":
            print(f"INFO: Running pip install as original user '{user}' via sudo.")
            cmd_to_run = ["sudo", "-u", user] + pip_cmd
        elif is_sudo:
            print(
                "WARNING: Running as root, installing packages globally or for root user."
            )
            # Consider installing globally? Might need permissions adjustments.
            # For simplicity, stick to --user for root too, though less ideal.

        print(f"EXEC: {' '.join(cmd_to_run)}")
        subprocess.check_call(cmd_to_run)
        print("SUCCESS: Dependencies seem installed. Please restart the script.")
        return True  # Indicate success
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to install dependencies using pip: {e}", file=sys.stderr)
        print("Please try installing manually:", file=sys.stderr)
        print(
            f"  {sys.executable} -m pip install --user {' '.join(required_packages)}",
            file=sys.stderr,
        )
        return False
    except Exception as e:
        print(
            f"ERROR: An unexpected error occurred during dependency installation: {e}",
            file=sys.stderr,
        )
        return False


def _check_homebrew():
    """Checks if Homebrew is installed."""
    if shutil.which("brew") is None:
        print(
            "ERROR: Homebrew is not installed. Homebrew is required to install FFmpeg.",
            file=sys.stderr,
        )
        print(
            "Please install Homebrew from https://brew.sh and rerun this script.",
            file=sys.stderr,
        )
        return False
    return True


def _check_and_install_ffmpeg():
    """Checks for FFmpeg and attempts installation via Homebrew if missing."""
    if shutil.which("ffmpeg"):
        print("INFO: FFmpeg found.")
        return True

    print("WARNING: FFmpeg not found.")
    if not _check_homebrew():
        return False  # Cannot install without Homebrew

    print("INFO: Attempting to install FFmpeg via Homebrew ('brew install ffmpeg')...")
    try:
        result = subprocess.run(
            ["brew", "install", "ffmpeg"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            print("SUCCESS: FFmpeg installed successfully via Homebrew!")
            if shutil.which("ffmpeg"):  # Verify again
                return True
            else:
                print(
                    "ERROR: FFmpeg installed according to Homebrew, but still not found in PATH.",
                    file=sys.stderr,
                )
                print(
                    "Please check your Homebrew installation and PATH configuration.",
                    file=sys.stderr,
                )
                return False
        else:
            print(
                f"ERROR: Failed to install FFmpeg using Homebrew (exit code {result.returncode}).",
                file=sys.stderr,
            )
            print(f"Stderr:\n{result.stderr}", file=sys.stderr)
            return False
    except Exception as e:
        print(
            f"ERROR: An error occurred while trying to install FFmpeg: {e}",
            file=sys.stderr,
        )
        return False


# --- Initial FFmpeg Check ---
if not _check_and_install_ffmpeg():
    print(
        "CRITICAL: FFmpeg is required but could not be found or installed. Exiting.",
        file=sys.stderr,
    )
    sys.exit(1)

# --- Python Package Imports & Handling ---
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
    import yt_dlp

    # Check yt-dlp version (optional but good practice)
    try:
        yt_dlp_version = yt_dlp.version.__version__
        print(f"INFO: Using yt-dlp version {yt_dlp_version}")
    except Exception:
        print("WARNING: Could not determine yt-dlp version.")

except ImportError as import_error:
    print(f"WARNING: Required Python package(s) missing ({import_error}).")
    if _install_dependencies():
        # Installation successful, suggest restart
        print("INFO: Please restart the script now.")
        sys.exit(0)  # Exit cleanly after install suggestion
    else:
        # Installation failed
        print("CRITICAL: Failed to install dependencies. Exiting.", file=sys.stderr)
        sys.exit(1)


# --- Global Configuration & Initialization ---
install_rich_traceback(show_locals=True)  # Enable rich tracebacks
console = Console()

APP_NAME = "pytube.py"
APP_TITLE = "The MacOS YouTube Downloader"
VERSION = "1.3.0"  # Version bump for file detection fix
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "PyTube")
CONFIG_DIR = os.path.expanduser("~/.config/pytube_downloader")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
YOUTUBE_HISTORY_FILENAME = "youtube_url_history.txt"
DEFAULT_TIMEOUT = 300  # Increased timeout for potentially long commands


# --- UI Styling (Nord Theme) ---
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
    def get_progress_columns(cls):
        """Returns columns for Rich Progress."""
        return [
            SpinnerColumn(spinner_name="dots", style=f"bold {cls.FROST_1}"),
            TextColumn(f"[bold {cls.FROST_2}]{{task.description}}[/]"),
            BarColumn(
                bar_width=None,
                style=cls.POLAR_NIGHT_3,
                complete_style=cls.FROST_2,
                finished_style=cls.GREEN,
            ),
            TaskProgressColumn(),  # No style for compatibility
            TransferSpeedColumn(),  # No style for compatibility
            TimeRemainingColumn(compact=True),
        ]


# --- Data Classes ---
@dataclass
class AppConfig:
    """Stores application configuration."""

    default_download_dir: str = DEFAULT_DOWNLOAD_DIR
    recent_urls: List[str] = field(default_factory=list)
    theme: str = "nord"
    max_recent_urls: int = 20

    def save(self):
        """Saves configuration to JSON file."""
        if not ensure_config_directory():
            return  # Don't save if dir fails
        try:
            self.recent_urls = self.recent_urls[: self.max_recent_urls]
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.__dict__, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print_error(f"Failed to save configuration: {e}")

    @classmethod
    def load(cls):
        """Loads configuration from JSON file or returns default."""
        config_to_load = cls()  # Start with default
        if not os.path.exists(CONFIG_FILE):
            print_info(f"Config file not found ({CONFIG_FILE}), using defaults.")
            return config_to_load

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Update default object with loaded data, ignoring extra keys
            for key, value in data.items():
                if hasattr(config_to_load, key):
                    # Basic type checking or conversion could be added here if needed
                    setattr(config_to_load, key, value)
            print_info("Configuration loaded successfully.")
            return config_to_load
        except json.JSONDecodeError as e:
            print_error(f"Failed to decode configuration file {CONFIG_FILE}: {e}")
        except Exception as e:
            print_error(f"Failed to load configuration: {e}")

        print_warning("Using default configuration due to loading error.")
        return cls()  # Return default on error


@dataclass
class DownloadHistoryEntry:
    """Represents a single entry in the download history."""

    url: str
    filename: Optional[str]  # Can be None if detection failed badly
    path: Optional[str]  # Can be None
    size: Optional[int]  # Can be None
    success: bool
    date: str
    elapsed_time: float
    download_type: str


@dataclass
class DownloadHistory:
    """Manages the download history."""

    entries: List[DownloadHistoryEntry] = field(default_factory=list)
    max_history_size: int = 50

    def add_entry(
        self,
        url: str,
        download_type: str,
        elapsed_time: float,
        success: bool,
        filename: Optional[str] = None,
        output_path: Optional[str] = None,
        size: Optional[int] = None,
    ):
        """Adds a new entry to the history."""
        entry = DownloadHistoryEntry(
            url=url,
            filename=filename,
            path=output_path,
            size=size,
            success=success,
            date=datetime.now().isoformat(),
            elapsed_time=elapsed_time,
            download_type=download_type,
        )
        self.entries.insert(0, entry)
        self.entries = self.entries[: self.max_history_size]
        self.save()

    def save(self):
        """Saves download history to JSON file."""
        if not ensure_config_directory():
            return
        try:
            history_data = [entry.__dict__ for entry in self.entries]
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump({"history": history_data}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print_error(f"Failed to save history: {e}")

    @classmethod
    def load(cls):
        """Loads download history from JSON file or returns default."""
        history_to_load = cls()
        if not os.path.exists(HISTORY_FILE):
            print_info("Download history file not found, starting fresh.")
            return history_to_load

        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Convert dicts back to dataclass objects, handling potential missing keys
            loaded_entries = []
            for entry_data in data.get("history", []):
                # Use .get for optional fields
                entry = DownloadHistoryEntry(
                    url=entry_data.get("url", "Unknown URL"),
                    filename=entry_data.get("filename"),  # Allow None
                    path=entry_data.get("path"),  # Allow None
                    size=entry_data.get("size"),  # Allow None
                    success=entry_data.get("success", False),
                    date=entry_data.get("date", datetime.now().isoformat()),
                    elapsed_time=entry_data.get("elapsed_time", 0.0),
                    download_type=entry_data.get("download_type", "unknown"),
                )
                loaded_entries.append(entry)
            history_to_load.entries = loaded_entries
            print_info("Download history loaded.")
            return history_to_load
        except json.JSONDecodeError as e:
            print_error(f"Failed to decode history file {HISTORY_FILE}: {e}")
        except Exception as e:
            print_error(f"Failed to load history: {e}")

        print_warning("Using empty download history due to loading error.")
        return cls()


# --- Utility Functions ---
def clear_screen():
    """Clears the terminal screen."""
    console.clear()


def create_header() -> Panel:
    """Creates the application header panel using PyFiglet and Rich."""
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)

    fonts = ["slant", "small_slant", "standard", "digital", "small"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=adjusted_width)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip() and len(ascii_art.splitlines()) > 1:
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = APP_NAME

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    frost_colors = NordColors.get_frost_gradient(min(len(ascii_lines), 4))
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = frost_colors[i % len(frost_colors)]
        escaped_line = line.replace("[", r"\[").replace("]", r"\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"

    panel = Panel(
        Text.from_markup(styled_text.strip()),
        border_style=NordColors.FROST_1,
        box=NordColors.NORD_BOX,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_3}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_TITLE}[/]",
        subtitle_align="center",
        width=adjusted_width,
    )
    return panel


# --- Console Output Helpers ---
def print_message(
    text: str, style: Union[Style, str] = NordColors.INFO, prefix: str = "•"
):
    """Prints a styled message to the console."""
    if isinstance(style, str):
        console.print(f"[{style}]{prefix} {text}[/{style}]")
    else:
        console.print(f"{prefix} {text}", style=style)


def print_error(message: str):
    print_message(message, NordColors.ERROR, "✗")


def print_success(message: str):
    print_message(message, NordColors.SUCCESS, "✓")


def print_warning(message: str):
    print_message(message, NordColors.WARNING, "⚠")


def print_step(message: str):
    print_message(message, NordColors.INFO, "→")


def print_info(message: str):
    print_message(message, NordColors.INFO, "ℹ")


def display_panel(
    title: str, message: Union[str, Text], style: Union[Style, str] = NordColors.INFO
):
    """Displays content within a styled Rich panel."""
    panel = Panel(
        Text.from_markup(message) if isinstance(message, str) else message,
        title=title,
        border_style=style,
        box=NordColors.NORD_BOX,
        padding=(1, 2),
    )
    console.print(panel)


# --- Formatting Helpers ---
def format_size(num_bytes: Union[int, float, None]) -> str:
    """Formats bytes into a human-readable string (KB, MB, GB)."""
    if num_bytes is None or num_bytes < 0:
        return "0 B"
    try:
        num_bytes = float(num_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if abs(num_bytes) < 1024.0:
                return f"{num_bytes:.2f} {unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.2f} PB"
    except (ValueError, TypeError):
        return "Invalid Size"


def format_time(seconds: Union[int, float, None]) -> str:
    """Formats seconds into a human-readable string (ms, s, m, h)."""
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "unknown"
    try:
        seconds = float(seconds)
        if seconds < 1:
            return f"{seconds * 1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes, rem_seconds = divmod(seconds, 60)
            return f"{int(minutes)}m {int(rem_seconds)}s"
        else:
            hours, remainder = divmod(seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{int(hours)}h {int(minutes)}m"
    except (ValueError, TypeError):
        return "Invalid Time"


# --- UI Components ---
def create_menu_table(title: str, options: List[Tuple[str, str, str]]) -> Table:
    """Creates a Rich table for displaying menu options."""
    table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        title=f"[bold {NordColors.FROST_1}]{title}[/]",
        border_style=NordColors.FROST_3,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("#", style=NordColors.ACCENT, width=3, justify="right")
    table.add_column("Option", style=NordColors.FROST_1, no_wrap=True)
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    for opt in options:
        table.add_row(*opt)
    return table


# --- File System & System Helpers ---
def ensure_config_directory() -> bool:
    """Creates the configuration directory if it doesn't exist. Returns True on success/exists, False on error."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        return True
    except Exception as e:
        print_error(f"Could not create or access config directory '{CONFIG_DIR}': {e}")
        return False


def ensure_directory(path: str, check_write: bool = False) -> bool:
    """Creates a directory if it doesn't exist. Optionally checks write permissions. Returns True on success, False on error."""
    try:
        os.makedirs(path, exist_ok=True)
        if check_write and not os.access(path, os.W_OK):
            print_error(
                f"Directory '{path}' exists but script lacks write permissions."
            )
            return False
        return True
    except Exception as e:
        print_error(f"Failed to create or access directory '{path}': {e}")
        return False


# --- Core Download Logic ---


def _run_yt_dlp_and_capture(cmd: List[str], verbose: bool) -> Tuple[int, List[str]]:
    """
    Runs the yt-dlp command, captures stdout/stderr, displays progress,
    and returns the exit code and captured output lines.
    """
    stdout_lines = []
    process = None  # Define process in outer scope

    try:
        if verbose:
            print_step(f"Executing yt-dlp: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Capture both stdout and stderr
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # Line buffered
        )

        with Progress(
            *NordColors.get_progress_columns(), console=console, transient=True
        ) as progress:
            download_task = progress.add_task("Initializing...", total=1000)
            current_percent = 0.0
            description = "Starting..."
            last_parsed_filename_hint = None  # Local hint

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if not line:
                    time.sleep(0.05)
                    continue

                line = line.strip()
                if line:
                    stdout_lines.append(line)  # Store all output

                if verbose:
                    console.log(f"[dim]yt-dlp: {line}[/dim]")

                # --- Live Progress Parsing ---
                # (Keep the existing parsing logic for live feedback)
                if "[download]" in line:
                    if "%" in line:
                        try:
                            parts = line.split()
                            for part in parts:
                                if "%" in part:
                                    percent_str = part.replace("%", "").split("m")[
                                        -1
                                    ]  # Handle potential color codes
                                    current_percent = float(percent_str)
                                    description = line  # Show the raw line
                                    break
                        except (ValueError, IndexError):
                            pass  # Ignore parsing errors
                    elif "Destination:" in line:
                        try:
                            last_parsed_filename_hint = os.path.basename(
                                line.split("Destination:")[1].strip()
                            )
                        except Exception:
                            pass
                        description = (
                            f"Downloading: {last_parsed_filename_hint or '...'}"
                        )
                    elif "has already been downloaded" in line:
                        description = "File already downloaded"
                        current_percent = 100.0
                        try:
                            filepath_part = (
                                line.split("]")[1].strip().split(" has already been")[0]
                            )
                            last_parsed_filename_hint = os.path.basename(filepath_part)
                        except Exception:
                            pass
                    else:
                        description = line  # Show other download messages
                elif "[ExtractAudio]" in line:
                    description = "Extracting Audio..."
                    current_percent = max(current_percent, 95.0)
                elif "[Merger]" in line or "[ffmpeg] Merging" in line:
                    description = "Merging Formats..."
                    current_percent = max(current_percent, 98.0)
                    try:
                        if "Merging formats into" in line:
                            last_parsed_filename_hint = os.path.basename(
                                line.split("Merging formats into")[-1]
                                .strip()
                                .strip('"')
                            )
                    except Exception:
                        pass
                elif "[Fixup" in line or "[Metadata]" in line:
                    description = "Processing..."
                    current_percent = max(current_percent, 90.0)
                elif "[ffmpeg]" in line:
                    description = "Processing (FFmpeg)..."
                    current_percent = max(current_percent, 97.0)
                # --- End Live Progress Parsing ---

                progress.update(
                    download_task,
                    completed=current_percent * 10,
                    description=description[: console.width - 40],
                )

            # Final update after loop
            exit_code = process.wait()  # Ensure process finishes and get code
            final_description = (
                "[green]Complete[/]" if exit_code == 0 else "[red]Failed[/]"
            )
            progress.update(
                download_task, completed=1000, description=final_description
            )
            time.sleep(0.3)  # Allow final status display

            return exit_code, stdout_lines

    except FileNotFoundError:
        print_error(f"Command not found: {cmd[0]}. Is yt-dlp installed and in PATH?")
        return -1, [
            "ERROR: yt-dlp command not found."
        ]  # Use a specific error code/message
    except Exception as e:
        print_error(f"Failed to execute or monitor yt-dlp: {e}")
        if process and process.poll() is None:  # Try to terminate if running
            process.terminate()
        return -2, [
            f"ERROR: Script error during execution: {e}"
        ]  # Different error code


def _find_downloaded_file(
    output_dir: str, stdout_lines: List[str], start_time: float
) -> Optional[str]:
    """
    Attempts to find the downloaded file path using yt-dlp output and fallback scan.
    Returns the absolute path if found, None otherwise.
    """
    downloaded_file_path = None

    # 1. Primary Method: Parse --print filename output (less strict)
    print_info("Locating final file path from yt-dlp output...")
    possible_paths = []
    for line in reversed(stdout_lines):
        potential_path = line.strip()
        # Check if it looks like *any* existing file/dir path first
        # yt-dlp should print absolute path, but be a bit lenient
        if potential_path and os.path.exists(potential_path):
            # Check if it's INSIDE the intended output directory (or IS the output dir itself, unlikely)
            # Use normpath for consistent comparison
            abs_potential_path = os.path.abspath(potential_path)
            abs_output_dir = os.path.abspath(output_dir)
            if abs_potential_path.startswith(abs_output_dir):
                # Reduce false positives: avoid lines clearly part of progress/debug
                if not (
                    potential_path.startswith("[")
                    or "ETA " in potential_path
                    or "%" in potential_path
                    or "/s" in potential_path
                    or "KiB" in potential_path
                    or "MiB" in potential_path
                    or "GiB" in potential_path
                ):
                    possible_paths.append(abs_potential_path)
                    # Don't break immediately, collect all plausible paths from the end

    if possible_paths:
        # Usually, the *last* existing path printed is the final one.
        downloaded_file_path = possible_paths[
            0
        ]  # The first one found iterating backwards
        print_success(
            f"Located candidate file via --print output: {downloaded_file_path}"
        )
        # Verify it's a file, not a directory (should be handled by yt-dlp printing file, but double check)
        if not os.path.isfile(downloaded_file_path):
            print_warning(
                f"Path found ({downloaded_file_path}) exists but is not a file. Ignoring."
            )
            downloaded_file_path = None  # Reset if it was a directory
        else:
            # Optional: check modification time as sanity check
            try:
                mod_time = os.path.getmtime(downloaded_file_path)
                if (
                    mod_time < start_time - 5
                ):  # If modified significantly *before* download started
                    print_warning(
                        f"File found ({downloaded_file_path}) seems too old (modified before download)."
                    )
                    # Decide whether to trust it or not - for now, let's trust yt-dlp's print
                    # downloaded_file_path = None
            except OSError:
                pass  # Ignore mtime check errors

    # 2. Fallback Method: Timestamp Scan (if primary failed)
    if not downloaded_file_path:
        print_warning(
            "Could not reliably identify path from --print output. Using fallback timestamp scan..."
        )
        # Use a slightly later start time for comparison to avoid race conditions
        scan_start_time = (
            start_time - 2
        )  # Files modified up to 2s before start might be relevant
        newest_time = scan_start_time
        candidate_file = None
        possible_extensions = (
            ".mp4",
            ".mkv",
            ".webm",
            ".mp3",
            ".m4a",
            ".opus",
            ".aac",
            ".flv",
            ".ogg",
        )  # Expanded list

        try:
            for filename in os.listdir(output_dir):
                # Check extension and avoid known temporary files
                if filename.endswith(possible_extensions) and not filename.endswith(
                    (".part", ".ytdl")
                ):
                    file_path = os.path.join(output_dir, filename)
                    try:
                        # Ensure it's a file we can check
                        if os.path.isfile(file_path):
                            file_mod_time = os.path.getmtime(file_path)
                            # Check if modified after (or very close to) download start AND is the newest found so far
                            if (
                                file_mod_time > scan_start_time
                                and file_mod_time > newest_time
                            ):
                                newest_time = file_mod_time
                                candidate_file = file_path
                    except OSError:
                        continue  # Ignore errors checking specific files (e.g., permissions)
        except OSError as e:
            print_error(f"Error scanning output directory '{output_dir}': {e}")
            # Cannot find file via scan if directory listing fails

        if candidate_file:
            downloaded_file_path = os.path.abspath(
                candidate_file
            )  # Store absolute path
            print_success(
                f"Located candidate file via fallback scan: {downloaded_file_path}"
            )
        else:
            print_error(
                "Fallback scan also failed to find a recently modified matching file."
            )

    return downloaded_file_path


def download_youtube(
    url: str, output_dir: str, download_type: str = "combined", verbose: bool = False
):
    """
    Downloads a YouTube video using yt-dlp with specified format options.

    Args:
        url: The YouTube URL to download.
        output_dir: The directory to save the downloaded file.
        download_type: 'combined', 'video', or 'audio'.
        verbose: If True, enables verbose output from yt-dlp.

    Returns:
        True if download succeeded and file located, False otherwise.
    """
    start_time = time.time()
    history = DownloadHistory.load()  # Load history at the start

    # 1. Prepare Directory and Check Permissions
    abs_output_dir = os.path.abspath(os.path.expanduser(output_dir))
    if not ensure_directory(abs_output_dir, check_write=True):
        print_error(
            f"Cannot proceed due to issues with output directory: {abs_output_dir}"
        )
        # Add failed entry (directory issue)
        history.add_entry(
            url=url,
            download_type=download_type,
            elapsed_time=time.time() - start_time,
            success=False,
            filename="error - output directory",
        )
        return False

    # 2. Build yt-dlp Command
    # Use %(title).%(ext)s which yt-dlp resolves correctly based on format/merging
    output_template = os.path.join(abs_output_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--print",
        "filename",
        "-o",
        output_template,
    ]  # Base + print + output
    format_string = ""
    info_panel_details = f"URL: {url}\n"

    if download_type == "audio":
        format_string = "bestaudio[ext=m4a]/bestaudio/best"
        cmd.extend(
            ["-f", format_string, "-x", "--audio-format", "mp3"]
        )  # -x implies audio extraction
        info_panel_details += "Type: Audio Only (MP3)\n"
    elif download_type == "video":
        format_string = "bestvideo[ext=mp4]/bestvideo/best"
        cmd.extend(["-f", format_string])
        info_panel_details += "Type: Video Only (Best Quality)\nFormat: MP4/WebM/MKV\n"
    else:  # 'combined'
        format_string = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        cmd.extend(["-f", format_string, "--merge-output-format", "mp4"])
        info_panel_details += (
            "Type: Combined Video+Audio (Best Quality)\nFormat: MP4 (merged)\n"
        )

    # Add other options AFTER format but BEFORE URL
    cmd.extend(["--newline"])  # Helps with live parsing slightly
    if verbose:
        cmd.append("-v")
    cmd.append(url)  # URL must be last

    info_panel_details += f"Destination Dir: {abs_output_dir}"
    display_panel("YouTube Download", info_panel_details, NordColors.FROST_2)

    # 3. Execute yt-dlp
    exit_code, stdout_lines = _run_yt_dlp_and_capture(cmd, verbose)
    download_time = time.time() - start_time

    # 4. Process Results
    if exit_code == 0:
        # yt-dlp exited successfully, now find the file
        downloaded_file_path = _find_downloaded_file(
            abs_output_dir, stdout_lines, start_time
        )

        if downloaded_file_path:
            final_filename = os.path.basename(downloaded_file_path)
            try:
                file_size = os.path.getsize(downloaded_file_path)
            except OSError as e:
                print_warning(
                    f"Could not get size of downloaded file '{final_filename}': {e}"
                )
                file_size = None

            # Add success entry to history
            history.add_entry(
                url=url,
                download_type=download_type,
                elapsed_time=download_time,
                success=True,
                filename=final_filename,
                output_path=downloaded_file_path,
                size=file_size,
            )
            display_panel(
                "YouTube Download Complete",
                f"✅ Downloaded: [bold]{final_filename}[/]\n"
                f"📦 Size: [bold]{format_size(file_size)}[/]\n"
                f"⏱️ Time: [bold]{format_time(download_time)}[/]\n"
                f"📂 Location: [bold]{downloaded_file_path}[/]",
                NordColors.GREEN,
            )
            return True
        else:
            # yt-dlp exited 0, but we couldn't find the file
            print_error(
                "yt-dlp reported success, but the final file could not be located."
            )
            print_info(f"Searched in: {abs_output_dir}")
            # Optionally print last few lines of output for debugging this specific case
            if stdout_lines:
                print_info("Last 10 lines of yt-dlp output:")
                for line in stdout_lines[-10:]:
                    console.print(f"[dim]  {line}[/dim]")

            # Add failure entry (file location issue)
            history.add_entry(
                url=url,
                download_type=download_type,
                elapsed_time=download_time,
                success=False,
                filename="error - file not found post-download",
            )
            return False
    else:
        # yt-dlp exited with an error
        display_panel(
            "YouTube Download Failed",
            f"❌ yt-dlp exited with error code {exit_code}\n"
            f"🔗 URL: {url}\n"
            f"⁉️ Check logs or run with verbose mode for details.",
            NordColors.RED,
        )
        # Print last few lines if not verbose, as they often contain the error reason
        if not verbose and stdout_lines:
            print_info("Last 10 lines of yt-dlp output:")
            for line in stdout_lines[-10:]:
                console.print(f"[dim]  {line}[/dim]")

        # Add failure entry (yt-dlp error)
        history.add_entry(
            url=url,
            download_type=download_type,
            elapsed_time=download_time,
            success=False,
            filename=f"error - yt-dlp exit code {exit_code}",
        )
        return False


# --- Signal Handling and Cleanup ---
def cleanup():
    """Performs cleanup actions before exiting."""
    try:
        # No explicit cleanup needed currently, but keep hook
        print_message(
            "Exiting...", NordColors.FROST_3, prefix=""
        )  # Cleaner exit message
    except Exception as e:
        # Use print directly in cleanup to avoid potential rich/console issues during shutdown
        print(f"Error during cleanup: {e}", file=sys.stderr)


def signal_handler(sig, frame):
    """Handles termination signals gracefully."""
    try:
        sig_int = int(sig)
        # Use signal.strsignal for more compatibility if available
        sig_name = (
            signal.strsignal(sig_int)
            if hasattr(signal, "strsignal")
            else f"Signal {sig_int}"
        )
        print_warning(f"\nProcess interrupted by {sig_name}. Cleaning up...")
    except Exception:
        print_warning(f"\nProcess interrupted by signal {sig}. Cleaning up...")
    # Let atexit handle actual cleanup, just exit appropriately
    sys.exit(128 + (sig_int if isinstance(sig, int) else 1))


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)

# --- Menu Functions ---


def youtube_download_menu():
    """Handles the YouTube download process, including format selection."""
    clear_screen()
    console.print(create_header())
    display_panel(
        "YouTube Download",
        "Download YouTube content with quality and format options.",
        NordColors.FROST_2,
    )

    config = AppConfig.load()
    # Prepare prompt_toolkit history
    history = None
    if ensure_config_directory():  # Only try if config dir is usable
        try:
            history_path = os.path.join(CONFIG_DIR, YOUTUBE_HISTORY_FILENAME)
            history = FileHistory(history_path)
            print_info(f"URL history enabled ({history_path})")
        except Exception as e:
            print_warning(f"Could not load/create URL history file: {e}")
    else:
        print_warning("Config directory inaccessible, URL history disabled.")

    url_completer = WordCompleter(config.recent_urls, sentence=True)

    # 1. Get URL
    url = pt_prompt(
        "Enter the YouTube URL: ",
        history=history,
        completer=url_completer,
        style=PTStyle.from_dict({"prompt": f"bold {NordColors.FROST_2}"}),
        validator=None,  # Keep validation simple for now
        validate_while_typing=False,
    ).strip()

    if not url:
        print_error("URL cannot be empty.")
        Prompt.ask("[dim]Press Enter to return to main menu...[/dim]")
        return

    # 2. Get Download Type
    download_type_options = [
        ("1", "Combined", "Video + Audio (Best Quality MP4) [Default]"),
        ("2", "Video Only", "Video Only (Best Quality MP4/WebM)"),
        ("3", "Audio Only", "Audio Only (Best Quality MP3)"),
    ]
    console.print(create_menu_table("Select Download Type", download_type_options))
    type_choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="1")

    download_type_map = {"1": "combined", "2": "video", "3": "audio"}
    download_type = download_type_map[type_choice]

    # 3. Get Output Directory
    output_dir = Prompt.ask(
        "Enter output directory",
        default=config.default_download_dir,
        # Consider adding path completion here later if desired
    )
    # Normalizing path early
    output_dir = os.path.abspath(os.path.expanduser(output_dir.strip()))

    # 4. Verbose Mode
    verbose = Confirm.ask("Enable verbose mode (for debugging)?", default=False)

    # 5. Execute Download
    success = download_youtube(url, output_dir, download_type, verbose)

    # 6. Update Recent URLs (only if URL seems valid, even on failure)
    if url.startswith("http"):  # Basic check
        if url not in config.recent_urls:
            config.recent_urls.insert(0, url)
            config.save()  # Save config with updated recent list

    Prompt.ask("[dim]Press Enter to return to main menu...[/dim]")


def view_download_history():
    """Displays the download history and allows interaction."""
    while True:  # Loop until user chooses to return
        clear_screen()
        console.print(create_header())
        history = DownloadHistory.load()

        if not history.entries:
            display_panel(
                "Download History", "No download history found.", NordColors.FROST_3
            )
            Prompt.ask("[dim]Press Enter to return to settings menu...[/dim]")
            return  # Exit the loop/function

        # --- Display History Table ---
        table = Table(
            show_header=True,
            header_style=NordColors.HEADER,
            box=ROUNDED,
            title="Download History (Most Recent First)",
            border_style=NordColors.FROST_3,
            expand=True,
        )
        table.add_column("#", style=NordColors.ACCENT, width=3, justify="right")
        table.add_column("Date", style=NordColors.FROST_2, width=16)
        table.add_column("Type", style=NordColors.PURPLE, width=8)
        table.add_column(
            "Filename / Status Info", style=NordColors.SNOW_STORM_1, overflow="fold"
        )
        table.add_column("Size", style=NordColors.FROST_3, justify="right", width=10)
        table.add_column("Status", style=NordColors.FROST_4, width=8)

        displayed_entries = history.entries[:20]  # Show more entries
        for i, entry in enumerate(displayed_entries, 1):
            try:
                date_str = (
                    datetime.fromisoformat(entry.date).strftime("%Y-%m-%d %H:%M")
                    if entry.date
                    else "No Date"
                )
            except (ValueError, TypeError):
                date_str = "Invalid Date"

            status_text = "[green]Success[/]" if entry.success else "[red]Failed[/]"
            dl_type = (entry.download_type or "N/A")[:7].capitalize()
            # Show filename if success, otherwise show the "filename" which might contain error info
            display_name = (
                entry.filename if entry.success else f"({entry.filename or 'Info N/A'})"
            )

            table.add_row(
                str(i),
                date_str,
                dl_type,
                display_name,
                format_size(entry.size),
                Text.from_markup(status_text),
            )
        console.print(table)

        # --- History Options Menu ---
        options = [
            ("1", "View Details", "Show full details for a specific download"),
            (
                "2",
                "Open Location",
                "Open the download location in Finder (if available)",
            ),
            ("3", "Clear History", "Delete all download history entries"),
            ("4", "Return", "Go back to the settings menu"),
        ]
        console.print(create_menu_table("History Options", options))
        choice = Prompt.ask(
            "Select option", choices=[str(i) for i in range(1, 5)], default="4"
        )

        if choice == "1":  # View Details
            if not displayed_entries:
                print_warning("No history entries to view.")
            else:
                entry_num_str = Prompt.ask(
                    "Enter download number to view details",
                    choices=[str(i) for i in range(1, len(displayed_entries) + 1)],
                    show_choices=False,
                )
                try:
                    entry_index = int(entry_num_str) - 1
                    if 0 <= entry_index < len(displayed_entries):
                        entry = displayed_entries[entry_index]
                        try:
                            date_str_full = (
                                datetime.fromisoformat(entry.date).strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                                if entry.date
                                else "No Date"
                            )
                        except (ValueError, TypeError):
                            date_str_full = "Invalid Date"

                        details_text = (
                            f"URL: {entry.url or 'N/A'}\n"
                            f"Filename: {entry.filename or 'N/A'}\n"
                            f"Path: {entry.path or 'N/A'}\n"
                            f"Type: {(entry.download_type or 'N/A').capitalize()}\n"
                            f"Size: {format_size(entry.size)}\n"
                            f"Status: {'Successful' if entry.success else 'Failed'}\n"
                            f"Date: {date_str_full}\n"
                            f"Download Time: {format_time(entry.elapsed_time)}"
                        )
                        display_panel(
                            f"Download Details: #{entry_num_str}",
                            details_text,
                            NordColors.FROST_2,
                        )
                    else:
                        print_error("Invalid entry number.")
                except ValueError:
                    print_error("Invalid input. Please enter a number.")
                Prompt.ask(
                    "[dim]Press Enter to continue...[/dim]"
                )  # Pause after details

        elif choice == "2":  # Open Location
            if not displayed_entries:
                print_warning("No history entries to open.")
            else:
                entry_num_str = Prompt.ask(
                    "Enter download number to open location",
                    choices=[str(i) for i in range(1, len(displayed_entries) + 1)],
                    show_choices=False,
                )
                try:
                    entry_index = int(entry_num_str) - 1
                    if 0 <= entry_index < len(displayed_entries):
                        entry = displayed_entries[entry_index]
                        path_to_open = (
                            entry.path
                            if entry.path and os.path.exists(entry.path)
                            else None
                        )
                        # If path is file, open containing dir; if path is dir, open dir
                        dir_to_open = None
                        if path_to_open:
                            if os.path.isfile(path_to_open):
                                dir_to_open = os.path.dirname(path_to_open)
                            elif os.path.isdir(
                                path_to_open
                            ):  # Should ideally be a file path, but handle dir case
                                dir_to_open = path_to_open

                        if dir_to_open and os.path.exists(dir_to_open):
                            try:
                                print_step(f"Opening '{dir_to_open}' in Finder...")
                                subprocess.run(
                                    ["open", "-R", path_to_open]
                                    if os.path.isfile(path_to_open)
                                    else ["open", dir_to_open],
                                    check=True,
                                )
                                time.sleep(0.5)  # Small delay
                            except Exception as e:
                                print_error(f"Failed to open location: {e}")
                        else:
                            print_warning(
                                "Path not available or does not exist for this entry."
                            )
                    else:
                        print_error("Invalid entry number.")
                except ValueError:
                    print_error("Invalid input. Please enter a number.")
                Prompt.ask(
                    "[dim]Press Enter to continue...[/dim]"
                )  # Pause after attempt

        elif choice == "3":  # Clear History
            if Confirm.ask(
                "[bold red]Are you sure you want to clear ALL download history? This cannot be undone.[/]",
                default=False,
            ):
                history.entries = []
                history.save()
                print_success("Download history cleared.")
                time.sleep(1)  # Pause briefly to see message

        elif choice == "4":  # Return
            return  # Exit the loop/function


def settings_menu():
    """Displays and manages application settings."""
    while True:  # Loop until user chooses to return
        clear_screen()
        console.print(create_header())
        display_panel(
            "Settings",
            "Configure application settings and preferences.",
            NordColors.FROST_2,
        )

        config = AppConfig.load()
        settings_options = [
            ("1", "Default Download Directory", config.default_download_dir),
            (
                "2",
                "View/Clear Recent URLs",
                f"{len(config.recent_urls)} stored (max {config.max_recent_urls})",
            ),
            ("3", "View Download History", "View, manage, and open past downloads"),
            ("4", "Check Dependencies", "Verify yt-dlp and FFmpeg"),
            ("5", "Application Info", "View app details and system info"),
            ("6", "Return", "Go back to the main menu"),
        ]

        console.print(create_menu_table("Settings Options", settings_options))
        choice = Prompt.ask(
            "Select option", choices=[str(i) for i in range(1, 7)], default="6"
        )

        action_taken = (
            False  # Flag to pause only if action occurred within this loop iteration
        )

        if choice == "1":  # Change Default Dir
            action_taken = True
            new_dir = Prompt.ask(
                "Enter new default download directory",
                default=config.default_download_dir,
            )
            abs_new_dir = os.path.abspath(os.path.expanduser(new_dir.strip()))
            abs_old_dir = os.path.abspath(config.default_download_dir)

            if abs_new_dir == abs_old_dir:
                print_info("Directory is already set to this value.")
            elif ensure_directory(
                abs_new_dir, check_write=False
            ):  # Create first if needed
                if os.access(abs_new_dir, os.W_OK):  # Now check write permissions
                    config.default_download_dir = abs_new_dir
                    config.save()
                    print_success(f"Default download directory updated: {abs_new_dir}")
                else:
                    print_error(
                        f"Directory created/exists, but write permission denied: {abs_new_dir}"
                    )
            # ensure_directory prints errors if creation/access fails

        elif choice == "2":  # View/Clear Recent URLs
            action_taken = True
            if config.recent_urls:
                recent_table = Table(
                    show_header=True,
                    header_style=NordColors.HEADER,
                    title="Recent URLs",
                    box=ROUNDED,
                    border_style=NordColors.FROST_3,
                    expand=True,
                )
                recent_table.add_column(
                    "#", style=NordColors.ACCENT, width=3, justify="right"
                )
                recent_table.add_column(
                    "URL", style=NordColors.SNOW_STORM_1, overflow="fold"
                )
                for i, url in enumerate(config.recent_urls, 1):
                    recent_table.add_row(str(i), url)
                console.print(recent_table)

                if Confirm.ask("Clear recent URLs list?", default=False):
                    config.recent_urls = []
                    config.save()
                    print_success("Recent URLs list cleared.")
            else:
                print_info("No recent URLs found.")

        elif choice == "3":  # View History
            view_download_history()  # Handles its own loop and pausing

        elif choice == "4":  # Check Dependencies
            action_taken = True
            print_step("Checking required dependencies...")
            deps_status = {
                "yt-dlp": "[yellow]Checking...[/]",
                "ffmpeg": "[yellow]Checking...[/]",
            }
            missing_deps = []

            # Check yt-dlp
            try:
                result = subprocess.run(
                    ["yt-dlp", "--version"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                if result.returncode == 0:
                    deps_status["yt-dlp"] = f"[green]OK ({result.stdout.strip()})[/]"
                else:
                    raise Exception(f"yt-dlp --version failed: {result.stderr}")
            except FileNotFoundError:
                missing_deps.append("yt-dlp")
                deps_status["yt-dlp"] = "[red]Missing[/]"
            except Exception as e:
                deps_status["yt-dlp"] = f"[yellow]Error checking ({e})[/]"

            # Check ffmpeg
            if shutil.which("ffmpeg"):
                try:
                    result = subprocess.run(
                        ["ffmpeg", "-version"],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        version_line = result.stdout.split("\n")[0]
                        version = (
                            version_line.split(" version ")[1].split(" ")[0]
                            if " version " in version_line
                            else "Unknown"
                        )
                        deps_status["ffmpeg"] = f"[green]OK ({version})[/]"
                    else:
                        deps_status["ffmpeg"] = (
                            "[yellow]Found (version check failed)[/]"
                        )
                except Exception as e:
                    deps_status["ffmpeg"] = f"[yellow]Found (Error: {e})[/]"
            else:
                missing_deps.append("ffmpeg")
                deps_status["ffmpeg"] = "[red]Missing[/]"

            # Display Table
            dep_table = Table(
                title="Dependency Status", box=ROUNDED, border_style=NordColors.FROST_3
            )
            dep_table.add_column("Dependency", style=NordColors.FROST_1)
            dep_table.add_column("Status / Version", style=NordColors.SNOW_STORM_1)
            for name, status in deps_status.items():
                dep_table.add_row(name, Text.from_markup(status))
            console.print(dep_table)

            if missing_deps:
                print_warning(f"Missing: {', '.join(missing_deps)}")
                if "yt-dlp" in missing_deps:
                    print_info("Install via pip: pip install --user yt-dlp")
                if "ffmpeg" in missing_deps:
                    print_info("Install via Homebrew: brew install ffmpeg")
            else:
                print_success("All dependencies seem OK.")

        elif choice == "5":  # App Info
            action_taken = True
            system_info = {
                "App Name": APP_NAME,
                "App Version": VERSION,
                "Python Version": platform.python_version(),
                "Interpreter Path": sys.executable,
                "macOS Version": platform.mac_ver()[0],
                "Architecture": platform.machine(),
                "User": os.environ.get("USER", "Unknown"),
                "Config Directory": CONFIG_DIR,
                "Default Downloads": config.default_download_dir,
            }
            info_content = "\n".join(
                [
                    f"[bold {NordColors.FROST_4}]{k}:[/] {v}"
                    for k, v in system_info.items()
                ]
            )
            display_panel(
                "Application Information",
                Text.from_markup(info_content),
                NordColors.FROST_2,
            )

        elif choice == "6":  # Return
            return  # Exit the settings loop

        # Pause only if an action was taken in *this* iteration (not after returning from history)
        if action_taken:
            Prompt.ask("[dim]Press Enter to return to settings menu...[/dim]")


def main_menu():
    """Displays the main menu and handles user interaction."""
    while True:
        clear_screen()
        console.print(create_header())

        main_options = [
            ("1", "Download YouTube URL", "Download video/audio from YouTube"),
            ("2", "Settings", "Configure preferences and view history"),
            ("3", "Exit", "Exit the application"),
        ]
        console.print(create_menu_table("Main Menu", main_options))

        # Quick Stats Panel
        try:
            config = AppConfig.load()  # Reload config for latest dir
            history = DownloadHistory.load()  # Reload history for latest count
            successful_downloads = sum(1 for e in history.entries if e.success)
            stats_panel = Panel(
                Text.from_markup(
                    f"Default Directory: [bold]{config.default_download_dir}[/]\n"
                    f"Recent URLs: [bold]{len(config.recent_urls)}[/] / History Items: [bold]{len(history.entries)}[/]\n"
                    f"Successful Downloads: [bold {NordColors.GREEN}]{successful_downloads}[/]"
                ),
                title="Quick Stats",
                border_style=NordColors.FROST_3,
                box=ROUNDED,
                padding=(1, 2),
                expand=False,
            )
            console.print(stats_panel)
        except Exception as e:
            print_warning(f"Could not display quick stats: {e}")

        choice = Prompt.ask("Select an option", choices=["1", "2", "3"], default="3")

        if choice == "1":
            youtube_download_menu()
        elif choice == "2":
            settings_menu()
        elif choice == "3":
            # Exit gracefully
            clear_screen()
            console.print(
                Panel(
                    Text.from_markup(
                        f"[bold {NordColors.FROST_1}]Thank you for using {APP_NAME}! ({APP_TITLE})[/]"
                    ),
                    title="Goodbye!",
                    title_align="center",
                    border_style=NordColors.FROST_2,
                    box=HEAVY,
                    padding=(2, 4),
                )
            )
            break  # Exit the main menu loop


# --- Main Execution ---
def main():
    """Main function to initialize and run the application."""
    try:
        clear_screen()
        console.print(create_header())

        # Initial checks and loading (simplified)
        print_step(f"Starting {APP_NAME} v{VERSION}...")
        ensure_config_directory()  # Ensure config dir exists early
        AppConfig.load()  # Load config
        DownloadHistory.load()  # Load history
        time.sleep(0.5)  # Brief pause

        main_menu()  # Enter the main application loop

    except KeyboardInterrupt:
        # Signal handler manages message and exit code
        pass  # Avoid printing extra messages here
    except Exception as e:
        console.print_exception(
            show_locals=True
        )  # Show detailed traceback for unexpected errors
        print_error(f"An unexpected critical error occurred: {e}")
        print_step("The application will now exit.")
        sys.exit(1)  # Exit with error code

    # Normal exit (from main_menu break)
    sys.exit(0)


if __name__ == "__main__":
    main()
