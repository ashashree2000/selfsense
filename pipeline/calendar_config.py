"""Calendar assumptions used by the SYNTHETIC data generator and the feature pipeline.

ALL DATES HERE ARE ASSUMPTIONS for a synthetic demo. Festival dates are
approximate (lunar/regional festivals shift each year) and the dry days are a
plausible illustrative set, not an official excise calendar for any state.
"""
from datetime import date, timedelta


def _span(start: str, days: int) -> list[str]:
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(days)]


# date -> demand multiplier (approximate dates, assumptions)
FESTIVALS: dict[str, float] = {}
for d in _span("2025-09-28", 4):          # Durga Puja 2025 (Saptami..Navami, approx.)
    FESTIVALS[d] = 1.9
FESTIVALS["2025-10-20"] = 1.6              # Diwali 2025 (approx.)
FESTIVALS["2025-12-24"] = 1.5              # Christmas Eve
FESTIVALS["2025-12-25"] = 1.4              # Christmas
FESTIVALS["2025-12-31"] = 2.6              # New Year's Eve
for d in _span("2026-01-13", 3):          # Magh Bihu 2026 (Uruka + Bihu, approx.)
    FESTIVALS[d] = 2.0
for d in _span("2026-04-14", 3):          # Rongali / Bohag Bihu 2026 (approx.)
    FESTIVALS[d] = 1.8
for d in _span("2026-10-17", 3):          # Durga Puja 2026 (approx.)
    FESTIVALS[d] = 1.9
FESTIVALS["2026-11-08"] = 1.6              # Diwali 2026 (approx.)
FESTIVALS["2026-12-24"] = 1.5
FESTIVALS["2026-12-25"] = 1.4
FESTIVALS["2026-12-31"] = 2.6
for d in _span("2027-01-13", 3):          # Magh Bihu 2027 (approx.)
    FESTIVALS[d] = 2.0
for d in _span("2027-04-14", 3):          # Rongali Bihu 2027 (approx.)
    FESTIVALS[d] = 1.8

# Dry days: zero sales (illustrative assumption set)
DRY_DAYS: set[str] = {
    "2025-08-15", "2025-10-02", "2026-01-26", "2026-04-09",  # 2026-04-09: assumed poll-day closure
    "2026-08-15", "2026-10-02", "2027-01-26",
}

# Public holidays used as a calendar feature (not dry days)
HOLIDAYS: set[str] = {"2025-12-25", "2026-01-01", "2026-12-25", "2027-01-01"}


def is_payday(d: date) -> bool:
    """Month-start effect: assumed salary days 1st-5th."""
    return d.day <= 5
