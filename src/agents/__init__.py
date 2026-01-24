"""Agents module for managing synthetic employee personas."""

from .agent_registry import AgentRegistry, AgentConfig
from .roles import Role, get_role, ROLE_REGISTRY
from .csv_importer import import_csv, Persona, normalize_folder_name
from .persona_loader import (
    LoadedPersona,
    PersonaRegistry,
    load_persona_from_folder,
    load_all_personas,
    build_system_prompt,
    get_email_signature,
)

__all__ = [
    # Agent registry
    "AgentRegistry",
    "AgentConfig",
    # Roles
    "Role",
    "get_role",
    "ROLE_REGISTRY",
    # CSV import
    "import_csv",
    "Persona",
    "normalize_folder_name",
    # Persona loading
    "LoadedPersona",
    "PersonaRegistry",
    "load_persona_from_folder",
    "load_all_personas",
    "build_system_prompt",
    "get_email_signature",
]
