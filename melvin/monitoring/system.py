"""
melvin/monitoring/system.py
============================
Background system resource monitor using psutil and (optionally) GPUtil.
"""

from __future__ import annotations

import threading
import time
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

import psutil
from rich.panel import Panel
from rich.text import Text

try:
    import GPUtil  # type: ignore
    _GPUTIL = True
except ImportError:
    _GPUTIL = False


@dataclass
class GpuStats:
    index: int
    name: str
    load_pct: float      # 0-100
    mem_used_mb: float
    mem_total_mb: float
    temperature: float   # Celsius


@dataclass
class SystemSnapshot:
    cpu_pct: float = 0.0
    cpu_cores: int = 0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    gpus: List[GpuStats] = field(default_factory=list)
    net_sent_mb: float = 0.0
    net_recv_mb: float = 0.0


class SystemMonitor:
    """
    Runs a daemon thread that refreshes system metrics every *interval* seconds.
    Thread-safe reads via a simple lock.
    """

    def __init__(self, interval: float = 2.0) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._snapshot = SystemSnapshot(cpu_cores=psutil.cpu_count(logical=True) or 1)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="SysMonitor")
        self._thread.start()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def snapshot(self) -> SystemSnapshot:
        with self._lock:
            return SystemSnapshot(
                cpu_pct=self._snapshot.cpu_pct,
                cpu_cores=self._snapshot.cpu_cores,
                ram_used_gb=self._snapshot.ram_used_gb,
                ram_total_gb=self._snapshot.ram_total_gb,
                disk_used_gb=self._snapshot.disk_used_gb,
                disk_total_gb=self._snapshot.disk_total_gb,
                gpus=list(self._snapshot.gpus),
                net_sent_mb=self._snapshot.net_sent_mb,
                net_recv_mb=self._snapshot.net_recv_mb,
            )

    def available_ram_gb(self) -> float:
        s = self.snapshot
        return s.ram_total_gb - s.ram_used_gb

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5)

    def get_stats_panel(self) -> Panel:
        s = self.snapshot
        t = Text()
        t.append(f"CPU  {s.cpu_pct:5.1f}%  ({s.cpu_cores} cores)\n", style="bold green")
        t.append(
            f"RAM  {s.ram_used_gb:.1f}/{s.ram_total_gb:.1f} GB  "
            f"({100 * s.ram_used_gb / max(s.ram_total_gb, 0.01):.0f}%)\n",
            style="bold cyan",
        )
        t.append(
            f"Disk {s.disk_used_gb:.0f}/{s.disk_total_gb:.0f} GB  "
            f"({100 * s.disk_used_gb / max(s.disk_total_gb, 0.01):.0f}%)\n",
            style="bold magenta",
        )
        t.append(
            f"Net  ↑{s.net_sent_mb:.1f} MB  ↓{s.net_recv_mb:.1f} MB\n",
            style="bold blue",
        )
        if s.gpus:
            for g in s.gpus:
                t.append(
                    f"GPU{g.index} {g.name}  {g.load_pct:.0f}%  "
                    f"VRAM {g.mem_used_mb:.0f}/{g.mem_total_mb:.0f} MB  "
                    f"{g.temperature:.0f}°C\n",
                    style="bold yellow",
                )
        else:
            t.append("GPU  not detected / no CUDA\n", style="dim yellow")

        return Panel(t, title="[bold red]⚡ System Resources[/]", border_style="bright_blue")

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                snap = self._collect()
                with self._lock:
                    self._snapshot = snap
            except Exception:  # noqa: BLE001
                pass
            self._stop_event.wait(timeout=self._interval)

    def _collect(self) -> SystemSnapshot:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()

        gpus: List[GpuStats] = []

        # Try GPUtil first (NVIDIA/AMD via OpenCL)
        if _GPUTIL:
            try:
                for g in GPUtil.getGPUs():
                    gpus.append(
                        GpuStats(
                            index=g.id,
                            name=g.name,
                            load_pct=g.load * 100,
                            mem_used_mb=g.memoryUsed,
                            mem_total_mb=g.memoryTotal,
                            temperature=g.temperature,
                        )
                    )
            except Exception:  # noqa: BLE001
                pass

        # Fallback: nvidia-smi
        if not gpus:
            gpus = self._nvidia_smi()

        return SystemSnapshot(
            cpu_pct=cpu,
            cpu_cores=psutil.cpu_count(logical=True) or 1,
            ram_used_gb=mem.used / 1024**3,
            ram_total_gb=mem.total / 1024**3,
            disk_used_gb=disk.used / 1024**3,
            disk_total_gb=disk.total / 1024**3,
            gpus=gpus,
            net_sent_mb=net.bytes_sent / 1024**2,
            net_recv_mb=net.bytes_recv / 1024**2,
        )

    @staticmethod
    def _nvidia_smi() -> List[GpuStats]:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode != 0:
                return []
            gpus = []
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 6:
                    continue
                gpus.append(
                    GpuStats(
                        index=int(parts[0]),
                        name=parts[1],
                        load_pct=float(parts[2]),
                        mem_used_mb=float(parts[3]),
                        mem_total_mb=float(parts[4]),
                        temperature=float(parts[5]),
                    )
                )
            return gpus
        except Exception:  # noqa: BLE001
            return []
