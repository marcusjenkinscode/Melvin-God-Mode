"""
main.py
========
Melvin AI – entry point.

Handles:
- Dependency bootstrap
- Signal handling (Ctrl-C graceful shutdown)
- Main event loop (non-blocking keyboard input via a thread)
- Menu navigation state machine
"""

from __future__ import annotations

import os
import sys
import signal
import threading
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Early dependency check & auto-install
# ---------------------------------------------------------------------------

def _ensure_deps() -> None:
    """Install missing packages from requirements.txt before importing them."""
    reqs = Path(__file__).parent / "requirements.txt"
    if not reqs.exists():
        return
    packages = [
        line.strip().split(">=")[0].split("==")[0]
        for line in reqs.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    missing = []
    for pkg in packages:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing missing packages: {', '.join(missing)} …")
        import subprocess
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        )


_ensure_deps()

# ---------------------------------------------------------------------------
# Normal imports (after deps are available)
# ---------------------------------------------------------------------------

from rich.console import Console
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich import print as rprint

from config import (
    OLLAMA_HOST,
    MODEL_CATALOGUE,
    APP_NAME,
    APP_VERSION,
    DATA_DIR,
    DATASET_FILE,
)
from melvin.monitoring.system import SystemMonitor
from melvin.core.dataset import Dataset
from melvin.core.agent import AgentRegistry
from melvin.core.router import ModelRouter
from melvin.tools.registry import REGISTRY, find_tool, search_tools
from melvin.tools.manager import ToolManager
from melvin.ui.layout import ThoughtLogger, ChatDisplay, MelvinLayout
from melvin.ui import menus

console = Console()

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

class AppState:
    def __init__(self) -> None:
        self.running = True
        self.god_mode = False
        self.current_menu = "main"
        self.menu_context: dict = {}   # holds category name, tool index, etc.


# ---------------------------------------------------------------------------
# Melvin Application
# ---------------------------------------------------------------------------

