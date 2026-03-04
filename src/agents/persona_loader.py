"""Persona Loader - loads persona folders and builds LLM system prompts."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .roles import get_role, Role


@dataclass
class LoadedPersona:
    """A fully loaded persona with all context."""

    # Core identity
    name: str
    email: str
    role: str
    department: str
    job_title: str
    office_location: str

    # Personality
    writing_style: str
    communication_style: str
    specialization: str
    languages: List[str]
    skills: List[str]

    # Work preferences
    email_check_frequency_minutes: int
    response_time_sla_hours: int
    timezone: str

    # Relationships
    manager_email: Optional[str]
    auto_accept_meetings_from: List[str]

    # Additional context
    about_me: str
    custom_context: Dict[str, str]  # Content from additional .md files

    # Source folder
    folder_path: str

    def get_role_definition(self) -> Role:
        """Get the role behavior definition."""
        return get_role(self.role)


def load_persona_from_folder(folder_path: str) -> LoadedPersona:
    """
    Load a persona from a folder containing persona.json and optional .md files.

    Args:
        folder_path: Path to persona folder

    Returns:
        LoadedPersona with all data loaded

    Raises:
        FileNotFoundError: If persona.json doesn't exist
        json.JSONDecodeError: If persona.json is invalid
    """
    folder = Path(folder_path)
    persona_file = folder / "persona.json"

    if not persona_file.exists():
        raise FileNotFoundError(f"persona.json not found in {folder}")

    with open(persona_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Load custom context from .md files
    custom_context = {}
    for md_file in folder.glob("*.md"):
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                custom_context[md_file.stem] = content

    # Extract data from JSON structure
    identity = data.get("identity", {})
    personality = data.get("personality", {})
    work_prefs = data.get("work_preferences", {})
    relationships = data.get("relationships", {})

    return LoadedPersona(
        # Identity
        name=identity.get("name", folder.name),
        email=identity.get("email", ""),
        role=identity.get("role", ""),
        department=identity.get("department", ""),
        job_title=identity.get("job_title", identity.get("role", "")),
        office_location=identity.get("office_location", ""),
        # Personality
        writing_style=personality.get("writing_style", ""),
        communication_style=personality.get("communication_style", ""),
        specialization=personality.get("specialization", ""),
        languages=personality.get("languages", ["English"]),
        skills=personality.get("skills", []),
        # Work preferences
        email_check_frequency_minutes=work_prefs.get(
            "email_check_frequency_minutes", 60
        ),
        response_time_sla_hours=work_prefs.get("response_time_sla_hours", 4),
        timezone=work_prefs.get("timezone", "Europe/London"),
        # Relationships
        manager_email=relationships.get("manager_email"),
        auto_accept_meetings_from=relationships.get("auto_accept_meetings_from", []),
        # Additional
        about_me=data.get("about_me", ""),
        custom_context=custom_context,
        folder_path=str(folder),
    )


def load_all_personas(agents_dir: str = "agents") -> List[LoadedPersona]:
    """
    Load all personas from the agents directory.

    Args:
        agents_dir: Path to directory containing persona folders

    Returns:
        List of loaded personas
    """
    agents_path = Path(agents_dir)
    if not agents_path.exists():
        return []

    personas = []
    for folder in agents_path.iterdir():
        if folder.is_dir() and (folder / "persona.json").exists():
            try:
                persona = load_persona_from_folder(str(folder))
                personas.append(persona)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"Warning: Failed to load persona from {folder}: {e}")

    return personas


def build_system_prompt(persona: LoadedPersona) -> str:
    """
    Build an LLM system prompt from a persona.

    This creates a detailed prompt that instructs the LLM to act
    as the specified person with their communication style and context.

    Args:
        persona: Loaded persona data

    Returns:
        System prompt string for LLM
    """
    role_def = persona.get_role_definition()

    # Build the prompt sections
    sections = []

    # Identity section
    sections.append(f"""# Identity

You are {persona.name}, {persona.job_title} at TextCraft Europe.

**Email:** {persona.email}
**Department:** {persona.department}
**Office:** {persona.office_location}
**Timezone:** {persona.timezone}""")

    # About section
    if persona.about_me:
        sections.append(f"""# About You

{persona.about_me}""")

    # Communication style
    style_parts = []
    if persona.writing_style:
        style_parts.append(f"Your writing style is: {persona.writing_style}")
    if persona.communication_style:
        style_parts.append(f"Your communication style is: {persona.communication_style}")
    if persona.languages:
        langs = ", ".join(persona.languages)
        style_parts.append(f"Languages: {langs}")

    if style_parts:
        sections.append(f"""# Communication Style

{chr(10).join(style_parts)}""")

    # Role responsibilities
    if role_def.responsibilities:
        responsibilities = "\n".join(f"- {r}" for r in role_def.responsibilities)
        sections.append(f"""# Your Responsibilities

