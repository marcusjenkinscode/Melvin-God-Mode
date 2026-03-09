"""
GPU Scheduler for Melvin God Mode AI Infrastructure Platform.
Manages GPU resource allocation, job scheduling, and load balancing.
"""

import subprocess
import threading
import time
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class GPUScheduler:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.active_jobs: dict = {}  # {job_id: {gpu_id, model, started}}
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._gpu_cache: list = []
        self._cache_ttl = self.config.get("cache_ttl", 5)
        self._cache_time = 0.0
        self._monitor_interval = self.config.get("monitor_interval", 10)

    # ------------------------------------------------------------------
    # GPU Detection
    # ------------------------------------------------------------------

    def _parse_nvidia_smi(self) -> list:
        """Query nvidia-smi and return structured GPU info."""
        query_fields = (
            "index,name,memory.total,memory.used,memory.free,"
            "utilization.gpu,temperature.gpu"
        )
        cmd = [
            "nvidia-smi",
            f"--query-gpu={query_fields}",
            "--format=csv,noheader,nounits",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return []

        gpus = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 7:
                continue
            try:
                gpus.append(
                    {
                        "id": int(parts[0]),
                        "name": parts[1],
                        "memory_total": int(parts[2]),
                        "memory_used": int(parts[3]),
                        "memory_free": int(parts[4]),
                        "utilization": int(parts[5]) if parts[5] not in ("N/A", "[N/A]") else 0,
                        "temperature": int(parts[6]) if parts[6] not in ("N/A", "[N/A]") else 0,
                        "source": "nvidia-smi",
                    }
                )
            except (ValueError, IndexError) as exc:
                logger.warning("Failed to parse nvidia-smi line '%s': %s", line, exc)
        return gpus

    def _parse_gputil(self) -> list:
        """Fallback: use GPUtil library to detect GPUs."""
        try:
            import GPUtil  # type: ignore

            gpus = []
            for g in GPUtil.getGPUs():
                gpus.append(
                    {
                        "id": g.id,
                        "name": g.name,
                        "memory_total": int(g.memoryTotal),
                        "memory_used": int(g.memoryUsed),
                        "memory_free": int(g.memoryFree),
                        "utilization": int(g.load * 100),
                        "temperature": int(g.temperature),
                        "source": "gputil",
                    }
                )
            return gpus
        except ImportError:
            logger.debug("GPUtil not installed; skipping GPUtil detection.")
        except Exception as exc:
            logger.warning("GPUtil error: %s", exc)
        return []

    def detect_gpus(self) -> list:
        """
        Detect available GPUs.

        Returns a list of dicts:
            {id, name, memory_total, memory_used, memory_free, utilization, temperature}

        Tries nvidia-smi first, then GPUtil, then returns an empty list.
        """
        gpus = []
        try:
            gpus = self._parse_nvidia_smi()
        except FileNotFoundError:
            logger.info("nvidia-smi not found; trying GPUtil.")
        except subprocess.TimeoutExpired:
            logger.warning("nvidia-smi timed out.")
        except Exception as exc:
            logger.warning("Unexpected error from nvidia-smi: %s", exc)

        if not gpus:
            gpus = self._parse_gputil()

        if not gpus:
            logger.info("No NVIDIA GPUs detected; running in CPU-only mode.")

        return gpus

    def _get_gpus_cached(self) -> list:
        """Return GPU list, refreshing the cache if stale."""
        now = time.monotonic()
        if now - self._cache_time > self._cache_ttl:
            self._gpu_cache = self.detect_gpus()
            self._cache_time = now
        return self._gpu_cache

    # ------------------------------------------------------------------
    # Job Scheduling
    # ------------------------------------------------------------------

    def schedule_job(
        self, job_id: str, model_name: str, memory_required: int
    ) -> Optional[int]:
        """
        Assign *job_id* to the GPU with the most free memory that satisfies
        *memory_required* (MiB).

        Returns the gpu_id on success, or None if no suitable GPU is found.
        """
        gpus = self._get_gpus_cached()
        if not gpus:
            logger.warning("No GPUs available to schedule job '%s'.", job_id)
            return None

        # Filter GPUs that meet the memory requirement
        candidates = [g for g in gpus if g["memory_free"] >= memory_required]
        if not candidates:
            logger.warning(
                "No GPU with >= %d MiB free memory for job '%s'. "
                "Available free memory: %s",
                memory_required,
                job_id,
                [g["memory_free"] for g in gpus],
            )
            return None

        # Pick the GPU with the most free memory
        best = max(candidates, key=lambda g: g["memory_free"])
        gpu_id = best["id"]

        with self._lock:
            if job_id in self.active_jobs:
                logger.warning("Job '%s' is already scheduled.", job_id)
                return self.active_jobs[job_id]["gpu_id"]

            self.active_jobs[job_id] = {
                "gpu_id": gpu_id,
                "model": model_name,
                "started": datetime.utcnow().isoformat(),
            }

        logger.info(
            "Scheduled job '%s' (model=%s, memory=%d MiB) on GPU %d.",
            job_id,
            model_name,
            memory_required,
            gpu_id,
        )
        return gpu_id

    def release_job(self, job_id: str) -> bool:
        """Remove *job_id* from active_jobs. Returns True if found."""
        with self._lock:
            if job_id in self.active_jobs:
                info = self.active_jobs.pop(job_id)
                logger.info(
                    "Released job '%s' from GPU %d (model=%s).",
                    job_id,
                    info["gpu_id"],
                    info["model"],
                )
                return True
        logger.warning("Attempted to release unknown job '%s'.", job_id)
        return False

    # ------------------------------------------------------------------
    # Stats & Reporting
    # ------------------------------------------------------------------

    def get_gpu_stats(self) -> list:
        """Return current GPU stats (with active job counts annotated)."""
        gpus = self.detect_gpus()
        # Count jobs per GPU
        with self._lock:
            jobs_per_gpu: dict = {}
            for info in self.active_jobs.values():
                gid = info["gpu_id"]
                jobs_per_gpu[gid] = jobs_per_gpu.get(gid, 0) + 1

        for gpu in gpus:
            gpu["active_jobs"] = jobs_per_gpu.get(gpu["id"], 0)
        return gpus

    def get_utilization_report(self) -> str:
        """Return a human-readable utilization report."""
        gpus = self.get_gpu_stats()
        if not gpus:
            return "No GPUs detected.\n"

        lines = [
            "=" * 70,
            f"{'GPU Utilization Report':^70}",
            f"{'Generated: ' + datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'):^70}",
            "=" * 70,
            f"{'ID':<4} {'Name':<30} {'Mem Used/Total':>16} {'Util%':>6} {'Temp°C':>7} {'Jobs':>5}",
            "-" * 70,
        ]
        for g in gpus:
            mem_str = f"{g['memory_used']}/{g['memory_total']} MiB"
            lines.append(
                f"{g['id']:<4} {g['name'][:30]:<30} {mem_str:>16} "
                f"{g['utilization']:>6} {g['temperature']:>7} {g['active_jobs']:>5}"
            )

        lines.append("-" * 70)
        with self._lock:
            total_jobs = len(self.active_jobs)
        lines.append(f"Total active jobs: {total_jobs}")
        lines.append("=" * 70)
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Load Balancing
    # ------------------------------------------------------------------

    def balance_load(self) -> dict:
        """
        Detect load imbalance and reassign jobs from overloaded GPUs to
        underloaded ones where possible.

        Returns a dict describing any reassignments made.
        """
        gpus = self._get_gpus_cached()
        if len(gpus) < 2:
            return {"reassignments": [], "message": "Nothing to balance (< 2 GPUs)."}

        with self._lock:
            jobs_by_gpu: dict = {}
            for job_id, info in self.active_jobs.items():
                gid = info["gpu_id"]
                jobs_by_gpu.setdefault(gid, []).append(job_id)

        if not jobs_by_gpu:
            return {"reassignments": [], "message": "No active jobs to balance."}

        gpu_load = {g["id"]: len(jobs_by_gpu.get(g["id"], [])) for g in gpus}
        avg_load = sum(gpu_load.values()) / len(gpu_load)
        reassignments = []

        for gpu in gpus:
            gid = gpu["id"]
            current = gpu_load.get(gid, 0)
            if current > avg_load + 1:
                excess = int(current - avg_load)
                jobs_to_move = jobs_by_gpu.get(gid, [])[:excess]
                for job_id in jobs_to_move:
                    # Find least-loaded GPU
                    target = min(
                        (g for g in gpus if g["id"] != gid),
                        key=lambda g: gpu_load.get(g["id"], 0),
                    )
                    with self._lock:
                        if job_id in self.active_jobs:
                            self.active_jobs[job_id]["gpu_id"] = target["id"]
                    gpu_load[gid] -= 1
                    gpu_load[target["id"]] = gpu_load.get(target["id"], 0) + 1
                    reassignments.append(
                        {
                            "job_id": job_id,
                            "from_gpu": gid,
                            "to_gpu": target["id"],
                        }
                    )
                    logger.info(
                        "Rebalanced job '%s' from GPU %d to GPU %d.",
                        job_id,
                        gid,
                        target["id"],
                    )

        return {"reassignments": reassignments, "message": f"{len(reassignments)} job(s) rebalanced."}

    # ------------------------------------------------------------------
    # Background Monitor
    # ------------------------------------------------------------------

    def monitor_loop(self) -> None:
        """Continuous monitoring loop — intended to run in a daemon thread."""
        self._running = True
        logger.info("GPU monitor loop started (interval=%ds).", self._monitor_interval)
        while self._running:
            try:
                stats = self.get_gpu_stats()
                for gpu in stats:
                    if gpu["utilization"] > self.config.get("util_alert_threshold", 95):
                        logger.warning(
                            "GPU %d (%s) utilization at %d%%!",
                            gpu["id"],
                            gpu["name"],
                            gpu["utilization"],
                        )
                    if gpu["temperature"] > self.config.get("temp_alert_threshold", 85):
                        logger.warning(
                            "GPU %d (%s) temperature at %d°C!",
                            gpu["id"],
                            gpu["name"],
                            gpu["temperature"],
                        )
            except Exception as exc:
                logger.error("GPU monitor error: %s", exc)
            time.sleep(self._monitor_interval)

    def start_monitor(self) -> None:
        """Start the monitor_loop in a background daemon thread."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Monitor thread already running.")
            return
        self._monitor_thread = threading.Thread(
            target=self.monitor_loop, name="gpu-monitor", daemon=True
        )
        self._monitor_thread.start()

    def stop_monitor(self) -> None:
        """Signal the monitor loop to stop."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=self._monitor_interval + 2)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    scheduler = GPUScheduler()
    print(scheduler.get_utilization_report())
