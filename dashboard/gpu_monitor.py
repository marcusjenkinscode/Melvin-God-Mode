"""
GPU Monitor for Melvin God Mode AI Infrastructure Platform.
Polls NVIDIA GPUs via nvidia-smi, maintains historical utilisation data,
and optionally monitors in a background thread.
"""

import collections
import logging
import subprocess
import threading
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_HISTORY_MAX_POINTS = 720  # keep up to 1 hour @ 5-second intervals


class GPUMonitor:
    def __init__(self):
        # {gpu_id: deque of {timestamp, utilization, memory_used, temperature}}
        self._history: dict = {}
        self._latest: dict = {}
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._nvidia_available = self._probe_nvidia()

    # ------------------------------------------------------------------
    # Availability Probe
    # ------------------------------------------------------------------

    @staticmethod
    def _probe_nvidia() -> bool:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    # ------------------------------------------------------------------
    # GPU List
    # ------------------------------------------------------------------

    def get_gpu_list(self) -> list:
        """
        Query nvidia-smi for all installed GPUs.

        Returns a list of dicts:
            {id, name, memory_total, memory_used, memory_free,
             utilization, temperature, power_draw, power_limit}

        Returns an empty list with a warning if NVIDIA tooling is absent.
        """
        if not self._nvidia_available:
            logger.info("No NVIDIA GPU available; returning empty GPU list.")
            return []

        query = (
            "index,name,memory.total,memory.used,memory.free,"
            "utilization.gpu,temperature.gpu,power.draw,power.limit"
        )
        cmd = [
            "nvidia-smi",
            f"--query-gpu={query}",
            "--format=csv,noheader,nounits",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
        except subprocess.TimeoutExpired:
            logger.warning("nvidia-smi timed out in get_gpu_list().")
            return []
        except FileNotFoundError:
            self._nvidia_available = False
            return []

        if result.returncode != 0:
            logger.warning("nvidia-smi returned non-zero: %s", result.stderr.strip())
            return []

        gpus = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 9:
                continue

            def _int(v: str, default: int = 0) -> int:
                try:
                    return int(float(v))
                except (ValueError, TypeError):
                    return default

            gpus.append(
                {
                    "id": _int(parts[0]),
                    "name": parts[1],
                    "memory_total": _int(parts[2]),
                    "memory_used": _int(parts[3]),
                    "memory_free": _int(parts[4]),
                    "utilization": _int(parts[5]),
                    "temperature": _int(parts[6]),
                    "power_draw": _int(parts[7]),
                    "power_limit": _int(parts[8]),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
        return gpus

    # ------------------------------------------------------------------
    # Processes
    # ------------------------------------------------------------------

    def get_gpu_processes(self, gpu_id: int) -> list:
        """
        Return a list of processes using *gpu_id*.

        Each entry: {pid, name, used_memory_mib}
        """
        if not self._nvidia_available:
            return []

        cmd = [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
            f"--id={gpu_id}",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("nvidia-smi process query failed: %s", exc)
            return []

        if result.returncode != 0:
            return []

        processes = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 4:
                continue
            try:
                processes.append(
                    {
                        "pid": int(parts[1]),
                        "name": parts[2],
                        "used_memory_mib": int(parts[3]) if parts[3].isdigit() else 0,
                    }
                )
            except (ValueError, IndexError) as exc:
                logger.debug("Skipping process line '%s': %s", line, exc)
        return processes

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record_history(self, gpus: list) -> None:
        """Append a snapshot of each GPU's stats to its history deque."""
        with self._lock:
            for gpu in gpus:
                gid = gpu["id"]
                if gid not in self._history:
                    self._history[gid] = collections.deque(maxlen=_HISTORY_MAX_POINTS)
                self._history[gid].append(
                    {
                        "timestamp": gpu["timestamp"],
                        "utilization": gpu["utilization"],
                        "memory_used": gpu["memory_used"],
                        "temperature": gpu["temperature"],
                    }
                )
            self._latest = {gpu["id"]: gpu for gpu in gpus}

    def get_gpu_history(self, gpu_id: int, seconds: int = 60) -> list:
        """
        Return historical utilisation points for *gpu_id* covering the last
        *seconds* seconds.

        Each point: {timestamp, utilization, memory_used, temperature}
        """
        with self._lock:
            history = self._history.get(gpu_id)
            if not history:
                return []
            cutoff = time.time() - seconds
            result = []
            for point in history:
                try:
                    ts = datetime.fromisoformat(point["timestamp"]).timestamp()
                    if ts >= cutoff:
                        result.append(point)
                except (ValueError, KeyError):
                    result.append(point)
            return result

    # ------------------------------------------------------------------
    # Background Monitor
    # ------------------------------------------------------------------

    def monitor_loop(self, interval: int = 5) -> None:
        """
        Poll GPU stats every *interval* seconds and record them in history.
        Designed to run in a daemon thread via start_monitor().
        """
        self._running = True
        logger.info("GPU monitor loop started (interval=%ds).", interval)
        while self._running:
            try:
                gpus = self.get_gpu_list()
                if gpus:
                    self._record_history(gpus)
            except Exception as exc:
                logger.error("Error in GPU monitor loop: %s", exc)
            time.sleep(interval)
        logger.info("GPU monitor loop stopped.")

    def start_monitor(self, interval: int = 5) -> None:
        """Start the background monitor thread."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("GPU monitor thread already running.")
            return
        self._monitor_thread = threading.Thread(
            target=self.monitor_loop,
            args=(interval,),
            name="gpu-monitor-dashboard",
            daemon=True,
        )
        self._monitor_thread.start()

    def stop_monitor(self) -> None:
        """Signal the monitor loop to stop and wait for thread exit."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=15)

    # ------------------------------------------------------------------
    # Latest Stats
    # ------------------------------------------------------------------

    def get_latest_stats(self) -> dict:
        """
        Return the most recently recorded stats for all GPUs.

        Returns {gpu_id: gpu_dict} or an empty dict if no data yet.
        """
        with self._lock:
            return dict(self._latest)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    monitor = GPUMonitor()
    gpus = monitor.get_gpu_list()
    if gpus:
        print(json.dumps(gpus, indent=2))
    else:
        print("No NVIDIA GPUs detected.")
