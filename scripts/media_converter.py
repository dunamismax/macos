#!/usr/bin/env python3

import atexit
import os
import sys
import time
import platform
import signal
import subprocess
import shutil
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)


def install_dependencies():
    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "ffmpeg-python"]
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


def check_ffmpeg():
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return True
    except Exception:
        print("FFmpeg not found. Attempting to install via Homebrew...")
        try:
            if shutil.which("brew") is None:
                print(
                    "Homebrew is not installed. Please install it from https://brew.sh"
                )
                return False
            subprocess.check_call(["brew", "install", "ffmpeg"])
            print("FFmpeg installed successfully!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to install FFmpeg: {e}")
            return False


try:
    import ffmpeg
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
    from rich.live import Live
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import PathCompleter, Completion
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PtStyle
except ImportError:
    install_dependencies()
    print("Dependencies installed. Checking for FFmpeg...")
    check_ffmpeg()
    print("Restarting script...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

if not check_ffmpeg():
    print("Warning: FFmpeg is required but could not be installed automatically.")

install_rich_traceback(show_locals=True)

APP_NAME = "macOS Media Converter"
APP_SUBTITLE = "FFmpeg Frontend for macOS"
VERSION = "1.0.0"

DEFAULT_INPUT_FOLDER = os.path.expanduser("~/Movies")
DEFAULT_OUTPUT_FOLDER = os.path.expanduser("~/Movies/Converted")
os.makedirs(DEFAULT_OUTPUT_FOLDER, exist_ok=True)

HISTORY_DIR = os.path.expanduser("~/.macos_media_converter")
os.makedirs(HISTORY_DIR, exist_ok=True)
COMMAND_HISTORY = os.path.join(HISTORY_DIR, "command_history")
PATH_HISTORY = os.path.join(HISTORY_DIR, "path_history")
CONFIG_FILE = os.path.join(HISTORY_DIR, "config.json")
for history_file in [COMMAND_HISTORY, PATH_HISTORY]:
    if not os.path.exists(history_file):
        open(history_file, "w").close()

VIDEO_CONTAINERS = {
    "mp4": "MPEG-4 (.mp4)",
    "mkv": "Matroska (.mkv)",
    "mov": "QuickTime (.mov)",
    "webm": "WebM (.webm)",
    "avi": "AVI (.avi)",
}

AUDIO_CONTAINERS = {
    "mp3": "MP3 Audio (.mp3)",
    "aac": "AAC Audio (.aac)",
    "flac": "FLAC (.flac)",
    "wav": "WAV Audio (.wav)",
    "ogg": "Ogg Vorbis (.ogg)",
    "m4a": "MPEG-4 Audio (.m4a)",
}

VIDEO_CODECS = {
    "h264": "H.264 / AVC",
    "h265": "H.265 / HEVC",
    "vp9": "VP9",
    "mpeg4": "MPEG-4",
    "prores": "Apple ProRes",
}

AUDIO_CODECS = {
    "aac": "AAC",
    "mp3": "MP3",
    "opus": "Opus",
    "vorbis": "Vorbis",
    "flac": "FLAC",
    "pcm_s16le": "PCM 16-bit",
}

PRESETS = {
    "ultrafast": "Ultrafast (lowest quality)",
    "fast": "Fast",
    "medium": "Medium (balanced)",
    "slow": "Slow",
    "veryslow": "Very Slow (highest quality)",
}

VIDEO_QUALITY = {
    "18": "High Quality",
    "23": "Good Quality",
    "28": "Medium Quality",
    "32": "Low Quality",
}

AUDIO_QUALITY = {
    "128": "Standard (128 kbps)",
    "192": "High (192 kbps)",
    "256": "Very High (256 kbps)",
    "320": "Extreme (320 kbps)",
}

EXTENSION_TO_TYPE = {
    **{ext: "video" for ext in VIDEO_CONTAINERS},
    **{ext: "audio" for ext in AUDIO_CONTAINERS},
    "srt": "subtitle",
    "sub": "subtitle",
    "vtt": "subtitle",
}


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


console = Console()


@dataclass
class MediaFile:
    path: str
    file_type: str = "unknown"
    container: str = ""
    video_codec: str = ""
    audio_codec: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    bitrate: int = 0
    size_bytes: int = 0

    def get_file_info(self) -> str:
        info = []
        if self.file_type != "unknown":
            info.append(f"Type: {self.file_type.capitalize()}")
        if self.container:
            info.append(f"Container: {self.container}")
        if self.video_codec and self.file_type == "video":
            info.append(f"Video: {self.video_codec}")
            if self.width and self.height:
                info.append(f"Resolution: {self.width}x{self.height}")
        if self.audio_codec:
            info.append(f"Audio: {self.audio_codec}")
        if self.duration > 0:
            mins, secs = divmod(self.duration, 60)
            hours, mins = divmod(mins, 60)
            if hours > 0:
                info.append(f"Duration: {int(hours)}:{int(mins):02d}:{int(secs):02d}")
            else:
                info.append(f"Duration: {int(mins):02d}:{int(secs):02d}")
        if self.size_bytes > 0:
            size_mb = self.size_bytes / (1024 * 1024)
            if size_mb < 1000:
                info.append(f"Size: {size_mb:.2f} MB")
            else:
                info.append(f"Size: {size_mb / 1024:.2f} GB")
        return " | ".join(info)


@dataclass
class ConversionJob:
    input_file: MediaFile
    output_path: str
    output_format: str
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    video_quality: Optional[str] = None
    audio_quality: Optional[str] = None
    preset: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    extract_audio: bool = False
    remux_only: bool = False
    additional_options: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    progress: float = 0.0
    error_message: Optional[str] = None


@dataclass
class Config:
    default_input_dir: str = DEFAULT_INPUT_FOLDER
    default_output_dir: str = DEFAULT_OUTPUT_FOLDER
    default_video_codec: str = "h264"
    default_audio_codec: str = "aac"
    default_video_quality: str = "23"
    default_audio_quality: str = "192"
    default_preset: str = "medium"
    recent_files: List[str] = field(default_factory=list)
    recent_outputs: List[str] = field(default_factory=list)
    favorite_formats: List[str] = field(default_factory=list)

    def save(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.__dict__, f, indent=2)

    @classmethod
    def load(cls):
        if not os.path.exists(CONFIG_FILE):
            return cls()
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return cls(
                    default_input_dir=data.get(
                        "default_input_dir", DEFAULT_INPUT_FOLDER
                    ),
                    default_output_dir=data.get(
                        "default_output_dir", DEFAULT_OUTPUT_FOLDER
                    ),
                    default_video_codec=data.get("default_video_codec", "h264"),
                    default_audio_codec=data.get("default_audio_codec", "aac"),
                    default_video_quality=data.get("default_video_quality", "23"),
                    default_audio_quality=data.get("default_audio_quality", "192"),
                    default_preset=data.get("default_preset", "medium"),
                    recent_files=data.get("recent_files", []),
                    recent_outputs=data.get("recent_outputs", []),
                    favorite_formats=data.get("favorite_formats", []),
                )
        except Exception as e:
            console.print(
                f"[bold {NordColors.YELLOW}]Warning: Failed to load config: {e}[/]"
            )
            return cls()


config = Config.load()


class SpinnerProgressManager:
    def __init__(self, title="", auto_refresh=True):
        self.title = title
        self.progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            auto_refresh=auto_refresh,
            console=console,
        )
        self.live = None
        self.tasks = {}
        self.start_times = {}
        self.total_sizes = {}
        self.completed_sizes = {}
        self.is_started = False

    def start(self):
        if not self.is_started:
            self.live = Live(self.progress, console=console, refresh_per_second=10)
            self.live.start()
            self.is_started = True

    def stop(self):
        if self.is_started and self.live:
            self.live.stop()
            self.is_started = False

    def add_task(self, description, total_size=None):
        task_id = f"task_{len(self.tasks)}"
        self.start_times[task_id] = time.time()
        if total_size is not None:
            self.total_sizes[task_id] = total_size
            self.completed_sizes[task_id] = 0
        self.tasks[task_id] = self.progress.add_task(
            description, total=100, visible=True
        )
        return task_id

    def update_task(self, task_id, status, completed=None):
        if task_id not in self.tasks:
            return
        task = self.tasks[task_id]
        self.progress.update(task, description=status)
        if completed is not None and task_id in self.total_sizes:
            self.completed_sizes[task_id] = completed
            percentage = min(100, int(100 * completed / self.total_sizes[task_id]))
            self.progress.update(task, completed=percentage)
            status_with_percentage = f"{status} ({percentage}%)"
            self.progress.update(task, description=status_with_percentage)
        elif completed is not None:
            self.progress.update(task, completed=min(100, completed))

    def complete_task(self, task_id, success=True):
        if task_id not in self.tasks:
            return
        task = self.tasks[task_id]
        status_text = "COMPLETED" if success else "FAILED"
        if task_id in self.total_sizes:
            self.completed_sizes[task_id] = self.total_sizes[task_id]
            self.progress.update(task, completed=100)
        elapsed = time.time() - self.start_times[task_id]
        elapsed_str = format_time(elapsed)
        status_msg = f"{status_text} in {elapsed_str}"
        self.progress.update(task, description=status_msg)


