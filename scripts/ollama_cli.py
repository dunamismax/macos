#!/usr/bin/env python3
"""
macOS Llama AI CLI Chat Interface (Enhanced)
--------------------------------------------------
An interactive, menu-driven CLI application to interact with Llama AI models via the Ollama CLI.
This production-grade app uses Rich for stylish CLI output, Pyfiglet for dynamic ASCII banners, and
prompt_toolkit for interactive command-line input. It provides a numbered menu for model selection,
maintains conversation history, and supports graceful error handling and signal cleanup.

Core Libraries & Features:
  • Dependency checks and auto-installation of required Python packages.
  • macOS-specific configuration using Homebrew where applicable.
  • Dynamic ASCII banners, rich menus, and progress spinners with ETAs.
  • Interact with the Ollama CLI to list available models and to send/receive messages.
  • Numbered model selection for an easier interactive chat session.
  • Robust error handling, signal cleanup, and modular design.
Version: 1.0.0
"""

import atexit
import os
import sys
import time
import socket
import getpass
import platform
import signal
import subprocess
import shutil
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

# Ensure we are running on macOS
if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)


# ----------------------------------------------------------------
# Dependency Check and Installation
# ----------------------------------------------------------------
def install_dependencies():
    """
    Ensure required third-party packages are installed.
    Uses pip (with --user if not run as root) to install:
      - rich
      - pyfiglet
      - prompt_toolkit
    """
    required_packages = ["rich", "pyfiglet", "prompt_toolkit"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER", getpass.getuser()))
    try:
        if os.geteuid() != 0:
            print(f"Installing dependencies for user: {user}")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--user"] + required_packages
            )
        else:
            print(f"Running as sudo. Installing dependencies for user: {user}")
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"]
                + required_packages
            )
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


def check_homebrew():
    """Ensure Homebrew is installed on macOS."""
    if shutil.which("brew") is None:
        print(
            "Homebrew is not installed. Please install Homebrew from https://brew.sh/ and rerun this script."
        )
        sys.exit(1)


def check_ollama():
    """
    Check if the Ollama CLI is installed.
    If not, inform the user and exit.
    """
    if shutil.which("ollama") is None:
        print(
            "Ollama CLI not found. Please install and configure Ollama before running this script."
        )
        sys.exit(1)


# ----------------------------------------------------------------
# Attempt to Import Dependencies; Install if Missing
# ----------------------------------------------------------------
try:
    from rich.console import Console
    from rich.text import Text
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
    )
    from rich.align import Align
    from rich.style import Style
    from rich.live import Live
    import pyfiglet
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PtStyle
except ImportError:
    print("Required libraries not found. Installing dependencies...")
    install_dependencies()
    print("Dependencies installed. Restarting script...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Check for Ollama CLI
check_ollama()

console: Console = Console()

# Install Rich traceback for better error reporting
from rich.traceback import install as install_rich_traceback

install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# macOS Dark/Light Mode Detection (Optional)
# ----------------------------------------------------------------
def get_macos_theme() -> str:
    """
    Detect macOS appearance setting.
    Returns 'dark' if Dark Mode is enabled, otherwise 'light'.
    """
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.stdout.strip() == "Dark":
            return "dark"
    except Exception:
        pass
    return "light"


THEME = get_macos_theme()

# ----------------------------------------------------------------
# Configuration & Constants (macOS tailored)
# ----------------------------------------------------------------
HOSTNAME: str = socket.gethostname()
DEFAULT_USERNAME: str = (
    os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
)
VERSION: str = "1.0.0"
APP_NAME: str = "macOS Llama Chat"
APP_SUBTITLE: str = "Interactive CLI for Llama AI via Ollama"

# Store history in a hidden folder in the user's home directory
HISTORY_DIR = os.path.expanduser("~/.macos_llama_chat")
os.makedirs(HISTORY_DIR, exist_ok=True)
COMMAND_HISTORY = os.path.join(HISTORY_DIR, "command_history")
if not os.path.exists(COMMAND_HISTORY):
    with open(COMMAND_HISTORY, "w") as f:
        pass


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    POLAR_NIGHT_1: str = "#2E3440"
    POLAR_NIGHT_2: str = "#3B4252"
    POLAR_NIGHT_3: str = "#434C5E"
    POLAR_NIGHT_4: str = "#4C566A"
    SNOW_STORM_1: str = "#D8DEE9"
    SNOW_STORM_2: str = "#E5E9F0"
    SNOW_STORM_3: str = "#ECEFF4"
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"
    RED: str = "#BF616A"
    ORANGE: str = "#D08770"
    YELLOW: str = "#EBCB8B"
    GREEN: str = "#A3BE8C"
    PURPLE: str = "#B48EAD"


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
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
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )
    return header_panel


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


