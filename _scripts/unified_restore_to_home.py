#!/usr/bin/env python3
"""
Unified Restore Script
--------------------------------------------------
A powerful, interactive terminal-based tool for restoring data from Backblaze B2 using Restic.
It automatically discovers Restic repositories in the specified B2 bucket, checks their snapshot status,
and allows you to restore one or more repositories into designated subdirectories.
All output is styled with a Nord-themed interface using Rich and Pyfiglet.

Version: 1.1.0
"""

import atexit
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "This script requires the 'rich' and 'pyfiglet' libraries. Install with: pip install rich pyfiglet"
    )
    sys.exit(1)

# Install rich traceback for better error diagnostics
install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# Application Configuration
# ----------------------------------------------------------------
class AppConfig:
    """Configuration settings for the Unified Restore Script."""

    VERSION: str = "1.1.0"
    APP_NAME: str = "Unified Restore"
    APP_SUBTITLE: str = "B2 & Restic Recovery Tool"

    # B2 & Restic Settings
    B2_CLI: str = "/home/sawyer/.local/bin/b2"  # Adjust if needed
    B2_ACCOUNT_ID: str = "12345678"
    B2_ACCOUNT_KEY: str = "12345678"
    B2_BUCKET: str = "sawyer-backups"
    RESTIC_PASSWORD: str = "12345678"  # Restic password

    # Restore Directory
    RESTORE_BASE: Path = Path("/home/sawyer/restic_restore")

    # Retry Settings
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 5  # seconds

    # Logging
    LOG_FILE: Path = Path("/var/log/unified_restore.log")


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for theming."""

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


# ----------------------------------------------------------------
# Console Setup
# ----------------------------------------------------------------
console: Console = Console()


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Repository:
    """
    Represents a Restic repository.

    Attributes:
        name: A friendly name or identifier for the repository.
        path: The full repository path used by Restic.
        has_snapshots: True if snapshots exist, False if empty, None if unknown.
    """

    name: str
    path: str
    has_snapshots: Optional[bool] = None


# ----------------------------------------------------------------
# Logging Helpers
# ----------------------------------------------------------------
def setup_logging() -> None:
    """Ensure the log file directory exists and log the session start."""
    log_dir = AppConfig.LOG_FILE.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    with AppConfig.LOG_FILE.open("a") as log_file:
        log_file.write(
            f"\n--- Restore session started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        )
    print_message(f"Logging to {AppConfig.LOG_FILE}", NordColors.FROST_1)


def log_message(message: str, level: str = "INFO") -> None:
    """Append a log message to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with AppConfig.LOG_FILE.open("a") as log_file:
        log_file.write(f"{timestamp} - {level} - {message}\n")


