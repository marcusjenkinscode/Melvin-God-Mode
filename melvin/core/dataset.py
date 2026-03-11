"""
melvin/core/dataset.py
=======================
Encrypted, append-only interaction dataset.

Each interaction is stored as a JSON line encrypted with a Fernet symmetric
key that lives in KEY_FILE.  On first run the key is generated automatically.
Reading back the dataset decrypts all lines.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet

from config import DATASET_FILE, KEY_FILE


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def _load_or_create_key(key_file: Path = KEY_FILE) -> bytes:
    """Return the Fernet key for *key_file*, creating it if necessary."""
    if key_file.exists():
        return key_file.read_bytes().strip()
    key = Fernet.generate_key()
    key_file.write_bytes(key)
    # Restrict permissions so only the owner can read the key
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class Dataset:
    """
    Append-only encrypted dataset.

    Usage::

        ds = Dataset()
        ds.append(input_text="hello", response="world", model="llama3.1:8b")
        interactions = ds.load_all()
    """

    def __init__(
        self,
        dataset_file: Path = DATASET_FILE,
        key_file: Path = KEY_FILE,
    ) -> None:
        self._dataset_file = dataset_file
        self._key = _load_or_create_key(key_file)
        self._fernet = Fernet(self._key)
        # Ensure the parent directory exists
        self._dataset_file.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(
        self,
        input_text: str,
        response: str,
        model: str,
        agent: str = "general",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Encrypt and append one interaction record."""
        record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input": input_text,
            "response": response,
            "model": model,
            "agent": agent,
            "tags": tags or [],
        }
        if metadata:
            record["metadata"] = metadata

        raw = json.dumps(record, ensure_ascii=False)
        token = self._fernet.encrypt(raw.encode())

        with open(self._dataset_file, "ab") as fh:
            fh.write(token + b"\n")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_all(self) -> List[Dict[str, Any]]:
        """Decrypt and return all interaction records."""
        if not self._dataset_file.exists():
            return []

        records: List[Dict[str, Any]] = []
        with open(self._dataset_file, "rb") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    plaintext = self._fernet.decrypt(line)
                    records.append(json.loads(plaintext))
                except Exception as exc:  # noqa: BLE001
                    # Corrupted line – skip but report
                    records.append(
                        {
                            "timestamp": None,
                            "input": f"[CORRUPTED LINE {line_no}]",
                            "response": str(exc),
                            "model": "N/A",
                            "agent": "N/A",
                            "tags": [],
                        }
                    )
        return records

    def count(self) -> int:
        """Return the number of stored interactions without decrypting."""
        if not self._dataset_file.exists():
            return 0
        with open(self._dataset_file, "rb") as fh:
            return sum(1 for line in fh if line.strip())

    def export_plaintext(self, dest: Path) -> None:
        """Decrypt the full dataset and write to *dest* as JSON."""
        records = self.load_all()
        dest.write_text(json.dumps(records, indent=2, ensure_ascii=False))

    def import_plaintext(self, src: Path) -> int:
        """Re-encrypt a plain JSON export and append to the dataset. Returns count."""
        data = json.loads(src.read_text())
        for record in data:
            self.append(
                input_text=record.get("input", ""),
                response=record.get("response", ""),
                model=record.get("model", "unknown"),
                agent=record.get("agent", "general"),
                tags=record.get("tags", []),
                metadata=record.get("metadata"),
            )
        return len(data)

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Simple substring search across decrypted dataset (case-insensitive)."""
        q = query.lower()
        results = []
        for record in self.load_all():
            if q in record.get("input", "").lower() or q in record.get("response", "").lower():
                results.append(record)
                if len(results) >= limit:
                    break
        return results
