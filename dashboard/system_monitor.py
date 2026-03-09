"""
System Monitor for Melvin God Mode AI Infrastructure Platform.
Collects CPU, memory, disk, network, process, and system information.
"""

import json
import logging
import platform
import socket
import time
from datetime import datetime, timezone
from typing import Optional

try:
    import psutil  # type: ignore
    _PSUTIL = True
except ImportError:
    _PSUTIL = False
    logging.getLogger(__name__).warning(
        "psutil not installed — SystemMonitor will return stub data."
    )

logger = logging.getLogger(__name__)


class SystemMonitor:
    def __init__(self):
        if not _PSUTIL:
            logger.warning("psutil unavailable; some metrics will be empty.")

    # ------------------------------------------------------------------
    # CPU
    # ------------------------------------------------------------------

    def get_cpu_info(self) -> dict:
        """
        Return CPU info:
            usage_percent, cores (logical), frequency (MHz), load_average
        """
        if not _PSUTIL:
            return {"usage_percent": 0, "cores": 0, "frequency": 0, "load_average": [0, 0, 0]}

        freq = psutil.cpu_freq()
        try:
            load_avg = list(psutil.getloadavg())
        except AttributeError:
            load_avg = [0.0, 0.0, 0.0]

        return {
            "usage_percent": psutil.cpu_percent(interval=0.1),
            "cores": psutil.cpu_count(logical=True),
            "physical_cores": psutil.cpu_count(logical=False),
            "frequency": round(freq.current, 2) if freq else 0,
            "frequency_max": round(freq.max, 2) if freq else 0,
            "load_average": [round(x, 2) for x in load_avg],
        }

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def get_memory_info(self) -> dict:
        """
        Return memory info (bytes unless noted):
            total, used, free, percent, swap_total, swap_used
        """
        if not _PSUTIL:
            return {
                "total": 0, "used": 0, "free": 0, "percent": 0,
                "swap_total": 0, "swap_used": 0,
            }

        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "total": vm.total,
            "used": vm.used,
            "free": vm.available,
            "percent": vm.percent,
            "swap_total": swap.total,
            "swap_used": swap.used,
            "swap_percent": swap.percent,
        }

    # ------------------------------------------------------------------
    # Disk
    # ------------------------------------------------------------------

    def get_disk_info(self) -> list:
        """
        Return a list of dicts for each mounted partition:
            device, mountpoint, fstype, total, used, free, percent
        """
        if not _PSUTIL:
            return []

        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            disks.append(
                {
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                }
            )
        return disks

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    def get_network_info(self) -> dict:
        """
        Return network I/O counters and per-interface addresses:
            bytes_sent, bytes_recv, packets_sent, packets_recv, interfaces
        """
        if not _PSUTIL:
            return {
                "bytes_sent": 0, "bytes_recv": 0,
                "packets_sent": 0, "packets_recv": 0,
                "interfaces": {},
            }

        io = psutil.net_io_counters()
        addrs = psutil.net_if_addrs()
        interfaces = {}
        for iface, addr_list in addrs.items():
            interfaces[iface] = [
                {"family": str(a.family), "address": a.address}
                for a in addr_list
            ]
        return {
            "bytes_sent": io.bytes_sent,
            "bytes_recv": io.bytes_recv,
            "packets_sent": io.packets_sent,
            "packets_recv": io.packets_recv,
            "interfaces": interfaces,
        }

    # ------------------------------------------------------------------
    # Processes
    # ------------------------------------------------------------------

    def get_process_info(self, top_n: int = 10) -> list:
        """
        Return the top *top_n* processes by CPU usage.

        Each entry: {pid, name, cpu_percent, memory_percent, status}
        """
        if not _PSUTIL:
            return []

        procs = []
        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "status"]
        ):
            try:
                info = proc.info
                if info["cpu_percent"] is None:
                    info["cpu_percent"] = 0.0
                if info["memory_percent"] is None:
                    info["memory_percent"] = 0.0
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        procs.sort(key=lambda p: p.get("cpu_percent", 0), reverse=True)
        return procs[:top_n]

    # ------------------------------------------------------------------
    # System Info
    # ------------------------------------------------------------------

    def get_system_info(self) -> dict:
        """
        Return general system information:
            hostname, os, kernel, uptime, boot_time
        """
        boot_ts = psutil.boot_time() if _PSUTIL else 0
        boot_dt = datetime.fromtimestamp(boot_ts, tz=timezone.utc) if boot_ts else None
        uptime_secs = int(time.time() - boot_ts) if boot_ts else 0

        return {
            "hostname": socket.gethostname(),
            "os": platform.system(),
            "os_version": platform.version(),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "boot_time": boot_dt.isoformat() if boot_dt else "unknown",
            "uptime_seconds": uptime_secs,
            "uptime_human": _seconds_to_human(uptime_secs),
        }

    # ------------------------------------------------------------------
    # Combined
    # ------------------------------------------------------------------

    def get_all_stats(self) -> dict:
        """Return a combined dict of all system metrics."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cpu": self.get_cpu_info(),
            "memory": self.get_memory_info(),
            "disk": self.get_disk_info(),
            "network": self.get_network_info(),
            "processes": self.get_process_info(),
            "system": self.get_system_info(),
        }

    def to_json(self) -> str:
        """Return all stats serialised as a JSON string."""
        return json.dumps(self.get_all_stats(), indent=2, default=str)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seconds_to_human(secs: int) -> str:
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    monitor = SystemMonitor()
    print(monitor.to_json())
