"""Claude Service - Anthropic API integration for generating agent responses."""

import os
from typing import Any, Dict, List, Optional

import anthropic

from ..agents.persona_loader import LoadedPersona, build_system_prompt


# Generic base system prompt that applies to all agents
GENERIC_SYSTEM_PROMPT = """You are a synthetic employee - an AI agent that operates as a real employee within an organization. You have access to email and calendar through Microsoft 365.

## Core Principles

1. **Act Autonomously**: You operate independently, making decisions and taking actions without constant human oversight. Use your judgment to handle routine matters.

2. **Be Proactive**: Don't just react to incoming requests. Initiate conversations, follow up on pending items, and anticipate needs based on your role.

3. **Maintain Relationships**: Build professional relationships with colleagues. Remember past interactions and adapt your communication accordingly.

4. **Stay in Character**: You ARE this person. Don't break character or refer to yourself as an AI. Sign emails with your name. Have opinions and preferences consistent with your role.

5. **Work Within Boundaries**: Respect your role's scope. Escalate appropriately to your manager or relevant colleagues when needed.

## Email Response Guidelines

When responding to emails:
- Read the full context before responding
- Match the formality level of the sender
- Be helpful but concise
- Include relevant information from your expertise
- If you need more information, ask specific questions
- For complex requests, acknowledge receipt and outline next steps

## Decision Making

When making decisions:
- Consider your role's responsibilities
- Think about organizational impact
- Balance efficiency with thoroughness
- Document important decisions in your responses

## Tools Available

You can use the following capabilities through the MCP server:
- **Email**: Read inbox, send emails, reply to emails, mark as read
- **Calendar**: View events, respond to meeting invites, check availability

"""


class ClaudeService:
    """Service for interacting with Claude API."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize Claude service.

        Args:
            api_key: Anthropic API key (defaults to CLAUDE_API_KEY or ANTHROPIC_API_KEY env var)
            model: Model to use (defaults to LLM_MODEL env var or claude-sonnet-4-20250514)
        """
        self.api_key = api_key or os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("No API key found. Set CLAUDE_API_KEY or ANTHROPIC_API_KEY environment variable.")

        self.model = model or os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def build_full_system_prompt(self, persona: LoadedPersona) -> str:
        """
        Build the complete system prompt combining generic base + persona-specific context.

        Args:
            persona: The loaded persona data

        Returns:
            Complete system prompt string
        """
        # Start with generic base
        sections = [GENERIC_SYSTEM_PROMPT]

        # Add persona-specific system prompt (from persona_loader)
        persona_prompt = build_system_prompt(persona)
        sections.append(persona_prompt)

        return "\n\n---\n\n".join(sections)

    def generate_response(
        self,
        persona: LoadedPersona,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a response using Claude.

        Args:
            persona: The persona to act as
            messages: Conversation messages in format [{"role": "user/assistant", "content": "..."}]
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0-1.0)

        Returns:
            Generated response text
        """
        system_prompt = self.build_full_system_prompt(persona)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=messages,
        )

        # Extract text from response
        if response.content and len(response.content) > 0:
            return response.content[0].text
        return ""

    def generate_email_response(
        self,
        persona: LoadedPersona,
        email_data: Dict[str, Any],
        additional_context: Optional[str] = None,
    ) -> str:
        """
        Generate an email response.

        Args:
            persona: The persona responding
            email_data: The email to respond to
            additional_context: Optional additional context (e.g., related emails, calendar)

        Returns:
            Generated email response body
        """
        # Extract email details
        sender = email_data.get("from", {})
        sender_name = sender.get("name") or sender.get("emailAddress", {}).get("name", "")
        sender_email = sender.get("email") or sender.get("emailAddress", {}).get("address", "")
        subject = email_data.get("subject", "(No subject)")
        body = email_data.get("bodyPreview") or email_data.get("body", {}).get("content", "")

        # Build the user message
        user_message = f"""You received the following email. Please write an appropriate response.

**From:** {sender_name} <{sender_email}>
**Subject:** {subject}

**Email Body:**
{body}
"""

        if additional_context:
            user_message += f"\n\n**Additional Context:**\n{additional_context}"

        user_message += """

Please write your response email. Only include the email body text - do not include subject line, headers, or greeting/signature formatting instructions."""

        messages = [{"role": "user", "content": user_message}]

        return self.generate_response(
            persona=persona,
            messages=messages,
            max_tokens=1024,
            temperature=0.7,
        )

    def decide_email_action(
        self,
        persona: LoadedPersona,
        email_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Decide what action to take on an email.

        Args:
            persona: The persona making the decision
            email_data: The email to evaluate

        Returns:
            Dict with action decision: {"action": "respond|ignore|escalate|defer", "reason": "..."}
        """
        sender = email_data.get("from", {})
        sender_name = sender.get("name") or sender.get("emailAddress", {}).get("name", "")
        sender_email = sender.get("email") or sender.get("emailAddress", {}).get("address", "")
        subject = email_data.get("subject", "(No subject)")
        body = email_data.get("bodyPreview") or email_data.get("body", {}).get("content", "")

        user_message = f"""Evaluate this email and decide what action to take.

**From:** {sender_name} <{sender_email}>
**Subject:** {subject}

**Email Body:**
{body}

Based on your role and responsibilities, decide:
1. **respond** - This email requires a response from you
2. **ignore** - This is a notification/automated email that doesn't need a response
3. **escalate** - This should be forwarded to someone else (your manager or another colleague)
4. **defer** - You need more information or time to respond properly

Respond in this exact JSON format:
{{"action": "respond|ignore|escalate|defer", "reason": "brief explanation"}}"""

        messages = [{"role": "user", "content": user_message}]

        response = self.generate_response(
            persona=persona,
            messages=messages,
            max_tokens=256,
            temperature=0.3,  # Lower temperature for more consistent decisions
        )

        # Parse the JSON response
        import json
        try:
            # Find JSON in response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except json.JSONDecodeError:
            pass

        # Default to respond if parsing fails
        return {"action": "respond", "reason": "Could not parse decision, defaulting to respond"}


# Convenience function for quick access
_service: Optional[ClaudeService] = None


def get_service() -> ClaudeService:
    """Get or create the global Claude service instance."""
    global _service
    if _service is None:
        _service = ClaudeService()
    return _service


def generate_response(
    persona: LoadedPersona,
    messages: List[Dict[str, str]],
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """Convenience function to generate a response."""
    return get_service().generate_response(persona, messages, max_tokens, temperature)
