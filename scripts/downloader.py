#!/usr/bin/env python3

import os
import sys
import time
import json
import signal
import shutil
import subprocess
import atexit
import urllib.parse
import platform
from dataclasses import dataclass, field
from typing import List, Optional, Any, Tuple, Dict, Union
from datetime import datetime

if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)

def install_dependencies():
    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "requests", "yt-dlp"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER"))
    try:
        if os.geteuid() != 0:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user"] + required_packages)
        else:
            subprocess.check_call(["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"] + required_packages)
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)

def check_homebrew():
    if shutil.which("brew") is None:
        print("Homebrew is not installed. Please install Homebrew from https://brew.sh and rerun this script.")
        sys.exit(1)

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
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
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style as PTStyle
    import requests
except ImportError:
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)

if not check_ffmpeg():
    print("FFmpeg is required but could not be installed. Exiting.")
    sys.exit(1)

install_rich_traceback(show_locals=True)
console = Console()

APP_NAME = "Downloader"
VERSION = "1.1.0"
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
CONFIG_DIR = os.path.expanduser("~/.macos_downloader")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
DOWNLOAD_TIMEOUT = 3600
DEFAULT_TIMEOUT = 120
CHUNK_SIZE = 16384

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
            TransferSpeedColumn(style=cls.FROST_3),
            TimeRemainingColumn(compact=True),
        ]

@dataclass
class DownloadSource:
    url: str
    name: str = ""
    size: int = 0
    content_type: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = self.get_filename_from_url()

    def get_filename_from_url(self):
        try:
            path = urllib.parse.urlsplit(self.url).path
            filename = os.path.basename(path)
            return urllib.parse.unquote(filename) if filename else "downloaded_file"
        except Exception:
            return "downloaded_file"

    def get_file_info(self):
        try:
            response = requests.head(self.url, timeout=10, allow_redirects=True)
            self.size = int(response.headers.get("content-length", 0))
            self.content_type = response.headers.get("content-type", "")
            
            if "content-disposition" in response.headers:
                import re
                filename_match = re.search(r'filename="?([^";]+)', response.headers["content-disposition"])
                if filename_match and filename_match.group(1):
                    self.name = filename_match.group(1)
            
            return {"size": self.size, "content_type": self.content_type, "filename": self.name}
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
    window_size: int = 20
    smoothing_factor: float = 0.3

    @property
    def is_complete(self):
        return self.end_time is not None or (self.total_size > 0 and self.bytes_downloaded >= self.total_size)

    @property
    def progress_percentage(self):
        if self.total_size <= 0:
            return 0.0
        return min(100.0, (self.bytes_downloaded / self.total_size) * 100)

    @property
    def elapsed_time(self):
        return (self.end_time or time.time()) - self.start_time

    @property
    def average_rate(self):
        if not self.rate_history:
            if self.elapsed_time > 0:
                return self.bytes_downloaded / self.elapsed_time
            return 0.0
        
        if len(self.rate_history) >= 3:
            recent_rates = self.rate_history[-5:]
            median_rate = sorted(recent_rates)[len(recent_rates) // 2]
            filtered_rates = [r for r in recent_rates if r <= median_rate * 2.5]
            if filtered_rates:
                return sum(filtered_rates) / len(filtered_rates)
        
        return self.rate_history[-1]

    @property
    def estimated_time_remaining(self):
        if self.is_complete:
            return 0.0
        
        if self.total_size <= 0 or self.average_rate <= 0:
            return float('inf')
        
        remaining_bytes = self.total_size - self.bytes_downloaded
        return remaining_bytes / self.average_rate

    def update_progress(self, new_bytes):
        now = time.time()
        time_diff = now - self.last_update_time
        
        if time_diff > 0.1:
            self.bytes_downloaded += new_bytes
            current_rate = new_bytes / time_diff
            
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
    theme: str = "dark"
    language: str = "en"
    max_concurrent_downloads: int = 1
    auto_close_completed: bool = False

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

@dataclass
class DownloadHistory:
    entries: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_entry(self, url, filename, output_path, size, success, elapsed_time):
        entry = {
            "url": url,
            "filename": filename,
            "path": output_path,
            "size": size,
            "success": success,
            "date": datetime.now().isoformat(),
            "elapsed_time": elapsed_time
        }
        self.entries.insert(0, entry)
        self.entries = self.entries[:50]
        self.save()
    
    def save(self):
        ensure_config_directory()
        try:
            with open(HISTORY_FILE, "w") as f:
                json.dump({"history": self.entries}, f, indent=2)
        except Exception as e:
            print_error(f"Failed to save history: {e}")
    
    @classmethod
    def load(cls):
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r") as f:
                    data = json.load(f)
                return cls(entries=data.get("history", []))
        except Exception as e:
            print_error(f"Failed to load history: {e}")
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
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]High-Quality macOS File Downloader[/]",
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

