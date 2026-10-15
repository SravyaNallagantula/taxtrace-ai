"""Hide Social Security numbers, account numbers, and IP PINs unless a cleared staff member asks."""
from __future__ import annotations

import re

SENSITIVE = re.compile(r"(?<!\d)666-\d{2}-\d{4}(?!\d)|(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)|(?i:IP PIN)\s*\d{6}")


def present(value, reveal: bool):
    if reveal or not isinstance(value, str):
        return value
    return SENSITIVE.sub("[REDACTED]", value)
