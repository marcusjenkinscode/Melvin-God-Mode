"""
ResearchAgent – specialises in research, knowledge gathering, and report compilation.
"""

import re
import time
from typing import Any, Dict, List, Optional

from agents.agent_base import AgentBase

DEFAULT_MODEL = "mixtral"
FALLBACK_MODEL = "llama3"


class ResearchAgent(AgentBase):
    """Agent that searches knowledge bases, summarises text, and compiles reports."""

    def __init__(
        self,
        name: str = "ResearchAgent",
        model: str = DEFAULT_MODEL,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(name, model, config)
        # Simple in-process knowledge base (key → list of text snippets)
        self._knowledge_base: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------
    # AgentBase abstract methods
    # ------------------------------------------------------------------

    def run(self, task: str) -> Dict[str, Any]:
        """
        High-level research task.  Compiles a full report on the topic
        described in *task*.
        """
        self.set_status(self.STATUS_RUNNING)
        start = time.time()
        self.log(f"Running research task: {task}")

        try:
            report = self.compile_report(task)
            result = {
                "task": task,
                "report": report,
                "model": self.model,
            }
            self.observe(result)
            self.set_status(self.STATUS_IDLE)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Research task failed: {exc}", "error")
            self.set_status(self.STATUS_ERROR)
            result = {"task": task, "error": str(exc)}

        self._record_task(task, result, time.time() - start)
        return result

    def think(self, prompt: str) -> str:
        return self.call_ollama(prompt)

    def act(self, action: Dict[str, Any]) -> Any:
        action_type = action.get("type")
        if action_type == "search":
            return self.search(action["query"])
        if action_type == "summarize":
            return self.summarize(action["text"])
        if action_type == "extract_facts":
            return self.extract_facts(action["text"])
        if action_type == "compile_report":
            return self.compile_report(action["topic"])
        self.log(f"Unknown action type: {action_type}", "warning")
        return None

    def observe(self, result: Any) -> None:
        if isinstance(result, dict):
            topic = result.get("task", "unknown")
            self.store_memory(f"research:{topic}", result, tags=["research"])

    # ------------------------------------------------------------------
    # Core capabilities
    # ------------------------------------------------------------------

    def search(self, query: str) -> Dict[str, Any]:
        """
        Search the internal knowledge base for *query*.

        Also queries the LLM for additional context when the knowledge base
        yields no results.
        """
        self.log(f"Searching for: {query}")
        kb_results = self.search_memory(query)

        if kb_results:
            snippets = [str(r.get("value", "")) for r in kb_results]
            self.log(f"Found {len(snippets)} memory entries")
        else:
            # Simulate a web/knowledge search via LLM
            prompt = (
                f"You are a research assistant with broad knowledge.\n"
                f"Provide a concise, factual answer to the following query:\n\n"
                f"{query}\n\n"
                "Include relevant details, dates, and sources where possible."
            )
            answer = self.call_ollama(prompt)
            snippets = [answer]
            self.store_memory(f"search:{query}", answer, tags=["search"])

        return {"query": query, "results": snippets, "count": len(snippets)}

    def summarize(self, text: str, max_sentences: int = 5) -> str:
        """
        Summarise *text* in at most *max_sentences* sentences.
        """
        self.log(f"Summarising text ({len(text)} chars)…")
        prompt = (
            f"Summarise the following text in no more than {max_sentences} sentences. "
            "Be concise and preserve the key points.\n\n"
            f"{text}"
        )
        summary = self.call_ollama(prompt)
        self.store_memory("summary", summary, tags=["summary"])
        return summary

    def extract_facts(self, text: str) -> List[str]:
        """
        Extract a list of key facts from *text*.

        Returns a list of fact strings.
        """
        self.log(f"Extracting facts from text ({len(text)} chars)…")
        prompt = (
            "Extract the most important facts from the text below.\n"
            "Return each fact on a new line starting with '- '.\n\n"
            f"{text}"
        )
        response = self.call_ollama(prompt)
        facts = [
            line.lstrip("- ").strip()
            for line in response.splitlines()
            if line.strip().startswith("-")
        ]
        if not facts:
            # Fallback: split by sentence
            facts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", response) if s.strip()]
        self.store_memory("facts", facts, tags=["facts"])
        return facts

    def compile_report(self, topic: str) -> Dict[str, Any]:
        """
        Compile a comprehensive research report on *topic*.

        Returns a structured dict with sections: overview, key_facts,
        analysis, and recommendations.
        """
        self.log(f"Compiling report on: {topic}")

        # Step 1 – overview
        overview_prompt = (
            f"Write a comprehensive overview of the topic: '{topic}'.\n"
            "Cover background, current state, and significance."
        )
        overview = self.call_ollama(overview_prompt)

        # Step 2 – key facts
        facts = self.extract_facts(overview)

        # Step 3 – analysis
        analysis_prompt = (
            f"Provide an in-depth analysis of '{topic}', including trends, "
            "challenges, opportunities, and future outlook."
        )
        analysis = self.call_ollama(analysis_prompt)

        # Step 4 – recommendations
        rec_prompt = (
            f"Based on your knowledge of '{topic}', provide actionable "
            "recommendations for practitioners or decision-makers."
        )
        recommendations = self.call_ollama(rec_prompt)

        report = {
            "topic": topic,
            "overview": overview,
            "key_facts": facts,
            "analysis": analysis,
            "recommendations": recommendations,
        }
        self.store_memory(f"report:{topic}", report, tags=["report"])
        return report

    def add_to_knowledge_base(self, key: str, content: str) -> None:
        """Add a document to the internal knowledge base."""
        if key not in self._knowledge_base:
            self._knowledge_base[key] = []
        self._knowledge_base[key].append(content)
        self.store_memory(key, content, tags=["kb"])
        self.log(f"Added entry to knowledge base under key='{key}'")

    def compare_topics(self, topic_a: str, topic_b: str) -> str:
        """Return a comparative analysis of two topics."""
        prompt = (
            f"Compare and contrast '{topic_a}' and '{topic_b}'.\n"
            "Highlight similarities, differences, advantages, and disadvantages."
        )
        self.log(f"Comparing '{topic_a}' vs '{topic_b}'")
        return self.call_ollama(prompt)
