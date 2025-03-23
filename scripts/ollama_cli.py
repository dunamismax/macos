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

if platform.system() != "Darwin":
    print("This script is tailored for macOS. Exiting.")
    sys.exit(1)


def install_dependencies():
    required_packages = ["rich", "pyfiglet", "prompt_toolkit"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER", getpass.getuser()))
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


def check_ollama():
    if shutil.which("ollama") is None:
        print(
            "Ollama CLI not found. Please install Ollama from https://ollama.ai and rerun this script."
        )
        sys.exit(1)


try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from rich.box import ROUNDED, HEAVY
    from rich.style import Style
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PTStyle
    import pyfiglet
except ImportError:
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)

check_ollama()
install_rich_traceback(show_locals=True)
console = Console()

APP_NAME = "Ollama CLI"
VERSION = "1.1.0"
HISTORY_DIR = os.path.expanduser("~/.ollama_cli")
CONFIG_DIR = HISTORY_DIR
os.makedirs(HISTORY_DIR, exist_ok=True)
COMMAND_HISTORY = os.path.join(HISTORY_DIR, "command_history.txt")
CHAT_HISTORY_FILE = os.path.join(HISTORY_DIR, "chat_history.json")
HOSTNAME = socket.gethostname()
USERNAME = os.environ.get("SUDO_USER", os.environ.get("USER", getpass.getuser()))


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
    NORD_BOX = ROUNDED

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


@dataclass
class ChatHistory:
    entries: List[Dict[str, Any]] = field(default_factory=list)

    def add_entry(self, model: str, messages: List[Dict[str, str]]):
        entry = {
            "model": model,
            "messages": messages,
            "date": datetime.now().isoformat(),
        }
        self.entries.insert(0, entry)
        self.entries = self.entries[:50]  # Keep last 50 conversations
        self.save()

    def save(self):
        try:
            with open(CHAT_HISTORY_FILE, "w") as f:
                json.dump({"history": self.entries}, f, indent=2)
        except Exception as e:
            print_error(f"Failed to save chat history: {e}")

    @classmethod
    def load(cls):
        try:
            if os.path.exists(CHAT_HISTORY_FILE):
                with open(CHAT_HISTORY_FILE, "r") as f:
                    data = json.load(f)
                return cls(entries=data.get("history", []))
        except Exception as e:
            print_error(f"Failed to load chat history: {e}")
        return cls()


@dataclass
class ChatSession:
    model: str
    messages: List[Dict[str, str]] = field(default_factory=list)

    def add_message(self, role: str, content: str):
        self.messages.append(
            {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        )

    def get_conversation_text(self) -> str:
        text = ""
        for msg in self.messages:
            if msg["role"] == "user":
                text += f"User: {msg['content']}\n"
            elif msg["role"] == "assistant":
                text += f"Assistant: {msg['content']}\n"
        return text


def clear_screen():
    console.clear()


def create_header():
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
    frost_colors = NordColors.get_frost_gradient(min(len(ascii_lines), 4))

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = frost_colors[i % len(frost_colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"

    border_style = NordColors.FROST_3
    border_char = "═"
    border_line = f"[{border_style}]{border_char * (adjusted_width - 8)}[/]"

    styled_text = border_line + "\n" + styled_text + border_line

    panel = Panel(
        Text.from_markup(styled_text),
        border_style=NordColors.FROST_1,
        box=NordColors.NORD_BOX,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_3}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]macOS Ollama Model Interface[/]",
        subtitle_align="center",
    )

    return panel


def print_message(text, style=NordColors.INFO, prefix="•"):
    if isinstance(style, str):
        console.print(f"[{style}]{prefix} {text}[/{style}]")
    else:
        console.print(f"{prefix} {text}", style=style)


def print_error(message):
    print_message(message, NordColors.ERROR, "✗")


def print_success(message):
    print_message(message, NordColors.SUCCESS, "✓")


def print_warning(message):
    print_message(message, NordColors.WARNING, "⚠")


def print_info(message):
    print_message(message, NordColors.INFO, "ℹ")


def display_panel(title, message, style=NordColors.INFO):
    if isinstance(style, str):
        panel = Panel(
            Text.from_markup(message),
            title=title,
            border_style=style,
            box=NordColors.NORD_BOX,
            padding=(1, 2),
        )
    else:
        panel = Panel(
            Text(message),
            title=title,
            border_style=style,
            box=NordColors.NORD_BOX,
            padding=(1, 2),
        )
    console.print(panel)


def create_menu_table(title, options):
    table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        title=title,
        border_style=NordColors.FROST_3,
        padding=(0, 1),
        expand=True,
    )

    table.add_column("#", style=NordColors.ACCENT, width=3, justify="right")
    table.add_column("Option", style=NordColors.FROST_1)
    table.add_column("Description", style=NordColors.SNOW_STORM_1)

    for opt in options:
        table.add_row(*opt)

    return table


