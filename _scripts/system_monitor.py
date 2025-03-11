#!/usr/bin/env python3
"""
Enhanced System Monitor and Benchmarker
--------------------------------------------------

A sophisticated terminal application for monitoring system performance
metrics and running benchmarks. This tool features real-time system monitoring,
CPU and GPU benchmarking, process tracking, and data export capabilities,
all presented in an elegant Nord-themed interface.

Version: 2.0.0
"""

# ----------------------------------------------------------------
# Imports & Dependency Check
# ----------------------------------------------------------------
import atexit
import csv
import json
import logging
import math
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Third-party libraries
try:
    import numpy as np
    import psutil
    import pyfiglet
    from rich.align import Align
    from rich.columns import Columns
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table
    from rich.text import Text
    from rich.style import Style
    from rich.prompt import Prompt, Confirm
    from rich.traceback import install as install_rich_traceback
except ImportError as e:
    print(f"Error: Missing dependency: {e}")
    print("Please install required dependencies using:")
    print("pip install numpy psutil pyfiglet rich")
    sys.exit(1)

install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION = "2.0.0"
APP_NAME = "Enhanced System Monitor"
APP_SUBTITLE = "Performance Analysis Suite"

DEFAULT_BENCHMARK_DURATION = 10  # seconds
DEFAULT_REFRESH_RATE = 2.0  # seconds between dashboard updates
DEFAULT_HISTORY_POINTS = 60  # history points for trend graphs
DEFAULT_TOP_PROCESSES = 8  # top processes to display
EXPORT_DIR = os.path.expanduser("~/system_monitor_exports")
LOG_FILE = os.path.join(Path.home(), ".system_monitor.log")
OPERATION_TIMEOUT = 30  # seconds


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    POLAR_NIGHT_1 = "#2E3440"  # Background darkest
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"  # Text darkest
    SNOW_STORM_2 = "#E5E9F0"
    SNOW_STORM_3 = "#ECEFF4"
    FROST_1 = "#8FBCBB"  # Accent light cyan
    FROST_2 = "#88C0D0"  # Accent light blue
    FROST_3 = "#81A1C1"  # Accent medium blue
    FROST_4 = "#5E81AC"  # Accent dark blue
    RED = "#BF616A"  # Error/High usage
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"

    # For specific components
    CPU = FROST_2
    MEM = FROST_1
    DISK = FROST_3
    NET = FROST_4
    LOAD = RED
    TEMP = ORANGE
    PROC = YELLOW
    SUCCESS = GREEN
    HEADER = FROST_2
    TEXT = SNOW_STORM_1