class EnhancedPathCompleter(PathCompleter):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if os.path.isdir(os.path.expanduser(text)) and not text.endswith("/"):
            yield Completion(
                text + "/",
                start_position=-len(text),
                style=f"bg:{NordColors.POLAR_NIGHT_2} fg:{NordColors.GREEN}",
            )
            return
        for completion in super().get_completions(document, complete_event):
            full_path = os.path.expanduser(
                os.path.join(text, completion.text)
                if text.endswith("/")
                else completion.text
            )
            if os.path.isdir(full_path) and not completion.text.endswith("/"):
                yield Completion(
                    completion.text + "/",
                    start_position=completion.start_position,
                    style=f"bg:{NordColors.POLAR_NIGHT_2} fg:{NordColors.GREEN}",
                )
            else:
                extension = os.path.splitext(full_path)[1].lower().lstrip(".")
                if extension in VIDEO_CONTAINERS:
                    style = f"bg:{NordColors.POLAR_NIGHT_2} fg:{NordColors.FROST_2}"
                elif extension in AUDIO_CONTAINERS:
                    style = f"bg:{NordColors.POLAR_NIGHT_2} fg:{NordColors.FROST_4}"
                else:
                    style = (
                        f"bg:{NordColors.POLAR_NIGHT_2} fg:{NordColors.SNOW_STORM_1}"
                    )
                yield Completion(
                    completion.text,
                    start_position=completion.start_position,
                    style=style,
                )


