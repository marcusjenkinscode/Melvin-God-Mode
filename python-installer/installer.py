#!/usr/bin/env python3
"""
Melvin God Mode – All-in-One Python TUI Installer
==================================================
Interactive terminal installer using Python's built-in curses library.

Navigation:
  ↑ / ↓       Move selection
  Enter       Confirm / open sub-menu
  Space       Toggle checkbox
  q / Esc     Back / Quit
"""

import curses
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import textwrap
import time
from typing import Callable, List, Optional, Tuple

# ── colour pair IDs ──────────────────────────────────────────────────────────
CP_TITLE   = 1   # banner title
CP_BORDER  = 2   # box borders
CP_NORMAL  = 3   # default text
CP_HILITE  = 4   # highlighted / selected row
CP_SUCCESS = 5   # green status
CP_WARN    = 6   # yellow warning
CP_ERROR   = 7   # red error
CP_DIM     = 8   # dim / inactive

# ── constants ─────────────────────────────────────────────────────────────────
APP_NAME    = "Melvin God Mode"
APP_VERSION = "1.0.0"
CONFIG_DIR  = pathlib.Path.home() / ".config" / "melvin"
DATA_DIR    = pathlib.Path.home() / ".local" / "share" / "melvin" / "chats"
VENV_DIR    = pathlib.Path("/opt/melvin/venv")

OLLAMA_MODELS = [
    ("llama3",       "Meta LLaMA 3 8B  – recommended, good all-rounder"),
    ("llama3:70b",   "Meta LLaMA 3 70B – needs 40 GB+ RAM"),
    ("mistral",      "Mistral 7B       – fast & lightweight"),
    ("gemma2",       "Google Gemma 2 9B"),
    ("phi3",         "Microsoft Phi-3 Mini – very fast, small footprint"),
    ("codellama",    "Meta Code LLaMA  – optimised for coding tasks"),
]


# ─────────────────────────────────────────────────────────────────────────────
#  Low-level drawing helpers
# ─────────────────────────────────────────────────────────────────────────────