class MelvinApp:
    def __init__(self) -> None:
        self.state = AppState()

        # Infrastructure
        self.monitor = SystemMonitor(interval=2.0)
        self.dataset = Dataset()
        self.logger = ThoughtLogger()
        self.chat_display = ChatDisplay()
        self.layout = MelvinLayout(self.logger, self.chat_display)

        # AI
        self.registry = AgentRegistry(
            dataset=self.dataset,
            logger=self.logger,
            ollama_host=OLLAMA_HOST,
        )
        self.router = ModelRouter(self.registry, self.monitor)

        # Tools
        self.tool_manager = ToolManager(self.logger)

        self.logger.log(f"{APP_NAME} v{APP_VERSION} initialised.")
        self.logger.log(f"Data dir: {DATA_DIR}")
        self.logger.log(f"Dataset interactions: {self.dataset.count()}")
        self.logger.log(f"Ollama host: {OLLAMA_HOST}")

        available = self.registry.list_available()
        self.logger.log(
            f"Available models: {len(available)} / {len(MODEL_CATALOGUE)}"
        )

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def _setup_signals(self) -> None:
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _handle_exit(self, signum, frame) -> None:  # noqa: ANN001
        self.logger.log("Shutdown signal received – cleaning up…", "WARN")
        self.state.running = False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._setup_signals()
        self._print_banner()

        with Live(
            console=console,
            refresh_per_second=4,
            screen=True,
        ) as live:
            while self.state.running:
                monitor_panel = self.monitor.get_stats_panel()

                if self.state.current_menu == "main":
                    main_panel = menus.main_menu()
                elif self.state.current_menu == "chat":
                    main_panel = self.chat_display.get_panel()
                elif self.state.current_menu == "agents":
                    all_agents = self.registry.list_agents()
                    available_tags = {a.spec.tag for a in self.registry.list_available()}
                    main_panel = menus.agents_menu(all_agents, available_tags)
                elif self.state.current_menu == "tools_categories":
                    main_panel = menus.tools_categories_menu()
                elif self.state.current_menu == "tools_list":
                    cat = self.state.menu_context.get("category", "")
                    tools = self.tool_manager.list_by_category(cat)
                    installed = {t.name for t in self.tool_manager.installed_tools()}
                    main_panel = menus.tools_list_menu(cat, tools, installed)
                elif self.state.current_menu == "dataset":
                    main_panel = menus.dataset_menu(self.dataset.count())
                elif self.state.current_menu == "settings":
                    main_panel = menus.settings_menu(OLLAMA_HOST, self.state.god_mode)
                elif self.state.current_menu == "sysinfo":
                    main_panel = menus.system_info_panel()
                else:
                    main_panel = menus.main_menu()

                live.update(
                    self.layout.refresh(monitor_panel, main_panel)
                )

                # Non-blocking: pause briefly then re-draw
                time.sleep(0.25)

        self._shutdown()

    # ------------------------------------------------------------------
    # Command processing
    # ------------------------------------------------------------------

    def handle_input(self, raw: str) -> None:
        """Dispatch a user input string based on current menu."""
        cmd = raw.strip()
        if not cmd:
            return

        menu = self.state.current_menu

        # Global commands
        if cmd.lower() == "q" or cmd.lower() == "quit":
            self.state.running = False
            return

        if menu == "main":
            self._handle_main(cmd)
        elif menu == "chat":
            self._handle_chat(cmd)
        elif menu == "agents":
            self._handle_agents(cmd)
        elif menu == "tools_categories":
            self._handle_tools_categories(cmd)
        elif menu == "tools_list":
            self._handle_tools_list(cmd)
        elif menu == "dataset":
            self._handle_dataset(cmd)
        elif menu == "settings":
            self._handle_settings(cmd)
        elif menu in ("sysinfo",):
            self.state.current_menu = "main"

    def _handle_main(self, cmd: str) -> None:
        mapping = {
            "1": "chat",
            "2": "agents",
            "3": "tools_categories",
            "4": "dataset",
            "5": "settings",
            "6": "sysinfo",
        }
        dest = mapping.get(cmd.upper())
        if dest:
            self.state.current_menu = dest
            self.logger.log(f"Navigated to: {dest}")

    def _handle_chat(self, cmd: str) -> None:
        if cmd.lower() in ("back", "b"):
            self.state.current_menu = "main"
            return
        if cmd.lower() == "reset":
            for agent in self.registry.list_available():
                agent.reset_memory()
            self.chat_display.add_system("Memory cleared.")
            return
        if cmd.lower() == "save":
            out = DATA_DIR / "dataset_export.json"
            self.dataset.export_plaintext(out)
            self.chat_display.add_system(f"Dataset exported to {out}")
            return

        # Route and chat
        agent, clean_prompt = self.router.route(cmd)
        if agent is None:
            self.chat_display.add_system(
                "No models available. Pull a model first: go to Agents menu."
            )
            return

        self.chat_display.add_user(cmd)
        self.layout.set_status(f"Thinking with {agent.spec.display_name}…")

        def _stream_cb(token: str) -> None:
            self.chat_display.append_stream_chunk(token)

        # Run in thread so the Live display keeps refreshing
        def _chat_thread() -> None:
            response = agent.chat(clean_prompt, stream_cb=_stream_cb)
            self.chat_display.flush_stream(model=agent.spec.tag)
            self.layout.set_status("")

        t = threading.Thread(target=_chat_thread, daemon=True)
        t.start()

    def _handle_agents(self, cmd: str) -> None:
        if cmd.upper() in ("B", "BACK"):
            self.state.current_menu = "main"
            return
        # Try numeric index
        try:
            idx = int(cmd) - 1
            agents = self.registry.list_agents()
            if 0 <= idx < len(agents):
                chosen = agents[idx]
                self.logger.log(f"Pulling model: {chosen.spec.tag}")
                console.print(f"\n[cyan]Pulling {chosen.spec.display_name}…[/]")
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("{task.percentage:>3.0f}%"),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(chosen.spec.tag, total=100)

                    def _cb(msg: str, pct: float) -> None:
                        progress.update(task, completed=pct, description=msg[:40])

                    self.registry.pull_agent(chosen.spec.tag, progress_cb=_cb)
                self.logger.log(f"{chosen.spec.tag} pull complete.")
        except ValueError:
            pass

    def _handle_tools_categories(self, cmd: str) -> None:
        if cmd.upper() in ("B", "BACK"):
            self.state.current_menu = "main"
            return
        if cmd.upper() == "S":
            query = Prompt.ask("[cyan]Search tools[/]")
            results = self.tool_manager.search(query)
            if results:
                installed = {t.name for t in self.tool_manager.installed_tools()}
                self.state.menu_context = {"category": f"Search: {query}", "_tools": results}
                # Reuse tools_list with the search results
                self.state.current_menu = "tools_list"
            else:
                console.print(f"[red]No tools found for: {query}[/]")
            return
        try:
            idx = int(cmd) - 1
            categories = list(REGISTRY.keys())
            if 0 <= idx < len(categories):
                self.state.menu_context = {"category": categories[idx]}
                self.state.current_menu = "tools_list"
        except ValueError:
            pass

    def _handle_tools_list(self, cmd: str) -> None:
        if cmd.upper() in ("B", "BACK"):
            self.state.current_menu = "tools_categories"
            return
        cat = self.state.menu_context.get("category", "")
        tools = self.state.menu_context.get("_tools") or self.tool_manager.list_by_category(cat)

        # "R3" means run tool #3
        if cmd.upper().startswith("R"):
            try:
                idx = int(cmd[1:]) - 1
                if 0 <= idx < len(tools):
                    tool = tools[idx]
                    if not self.tool_manager.is_installed(tool.name):
                        console.print(f"[red]{tool.name} is not installed.[/]")
                    else:
                        console.print(f"\n[cyan]Running: {tool.name}[/]")
                        proc = self.tool_manager.run(tool.name, ["--help"])
                        out, _ = proc.communicate(timeout=10)
                        console.print(out[:2000])
                return
            except (ValueError, IndexError):
                pass

        try:
            idx = int(cmd) - 1
            if 0 <= idx < len(tools):
                tool = tools[idx]
                installed = self.tool_manager.is_installed(tool.name)
                console.print(menus.tool_detail_panel(tool, installed))
                if not installed:
                    confirm = Prompt.ask(f"Install {tool.name}?", choices=["y", "n"], default="n")
                    if confirm == "y":
                        with Progress(
                            SpinnerColumn(),
                            TextColumn("[progress.description]{task.description}"),
                            BarColumn(),
                            console=console,
                        ) as progress:
                            task = progress.add_task(f"Installing {tool.name}…", total=100)
                            success, msg = self.tool_manager.install(
                                tool.name,
                                progress_cb=lambda pct: progress.update(task, completed=pct),
                            )
                        if success:
                            console.print(f"[green]✔ {msg}[/]")
                        else:
                            console.print(f"[red]✘ {msg}[/]")
        except ValueError:
            pass

    def _handle_dataset(self, cmd: str) -> None:
        if cmd.upper() in ("B", "BACK"):
            self.state.current_menu = "main"
            return
        if cmd == "1":
            records = self.dataset.load_all()[-20:]
            console.print(menus.dataset_view(records))
            input("Press Enter to continue…")
        elif cmd == "2":
            query = Prompt.ask("[cyan]Search[/]")
            results = self.dataset.search(query)
            if results:
                console.print(menus.dataset_view(results))
            else:
                console.print("[red]No results found.[/]")
            input("Press Enter to continue…")
        elif cmd == "3":
            out = DATA_DIR / "dataset_export.json"
            self.dataset.export_plaintext(out)
            console.print(f"[green]Exported to {out}[/]")
        elif cmd == "4":
            src_str = Prompt.ask("[cyan]Path to JSON file[/]")
            src = Path(src_str)
            if src.exists():
                count = self.dataset.import_plaintext(src)
                console.print(f"[green]Imported {count} records.[/]")
            else:
                console.print(f"[red]File not found: {src}[/]")

    def _handle_settings(self, cmd: str) -> None:
        if cmd.upper() in ("B", "BACK"):
            self.state.current_menu = "main"
            return
        if cmd == "2":
            self.state.god_mode = not self.state.god_mode
            status = "ON" if self.state.god_mode else "OFF"
            self.logger.log(f"God Mode: {status}")
            self.layout.set_mode("GOD MODE" if self.state.god_mode else "NORMAL")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _shutdown(self) -> None:
        self.logger.log("Shutting down…")
        self.monitor.stop()
        console.print(f"\n[bold green]Goodbye from {APP_NAME}! 👋[/]\n")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _print_banner() -> None:
        console.print(
            Panel(
                Text(
                    f"  {APP_NAME} v{APP_VERSION}\n"
                    "  Self-Learning AI · Universal Toolkit · Hacker CLI\n"
                    "  Debian Edition  🔥",
                    justify="center",
                    style="bold green",
                ),
                border_style="bright_blue",
            )
        )


# ---------------------------------------------------------------------------
# Interactive input loop (runs alongside the Live display in a thread)
# ---------------------------------------------------------------------------

def _input_loop(app: MelvinApp) -> None:
    """Read lines from stdin and dispatch them to app.handle_input()."""
    while app.state.running:
        try:
            line = input()
            app.handle_input(line)
        except EOFError:
            app.state.running = False
            break
        except KeyboardInterrupt:
            app.state.running = False
            break


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = MelvinApp()

    # Run input loop in background thread
    input_thread = threading.Thread(
        target=_input_loop,
        args=(app,),
        daemon=True,
        name="InputLoop",
    )
    input_thread.start()

    # Main Live loop (blocks until running = False)
    app.run()


if __name__ == "__main__":
    main()
