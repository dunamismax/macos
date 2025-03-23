#!/usr/bin/env python3

import os
import sys
import hashlib
import shutil
import signal
import subprocess
import time
import asyncio
import pwd
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import platform

if platform.system() != "Darwin":
    print("This script is designed for macOS. Exiting.")
    sys.exit(1)


def install_dependencies():
    required_packages = ["rich", "pyfiglet", "prompt_toolkit"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER"))
    try:
        if os.geteuid() != 0:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--user"] + required_packages
            )
        else:
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"]
                + required_packages
            )
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
    from rich.theme import Theme
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style as PtStyle
except ImportError:
    print("Required libraries not found. Installing dependencies...")
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)

install_rich_traceback(show_locals=True)


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

    @classmethod
    def get_frost_gradient(cls, steps=4):
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


console = Console(
    theme=Theme(
        {
            "info": f"bold {NordColors.FROST_2}",
            "warning": f"bold {NordColors.YELLOW}",
            "error": f"bold {NordColors.RED}",
            "success": f"bold {NordColors.GREEN}",
            "filename": f"italic {NordColors.FROST_1}",
        }
    )
)


@dataclass
class AppConfig:
    VERSION: str = "1.1.0"
    APP_NAME: str = "macOS Script Deployer"
    APP_SUBTITLE: str = "File Deployment Utility"
    SOURCE_DIR: str = os.path.expanduser("~/github/macos/scripts")
    DEST_DIR: str = os.path.expanduser("~/bin")
    OWNER_USER: str = "sawyer"
    FILE_PERMISSIONS: int = 0o644
    DIR_PERMISSIONS: int = 0o755
    MAX_WORKERS: int = 4
    TERM_WIDTH: int = 80
    PROGRESS_WIDTH: int = 50
    OWNER_UID: Optional[int] = None
    OWNER_GID: Optional[int] = None

    def __post_init__(self):
        try:
            self.TERM_WIDTH = shutil.get_terminal_size().columns
            self.PROGRESS_WIDTH = min(50, self.TERM_WIDTH - 30)
            pwd_entry = pwd.getpwnam(self.OWNER_USER)
            self.OWNER_UID = pwd_entry.pw_uid
            self.OWNER_GID = pwd_entry.pw_gid
        except Exception:
            pass


class FileStatus(str, Enum):
    NEW = "new"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    FAILED = "failed"


@dataclass
class FileInfo:
    filename: str
    status: FileStatus
    permission_changed: bool = False
    source_path: str = ""
    dest_path: str = ""
    error_message: str = ""


@dataclass
class DeploymentResult:
    new_files: int = 0
    updated_files: int = 0
    unchanged_files: int = 0
    failed_files: int = 0
    permission_changes: int = 0
    files: List[FileInfo] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    @property
    def total_files(self):
        return (
            self.new_files
            + self.updated_files
            + self.unchanged_files
            + self.failed_files
        )

    @property
    def elapsed_time(self):
        return (self.end_time or time.time()) - self.start_time

    def complete(self):
        self.end_time = time.time()

    def add_file(self, file_info: FileInfo):
        self.files.append(file_info)
        if file_info.status == FileStatus.NEW:
            self.new_files += 1
        elif file_info.status == FileStatus.UPDATED:
            self.updated_files += 1
        elif file_info.status == FileStatus.UNCHANGED:
            self.unchanged_files += 1
        elif file_info.status == FileStatus.FAILED:
            self.failed_files += 1
        if file_info.permission_changed:
            self.permission_changes += 1


def create_header():
    config = AppConfig()
    term_width = min(shutil.get_terminal_size().columns - 4, 80)
    fonts = ["slant", "big", "digital", "standard", "small"]
    ascii_art = ""

    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=term_width)
            ascii_art = fig.renderText(config.APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(min(len(ascii_lines), 4))
    styled_text = ""

    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"

    border = f"[{NordColors.FROST_3}]{'━' * (term_width - 6)}[/]"
    styled_text = border + "\n" + styled_text + border

    return Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{config.VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{config.APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(text, style=NordColors.FROST_2, prefix="•"):
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message):
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message):
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message):
    print_message(message, NordColors.RED, "✗")


def print_step(message):
    print_message(message, NordColors.FROST_2, "→")


def display_panel(message, style=NordColors.FROST_2, title=None):
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def cleanup():
    print_message("Cleaning up resources...", NordColors.FROST_3)


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


async def get_file_hash(file_path):
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, lambda: _calculate_hash(file_path))
    except Exception as e:
        raise Exception(f"Failed to calculate hash for {file_path}: {e}")


def _calculate_hash(file_path):
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