def init_colours() -> None:
    """Initialise all colour pairs."""
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_TITLE,   curses.COLOR_CYAN,   -1)
    curses.init_pair(CP_BORDER,  curses.COLOR_BLUE,   -1)
    curses.init_pair(CP_NORMAL,  -1,                  -1)
    curses.init_pair(CP_HILITE,  curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(CP_SUCCESS, curses.COLOR_GREEN,  -1)
    curses.init_pair(CP_WARN,    curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_ERROR,   curses.COLOR_RED,    -1)
    curses.init_pair(CP_DIM,     curses.COLOR_WHITE,  -1)


def safe_addstr(win, y: int, x: int, text: str, attr: int = 0) -> None:
    """addstr that silently ignores out-of-bounds writes."""
    max_y, max_x = win.getmaxyx()
    if y < 0 or y >= max_y or x < 0:
        return
    available = max_x - x - 1
    if available <= 0:
        return
    try:
        win.addstr(y, x, text[:available], attr)
    except curses.error:
        pass


def draw_box(win, title: str = "") -> None:
    """Draw a bordered box with an optional title."""
    win.erase()
    win.attron(curses.color_pair(CP_BORDER))
    win.box()
    win.attroff(curses.color_pair(CP_BORDER))
    if title:
        max_x = win.getmaxyx()[1]
        label = f" {title} "
        x = max(1, (max_x - len(label)) // 2)
        safe_addstr(win, 0, x, label, curses.color_pair(CP_TITLE) | curses.A_BOLD)


def draw_banner(win, start_y: int = 1) -> int:
    """Draw the Melvin God Mode ASCII banner. Returns the next free row."""
    lines = [
        "  ███╗   ███╗███████╗██╗    ██╗   ██╗██╗███╗   ██╗",
        "  ████╗ ████║██╔════╝██║    ██║   ██║██║████╗  ██║",
        "  ██╔████╔██║█████╗  ██║    ██║   ██║██║██╔██╗ ██║",
        "  ██║╚██╔╝██║██╔══╝  ██║    ╚██╗ ██╔╝██║██║╚██╗██║",
        "  ██║ ╚═╝ ██║███████╗███████╗╚████╔╝ ██║██║ ╚████║",
        "  ╚═╝     ╚═╝╚══════╝╚══════╝ ╚═══╝  ╚═╝╚═╝  ╚═══╝",
        "",
        f"            God Mode  v{APP_VERSION}  –  Installer",
    ]
    max_y, max_x = win.getmaxyx()
    for i, line in enumerate(lines):
        row = start_y + i
        if row >= max_y - 1:
            break
        attr = curses.color_pair(CP_TITLE) | curses.A_BOLD
        safe_addstr(win, row, 0, line.center(max_x - 1), attr)
    return start_y + len(lines) + 1


def draw_footer(win, hint: str = "↑/↓ Navigate   Enter Select   q Quit") -> None:
    """Draw a footer hint line at the bottom of *win*."""
    max_y, max_x = win.getmaxyx()
    safe_addstr(
        win, max_y - 1, 0,
        hint.center(max_x - 1),
        curses.color_pair(CP_DIM),
    )


def draw_progress_bar(win, y: int, x: int, width: int,
                      fraction: float, label: str = "") -> None:
    """Render a simple ASCII progress bar."""
    filled = int(fraction * (width - 2))
    bar = "[" + "█" * filled + "░" * (width - 2 - filled) + "]"
    pct = f" {int(fraction * 100):3d}%"
    safe_addstr(win, y, x, bar + pct, curses.color_pair(CP_SUCCESS))
    if label:
        safe_addstr(win, y + 1, x, label[:width], curses.color_pair(CP_DIM))


# ─────────────────────────────────────────────────────────────────────────────
#  Menu widget
# ─────────────────────────────────────────────────────────────────────────────

class Menu:
    """Simple scrollable vertical menu inside a curses window."""

    def __init__(self, win, items: List[Tuple[str, str]], start_row: int = 1):
        self.win       = win
        self.items     = items          # [(label, description), ...]
        self.start_row = start_row
        self.cursor    = 0
        self.offset    = 0              # scroll offset

    def _visible_rows(self) -> int:
        max_y = self.win.getmaxyx()[0]
        return max(1, max_y - self.start_row - 3)

    def draw(self) -> None:
        max_y, max_x = self.win.getmaxyx()
        visible = self._visible_rows()

        for i in range(visible):
            idx = self.offset + i
            row = self.start_row + i
            if row >= max_y - 2:
                break
            if idx >= len(self.items):
                safe_addstr(self.win, row, 2, " " * (max_x - 4))
                continue

            label, desc = self.items[idx]
            line = f"  {label:<28}  {desc}"
            if idx == self.cursor:
                self.win.attron(curses.color_pair(CP_HILITE))
                safe_addstr(self.win, row, 1, " " * (max_x - 2))
                safe_addstr(self.win, row, 2, line, curses.color_pair(CP_HILITE))
                self.win.attroff(curses.color_pair(CP_HILITE))
            else:
                safe_addstr(self.win, row, 2, line, curses.color_pair(CP_NORMAL))

        # scroll indicator
        if len(self.items) > visible:
            total = len(self.items)
            bar_h = max(1, visible * visible // total)
            bar_y = self.start_row + (self.offset * (visible - bar_h) // max(1, total - visible))
            for r in range(visible):
                ch = "│" if bar_y <= r < bar_y + bar_h else " "
                safe_addstr(self.win, self.start_row + r, max_x - 2, ch,
                            curses.color_pair(CP_BORDER))

    def handle_key(self, key: int) -> Optional[int]:
        """
        Process a keypress. Returns the selected index on Enter,
        -1 on Quit/Back (q or Esc), or None to keep the menu open.
        """
        visible = self._visible_rows()
        if key in (curses.KEY_UP, ord('k')):
            if self.cursor > 0:
                self.cursor -= 1
                if self.cursor < self.offset:
                    self.offset = self.cursor
        elif key in (curses.KEY_DOWN, ord('j')):
            if self.cursor < len(self.items) - 1:
                self.cursor += 1
                if self.cursor >= self.offset + visible:
                    self.offset = self.cursor - visible + 1
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            return self.cursor
        elif key in (ord('q'), ord('Q'), 27):   # 27 = Esc
            return -1
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Checkbox list widget
# ─────────────────────────────────────────────────────────────────────────────

class CheckboxList:
    """Multi-select checkbox list."""

    def __init__(self, win, options: List[str], checked: Optional[List[bool]] = None,
                 start_row: int = 1):
        self.win       = win
        self.options   = options
        self.checked   = checked if checked else [False] * len(options)
        self.start_row = start_row
        self.cursor    = 0

    def draw(self) -> None:
        max_x = self.win.getmaxyx()[1]
        for i, option in enumerate(self.options):
            row  = self.start_row + i
            mark = "✔" if self.checked[i] else " "
            line = f"  [{mark}]  {option}"
            if i == self.cursor:
                self.win.attron(curses.color_pair(CP_HILITE))
                safe_addstr(self.win, row, 1, " " * (max_x - 2))
                safe_addstr(self.win, row, 2, line, curses.color_pair(CP_HILITE))
                self.win.attroff(curses.color_pair(CP_HILITE))
            else:
                safe_addstr(self.win, row, 2, line, curses.color_pair(CP_NORMAL))

    def handle_key(self, key: int) -> Optional[bool]:
        """Returns True when user presses Enter (done), -1 on Back, None otherwise."""
        if key in (curses.KEY_UP, ord('k')):
            self.cursor = max(0, self.cursor - 1)
        elif key in (curses.KEY_DOWN, ord('j')):
            self.cursor = min(len(self.options) - 1, self.cursor + 1)
        elif key in (ord(' '),):
            self.checked[self.cursor] = not self.checked[self.cursor]
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            return True
        elif key in (ord('q'), ord('Q'), 27):
            return False  # treat as "back"
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Step runner (shows live progress)
# ─────────────────────────────────────────────────────────────────────────────

class StepRunner:
    """
    Execute a list of (label, callable) steps and display progress in the
    terminal via a dedicated curses window.
    """

    def __init__(self, stdscr, title: str, steps: List[Tuple[str, Callable]]):
        self.stdscr = stdscr
        self.title  = title
        self.steps  = steps

    def run(self) -> bool:
        """
        Run all steps. Returns True on full success, False if any step failed.
        """
        max_y, max_x = self.stdscr.getmaxyx()
        win_h = min(len(self.steps) + 10, max_y - 2)
        win_w = min(80, max_x - 4)
        win_y = (max_y - win_h) // 2
        win_x = (max_x - win_w) // 2

        win = curses.newwin(win_h, win_w, win_y, win_x)
        draw_box(win, self.title)

        log_lines: List[str] = []
        success_all = True

        for idx, (label, fn) in enumerate(self.steps):
            fraction = idx / len(self.steps)
            draw_progress_bar(win, 2, 2, win_w - 4, fraction, f"Step {idx + 1}/{len(self.steps)}: {label}")

            # Draw step list
            for i, (lbl, _) in enumerate(self.steps):
                row = 5 + i
                if row >= win_h - 3:
                    break
                if i < idx:
                    marker = ("✔ ", curses.color_pair(CP_SUCCESS))
                elif i == idx:
                    marker = ("⟳ ", curses.color_pair(CP_WARN) | curses.A_BOLD)
                else:
                    marker = ("  ", curses.color_pair(CP_DIM))
                safe_addstr(win, row, 3, marker[0] + lbl, marker[1])

            win.refresh()

            # Execute step
            try:
                fn()
                log_lines.append(f"✔ {label}")
            except Exception as exc:
                log_lines.append(f"✘ {label}: {exc}")
                success_all = False
                # Show error and wait for key
                safe_addstr(win, win_h - 3, 2,
                            f"Error: {str(exc)[:win_w - 8]}",
                            curses.color_pair(CP_ERROR) | curses.A_BOLD)
                safe_addstr(win, win_h - 2, 2,
                            "Press any key to continue...",
                            curses.color_pair(CP_DIM))
                win.refresh()
                win.getch()
                break

        # Final progress bar at 100 %
        draw_progress_bar(win, 2, 2, win_w - 4, 1.0, "Done")
        last_failed = len(self.steps) if success_all else len(self.steps) - 1
        for i, (lbl, _) in enumerate(self.steps):
            row = 5 + i
            if row >= win_h - 3:
                break
            if i < last_failed:
                marker = ("✔ ", curses.color_pair(CP_SUCCESS))
            else:
                marker = ("  ", curses.color_pair(CP_DIM))
            safe_addstr(win, row, 3, marker[0] + lbl, marker[1])

        status = "✔  All steps completed!" if success_all else "✘  Some steps failed."
        attr = curses.color_pair(CP_SUCCESS) | curses.A_BOLD if success_all else curses.color_pair(CP_ERROR) | curses.A_BOLD
        safe_addstr(win, win_h - 3, 2, status, attr)
        safe_addstr(win, win_h - 2, 2, "Press any key to return to the menu...", curses.color_pair(CP_DIM))
        win.refresh()
        win.getch()
        return success_all


# ─────────────────────────────────────────────────────────────────────────────
#  Installation steps (actual logic)
# ─────────────────────────────────────────────────────────────────────────────

def _run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command, capturing output."""
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=check,
    )


def step_check_python() -> None:
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 9):
        raise RuntimeError(f"Python 3.9+ required, found {v.major}.{v.minor}")


def step_install_pip_packages() -> None:
    packages = ["cryptography", "requests", "rich", "textual"]
    _run([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade"] + packages)


def step_create_directories() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def step_write_default_config() -> None:
    config_file = CONFIG_DIR / "config.json"
    if not config_file.exists():
        config = {
            "model": "llama3",
            "host": "127.0.0.1",
            "port": 11434,
            "chat_history_dir": str(DATA_DIR),
            "encryption_enabled": True,
            "log_level": "info",
        }
        config_file.write_text(json.dumps(config, indent=4))


def step_check_ollama() -> None:
    if not shutil.which("ollama"):
        raise RuntimeError(
            "Ollama not found. Visit https://ollama.com/download to install it."
        )


def step_verify_install() -> None:
    time.sleep(0.3)   # small delay so the progress bar is visible
    if not (CONFIG_DIR / "config.json").exists():
        raise RuntimeError("Config file was not created.")


# ─────────────────────────────────────────────────────────────────────────────
#  Screen: About
# ─────────────────────────────────────────────────────────────────────────────

def screen_about(stdscr) -> None:
    max_y, max_x = stdscr.getmaxyx()
    win = curses.newwin(max_y - 2, max_x - 4, 1, 2)
    draw_box(win, "About Melvin God Mode")

    lines = [
        "",
        f"  {APP_NAME}  v{APP_VERSION}",
        "",
        "  An AI assistant that runs entirely on your local machine.",
        "  No data is ever sent to external servers.",
        "",
        "  Features:",
        "   • Multiple open-source LLMs via Ollama",
        "   • Encrypted, persistent chat history (AES-256)",
        "   • JSON-based storage – portable and inspectable",
        "   • Configurable models, ports, and storage paths",
        "",
        f"  Platform:  {platform.system()} {platform.release()}",
        f"  Python:    {sys.version.split()[0]}",
        f"  Config:    {CONFIG_DIR}",
        f"  Data:      {DATA_DIR}",
        "",
        "  Repository: github.com/marcusjenkinscode/Melvin-God-Mode",
    ]

    for i, line in enumerate(lines):
        safe_addstr(win, 1 + i, 0, line, curses.color_pair(CP_NORMAL))

    draw_footer(win, "Press any key to return")
    win.refresh()
    win.getch()


# ─────────────────────────────────────────────────────────────────────────────
#  Screen: Install
# ─────────────────────────────────────────────────────────────────────────────

def screen_install(stdscr) -> None:
    steps = [
        ("Check Python version",         step_check_python),
        ("Install Python packages",      step_install_pip_packages),
        ("Create config directories",    step_create_directories),
        ("Write default config",         step_write_default_config),
        ("Verify Ollama is available",   step_check_ollama),
        ("Verify installation",          step_verify_install),
    ]
    StepRunner(stdscr, "Installing Melvin God Mode", steps).run()


# ─────────────────────────────────────────────────────────────────────────────
#  Screen: Model Manager
# ─────────────────────────────────────────────────────────────────────────────

def screen_models(stdscr) -> None:
    max_y, max_x = stdscr.getmaxyx()
    win = curses.newwin(max_y - 2, max_x - 4, 1, 2)
    draw_box(win, "Model Manager")

    items = [(m, d) for m, d in OLLAMA_MODELS] + [("← Back", "Return to main menu")]
    menu = Menu(win, items, start_row=2)

    safe_addstr(win, 1, 2,
                "Select a model to pull via Ollama  (requires internet connection)",
                curses.color_pair(CP_DIM))

    while True:
        menu.draw()
        draw_footer(win, "↑/↓ Navigate   Enter Pull model   q Back")
        win.refresh()
        key = win.getch()
        result = menu.handle_key(key)
        if result is None:
            continue
        if result == -1 or result == len(OLLAMA_MODELS):
            return

        model_name, _ = OLLAMA_MODELS[result]
        _pull_model_screen(stdscr, model_name)
        # Redraw the box after returning
        draw_box(win, "Model Manager")
        safe_addstr(win, 1, 2,
                    "Select a model to pull via Ollama  (requires internet connection)",
                    curses.color_pair(CP_DIM))


def _pull_model_screen(stdscr, model_name: str) -> None:
    max_y, max_x = stdscr.getmaxyx()
    win_h, win_w = 8, min(60, max_x - 4)
    win = curses.newwin(win_h, win_w, (max_y - win_h) // 2, (max_x - win_w) // 2)
    draw_box(win, f"Pulling  {model_name}")

    safe_addstr(win, 2, 2, f"Running: ollama pull {model_name}", curses.color_pair(CP_NORMAL))
    safe_addstr(win, 3, 2, "This may take several minutes...", curses.color_pair(CP_WARN))
    safe_addstr(win, 5, 2, "(output hidden – check terminal after exit)", curses.color_pair(CP_DIM))
    win.refresh()

    if not shutil.which("ollama"):
        safe_addstr(win, 4, 2,
                    "✘  Ollama not found in PATH!",
                    curses.color_pair(CP_ERROR) | curses.A_BOLD)
        safe_addstr(win, 6, 2, "Press any key...", curses.color_pair(CP_DIM))
        win.refresh()
        win.getch()
        return

    try:
        subprocess.run(["ollama", "pull", model_name], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        safe_addstr(win, 4, 2,
                    f"✔  {model_name} pulled successfully!",
                    curses.color_pair(CP_SUCCESS) | curses.A_BOLD)
    except subprocess.CalledProcessError:
        safe_addstr(win, 4, 2,
                    f"✘  Failed to pull {model_name}",
                    curses.color_pair(CP_ERROR) | curses.A_BOLD)

    safe_addstr(win, 6, 2, "Press any key to return...", curses.color_pair(CP_DIM))
    win.refresh()
    win.getch()


# ─────────────────────────────────────────────────────────────────────────────
#  Screen: Configure
# ─────────────────────────────────────────────────────────────────────────────

def screen_configure(stdscr) -> None:
    """Simple in-TUI config editor."""
    max_y, max_x = stdscr.getmaxyx()
    win = curses.newwin(max_y - 2, max_x - 4, 1, 2)
    draw_box(win, "Configure Melvin God Mode")

    # Load existing config
    config_file = CONFIG_DIR / "config.json"
    config: dict = {}
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text())
        except json.JSONDecodeError:
            config = {}

    fields = [
        ("model",              config.get("model",            "llama3")),
        ("host",               config.get("host",             "127.0.0.1")),
        ("port",               str(config.get("port",         11434))),
        ("encryption_enabled", str(config.get("encryption_enabled", True))),
        ("log_level",          config.get("log_level",        "info")),
    ]

    safe_addstr(win, 1, 2,
                "Edit config values.  Press Enter on a field to edit it.",
                curses.color_pair(CP_DIM))

    items = [(f[0], f"Current: {f[1]}") for f in fields]
    items.append(("Save & Exit", "Write config.json and return"))
    items.append(("Cancel",      "Discard changes and return"))

    menu = Menu(win, items, start_row=3)

    while True:
        menu.draw()
        draw_footer(win, "↑/↓ Navigate   Enter Edit / Save   q Cancel")
        win.refresh()
        key = win.getch()
        result = menu.handle_key(key)
        if result is None:
            continue

        if result == -1 or result == len(items) - 1:
            return   # Cancel

        if result == len(items) - 2:
            # Save
            config = dict(fields)
            try:
                config["port"] = int(config["port"])
            except ValueError:
                config["port"] = 11434
            config["encryption_enabled"] = config["encryption_enabled"].lower() in ("true", "1", "yes")
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            config_file.write_text(json.dumps(config, indent=4))
            _show_message(stdscr, "Saved!", f"Config written to\n{config_file}", success=True)
            return

        if result < len(fields):
            # Edit a field
            field_name, old_val = fields[result]
            new_val = _input_popup(stdscr, f"Edit:  {field_name}", old_val)
            if new_val is not None:
                fields[result] = (field_name, new_val)
                items[result] = (field_name, f"Current: {new_val}")
                menu.items = items

            # Redraw after popup
            draw_box(win, "Configure Melvin God Mode")
            safe_addstr(win, 1, 2,
                        "Edit config values.  Press Enter on a field to edit it.",
                        curses.color_pair(CP_DIM))


def _input_popup(stdscr, prompt: str, default: str) -> Optional[str]:
    """Show a small input box. Returns the new value or None if cancelled."""
    max_y, max_x = stdscr.getmaxyx()
    win_h, win_w = 6, min(60, max_x - 4)
    win = curses.newwin(win_h, win_w, (max_y - win_h) // 2, (max_x - win_w) // 2)
    draw_box(win, "Edit Value")
    safe_addstr(win, 1, 2, prompt[:win_w - 4], curses.color_pair(CP_NORMAL))
    safe_addstr(win, 2, 2, "New value:", curses.color_pair(CP_DIM))

    curses.curs_set(1)
    curses.echo()
    win.refresh()

    buf = list(default)
    safe_addstr(win, 3, 2, "".join(buf) + " " * (win_w - 4 - len(buf)), curses.color_pair(CP_HILITE))
    win.refresh()

    # Simple line editor
    while True:
        ch = win.getch(3, 2 + len(buf))
        if ch in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            break
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            if buf:
                buf.pop()
        elif ch == 27:   # Esc = cancel
            curses.noecho()
            curses.curs_set(0)
            return None
        elif 32 <= ch < 127:
            if len(buf) < win_w - 6:
                buf.append(chr(ch))
        safe_addstr(win, 3, 2, "".join(buf) + " " * (win_w - 4 - len(buf)), curses.color_pair(CP_HILITE))
        win.refresh()

    curses.noecho()
    curses.curs_set(0)
    return "".join(buf).strip() or default


def _show_message(stdscr, title: str, message: str, success: bool = True) -> None:
    max_y, max_x = stdscr.getmaxyx()
    lines = message.split("\n")
    win_h = len(lines) + 5
    win_w = min(max(len(l) for l in lines) + 6, max_x - 4)
    win = curses.newwin(win_h, win_w, (max_y - win_h) // 2, (max_x - win_w) // 2)
    draw_box(win, title)
    attr = curses.color_pair(CP_SUCCESS) if success else curses.color_pair(CP_ERROR)
    for i, line in enumerate(lines):
        safe_addstr(win, 1 + i, 2, line[:win_w - 4], attr)
    safe_addstr(win, win_h - 2, 2, "Press any key...", curses.color_pair(CP_DIM))
    win.refresh()
    win.getch()


# ─────────────────────────────────────────────────────────────────────────────
#  Screen: Uninstall
# ─────────────────────────────────────────────────────────────────────────────

def screen_uninstall(stdscr) -> None:
    max_y, max_x = stdscr.getmaxyx()
    win_h, win_w = 12, min(64, max_x - 4)
    win = curses.newwin(win_h, win_w, (max_y - win_h) // 2, (max_x - win_w) // 2)
    draw_box(win, "Uninstall Melvin God Mode")

    options = [
        "Remove Python packages (cryptography, requests, rich, textual)",
        f"Delete config directory  ({CONFIG_DIR})",
        f"Delete chat history      ({DATA_DIR})",
    ]
    checked = [True, False, False]

    cbl = CheckboxList(win, options, checked=checked, start_row=2)
    safe_addstr(win, 1, 2,
                "Select what to remove  (Space toggle, Enter confirm)",
                curses.color_pair(CP_WARN))

    while True:
        cbl.draw()
        draw_footer(win, "Space Toggle   Enter Confirm   q Cancel")
        win.refresh()
        key = win.getch()
        result = cbl.handle_key(key)
        if result is None:
            continue
        if not result:
            return   # Cancel

        # Confirm
        draw_box(win, "Confirm Uninstall")
        safe_addstr(win, 2, 2, "Are you sure? This cannot be undone.",
                    curses.color_pair(CP_ERROR) | curses.A_BOLD)
        safe_addstr(win, 4, 2, "[y] Yes, remove selected   [n] Cancel",
                    curses.color_pair(CP_NORMAL))
        win.refresh()
        ch = win.getch()
        if ch not in (ord('y'), ord('Y')):
            return

        _do_uninstall(stdscr, cbl.checked)
        return


def _do_uninstall(stdscr, checked: List[bool]) -> None:
    steps = []
    if checked[0]:
        steps.append(("Remove pip packages", lambda: _run(
            [sys.executable, "-m", "pip", "uninstall", "-y",
             "cryptography", "requests", "rich", "textual"],
            check=False,
        )))
    if checked[1]:
        steps.append(("Delete config directory", lambda: shutil.rmtree(CONFIG_DIR, ignore_errors=True)))
    if checked[2]:
        steps.append(("Delete chat history", lambda: shutil.rmtree(DATA_DIR, ignore_errors=True)))

    if steps:
        StepRunner(stdscr, "Uninstalling", steps).run()
    else:
        _show_message(stdscr, "Nothing to do", "No options were selected.", success=False)


# ─────────────────────────────────────────────────────────────────────────────
#  Main menu & application entry point
# ─────────────────────────────────────────────────────────────────────────────

MAIN_MENU_ITEMS = [
    ("Install",        "Install Melvin God Mode and dependencies"),
    ("Model Manager",  "Pull or manage local Ollama AI models"),
    ("Configure",      "Edit config.json (model, host, port, encryption …)"),
    ("Uninstall",      "Remove Melvin God Mode components"),
    ("About",          "Version info and system details"),
    ("Quit",           "Exit the installer"),
]


def main(stdscr) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    init_colours()

    max_y, max_x = stdscr.getmaxyx()
    if max_y < 20 or max_x < 60:
        stdscr.clear()
        stdscr.addstr(0, 0, f"Terminal too small ({max_x}x{max_y}). Please resize to at least 60x20.")
        stdscr.refresh()
        stdscr.getch()
        return

    # Main loop
    while True:
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        next_row = draw_banner(stdscr, start_y=1)

        # Status bar
        installed_marker = "✔ installed" if (CONFIG_DIR / "config.json").exists() else "not installed"
        ollama_ok = "✔ ollama found" if shutil.which("ollama") else "✘ ollama missing"
        status_line = f"  Status:  Melvin {installed_marker}   |   {ollama_ok}"
        safe_addstr(stdscr, next_row, 0,
                    status_line.center(max_x - 1),
                    curses.color_pair(CP_DIM))
        next_row += 2

        # Menu
        menu = Menu(stdscr, MAIN_MENU_ITEMS, start_row=next_row)

        while True:
            menu.draw()
            draw_footer(stdscr, "↑/↓ Navigate   Enter Select   q Quit")
            stdscr.refresh()
            key = stdscr.getch()
            result = menu.handle_key(key)
            if result is None:
                continue
            break

        if result == -1 or result == len(MAIN_MENU_ITEMS) - 1:
            break   # Quit

        screen_map = {
            0: screen_install,
            1: screen_models,
            2: screen_configure,
            3: screen_uninstall,
            4: screen_about,
        }
        handler = screen_map.get(result)
        if handler:
            handler(stdscr)


def entry_point() -> None:
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    print(f"\n  {APP_NAME} installer closed.\n")


if __name__ == "__main__":
    entry_point()
