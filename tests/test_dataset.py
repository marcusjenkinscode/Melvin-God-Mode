"""
tests/test_dataset.py
======================
Unit tests for the encrypted dataset module.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Patch DATA_DIR / KEY_FILE / DATASET_FILE to use temp directory
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_dataset(tmp_path, monkeypatch):
    """Return a Dataset instance backed by a temp directory."""
    key_file = tmp_path / "test.key"
    dataset_file = tmp_path / "dataset.enc"

    # Patch config constants before importing Dataset
    import config
    monkeypatch.setattr(config, "KEY_FILE", key_file)
    monkeypatch.setattr(config, "DATASET_FILE", dataset_file)

    # Re-import Dataset so it picks up patched config
    import importlib
    import melvin.core.dataset as ds_mod
    importlib.reload(ds_mod)

    from melvin.core.dataset import Dataset
    return Dataset(dataset_file=dataset_file, key_file=key_file)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDatasetBasics:
    def test_empty_on_init(self, tmp_dataset):
        assert tmp_dataset.count() == 0
        assert tmp_dataset.load_all() == []

    def test_append_and_count(self, tmp_dataset):
        tmp_dataset.append("hello", "world", "test-model")
        assert tmp_dataset.count() == 1

    def test_load_all_returns_correct_fields(self, tmp_dataset):
        tmp_dataset.append("my input", "my response", "llama3:8b", agent="code")
        records = tmp_dataset.load_all()
        assert len(records) == 1
        r = records[0]
        assert r["input"] == "my input"
        assert r["response"] == "my response"
        assert r["model"] == "llama3:8b"
        assert r["agent"] == "code"
        assert "timestamp" in r

    def test_multiple_appends(self, tmp_dataset):
        for i in range(10):
            tmp_dataset.append(f"input {i}", f"response {i}", "model")
        assert tmp_dataset.count() == 10
        records = tmp_dataset.load_all()
        assert len(records) == 10

    def test_persistence_across_instances(self, tmp_path):
        """A second Dataset instance should read data written by the first."""
        key_file = tmp_path / "persist.key"
        dataset_file = tmp_path / "persist.enc"

        from melvin.core.dataset import Dataset
        ds1 = Dataset(dataset_file=dataset_file, key_file=key_file)
        ds1.append("ping", "pong", "model-x")

        ds2 = Dataset(dataset_file=dataset_file, key_file=key_file)
        assert ds2.count() == 1
        assert ds2.load_all()[0]["input"] == "ping"

    def test_export_and_reimport(self, tmp_path):
        key_file = tmp_path / "key2"
        dataset_file = tmp_path / "data.enc"
        export_file = tmp_path / "export.json"

        from melvin.core.dataset import Dataset
        ds = Dataset(dataset_file=dataset_file, key_file=key_file)
        ds.append("a", "b", "m", agent="general", tags=["test"])

        ds.export_plaintext(export_file)
        data = json.loads(export_file.read_text())
        assert len(data) == 1
        assert data[0]["input"] == "a"

        # Re-import
        ds.import_plaintext(export_file)
        assert ds.count() == 2

    def test_search(self, tmp_dataset):
        tmp_dataset.append("nmap is a scanner", "correct", "model")
        tmp_dataset.append("python code", "print hello", "model")
        results = tmp_dataset.search("nmap")
        assert len(results) == 1
        assert "nmap" in results[0]["input"]

    def test_search_no_results(self, tmp_dataset):
        tmp_dataset.append("hello world", "response", "model")
        results = tmp_dataset.search("nonexistent_xyz_42")
        assert results == []

    def test_wrong_key_skips_corrupted(self, tmp_path):
        """If we load with a different key, corrupted lines should be skipped gracefully."""
        key_file_a = tmp_path / "key_a"
        dataset_file = tmp_path / "shared.enc"
        key_file_b = tmp_path / "key_b"

        from melvin.core.dataset import Dataset
        ds_a = Dataset(dataset_file=dataset_file, key_file=key_file_a)
        ds_a.append("secret", "content", "model")

        # New dataset with different key – should get corrupted entry, not crash
        ds_b = Dataset(dataset_file=dataset_file, key_file=key_file_b)
        records = ds_b.load_all()
        assert len(records) == 1
        assert "CORRUPTED" in records[0]["input"]