def get_prompt_style():
    return PTStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})


def current_time_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_ollama_models():
    try:
        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Fetching Ollama models..."),
            console=console,
        ) as progress:
            task = progress.add_task("", total=None)
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, check=True
            )

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]

        models = []
        if lines and "NAME" in lines[0].upper():
            header = lines[0]
            lines = lines[1:]

        for line in lines:
            parts = re.split(r"\s{2,}", line)
            if len(parts) >= 4:
                models.append(
                    {
                        "name": parts[0],
                        "id": parts[1],
                        "size": parts[2],
                        "modified": parts[3],
                    }
                )
            elif len(parts) >= 1:
                models.append({"name": parts[0], "id": "", "size": "", "modified": ""})

        if not models:
            print_warning("No models found. Returning default models.")
            models = [
                {"name": "llama2", "id": "", "size": "", "modified": ""},
                {"name": "mistral", "id": "", "size": "", "modified": ""},
                {"name": "gemma", "id": "", "size": "", "modified": ""},
            ]

        return models
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to list Ollama models: {e}")
        return [
            {"name": "llama2", "id": "", "size": "", "modified": ""},
            {"name": "mistral", "id": "", "size": "", "modified": ""},
            {"name": "gemma", "id": "", "size": "", "modified": ""},
        ]


def get_model_response(model, conversation):
    with Progress(
        SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Waiting for {model} response..."),
        BarColumn(
            bar_width=None,
            style=NordColors.POLAR_NIGHT_3,
            complete_style=NordColors.FROST_2,
        ),
        console=console,
    ) as progress:
        task = progress.add_task("", total=None)
        try:
            result = subprocess.run(
                ["ollama", "run", model],
                input=conversation,
                text=True,
                capture_output=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print_error(f"Error communicating with model: {e}")
            if e.stderr:
                print_error(f"Error details: {e.stderr}")
            return "Error: Unable to get response from the model."


def display_model_list():
    clear_screen()
    console.print(create_header())
    models = list_ollama_models()

    table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        title="Available Ollama Models",
        border_style=NordColors.FROST_3,
        expand=True,
    )

    table.add_column("#", style=NordColors.ACCENT, width=3)
    table.add_column("Model Name", style=NordColors.FROST_1)
    table.add_column("ID", style=NordColors.SNOW_STORM_1)
    table.add_column("Size", style=NordColors.FROST_3)
    table.add_column("Modified", style=NordColors.SNOW_STORM_1)

    for i, model in enumerate(models, 1):
        table.add_row(
            str(i),
            model["name"],
            model["id"] or "N/A",
            model["size"] or "N/A",
            model["modified"] or "N/A",
        )

    console.print(table)
    print_info(f"Total models available: {len(models)}")
    Prompt.ask("Press Enter to return to the main menu")


