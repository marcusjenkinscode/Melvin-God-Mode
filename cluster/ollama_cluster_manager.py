"""
Ollama Cluster Manager for Melvin God Mode AI Infrastructure Platform.
Manages a pool of Ollama nodes: health checks, model replication, and
load-balanced request routing.
"""

import logging
import time
import uuid
from typing import Optional
from datetime import datetime

try:
    import requests  # type: ignore
except ImportError:
    requests = None  # type: ignore

logger = logging.getLogger(__name__)

_OLLAMA_DEFAULT_PORT = 11434


class OllamaClusterManager:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        # {node_id: {host, port, name, type, healthy, models, load}}
        self.nodes: dict = {}
        self._timeout = self.config.get("request_timeout", 10)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _base_url(self, node: dict) -> str:
        return f"http://{node['host']}:{node['port']}"

    def _get(self, url: str, **kwargs) -> Optional[dict]:
        if requests is None:
            raise RuntimeError("'requests' library is required but not installed.")
        try:
            resp = requests.get(url, timeout=self._timeout, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.debug("GET %s failed: %s", url, exc)
            return None

    def _post(self, url: str, json_body: dict, **kwargs) -> Optional[dict]:
        if requests is None:
            raise RuntimeError("'requests' library is required but not installed.")
        try:
            resp = requests.post(
                url, json=json_body, timeout=self._timeout, **kwargs
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.debug("POST %s failed: %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # Node Management
    # ------------------------------------------------------------------

    def add_node(
        self,
        host: str,
        port: int = _OLLAMA_DEFAULT_PORT,
        name: Optional[str] = None,
        node_type: str = "worker",
    ) -> bool:
        """
        Register a new Ollama node. Performs an initial health check.

        Returns True if the node is reachable and successfully added.
        """
        node_id = str(uuid.uuid4())
        node = {
            "id": node_id,
            "host": host,
            "port": port,
            "name": name or f"{host}:{port}",
            "type": node_type,
            "healthy": False,
            "models": [],
            "load": 0,
            "added_at": datetime.utcnow().isoformat(),
        }
        healthy = self.check_node_health(node)
        node["healthy"] = healthy
        if healthy:
            node["models"] = self.list_models_on_node(node)

        self.nodes[node_id] = node
        status = "healthy" if healthy else "unreachable"
        logger.info("Added node '%s' (%s:%d) — %s.", node["name"], host, port, status)
        return healthy

    def remove_node(self, node_id: str) -> bool:
        """Remove a node by its ID. Returns True if it existed."""
        if node_id in self.nodes:
            name = self.nodes[node_id]["name"]
            del self.nodes[node_id]
            logger.info("Removed node '%s' (id=%s).", name, node_id)
            return True
        logger.warning("remove_node: unknown node_id '%s'.", node_id)
        return False

    def get_nodes(self) -> list:
        """Return a list of all node dicts."""
        return list(self.nodes.values())

    # ------------------------------------------------------------------
    # Health Checks
    # ------------------------------------------------------------------

    def check_node_health(self, node: dict) -> bool:
        """
        Perform a lightweight health check by calling GET /api/tags on the node.

        Returns True if the node responds successfully.
        """
        url = f"{self._base_url(node)}/api/tags"
        result = self._get(url)
        return result is not None

    def health_check_all(self) -> dict:
        """
        Check health of every registered node.

        Returns {node_id: bool}.
        """
        results = {}
        for node_id, node in self.nodes.items():
            healthy = self.check_node_health(node)
            self.nodes[node_id]["healthy"] = healthy
            if healthy:
                self.nodes[node_id]["models"] = self.list_models_on_node(node)
            results[node_id] = healthy
        return results

    # ------------------------------------------------------------------
    # Model Management
    # ------------------------------------------------------------------

    def list_models_on_node(self, node: dict) -> list:
        """
        Return the list of models available on *node* via GET /api/tags.
        Returns an empty list on failure.
        """
        url = f"{self._base_url(node)}/api/tags"
        data = self._get(url)
        if not data:
            return []
        return [m.get("name", "") for m in data.get("models", [])]

    def replicate_model(self, model_name: str, target_nodes: Optional[list] = None) -> dict:
        """
        Pull *model_name* on each node in *target_nodes* (defaults to all healthy nodes).

        Returns {node_id: "ok" | "failed" | "skipped"}.
        """
        if target_nodes is None:
            target_nodes = [n for n in self.nodes.values() if n["healthy"]]

        results = {}
        for node in target_nodes:
            node_id = node["id"]
            url = f"{self._base_url(node)}/api/pull"
            logger.info(
                "Replicating model '%s' to node '%s'…", model_name, node["name"]
            )
            response = self._post(url, {"name": model_name}, timeout=300)
            if response is not None:
                # Update local model cache
                if model_name not in self.nodes[node_id]["models"]:
                    self.nodes[node_id]["models"].append(model_name)
                results[node_id] = "ok"
                logger.info("Model '%s' pulled on node '%s'.", model_name, node["name"])
            else:
                results[node_id] = "failed"
                logger.warning(
                    "Failed to pull model '%s' on node '%s'.", model_name, node["name"]
                )

        return results

    # ------------------------------------------------------------------
    # Load-Balanced Routing
    # ------------------------------------------------------------------

    def route_request(self, model_name: str) -> Optional[dict]:
        """
        Return the best healthy node that has *model_name*, using least-load
        balancing.

        Returns a node dict or None if no eligible node is found.
        """
        candidates = [
            n
            for n in self.nodes.values()
            if n["healthy"] and model_name in n["models"]
        ]
        if not candidates:
            # Try any healthy node (model may be available but not cached locally)
            candidates = [n for n in self.nodes.values() if n["healthy"]]

        if not candidates:
            logger.warning(
                "No healthy nodes available to serve model '%s'.", model_name
            )
            return None

        best = min(candidates, key=lambda n: n["load"])
        self.nodes[best["id"]]["load"] += 1
        return best

    def release_request(self, node_id: str) -> None:
        """Decrement load counter for *node_id* after a request completes."""
        if node_id in self.nodes:
            self.nodes[node_id]["load"] = max(0, self.nodes[node_id]["load"] - 1)

    # ------------------------------------------------------------------
    # Cluster Status
    # ------------------------------------------------------------------

    def get_cluster_status(self) -> dict:
        """
        Return a comprehensive cluster status dictionary.
        """
        nodes = list(self.nodes.values())
        healthy_count = sum(1 for n in nodes if n["healthy"])
        all_models: set = set()
        for n in nodes:
            all_models.update(n["models"])

        total_load = sum(n["load"] for n in nodes)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_nodes": len(nodes),
            "healthy_nodes": healthy_count,
            "unhealthy_nodes": len(nodes) - healthy_count,
            "total_load": total_load,
            "available_models": sorted(all_models),
            "nodes": nodes,
        }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    manager = OllamaClusterManager()
    print(json.dumps(manager.get_cluster_status(), indent=2))
