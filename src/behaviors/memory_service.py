"""Memory service for agent conversation context and knowledge management.

This module provides memory capabilities for agents, enabling them to:
- Track conversation context across email/Teams threads
- Learn and remember knowledge about people and topics
- Build relevant context for LLM prompts

Inspired by OpenClaw's session-based context management, adapted for
scheduled NPC behavior patterns.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from ..database.db_service import get_db, DatabaseService


class ContextType(Enum):
    """Types of conversation context."""
    EMAIL_THREAD = "email_thread"
    TEAMS_CHAT = "teams_chat"
    TEAMS_CHANNEL = "teams_channel"
    PROJECT = "project"


class KnowledgeType(Enum):
    """Types of knowledge an agent can learn."""
    PERSON = "person"
    TOPIC = "topic"
    PREFERENCE = "preference"
    PROJECT = "project"
    SKILL = "skill"


class Sentiment(Enum):
    """Sentiment classification for conversations."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class SourceType(Enum):
    """Source of knowledge."""
    EMAIL = "email"
    TEAMS = "teams"
    OBSERVATION = "observation"
    EXPLICIT = "explicit"
    INFERRED = "inferred"


@dataclass
class ConversationContext:
    """Represents context from a conversation."""
    conversation_id: str
    agent_email: str
    participants: List[str]
    context_type: ContextType
    summary: Optional[str] = None
    key_points: List[str] = field(default_factory=list)
    sentiment: Optional[Sentiment] = None
    message_count: int = 0
    last_interaction_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Knowledge:
    """Represents a piece of learned knowledge."""
    agent_email: str
    knowledge_type: KnowledgeType
    subject: str
    content: str
    confidence: float = 0.5
    source: Optional[str] = None
    source_type: Optional[SourceType] = None
    use_count: int = 0
    last_used_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class RelevantContext:
    """Context package for LLM prompts."""
    conversation_history: List[ConversationContext]
    relevant_knowledge: List[Knowledge]
    participant_info: Dict[str, Dict[str, Any]]
    summary: str


