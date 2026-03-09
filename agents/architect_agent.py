"""
ArchitectAgent – system architecture design, review, and resource estimation.
"""

import json
import time
from typing import Any, Dict, List, Optional

from agents.agent_base import AgentBase

DEFAULT_MODEL = "llama3"


class ArchitectAgent(AgentBase):
    """Agent that designs, reviews, and improves system architectures."""

    def __init__(
        self,
        name: str = "ArchitectAgent",
        model: str = DEFAULT_MODEL,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(name, model, config)

    # ------------------------------------------------------------------
    # AgentBase abstract methods
    # ------------------------------------------------------------------

    def run(self, task: str) -> Dict[str, Any]:
        self.set_status(self.STATUS_RUNNING)
        start = time.time()
        self.log(f"Architecture task: {task}")

        try:
            design = self.design_system(task)
            result = {"task": task, "design": design, "model": self.model}
            self.observe(result)
            self.set_status(self.STATUS_IDLE)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Architecture task failed: {exc}", "error")
            self.set_status(self.STATUS_ERROR)
            result = {"task": task, "error": str(exc)}

        self._record_task(task, result, time.time() - start)
        return result

    def think(self, prompt: str) -> str:
        return self.call_ollama(prompt)

    def act(self, action: Dict[str, Any]) -> Any:
        action_type = action.get("type")
        if action_type == "design_system":
            return self.design_system(action["requirements"])
        if action_type == "review_architecture":
            return self.review_architecture(action["design"])
        if action_type == "suggest_improvements":
            return self.suggest_improvements(action["system"])
        if action_type == "create_diagram":
            return self.create_diagram(action["components"])
        if action_type == "estimate_resources":
            return self.estimate_resources(action["design"])
        self.log(f"Unknown action type: {action_type}", "warning")
        return None

    def observe(self, result: Any) -> None:
        if isinstance(result, dict):
            self.store_memory("last_design", result, tags=["architecture"])

    # ------------------------------------------------------------------
    # Core capabilities
    # ------------------------------------------------------------------

    def design_system(self, requirements: str) -> Dict[str, Any]:
        """
        Create a comprehensive system design from *requirements*.

        Returns a dict with keys: overview, components, data_flow,
        technology_stack, scalability, security_considerations.
        """
        self.log(f"Designing system for: {requirements[:80]}…")
        prompt = (
            "You are a principal software architect.\n"
            "Design a complete system architecture for the following requirements. "
            "Return valid JSON with keys:\n"
            "  overview (string),\n"
            "  components (list of {name, type, responsibility, technology}),\n"
            "  data_flow (list of {from, to, protocol, description}),\n"
            "  technology_stack (dict of layer→technology),\n"
            "  scalability (string),\n"
            "  security_considerations (list of strings)\n\n"
            f"Requirements:\n{requirements}"
        )
        response = self.call_ollama(prompt)

        design: Dict[str, Any] = {}
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1:
                design = json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        # Ensure required keys with fallbacks
        result = {
            "requirements": requirements,
            "overview": design.get("overview", response[:400]),
            "components": design.get("components", []),
            "data_flow": design.get("data_flow", []),
            "technology_stack": design.get("technology_stack", {}),
            "scalability": design.get("scalability", ""),
            "security_considerations": design.get("security_considerations", []),
        }
        self.store_memory(f"design:{requirements[:50]}", result, tags=["design"])
        return result

    def review_architecture(self, design: Dict[str, Any]) -> Dict[str, Any]:
        """
        Review an existing architecture dict and return a structured critique.
        """
        self.log("Reviewing architecture…")
        design_summary = json.dumps(design, indent=2)[:3000]

        prompt = (
            "You are a senior systems architect conducting a design review.\n"
            "Evaluate the following architecture and return JSON with keys:\n"
            "  strengths (list of strings),\n"
            "  weaknesses (list of strings),\n"
            "  risks (list of {risk, impact, likelihood}),\n"
            "  score (int 1-10),\n"
            "  verdict (string)\n\n"
            f"Architecture:\n{design_summary}"
        )
        response = self.call_ollama(prompt)

        review: Dict[str, Any] = {}
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1:
                review = json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            review = {"verdict": response[:400]}

        return {
            "design_summary": design.get("overview", ""),
            "strengths": review.get("strengths", []),
            "weaknesses": review.get("weaknesses", []),
            "risks": review.get("risks", []),
            "score": review.get("score", 0),
            "verdict": review.get("verdict", ""),
        }

    def suggest_improvements(self, system: str) -> List[Dict[str, Any]]:
        """
        Suggest concrete improvements for *system* description.

        Returns a list of improvement dicts with keys:
        area, current_issue, suggestion, expected_benefit, priority.
        """
        self.log(f"Suggesting improvements for: {system[:80]}…")
        prompt = (
            "You are a solutions architect optimising an existing system.\n"
            "Suggest improvements for the system described below. "
            "Return a JSON array of improvements, each with keys:\n"
            "  area (string: performance/scalability/security/reliability/cost),\n"
            "  current_issue (string),\n"
            "  suggestion (string),\n"
            "  expected_benefit (string),\n"
            "  priority (high/medium/low)\n\n"
            f"System: {system}"
        )
        response = self.call_ollama(prompt)

        improvements: List[Dict[str, Any]] = []
        try:
            start = response.find("[")
            end = response.rfind("]") + 1
            if start != -1:
                improvements = json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            improvements = [
                {
                    "area": "general",
                    "current_issue": "See full analysis",
                    "suggestion": response[:300],
                    "expected_benefit": "Improved system quality",
                    "priority": "medium",
                }
            ]

        self.store_memory(f"improvements:{system[:50]}", improvements, tags=["improvement"])
        return improvements

    def create_diagram(self, components: List[Dict[str, Any]]) -> str:
        """
        Generate a text-based ASCII architecture diagram from *components*.

        Each component dict should have at least a 'name' key; optional keys:
        'type', 'connects_to' (list).
        """
        self.log(f"Creating diagram for {len(components)} components…")

        # Build a prompt-friendly representation
        comp_list = "\n".join(
            f"- {c.get('name', 'Unknown')} ({c.get('type', 'service')})"
            f"{': connects to ' + ', '.join(c['connects_to']) if 'connects_to' in c else ''}"
            for c in components
        )
        prompt = (
            "You are a technical documentation writer.\n"
            "Create a clear ASCII art architecture diagram for the following components "
            "and their connections. Use boxes, arrows (-->, <-->, ---), and labels.\n\n"
            f"Components:\n{comp_list}"
        )
        diagram = self.call_ollama(prompt)
        self.store_memory("diagram", diagram, tags=["diagram"])
        return diagram

    def estimate_resources(self, design: Dict[str, Any]) -> Dict[str, Any]:
        """
        Estimate infrastructure resource requirements for a given *design*.

        Returns a dict with CPU, memory, storage, network, and cost estimates.
        """
        self.log("Estimating resources…")
        design_summary = json.dumps(design, indent=2)[:2000]

        prompt = (
            "You are a cloud infrastructure estimator.\n"
            "Estimate the resources required to run the following system design "
            "at modest scale (1000 concurrent users). "
            "Return JSON with keys:\n"
            "  cpu_cores (int),\n"
            "  memory_gb (int),\n"
            "  storage_gb (int),\n"
            "  network_bandwidth_mbps (int),\n"
            "  instances (list of {service, count, instance_type}),\n"
            "  estimated_monthly_cost_usd (float),\n"
            "  notes (string)\n\n"
            f"Design:\n{design_summary}"
        )
        response = self.call_ollama(prompt)

        estimate: Dict[str, Any] = {}
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1:
                estimate = json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            estimate = {"notes": response[:400]}

        result = {
            "design_overview": design.get("overview", "")[:200],
            "cpu_cores": estimate.get("cpu_cores", 0),
            "memory_gb": estimate.get("memory_gb", 0),
            "storage_gb": estimate.get("storage_gb", 0),
            "network_bandwidth_mbps": estimate.get("network_bandwidth_mbps", 0),
            "instances": estimate.get("instances", []),
            "estimated_monthly_cost_usd": estimate.get("estimated_monthly_cost_usd", 0.0),
            "notes": estimate.get("notes", ""),
        }
        self.store_memory("resource_estimate", result, tags=["estimate"])
        return result

    def compare_architectures(
        self,
        design_a: Dict[str, Any],
        design_b: Dict[str, Any],
    ) -> str:
        """Compare two architecture designs and recommend the better option."""
        summary_a = json.dumps(design_a, indent=2)[:1500]
        summary_b = json.dumps(design_b, indent=2)[:1500]
        prompt = (
            "Compare the following two system architectures. Analyse trade-offs "
            "in performance, scalability, cost, complexity, and maintainability. "
            "Recommend which is better and why.\n\n"
            f"ARCHITECTURE A:\n{summary_a}\n\n"
            f"ARCHITECTURE B:\n{summary_b}"
        )
        return self.call_ollama(prompt)
