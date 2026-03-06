"""Team directory builder for KAM delegation.

Builds a compact text roster of available team members grouped by role,
with specialization, country, and email. Injected into KAM agent context
so they can pick the best team for each project.
"""

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _load_csv_data(csv_path: str = "textcraft-europe.csv") -> Dict[str, Dict]:
    """Load specialization and country data from CSV keyed by email."""
    path = Path(csv_path)
    if not path.exists():
        return {}

    data = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            email = row.get("email", "").lower()
            data[email] = {
                "specialization": row.get("Specialization", ""),
                "country": row.get("country", ""),
                "city": row.get("city", ""),
                "languages": row.get("languages", ""),
            }
    return data


def _categorize_role(job_title: str) -> Optional[str]:
    """Map a job title to a team category."""
    t = job_title.lower()
    if "writer" in t or "copywriter" in t:
        return "Writers"
    if "editor" in t or "copy chief" in t:
        return "Editors"
    if "proofread" in t or "fact check" in t or "consistency" in t or "plagiarism" in t:
        return "Quality Assurance"
    return None


def build_team_directory(
    persona_registry,
    exclude_email: str,
    csv_path: str = "textcraft-europe.csv",
) -> str:
    """Build compact team directory for KAM delegation.

    Returns a formatted string listing available team members grouped
    by role (Writers, Editors, QA) with specialization and country.
    """
    csv_data = _load_csv_data(csv_path)

    groups: Dict[str, List[str]] = {
        "Writers": [],
        "Editors": [],
        "Quality Assurance": [],
    }

    for persona in persona_registry.list_all():
        if persona.email.lower() == exclude_email.lower():
            continue

        job_title = persona.role or persona.job_title or ""
        category = _categorize_role(job_title)
        if not category:
            continue

        csv_row = csv_data.get(persona.email.lower(), {})
        spec = csv_row.get("specialization", "") or persona.specialization or ""
        country = csv_row.get("country", "")
        city = csv_row.get("city", "")
        location = city or country

        line = f"- {persona.name} | {job_title} | {spec} | {location} | {persona.email}"
        groups[category].append(line)

    lines = ["## Available Team Members\n"]
    for group_name in ["Writers", "Editors", "Quality Assurance"]:
        members = groups[group_name]
        if members:
            lines.append(f"### {group_name} ({len(members)})")
            lines.extend(sorted(members))
            lines.append("")

    result = "\n".join(lines)
    logger.info("Built team directory: %d writers, %d editors, %d QA",
                len(groups["Writers"]), len(groups["Editors"]), len(groups["Quality Assurance"]))
    return result
