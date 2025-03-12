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
Version: 1.0.0
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
from typing import List, Optional, Any, Tuple

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
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from prompt_toolkit import prompt as pt_prompt
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
VERSION: str = "1.0.0"
DEFAULT_DOWNLOAD_DIR: str = os.path.join(os.path.expanduser("~"), "Downloads")
CONFIG_DIR: str = os.path.expanduser("~/.macos_downloader")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")
DOWNLOAD_TIMEOUT: int = 3600  # 1 hour timeout for downloads
DEFAULT_TIMEOUT: int = 120  # 2 minutes default timeout for commands


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

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        return [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4][:steps]


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class DownloadSource:
    url: str
    name: str = ""
    size: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.get_filename_from_url()

    def get_filename_from_url(self) -> str:
        try:
            path = self.url.split("?")[0]
            filename = os.path.basename(path)
            return filename if filename else "downloaded_file"
        except Exception:
            return "downloaded_file"


@dataclass
class DownloadStats:
    bytes_downloaded: int = 0
    total_size: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    rate_history: List[float] = field(default_factory=list)

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
        if not self.rate_history:
            if self.elapsed_time > 0:
                return self.bytes_downloaded / self.elapsed_time
            return 0.0
        return sum(self.rate_history) / len(self.rate_history)

    def update_progress(self, new_bytes: int) -> None:
        now = time.time()
        if self.bytes_downloaded > 0:
            time_diff = now - (self.end_time or self.start_time)
            if time_diff > 0:
                rate = new_bytes / time_diff
                self.rate_history.append(rate)
                if len(self.rate_history) > 5:
                    self.rate_history.pop(0)
        self.bytes_downloaded += new_bytes
        self.end_time = now
        if self.total_size > 0 and self.bytes_downloaded >= self.total_size:
            self.bytes_downloaded = self.total_size


@dataclass
class AppConfig:
    default_download_dir: str = DEFAULT_DOWNLOAD_DIR
    recent_downloads: List[str] = field(default_factory=list)

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


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def clear_screen() -> None:
    console.clear()


def create_header() -> Panel:
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)
    fonts = ["slant", "big", "digital", "standard", "small"]
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
    colors = NordColors.get_frost_gradient(len(ascii_lines))
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"
    border = f"[{NordColors.FROST_3}]{'━' * (adjusted_width - 6)}[/]"
    styled_text = border + "\n" + styled_text + border
    return Panel(
        Text.from_markup(styled_text),
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]High-Res Downloader[/]",
        subtitle_align="center",
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    panel = Panel(
        Text.from_markup(message), title=title, border_style=style, padding=(1, 2)
    )
    console.print(panel)


