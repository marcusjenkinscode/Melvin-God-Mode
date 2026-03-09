"""
CoderAgent – specialises in code generation, file writing, and code review.
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.agent_base import AgentBase

# Default model preference order (first available is used)
DEFAULT_MODELS = ["deepseek-coder", "codellama", "llama3"]
DEFAULT_MODEL = DEFAULT_MODELS[0]

SUPPORTED_LANGUAGES = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "bash": ".sh",
    "shell": ".sh",
    "go": ".go",
    "rust": ".rs",
    "java": ".java",
    "c": ".c",
    "cpp": ".cpp",
    "c++": ".cpp",
    "yaml": ".yaml",
    "json": ".json",
    "dockerfile": "",
    "sql": ".sql",
    "html": ".html",
    "css": ".css",
}


class CoderAgent(AgentBase):
    """Agent that generates, writes, reviews, and tests code."""

    def __init__(
        self,
        name: str = "CoderAgent",
        model: str = DEFAULT_MODEL,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(name, model, config)
        self.default_output_dir: str = self.config.get("output_dir", "/tmp/melvin_code")
        os.makedirs(self.default_output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # AgentBase abstract methods
    # ------------------------------------------------------------------

    def run(self, task: str) -> Dict[str, Any]:
        """
        High-level entry point.  Accepts a plain-English coding task,
        generates code, optionally writes it to disk, and returns a result
        dict containing the code and suggested tests.
        """
        self.set_status(self.STATUS_RUNNING)
        start = time.time()
        self.log(f"Running task: {task}")

        try:
            code = self.generate_code(task)
            tests = self.suggest_tests(code, task)
            result = {
                "task": task,
                "code": code,
                "suggested_tests": tests,
                "model": self.model,
            }
            self.observe(result)
            self.set_status(self.STATUS_IDLE)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Task failed: {exc}", "error")
            self.set_status(self.STATUS_ERROR)
            result = {"task": task, "error": str(exc)}

        self._record_task(task, result, time.time() - start)
        return result

    def think(self, prompt: str) -> str:
        return self.call_ollama(prompt)

    def act(self, action: Dict[str, Any]) -> Any:
        """
        Dispatch a structured action dict.
        Supported action types: generate_code, write_file, review_code.
        """
        action_type = action.get("type")
        if action_type == "generate_code":
            return self.generate_code(action["requirements"])
        if action_type == "write_file":
            return self.write_file(action["path"], action["content"])
        if action_type == "review_code":
            return self.review_code(action["code"])
        self.log(f"Unknown action type: {action_type}", "warning")
        return None

    def observe(self, result: Any) -> None:
        """Store the latest result in memory."""
        if isinstance(result, dict):
            self.store_memory("last_result", result, tags=["result"])

    # ------------------------------------------------------------------
    # Core capabilities
    # ------------------------------------------------------------------

    def generate_code(self, requirements: str, language: str = "python") -> str:
        """
        Generate code from *requirements*.

        Returns the raw code string produced by the model.
        """
        lang = language.lower()
        prompt = (
            f"You are an expert software engineer.\n"
            f"Write clean, production-quality {lang} code that satisfies the "
            f"following requirements:\n\n{requirements}\n\n"
            f"Return only the code without explanation or markdown fences."
        )
        self.log(f"Generating {lang} code for requirements: {requirements[:80]}…")
        code = self.call_ollama(prompt)
        self.store_memory("generated_code", {"requirements": requirements, "code": code})
        return code

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """
        Write *content* to *path*, creating parent directories as needed.

        Returns a status dict.
        """
        target = Path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            self.log(f"Wrote {len(content)} bytes to '{path}'")
            result = {"success": True, "path": str(target.resolve()), "bytes": len(content)}
        except OSError as exc:
            self.log(f"Failed to write '{path}': {exc}", "error")
            result = {"success": False, "path": path, "error": str(exc)}
        self.store_memory("file_writes", result, tags=["file"])
        return result

    def review_code(self, code: str) -> Dict[str, Any]:
        """
        Review *code* for correctness, style, and potential bugs.

        Returns a dict with the review summary and an improved code version.
        """
        prompt = (
            "You are a senior code reviewer.\n"
            "Review the following code for correctness, performance, security, "
            "and style. List issues found and then provide an improved version.\n\n"
            f"```\n{code}\n```\n\n"
            "Format your response as:\n"
            "ISSUES:\n<bullet list of issues>\n\n"
            "IMPROVED CODE:\n<improved code>"
        )
        self.log("Reviewing code…")
        response = self.call_ollama(prompt)
        parts = response.split("IMPROVED CODE:", 1)
        issues_section = parts[0].replace("ISSUES:", "").strip() if len(parts) >= 1 else ""
        improved = parts[1].strip() if len(parts) == 2 else code

        return {
            "original_code": code,
            "issues": issues_section,
            "improved_code": improved,
        }

    def suggest_tests(self, code: str, context: str = "") -> str:
        """Return a string containing suggested unit tests for *code*."""
        prompt = (
            "You are a test engineer.\n"
            "Given the following code, write comprehensive unit tests.\n"
            f"Context: {context}\n\n"
            f"```\n{code}\n```\n\n"
            "Return only the test code without markdown fences."
        )
        self.log("Generating test suggestions…")
        return self.call_ollama(prompt)

    def detect_language(self, code: str) -> str:
        """Heuristically detect the programming language of *code*."""
        indicators: Dict[str, List[str]] = {
            "python": ["def ", "import ", "class ", "print(", "elif "],
            "javascript": ["const ", "let ", "var ", "function ", "=>", "console.log"],
            "typescript": ["interface ", ": string", ": number", ": boolean", "export "],
            "bash": ["#!/bin/bash", "echo ", "fi\n", "then\n", "do\n"],
            "go": ["func ", "package ", "import (", ":= ", "fmt."],
            "rust": ["fn ", "let mut", "use std", "impl ", "->"],
            "java": ["public class", "void main", "System.out", "import java"],
            "sql": ["SELECT ", "FROM ", "WHERE ", "INSERT INTO", "CREATE TABLE"],
        }
        scores: Dict[str, int] = {}
        for lang, hints in indicators.items():
            scores[lang] = sum(1 for h in hints if h in code)
        if not any(scores.values()):
            return "unknown"
        return max(scores, key=lambda k: scores[k])

    def format_code(self, code: str, language: str = "") -> str:
        """Ask the model to format / prettify *code*."""
        lang = language or self.detect_language(code)
        prompt = (
            f"Format and prettify the following {lang} code according to best practices. "
            "Return only the formatted code.\n\n"
            f"```\n{code}\n```"
        )
        return self.call_ollama(prompt)
