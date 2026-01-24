"""CSV Importer - creates persona folders from TextCraft Europe CSV."""

import csv
import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any


@dataclass
class PersonaIdentity:
    """Core identity information for an agent."""

    name: str
    email: str
    role: str
    department: str
    job_title: str
    office_location: str


@dataclass
class PersonaPersonality:
    """Personality and communication traits."""

    writing_style: str
    communication_style: str
    specialization: str
    languages: List[str]
    skills: List[str]


@dataclass
class PersonaWorkPreferences:
    """Work behavior preferences."""

    email_check_frequency_minutes: int
    response_time_sla_hours: int
    timezone: str


@dataclass
class PersonaRelationships:
    """Organizational relationships."""

    manager_email: Optional[str]
    auto_accept_meetings_from: List[str]


@dataclass
class Persona:
    """Complete persona definition for an agent."""

    identity: PersonaIdentity
    personality: PersonaPersonality
    work_preferences: PersonaWorkPreferences
    relationships: PersonaRelationships
    about_me: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "identity": asdict(self.identity),
            "personality": asdict(self.personality),
            "work_preferences": asdict(self.work_preferences),
            "relationships": asdict(self.relationships),
            "about_me": self.about_me,
        }


# Role to check frequency mapping (minutes)
ROLE_EMAIL_FREQUENCIES = {
    "CEO": 30,
    "Managing Director": 30,
    "Editorial Director": 30,
    "Director": 30,
    "Senior Editor": 45,
    "Editor": 60,
    "Assistant Editor": 60,
    "Manager": 45,
    "Specialist": 60,
    "Analyst": 60,
    "Coordinator": 45,
    "Designer": 60,
    "Developer": 60,
    "default": 60,
}

# Role to SLA hours mapping
ROLE_SLA_HOURS = {
    "CEO": 1,
    "Managing Director": 2,
    "Editorial Director": 2,
    "Director": 2,
    "Senior Editor": 4,
    "Editor": 4,
    "Assistant Editor": 6,
    "Manager": 3,
    "Specialist": 4,
    "Analyst": 4,
    "Coordinator": 4,
    "Designer": 4,
    "Developer": 4,
    "default": 4,
}

# Location to timezone mapping
LOCATION_TIMEZONES = {
    "London": "Europe/London",
    "Paris": "Europe/Paris",
    "Berlin": "Europe/Berlin",
    "Amsterdam": "Europe/Amsterdam",
    "Milan": "Europe/Rome",
    "Madrid": "Europe/Madrid",
    "Stockholm": "Europe/Stockholm",
    "Copenhagen": "Europe/Copenhagen",
    "Oslo": "Europe/Oslo",
    "Dublin": "Europe/Dublin",
    "Brussels": "Europe/Brussels",
    "Vienna": "Europe/Vienna",
    "Zurich": "Europe/Zurich",
    "Lisbon": "Europe/Lisbon",
    "Warsaw": "Europe/Warsaw",
    "Prague": "Europe/Prague",
    "Budapest": "Europe/Budapest",
    "default": "Europe/London",
}


def normalize_folder_name(name: str) -> str:
    """
    Convert a name to a folder-safe format.

    Example: "Victoria Palmer" -> "victoria.palmer"
    """
    # Convert to lowercase
    name = name.lower()
    # Replace spaces with dots
    name = name.replace(" ", ".")
    # Remove special characters except dots and hyphens
    name = re.sub(r"[^a-z0-9.\-]", "", name)
    # Remove consecutive dots
    name = re.sub(r"\.+", ".", name)
    # Remove leading/trailing dots
    name = name.strip(".")
    return name


def parse_languages(languages_str: str) -> List[str]:
    """Parse languages from CSV format like 'English (Native), French (Fluent)'."""
    if not languages_str:
        return []
    return [lang.strip() for lang in languages_str.split(",")]


def parse_skills(skills_str: str) -> List[str]:
    """Parse skills from CSV format like 'Copy editing, Proofreading'."""
    if not skills_str:
        return []
    return [skill.strip() for skill in skills_str.split(",")]


def get_email_frequency(role: str) -> int:
    """Get email check frequency based on role."""
    for role_key, frequency in ROLE_EMAIL_FREQUENCIES.items():
        if role_key.lower() in role.lower():
            return frequency
    return ROLE_EMAIL_FREQUENCIES["default"]


def get_sla_hours(role: str) -> int:
    """Get response SLA hours based on role."""
    for role_key, hours in ROLE_SLA_HOURS.items():
        if role_key.lower() in role.lower():
            return hours
    return ROLE_SLA_HOURS["default"]


def get_timezone(location: str) -> str:
    """Get timezone based on office location."""
    for loc_key, tz in LOCATION_TIMEZONES.items():
        if loc_key.lower() in location.lower():
            return tz
    return LOCATION_TIMEZONES["default"]


