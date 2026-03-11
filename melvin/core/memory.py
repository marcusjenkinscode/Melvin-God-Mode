"""
melvin/core/memory.py
======================
In-process conversation memory with a sliding context window.

Keeps the last *max_tokens* (approximate) tokens of conversation history
so that each new call to the LLM is contextually aware of previous turns.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Literal


Role = Literal["system", "user", "assistant"]


@dataclass
class Message:
    role: Role
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class ConversationMemory:
    """
    Sliding-window conversation memory for a single agent session.

    The memory stores messages and, when asked for the context to send to
    the LLM, trims to stay under *max_tokens* (a rough character-based
    approximation – good enough for most local models).
    """

    # Characters-per-token approximation (conservative)
    CHARS_PER_TOKEN = 4

    def __init__(self, system_prompt: str, max_tokens: int = 4096) -> None:
        self._lock = threading.Lock()
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        self._messages: Deque[Message] = deque()

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def add_user(self, text: str) -> None:
        with self._lock:
            self._messages.append(Message("user", text))
            self._trim()

    def add_assistant(self, text: str) -> None:
        with self._lock:
            self._messages.append(Message("assistant", text))
            self._trim()

    def clear(self) -> None:
        """Clear conversation history (keep system prompt)."""
        with self._lock:
            self._messages.clear()

    def update_system_prompt(self, prompt: str) -> None:
        with self._lock:
            self._system_prompt = prompt

    @property
    def system_prompt(self) -> str:
        with self._lock:
            return self._system_prompt

    # ------------------------------------------------------------------
    # Readers
    # ------------------------------------------------------------------

    def get_messages(self) -> List[dict]:
        """Return full message list including system prompt, ready for Ollama."""
        with self._lock:
            messages = [{"role": "system", "content": self._system_prompt}]
            messages.extend(m.to_dict() for m in self._messages)
            return messages

    def last_n_turns(self, n: int = 5) -> List[Message]:
        with self._lock:
            return list(self._messages)[-n * 2:]

    def __len__(self) -> int:
        with self._lock:
            return len(self._messages)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _trim(self) -> None:
        """Drop oldest user/assistant pairs until we fit within max_tokens."""
        max_chars = self._max_tokens * self.CHARS_PER_TOKEN
        while self._total_chars() > max_chars and len(self._messages) >= 2:
            # Always drop in pairs to keep user/assistant balance
            self._messages.popleft()
            if self._messages:
                self._messages.popleft()

    def _total_chars(self) -> int:
        base = len(self._system_prompt)
        return base + sum(len(m.content) for m in self._messages)