def format_size(num_bytes):
    if num_bytes < 0:
        return "0 B"
    
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            if num_bytes < 0.1 and unit != "B":
                return f"{num_bytes * 1024:.2f} {unit.replace('B', '')}B"
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"

def format_time(seconds):
    if seconds < 0 or seconds == float('inf'):
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

def run_command(cmd, check=True, timeout=DEFAULT_TIMEOUT, verbose=False):
    try:
        if verbose:
            print_step(f"Executing: {' '.join(cmd)}")
            
        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Running command..."),
            console=console
        ) as progress:
            task = progress.add_task("", total=None)
            result = subprocess.run(cmd, check=check, text=True, capture_output=True, timeout=timeout)
            
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

def ensure_directory(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        raise

def download_file(url, output_dir, verbose=False):
    try:
        ensure_directory(output_dir)
        source = DownloadSource(url=url)
        source.get_file_info()
        
        base_filename = source.name
        filename = base_filename
        counter = 1
        
        while os.path.exists(os.path.join(output_dir, filename)):
            name, ext = os.path.splitext(base_filename)
            filename = f"{name}_{counter}{ext}"
            counter += 1
            
        output_path = os.path.join(output_dir, filename)
        
        display_panel(
            "Download Information",
            f"URL: {url}\n"
            f"Filename: {filename}\n"
            f"Content Type: {source.content_type or 'Unknown'}\n"
            f"Size: {format_size(source.size) if source.size else 'Unknown'}\n"
            f"Destination: {output_path}",
            NordColors.FROST_2
        )
        
        start_time = time.time()
        success = False
        
        try:
            with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                
                with Progress(
                    SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
                    TextColumn(f"[bold {NordColors.FROST_2}]Downloading"),
                    BarColumn(style=NordColors.POLAR_NIGHT_3, complete_style=NordColors.FROST_2, finished_style=NordColors.GREEN),
                    TaskProgressColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(compact=True),
                    console=console,
                ) as progress:
                    task = progress.add_task("Downloading", total=total_size or None)
                    
                    with open(output_path, 'wb') as f:
                        downloaded = 0
                        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                progress.update(task, completed=downloaded, description=f"Downloading: {filename}")
                                
                                if total_size == 0:
                                    progress.update(task, advance=len(chunk) / CHUNK_SIZE)
            
            success = True
        except Exception as e:
            if verbose:
                print_error(f"Download error details: {str(e)}")
            raise
            
        end_time = time.time()
        download_time = end_time - start_time
        
        if success and os.path.exists(output_path):
            file_stats = os.stat(output_path)
            file_size = file_stats.st_size
            download_speed = file_size / max(download_time, 0.1)
            
            history = DownloadHistory.load()
            history.add_entry(url=url, filename=filename, output_path=output_path, size=file_size, 
                             success=True, elapsed_time=download_time)
            
            display_panel(
                "Download Complete",
                f"✅ Downloaded: [bold]{filename}[/]\n"
                f"📦 Size: [bold]{format_size(file_size)}[/]\n"
                f"⏱️ Time: [bold]{format_time(download_time)}[/]\n"
                f"⚡ Speed: [bold]{format_size(download_speed)}/s[/]\n"
                f"📂 Location: [bold]{output_path}[/]",
                NordColors.GREEN
            )
            return True
        else:
            history = DownloadHistory.load()
            history.add_entry(url=url, filename=filename, output_path=output_path, size=0,
                             success=False, elapsed_time=download_time)
            
            display_panel(
                "Download Failed",
                f"❌ Failed to download: {filename}\n🔗 URL: {url}",
                NordColors.RED
            )
            return False
    except Exception as e:
        print_error(f"Download failed: {e}")
        if verbose:
            console.print_exception()
        return False

def download_youtube(url, output_dir, verbose=False):
    try:
        ensure_directory(output_dir)
        output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
        
        display_panel(
            "YouTube Download",
            f"URL: {url}\n"
            f"Quality: Best video + best audio\n"
            f"Format: MP4 (merged)\n"
            f"Destination: {output_dir}",
            NordColors.FROST_2
        )
        
        cmd = [
            "yt-dlp",
            "-f", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "-o", output_template,
            "--newline",
            url,
        ]
        
        if verbose:
            cmd.append("-v")
        
        start_time = time.time()
        
        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(style=NordColors.POLAR_NIGHT_3, complete_style=NordColors.FROST_2, finished_style=NordColors.GREEN),
            TaskProgressColumn(style=NordColors.SNOW_STORM_1),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        ) as progress:
            download_task = progress.add_task("Starting YouTube download...", total=1000)
            video_title = "video"
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            
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
                
                if "[download]" in line and "%" in line:
                    try:
                        percent_str = line.split("%")[0].split()[-1]
                        if percent_str.replace('.', '', 1).isdigit():
                            percent = float(percent_str)
                            progress_value = percent * 10
                            progress.update(download_task, completed=progress_value)
                    except (ValueError, IndexError):
                        pass
                    
                    progress.update(download_task, description=line.strip())
                    
                elif "[ExtractAudio]" in line or "Extracting audio" in line:
                    current_stage = "Extracting Audio"
                    progress.update(download_task, description=current_stage)
                    
                elif "Merging formats into" in line:
                    current_stage = "Merging Formats"
                    progress.update(download_task, description=current_stage)
                    try:
                        video_title = line.split("Merging formats into")[1].strip().strip('"')
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
                
                if "%" not in line and progress_value < 990:
                    progress.advance(download_task, advance=0.5)
            
            progress.update(download_task, completed=1000, description="Download Complete")
            
        end_time = time.time()
        download_time = end_time - start_time
        return_code = process.returncode
        
        if return_code == 0:
            time.sleep(0.5)
            
            downloaded_file = None
            newest_time = 0
            
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    if file.endswith(('.mp4', '.mkv', '.webm', '.mp3', '.m4a')):
                        file_path = os.path.join(root, file)
                        try:
                            file_stats = os.stat(file_path)
                            file_time = max(file_stats.st_mtime, file_stats.st_ctime)
                            
                            if file_time > start_time - 1 and file_time > newest_time:
                                newest_time = file_time
                                downloaded_file = file
                                if root != output_dir:
                                    downloaded_file = os.path.relpath(file_path, output_dir)
                        except Exception as e:
                            if verbose:
                                print_warning(f"Error checking file {file}: {e}")
                            continue
            
            if downloaded_file:
                file_path = os.path.join(output_dir, downloaded_file)
                file_size = os.path.getsize(file_path)
                
                history = DownloadHistory.load()
                history.add_entry(url=url, filename=downloaded_file, output_path=file_path, 
                                 size=file_size, success=True, elapsed_time=download_time)
                
                display_panel(
                    "YouTube Download Complete",
                    f"✅ Downloaded: [bold]{downloaded_file}[/]\n"
                    f"📦 Size: [bold]{format_size(file_size)}[/]\n"
                    f"⏱️ Time: [bold]{format_time(download_time)}[/]\n"
                    f"📂 Location: [bold]{file_path}[/]",
                    NordColors.GREEN
                )
                return True
            else:
                print_warning("Download may have succeeded but file not found")
                return True
        else:
            history = DownloadHistory.load()
            history.add_entry(url=url, filename=video_title, output_path=output_dir,
                             size=0, success=False, elapsed_time=download_time)
            
            display_panel(
                "YouTube Download Failed",
                f"❌ Failed to download: {url}\n📂 Check {output_dir} for any partial downloads",
                NordColors.RED
            )
            return False
    except Exception as e:
        print_error(f"YouTube download failed: {e}")
        if verbose:
            console.print_exception()
        return False