def parse_csv_row(row: Dict[str, str], domain: str) -> Optional[Persona]:
    """
    Parse a CSV row into a Persona object.

    Expected CSV columns (flexible matching):
    - Name/Full Name/Employee Name
    - Email/Email Address (or generated from name + domain)
    - Role/Job Title/Position
    - Department
    - Location/Office/Office Location
    - Languages
    - Skills/Specialization
    - Writing Style/Communication Style
    - Manager/Reports To
    - About/Bio/About Me
    """
    # Helper to find column by multiple possible names
    def get_col(row: Dict, *names: str, default: str = "") -> str:
        for name in names:
            # Try exact match first
            if name in row:
                return row[name].strip()
            # Try case-insensitive match
            for key in row.keys():
                if key.lower() == name.lower():
                    return row[key].strip()
        return default

    # Extract basic identity
    name = get_col(row, "Name", "Full Name", "Employee Name", "DisplayName")
    if not name:
        return None

    # Generate email if not provided
    email = get_col(row, "Email", "Email Address", "UserPrincipalName")
    if not email:
        email = f"{normalize_folder_name(name).replace('.', '.')}@{domain}"

    role = get_col(row, "Role", "Job Title", "Position", "Title")
    department = get_col(row, "Department", "Team", "Division", default="General")
    location = get_col(row, "Location", "Office", "Office Location", default="London")

    # Personality traits
    writing_style = get_col(row, "Writing Style", "Style")
    communication_style = get_col(row, "Communication Style", "Comm Style")
    specialization = get_col(row, "Specialization", "Focus", "Expertise")
    languages = parse_languages(get_col(row, "Languages", "Language"))
    skills = parse_skills(get_col(row, "Skills", "Skill Set"))

    # Relationships
    manager = get_col(row, "Manager", "Reports To", "Manager Email")
    if manager and "@" not in manager:
        # Convert name to email format
        manager = f"{normalize_folder_name(manager).replace('.', '.')}@{domain}"

    # About
    about = get_col(row, "About", "Bio", "About Me", "Description")

    # Create persona
    identity = PersonaIdentity(
        name=name,
        email=email,
        role=role,
        department=department,
        job_title=role,
        office_location=location,
    )

    personality = PersonaPersonality(
        writing_style=writing_style or "Professional",
        communication_style=communication_style or "Clear and concise",
        specialization=specialization or department,
        languages=languages or ["English"],
        skills=skills or [],
    )

    work_preferences = PersonaWorkPreferences(
        email_check_frequency_minutes=get_email_frequency(role),
        response_time_sla_hours=get_sla_hours(role),
        timezone=get_timezone(location),
    )

    relationships = PersonaRelationships(
        manager_email=manager if manager else None,
        auto_accept_meetings_from=[],
    )

    return Persona(
        identity=identity,
        personality=personality,
        work_preferences=work_preferences,
        relationships=relationships,
        about_me=about,
    )


def import_csv(
    csv_path: str,
    output_dir: str = "agents",
    domain: str = "textcraft.onmicrosoft.com",
) -> List[Dict[str, Any]]:
    """
    Import agents from CSV and create persona folders.

    Args:
        csv_path: Path to CSV file
        output_dir: Directory to create persona folders in
        domain: Email domain if not specified in CSV

    Returns:
        List of created persona dictionaries
    """
    csv_path = Path(csv_path)
    output_path = Path(output_dir)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # Create output directory if needed
    output_path.mkdir(parents=True, exist_ok=True)

    created_personas = []

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            persona = parse_csv_row(row, domain)
            if not persona:
                continue

            # Create folder for this persona
            folder_name = normalize_folder_name(persona.identity.name)
            persona_folder = output_path / folder_name
            persona_folder.mkdir(exist_ok=True)

            # Write persona.json
            persona_file = persona_folder / "persona.json"
            with open(persona_file, "w", encoding="utf-8") as pf:
                json.dump(persona.to_dict(), pf, indent=2, ensure_ascii=False)

            created_personas.append(
                {
                    "folder": str(persona_folder),
                    "name": persona.identity.name,
                    "email": persona.identity.email,
                    "role": persona.identity.role,
                    "department": persona.identity.department,
                }
            )

    return created_personas


def create_sample_csv(output_path: str = "sample_employees.csv"):
    """Create a sample CSV file for testing."""
    sample_data = [
        {
            "Name": "Victoria Palmer",
            "Email": "victoria.palmer@textcraft.onmicrosoft.com",
            "Role": "Editorial Director",
            "Department": "Editorial",
            "Location": "London",
            "Languages": "English (Native), French (Professional)",
            "Skills": "Editorial leadership, Style governance, Quality assurance",
            "Writing Style": "Authoritative, Style Guardian",
            "Manager": "",
            "About": "Leads the Editorial team ensuring consistent quality across all TextCraft output. Former editor at a major British publishing house with 18 years experience.",
        },
        {
            "Name": "Francois Moreau",
            "Email": "francois.moreau@textcraft.onmicrosoft.com",
            "Role": "Senior Editor - Literary",
            "Department": "Editorial",
            "Location": "Paris",
            "Languages": "French (Native), English (Fluent), Spanish (Conversational)",
            "Skills": "Fiction editing, Poetry, Narrative craft",
            "Writing Style": "Literary, Thoughtful",
            "Manager": "Victoria Palmer",
            "About": "Senior literary editor specializing in fiction and poetry. Brings a deep appreciation for narrative craft and the musicality of language.",
        },
    ]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sample_data[0].keys())
        writer.writeheader()
        writer.writerows(sample_data)

    return output_path


if __name__ == "__main__":
    # Test the importer
    import sys

    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        # Create and use sample
        csv_file = create_sample_csv()
        print(f"Created sample CSV: {csv_file}")

    personas = import_csv(csv_file)
    print(f"\nImported {len(personas)} personas:")
    for p in personas:
        print(f"  - {p['name']} ({p['role']}) -> {p['folder']}")