def format_time(seconds):
    if seconds < 1:
        return "less than a second"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {int(seconds)}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m"


def create_header():
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)
    fonts = ["slant", "big", "standard", "small"]
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
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"
    border = f"[{NordColors.FROST_3}]{'━' * (adjusted_width - 6)}[/]"
    styled_text = border + "\n" + styled_text + border
    return Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
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


def get_prompt_style():
    return PtStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})


def wait_for_key():
    pt_prompt(
        "Press Enter to continue...",
        style=PtStyle.from_dict({"prompt": f"{NordColors.FROST_2}"}),
    )


def display_status_bar():
    ffmpeg_version = "Unknown"
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        match = re.search(r"ffmpeg version (\S+)", result.stdout)
        if match:
            ffmpeg_version = match.group(1)
    except Exception:
        pass
    console.print(
        Panel(
            Text.from_markup(
                f"[bold {NordColors.GREEN}]FFmpeg Version: {ffmpeg_version}[/] | [dim]Output: {config.default_output_dir}[/]"
            ),
            border_style=NordColors.FROST_4,
            padding=(0, 2),
        )
    )


def analyze_media_file(file_path):
    try:
        file_path = os.path.expanduser(file_path)
        if not os.path.exists(file_path):
            print_error(f"File not found: {file_path}")
            return MediaFile(path=file_path)

        size_bytes = os.path.getsize(file_path)
        _, ext = os.path.splitext(file_path.lower())
        ext = ext.lstrip(".")
        file_type = EXTENSION_TO_TYPE.get(ext, "unknown")

        try:
            probe = ffmpeg.probe(file_path)
            media_file = MediaFile(
                path=file_path,
                file_type=file_type,
                container=ext,
                size_bytes=size_bytes,
            )

            if "format" in probe and "duration" in probe["format"]:
                media_file.duration = float(probe["format"]["duration"])
            if "format" in probe and "bit_rate" in probe["format"]:
                try:
                    media_file.bitrate = int(probe["format"]["bit_rate"])
                except ValueError:
                    pass

            for stream in probe.get("streams", []):
                codec_type = stream.get("codec_type", "")
                if codec_type == "video":
                    media_file.video_codec = stream.get("codec_name", "")
                    media_file.width = stream.get("width", 0)
                    media_file.height = stream.get("height", 0)
                elif codec_type == "audio":
                    media_file.audio_codec = stream.get("codec_name", "")

            return media_file
        except ffmpeg.Error as e:
            console.print(
                f"[bold {NordColors.RED}]Error analyzing file: {e.stderr.decode() if e.stderr else str(e)}[/]"
            )
            return MediaFile(path=file_path, file_type=file_type, size_bytes=size_bytes)
    except Exception as e:
        console.print(
            f"[bold {NordColors.RED}]Unexpected error analyzing file: {str(e)}[/]"
        )
        return MediaFile(path=file_path)