def wait_for_key() -> None:
    pt_prompt(
        "Press Enter to continue...",
        style=PtStyle.from_dict({"prompt": f"{NordColors.FROST_2}"}),
    )


def get_prompt_style() -> PtStyle:
    return PtStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})


# ----------------------------------------------------------------
# Enhanced Spinner Progress Manager
# ----------------------------------------------------------------
class SpinnerProgressManager:
    """Manages Rich spinners with consistent styling."""

    def __init__(self, title: str = "", auto_refresh: bool = True):
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

    def add_task(self, description: str) -> str:
        task_id = f"task_{len(self.tasks)}"
        self.start_times[task_id] = time.time()
        self.tasks[task_id] = self.progress.add_task(
            description, total=100, visible=True
        )
        return task_id

    def update_task(
        self, task_id: str, description: str, completed: Optional[int] = None
    ):
        if task_id not in self.tasks:
            return
        task = self.tasks[task_id]
        self.progress.update(task, description=description)
        if completed is not None:
            self.progress.update(task, completed=min(100, completed))

    def complete_task(self, task_id: str, success: bool = True):
        if task_id not in self.tasks:
            return
        task = self.tasks[task_id]
        status_text = "COMPLETED" if success else "FAILED"
        self.progress.update(task, completed=100, description=f"{status_text}")


# ----------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------
def current_time_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ----------------------------------------------------------------
# Interaction with Ollama CLI
# ----------------------------------------------------------------
def list_models() -> List[str]:
    """
    List available models from Ollama.
    Uses the 'ollama list' command and parses its output.
    """
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, check=True
        )
        # Assume one model per line in the output
        models = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not models:
            models = ["llama2", "stablelm", "alpaca"]
        return models
    except subprocess.CalledProcessError:
        print_warning(
            "Failed to list models using Ollama CLI. Using default model list."
        )
        return ["llama2", "stablelm", "alpaca"]


def get_model_response(model: str, conversation: str) -> str:
    """
    Send the conversation history to the model using 'ollama run' command
    and return the model's response.
    """
    spinner = SpinnerProgressManager("Model Response")
    task_id = spinner.add_task("Waiting for response...")
    spinner.start()
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=conversation,
            text=True,
            capture_output=True,
            check=True,
        )
        spinner.complete_task(task_id, True)
        response = result.stdout.strip()
        return response
    except subprocess.CalledProcessError as e:
        spinner.complete_task(task_id, False)
        print_error(f"Error communicating with model: {e}")
        return "Error: Unable to get response."
    finally:
        spinner.stop()


@dataclass
class ChatSession:
    """
    Represents a chat session with a selected model.
    Maintains conversation history.
    """

    model: str
    conversation_history: List[Dict[str, str]] = field(default_factory=list)

    def append_message(self, role: str, message: str):
        self.conversation_history.append({"role": role, "message": message})

    def get_conversation_text(self) -> str:
        """
        Format conversation history into a single text string to send to Ollama.
        """
        text = ""
        for entry in self.conversation_history:
            if entry["role"] == "user":
                text += f"User: {entry['message']}\n"
            elif entry["role"] == "assistant":
                text += f"Assistant: {entry['message']}\n"
        return text