# ----------------------------------------------------------------
# UI Components
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Generate an ASCII art header using Pyfiglet and style it with Nord colors.
    Returns a Rich Panel containing the header.
    """
    fonts = ["slant", "small", "smslant", "mini", "digital"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(AppConfig.APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = f"{AppConfig.APP_NAME}"

    # Apply gradient effect using Nord colors
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
    border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    header_text = f"{border}\n{styled}{border}"
    return Panel(
        Text.from_markup(header_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{AppConfig.VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{AppConfig.APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message to the console."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a message in a styled Rich panel."""
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exiting."""
    print_message("Cleaning up...", NordColors.FROST_3)
    log_message("Cleanup initiated")


def signal_handler(sig: int, frame: Any) -> None:
    """Handle termination signals gracefully."""
    sig_name = signal.Signals(sig).name
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    log_message(f"Process interrupted by {sig_name}", "WARNING")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers and cleanup
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Repository Operations
# ----------------------------------------------------------------
def check_root() -> bool:
    """
    Check if the script is running with root privileges.
    Returns True if running as root; otherwise, display an error and return False.
    """
    if os.geteuid() != 0:
        display_panel(
            "This script must be run with root privileges to restore file permissions.",
            style=NordColors.RED,
            title="Insufficient Privileges",
        )
        log_message("Script not running with root privileges", "ERROR")
        return False
    return True


def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    capture_output: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """
    Execute a system command.
    Retries are handled at a higher level when needed.
    """
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=True,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_message(f"Command failed: {' '.join(cmd)}", NordColors.RED, "✗")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_message(f"Command timed out after {timeout} seconds", NordColors.RED, "✗")
        raise
    except Exception as e:
        print_message(f"Error executing command: {e}", NordColors.RED, "✗")
        raise


def scan_for_repos() -> Dict[int, Repository]:
    """
    Scan the B2 bucket recursively for Restic repositories.
    A repository is identified by a 'config' file.
    Returns a dictionary mapping numbers to Repository objects.
    """
    display_panel(
        f"Scanning B2 bucket '{AppConfig.B2_BUCKET}' for restic repositories...",
        style=NordColors.FROST_3,
        title="Repository Discovery",
    )
    repos: Dict[int, Repository] = {}
    seen: Set[str] = set()

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Scanning repositories..."),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TextColumn(f"[bold {NordColors.SNOW_STORM_1}]Please wait..."),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning", total=None)
        cmd = [AppConfig.B2_CLI, "ls", AppConfig.B2_BUCKET, "--recursive"]
        result = run_command(cmd)
        for line in result.stdout.splitlines():
            line = line.strip()
            parts = line.split("/")
            if parts[-1] == "config" and len(parts) > 1:
                repo_folder = "/".join(parts[:-1])
                if repo_folder in seen:
                    continue
                seen.add(repo_folder)
                repo_name = repo_folder.split("/")[-1]
                repo_path = f"b2:{AppConfig.B2_BUCKET}:{repo_folder}"
                repos[len(repos) + 1] = Repository(name=repo_name, path=repo_path)
                progress.update(
                    task,
                    description=f"[bold {NordColors.FROST_2}]Found {len(repos)} repositories",
                )
        progress.update(task, description=f"[bold {NordColors.FROST_2}]Scan complete")
    if repos:
        print_message(f"Found {len(repos)} restic repositories", NordColors.GREEN, "✓")
        log_message(f"Found {len(repos)} repositories in bucket {AppConfig.B2_BUCKET}")
    else:
        print_message(
            f"No restic repositories found in bucket {AppConfig.B2_BUCKET}",
            NordColors.YELLOW,
            "⚠",
        )
        log_message(f"No repositories found in bucket {AppConfig.B2_BUCKET}", "WARNING")
    return repos


def run_restic(
    repo: str, args: List[str], capture_output: bool = True
) -> subprocess.CompletedProcess:
    """
    Run a restic command with the proper environment settings.
    Retries the command on transient errors up to MAX_RETRIES.
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = AppConfig.RESTIC_PASSWORD
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = AppConfig.B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = AppConfig.B2_ACCOUNT_KEY
    cmd = ["restic", "--repo", repo] + args
    log_message(f"Running restic command: {' '.join(cmd)}")
    retries = 0
    while retries <= AppConfig.MAX_RETRIES:
        try:
            return run_command(cmd, env=env, capture_output=capture_output)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or str(e)
            if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                retries += 1
                delay = AppConfig.RETRY_DELAY * (2 ** (retries - 1))
                print_message(
                    f"Transient error; retrying in {delay} seconds (attempt {retries}/{AppConfig.MAX_RETRIES})",
                    NordColors.YELLOW,
                    "⚠",
                )
                log_message(
                    f"Transient error; retrying in {delay} seconds (attempt {retries}/{AppConfig.MAX_RETRIES})",
                    "WARNING",
                )
                time.sleep(delay)
            else:
                display_panel(
                    f"Restic command failed: {error_msg}",
                    style=NordColors.RED,
                    title="Command Error",
                )
                log_message(f"Restic command failed: {error_msg}", "ERROR")
                raise
    err = f"Max retries ({AppConfig.MAX_RETRIES}) exceeded for restic command"
    display_panel(err, style=NordColors.RED, title="Error")
    log_message(err, "ERROR")
    raise RuntimeError(err)


