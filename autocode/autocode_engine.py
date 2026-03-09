"""
Melvin God Mode - AutoCode Engine
AI-powered code generation, improvement, documentation, and analysis.
"""

import ast
import json
import re
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore


_OLLAMA_DEFAULT_HOST = "http://localhost:11434"

# Rough cyclomatic-complexity analyser for Python (AST-based)
_BRANCH_NODES = (
    ast.If, ast.For, ast.While, ast.ExceptHandler,
    ast.With, ast.Assert, ast.comprehension,
)


class AutoCodeEngine:
    """
    AI-powered code engine backed by an Ollama model.

    All generation methods return plain strings; no parsing or execution
    is performed here – that is the responsibility of the caller / TestRunner.
    """

    def __init__(
        self,
        model: str = "deepseek-coder",
        ollama_host: str = _OLLAMA_DEFAULT_HOST,
        temperature: float = 0.2,
        timeout: int = 120,
    ):
        if requests is None:
            raise ImportError("requests is required. pip install requests")
        self.model = model
        self.ollama_host = ollama_host.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _chat(self, system: str, user: str) -> str:
        """Send a chat request to Ollama and return the assistant reply."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        resp = requests.post(
            f"{self.ollama_host}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()

    @staticmethod
    def _extract_code_block(text: str, language: str = "") -> str:
        """Extract the first fenced code block from *text*, or return *text* as-is."""
        pattern = rf"```(?:{language})?\s*\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Fallback: strip any leading/trailing backtick fences
        cleaned = re.sub(r"^```[^\n]*\n?", "", text.strip())
        cleaned = re.sub(r"\n?```$", "", cleaned.strip())
        return cleaned.strip()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, requirements: str, language: str = "python") -> str:
        """
        Generate code from *requirements*.

        Args:
            requirements: Natural-language description of what to build.
            language:     Target programming language.

        Returns:
            Generated source code as a string.
        """
        system = (
            f"You are an expert {language} developer. "
            "Write clean, well-structured, production-quality code. "
            "Return ONLY the code inside a single fenced code block with no extra commentary."
        )
        user = f"Write {language} code that satisfies the following requirements:\n\n{requirements}"
        reply = self._chat(system, user)
        return self._extract_code_block(reply, language)

    def improve(self, code: str, feedback: str) -> str:
        """
        Improve *code* based on *feedback*.

        Returns improved source code.
        """
        system = (
            "You are a senior code reviewer and developer. "
            "Improve the provided code according to the feedback. "
            "Return ONLY the improved code in a fenced code block."
        )
        user = f"Feedback:\n{feedback}\n\nOriginal code:\n```\n{code}\n```"
        reply = self._chat(system, user)
        return self._extract_code_block(reply)

    def complete(self, partial_code: str) -> str:
        """
        Complete *partial_code* — fill in TODOs, stubs, and missing logic.

        Returns the completed source code.
        """
        system = (
            "You are an expert developer. Complete the provided partial code. "
            "Preserve all existing logic and fill in any TODOs, stubs, or incomplete sections. "
            "Return ONLY the completed code in a fenced code block."
        )
        user = f"Complete the following partial code:\n```\n{partial_code}\n```"
        reply = self._chat(system, user)
        return self._extract_code_block(reply)

    def document(self, code: str) -> str:
        """
        Add comprehensive docstrings and inline comments to *code*.

        Returns the documented source code.
        """
        system = (
            "You are a technical writer and developer. "
            "Add clear, concise docstrings (Google style) and inline comments to the code. "
            "Do NOT change any logic. Return ONLY the documented code in a fenced code block."
        )
        user = f"Add documentation to this code:\n```\n{code}\n```"
        reply = self._chat(system, user)
        return self._extract_code_block(reply)

    def refactor(self, code: str) -> str:
        """
        Refactor *code* for readability, performance, and best practices.

        Returns the refactored source code.
        """
        system = (
            "You are a senior software engineer specialising in code quality. "
            "Refactor the provided code: improve naming, reduce duplication, apply SOLID principles, "
            "and optimise where appropriate. Preserve the external interface. "
            "Return ONLY the refactored code in a fenced code block."
        )
        user = f"Refactor this code:\n```\n{code}\n```"
        reply = self._chat(system, user)
        return self._extract_code_block(reply)

    def generate_tests(self, code: str) -> str:
        """
        Generate a comprehensive pytest test suite for *code*.

        Returns a string containing the test source code.
        """
        system = (
            "You are a senior QA engineer. Write a thorough pytest test suite for the provided code. "
            "Cover happy paths, edge cases, and error conditions. "
            "Use mocking where external dependencies are involved. "
            "Return ONLY the test code in a fenced Python code block."
        )
        user = f"Write pytest tests for this code:\n```python\n{code}\n```"
        reply = self._chat(system, user)
        return self._extract_code_block(reply, "python")

    def analyze_complexity(self, code: str) -> dict:
        """
        Analyse the cyclomatic complexity of Python *code*.

        Returns a dict with keys:
            functions      : list of {name, complexity, line}
            total_complexity : int
            average_complexity : float
            lines_of_code  : int
            blank_lines    : int
            comment_lines  : int
            assessment     : str  ("low" | "medium" | "high" | "very_high")
            warnings       : list of str
        """
        result = {
            "functions": [],
            "total_complexity": 0,
            "average_complexity": 0.0,
            "lines_of_code": 0,
            "blank_lines": 0,
            "comment_lines": 0,
            "assessment": "unknown",
            "warnings": [],
        }

        lines = code.splitlines()
        result["lines_of_code"] = len(lines)
        result["blank_lines"] = sum(1 for l in lines if not l.strip())
        result["comment_lines"] = sum(1 for l in lines if l.strip().startswith("#"))

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            result["warnings"].append(f"Syntax error – cannot analyse: {exc}")
            return result

        func_complexities = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = 1  # base path
                for child in ast.walk(node):
                    if isinstance(child, _BRANCH_NODES):
                        cc += 1
                    elif isinstance(child, ast.BoolOp):
                        cc += len(child.values) - 1
                func_complexities.append(cc)
                result["functions"].append({
                    "name": node.name,
                    "complexity": cc,
                    "line": node.lineno,
                })
                if cc > 10:
                    result["warnings"].append(
                        f"Function '{node.name}' has high complexity ({cc}). Consider refactoring."
                    )

        if func_complexities:
            result["total_complexity"] = sum(func_complexities)
            result["average_complexity"] = round(
                result["total_complexity"] / len(func_complexities), 2
            )

        avg = result["average_complexity"]
        if avg <= 5:
            result["assessment"] = "low"
        elif avg <= 10:
            result["assessment"] = "medium"
        elif avg <= 20:
            result["assessment"] = "high"
        else:
            result["assessment"] = "very_high"

        return result
