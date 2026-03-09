"""
Cluster Status for Melvin God Mode AI Infrastructure Platform.
Aggregates status from OllamaClusterManager and GPUScheduler and presents
it in human-readable and machine-readable formats.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from rich.console import Console  # type: ignore
    from rich.table import Table  # type: ignore
    from rich import box  # type: ignore

    _RICH = True
except ImportError:
    _RICH = False


class ClusterStatus:
    def __init__(self, cluster_manager=None, gpu_scheduler=None):
        """
        Parameters
        ----------
        cluster_manager : OllamaClusterManager | None
        gpu_scheduler   : GPUScheduler | None
        """
        self.cluster_manager = cluster_manager
        self.gpu_scheduler = gpu_scheduler

    # ------------------------------------------------------------------
    # Core Data Gathering
    # ------------------------------------------------------------------

    def get_full_status(self) -> dict:
        """Return a comprehensive status dict combining cluster and GPU info."""
        status: dict = {
            "timestamp": datetime.utcnow().isoformat(),
            "cluster": {},
            "gpus": [],
            "active_jobs": {},
        }

        if self.cluster_manager is not None:
            try:
                status["cluster"] = self.cluster_manager.get_cluster_status()
            except Exception as exc:
                logger.error("Failed to get cluster status: %s", exc)
                status["cluster"] = {"error": str(exc)}

        if self.gpu_scheduler is not None:
            try:
                status["gpus"] = self.gpu_scheduler.get_gpu_stats()
            except Exception as exc:
                logger.error("Failed to get GPU stats: %s", exc)
                status["gpus"] = []

            try:
                with self.gpu_scheduler._lock:
                    status["active_jobs"] = dict(self.gpu_scheduler.active_jobs)
            except Exception as exc:
                logger.error("Failed to get active jobs: %s", exc)

        return status

    # ------------------------------------------------------------------
    # Formatted Summaries
    # ------------------------------------------------------------------

    def get_nodes_summary(self) -> str:
        """Return a formatted table string of all cluster nodes."""
        if self.cluster_manager is None:
            return "No cluster manager configured.\n"

        nodes = self.cluster_manager.get_nodes()
        if not nodes:
            return "No nodes registered.\n"

        col_widths = [24, 8, 8, 10, 7, 30]
        header = (
            f"{'Name':<{col_widths[0]}} {'Host':<{col_widths[1]}} "
            f"{'Port':<{col_widths[2]}} {'Type':<{col_widths[3]}} "
            f"{'Status':<{col_widths[4]}} {'Models':<{col_widths[5]}}"
        )
        sep = "-" * sum(col_widths)
        rows = [
            "=" * sum(col_widths),
            f"{'Cluster Nodes':^{sum(col_widths)}}",
            "=" * sum(col_widths),
            header,
            sep,
        ]
        for n in nodes:
            health = "healthy" if n["healthy"] else "DOWN"
            models_str = ", ".join(n.get("models", []))[:28] or "—"
            rows.append(
                f"{n['name'][:23]:<{col_widths[0]}} {n['host'][:7]:<{col_widths[1]}} "
                f"{n['port']:<{col_widths[2]}} {n['type']:<{col_widths[3]}} "
                f"{health:<{col_widths[4]}} {models_str}"
            )
        rows.append(sep)
        rows.append(f"Total nodes: {len(nodes)}")
        rows.append("=" * sum(col_widths))
        return "\n".join(rows) + "\n"

    def get_gpu_summary(self) -> str:
        """Return a formatted GPU status table."""
        if self.gpu_scheduler is None:
            return "No GPU scheduler configured.\n"

        gpus = self.gpu_scheduler.get_gpu_stats()
        if not gpus:
            return "No GPUs detected.\n"

        header = (
            f"{'ID':<4} {'Name':<30} {'Mem Free/Total':>16} {'Util%':>6} "
            f"{'Temp°C':>7} {'Jobs':>5}"
        )
        sep = "-" * 72
        rows = [
            "=" * 72,
            f"{'GPU Summary':^72}",
            "=" * 72,
            header,
            sep,
        ]
        for g in gpus:
            mem_str = f"{g['memory_free']}/{g['memory_total']} MiB"
            rows.append(
                f"{g['id']:<4} {g['name'][:30]:<30} {mem_str:>16} "
                f"{g['utilization']:>6} {g['temperature']:>7} "
                f"{g.get('active_jobs', 0):>5}"
            )
        rows.append(sep)
        rows.append("=" * 72)
        return "\n".join(rows) + "\n"

    def get_job_queue(self) -> list:
        """Return a list of currently queued (active) jobs."""
        if self.gpu_scheduler is None:
            return []
        with self.gpu_scheduler._lock:
            return [
                {"job_id": jid, **info}
                for jid, info in self.gpu_scheduler.active_jobs.items()
            ]

    # ------------------------------------------------------------------
    # Export & Print
    # ------------------------------------------------------------------

    def export_status_json(self, filepath: str) -> None:
        """Save the full status to *filepath* as pretty-printed JSON."""
        status = self.get_full_status()
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(status, fh, indent=2, default=str)
        logger.info("Status exported to '%s'.", filepath)

    def print_status(self) -> None:
        """Print a formatted cluster + GPU status to stdout."""
        if _RICH:
            self._print_rich()
        else:
            self._print_plain()

    def _print_plain(self) -> None:
        status = self.get_full_status()
        print(f"\n{'='*72}")
        print(f"  Melvin God Mode — Cluster Status")
        print(f"  {status['timestamp']}")
        print(f"{'='*72}\n")
        print(self.get_nodes_summary())
        print(self.get_gpu_summary())
        jobs = self.get_job_queue()
        print(f"Active jobs: {len(jobs)}")
        for j in jobs:
            print(f"  [{j['job_id']}] model={j['model']} gpu={j['gpu_id']} started={j['started']}")
        print()

    def _print_rich(self) -> None:
        console = Console()
        status = self.get_full_status()
        console.rule("[bold blue]Melvin God Mode — Cluster Status")
        console.print(f"[dim]{status['timestamp']}[/dim]\n")

        # Nodes table
        cluster = status.get("cluster", {})
        nodes = cluster.get("nodes", [])
        if nodes:
            node_table = Table(title="Cluster Nodes", box=box.ROUNDED)
            node_table.add_column("Name", style="cyan")
            node_table.add_column("Host")
            node_table.add_column("Port")
            node_table.add_column("Type")
            node_table.add_column("Status")
            node_table.add_column("Load")
            node_table.add_column("Models")
            for n in nodes:
                health_str = "[green]healthy[/green]" if n["healthy"] else "[red]DOWN[/red]"
                models_str = ", ".join(n.get("models", []))[:40] or "—"
                node_table.add_row(
                    n["name"], n["host"], str(n["port"]),
                    n["type"], health_str, str(n["load"]), models_str,
                )
            console.print(node_table)

        # GPU table
        gpus = status.get("gpus", [])
        if gpus:
            gpu_table = Table(title="GPUs", box=box.ROUNDED)
            gpu_table.add_column("ID")
            gpu_table.add_column("Name", style="cyan")
            gpu_table.add_column("Mem Free/Total")
            gpu_table.add_column("Util%")
            gpu_table.add_column("Temp°C")
            gpu_table.add_column("Jobs")
            for g in gpus:
                mem_str = f"{g['memory_free']}/{g['memory_total']} MiB"
                util = g["utilization"]
                util_color = "green" if util < 70 else ("yellow" if util < 90 else "red")
                gpu_table.add_row(
                    str(g["id"]), g["name"], mem_str,
                    f"[{util_color}]{util}[/{util_color}]",
                    str(g["temperature"]),
                    str(g.get("active_jobs", 0)),
                )
            console.print(gpu_table)

        # Jobs
        jobs = self.get_job_queue()
        console.print(f"\n[bold]Active jobs:[/bold] {len(jobs)}")
        for j in jobs:
            console.print(
                f"  [yellow]{j['job_id']}[/yellow]  model={j['model']}  "
                f"gpu={j['gpu_id']}  started={j['started']}"
            )
        console.print()


# ---------------------------------------------------------------------------
# Standalone Script Entry-Point
# ---------------------------------------------------------------------------

def main():
    import argparse

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Print Melvin cluster status.")
    parser.add_argument("--json", metavar="FILE", help="Export status to JSON file.")
    args = parser.parse_args()

    # Import lazily to avoid circular deps when used as a library
    try:
        from cluster.gpu_scheduler import GPUScheduler  # type: ignore
        from cluster.ollama_cluster_manager import OllamaClusterManager  # type: ignore
    except ImportError:
        from gpu_scheduler import GPUScheduler  # type: ignore
        from ollama_cluster_manager import OllamaClusterManager  # type: ignore

    manager = OllamaClusterManager()
    scheduler = GPUScheduler()
    cs = ClusterStatus(cluster_manager=manager, gpu_scheduler=scheduler)

    if args.json:
        cs.export_status_json(args.json)
        print(f"Status saved to {args.json}")
    else:
        cs.print_status()


if __name__ == "__main__":
    main()