def get_latest_snapshot(repo: str) -> Optional[str]:
    """
    Retrieve the latest snapshot ID from the repository.
    Returns the snapshot ID or None if no snapshots are found.
    """
    print_message(f"Retrieving latest snapshot for {repo}...", NordColors.FROST_2, ">")
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Retrieving snapshots..."),
        console=console,
    ) as progress:
        task = progress.add_task("Retrieving", total=None)
        result = run_restic(repo, ["snapshots", "--json"], capture_output=True)
        snapshots = json.loads(result.stdout) if result.stdout else []
    if not snapshots:
        print_message(
            f"No snapshots found in repository: {repo}", NordColors.YELLOW, "⚠"
        )
        log_message(f"No snapshots found in repository: {repo}", "WARNING")
        return None
    latest = max(snapshots, key=lambda s: s.get("time", ""))
    snap_id = latest.get("id")
    snap_date = latest.get("time", "").split("T")[0]
    print_message(f"Latest snapshot: {snap_id} from {snap_date}", NordColors.GREEN, "✓")
    log_message(f"Latest snapshot for {repo}: {snap_id} from {snap_date}")
    return snap_id


def restore_repo(repo: str, target: Path) -> bool:
    """
    Restore the latest snapshot from a repository into the target directory.
    Returns True if successful.
    """
    display_panel(
        f"Restoring repository: {repo}",
        style=NordColors.FROST_3,
        title="Restore Operation",
    )
    log_message(f"Starting restore of {repo} into {target}")
    snap_id = get_latest_snapshot(repo)
    if not snap_id:
        display_panel(
            f"Cannot restore {repo} - no snapshots found.",
            style=NordColors.RED,
            title="Restore Error",
        )
        log_message(f"Skipping restore for {repo} – no snapshot found.", "ERROR")
        return False
    target.mkdir(parents=True, exist_ok=True)
    print_message(
        f"Restoring snapshot {snap_id} into {target}...", NordColors.FROST_2, ">"
    )
    log_message(f"Restoring snapshot {snap_id} into {target}")
    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Restoring data"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[bold {NordColors.SNOW_STORM_1}]Please wait..."),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Restoring", total=None)
            run_restic(
                repo, ["restore", snap_id, "--target", str(target)], capture_output=True
            )
            if not any(target.iterdir()):
                display_panel(
                    f"Restore failed: {target} is empty.",
                    style=NordColors.RED,
                    title="Restore Failed",
                )
                log_message(f"Restore failed: {target} is empty.", "ERROR")
                return False
        display_panel(
            f"Successfully restored into {target}",
            style=NordColors.GREEN,
            title="Restore Complete",
        )
        log_message(f"Restored {repo} into {target}")
        return True
    except Exception as e:
        display_panel(
            f"Restore failed for {repo}: {e}",
            style=NordColors.RED,
            title="Restore Error",
        )
        log_message(f"Restore failed for {repo}: {e}", "ERROR")
        return False