def get_optimal_output_settings(input_file, output_format):
    settings = {
        "video_codec": config.default_video_codec,
        "audio_codec": config.default_audio_codec,
        "video_quality": config.default_video_quality,
        "audio_quality": config.default_audio_quality,
        "preset": config.default_preset,
    }

    if output_format in VIDEO_CONTAINERS:
        if output_format == "mp4":
            settings["video_codec"] = "h264"
            settings["audio_codec"] = "aac"
        elif output_format == "mkv":
            settings["video_codec"] = "h264"
        elif output_format == "mov":
            settings["video_codec"] = "prores"
        elif output_format == "webm":
            settings["video_codec"] = "vp9"
            settings["audio_codec"] = "opus"
    elif output_format in AUDIO_CONTAINERS:
        settings["video_codec"] = None
        if output_format == "mp3":
            settings["audio_codec"] = "mp3"
        elif output_format == "ogg":
            settings["audio_codec"] = "vorbis"
        elif output_format == "flac":
            settings["audio_codec"] = "flac"
        elif output_format == "wav":
            settings["audio_codec"] = "pcm_s16le"
        elif output_format == "m4a":
            settings["audio_codec"] = "aac"

    return settings


def create_conversion_job(input_path, output_format, custom_options=None):
    try:
        input_file = analyze_media_file(input_path)
        if input_file.file_type == "unknown":
            print_warning(f"Unknown file type: {input_path}")
            if not Confirm.ask(
                f"[bold {NordColors.YELLOW}]Attempt conversion anyway?[/]",
                default=False,
            ):
                return None

        if input_path not in config.recent_files:
            config.recent_files.insert(0, input_path)
            config.recent_files = config.recent_files[:10]
            config.save()

        original_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(original_name)[0]
        output_name = f"{name_without_ext}.{output_format}"
        output_path = os.path.join(config.default_output_dir, output_name)

        if os.path.exists(output_path):
            if not Confirm.ask(
                f"[bold {NordColors.YELLOW}]Output file already exists. Overwrite?[/]",
                default=False,
            ):
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                output_name = f"{name_without_ext}_{timestamp}.{output_format}"
                output_path = os.path.join(config.default_output_dir, output_name)
                print_step(f"Using alternative output path: {output_path}")

        settings = get_optimal_output_settings(input_file, output_format)
        if custom_options:
            settings.update(custom_options)

        remux_only = False
        if (
            input_file.file_type == "video"
            and output_format in VIDEO_CONTAINERS
            and input_file.video_codec == settings["video_codec"]
            and input_file.audio_codec == settings["audio_codec"]
        ):
            if Confirm.ask(
                f"[bold {NordColors.GREEN}]Input and output codecs match. Use remuxing to avoid re-encoding?[/]",
                default=True,
            ):
                remux_only = True
                print_step("Using remuxing mode (faster, no quality loss)")

        job = ConversionJob(
            input_file=input_file,
            output_path=output_path,
            output_format=output_format,
            video_codec=settings["video_codec"],
            audio_codec=settings["audio_codec"],
            video_quality=settings["video_quality"],
            audio_quality=settings["audio_quality"],
            preset=settings["preset"],
            remux_only=remux_only,
            extract_audio=input_file.file_type == "video"
            and output_format in AUDIO_CONTAINERS,
        )
        return job
    except Exception as e:
        print_error(f"Error creating conversion job: {e}")
        return None