class MemoryService:
    """Service for managing agent memory and context.

    Provides methods for:
    - Storing and retrieving conversation context
    - Learning and querying knowledge
    - Building context for LLM prompts
    """

    def __init__(self, db: Optional[DatabaseService] = None):
        """Initialize memory service.

        Args:
            db: Database service instance. Uses global instance if not provided.
        """
        self.db = db or get_db()

    # =========================================================================
    # Conversation Context Methods
    # =========================================================================

    def get_conversation_context(
        self,
        agent_email: str,
        conversation_id: str,
    ) -> Optional[ConversationContext]:
        """Retrieve context for a specific conversation.

        Args:
            agent_email: The agent's email address
            conversation_id: The conversation/thread ID

        Returns:
            ConversationContext if found, None otherwise
        """
        result = self.db.get_conversation_memory(agent_email, conversation_id)
        if not result:
            return None

        return self._row_to_conversation_context(result)

    def get_recent_conversations(
        self,
        agent_email: str,
        hours: int = 24,
        context_type: Optional[ContextType] = None,
        limit: int = 10,
    ) -> List[ConversationContext]:
        """Get recent conversations for an agent.

        Args:
            agent_email: The agent's email address
            hours: How far back to look (default 24 hours)
            context_type: Optional filter by context type
            limit: Maximum number of conversations to return

        Returns:
            List of ConversationContext ordered by last_interaction_at desc
        """
        results = self.db.get_recent_conversation_memories(
            agent_email=agent_email,
            hours=hours,
            context_type=context_type.value if context_type else None,
            limit=limit,
        )
        return [self._row_to_conversation_context(r) for r in results]

    def update_conversation_context(
        self,
        agent_email: str,
        conversation_id: str,
        context_type: ContextType,
        participants: List[str],
        summary: Optional[str] = None,
        key_points: Optional[List[str]] = None,
        sentiment: Optional[Sentiment] = None,
        message_count: Optional[int] = None,
    ) -> ConversationContext:
        """Store or update context for a conversation.

        This method handles both creating new context and updating existing.
        If context exists, it merges key_points and updates other fields.

        Args:
            agent_email: The agent's email address
            conversation_id: The conversation/thread ID
            context_type: Type of conversation
            participants: List of participant email addresses
            summary: Optional summary of the conversation
            key_points: Optional list of key points to add
            sentiment: Optional sentiment classification
            message_count: Optional message count (increments if not provided)

        Returns:
            Updated ConversationContext
        """
        existing = self.get_conversation_context(agent_email, conversation_id)

        if existing:
            # Merge key points
            merged_key_points = existing.key_points or []
            if key_points:
                for point in key_points:
                    if point not in merged_key_points:
                        merged_key_points.append(point)

            # Use provided values or existing ones
            final_summary = summary if summary is not None else existing.summary
            final_sentiment = sentiment if sentiment is not None else existing.sentiment
            final_message_count = (
                message_count if message_count is not None
                else (existing.message_count or 0) + 1
            )
        else:
            merged_key_points = key_points or []
            final_summary = summary
            final_sentiment = sentiment
            final_message_count = message_count or 1

        self.db.upsert_conversation_memory(
            agent_email=agent_email,
            conversation_id=conversation_id,
            participants=participants,
            context_type=context_type.value,
            summary=final_summary,
            key_points=merged_key_points,
            sentiment=final_sentiment.value if final_sentiment else None,
            message_count=final_message_count,
        )

        return self.get_conversation_context(agent_email, conversation_id)

    def get_conversations_with_participant(
        self,
        agent_email: str,
        participant_email: str,
        limit: int = 10,
    ) -> List[ConversationContext]:
        """Get conversations involving a specific participant.

        Args:
            agent_email: The agent's email address
            participant_email: Email of participant to search for
            limit: Maximum number of conversations to return

        Returns:
            List of ConversationContext involving the participant
        """
        results = self.db.get_conversation_memories_by_participant(
            agent_email=agent_email,
            participant_email=participant_email,
            limit=limit,
        )
        return [self._row_to_conversation_context(r) for r in results]

    # =========================================================================
    # Knowledge Methods
    # =========================================================================

    def learn(
        self,
        agent_email: str,
        knowledge_type: KnowledgeType,
        subject: str,
        content: str,
        confidence: float = 0.5,
        source: Optional[str] = None,
        source_type: Optional[SourceType] = None,
    ) -> Knowledge:
        """Store learned knowledge.

        If knowledge with same type and subject exists, updates it with
        potentially higher confidence.

        Args:
            agent_email: The agent's email address
            knowledge_type: Type of knowledge being stored
            subject: Subject of the knowledge (e.g., person name, topic)
            content: The knowledge content
            confidence: Confidence level (0.0-1.0)
            source: Source identifier (email_id, etc.)
            source_type: How the knowledge was acquired

        Returns:
            The stored Knowledge object
        """
        existing = self.get_knowledge(agent_email, knowledge_type, subject)

        if existing:
            # Update with potentially higher confidence
            new_confidence = max(existing.confidence, confidence)
            # Append new content if different
            if content != existing.content:
                new_content = f"{existing.content}\n---\n{content}"
            else:
                new_content = content
        else:
            new_confidence = confidence
            new_content = content

        self.db.upsert_agent_knowledge(
            agent_email=agent_email,
            knowledge_type=knowledge_type.value,
            subject=subject,
            content=new_content,
            confidence=new_confidence,
            source=source,
            source_type=source_type.value if source_type else None,
        )

        return self.get_knowledge(agent_email, knowledge_type, subject)

    def get_knowledge(
        self,
        agent_email: str,
        knowledge_type: KnowledgeType,
        subject: str,
    ) -> Optional[Knowledge]:
        """Retrieve specific knowledge.

        Args:
            agent_email: The agent's email address
            knowledge_type: Type of knowledge
            subject: Subject of the knowledge

        Returns:
            Knowledge if found, None otherwise
        """
        result = self.db.get_agent_knowledge(
            agent_email=agent_email,
            knowledge_type=knowledge_type.value,
            subject=subject,
        )
        if not result:
            return None

        return self._row_to_knowledge(result)

    def get_knowledge_by_type(
        self,
        agent_email: str,
        knowledge_type: KnowledgeType,
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> List[Knowledge]:
        """Get all knowledge of a specific type.

        Args:
            agent_email: The agent's email address
            knowledge_type: Type of knowledge to retrieve
            min_confidence: Minimum confidence threshold
            limit: Maximum number of items to return

        Returns:
            List of Knowledge items sorted by confidence desc
        """
        results = self.db.get_agent_knowledge_by_type(
            agent_email=agent_email,
            knowledge_type=knowledge_type.value,
            min_confidence=min_confidence,
            limit=limit,
        )
        return [self._row_to_knowledge(r) for r in results]

    def get_knowledge_about_person(
        self,
        agent_email: str,
        person_email: str,
    ) -> Optional[Knowledge]:
        """Get knowledge about a specific person.

        Convenience method for getting person-type knowledge.

        Args:
            agent_email: The agent's email address
            person_email: Email of the person to look up

        Returns:
            Knowledge about the person if exists
        """
        return self.get_knowledge(agent_email, KnowledgeType.PERSON, person_email)

    def record_knowledge_use(
        self,
        agent_email: str,
        knowledge_type: KnowledgeType,
        subject: str,
    ) -> None:
        """Record that a piece of knowledge was used.

        Updates use_count and last_used_at for the knowledge item.

        Args:
            agent_email: The agent's email address
            knowledge_type: Type of knowledge
            subject: Subject of the knowledge
        """
        self.db.increment_knowledge_use_count(
            agent_email=agent_email,
            knowledge_type=knowledge_type.value,
            subject=subject,
        )

    def search_knowledge(
        self,
        agent_email: str,
        query: str,
        knowledge_types: Optional[List[KnowledgeType]] = None,
        limit: int = 10,
    ) -> List[Knowledge]:
        """Search knowledge by content/subject.

        Args:
            agent_email: The agent's email address
            query: Search query
            knowledge_types: Optional filter by knowledge types
            limit: Maximum results to return

        Returns:
            List of matching Knowledge items
        """
        type_values = (
            [kt.value for kt in knowledge_types]
            if knowledge_types
            else None
        )
        results = self.db.search_agent_knowledge(
            agent_email=agent_email,
            query=query,
            knowledge_types=type_values,
            limit=limit,
        )
        return [self._row_to_knowledge(r) for r in results]

    # =========================================================================
    # Context Building Methods
    # =========================================================================

    def get_relevant_context(
        self,
        agent_email: str,
        conversation_id: Optional[str] = None,
        participants: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        context_window_hours: int = 48,
        max_conversations: int = 5,
        max_knowledge_items: int = 10,
    ) -> RelevantContext:
        """Build relevant context for an LLM prompt.

        Gathers conversation history and relevant knowledge to provide
        context for generating responses.

        Args:
            agent_email: The agent's email address
            conversation_id: Optional specific conversation to focus on
            participants: Optional list of participant emails to consider
            topics: Optional list of topics to search for
            context_window_hours: How far back to look for context
            max_conversations: Maximum conversations to include
            max_knowledge_items: Maximum knowledge items to include

        Returns:
            RelevantContext containing conversation history, knowledge,
            and a summary suitable for LLM prompts
        """
        conversations: List[ConversationContext] = []
        knowledge_items: List[Knowledge] = []
        participant_info: Dict[str, Dict[str, Any]] = {}

        # Get the specific conversation if provided
        if conversation_id:
            specific_conv = self.get_conversation_context(
                agent_email, conversation_id
            )
            if specific_conv:
                conversations.append(specific_conv)
                # Add participants from this conversation
                if specific_conv.participants:
                    for p in specific_conv.participants:
                        if p not in (participants or []):
                            participants = (participants or []) + [p]

        # Get recent conversations
        recent = self.get_recent_conversations(
            agent_email=agent_email,
            hours=context_window_hours,
            limit=max_conversations,
        )
        for conv in recent:
            if conv.conversation_id not in [c.conversation_id for c in conversations]:
                conversations.append(conv)

        # Get knowledge about participants
        if participants:
            for participant_email in participants:
                person_knowledge = self.get_knowledge_about_person(
                    agent_email, participant_email
                )
                if person_knowledge:
                    knowledge_items.append(person_knowledge)
                    participant_info[participant_email] = {
                        "knowledge": person_knowledge.content,
                        "confidence": person_knowledge.confidence,
                    }
                    self.record_knowledge_use(
                        agent_email, KnowledgeType.PERSON, participant_email
                    )

        # Get knowledge about topics
        if topics:
            for topic in topics:
                topic_results = self.search_knowledge(
                    agent_email=agent_email,
                    query=topic,
                    knowledge_types=[KnowledgeType.TOPIC, KnowledgeType.PROJECT],
                    limit=3,
                )
                for k in topic_results:
                    if k not in knowledge_items:
                        knowledge_items.append(k)

        # Limit knowledge items
        knowledge_items = knowledge_items[:max_knowledge_items]

        # Build summary
        summary = self._build_context_summary(
            conversations, knowledge_items, participant_info
        )

        return RelevantContext(
            conversation_history=conversations[:max_conversations],
            relevant_knowledge=knowledge_items,
            participant_info=participant_info,
            summary=summary,
        )

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _row_to_conversation_context(
        self, row: Dict[str, Any]
    ) -> ConversationContext:
        """Convert database row to ConversationContext."""
        return ConversationContext(
            conversation_id=row["conversation_id"],
            agent_email=row["agent_email"],
            participants=json.loads(row["participants"]) if row.get("participants") else [],
            context_type=ContextType(row["context_type"]),
            summary=row.get("summary"),
            key_points=json.loads(row["key_points"]) if row.get("key_points") else [],
            sentiment=Sentiment(row["sentiment"]) if row.get("sentiment") else None,
            message_count=row.get("message_count", 0),
            last_interaction_at=self._parse_datetime(row.get("last_interaction_at")),
            created_at=self._parse_datetime(row.get("created_at")),
            updated_at=self._parse_datetime(row.get("updated_at")),
        )

    def _row_to_knowledge(self, row: Dict[str, Any]) -> Knowledge:
        """Convert database row to Knowledge."""
        return Knowledge(
            agent_email=row["agent_email"],
            knowledge_type=KnowledgeType(row["knowledge_type"]),
            subject=row["subject"],
            content=row["content"],
            confidence=row.get("confidence", 0.5),
            source=row.get("source"),
            source_type=SourceType(row["source_type"]) if row.get("source_type") else None,
            use_count=row.get("use_count", 0),
            last_used_at=self._parse_datetime(row.get("last_used_at")),
            created_at=self._parse_datetime(row.get("created_at")),
            updated_at=self._parse_datetime(row.get("updated_at")),
        )

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    def _build_context_summary(
        self,
        conversations: List[ConversationContext],
        knowledge: List[Knowledge],
        participant_info: Dict[str, Dict[str, Any]],
    ) -> str:
        """Build a text summary of the context for LLM prompts."""
        parts = []

        # Conversation summary
        if conversations:
            conv_summaries = []
            for conv in conversations[:3]:
                if conv.summary:
                    conv_summaries.append(f"- {conv.summary}")
            if conv_summaries:
                parts.append("Recent conversations:\n" + "\n".join(conv_summaries))

        # Participant summary
        if participant_info:
            participant_summaries = []
            for email, info in participant_info.items():
                if info.get("knowledge"):
                    # Extract first sentence or line as brief summary
                    brief = info["knowledge"].split("\n")[0][:100]
                    participant_summaries.append(f"- {email}: {brief}")
            if participant_summaries:
                parts.append("Known about participants:\n" + "\n".join(participant_summaries))

        # Knowledge summary
        topic_knowledge = [k for k in knowledge if k.knowledge_type != KnowledgeType.PERSON]
        if topic_knowledge:
            knowledge_summaries = []
            for k in topic_knowledge[:3]:
                brief = k.content.split("\n")[0][:100]
                knowledge_summaries.append(f"- {k.subject}: {brief}")
            if knowledge_summaries:
                parts.append("Relevant knowledge:\n" + "\n".join(knowledge_summaries))

        return "\n\n".join(parts) if parts else ""


# Global memory service instance
_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """Get or create the global memory service instance."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service
