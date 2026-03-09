"""
SwarmController – manages all agents, task decomposition, and parallel execution.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from agents.agent_base import AgentBase
from agents.architect_agent import ArchitectAgent
from agents.coder_agent import CoderAgent
from agents.debugger_agent import DebuggerAgent
from agents.devops_agent import DevOpsAgent
from agents.planner_agent import PlannerAgent
from agents.research_agent import ResearchAgent
from agents.security_agent import SecurityAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SwarmController] %(levelname)s: %(message)s",
)

logger = logging.getLogger("SwarmController")


class SwarmController:
    """
    Orchestrates the full agent swarm.

    Responsibilities:
    - Initialise and register all agents.
    - Decompose high-level tasks via PlannerAgent.
    - Assign subtasks to the most appropriate agents.
    - Execute subtasks in parallel where possible.
    - Collect and aggregate results.
    - Broadcast messages to all agents.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self._results: List[Dict[str, Any]] = []

        # Instantiate and register all agents
        self._registry: Dict[str, AgentBase] = {}
        self._init_agents()

        logger.info(
            "SwarmController ready with %d agents: %s",
            len(self._registry),
            list(self._registry.keys()),
        )

    # ------------------------------------------------------------------
    # Agent initialisation
    # ------------------------------------------------------------------

    def _init_agents(self) -> None:
        """Create all agents and store them in the registry."""
        agents: List[AgentBase] = [
            CoderAgent(config=self.config.get("coder", {})),
            ResearchAgent(config=self.config.get("research", {})),
            PlannerAgent(config=self.config.get("planner", {})),
            DevOpsAgent(config=self.config.get("devops", {})),
            SecurityAgent(config=self.config.get("security", {})),
            DebuggerAgent(config=self.config.get("debugger", {})),
            ArchitectAgent(config=self.config.get("architect", {})),
        ]
        for agent in agents:
            self._registry[agent.name] = agent

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_agent(self, name: str) -> Optional[AgentBase]:
        """Return the agent registered under *name*, or None."""
        return self._registry.get(name)

    def register_agent(self, agent: AgentBase) -> None:
        """Add a custom agent to the registry."""
        self._registry[agent.name] = agent
        logger.info("Registered agent: %s", agent.name)

    def run_swarm(self, task: str) -> Dict[str, Any]:
        """
        High-level entry point.

        1. Uses PlannerAgent to decompose the task.
        2. Assigns each subtask to the best agent.
        3. Executes all subtasks (in parallel where supported).
        4. Collects and returns aggregated results.
        """
        logger.info("Swarm starting on task: %s", task)
        start = time.time()

        planner = self.get_agent("PlannerAgent")
        if planner is None:
            logger.error("PlannerAgent not found in registry; cannot decompose task.")
            return {"original_task": task, "error": "PlannerAgent unavailable", "results": []}
        planner = planner  # type: PlannerAgent
        plan = planner.create_plan(task)
        assignments = planner.assign_agents(plan.get("subtasks", [task]))

        # Build task→agent pairs
        task_agent_pairs = [
            (subtask, assignments.get(subtask, "CoderAgent"))
            for subtask in assignments
        ]

        # Run all subtasks
        results = asyncio.run(self._execute_all(task_agent_pairs))
        self._results.extend(results)

        summary = {
            "original_task": task,
            "plan": plan,
            "assignments": assignments,
            "results": results,
            "duration_seconds": round(time.time() - start, 3),
        }
        logger.info("Swarm completed in %.2fs", time.time() - start)
        return summary

    def broadcast(self, message: Any) -> None:
        """Send *message* to every registered agent."""
        logger.info("Broadcasting message to %d agents", len(self._registry))
        for agent in self._registry.values():
            agent.send_to_agent(agent.name, message)

    def get_status(self) -> Dict[str, Any]:
        """Return a status snapshot for every agent."""
        return {
            name: {
                "status": agent.status,
                "task_history_count": len(agent.task_history),
                "memory_entries": len(agent._memory),
            }
            for name, agent in self._registry.items()
        }

    def collect_results(self) -> List[Dict[str, Any]]:
        """Return all results accumulated since the controller was created."""
        return list(self._results)

    def execute_parallel(
        self,
        tasks: List[str],
        agents: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Run *tasks* in parallel, each on the corresponding agent in *agents*.

        len(tasks) must equal len(agents).
        """
        if len(tasks) != len(agents):
            raise ValueError("tasks and agents lists must have the same length.")
        pairs = list(zip(tasks, agents))
        return asyncio.run(self._execute_all(pairs))

    # ------------------------------------------------------------------
    # Internal async execution
    # ------------------------------------------------------------------

    async def _execute_all(
        self,
        task_agent_pairs: List[tuple],
    ) -> List[Dict[str, Any]]:
        """Run all (task, agent_name) pairs concurrently via asyncio."""
        coroutines = [
            self._run_agent_task(task, agent_name)
            for task, agent_name in task_agent_pairs
        ]
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        processed = []
        for (task, agent_name), result in zip(task_agent_pairs, results):
            if isinstance(result, Exception):
                processed.append(
                    {"task": task, "agent": agent_name, "error": str(result)}
                )
            else:
                processed.append(result)
        return processed

    async def _run_agent_task(self, task: str, agent_name: str) -> Dict[str, Any]:
        """Execute *task* on *agent_name* in a thread pool to avoid blocking."""
        agent = self._registry.get(agent_name)
        if agent is None:
            logger.warning("Agent '%s' not found; falling back to CoderAgent.", agent_name)
            agent = self._registry.get("CoderAgent")
        if agent is None:
            return {"task": task, "agent": agent_name, "error": "Agent not found and no fallback available."}

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, agent.run, task)
            return {
                "task": task,
                "agent": agent_name,
                "result": result,
                "status": "success",
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Agent '%s' failed on task '%s': %s", agent_name, task, exc)
            return {"task": task, "agent": agent_name, "error": str(exc), "status": "error"}

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def run_single(self, task: str, agent_name: str) -> Dict[str, Any]:
        """Run a single task on a named agent synchronously."""
        agent = self._registry.get(agent_name)
        if agent is None:
            return {"error": f"Agent '{agent_name}' not found."}
        return agent.run(task)

    def reset_all(self) -> None:
        """Reset all agents to idle and clear the results buffer."""
        for agent in self._registry.values():
            agent.set_status(AgentBase.STATUS_IDLE)
            agent.task_history.clear()
        self._results.clear()
        logger.info("All agents reset.")

    def to_json(self) -> str:
        """Return a JSON summary of the swarm state."""
        return json.dumps(
            {
                "agents": {
                    name: agent.to_dict() for name, agent in self._registry.items()
                },
                "result_count": len(self._results),
            },
            indent=2,
        )

    def __repr__(self) -> str:
        return (
            f"<SwarmController agents={list(self._registry.keys())} "
            f"results={len(self._results)}>"
        )