async def list_all_files(directory):
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, lambda: _walk_directory(directory))
    except Exception as e:
        raise Exception(f"Failed to list files in {directory}: {e}")


def _walk_directory(directory):
    file_paths = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith(".py") or f.endswith(".sh"):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, directory)
                file_paths.append(rel_path)
    return sorted(file_paths)


async def set_owner(path, config):
    if config.OWNER_UID is None or config.OWNER_GID is None:
        return False
    loop = asyncio.get_running_loop()
    try:
        stat_info = await loop.run_in_executor(None, os.stat, path)
        if (
            stat_info.st_uid == config.OWNER_UID
            and stat_info.st_gid == config.OWNER_GID
        ):
            return False
        await loop.run_in_executor(
            None, lambda: os.chown(path, config.OWNER_UID, config.OWNER_GID)
        )
        return True
    except Exception as e:
        print_warning(f"Failed to set ownership on {path}: {e}")
        return False


async def set_permissions(path, config, is_directory=False):
    loop = asyncio.get_running_loop()
    try:
        owner_changed = await set_owner(path, config)
        permissions = (
            config.DIR_PERMISSIONS if is_directory else config.FILE_PERMISSIONS
        )
        await loop.run_in_executor(None, lambda: os.chmod(path, permissions))
        return owner_changed or True
    except Exception as e:
        print_warning(f"Failed to set permissions on {path}: {e}")
        return False


async def verify_paths(config):
    if not os.path.exists(config.SOURCE_DIR) or not os.path.isdir(config.SOURCE_DIR):
        print_error(f"Source directory invalid: {config.SOURCE_DIR}")
        return False

    if not os.path.exists(config.DEST_DIR):
        try:
            os.makedirs(config.DEST_DIR, exist_ok=True)
            print_step(f"Created destination directory: {config.DEST_DIR}")
            await set_permissions(config.DEST_DIR, config, is_directory=True)
        except Exception as e:
            print_error(f"Failed to create destination directory: {e}")
            return False
    elif not os.path.isdir(config.DEST_DIR):
        print_error(f"Destination path is not a directory: {config.DEST_DIR}")
        return False

    await set_permissions(config.DEST_DIR, config, is_directory=True)
    return True


async def process_file(rel_path, config, progress=None, task_id=None):
    source_path = os.path.join(config.SOURCE_DIR, rel_path)
    dest_path = os.path.join(config.DEST_DIR, rel_path)
    filename = os.path.basename(source_path)
    perm_changed = False

    if progress and task_id is not None:
        progress.update(task_id, description=f"Processing {filename}")

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    if not os.path.exists(dest_path):
        status = FileStatus.NEW
    else:
        try:
            source_hash = await get_file_hash(source_path)
            dest_hash = await get_file_hash(dest_path)
            status = (
                FileStatus.UPDATED if source_hash != dest_hash else FileStatus.UNCHANGED
            )
        except Exception as e:
            print_warning(f"Error comparing file {filename}: {e}")
            status = FileStatus.UPDATED

    if status in (FileStatus.NEW, FileStatus.UPDATED):
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: shutil.copy2(source_path, dest_path)
            )
            perm_changed = await set_permissions(dest_path, config)
        except Exception as e:
            return FileInfo(
                filename=rel_path,
                status=FileStatus.FAILED,
                source_path=source_path,
                dest_path=dest_path,
                error_message=str(e),
            )
    else:
        perm_changed = await set_permissions(dest_path, config)

    if progress and task_id is not None:
        progress.advance(task_id)

    return FileInfo(
        filename=rel_path,
        status=status,
        permission_changed=perm_changed,
        source_path=source_path,
        dest_path=dest_path,
    )