def cleanup():
    try:
        config = AppConfig.load()
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

def file_download_menu():
    clear_screen()
    console.print(create_header())
    display_panel(
        "File Download", 
        "Download any file from the web with optimized progress tracking.",
        NordColors.FROST_2
    )
    
    config = AppConfig.load()
    history = FileHistory(os.path.join(CONFIG_DIR, "url_history.txt"))
    url_completer = WordCompleter(config.recent_downloads, sentence=True)
    
    url = pt_prompt(
        "Enter the URL to download: ",
        history=history,
        completer=url_completer,
        style=PTStyle.from_dict({'prompt': f'bold {NordColors.FROST_2}',})
    )
    
    if not url:
        print_error("URL cannot be empty")
        Prompt.ask("Press Enter to return to the main menu")
        return
    
    output_dir = Prompt.ask(
        "Enter the output directory",
        default=config.default_download_dir,
        show_choices=False
    )
    
    verbose = Confirm.ask("Enable verbose mode?", default=False)
    success = download_file(url, output_dir, verbose)
    
    if success:
        if url not in config.recent_downloads:
            config.recent_downloads.insert(0, url)
            config.recent_downloads = config.recent_downloads[:10]
        config.save()
    
    Prompt.ask("Press Enter to return to the main menu")

def youtube_download_menu():
    clear_screen()
    console.print(create_header())
    display_panel(
        "YouTube Download",
        "Download YouTube videos with highest quality merged into MP4.",
        NordColors.FROST_2
    )
    
    if not shutil.which("yt-dlp"):
        display_panel(
            "Dependency Missing",
            "yt-dlp is not installed. Would you like to install it now?",
            NordColors.WARNING
        )
        
        if Confirm.ask("Install yt-dlp?", default=True):
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "yt-dlp"])
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
    youtube_urls = [url for url in config.recent_downloads if "youtube.com" in url or "youtu.be" in url]
    url_completer = WordCompleter(youtube_urls, sentence=True)
    
    url = pt_prompt(
        "Enter the YouTube URL: ",
        history=history,
        completer=url_completer,
        style=PTStyle.from_dict({'prompt': f'bold {NordColors.FROST_2}',})
    )
    
    if not url:
        print_error("URL cannot be empty")
        Prompt.ask("Press Enter to return to the main menu")
        return
    
    output_dir = Prompt.ask(
        "Enter the output directory",
        default=config.default_download_dir,
        show_choices=False
    )
    
    verbose = Confirm.ask("Enable verbose mode?", default=False)
    success = download_youtube(url, output_dir, verbose)
    
    if success:
        if url not in config.recent_downloads:
            config.recent_downloads.insert(0, url)
            config.recent_downloads = config.recent_downloads[:10]
        config.save()
    
    Prompt.ask("Press Enter to return to the main menu")

