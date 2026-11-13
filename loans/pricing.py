"""Loan pricing, kept in whole pence to avoid floating-point errors.

The model mirrors the live Swiftella calculator and the FCA high-cost
short-term credit (HCSTC) price cap (CONC 5A):
  * interest and fees are capped at 0.8% of the amount borrowed per day;
  * total charges can never exceed 100% of the amount borrowed;
  * the GBP 15 processing fee is part of the capped charge, never added to it.

Months are counted as 30 days, as in the live calculator. The output is an
indicative maximum, not a representative APR or an offer of credit.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

DAILY_RATE = Decimal("0.008")
TOTAL_COST_CAP = Decimal("1.00")
PROCESSING_FEE_PENCE = 1500
DAYS_PER_MONTH = 30

MIN_AMOUNT_GBP = 100
MAX_AMOUNT_GBP = 1000
TERM_CHOICES = (1, 3, 6)


@dataclass
class Instalment:
    number: int
    due_date: date
    amount_pence: int


@dataclass
class LoanQuote:
    principal_pence: int
    term_months: int
    term_days: int
    processing_fee_pence: int
    interest_pence: int
    total_charges_pence: int
    total_repayable_pence: int
    apr_percent: Decimal
    instalments: list[Instalment] = field(default_factory=list)


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def quote(principal_pence: int, term_months: int, start: date | None = None) -> LoanQuote:
    if term_months not in TERM_CHOICES:
        raise ValueError(f"term_months must be one of {TERM_CHOICES}")
    if not MIN_AMOUNT_GBP * 100 <= principal_pence <= MAX_AMOUNT_GBP * 100:
        raise ValueError("principal outside permitted range")

    start = start or date.today()
    principal = Decimal(principal_pence)
    term_days = term_months * DAYS_PER_MONTH

    daily_capped = principal * DAILY_RATE * term_days
    total_cap = principal * TOTAL_COST_CAP
    total_charges = _round(min(daily_capped, total_cap))

    fee = min(PROCESSING_FEE_PENCE, total_charges)
    interest = total_charges - fee
    total_repayable = principal_pence + total_charges

    # Annualised rate on the same basis as the live calculator.
    rate = float(total_charges) / float(principal_pence)
    apr = Decimal(str(((1 + rate) ** (365 / term_days) - 1) * 100)).quantize(Decimal("0.1"))

    base, remainder = divmod(total_repayable, term_months)
    instalments = []
    for n in range(1, term_months + 1):
        amount = base + (remainder if n == term_months else 0)
        instalments.append(Instalment(n, add_months(start, n), amount))

    return LoanQuote(
        principal_pence=principal_pence,
        term_months=term_months,
        term_days=term_days,
        processing_fee_pence=fee,
        interest_pence=interest,
        total_charges_pence=total_charges,
        total_repayable_pence=total_repayable,
        apr_percent=apr,
        instalments=instalments,
    )


def gbp(pence: int) -> str:
    sign = "-" if pence < 0 else ""
    pounds, p = divmod(abs(int(pence)), 100)
    return f"{sign}£{pounds:,}.{p:02d}"