def select_model():
    clear_screen()
    console.print(create_header())
    models = list_ollama_models()

    table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        title="Select an Ollama Model",
        border_style=NordColors.FROST_3,
        expand=True,
    )

    table.add_column("#", style=NordColors.ACCENT, width=3)
    table.add_column("Model Name", style=NordColors.FROST_1)
    table.add_column("Size", style=NordColors.FROST_3)

    for i, model in enumerate(models, 1):
        table.add_row(str(i), model["name"], model["size"] or "N/A")

    console.print(table)

    while True:
        choice = pt_prompt("Enter model number: ", style=get_prompt_style())

        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(models):
            print_error("Invalid selection. Please enter a valid model number.")
        else:
            selected_model = models[int(choice) - 1]["name"]
            print_success(f"Selected model: {selected_model}")
            return selected_model


def interactive_chat():
    model = select_model()
    session = ChatSession(model=model)
    history = ChatHistory.load()

    if not os.path.exists(COMMAND_HISTORY):
        with open(COMMAND_HISTORY, "w") as f:
            pass

    clear_screen()
    console.print(create_header())
    display_panel(
        "Chat Session",
        f"Model: [bold]{model}[/]\nType your messages and press Enter. Type 'exit' or 'quit' to end the session.",
        NordColors.FROST_2,
    )

    while True:
        user_input = pt_prompt(
            f"[You] > ",
            history=FileHistory(COMMAND_HISTORY),
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        )

        if user_input.lower().strip() in ["exit", "quit"]:
            break

        if not user_input.strip():
            continue

        session.add_message("user", user_input)

        conversation = session.get_conversation_text()
        response = get_model_response(model, conversation)

        session.add_message("assistant", response)

        console.print(
            Panel(
                user_input,
                title=f"[bold {NordColors.SNOW_STORM_3}]You[/]",
                border_style=NordColors.FROST_3,
                box=NordColors.NORD_BOX,
            )
        )

        console.print(
            Panel(
                response,
                title=f"[bold {NordColors.SNOW_STORM_3}]{model}[/]",
                border_style=NordColors.FROST_1,
                box=NordColors.NORD_BOX,
            )
        )

    if len(session.messages) > 0:
        history.add_entry(model, session.messages)
        print_success(f"Chat session with {model} completed and saved to history.")


def view_chat_history():
    clear_screen()
    console.print(create_header())
    history = ChatHistory.load()

    if not history.entries:
        display_panel("Chat History", "No chat history found.", NordColors.FROST_3)
        Prompt.ask("Press Enter to return to the main menu")
        return

    table = Table(
        show_header=True,
        header_style=NordColors.HEADER,
        box=ROUNDED,
        title="Chat History",
        border_style=NordColors.FROST_3,
        expand=True,
    )

    table.add_column("#", style=NordColors.ACCENT, width=3)
    table.add_column("Date", style=NordColors.FROST_2)
    table.add_column("Model", style=NordColors.SNOW_STORM_1)
    table.add_column("Messages", style=NordColors.FROST_3, justify="right")

    for i, entry in enumerate(history.entries[:10], 1):
        date_str = datetime.fromisoformat(entry["date"]).strftime("%Y-%m-%d %H:%M")
        message_count = len(entry["messages"])
        table.add_row(str(i), date_str, entry["model"], str(message_count))

    console.print(table)

    options = [
        ("1", "View Chat Details", "See a specific conversation"),
        ("2", "Clear History", "Delete all chat history"),
        ("3", "Return to Main Menu", ""),
    ]

    console.print(create_menu_table("History Options", options))
    choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="3")

    if choice == "1":
        entry_num = Prompt.ask(
            "Enter chat number to view",
            choices=[str(i) for i in range(1, min(11, len(history.entries) + 1))],
            show_choices=False,
        )

        entry = history.entries[int(entry_num) - 1]

        clear_screen()
        console.print(create_header())
        display_panel(
            f"Chat with {entry['model']}",
            f"Date: {datetime.fromisoformat(entry['date']).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Messages: {len(entry['messages'])}",
            NordColors.FROST_2,
        )

        for msg in entry["messages"]:
            if msg["role"] == "user":
                console.print(
                    Panel(
                        msg["content"],
                        title="You",
                        border_style=NordColors.FROST_3,
                        box=NordColors.NORD_BOX,
                    )
                )
            else:
                console.print(
                    Panel(
                        msg["content"],
                        title=entry["model"],
                        border_style=NordColors.FROST_1,
                        box=NordColors.NORD_BOX,
                    )
                )

        Prompt.ask("Press Enter to return to history menu")
        view_chat_history()

    elif choice == "2":
        if Confirm.ask(
            "Are you sure you want to clear all chat history?", default=False
        ):
            history.entries = []
            history.save()
            print_success("Chat history cleared")
        view_chat_history()