async def deploy_files(config):
    result = DeploymentResult()
    try:
        source_files = await list_all_files(config.SOURCE_DIR)
        if not source_files:
            print_warning("No script or Python files found in source directory")
            result.complete()
            return result
    except Exception as e:
        print_error(str(e))
        result.complete()
        return result

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
        BarColumn(
            bar_width=config.PROGRESS_WIDTH,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Deploying files", total=len(source_files))
        semaphore = asyncio.Semaphore(config.MAX_WORKERS)

        async def process_with_semaphore(file_path):
            async with semaphore:
                return await process_file(file_path, config, progress, task)

        tasks = [
            asyncio.create_task(process_with_semaphore(file_path))
            for file_path in source_files
        ]
        file_results = await asyncio.gather(*tasks)
        for file_info in file_results:
            result.add_file(file_info)

    result.complete()
    return result


def display_deployment_details(config):
    current_user = os.environ.get("USER", "unknown")
    is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
    permission_warning = ""

    if not is_root and config.OWNER_USER != current_user:
        permission_warning = f"\n[bold {NordColors.YELLOW}]Warning: Not running as root. Permission changes may fail.[/]"

    panel_content = f"""
Source: [bold]{config.SOURCE_DIR}[/]
Target: [bold]{config.DEST_DIR}[/]
Owner: [bold]{config.OWNER_USER}[/] (UID: {getattr(config, "OWNER_UID", "Unknown")})
Permissions: [bold]Files: {oct(config.FILE_PERMISSIONS)[2:]}, Dirs: {oct(config.DIR_PERMISSIONS)[2:]}[/]
Running as: [bold]{current_user}[/] ({"root" if is_root else "non-root"})
{permission_warning}
"""
    console.print(
        Panel(
            Text.from_markup(panel_content),
            title=f"[bold {NordColors.FROST_2}]Deployment Details[/]",
            border_style=NordColors.FROST_3,
            padding=(1, 2),
            expand=True,
        )
    )


def create_stats_table(result):
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        expand=True,
        title=f"[bold {NordColors.SNOW_STORM_2}]Deployment Statistics[/]",
        title_justify="center",
    )
    table.add_column("Metric", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)
    table.add_row("New Files", str(result.new_files))
    table.add_row("Updated Files", str(result.updated_files))
    table.add_row("Unchanged Files", str(result.unchanged_files))
    table.add_row("Failed Files", str(result.failed_files))
    table.add_row("Total Files", str(result.total_files))
    table.add_row("Permission Changes", str(result.permission_changes))
    table.add_row("Elapsed Time", f"{result.elapsed_time:.2f} seconds")
    return table


def create_file_details_table(result, max_files=20):
    modified_files = [
        f for f in result.files if f.status in (FileStatus.NEW, FileStatus.UPDATED)
    ]
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        expand=True,
        title=f"[bold {NordColors.SNOW_STORM_2}]Modified Files[/]",
        title_justify="center",
    )
    table.add_column("Filename", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", justify="center")
    table.add_column("Permissions", justify="center")

    display_files = modified_files[:max_files]
    for file_info in display_files:
        if file_info.status == FileStatus.NEW:
            status_text = Text("✓ NEW", style=f"bold {NordColors.GREEN}")
        elif file_info.status == FileStatus.UPDATED:
            status_text = Text("↺ UPDATED", style=f"bold {NordColors.FROST_2}")
        elif file_info.status == FileStatus.FAILED:
            status_text = Text("✗ FAILED", style=f"bold {NordColors.RED}")
        else:
            status_text = Text("● UNCHANGED", style=NordColors.SNOW_STORM_1)

        permission_text = "changed" if file_info.permission_changed else "standard"
        table.add_row(file_info.filename, status_text, permission_text)

    if len(modified_files) > max_files:
        table.add_row(f"... and {len(modified_files) - max_files} more files", "", "")

    return table


async def run_deployment():
    config = AppConfig()
    console.print(create_header())
    print_step(
        f"Starting deployment at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    display_deployment_details(config)

    console.print(
        Panel("Path Verification", style=f"bold {NordColors.FROST_2}", padding=(0, 2))
    )
    if not await verify_paths(config):
        display_panel(
            "Deployment failed due to path verification errors.",
            style=NordColors.RED,
            title="Error",
        )
        sys.exit(1)
    print_success("Source and destination directories verified\n")

    console.print(
        Panel("File Deployment", style=f"bold {NordColors.FROST_2}", padding=(0, 2))
    )
    try:
        result = await deploy_files(config)
        console.print(create_stats_table(result))
        console.print()

        if result.new_files or result.updated_files:
            console.print(create_file_details_table(result))
            console.print()
            display_panel(
                f"Successfully deployed {result.new_files + result.updated_files} files.\n"
                f"Changed permissions on {result.permission_changes} files/dirs.\n"
                f"User '{config.OWNER_USER}' now has appropriate permissions on all deployed files.",
                style=NordColors.GREEN,
                title="Deployment Successful",
            )
        else:
            display_panel(
                f"No files needed updating. All files are already up to date.\n"
                f"Verified permissions on {result.permission_changes} files/dirs.",
                style=NordColors.FROST_3,
                title="Deployment Complete",
            )
    except Exception as e:
        display_panel(
            f"Deployment failed: {str(e)}", style=NordColors.RED, title="Error"
        )
        console.print_exception()
        sys.exit(1)


def main():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_deployment())
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user.")
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
    finally:
        try:
            loop = asyncio.get_event_loop()
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.close()
        except Exception as e:
            print_error(f"Error during shutdown: {e}")
        print_message("Application terminated.", NordColors.FROST_3)


if __name__ == "__main__":
    main()
