"""
DevOpsAgent – DevOps automation: shell commands, Docker services, resource monitoring.
"""

import shlex
import subprocess
import time
from typing import Any, Dict, List, Optional

import psutil

from agents.agent_base import AgentBase

DEFAULT_MODEL = "llama3"

# Commands that are explicitly forbidden for safety
FORBIDDEN_PREFIXES = (
    "rm -rf /",
    "mkfs",
    "dd if=/dev/zero",
    ":(){:|:&};:",  # fork bomb
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
)


def _is_safe_command(cmd: str) -> bool:
    cmd_stripped = cmd.strip()
    for prefix in FORBIDDEN_PREFIXES:
        if cmd_stripped.startswith(prefix):
            return False
    return True


class DevOpsAgent(AgentBase):
    """Agent that automates DevOps tasks: shell, Docker, monitoring."""

    def __init__(
        self,
        name: str = "DevOpsAgent",
        model: str = DEFAULT_MODEL,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(name, model, config)
        self.command_timeout: int = self.config.get("command_timeout", 60)

    # ------------------------------------------------------------------
    # AgentBase abstract methods
    # ------------------------------------------------------------------

    def run(self, task: str) -> Dict[str, Any]:
        self.set_status(self.STATUS_RUNNING)
        start = time.time()
        self.log(f"DevOps task: {task}")

        try:
            # Ask the LLM what shell command(s) to run for this task
            plan_prompt = (
                "You are a DevOps engineer.\n"
                "For the following task, list the exact shell command(s) to run, "
                "one per line. Return only the commands, no explanation.\n\n"
                f"Task: {task}"
            )
            commands_text = self.call_ollama(plan_prompt)
            commands = [
                line.strip()
                for line in commands_text.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]

            outputs = []
            for cmd in commands[:5]:  # cap at 5 commands per task
                output = self.run_command(cmd)
                outputs.append(output)

            result = {"task": task, "commands": commands, "outputs": outputs}
            self.observe(result)
            self.set_status(self.STATUS_IDLE)
        except Exception as exc:  # noqa: BLE001
            self.log(f"DevOps task failed: {exc}", "error")
            self.set_status(self.STATUS_ERROR)
            result = {"task": task, "error": str(exc)}

        self._record_task(task, result, time.time() - start)
        return result

    def think(self, prompt: str) -> str:
        return self.call_ollama(prompt)

    def act(self, action: Dict[str, Any]) -> Any:
        action_type = action.get("type")
        if action_type == "run_command":
            return self.run_command(action["cmd"])
        if action_type == "deploy":
            return self.deploy_service(action["service_name"])
        if action_type == "health_check":
            return self.check_service_health(action["service"])
        if action_type == "restart":
            return self.restart_service(action["service"])
        if action_type == "logs":
            return self.get_logs(action["service"])
        if action_type == "monitor":
            return self.monitor_resources()
        self.log(f"Unknown action type: {action_type}", "warning")
        return None

    def observe(self, result: Any) -> None:
        if isinstance(result, dict):
            self.store_memory("last_devops_result", result, tags=["devops"])

    # ------------------------------------------------------------------
    # Core capabilities
    # ------------------------------------------------------------------

    def run_command(self, cmd: str) -> Dict[str, Any]:
        """
        Run a shell command safely (shell=False always) and return stdout/stderr/returncode.

        Commands are split via shlex to avoid shell injection.  Dangerous
        commands are blocked by the _is_safe_command() guard.
        """
        if not _is_safe_command(cmd):
            self.log(f"Refusing to run forbidden command: {cmd}", "error")
            return {"cmd": cmd, "returncode": -1, "stdout": "", "stderr": "Command blocked for safety."}

        self.log(f"Running command: {cmd}")
        try:
            args = shlex.split(cmd)
            proc = subprocess.run(  # noqa: S603
                args,
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
                shell=False,
            )
            result = {
                "cmd": cmd,
                "returncode": proc.returncode,
                "stdout": proc.stdout[:4096],
                "stderr": proc.stderr[:2048],
            }
        except subprocess.TimeoutExpired:
            result = {"cmd": cmd, "returncode": -1, "stdout": "", "stderr": "Command timed out."}
        except FileNotFoundError as exc:
            result = {"cmd": cmd, "returncode": -1, "stdout": "", "stderr": str(exc)}
        except Exception as exc:  # noqa: BLE001
            result = {"cmd": cmd, "returncode": -1, "stdout": "", "stderr": str(exc)}

        self.store_memory("command_history", result, tags=["command"])
        return result

    def deploy_service(self, service_name: str) -> Dict[str, Any]:
        """Start / deploy a Docker Compose service."""
        self.log(f"Deploying service: {service_name}")
        result = self.run_command(f"docker compose up -d {service_name}")
        result["service"] = service_name
        return result

    def check_service_health(self, service: str) -> Dict[str, Any]:
        """Check if a Docker service container is running."""
        self.log(f"Checking health of service: {service}")
        result = self.run_command(
            f'docker inspect --format="{{{{.State.Status}}}}" {service}'
        )
        status = result.get("stdout", "").strip().strip('"')
        health = {
            "service": service,
            "status": status if status else "not found",
            "healthy": status == "running",
            "raw": result,
        }
        return health

    def restart_service(self, service: str) -> Dict[str, Any]:
        """Restart a Docker Compose service."""
        self.log(f"Restarting service: {service}")
        result = self.run_command(f"docker compose restart {service}")
        result["service"] = service
        return result

    def get_logs(self, service: str, tail: int = 100) -> Dict[str, Any]:
        """Fetch the last *tail* lines of logs for a Docker service."""
        self.log(f"Fetching logs for service: {service} (tail={tail})")
        result = self.run_command(f"docker logs --tail={tail} {service}")
        result["service"] = service
        return result

    def monitor_resources(self) -> Dict[str, Any]:
        """Return current CPU, memory, disk, and network stats via psutil."""
        self.log("Monitoring system resources…")
        try:
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()

            stats: Dict[str, Any] = {
                "cpu_percent": cpu,
                "memory": {
                    "total_gb": round(mem.total / 1e9, 2),
                    "used_gb": round(mem.used / 1e9, 2),
                    "percent": mem.percent,
                },
                "disk": {
                    "total_gb": round(disk.total / 1e9, 2),
                    "used_gb": round(disk.used / 1e9, 2),
                    "percent": disk.percent,
                },
                "network": {
                    "bytes_sent": net.bytes_sent,
                    "bytes_recv": net.bytes_recv,
                },
            }
        except Exception as exc:  # noqa: BLE001
            self.log(f"Resource monitoring failed: {exc}", "error")
            stats = {"error": str(exc)}

        self.store_memory("resource_stats", stats, tags=["monitoring"])
        return stats

    def list_running_containers(self) -> List[Dict[str, str]]:
        """Return a list of currently running Docker containers."""
        result = self.run_command("docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}'")
        containers = []
        for line in result.get("stdout", "").splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                containers.append({"name": parts[0], "status": parts[1], "image": parts[2]})
        return containers

    def execute_playbook(self, steps: List[str]) -> List[Dict[str, Any]]:
        """Execute an ordered list of shell commands and collect results."""
        results = []
        for step in steps:
            self.log(f"Playbook step: {step}")
            result = self.run_command(step)
            results.append(result)
            if result["returncode"] != 0:
                self.log(f"Playbook step failed: {step}", "error")
                break
        return results
