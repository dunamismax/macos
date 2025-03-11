#!/usr/bin/env python3
"""
Enhanced Interactive Restore Manager
--------------------------------------------------
A Nord-themed interactive terminal application for restoring VM and Plex data from backups.
Features:
  • Fully interactive, numbered menu system using Rich and Pyfiglet
  • Restoration of VM Libvirt configurations and Plex Media Server data
  • Real-time progress tracking with Rich spinners and progress bars
  • Service control (stop/start) before and after restore operations
  • Detailed logging and error handling

Version: 1.2.0
"""

import atexit
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback for improved error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION: str = "1.2.0"
APP_NAME: str = "Restore Manager"
APP_SUBTITLE: str = "Backup Recovery System"

# System settings
HOSTNAME: str = os.uname().nodename if hasattr(os, "uname") else "Unknown"
LOG_FILE: str = "/var/log/restore_manager.log"

# Define restore tasks (source, target, description, and optional service)
RESTORE_TASKS: Dict[str, Dict[str, str]] = {
    "vm-libvirt-var": {
        "name": "VM Libvirt (var)",
        "description": "Restore VM configurations and storage from /var/lib/libvirt",
        "source": "/home/sawyer/restic_restore/vm-backups/var/lib/libvirt",
        "target": "/var/lib/libvirt",
        "service": "libvirtd",
    },
    "vm-libvirt-etc": {
        "name": "VM Libvirt (etc)",
        "description": "Restore VM config files from /etc/libvirt",
        "source": "/home/sawyer/restic_restore/vm-backups/etc/libvirt",
        "target": "/etc/libvirt",
        "service": "libvirtd",
    },
    "plex": {
        "name": "Plex Media Server",
        "description": "Restore Plex library data and configuration",
        "source": "/home/sawyer/restic_restore/plex-media-server-backup/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "target": "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "service": "plexmediaserver",
    },
}

# File copy settings
BUFFER_SIZE: int = 4 * 1024 * 1024  # 4 MB
MAX_RETRIES: int = 3
RETRY_DELAY: int = 2  # seconds (base delay; exponential backoff applied)
OPERATION_TIMEOUT: int = 120  # seconds


# ----------------------------------------------------------------
# Nord-Themed Colors & Console Setup
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"


# Create a Rich Console instance
console: Console = Console()


