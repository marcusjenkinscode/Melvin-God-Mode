"""
tests/test_router.py
=====================
Unit tests for the model router.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from melvin.core.router import ModelRouter, _CATEGORY_KEYWORDS, _COMPILED


class TestCategoryInference:
    """Test the keyword-based category detection."""

    def _make_router(self, available_ram=24.0):
        registry = MagicMock()
        registry.list_available.return_value = []
        monitor = MagicMock()
        monitor.available_ram_gb.return_value = available_ram
        return ModelRouter(registry, monitor)

    def test_code_category(self):
        r = self._make_router()
        cat = r._infer_category("write a python function to sort a list")
        assert cat == "code"

    def test_math_category(self):
        r = self._make_router()
        cat = r._infer_category("calculate the integral of x squared")
        assert cat == "math"

    def test_creative_category(self):
        r = self._make_router()
        cat = r._infer_category("write a poem about the ocean")
        assert cat == "creative"

    def test_security_category(self):
        r = self._make_router()
        cat = r._infer_category("how do I exploit a buffer overflow")
        assert cat == "security"

    def test_osint_category(self):
        r = self._make_router()
        cat = r._infer_category("how to do osint on a username")
        assert cat == "osint"

    def test_general_fallback(self):
        r = self._make_router()
        cat = r._infer_category("tell me about the history of rome")
        assert cat == "general"


class TestOverridePrefixes:
    def _make_router(self):
        registry = MagicMock()
        registry.list_available.return_value = []
        monitor = MagicMock()
        monitor.available_ram_gb.return_value = 24.0
        return ModelRouter(registry, monitor)

    def test_override_strips_prefix(self):
        r = self._make_router()
        _, clean = r.route("!code write me a sort function")
        assert clean == "write me a sort function"

    def test_no_override_keeps_full_prompt(self):
        r = self._make_router()
        _, clean = r.route("write a poem about the sea")
        assert clean == "write a poem about the sea"
