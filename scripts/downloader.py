#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pytube.py: The MacOS YouTube Downloader
A command-line tool for downloading YouTube videos on macOS with quality options.
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
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)

# --- Dependency Management ---
_INSTALL_ATTEMPTED = False


def _install_dependencies():
    """Installs required Python packages using pip."""
    global _INSTALL_ATTEMPTED
    if _INSTALL_ATTEMPTED:
        print("Dependency installation already attempted. Exiting to prevent loop.")
        sys.exit(1)
    _INSTALL_ATTEMPTED = True

    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "yt-dlp"]
    print("Attempting to install missing Python dependencies...")
    user = os.environ.get("SUDO_USER", os.environ.get("USER"))
    try:
        pip_cmd = [sys.executable, "-m", "pip", "install", "--user"] + required_packages
        if os.geteuid() == 0 and user:
            # If running as root (e.g., via sudo), install for the original user
            subprocess.check_call(["sudo", "-u", user] + pip_cmd)
        else:
            # Run as the current user
            subprocess.check_call(pip_cmd)
        print("Dependencies installed successfully. Please restart the script.")
        # Return True to indicate success, allowing a retry of imports
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}", file=sys.stderr)
        print("Please install the following packages manually:", file=sys.stderr)
        print(
            f"  {sys.executable} -m pip install {' '.join(required_packages)}",
            file=sys.stderr,
        )
        return False
    except Exception as e:
        print(
            f"An unexpected error occurred during dependency installation: {e}",
            file=sys.stderr,
        )
        return False


