"""
Cluster Monitor for Melvin God Mode AI Infrastructure Platform.
Provides health metrics, node monitoring, model distribution, request
statistics, alerting, and report generation for the Ollama cluster.
"""

import logging
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ClusterMonitor:
    def __init__(self, cluster_manager=None):
        """
        Parameters
        ----------
        cluster_manager : OllamaClusterManager | None
            If None the monitor operates in a stub/demo mode.
        """
        self.cluster_manager = cluster_manager
        # Simple in-memory request stats accumulator
        self._request_stats: dict = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "latencies": [],  # seconds
        }
        self._alert_callbacks: list = []

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def get_cluster_health(self) -> float:
        """
        Return the fraction of healthy nodes (0.0 – 1.0).

        Returns 0.0 if there are no nodes, 1.0 if all are healthy.
        """
        if self.cluster_manager is None:
            return 0.0

        nodes = self.cluster_manager.get_nodes()
        if not nodes:
            return 0.0

        healthy = sum(1 for n in nodes if n.get("healthy", False))
        return healthy / len(nodes)

    def get_node_metrics(self) -> list:
        """
        Return a list of metric dicts — one per registered node.

        Each dict: {id, name, host, port, type, healthy, load, model_count}
        """
        if self.cluster_manager is None:
            return []

        metrics = []
        for node in self.cluster_manager.get_nodes():
            metrics.append(
                {
                    "id": node.get("id"),
                    "name": node.get("name"),
                    "host": node.get("host"),
                    "port": node.get("port"),
                    "type": node.get("type"),
                    "healthy": node.get("healthy", False),
                    "load": node.get("load", 0),
                    "model_count": len(node.get("models", [])),
                }
            )
        return metrics

    # ------------------------------------------------------------------
    # Model Distribution
    # ------------------------------------------------------------------

    def get_model_distribution(self) -> dict:
        """
        Return a mapping of model_name -> [node_ids] showing where each
        model is available across the cluster.
        """
        if self.cluster_manager is None:
            return {}

        distribution: dict = {}
        for node in self.cluster_manager.get_nodes():
            for model in node.get("models", []):
                distribution.setdefault(model, []).append(node["id"])
        return distribution

    # ------------------------------------------------------------------
    # Request Stats
    # ------------------------------------------------------------------

    def record_request(self, success: bool, latency_seconds: float) -> None:
        """
        Record a completed request for statistics tracking.
        Call this from your request handler after each inference call.
        """
        self._request_stats["total"] += 1
        if success:
            self._request_stats["success"] += 1
        else:
            self._request_stats["failed"] += 1
        self._request_stats["latencies"].append(latency_seconds)
        # Keep only the last 10 000 latencies to avoid unbounded memory growth
        if len(self._request_stats["latencies"]) > 10_000:
            self._request_stats["latencies"] = self._request_stats["latencies"][-10_000:]

    def get_request_stats(self) -> dict:
        """
        Return aggregated request statistics:
            {total, success, failed, avg_latency, p95_latency, p99_latency}
        """
        stats = dict(self._request_stats)
        latencies = stats.pop("latencies", [])
        stats["avg_latency"] = (
            round(sum(latencies) / len(latencies), 4) if latencies else 0.0
        )
        if latencies:
            sorted_lat = sorted(latencies)
            stats["p95_latency"] = round(sorted_lat[int(len(sorted_lat) * 0.95)], 4)
            stats["p99_latency"] = round(sorted_lat[int(len(sorted_lat) * 0.99)], 4)
        else:
            stats["p95_latency"] = 0.0
            stats["p99_latency"] = 0.0
        return stats

    # ------------------------------------------------------------------
    # Alerting
    # ------------------------------------------------------------------

    def register_alert_callback(self, callback) -> None:
        """
        Register a callable that will be invoked with (health: float, message: str)
        when cluster health drops below the threshold.
        """
        self._alert_callbacks.append(callback)

    def alert_if_unhealthy(self, threshold: float = 0.8) -> Optional[str]:
        """
        Check cluster health and emit an alert if it is below *threshold*.

        Returns the alert message string if an alert was triggered, else None.
        """
        health = self.get_cluster_health()
        if health < threshold:
            nodes = self.cluster_manager.get_nodes() if self.cluster_manager else []
            healthy_count = sum(1 for n in nodes if n.get("healthy", False))
            total_count = len(nodes)
            message = (
                f"[ALERT] Cluster health is {health:.0%} "
                f"({healthy_count}/{total_count} nodes healthy) — "
                f"below threshold of {threshold:.0%}."
            )
            logger.warning(message)
            for cb in self._alert_callbacks:
                try:
                    cb(health, message)
                except Exception as exc:
                    logger.error("Alert callback error: %s", exc)
            return message
        return None

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def generate_report(self) -> str:
        """Return a formatted health report string."""
        health = self.get_cluster_health()
        metrics = self.get_node_metrics()
        distribution = self.get_model_distribution()
        req_stats = self.get_request_stats()

        bar_width = 30
        filled = int(health * bar_width)
        health_bar = "█" * filled + "░" * (bar_width - filled)
        health_pct = f"{health:.0%}"

        lines = [
            "=" * 70,
            f"{'Melvin God Mode — Cluster Health Report':^70}",
            f"{'Generated: ' + datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'):^70}",
            "=" * 70,
            "",
            f"  Overall Health : [{health_bar}] {health_pct}",
            f"  Total Nodes    : {len(metrics)}",
            f"  Healthy Nodes  : {sum(1 for m in metrics if m['healthy'])}",
            f"  Unhealthy Nodes: {sum(1 for m in metrics if not m['healthy'])}",
            "",
            "  Node Metrics:",
            f"  {'Name':<24} {'Type':<8} {'Status':<9} {'Load':>4} {'Models':>6}",
            "  " + "-" * 56,
        ]

        for m in metrics:
            status = "healthy" if m["healthy"] else "DOWN"
            lines.append(
                f"  {m['name'][:23]:<24} {m['type']:<8} {status:<9} "
                f"{m['load']:>4} {m['model_count']:>6}"
            )

        lines += [
            "",
            "  Model Distribution:",
            f"  {'Model':<40} {'Replicas':>8}",
            "  " + "-" * 50,
        ]
        if distribution:
            for model, node_ids in sorted(distribution.items()):
                lines.append(f"  {model[:39]:<40} {len(node_ids):>8}")
        else:
            lines.append("  No models found.")

        lines += [
            "",
            "  Request Statistics:",
            f"  Total requests  : {req_stats['total']}",
            f"  Successful      : {req_stats['success']}",
            f"  Failed          : {req_stats['failed']}",
            f"  Avg latency     : {req_stats['avg_latency']} s",
            f"  P95 latency     : {req_stats['p95_latency']} s",
            f"  P99 latency     : {req_stats['p99_latency']} s",
            "",
            "=" * 70,
        ]
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import os

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    # Try to import the cluster manager from the cluster package
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    try:
        from cluster.ollama_cluster_manager import OllamaClusterManager  # type: ignore
    except ImportError:
        OllamaClusterManager = None  # type: ignore

    manager = OllamaClusterManager() if OllamaClusterManager else None
    monitor = ClusterMonitor(cluster_manager=manager)
    print(monitor.generate_report())