def interactive_chat(session: ChatSession) -> None:
    """
    Start an interactive chat session with the selected model.
    Type 'exit' or 'quit' to end the session.
    """
    console.clear()
    console.print(create_header())
    console.print(
        f"[bold {NordColors.SNOW_STORM_1}]Chatting with model:[/] [bold {NordColors.FROST_2}]{session.model}[/]"
    )
    console.print(f"[dim]Type 'exit' or 'quit' to end the chat session.[/dim]\n")
    while True:
        user_input = pt_prompt(
            "You: ",
            style=get_prompt_style(),
            history=FileHistory(COMMAND_HISTORY),
            auto_suggest=AutoSuggestFromHistory(),
        )
        if user_input.lower().strip() in ["exit", "quit"]:
            print_warning("Exiting chat session.")
            break
        if not user_input.strip():
            continue
        session.append_message("user", user_input.strip())
        conversation_text = session.get_conversation_text()
        response = get_model_response(session.model, conversation_text)
        session.append_message("assistant", response)
        console.print(
            Panel(
                f"[bold {NordColors.FROST_2}]You:[/] {user_input}",
                style=NordColors.POLAR_NIGHT_2,
            )
        )
        console.print(
            Panel(
                f"[bold {NordColors.FROST_2}]Assistant:[/] {response}",
                style=NordColors.POLAR_NIGHT_3,
            )
        )


def choose_model_menu() -> str:
    """
    Present a numbered menu of available models and let the user choose one.
    Returns the selected model name.
    """
    models = list_models()
    table = Table(
        title="Available Ollama Models",
        show_header=True,
        header_style=f"bold {NordColors.FROST_3}",
    )
    table.add_column("No.", style="bold", width=4)
    table.add_column("Model Name", style=NordColors.FROST_2)
    for i, model in enumerate(models, 1):
        table.add_row(str(i), model)
    console.print(table)
    while True:
        choice = pt_prompt("Enter model number: ", style=get_prompt_style())
        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(models):
            print_error("Invalid selection. Please enter a valid model number.")
        else:
            selected_model = models[int(choice) - 1]
            print_success(f"Selected model: {selected_model}")
            return selected_model


# ----------------------------------------------------------------
# Main Menu and Program Control
# ----------------------------------------------------------------
def chat_menu() -> None:
    menu_options = [
        ("1", "List Available Models", lambda: list_models_menu()),
        ("2", "Start Chat Session", lambda: start_chat_session()),
        ("H", "Help", lambda: show_help()),
        ("0", "Exit", lambda: sys.exit(0)),
    ]
    while True:
        console.clear()
        console.print(create_header())
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time_str()}[/] | Host: {HOSTNAME}"
            )
        )
        console.print(f"\n[bold {NordColors.PURPLE}]Ollama Llama Chat Menu[/]")
        table = Table(
            show_header=True, header_style=f"bold {NordColors.FROST_3}", expand=True
        )
        table.add_column("Option", style="bold", width=8)
        table.add_column("Description", style="bold")
        for option, description, _ in menu_options:
            table.add_row(option, description)
        console.print(table)
        choice = pt_prompt(
            "Enter your choice: ",
            history=FileHistory(COMMAND_HISTORY),
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).upper()
        found = False
        for option, _, func in menu_options:
            if choice == option:
                func()
                found = True
                break
        if not found:
            print_error(f"Invalid selection: {choice}")
            wait_for_key()


def list_models_menu() -> None:
    """
    Display the list of available Ollama models.
    """
    models = list_models()
    table = Table(
        title="Available Ollama Models",
        show_header=True,
        header_style=f"bold {NordColors.FROST_3}",
    )
    table.add_column("#", style="bold", width=4)
    table.add_column("Model Name", style=NordColors.FROST_2)
    for i, model in enumerate(models, 1):
        table.add_row(str(i), model)
    console.print(table)
    wait_for_key()


def start_chat_session() -> None:
    """
    Start an interactive chat session by selecting a model from a numbered list.
    """
    selected_model = choose_model_menu()
    session = ChatSession(model=selected_model)
    interactive_chat(session)
    wait_for_key()


def show_help() -> None:
    help_text = f"""
[bold]Available Commands:[/]

[bold {NordColors.FROST_2}]1[/]: List available models
[bold {NordColors.FROST_2}]2[/]: Start chat session (choose model by number)
[bold {NordColors.FROST_2}]H[/]: Help screen
[bold {NordColors.FROST_2}]0[/]: Exit application

[bold]Chat Commands:[/]
Type your message and press Enter.
Type 'exit' or 'quit' to end the chat session.
"""
    console.print(
        Panel(
            Text.from_markup(help_text),
            title=f"[bold {NordColors.FROST_1}]Help & Commands[/]",
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )
    )
    wait_for_key()


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    print_message("Cleaning up session resources...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
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


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    chat_menu()


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
