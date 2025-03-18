#!/usr/bin/env python3
"""
macOS Downloader
--------------------------------------------------
A macOS-specific downloader for web files and YouTube videos.
Features:
  • Dynamic ASCII banners with Pyfiglet and Rich.
  • Interactive, menu-driven CLI with prompt_toolkit.
  • Dependency management using Homebrew (for ffmpeg) and pip.
  • High-quality file downloads with progress tracking.
  • YouTube downloads that always select the best video and audio
    streams and merge them into an MP4.
Version: 1.1.0
"""

import os
import sys
import time
import json
import signal
import shutil
import subprocess
import asyncio
import atexit
import urllib.parse
import platform
from dataclasses import dataclass, field
from typing import List, Optional, Any, Tuple, Dict, Union
from datetime import datetime

# Ensure we are running on macOS
if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)


# ----------------------------------------------------------------
# Dependency Check and Installation (macOS-specific)
# ----------------------------------------------------------------
def install_dependencies() -> None:
    """
    Install required Python packages using pip (with --user flag).
    Required packages: rich, pyfiglet, prompt_toolkit, requests, yt-dlp
    """
    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "requests", "yt-dlp"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER"))
    try:
        if os.geteuid() != 0:
            print(f"Installing dependencies for user: {user}")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--user"] + required_packages
            )
        else:
            print(f"Running as sudo. Installing dependencies for user: {user}")
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"]
                + required_packages
            )
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


def check_homebrew() -> None:
    """Ensure Homebrew is installed on macOS."""
    if shutil.which("brew") is None:
        print(
            "Homebrew is not installed. Please install Homebrew from https://brew.sh and rerun this script."
        )
        sys.exit(1)


def check_ffmpeg() -> bool:
    """
    Check if FFmpeg is installed. If missing, attempt to install it using Homebrew.
    """
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return True
    except Exception:
        print("FFmpeg not found. Attempting to install FFmpeg via Homebrew...")
        try:
            check_homebrew()
            subprocess.check_call(["brew", "install", "ffmpeg"])
            print("FFmpeg installed successfully!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to install FFmpeg: {e}")
            return False


# Attempt to import dependencies; install if missing.
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
        DownloadColumn,
        TransferSpeedColumn,
        MofNCompleteColumn,
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from rich.align import Align
    from rich.layout import Layout
    from rich.style import Style
    from rich.live import Live
    from rich.box import Box, ROUNDED, DOUBLE, HEAVY
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style as PTStyle
    import requests
except ImportError:
    print("Required libraries not found. Installing dependencies...")
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)

if not check_ffmpeg():
    print("FFmpeg is required but could not be installed. Exiting.")
    sys.exit(1)

install_rich_traceback(show_locals=True)
console: Console = Console()

# ----------------------------------------------------------------
# Configuration & Constants (macOS tailored)
# ----------------------------------------------------------------
APP_NAME: str = "macOS Downloader"
VERSION: str = "1.1.0"
DEFAULT_DOWNLOAD_DIR: str = os.path.join(os.path.expanduser("~"), "Downloads")
CONFIG_DIR: str = os.path.expanduser("~/.macos_downloader")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")
HISTORY_FILE: str = os.path.join(CONFIG_DIR, "history.json")
DOWNLOAD_TIMEOUT: int = 3600  # 1 hour timeout for downloads
DEFAULT_TIMEOUT: int = 120  # 2 minutes default timeout for commands
CHUNK_SIZE: int = 16384  # 16KB chunks for smoother progress updates


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    POLAR_NIGHT_1: str = "#2E3440"
    POLAR_NIGHT_2: str = "#3B4252"
    POLAR_NIGHT_3: str = "#434C5E"
    POLAR_NIGHT_4: str = "#4C566A"
    SNOW_STORM_1: str = "#D8DEE9"
    SNOW_STORM_2: str = "#E5E9F0"
    SNOW_STORM_3: str = "#ECEFF4"
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"
    RED: str = "#BF616A"
    ORANGE: str = "#D08770"
    YELLOW: str = "#EBCB8B"
    GREEN: str = "#A3BE8C"
    PURPLE: str = "#B48EAD"

    # Custom styles for enhanced UI
    SUCCESS: Style = Style(color=GREEN, bold=True)
    ERROR: Style = Style(color=RED, bold=True)
    WARNING: Style = Style(color=YELLOW, bold=True)
    INFO: Style = Style(color=FROST_2, bold=True)
    HEADER: Style = Style(color=FROST_1, bold=True)
    SUBHEADER: Style = Style(color=FROST_3, bold=True)
    ACCENT: Style = Style(color=FROST_4, bold=True)

    # Custom boxes for panels
    NORD_BOX = Box(
        "╭─",
        "─",
        "─╮",
        "│ ",
        " │",
        "╰─",
        "─",
        "─╯",
        "",
    )

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        return [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4][:steps]

    @classmethod
    def get_polar_gradient(cls, steps: int = 4) -> List[str]:
        return [
            cls.POLAR_NIGHT_1,
            cls.POLAR_NIGHT_2,
            cls.POLAR_NIGHT_3,
            cls.POLAR_NIGHT_4,
        ][:steps]

    @classmethod
    def get_progress_columns(cls) -> List[Any]:
        """Return consistently styled progress columns for all progress bars"""
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
            MofNCompleteColumn(style=cls.SNOW_STORM_1),
            TransferSpeedColumn(style=cls.FROST_3),
            TimeRemainingColumn(style=cls.FROST_4, compact=True),
        ]


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class DownloadSource:
    url: str
    name: str = ""
    size: int = 0
    content_type: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.get_filename_from_url()

    def get_filename_from_url(self) -> str:
        try:
            path = urllib.parse.urlsplit(self.url).path
            filename = os.path.basename(path)
            return urllib.parse.unquote(filename) if filename else "downloaded_file"
        except Exception:
            return "downloaded_file"

    def get_file_info(self) -> Dict[str, Any]:
        try:
            response = requests.head(self.url, timeout=10, allow_redirects=True)
            self.size = int(response.headers.get("content-length", 0))
            self.content_type = response.headers.get("content-type", "")

            # Try to get a better filename from Content-Disposition if available
            if "content-disposition" in response.headers:
                import re

                filename_match = re.search(
                    r'filename="?([^";]+)', response.headers["content-disposition"]
                )
                if filename_match and filename_match.group(1):
                    self.name = filename_match.group(1)

            return {
                "size": self.size,
                "content_type": self.content_type,
                "filename": self.name,
            }
        except Exception as e:
            print_error(f"Could not determine file info: {e}")
            return {"size": 0, "content_type": "", "filename": self.name}


