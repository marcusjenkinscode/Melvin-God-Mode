"""
Base agent class for the Melvin God Mode AI infrastructure platform.
All agents inherit from AgentBase.
"""

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Module-level logger (each instance overrides with a child logger)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_TIMEOUT = 120  # seconds


class AgentBase(ABC):
    """Abstract base class for all Melvin God Mode agents."""

    # Valid status values
    STATUS_IDLE = "idle"
    STATUS_RUNNING = "running"
    STATUS_ERROR = "error"

    def __init__(
        self,
        name: str,
        model: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.model = model
        self.config: Dict[str, Any] = config or {}

        self.agent_id: str = str(uuid.uuid4())
        self.status: str = self.STATUS_IDLE
        self.task_history: List[Dict[str, Any]] = []

        # Async message queue (created lazily so it always belongs to the
        # running event-loop when first used).
        self._message_queue: Optional[asyncio.Queue] = None

        # Simple in-process vector store simulation (list of dicts)
        self._memory: List[Dict[str, Any]] = []

        self.logger = logging.getLogger(f"agent.{self.name}")
        self.logger.info("Agent '%s' initialised (model=%s)", self.name, self.model)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def run(self, task: str) -> Any:
        """Execute a task and return the result."""

    @abstractmethod
    def think(self, prompt: str) -> str:
        """Internal reasoning step; returns a string response."""

    @abstractmethod
    def act(self, action: Dict[str, Any]) -> Any:
        """Execute a concrete action."""

    @abstractmethod
    def observe(self, result: Any) -> None:
        """Process the result of an action."""

    # ------------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------------

    def log(self, message: str, level: str = "info") -> None:
        """Log a message at the given level."""
        log_fn = getattr(self.logger, level.lower(), self.logger.info)
        log_fn(message)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def _get_queue(self) -> asyncio.Queue:
        if self._message_queue is None:
            self._message_queue = asyncio.Queue()
        return self._message_queue

    def send_to_agent(self, agent_name: str, message: Any) -> None:
        """
        Enqueue a message addressed to *agent_name*.

        The SwarmController is expected to route the message; here we log the
        intent and push it to our own outbox so the controller can inspect it.
        """
        envelope = {
            "from": self.name,
            "to": agent_name,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.log(f"Sending message to '{agent_name}': {message}")
        # Push to queue in a fire-and-forget fashion
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(self._get_queue().put_nowait, envelope)
            else:
                self._get_queue().put_nowait(envelope)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Could not enqueue message: %s", exc)

    async def receive_message(self) -> Any:
        """Await and return the next message from the queue."""
        return await self._get_queue().get()

    # ------------------------------------------------------------------
    # Ollama integration
    # ------------------------------------------------------------------

    def call_ollama(
        self,
        prompt: str,
        model: Optional[str] = None,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send *prompt* to the local Ollama API and return the generated text.

        Falls back to a placeholder string if Ollama is unreachable so that
        tests / offline development still function.
        """
        target_model = model or self.model
        payload: Dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": stream,
        }
        if options:
            payload["options"] = options

        self.log(f"Calling Ollama model='{target_model}' prompt_len={len(prompt)}")
        try:
            response = requests.post(
                OLLAMA_API_URL,
                json=payload,
                timeout=OLLAMA_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except requests.exceptions.ConnectionError:
            self.log("Ollama unreachable – returning placeholder response.", "warning")
            return f"[Ollama offline] Placeholder response for model '{target_model}'."
        except requests.exceptions.Timeout:
            self.log("Ollama request timed out.", "error")
            return "[Ollama timeout] Request exceeded allowed duration."
        except Exception as exc:  # noqa: BLE001
            self.log(f"Ollama request failed: {exc}", "error")
            return f"[Ollama error] {exc}"

    # ------------------------------------------------------------------
    # Memory / vector store (simple in-process implementation)
    # ------------------------------------------------------------------

    def store_memory(self, key: str, value: Any, tags: Optional[List[str]] = None) -> None:
        """Store a value in the agent's memory."""
        entry = {
            "id": str(uuid.uuid4()),
            "key": key,
            "value": value,
            "tags": tags or [],
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._memory.append(entry)
        self.log(f"Stored memory key='{key}'")

    def retrieve_memory(self, key: str) -> List[Any]:
        """Retrieve all memory entries matching *key*."""
        results = [e["value"] for e in self._memory if e["key"] == key]
        self.log(f"Retrieved {len(results)} memory entries for key='{key}'")
        return results

    def search_memory(self, query: str) -> List[Dict[str, Any]]:
        """Naive keyword search across stored memory values."""
        query_lower = query.lower()
        return [
            e for e in self._memory
            if query_lower in str(e.get("value", "")).lower()
            or query_lower in str(e.get("key", "")).lower()
        ]

    def clear_memory(self) -> None:
        """Wipe all stored memories."""
        self._memory.clear()
        self.log("Memory cleared.")

    # ------------------------------------------------------------------
    # Task history
    # ------------------------------------------------------------------

    def _record_task(self, task: str, result: Any, duration: float) -> None:
        """Append a task record to the history list."""
        self.task_history.append(
            {
                "id": str(uuid.uuid4()),
                "task": task,
                "result_summary": str(result)[:500],
                "duration_seconds": round(duration, 3),
                "timestamp": datetime.utcnow().isoformat(),
                "status": self.status,
            }
        )

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    def set_status(self, status: str) -> None:
        valid = {self.STATUS_IDLE, self.STATUS_RUNNING, self.STATUS_ERROR}
        if status not in valid:
            raise ValueError(f"Invalid status '{status}'. Must be one of {valid}.")
        self.status = status
        self.log(f"Status changed to '{status}'")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation of the agent's state."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "model": self.model,
            "status": self.status,
            "config": self.config,
            "task_history_count": len(self.task_history),
            "memory_entry_count": len(self._memory),
        }

    def to_json(self) -> str:
        """Return agent state as a JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} name={self.name!r} "
            f"model={self.model!r} status={self.status!r}>"
        )
