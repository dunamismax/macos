#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
youtube_dl.py: A minimalist YouTube Downloader for macOS.
Downloads a single video or a playlist to the ~/Downloads folder.
"""

import os
import sys
import subprocess
import shutil
import platform
from pathlib import Path
from typing import List, Tuple, Optional

# --- Platform Check ---
if platform.system() != "Darwin":
    print(
        "ERROR: This script is designed specifically for macOS. Exiting.",
        file=sys.stderr,
    )
    sys.exit(1)

# --- Constants ---
DOWNLOAD_DIR: Path = Path.home() / "Downloads"
SCRIPT_NAME: str = "Minimal YouTube Downloader"

# --- Dependency Check/Installation ---

# Attempt to import rich first for better output during checks
try:
    from rich.console import Console
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

    console = Console()
    ERROR_STYLE = "bold red"
    SUCCESS_STYLE = "bold green"
    INFO_STYLE = "cyan"
    WARNING_STYLE = "yellow"
except ImportError:
    print("WARNING: 'rich' library not found. Output will be basic.")

    # Define a dummy Console and styles if rich is not available
    class DummyConsole:
        def print(self, msg: str, style: Optional[str] = None):
            print(msg)

    console = DummyConsole()
    ERROR_STYLE = ""
    SUCCESS_STYLE = ""
    INFO_STYLE = ""
    WARNING_STYLE = ""


def print_message(msg: str, style: str = INFO_STYLE):
    """Prints a styled message."""
    console.print(msg, style=style)


def check_or_install_ffmpeg() -> bool:
    """Checks for FFmpeg and attempts installation via Homebrew if missing."""
    if shutil.which("ffmpeg"):
        print_message("✓ FFmpeg found.", SUCCESS_STYLE)
        return True

    print_message("✗ FFmpeg not found.", WARNING_STYLE)
    if not shutil.which("brew"):
        print_message(
            "ERROR: Homebrew is not installed, and FFmpeg is missing.",
            ERROR_STYLE,
        )
        print_message(
            "Please install Homebrew (https://brew.sh) and then run 'brew install ffmpeg'.",
            INFO_STYLE,
        )
        return False

    print_message(
        "Attempting to install FFmpeg via Homebrew ('brew install ffmpeg')...",
        INFO_STYLE,
    )
    try:
        result = subprocess.run(
            ["brew", "install", "ffmpeg"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            if shutil.which("ffmpeg"):
                print_message(
                    "✓ FFmpeg installed successfully via Homebrew!", SUCCESS_STYLE
                )
                return True
            else:
                print_message(
                    "ERROR: FFmpeg installed but still not found in PATH.", ERROR_STYLE
                )
                print_message(
                    "Please check your Homebrew installation and PATH configuration.",
                    INFO_STYLE,
                )
                return False
        else:
            print_message(
                f"ERROR: Failed to install FFmpeg via Homebrew (exit code {result.returncode}).",
                ERROR_STYLE,
            )
            if result.stderr:
                print_message(f"Brew stderr:\n{result.stderr}", WARNING_STYLE)
            return False
    except Exception as e:
        print_message(
            f"ERROR: An unexpected error occurred while trying to install FFmpeg: {e}",
            ERROR_STYLE,
        )
        return False


def check_or_install_yt_dlp() -> bool:
    """Checks if yt-dlp is installed and attempts installation via pip if missing."""
    try:
        # Try importing first
        import yt_dlp

        try:
            version = getattr(
                yt_dlp, "__version__", "unknown"
            )  # Handle older yt-dlp versions without __version__ attribute directly on module
            if version == "unknown" and hasattr(yt_dlp, "version"):
                version = getattr(
                    yt_dlp.version, "__version__", "unknown"
                )  # Newer versions
            print_message(f"✓ yt-dlp found (version: {version}).", SUCCESS_STYLE)
            return True
        except Exception:
            print_message(f"✓ yt-dlp found (version: unknown).", SUCCESS_STYLE)
            return True  # Still usable even if version check fails slightly
    except ImportError:
        print_message("✗ yt-dlp not found.", WARNING_STYLE)
        print_message("Attempting to install yt-dlp using pip...", INFO_STYLE)
        try:
            # Use sys.executable to ensure pip matches the current Python interpreter
            pip_cmd = [sys.executable, "-m", "pip", "install", "--user", "yt-dlp"]
            print_message(f"Running: {' '.join(pip_cmd)}", INFO_STYLE)
            result = subprocess.run(
                pip_cmd, capture_output=True, text=True, check=False
            )

            if result.returncode == 0:
                print_message("✓ yt-dlp installed successfully via pip.", SUCCESS_STYLE)
                print_message(
                    "Please restart the script for the changes to take effect.",
                    INFO_STYLE,
                )
                sys.exit(0)  # Exit cleanly after successful installation
            else:
                print_message(
                    f"ERROR: Failed to install yt-dlp using pip (exit code {result.returncode}).",
                    ERROR_STYLE,
                )
                if result.stderr:
                    print_message(f"Pip stderr:\n{result.stderr}", WARNING_STYLE)
                print_message(
                    "Please try installing manually: 'pip install --user yt-dlp'",
                    INFO_STYLE,
                )
                return False
        except Exception as e:
            print_message(
                f"ERROR: An unexpected error occurred while trying to install yt-dlp: {e}",
                ERROR_STYLE,
            )
            return False


# --- Core Download Logic ---


def run_yt_dlp(url: str, download_dir: Path) -> Tuple[bool, str]:
    """
    Runs the yt-dlp command to download the video/playlist.

    Args:
        url: The YouTube URL.
        download_dir: The directory to download to.

    Returns:
        A tuple (success: bool, message: str).
    """
    # Ensure download directory exists
    try:
        download_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(str(download_dir), os.W_OK):
            raise OSError(f"No write permission for directory: {download_dir}")
    except OSError as e:
        return False, f"Failed to create or access download directory: {e}"

    # Define the output template. %(id)s helps prevent overwriting files with same title.
    output_template = str(download_dir / "%(title)s [%(id)s].%(ext)s")

    # Construct the command based on user requirements
    cmd = [
        "yt-dlp",
        "-f",
        "bestvideo+bestaudio",  # Select best video and audio streams
        "--merge-output-format",
        "mp4",  # Merge into MP4 container
        "-o",
        output_template,  # Define output filename and path
        "--newline",  # Progress on new lines
        # Removed --no-playlist to allow playlist downloads
        url,  # The URL to download
    ]

    print_message(f"Starting download for: {url}", INFO_STYLE)
    print_message(f"Saving to: {download_dir}", INFO_STYLE)
    print_message(f"Command: {' '.join(cmd)}", "dim")  # Print command dimmed

    process: Optional[subprocess.Popen] = None
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Redirect stderr to stdout
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # Line buffered
        )

        # Use rich Progress if available
        if "rich" in sys.modules:
            with Progress(
                SpinnerColumn(spinner_name="dots"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None),
                TaskProgressColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(compact=True),
                console=console,
                transient=False,  # Keep progress visible after completion
            ) as progress:
                download_task = progress.add_task("Initializing...", total=1000)
                current_percent: float = 0.0
                description: str = "Starting..."

                while True:
                    line = process.stdout.readline() if process.stdout else ""
                    if not line and process.poll() is not None:
                        break  # Process finished
                    if not line:
                        continue  # No output yet

                    line = line.strip()
                    if not line:
                        continue

                    console.print(
                        f"[dim] {line}", end="\n"
                    )  # Print yt-dlp output dimmed

                    # --- Live Progress Parsing ---
                    if "[download]" in line and "%" in line:
                        try:
                            parts = line.split()
                            for part in parts:
                                if part.endswith("%"):
                                    percent_str = part.replace("%", "")
                                    # Handle potential escape codes around percentage
                                    cleaned_percent_str = "".join(
                                        filter(
                                            lambda c: c.isdigit() or c == ".",
                                            percent_str,
                                        )
                                    )
                                    if cleaned_percent_str:
                                        current_percent = float(cleaned_percent_str)
                                        description = (
                                            line  # Use the whole line as description
                                        )
                                        progress.update(
                                            download_task,
                                            completed=current_percent
                                            * 10,  # Scale 0-100 to 0-1000
                                            description=description[
                                                : console.width - 50
                                            ],  # Truncate desc
                                        )
                                        break
                        except (ValueError, IndexError):
                            # Ignore lines that look like progress but fail parsing
                            pass
                    elif (
                        "[Merger]" in line
                        or "[ExtractAudio]" in line
                        or "[Fixup" in line
                    ):
                        # Show activity during post-processing steps
                        description = line.split("]", 1)[-1].strip()  # Get text after ]
                        progress.update(
                            download_task, description=description[: console.width - 50]
                        )
                    # --- End Live Progress Parsing ---

                exit_code = process.wait()

                if exit_code == 0:
                    progress.update(
                        download_task,
                        completed=1000,
                        description="[green]Download Complete[/green]",
                    )
                    return True, "Download finished successfully."
                else:
                    progress.update(
                        download_task,
                        completed=current_percent * 10,
                        description=f"[red]Download Failed (code: {exit_code})[/red]",
                    )
                    return (
                        False,
                        f"yt-dlp exited with error code {exit_code}. Check output above for details.",
                    )

        else:  # Basic output if rich is not installed
            while True:
                line = process.stdout.readline() if process.stdout else ""
                if not line and process.poll() is not None:
                    break
                if line:
                    print(line.strip())  # Print raw output

            exit_code = process.wait()
            if exit_code == 0:
                return True, "Download finished successfully."
            else:
                return (
                    False,
                    f"yt-dlp exited with error code {exit_code}. Check output above for details.",
                )

    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}. Is yt-dlp installed and in PATH?"
    except Exception as e:
        print_message(
            f"\nERROR: An unexpected error occurred during download: {e}", ERROR_STYLE
        )
        if process and process.poll() is None:
            process.terminate()  # Attempt to stop the process if it's running
        return False, f"Script error during download execution: {e}"


# --- Main Execution ---


def main():
    """Main function to run the downloader."""
    console.print(f"\n--- {SCRIPT_NAME} ---", style="bold magenta")

    # 1. Check Dependencies
    print_message("\nChecking dependencies...", INFO_STYLE)
    if not check_or_install_ffmpeg():
        print_message(
            "ERROR: FFmpeg is required but could not be found or installed. Exiting.",
            ERROR_STYLE,
        )
        sys.exit(1)
    if not check_or_install_yt_dlp():
        print_message(
            "ERROR: yt-dlp is required but could not be found or installed. Exiting.",
            ERROR_STYLE,
        )
        sys.exit(1)
    print_message("✓ All required dependencies are present.", SUCCESS_STYLE)

    # 2. Get YouTube URL
    print_message("\nEnter the YouTube video or playlist URL to download:")
    try:
        youtube_url = input("> ").strip()
    except EOFError:  # Handle case where input stream is closed (e.g., piping)
        print_message("\nERROR: No input received.", ERROR_STYLE)
        sys.exit(1)
    except KeyboardInterrupt:
        print_message("\nOperation cancelled by user. Exiting.", WARNING_STYLE)
        sys.exit(0)

    if not youtube_url:
        print_message("ERROR: No URL provided. Exiting.", ERROR_STYLE)
        sys.exit(1)

    # Basic URL validation (very simple)
    if not (youtube_url.startswith("http://") or youtube_url.startswith("https://")):
        print_message(
            "WARNING: URL does not look valid (missing http:// or https://). Attempting anyway...",
            WARNING_STYLE,
        )

    # 3. Run Download
    print_message("-" * 30, "dim")  # Separator
    success, message = run_yt_dlp(youtube_url, DOWNLOAD_DIR)
    print_message("-" * 30, "dim")  # Separator

    # 4. Print Result
    if success:
        print_message(f"✓ {message}", SUCCESS_STYLE)
        print_message(f"File(s) should be in: {DOWNLOAD_DIR}", INFO_STYLE)
        # Attempt to reveal the folder in Finder
        try:
            subprocess.run(["open", str(DOWNLOAD_DIR)], check=False)
        except Exception:
            print_message(
                "Could not automatically open the Downloads folder in Finder.",
                WARNING_STYLE,
            )
        sys.exit(0)
    else:
        print_message(f"✗ {message}", ERROR_STYLE)
        sys.exit(1)


if __name__ == "__main__":
    main()
