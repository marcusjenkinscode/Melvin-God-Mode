"""
melvin/core/router.py
======================
Intelligent model router.

Given a user prompt and the current system state, the router selects the
most appropriate agent.  Selection logic is:

1. If a specific agent was explicitly requested (e.g. ``!code``, ``!math``),
   use that category.
2. Keyword heuristics map the prompt to a category.
3. Prefer agents whose model is already running / recently used.
4. Respect available RAM – skip models that require more RAM than is free.
5. Fall back to the best available general-purpose agent.
"""

from __future__ import annotations

import re
from typing import Optional

from config import ModelSpec
from melvin.core.agent import Agent, AgentRegistry
from melvin.monitoring.system import SystemMonitor


# ---------------------------------------------------------------------------
# Category keyword maps
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "code": [
        "code", "python", "javascript", "bash", "script", "function", "class",
        "debug", "error", "exception", "compile", "program", "algorithm",
        "regex", "sql", "query", "api", "endpoint", "git", "refactor",
    ],
    "math": [
        "math", "calculate", "equation", "integral", "derivative", "algebra",
        "statistics", "probability", "matrix", "vector", "proof", "theorem",
        "sum", "product", "formula", "solve", "numeric",
    ],
    "creative": [
        "poem", "story", "write", "creative", "fiction", "blog", "article",
        "email", "letter", "essay", "script", "lyrics", "idea", "brainstorm",
        "metaphor", "analogy",
    ],
    "security": [
        "hack", "exploit", "vulnerability", "pentest", "payload", "reverse shell",
        "privilege escalation", "buffer overflow", "injection", "xss", "csrf",
        "cve", "malware", "ransomware", "phishing", "social engineering",
    ],
    "osint": [
        "osint", "recon", "reconnaissance", "investigate", "find information",
        "username", "domain", "whois", "email address", "social media",
        "person lookup", "ip address", "geolocation",
    ],
    "vision": [
        "image", "picture", "photo", "screenshot", "describe image",
        "what is in", "ocr", "read text from",
    ],
}

# Compiled regex per category for speed — use word boundaries to avoid
# false-positives like matching "story" inside "history".
_COMPILED: dict[str, re.Pattern] = {
    cat: re.compile(
        "|".join(r"\b" + re.escape(kw) + r"\b" for kw in kws),
        re.IGNORECASE,
    )
    for cat, kws in _CATEGORY_KEYWORDS.items()
}

# Explicit override prefixes (user types "!code ask me …")
_OVERRIDE_PREFIX = re.compile(
    r"^!(?P<category>code|math|creative|security|osint|vision|general)\s+",
    re.IGNORECASE,
)


class ModelRouter:
    """
    Selects the best available agent for a given prompt.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        monitor: SystemMonitor,
    ) -> None:
        self._registry = registry
        self._monitor = monitor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, prompt: str) -> tuple[Optional[Agent], str]:
        """
        Return *(agent, clean_prompt)*.

        *clean_prompt* has any ``!category`` override prefix stripped.
        If no suitable agent is found, *agent* is ``None``.
        """
        # 1. Explicit override — always strip the prefix from the prompt
        m = _OVERRIDE_PREFIX.match(prompt)
        if m:
            category = m.group("category").lower()
            clean_prompt = prompt[m.end():]
            agent = self._best_for_category(category)
            # Return even if agent is None so the prefix is always stripped
            return agent, clean_prompt

        clean_prompt = prompt
        # 2. Keyword heuristics
        category = self._infer_category(prompt)

        # 3. Check RAM and return best fit
        agent = self._best_for_category(category)
        if agent:
            return agent, clean_prompt

        # 4. Absolute fallback – any available agent
        available = self._registry.list_available()
        if available:
            return available[0], clean_prompt

        return None, clean_prompt

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _infer_category(self, prompt: str) -> str:
        for category, pattern in _COMPILED.items():
            if pattern.search(prompt):
                return category
        return "general"

    def _best_for_category(self, category: str) -> Optional[Agent]:
        available_ram = self._monitor.available_ram_gb()

        # Gather agents for category that are available AND fit in RAM
        candidates: list[Agent] = []
        for agent in self._registry.list_available():
            if agent.category != category:
                continue
            if agent.spec.min_ram_gb <= available_ram:
                candidates.append(agent)

        if candidates:
            # Prefer larger (higher quality) models that still fit
            return max(candidates, key=lambda a: a.spec.size_gb)

        # Category-specific match failed – try general with RAM check
        if category != "general":
            return self._best_for_category("general")

        return None
