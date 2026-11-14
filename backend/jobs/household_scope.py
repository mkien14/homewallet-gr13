"""Limit production jobs to the same reviewed household scope as the API."""
from enum import Enum
from app.household_policy import public_registration


class PublicScope(Enum):
    EXCEPT_RETAINED = "public-except-retained"


def approved_households(config):
    if config.get("APP_ENV", "dev").strip().lower() != "production":
        return None
    if public_registration(config):
        return PublicScope.EXCEPT_RETAINED
    values = config.get("PRODUCTION_ALLOWED_HOUSEHOLD_IDS")
    if (
        not isinstance(values, (set, frozenset, list, tuple))
        or not values
        or any(type(value) is not int or value <= 1 for value in values)
    ):
        raise ValueError("Production jobs require approved household IDs excluding 1")
    return tuple(sorted(set(values)))


def household_filter(household_ids, column):
    """Return a parameterized AND clause; an explicit empty scope denies all."""
    if household_ids is None:
        return "", ()
    if household_ids is PublicScope.EXCEPT_RETAINED:
        return f" AND {column} > %s", (1,)
    if not household_ids:
        return " AND 1 = 0", ()
    placeholders = ", ".join("%s" for _ in household_ids)
    return f" AND {column} IN ({placeholders})", tuple(household_ids)
