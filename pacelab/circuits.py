"""Circuit taxonomy: classify each Grand Prix into archetypes.

The classification is intentionally simple — circuit names mapped to a
small set of mutually exclusive primary characters:

* **street** — Monaco, Singapore, Baku, Jeddah, Las Vegas, Miami, etc.
* **high_speed** — Monza, Spa, Silverstone, Suzuka, Spielberg, Mexico City.
* **technical_low_speed** — Hungary, Zandvoort, Imola.
* **balanced_medium** — most permanent road courses that don't sit at an
  extreme: Bahrain, Barcelona, Australia, COTA, Sao Paulo, Shanghai.
* **high_deg** — circuits where tyre management dominates strategy:
  Bahrain (high), Spain, Singapore. (A circuit may carry this flag in
  addition to its primary character.)

This is opinionated. The classifications are documented and fixed; if
you disagree with one, open an issue and we'll discuss. The whole point
of this site is that every choice is auditable.
"""

from __future__ import annotations

# Map from FastF1 EventName -> primary archetype.
PRIMARY: dict[str, str] = {
    # Street circuits
    "Monaco Grand Prix": "street",
    "Singapore Grand Prix": "street",
    "Azerbaijan Grand Prix": "street",
    "Saudi Arabian Grand Prix": "street",
    "Las Vegas Grand Prix": "street",
    "Miami Grand Prix": "street",

    # High speed / power
    "Italian Grand Prix": "high_speed",
    "Belgian Grand Prix": "high_speed",
    "British Grand Prix": "high_speed",
    "Japanese Grand Prix": "high_speed",
    "Austrian Grand Prix": "high_speed",
    "Mexico City Grand Prix": "high_speed",
    "Mexican Grand Prix": "high_speed",
    "Russian Grand Prix": "high_speed",
    "Turkish Grand Prix": "high_speed",

    # Technical / low speed
    "Hungarian Grand Prix": "technical_low_speed",
    "Dutch Grand Prix": "technical_low_speed",
    "Emilia Romagna Grand Prix": "technical_low_speed",
    "Spanish Grand Prix": "technical_low_speed",  # arguable; goes here vs balanced

    # Balanced
    "Bahrain Grand Prix": "balanced_medium",
    "Australian Grand Prix": "balanced_medium",
    "United States Grand Prix": "balanced_medium",
    "São Paulo Grand Prix": "balanced_medium",
    "Sao Paulo Grand Prix": "balanced_medium",
    "Brazilian Grand Prix": "balanced_medium",
    "Chinese Grand Prix": "balanced_medium",
    "Canadian Grand Prix": "balanced_medium",
    "Abu Dhabi Grand Prix": "balanced_medium",
    "Qatar Grand Prix": "balanced_medium",
    "French Grand Prix": "balanced_medium",
    "Eifel Grand Prix": "balanced_medium",
    "Portuguese Grand Prix": "balanced_medium",
    "Tuscan Grand Prix": "balanced_medium",
    "Styrian Grand Prix": "balanced_medium",
    "70th Anniversary Grand Prix": "balanced_medium",
    "Sakhir Grand Prix": "balanced_medium",
    "German Grand Prix": "balanced_medium",
    "Malaysian Grand Prix": "balanced_medium",
}

# Additional tags (a circuit can carry zero or more).
SECONDARY_TAGS: dict[str, list[str]] = {
    "Bahrain Grand Prix": ["high_deg"],
    "Spanish Grand Prix": ["high_deg"],
    "Singapore Grand Prix": ["heat", "long"],
    "Qatar Grand Prix": ["heat", "high_deg"],
    "Monaco Grand Prix": ["overtake_hard"],
    "Hungarian Grand Prix": ["overtake_hard"],
    "Singapore Grand Prix_": ["overtake_hard"],
}

ARCHETYPE_LABELS: dict[str, str] = {
    "street": "Street",
    "high_speed": "High speed",
    "technical_low_speed": "Technical / low speed",
    "balanced_medium": "Balanced medium",
}


def classify(event_name: str) -> str:
    """Primary archetype for an Event. Returns 'balanced_medium' if unknown."""
    return PRIMARY.get(event_name, "balanced_medium")


def secondary_tags(event_name: str) -> list[str]:
    """Optional secondary tags."""
    return list(SECONDARY_TAGS.get(event_name, []))


__all__ = [
    "PRIMARY",
    "SECONDARY_TAGS",
    "ARCHETYPE_LABELS",
    "classify",
    "secondary_tags",
]