def format_size(num_bytes: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


def create_menu_table(title: str, options: List[Tuple[str, str, str]]) -> Table:
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=None,
        title=title,
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3, justify="right")
    table.add_column("Option", style=f"bold {NordColors.FROST_1}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    for opt in options:
        table.add_row(*opt)
    return table


# ----------------------------------------------------------------
# Core Functionality
# ----------------------------------------------------------------
def ensure_config_directory() -> None:
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
    try:
        if verbose:
            print_step(f"Executing: {' '.join(cmd)}")
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
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


def get_file_size(url: str) -> int:
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        content_length = response.headers.get("content-length")
        if content_length and content_length.isdigit():
            return int(content_length)
        return 0
    except Exception as e:
        print_warning(f"Could not determine file size: {e}")
        return 0


async def download_file_with_progress(url: str, output_path: str) -> bool:
    source = DownloadSource(url=url)
    source.size = get_file_size(url)
    stats = DownloadStats(total_size=source.size)
    safe_url = urllib.parse.quote(url, safe=":/?&=")
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Downloading"),
            BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            download_task = progress.add_task(
                "Downloading", total=source.size if source.size > 0 else None
            )
            with requests.get(
                safe_url, stream=True, timeout=DOWNLOAD_TIMEOUT
            ) as response:
                response.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            chunk_size = len(chunk)
                            stats.update_progress(chunk_size)
                            progress.update(
                                download_task,
                                completed=stats.bytes_downloaded,
                                description=f"Speed: {format_size(stats.average_rate)}/s",
                            )
                            if source.size <= 0:
                                progress.update(download_task, advance=0.5)
        return True
    except Exception as e:
        print_error(f"Download failed: {e}")
        return False


def ensure_directory(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        raise


def download_file(url: str, output_dir: str, verbose: bool = False) -> bool:
    try:
        ensure_directory(output_dir)
        source = DownloadSource(url=url)
        filename = source.name
        output_path = os.path.join(output_dir, filename)
        print_step(f"Downloading: {url}")
        print_step(f"Destination: {output_path}")
        start_time = time.time()
        loop = asyncio.get_event_loop()
        success = loop.run_until_complete(download_file_with_progress(url, output_path))
        if success and os.path.exists(output_path):
            file_stats = os.stat(output_path)
            download_time = time.time() - start_time
            download_speed = file_stats.st_size / max(download_time, 0.1)
            display_panel(
                "Download Complete",
                f"Downloaded: {filename}\nSize: {format_size(file_stats.st_size)}\nTime: {format_time(download_time)}\nSpeed: {format_size(download_speed)}/s\nLocation: {output_path}",
                NordColors.GREEN,
            )
            return True
        else:
            print_error("Download failed or file not created")
            return False
    except Exception as e:
        print_error(f"Download failed: {e}")
        return False


def download_youtube(url: str, output_dir: str, verbose: bool = False) -> bool:
    """
    Download a YouTube video by always selecting the highest quality video and audio,
    merging them into an MP4.
    """
    try:
        ensure_directory(output_dir)
        # Use yt-dlp to download bestvideo+bestaudio and merge to mp4.
        output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
        print_step(f"Downloading YouTube video: {url}")
        print_step(f"Destination: {output_dir}")
        cmd = [
            "yt-dlp",
            "-f",
            "bestvideo+bestaudio/best",
            "--merge-output-format",
            "mp4",
            "-o",
            output_template,
            url,
        ]
        if verbose:
            cmd.append("-v")
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}"),
            BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            download_task = progress.add_task(
                "Starting YouTube download...", total=None
            )
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            while True:
                if process.poll() is not None:
                    break
                stdout_line = process.stdout.readline()
                if stdout_line:
                    if "[download]" in stdout_line and "%" in stdout_line:
                        progress.update(download_task, description=stdout_line.strip())
                    elif "Downloading video" in stdout_line:
                        progress.update(
                            download_task, description="Downloading video..."
                        )
                    elif "Downloading audio" in stdout_line:
                        progress.update(
                            download_task, description="Downloading audio..."
                        )
                    elif "Merging formats" in stdout_line:
                        progress.update(download_task, description="Merging formats...")
                time.sleep(0.1)
            return_code = process.wait()
        if return_code == 0:
            files = os.listdir(output_dir)
            downloaded_file = None
            newest_time = 0
            for file in files:
                file_path = os.path.join(output_dir, file)
                file_time = os.path.getmtime(file_path)
                if file_time > newest_time:
                    newest_time = file_time
                    downloaded_file = file
            if downloaded_file:
                display_panel(
                    "Download Complete",
                    f"Downloaded: {downloaded_file}\nLocation: {output_dir}",
                    NordColors.GREEN,
                )
                return True
            else:
                print_warning("Download may have succeeded but file not found")
                return True
        else:
            print_error("YouTube download failed")
            return False
    except Exception as e:
        print_error(f"YouTube download failed: {e}")
        return False


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    config = AppConfig.load()
    config.save()
    print_message("Cleaning up resources...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
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
# Menu Functions
# ----------------------------------------------------------------
def create_menu_table(title: str, options: List[Tuple[str, str, str]]) -> Table:
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=None,
        title=title,
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3, justify="right")
    table.add_column("Option", style=f"bold {NordColors.FROST_1}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    for option in options:
        table.add_row(*option)
    return table


def file_download_menu() -> None:
    clear_screen()
    console.print(create_header())
    display_panel("File Download", "Download any file from the web", NordColors.FROST_2)
    url = Prompt.ask("Enter the URL to download")
    if not url:
        print_error("URL cannot be empty")
        Prompt.ask("Press Enter to return to the main menu")
        return
    config = AppConfig.load()
    output_dir = Prompt.ask(
        "Enter the output directory", default=config.default_download_dir
    )
    verbose = Confirm.ask("Enable verbose mode?", default=False)
    success = download_file(url, output_dir, verbose)
    if success:
        if url not in config.recent_downloads:
            config.recent_downloads.insert(0, url)
            config.recent_downloads = config.recent_downloads[:5]
        config.save()
    Prompt.ask("Press Enter to return to the main menu")


def youtube_download_menu() -> None:
    clear_screen()
    console.print(create_header())
    display_panel(
        "YouTube Download",
        "Download YouTube videos with highest quality merged into MP4",
        NordColors.FROST_2,
    )
    if not shutil.which("yt-dlp"):
        print_error("yt-dlp is not installed. Install it with: pip install yt-dlp")
        Prompt.ask("Press Enter to return to the main menu")
        return
    url = Prompt.ask("Enter the YouTube URL")
    if not url:
        print_error("URL cannot be empty")
        Prompt.ask("Press Enter to return to the main menu")
        return
    config = AppConfig.load()
    output_dir = Prompt.ask(
        "Enter the output directory", default=config.default_download_dir
    )
    verbose = Confirm.ask("Enable verbose mode?", default=False)
    success = download_youtube(url, output_dir, verbose)
    if success:
        if url not in config.recent_downloads:
            config.recent_downloads.insert(0, url)
            config.recent_downloads = config.recent_downloads[:5]
        config.save()
    Prompt.ask("Press Enter to return to the main menu")


def settings_menu() -> None:
    clear_screen()
    console.print(create_header())
    display_panel("Settings", "Configure application settings", NordColors.FROST_2)
    config = AppConfig.load()
    settings_options = [
        ("1", "Change Default Download Directory", config.default_download_dir),
        ("2", "View Recent Downloads", f"{len(config.recent_downloads)} downloads"),
        ("3", "Check Dependencies", ""),
        ("4", "Return to Main Menu", ""),
    ]
    console.print(create_menu_table("Settings Options", settings_options))
    choice = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="4")
    if choice == "1":
        new_dir = Prompt.ask(
            "Enter new default download directory", default=config.default_download_dir
        )
        if os.path.isdir(new_dir) or Confirm.ask(
            f"Directory '{new_dir}' doesn't exist. Create it?", default=True
        ):
            try:
                ensure_directory(new_dir)
                config.default_download_dir = new_dir
                config.save()
                print_success(f"Default download directory updated to: {new_dir}")
            except Exception as e:
                print_error(f"Failed to set directory: {e}")
        else:
            print_warning("Directory change canceled")
    elif choice == "2":
        if config.recent_downloads:
            recent_table = Table(
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
                title="Recent Downloads",
            )
            recent_table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3)
            recent_table.add_column("URL", style=NordColors.SNOW_STORM_1)
            for i, url in enumerate(config.recent_downloads, 1):
                recent_table.add_row(str(i), url)
            console.print(recent_table)
        else:
            print_warning("No recent downloads found")
    elif choice == "3":
        dependencies = {
            "curl": ["brew", "install", "curl"],
            "wget": ["brew", "install", "wget"],
            "yt-dlp": ["pip", "install", "yt-dlp"],
            "ffmpeg": ["brew", "install", "ffmpeg"],
        }
        dep_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            title="Dependency Status",
        )
        dep_table.add_column("Dependency", style=f"bold {NordColors.FROST_1}")
        dep_table.add_column("Status", style=NordColors.SNOW_STORM_1)
        missing_deps = {}
        for name, cmd in dependencies.items():
            installed = shutil.which(name) is not None
            status_text = "Installed" if installed else "Missing"
            status_style = NordColors.GREEN if installed else NordColors.RED
            dep_table.add_row(name, f"[{status_style}]{status_text}[/{status_style}]")
            if not installed:
                missing_deps[name] = cmd
        console.print(dep_table)
        if missing_deps:
            if Confirm.ask("Install missing dependencies?", default=True):
                with Progress(
                    SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                    TextColumn("[bold]{task.description}"),
                    BarColumn(
                        style=NordColors.FROST_4, complete_style=NordColors.FROST_2
                    ),
                    TaskProgressColumn(),
                    console=console,
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
    Prompt.ask("Press Enter to return to the main menu")


def main_menu() -> None:
    while True:
        clear_screen()
        console.print(create_header())
        main_options = [
            ("1", "Download File", "Download any file from the web"),
            ("2", "Download YouTube", "Download YouTube video (highest quality)"),
            ("3", "Settings", "Configure application settings"),
            ("4", "Exit", "Exit the application"),
        ]
        console.print(create_menu_table("Main Menu", main_options))
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
                    Text("Goodbye!", style=f"bold {NordColors.FROST_2}"),
                    border_style=NordColors.FROST_1,
                )
            )
            break


def main() -> None:
    try:
        ensure_config_directory()
        while True:
            main_menu()
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
    finally:
        cleanup()


if __name__ == "__main__":
    main()