def execute_conversion_job(job):
    try:
        job.status = "running"
        os.makedirs(os.path.dirname(job.output_path), exist_ok=True)
        input_stream = ffmpeg.input(job.input_file.path)
        output_args = {}

        if job.remux_only:
            output_args.update({"c:v": "copy", "c:a": "copy"})
            print_step("Using stream copy mode (remuxing)")
        else:
            if job.video_codec and not job.extract_audio:
                output_args.update({"c:v": job.video_codec})
                if job.video_codec in ["h264", "h265"]:
                    output_args.update({"crf": job.video_quality})
                if job.preset and job.video_codec in ["h264", "h265"]:
                    output_args.update({"preset": job.preset})
            elif job.extract_audio:
                output_args.update({"vn": None})

            if job.audio_codec:
                output_args.update({"c:a": job.audio_codec})
                if job.audio_quality and job.audio_codec not in ["flac", "pcm_s16le"]:
                    output_args.update({"b:a": f"{job.audio_quality}k"})

            if job.start_time is not None:
                output_args.update({"ss": job.start_time})
            if job.end_time is not None:
                output_args.update({"to": job.end_time})

            output_args.update(job.additional_options)

        total_duration = job.input_file.duration
        if job.start_time is not None and job.end_time is not None:
            total_duration = job.end_time - job.start_time
        elif job.start_time is not None:
            total_duration = total_duration - job.start_time
        elif job.end_time is not None:
            total_duration = job.end_time

        if total_duration <= 0:
            total_duration = 60

        progress_regex = re.compile(r"time=(\d+):(\d+):(\d+)\.\d+")

        def progress_callback(line):
            match = progress_regex.search(line)
            if match:
                hours, minutes, seconds = map(int, match.groups())
                time_seconds = hours * 3600 + minutes * 60 + seconds
                progress_percentage = min(100, time_seconds / total_duration * 100)
                job.progress = progress_percentage
                return progress_percentage
            return None

        spinner_progress = SpinnerProgressManager("Conversion Operation")
        task_id = spinner_progress.add_task(
            f"Converting {os.path.basename(job.input_file.path)} → {os.path.basename(job.output_path)}"
        )

        try:
            spinner_progress.start()
            process = (
                ffmpeg.output(input_stream, job.output_path, **output_args)
                .global_args("-progress", "pipe:1")
                .overwrite_output()
                .run_async(pipe_stdout=True, pipe_stderr=True)
            )

            while True:
                line = process.stdout.readline().decode("utf-8", errors="ignore")
                if not line:
                    break
                percent = progress_callback(line)
                if percent is not None:
                    spinner_progress.update_task(task_id, "Converting", percent)

            process.wait()

            if process.returncode != 0:
                error_message = process.stderr.read().decode("utf-8", errors="ignore")
                job.status = "failed"
                job.error_message = error_message
                spinner_progress.complete_task(task_id, False)
                print_error(f"Conversion failed: {error_message}")
                return False

            job.status = "completed"
            job.progress = 100
            spinner_progress.complete_task(task_id, True)

            if job.output_path not in config.recent_outputs:
                config.recent_outputs.insert(0, job.output_path)
                config.recent_outputs = config.recent_outputs[:10]
                config.save()

            print_success(f"Conversion completed: {job.output_path}")
            return True

        finally:
            spinner_progress.stop()

    except ffmpeg.Error as e:
        error_message = (
            e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
        )
        job.status = "failed"
        job.error_message = error_message
        print_error(f"FFmpeg error: {error_message}")
        return False
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        print_error(f"Conversion error: {e}")
        return False


