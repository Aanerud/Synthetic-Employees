"""LLM Service - Claude API integration for synthetic employees."""

from .claude_service import ClaudeService, generate_response

__all__ = ["ClaudeService", "generate_response"]