def view_download_history():
    clear_screen()
    console.print(create_header())
    history = DownloadHistory.load()
    
    if not history.entries:
        display_panel("Download History", "No download history found.", NordColors.FROST_3)
        Prompt.ask("Press Enter to return to the settings menu")
        return
    
    table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        title="Download History",
        border_style=NordColors.FROST_3,
        expand=True
    )
    
    table.add_column("#", style=NordColors.ACCENT, width=3)
    table.add_column("Date", style=NordColors.FROST_2)
    table.add_column("Filename", style=NordColors.SNOW_STORM_1)
    table.add_column("Size", style=NordColors.FROST_3, justify="right")
    table.add_column("Status", style=NordColors.FROST_4)
    
    for i, entry in enumerate(history.entries[:15], 1):
        date_str = datetime.fromisoformat(entry["date"]).strftime("%Y-%m-%d %H:%M")
        status = "[green]Success[/green]" if entry["success"] else "[red]Failed[/red]"
        table.add_row(str(i), date_str, entry["filename"], format_size(entry["size"]), status)
    
    console.print(table)
    
    options = [
        ("1", "View Download Details", "See details for a specific download"),
        ("2", "Clear History", "Delete all download history"),
        ("3", "Return to Settings", "Go back to the settings menu")
    ]
    
    console.print(create_menu_table("History Options", options))
    choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="3")
    
    if choice == "1":
        entry_num = Prompt.ask(
            "Enter download number to view details",
            choices=[str(i) for i in range(1, min(16, len(history.entries) + 1))],
            show_choices=False
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
            NordColors.FROST_2
        )
        
    elif choice == "2":
        if Confirm.ask("Are you sure you want to clear all download history?", default=False):
            history.entries = []
            history.save()
            print_success("Download history cleared")
    
    view_download_history() if choice != "3" else None