# ----------------------------------------------------------------
# Menu and UI Helpers
# ----------------------------------------------------------------
def create_repo_table(repos: Dict[int, Repository]) -> Table:
    """
    Create a table displaying available repositories.
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Available Restic Repositories[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", justify="right", width=4)
    table.add_column("Repository Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("Path", style=NordColors.SNOW_STORM_1)
    table.add_column("Status", justify="center", width=10)
    for idx, repo in repos.items():
        if repo.has_snapshots is True:
            status = Text("● READY", style=f"bold {NordColors.GREEN}")
        elif repo.has_snapshots is False:
            status = Text("● EMPTY", style=f"bold {NordColors.YELLOW}")
        else:
            status = Text("○ UNKNOWN", style=f"dim {NordColors.POLAR_NIGHT_4}")
        table.add_row(str(idx), repo.name, repo.path, status)
    return table


def display_repos(repos: Dict[int, Repository]) -> None:
    """Display the repository table."""
    if not repos:
        display_panel(
            "No repositories found. Try manual input.",
            style=NordColors.YELLOW,
            title="No Repositories",
        )
        return
    console.print(create_repo_table(repos))


def check_snapshot_status(repos: Dict[int, Repository]) -> Dict[int, Repository]:
    """
    Check snapshot availability for each repository.
    Updates each repository’s 'has_snapshots' field.
    """
    display_panel(
        "Checking snapshot availability...",
        style=NordColors.FROST_3,
        title="Snapshot Verification",
    )
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Checking repository"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        console=console,
    ) as progress:
        task = progress.add_task("Checking", total=len(repos))
        for idx, repo in repos.items():
            progress.update(
                task, description=f"[bold {NordColors.FROST_2}]Checking {repo.name}"
            )
            try:
                result = run_restic(
                    repo.path, ["snapshots", "--json"], capture_output=True
                )
                snapshots = json.loads(result.stdout) if result.stdout else []
                repo.has_snapshots = len(snapshots) > 0
            except Exception:
                repo.has_snapshots = None
            progress.advance(task)
    return repos


def select_repos(repos: Dict[int, Repository]) -> Dict[int, Repository]:
    """
    Prompt the user to select repositories to restore.
    Returns a dictionary of selected repositories.
    """
    if not repos:
        return {}
    repos = check_snapshot_status(repos)
    display_repos(repos)
    while True:
        console.print(
            f"\n[bold {NordColors.FROST_2}]Enter repository numbers (space-separated) or 'all':[/]",
            end=" ",
        )
        selection = input().strip().lower()
        if not selection:
            print_message(
                "No selection made. Please try again.", NordColors.YELLOW, "⚠"
            )
            continue
        if selection == "all":
            print_message("All repositories selected.", NordColors.GREEN, "✓")
            return repos
        try:
            choices = [int(num) for num in selection.split()]
            invalid = [num for num in choices if num not in repos]
            if invalid:
                print_message(
                    f"Invalid selections: {', '.join(map(str, invalid))}",
                    NordColors.RED,
                    "✗",
                )
                continue
            selected = {num: repos[num] for num in choices}
            if not selected:
                print_message(
                    "No valid repositories selected. Please try again.",
                    NordColors.YELLOW,
                    "⚠",
                )
                continue
            print_message(
                f"Selected {len(selected)} repositories for restore.",
                NordColors.GREEN,
                "✓",
            )
            return selected
        except ValueError:
            print_message(
                "Invalid input. Enter numbers separated by spaces.", NordColors.RED, "✗"
            )


def single_repo_input() -> Dict[int, Repository]:
    """
    Prompt for manual repository path input.
    Returns a dictionary with a single Repository.
    """
    display_panel(
        "Enter a complete Restic repository path.",
        style=NordColors.FROST_3,
        title="Manual Repository Input",
    )
    console.print(
        f"[bold {NordColors.FROST_2}]Repository path (e.g., 'b2:{AppConfig.B2_BUCKET}:some/repo'):[/]"
    )
    repo_path = input("> ").strip()
    if not repo_path:
        print_message("No repository path provided.", NordColors.RED, "✗")
        return {}
    repo_name = (
        repo_path.split(":")[-1].split("/")[-1] if ":" in repo_path else "manual-repo"
    )
    return {1: Repository(name=repo_name, path=repo_path)}


def print_summary(results: Dict[str, bool], total_time: float) -> None:
    """
    Display a summary of restore operations in a table.
    """
    display_panel(
        "Restore Operations Summary", style=NordColors.FROST_1, title="Summary"
    )
    if not results:
        print_message("No repositories were restored.", NordColors.YELLOW, "⚠")
        return
    successful = sum(1 for success in results.values() if success)
    failed = len(results) - successful
    summary_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        border_style=NordColors.FROST_3,
    )
    summary_table.add_column("Metric", style=f"bold {NordColors.FROST_2}")
    summary_table.add_column("Value", style=NordColors.SNOW_STORM_1)
    summary_table.add_row("Total repositories", str(len(results)))
    summary_table.add_row(
        "Successfully restored", f"[bold {NordColors.GREEN}]{successful}[/]"
    )
    summary_table.add_row("Failed to restore", f"[bold {NordColors.RED}]{failed}[/]")
    summary_table.add_row("Total restore time", f"{total_time:.2f} seconds")
    console.print(summary_table)
    console.print(f"\n[bold {NordColors.FROST_2}]Repository Results:[/]")
    repo_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        border_style=NordColors.FROST_4,
    )
    repo_table.add_column("Repository", style=NordColors.FROST_2)
    repo_table.add_column("Status", justify="center")
    for repo_name, success in results.items():
        status_text = "[bold green]SUCCESS[/]" if success else "[bold red]FAILED[/]"
        repo_table.add_row(repo_name, status_text)
    console.print(repo_table)
    log_message(
        f"Summary: {successful} successful, {failed} failed, {total_time:.2f} seconds"
    )


# ----------------------------------------------------------------
# Interactive Menu
# ----------------------------------------------------------------
def interactive_menu() -> None:
    """
    Display the main interactive menu and handle user selections.
    """
    while True:
        console.clear()
        console.print(create_header())
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Restore Base: {AppConfig.RESTORE_BASE}[/]"
            )
        )
        console.print()
        menu_panel = Panel(
            Text.from_markup(
                f"[bold {NordColors.FROST_2}]1.[/] [bold {NordColors.SNOW_STORM_1}]Scan for Repositories[/]\n"
                f"[bold {NordColors.FROST_2}]2.[/] [bold {NordColors.SNOW_STORM_1}]Enter Repository Path Manually[/]\n"
                f"[bold {NordColors.FROST_2}]3.[/] [bold {NordColors.SNOW_STORM_1}]Exit[/]"
            ),
            border_style=Style(color=NordColors.FROST_3),
            title=f"[bold {NordColors.FROST_2}]Menu Options[/]",
            padding=(1, 2),
        )
        console.print(menu_panel)
        console.print(f"[bold {NordColors.FROST_2}]Select an option (1-3):[/]", end=" ")
        choice = input().strip()
        if choice == "1":
            available_repos = scan_for_repos()
            if not available_repos:
                display_panel(
                    f"No repositories found in bucket {AppConfig.B2_BUCKET}.",
                    style=NordColors.YELLOW,
                    title="No Repositories Found",
                )
                input(f"\nPress Enter to return to the menu...")
                continue
            selected_repos = select_repos(available_repos)
            if selected_repos:
                start_time = time.time()
                results: Dict[str, bool] = {}
                for _, repo in selected_repos.items():
                    target_dir = AppConfig.RESTORE_BASE / repo.name
                    result = restore_repo(repo.path, target_dir)
                    results[repo.name] = result
                total_time = time.time() - start_time
                print_summary(results, total_time)
            input(f"\nPress Enter to return to the menu...")
        elif choice == "2":
            selected_repo = single_repo_input()
            if selected_repo:
                start_time = time.time()
                results: Dict[str, bool] = {}
                for _, repo in selected_repo.items():
                    target_dir = AppConfig.RESTORE_BASE / repo.name
                    result = restore_repo(repo.path, target_dir)
                    results[repo.name] = result
                total_time = time.time() - start_time
                print_summary(results, total_time)
            input(f"\nPress Enter to return to the menu...")
        elif choice == "3":
            display_panel(
                "Thank you for using the Unified Restore Script!",
                style=NordColors.FROST_2,
                title="Goodbye",
            )
            break
        else:
            print_message(
                "Invalid selection, please try again.", NordColors.YELLOW, "⚠"
            )
            time.sleep(1)


# ----------------------------------------------------------------
# Main Application Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """
    Main function to set up the environment and launch the interactive menu.
    """
    console.clear()
    console.print(create_header())
    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
        )
    )
    console.print()
    setup_logging()
    if not check_root():
        input(f"\nPress Enter to exit...")
        sys.exit(1)
    if not AppConfig.RESTORE_BASE.exists():
        try:
            AppConfig.RESTORE_BASE.mkdir(parents=True, exist_ok=True)
            print_message(
                f"Created restore base directory: {AppConfig.RESTORE_BASE}",
                NordColors.GREEN,
                "✓",
            )
        except Exception as e:
            display_panel(
                f"Failed to create restore directory {AppConfig.RESTORE_BASE}: {e}",
                style=NordColors.RED,
                title="Directory Error",
            )
            log_message(
                f"Failed to create restore directory {AppConfig.RESTORE_BASE}: {e}",
                "ERROR",
            )
            input(f"\nPress Enter to exit...")
            sys.exit(1)
    interactive_menu()
    print_message("Script execution completed.", NordColors.GREEN, "✓")
    log_message("Script execution completed.")


# ----------------------------------------------------------------
# Program Entry Point
# ----------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        display_panel(
            "Operation cancelled by user", style=NordColors.YELLOW, title="Cancelled"
        )
        log_message("Script interrupted by user.", "WARNING")
        sys.exit(130)
    except Exception as e:
        display_panel(f"Unhandled error: {e}", style=NordColors.RED, title="Error")
        console.print_exception()
        log_message(f"Unhandled error: {e}", "ERROR")
        sys.exit(1)
