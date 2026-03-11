"""
melvin/ui/menus.py
===================
All menu screens rendered as Rich renderables.
"""

from __future__ import annotations

import platform
from typing import List, Optional

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import APP_NAME, APP_VERSION, MODEL_CATALOGUE
from melvin.tools.registry import REGISTRY, ToolEntry
from melvin.core.agent import Agent


console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _section(title: str, content: str, color: str = "bright_blue") -> Panel:
    return Panel(content, title=f"[bold {color}]{title}[/]", border_style=color)


# ---------------------------------------------------------------------------
# Main Menu
# ---------------------------------------------------------------------------

MAIN_MENU_OPTIONS = [
    ("1", "💬 Chat with Melvin",   "Ask anything – AI routes to the best model"),
    ("2", "🤖 Agents",             "Browse & manage AI agents (models)"),
    ("3", "🛠  Tools",              "Browse, search, install & run 100+ tools"),
    ("4", "📚 Dataset",            "View conversation history / export dataset"),
    ("5", "⚙  Settings",           "Configure Ollama host, themes, limits"),
    ("6", "ℹ  System Info",        "Detailed hardware & OS information"),
    ("Q", "🚪 Quit",               "Exit Melvin"),
]

CHAT_HELP = (
    "Type your message and press [bold]Enter[/].\n"
    "Prefix with [bold cyan]!code[/], [bold yellow]!math[/], [bold green]!creative[/], "
    "[bold red]!security[/], [bold magenta]!osint[/] to force an agent.\n"
    "[bold]reset[/]  – clear conversation memory\n"
    "[bold]save[/]   – export dataset to plain JSON\n"
    "[bold]back[/]   – return to main menu"
)


def main_menu() -> Panel:
    t = Table(show_header=False, box=box.SIMPLE, expand=True)
    t.add_column("Key",  style="bold cyan",  no_wrap=True, width=5)
    t.add_column("Name", style="bold white", no_wrap=True)
    t.add_column("Desc", style="dim")

    for key, name, desc in MAIN_MENU_OPTIONS:
        t.add_row(f"[{key}]", name, desc)

    host = platform.node()
    return Panel(
        t,
        title=f"[bold red]✦ {APP_NAME} v{APP_VERSION} ✦[/]  [dim]{host}[/]",
        border_style="bright_blue",
        subtitle="[dim]Type the key and press Enter[/]",
    )


# ---------------------------------------------------------------------------
# Agent / Model menus
# ---------------------------------------------------------------------------

def agents_menu(agents: List[Agent], available_tags: set[str]) -> Panel:
    t = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.ROUNDED,
        expand=True,
    )
    t.add_column("#",        width=4,  style="dim")
    t.add_column("Model",              style="bold cyan")
    t.add_column("Category",           style="bold yellow")
    t.add_column("Size",     width=8,  style="cyan")
    t.add_column("RAM req",  width=10, style="green")
    t.add_column("Status",             justify="center")
    t.add_column("Description",        style="dim")

    for idx, agent in enumerate(agents, start=1):
        status = (
            "[bold green]✔ Installed[/]"
            if agent.spec.tag in available_tags
            else "[dim red]✘ Not pulled[/]"
        )
        t.add_row(
            str(idx),
            agent.spec.display_name,
            agent.spec.category,
            f"{agent.spec.size_gb:.1f} GB",
            f"{agent.spec.min_ram_gb:.0f} GB",
            status,
            agent.spec.description,
        )

    return Panel(
        t,
        title="[bold magenta]🤖 AI Agents[/]",
        border_style="magenta",
        subtitle="[dim]Enter model # to pull/use · B=back[/]",
    )


# ---------------------------------------------------------------------------
# Tools menus
# ---------------------------------------------------------------------------

def tools_categories_menu() -> Panel:
    t = Table(show_header=False, box=box.SIMPLE, expand=True)
    t.add_column("#",       style="bold cyan",  no_wrap=True, width=5)
    t.add_column("Category", style="bold white")
    t.add_column("Tools",   style="dim", justify="right", width=8)

    for idx, (cat, entries) in enumerate(REGISTRY.items(), start=1):
        t.add_row(str(idx), cat, str(len(entries)))

    t.add_row("S", "[bold yellow]Search tools[/]", "")
    t.add_row("B", "[bold red]Back[/]", "")

    return Panel(
        t,
        title="[bold green]🛠  Tools[/]",
        border_style="green",
        subtitle=f"[dim]{sum(len(v) for v in REGISTRY.values())} tools across {len(REGISTRY)} categories[/]",
    )


