"""
Melvin God Mode - Model Manager
Manages Ollama models: listing, pulling, deleting, and inspecting.
"""

import json
import os
import fnmatch
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore


RECOMMENDED_MODELS = {
    "general": [
        "llama3.1:8b",
        "mistral:7b",
        "gemma2:9b",
        "phi3:mini",
        "qwen2.5:7b",
    ],
    "coding": [
        "qwen2.5-coder:7b",
        "deepseek-coder:6.7b",
        "codellama:13b",
        "codegemma:7b",
        "starcoder2:7b",
    ],
    "reasoning": [
        "deepseek-r1:7b",
        "qwq:32b",
        "deepseek-r1:14b",
    ],
    "embedding": [
        "nomic-embed-text",
        "mxbai-embed-large",
        "all-minilm",
    ],
    "vision": [
        "llava:7b",
        "llama3.2-vision:11b",
        "moondream",
    ],
    "uncensored": [
        "dolphin-mistral:7b",
        "dolphin-llama3:8b",
    ],
    "tool_use": [
        "llama3-groq-tool-use:8b",
        "firefunction-v2",
    ],
}


class ModelManager:
    """Manages Ollama models via the Ollama REST API."""

    def __init__(self, ollama_host: str = "http://localhost:11434"):
        self.ollama_host = ollama_host.rstrip("/")
        if requests is None:
            raise ImportError("requests library is required. Install with: pip install requests")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, endpoint: str, **kwargs) -> "requests.Response":
        url = f"{self.ollama_host}{endpoint}"
        response = requests.get(url, **kwargs)
        response.raise_for_status()
        return response

    def _post(self, endpoint: str, payload: dict, **kwargs) -> "requests.Response":
        url = f"{self.ollama_host}{endpoint}"
        response = requests.post(url, json=payload, **kwargs)
        response.raise_for_status()
        return response

    def _delete(self, endpoint: str, payload: dict) -> "requests.Response":
        url = f"{self.ollama_host}{endpoint}"
        response = requests.delete(url, json=payload)
        response.raise_for_status()
        return response

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_models(self) -> list:
        """Return a list of model dicts currently available in Ollama."""
        try:
            resp = self._get("/api/tags")
            return resp.json().get("models", [])
        except Exception as exc:
            print(f"[ModelManager] list_models error: {exc}")
            return []

    def pull_model(self, model_name: str) -> bool:
        """
        Stream-pull a model from Ollama.
        Prints progress to stdout and returns True on success.
        """
        print(f"[ModelManager] Pulling '{model_name}' ...")
        try:
            url = f"{self.ollama_host}/api/pull"
            with requests.post(url, json={"name": model_name}, stream=True) as resp:
                resp.raise_for_status()
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    data = json.loads(raw_line)
                    status = data.get("status", "")
                    if "total" in data and "completed" in data:
                        pct = int(data["completed"] / data["total"] * 100)
                        print(f"\r  {status}: {pct}%", end="", flush=True)
                    else:
                        print(f"  {status}")
                    if data.get("status") == "success":
                        print(f"\n[ModelManager] '{model_name}' pulled successfully.")
                        return True
            return True
        except Exception as exc:
            print(f"\n[ModelManager] pull_model error for '{model_name}': {exc}")
            return False

    def delete_model(self, model_name: str) -> bool:
        """Delete a locally stored model. Returns True on success."""
        try:
            self._delete("/api/delete", {"name": model_name})
            print(f"[ModelManager] Deleted '{model_name}'.")
            return True
        except Exception as exc:
            print(f"[ModelManager] delete_model error for '{model_name}': {exc}")
            return False

    def model_info(self, model_name: str) -> dict:
        """Return detailed information about a model."""
        try:
            resp = self._post("/api/show", {"name": model_name})
            return resp.json()
        except Exception as exc:
            print(f"[ModelManager] model_info error for '{model_name}': {exc}")
            return {}

    def is_model_available(self, model_name: str) -> bool:
        """Check whether a model is already pulled locally."""
        models = self.list_models()
        available_names = [m.get("name", "") for m in models]
        if model_name in available_names:
            return True
        # Also try without tag if user omitted it
        base = model_name.split(":")[0]
        return any(m.get("name", "").startswith(base) for m in models)

    def get_recommended_models(self) -> dict:
        """Return the curated recommended-models dict organised by category."""
        return RECOMMENDED_MODELS

    def pull_all_models(self, models_file: Optional[str] = None) -> dict:
        """
        Pull every model listed in *models_file*.
        Lines starting with '#' or blank lines are ignored.
        Returns a summary dict with 'succeeded' and 'failed' lists.
        """
        if models_file is None:
            models_file = os.path.join(os.path.dirname(__file__), "models.txt")

        models_file = str(Path(models_file).resolve())
        if not os.path.isfile(models_file):
            raise FileNotFoundError(f"Models file not found: {models_file}")

        with open(models_file, "r", encoding="utf-8") as fh:
            lines = fh.readlines()

        model_names = [
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("#")
        ]

        succeeded, failed = [], []
        for name in model_names:
            if self.pull_model(name):
                succeeded.append(name)
            else:
                failed.append(name)

        print(f"\n[ModelManager] Pull complete. {len(succeeded)} succeeded, {len(failed)} failed.")
        return {"succeeded": succeeded, "failed": failed}

    def get_model_size(self, model_name: str) -> str:
        """Return a human-readable size string for the given model."""
        info = self.model_info(model_name)
        size_bytes = info.get("size", 0)
        if not size_bytes:
            # Fall back to the listing endpoint
            for m in self.list_models():
                if m.get("name") == model_name:
                    size_bytes = m.get("size", 0)
                    break
        if size_bytes == 0:
            return "unknown"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"

    def search_models(self, query: str) -> list:
        """
        Filter the locally available models whose names contain *query*.
        The search is case-insensitive and supports '*' wildcards.
        """
        query_lower = query.lower()
        models = self.list_models()
        if "*" in query_lower or "?" in query_lower:
            return [
                m for m in models
                if fnmatch.fnmatch(m.get("name", "").lower(), query_lower)
            ]
        return [
            m for m in models
            if query_lower in m.get("name", "").lower()
        ]
