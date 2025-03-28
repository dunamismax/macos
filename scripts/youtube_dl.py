#!/usr/bin/env python3

import os
import sys
import time
import json
import signal
import socket
import getpass
import platform
import subprocess
import shutil
import re
import atexit
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path

# --- Platform Check ---
if platform.system() != "Darwin":
    print("ERROR: This script is tailored for macOS. Exiting.")
    sys.exit(1)


# --- Dependency Installation ---
def install_dependencies():
    """Installs required Python packages using pip."""
    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "yt-dlp"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER", getpass.getuser()))
    print(f"Checking/installing dependencies for user: {user}")
    print(f"Required packages: {', '.join(required_packages)}")
    try:
        pip_cmd = [sys.executable, "-m", "pip", "install", "--user"] + required_packages
        if os.geteuid() == 0 and user != "root":
            # If running as root (e.g., via sudo), install for the original user
            print(f"Running pip install as user {user} using sudo -u...")
            subprocess.check_call(["sudo", "-u", user] + pip_cmd)
        else:
            # Running as a normal user or as root for root's own packages
            print("Running pip install directly...")
            subprocess.check_call(pip_cmd)
        print("Dependencies checked/installed successfully.")
        # Trigger restart after install
        print("Restarting script to load new dependencies...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to install dependencies: {e}", file=sys.stderr)
        if hasattr(e, "stderr") and e.stderr:
            print(f"Stderr: {e.stderr.decode()}", file=sys.stderr)
        if hasattr(e, "stdout") and e.stdout:
            print(f"Stdout: {e.stdout.decode()}", file=sys.stderr)
        print("Please try installing the packages manually:", file=sys.stderr)
        print(
            f"  {sys.executable} -m pip install --user {' '.join(required_packages)}",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(
            f"ERROR: An unexpected error occurred during dependency installation: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


# --- Import Third-Party Libraries ---
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from rich.box import ROUNDED, HEAVY
    from rich.style import Style
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PTStyle
    import pyfiglet
    import yt_dlp  # Check specifically for yt_dlp as well
except ImportError:
    print("Required Python libraries not found. Attempting installation...")
    install_dependencies()
    # If install_dependencies succeeds, it will restart the script via os.execv.
    # If it fails, it will sys.exit. This line should ideally not be reached.
    print(
        "Installation failed or did not restart. Please check errors.", file=sys.stderr
    )
    sys.exit(1)


# --- Initialize Rich and Traceback ---
install_rich_traceback(show_locals=True)
console = Console()

# --- Constants ---
APP_NAME = "YT Downloader"
VERSION = "1.0.0"
CONFIG_BASE_DIR = Path.home() / ".config" / "yt_downloader_cli"
HISTORY_DIR = CONFIG_BASE_DIR / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
URL_HISTORY_FILE = HISTORY_DIR / "url_history.txt"
DOWNLOAD_DIR: Path = Path.home() / "Downloads"
HOSTNAME = socket.gethostname()
USERNAME = os.environ.get("SUDO_USER", os.environ.get("USER", getpass.getuser()))


# --- Nord Color Theme ---
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
    DIM = Style(color=POLAR_NIGHT_4, dim=True)
    NORD_BOX = ROUNDED

    @classmethod
    def get_frost_gradient(cls, steps=4):
        return [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4][:steps]


# --- Helper Functions ---


def clear_screen():
    """Clears the terminal screen."""
    console.clear()


def create_header() -> Panel:
    """Creates the application header panel using pyfiglet and rich."""
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
    if not ascii_art:  # Fallback if all fonts fail
        ascii_art = APP_NAME

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    frost_colors = NordColors.get_frost_gradient(min(len(ascii_lines), 4))

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = frost_colors[i % len(frost_colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"

    border_style = NordColors.FROST_3
    # border_char = "═" # Using default box chars is fine
    # border_line = f"[{border_style}]{border_char * (adjusted_width - 8)}[/]"
    # styled_text = border_line + "\n" + styled_text + border_line # Simpler with just panel

    panel = Panel(
        Text.from_markup(styled_text.strip()),
        border_style=NordColors.FROST_1,
        box=NordColors.NORD_BOX,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_3}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]Minimal YouTube Downloader[/]",
        subtitle_align="center",
    )
    return panel


def print_message(text: str, style: Style = NordColors.INFO, prefix: str = "•"):
    """Prints a styled message with a prefix."""
    console.print(f"{prefix} {text}", style=style)


def print_error(message: str):
    """Prints an error message."""
    print_message(message, NordColors.ERROR, "✗")


def print_success(message: str):
    """Prints a success message."""
    print_message(message, NordColors.SUCCESS, "✓")


def print_warning(message: str):
    """Prints a warning message."""
    print_message(message, NordColors.WARNING, "⚠")


def print_info(message: str):
    """Prints an informational message."""
    print_message(message, NordColors.INFO, "ℹ")


def print_dim(message: str):
    """Prints a dimmed message."""
    console.print(message, style=NordColors.DIM)


def display_panel(title: str, message: str, style: Style = NordColors.INFO):
    """Displays text within a styled panel."""
    panel = Panel(
        Text.from_markup(message),  # Allows rich markup in message
        title=title,
        border_style=style,
        box=NordColors.NORD_BOX,
        padding=(1, 2),
    )
    console.print(panel)


def get_prompt_style() -> PTStyle:
    """Returns the style for prompt_toolkit prompts."""
    return PTStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})


