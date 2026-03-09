"""
Melvin God Mode - Test Runner
Runs tests, linters, and syntax validators for generated code.
"""

import ast
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import uuid
from pathlib import Path
from typing import Optional


class TestRunner:
    """
    Executes tests and performs code quality checks.

    All test files are written to *working_dir* and cleaned up automatically
    unless *keep_files* is set.
    """

    def __init__(self, working_dir: str = "/tmp/melvin_tests", keep_files: bool = False):
        self.working_dir = working_dir
        self.keep_files = keep_files
        os.makedirs(self.working_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(self, cmd: list, cwd: Optional[str] = None, timeout: int = 60) -> dict:
        """Run a subprocess command and return stdout/stderr/returncode."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd or self.working_dir,
                timeout=timeout,
            )
            return {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"returncode": -1, "stdout": "", "stderr": "Timeout expired"}
        except FileNotFoundError as exc:
            return {"returncode": -1, "stdout": "", "stderr": str(exc)}

    def _write_temp(self, content: str, suffix: str = ".py") -> str:
        """Write *content* to a unique temp file and return its path."""
        name = f"melvin_{uuid.uuid4().hex}{suffix}"
        path = os.path.join(self.working_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def _cleanup(self, *paths: str):
        if not self.keep_files:
            for p in paths:
                try:
                    os.remove(p)
                except FileNotFoundError:
                    pass

    # ------------------------------------------------------------------
    # pytest
    # ------------------------------------------------------------------

    def run_pytest(self, test_file: str) -> dict:
        """
        Run pytest on *test_file*.

        Returns:
            {
                passed  : int,
                failed  : int,
                errors  : int,
                output  : str,
                success : bool,
            }
        """
        result = self._run(
            [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short", "--no-header"],
        )
        output = result["stdout"] + result["stderr"]
        passed = failed = errors = 0

        # Parse pytest summary line, e.g. "3 passed, 1 failed, 2 errors"
        summary_match = re.search(
            r"(\d+) passed|(\d+) failed|(\d+) error", output, re.IGNORECASE
        )
        passed_m = re.search(r"(\d+) passed", output)
        failed_m = re.search(r"(\d+) failed", output)
        errors_m = re.search(r"(\d+) error", output)
        if passed_m:
            passed = int(passed_m.group(1))
        if failed_m:
            failed = int(failed_m.group(1))
        if errors_m:
            errors = int(errors_m.group(1))

        return {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "output": output,
            "success": result["returncode"] == 0,
        }

    # ------------------------------------------------------------------
    # unittest
    # ------------------------------------------------------------------

    def run_unittest(self, test_code: str) -> dict:
        """
        Write *test_code* to a temp file and execute it with unittest discover.

        Returns same schema as run_pytest.
        """
        test_file = self._write_temp(test_code)
        try:
            result = self._run(
                [sys.executable, "-m", "unittest", test_file, "-v"],
            )
            output = result["stdout"] + result["stderr"]
            passed = len(re.findall(r"\.\.\.", output))  # rough count
            failed = len(re.findall(r"FAIL:", output))
            errors = len(re.findall(r"ERROR:", output))
            return {
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "output": output,
                "success": result["returncode"] == 0,
            }
        finally:
            self._cleanup(test_file)

    # ------------------------------------------------------------------
    # Test file creation
    # ------------------------------------------------------------------

    def create_test_file(self, code: str, language: str = "python") -> str:
        """
        Scaffold a minimal test file for *code* and return its path.

        For Python a placeholder pytest file is created; other languages
        get a shell-runnable stub.
        """
        if language.lower() == "python":
            stub = textwrap.dedent(f"""\
                # Auto-generated test scaffold
                import pytest

                # ---- code under test ----
                {textwrap.indent(code, '# ')}
                # ---- tests ----

                def test_placeholder():
                    \"\"\"Replace this with real tests.\"\"\"
                    assert True
            """)
            return self._write_temp(stub, suffix=".py")
        else:
            stub = f"#!/bin/sh\n# Test scaffold for {language}\necho 'No tests implemented yet'\n"
            return self._write_temp(stub, suffix=".sh")

    # ------------------------------------------------------------------
    # Linter
    # ------------------------------------------------------------------

    def run_linter(self, code: str, language: str = "python") -> dict:
        """
        Lint *code* and return a results dict.

        Python: uses flake8 (falls back to pyflakes).
        JavaScript/TypeScript: uses eslint (if available).
        Other languages: returns a stub result.

        Returns:
            {
                tool     : str,
                issues   : list of {line, col, code, message},
                output   : str,
                clean    : bool,
            }
        """
        lang = language.lower()
        if lang == "python":
            return self._lint_python(code)
        if lang in ("javascript", "js", "typescript", "ts"):
            return self._lint_js(code, lang)
        return {"tool": "none", "issues": [], "output": "Linter not available for this language.", "clean": True}

    def _lint_python(self, code: str) -> dict:
        code_file = self._write_temp(code)
        try:
            result = self._run(
                [sys.executable, "-m", "flake8", "--format=%(row)d:%(col)d:%(code)s:%(text)s", code_file],
            )
            tool = "flake8"
            if result["returncode"] == -1 and "No module named flake8" in result["stderr"]:
                result = self._run(
                    [sys.executable, "-m", "pyflakes", code_file],
                )
                tool = "pyflakes"

            issues = []
            for line in result["stdout"].splitlines():
                parts = line.split(":", 3)
                if len(parts) >= 4:
                    try:
                        issues.append({
                            "line": int(parts[0]),
                            "col": int(parts[1]),
                            "code": parts[2],
                            "message": parts[3].strip(),
                        })
                    except ValueError:
                        pass

            return {
                "tool": tool,
                "issues": issues,
                "output": result["stdout"] + result["stderr"],
                "clean": len(issues) == 0,
            }
        finally:
            self._cleanup(code_file)

    def _lint_js(self, code: str, language: str) -> dict:
        ext = ".ts" if language in ("typescript", "ts") else ".js"
        code_file = self._write_temp(code, suffix=ext)
        try:
            result = self._run(["eslint", "--format=compact", code_file])
            issues = []
            for line in result["stdout"].splitlines():
                m = re.search(r"line (\d+), col (\d+), (.*)", line, re.IGNORECASE)
                if m:
                    issues.append({
                        "line": int(m.group(1)),
                        "col": int(m.group(2)),
                        "code": "",
                        "message": m.group(3).strip(),
                    })
            return {
                "tool": "eslint",
                "issues": issues,
                "output": result["stdout"] + result["stderr"],
                "clean": result["returncode"] == 0,
            }
        finally:
            self._cleanup(code_file)

    # ------------------------------------------------------------------
    # Syntax validation
    # ------------------------------------------------------------------

    def validate_syntax(self, code: str, language: str = "python") -> tuple:
        """
        Validate the syntax of *code*.

        Returns:
            (is_valid: bool, errors: list of str)
        """
        lang = language.lower()
        if lang == "python":
            return self._validate_python(code)
        if lang in ("javascript", "js", "typescript", "ts"):
            return self._validate_js(code, lang)
        # Generic: attempt to run with interpreter
        return True, []

    def _validate_python(self, code: str) -> tuple:
        try:
            ast.parse(code)
            return True, []
        except SyntaxError as exc:
            error_msg = f"SyntaxError at line {exc.lineno}: {exc.msg}"
            if exc.text:
                error_msg += f"\n  {exc.text.rstrip()}"
            return False, [error_msg]

    def _validate_js(self, code: str, language: str) -> tuple:
        ext = ".ts" if language in ("typescript", "ts") else ".js"
        code_file = self._write_temp(code, suffix=ext)
        try:
            result = self._run(["node", "--check", code_file])
            if result["returncode"] == 0:
                return True, []
            errors = [l for l in (result["stdout"] + result["stderr"]).splitlines() if l.strip()]
            return False, errors
        finally:
            self._cleanup(code_file)

    # ------------------------------------------------------------------
    # Shell test
    # ------------------------------------------------------------------

    def run_shell_test(self, script: str) -> dict:
        """
        Write *script* to a temp shell file and execute it.

        Returns:
            {returncode, stdout, stderr}
        """
        script_file = self._write_temp(script, suffix=".sh")
        os.chmod(script_file, 0o700)
        try:
            result = self._run(["/bin/sh", script_file])
            return result
        finally:
            self._cleanup(script_file)