def show_help():
    clear_screen()
    console.print(create_header())

    help_content = """
[bold {NordColors.FROST_1}]Ollama CLI Help[/]

[bold {NordColors.FROST_2}]Commands:[/]
1. [bold]List Models[/] - View all available Ollama models on your system
2. [bold]Chat with Model[/] - Start an interactive chat session with a selected model
3. [bold]View History[/] - Browse previous chat sessions
4. [bold]Help[/] - Display this help screen
0. [bold]Exit[/] - Exit the application

[bold {NordColors.FROST_2}]Chat Controls:[/]
- Type your message and press Enter to send
- Type 'exit' or 'quit' to end a chat session

[bold {NordColors.FROST_2}]Usage Notes:[/]
- Models must be installed using the Ollama CLI before they appear in the list
- Install new models with: ollama pull modelname
- System responses are streamed in real-time
"""

    display_panel("Help & Documentation", help_content, NordColors.FROST_2)
    Prompt.ask("Press Enter to return to the main menu")


def cleanup():
    try:
        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        pass


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


def main():
    try:
        clear_screen()
        console.print(create_header())

        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Starting Ollama CLI..."),
            console=console,
        ) as progress:
            task = progress.add_task("", total=100)
            progress.update(
                task, completed=30, description="Checking Ollama installation..."
            )
            progress.update(task, completed=60, description="Loading configuration...")
            progress.update(task, completed=90, description="Initializing interface...")
            progress.update(task, completed=100, description="Ready!")
            time.sleep(0.5)

        main_menu()

    except KeyboardInterrupt:
        print_warning("Operation cancelled by user")

    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        if Confirm.ask("Show detailed error information?", default=False):
            console.print_exception()

    finally:
        cleanup()


def main_menu():
    while True:
        clear_screen()
        console.print(create_header())

        # Display current time and host
        console.print(
            f"[dim]Current Time: {current_time_str()} | Host: {HOSTNAME} | User: {USERNAME}[/dim]"
        )

        main_options = [
            ("1", "List Models", "View all available Ollama models"),
            ("2", "Chat with Model", "Start interactive chat with an Ollama model"),
            ("3", "View History", "Browse previous chat sessions"),
            ("4", "Help", "Show help and documentation"),
            ("0", "Exit", "Exit the application"),
        ]

        console.print(create_menu_table("Main Menu", main_options))

        choice = pt_prompt("Select an option: ", style=get_prompt_style())

        if choice == "1":
            display_model_list()
        elif choice == "2":
            interactive_chat()
        elif choice == "3":
            view_chat_history()
        elif choice == "4":
            show_help()
        elif choice == "0":
            clear_screen()
            console.print(
                Panel(
                    Text.from_markup(
                        "[bold]Thank you for using Ollama CLI![/]\n\n"
                        "Developed with the Nord theme for a beautiful macOS experience."
                    ),
                    title="Goodbye!",
                    title_align="center",
                    border_style=NordColors.FROST_2,
                    box=HEAVY,
                    padding=(2, 4),
                )
            )
            break
        else:
            print_error(f"Invalid selection: {choice}")
            time.sleep(1)


if __name__ == "__main__":
    main()
