"""Validators for UK-specific customer and bank data."""

import re
from datetime import date

from django.core.exceptions import ValidationError

# Royal Mail postcode format (covers all standard UK postcodes and GIR 0AA).
POSTCODE_RE = re.compile(
    r"^(GIR ?0AA|[A-PR-UWYZ]([0-9]{1,2}|[A-HK-Y][0-9]{1,2}|[0-9][A-HJKPS-UW]|[A-HK-Y][0-9][ABEHMNPRV-Y]) ?[0-9][ABD-HJLNP-UW-Z]{2})$"
)

# HMRC National Insurance number rules:
#  - first letter not D, F, I, Q, U or V; second letter not D, F, I, O, Q, U or V
#  - prefixes BG, GB, KN, NK, NT, TN and ZZ are never issued
#  - six digits then a suffix A-D
NINO_RE = re.compile(r"^(?!BG|GB|KN|NK|NT|TN|ZZ)[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z][0-9]{6}[A-D]$")

UK_PHONE_RE = re.compile(r"^(?:\+44|0)7\d{9}$|^(?:\+44|0)[1-3]\d{8,9}$")


def normalise_postcode(value: str) -> str:
    compact = re.sub(r"\s+", "", (value or "").upper())
    if len(compact) > 3:
        return f"{compact[:-3]} {compact[-3:]}"
    return compact


def validate_uk_postcode(value: str) -> None:
    if not POSTCODE_RE.match(normalise_postcode(value)):
        raise ValidationError("Enter a valid UK postcode, for example SW1A 1AA.")


def normalise_ni_number(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").upper())


def validate_ni_number(value: str) -> None:
    if not NINO_RE.match(normalise_ni_number(value)):
        raise ValidationError("Enter a valid National Insurance number, for example AB 12 34 56 C.")


def normalise_sort_code(value: str) -> str:
    return re.sub(r"[\s-]", "", value or "")


def validate_sort_code(value: str) -> None:
    if not re.fullmatch(r"\d{6}", normalise_sort_code(value)):
        raise ValidationError("Enter a 6-digit sort code, for example 12-34-56.")


def format_sort_code(value: str) -> str:
    digits = normalise_sort_code(value)
    return f"{digits[0:2]}-{digits[2:4]}-{digits[4:6]}" if len(digits) == 6 else digits


def normalise_account_number(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def validate_account_number(value: str) -> None:
    if not re.fullmatch(r"\d{8}", normalise_account_number(value)):
        raise ValidationError("Enter an 8-digit UK bank account number.")


def normalise_phone(value: str) -> str:
    return re.sub(r"[\s()-]", "", value or "")


def validate_uk_phone(value: str) -> None:
    if not UK_PHONE_RE.match(normalise_phone(value)):
        raise ValidationError("Enter a valid UK telephone number, for example 07700 900123.")


def validate_adult(dob: date, today: date | None = None) -> None:
    today = today or date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < 18:
        raise ValidationError("You must be 18 or over to apply.")
    if age > 120:
        raise ValidationError("Enter a valid date of birth.")
