"""
DebuggerAgent – code debugging, error analysis, and code explanation.
"""

import ast
import re
import time
from typing import Any, Dict, List, Optional

from agents.agent_base import AgentBase

DEFAULT_MODEL = "deepseek-coder"
FALLBACK_MODEL = "codellama"


class DebuggerAgent(AgentBase):
    """Agent that analyses errors, suggests fixes, and explains code."""

    def __init__(
        self,
        name: str = "DebuggerAgent",
        model: str = DEFAULT_MODEL,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(name, model, config)

    # ------------------------------------------------------------------
    # AgentBase abstract methods
    # ------------------------------------------------------------------

    def run(self, task: str) -> Dict[str, Any]:
        """
        Accept a task string describing what to debug and return analysis.
        The task may be an error message, a code snippet, or a description.
        """
        self.set_status(self.STATUS_RUNNING)
        start = time.time()
        self.log(f"Debugging task: {task}")

        try:
            analysis = self.analyze_error(task)
            result = {"task": task, "analysis": analysis, "model": self.model}
            self.observe(result)
            self.set_status(self.STATUS_IDLE)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Debugging task failed: {exc}", "error")
            self.set_status(self.STATUS_ERROR)
            result = {"task": task, "error": str(exc)}

        self._record_task(task, result, time.time() - start)
        return result

    def think(self, prompt: str) -> str:
        return self.call_ollama(prompt)

    def act(self, action: Dict[str, Any]) -> Any:
        action_type = action.get("type")
        if action_type == "analyze_error":
            return self.analyze_error(action["error_text"])
        if action_type == "suggest_fix":
            return self.suggest_fix(action["code"], action["error"])
        if action_type == "trace_execution":
            return self.trace_execution(action["code"])
        if action_type == "find_bugs":
            return self.find_bugs(action["code"])
        if action_type == "explain_code":
            return self.explain_code(action["code"])
        self.log(f"Unknown action type: {action_type}", "warning")
        return None

    def observe(self, result: Any) -> None:
        if isinstance(result, dict):
            self.store_memory("last_debug_result", result, tags=["debug"])

    # ------------------------------------------------------------------
    # Core capabilities
    # ------------------------------------------------------------------

    def analyze_error(self, error_text: str) -> Dict[str, Any]:
        """
        Analyse an error message and return structured diagnosis.

        Returns dict with keys: error_type, root_cause, explanation,
        possible_fixes, severity.
        """
        self.log(f"Analysing error: {error_text[:120]}…")

        # Quick static classification
        error_type = self._classify_error(error_text)

        prompt = (
            "You are an expert debugger.\n"
            "Analyse the following error message and provide a structured diagnosis.\n"
            "Return JSON with keys:\n"
            "  error_type (string),\n"
            "  root_cause (string),\n"
            "  explanation (string, 2-3 sentences),\n"
            "  possible_fixes (list of strings),\n"
            "  severity (critical/high/medium/low)\n\n"
            f"Error:\n{error_text}"
        )
        response = self.call_ollama(prompt)

        import json  # noqa: PLC0415
        data: Dict[str, Any] = {}
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1:
                data = json.loads(response[start:end])
        except Exception:  # noqa: BLE001
            data = {}

        result = {
            "error_text": error_text[:500],
            "error_type": data.get("error_type", error_type),
            "root_cause": data.get("root_cause", ""),
            "explanation": data.get("explanation", response[:400]),
            "possible_fixes": data.get("possible_fixes", []),
            "severity": data.get("severity", "medium"),
        }
        self.store_memory("error_analysis", result, tags=["error"])
        return result

    def suggest_fix(self, code: str, error: str) -> Dict[str, Any]:
        """
        Suggest a corrected version of *code* given *error*.
        """
        self.log(f"Suggesting fix for error: {error[:80]}…")
        prompt = (
            "You are a senior software engineer.\n"
            "The following code produces an error. Provide the fixed code.\n\n"
            f"CODE:\n```\n{code}\n```\n\n"
            f"ERROR:\n{error}\n\n"
            "Respond with:\n"
            "EXPLANATION: <brief explanation of the bug>\n\n"
            "FIXED CODE:\n<corrected code only, no markdown fences>"
        )
        response = self.call_ollama(prompt)

        parts = response.split("FIXED CODE:", 1)
        explanation = ""
        fixed_code = code  # fallback to original

        if "EXPLANATION:" in parts[0]:
            explanation = parts[0].replace("EXPLANATION:", "").strip()
        if len(parts) == 2:
            fixed_code = parts[1].strip()

        result = {
            "original_code": code,
            "error": error,
            "explanation": explanation,
            "fixed_code": fixed_code,
        }
        self.store_memory("fix_suggestion", result, tags=["fix"])
        return result

    def trace_execution(self, code: str) -> Dict[str, Any]:
        """
        Trace through *code* step-by-step and return an execution narrative.

        For Python code, attempts a static AST walk first.
        """
        self.log("Tracing code execution…")

        # Attempt Python AST analysis
        ast_info = self._python_ast_trace(code)

        prompt = (
            "You are a code execution tracer.\n"
            "Walk through the following code step by step, explaining what "
            "each significant line does and what the program state looks like "
            "after each step.\n\n"
            f"```\n{code}\n```"
        )
        narrative = self.call_ollama(prompt)

        result = {
            "code": code[:500],
            "ast_info": ast_info,
            "narrative": narrative,
        }
        self.store_memory("trace", result, tags=["trace"])
        return result

    def find_bugs(self, code: str) -> List[Dict[str, Any]]:
        """
        Identify potential bugs in *code*.

        Returns a list of bug dicts with keys: line, type, description, fix.
        """
        self.log(f"Searching for bugs ({len(code)} chars)…")

        # Static Python check
        static_bugs = self._python_static_check(code)

        prompt = (
            "You are a code review expert specialising in bug detection.\n"
            "Find all bugs, potential runtime errors, logic flaws, and security "
            "issues in the following code.\n"
            "Return JSON array: [{\"line\": int_or_null, \"type\": str, "
            "\"description\": str, \"fix\": str}]\n\n"
            f"```\n{code}\n```"
        )
        response = self.call_ollama(prompt)

        llm_bugs: List[Dict[str, Any]] = []
        try:
            import json  # noqa: PLC0415
            start = response.find("[")
            end = response.rfind("]") + 1
            if start != -1:
                llm_bugs = json.loads(response[start:end])
        except Exception:  # noqa: BLE001
            llm_bugs = [{"line": None, "type": "unknown", "description": response[:300], "fix": "Review manually"}]

        all_bugs = static_bugs + llm_bugs
        self.store_memory("bugs_found", all_bugs, tags=["bugs"])
        return all_bugs

    def explain_code(self, code: str, detail_level: str = "medium") -> str:
        """
        Explain what *code* does in plain English.

        *detail_level* can be 'brief', 'medium', or 'detailed'.
        """
        self.log(f"Explaining code (detail={detail_level})…")
        verbosity = {
            "brief": "in 2-3 sentences",
            "medium": "in a short paragraph covering purpose, logic, and output",
            "detailed": "in detail covering every function, loop, and condition",
        }.get(detail_level, "in a short paragraph")

        prompt = (
            f"Explain the following code {verbosity}. "
            "Use plain English suitable for a non-expert developer.\n\n"
            f"```\n{code}\n```"
        )
        explanation = self.call_ollama(prompt)
        self.store_memory("code_explanation", explanation, tags=["explain"])
        return explanation

    def compare_versions(self, code_before: str, code_after: str) -> str:
        """Explain the differences between two versions of code."""
        prompt = (
            "Compare the two code versions below and explain what changed, "
            "why the change improves (or worsens) the code, and any risks "
            "introduced.\n\n"
            f"BEFORE:\n```\n{code_before}\n```\n\n"
            f"AFTER:\n```\n{code_after}\n```"
        )
        return self.call_ollama(prompt)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _classify_error(self, error_text: str) -> str:
        """Heuristically classify a common error type."""
        patterns = {
            "SyntaxError": r"SyntaxError",
            "TypeError": r"TypeError",
            "ValueError": r"ValueError",
            "AttributeError": r"AttributeError",
            "ImportError": r"ImportError|ModuleNotFoundError",
            "IndexError": r"IndexError|list index out of range",
            "KeyError": r"KeyError",
            "FileNotFoundError": r"FileNotFoundError|No such file",
            "PermissionError": r"PermissionError",
            "ConnectionError": r"ConnectionError|ConnectionRefused",
            "TimeoutError": r"TimeoutError|timed out",
            "MemoryError": r"MemoryError|out of memory",
            "SegmentationFault": r"Segmentation fault|SIGSEGV",
            "NullPointerException": r"NullPointerException|NoneType.*NoneType",
        }
        for error_type, pattern in patterns.items():
            if re.search(pattern, error_text, re.IGNORECASE):
                return error_type
        return "UnknownError"

    def _python_ast_trace(self, code: str) -> Dict[str, Any]:
        """Parse Python code with the AST module for static info."""
        try:
            tree = ast.parse(code)
            functions = [
                node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
            ]
            classes = [
                node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
            ]
            imports = [
                (node.names[0].name if isinstance(node, ast.Import) else node.module)
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
            ]
            return {
                "valid_python": True,
                "functions": functions,
                "classes": classes,
                "imports": [i for i in imports if i],
                "line_count": len(code.splitlines()),
            }
        except SyntaxError as exc:
            return {"valid_python": False, "syntax_error": str(exc)}

    def _python_static_check(self, code: str) -> List[Dict[str, Any]]:
        """Return obvious static bugs found in Python code."""
        bugs: List[Dict[str, Any]] = []
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return [{"line": exc.lineno, "type": "SyntaxError", "description": str(exc), "fix": "Fix syntax"}]

        for node in ast.walk(tree):
            # Bare except clause
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                bugs.append({
                    "line": node.lineno,
                    "type": "BareExcept",
                    "description": "Bare 'except:' clause catches all exceptions including SystemExit.",
                    "fix": "Use 'except Exception as e:' or a specific exception type.",
                })
            # Mutable default argument
            if isinstance(node, ast.FunctionDef):
                for default in node.args.defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        bugs.append({
                            "line": node.lineno,
                            "type": "MutableDefaultArgument",
                            "description": f"Function '{node.name}' uses a mutable default argument.",
                            "fix": "Use None as default and initialise inside the function body.",
                        })
        return bugs
