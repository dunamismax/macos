#!/usr/bin/env python3

import atexit
import json
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import pyfiglet
    import shutil
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.align import Align
    from rich.style import Style
    from rich.prompt import Prompt, Confirm
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
        TaskProgressColumn,
    )
    from rich.traceback import install as install_rich_traceback
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.styles import Style as PtStyle
except ImportError:
    print(
        "Missing required packages. Please install with: pip install rich pyfiglet prompt_toolkit"
    )
    sys.exit(1)

install_rich_traceback(show_locals=True)
console = Console()

HOSTNAME = socket.gethostname()
VERSION = "2.1.0"
APP_NAME = "Restic Backup Manager"
APP_SUBTITLE = "macOS Backup Solution"

B2_ACCOUNT_ID = "YOUR_B2_ACCOUNT_ID"
B2_ACCOUNT_KEY = "YOUR_B2_ACCOUNT_KEY"
B2_BUCKET = "your-backup-bucket"
RESTIC_PASSWORD = "YOUR_RESTIC_PASSWORD"

REPOSITORIES = {
    "system": f"b2:{B2_BUCKET}:{HOSTNAME}/macos-system-backup",
    "vm": f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups",
    "plex": f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup",
}

BACKUP_CONFIGS = {
    "system": {
        "paths": ["/Users", "/Applications", "/Library", "/etc"],
        "excludes": [
            "/Users/*/Downloads",
            "/Users/*/Library/Caches",
            "/Users/*/Library/Application Support/Steam/steamapps",
            "/Users/*/Movies",
            "*.tmp",
            "*.dmg",
            "*.iso",
            "/.DocumentRevisions-V100",
            "/System/Volumes/Data/.DocumentRevisions-V100",
        ],
        "name": "System",
        "description": "User data and system configuration",
    },
    "vm": {
        "paths": ["/Users/*/Virtual Machines", "/opt/homebrew/var/lib/libvirt"],
        "excludes": ["*.log", "*.tmp"],
        "name": "Virtual Machines",
        "description": "VM configuration and storage",
    },
    "plex": {
        "paths": [
            "/Users/*/Library/Application Support/Plex Media Server",
            "/Library/Application Support/Plex Media Server",
        ],
        "excludes": ["Cache", "Crash Reports", "Logs", "Codecs"],
        "name": "Plex Media Server",
        "description": "Plex configuration and data",
    },
}

RETENTION_POLICY = "30d"
LOG_DIR = os.path.expanduser("~/Library/Logs/ResticBackup")
LOG_FILE = f"{LOG_DIR}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
OPERATION_TIMEOUT = 600
COMMAND_TIMEOUT = 60


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
        return [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4][:steps]

    @classmethod
    def get_polar_gradient(cls, steps=4):
        return [
            cls.POLAR_NIGHT_1,
            cls.POLAR_NIGHT_2,
            cls.POLAR_NIGHT_3,
            cls.POLAR_NIGHT_4,
        ][:steps]


def create_header() -> Panel:
    term_width = shutil.get_terminal_size().columns
    max_width = min(term_width - 4, 80)
    fonts = ["slant", "small", "standard", "digital", "banner3", "smslant"]

    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=max_width)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue

    if not ascii_art.strip():
        ascii_art = APP_NAME

    colors = NordColors.get_frost_gradient()
    styled_lines = []
    for i, line in enumerate(ascii_art.splitlines()):
        color = colors[i % len(colors)]
        styled_lines.append(f"[bold {color}]{line}[/]")

    header_text = "\n".join(styled_lines)
    border = f"[{NordColors.FROST_3}]" + "─" * (max_width) + "[/]"
    content = f"{border}\n{header_text}\n{border}"

    return Panel(
        Text.from_markup(content),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        title_align="right",
        subtitle_align="center",
    )


def print_message(text: str, style=NordColors.FROST_2, prefix="•", log=True) -> None:
    message = f"{prefix} {text}"
    console.print(f"[{style}]{message}[/{style}]")
    if log:
        log_message(text)


def print_success(text: str, log=True) -> None:
    print_message(text, NordColors.GREEN, "✓", log)


def print_warning(text: str, log=True) -> None:
    print_message(text, NordColors.YELLOW, "⚠", log)


def print_error(text: str, log=True) -> None:
    print_message(text, NordColors.RED, "✗", log)