def settings_menu():
    clear_screen()
    console.print(create_header())
    display_panel("Settings", "Configure application settings and preferences.", NordColors.FROST_2)
    
    config = AppConfig.load()
    settings_options = [
        ("1", "Change Default Download Directory", config.default_download_dir),
        ("2", "View Recent Downloads", f"{len(config.recent_downloads)} downloads"),
        ("3", "View Download History", "View and manage download history"),
        ("4", "Check Dependencies", "Verify required tools are installed"),
        ("5", "Application Information", "View app details and system info"),
        ("6", "Return to Main Menu", "")
    ]
    
    console.print(create_menu_table("Settings Options", settings_options))
    choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "5", "6"], default="6")
    
    if choice == "1":
        new_dir = Prompt.ask("Enter new default download directory", default=config.default_download_dir)
        
        if os.path.isdir(new_dir):
            config.default_download_dir = new_dir
            config.save()
            print_success(f"Default download directory updated to: {new_dir}")
        elif Confirm.ask(f"Directory '{new_dir}' doesn't exist. Create it?", default=True):
            try:
                ensure_directory(new_dir)
                config.default_download_dir = new_dir
                config.save()
                print_success(f"Created and set default download directory to: {new_dir}")
            except Exception as e:
                print_error(f"Failed to create directory: {e}")
        else:
            print_warning("Directory change canceled")
            
    elif choice == "2":
        if config.recent_downloads:
            recent_table = Table(
                show_header=True,
                header_style=NordColors.HEADER,
                title="Recent Downloads",
                box=ROUNDED,
                border_style=NordColors.FROST_3,
                expand=True
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
        view_download_history()
        
    elif choice == "4":
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
            border_style=NordColors.FROST_3
        )
        
        dep_table.add_column("Dependency", style=NordColors.FROST_1)
        dep_table.add_column("Status", style=NordColors.SNOW_STORM_1)
        dep_table.add_column("Version", style=NordColors.FROST_3)
        
        missing_deps = {}
        
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Checking dependencies..."),
            console=console
        ) as progress:
            check_task = progress.add_task("Checking...", total=len(dependencies))
            
            for name, cmd in dependencies.items():
                installed = shutil.which(name) is not None
                status_text = "Installed" if installed else "Missing"
                status_style = NordColors.GREEN if installed else NordColors.RED
                
                version = "N/A"
                if installed:
                    try:
                        if name == "ffmpeg":
                            version_result = subprocess.run([name, "-version"], capture_output=True, text=True, check=False)
                            if version_result.returncode == 0:
                                version_line = version_result.stdout.split("\n")[0]
                                version = version_line.split(" ")[2] if len(version_line.split(" ")) > 2 else "Unknown"
                        elif name == "yt-dlp":
                            version_result = subprocess.run([name, "--version"], capture_output=True, text=True, check=False)
                            if version_result.returncode == 0:
                                version = version_result.stdout.strip()
                        else:
                            version_result = subprocess.run([name, "--version"], capture_output=True, text=True, check=False)
                            if version_result.returncode == 0:
                                version = version_result.stdout.strip().split("\n")[0]
                    except Exception:
                        version = "Unknown"
                
                dep_table.add_row(name, f"[{status_style}]{status_text}[/{status_style}]", version)
                
                if not installed:
                    missing_deps[name] = cmd
                    
                progress.advance(check_task)
        
        console.print(dep_table)
        
        if missing_deps:
            if Confirm.ask("Install missing dependencies?", default=True):
                with Progress(*NordColors.get_progress_columns(), console=console) as progress:
                    install_task = progress.add_task("Installing", total=len(missing_deps))
                    
                    for name, cmd in missing_deps.items():
                        progress.update(install_task, description=f"Installing {name}...")
                        
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
        system_info = {
            "App Version": VERSION,
            "Python Version": platform.python_version(),
            "macOS Version": platform.mac_ver()[0],
            "Architecture": platform.machine(),
            "User": os.environ.get("USER", "Unknown"),
            "Home Directory": os.path.expanduser("~"),
            "Config Directory": CONFIG_DIR,
        }
        
        info_content = "\n".join([f"{k}: {v}" for k, v in system_info.items()])
        display_panel("Application Information", info_content, NordColors.FROST_2)
        
    Prompt.ask("Press Enter to continue" if choice != "6" else "Press Enter to return to the main menu")
    if choice != "6":
        settings_menu()

def main_menu():
    while True:
        clear_screen()
        console.print(create_header())
        
        main_options = [
            ("1", "Download File", "Download any file from the web with progress tracking"),
            ("2", "Download YouTube", "Download YouTube videos in highest quality as MP4"),
            ("3", "Settings", "Configure application preferences and view history"),
            ("4", "Exit", "Exit the application")
        ]
        
        console.print(create_menu_table("Main Menu", main_options))
        
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
            padding=(1, 2)
        )
        
        console.print(stats_panel)
        choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4"], default="4")
        
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
            TextColumn(f"[bold {NordColors.FROST_2}]Starting macOS Downloader..."),
            console=console
        ) as progress:
            task = progress.add_task("", total=100)
            ensure_config_directory()
            progress.update(task, completed=30, description="Checking configuration...")
            check_ffmpeg()
            progress.update(task, completed=60, description="Verifying dependencies...")
            AppConfig.load()
            progress.update(task, completed=90, description="Loading settings...")
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