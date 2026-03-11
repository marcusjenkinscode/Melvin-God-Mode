"""
melvin/core/agent.py
=====================
AI agents backed by Ollama.

Each agent wraps a specific Ollama model and system prompt.  When called,
it streams tokens back to a callback so the TUI can display them in real
time.  All interactions are automatically persisted to the encrypted dataset.
"""

from __future__ import annotations

import time
from typing import Callable, Generator, Iterator, Optional

import ollama  # type: ignore
from ollama import ResponseError, RequestError  # type: ignore

from config import AGENT_PROMPTS, MODEL_CATALOGUE, ModelSpec
from melvin.core.dataset import Dataset
from melvin.core.memory import ConversationMemory


# ---------------------------------------------------------------------------
# Thought logger protocol (avoids circular imports)
# ---------------------------------------------------------------------------
class _ThoughtSink:
    """Minimal interface for logging agent thoughts."""

    def log(self, message: str, level: str = "INFO") -> None:  # noqa: D102
        pass


# ---------------------------------------------------------------------------
# Single agent
# ---------------------------------------------------------------------------

class Agent:
    """
    A single Ollama-backed conversational agent.

    Parameters
    ----------
    spec:
        The ModelSpec describing the underlying Ollama model.
    category:
        Used to look up the system prompt in AGENT_PROMPTS.
    dataset:
        Shared Dataset for persisting interactions.
    logger:
        ThoughtLogger (or any object with a .log() method).
    max_context_tokens:
        Sliding-window context size (approximate).
    """

    def __init__(
        self,
        spec: ModelSpec,
        category: str,
        dataset: Dataset,
        logger: _ThoughtSink,
        max_context_tokens: int = 4096,
        ollama_host: Optional[str] = None,
    ) -> None:
        self.spec = spec
        self.category = category
        self._dataset = dataset
        self._logger = logger

        system_prompt = AGENT_PROMPTS.get(category, AGENT_PROMPTS["general"])
        self._memory = ConversationMemory(
            system_prompt=system_prompt,
            max_tokens=max_context_tokens,
        )
        self._client = ollama.Client(host=ollama_host) if ollama_host else ollama.Client()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.spec.display_name

    @property
    def model_tag(self) -> str:
        return self.spec.tag

    def is_available(self) -> bool:
        """Return True if the model is present in the local Ollama library."""
        try:
            models = self._client.list()
            tags = [m["model"] for m in models.get("models", [])]
            return self.spec.tag in tags
        except Exception:  # noqa: BLE001
            return False

    def pull(self, progress_cb: Optional[Callable[[str, float], None]] = None) -> None:
        """Pull (download) the model from the Ollama registry."""
        self._logger.log(f"Pulling {self.spec.tag} ({self.spec.size_gb:.1f} GB) …")
        for status in self._client.pull(self.spec.tag, stream=True):
            msg = status.get("status", "")
            total = status.get("total", 0) or 1
            completed = status.get("completed", 0)
            pct = (completed / total) * 100 if total else 0.0
            if progress_cb:
                progress_cb(msg, pct)
        self._logger.log(f"Model {self.spec.tag} ready.")

    def chat(
        self,
        user_input: str,
        stream_cb: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Send *user_input* to the model and return the full response string.

        If *stream_cb* is provided, each token chunk is forwarded to it as it
        arrives so the UI can display streaming output.
        """
        self._logger.log(f"[{self.spec.tag}] Processing: {user_input[:60]}…")
        self._memory.add_user(user_input)

        full_response = ""
        start = time.perf_counter()

        try:
            stream: Iterator = self._client.chat(
                model=self.spec.tag,
                messages=self._memory.get_messages(),
                stream=True,
            )
            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                full_response += token
                if stream_cb:
                    stream_cb(token)
        except (ResponseError, RequestError) as exc:
            full_response = (
                f"[Ollama error] {exc}\n\n"
                "Is Ollama running?  Start it with: `ollama serve`\n"
                f"Is the model pulled?  Run: `ollama pull {self.spec.tag}`"
            )
            self._logger.log(str(exc), "ERROR")

        elapsed = time.perf_counter() - start
        self._logger.log(
            f"[{self.spec.tag}] Response in {elapsed:.1f}s "
            f"({len(full_response.split())} words)"
        )

        self._memory.add_assistant(full_response)
        self._dataset.append(
            input_text=user_input,
            response=full_response,
            model=self.spec.tag,
            agent=self.category,
        )
        return full_response

    def reset_memory(self) -> None:
        self._memory.clear()
        self._logger.log(f"[{self.spec.tag}] Conversation memory cleared.")

    def inject_context(self, text: str) -> None:
        """Inject arbitrary text into the system prompt (e.g. tool output)."""
        self._logger.log(f"[{self.spec.tag}] Injecting {len(text)} chars of context.")
        self._memory.update_system_prompt(
            self._memory._system_prompt + f"\n\n[CONTEXT]\n{text}\n[/CONTEXT]"
        )


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------

class AgentRegistry:
    """
    Manages all agents.  At startup each agent is checked against the local
    Ollama library; unavailable agents are marked so the router can skip them.
    """

    def __init__(
        self,
        dataset: Dataset,
        logger: _ThoughtSink,
        ollama_host: Optional[str] = None,
    ) -> None:
        self._dataset = dataset
        self._logger = logger
        self._ollama_host = ollama_host
        self._agents: dict[str, Agent] = {}
        self._build_agents()

    def _build_agents(self) -> None:
        for spec in MODEL_CATALOGUE:
            agent = Agent(
                spec=spec,
                category=spec.category,
                dataset=self._dataset,
                logger=self._logger,
                ollama_host=self._ollama_host,
            )
            # Use tag as key; also register by category (last wins – highest quality)
            self._agents[spec.tag] = agent

    def get_by_tag(self, tag: str) -> Optional[Agent]:
        return self._agents.get(tag)

    def get_by_category(self, category: str) -> Optional[Agent]:
        """Return the first available agent in the given category."""
        for spec in MODEL_CATALOGUE:
            if spec.category == category:
                agent = self._agents.get(spec.tag)
                if agent and agent.is_available():
                    return agent
        return None

    def list_agents(self) -> list[Agent]:
        return list(self._agents.values())

    def list_available(self) -> list[Agent]:
        return [a for a in self._agents.values() if a.is_available()]

    def pull_agent(
        self,
        tag: str,
        progress_cb: Optional[Callable[[str, float], None]] = None,
    ) -> bool:
        agent = self._agents.get(tag)
        if not agent:
            self._logger.log(f"Unknown model tag: {tag}", "ERROR")
            return False
        try:
            agent.pull(progress_cb)
            return True
        except Exception as exc:  # noqa: BLE001
            self._logger.log(f"Pull failed: {exc}", "ERROR")
            return False
