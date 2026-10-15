"""Prior-year variance flags and cross-document ties.

A variance is the firm's review flag: the line changed by more than 10 percent
and by more than $1,000. It is not a correction. Agreed ties are sums of
printed amounts. Open ties stay unexplained and are not given a tax effect.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def reconciliation(data: dict) -> dict:
    version = next(item for item in data["return_versions"] if item["version"] == "v3")
    lines = {line["key"]: line for line in version["lines"]}
    facts = {fact["id"]: fact for fact in data["extracted_values"]}
    rule = data["firm"]["starter_standards"]["variance_review"]
    return {
        "variance_rule": {
            "compare_to": rule["compare_to"],
            "flag_if_change_over_percent": rule["flag_if_change_over_percent"],
            "and_over_amount": rule["and_over_amount"],
            "note": (
                "The firm asks for an explanation when a line changes by more than both limits "
                "from the 2024 return. A flag is not a tax correction and it does not change the return."
            ),
        },
        "variances": _variances(data, lines, rule),
        "agreed": [item for item in (
            _agree_wages(facts, lines),
            _agree_mileage(data, facts, lines),
            _agree_mortgage(facts, lines),
            _agree_espp(facts, lines),
            _agree_prior_agi(data),
        ) if item],
        "open": [item for item in (
            _open_phone(facts, data, lines),
            _open_california_wages(data, lines),
        ) if item],
    }


def _variances(data: dict, lines: dict, rule: dict) -> list[dict]:
    prior = data["prior_years"]["return_2024"]["lines"]
    amount_limit = Decimal(str(rule["and_over_amount"]))
    percent_limit = Decimal(str(rule["flag_if_change_over_percent"]))
    flagged = []
    for key, old in prior.items():
        current = lines.get(key)
        if current is None:
            continue
        new = current["value"]
        if isinstance(old, bool) or isinstance(new, bool):
            continue
        if not isinstance(old, (int, float)) or not isinstance(new, (int, float)):
            continue
        before = Decimal(str(old))
        after = Decimal(str(new))
        change = after - before
        if abs(change) <= amount_limit:
            continue
        if before != 0 and (abs(change) / abs(before) * Decimal("100")) <= percent_limit:
            continue
        percent = None
        if before != 0:
            percent = float((abs(change) / abs(before) * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        flagged.append({
            "line_key": key,
            "label": current["label"],
            "prior": _plain(before),
            "current": _plain(after),
            "change": _plain(change),
            "percent": percent,
        })
    flagged.sort(key=lambda item: (-abs(Decimal(str(item["change"]))), item["line_key"]))
    return flagged


def _plain(value: Decimal):
    if value == value.to_integral():
        return int(value)
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _money(value: Decimal) -> str:
    number = _plain(value)
    if isinstance(number, int):
        return f"${number:,}"
    return f"${number:,.2f}"


def _fact(facts: dict, document_id: str, field: str) -> dict | None:
    return next((fact for fact in facts.values() if fact["document_id"] == document_id and fact["field"] == field), None)


def _page(data: dict, document_id: str) -> str:
    document = next(item for item in data["documents"] if item["id"] == document_id)
    return "\n".join(page["printed_content"] for page in document["pages"])


def _agree_wages(facts: dict, lines: dict) -> dict | None:
    first = _fact(facts, "D08", "box1")
    second = _fact(facts, "D09", "box1")
    photo = _fact(facts, "D10", "box1")
    line = lines.get("F1040.1a")
    if not first or not second or not photo or not line:
        return None
    total = Decimal(str(first["value"])) + Decimal(str(second["value"]))
    if total != Decimal(str(line["value"])) or Decimal(str(photo["value"])) != Decimal(str(second["value"])):
        return None
    return {
        "id": "agree-wages",
        "title": "Wages match the two W-2s",
        "detail": (
            f"Form 1040 line 1a is {_money(Decimal(str(line['value'])))}. "
            f"D08 box 1 is {_money(Decimal(str(first['value'])))} and D09 box 1 is {_money(Decimal(str(second['value'])))}. "
            "D10 repeats the D09 amount and is not added again."
        ),
        "refs": ["F1040.1a", "D08", "D09", "D10"],
    }


def _agree_mileage(data: dict, facts: dict, lines: dict) -> dict | None:
    start = _fact(facts, "D23", "odometer_start")
    end = _fact(facts, "D23", "odometer_end")
    business = lines.get("SchC.44a")
    other = lines.get("SchC.44c")
    deduction = lines.get("SchC.9")
    rate = data["engine_reference"]["parameters"].get("mileage_rate")
    if not start or not end or not business or not other or not deduction or rate is None:
        return None
    driven = Decimal(str(end["value"])) - Decimal(str(start["value"]))
    listed = Decimal(str(business["value"])) + Decimal(str(other["value"]))
    computed = (Decimal(str(business["value"])) * Decimal(str(rate))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if driven != listed or computed != Decimal(str(deduction["value"])):
        return None
    return {
        "id": "agree-mileage",
        "title": "Mileage log, odometer, and the mileage deduction agree",
        "detail": (
            f"The odometer moved from {_plain(Decimal(str(start['value']))):,} to {_plain(Decimal(str(end['value']))):,}, "
            f"which is {_plain(driven):,} miles. Business miles {_plain(Decimal(str(business['value']))):,} plus other miles "
            f"{_plain(Decimal(str(other['value']))):,} equal that distance. "
            f"Business miles times the packet mileage rate of {rate} equal the Schedule C deduction of {_money(Decimal(str(deduction['value'])))}."
        ),
        "refs": ["D23", "SchC.44a", "SchC.44c", "SchC.9"],
    }


def _agree_mortgage(facts: dict, lines: dict) -> dict | None:
    parts = (
        _fact(facts, "D55", "box1"),
        _fact(facts, "D56", "interest"),
        _fact(facts, "D57", "box1"),
        _fact(facts, "D55", "box6"),
    )
    line = lines.get("SchA.8a")
    if any(part is None for part in parts) or line is None:
        return None
    total = sum((Decimal(str(part["value"])) for part in parts), Decimal("0"))
    if total != Decimal(str(line["value"])):
        return None
    return {
        "id": "agree-mortgage",
        "title": "Mortgage interest matches the three Forms 1098",
        "detail": (
            "Schedule A line 8a equals D55 interest plus D56 payoff interest plus D57 interest plus D55 points: "
            f"{_money(total)}."
        ),
        "refs": ["SchA.8a", "D55", "D56", "D57"],
    }


def _agree_espp(facts: dict, lines: dict) -> dict | None:
    line = lines.get("F8949.A.N2")
    supplement = _fact(facts, "D11", "ESPP-2406_adjusted_basis")
    if line is None or supplement is None:
        return None
    label = line["label"]
    if "basis 3,825.00" not in label or "adjustment B -675.00" not in label:
        return None
    if Decimal(str(supplement["value"])) != Decimal("4500"):
        return None
    return {
        "id": "agree-espp",
        "title": "ESPP basis on the return includes the supplement adjustment",
        "detail": (
            "Form 8949 prints broker basis 3,825.00 and code B adjustment -675.00 for the ESPP lot. "
            "D11 adjusted basis is 4,500. 3,825 plus 675 is 4,500. The broker basis is not a second error."
        ),
        "refs": ["F8949.A.N2", "D11", "D28"],
    }


def _agree_prior_agi(data: dict) -> dict | None:
    organizer = data["household"].get("prior_year_agi_for_esignature")
    filed = data["prior_years"]["return_2024"]["lines"].get("F1040.11")
    if organizer is None or filed is None:
        return None
    if Decimal(str(organizer)) != Decimal(str(filed)):
        return None
    return {
        "id": "agree-prior-agi",
        "title": "Prior-year AGI matches the 2024 return",
        "detail": (
            f"The organizer prior-year AGI and the 2024 Form 1040 line 11 are both {_money(Decimal(str(filed)))}."
        ),
        "refs": ["py:/return_2024/lines/F1040.11"],
    }


def _open_phone(facts: dict, data: dict, lines: dict) -> dict | None:
    mobile = _fact(facts, "D15", "phone_monthly")
    internet = _fact(facts, "D15", "internet_monthly")
    line = lines.get("SchC.25")
    notes = " ".join(note for call in data["client"]["call_notes"] for note in call["notes"])
    if not mobile or not internet or line is None:
        return None
    annual = (Decimal(str(mobile["value"])) + Decimal(str(internet["value"]))) * Decimal("12")
    if annual != Decimal(str(line["value"])):
        return None
    if "70%" not in notes or "50%" not in notes:
        return None
    return {
        "id": "open-phone-internet",
        "title": "Telephone and internet are deducted in full",
        "detail": (
            f"D15 shows a mobile plan of {_money(Decimal(str(mobile['value'])))} per month and internet of "
            f"{_money(Decimal(str(internet['value'])))} per month. Twelve months is {_money(annual)}, "
            "and Schedule C line 25 deducts that full amount. The March 26 call estimates business use at "
            "70 percent of the mobile plan and 50 percent of internet. That estimate is not booked."
        ),
        "refs": ["D15", "SchC.25", "call-01"],
    }


def _open_california_wages(data: dict, lines: dict) -> dict | None:
    federal = lines.get("F1040.1a")
    california = lines.get("SchCA540NR.1.E")
    addition = lines.get("SchCA540NR.1.C")
    if not federal or not california or not addition:
        return None
    if "California as the work state through 09/30/2025" not in _page(data, "D09"):
        return None
    answer = next(item["answer"] for item in data["client"]["questionnaire"] if item["id"] == "qa-45")
    residency = next(item for item in data["household"]["residency"] if item["state"] == "CA")
    return {
        "id": "open-california-wages",
        "title": "California wages are higher than federal wages",
        "detail": (
            f"Federal wages are {_money(Decimal(str(federal['value'])))}. "
            f"Schedule CA line 1 column E is {_money(Decimal(str(california['value'])))}, "
            f"and column C additions are {_money(Decimal(str(addition['value'])))}. "
            f"D09 says Halvorsen kept California as the work state through 09/30/2025. "
            f"The household residency record ends California residency on {residency['to']}. "
            f"Questionnaire qa-45 says: {answer} No California tax is computed for this difference."
        ),
        "refs": ["F1040.1a", "SchCA540NR.1.E", "SchCA540NR.1.C", "D09", "qa-45"],
    }
