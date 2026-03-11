"""
melvin/ui/layout.py
====================
Main TUI layout using Rich's Live display and Layout engine.
"""

from __future__ import annotations

import platform
import queue
import threading
from collections import deque
from datetime import datetime
from typing import Deque, Optional

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from config import APP_NAME, APP_VERSION


# ---------------------------------------------------------------------------
# Thought Logger
# ---------------------------------------------------------------------------

class ThoughtLogger:
    """
    Thread-safe, bounded circular log of Melvin's internal thoughts.
    Designed to be displayed in a side panel.
    """

    LEVEL_STYLES = {
        "INFO":  "white",
        "WARN":  "bold yellow",
        "ERROR": "bold red",
        "DEBUG": "dim",
    }

    def __init__(self, max_lines: int = 200) -> None:
        self._max = max_lines
        self._lock = threading.Lock()
        self._lines: Deque[str] = deque(maxlen=max_lines)

    def log(self, message: str, level: str = "INFO") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        style = self.LEVEL_STYLES.get(level, "white")
        entry = f"[dim]{ts}[/] [{style}][{level}][/] {message}"
        with self._lock:
            self._lines.append(entry)

    def get_lines(self, n: int = 50) -> list[str]:
        with self._lock:
            return list(self._lines)[-n:]

    def get_panel(self, height: int = 30) -> Panel:
        lines = self.get_lines(height - 2)
        content = "\n".join(lines) if lines else "[dim]No thoughts yet…[/]"
        return Panel(
            content,
            title="[bold purple]🧠 Melvin's Thoughts[/]",
            border_style="bright_green",
            height=height,
        )


# ---------------------------------------------------------------------------
# Chat Display
# ---------------------------------------------------------------------------

class ChatDisplay:
    """Stores the chat history as Rich markup strings for rendering."""

    def __init__(self, max_messages: int = 100) -> None:
        self._lock = threading.Lock()
        self._messages: Deque[str] = deque(maxlen=max_messages)
        self._streaming_buffer: str = ""

    def add_user(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self._messages.append(
                f"[dim]{ts}[/] [bold cyan]You >[/] {text}"
            )

    def add_assistant(self, text: str, model: str = "") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        tag = f" [dim]({model})[/]" if model else ""
        with self._lock:
            self._messages.append(
                f"[dim]{ts}[/] [bold green]Melvin{tag} >[/] {text}"
            )

    def add_system(self, text: str) -> None:
        with self._lock:
            self._messages.append(f"[dim italic]{text}[/]")

    def append_stream_chunk(self, chunk: str) -> None:
        with self._lock:
            self._streaming_buffer += chunk

    def flush_stream(self, model: str = "") -> None:
        with self._lock:
            if self._streaming_buffer:
                self.add_assistant(self._streaming_buffer, model)
                self._streaming_buffer = ""

    def get_panel(self, height: int = 40) -> Panel:
        with self._lock:
            msgs = list(self._messages)[-height:]
            buf = self._streaming_buffer

        content_parts = list(msgs)
        if buf:
            content_parts.append(f"[bold green]Melvin >[/] {buf}[blink]▌[/]")

        content = "\n".join(content_parts) if content_parts else "[dim]Start chatting…[/]"
        return Panel(
            content,
            title="[bold green]💬 Chat[/]",
            border_style="bright_green",
            height=height,
        )


# ---------------------------------------------------------------------------
# Full TUI
# ---------------------------------------------------------------------------

class MelvinLayout:
    """
    Builds and manages the full-screen Rich TUI.

    The layout is:

        ┌─ header (stats + title) ───────────────────────────────────────┐
        │                                                                 │
        ├─ thoughts (sidebar, 1/3) ─┬─ main (chat / menu, 2/3) ─────────┤
        │                           │                                     │
        └─ footer (input prompt) ───────────────────────────────────────┘
    """

    def __init__(
        self,
        thought_logger: ThoughtLogger,
        chat_display: ChatDisplay,
    ) -> None:
        self._logger = thought_logger
        self._chat = chat_display
        self._layout = self._build_layout()
        self._input_buffer = ""
        self._mode_label = "NORMAL"
        self._status_msg = ""

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_input_buffer(self, text: str) -> None:
        self._input_buffer = text

    def set_mode(self, label: str) -> None:
        self._mode_label = label

    def set_status(self, msg: str) -> None:
        self._status_msg = msg

    def refresh(
        self,
        monitor_panel: Panel,
        main_panel: Optional[Panel] = None,
    ) -> Layout:
        """Update all layout regions and return the layout object."""
        self._layout["header"].update(monitor_panel)
        self._layout["thoughts"].update(self._logger.get_panel())
        self._layout["main"].update(main_panel or self._chat.get_panel())
        self._layout["footer"].update(self._build_footer())
        return self._layout

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_layout(self) -> Layout:
        layout = Layout()
        layout.split(
            Layout(name="header", size=7),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        layout["body"].split_row(
            Layout(name="thoughts", ratio=1),
            Layout(name="main", ratio=2),
        )
        return layout

    def _build_footer(self) -> Panel:
        host = platform.node()
        mode_style = "bold red" if self._mode_label == "GOD MODE" else "bold green"
        prompt_text = Text()
        prompt_text.append(f" [{self._mode_label}] ", style=mode_style)
        prompt_text.append(f"melvin@{host}:~$ ", style="bold cyan")
        prompt_text.append(self._input_buffer, style="white")
        prompt_text.append("▌", style="blink")
        if self._status_msg:
            prompt_text.append(f"  {self._status_msg}", style="dim yellow")
        return Panel(prompt_text, border_style="bright_blue", height=3)