def current_time_str() -> str:
    """Returns the current time as a formatted string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --- Tool Check Functions ---


def check_tool(tool_name: str) -> bool:
    """Checks if a command-line tool exists in the system PATH."""
    if shutil.which(tool_name):
        print_success(f"{tool_name} found.")
        return True
    else:
        print_error(f"{tool_name} not found in PATH.")
        return False


def check_brew() -> bool:
    """Checks if Homebrew is installed."""
    return shutil.which("brew") is not None


# --- Core Download Logic ---


def run_yt_dlp_download(url: str, download_dir: Path) -> Tuple[bool, str]:
    """
    Runs the yt-dlp command to download the video/playlist with rich progress.

    Args:
        url: The YouTube URL.
        download_dir: The directory to download to.

    Returns:
        A tuple (success: bool, message: str).
    """
    try:
        download_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(str(download_dir), os.W_OK):
            raise OSError(f"No write permission for directory: {download_dir}")
    except OSError as e:
        return False, f"Failed to create or access download directory: {e}"

    output_template = str(download_dir / "%(title)s [%(id)s].%(ext)s")
    cmd = [
        "yt-dlp",
        "-f",
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format",
        "mp4",
        "-o",
        output_template,
        "--newline",
        url,
    ]

    print_info(f"Starting download for: {url}")
    print_info(f"Saving to: {download_dir}")
    print_dim(f"Command: {' '.join(cmd)}")

    process: Optional[subprocess.Popen] = None
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        # CORRECTED Progress setup: Removed 'style' from TaskProgressColumn,
        # TransferSpeedColumn, and TimeRemainingColumn constructors.
        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(
                "[progress.description]{task.description}", style=NordColors.FROST_2
            ),
            BarColumn(
                bar_width=None,
                style=NordColors.POLAR_NIGHT_3,
                complete_style=NordColors.FROST_1,
            ),
            TaskProgressColumn(),  # Removed style
            TransferSpeedColumn(),  # Removed style
            TimeRemainingColumn(compact=True),  # Removed style
            console=console,
            transient=False,
        ) as progress:
            download_task = progress.add_task("Initializing...", total=1000)
            current_percent: float = 0.0
            description: str = "Starting..."
            last_line: str = ""

            while True:
                line = process.stdout.readline() if process.stdout else ""
                if not line and process.poll() is not None:
                    break
                if not line:
                    continue

                line = line.strip()
                if not line or line == last_line:
                    continue
                last_line = line

                # --- Live Progress Parsing ---
                match = re.search(
                    r"\[download\]\s+(\d+\.?\d*)%\s+of\s+~\s*([\d.]+)(MiB|KiB|GiB)\s+at\s+([\d.]+)(MiB|KiB|GiB)/s\s+ETA\s+(\d{2}:\d{2}:\d{2}|\d{2}:\d{2})",
                    line,
                    re.IGNORECASE,
                )
                match_simple = re.search(
                    r"\[download\]\s+(\d+\.?\d*)%", line, re.IGNORECASE
                )

                if match:
                    try:
                        current_percent = float(match.group(1))
                        total_size_num = float(match.group(2))
                        total_size_unit = match.group(3)
                        # Display total size more dynamically if available from yt-dlp
                        total_size_str = (
                            f"{total_size_num:.1f}{total_size_unit}"
                            if total_size_num > 0
                            else "~"
                        )

                        speed_num = float(match.group(4))
                        speed_unit = match.group(5)
                        speed_str = (
                            f"{speed_num:.1f}{speed_unit}/s" if speed_num > 0 else "..."
                        )

                        eta_str = match.group(6) if match.group(6) else "..."
                        description = (
                            f"Downloading {total_size_str} @ {speed_str} ETA {eta_str}"
                        )

                        # Update progress task
                        progress.update(
                            download_task,
                            completed=current_percent * 10,
                            description=description[
                                : console.width - 55
                            ],  # Adjust truncation slightly
                        )
                    except (ValueError, IndexError) as parse_err:
                        print_warning(
                            f"Could not parse progress line: {line} ({parse_err})"
                        )
                        progress.update(
                            download_task, description=line[: console.width - 55]
                        )

                elif match_simple and not match:
                    try:
                        current_percent = float(match_simple.group(1))
                        description = line  # Show the basic percentage line
                        progress.update(
                            download_task,
                            completed=current_percent * 10,
                            description=description[: console.width - 55],
                        )
                    except (ValueError, IndexError) as parse_err:
                        print_warning(
                            f"Could not parse simple progress line: {line} ({parse_err})"
                        )
                        progress.update(
                            download_task, description=line[: console.width - 55]
                        )

                elif (
                    "[Merger]" in line
                    or "[ExtractAudio]" in line
                    or "[Fixup" in line
                    or "Deleting original file" in line
                ):
                    description = (
                        line.split("]", 1)[-1].strip() if "]" in line else line
                    )
                    progress.update(
                        download_task,
                        completed=max(995, current_percent * 10),
                        description=f"Post-processing: {description}"[
                            : console.width - 55
                        ],
                    )
                elif "has already been downloaded" in line:
                    description = line.split("]", 1)[-1].strip()
                    progress.update(
                        download_task,
                        completed=1000,
                        description=f"[yellow]{description}[/]",
                    )
                elif (
                    "Downloading item" in line and "of" in line
                ):  # Handle playlist progress indication
                    description = line.split("]", 1)[-1].strip()
                    # Reset percentage visually for the new item, but keep description
                    current_percent = 0.0
                    progress.update(
                        download_task,
                        completed=0,
                        description=description[: console.width - 55],
                    )

                elif "[info]" in line or "[debug]" in line:
                    pass  # Ignore these for progress description
                elif line:  # Catch other lines from yt-dlp
                    # Only update description if it seems relevant, avoid overwriting progress info
                    if not description.startswith(
                        "Downloading"
                    ) and not description.startswith("Post-processing"):
                        progress.update(
                            download_task, description=line[: console.width - 55]
                        )
                # --- End Live Progress Parsing ---

            exit_code = process.wait()

            if exit_code == 0:
                current_desc = progress._tasks[download_task].description
                if (
                    "complete" not in current_desc.lower()
                    and "downloaded" not in current_desc.lower()
                ):
                    progress.update(
                        download_task,
                        completed=1000,
                        description="[green]Download Complete[/]",
                    )
                elif "[yellow]" not in current_desc:
                    progress.update(download_task, completed=1000)
                return True, "Download finished successfully."
            else:
                progress.update(
                    download_task,
                    description=f"[red]Download Failed (yt-dlp exit code: {exit_code})[/]",
                )
                # Try to capture last few lines of output on error
                error_context = last_line  # At least the very last line
                return (
                    False,
                    f"yt-dlp exited with error code {exit_code}. Last output: '{error_context}'",
                )

    except FileNotFoundError:
        print_error(f"Command not found: 'yt-dlp'. Is it installed and in PATH?")
        return False, "yt-dlp command not found."
    except Exception as e:
        print_error(f"An unexpected error occurred during download execution: {e}")
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception as term_err:
                print_warning(f"Could not terminate yt-dlp process: {term_err}")
        return False, f"Script error during download execution: {e}"
    finally:
        pass  # 'with' context handles progress stopping


# --- Cleanup and Signal Handling ---


def cleanup():
    """Performs cleanup actions before exiting."""
    try:
        # No specific resources to clean up in this simple script yet
        print_message("Exiting...", NordColors.FROST_3, prefix="👋")
    except Exception:
        # Avoid errors during cleanup itself
        pass


def signal_handler(sig, frame):
    """Handles termination signals gracefully."""
    try:
        sig_name = signal.Signals(sig).name
        print_warning(
            f"\nProcess interrupted by {sig_name} (Signal {sig}). Cleaning up..."
        )
    except Exception:
        print_warning(f"\nProcess interrupted by Signal {sig}. Cleaning up...")
    # Cleanup is registered with atexit, so it will run automatically on sys.exit
    sys.exit(128 + sig)  # Standard exit code for signal termination


signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Handle termination request
atexit.register(cleanup)

# --- Main Execution ---


def main():
    """Main function to run the downloader."""
    try:
        clear_screen()
        console.print(create_header())
        console.print(
            f"[dim]{current_time_str()} | Host: {HOSTNAME} | User: {USERNAME}[/dim]"
        )

        # 1. Check External Dependencies (ffmpeg)
        print_info("Checking for required external tools...")
        ffmpeg_ok = check_tool("ffmpeg")
        if not ffmpeg_ok:
            if check_brew():
                print_warning("FFmpeg is required for merging formats.")
                print_info("You can install it using Homebrew:")
                print_dim("  brew install ffmpeg")
            else:
                print_warning("FFmpeg is required but not found.")
                print_info("Please install FFmpeg manually.")
            # Allow continuing, yt-dlp might work without merge for some formats
            # if not Confirm.ask("FFmpeg not found. Continue anyway?", default=True):
            #     sys.exit(1)
        # yt-dlp dependency is checked via import at the top

        # 2. Get YouTube URL
        print_info(
            f"Enter the YouTube video or playlist URL (downloads to: {DOWNLOAD_DIR})"
        )
        try:
            # Ensure history file exists
            if not URL_HISTORY_FILE.exists():
                URL_HISTORY_FILE.touch()

            youtube_url = pt_prompt(
                "> ",
                history=FileHistory(str(URL_HISTORY_FILE)),
                auto_suggest=AutoSuggestFromHistory(),
                style=get_prompt_style(),
            ).strip()
        except EOFError:
            print_error("\nNo input received. Exiting.")
            sys.exit(1)
        # KeyboardInterrupt is handled by the signal handler

        if not youtube_url:
            print_error("No URL provided. Exiting.")
            sys.exit(1)

        # Basic URL validation
        if not (
            youtube_url.startswith("http://") or youtube_url.startswith("https://")
        ):
            # Allow non-http URLs as yt-dlp might support other identifiers
            print_warning(
                f"Input '{youtube_url}' doesn't look like a standard URL. Attempting anyway..."
            )

        # 3. Run Download
        console.rule(style=NordColors.FROST_4)  # Separator
        success, message = run_yt_dlp_download(youtube_url, DOWNLOAD_DIR)
        console.rule(style=NordColors.FROST_4)  # Separator

        # 4. Print Result and Open Finder
        if success:
            print_success(message)
            print_info(f"File(s) saved in: {DOWNLOAD_DIR}")
            try:
                print_info("Attempting to open download folder in Finder...")
                subprocess.run(["open", str(DOWNLOAD_DIR)], check=True)
            except Exception as e:
                print_warning(f"Could not automatically open folder in Finder: {e}")
            sys.exit(0)
        else:
            print_error(message)
            sys.exit(1)

    except KeyboardInterrupt:
        # Should be caught by signal handler, but as a fallback
        print_warning("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print_error(f"An unexpected error occurred in the main execution: {e}")
        # Display rich traceback for unexpected errors
        console.print_exception(show_locals=True)
        sys.exit(1)
    # finally:
    # Cleanup is handled by atexit


if __name__ == "__main__":
    main()