@dataclass
class DownloadStats:
    bytes_downloaded: int = 0
    total_size: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    rate_history: List[float] = field(default_factory=list)
    last_update_time: float = field(default_factory=time.time)
    last_bytes: int = 0

    # For smoother rate calculation
    window_size: int = 20  # Keep last 20 rate samples
    smoothing_factor: float = 0.3  # For exponential moving average

    @property
    def is_complete(self) -> bool:
        return self.end_time is not None or (
            self.total_size > 0 and self.bytes_downloaded >= self.total_size
        )

    @property
    def progress_percentage(self) -> float:
        if self.total_size <= 0:
            return 0.0
        return min(100.0, (self.bytes_downloaded / self.total_size) * 100)

    @property
    def elapsed_time(self) -> float:
        return (self.end_time or time.time()) - self.start_time

    @property
    def average_rate(self) -> float:
        """Calculate smoothed download rate"""
        if not self.rate_history:
            if self.elapsed_time > 0:
                return self.bytes_downloaded / self.elapsed_time
            return 0.0

        # Return exponential moving average for smoother rate display
        if len(self.rate_history) >= 3:
            # Use more sophisticated calculation for smoother rates
            recent_rates = self.rate_history[-5:]
            # Remove outliers (rates that are more than 2x the median)
            median_rate = sorted(recent_rates)[len(recent_rates) // 2]
            filtered_rates = [r for r in recent_rates if r <= median_rate * 2.5]
            if filtered_rates:
                return sum(filtered_rates) / len(filtered_rates)

        return self.rate_history[-1]  # Return most recent rate

    @property
    def estimated_time_remaining(self) -> float:
        """Estimate time remaining to complete the download"""
        if self.is_complete:
            return 0.0

        if self.total_size <= 0 or self.average_rate <= 0:
            return float("inf")

        remaining_bytes = self.total_size - self.bytes_downloaded
        return remaining_bytes / self.average_rate

    def update_progress(self, new_bytes: int) -> None:
        """
        Update download progress with improved rate calculation.

        Args:
            new_bytes: Number of new bytes received since last update
        """
        now = time.time()
        time_diff = now - self.last_update_time

        if time_diff > 0.1:  # Only update if at least 100ms has passed
            self.bytes_downloaded += new_bytes
            current_rate = new_bytes / time_diff

            # Add to rate history with limit to window size
            self.rate_history.append(current_rate)
            if len(self.rate_history) > self.window_size:
                self.rate_history.pop(0)

            self.last_update_time = now
            self.last_bytes = new_bytes

            if self.total_size > 0 and self.bytes_downloaded >= self.total_size:
                self.bytes_downloaded = self.total_size
                self.end_time = now


@dataclass
class AppConfig:
    default_download_dir: str = DEFAULT_DOWNLOAD_DIR
    recent_downloads: List[str] = field(default_factory=list)
    theme: str = "dark"  # Default theme is dark nord
    language: str = "en"  # Default language is English
    max_concurrent_downloads: int = 1  # Default to single download at a time
    auto_close_completed: bool = False  # Don't auto close completed downloads

    def save(self) -> None:
        ensure_config_directory()
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.__dict__, f, indent=2)
        except Exception as e:
            print_error(f"Failed to save configuration: {e}")

    @classmethod
    def load(cls) -> "AppConfig":
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                return cls(**data)
        except Exception as e:
            print_error(f"Failed to load configuration: {e}")
        return cls()


