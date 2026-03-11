"""
melvin/tools/manager.py
========================
Install, check, and run tools from the registry.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from typing import Callable, List, Optional

from melvin.tools.registry import ToolEntry, find_tool, search_tools, all_tools, REGISTRY


class _ThoughtSink:
    def log(self, message: str, level: str = "INFO") -> None:
        pass


class ToolManager:
    """
    Manages lifecycle of system tools: check installation, install, run, search.
    """

    def __init__(self, logger: _ThoughtSink) -> None:
        self._logger = logger
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Check
    # ------------------------------------------------------------------

    def is_installed(self, name: str) -> bool:
        """Return True if the binary is on PATH."""
        # pip-installed scripts end up on PATH; snap/apt too
        # Special case: some tools have different binary names
        binary_aliases = {
            "metasploit-framework": "msfconsole",
            "volatility3": "vol",
            "fd": "fd",          # Debian: fd-find → fdfind
            "bat": "batcat",     # Debian: bat → batcat
            "ripgrep": "rg",
            "imagemagick": "convert",
            "nodejs": "node",
            "rustc": "rustc",
            "go": "go",
        }
        binary = binary_aliases.get(name, name)
        found = shutil.which(binary) is not None
        # Debian special: fd-find is installed as fdfind
        if not found and name == "fd":
            found = shutil.which("fdfind") is not None
        return found

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def install(
        self,
        name: str,
        progress_cb: Optional[Callable[[int], None]] = None,
    ) -> tuple[bool, str]:
        """
        Install a tool.  Returns (success, message).

        Tries (in order): pip, snap, apt, manual notice.
        """
        entry = find_tool(name)
        if not entry:
            return False, f"Tool '{name}' not found in registry."

        self._logger.log(f"Installing {name} …")

        # --- pip ---
        if entry.pip_pkg:
            return self._run_install(
                ["pip", "install", "--quiet", entry.pip_pkg],
                progress_cb,
                f"pip install {entry.pip_pkg}",
            )

        # --- snap ---
        if entry.snap_pkg:
            return self._run_install(
                ["snap", "install"] + entry.snap_pkg.split(),
                progress_cb,
                f"snap install {entry.snap_pkg}",
            )

        # --- apt ---
        if entry.manual_url:
            msg = (
                f"'{name}' requires manual installation.\n"
                f"Visit: {entry.manual_url}"
            )
            self._logger.log(msg, "WARN")
            return False, msg

        pkg = entry.apt_pkg or name
        return self._run_install(
            ["apt", "install", "-y", pkg],
            progress_cb,
            f"apt install {pkg}",
        )

    def _run_install(
        self,
        cmd: List[str],
        progress_cb: Optional[Callable[[int]], None],
        label: str,
    ) -> tuple[bool, str]:
        self._logger.log(f"Running: {' '.join(cmd)}")
        try:
            with self._lock:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                output_lines: List[str] = []
                step = 0
                for line in proc.stdout or []:
                    output_lines.append(line.rstrip())
                    step = min(step + 1, 99)
                    if progress_cb:
                        progress_cb(step)
                proc.wait()
                if progress_cb:
                    progress_cb(100)

            if proc.returncode == 0:
                self._logger.log(f"{label} succeeded.")
                return True, f"'{label}' completed successfully."
            else:
                err = "\n".join(output_lines[-10:])
                self._logger.log(f"{label} failed: {err}", "ERROR")
                return False, f"Installation failed:\n{err}"
        except FileNotFoundError:
            msg = f"Package manager not found for: {label}"
            self._logger.log(msg, "ERROR")
            return False, msg
        except Exception as exc:  # noqa: BLE001
            self._logger.log(str(exc), "ERROR")
            return False, str(exc)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(
        self,
        name: str,
        args: Optional[List[str]] = None,
    ) -> subprocess.Popen:
        """
        Launch a tool as a subprocess.  Returns the Popen handle.
        The caller is responsible for communicating with / waiting for it.
        """
        cmd = [name] + (args or [])
        self._logger.log(f"Running: {' '.join(cmd)}")
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    # ------------------------------------------------------------------
    # Search / list
    # ------------------------------------------------------------------

    def search(self, query: str) -> List[ToolEntry]:
        return search_tools(query)

    def list_by_category(self, category: str) -> List[ToolEntry]:
        return REGISTRY.get(category, [])

    def all(self) -> List[ToolEntry]:
        return all_tools()

    def categories(self) -> List[str]:
        return list(REGISTRY.keys())

    def installed_tools(self) -> List[ToolEntry]:
        return [t for t in all_tools() if self.is_installed(t.name)]