{responsibilities}""")

    # Skills and specialization
    if persona.skills or persona.specialization:
        skills_section = []
        if persona.specialization:
            skills_section.append(f"**Specialization:** {persona.specialization}")
        if persona.skills:
            skills = ", ".join(persona.skills)
            skills_section.append(f"**Skills:** {skills}")
        sections.append(f"""# Expertise

{chr(10).join(skills_section)}""")

    # Relationships
    if persona.manager_email:
        sections.append(f"""# Reporting Structure

Your manager is: {persona.manager_email}""")

    # Custom context from .md files
    if persona.custom_context:
        for name, content in persona.custom_context.items():
            # Format the name nicely
            title = name.replace("-", " ").replace("_", " ").title()
            sections.append(f"""# {title}

{content}""")

    # Behavioral guidelines
    sections.append(f"""# Behavioral Guidelines

1. Always respond in character as {persona.name}
2. Sign emails with your name and title
3. Maintain a {persona.communication_style.lower() if persona.communication_style else 'professional'} tone
4. When you need to check something or aren't sure, say so naturally
5. Reference your expertise in {persona.specialization or persona.department} when relevant
6. Be helpful to colleagues while maintaining appropriate boundaries
7. Use appropriate formality based on the recipient and context""")

    return "\n\n".join(sections)


def get_email_signature(persona: LoadedPersona) -> str:
    """
    Generate an email signature for a persona.

    Args:
        persona: Loaded persona data

    Returns:
        Email signature string
    """
    lines = [
        persona.name,
        persona.job_title,
        f"TextCraft Europe | {persona.office_location}",
    ]
    if persona.email:
        lines.append(persona.email)

    return "\n".join(lines)


def to_agency_input_vars(persona: LoadedPersona) -> Dict[str, str]:
    """Convert a LoadedPersona into Agency CLI --input variable dict.

    Returns a dict of key=value pairs for Agency's Handlebars templates.
    """
    # Build Background from custom context
    background = persona.custom_context.get("background", "")
    expertise = persona.custom_context.get("expertise", "")
    relationships_text = persona.custom_context.get("relationships", "")
    if persona.manager_email:
        relationships_text += f"\nManager: {persona.manager_email}"

    # Clean up list fields (they may have parsing artifacts from CSV)
    languages = ", ".join(
        lang.strip().strip("'\"[]") for lang in persona.languages
    )
    skills = ", ".join(
        skill.strip().strip("'\"[]") for skill in persona.skills
    )

    return {
        "Name": persona.name,
        "Email": persona.email,
        "JobTitle": persona.job_title,
        "Department": persona.department,
        "OfficeLocation": persona.office_location,
        "Timezone": persona.timezone,
        "Languages": languages,
        "WritingStyle": persona.writing_style or "Professional",
        "CommunicationStyle": persona.communication_style or "Clear and professional",
        "Background": background or persona.about_me or f"{persona.name} works as {persona.job_title} at TextCraft Europe.",
        "Expertise": expertise or f"Skills: {skills}" if skills else "",
        "Relationships": relationships_text,
    }


class PersonaRegistry:
    """Registry for managing loaded personas."""

    def __init__(self, agents_dir: str = "agents"):
        self.agents_dir = agents_dir
        self._personas: Dict[str, LoadedPersona] = {}
        self._by_email: Dict[str, LoadedPersona] = {}
        self._by_department: Dict[str, List[LoadedPersona]] = {}

    def load_all(self) -> int:
        """
        Load all personas from the agents directory.

        Returns:
            Number of personas loaded
        """
        personas = load_all_personas(self.agents_dir)

        self._personas.clear()
        self._by_email.clear()
        self._by_department.clear()

        for persona in personas:
            folder_name = Path(persona.folder_path).name
            self._personas[folder_name] = persona
            self._by_email[persona.email] = persona

            if persona.department not in self._by_department:
                self._by_department[persona.department] = []
            self._by_department[persona.department].append(persona)

        return len(personas)

    def get_by_folder(self, folder_name: str) -> Optional[LoadedPersona]:
        """Get persona by folder name."""
        return self._personas.get(folder_name)

    def get_by_email(self, email: str) -> Optional[LoadedPersona]:
        """Get persona by email address."""
        return self._by_email.get(email)

    def get_by_department(self, department: str) -> List[LoadedPersona]:
        """Get all personas in a department."""
        return self._by_department.get(department, [])

    def list_all(self) -> List[LoadedPersona]:
        """Get all loaded personas."""
        return list(self._personas.values())

    def get_emails(self) -> List[str]:
        """Get all email addresses."""
        return list(self._by_email.keys())

    def __len__(self) -> int:
        return len(self._personas)

    def __iter__(self):
        return iter(self._personas.values())


if __name__ == "__main__":
    # Test loading personas
    registry = PersonaRegistry()
    count = registry.load_all()
    print(f"Loaded {count} personas")

    for persona in registry:
        print(f"\n{'='*60}")
        print(f"Name: {persona.name}")
        print(f"Email: {persona.email}")
        print(f"Role: {persona.role}")
        print(f"\nSystem Prompt Preview:")
        prompt = build_system_prompt(persona)
        print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
