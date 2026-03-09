"""
PlannerAgent – task decomposition, planning, prioritisation, and agent assignment.
"""

import json
import time
from typing import Any, Dict, List, Optional

from agents.agent_base import AgentBase

DEFAULT_MODEL = "llama3"

# Known agent names available in the swarm
KNOWN_AGENTS = {
    "coding": "CoderAgent",
    "code": "CoderAgent",
    "develop": "CoderAgent",
    "implement": "CoderAgent",
    "research": "ResearchAgent",
    "search": "ResearchAgent",
    "investigate": "ResearchAgent",
    "analyse": "ResearchAgent",
    "analyze": "ResearchAgent",
    "deploy": "DevOpsAgent",
    "devops": "DevOpsAgent",
    "infrastructure": "DevOpsAgent",
    "monitor": "DevOpsAgent",
    "security": "SecurityAgent",
    "audit": "SecurityAgent",
    "scan": "SecurityAgent",
    "debug": "DebuggerAgent",
    "fix": "DebuggerAgent",
    "error": "DebuggerAgent",
    "architecture": "ArchitectAgent",
    "design": "ArchitectAgent",
    "plan": "PlannerAgent",
    "decompose": "PlannerAgent",
}


class PlannerAgent(AgentBase):
    """Agent that decomposes goals into subtasks, creates plans, and assigns work."""

    def __init__(
        self,
        name: str = "PlannerAgent",
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
        self.log(f"Planning task: {task}")

        try:
            plan = self.create_plan(task)
            result = {"task": task, "plan": plan, "model": self.model}
            self.observe(result)
            self.set_status(self.STATUS_IDLE)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Planning failed: {exc}", "error")
            self.set_status(self.STATUS_ERROR)
            result = {"task": task, "error": str(exc)}

        self._record_task(task, result, time.time() - start)
        return result

    def think(self, prompt: str) -> str:
        return self.call_ollama(prompt)

    def act(self, action: Dict[str, Any]) -> Any:
        action_type = action.get("type")
        if action_type == "decompose":
            return self.decompose_task(action["task"])
        if action_type == "create_plan":
            return self.create_plan(action["goal"])
        if action_type == "prioritize":
            return self.prioritize(action["tasks"])
        if action_type == "estimate":
            return self.estimate_complexity(action["task"])
        if action_type == "assign":
            return self.assign_agents(action["tasks"])
        self.log(f"Unknown action type: {action_type}", "warning")
        return None

    def observe(self, result: Any) -> None:
        if isinstance(result, dict):
            self.store_memory("last_plan", result, tags=["plan"])

    # ------------------------------------------------------------------
    # Core capabilities
    # ------------------------------------------------------------------

    def decompose_task(self, task: str) -> List[str]:
        """
        Break *task* into an ordered list of subtasks.
        """
        self.log(f"Decomposing task: {task}")
        prompt = (
            "You are an expert project manager.\n"
            "Break the following high-level task into a numbered list of clear, "
            "actionable subtasks. Each subtask should be independently executable.\n\n"
            f"Task: {task}\n\n"
            "Return ONLY a numbered list, one subtask per line."
        )
        response = self.call_ollama(prompt)
        subtasks: List[str] = []
        for line in response.splitlines():
            line = line.strip()
            # Strip leading numbering like "1.", "1)", "- ", etc.
            cleaned = line.lstrip("0123456789.-) ").strip()
            if cleaned:
                subtasks.append(cleaned)

        self.store_memory(f"decompose:{task[:50]}", subtasks, tags=["subtasks"])
        return subtasks

    def create_plan(self, goal: str) -> Dict[str, Any]:
        """
        Create a structured execution plan for *goal*.

        Returns a dict with keys: goal, phases, tasks, dependencies,
        success_criteria, risks.
        """
        self.log(f"Creating plan for goal: {goal}")
        prompt = (
            "You are a strategic planner.\n"
            "Create a detailed execution plan for the following goal. "
            "Return valid JSON with keys: phases (list of phase names), "
            "tasks (list of {name, phase, description, agent_type}), "
            "dependencies (list of {task, depends_on}), "
            "success_criteria (list of strings), "
            "risks (list of {risk, mitigation}).\n\n"
            f"Goal: {goal}"
        )
        response = self.call_ollama(prompt)

        # Attempt to parse JSON; fall back to a structured dict if parsing fails
        try:
            # Extract first JSON object from the response
            start = response.find("{")
            end = response.rfind("}") + 1
            plan_data = json.loads(response[start:end]) if start != -1 else {}
        except (json.JSONDecodeError, ValueError):
            plan_data = {}

        # Ensure required keys exist
        subtasks = self.decompose_task(goal)
        default_phases = ["Phase 1: Discovery", "Phase 2: Execution", "Phase 3: Review"]
        default_tasks = [
            {"name": t, "phase": "Phase 2: Execution", "description": t}
            for t in subtasks
        ]
        plan: Dict[str, Any] = {
            "goal": goal,
            "phases": plan_data.get("phases", default_phases),
            "tasks": plan_data.get("tasks", default_tasks),
            "dependencies": plan_data.get("dependencies", []),
            "success_criteria": plan_data.get("success_criteria", []),
            "risks": plan_data.get("risks", []),
            "subtasks": subtasks,
        }
        self.store_memory(f"plan:{goal[:50]}", plan, tags=["plan"])
        return plan

    def prioritize(self, tasks: List[str]) -> List[str]:
        """
        Return *tasks* sorted by priority (most important first).
        """
        self.log(f"Prioritising {len(tasks)} tasks…")
        if not tasks:
            return []

        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks))
        prompt = (
            "You are a project manager.\n"
            "Prioritise the following tasks from most to least important, "
            "considering dependencies, impact, and urgency.\n"
            "Return ONLY the tasks renumbered in priority order.\n\n"
            f"{numbered}"
        )
        response = self.call_ollama(prompt)
        prioritised: List[str] = []
        for line in response.splitlines():
            cleaned = line.strip().lstrip("0123456789.-) ").strip()
            if cleaned:
                prioritised.append(cleaned)

        # If LLM returned garbage, fall back to original order
        if len(prioritised) < len(tasks) // 2:
            return tasks
        return prioritised

    def estimate_complexity(self, task: str) -> Dict[str, Any]:
        """
        Estimate the complexity of *task*.

        Returns a dict with keys: score (1–10), level, reasoning, estimated_hours.
        """
        self.log(f"Estimating complexity for: {task}")
        prompt = (
            "You are a technical estimator.\n"
            "Estimate the complexity of the following task on a scale from 1 (trivial) "
            "to 10 (extremely complex). Return JSON with keys: score (int), "
            "level (string: low/medium/high/critical), reasoning (string), "
            "estimated_hours (float).\n\n"
            f"Task: {task}"
        )
        response = self.call_ollama(prompt)
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            data = json.loads(response[start:end]) if start != -1 else {}
        except (json.JSONDecodeError, ValueError):
            data = {}

        return {
            "task": task,
            "score": data.get("score", 5),
            "level": data.get("level", "medium"),
            "reasoning": data.get("reasoning", response[:200]),
            "estimated_hours": data.get("estimated_hours", 4.0),
        }

    def assign_agents(self, tasks: List[str]) -> Dict[str, str]:
        """
        Map each task to the most appropriate agent name.

        Returns a dict of {task: agent_name}.
        """
        self.log(f"Assigning agents to {len(tasks)} tasks…")
        assignments: Dict[str, str] = {}
        for task in tasks:
            task_lower = task.lower()
            assigned = "CoderAgent"  # sensible default
            for keyword, agent in KNOWN_AGENTS.items():
                if keyword in task_lower:
                    assigned = agent
                    break
            assignments[task] = assigned

        self.store_memory("assignments", assignments, tags=["assignment"])
        return assignments

    def create_timeline(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate a simple ordered timeline from a plan dict."""
        timeline = []
        for i, task in enumerate(plan.get("subtasks", []), start=1):
            estimate = self.estimate_complexity(task)
            timeline.append(
                {
                    "step": i,
                    "task": task,
                    "estimated_hours": estimate["estimated_hours"],
                    "complexity": estimate["level"],
                }
            )
        return timeline
