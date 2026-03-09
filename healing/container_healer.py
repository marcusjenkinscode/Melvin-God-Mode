"""
Container self-healing engine for Melvin God Mode.
"""

import time
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import docker
    from docker.errors import DockerException, NotFound, APIError
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    logger.warning("docker-py not installed; container healing disabled")

try:
    import requests as _requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

DEFAULT_CONFIG = {
    "docker_base_url": None,          # None → use environment / default socket
    "heal_interval": 60,              # seconds between monitor sweeps
    "max_retries": 3,
    "restart_delay": 5,               # seconds between restart attempts
    "alert_webhook": None,            # Slack / Teams / generic webhook URL
    "max_healing_history": 1000,
    "excluded_containers": [],        # names/IDs to skip
    "restart_policy_check": True,     # skip containers managed by orchestrator
}


class ContainerHealer:
    """Monitors Docker containers and automatically heals unhealthy ones."""

    def __init__(self, config: Optional[dict] = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.healing_log: list[dict] = []
        self._client: Optional["docker.DockerClient"] = None  # lazy

    # ------------------------------------------------------------------
    # Docker client
    # ------------------------------------------------------------------

    def get_docker_client(self) -> "docker.DockerClient":
        if not DOCKER_AVAILABLE:
            raise RuntimeError("docker-py library not installed")
        if self._client is None:
            base_url = self.config.get("docker_base_url")
            try:
                self._client = (
                    docker.DockerClient(base_url=base_url)
                    if base_url
                    else docker.from_env()
                )
                self._client.ping()
                logger.info("Docker client connected")
            except DockerException as exc:
                raise RuntimeError(f"Cannot connect to Docker daemon: {exc}") from exc
        return self._client

    # ------------------------------------------------------------------
    # Container introspection
    # ------------------------------------------------------------------

    def list_containers(self, all_containers: bool = False) -> list[dict]:
        """Return a list of container summary dicts."""
        client = self.get_docker_client()
        containers = []
        for c in client.containers.list(all=all_containers):
            containers.append({
                "id": c.id,
                "short_id": c.short_id,
                "name": c.name,
                "status": c.status,
                "image": c.image.tags[0] if c.image.tags else c.image.id[:12],
                "labels": c.labels,
            })
        return containers

    def check_container_health(self, container_id: str) -> dict:
        """Return health information for a single container."""
        client = self.get_docker_client()
        try:
            c = client.containers.get(container_id)
            c.reload()
            attrs = c.attrs

            health_status = "unknown"
            health_info = attrs.get("State", {}).get("Health", {})
            if health_info:
                health_status = health_info.get("Status", "unknown")

            exit_code = attrs.get("State", {}).get("ExitCode", 0)
            running = attrs.get("State", {}).get("Running", False)

            healthy = (
                running and health_status in ("healthy", "unknown")
                and exit_code == 0
            )

            return {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "running": running,
                "health_status": health_status,
                "exit_code": exit_code,
                "healthy": healthy,
            }
        except NotFound:
            return {"id": container_id, "healthy": False, "status": "not_found",
                    "exit_code": -1, "health_status": "not_found"}
        except APIError as exc:
            logger.error("Docker API error checking %s: %s", container_id, exc)
            return {"id": container_id, "healthy": False, "status": "error",
                    "exit_code": -1, "health_status": "api_error"}

    # ------------------------------------------------------------------
    # Healing actions
    # ------------------------------------------------------------------

    def restart_container(self, container_id: str) -> bool:
        """Attempt a single restart of the named container."""
        client = self.get_docker_client()
        try:
            c = client.containers.get(container_id)
            logger.info("Restarting container %s (%s)", c.name, c.short_id)
            c.restart(timeout=30)
            time.sleep(self.config["restart_delay"])
            c.reload()
            return c.status == "running"
        except NotFound:
            logger.error("Container %s not found for restart", container_id)
            return False
        except APIError as exc:
            logger.error("Restart failed for %s: %s", container_id, exc)
            return False

    def heal_container(self, container_id: str, max_retries: Optional[int] = None) -> bool:
        """Try up to *max_retries* times to bring a container back healthy."""
        retries = max_retries if max_retries is not None else self.config["max_retries"]

        for attempt in range(1, retries + 1):
            logger.info(
                "Heal attempt %d/%d for container %s", attempt, retries, container_id
            )
            success = self.restart_container(container_id)
            if success:
                health = self.check_container_health(container_id)
                if health["healthy"] or health["running"]:
                    msg = f"Container {container_id} healed after {attempt} attempt(s)"
                    logger.info(msg)
                    self.log_failure(container_id, f"Recovered after {attempt} attempt(s)")
                    self.send_alert(f"✅ {msg}")
                    return True
            time.sleep(self.config["restart_delay"] * attempt)

        msg = f"Container {container_id} could not be healed after {retries} attempts"
        logger.error(msg)
        self.log_failure(container_id, "Healing failed after max retries")
        self.send_alert(f"🚨 {msg}")
        return False

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    def get_failed_containers(self) -> list[dict]:
        """Return containers that exited with a non-zero exit code."""
        client = self.get_docker_client()
        failed = []
        excluded = set(self.config.get("excluded_containers", []))
        for c in client.containers.list(all=True, filters={"status": "exited"}):
            if c.name in excluded or c.id in excluded:
                continue
            c.reload()
            exit_code = c.attrs.get("State", {}).get("ExitCode", 0)
            if exit_code != 0:
                failed.append({
                    "id": c.id,
                    "short_id": c.short_id,
                    "name": c.name,
                    "exit_code": exit_code,
                    "status": c.status,
                })
        return failed

    def monitor_all(self) -> dict:
        """Inspect every running container; heal any that are unhealthy."""
        results = {"checked": 0, "healthy": 0, "healed": 0, "failed": 0}
        excluded = set(self.config.get("excluded_containers", []))

        try:
            containers = self.list_containers(all_containers=True)
        except RuntimeError as exc:
            logger.error("Cannot list containers: %s", exc)
            return results

        for info in containers:
            cid = info["id"]
            if info["name"] in excluded or cid in excluded:
                continue
            # Skip permanently stopped containers with exit code 0
            if info["status"] == "exited":
                health = self.check_container_health(cid)
                if health["exit_code"] == 0:
                    continue

            results["checked"] += 1
            health = self.check_container_health(cid)

            if health["healthy"] or health["status"] == "running":
                results["healthy"] += 1
            else:
                logger.warning(
                    "Unhealthy container detected: %s (status=%s, exit=%s)",
                    info["name"], health["status"], health["exit_code"],
                )
                if self.heal_container(cid):
                    results["healed"] += 1
                else:
                    results["failed"] += 1

        # Also heal crashed (exited non-zero) containers
        for fc in self.get_failed_containers():
            if fc["id"] not in {c["id"] for c in containers}:
                continue
            results["checked"] += 1
            if self.heal_container(fc["id"]):
                results["healed"] += 1
            else:
                results["failed"] += 1

        logger.info(
            "Monitor sweep complete — checked=%d healthy=%d healed=%d failed=%d",
            results["checked"], results["healthy"], results["healed"], results["failed"],
        )
        return results

    # ------------------------------------------------------------------
    # Logging & alerting
    # ------------------------------------------------------------------

    def log_failure(self, container_id: str, reason: str) -> None:
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "container_id": container_id,
            "reason": reason,
        }
        self.healing_log.append(entry)
        # Trim history to avoid unbounded growth
        max_len = self.config["max_healing_history"]
        if len(self.healing_log) > max_len:
            self.healing_log = self.healing_log[-max_len:]
        logger.debug("Logged failure: %s", entry)

    def send_alert(self, message: str) -> None:
        webhook = self.config.get("alert_webhook")
        if not webhook or not REQUESTS_AVAILABLE:
            return
        try:
            _requests.post(webhook, json={"text": message}, timeout=10)
        except Exception as exc:
            logger.error("Alert webhook error: %s", exc)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_healing_report(self) -> dict:
        """Summarise all healing actions recorded in this session."""
        total = len(self.healing_log)
        recovered = sum(
            1 for e in self.healing_log if "Recovered" in e.get("reason", "")
        )
        failed = sum(
            1 for e in self.healing_log if "failed" in e.get("reason", "").lower()
        )
        return {
            "total_events": total,
            "recovered": recovered,
            "permanently_failed": failed,
            "history": list(self.healing_log),
        }

    # ------------------------------------------------------------------
    # Continuous loop
    # ------------------------------------------------------------------

    def run_healing_loop(self, interval: Optional[int] = None) -> None:
        """Blocking loop that calls monitor_all() every *interval* seconds."""
        interval = interval if interval is not None else self.config["heal_interval"]
        logger.info("Container healing loop started (interval=%ds)", interval)

        while True:
            try:
                self.monitor_all()
            except Exception as exc:
                logger.error("Healing loop error: %s", exc)
            time.sleep(interval)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    healer = ContainerHealer()
    healer.run_healing_loop()