def tools_list_menu(category: str, tools: List[ToolEntry], installed: set[str]) -> Panel:
    t = Table(
        show_header=True,
        header_style="bold green",
        box=box.ROUNDED,
        expand=True,
    )
    t.add_column("#",      width=5,  style="dim")
    t.add_column("Tool",             style="bold cyan")
    t.add_column("Status",  width=14, justify="center")
    t.add_column("Install",          style="dim")
    t.add_column("Description",      style="dim")

    for idx, tool in enumerate(tools, start=1):
        status = (
            "[bold green]✔ Installed[/]"
            if tool.name in installed
            else "[dim red]✘ Missing[/]"
        )
        t.add_row(
            str(idx),
            tool.name,
            status,
            tool.install_method,
            tool.description,
        )

    return Panel(
        t,
        title=f"[bold green]🛠  {category}[/]",
        border_style="green",
        subtitle="[dim]Enter # to install · R+# to run · B=back[/]",
    )


def tool_detail_panel(tool: ToolEntry, is_installed: bool) -> Panel:
    lines = Text()
    lines.append(f"{tool.name}\n", style="bold cyan")
    lines.append(f"{tool.description}\n\n", style="white")
    lines.append(f"Category:  ", style="dim")
    lines.append(f"{tool.category}\n", style="bold")
    lines.append(f"Install:   ", style="dim")
    lines.append(f"{tool.install_method}\n", style="bold yellow")
    lines.append(f"Status:    ", style="dim")
    lines.append(
        "✔ Installed\n" if is_installed else "✘ Not installed\n",
        style="bold green" if is_installed else "bold red",
    )
    if tool.examples:
        lines.append("\nExamples:\n", style="bold magenta")
        for ex in tool.examples:
            lines.append(f"  $ {ex}\n", style="cyan")

    return Panel(lines, title=f"[bold]{tool.name}[/]", border_style="bright_blue")


# ---------------------------------------------------------------------------
# Dataset menu
# ---------------------------------------------------------------------------

def dataset_menu(count: int) -> Panel:
    t = Table(show_header=False, box=box.SIMPLE, expand=True)
    t.add_column("Key",  style="bold cyan",  no_wrap=True, width=5)
    t.add_column("Action", style="bold white")

    t.add_row("[1]", "View last 20 interactions")
    t.add_row("[2]", "Search interactions")
    t.add_row("[3]", "Export to plain JSON")
    t.add_row("[4]", "Import from plain JSON")
    t.add_row("[B]", "[bold red]Back[/]")

    return Panel(
        t,
        title=f"[bold yellow]📚 Dataset — {count:,} interactions[/]",
        border_style="yellow",
    )


def dataset_view(records: list) -> Panel:
    t = Table(
        show_header=True,
        header_style="bold yellow",
        box=box.ROUNDED,
        expand=True,
    )
    t.add_column("Time",    width=10, style="dim")
    t.add_column("Agent",   width=10, style="bold cyan")
    t.add_column("Model",   width=22, style="cyan")
    t.add_column("Input",   style="white")
    t.add_column("Response", style="dim")

    for r in records:
        ts = (r.get("timestamp") or "")[:10]
        t.add_row(
            ts,
            r.get("agent", ""),
            r.get("model", ""),
            r.get("input", "")[:60],
            r.get("response", "")[:80],
        )

    return Panel(t, title="[bold yellow]Recent Interactions[/]", border_style="yellow")


# ---------------------------------------------------------------------------
# Settings menu
# ---------------------------------------------------------------------------

def settings_menu(ollama_host: str, god_mode: bool) -> Panel:
    t = Table(show_header=False, box=box.SIMPLE, expand=True)
    t.add_column("Key",     style="bold cyan",  no_wrap=True, width=5)
    t.add_column("Setting", style="bold white")
    t.add_column("Value",   style="bold yellow")

    t.add_row("[1]", "Ollama host", ollama_host)
    t.add_row("[2]", "God Mode (unrestricted agent)",
              "[bold red]ON[/]" if god_mode else "[dim]off[/]")
    t.add_row("[B]", "[bold red]Back[/]", "")

    return Panel(t, title="[bold blue]⚙  Settings[/]", border_style="blue")


# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------

def system_info_panel() -> Panel:
    import psutil

    uname = platform.uname()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    lines = Text()
    lines.append("OS:        ", style="dim"); lines.append(f"{uname.system} {uname.release}\n")
    lines.append("Host:      ", style="dim"); lines.append(f"{uname.node}\n")
    lines.append("Arch:      ", style="dim"); lines.append(f"{uname.machine}\n")
    lines.append("CPU:       ", style="dim"); lines.append(f"{psutil.cpu_count(logical=False)} cores / {psutil.cpu_count()} threads\n")
    lines.append("RAM:       ", style="dim"); lines.append(f"{mem.total / 1024**3:.1f} GB total\n")
    lines.append("Disk (/):  ", style="dim"); lines.append(f"{disk.total / 1024**3:.0f} GB total · {disk.free / 1024**3:.0f} GB free\n")
    lines.append("Python:    ", style="dim"); lines.append(f"{platform.python_version()}\n")

    return Panel(lines, title="[bold blue]ℹ  System Information[/]", border_style="blue")