# ----------------------------------------------------------------
# Console & Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Generate an ASCII art header using Pyfiglet with a Nord gradient.

    Returns:
        A Rich Panel containing the styled header.
    """
    compact_fonts = ["slant", "small", "smslant", "digital", "mini"]
    ascii_art = ""
    for font in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = f"--- {APP_NAME} ---"
    lines = [line for line in ascii_art.split("\n") if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]
    styled_text = ""
    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "━" * 40 + "[/]"
    styled_text = border + "\n" + styled_text + border
    header = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )
    return header


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message with a prefix."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(text: str) -> None:
    """Print a success message."""
    print_message(text, NordColors.GREEN, "✓")


def print_warning(text: str) -> None:
    """Print a warning message."""
    print_message(text, NordColors.YELLOW, "⚠")


def print_error(text: str) -> None:
    """Print an error message."""
    print_message(text, NordColors.RED, "✗")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a message inside a styled panel."""
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def setup_logging() -> None:
    """Initialize logging by appending a header to the log file."""
    log_dir = Path(LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as log_file:
        log_file.write(
            f"\n--- Restore session started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        )
    print_success(f"Logging to {LOG_FILE}")


def log_message(message: str, level: str = "INFO") -> None:
    """Append a log message with timestamp and level to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as log_file:
        log_file.write(f"{timestamp} - {level} - {message}\n")


# ----------------------------------------------------------------
# Command Execution and Signal Handling
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
) -> subprocess.CompletedProcess:
    """
    Run a system command and return its CompletedProcess.

    Raises:
        Exception if the command fails or times out.
    """
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
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


def cleanup() -> None:
    """Perform cleanup tasks on exit."""
    print_message("Performing cleanup tasks...", NordColors.FROST_3)
    log_message("Cleanup performed during script exit")


def signal_handler(sig: int, frame: Any) -> None:
    """Gracefully handle termination signals."""
    sig_name = signal.Signals(sig).name
    print_warning(f"Process interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers and atexit cleanup
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Core Restore Functions
# ----------------------------------------------------------------
def check_root() -> bool:
    """
    Verify that the script is running with root privileges.

    Returns:
        True if running as root; otherwise, prints error and returns False.
    """
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges")
        log_message("Script execution attempted without root privileges", "ERROR")
        return False
    return True


def control_service(service: str, action: str) -> bool:
    """
    Control a service (start/stop) using systemctl.

    Args:
        service: The name of the service.
        action: The action to perform ('start' or 'stop').

    Returns:
        True if the service reaches the expected state.
    """
    print_message(
        f"{action.capitalize()}ing service '{service}'...", NordColors.FROST_3
    )
    log_message(f"{action.capitalize()}ing service '{service}'")
    try:
        run_command(["systemctl", action, service])
        time.sleep(2)  # Allow time for state change
        status = run_command(
            ["systemctl", "is-active", service], check=False
        ).stdout.strip()
        expected = "active" if action == "start" else "inactive"
        if (action == "start" and status == "active") or (
            action == "stop" and status != "active"
        ):
            print_success(f"Service '{service}' {action}ed successfully")
            log_message(f"Service '{service}' {action}ed successfully")
            return True
        else:
            print_warning(
                f"Service '{service}' did not {action} properly (status: {status})"
            )
            log_message(
                f"Service '{service}' did not {action} properly (status: {status})",
                "WARNING",
            )
            return False
    except Exception as e:
        print_error(f"Failed to {action} service '{service}': {e}")
        log_message(f"Failed to {action} service '{service}': {e}", "ERROR")
        return False


def is_restore_needed(source_path: str, target_path: str) -> bool:
    """
    Determine if restoration is needed by comparing file counts.

    Args:
        source_path: Path to the backup source.
        target_path: Path to the restore destination.

    Returns:
        True if restoration is needed; otherwise, False.
    """
    source = Path(source_path)
    target = Path(target_path)
    if not source.exists():
        print_error(f"Source directory not found: {source}")
        log_message(f"Source directory not found: {source}", "ERROR")
        return False
    if not target.exists():
        print_message(f"Target directory doesn't exist: {target}", NordColors.FROST_3)
        log_message(f"Target directory doesn't exist: {target}")
        return True
    print_message("Comparing file counts...", NordColors.FROST_3)
    source_count = sum(1 for _ in source.rglob("*") if _.is_file())
    target_count = sum(1 for _ in target.rglob("*") if _.is_file())
    if source_count != target_count:
        print_message(
            f"File count differs. Source: {source_count}, Target: {target_count}",
            NordColors.FROST_3,
        )
        log_message(
            f"File count differs. Source: {source_count}, Target: {target_count}"
        )
        return True
    print_message("Source and target directories appear identical", NordColors.FROST_3)
    log_message("Source and target directories appear identical")
    return False


def copy_directory(source_path: str, target_path: str) -> bool:
    """
    Recursively copy files from source to target with progress feedback.

    Args:
        source_path: Source directory.
        target_path: Destination directory.

    Returns:
        True if copy succeeds; otherwise, False.
    """
    source = Path(source_path)
    target = Path(target_path)
    if not source.exists():
        print_error(f"Source directory not found: {source}")
        log_message(f"Source directory not found: {source}", "ERROR")
        return False

    print_message(
        f"Preparing to copy from '{source}' to '{target}'", NordColors.FROST_3
    )
    log_message(f"Starting copy from '{source}' to '{target}'")
    if target.exists():
        try:
            shutil.rmtree(target)
            print_message(
                f"Removed existing target directory: {target}", NordColors.FROST_3
            )
        except Exception as e:
            print_error(f"Failed to remove target directory: {e}")
            log_message(f"Failed to remove target directory: {e}", "ERROR")
            return False

    target.parent.mkdir(parents=True, exist_ok=True)
    file_paths: List[Path] = []
    total_size = 0
    for f in source.rglob("*"):
        if f.is_file():
            file_paths.append(f)
            total_size += f.stat().st_size

    file_count = len(file_paths)
    size_mb = total_size / (1024 * 1024)
    print_message(
        f"Found {file_count} files, total size: {size_mb:.2f} MB", NordColors.FROST_3
    )
    log_message(f"Copying {file_count} files ({size_mb:.2f} MB)")

    copied_size = 0
    errors = []
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        overall_task = progress.add_task("Overall Progress", total=total_size)
        current_task = progress.add_task("Copying...", total=1, visible=False)
        # Create target directories first
        dirs = {target / f.relative_to(source).parent for f in file_paths}
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        for f in file_paths:
            rel_path = f.relative_to(source)
            dest = target / rel_path
            file_size = f.stat().st_size
            progress.update(
                current_task,
                total=file_size,
                completed=0,
                visible=True,
                description=f"Copying {rel_path}",
            )
            for attempt in range(MAX_RETRIES):
                try:
                    with open(f, "rb") as src, open(dest, "wb") as dst:
                        copied = 0
                        while True:
                            buf = src.read(BUFFER_SIZE)
                            if not buf:
                                break
                            dst.write(buf)
                            copied += len(buf)
                            copied_size += len(buf)
                            progress.update(current_task, completed=copied)
                            progress.update(overall_task, completed=copied_size)
                    shutil.copystat(f, dest)
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAY * (2**attempt)
                        progress.update(
                            current_task, description=f"Retry in {delay}s: {rel_path}"
                        )
                        time.sleep(delay)
                    else:
                        errors.append((str(rel_path), str(e)))
                        log_message(f"Failed to copy {rel_path}: {e}", "ERROR")
            progress.update(current_task, visible=False)
    if errors:
        print_warning(f"Encountered {len(errors)} errors during copy")
        log_message(f"Copy completed with {len(errors)} errors", "WARNING")
        for file_err, err in errors[:5]:
            print_error(f"Error copying {file_err}: {err}")
        if len(errors) > 5:
            print_warning(f"...and {len(errors) - 5} more errors")
        return False
    else:
        print_success("Files copied successfully")
        log_message("Copy completed successfully")
        return True


def restore_task(task_key: str) -> bool:
    """
    Execute a single restore task with service control.

    Args:
        task_key: Key of the restore task.

    Returns:
        True if restore succeeds; otherwise, False.
    """
    if task_key not in RESTORE_TASKS:
        print_error(f"Unknown restore task: {task_key}")
        log_message(f"Unknown restore task: {task_key}", "ERROR")
        return False

    config = RESTORE_TASKS[task_key]
    name = config["name"]
    source = config["source"]
    target = config["target"]
    service = config.get("service", "")

    display_panel(
        f"Restoring {name}", style=NordColors.FROST_2, title="Restore Operation"
    )
    log_message(f"Starting restore task: {name}")
    if not is_restore_needed(source, target):
        print_success(f"Restore not needed for {name} – target is already up to date")
        log_message(f"Restore not needed for {name} – target is already up to date")
        return True

    if service:
        if not control_service(service, "stop"):
            if not prompt_yes_no(f"Failed to stop service {service}. Continue anyway?"):
                print_warning(f"Restore of {name} aborted by user")
                log_message(f"Restore of {name} aborted by user", "WARNING")
                return False

    success = copy_directory(source, target)

    if service:
        if not control_service(service, "start"):
            print_warning(f"Failed to restart service {service}")
            log_message(f"Failed to restart service {service}", "WARNING")
            success = False

    if success:
        print_success(f"Successfully restored {name}")
        log_message(f"Successfully restored {name}")
    else:
        print_error(f"Failed to restore {name}")
        log_message(f"Failed to restore {name}", "ERROR")
    return success


def restore_all() -> Dict[str, bool]:
    """
    Restore all defined tasks sequentially.

    Returns:
        A dictionary mapping each task key to its success status.
    """
    results: Dict[str, bool] = {}
    display_panel(
        "Starting batch restore", style=NordColors.FROST_2, title="Batch Restore"
    )
    log_message("Starting restore of all tasks")
    for key in RESTORE_TASKS:
        results[key] = restore_task(key)
        time.sleep(1)  # Brief pause between tasks
    return results


def print_status_report(results: Dict[str, bool]) -> None:
    """
    Display a summary report of restore operations.

    Args:
        results: Dictionary of task results.
    """
    display_panel("Restore Status Report", style=NordColors.FROST_2, title="Results")
    log_message("Generating status report")
    table = Table(
        title="Restore Results", header_style=f"bold {NordColors.FROST_2}", box=None
    )
    table.add_column("Task", style=NordColors.SNOW_STORM_1)
    table.add_column("Status", justify="center")
    table.add_column("Description", style=NordColors.FROST_3)
    for key, success in results.items():
        name = RESTORE_TASKS[key]["name"]
        desc = RESTORE_TASKS[key].get("description", "")
        status_str = "SUCCESS" if success else "FAILED"
        status_style = (
            f"bold {NordColors.GREEN}" if success else f"bold {NordColors.RED}"
        )
        table.add_row(name, f"[{status_style}]{status_str}[/{status_style}]", desc)
    console.print(table)
    success_count = sum(1 for s in results.values() if s)
    total = len(results)
    success_rate = (success_count / total * 100) if total else 0
    summary = (
        f"[bold {NordColors.FROST_2}]Tasks completed:[/] ["
        f"{NordColors.SNOW_STORM_1}]{success_count}/{total} ({success_rate:.1f}%)[/]\n"
        f"[bold {NordColors.FROST_2}]Successful:[/] [{NordColors.GREEN}]{success_count}[/]\n"
        f"[bold {NordColors.FROST_2}]Failed:[/] [{NordColors.RED}]{total - success_count}[/]"
    )
    console.print(
        Panel(
            Text.from_markup(summary),
            title=f"[bold {NordColors.FROST_2}]Summary[/]",
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )
    )
    for key, success in results.items():
        name = RESTORE_TASKS[key]["name"]
        status = "SUCCESS" if success else "FAILED"
        log_message(f"Restore {status} for {name}")


def prompt_yes_no(question: str) -> bool:
    """
    Prompt the user with a yes/no question.

    Args:
        question: The question string.

    Returns:
        True if yes; otherwise, False.
    """
    return Confirm.ask(f"[bold {NordColors.FROST_2}]{question}[/]")


def display_tasks_table() -> None:
    """Display available restore tasks in a formatted table."""
    display_panel("Available Restore Tasks", style=NordColors.FROST_2, title="Tasks")
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        box=None,
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", justify="right", width=4)
    table.add_column("Name", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_column("Source Path", style="dim")
    for i, (key, task) in enumerate(RESTORE_TASKS.items(), 1):
        src = task["source"]
        if len(src) > 40:
            src = src[:20] + "..." + src[-17:]
        table.add_row(str(i), task["name"], task.get("description", ""), src)
    console.print(table)


# ----------------------------------------------------------------
# Interactive Menu Functions
# ----------------------------------------------------------------
def interactive_menu() -> None:
    """
    Main interactive loop displaying a numbered menu and handling user selections.
    """
    while True:
        console.clear()
        console.print(create_header())
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | [{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )
        console.print()
        menu_panel = Panel.fit(
            "[bold]Select an operation:[/]",
            border_style=NordColors.FROST_2,
            padding=(1, 3),
        )
        console.print(menu_panel)
        console.print(f"1. [bold {NordColors.FROST_2}]View Available Restore Tasks[/]")
        console.print(f"2. [bold {NordColors.FROST_2}]Restore Individual Task[/]")
        console.print(f"3. [bold {NordColors.FROST_2}]Restore All Tasks[/]")
        console.print(f"4. [bold {NordColors.FROST_2}]View Previous Restore Log[/]")
        console.print(f"5. [bold {NordColors.RED}]Exit[/]")
        console.print()
        choice = Prompt.ask(
            f"[bold {NordColors.FROST_2}]Enter your choice (1-5)[/]",
            choices=["1", "2", "3", "4", "5"],
        )
        if choice == "1":
            console.clear()
            console.print(create_header())
            display_tasks_table()
            console.print(
                f"[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )
            input()
        elif choice == "2":
            console.clear()
            console.print(create_header())
            display_tasks_table()
            console.print()
            while True:
                task_choice = Prompt.ask(
                    f"[bold {NordColors.FROST_2}]Enter task number (1-{len(RESTORE_TASKS)}) or 'c' to cancel[/]"
                )
                if task_choice.lower() == "c":
                    break
                try:
                    task_num = int(task_choice)
                    if 1 <= task_num <= len(RESTORE_TASKS):
                        task_key = list(RESTORE_TASKS.keys())[task_num - 1]
                        task_name = RESTORE_TASKS[task_key]["name"]
                        if prompt_yes_no(
                            f"Are you sure you want to restore {task_name}?"
                        ):
                            start_time = time.time()
                            success = restore_task(task_key)
                            elapsed = time.time() - start_time
                            if success:
                                print_success(
                                    f"Restore completed in {elapsed:.2f} seconds"
                                )
                            else:
                                print_error(
                                    f"Restore failed after {elapsed:.2f} seconds"
                                )
                        break
                    else:
                        print_error(
                            f"Enter a number between 1 and {len(RESTORE_TASKS)}"
                        )
                except ValueError:
                    print_error("Please enter a valid number")
            console.print(
                f"[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )
            input()
        elif choice == "3":
            console.clear()
            console.print(create_header())
            if prompt_yes_no(
                "Are you sure you want to restore ALL tasks? This may take some time"
            ):
                start_time = time.time()
                results = restore_all()
                elapsed = time.time() - start_time
                print_status_report(results)
                if all(results.values()):
                    print_success(
                        f"All tasks restored successfully in {elapsed:.2f} seconds"
                    )
                else:
                    print_warning(
                        f"Some tasks failed. Total time: {elapsed:.2f} seconds"
                    )
            console.print(
                f"[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )
            input()
        elif choice == "4":
            console.clear()
            console.print(create_header())
            display_panel("Recent Log Entries", style=NordColors.FROST_2, title="Logs")
            try:
                log_path = Path(LOG_FILE)
                if log_path.exists():
                    lines = log_path.read_text().splitlines()
                    recent = lines[-min(20, len(lines)) :]
                    for line in recent:
                        if "ERROR" in line:
                            console.print(line, style=NordColors.RED)
                        elif "WARNING" in line:
                            console.print(line, style=NordColors.YELLOW)
                        else:
                            console.print(line, style=NordColors.FROST_2)
                else:
                    print_warning(f"Log file not found: {LOG_FILE}")
            except Exception as e:
                print_error(f"Error reading log file: {e}")
            console.print(
                f"[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )
            input()
        elif choice == "5":
            console.clear()
            console.print(create_header())
            display_panel(
                "Thank you for using the Restore Manager!",
                style=NordColors.FROST_2,
                title="Exit",
            )
            break
        else:
            print_error("Invalid choice. Please enter a number between 1 and 5")
            time.sleep(1)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main function to initialize and run the interactive restore manager."""
    try:
        console.clear()
        console.print(create_header())
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Starting at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
            )
        )
        setup_logging()
        if not check_root():
            display_panel(
                "This script requires root privileges to function properly.\nPlease run with sudo or as the root user.",
                style=NordColors.RED,
                title="Permission Error",
            )
            sys.exit(1)
        missing_sources = []
        for key, task in RESTORE_TASKS.items():
            if not Path(task["source"]).exists():
                missing_sources.append((task["name"], task["source"]))
        if missing_sources:
            display_panel(
                f"Found {len(missing_sources)} tasks with missing source directories.",
                style=NordColors.YELLOW,
                title="Warning",
            )
            for name, path in missing_sources:
                print_error(f"{name}: {path}")
            if not prompt_yes_no("Continue anyway?"):
                print_error("Exiting due to missing source directories")
                log_message("Script exited due to missing source directories", "ERROR")
                sys.exit(1)
        interactive_menu()
        print_success("Script execution completed")
        log_message("Script execution completed")
    except KeyboardInterrupt:
        print_warning("Script interrupted by user")
        log_message("Script interrupted by user", "WARNING")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        log_message(f"Unhandled error: {e}", "ERROR")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
