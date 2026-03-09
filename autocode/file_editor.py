"""
Melvin God Mode - File Editor
Safe file and directory operations with path-traversal protection.
"""

import fnmatch
import glob as _glob
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


class FileEditor:
    """
    Safe file and directory operations anchored to *base_dir*.

    All paths are resolved and validated to be within *base_dir* before
    any operation is performed, preventing directory-traversal attacks.
    """

    def __init__(self, base_dir: str = "/"):
        self.base_dir = str(Path(base_dir).resolve())

    # ------------------------------------------------------------------
    # Path validation
    # ------------------------------------------------------------------

    def _safe_path(self, path: str) -> str:
        """
        Resolve *path* and raise ValueError if it escapes *base_dir*.

        Returns the absolute, resolved path as a string.
        """
        resolved = str(Path(self.base_dir, path).resolve())
        if not resolved.startswith(self.base_dir):
            raise ValueError(
                f"Path traversal detected: '{path}' resolves outside base_dir '{self.base_dir}'"
            )
        return resolved

    # ------------------------------------------------------------------
    # Read / Write
    # ------------------------------------------------------------------

    def read(self, path: str) -> str:
        """Read and return the full contents of a file."""
        safe = self._safe_path(path)
        with open(safe, "r", encoding="utf-8") as fh:
            return fh.read()

    def write(self, path: str, content: str) -> bool:
        """Overwrite (or create) a file with *content*. Returns True on success."""
        try:
            safe = self._safe_path(path)
            os.makedirs(os.path.dirname(safe) or ".", exist_ok=True)
            with open(safe, "w", encoding="utf-8") as fh:
                fh.write(content)
            return True
        except Exception as exc:
            print(f"[FileEditor] write error: {exc}")
            return False

    def append(self, path: str, content: str) -> bool:
        """Append *content* to a file. Creates the file if it does not exist."""
        try:
            safe = self._safe_path(path)
            os.makedirs(os.path.dirname(safe) or ".", exist_ok=True)
            with open(safe, "a", encoding="utf-8") as fh:
                fh.write(content)
            return True
        except Exception as exc:
            print(f"[FileEditor] append error: {exc}")
            return False

    def replace(self, path: str, old_text: str, new_text: str) -> bool:
        """
        Replace the first occurrence of *old_text* with *new_text* in a file.

        Returns True if a replacement was made, False otherwise.
        """
        try:
            content = self.read(path)
            if old_text not in content:
                return False
            new_content = content.replace(old_text, new_text, 1)
            return self.write(path, new_content)
        except Exception as exc:
            print(f"[FileEditor] replace error: {exc}")
            return False

    def delete(self, path: str) -> bool:
        """Delete a file. Returns True on success."""
        try:
            safe = self._safe_path(path)
            os.remove(safe)
            return True
        except Exception as exc:
            print(f"[FileEditor] delete error: {exc}")
            return False

    # ------------------------------------------------------------------
    # Directory operations
    # ------------------------------------------------------------------

    def create_directory(self, path: str) -> bool:
        """Create a directory (and all parents). Returns True on success."""
        try:
            safe = self._safe_path(path)
            os.makedirs(safe, exist_ok=True)
            return True
        except Exception as exc:
            print(f"[FileEditor] create_directory error: {exc}")
            return False

    def list_files(self, path: str = ".", pattern: str = "*") -> list:
        """
        List files in *path* matching *pattern* (supports glob wildcards).

        Returns a sorted list of relative paths.
        """
        safe = self._safe_path(path)
        matches = []
        for entry in _glob.glob(os.path.join(safe, "**", pattern), recursive=True):
            if os.path.isfile(entry):
                rel = os.path.relpath(entry, self.base_dir)
                matches.append(rel)
        return sorted(matches)

    def search_in_files(self, directory: str, pattern: str) -> list:
        """
        Search for regex *pattern* in every file under *directory*.

        Returns a list of dicts: {file, line, content}.
        """
        safe_dir = self._safe_path(directory)
        regex = re.compile(pattern)
        results = []
        for root, _, files in os.walk(safe_dir):
            for fname in files:
                filepath = os.path.join(root, fname)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                        for lineno, line in enumerate(fh, start=1):
                            if regex.search(line):
                                results.append({
                                    "file": os.path.relpath(filepath, self.base_dir),
                                    "line": lineno,
                                    "content": line.rstrip(),
                                })
                except (PermissionError, IsADirectoryError):
                    continue
        return results

    # ------------------------------------------------------------------
    # Backup / Restore
    # ------------------------------------------------------------------

    def backup(self, path: str) -> str:
        """
        Create a timestamped backup of *path*.

        Returns the backup file path.
        """
        safe = self._safe_path(path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{safe}.backup_{timestamp}"
        shutil.copy2(safe, backup_path)
        return os.path.relpath(backup_path, self.base_dir)

    def restore(self, backup_path: str, original_path: str) -> bool:
        """
        Restore *original_path* from *backup_path*.

        Returns True on success.
        """
        try:
            safe_backup = self._safe_path(backup_path)
            safe_original = self._safe_path(original_path)
            shutil.copy2(safe_backup, safe_original)
            return True
        except Exception as exc:
            print(f"[FileEditor] restore error: {exc}")
            return False