# ----------------------------------------------------------------
# Console Setup
# ----------------------------------------------------------------
console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Generate an ASCII art header using Pyfiglet with a gradient in Nord colors.
    """
    fonts = ["slant", "small", "digital", "mini", "smslant"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=70)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = APP_NAME

    # Build a gradient by cycling through our accent colors
    lines = [line for line in ascii_art.split("\n") if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]
    styled_text = ""
    for idx, line in enumerate(lines):
        color = colors[idx % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "━" * 70 + "[/]"
    full_text = f"{border}\n{styled_text}{border}"
    header = Panel(
        Text.from_markup(full_text),
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
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")
    console.print()


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    print_step("Performing cleanup tasks...")
    # Additional cleanup can be added here


def signal_handler(sig: int, frame: Any) -> None:
    sig_name = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"Signal {sig}"
    )
    print_warning(f"Process interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging() -> None:
    try:
        log_dir = Path(LOG_FILE).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(LOG_FILE, mode="a"),
            ],
        )
        print_success("Logging initialized successfully")
    except Exception as e:
        print_error(f"Failed to setup logging: {e}")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )


# ----------------------------------------------------------------
# System Information Functions
# ----------------------------------------------------------------
def get_system_uptime() -> str:
    boot_time = psutil.boot_time()
    uptime = time.time() - boot_time
    days = int(uptime // 86400)
    hours = int((uptime % 86400) // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)
    return f"{days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"


def get_cpu_info() -> Dict[str, Any]:
    freq = psutil.cpu_freq()
    usage = psutil.cpu_percent(interval=None)
    cores = psutil.cpu_count(logical=False)
    threads = psutil.cpu_count(logical=True)
    cpu_name = "Unknown CPU"
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        cpu_name = line.split(":", 1)[1].strip()
                        break
        elif sys.platform == "darwin":
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                text=True,
                capture_output=True,
            )
            cpu_name = result.stdout.strip()
        elif sys.platform == "win32":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0]
    except Exception:
        pass
    return {
        "model": cpu_name,
        "cores": cores,
        "threads": threads,
        "frequency_current": freq.current if freq else 0,
        "frequency_max": freq.max if freq and freq.max else 0,
        "usage": usage,
    }


def get_cpu_temperature() -> Optional[float]:
    temps = (
        psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}
    )
    if temps:
        for key in ("coretemp", "cpu_thermal", "cpu-thermal", "k10temp"):
            if key in temps and temps[key]:
                sensor = temps[key]
                return sum(t.current for t in sensor) / len(sensor)
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception:
        return None


def get_gpu_info() -> Dict[str, Any]:
    gpu_info = {
        "name": "No GPU detected",
        "load": 0.0,
        "memory": 0.0,
        "temperature": None,
    }
    try:
        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                gpu_info = {
                    "name": gpu.name,
                    "load": gpu.load * 100,
                    "memory": gpu.memoryUtil * 100,
                    "temperature": gpu.temperature,
                }
                return gpu_info
        except ImportError:
            pass
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,utilization.memory,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            if result.stdout:
                values = [v.strip() for v in result.stdout.strip().split(",")]
                gpu_info = {
                    "name": values[0],
                    "load": float(values[1]),
                    "memory": float(values[2]),
                    "temperature": float(values[3]),
                }
                return gpu_info
        except Exception:
            pass
        if sys.platform.startswith("linux"):
            result = subprocess.run(
                ["lspci", "-v"], text=True, capture_output=True, check=False
            )
            for line in result.stdout.splitlines():
                if "VGA" in line or "3D" in line:
                    gpu_info["name"] = line.split(":", 1)[1].strip()
                    break
    except Exception as e:
        logging.warning(f"Error retrieving GPU info: {e}")
    return gpu_info


def get_memory_metrics() -> Tuple[float, float, float, float]:
    mem = psutil.virtual_memory()
    return mem.total, mem.used, mem.available, mem.percent


def get_load_average() -> Tuple[float, float, float]:
    try:
        return os.getloadavg()
    except Exception:
        return (0.0, 0.0, 0.0)


# ----------------------------------------------------------------
# Benchmark Functions
# ----------------------------------------------------------------
def is_prime(n: int) -> bool:
    if n <= 1:
        return False
    if n <= 3:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


def cpu_prime_benchmark(duration_sec: int) -> Dict[str, Any]:
    start = time.time()
    end = start + duration_sec
    prime_count = 0
    num = 2
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.CPU}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=40, style=NordColors.CPU, complete_style=NordColors.FROST_2
        ),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Calculating primes for {duration_sec} seconds...", total=100
        )
        while time.time() < end:
            if is_prime(num):
                prime_count += 1
            num += 1
            elapsed = time.time() - start
            progress.update(task, completed=min(100, (elapsed / duration_sec) * 100))
    total_time = time.time() - start
    return {
        "primes_per_sec": prime_count / total_time if total_time > 0 else 0,
        "elapsed_time": total_time,
        "prime_count": prime_count,
        "highest_prime_checked": num - 1,
    }


def cpu_benchmark(duration_sec: int = DEFAULT_BENCHMARK_DURATION) -> Dict[str, Any]:
    print_section("Running CPU Benchmark")
    print_step(f"Benchmarking for {duration_sec} seconds...")
    try:
        prime_results = cpu_prime_benchmark(duration_sec)
        cpu_info = get_cpu_info()
        return {**prime_results, **cpu_info}
    except Exception as e:
        print_error(f"Error during CPU benchmark: {e}")
        logging.exception("CPU benchmark error")
        return {"error": str(e)}


def gpu_matrix_benchmark(duration_sec: int) -> Dict[str, Any]:
    gpu_info = get_gpu_info()
    matrix_size = 1024
    try:
        mem = psutil.virtual_memory()
        avail_gb = mem.available / (1024**3)
        if avail_gb > 8:
            matrix_size = 2048
        elif avail_gb < 2:
            matrix_size = 512
    except Exception:
        pass
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.GPU}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=40, style=NordColors.GPU, complete_style=NordColors.FROST_1
        ),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Running {matrix_size}x{matrix_size} matrix multiplications for {duration_sec} seconds...",
            total=100,
        )
        try:
            A = np.random.rand(matrix_size, matrix_size).astype(np.float32)
            B = np.random.rand(matrix_size, matrix_size).astype(np.float32)
        except MemoryError:
            matrix_size = 512
            A = np.random.rand(matrix_size, matrix_size).astype(np.float32)
            B = np.random.rand(matrix_size, matrix_size).astype(np.float32)
        iterations = 0
        start = time.time()
        end = start + duration_sec
        while time.time() < end:
            np.dot(A, B)
            iterations += 1
            elapsed = time.time() - start
            progress.update(task, completed=min(100, (elapsed / duration_sec) * 100))
    total_time = time.time() - start
    return {
        "iterations_per_sec": iterations / total_time if total_time > 0 else 0,
        "elapsed_time": total_time,
        "matrix_size": matrix_size,
        "gpu_info": gpu_info,
    }


def gpu_benchmark(duration_sec: int = DEFAULT_BENCHMARK_DURATION) -> Dict[str, Any]:
    print_section("Running GPU Benchmark")
    print_step(f"Benchmarking for {duration_sec} seconds...")
    try:
        return gpu_matrix_benchmark(duration_sec)
    except Exception as e:
        print_error(f"Error during GPU benchmark: {e}")
        logging.exception("GPU benchmark error")
        return {"error": str(e)}


def display_cpu_results(results: Dict[str, Any]) -> None:
    if "error" in results:
        print_error(f"Benchmark Error: {results['error']}")
        return
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.CPU}]CPU Benchmark Results[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )
    table.add_column("Metric", style=f"bold {NordColors.FROST_3}")
    table.add_column("Value", style=f"{NordColors.TEXT}")
    if "model" in results:
        table.add_row("CPU Model", results["model"])
    table.add_row("Physical Cores", str(results["cores"]))
    table.add_row("Logical Cores", str(results["threads"]))
    table.add_row("Current Frequency", f"{results['frequency_current']:.2f} MHz")
    if results.get("frequency_max", 0) > 0:
        table.add_row("Max Frequency", f"{results['frequency_max']:.2f} MHz")
    table.add_row("CPU Usage", f"{results['usage']:.2f}%")
    table.add_row("Benchmark Duration", f"{results['elapsed_time']:.2f} seconds")
    table.add_row("Primes Found", f"{results['prime_count']:,}")
    table.add_row("Highest Number Checked", f"{results['highest_prime_checked']:,}")
    table.add_row(
        "Primes/Second",
        f"{results['primes_per_sec']:.2f}",
        style=f"bold {NordColors.SUCCESS}",
    )
    console.print(table)
    console.print("\n[bold {0}]Benchmark Explanation:[/{0}]".format(NordColors.FROST_2))
    console.print(
        "• Prime calculations stress single-core performance and integer operations."
    )
    console.print("• Higher primes/second indicate better CPU performance.")


def display_gpu_results(results: Dict[str, Any]) -> None:
    if "error" in results:
        print_error(f"Benchmark Error: {results['error']}")
        return
    gpu_info = results.get("gpu_info", {})
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.GPU}]GPU Benchmark Results[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )
    table.add_column("Metric", style=f"bold {NordColors.FROST_3}")
    table.add_column("Value", style=f"{NordColors.TEXT}")
    if gpu_info:
        table.add_row("GPU Name", gpu_info.get("name", "Unknown"))
        if "load" in gpu_info:
            table.add_row("GPU Load", f"{gpu_info['load']:.2f}%")
        if "memory" in gpu_info:
            table.add_row("Memory Usage", f"{gpu_info['memory']:.2f}%")
        if gpu_info.get("temperature") is not None:
            table.add_row("GPU Temp", f"{gpu_info['temperature']:.1f}°C")
    table.add_row("Benchmark Duration", f"{results['elapsed_time']:.2f} seconds")
    table.add_row("Matrix Size", f"{results['matrix_size']}x{results['matrix_size']}")
    table.add_row(
        "Ops/Second",
        f"{results['iterations_per_sec']:.2f}",
        style=f"bold {NordColors.SUCCESS}",
    )
    console.print(table)
    console.print("\n[bold {0}]Benchmark Explanation:[/{0}]".format(NordColors.FROST_2))
    console.print("• Matrix multiplication tests floating-point performance.")
    console.print(
        "• This benchmark uses NumPy; for true GPU testing, consider CUDA/OpenCL-based tools."
    )


# ----------------------------------------------------------------
# Data Structures for Monitoring
# ----------------------------------------------------------------
@dataclass
class DiskInfo:
    device: str
    mountpoint: str
    total: int
    used: int
    free: int
    percent: float
    filesystem: str = "unknown"
    io_stats: Dict[str, Union[int, float]] = field(default_factory=dict)


@dataclass
class NetworkInfo:
    name: str
    ipv4: str = "N/A"
    ipv6: str = "N/A"
    mac: str = "N/A"
    bytes_sent: int = 0
    bytes_recv: int = 0
    packets_sent: int = 0
    packets_recv: int = 0
    bytes_sent_rate: float = 0.0
    bytes_recv_rate: float = 0.0
    is_up: bool = True
    mtu: int = 0


@dataclass
class MemoryInfo:
    total: int = 0
    used: int = 0
    available: int = 0
    percent: float = 0.0
    swap_total: int = 0
    swap_used: int = 0
    swap_percent: float = 0.0


# ----------------------------------------------------------------
# Monitor Classes
# ----------------------------------------------------------------
class DiskMonitor:
    def __init__(self) -> None:
        self.disks: List[DiskInfo] = []
        self.last_update: float = 0.0

    def update(self) -> None:
        self.last_update = time.time()
        self.disks = []
        try:
            partitions = psutil.disk_partitions(all=False)
            for part in partitions:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disk = DiskInfo(
                        device=part.device,
                        mountpoint=part.mountpoint,
                        total=usage.total,
                        used=usage.used,
                        free=usage.free,
                        percent=usage.percent,
                        filesystem=part.fstype,
                    )
                    try:
                        if hasattr(psutil, "disk_io_counters"):
                            io_counters = psutil.disk_io_counters(perdisk=True)
                            disk_name = os.path.basename(part.device)
                            if disk_name in io_counters:
                                io_stats = io_counters[disk_name]
                                disk.io_stats = {
                                    "read_count": io_stats.read_count,
                                    "write_count": io_stats.write_count,
                                    "read_bytes": io_stats.read_bytes,
                                    "write_bytes": io_stats.write_bytes,
                                }
                    except Exception as e:
                        logging.debug(f"IO stats error for {part.device}: {e}")
                    self.disks.append(disk)
                except (PermissionError, FileNotFoundError):
                    continue
        except Exception as e:
            logging.error(f"Error updating disk info: {e}")
            print_error(f"Error updating disk info: {e}")


class NetworkMonitor:
    def __init__(self) -> None:
        self.interfaces: List[NetworkInfo] = []
        self.last_stats: Dict[str, Dict[str, int]] = {}
        self.last_update: float = 0.0

    def update(self) -> None:
        now = time.time()
        delta = now - self.last_update if self.last_update > 0 else 1.0
        self.last_update = now
        try:
            addrs = psutil.net_if_addrs()
            io_counters = psutil.net_io_counters(pernic=True)
            stats = psutil.net_if_stats()
            self.interfaces = []
            for name, addr_list in addrs.items():
                iface = NetworkInfo(name=name)
                for addr in addr_list:
                    if addr.family == socket.AF_INET:
                        iface.ipv4 = addr.address
                    elif addr.family == socket.AF_INET6:
                        iface.ipv6 = addr.address
                    elif addr.family == psutil.AF_LINK:
                        iface.mac = addr.address
                if name in stats:
                    iface.is_up = stats[name].isup
                    iface.mtu = stats[name].mtu
                if name in io_counters:
                    iface.bytes_sent = io_counters[name].bytes_sent
                    iface.bytes_recv = io_counters[name].bytes_recv
                    iface.packets_sent = io_counters[name].packets_sent
                    iface.packets_recv = io_counters[name].packets_recv
                    if name in self.last_stats:
                        last = self.last_stats[name]
                        iface.bytes_sent_rate = (
                            iface.bytes_sent - last.get("bytes_sent", 0)
                        ) / delta
                        iface.bytes_recv_rate = (
                            iface.bytes_recv - last.get("bytes_recv", 0)
                        ) / delta
                    self.last_stats[name] = {
                        "bytes_sent": iface.bytes_sent,
                        "bytes_recv": iface.bytes_recv,
                    }
                self.interfaces.append(iface)
        except Exception as e:
            logging.error(f"Error updating network info: {e}")
            print_error(f"Error updating network info: {e}")


class CpuMonitor:
    def __init__(self) -> None:
        self.usage_percent: float = 0.0
        self.per_core: List[float] = []
        self.core_count: int = os.cpu_count() or 1
        self.load_avg: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.frequency: float = 0.0
        self.temperature: Optional[float] = None
        self.last_update: float = 0.0

    def update(self) -> None:
        self.last_update = time.time()
        try:
            self.usage_percent = psutil.cpu_percent(interval=None)
            self.per_core = psutil.cpu_percent(interval=None, percpu=True)
            self.load_avg = (
                os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
            )
            freq = psutil.cpu_freq()
            self.frequency = freq.current if freq else 0.0
            self.temperature = get_cpu_temperature()
        except Exception as e:
            logging.error(f"Error updating CPU info: {e}")
            print_error(f"Error updating CPU info: {e}")


class MemoryMonitor:
    def __init__(self) -> None:
        self.info = MemoryInfo()
        self.last_update: float = 0.0

    def update(self) -> None:
        self.last_update = time.time()
        try:
            mem = psutil.virtual_memory()
            self.info.total = mem.total
            self.info.used = mem.used
            self.info.available = mem.available
            self.info.percent = mem.percent
            swap = psutil.swap_memory()
            self.info.swap_total = swap.total
            self.info.swap_used = swap.used
            self.info.swap_percent = swap.percent
        except Exception as e:
            logging.error(f"Error updating memory info: {e}")
            print_error(f"Error updating memory info: {e}")


class ProcessMonitor:
    def __init__(self, limit: int = DEFAULT_TOP_PROCESSES) -> None:
        self.limit = limit
        self.processes: List[Dict[str, Any]] = []
        self.last_update: float = 0.0

    def update(self, sort_by: str = "cpu") -> None:
        self.last_update = time.time()
        procs = []
        try:
            for proc in psutil.process_iter(
                ["pid", "name", "username", "cpu_percent", "memory_percent", "status"]
            ):
                try:
                    info = proc.info
                    with proc.oneshot():
                        try:
                            info["create_time"] = proc.create_time()
                        except Exception:
                            info["create_time"] = 0
                        try:
                            mem_info = proc.memory_info()
                            info["memory_mb"] = mem_info.rss / (1024 * 1024)
                        except Exception:
                            info["memory_mb"] = 0.0
                    procs.append(info)
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    continue
            if sort_by.lower() == "memory":
                procs.sort(key=lambda p: p.get("memory_percent", 0), reverse=True)
            else:
                procs.sort(key=lambda p: p.get("cpu_percent", 0), reverse=True)
            self.processes = procs[: self.limit]
        except Exception as e:
            logging.error(f"Error updating process list: {e}")
            print_error(f"Error updating process list: {e}")


class UnifiedMonitor:
    def __init__(
        self,
        refresh_rate: float = DEFAULT_REFRESH_RATE,
        top_limit: int = DEFAULT_TOP_PROCESSES,
    ) -> None:
        self.refresh_rate = refresh_rate
        self.start_time = time.time()
        self.top_limit = top_limit
        self.disk_monitor = DiskMonitor()
        self.network_monitor = NetworkMonitor()
        self.cpu_monitor = CpuMonitor()
        self.memory_monitor = MemoryMonitor()
        self.process_monitor = ProcessMonitor(limit=top_limit)
        self.cpu_history = deque(maxlen=DEFAULT_HISTORY_POINTS)
        self.memory_history = deque(maxlen=DEFAULT_HISTORY_POINTS)

    def update(self) -> None:
        self.cpu_monitor.update()
        self.memory_monitor.update()
        self.disk_monitor.update()
        self.network_monitor.update()
        self.process_monitor.update()
        self.cpu_history.append(self.cpu_monitor.usage_percent)
        self.memory_history.append(self.memory_monitor.info.percent)

    def _create_bar(self, percentage: float, color: str) -> str:
        width = 20
        filled = int((percentage / 100) * width)
        if percentage > 90:
            bar_color = NordColors.RED
        elif percentage > 70:
            bar_color = NordColors.YELLOW
        else:
            bar_color = color
        bar = f"[{bar_color}]{'█' * filled}[/][{NordColors.POLAR_NIGHT_4}]{'█' * (width - filled)}[/]"
        return bar

    def _get_temperature_color(self, temp: float) -> str:
        if temp > 80:
            return NordColors.RED
        elif temp > 70:
            return NordColors.ORANGE
        elif temp > 60:
            return NordColors.YELLOW
        else:
            return NordColors.GREEN

    def _format_network_rate(self, bytes_per_sec: float) -> str:
        if bytes_per_sec > 1024**3:
            return f"{bytes_per_sec / 1024**3:.2f} GB/s"
        elif bytes_per_sec > 1024**2:
            return f"{bytes_per_sec / 1024**2:.2f} MB/s"
        elif bytes_per_sec > 1024:
            return f"{bytes_per_sec / 1024:.2f} KB/s"
        else:
            return f"{bytes_per_sec:.1f} B/s"

    def build_dashboard(self, sort_by: str = "cpu") -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        hostname = socket.gethostname()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uptime = get_system_uptime()
        header_text = f"[bold {NordColors.HEADER}]Hostname: {hostname} | Time: {current_time} | Uptime: {uptime}[/]"
        layout["header"].update(Panel(header_text, style=NordColors.HEADER))
        body = Layout()
        body.split_row(Layout(name="left", ratio=2), Layout(name="right", ratio=3))
        # Left panels: CPU, Memory, Disk
        body["left"].split_column(
            Layout(name="cpu", ratio=2),
            Layout(name="memory", ratio=1),
            Layout(name="disk", ratio=2),
        )
        # Right panels: Processes, Network
        body["right"].split_column(
            Layout(name="processes", ratio=2), Layout(name="network", ratio=1)
        )
        # CPU Panel
        cpu_info = self.cpu_monitor
        cpu_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.CPU}",
            expand=True,
            box=None,
        )
        cpu_table.add_column(
            "Core", style=f"bold {NordColors.FROST_4}", justify="right"
        )
        cpu_table.add_column("Usage", style=f"{NordColors.TEXT}")
        cpu_table.add_column(
            "Bar", style=f"{NordColors.CPU}", justify="center", ratio=3
        )
        cpu_table.add_row(
            "All",
            f"{cpu_info.usage_percent:.1f}%",
            self._create_bar(cpu_info.usage_percent, NordColors.CPU),
        )
        for i, usage in enumerate(cpu_info.per_core):
            cpu_table.add_row(
                f"{i + 1}", f"{usage:.1f}%", self._create_bar(usage, NordColors.CPU)
            )
        cpu_stats = Table(box=None, expand=True, show_header=False)
        cpu_stats.add_column("Metric", style=f"bold {NordColors.FROST_3}")
        cpu_stats.add_column("Value", style=f"{NordColors.TEXT}")
        cpu_stats.add_row("Frequency", f"{cpu_info.frequency:.1f} MHz")
        cpu_stats.add_row(
            "Load Avg",
            f"{cpu_info.load_avg[0]:.2f}, {cpu_info.load_avg[1]:.2f}, {cpu_info.load_avg[2]:.2f}",
        )
        if cpu_info.temperature is not None:
            temp_color = self._get_temperature_color(cpu_info.temperature)
            cpu_stats.add_row("Temp", f"[{temp_color}]{cpu_info.temperature:.1f}°C[/]")
        cpu_panel = Panel(
            Columns([cpu_table, cpu_stats], expand=True),
            title=f"[bold {NordColors.CPU}]CPU Usage[/]",
            border_style=NordColors.CPU,
        )
        body["left"]["cpu"].update(cpu_panel)
        # Memory Panel
        mem_info = self.memory_monitor.info
        mem_table = Table(box=None, expand=True)
        mem_table.add_column("Memory", style=f"bold {NordColors.MEM}")
        mem_table.add_column("Usage", style=f"{NordColors.TEXT}")
        mem_table.add_column("Bar", ratio=3, justify="center")
        mem_used_gb = mem_info.used / (1024**3)
        mem_total_gb = mem_info.total / (1024**3)
        mem_table.add_row(
            "RAM",
            f"{mem_info.percent:.1f}% ({mem_used_gb:.1f}/{mem_total_gb:.1f} GB)",
            self._create_bar(mem_info.percent, NordColors.MEM),
        )
        if mem_info.swap_total > 0:
            swap_used_gb = mem_info.swap_used / (1024**3)
            swap_total_gb = mem_info.swap_total / (1024**3)
            mem_table.add_row(
                "Swap",
                f"{mem_info.swap_percent:.1f}% ({swap_used_gb:.1f}/{swap_total_gb:.1f} GB)",
                self._create_bar(mem_info.swap_percent, NordColors.MEM),
            )
        mem_panel = Panel(
            mem_table,
            title=f"[bold {NordColors.MEM}]Memory Usage[/]",
            border_style=NordColors.MEM,
        )
        body["left"]["memory"].update(mem_panel)
        # Disk Panel
        disk_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.DISK}",
            expand=True,
            box=None,
        )
        disk_table.add_column("Mount", style=f"bold {NordColors.FROST_3}")
        disk_table.add_column("Size", style=f"{NordColors.TEXT}", justify="right")
        disk_table.add_column("Used", style=f"{NordColors.TEXT}", justify="right")
        disk_table.add_column("Free", style=f"{NordColors.TEXT}", justify="right")
        disk_table.add_column(
            "Usage", style=f"{NordColors.TEXT}", justify="center", ratio=2
        )
        for disk in self.disk_monitor.disks[:4]:
            disk_table.add_row(
                disk.mountpoint,
                f"{disk.total / (1024**3):.1f} GB",
                f"{disk.used / (1024**3):.1f} GB",
                f"{disk.free / (1024**3):.1f} GB",
                self._create_bar(disk.percent, NordColors.DISK),
            )
        disk_panel = Panel(
            disk_table,
            title=f"[bold {NordColors.DISK}]Disk Usage[/]",
            border_style=NordColors.DISK,
        )
        body["left"]["disk"].update(disk_panel)
        # Processes Panel
        proc_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.PROC}",
            expand=True,
            box=None,
        )
        proc_table.add_column(
            "PID", style=f"bold {NordColors.FROST_4}", justify="right"
        )
        proc_table.add_column("Name", style=f"{NordColors.TEXT}")
        proc_table.add_column("CPU%", style=f"{NordColors.CPU}", justify="right")
        proc_table.add_column("MEM%", style=f"{NordColors.MEM}", justify="right")
        proc_table.add_column("MEM", style=f"{NordColors.TEXT}", justify="right")
        proc_table.add_column("User", style=f"{NordColors.TEXT}")
        proc_table.add_column("Status", style=f"{NordColors.TEXT}")
        for proc in self.process_monitor.processes:
            status_color = {
                "running": NordColors.GREEN,
                "sleeping": NordColors.FROST_3,
                "stopped": NordColors.YELLOW,
                "zombie": NordColors.RED,
            }.get(proc.get("status", "").lower(), NordColors.TEXT)
            proc_table.add_row(
                str(proc.get("pid", "N/A")),
                proc.get("name", "Unknown")[:20],
                f"{proc.get('cpu_percent', 0.0):.1f}",
                f"{proc.get('memory_percent', 0.0):.1f}",
                f"{proc.get('memory_mb', 0.0):.1f} MB",
                proc.get("username", "")[:10],
                f"[{status_color}]{proc.get('status', 'unknown')}[/]",
            )
        proc_panel = Panel(
            proc_table,
            title=f"[bold {NordColors.PROC}]Top Processes (sorted by {sort_by.upper()})[/]",
            border_style=NordColors.PROC,
        )
        body["right"]["processes"].update(proc_panel)
        # Network Panel
        net_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.NET}",
            expand=True,
            box=None,
        )
        net_table.add_column("Interface", style=f"bold {NordColors.FROST_3}")
        net_table.add_column("IP", style=f"{NordColors.TEXT}")
        net_table.add_column("RX", style=f"{NordColors.TEXT}", justify="right")
        net_table.add_column("TX", style=f"{NordColors.TEXT}", justify="right")
        net_table.add_column("Status", style=f"{NordColors.TEXT}", justify="center")
        active_ifaces = [
            iface
            for iface in self.network_monitor.interfaces
            if iface.bytes_recv_rate > 0
            or iface.bytes_sent_rate > 0
            or iface.name.startswith(("en", "eth", "wl", "ww"))
        ]
        if not active_ifaces:
            active_ifaces = self.network_monitor.interfaces
        for iface in active_ifaces[:4]:
            rx_rate = self._format_network_rate(iface.bytes_recv_rate)
            tx_rate = self._format_network_rate(iface.bytes_sent_rate)
            status = "● Online" if iface.is_up else "○ Offline"
            status_color = NordColors.GREEN if iface.is_up else NordColors.RED
            net_table.add_row(
                iface.name, iface.ipv4, rx_rate, tx_rate, f"[{status_color}]{status}[/]"
            )
        net_panel = Panel(
            net_table,
            title=f"[bold {NordColors.NET}]Network Interfaces[/]",
            border_style=NordColors.NET,
        )
        body["right"]["network"].update(net_panel)
        layout["body"].update(body)
        footer_text = f"[{NordColors.TEXT}]Press Ctrl+C to exit | r: refresh | q: quit | e: export data[/{NordColors.TEXT}]"
        layout["footer"].update(Panel(footer_text, style=NordColors.HEADER))
        return layout

    def export_data(
        self, export_format: str, output_file: Optional[str] = None
    ) -> None:
        data = {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "hostname": socket.gethostname(),
                "uptime": get_system_uptime(),
            },
            "cpu": {
                "usage_percent": self.cpu_monitor.usage_percent,
                "per_core": self.cpu_monitor.per_core,
                "load_avg": self.cpu_monitor.load_avg,
                "frequency": self.cpu_monitor.frequency,
                "temperature": self.cpu_monitor.temperature,
            },
            "memory": asdict(self.memory_monitor.info),
            "disks": [asdict(d) for d in self.disk_monitor.disks],
            "network": [asdict(n) for n in self.network_monitor.interfaces],
            "processes": self.process_monitor.processes,
        }
        os.makedirs(EXPORT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not output_file:
            output_file = os.path.join(
                EXPORT_DIR, f"system_monitor_{timestamp}.{export_format}"
            )
        try:
            if export_format.lower() == "json":
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(
                        data,
                        f,
                        indent=2,
                        default=lambda o: o.__dict__
                        if hasattr(o, "__dict__")
                        else str(o),
                    )
                print_success(f"Data exported to {output_file}")
            elif export_format.lower() == "csv":
                base, _ = os.path.splitext(output_file)
                with open(f"{base}_cpu.csv", "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "timestamp",
                            "usage_percent",
                            "load_avg_1m",
                            "load_avg_5m",
                            "load_avg_15m",
                            "frequency",
                            "temperature",
                        ]
                    )
                    writer.writerow(
                        [
                            data["timestamp"],
                            data["cpu"]["usage_percent"],
                            data["cpu"]["load_avg"][0],
                            data["cpu"]["load_avg"][1],
                            data["cpu"]["load_avg"][2],
                            data["cpu"]["frequency"],
                            data["cpu"]["temperature"] or "N/A",
                        ]
                    )
                with open(f"{base}_memory.csv", "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "timestamp",
                            "total",
                            "used",
                            "available",
                            "percent",
                            "swap_total",
                            "swap_used",
                            "swap_percent",
                        ]
                    )
                    mem = data["memory"]
                    writer.writerow(
                        [
                            data["timestamp"],
                            mem["total"],
                            mem["used"],
                            mem["available"],
                            mem["percent"],
                            mem["swap_total"],
                            mem["swap_used"],
                            mem["swap_percent"],
                        ]
                    )
                with open(f"{base}_disks.csv", "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "timestamp",
                            "device",
                            "mountpoint",
                            "total",
                            "used",
                            "free",
                            "percent",
                            "filesystem",
                        ]
                    )
                    for disk in data["disks"]:
                        writer.writerow(
                            [
                                data["timestamp"],
                                disk["device"],
                                disk["mountpoint"],
                                disk["total"],
                                disk["used"],
                                disk["free"],
                                disk["percent"],
                                disk["filesystem"],
                            ]
                        )
                print_success(f"Data exported to {base}_*.csv files")
            else:
                print_error(f"Unsupported export format: {export_format}")
        except Exception as e:
            print_error(f"Error exporting data: {e}")
            logging.exception("Error exporting data")


# ----------------------------------------------------------------
# Interactive Monitor Functions
# ----------------------------------------------------------------
def run_monitor(
    refresh: float = DEFAULT_REFRESH_RATE,
    duration: float = 0.0,
    export_format: Optional[str] = None,
    export_interval: float = 0.0,
    output_file: Optional[str] = None,
    sort_by: str = "cpu",
) -> None:
    setup_logging()
    if os.name == "posix" and os.geteuid() != 0:
        print_warning("Running without root privileges may limit functionality.")
        if not Confirm.ask("Continue anyway?"):
            return
    console.clear()
    console.print(create_header())
    start_time = time.time()
    monitor = UnifiedMonitor(refresh_rate=refresh, top_limit=DEFAULT_TOP_PROCESSES)
    last_export_time = 0.0
    try:
        with Live(
            monitor.build_dashboard(sort_by),
            refresh_per_second=1 / refresh,
            screen=True,
        ) as live:
            running = True
            while running:
                monitor.update()
                live.update(monitor.build_dashboard(sort_by))
                now = time.time()
                if export_format and export_interval > 0:
                    if now - last_export_time >= export_interval * 60:
                        monitor.export_data(export_format, output_file)
                        last_export_time = now
                if duration > 0 and (now - start_time) >= duration:
                    break
                time.sleep(refresh)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        traceback.print_exc()
    if export_format and not export_interval:
        monitor.export_data(export_format, output_file)
    console.print(f"\n[bold {NordColors.SUCCESS}]Monitor session completed.[/]")


def monitor_menu() -> None:
    refresh_rate = DEFAULT_REFRESH_RATE
    duration = 0.0
    export_format = None
    export_interval = 0.0
    output_file = None
    sort_by = "cpu"
    while True:
        console.clear()
        console.print(create_header())
        print_section("Monitor Configuration")
        settings_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            expand=True,
            box=None,
        )
        settings_table.add_column("Option", style=f"bold {NordColors.FROST_3}")
        settings_table.add_column("Setting", style=f"{NordColors.TEXT}")
        settings_table.add_column("Description", style=f"dim {NordColors.TEXT}")
        settings_table.add_row(
            "1. Refresh Rate", f"{refresh_rate} seconds", "Time between updates"
        )
        settings_table.add_row(
            "2. Duration",
            f"{duration if duration > 0 else 'Unlimited'} seconds",
            "Monitoring duration (0=unlimited)",
        )
        settings_table.add_row(
            "3. Export Format",
            f"{export_format if export_format else 'None'}",
            "Data export format",
        )
        settings_table.add_row(
            "4. Export Interval",
            f"{export_interval} minutes",
            "Interval between exports (0=end only)",
        )
        settings_table.add_row(
            "5. Output File",
            f"{output_file if output_file else 'Auto-generated'}",
            "Export file location",
        )
        settings_table.add_row(
            "6. Sort Processes By", f"{sort_by.upper()}", "Sort criteria: CPU or Memory"
        )
        console.print(
            Panel(
                settings_table,
                title="Current Settings",
                border_style=NordColors.FROST_2,
            )
        )
        actions_table = Table(show_header=False, box=None, expand=True)
        actions_table.add_column("Action", style=f"bold {NordColors.FROST_2}")
        actions_table.add_column("Description", style=f"{NordColors.TEXT}")
        actions_table.add_row("7", "[bold]Start Monitor[/]")
        actions_table.add_row("8", "Return to Main Menu")
        console.print(
            Panel(actions_table, title="Actions", border_style=NordColors.FROST_3)
        )
        try:
            choice = Prompt.ask(
                f"[bold {NordColors.FROST_2}]Enter your choice[/]",
                choices=["1", "2", "3", "4", "5", "6", "7", "8"],
                default="7",
            )
            if choice == "1":
                try:
                    value = float(
                        Prompt.ask(
                            "Enter refresh rate in seconds", default=str(refresh_rate)
                        )
                    )
                    if value <= 0:
                        print_error("Refresh rate must be > 0")
                    else:
                        refresh_rate = value
                except ValueError:
                    print_error("Please enter a valid number")
            elif choice == "2":
                try:
                    value = float(
                        Prompt.ask(
                            "Enter duration in seconds (0=unlimited)",
                            default=str(duration),
                        )
                    )
                    if value < 0:
                        print_error("Duration cannot be negative")
                    else:
                        duration = value
                except ValueError:
                    print_error("Please enter a valid number")
            elif choice == "3":
                console.print(
                    "\n[bold {0}]Export Formats:[/{0}]".format(NordColors.FROST_2)
                )
                console.print("1. None")
                console.print("2. JSON")
                console.print("3. CSV")
                fmt_choice = Prompt.ask(
                    "Choose export format", choices=["1", "2", "3"], default="1"
                )
                export_format = (
                    None
                    if fmt_choice == "1"
                    else "json"
                    if fmt_choice == "2"
                    else "csv"
                )
            elif choice == "4":
                try:
                    value = float(
                        Prompt.ask(
                            "Enter export interval in minutes (0=end only)",
                            default=str(export_interval),
                        )
                    )
                    if value < 0:
                        print_error("Interval cannot be negative")
                    else:
                        export_interval = value
                except ValueError:
                    print_error("Please enter a valid number")
            elif choice == "5":
                path = Prompt.ask(
                    "Enter output file path (leave empty for auto-generated)",
                    default="" if not output_file else output_file,
                )
                output_file = path if path else None
            elif choice == "6":
                console.print(
                    "\n[bold {0}]Sort Options:[/{0}]".format(NordColors.FROST_2)
                )
                console.print("1. CPU Usage")
                console.print("2. Memory Usage")
                sort_choice = Prompt.ask(
                    "Choose sort criteria",
                    choices=["1", "2"],
                    default="1" if sort_by == "cpu" else "2",
                )
                sort_by = "cpu" if sort_choice == "1" else "memory"
            elif choice == "7":
                run_monitor(
                    refresh=refresh_rate,
                    duration=duration,
                    export_format=export_format,
                    export_interval=export_interval,
                    output_file=output_file,
                    sort_by=sort_by,
                )
            elif choice == "8":
                break
        except KeyboardInterrupt:
            print_warning("Operation cancelled.")
        if choice not in ["7", "8"]:
            Prompt.ask(f"[{NordColors.TEXT}]Press Enter to continue[/]", default="")


def benchmark_menu() -> None:
    duration = DEFAULT_BENCHMARK_DURATION
    while True:
        console.clear()
        console.print(create_header())
        print_section("Benchmark Configuration")
        settings_table = Table(show_header=False, box=None, expand=True)
        settings_table.add_column("Setting", style=f"bold {NordColors.FROST_3}")
        settings_table.add_column("Value", style=f"{NordColors.TEXT}")
        settings_table.add_row("Benchmark Duration", f"{duration} seconds")
        console.print(
            Panel(
                settings_table,
                title="Current Settings",
                border_style=NordColors.FROST_2,
            )
        )
        actions_table = Table(show_header=False, box=None, expand=True)
        actions_table.add_column("Option", style=f"bold {NordColors.FROST_2}")
        actions_table.add_column("Description", style=f"{NordColors.TEXT}")
        actions_table.add_row("1", "Change Benchmark Duration")
        actions_table.add_row("2", "Run CPU Benchmark")
        actions_table.add_row("3", "Run GPU Benchmark")
        actions_table.add_row("4", "Run Both CPU and GPU Benchmarks")
        actions_table.add_row("5", "Return to Main Menu")
        console.print(
            Panel(
                actions_table,
                title="Available Benchmarks",
                border_style=NordColors.FROST_3,
            )
        )
        try:
            choice = Prompt.ask(
                f"[bold {NordColors.FROST_2}]Enter your choice[/]",
                choices=["1", "2", "3", "4", "5"],
                default="2",
            )
            if choice == "1":
                try:
                    value = int(
                        Prompt.ask(
                            "Enter benchmark duration in seconds", default=str(duration)
                        )
                    )
                    if value <= 0:
                        print_error("Duration must be > 0")
                    else:
                        duration = value
                except ValueError:
                    print_error("Please enter a valid number")
            elif choice == "2":
                console.clear()
                console.print(create_header())
                results = cpu_benchmark(duration)
                display_cpu_results(results)
            elif choice == "3":
                console.clear()
                console.print(create_header())
                results = gpu_benchmark(duration)
                display_gpu_results(results)
            elif choice == "4":
                console.clear()
                console.print(create_header())
                cpu_results = {}
                gpu_results = {}

                def run_cpu() -> None:
                    nonlocal cpu_results
                    cpu_results = cpu_benchmark(duration)

                def run_gpu() -> None:
                    nonlocal gpu_results
                    gpu_results = gpu_benchmark(duration)

                with Progress(
                    SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                    TextColumn("[progress.description]{task.description}"),
                    TimeRemainingColumn(),
                    console=console,
                ) as progress:
                    progress.add_task(
                        f"Running benchmarks for {duration} seconds...", total=None
                    )
                    cpu_thread = threading.Thread(target=run_cpu)
                    gpu_thread = threading.Thread(target=run_gpu)
                    cpu_thread.start()
                    gpu_thread.start()
                    cpu_thread.join()
                    gpu_thread.join()
                display_cpu_results(cpu_results)
                console.print()
                display_gpu_results(gpu_results)
                print_success("CPU and GPU Benchmarks Completed")
            elif choice == "5":
                break
        except KeyboardInterrupt:
            print_warning("Benchmark interrupted.")
        if choice != "5":
            Prompt.ask(f"[{NordColors.TEXT}]Press Enter to continue[/]", default="")


def display_system_info() -> None:
    hostname = socket.gethostname()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    uptime = get_system_uptime()
    info_table = Table(show_header=False, box=None, expand=True)
    info_table.add_column("Property", style=f"bold {NordColors.FROST_3}")
    info_table.add_column("Value", style=f"{NordColors.TEXT}")
    info_table.add_row("Hostname", hostname)
    info_table.add_row("Time", current_time)
    info_table.add_row("Uptime", uptime)
    cpu_info = get_cpu_info()
    mem = psutil.virtual_memory()
    info_table.add_row(
        "CPU",
        f"{cpu_info['model'][:40]}... ({cpu_info['cores']} cores / {cpu_info['threads']} threads)",
    )
    info_table.add_row("Memory", f"{mem.total / (1024**3):.2f} GB total")
    if os.name == "posix" and os.geteuid() != 0:
        info_table.add_row(
            "Privileges",
            f"[bold {NordColors.YELLOW}]Running without root privileges.[/]",
        )
    console.print(
        Panel(info_table, title="System Information", border_style=NordColors.FROST_2)
    )


def quick_cpu_status() -> None:
    console.clear()
    console.print(create_header())
    print_section("Current CPU Status")
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.CPU}"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Measuring CPU usage...", total=None)
        cpu_usage = psutil.cpu_percent(interval=1, percpu=True)
        progress.update(task, description="CPU information gathered")
    cpu_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.CPU}",
        expand=True,
        title=f"[bold {NordColors.CPU}]Per-Core CPU Usage[/]",
        border_style=NordColors.CPU,
    )
    cpu_table.add_column("Core", style=f"bold {NordColors.FROST_4}", justify="right")
    cpu_table.add_column("Usage", style=f"{NordColors.TEXT}", justify="right")
    cpu_table.add_column("Bar", style=f"{NordColors.CPU}", ratio=3)
    width = 30
    for i, usage in enumerate(cpu_usage):
        if usage > 90:
            bar_color = NordColors.RED
        elif usage > 70:
            bar_color = NordColors.YELLOW
        else:
            bar_color = NordColors.CPU
        filled = int((usage / 100) * width)
        bar = f"[{bar_color}]{'█' * filled}[/][{NordColors.POLAR_NIGHT_4}]{'█' * (width - filled)}[/]"
        cpu_table.add_row(f"Core {i + 1}", f"{usage:.1f}%", bar)
    avg = sum(cpu_usage) / len(cpu_usage)
    avg_color = (
        NordColors.RED
        if avg > 90
        else NordColors.YELLOW
        if avg > 70
        else NordColors.GREEN
    )
    avg_filled = int((avg / 100) * width)
    avg_bar = f"[{avg_color}]{'█' * avg_filled}[/][{NordColors.POLAR_NIGHT_4}]{'█' * (width - avg_filled)}[/]"
    cpu_table.add_row(
        "Average", f"{avg:.1f}%", avg_bar, style=f"bold {NordColors.FROST_2}"
    )
    console.print(cpu_table)
    info_table = Table(show_header=False, box=None, expand=True)
    info_table.add_column("Metric", style=f"bold {NordColors.FROST_3}")
    info_table.add_column("Value", style=f"{NordColors.TEXT}")
    cpu_info = get_cpu_info()
    load = get_load_average()
    temp = get_cpu_temperature()
    if "model" in cpu_info:
        info_table.add_row("CPU Model", cpu_info["model"])
    info_table.add_row("Cores/Threads", f"{cpu_info['cores']} / {cpu_info['threads']}")
    info_table.add_row("Frequency", f"{cpu_info['frequency_current']:.1f} MHz")
    load_color = (
        NordColors.RED
        if load[0] > cpu_info["threads"]
        else NordColors.YELLOW
        if load[0] > cpu_info["threads"] / 2
        else NordColors.LOAD
    )
    info_table.add_row(
        "Load Avg", f"[{load_color}]{load[0]:.2f}[/], {load[1]:.2f}, {load[2]:.2f}"
    )
    if temp:
        temp_color = (
            NordColors.RED
            if temp > 80
            else NordColors.ORANGE
            if temp > 70
            else NordColors.YELLOW
            if temp > 60
            else NordColors.GREEN
        )
        info_table.add_row("Temperature", f"[{temp_color}]{temp:.1f}°C[/]")
    console.print(
        Panel(
            info_table,
            title="Additional CPU Information",
            border_style=NordColors.FROST_3,
        )
    )
    Prompt.ask(f"[{NordColors.TEXT}]Press Enter to continue[/]", default="")


def main_menu() -> None:
    while True:
        console.clear()
        console.print(create_header())
        display_system_info()
        menu_table = Table(
            show_header=False,
            box=None,
            expand=True,
            title=f"[bold {NordColors.FROST_2}]Main Menu[/]",
            title_justify="center",
            border_style=NordColors.FROST_2,
        )
        menu_table.add_column("Option", style=f"bold {NordColors.FROST_2}")
        menu_table.add_column("Description", style=f"{NordColors.TEXT}")
        menu_table.add_row("1", "System Monitor (Real-time Dashboard)")
        menu_table.add_row("2", "Run Performance Benchmarks")
        menu_table.add_row("3", "Quick CPU Status")
        menu_table.add_row("4", "About This Tool")
        menu_table.add_row("5", "Exit")
        console.print(Panel(menu_table))
        try:
            choice = Prompt.ask(
                f"[bold {NordColors.FROST_2}]Enter your choice[/]",
                choices=["1", "2", "3", "4", "5"],
                default="1",
            )
            if choice == "1":
                monitor_menu()
            elif choice == "2":
                benchmark_menu()
            elif choice == "3":
                quick_cpu_status()
                Prompt.ask(f"[{NordColors.TEXT}]Press Enter to continue[/]", default="")
            elif choice == "4":
                console.clear()
                console.print(create_header())
                about_text = f"""
[bold {NordColors.FROST_2}]Enhanced System Monitor and Benchmarker v{VERSION}[/]

A terminal application for monitoring system performance and running benchmarks.
Key Features:
• Real-time system resource monitoring with historical tracking
• CPU benchmarking via prime number calculations
• GPU benchmarking via matrix multiplications
• Process monitoring with sorting by CPU or memory usage
• Data export in JSON or CSV format
• Fully interactive, menu-driven interface with Nord-themed styling
                """
                console.print(
                    Panel(about_text, title="About", border_style=NordColors.FROST_2)
                )
                Prompt.ask(f"[{NordColors.TEXT}]Press Enter to continue[/]", default="")
            elif choice == "5":
                console.clear()
                goodbye = Panel(
                    f"[bold {NordColors.FROST_2}]Thank you for using the Enhanced System Monitor![/]",
                    border_style=Style(color=NordColors.FROST_1),
                    padding=(1, 2),
                )
                console.print(goodbye)
                break
        except KeyboardInterrupt:
            print_warning("Operation cancelled.")
            continue


def main() -> None:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)
    try:
        main_menu()
    except KeyboardInterrupt:
        print_warning("Program interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
