#!/usr/bin/env python3
"""
Enhanced File Operations Toolkit
--------------------------------------------------
A powerful, interactive terminal utility for advanced file management.
Features include:
  • Copying files/directories with real-time progress tracking
  • Moving files/directories with cross-device detection
  • Deleting files/directories with interactive confirmation
  • Finding files using pattern matching and detailed listings
  • Compressing files/directories into tar.gz with compression feedback
  • Calculating file checksums (MD5, SHA1, SHA256, SHA512) with progress
  • Analyzing disk usage with visual summary tables
  • Batch operations for efficient workflows

Note: Some operations may require root privileges.
Version: 2.0.0
"""

import atexit
import datetime
import hashlib
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
from datetime import datetime as dt
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any

import pyfiglet
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TaskID,
)
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from rich.text import Text
from rich.traceback import install as install_rich_traceback
from rich.style import Style
from rich.theme import Theme

# Install rich traceback handler for improved error reporting.
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME = "File Operations Toolkit"
APP_SUBTITLE = "Advanced File Management System"
VERSION = "2.0.0"
HOSTNAME = (
    os.uname().nodename
    if hasattr(os, "uname")
    else os.environ.get("COMPUTERNAME", "Unknown")
)

# Buffer sizes and thresholds
CHUNK_SIZE = 1024 * 1024  # 1 MB (used for checksum/compression progress)
DEFAULT_BUFFER_SIZE = 8192  # Buffer for copy operations
COMPRESSION_LEVEL = 9  # tar.gz compression level
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB

# File category extensions
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".rar", ".7z", ".bz2"}
CODE_EXTENSIONS = {".py", ".js", ".java", ".c", ".cpp", ".h", ".php", ".html", ".css"}
CHECKSUM_ALGORITHMS = ["md5", "sha1", "sha256", "sha512"]

# Terminal width for formatting
TERM_WIDTH = shutil.get_terminal_size().columns


