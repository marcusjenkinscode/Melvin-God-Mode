"""
Melvin God Mode - Knowledge Store
High-level semantic knowledge management built on top of VectorMemory.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from .vector_memory import VectorMemory


class KnowledgeStore:
    """
    High-level knowledge management layer wrapping VectorMemory.

    Provides specialised storage/recall for:
    - General knowledge (topic + content)
    - Agent memories (task/result pairs per agent)
    - Code snippets
    """

    def __init__(self, vector_memory: VectorMemory):
        self._mem = vector_memory

    # ------------------------------------------------------------------
    # General knowledge
    # ------------------------------------------------------------------

    def store_knowledge(self, topic: str, content: str, source: Optional[str] = None) -> str:
        """
        Store a piece of knowledge.

        Args:
            topic:   Short label for the knowledge item.
            content: The actual knowledge text.
            source:  Optional provenance string (URL, filename, …).

        Returns:
            Document id.
        """
        text = f"[TOPIC: {topic}]\n{content}"
        metadata = {
            "type": "knowledge",
            "topic": topic,
            "source": source or "",
            "timestamp": _now(),
        }
        return self._mem.store(text, metadata)

    def recall(self, query: str, k: int = 5) -> list:
        """
        Retrieve the *k* most relevant knowledge items for *query*.

        Returns list of dicts: {text, metadata, score}.
        """
        results = self._mem.retrieve(query, n_results=k * 2)
        # Prefer knowledge-type entries first, but include others if needed
        knowledge = [r for r in results if r["metadata"].get("type") == "knowledge"]
        others = [r for r in results if r["metadata"].get("type") != "knowledge"]
        combined = (knowledge + others)[:k]
        return combined

    # ------------------------------------------------------------------
    # Agent memories
    # ------------------------------------------------------------------

    def store_agent_memory(self, agent_name: str, task: str, result: str) -> str:
        """
        Persist the result of an agent's completed task.

        Returns document id.
        """
        text = f"[AGENT: {agent_name}] Task: {task}\nResult: {result}"
        metadata = {
            "type": "agent_memory",
            "agent": agent_name,
            "task": task,
            "timestamp": _now(),
        }
        return self._mem.store(text, metadata)

    def recall_agent_memory(self, agent_name: str, query: str, k: int = 5) -> list:
        """
        Retrieve past memories for *agent_name* relevant to *query*.

        Returns list of dicts: {text, metadata, score}.
        """
        results = self._mem.retrieve(query, n_results=k * 3)
        filtered = [
            r for r in results
            if r["metadata"].get("type") == "agent_memory"
            and r["metadata"].get("agent") == agent_name
        ]
        return filtered[:k]

    # ------------------------------------------------------------------
    # Code snippets
    # ------------------------------------------------------------------

    def store_code(self, code: str, language: str, description: str) -> str:
        """
        Store a code snippet with its language and description.

        Returns document id.
        """
        text = f"[CODE: {language}] {description}\n```{language}\n{code}\n```"
        metadata = {
            "type": "code",
            "language": language,
            "description": description,
            "timestamp": _now(),
        }
        return self._mem.store(text, metadata)

    def search_code(self, query: str, k: int = 5) -> list:
        """
        Search for code snippets relevant to *query*.

        Returns list of dicts: {text, metadata, score}.
        """
        results = self._mem.retrieve(query, n_results=k * 3)
        code_results = [
            r for r in results
            if r["metadata"].get("type") == "code"
        ]
        return code_results[:k]

    # ------------------------------------------------------------------
    # Import / Export
    # ------------------------------------------------------------------

    def export_to_json(self, filepath: str) -> None:
        """
        Export all stored knowledge to a JSON file.

        The export format is a list of {text, metadata} dicts that can be
        re-imported with :meth:`import_from_json`.
        """
        # Retrieve a large batch – use a broad query that will hit everything
        results = self._mem.retrieve("", n_results=10_000)
        records = [{"text": r["text"], "metadata": r["metadata"]} for r in results]
        filepath = os.path.abspath(filepath)
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2, ensure_ascii=False)
        print(f"[KnowledgeStore] Exported {len(records)} records to '{filepath}'.")

    def import_from_json(self, filepath: str) -> int:
        """
        Import knowledge from a previously exported JSON file.

        Returns the number of records imported.
        """
        filepath = os.path.abspath(filepath)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Import file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as fh:
            records = json.load(fh)
        if not isinstance(records, list):
            raise ValueError("JSON file must contain a list of records.")
        count = 0
        for record in records:
            text = record.get("text", "")
            meta = record.get("metadata", {})
            if text:
                self._mem.store(text, meta)
                count += 1
        print(f"[KnowledgeStore] Imported {count} records from '{filepath}'.")
        return count


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