def display_panel(message: str, style=NordColors.FROST_2, title=None) -> None:
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def get_user_input(prompt_text: str, default=None) -> str:
    pt_style = PtStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})
    history = InMemoryHistory()
    return pt_prompt(
        f"{prompt_text} ", default=default, style=pt_style, history=history
    )


def wait_for_enter() -> None:
    console.print(f"[{NordColors.SNOW_STORM_1}]Press Enter to continue...[/]", end="")
    input()


def setup_logging() -> None:
    try:
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as log_file:
            log_file.write(
                f"\n--- Backup session started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            )
        print_success(f"Logging to {LOG_FILE}", log=False)
    except Exception as e:
        print_warning(f"Logging setup failed: {e}", log=False)


def log_message(message: str, level="INFO") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a") as log_file:
            log_file.write(f"{timestamp} - {level} - {message}\n")
    except Exception:
        pass


def run_command(
    cmd: List[str],
    env=None,
    check=True,
    capture_output=True,
    timeout=COMMAND_TIMEOUT,
    silent=False,
) -> subprocess.CompletedProcess:
    try:
        if not silent:
            print_message(f"Running: {' '.join(cmd)}", log=False)

        command_env = env if env is not None else os.environ.copy()
        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Running command..."),
            console=console,
        ) as progress:
            task = progress.add_task("", total=None)
            result = subprocess.run(
                cmd,
                env=command_env,
                check=check,
                text=True,
                capture_output=capture_output,
                timeout=timeout,
            )
        return result
    except subprocess.CalledProcessError as e:
        if not silent:
            print_error(f"Command failed: {' '.join(cmd)}", log=False)
            if e.stdout:
                console.print(f"[dim]{e.stdout.strip()}[/dim]")
            if e.stderr:
                console.print(f"[bold {NordColors.RED}]{e.stderr.strip()}[/]")
        log_message(f"Command failed: {' '.join(cmd)}", "ERROR")
        raise
    except subprocess.TimeoutExpired:
        err_msg = f"Command timed out after {timeout} seconds: {' '.join(cmd)}"
        if not silent:
            print_error(err_msg, log=False)
        log_message(err_msg, "ERROR")
        raise
    except Exception as e:
        err_msg = f"Error executing command: {' '.join(cmd)}\nDetails: {str(e)}"
        if not silent:
            print_error(err_msg, log=False)
        log_message(err_msg, "ERROR")
        raise


def cleanup() -> None:
    print_message("Cleaning up...", NordColors.FROST_3, log=False)
    log_message("Cleanup performed")