def check_media_info():
    path_completer = EnhancedPathCompleter(only_directories=False, expanduser=True)
    input_path = pt_prompt(
        "Enter media file path: ",
        completer=path_completer,
        default=config.default_input_dir,
        history=FileHistory(PATH_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )

    if not os.path.exists(os.path.expanduser(input_path)):
        print_error(f"File not found: {input_path}")
        return

    print_step(f"Analyzing {input_path}...")
    spinner = SpinnerProgressManager("Media Analysis")
    task_id = spinner.add_task("Retrieving media information...")

    try:
        spinner.start()
        probe = ffmpeg.probe(input_path)
        spinner.update_task(task_id, "Analysis complete")
        spinner.complete_task(task_id, True)
        spinner.stop()

        console.print(f"[bold {NordColors.FROST_3}]Media Information:[/]")
        format_info = probe.get("format", {})

        format_table = Table(
            title="Container Information",
            show_header=True,
            header_style=f"bold {NordColors.FROST_3}",
        )
        format_table.add_column("Property", style="bold")
        format_table.add_column("Value")
        format_table.add_row("Filename", os.path.basename(input_path))
        format_table.add_row("Format", format_info.get("format_name", "Unknown"))
        format_table.add_row(
            "Duration", f"{float(format_info.get('duration', 0)):.2f} seconds"
        )

        size_bytes = format_info.get("size", 0)
        if size_bytes:
            size_mb = int(size_bytes) / (1024 * 1024)
            if size_mb < 1000:
                format_table.add_row("Size", f"{size_mb:.2f} MB")
            else:
                format_table.add_row("Size", f"{size_mb / 1024:.2f} GB")

        bit_rate = format_info.get("bit_rate", 0)
        if bit_rate:
            format_table.add_row("Bitrate", f"{int(bit_rate) / 1000:.0f} kbps")

        console.print(format_table)

        for i, stream in enumerate(probe.get("streams", [])):
            stream_type = stream.get("codec_type", "unknown").capitalize()
            stream_table = Table(
                title=f"{stream_type} Stream #{i}",
                show_header=True,
                header_style=f"bold {NordColors.FROST_3}",
            )
            stream_table.add_column("Property", style="bold")
            stream_table.add_column("Value")
            stream_table.add_row("Codec", stream.get("codec_name", "Unknown"))

            if stream_type.lower() == "video":
                stream_table.add_row(
                    "Resolution", f"{stream.get('width', 0)}x{stream.get('height', 0)}"
                )
                stream_table.add_row(
                    "Frame Rate", f"{eval(stream.get('avg_frame_rate', '0/1')):.2f} fps"
                )
                if "bit_rate" in stream:
                    stream_table.add_row(
                        "Video Bitrate", f"{int(stream['bit_rate']) / 1000:.0f} kbps"
                    )
            elif stream_type.lower() == "audio":
                stream_table.add_row(
                    "Sample Rate", f"{stream.get('sample_rate', 0)} Hz"
                )
                stream_table.add_row("Channels", str(stream.get("channels", 0)))
                if "bit_rate" in stream:
                    stream_table.add_row(
                        "Audio Bitrate", f"{int(stream['bit_rate']) / 1000:.0f} kbps"
                    )
            elif stream_type.lower() == "subtitle":
                stream_table.add_row(
                    "Language", stream.get("tags", {}).get("language", "Unknown")
                )

            console.print(stream_table)

    except ffmpeg.Error as e:
        if spinner.is_started:
            spinner.complete_task(task_id, False)
            spinner.stop()
        print_error(
            f"Error analyzing media: {e.stderr.decode() if e.stderr else str(e)}"
        )
    except Exception as e:
        if spinner.is_started:
            spinner.complete_task(task_id, False)
            spinner.stop()
        print_error(f"Error: {e}")


def extract_audio_from_video():
    path_completer = EnhancedPathCompleter(only_directories=False, expanduser=True)
    input_path = pt_prompt(
        "Enter video file path: ",
        completer=path_completer,
        default=config.default_input_dir,
        history=FileHistory(PATH_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )

    if not os.path.exists(os.path.expanduser(input_path)):
        print_error(f"File not found: {input_path}")
        return

    spinner = SpinnerProgressManager("Media Analysis")
    task_id = spinner.add_task("Analyzing video file...")

    try:
        spinner.start()
        media_file = analyze_media_file(input_path)
        spinner.update_task(task_id, "Analysis complete")
        spinner.complete_task(task_id, True)
        spinner.stop()

        if media_file.file_type != "video":
            print_error(f"Not a video file: {input_path}")
            return

        if not media_file.audio_codec:
            print_warning(f"No audio stream detected in: {input_path}")
            if not Confirm.ask(
                f"[bold {NordColors.YELLOW}]Continue anyway?[/]", default=False
            ):
                return

        console.print(f"[bold {NordColors.FROST_3}]Video Information:[/]")
        console.print(f"[{NordColors.FROST_2}]{media_file.get_file_info()}[/]")
        console.print()

        audio_formats = sorted(AUDIO_CONTAINERS.keys())
        format_table = Table(title="Available Audio Formats", show_header=True)
        format_table.add_column("Format", style="bold")
        format_table.add_column("Description", style=NordColors.FROST_2)

        for fmt, desc in sorted(AUDIO_CONTAINERS.items()):
            format_table.add_row(fmt, desc)

        console.print(format_table)

        output_format = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Select output audio format[/]",
            choices=audio_formats,
            default="mp3",
        )

        audio_codec = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Select audio codec[/]",
            choices=sorted(AUDIO_CODECS.keys()),
            default=get_optimal_output_settings(media_file, output_format)[
                "audio_codec"
            ],
        )

        audio_quality = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Select audio quality (kbps)[/]",
            choices=sorted(AUDIO_QUALITY.keys()),
            default=config.default_audio_quality,
        )

        job = create_conversion_job(
            input_path,
            output_format,
            {
                "video_codec": None,
                "audio_codec": audio_codec,
                "audio_quality": audio_quality,
                "extract_audio": True,
            },
        )

        if job:
            if execute_conversion_job(job):
                print_success(f"Audio extracted to: {job.output_path}")
                config.default_audio_codec = audio_codec
                config.default_audio_quality = audio_quality
                config.save()

    except Exception as e:
        if spinner.is_started:
            spinner.complete_task(task_id, False)
            spinner.stop()
        print_error(f"Error extracting audio: {e}")