# ----------------------------------------------------------------
# Nord-Themed Colors & Console Setup
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming."""

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


# Create a Rich Console with a basic theme (you may expand the theme if desired)
console = Console(
    theme=Theme(
        {
            "info": f"bold {NordColors.FROST_2}",
            "warning": f"bold {NordColors.YELLOW}",
            "error": f"bold {NordColors.RED}",
            "success": f"bold {NordColors.GREEN}",
            "prompt": f"bold {NordColors.PURPLE}",
        }
    )
)


# ----------------------------------------------------------------
# Helper Functions & UI Components
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Generate an ASCII art header using Pyfiglet with a Nord gradient.
    Returns:
        A Rich Panel containing the styled header.
    """
    fonts = ["slant", "small", "digital", "standard", "mini"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = APP_NAME

    lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled = ""
    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        styled += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]{'━' * min(60, TERM_WIDTH - 10)}[/]"
    header_text = f"{border}\n{styled}{border}"
    return Panel(
        Text.from_markup(header_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
        title_align="right",
    )


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def pause() -> None:
    """Pause and wait for the user to press Enter."""
    console.input(f"\n[bold {NordColors.PURPLE}]Press Enter to continue...[/]")


def print_message(
    message: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message."""
    console.print(f"[{style}]{prefix} {message}[/{style}]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {NordColors.GREEN}]✓ {message}[/]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {NordColors.YELLOW}]⚠ {message}[/]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {NordColors.RED}]✗ {message}[/]")


def print_section(title: str) -> None:
    """Print a section header."""
    border = "═" * min(80, TERM_WIDTH - 4)
    console.print(f"\n[bold {NordColors.FROST_3}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]  {title}[/]")
    console.print(f"[bold {NordColors.FROST_3}]{border}[/]\n")


def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """
    Create a numbered menu table.
    Args:
        title: Title of the menu
        options: List of (number, description) pairs
    Returns:
        A Rich Table.
    """
    table = Table(
        title=title,
        title_style=f"bold {NordColors.FROST_1}",
        show_header=False,
        box=None,
        expand=True,
        border_style=NordColors.FROST_3,
    )
    table.add_column(
        "Option", style=f"bold {NordColors.FROST_3}", width=4, justify="right"
    )
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    for num, desc in options:
        table.add_row(num, desc)
    return table


def format_size(num_bytes: float) -> str:
    """Return human-readable file size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def format_time(seconds: float) -> str:
    """Return human-readable elapsed time."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{int(m)}m {int(s)}s"
    else:
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h)}h {int(m)}m {int(s)}s"


def get_user_input(prompt_text: str, default: str = "") -> str:
    """Prompt for user input with styling."""
    return Prompt.ask(f"[bold {NordColors.FROST_2}]{prompt_text}[/]", default=default)


def get_user_confirmation(prompt_text: str) -> bool:
    """Prompt for yes/no confirmation."""
    return Confirm.ask(f"[bold {NordColors.FROST_2}]{prompt_text}[/]")


# ----------------------------------------------------------------
# Progress Tracking Classes
# ----------------------------------------------------------------
class ProgressManager:
    """
    A context manager that wraps a Rich Progress for uniform progress tracking.
    """

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(
                complete_style=NordColors.FROST_2, finished_style=NordColors.GREEN
            ),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        self.progress.start()
        return self.progress

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()


class Spinner:
    """
    A simple spinner for indeterminate progress.
    """

    def __init__(self, message: str):
        self.message = message
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.index = 0
        self.running = False
        self.thread = None
        self.start_time = 0

    def _spin(self):
        while self.running:
            elapsed = format_time(time.time() - self.start_time)
            console.print(
                f"\r[{NordColors.FROST_1}]{self.spinner_chars[self.index]}[/] "
                f"[{NordColors.FROST_2}]{self.message}[/] [dim]elapsed: {elapsed}[/dim]",
                end="",
            )
            self.index = (self.index + 1) % len(self.spinner_chars)
            time.sleep(0.1)

    def __enter__(self):
        self.running = True
        self.start_time = time.time()
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.running = False
        self.thread.join()
        console.print("\r" + " " * TERM_WIDTH, end="\r")
        if exc_type is None:
            console.print(
                f"[{NordColors.GREEN}]✓[/] [{NordColors.FROST_2}]{self.message}[/] [green]completed[/]"
            )
        else:
            console.print(
                f"[{NordColors.RED}]✗[/] [{NordColors.FROST_2}]{self.message}[/] [red]failed[/]"
            )


# ----------------------------------------------------------------
# System & Privilege Helpers
# ----------------------------------------------------------------
def check_root_privileges() -> bool:
    """Return True if running as root/admin."""
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def ensure_root() -> None:
    """Warn the user if not running with root privileges."""
    if not check_root_privileges():
        print_warning("Some operations may require root privileges.")
        console.print("[info]Consider running with sudo for full functionality.[/info]")


# ----------------------------------------------------------------
# File Operation Functions
# ----------------------------------------------------------------
def copy_item(src: str, dest: str) -> bool:
    """
    Copy a file or directory with progress feedback.
    Args:
        src: Source path.
        dest: Destination path.
    Returns:
        True if the copy succeeds; otherwise False.
    """
    print_section(f"Copying: {Path(src).name}")
    if not Path(src).exists():
        print_error(f"Source not found: {src}")
        return False
    try:
        if Path(src).is_dir():
            total_size = sum(
                f.stat().st_size for f in Path(src).rglob("*") if f.is_file()
            )
            if total_size == 0:
                print_warning("Directory is empty; nothing to copy.")
                return True
            start_time = time.time()
            with ProgressManager() as progress:
                task = progress.add_task(
                    "Copying directory", total=total_size, color=NordColors.FROST_2
                )
                for root, dirs, files in os.walk(src):
                    rel = os.path.relpath(root, src)
                    target = Path(dest) / rel if rel != "." else Path(dest)
                    target.mkdir(parents=True, exist_ok=True)
                    for file in files:
                        src_file = Path(root) / file
                        dst_file = target / file
                        with src_file.open("rb") as fin, dst_file.open("wb") as fout:
                            while buf := fin.read(DEFAULT_BUFFER_SIZE):
                                fout.write(buf)
                                progress.update(task, advance=len(buf))
                        shutil.copystat(src_file, dst_file)
            elapsed = time.time() - start_time
            print_success(
                f"Copied directory ({format_size(total_size)}) in {format_time(elapsed)}"
            )
        else:
            file_size = Path(src).stat().st_size
            start_time = time.time()
            with ProgressManager() as progress:
                task = progress.add_task(
                    f"Copying {Path(src).name}",
                    total=file_size,
                    color=NordColors.FROST_2,
                )
                with open(src, "rb") as fin, open(dest, "wb") as fout:
                    while buf := fin.read(DEFAULT_BUFFER_SIZE):
                        fout.write(buf)
                        progress.update(task, advance=len(buf))
            shutil.copystat(src, dest)
            elapsed = time.time() - start_time
            print_success(
                f"Copied file ({format_size(file_size)}) in {format_time(elapsed)}"
            )
        return True
    except Exception as e:
        print_error(f"Error copying {src}: {e}")
        return False


def move_item(src: str, dest: str) -> bool:
    """
    Move a file or directory. If source and destination are on different filesystems,
    perform a copy then delete.
    Args:
        src: Source path.
        dest: Destination path.
    Returns:
        True if move succeeds; otherwise False.
    """
    print_section(f"Moving: {Path(src).name}")
    if not Path(src).exists():
        print_error(f"Source not found: {src}")
        return False
    try:
        same_fs = os.stat(src).st_dev == os.stat(Path(dest).parent or ".").st_dev
        start_time = time.time()
        if same_fs:
            os.rename(src, dest)
            print_success(
                f"Moved {src} to {dest} in {format_time(time.time() - start_time)}"
            )
        else:
            print_message(
                "Different filesystem detected: copying then deleting source...",
                NordColors.FROST_2,
                "➜",
            )
            if not copy_item(src, dest):
                return False
            if Path(src).is_dir():
                shutil.rmtree(src)
            else:
                os.remove(src)
            print_success(f"Moved {src} to {dest} by copying and deleting source")
        return True
    except Exception as e:
        print_error(f"Error moving {src}: {e}")
        return False


def delete_item(path: str, force: bool = False) -> bool:
    """
    Delete a file or directory after confirmation.
    Args:
        path: Path to delete.
        force: If True, skip confirmation.
    Returns:
        True if deletion succeeds; otherwise False.
    """
    print_section(f"Deleting: {Path(path).name}")
    if not Path(path).exists():
        print_error(f"Path not found: {path}")
        return False
    if not force and not get_user_confirmation(
        f"Are you sure you want to delete {path}?"
    ):
        print_message("Deletion cancelled", NordColors.FROST_2, "➜")
        return False
    try:
        start_time = time.time()
        if Path(path).is_dir():
            shutil.rmtree(path)
        else:
            os.remove(path)
        print_success(f"Deleted {path} in {format_time(time.time() - start_time)}")
        return True
    except Exception as e:
        print_error(f"Error deleting {path}: {e}")
        return False


def find_files() -> None:
    """
    Search for files matching a pattern in a directory.
    Offers an option to display detailed file information.
    """
    directory = get_user_input("Enter directory to search")
    if not directory or not Path(directory).exists():
        print_error("Invalid directory")
        return
    pattern = get_user_input("Enter search pattern (wildcards allowed)", ".*")
    details = get_user_confirmation("Show detailed file information?")
    print_section(f"Searching in {directory}")
    regex = re.compile(pattern.replace("*", ".*").replace("?", "."), re.IGNORECASE)
    matches = []
    with Spinner("Searching for files"):
        for root, _, files in os.walk(directory):
            for file in files:
                if regex.search(file):
                    matches.append(str(Path(root) / file))
    print_success(f"Found {len(matches)} matching files")
    if details and matches:
        table = Table(
            title="Search Results",
            title_style=f"bold {NordColors.FROST_1}",
            border_style=NordColors.FROST_3,
            highlight=True,
        )
        table.add_column("File Path", style=NordColors.SNOW_STORM_1)
        table.add_column("Size", style=NordColors.FROST_2, justify="right")
        table.add_column("Modified", style=NordColors.FROST_1)
        table.add_column("Type", style=NordColors.FROST_3)
        for match in matches[:100]:
            try:
                p = Path(match)
                size = format_size(p.stat().st_size)
                modified = dt.fromtimestamp(p.stat().st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                ext = p.suffix.lower()
                if ext in DOCUMENT_EXTENSIONS:
                    ftype = "Document"
                elif ext in IMAGE_EXTENSIONS:
                    ftype = "Image"
                elif ext in VIDEO_EXTENSIONS:
                    ftype = "Video"
                elif ext in AUDIO_EXTENSIONS:
                    ftype = "Audio"
                elif ext in ARCHIVE_EXTENSIONS:
                    ftype = "Archive"
                elif ext in CODE_EXTENSIONS:
                    ftype = "Code"
                else:
                    ftype = "Other"
                table.add_row(str(p), size, modified, ftype)
            except Exception as e:
                print_error(f"Error reading {match}: {e}")
        console.print(table)
        if len(matches) > 100:
            print_warning(f"Showing first 100 of {len(matches)} matches")
    else:
        for match in matches[:100]:
            console.print(
                f"[{NordColors.SNOW_STORM_1}]{match}[/{NordColors.SNOW_STORM_1}]"
            )
        if len(matches) > 100:
            print_warning(f"Showing first 100 of {len(matches)} matches")


def compress_files() -> bool:
    """
    Compress a file or directory into a tar.gz archive with progress tracking.
    Returns:
        True if compression succeeds; otherwise False.
    """
    src = get_user_input("Enter source file/directory to compress")
    if not src or not Path(src).exists():
        print_error("Invalid source path")
        return False
    dest = get_user_input("Enter destination archive path (without extension)")
    if not dest:
        print_error("Destination path cannot be empty")
        return False
    if not dest.endswith((".tar.gz", ".tgz")):
        dest = f"{dest}.tar.gz"
    print_section(f"Compressing: {Path(src).name}")
    total_size = 0
    if Path(src).is_dir():
        with Spinner("Calculating total size"):
            total_size = sum(
                f.stat().st_size for f in Path(src).rglob("*") if f.is_file()
            )
    else:
        total_size = Path(src).stat().st_size
    if total_size == 0:
        print_warning("No data to compress.")
        return True
    start_time = time.time()
    try:
        with ProgressManager() as progress:
            task = progress.add_task(
                "Compressing files", total=total_size, color=NordColors.FROST_2
            )
            with (
                open(dest, "wb") as fout,
                tarfile.open(
                    fileobj=fout, mode="w:gz", compresslevel=COMPRESSION_LEVEL
                ) as tar,
            ):

                def progress_filter(ti):
                    if ti.size:
                        progress.update(task, advance=ti.size)
                    return ti

                tar.add(src, arcname=Path(src).name, filter=progress_filter)
        elapsed = time.time() - start_time
        out_size = Path(dest).stat().st_size
        ratio = (total_size - out_size) / total_size * 100 if total_size > 0 else 0
        panel = Panel(
            Text.from_markup(
                f"[{NordColors.SNOW_STORM_1}]Original size: {format_size(total_size)}[/]\n"
                f"[{NordColors.SNOW_STORM_1}]Compressed size: {format_size(out_size)}[/]\n"
                f"[bold {NordColors.FROST_2}]Compression ratio: {ratio:.1f}% saved[/]"
            ),
            title=f"[bold {NordColors.GREEN}]Compression Complete[/]",
            border_style=NordColors.FROST_3,
            padding=(1, 2),
        )
        console.print(panel)
        print_success(f"Compressed to {dest} in {format_time(elapsed)}")
        return True
    except Exception as e:
        print_error(f"Error compressing {src}: {e}")
        if Path(dest).exists():
            try:
                Path(dest).unlink()
            except Exception:
                pass
        return False


def calculate_checksum() -> bool:
    """
    Calculate and display the checksum of a file using a chosen algorithm.
    Returns:
        True if checksum calculation succeeds; otherwise False.
    """
    path = get_user_input("Enter file path for checksum calculation")
    if not path or not Path(path).exists() or Path(path).is_dir():
        print_error("Invalid file path")
        return False
    algo_options = [
        (str(i + 1), algo.upper()) for i, algo in enumerate(CHECKSUM_ALGORITHMS)
    ]
    console.print(create_menu_table("Select Checksum Algorithm", algo_options))
    choice = get_user_input("Select algorithm (1-4)", "1")
    try:
        algorithm = CHECKSUM_ALGORITHMS[int(choice) - 1]
    except (ValueError, IndexError):
        print_error("Invalid selection. Defaulting to MD5.")
        algorithm = "md5"
    print_section(f"Calculating {algorithm.upper()} checksum for {Path(path).name}")
    try:
        file_size = Path(path).stat().st_size
        hash_func = hashlib.new(algorithm)
        start_time = time.time()
        with ProgressManager() as progress:
            task = progress.add_task(
                "Reading file", total=file_size, color=NordColors.FROST_2
            )
            with open(path, "rb") as fin:
                while chunk := fin.read(CHUNK_SIZE):
                    hash_func.update(chunk)
                    progress.update(task, advance=len(chunk))
        checksum = hash_func.hexdigest()
        elapsed = time.time() - start_time
        panel = Panel(
            Text.from_markup(f"[bold {NordColors.FROST_2}]{checksum}[/]"),
            title=f"[bold {NordColors.FROST_1}]{algorithm.upper()} Checksum[/]",
            border_style=NordColors.GREEN,
            padding=(1, 2),
        )
        console.print(panel)
        console.print(f"Time taken: {format_time(elapsed)}")
        return True
    except Exception as e:
        print_error(f"Error calculating checksum: {e}")
        return False


def disk_usage() -> bool:
    """
    Analyze disk usage for a given directory and display a summary.
    Returns:
        True if analysis succeeds; otherwise False.
    """
    directory = get_user_input("Enter directory to analyze")
    if not directory or not Path(directory).exists():
        print_error("Invalid directory")
        return False
    threshold_mb = get_user_input("Size threshold in MB (highlight if exceeded)", "100")
    try:
        threshold = int(threshold_mb) * 1024 * 1024
    except ValueError:
        print_warning("Invalid threshold; using default (100 MB)")
        threshold = LARGE_FILE_THRESHOLD
    print_section(f"Analyzing disk usage in {directory}")
    total_size = 0
    file_count = 0
    large_files = []
    category_sizes: Dict[str, int] = {}
    with Spinner("Analyzing directory"):
        for root, _, files in os.walk(directory):
            for file in files:
                try:
                    fp = Path(root) / file
                    size = fp.stat().st_size
                    total_size += size
                    file_count += 1
                    ext = fp.suffix.lower()
                    if ext in DOCUMENT_EXTENSIONS:
                        cat = "Document"
                    elif ext in IMAGE_EXTENSIONS:
                        cat = "Image"
                    elif ext in VIDEO_EXTENSIONS:
                        cat = "Video"
                    elif ext in AUDIO_EXTENSIONS:
                        cat = "Audio"
                    elif ext in ARCHIVE_EXTENSIONS:
                        cat = "Archive"
                    elif ext in CODE_EXTENSIONS:
                        cat = "Code"
                    else:
                        cat = "Other"
                    category_sizes[cat] = category_sizes.get(cat, 0) + size
                    if size > threshold:
                        large_files.append((str(fp), size))
                except Exception:
                    continue
    summary = Table(
        title="Disk Usage Summary",
        title_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
    )
    summary.add_column("Metric", style=NordColors.FROST_2)
    summary.add_column("Value", style=NordColors.SNOW_STORM_1)
    summary.add_row("Total files", str(file_count))
    summary.add_row("Total size", format_size(total_size))
    summary.add_row(f"Files > {format_size(threshold)}", str(len(large_files)))
    console.print(summary)
    if category_sizes:
        cat_table = Table(
            title="Size by File Type",
            title_style=f"bold {NordColors.FROST_1}",
            border_style=NordColors.FROST_3,
        )
        cat_table.add_column("Category", style=NordColors.FROST_2)
        cat_table.add_column("Size", style=NordColors.SNOW_STORM_1, justify="right")
        cat_table.add_column("Percentage", style=NordColors.FROST_1, justify="right")
        for cat, size in sorted(
            category_sizes.items(), key=lambda x: x[1], reverse=True
        ):
            perc = (size / total_size * 100) if total_size > 0 else 0
            cat_table.add_row(cat, format_size(size), f"{perc:.1f}%")
        console.print(cat_table)
    if large_files:
        large_files.sort(key=lambda x: x[1], reverse=True)
        lf_table = Table(
            title=f"Large Files (>{format_size(threshold)})",
            title_style=f"bold {NordColors.FROST_1}",
            border_style=NordColors.FROST_3,
        )
        lf_table.add_column("File", style=NordColors.SNOW_STORM_1)
        lf_table.add_column("Size", style=NordColors.RED, justify="right")
        for file_path, size in large_files[:10]:
            lf_table.add_row(file_path, format_size(size))
        console.print(lf_table)
        if len(large_files) > 10:
            print_warning(f"Showing top 10 of {len(large_files)} large files")
    return True


# ----------------------------------------------------------------
# Batch Operation Functions
# ----------------------------------------------------------------
def batch_operation_menu() -> None:
    """Handle batch file operations (copy, move, delete)."""
    clear_screen()
    console.print(create_header())
    print_section("Batch Operations")
    options = [
        ("1", "Batch Copy"),
        ("2", "Batch Move"),
        ("3", "Batch Delete"),
        ("0", "Back to Main Menu"),
    ]
    console.print(create_menu_table("Operations", options))
    choice = get_user_input("Select operation type (0-3)", "0")
    if choice == "0":
        return
    sources: List[str] = []
    print_section("Enter Source Paths (empty line to finish)")
    while True:
        src = get_user_input("Source path")
        if not src:
            break
        if not Path(src).exists():
            print_warning(f"Path not found: {src} (skipping)")
            continue
        sources.append(src)
    if not sources:
        print_error("No valid source paths provided.")
        return
    if choice in ("1", "2"):
        dest = get_user_input("Enter destination directory")
        if not dest:
            print_error("Destination cannot be empty.")
            return
        if not Path(dest).exists():
            if get_user_confirmation(f"Create destination directory {dest}?"):
                Path(dest).mkdir(parents=True, exist_ok=True)
            else:
                return
        for src in sources:
            target = str(Path(dest) / Path(src).name)
            if choice == "1":
                if not copy_item(src, target):
                    print_warning(f"Failed to copy {src}")
            else:
                if not move_item(src, target):
                    print_warning(f"Failed to move {src}")
    elif choice == "3":
        force = get_user_confirmation("Skip confirmation for each file?")
        for src in sources:
            if not delete_item(src, force):
                print_warning(f"Failed to delete {src}")
    print_success("Batch operation completed.")


# ----------------------------------------------------------------
# Menu System
# ----------------------------------------------------------------
def main_menu() -> None:
    """Display the main menu and process user selection."""
    while True:
        clear_screen()
        console.print(create_header())
        info_panel = Panel(
            Text.from_markup(
                f"[bold {NordColors.FROST_2}]System:[/] {os.uname().sysname if hasattr(os, 'uname') else 'Unknown'} | "
                f"[bold {NordColors.FROST_2}]Time:[/] {dt.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                f"[bold {NordColors.FROST_2}]Root:[/] {'Yes' if check_root_privileges() else 'No'}"
            ),
            border_style=Style(color=NordColors.FROST_4),
            padding=(1, 2),
            title=f"[bold {NordColors.FROST_1}]System Info[/]",
        )
        console.print(Align.center(info_panel))
        options = [
            ("1", "Copy Files/Directories"),
            ("2", "Move Files/Directories"),
            ("3", "Delete Files/Directories"),
            ("4", "Find Files"),
            ("5", "Compress Files/Directories"),
            ("6", "Calculate File Checksum"),
            ("7", "Analyze Disk Usage"),
            ("8", "Batch Operations"),
            ("0", "Exit"),
        ]
        console.print(create_menu_table("Main Menu", options))
        choice = get_user_input("Enter your choice (0-8)", "0")
        if choice == "1":
            copy_menu()
            pause()
        elif choice == "2":
            move_menu()
            pause()
        elif choice == "3":
            delete_menu()
            pause()
        elif choice == "4":
            find_files()
            pause()
        elif choice == "5":
            compress_files()
            pause()
        elif choice == "6":
            calculate_checksum()
            pause()
        elif choice == "7":
            disk_usage()
            pause()
        elif choice == "8":
            batch_operation_menu()
            pause()
        elif choice == "0":
            clear_screen()
            farewell = Panel(
                Text.from_markup(
                    f"[bold {NordColors.FROST_2}]Thank you for using the File Operations Toolkit.[/]\n"
                    f"[{NordColors.SNOW_STORM_1}]Version {VERSION}[/]"
                ),
                border_style=Style(color=NordColors.FROST_1),
                padding=(1, 2),
                title=f"[bold {NordColors.FROST_1}]Goodbye![/]",
            )
            console.print(farewell)
            time.sleep(1)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


# Individual menus for copy, move, and delete operations.
def copy_menu() -> None:
    """Interactive menu for copying files/directories."""
    clear_screen()
    console.print(create_header())
    print_section("Copy Files/Directories")
    src = get_user_input("Enter source file/directory path")
    if not src or not Path(src).exists():
        print_error("Invalid source path.")
        return
    dest = get_user_input("Enter destination path")
    if not dest:
        print_error("Destination cannot be empty.")
        return
    if Path(src).is_file() and not Path(dest).parent.exists():
        if get_user_confirmation(f"Create parent directory {Path(dest).parent}?"):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
    if Path(dest).is_dir():
        dest = str(Path(dest) / Path(src).name)
        console.print(f"[dim]Full destination: {dest}[/]")
    if not copy_item(src, dest):
        print_error("Copy operation failed.")
    else:
        print_success("Copy completed successfully.")


def move_menu() -> None:
    """Interactive menu for moving files/directories."""
    clear_screen()
    console.print(create_header())
    print_section("Move Files/Directories")
    src = get_user_input("Enter source file/directory path")
    if not src or not Path(src).exists():
        print_error("Invalid source path.")
        return
    dest = get_user_input("Enter destination path")
    if not dest:
        print_error("Destination cannot be empty.")
        return
    if Path(src).is_file() and not Path(dest).parent.exists():
        if get_user_confirmation(f"Create parent directory {Path(dest).parent}?"):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
    if Path(dest).is_dir():
        dest = str(Path(dest) / Path(src).name)
        console.print(f"[dim]Full destination: {dest}[/]")
    if not move_item(src, dest):
        print_error("Move operation failed.")
    else:
        print_success("Move completed successfully.")


def delete_menu() -> None:
    """Interactive menu for deleting files/directories."""
    clear_screen()
    console.print(create_header())
    print_section("Delete Files/Directories")
    path = get_user_input("Enter file/directory path to delete")
    if not path or not Path(path).exists():
        print_error("Invalid path.")
        return
    force = get_user_confirmation("Skip confirmation for deletion?")
    if not delete_item(path, force):
        print_error("Deletion failed or cancelled.")
    else:
        print_success("Deletion completed successfully.")


# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_message("Performing cleanup...", NordColors.FROST_3)
    # Additional cleanup steps can be added here.


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main function: sets up the environment and launches the interactive menu."""
    try:
        ensure_root()
        main_menu()
    except KeyboardInterrupt:
        print_warning("\nScript interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