def signal_handler(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
    except Exception:
        sig_name = f"Signal {sig}"
    print_warning(f"Process interrupted by {sig_name}", log=False)
    log_message(f"Process interrupted by {sig_name}", "WARNING")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


def check_root_privileges() -> bool:
    if os.name == "posix":
        return os.geteuid() == 0
    return False


def install_dependencies() -> bool:
    setup_progress = True

    if not shutil.which("restic"):
        print_warning("Restic not found. Attempting installation...")
        try:
            if shutil.which("brew"):
                run_command(["brew", "install", "restic"])
                setup_progress = shutil.which("restic") is not None
            else:
                print_error(
                    "Homebrew not found. Please install it from https://brew.sh"
                )
                setup_progress = False
        except Exception as e:
            print_error(f"Restic installation failed: {str(e)}")
            setup_progress = False

    if not shutil.which("b2"):
        print_warning("B2 CLI tool not found. Attempting to install via pip...")
        try:
            run_command([sys.executable, "-m", "pip", "install", "--user", "b2"])
            b2_path = shutil.which("b2")
            if b2_path:
                if os.path.exists(b2_path) and not os.access(b2_path, os.X_OK):
                    run_command(["chmod", "+x", b2_path])
                setup_progress = setup_progress and True
            else:
                print_error(
                    "B2 CLI tool installation failed: command not found after installation"
                )
                setup_progress = False
        except Exception as e:
            print_error(f"B2 CLI installation failed: {str(e)}")
            setup_progress = False

    return setup_progress


def authorize_b2() -> bool:
    if B2_ACCOUNT_ID == "YOUR_B2_ACCOUNT_ID" or B2_ACCOUNT_KEY == "YOUR_B2_ACCOUNT_KEY":
        print_error(
            "B2 credentials not configured. Update the script with your actual credentials."
        )
        return False

    try:
        run_command(["b2", "authorize-account", B2_ACCOUNT_ID, B2_ACCOUNT_KEY])
        print_success("B2 CLI tool authorized successfully")
        return True
    except Exception as e:
        print_error(f"B2 authorization failed: {str(e)}")
        return False


def ensure_bucket_exists(bucket: str) -> bool:
    try:
        result = run_command(["b2", "list-buckets"])
        if bucket in result.stdout:
            print_success(f"Bucket '{bucket}' exists")
            return True
        else:
            print_warning(f"Bucket '{bucket}' not found. Creating it...")
            run_command(["b2", "create-bucket", bucket, "allPrivate"])
            print_success(f"Bucket '{bucket}' created")
            return True
    except Exception as e:
        print_error(f"Error ensuring bucket exists: {str(e)}")
        return False


def check_restic_password() -> bool:
    if RESTIC_PASSWORD == "YOUR_RESTIC_PASSWORD":
        print_error(
            "Restic password not configured. Update the script with your actual password."
        )
        return False
    return True


def initialize_repository(service: str) -> bool:
    if not check_restic_password():
        return False

    repo = REPOSITORIES[service]
    env = os.environ.copy()
    env.update({"RESTIC_PASSWORD": RESTIC_PASSWORD})

    display_panel(
        "Repository Initialization", NordColors.FROST_3, title=service.upper()
    )
    print_message(f"Checking repository: {repo}")

    try:
        run_command(["restic", "--repo", repo, "snapshots"], env=env, silent=True)
        print_success("Repository already initialized")
        return True
    except subprocess.CalledProcessError:
        print_warning("Repository not found. Initializing...")
        try:
            run_command(["restic", "--repo", repo, "init"], env=env)
            print_success("Repository initialized successfully")
            return True
        except Exception as e:
            print_error(f"Failed to initialize repository: {str(e)}")
            return False
    except Exception as e:
        print_error(f"Error during repository initialization: {str(e)}")
        return False


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def perform_backup(service: str) -> bool:
    if service not in BACKUP_CONFIGS:
        print_error(f"Unknown service '{service}'")
        return False

    config = BACKUP_CONFIGS[service]
    repo = REPOSITORIES[service]

    display_panel(
        f"{config['name']} Backup", NordColors.FROST_2, title="Backup Operation"
    )
    log_message(f"Starting backup for {config['name']}")

    for path in config["paths"]:
        expanded_path = os.path.expanduser(path)
        if "*" not in expanded_path and not Path(expanded_path).exists():
            print_error(f"Required path {path} not found for {config['name']} backup.")
            log_message(f"Path {path} not found for {config['name']} backup", "ERROR")
            return False

    if not initialize_repository(service):
        return False

    env = os.environ.copy()
    env.update({"RESTIC_PASSWORD": RESTIC_PASSWORD})

    backup_cmd = ["restic", "--repo", repo, "backup"] + config["paths"]
    for excl in config.get("excludes", []):
        backup_cmd.extend(["--exclude", excl])
    backup_cmd.append("--verbose")

    print_message(f"Starting backup for {config['name']}...")
    log_message(f"Executing backup command for {service}")

    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        ) as progress:
            task_id = progress.add_task(f"Backing up {config['name']}...", total=100)

            process = subprocess.Popen(
                backup_cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            output_buffer = []
            pattern = re.compile(r"(\d+\.\d+)% done")

            for line in iter(process.stdout.readline, ""):
                output_buffer.append(line.strip())
                if len(output_buffer) > 10:
                    output_buffer.pop(0)

                match = pattern.search(line)
                if match:
                    percent = float(match.group(1))
                    progress.update(task_id, completed=percent)

            exit_code = process.wait()
            if exit_code != 0:
                print_error(f"Backup failed with exit code {exit_code}")
                log_message(f"Backup failed with exit code {exit_code}", "ERROR")
                log_message(f"Last output: {' | '.join(output_buffer)}", "ERROR")
                return False

        print_success(f"{config['name']} backup completed successfully")
        log_message(f"{config['name']} backup completed successfully")
        return True

    except Exception as e:
        print_error(f"Backup error: {str(e)}")
        log_message(f"Backup error for {service}: {str(e)}", "ERROR")
        return False


def apply_retention(service: str) -> bool:
    repo = REPOSITORIES[service]
    display_panel(
        f"Applying Retention Policy for {BACKUP_CONFIGS[service]['name']}",
        NordColors.FROST_3,
        title="Snapshot Management",
    )

    print_message(f"Keeping snapshots within {RETENTION_POLICY}")
    log_message(f"Applying retention for {service}: {RETENTION_POLICY}")

    env = os.environ.copy()
    env.update({"RESTIC_PASSWORD": RESTIC_PASSWORD})

    retention_cmd = [
        "restic",
        "--repo",
        repo,
        "forget",
        "--prune",
        "--keep-within",
        RETENTION_POLICY,
    ]

    try:
        result = run_command(retention_cmd, env=env, timeout=OPERATION_TIMEOUT)
        console.print(result.stdout.strip(), style=NordColors.SNOW_STORM_1)
        print_success("Retention policy applied successfully")
        return True
    except Exception as e:
        print_error(f"Retention policy application failed: {str(e)}")
        return False


def list_snapshots(service: str) -> bool:
    repo = REPOSITORIES[service]
    display_panel(
        f"{BACKUP_CONFIGS[service]['name']} Snapshots",
        NordColors.FROST_2,
        title="Snapshot List",
    )

    log_message(f"Listing snapshots for {service}")
    env = os.environ.copy()
    env.update({"RESTIC_PASSWORD": RESTIC_PASSWORD})

    try:
        try:
            run_command(
                ["restic", "--repo", repo, "snapshots", "--compact"],
                env=env,
                silent=True,
            )
        except subprocess.CalledProcessError:
            print_warning(f"No repository found for {BACKUP_CONFIGS[service]['name']}")
            return False

        result = run_command(["restic", "--repo", repo, "snapshots", "--json"], env=env)
        snapshots = json.loads(result.stdout)

        if snapshots:
            table = Table(
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
                expand=True,
                title=f"[bold {NordColors.FROST_2}]{BACKUP_CONFIGS[service]['name']} Snapshots[/]",
                border_style=NordColors.FROST_3,
            )

            table.add_column("ID", style=f"bold {NordColors.FROST_4}", no_wrap=True)
            table.add_column("Date", style=NordColors.SNOW_STORM_1)
            table.add_column("Size", style=NordColors.SNOW_STORM_1)
            table.add_column("Paths", style=NordColors.SNOW_STORM_1)

            for snap in snapshots:
                sid = snap.get("short_id", "unknown")
                time_str = snap.get("time", "")

                try:
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

                size_str = "N/A"
                if "summary" in snap and "total_size" in snap["summary"]:
                    size_str = format_size(snap["summary"]["total_size"])

                paths = ", ".join(snap.get("paths", []))
                table.add_row(sid, time_str, size_str, paths)

            console.print(table)
            log_message(f"Found {len(snapshots)} snapshots for {service}")
        else:
            print_warning("No snapshots found")
            log_message("No snapshots found", "WARNING")

        return True

    except Exception as e:
        print_error(f"Failed to list snapshots: {str(e)}")
        return False


def backup_service(service: str) -> bool:
    config = BACKUP_CONFIGS.get(service)
    if not config:
        print_error(f"Unknown service: {service}")
        return False

    print_message(f"Starting {config['name']} backup workflow...")
    log_message(f"Starting {service} backup workflow")

    if not perform_backup(service):
        return False

    if not apply_retention(service):
        print_warning("Backup succeeded but retention policy application failed")
        return True  # Continue even if retention fails

    if not list_snapshots(service):
        print_warning("Backup and retention succeeded but listing snapshots failed")

    return True


def backup_all_services() -> Dict[str, bool]:
    results = {}
    console.clear()
    console.print(create_header())
    display_panel(
        "Starting Backup for All Services", NordColors.FROST_2, title="Unified Backup"
    )
    log_message("Starting backup for all services")

    for svc in BACKUP_CONFIGS.keys():
        print_message(f"Processing {BACKUP_CONFIGS[svc]['name']}...")
        results[svc] = backup_service(svc)

    console.print("\n")
    display_panel(
        "Backup Results Summary", NordColors.FROST_3, title="Completion Status"
    )

    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        border_style=NordColors.FROST_3,
    )

    table.add_column("Service", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_column("Status", justify="center")

    for svc, success in results.items():
        status_text = "✓ SUCCESS" if success else "✗ FAILED"
        status_style = NordColors.GREEN if success else NordColors.RED
        table.add_row(
            BACKUP_CONFIGS[svc]["name"],
            BACKUP_CONFIGS[svc]["description"],
            f"[bold {status_style}]{status_text}[/]",
        )

    console.print(table)

    success_count = sum(1 for s in results.values() if s)
    total_count = len(results)
    log_message(
        f"Completed backup for all services: {success_count}/{total_count} successful"
    )

    return results


def show_system_info() -> None:
    display_panel("System Information", NordColors.FROST_3, title="Configuration")

    info_table = Table(show_header=False, expand=False, border_style=NordColors.FROST_4)
    info_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    info_table.add_column("Value", style=NordColors.SNOW_STORM_1)

    info_table.add_row("Hostname", HOSTNAME)
    info_table.add_row("Platform", platform.platform())
    info_table.add_row("Python Version", platform.python_version())
    info_table.add_row("macOS Version", platform.mac_ver()[0])

    try:
        result = run_command(["restic", "version"], silent=True)
        match = re.search(r"restic (\d+\.\d+\.\d+)", result.stdout.strip())
        restic_version = match.group(1) if match else result.stdout.strip()
    except Exception:
        restic_version = "Not installed"

    info_table.add_row("Restic Version", restic_version)
    info_table.add_row("B2 Bucket", B2_BUCKET)
    info_table.add_row("Retention Policy", RETENTION_POLICY)
    info_table.add_row("Log File", LOG_FILE)

    console.print(info_table)

    svc_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Available Backup Services[/]",
        border_style=NordColors.FROST_3,
    )

    svc_table.add_column("Service", style=f"bold {NordColors.FROST_2}")
    svc_table.add_column("Description", style=NordColors.SNOW_STORM_1)
    svc_table.add_column("Paths", style=NordColors.SNOW_STORM_1)

    for key, config in BACKUP_CONFIGS.items():
        svc_table.add_row(
            config["name"], config["description"], ", ".join(config["paths"])
        )

    console.print(svc_table)