@dataclass
class DownloadHistory:
    entries: List[Dict[str, Any]] = field(default_factory=list)

    def add_entry(
        self,
        url: str,
        filename: str,
        output_path: str,
        size: int,
        success: bool,
        elapsed_time: float,
    ) -> None:
        """Add a download to history"""
        entry = {
            "url": url,
            "filename": filename,
            "path": output_path,
            "size": size,
            "success": success,
            "date": datetime.now().isoformat(),
            "elapsed_time": elapsed_time,
        }
        self.entries.insert(0, entry)  # Add to beginning
        self.entries = self.entries[:50]  # Keep only the last 50 entries
        self.save()

    def save(self) -> None:
        """Save history to file"""
        ensure_config_directory()
        try:
            with open(HISTORY_FILE, "w") as f:
                json.dump({"history": self.entries}, f, indent=2)
        except Exception as e:
            print_error(f"Failed to save history: {e}")

    @classmethod
    def load(cls) -> "DownloadHistory":
        """Load history from file"""
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r") as f:
                    data = json.load(f)
                return cls(entries=data.get("history", []))
        except Exception as e:
            print_error(f"Failed to load history: {e}")
        return cls()


# ----------------------------------------------------------------
# Enhanced UI Functions
# ----------------------------------------------------------------
def clear_screen() -> None:
    """Clear the terminal screen"""
    console.clear()


def create_header() -> Panel:
    """Create an enhanced header with Nord theme styling"""
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)

    # Try different fonts for the ASCII art
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

    # Create gradient effect for header
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = frost_colors[i % len(frost_colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"

    # Add fancy borders
    border_style = NordColors.FROST_3
    border_char = "═"
    border_line = f"[{border_style}]{border_char * (adjusted_width - 8)}[/]"

    styled_text = border_line + "\n" + styled_text + border_line

    # Create the panel with enhanced styling
    panel = Panel(
        Text.from_markup(styled_text),
        border_style=NordColors.FROST_1,
        box=NordColors.NORD_BOX,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_3}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]High-Quality macOS File Downloader[/]",
        subtitle_align="center",
    )

    return panel


def print_message(
    text: str, style: Union[str, Style] = NordColors.INFO, prefix: str = "•"
) -> None:
    """Print a styled message to the console"""
    if isinstance(style, str):
        console.print(f"[{style}]{prefix} {text}[/{style}]")
    else:
        console.print(f"{prefix} {text}", style=style)


def print_error(message: str) -> None:
    """Print an error message"""
    print_message(message, NordColors.ERROR, "✗")


def print_success(message: str) -> None:
    """Print a success message"""
    print_message(message, NordColors.SUCCESS, "✓")


def print_warning(message: str) -> None:
    """Print a warning message"""
    print_message(message, NordColors.WARNING, "⚠")


def print_step(message: str) -> None:
    """Print a step message"""
    print_message(message, NordColors.INFO, "→")


def print_info(message: str) -> None:
    """Print an informational message"""
    print_message(message, NordColors.INFO, "ℹ")


def display_panel(
    title: str, message: str, style: Union[str, Style] = NordColors.INFO
) -> None:
    """Display a styled panel with content"""
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


def format_size(num_bytes: float) -> str:
    """Format byte size to human-readable format"""
    if num_bytes < 0:
        return "0 B"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            if num_bytes < 0.1 and unit != "B":
                return f"{num_bytes * 1024:.2f} {unit.replace('B', '')}B"
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def format_time(seconds: float) -> str:
    """Format seconds to human-readable time format"""
    if seconds < 0 or seconds == float("inf"):
        return "unknown"

    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        remaining_seconds = seconds % 60
        return f"{int(minutes)}m {int(remaining_seconds)}s"
    else:
        hours = seconds / 3600
        remaining_minutes = (seconds % 3600) / 60
        return f"{int(hours)}h {int(remaining_minutes)}m"


def create_menu_table(title: str, options: List[Tuple[str, str, str]]) -> Table:
    """Create a styled table for menu options"""
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


# ----------------------------------------------------------------
# Core Functionality
# ----------------------------------------------------------------
def ensure_config_directory() -> None:
    """Ensure the config directory exists"""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