def _check_homebrew():
    """Checks if Homebrew is installed."""
    if shutil.which("brew") is None:
        print(
            "Homebrew is not installed. Homebrew is required to install FFmpeg.",
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
        return True

    print("FFmpeg not found.")
    if not _check_homebrew():
        return False

    print("Attempting to install FFmpeg via Homebrew...")
    try:
        # Use subprocess.run to capture output/errors better
        result = subprocess.run(
            ["brew", "install", "ffmpeg"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            print("FFmpeg installed successfully!")
            # Verify installation
            if shutil.which("ffmpeg"):
                return True
            else:
                print(
                    "FFmpeg installed, but not found in PATH. Please check your Homebrew setup.",
                    file=sys.stderr,
                )
                return False
        else:
            print(f"Failed to install FFmpeg using Homebrew.", file=sys.stderr)
            print(f"Stderr:\n{result.stderr}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"An error occurred while trying to install FFmpeg: {e}", file=sys.stderr)
        return False


# --- Initial FFmpeg Check ---
if not _check_and_install_ffmpeg():
    print(
        "FFmpeg is required for merging video and audio, but could not be installed.",
        file=sys.stderr,
    )
    print(
        "Please install FFmpeg manually (e.g., 'brew install ffmpeg') and try again.",
        file=sys.stderr,
    )
    sys.exit(1)


# --- Python Package Imports ---
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
        # MofNCompleteColumn, # Not easily applicable with yt-dlp's output
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
    import yt_dlp  # Check if yt-dlp is importable

except ImportError:
    print("Required Python packages are missing.")
    if _install_dependencies():
        print("Attempting to reload modules...")
        # Try importing again after installation
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

            print("Modules loaded successfully after installation.")
        except ImportError as e:
            print(
                f"Still failed to import modules after installation attempt: {e}",
                file=sys.stderr,
            )
            print(
                "Please check your Python environment and permissions.", file=sys.stderr
            )
            sys.exit(1)
    else:
        # Installation failed
        sys.exit(1)


# --- Global Configuration & Initialization ---
install_rich_traceback(show_locals=True)
console = Console()

APP_NAME = "pytube.py"
APP_TITLE = "The MacOS YouTube Downloader"
VERSION = "1.2.1"  # Version bump for fix
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "PyTube")
CONFIG_DIR = os.path.expanduser(
    "~/.config/pytube_downloader"
)  # Changed config dir name
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
DEFAULT_TIMEOUT = 120  # For general subprocess calls if needed


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

    # Corrected Method: Removed style from TaskProgressColumn and TransferSpeedColumn
    @classmethod
    def get_progress_columns(cls):
        """
        Returns columns for Rich Progress specific to yt-dlp output style.
        NOTE: Removed 'style' from TaskProgressColumn and TransferSpeedColumn
              for compatibility with older Rich versions where it wasn't accepted.
              Styling for these columns might revert to defaults in some versions.
        """
        return [
            SpinnerColumn(spinner_name="dots", style=f"bold {cls.FROST_1}"),
            TextColumn(f"[bold {cls.FROST_2}]{{task.description}}[/]"),
            BarColumn(
                bar_width=None,
                style=cls.POLAR_NIGHT_3,  # Base bar style
                complete_style=cls.FROST_2,  # Completed part style
                finished_style=cls.GREEN,  # Finished bar style
            ),
            # TaskProgressColumn(style=cls.SNOW_STORM_1), # Removed style for compatibility
            TaskProgressColumn(),  # Use default style
            # TransferSpeedColumn(style=cls.FROST_3), # Removed style for compatibility
            TransferSpeedColumn(),  # Use default style
            TimeRemainingColumn(compact=True),  # No style needed/accepted
        ]


# --- Data Classes ---
@dataclass
class AppConfig:
    """Stores application configuration."""

    default_download_dir: str = DEFAULT_DOWNLOAD_DIR
    recent_urls: List[str] = field(default_factory=list)  # Renamed for clarity
    theme: str = "nord"  # Keep theme, though only Nord is implemented here
    max_recent_urls: int = 20  # Limit history size

    def save(self):
        """Saves configuration to JSON file."""
        ensure_config_directory()
        try:
            # Prune recent URLs list
            self.recent_urls = self.recent_urls[: self.max_recent_urls]
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.__dict__, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print_error(f"Failed to save configuration: {e}")

    @classmethod
    def load(cls):
        """Loads configuration from JSON file or returns default."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Ensure all expected fields exist, using defaults if not
                loaded_config = cls()
                for key, value in data.items():
                    if hasattr(loaded_config, key):
                        setattr(loaded_config, key, value)
                return loaded_config
        except json.JSONDecodeError as e:
            print_error(f"Failed to decode configuration file {CONFIG_FILE}: {e}")
            print_warning("Using default configuration.")
        except Exception as e:
            print_error(f"Failed to load configuration: {e}")
            print_warning("Using default configuration.")
        return cls()  # Return default config on any error


@dataclass
class DownloadHistoryEntry:
    """Represents a single entry in the download history."""

    url: str
    filename: str
    path: str
    size: int
    success: bool
    date: str
    elapsed_time: float
    download_type: str  # 'combined', 'video', 'audio'


@dataclass
class DownloadHistory:
    """Manages the download history."""

    entries: List[DownloadHistoryEntry] = field(default_factory=list)
    max_history_size: int = 50

    def add_entry(
        self,
        url: str,
        filename: str,
        output_path: str,
        size: int,
        success: bool,
        elapsed_time: float,
        download_type: str,
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
        # Prune old entries
        self.entries = self.entries[: self.max_history_size]
        self.save()

    def save(self):
        """Saves download history to JSON file."""
        ensure_config_directory()
        try:
            # Convert list of dataclass objects to list of dicts for JSON
            history_data = [entry.__dict__ for entry in self.entries]
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump({"history": history_data}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print_error(f"Failed to save history: {e}")

    @classmethod
    def load(cls):
        """Loads download history from JSON file or returns default."""
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Convert list of dicts back to list of dataclass objects
                history_list = [
                    DownloadHistoryEntry(**entry_data)
                    for entry_data in data.get("history", [])
                ]
                return cls(entries=history_list)
        except json.JSONDecodeError as e:
            print_error(f"Failed to decode history file {HISTORY_FILE}: {e}")
            print_warning("Using empty download history.")
        except Exception as e:
            print_error(f"Failed to load history: {e}")
            print_warning("Using empty download history.")
        return cls()


# --- Utility Functions ---
def clear_screen():
    """Clears the terminal screen."""
    console.clear()


def create_header() -> Panel:
    """Creates the application header panel using PyFiglet and Rich."""
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)  # Adjust width for padding/borders

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
def format_size(num_bytes: Union[int, float]) -> str:
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
            minutes, remaining_seconds = divmod(seconds, 60)
            return f"{int(minutes)}m {int(remaining_seconds)}s"
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
def ensure_config_directory():
    """Creates the configuration directory if it doesn't exist."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory '{CONFIG_DIR}': {e}")


def ensure_directory(path: str):
    """Creates a directory if it doesn't exist, raising errors."""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        raise


def run_command(
    cmd: List[str],
    check: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> Optional[subprocess.CompletedProcess]:
    """Runs a shell command using subprocess, with optional progress display."""
    try:
        if verbose:
            print_step(f"Executing: {' '.join(cmd)}")

        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Running command..."),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Executing", total=None)
            result = subprocess.run(
                cmd, check=check, text=True, capture_output=True, timeout=timeout
            )
        if verbose and result.stdout:
            console.print(f"[dim]Stdout: {result.stdout.strip()}[/dim]")
        if result.stderr and result.returncode != 0:
            console.print(f"[bold {NordColors.RED}]Stderr: {result.stderr.strip()}[/]")

        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if verbose and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        if check:
            raise
        return None
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        if check:
            raise
        return None
    except FileNotFoundError:
        print_error(f"Command not found: {cmd[0]}")
        if check:
            raise
        return None
    except Exception as e:
        print_error(f"Error executing command {' '.join(cmd)}: {e}")
        if check:
            raise
        return None


# --- Core Download Logic ---


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
        True if download succeeded, False otherwise.
    """
    start_time = time.time()  # Define start_time early for error handling
    try:
        ensure_directory(output_dir)

        output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
        cmd = ["yt-dlp", "--no-playlist"]
        format_string = ""
        info_panel_details = f"URL: {url}\n"

        if download_type == "audio":
            format_string = "bestaudio[ext=m4a]/bestaudio/best"
            cmd.extend(["-f", format_string, "-x", "--audio-format", "mp3"])
            info_panel_details += "Type: Audio Only (MP3)\n"
            output_template = os.path.join(output_dir, "%(title)s.mp3")
        elif download_type == "video":
            format_string = "bestvideo[ext=mp4]/bestvideo/best"
            cmd.extend(["-f", format_string])
            info_panel_details += (
                "Type: Video Only (Highest Quality)\nFormat: MP4/WebM/MKV\n"
            )
        else:  # 'combined'
            format_string = (
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            )
            cmd.extend(["-f", format_string, "--merge-output-format", "mp4"])
            info_panel_details += (
                "Type: Combined Video+Audio (Highest Quality)\nFormat: MP4 (merged)\n"
            )

        cmd.extend(["-o", output_template, "--newline"])
        if verbose:
            cmd.append("-v")
        cmd.append(url)

        info_panel_details += f"Destination: {output_dir}"
        display_panel("YouTube Download", info_panel_details, NordColors.FROST_2)

        last_found_filename = "downloaded_file"  # Placeholder

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        # Use Rich Progress with corrected columns
        with Progress(
            *NordColors.get_progress_columns(), console=console, transient=True
        ) as progress:
            download_task = progress.add_task("Initializing...", total=1000)

            current_percent = 0.0
            description = "Starting..."

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if not line:
                    time.sleep(0.05)
                    continue

                line = line.strip()
                if verbose and line:
                    console.log(f"[dim]yt-dlp: {line}[/dim]")

                if "[download]" in line:
                    if "%" in line:
                        try:
                            parts = line.split()
                            for i, part in enumerate(parts):
                                if "%" in part:
                                    percent_str = part.replace("%", "")
                                    if "\x1b" in percent_str:
                                        percent_str = percent_str.split("\x1b")[
                                            -1
                                        ].split("m")[-1]
                                    current_percent = float(percent_str)
                                    description = line
                                    if "Destination:" in line:
                                        try:
                                            last_found_filename = os.path.basename(
                                                line.split("Destination:")[1].strip()
                                            )
                                        except IndexError:
                                            pass
                                    break
                        except (ValueError, IndexError) as parse_err:
                            if verbose:
                                print_warning(
                                    f"Couldn't parse percentage: {line} ({parse_err})"
                                )
                            current_percent = min(current_percent + 0.1, 99.9)
                    elif "Destination:" in line:
                        try:
                            last_found_filename = os.path.basename(
                                line.split("Destination:")[1].strip()
                            )
                            description = f"Downloading: {last_found_filename}"
                        except IndexError:
                            pass
                    elif "has already been downloaded" in line:
                        description = "File already downloaded"
                        current_percent = 100.0
                        try:
                            filepath_part = (
                                line.split("]")[1].strip().split(" has already been")[0]
                            )
                            last_found_filename = os.path.basename(filepath_part)
                        except Exception:
                            pass
                    else:
                        description = line

                elif "[ExtractAudio]" in line or "Extracting audio" in line:
                    description = "Extracting Audio..."
                    current_percent = max(current_percent, 95.0)
                elif "[Merger]" in line or "Merging formats into" in line:
                    description = "Merging Formats..."
                    current_percent = max(current_percent, 98.0)
                    try:
                        if "Merging formats into" in line:
                            filepath_part = (
                                line.split("Merging formats into")[-1]
                                .strip()
                                .strip('"')
                            )
                            last_found_filename = os.path.basename(filepath_part)
                    except Exception:
                        pass
                elif "[FixupM3u8]" in line:
                    description = "Fixing M3U8..."
                    current_percent = max(current_percent, 90.0)
                elif "[ffmpeg]" in line:
                    description = "Processing (FFmpeg)..."
                    current_percent = max(current_percent, 97.0)

                progress.update(
                    download_task,
                    completed=current_percent * 10,
                    description=description[: console.width - 40],
                )

            process.wait()
            return_code = process.returncode
            end_time = time.time()
            download_time = end_time - start_time

            if return_code == 0:
                progress.update(
                    download_task,
                    completed=1000,
                    description="[green]Download Complete[/]",
                )
                time.sleep(0.5)

                downloaded_file_path = None
                scan_start_time = (
                    start_time - 10
                )  # Use start_time defined outside the block
                newest_time = scan_start_time
                potential_filename = last_found_filename

                expected_path = os.path.join(output_dir, potential_filename)
                # Check existence and modification time relative to scan_start_time
                if os.path.exists(expected_path):
                    try:
                        if os.path.getmtime(expected_path) > scan_start_time:
                            downloaded_file_path = expected_path
                            newest_time = os.path.getmtime(
                                expected_path
                            )  # Update newest_time
                    except OSError:
                        pass  # Ignore potential errors reading mtime

                # Scan directory if expected path wasn't found or wasn't recent enough
                if not downloaded_file_path:
                    print_info("Verifying downloaded file...")
                    possible_extensions = (
                        ".mp4",
                        ".mkv",
                        ".webm",
                        ".mp3",
                        ".m4a",
                        ".opus",
                    )
                    for f in os.listdir(output_dir):
                        if f.endswith(possible_extensions):
                            file_path = os.path.join(output_dir, f)
                            try:
                                file_mod_time = os.path.getmtime(file_path)
                                # Ensure file is recent and newer than any other recent file found so far
                                if (
                                    file_mod_time > scan_start_time
                                    and file_mod_time > newest_time
                                ):
                                    newest_time = file_mod_time
                                    downloaded_file_path = file_path
                            except OSError:
                                continue

                if downloaded_file_path and os.path.exists(downloaded_file_path):
                    final_filename = os.path.basename(downloaded_file_path)
                    file_size = os.path.getsize(downloaded_file_path)

                    history = DownloadHistory.load()
                    history.add_entry(
                        url=url,
                        filename=final_filename,
                        output_path=downloaded_file_path,
                        size=file_size,
                        success=True,
                        elapsed_time=download_time,
                        download_type=download_type,
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
                    print_warning(
                        "yt-dlp reported success, but the downloaded file could not be located."
                    )
                    history = DownloadHistory.load()
                    history.add_entry(
                        url=url,
                        filename=potential_filename,
                        output_path=output_dir,
                        size=0,
                        success=False,
                        elapsed_time=download_time,
                        download_type=download_type,
                    )
                    return False
            else:
                progress.update(
                    download_task,
                    completed=current_percent * 10,
                    description="[red]Download Failed[/]",
                )
                time.sleep(0.5)
                display_panel(
                    "YouTube Download Failed",
                    f"❌ yt-dlp exited with error code {return_code}\n"
                    f"🔗 URL: {url}\n"
                    f"⁉️ Check logs above for details.",
                    NordColors.RED,
                )
                history = DownloadHistory.load()
                history.add_entry(
                    url=url,
                    filename=last_found_filename,
                    output_path=output_dir,
                    size=0,
                    success=False,
                    elapsed_time=download_time,
                    download_type=download_type,
                )
                return False

    except FileNotFoundError:
        print_error("yt-dlp command not found. Is it installed and in your PATH?")
        history = DownloadHistory.load()
        history.add_entry(
            url=url,
            filename="error",
            output_path=output_dir,
            size=0,
            success=False,
            elapsed_time=time.time() - start_time,
            download_type=download_type,
        )
        return False
    except Exception as e:
        print_error(f"An unexpected error occurred during YouTube download: {e}")
        if verbose:
            console.print_exception(show_locals=True)
        history = DownloadHistory.load()
        history.add_entry(
            url=url,
            filename="error",
            output_path=output_dir,
            size=0,
            success=False,
            elapsed_time=time.time() - start_time,
            download_type=download_type,
        )
        return False


# --- Signal Handling and Cleanup ---
def cleanup():
    """Performs cleanup actions before exiting."""
    try:
        print_message("Exiting...", NordColors.FROST_3)
    except Exception as e:
        print(f"Error during cleanup: {e}", file=sys.stderr)


def signal_handler(sig, frame):
    """Handles termination signals gracefully."""
    try:
        sig_int = int(sig)
        sig_name = (
            signal.Signals(sig_int).name
            if sig_int in signal.Signals._value2member_map_
            else f"Signal {sig_int}"
        )
        print_warning(f"\nProcess interrupted by {sig_name}. Cleaning up...")
    except Exception:  # Fallback if signal conversion fails
        print_warning(f"\nProcess interrupted by signal {sig}. Cleaning up...")
    # atexit will handle cleanup
    sys.exit(
        128 + sig_int if isinstance(sig, int) else 1
    )  # Standard exit code for signals


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
    try:  # Ensure history file path exists
        ensure_config_directory()
        history_path = os.path.join(CONFIG_DIR, "youtube_url_history.txt")
        history = FileHistory(history_path)
    except Exception as e:
        print_warning(f"Could not load/create URL history file: {e}")
        history = None  # Disable history if it fails

    url_completer = WordCompleter(config.recent_urls, sentence=True)

    url = pt_prompt(
        "Enter the YouTube URL: ",
        history=history,
        completer=url_completer,
        style=PTStyle.from_dict({"prompt": f"bold {NordColors.FROST_2}"}),
        validator=None,
        validate_while_typing=False,
    ).strip()

    if not url:
        print_error("URL cannot be empty.")
        Prompt.ask("[dim]Press Enter to return to main menu...[/dim]")
        return

    download_type_options = [
        ("1", "Combined", "Video + Audio (Best Quality MP4) [Default]"),
        ("2", "Video Only", "Video Only (Best Quality MP4/WebM)"),
        ("3", "Audio Only", "Audio Only (Best Quality MP3)"),
    ]
    console.print(create_menu_table("Select Download Type", download_type_options))
    type_choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="1")

    download_type = "combined"
    if type_choice == "2":
        download_type = "video"
    elif type_choice == "3":
        download_type = "audio"

    output_dir = Prompt.ask(
        "Enter output directory",
        default=config.default_download_dir,
    )
    output_dir = os.path.expanduser(output_dir)

    verbose = Confirm.ask("Enable verbose mode (for debugging)?", default=False)

    success = download_youtube(url, output_dir, download_type, verbose)

    if success or Confirm.ask(
        "Add URL to recent list even if download failed?", default=False
    ):
        if url not in config.recent_urls:
            config.recent_urls.insert(0, url)
            config.save()

    Prompt.ask("[dim]Press Enter to return to main menu...[/dim]")


def view_download_history():
    """Displays the download history and allows interaction."""
    clear_screen()
    console.print(create_header())
    history = DownloadHistory.load()

    if not history.entries:
        display_panel(
            "Download History", "No download history found.", NordColors.FROST_3
        )
        Prompt.ask("[dim]Press Enter to return to settings menu...[/dim]")
        return

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
    table.add_column("Filename", style=NordColors.SNOW_STORM_1, overflow="fold")
    table.add_column("Size", style=NordColors.FROST_3, justify="right", width=10)
    table.add_column("Status", style=NordColors.FROST_4, width=8)

    displayed_entries = history.entries[:15]
    for i, entry in enumerate(displayed_entries, 1):
        try:
            if entry.date:
                date_obj = datetime.fromisoformat(entry.date)
                date_str = date_obj.strftime("%Y-%m-%d %H:%M")
            else:
                date_str = "No Date"
        except (ValueError, TypeError):
            date_str = "Invalid Date"

        status = "[green]Success[/]" if entry.success else "[red]Failed[/]"
        dl_type = entry.download_type[:7] if entry.download_type else "N/A"

        table.add_row(
            str(i),
            date_str,
            dl_type.capitalize(),
            entry.filename or "N/A",
            format_size(entry.size) if entry.size is not None else "N/A",
            Text.from_markup(status),
        )
    console.print(table)

    options = [
        ("1", "View Details", "Show full details for a specific download"),
        ("2", "Clear History", "Delete all download history entries"),
        ("3", "Return", "Go back to the settings menu"),
    ]
    console.print(create_menu_table("History Options", options))
    choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="3")

    if choice == "1":
        if not displayed_entries:
            print_warning("No history entries to view details for.")
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
                        if entry.date:
                            date_obj = datetime.fromisoformat(entry.date)
                            date_str_full = date_obj.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            date_str_full = "No Date"
                    except (ValueError, TypeError):
                        date_str_full = "Invalid Date"

                    details_text = (
                        f"URL: {entry.url or 'N/A'}\n"
                        f"Filename: {entry.filename or 'N/A'}\n"
                        f"Path: {entry.path or 'N/A'}\n"
                        f"Type: {(entry.download_type or 'N/A').capitalize()}\n"
                        f"Size: {format_size(entry.size) if entry.size is not None else 'N/A'}\n"
                        f"Status: {'Successful' if entry.success else 'Failed'}\n"
                        f"Date: {date_str_full}\n"
                        f"Download Time: {format_time(entry.elapsed_time) if entry.elapsed_time is not None else 'N/A'}"
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

    elif choice == "2":
        if Confirm.ask(
            "[bold red]Are you sure you want to clear ALL download history? This cannot be undone.[/]",
            default=False,
        ):
            history.entries = []
            history.save()
            print_success("Download history cleared.")
            time.sleep(1)

    if choice != "3":
        if choice == "1":
            Prompt.ask("[dim]Press Enter to return to history menu...[/dim]")
        view_download_history()


def settings_menu():
    """Displays and manages application settings."""
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
            "View Recent URLs",
            f"{len(config.recent_urls)} URLs stored (max {config.max_recent_urls})",
        ),
        ("3", "View Download History", "View and manage past downloads"),
        ("4", "Check Dependencies", "Verify yt-dlp and FFmpeg"),
        ("5", "Application Info", "View app details and system info"),
        ("6", "Return", "Go back to the main menu"),
    ]

    console.print(create_menu_table("Settings Options", settings_options))
    choice = Prompt.ask(
        "Select option", choices=[str(i) for i in range(1, 7)], default="6"
    )

    action_taken = False

    if choice == "1":
        action_taken = True
        new_dir = Prompt.ask(
            "Enter new default download directory", default=config.default_download_dir
        )
        new_dir = os.path.expanduser(new_dir)

        if os.path.abspath(new_dir) == os.path.abspath(config.default_download_dir):
            print_info("Directory is already set to this value.")
        elif os.path.isdir(new_dir):
            config.default_download_dir = new_dir
            config.save()
            print_success(f"Default download directory updated to: {new_dir}")
        elif Confirm.ask(
            f"Directory '{new_dir}' doesn't exist. Create it?", default=True
        ):
            try:
                ensure_directory(new_dir)
                config.default_download_dir = new_dir
                config.save()
                print_success(f"Created and set default download directory: {new_dir}")
            except Exception as e:
                print_error(f"Failed to create directory: {e}")
        else:
            print_warning("Directory change cancelled.")

    elif choice == "2":
        action_taken = True
        if config.recent_urls:
            recent_table = Table(
                show_header=True,
                header_style=NordColors.HEADER,
                title="Recent URLs (Most Recent First)",
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

    elif choice == "3":
        view_download_history()

    elif choice == "4":
        action_taken = True
        print_step("Checking required dependencies...")
        dependencies = {"yt-dlp": None, "ffmpeg": None}
        missing_deps = []

        try:
            result = run_command(["yt-dlp", "--version"], check=False, verbose=False)
            if result and result.returncode == 0:
                dependencies["yt-dlp"] = result.stdout.strip()
            else:
                missing_deps.append("yt-dlp")
                dependencies["yt-dlp"] = "[red]Missing[/]"
        except FileNotFoundError:
            missing_deps.append("yt-dlp")
            dependencies["yt-dlp"] = "[red]Missing[/]"
        except Exception as e:
            dependencies["yt-dlp"] = f"[yellow]Error checking ({e})[/]"

        if shutil.which("ffmpeg"):
            try:
                result = run_command(["ffmpeg", "-version"], check=False, verbose=False)
                if result and result.returncode == 0:
                    version_line = result.stdout.split("\n")[0]
                    version = (
                        version_line.split(" version ")[1].split(" ")[0]
                        if " version " in version_line
                        else "Unknown"
                    )
                    dependencies["ffmpeg"] = version
                else:
                    dependencies["ffmpeg"] = "[yellow]Found (version check failed)[/]"
            except Exception as e:
                dependencies["ffmpeg"] = f"[yellow]Found (Error checking: {e})[/]"
        else:
            missing_deps.append("ffmpeg")
            dependencies["ffmpeg"] = "[red]Missing[/]"

        dep_table = Table(
            show_header=True,
            header_style=NordColors.HEADER,
            title="Dependency Status",
            box=ROUNDED,
            border_style=NordColors.FROST_3,
        )
        dep_table.add_column("Dependency", style=NordColors.FROST_1)
        dep_table.add_column("Status / Version", style=NordColors.SNOW_STORM_1)

        dep_table.add_row(
            "yt-dlp", Text.from_markup(dependencies["yt-dlp"] or "[yellow]Unknown[/]")
        )
        dep_table.add_row(
            "FFmpeg", Text.from_markup(dependencies["ffmpeg"] or "[yellow]Unknown[/]")
        )
        console.print(dep_table)

        if missing_deps:
            print_warning(f"Missing dependencies: {', '.join(missing_deps)}")
            if "yt-dlp" in missing_deps:
                print_info(
                    "You can try installing yt-dlp using: pip install --user yt-dlp"
                )
            if "ffmpeg" in missing_deps:
                print_info(
                    "You can try installing FFmpeg using Homebrew: brew install ffmpeg"
                )
        else:
            print_success("All required dependencies are installed.")

    elif choice == "5":
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
            [f"[bold {NordColors.FROST_4}]{k}:[/] {v}" for k, v in system_info.items()]
        )
        display_panel(
            "Application Information",
            Text.from_markup(info_content),
            NordColors.FROST_2,
        )

    if action_taken:
        Prompt.ask("[dim]Press Enter to return to settings menu...[/dim]")
        settings_menu()


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

        try:
            config = AppConfig.load()
            history = DownloadHistory.load()
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
            clear_screen()
            console.print(
                Panel(
                    Text.from_markup(
                        f"[bold {NordColors.FROST_1}]Thank you for using {APP_NAME}! ({APP_TITLE})[/]\n\n"
                        f"[ {NordColors.SNOW_STORM_1}]Exiting gracefully...[/]"
                    ),
                    title="Goodbye!",
                    title_align="center",
                    border_style=NordColors.FROST_2,
                    box=HEAVY,
                    padding=(2, 4),
                )
            )
            break


# --- Main Execution ---
def main():
    """Main function to initialize and run the application."""
    try:
        clear_screen()
        console.print(create_header())

        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Initializing {APP_NAME}..."),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("startup", total=3)
            ensure_config_directory()
            progress.advance(task)
            AppConfig.load()
            progress.advance(task)
            DownloadHistory.load()
            progress.advance(task)
            time.sleep(0.3)

        main_menu()

    except KeyboardInterrupt:
        # Signal handler handles the message
        sys.exit(130)

    except Exception as e:
        print_error(f"An unexpected critical error occurred: {e}")
        console.print_exception(show_locals=True)
        print_step("The application will now exit.")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