def convert_media_file():
    path_completer = EnhancedPathCompleter(only_directories=False, expanduser=True)
    input_path = pt_prompt(
        "Enter media file path: ",
        completer=path_completer,
        default=config.default_input_dir,
        history=FileHistory(PATH_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )

    if not os.path.exists(os.path.expanduser(input_path)):
        print_error(f"File not found: {input_path}")
        return

    spinner = SpinnerProgressManager("Media Analysis")
    task_id = spinner.add_task("Analyzing media file...")

    try:
        spinner.start()
        media_file = analyze_media_file(input_path)
        spinner.update_task(task_id, "Analysis complete")
        spinner.complete_task(task_id, True)
        spinner.stop()

        console.print(f"[bold {NordColors.FROST_3}]File Information:[/]")
        console.print(f"[{NordColors.FROST_2}]{media_file.get_file_info()}[/]")
        console.print()

        formats = []
        default_format = "mp4"

        if media_file.file_type == "video":
            formats = list(VIDEO_CONTAINERS.keys())
            default_format = "mp4"
        elif media_file.file_type == "audio":
            formats = list(AUDIO_CONTAINERS.keys())
            default_format = "mp3"
        else:
            formats = list(VIDEO_CONTAINERS.keys()) + list(AUDIO_CONTAINERS.keys())

        output_format = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Select output format[/]",
            choices=sorted(formats),
            default=default_format,
        )

        custom_options = {}

        if output_format in VIDEO_CONTAINERS and media_file.file_type == "video":
            if Confirm.ask(
                f"[bold {NordColors.FROST_3}]Configure video settings?[/]", default=True
            ):
                video_codec = Prompt.ask(
                    f"[bold {NordColors.PURPLE}]Video codec[/]",
                    choices=sorted(VIDEO_CODECS.keys()),
                    default=config.default_video_codec,
                )
                custom_options["video_codec"] = video_codec

                video_quality = Prompt.ask(
                    f"[bold {NordColors.PURPLE}]Video quality (CRF value)[/]",
                    choices=sorted(VIDEO_QUALITY.keys()),
                    default=config.default_video_quality,
                )
                custom_options["video_quality"] = video_quality

                preset = Prompt.ask(
                    f"[bold {NordColors.PURPLE}]Encoding preset[/]",
                    choices=sorted(PRESETS.keys()),
                    default=config.default_preset,
                )
                custom_options["preset"] = preset

        if (
            output_format in VIDEO_CONTAINERS and media_file.file_type == "video"
        ) or output_format in AUDIO_CONTAINERS:
            if Confirm.ask(
                f"[bold {NordColors.FROST_3}]Configure audio settings?[/]", default=True
            ):
                audio_codec = Prompt.ask(
                    f"[bold {NordColors.PURPLE}]Audio codec[/]",
                    choices=sorted(AUDIO_CODECS.keys()),
                    default=config.default_audio_codec,
                )
                custom_options["audio_codec"] = audio_codec

                if audio_codec not in ["flac", "pcm_s16le"]:
                    audio_quality = Prompt.ask(
                        f"[bold {NordColors.PURPLE}]Audio bitrate (kbps)[/]",
                        choices=sorted(AUDIO_QUALITY.keys()),
                        default=config.default_audio_quality,
                    )
                    custom_options["audio_quality"] = audio_quality

        job = create_conversion_job(input_path, output_format, custom_options)

        if job:
            if execute_conversion_job(job):
                print_success(f"Conversion completed: {job.output_path}")

                if "video_codec" in custom_options:
                    config.default_video_codec = custom_options["video_codec"]
                if "audio_codec" in custom_options:
                    config.default_audio_codec = custom_options["audio_codec"]
                if "video_quality" in custom_options:
                    config.default_video_quality = custom_options["video_quality"]
                if "audio_quality" in custom_options:
                    config.default_audio_quality = custom_options["audio_quality"]
                if "preset" in custom_options:
                    config.default_preset = custom_options["preset"]

                config.save()

    except Exception as e:
        if spinner.is_started:
            spinner.complete_task(task_id, False)
            spinner.stop()
        print_error(f"Error converting media file: {e}")


def display_recent_files():
    if not config.recent_files:
        return

    recent_table = Table(
        title="Recent Files",
        show_header=True,
        header_style=f"bold {NordColors.FROST_3}",
    )
    recent_table.add_column("#", style="bold", width=3)
    recent_table.add_column("Filename", style="bold")
    recent_table.add_column("Path", style=f"{NordColors.FROST_4}")

    for i, file_path in enumerate(config.recent_files[:5], 1):
        filename = os.path.basename(file_path)
        directory = os.path.dirname(file_path)
        recent_table.add_row(str(i), filename, directory)

    console.print(recent_table)