def run_command(
    cmd: List[str],
    check: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """Run a shell command with proper handling"""
    try:
        if verbose:
            print_step(f"Executing: {' '.join(cmd)}")

        # Create a progress spinner for long-running commands
        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Running command..."),
            console=console,
        ) as progress:
            task = progress.add_task("", total=None)
            result = subprocess.run(
                cmd, check=check, text=True, capture_output=True, timeout=timeout
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


async def download_file_with_progress(url: str, output_path: str) -> bool:
    """
    Download a file with enhanced progress tracking and Nord-themed progress bar.

    Args:
        url: The URL to download
        output_path: Where to save the file

    Returns:
        bool: True if download succeeded, False otherwise
    """
    source = DownloadSource(url=url)
    source.get_file_info()  # Get file size and content type
    stats = DownloadStats(total_size=source.size)
    safe_url = urllib.parse.quote(url, safe=":/?&=")

    try:
        # Create an enhanced progress display with Nord theme
        with Progress(
            *NordColors.get_progress_columns(),
            console=console,
        ) as progress:
            download_task = progress.add_task(
                "Starting download...", total=source.size if source.size > 0 else None
            )

            with requests.get(
                safe_url, stream=True, timeout=DOWNLOAD_TIMEOUT
            ) as response:
                response.raise_for_status()

                # If we didn't get content length from HEAD request, try again from GET
                if stats.total_size <= 0 and "content-length" in response.headers:
                    content_length = response.headers.get("content-length")
                    if content_length and content_length.isdigit():
                        stats.total_size = int(content_length)
                        progress.update(download_task, total=stats.total_size)

                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            chunk_size = len(chunk)
                            stats.update_progress(chunk_size)

                            # Update progress with improved rate display
                            speed_text = f"{format_size(stats.average_rate)}/s"
                            time_left = stats.estimated_time_remaining
                            progress_desc = f"Downloading: {source.name}"

                            progress.update(
                                download_task,
                                completed=stats.bytes_downloaded,
                                description=progress_desc,
                                refresh=True,
                            )

                            # For unknown size files, show animated progress
                            if source.size <= 0:
                                progress.update(
                                    download_task, advance=len(chunk) / CHUNK_SIZE
                                )

        return True
    except requests.exceptions.RequestException as e:
        print_error(f"Download failed: {str(e)}")
        if os.path.exists(output_path):
            os.unlink(output_path)  # Remove partial file
        return False
    except IOError as e:
        print_error(f"File I/O error: {str(e)}")
        if os.path.exists(output_path):
            os.unlink(output_path)  # Remove partial file
        return False
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        if os.path.exists(output_path):
            os.unlink(output_path)  # Remove partial file
        return False


def ensure_directory(path: str) -> None:
    """Ensure a directory exists, creating it if necessary"""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        raise


def download_file(url: str, output_dir: str, verbose: bool = False) -> bool:
    """
    Download a file from a URL with enhanced UI and progress tracking.

    Args:
        url: The URL to download
        output_dir: The directory to save the file in
        verbose: Whether to show verbose output

    Returns:
        bool: True if download succeeded, False otherwise
    """
    try:
        ensure_directory(output_dir)
        source = DownloadSource(url=url)
        source.get_file_info()  # Get file size, type, and better filename

        # Get a filename that doesn't conflict with existing files
        base_filename = source.name
        filename = base_filename
        counter = 1

        while os.path.exists(os.path.join(output_dir, filename)):
            name, ext = os.path.splitext(base_filename)
            filename = f"{name}_{counter}{ext}"
            counter += 1

        output_path = os.path.join(output_dir, filename)

        # Show download information in a panel
        display_panel(
            "Download Information",
            f"URL: {url}\n"
            f"Filename: {filename}\n"
            f"Content Type: {source.content_type or 'Unknown'}\n"
            f"Size: {format_size(source.size) if source.size else 'Unknown'}\n"
            f"Destination: {output_path}",
            NordColors.FROST_2,
        )

        # Start the download
        start_time = time.time()
        loop = asyncio.get_event_loop()
        success = loop.run_until_complete(download_file_with_progress(url, output_path))
        end_time = time.time()
        download_time = end_time - start_time

        if success and os.path.exists(output_path):
            file_stats = os.stat(output_path)
            file_size = file_stats.st_size
            download_speed = file_size / max(download_time, 0.1)

            # Add to download history
            history = DownloadHistory.load()
            history.add_entry(
                url=url,
                filename=filename,
                output_path=output_path,
                size=file_size,
                success=True,
                elapsed_time=download_time,
            )

            # Show success panel with detailed stats
            display_panel(
                "Download Complete",
                f"✅ Downloaded: [bold]{filename}[/]\n"
                f"📦 Size: [bold]{format_size(file_size)}[/]\n"
                f"⏱️ Time: [bold]{format_time(download_time)}[/]\n"
                f"⚡ Speed: [bold]{format_size(download_speed)}/s[/]\n"
                f"📂 Location: [bold]{output_path}[/]",
                NordColors.GREEN,
            )
            return True
        else:
            # Add failed download to history
            history = DownloadHistory.load()
            history.add_entry(
                url=url,
                filename=filename,
                output_path=output_path,
                size=0,
                success=False,
                elapsed_time=download_time,
            )

            display_panel(
                "Download Failed",
                f"❌ Failed to download: {filename}\n🔗 URL: {url}",
                NordColors.RED,
            )
            return False
    except Exception as e:
        print_error(f"Download failed: {e}")
        if verbose:
            console.print_exception()
        return False


def download_youtube(url: str, output_dir: str, verbose: bool = False) -> bool:
    """
    Download a YouTube video with enhanced progress display.

    Args:
        url: YouTube URL
        output_dir: Directory to save the video
        verbose: Whether to display verbose output

    Returns:
        bool: True if download succeeded, False otherwise
    """
    try:
        ensure_directory(output_dir)
        output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

        # Display YouTube download information
        display_panel(
            "YouTube Download",
            f"URL: {url}\n"
            f"Quality: Best video + best audio\n"
            f"Format: MP4 (merged)\n"
            f"Destination: {output_dir}",
            NordColors.FROST_2,
        )

        # Build yt-dlp command
        cmd = [
            "yt-dlp",
            "-f",
            "bestvideo+bestaudio/best",
            "--merge-output-format",
            "mp4",
            "-o",
            output_template,
            "--newline",  # For better progress parsing
            url,
        ]

        if verbose:
            cmd.append("-v")

        start_time = time.time()

        # Enhanced progress display with Nord theme
        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(
                style=NordColors.POLAR_NIGHT_3,
                complete_style=NordColors.FROST_2,
                finished_style=NordColors.GREEN,
            ),
            TaskProgressColumn(style=NordColors.SNOW_STORM_1),
            TimeRemainingColumn(style=NordColors.FROST_4),
            console=console,
            expand=True,
        ) as progress:
            download_task = progress.add_task(
                "Starting YouTube download...", total=1000
            )
            video_title = "video"

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Variable to track current stage
            current_stage = "Initializing"
            progress_value = 0.0

            while True:
                if process.poll() is not None:
                    break

                line = process.stdout.readline().strip()

                if not line:
                    time.sleep(0.1)
                    continue

                if verbose:
                    console.log(line, style="dim")

                # Parse and update progress based on yt-dlp output
                if "[download]" in line and "%" in line:
                    try:
                        # Extract percentage and update progress
                        percent_str = line.split("%")[0].split()[-1]
                        if percent_str.replace(".", "", 1).isdigit():
                            percent = float(percent_str)
                            progress_value = percent * 10  # Scale to 0-1000
                            progress.update(download_task, completed=progress_value)
                    except (ValueError, IndexError):
                        pass

                    # Update description with current task
                    progress.update(download_task, description=line.strip())

                elif "[ExtractAudio]" in line or "Extracting audio" in line:
                    current_stage = "Extracting Audio"
                    progress.update(download_task, description=current_stage)

                elif "Merging formats into" in line:
                    current_stage = "Merging Formats"
                    progress.update(download_task, description=current_stage)
                    # Extract filename
                    try:
                        video_title = (
                            line.split("Merging formats into")[1].strip().strip('"')
                        )
                    except (IndexError, AttributeError):
                        pass

                elif "Destination:" in line:
                    try:
                        video_title = line.split("Destination:")[1].strip()
                    except (IndexError, AttributeError):
                        pass

                elif "[ffmpeg] Merging formats into" in line:
                    current_stage = "Finalizing Video"
                    progress.update(download_task, description=current_stage)

                # Keep progress bar moving for operations without percent indicators
                if "%" not in line and progress_value < 990:
                    # Advance slightly to show activity
                    progress.advance(download_task, advance=0.5)

            # Set to completed when done
            progress.update(
                download_task, completed=1000, description="Download Complete"
            )

        end_time = time.time()
        download_time = end_time - start_time
        return_code = process.returncode

        if return_code == 0:
            # Find the most recently downloaded file
            files = os.listdir(output_dir)
            downloaded_file = None
            newest_time = 0

            for file in files:
                file_path = os.path.join(output_dir, file)
                try:
                    file_time = os.path.getmtime(file_path)
                    if file_time > newest_time and file_time >= start_time:
                        newest_time = file_time
                        downloaded_file = file
                except Exception:
                    continue

            if downloaded_file:
                file_path = os.path.join(output_dir, downloaded_file)
                file_size = os.path.getsize(file_path)

                # Add to download history
                history = DownloadHistory.load()
                history.add_entry(
                    url=url,
                    filename=downloaded_file,
                    output_path=file_path,
                    size=file_size,
                    success=True,
                    elapsed_time=download_time,
                )

                display_panel(
                    "YouTube Download Complete",
                    f"✅ Downloaded: [bold]{downloaded_file}[/]\n"
                    f"📦 Size: [bold]{format_size(file_size)}[/]\n"
                    f"⏱️ Time: [bold]{format_time(download_time)}[/]\n"
                    f"📂 Location: [bold]{file_path}[/]",
                    NordColors.GREEN,
                )
                return True
            else:
                print_warning("Download may have succeeded but file not found")
                return True
        else:
            # Add failed download to history
            history = DownloadHistory.load()
            history.add_entry(
                url=url,
                filename=video_title,
                output_path=output_dir,
                size=0,
                success=False,
                elapsed_time=download_time,
            )

            display_panel(
                "YouTube Download Failed",
                f"❌ Failed to download: {url}\n"
                f"📂 Check {output_dir} for any partial downloads",
                NordColors.RED,
            )
            return False
    except Exception as e:
        print_error(f"YouTube download failed: {e}")
        if verbose:
            console.print_exception()
        return False


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup operations before exit"""
    try:
        config = AppConfig.load()
        config.save()
        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


def signal_handler(sig: int, frame: Any) -> None:
    """Handle interrupt signals"""
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


# ----------------------------------------------------------------
# Enhanced Menu Functions
# ----------------------------------------------------------------
def file_download_menu() -> None:
    """Menu for downloading files from URLs"""
    clear_screen()
    console.print(create_header())
    display_panel(
        "File Download",
        "Download any file from the web with optimized progress tracking.",
        NordColors.FROST_2,
    )

    config = AppConfig.load()
    history = FileHistory(os.path.join(CONFIG_DIR, "url_history.txt"))

    # Create a URL completer with recent downloads
    url_completer = WordCompleter(config.recent_downloads, sentence=True)

    # Use prompt toolkit for nicer URL input with history
    url = pt_prompt(
        "Enter the URL to download: ",
        history=history,
        completer=url_completer,
        style=PTStyle.from_dict(
            {
                "prompt": f"bold {NordColors.FROST_2}",
            }
        ),
    )

    if not url:
        print_error("URL cannot be empty")
        Prompt.ask("Press Enter to return to the main menu")
        return

    # Enhanced output directory selection
    output_dir = Prompt.ask(
        "Enter the output directory",
        default=config.default_download_dir,
        show_choices=False,
    )

    # Option for verbose output
    verbose = Confirm.ask("Enable verbose mode?", default=False)

    # Perform the download with enhanced feedback
    success = download_file(url, output_dir, verbose)

    if success:
        # Update recent downloads list
        if url not in config.recent_downloads:
            config.recent_downloads.insert(0, url)
            config.recent_downloads = config.recent_downloads[:10]  # Keep top 10
        config.save()

    Prompt.ask("Press Enter to return to the main menu")


def youtube_download_menu() -> None:
    """Menu for downloading YouTube videos"""
    clear_screen()
    console.print(create_header())
    display_panel(
        "YouTube Download",
        "Download YouTube videos with highest quality merged into MP4.",
        NordColors.FROST_2,
    )

    # Check for yt-dlp
    if not shutil.which("yt-dlp"):
        display_panel(
            "Dependency Missing",
            "yt-dlp is not installed. Would you like to install it now?",
            NordColors.WARNING,
        )

        if Confirm.ask("Install yt-dlp?", default=True):
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--user", "yt-dlp"]
                )
                print_success("yt-dlp installed successfully!")
            except Exception as e:
                print_error(f"Failed to install yt-dlp: {e}")
                Prompt.ask("Press Enter to return to the main menu")
                return
        else:
            print_warning("yt-dlp is required for YouTube downloads")
            Prompt.ask("Press Enter to return to the main menu")
            return

    config = AppConfig.load()
    history = FileHistory(os.path.join(CONFIG_DIR, "youtube_history.txt"))

    # Create URL completer with YouTube URLs from history
    youtube_urls = [
        url
        for url in config.recent_downloads
        if "youtube.com" in url or "youtu.be" in url
    ]
    url_completer = WordCompleter(youtube_urls, sentence=True)

    # Use prompt toolkit for nicer URL input with history
    url = pt_prompt(
        "Enter the YouTube URL: ",
        history=history,
        completer=url_completer,
        style=PTStyle.from_dict(
            {
                "prompt": f"bold {NordColors.FROST_2}",
            }
        ),
    )

    if not url:
        print_error("URL cannot be empty")
        Prompt.ask("Press Enter to return to the main menu")
        return

    # Enhanced output directory selection
    output_dir = Prompt.ask(
        "Enter the output directory",
        default=config.default_download_dir,
        show_choices=False,
    )

    # Option for verbose output
    verbose = Confirm.ask("Enable verbose mode?", default=False)

    # Perform the YouTube download with enhanced feedback
    success = download_youtube(url, output_dir, verbose)

    if success:
        # Update recent downloads list
        if url not in config.recent_downloads:
            config.recent_downloads.insert(0, url)
            config.recent_downloads = config.recent_downloads[:10]  # Keep top 10
        config.save()

    Prompt.ask("Press Enter to return to the main menu")


def view_download_history() -> None:
    """View and manage download history"""
    clear_screen()
    console.print(create_header())

    # Load download history
    history = DownloadHistory.load()

    if not history.entries:
        display_panel(
            "Download History", "No download history found.", NordColors.FROST_3
        )
        Prompt.ask("Press Enter to return to the settings menu")
        return

    # Create a table to display download history
    table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        title="Download History",
        border_style=NordColors.FROST_3,
        expand=True,
    )

    # Add columns
    table.add_column("#", style=NordColors.ACCENT, width=3)
    table.add_column("Date", style=NordColors.FROST_2)
    table.add_column("Filename", style=NordColors.SNOW_STORM_1)
    table.add_column("Size", style=NordColors.FROST_3, justify="right")
    table.add_column("Status", style=NordColors.FROST_4)

    # Add rows (show last 15 downloads)
    for i, entry in enumerate(history.entries[:15], 1):
        date_str = datetime.fromisoformat(entry["date"]).strftime("%Y-%m-%d %H:%M")
        status = "[green]Success[/green]" if entry["success"] else "[red]Failed[/red]"

        table.add_row(
            str(i), date_str, entry["filename"], format_size(entry["size"]), status
        )

    console.print(table)

    # Options for history management
    options = [
        ("1", "View Download Details", "See details for a specific download"),
        ("2", "Clear History", "Delete all download history"),
        ("3", "Return to Settings", "Go back to the settings menu"),
    ]

    console.print(create_menu_table("History Options", options))
    choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="3")

    if choice == "1":
        entry_num = Prompt.ask(
            "Enter download number to view details",
            choices=[str(i) for i in range(1, min(16, len(history.entries) + 1))],
            show_choices=False,
        )

        entry = history.entries[int(entry_num) - 1]
        display_panel(
            f"Download Details: {entry['filename']}",
            f"URL: {entry['url']}\n"
            f"Filename: {entry['filename']}\n"
            f"Path: {entry['path']}\n"
            f"Size: {format_size(entry['size'])}\n"
            f"Status: {'Successful' if entry['success'] else 'Failed'}\n"
            f"Date: {datetime.fromisoformat(entry['date']).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Download Time: {format_time(entry['elapsed_time'])}",
            NordColors.FROST_2,
        )

    elif choice == "2":
        if Confirm.ask(
            "Are you sure you want to clear all download history?", default=False
        ):
            history.entries = []
            history.save()
            print_success("Download history cleared")

    view_download_history() if choice != "3" else None


def settings_menu() -> None:
    """Enhanced settings menu"""
    clear_screen()
    console.print(create_header())
    display_panel(
        "Settings",
        "Configure application settings and preferences.",
        NordColors.FROST_2,
    )

    config = AppConfig.load()

    # Create a more visually appealing settings menu
    settings_options = [
        ("1", "Change Default Download Directory", config.default_download_dir),
        ("2", "View Recent Downloads", f"{len(config.recent_downloads)} downloads"),
        ("3", "View Download History", "View and manage download history"),
        ("4", "Check Dependencies", "Verify required tools are installed"),
        ("5", "Application Information", "View app details and system info"),
        ("6", "Return to Main Menu", ""),
    ]

    console.print(create_menu_table("Settings Options", settings_options))
    choice = Prompt.ask(
        "Select option", choices=["1", "2", "3", "4", "5", "6"], default="6"
    )

    if choice == "1":
        # Enhanced directory selection with better feedback
        new_dir = Prompt.ask(
            "Enter new default download directory", default=config.default_download_dir
        )

        if os.path.isdir(new_dir):
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
                print_success(
                    f"Created and set default download directory to: {new_dir}"
                )
            except Exception as e:
                print_error(f"Failed to create directory: {e}")
        else:
            print_warning("Directory change canceled")

    elif choice == "2":
        # Show recent downloads in a table
        if config.recent_downloads:
            recent_table = Table(
                show_header=True,
                header_style=NordColors.HEADER,
                title="Recent Downloads",
                box=ROUNDED,
                border_style=NordColors.FROST_3,
                expand=True,
            )

            recent_table.add_column("#", style=NordColors.ACCENT, width=3)
            recent_table.add_column("URL", style=NordColors.SNOW_STORM_1)

            for i, url in enumerate(config.recent_downloads, 1):
                recent_table.add_row(str(i), url)

            console.print(recent_table)

            if Confirm.ask("Clear recent downloads list?", default=False):
                config.recent_downloads = []
                config.save()
                print_success("Recent downloads list cleared")
        else:
            print_warning("No recent downloads found")

    elif choice == "3":
        # View download history
        view_download_history()

    elif choice == "4":
        # Check dependencies with enhanced visual feedback
        dependencies = {
            "curl": ["brew", "install", "curl"],
            "wget": ["brew", "install", "wget"],
            "yt-dlp": ["pip", "install", "yt-dlp"],
            "ffmpeg": ["brew", "install", "ffmpeg"],
        }

        dep_table = Table(
            show_header=True,
            header_style=NordColors.HEADER,
            title="Dependency Status",
            box=ROUNDED,
            border_style=NordColors.FROST_3,
        )

        dep_table.add_column("Dependency", style=NordColors.FROST_1)
        dep_table.add_column("Status", style=NordColors.SNOW_STORM_1)
        dep_table.add_column("Version", style=NordColors.FROST_3)

        missing_deps = {}

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Checking dependencies..."),
            console=console,
        ) as progress:
            check_task = progress.add_task("Checking...", total=len(dependencies))

            for name, cmd in dependencies.items():
                installed = shutil.which(name) is not None
                status_text = "Installed" if installed else "Missing"
                status_style = NordColors.GREEN if installed else NordColors.RED

                # Get version if installed
                version = "N/A"
                if installed:
                    try:
                        if name == "ffmpeg":
                            version_result = subprocess.run(
                                [name, "-version"],
                                capture_output=True,
                                text=True,
                                check=False,
                            )
                            if version_result.returncode == 0:
                                version_line = version_result.stdout.split("\n")[0]
                                version = (
                                    version_line.split(" ")[2]
                                    if len(version_line.split(" ")) > 2
                                    else "Unknown"
                                )
                        elif name == "yt-dlp":
                            version_result = subprocess.run(
                                [name, "--version"],
                                capture_output=True,
                                text=True,
                                check=False,
                            )
                            if version_result.returncode == 0:
                                version = version_result.stdout.strip()
                        else:
                            version_result = subprocess.run(
                                [name, "--version"],
                                capture_output=True,
                                text=True,
                                check=False,
                            )
                            if version_result.returncode == 0:
                                version = version_result.stdout.strip().split("\n")[0]
                    except Exception:
                        version = "Unknown"

                dep_table.add_row(
                    name, f"[{status_style}]{status_text}[/{status_style}]", version
                )

                if not installed:
                    missing_deps[name] = cmd

                progress.advance(check_task)

        console.print(dep_table)

        if missing_deps:
            if Confirm.ask("Install missing dependencies?", default=True):
                with Progress(
                    *NordColors.get_progress_columns(), console=console
                ) as progress:
                    install_task = progress.add_task(
                        "Installing", total=len(missing_deps)
                    )

                    for name, cmd in missing_deps.items():
                        progress.update(
                            install_task, description=f"Installing {name}..."
                        )

                        if cmd[0] in ["brew", "apt"] and os.geteuid() != 0:
                            cmd = ["sudo"] + cmd

                        try:
                            run_command(cmd, check=False, verbose=True)

                            if shutil.which(name):
                                print_success(f"Installed {name}")
                            else:
                                print_error(f"Failed to install {name}")

                        except Exception as e:
                            print_error(f"Error installing {name}: {e}")

                        progress.advance(install_task)
            else:
                print_warning("Dependency installation skipped")
        else:
            print_success("All dependencies are installed")

    elif choice == "5":
        # Application information display
        system_info = {
            "App Version": VERSION,
            "Python Version": platform.python_version(),
            "macOS Version": platform.mac_ver()[0],
            "Architecture": platform.machine(),
            "User": os.environ.get("USER", "Unknown"),
            "Home Directory": os.path.expanduser("~"),
            "Config Directory": CONFIG_DIR,
        }

        # Create an info panel
        info_content = "\n".join([f"{k}: {v}" for k, v in system_info.items()])

        display_panel("Application Information", info_content, NordColors.FROST_2)

    Prompt.ask(
        "Press Enter to continue"
        if choice != "6"
        else "Press Enter to return to the main menu"
    )
    if choice != "6":
        settings_menu()


def main_menu() -> None:
    """Enhanced main menu with better visual styling"""
    while True:
        clear_screen()
        console.print(create_header())

        # Enhanced main menu with better descriptions
        main_options = [
            (
                "1",
                "Download File",
                "Download any file from the web with progress tracking",
            ),
            (
                "2",
                "Download YouTube",
                "Download YouTube videos in highest quality as MP4",
            ),
            ("3", "Settings", "Configure application preferences and view history"),
            ("4", "Exit", "Exit the application"),
        ]

        console.print(create_menu_table("Main Menu", main_options))

        # Add quick stats panel
        config = AppConfig.load()
        history = DownloadHistory.load()

        stats_panel = Panel(
            Text.from_markup(
                f"Default download directory: [bold]{config.default_download_dir}[/]\n"
                f"Recent downloads: [bold]{len(config.recent_downloads)}[/]\n"
                f"Downloaded files: [bold]{len([e for e in history.entries if e['success']])}[/]\n"
            ),
            title="Quick Stats",
            border_style=NordColors.FROST_3,
            box=ROUNDED,
            padding=(1, 2),
        )

        console.print(stats_panel)

        choice = Prompt.ask(
            "Select an option", choices=["1", "2", "3", "4"], default="4"
        )

        if choice == "1":
            file_download_menu()
        elif choice == "2":
            youtube_download_menu()
        elif choice == "3":
            settings_menu()
        elif choice == "4":
            clear_screen()
            console.print(
                Panel(
                    Text.from_markup(
                        "[bold]Thank you for using macOS Downloader![/]\n\n"
                        "Developed with the Nord theme for a beautiful macOS experience."
                    ),
                    title="Goodbye!",
                    title_align="center",
                    border_style=NordColors.FROST_2,
                    box=HEAVY,
                    padding=(2, 4),
                )
            )
            break


def main() -> None:
    """Main application entry point with enhanced error handling"""
    try:
        # Display a splash screen
        clear_screen()
        console.print(create_header())

        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Starting macOS Downloader..."),
            console=console,
        ) as progress:
            task = progress.add_task("", total=100)

            # Initialize application
            ensure_config_directory()
            progress.update(task, completed=30, description="Checking configuration...")

            # Check ffmpeg
            check_ffmpeg()
            progress.update(task, completed=60, description="Verifying dependencies...")

            # Load config
            AppConfig.load()
            progress.update(task, completed=90, description="Loading settings...")

            # Complete
            progress.update(task, completed=100, description="Ready!")
            time.sleep(0.5)  # Brief pause to show completion

        # Start the main menu
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
