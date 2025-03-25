# Please review the following script thoroughly. This reference script serves as the comprehensive template for all future Python scripts you generate on my behalf. All scripts must strictly adhere to the structure, style, and best practices demonstrated below, optimized for macOS environments. Do not generate or write any code or respond in any way other than acknowledging you understand the below code and what you can help me with

```python
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
VERSION = "1.2.0"  # Updated version
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

    @classmethod
    def get_progress_columns(cls):
        """Returns columns for Rich Progress specific to yt-dlp output style."""
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
            # MofNCompleteColumn(), # Not reliably parseable from yt-dlp
            TransferSpeedColumn(style=cls.FROST_3),
            TimeRemainingColumn(compact=True),
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
    # Use rich's clear method for better cross-platform compatibility if needed later
    # os.system('cls' if os.name == 'nt' else 'clear')
    console.clear()


def create_header() -> Panel:
    """Creates the application header panel using PyFiglet and Rich."""
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)  # Adjust width for padding/borders

    # Try different fonts for the Figlet header
    fonts = ["slant", "small_slant", "standard", "digital", "small"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=adjusted_width)
            ascii_art = fig.renderText(APP_NAME)
            if (
                ascii_art.strip() and len(ascii_art.splitlines()) > 1
            ):  # Ensure non-empty art
                break
        except Exception:
            continue
    # Fallback if no font worked
    if not ascii_art.strip():
        ascii_art = APP_NAME

    # Apply Nord color gradient to the ASCII art lines
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    frost_colors = NordColors.get_frost_gradient(min(len(ascii_lines), 4))
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = frost_colors[i % len(frost_colors)]
        escaped_line = line.replace("[", r"\[").replace(
            "]", r"\]"
        )  # Escape Rich markup
        styled_text += f"[bold {color}]{escaped_line}[/]\n"

    # Create the panel
    panel = Panel(
        Text.from_markup(styled_text.strip()),
        border_style=NordColors.FROST_1,
        box=NordColors.NORD_BOX,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_3}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_TITLE}[/]",
        subtitle_align="center",
        width=adjusted_width,  # Set panel width
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


def display_panel(title: str, message: str, style: Union[Style, str] = NordColors.INFO):
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
        expand=True,  # Allow table to expand to console width
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
        # Allow script to continue if possible, config/history saving will just fail
        # sys.exit(1) # Optionally exit if config dir is critical


def ensure_directory(path: str):
    """Creates a directory if it doesn't exist, raising errors."""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        raise  # Re-raise the exception to halt the process relying on this dir


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

        # Use a simple spinner for quick commands
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
        if (
            result.stderr and result.returncode != 0
        ):  # Only show stderr on error by default
            console.print(f"[bold {NordColors.RED}]Stderr: {result.stderr.strip()}[/]")

        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if verbose and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        if check:
            raise  # Re-raise if check=True
        return None  # Return None if check=False and it failed
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
    try:
        ensure_directory(output_dir)

        # --- Configure yt-dlp command based on download_type ---
        output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
        cmd = [
            "yt-dlp",
            "--no-playlist",
        ]  # Default args, prevent downloading whole playlists by default
        format_string = ""
        info_panel_details = f"URL: {url}\n"

        if download_type == "audio":
            format_string = "bestaudio[ext=m4a]/bestaudio/best"  # Prefer m4a, fallback
            cmd.extend(["-f", format_string, "-x", "--audio-format", "mp3"])
            info_panel_details += "Type: Audio Only (MP3)\n"
            output_template = os.path.join(
                output_dir, "%(title)s.mp3"
            )  # Explicitly set mp3 extension
        elif download_type == "video":
            format_string = (
                "bestvideo[ext=mp4]/bestvideo/best"  # Prefer mp4 video, fallback
            )
            cmd.extend(["-f", format_string])
            info_panel_details += (
                "Type: Video Only (Highest Quality)\nFormat: MP4/WebM/MKV\n"
            )
        else:  # 'combined' (default)
            # Prefer mp4 video + m4a audio, fallback to best available video+audio, then best overall
            format_string = (
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            )
            cmd.extend(["-f", format_string, "--merge-output-format", "mp4"])
            info_panel_details += (
                "Type: Combined Video+Audio (Highest Quality)\nFormat: MP4 (merged)\n"
            )

        cmd.extend(
            ["-o", output_template, "--newline"]
        )  # Use newline for better parsing
        if verbose:
            cmd.append("-v")
            # Also print cookies info if available/needed for private videos
            # cmd.extend(["--cookies-from-browser", "chrome"]) # Example
        cmd.append(url)  # Add URL at the end

        info_panel_details += f"Destination: {output_dir}"
        display_panel("YouTube Download", info_panel_details, NordColors.FROST_2)

        start_time = time.time()
        last_found_filename = "downloaded_file"  # Placeholder

        # --- Execute yt-dlp and parse progress ---
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Redirect stderr to stdout
            text=True,
            encoding="utf-8",  # Ensure correct decoding
            errors="replace",  # Replace chars that can't be decoded
            bufsize=1,  # Line buffered
        )

        # Use Rich Progress to display download status
        with Progress(
            *NordColors.get_progress_columns(), console=console, transient=True
        ) as progress:
            # Add a single task representing the overall download
            download_task = progress.add_task(
                "Initializing...", total=1000
            )  # Use 1000 steps for finer % granularity

            current_percent = 0.0
            description = "Starting..."

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break  # Process finished
                if not line:
                    time.sleep(0.05)  # Avoid busy-waiting
                    continue

                line = line.strip()
                if verbose and line:
                    console.log(
                        f"[dim]yt-dlp: {line}[/dim]"
                    )  # Log verbose output dimmed

                # --- Parse yt-dlp output for progress and status ---
                if "[download]" in line:
                    if "%" in line:
                        try:
                            # Extract percentage (handle potential variations in output)
                            parts = line.split()
                            for i, part in enumerate(parts):
                                if "%" in part:
                                    percent_str = part.replace("%", "")
                                    # Handle potential color codes before the number
                                    if "\x1b" in percent_str:
                                        percent_str = percent_str.split("\x1b")[
                                            -1
                                        ].split("m")[-1]
                                    current_percent = float(percent_str)
                                    description = line  # Show the full download line
                                    # Try to get filename if available in the same line
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
                            # Advance progress slightly even if parsing fails
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
                        current_percent = 100.0  # Mark as complete
                        try:
                            # Example: [download] /path/to/video.mp4 has already been downloaded
                            filepath_part = (
                                line.split("]")[1].strip().split(" has already been")[0]
                            )
                            last_found_filename = os.path.basename(filepath_part)
                        except Exception:
                            pass
                    else:
                        # Show other [download] messages like pre-processing
                        description = line

                elif "[ExtractAudio]" in line or "Extracting audio" in line:
                    description = "Extracting Audio..."
                    current_percent = max(
                        current_percent, 95.0
                    )  # Assume near completion
                elif "[Merger]" in line or "Merging formats into" in line:
                    description = "Merging Formats..."
                    current_percent = max(
                        current_percent, 98.0
                    )  # Assume near completion
                    try:  # Try to get final filename from merge message
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
                elif "[ffmpeg]" in line:  # Generic ffmpeg messages
                    description = "Processing (FFmpeg)..."
                    current_percent = max(current_percent, 97.0)

                # Update the progress bar
                progress.update(
                    download_task,
                    completed=current_percent * 10,
                    description=description[: console.width - 40],
                )  # Truncate desc

            # --- Finalize Progress and Check Result ---
            process.wait()  # Ensure process is finished
            return_code = process.returncode
            end_time = time.time()
            download_time = end_time - start_time

            if return_code == 0:
                progress.update(
                    download_task,
                    completed=1000,
                    description="[green]Download Complete[/]",
                )
                time.sleep(0.5)  # Allow progress bar to show complete state

                # --- Find the downloaded file (yt-dlp might rename it) ---
                downloaded_file_path = None
                newest_time = (
                    start_time - 10
                )  # Look for files created/modified after start
                potential_filename = (
                    last_found_filename  # Start with the last known name
                )

                # Check specific expected path first
                expected_path = os.path.join(output_dir, potential_filename)
                if (
                    os.path.exists(expected_path)
                    and os.path.getmtime(expected_path) > newest_time
                ):
                    downloaded_file_path = expected_path
                else:
                    # If not found, scan the directory for the most recent relevant file
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
                                if file_mod_time > newest_time:
                                    newest_time = file_mod_time
                                    downloaded_file_path = file_path
                            except OSError:
                                continue  # Ignore permission errors etc.

                if downloaded_file_path and os.path.exists(downloaded_file_path):
                    final_filename = os.path.basename(downloaded_file_path)
                    file_size = os.path.getsize(downloaded_file_path)

                    # Add to history
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
                    # Success code 0 but file not found - unusual case
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
                # Download failed
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
                # Add failed entry to history
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
        return False
    except Exception as e:
        print_error(f"An unexpected error occurred during YouTube download: {e}")
        if verbose:
            console.print_exception(show_locals=True)
        # Add failed entry to history
        history = DownloadHistory.load()
        history.add_entry(
            url=url,
            filename="error",
            output_path=output_dir,
            size=0,
            success=False,
            elapsed_time=time.time() - start_time if "start_time" in locals() else 0,
            download_type=download_type,
        )
        return False


# --- Signal Handling and Cleanup ---
def cleanup():
    """Performs cleanup actions before exiting."""
    try:
        print_message("Exiting...", NordColors.FROST_3)
        # Config is saved implicitly by AppConfig.load() and then config.save() in menus
        # History is saved after each download attempt
    except Exception as e:
        # Avoid errors during cleanup itself
        print(f"Error during cleanup: {e}", file=sys.stderr)


def signal_handler(sig, frame):
    """Handles termination signals gracefully."""
    sig_name = signal.Signals(sig).name if sig in signal.Signals else f"Signal {sig}"
    print_warning(f"\nProcess interrupted by {sig_name}. Cleaning up...")
    # cleanup() # atexit will handle this
    sys.exit(128 + sig)  # Standard exit code for signals


signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Termination signal
atexit.register(cleanup)  # Register cleanup for normal exit

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
    history = FileHistory(os.path.join(CONFIG_DIR, "youtube_url_history.txt"))
    url_completer = WordCompleter(config.recent_urls, sentence=True)

    # Get URL
    url = pt_prompt(
        "Enter the YouTube URL: ",
        history=history,
        completer=url_completer,
        style=PTStyle.from_dict({"prompt": f"bold {NordColors.FROST_2}"}),
        # Basic validation - could be improved with regex
        validator=None,  # lambda text: text.startswith("http") and ("youtube.com" in text or "youtu.be" in text),
        validate_while_typing=False,
    ).strip()

    if not url:
        print_error("URL cannot be empty.")
        Prompt.ask("[dim]Press Enter to return to main menu...[/dim]")
        return

    # Get Download Type
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

    # Get Output Directory
    output_dir = Prompt.ask(
        "Enter output directory",
        default=config.default_download_dir,
        # Add path completion? Might be complex with prompt_toolkit
    )
    output_dir = os.path.expanduser(output_dir)  # Expand ~

    # Verbose Mode
    verbose = Confirm.ask("Enable verbose mode (for debugging)?", default=False)

    # Execute Download
    success = download_youtube(url, output_dir, download_type, verbose)

    # Update Recent URLs
    if success or Confirm.ask(
        "Add URL to recent list even if download failed?", default=False
    ):
        if url not in config.recent_urls:
            config.recent_urls.insert(0, url)
            config.save()  # Save config with updated recent list

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
        "Filename", style=NordColors.SNOW_STORM_1, overflow="fold"
    )  # Allow filename wrap
    table.add_column("Size", style=NordColors.FROST_3, justify="right", width=10)
    table.add_column("Status", style=NordColors.FROST_4, width=8)

    displayed_entries = history.entries[:15]  # Show max 15 entries initially
    for i, entry in enumerate(displayed_entries, 1):
        try:
            date_obj = datetime.fromisoformat(entry.date)
            date_str = date_obj.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            date_str = "Invalid Date"

        status = "[green]Success[/]" if entry.success else "[red]Failed[/]"
        dl_type = entry.download_type[:7]  # Truncate type if needed

        table.add_row(
            str(i),
            date_str,
            dl_type.capitalize(),
            entry.filename,
            format_size(entry.size),
            Text.from_markup(status),
        )
    console.print(table)

    # --- History Options Menu ---
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
            view_download_history()  # Re-show menu
            return

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
                    date_obj = datetime.fromisoformat(entry.date)
                    date_str_full = date_obj.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    date_str_full = "Invalid Date"

                details_text = (
                    f"URL: {entry.url}\n"
                    f"Filename: {entry.filename}\n"
                    f"Path: {entry.path}\n"
                    f"Type: {entry.download_type.capitalize()}\n"
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

    elif choice == "2":
        if Confirm.ask(
            "[bold red]Are you sure you want to clear ALL download history? This cannot be undone.[/]",
            default=False,
        ):
            history.entries = []
            history.save()
            print_success("Download history cleared.")
            time.sleep(1)  # Pause briefly

    # Loop back or return
    if choice != "3":
        if choice == "1":  # Pause after showing details
            Prompt.ask("[dim]Press Enter to return to history menu...[/dim]")
        view_download_history()  # Show history menu again


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

    action_taken = False  # Flag to decide whether to pause before re-displaying

    if choice == "1":
        action_taken = True
        new_dir = Prompt.ask(
            "Enter new default download directory", default=config.default_download_dir
        )
        new_dir = os.path.expanduser(new_dir)  # Expand ~ if present

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
                ensure_directory(new_dir)  # Uses os.makedirs
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
        view_download_history()  # This function handles its own loop/return

    elif choice == "4":
        action_taken = True
        print_step("Checking required dependencies...")
        dependencies = {"yt-dlp": None, "ffmpeg": None}  # Store version info
        missing_deps = []

        # Check yt-dlp
        try:
            # Use yt-dlp --version which is reliable
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

        # Check ffmpeg
        if shutil.which("ffmpeg"):
            try:
                result = run_command(["ffmpeg", "-version"], check=False, verbose=False)
                if result and result.returncode == 0:
                    # Extract version from the first line, e.g., "ffmpeg version 4.4.1 ..."
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

        # Display Status Table
        dep_table = Table(
            show_header=True,
            header_style=NordColors.HEADER,
            title="Dependency Status",
            box=ROUNDED,
            border_style=NordColors.FROST_3,
        )
        dep_table.add_column("Dependency", style=NordColors.FROST_1)
        dep_table.add_column("Status / Version", style=NordColors.SNOW_STORM_1)

        dep_table.add_row("yt-dlp", Text.from_markup(dependencies["yt-dlp"]))
        dep_table.add_row("FFmpeg", Text.from_markup(dependencies["ffmpeg"]))
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

    # Pause and loop back to settings menu if an action was taken, otherwise return
    if action_taken:
        Prompt.ask("[dim]Press Enter to return to settings menu...[/dim]")
        settings_menu()
    # If choice was 6 or 3 (history handled its return), this function will simply return


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

        # Optional: Show quick stats panel
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
                expand=False,  # Don't let it expand too much
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
            break  # Exit the while loop


# --- Main Execution ---
def main():
    """Main function to initialize and run the application."""
    try:
        clear_screen()
        console.print(create_header())

        # Brief startup sequence (optional)
        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Initializing {APP_NAME}..."),
            console=console,
            transient=True,  # Hide after completion
        ) as progress:
            task = progress.add_task("startup", total=3)
            ensure_config_directory()
            progress.advance(task)
            AppConfig.load()  # Load config early
            progress.advance(task)
            DownloadHistory.load()  # Load history early
            progress.advance(task)
            time.sleep(0.3)  # Short pause

        main_menu()

    except KeyboardInterrupt:
        # Signal handler already prints a message
        print_warning("Operation cancelled by user.")
        sys.exit(130)  # Standard exit code for Ctrl+C

    except Exception as e:
        print_error(f"An unexpected critical error occurred: {e}")
        # Use Rich traceback for detailed debugging if needed
        console.print_exception(show_locals=True)
        print_step("The application will now exit.")
        sys.exit(1)

    # cleanup() is registered with atexit, no need to call explicitly here
    sys.exit(0)  # Explicit successful exit


if __name__ == "__main__":
    main()
```