def show_help():
    help_text = f"""
[bold]Available Commands:[/]

[bold {NordColors.FROST_2}]1-5[/]:      Menu selection numbers
[bold {NordColors.FROST_2}]Tab[/]:      Auto-complete file paths
[bold {NordColors.FROST_2}]Up/Down[/]:  Navigate command history
[bold {NordColors.FROST_2}]Ctrl+C[/]:   Cancel current operation
[bold {NordColors.FROST_2}]h[/]:        Show this help screen

[bold]Supported Formats:[/]

[bold {NordColors.FROST_3}]Video[/]: {", ".join(sorted(VIDEO_CONTAINERS.keys()))}
[bold {NordColors.FROST_3}]Audio[/]: {", ".join(sorted(AUDIO_CONTAINERS.keys()))}
"""
    console.print(
        Panel(
            Text.from_markup(help_text),
            title=f"[bold {NordColors.FROST_1}]Help & Commands[/]",
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )
    )


def configure_settings():
    console.print(
        Panel(f"[bold {NordColors.FROST_2}]Configuration Settings[/]", expand=False)
    )

    new_input_dir = pt_prompt(
        "Default input directory: ",
        default=config.default_input_dir,
        completer=EnhancedPathCompleter(only_directories=True, expanduser=True),
        style=get_prompt_style(),
    )

    if os.path.isdir(os.path.expanduser(new_input_dir)):
        config.default_input_dir = new_input_dir
    else:
        print_warning(f"Directory doesn't exist: {new_input_dir}")
        if Confirm.ask(
            f"[bold {NordColors.YELLOW}]Create this directory?[/]", default=True
        ):
            os.makedirs(os.path.expanduser(new_input_dir), exist_ok=True)
            config.default_input_dir = new_input_dir

    new_output_dir = pt_prompt(
        "Default output directory: ",
        default=config.default_output_dir,
        completer=EnhancedPathCompleter(only_directories=True, expanduser=True),
        style=get_prompt_style(),
    )

    if os.path.isdir(os.path.expanduser(new_output_dir)):
        config.default_output_dir = new_output_dir
    else:
        print_warning(f"Directory doesn't exist: {new_output_dir}")
        if Confirm.ask(
            f"[bold {NordColors.YELLOW}]Create this directory?[/]", default=True
        ):
            os.makedirs(os.path.expanduser(new_output_dir), exist_ok=True)
            config.default_output_dir = new_output_dir

    config.default_video_codec = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Default video codec[/]",
        choices=sorted(VIDEO_CODECS.keys()),
        default=config.default_video_codec,
    )

    config.default_audio_codec = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Default audio codec[/]",
        choices=sorted(AUDIO_CODECS.keys()),
        default=config.default_audio_codec,
    )

    config.default_video_quality = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Default video quality (CRF value)[/]",
        choices=sorted(VIDEO_QUALITY.keys()),
        default=config.default_video_quality,
    )

    config.default_audio_quality = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Default audio bitrate (kbps)[/]",
        choices=sorted(AUDIO_QUALITY.keys()),
        default=config.default_audio_quality,
    )

    config.default_preset = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Default encoding preset[/]",
        choices=sorted(PRESETS.keys()),
        default=config.default_preset,
    )

    config.save()
    print_success("Configuration saved successfully")


def cleanup():
    print_message("Cleaning up session resources...", NordColors.FROST_3)


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


def main_menu():
    menu_options = [
        ("1", "Convert Media File", lambda: convert_media_file()),
        ("2", "Extract Audio from Video", lambda: extract_audio_from_video()),
        ("3", "Media Information", lambda: check_media_info()),
        ("4", "Configure Settings", lambda: configure_settings()),
        ("h", "Help", lambda: show_help()),
        ("0", "Exit", lambda: None),
    ]

    while True:
        console.clear()
        console.print(create_header())
        display_status_bar()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/]")
        )
        console.print()

        console.print(f"[bold {NordColors.PURPLE}]Media Conversion Menu[/]")
        table = Table(
            show_header=True, header_style=f"bold {NordColors.FROST_3}", expand=True
        )
        table.add_column("Option", style="bold", width=8)
        table.add_column("Description", style="bold")

        for option, description, _ in menu_options:
            table.add_row(option, description)

        console.print(table)

        if config.recent_files:
            display_recent_files()

        command_history = FileHistory(COMMAND_HISTORY)
        choice = pt_prompt(
            "Enter your choice: ",
            history=command_history,
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).lower()

        if choice == "0":
            console.print()
            console.print(
                Panel(
                    Text(
                        f"Thank you for using the macOS Media Converter!",
                        style=f"bold {NordColors.FROST_2}",
                    ),
                    border_style=Style(color=NordColors.FROST_1),
                    padding=(1, 2),
                )
            )
            sys.exit(0)
        else:
            for option, _, func in menu_options:
                if choice == option.lower():
                    func()
                    wait_for_key()
                    break
            else:
                print_error(f"Invalid selection: {choice}")
                wait_for_key()


def main():
    main_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        console.print_exception()
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)
