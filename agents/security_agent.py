"""
SecurityAgent – security auditing, port scanning, SSL checks, and vulnerability assessment.
"""

import json
import shlex
import socket
import ssl
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from agents.agent_base import AgentBase

DEFAULT_MODEL = "llama3"

# Common service ports for quick checks when nmap is unavailable
COMMON_PORTS: List[Tuple[int, str]] = [
    (21, "FTP"),
    (22, "SSH"),
    (23, "Telnet"),
    (25, "SMTP"),
    (53, "DNS"),
    (80, "HTTP"),
    (110, "POP3"),
    (143, "IMAP"),
    (443, "HTTPS"),
    (445, "SMB"),
    (3306, "MySQL"),
    (5432, "PostgreSQL"),
    (6379, "Redis"),
    (8080, "HTTP-alt"),
    (27017, "MongoDB"),
]

RISKY_CONFIG_KEYS = [
    "password",
    "secret",
    "private_key",
    "api_key",
    "token",
    "credential",
    "passwd",
]


class SecurityAgent(AgentBase):
    """Agent that performs security auditing, scanning, and reporting."""

    def __init__(
        self,
        name: str = "SecurityAgent",
        model: str = DEFAULT_MODEL,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(name, model, config)
        self.scan_timeout: float = self.config.get("scan_timeout", 2.0)

    # ------------------------------------------------------------------
    # AgentBase abstract methods
    # ------------------------------------------------------------------

    def run(self, task: str) -> Dict[str, Any]:
        self.set_status(self.STATUS_RUNNING)
        start = time.time()
        self.log(f"Security task: {task}")

        try:
            report = self.generate_security_report(task)
            result = {"task": task, "report": report, "model": self.model}
            self.observe(result)
            self.set_status(self.STATUS_IDLE)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Security task failed: {exc}", "error")
            self.set_status(self.STATUS_ERROR)
            result = {"task": task, "error": str(exc)}

        self._record_task(task, result, time.time() - start)
        return result

    def think(self, prompt: str) -> str:
        return self.call_ollama(prompt)

    def act(self, action: Dict[str, Any]) -> Any:
        action_type = action.get("type")
        if action_type == "scan_ports":
            return self.scan_ports(action["host"], action.get("ports"))
        if action_type == "check_vulnerabilities":
            return self.check_vulnerabilities(action["target"])
        if action_type == "audit_config":
            return self.audit_config(action["config_file"])
        if action_type == "security_report":
            return self.generate_security_report(action["target"])
        if action_type == "check_ssl":
            return self.check_ssl(action["host"])
        self.log(f"Unknown action type: {action_type}", "warning")
        return None

    def observe(self, result: Any) -> None:
        if isinstance(result, dict):
            self.store_memory("last_security_result", result, tags=["security"])

    # ------------------------------------------------------------------
    # Core capabilities
    # ------------------------------------------------------------------

    def scan_ports(
        self,
        host: str,
        ports: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Scan *ports* on *host*.  Uses nmap when available; falls back to
        a pure-Python socket scan.
        """
        self.log(f"Scanning ports on {host}…")
        target_ports = ports or [p for p, _ in COMMON_PORTS]

        # Try nmap first
        nmap_result = self._try_nmap(host, target_ports)
        if nmap_result is not None:
            return nmap_result

        # Fallback: socket-based scan
        open_ports: List[Dict[str, Any]] = []
        closed_ports: List[int] = []

        for port in target_ports:
            try:
                with socket.create_connection((host, port), timeout=self.scan_timeout):
                    service = next((s for p, s in COMMON_PORTS if p == port), "unknown")
                    open_ports.append({"port": port, "service": service, "state": "open"})
            except (OSError, socket.timeout):
                closed_ports.append(port)

        result = {
            "host": host,
            "open_ports": open_ports,
            "closed_count": len(closed_ports),
            "scanner": "socket",
        }
        self.store_memory(f"scan:{host}", result, tags=["scan"])
        return result

    def _try_nmap(self, host: str, ports: List[int]) -> Optional[Dict[str, Any]]:
        """Attempt an nmap scan; return None if nmap is not installed."""
        port_str = ",".join(map(str, ports))
        try:
            proc = subprocess.run(
                shlex.split(f"nmap -p {port_str} --open -oG - {host}"),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                return None
            open_ports = []
            for line in proc.stdout.splitlines():
                if "Ports:" in line:
                    for chunk in line.split("Ports:")[1].split(","):
                        parts = chunk.strip().split("/")
                        if len(parts) >= 2 and parts[1] == "open":
                            service = parts[4] if len(parts) > 4 else "unknown"
                            open_ports.append(
                                {"port": int(parts[0]), "service": service, "state": "open"}
                            )
            return {"host": host, "open_ports": open_ports, "scanner": "nmap"}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def check_vulnerabilities(self, target: str) -> Dict[str, Any]:
        """
        Perform a basic vulnerability assessment of *target*.

        Combines port scan results with LLM-driven analysis.
        """
        self.log(f"Checking vulnerabilities for: {target}")
        port_data = self.scan_ports(target)

        open_ports_summary = ", ".join(
            f"{p['port']}/{p.get('service','?')}" for p in port_data.get("open_ports", [])
        )
        prompt = (
            "You are a security analyst.\n"
            f"Target: {target}\n"
            f"Open ports: {open_ports_summary or 'none detected'}\n\n"
            "List potential vulnerabilities and attack vectors associated with these "
            "open ports and services.  Rate each as: Critical / High / Medium / Low.\n"
            "Return as JSON: [{\"vulnerability\": str, \"severity\": str, \"recommendation\": str}]"
        )
        response = self.call_ollama(prompt)

        vulnerabilities: List[Dict[str, Any]] = []
        try:
            start = response.find("[")
            end = response.rfind("]") + 1
            if start != -1:
                vulnerabilities = json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            vulnerabilities = [{"vulnerability": response[:500], "severity": "unknown", "recommendation": "Review manually"}]

        result = {
            "target": target,
            "port_scan": port_data,
            "vulnerabilities": vulnerabilities,
            "vulnerability_count": len(vulnerabilities),
        }
        self.store_memory(f"vuln:{target}", result, tags=["vulnerability"])
        return result

    def audit_config(self, config_file: str) -> Dict[str, Any]:
        """
        Audit a configuration file for security issues (e.g. hardcoded secrets).
        """
        self.log(f"Auditing config file: {config_file}")
        try:
            with open(config_file, encoding="utf-8") as fh:
                content = fh.read()
        except OSError as exc:
            return {"config_file": config_file, "error": str(exc)}

        issues: List[Dict[str, str]] = []

        # Static checks for risky keys
        for line_no, line in enumerate(content.splitlines(), start=1):
            line_lower = line.lower()
            for risky_key in RISKY_CONFIG_KEYS:
                if risky_key in line_lower and "=" in line:
                    # Check that there is an actual value (not empty)
                    value_part = line.split("=", 1)[-1].strip().strip("\"'")
                    if value_part and value_part not in ("", "null", "none", "''", '""'):
                        issues.append(
                            {
                                "line": line_no,
                                "type": "potential_secret",
                                "detail": f"Key containing '{risky_key}' may expose a secret.",
                                "severity": "high",
                            }
                        )

        # LLM-assisted review
        prompt = (
            "You are a security auditor.\n"
            "Review the following configuration for security issues such as "
            "hardcoded credentials, insecure settings, and misconfigurations.\n"
            "Be concise.\n\n"
            f"{content[:3000]}"
        )
        llm_review = self.call_ollama(prompt)

        result = {
            "config_file": config_file,
            "static_issues": issues,
            "llm_review": llm_review,
            "total_issues": len(issues),
        }
        self.store_memory(f"audit:{config_file}", result, tags=["audit"])
        return result

    def generate_security_report(self, target: str) -> Dict[str, Any]:
        """
        Compile a comprehensive security report for *target*.
        """
        self.log(f"Generating security report for: {target}")
        vuln_data = self.check_vulnerabilities(target)
        ssl_data = self.check_ssl(target) if not target.startswith("/") else {}

        prompt = (
            "You are a senior security engineer.\n"
            f"Write an executive-level security report for target: {target}\n"
            f"Vulnerability findings: {json.dumps(vuln_data.get('vulnerabilities', [])[:5])}\n"
            "Include: Executive Summary, Risk Rating (Critical/High/Medium/Low), "
            "Detailed Findings, Recommendations, and Remediation Timeline."
        )
        narrative = self.call_ollama(prompt)

        report = {
            "target": target,
            "vulnerability_assessment": vuln_data,
            "ssl_assessment": ssl_data,
            "narrative": narrative,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.store_memory(f"report:{target}", report, tags=["report"])
        return report

    def check_ssl(self, host: str, port: int = 443) -> Dict[str, Any]:
        """
        Check the SSL/TLS configuration for *host*:*port*.
        """
        self.log(f"Checking SSL for {host}:{port}…")
        result: Dict[str, Any] = {"host": host, "port": port}
        try:
            ctx = ssl.create_default_context()
            # Enforce a minimum of TLS 1.2 to prevent use of deprecated protocols
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            with socket.create_connection((host, port), timeout=self.scan_timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    result["protocol"] = ssock.version()
                    result["cipher"] = ssock.cipher()
                    result["subject"] = dict(x[0] for x in cert.get("subject", []))
                    result["issuer"] = dict(x[0] for x in cert.get("issuer", []))
                    result["expires"] = cert.get("notAfter", "unknown")
                    result["valid"] = True
        except ssl.SSLCertVerificationError as exc:
            result["valid"] = False
            result["error"] = f"Certificate verification failed: {exc}"
        except (OSError, socket.timeout) as exc:
            result["valid"] = False
            result["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001
            result["valid"] = False
            result["error"] = str(exc)

        self.store_memory(f"ssl:{host}", result, tags=["ssl"])
        return result
