"""
tests/test_memory.py
=====================
Unit tests for ConversationMemory.
"""

from __future__ import annotations

from melvin.core.memory import ConversationMemory


class TestConversationMemory:
    def test_initial_state(self):
        mem = ConversationMemory("You are a test assistant.")
        assert len(mem) == 0
        msgs = mem.get_messages()
        assert msgs[0]["role"] == "system"
        assert "test assistant" in msgs[0]["content"]

    def test_add_user_and_assistant(self):
        mem = ConversationMemory("sys")
        mem.add_user("hello")
        mem.add_assistant("hi there")
        assert len(mem) == 2
        msgs = mem.get_messages()
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"

    def test_clear(self):
        mem = ConversationMemory("sys")
        mem.add_user("a")
        mem.add_assistant("b")
        mem.clear()
        assert len(mem) == 0

    def test_trimming(self):
        # Set very small max_tokens to force trimming
        mem = ConversationMemory("sys", max_tokens=50)
        # Each message is ~20 chars; add many to force trim
        for i in range(20):
            mem.add_user(f"user message {i}")
            mem.add_assistant(f"assistant reply {i}")
        # Memory should be trimmed – we can't have 40 messages with 50 token limit
        assert len(mem) < 40

    def test_update_system_prompt(self):
        mem = ConversationMemory("original")
        mem.update_system_prompt("updated")
        msgs = mem.get_messages()
        assert msgs[0]["content"] == "updated"

    def test_last_n_turns(self):
        mem = ConversationMemory("sys")
        for i in range(5):
            mem.add_user(f"q{i}")
            mem.add_assistant(f"a{i}")
        last = mem.last_n_turns(2)
        # Last 2 turns = 4 messages
        assert len(last) == 4
        assert last[-1].content == "a4"