def create_menu_panel() -> Panel:
    menu_text = Text()

    menu_text.append("┌── ", style=NordColors.FROST_3)
    menu_text.append("Backup Operations", style=f"bold {NordColors.FROST_2}")
    menu_text.append(" ───────────────┐\n", style=NordColors.FROST_3)
    menu_text.append("  1. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup System\n", style=NordColors.SNOW_STORM_1)
    menu_text.append("  2. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup Virtual Machines\n", style=NordColors.SNOW_STORM_1)
    menu_text.append("  3. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup Plex Media Server\n", style=NordColors.SNOW_STORM_1)
    menu_text.append("  4. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup All Services\n", style=NordColors.SNOW_STORM_1)
    menu_text.append("└─────────────────────────────┘\n", style=NordColors.FROST_3)
    menu_text.append("\n")

    menu_text.append("┌── ", style=NordColors.FROST_3)
    menu_text.append("Snapshot Operations", style=f"bold {NordColors.FROST_2}")
    menu_text.append(" ─────────────┐\n", style=NordColors.FROST_3)
    menu_text.append("  5. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("List Snapshots (per service)\n", style=NordColors.SNOW_STORM_1)
    menu_text.append("  6. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("List All Snapshots\n", style=NordColors.SNOW_STORM_1)
    menu_text.append("└─────────────────────────────┘\n", style=NordColors.FROST_3)
    menu_text.append("\n")

    menu_text.append("┌── ", style=NordColors.FROST_3)
    menu_text.append("System Operations", style=f"bold {NordColors.FROST_2}")
    menu_text.append(" ──────────────┐\n", style=NordColors.FROST_3)
    menu_text.append("  7. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Show System Information\n", style=NordColors.SNOW_STORM_1)
    menu_text.append("  8. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Exit\n", style=NordColors.SNOW_STORM_1)
    menu_text.append("└─────────────────────────────┘", style=NordColors.FROST_3)

    return Panel(
        menu_text,
        border_style=Style(color=NordColors.FROST_2),
        padding=(1, 2),
        title=f"[bold {NordColors.FROST_3}]Menu Options[/]",
        title_align="center",
    )


def select_service_for_snapshots() -> None:
    console.clear()
    console.print(create_header())
    display_panel("Select Service", NordColors.FROST_2, title="Service Selection")

    svc_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=False,
        border_style=NordColors.FROST_3,
    )

    svc_table.add_column("Option", style=f"bold {NordColors.FROST_4}", justify="center")
    svc_table.add_column("Service", style=f"bold {NordColors.FROST_2}")
    svc_table.add_column("Description", style=NordColors.SNOW_STORM_1)

    for idx, (svc, config) in enumerate(BACKUP_CONFIGS.items(), 1):
        svc_table.add_row(str(idx), config["name"], config["description"])

    console.print(svc_table)

    svc_choice = get_user_input(f"Enter service number (1-{len(BACKUP_CONFIGS)})", "1")

    try:
        svc_idx = int(svc_choice) - 1
        if 0 <= svc_idx < len(BACKUP_CONFIGS):
            service = list(BACKUP_CONFIGS.keys())[svc_idx]
            list_snapshots(service)
        else:
            print_error(f"Invalid selection: {svc_choice}")
    except ValueError:
        print_error(f"Invalid input: {svc_choice}")


def interactive_menu() -> None:
    while True:
        console.clear()
        console.print(create_header())

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )

        console.print()
        console.print(create_menu_panel())
        console.print()

        choice = get_user_input("Select an option (1-8)", "8")

        if choice == "1":
            backup_service("system")
        elif choice == "2":
            backup_service("vm")
        elif choice == "3":
            backup_service("plex")
        elif choice == "4":
            backup_all_services()
        elif choice == "5":
            select_service_for_snapshots()
        elif choice == "6":
            console.clear()
            console.print(create_header())
            display_panel(
                "All Snapshots", NordColors.FROST_2, title="Snapshot Overview"
            )
            for svc in BACKUP_CONFIGS.keys():
                list_snapshots(svc)
        elif choice == "7":
            console.clear()
            console.print(create_header())
            show_system_info()
        elif choice == "8":
            console.clear()
            console.print(create_header())
            display_panel(
                "Thank you for using Restic Backup Manager!",
                NordColors.FROST_2,
                title="Exit",
            )
            break
        else:
            print_warning("Invalid selection, please try again")

        wait_for_enter()


