"""
tests/test_tools_registry.py
==============================
Unit tests for the tool registry.
"""

from __future__ import annotations

import pytest

from melvin.tools.registry import (
    REGISTRY,
    ToolEntry,
    all_tools,
    find_tool,
    search_tools,
)


class TestRegistry:
    def test_registry_not_empty(self):
        assert len(REGISTRY) > 0

    def test_all_tools_returns_entries(self):
        tools = all_tools()
        assert len(tools) > 0
        assert all(isinstance(t, ToolEntry) for t in tools)

    def test_find_tool_exists(self):
        tool = find_tool("nmap")
        assert tool is not None
        assert tool.name == "nmap"
        assert tool.category == "Network Scanning"

    def test_find_tool_not_exists(self):
        assert find_tool("definitely_fake_tool_xyz") is None

    def test_find_tool_case_insensitive(self):
        assert find_tool("NMAP") is not None
        assert find_tool("Nmap") is not None

    def test_search_by_name(self):
        results = search_tools("nmap")
        assert any(t.name == "nmap" for t in results)

    def test_search_by_description(self):
        results = search_tools("wordlist")
        # hashcat, john, cewl, crunch descriptions mention wordlist
        assert len(results) > 0

    def test_search_by_category(self):
        results = search_tools("forensics")
        assert all("forensic" in t.category.lower() or "forensic" in t.description.lower()
                   for t in results)

    def test_install_method_present(self):
        for tool in all_tools():
            method = tool.install_method
            assert isinstance(method, str)
            assert len(method) > 0

    def test_examples_list(self):
        tool = find_tool("nmap")
        assert isinstance(tool.examples, list)
        assert len(tool.examples) >= 1

    def test_all_entries_have_name_and_category(self):
        for tool in all_tools():
            assert tool.name
            assert tool.category

    def test_tool_in_registry_category(self):
        for cat, entries in REGISTRY.items():
            for entry in entries:
                assert entry.category == cat
