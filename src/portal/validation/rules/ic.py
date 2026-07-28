"""ICRule — validates National Registration Identity Card (NRIC) number format.

Supports Malaysia NRIC format: YYYYMMDD-XX-XXXX
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from src.portal.validation.models import RuleStatus, ValidationContext
from src.portal.validation.rules.base import BaseRule


MY_NRIC_PATTERN = re.compile(r"^(\d{6})-?(\d{2})-?(\d{4})$")


@dataclass
class ICRule(BaseRule):
    """Validates NRIC format and optionally checks birth date validity.

    Config:
        country: Country code (default: "MY" for Malaysia)
        validate_date: If True, checks that the DOB portion is a valid date
    """

    country: str = "MY"
    validate_date: bool = True

    def validate(self, context: ValidationContext) -> RuleStatus:
        value = self.get_value(context)

        if value is None or not isinstance(value, str):
            return self.fail()

        ic = value.strip().replace("-", "")
        if not ic.isdigit() or len(ic) != 12:
            self.metadata["message"] = "IC must be 12 digits"
            return self.fail()

        if self.country == "MY":
            return self._validate_my(ic)
        return self.pass_()

    def _validate_my(self, ic: str) -> RuleStatus:
        """Validate Malaysia NRIC."""
        yymmdd = ic[:6]
        dd = int(yymmdd[4:6])
        mm = int(yymmdd[2:4])
        yy = int(yymmdd[:2])

        if dd < 1 or dd > 31 or mm < 1 or mm > 12:
            return self.fail()

        if self.validate_date:
            for century in (2000, 1900):
                year = century + yy
                try:
                    date(year, mm, dd)
                    return self.pass_()
                except ValueError:
                    continue
            self.metadata["message"] = "Invalid birth date in IC"
            return self.fail()

        return self.pass_()