def main() -> None:
    console.clear()
    console.print(create_header())

    if not check_root_privileges():
        display_panel(
            "Warning: This script is not running with administrator privileges.\nSome backup operations may fail due to permission issues.",
            NordColors.YELLOW,
            title="Permission Warning",
        )
        if not Confirm.ask("Continue anyway?", default=True):
            display_panel(
                "Exiting as requested. Please restart with appropriate privileges.",
                NordColors.FROST_2,
                title="Exit",
            )
            sys.exit(0)

    display_panel(
        f"Starting Unified Restic Backup Manager\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        NordColors.FROST_2,
        title="Initialization",
    )

    setup_logging()

    if (
        B2_ACCOUNT_ID == "YOUR_B2_ACCOUNT_ID"
        or B2_ACCOUNT_KEY == "YOUR_B2_ACCOUNT_KEY"
        or RESTIC_PASSWORD == "YOUR_RESTIC_PASSWORD"
    ):
        display_panel(
            "The script is using placeholder credentials.\nPlease update the script with your actual B2 and Restic credentials before running backups.",
            NordColors.YELLOW,
            title="Configuration Warning",
        )
        wait_for_enter()

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
        console=console,
    ) as progress:
        task = progress.add_task("Setting up backup environment...", total=3)

        if not install_dependencies():
            print_error("Dependency installation failed. Some functions may not work.")
        progress.advance(task)

        if (
            B2_ACCOUNT_ID != "YOUR_B2_ACCOUNT_ID"
            and B2_ACCOUNT_KEY != "YOUR_B2_ACCOUNT_KEY"
        ):
            if not authorize_b2():
                print_error("B2 authorization failed. Cloud backups may not work.")
            progress.advance(task)

            if not ensure_bucket_exists(B2_BUCKET):
                print_error(
                    "Failed to ensure B2 bucket exists. Cloud backups may not work."
                )
            progress.advance(task)
        else:
            print_warning("Skipping B2 setup due to missing credentials")
            progress.advance(task, 2)

    show_system_info()
    interactive_menu()

    print_success("Backup operations completed")
    log_message("Script execution completed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Backup interrupted by user")
        log_message("Backup interrupted by user", "WARNING")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        log_message(f"Unhandled error: {e}", "ERROR")
        console.print_exception()
        sys.exit(1)
