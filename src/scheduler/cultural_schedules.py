"""Country-specific work schedule definitions.

Maps ISO 3166-1 alpha-2 country codes (and common usage locations)
to work hours, lunch breaks, and timezone defaults.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CulturalSchedule:
    """Work schedule for a specific country/culture."""

    country_code: str
    timezone: str
    work_start: str  # "HH:MM"
    work_end: str  # "HH:MM"
    lunch_start: str  # "HH:MM"
    lunch_end: str  # "HH:MM"
    breaks: List[str] = field(default_factory=list)  # ["HH:MM-HH:MM", ...]

    @property
    def work_start_hour(self) -> int:
        return int(self.work_start.split(":")[0])

    @property
    def work_end_hour(self) -> int:
        return int(self.work_end.split(":")[0])

    @property
    def lunch_start_hour(self) -> float:
        parts = self.lunch_start.split(":")
        return int(parts[0]) + int(parts[1]) / 60

    @property
    def lunch_end_hour(self) -> float:
        parts = self.lunch_end.split(":")
        return int(parts[0]) + int(parts[1]) / 60


# Default schedules per country
# Based on typical European work culture norms
CULTURAL_SCHEDULES: Dict[str, CulturalSchedule] = {
    "IT": CulturalSchedule(
        country_code="IT",
        timezone="Europe/Rome",
        work_start="09:00",
        work_end="18:00",
        lunch_start="12:30",
        lunch_end="14:00",
    ),
    "SE": CulturalSchedule(
        country_code="SE",
        timezone="Europe/Stockholm",
        work_start="08:00",
        work_end="16:30",
        lunch_start="12:00",
        lunch_end="13:00",
        breaks=["10:00-10:15", "15:00-15:15"],  # Fika
    ),
    "FR": CulturalSchedule(
        country_code="FR",
        timezone="Europe/Paris",
        work_start="09:30",
        work_end="18:30",
        lunch_start="12:30",
        lunch_end="14:00",
    ),
    "DE": CulturalSchedule(
        country_code="DE",
        timezone="Europe/Berlin",
        work_start="08:30",
        work_end="17:00",
        lunch_start="12:00",
        lunch_end="13:00",
    ),
    "ES": CulturalSchedule(
        country_code="ES",
        timezone="Europe/Madrid",
        work_start="09:00",
        work_end="19:00",
        lunch_start="14:00",
        lunch_end="16:00",
    ),
    "PL": CulturalSchedule(
        country_code="PL",
        timezone="Europe/Warsaw",
        work_start="08:00",
        work_end="16:00",
        lunch_start="12:00",
        lunch_end="12:30",
    ),
    "NL": CulturalSchedule(
        country_code="NL",
        timezone="Europe/Amsterdam",
        work_start="08:30",
        work_end="17:00",
        lunch_start="12:00",
        lunch_end="13:00",
    ),
    "BE": CulturalSchedule(
        country_code="BE",
        timezone="Europe/Brussels",
        work_start="08:30",
        work_end="17:30",
        lunch_start="12:00",
        lunch_end="13:00",
    ),
    "PT": CulturalSchedule(
        country_code="PT",
        timezone="Europe/Lisbon",
        work_start="09:00",
        work_end="18:00",
        lunch_start="13:00",
        lunch_end="14:00",
    ),
    "AT": CulturalSchedule(
        country_code="AT",
        timezone="Europe/Vienna",
        work_start="08:00",
        work_end="16:30",
        lunch_start="12:00",
        lunch_end="13:00",
    ),
    "DK": CulturalSchedule(
        country_code="DK",
        timezone="Europe/Copenhagen",
        work_start="08:00",
        work_end="16:00",
        lunch_start="12:00",
        lunch_end="12:30",
    ),
    "IE": CulturalSchedule(
        country_code="IE",
        timezone="Europe/Dublin",
        work_start="09:00",
        work_end="17:30",
        lunch_start="13:00",
        lunch_end="14:00",
    ),
    "CH": CulturalSchedule(
        country_code="CH",
        timezone="Europe/Zurich",
        work_start="08:00",
        work_end="17:00",
        lunch_start="12:00",
        lunch_end="13:00",
    ),
    "GB": CulturalSchedule(
        country_code="GB",
        timezone="Europe/London",
        work_start="09:00",
        work_end="17:30",
        lunch_start="12:30",
        lunch_end="13:30",
    ),
}

# Map full country names and usage locations to codes
COUNTRY_NAME_TO_CODE: Dict[str, str] = {
    "Italy": "IT",
    "Sweden": "SE",
    "France": "FR",
    "Germany": "DE",
    "Spain": "ES",
    "Poland": "PL",
    "Netherlands": "NL",
    "Belgium": "BE",
    "Portugal": "PT",
    "Austria": "AT",
    "Denmark": "DK",
    "Ireland": "IE",
    "Switzerland": "CH",
    "United Kingdom": "GB",
    # Usage location codes
    "IT": "IT",
    "SE": "SE",
    "FR": "FR",
    "DE": "DE",
    "ES": "ES",
    "PL": "PL",
    "NL": "NL",
    "BE": "BE",
    "PT": "PT",
    "AT": "AT",
    "DK": "DK",
    "IE": "IE",
    "CH": "CH",
    "GB": "GB",
}


def get_cultural_schedule(
    country: Optional[str] = None,
    usage_location: Optional[str] = None,
) -> CulturalSchedule:
    """Get cultural schedule from country name or usage location code.

    Falls back to GB (United Kingdom) if no match found.
    """
    lookup = country or usage_location or "GB"
    code = COUNTRY_NAME_TO_CODE.get(lookup, lookup.upper())
    return CULTURAL_SCHEDULES.get(code, CULTURAL_SCHEDULES["GB"])
