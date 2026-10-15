"""Deterministic comparisons between the printed page, the extraction, and v3.

These checks do not recompute the tax return. Dollar effects multiply a
documented difference by the v3 rate for that category, or copy a named
what_if result. They are not a new return.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

# Firm starter_standards: partner sign-off when the tax effect is over this amount.
PARTNER_TAX_THRESHOLD = 1000


def independent_findings(data: dict) -> list[dict]:
    docs = {doc["id"]: doc for doc in data["documents"]}
    facts = {fact["id"]: fact for fact in data["extracted_values"]}
    version = next(item for item in data["return_versions"] if item["version"] == "v3")
    lines = {line["key"]: line for line in version["lines"]}
    rates = version["tax_effect_rates"]
    findings = [
        _mileage_duplicate(docs),
        _duplicate_w2(docs),
        _rsu_basis(docs, lines, rates),
        _double_counted_card_receipts(docs, facts, lines, rates),
        _federal_estimate(data, lines),
        _california_estimate_year(facts, lines),
        _vehicle_donation(facts, lines, rates),
        _self_employed_health(data, lines, rates),
        _hvac_repair(docs, data, lines),
        _spotify(docs, lines, rates),
        _dependent_ssn(data, facts),
        _unread_broker_page(docs, facts, version),
    ]
    return [item for item in findings if item]


def _finding(
    finding_id: str,
    title: str,
    description: str,
    severity: str,
    refs: list[str],
    tax_effect: dict | None = None,
) -> dict:
    item = {
        "id": finding_id,
        "title": title,
        "description": description,
        "severity": severity,
        "source": "independent document comparison",
        "refs": refs,
    }
    if tax_effect is not None:
        item["tax_effect"] = tax_effect
    return item


def _dollars(amount: float, rate: float) -> float:
    value = (Decimal(str(amount)) * Decimal(str(rate))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(value)


def _sum_dollars(*parts: float) -> float:
    total = sum((Decimal(str(part)) for part in parts), Decimal("0"))
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _tax_effect(federal: float, california: float | None, method: str) -> dict:
    partner = abs(federal) > PARTNER_TAX_THRESHOLD or (
        california is not None and abs(california) > PARTNER_TAX_THRESHOLD
    )
    return {
        "federal": federal,
        "california": california,
        "threshold": PARTNER_TAX_THRESHOLD,
        "partner_required": partner,
        "method": method,
    }


def _page_text(doc: dict) -> str:
    return "\n".join(page["printed_content"] for page in doc["pages"])


def _mileage_duplicate(docs: dict) -> dict | None:
    document = docs["D23"]
    page2 = document["pages"][1]["printed_content"]
    page3 = document["pages"][2]["printed_content"]
    duplicated = "Second scan" in page3 and page2.split("Mileage log May-Aug.")[1].strip() == page3.split("Mileage log May-Aug.")[1].strip()
    if not duplicated:
        return None
    return _finding(
        "independent-mileage-duplicate",
        "Duplicated mileage log page",
        "D23 page 3 identifies itself as a second scan of page 2, and the trip lines after the heading match. The annual total should be checked before those miles are counted twice.",
        "warning",
        ["doc:D23#page2", "doc:D23#page3"],
    )


def _duplicate_w2(docs: dict) -> dict | None:
    official = docs["D09"]["pages"][0]["printed_content"]
    photo = docs["D10"]["pages"][0]["printed_content"]
    if "Box 1 107,800.00" not in official or "Box 1 107,800.00" not in photo:
        return None
    return _finding(
        "independent-duplicate-w2",
        "Two copies of the same W-2",
        "D09 and D10 both report Halvorsen box 1 as $107,800. Wages on the return use D09 once. D10 is the phone photo described in msg-02.",
        "info",
        ["D09", "D10", "F1040.1a"],
    )


def _rsu_basis(docs: dict, lines: dict, rates: dict) -> dict | None:
    supplement = _page_text(docs["D11"])
    expected = ("19,100.00", "19,100.00", "9,420.00")
    if not all(amount in supplement for amount in expected):
        return None
    zero_basis = [
        key for key in ("F8949.B.N1", "F8949.B.N3", "F8949.E.N4")
        if "basis 0.00" in lines[key]["label"]
    ]
    if len(zero_basis) != 3:
        return None
    short_basis = 19100 + 19100
    long_basis = 9420
    federal = _sum_dollars(
        _dollars(short_basis, rates["stcg"]["federal_per_dollar"]),
        _dollars(long_basis, rates["ltcg"]["federal_per_dollar"]),
    )
    # N1 (2025-02-18) and N3 (2025-05-20) were sold during California residency.
    # N4 was sold 2025-08-12, after the 2025-07-15 move, so the blended gain rate is the wrong tool.
    california = _dollars(short_basis, rates["ca_source_income"]["california_per_dollar"])
    return _finding(
        "independent-rsu-basis",
        "RSU sales use basis $0",
        "D11 states adjusted basis of $19,100, $19,100, and $9,420 for the three Corvane RSU lots. Form 8949 reports basis $0 for N1, N3, and N4. The $38,200 of 2025 vest value is already on the Corvane W-2.",
        "warning",
        ["D11", "D08", "F8949.B.N1", "F8949.B.N3", "F8949.E.N4"],
        _tax_effect(
            federal,
            california,
            "Omitted short-term basis of $38,200 times the v3 short-term gain rate, plus omitted long-term basis of $9,420 times the v3 long-term gain rate. California uses the ca_source_income rate on the $38,200 only. N4 was sold after the move to Texas, so no California rate is applied to that lot.",
        ),
    )


def _double_counted_card_receipts(docs: dict, facts: dict, lines: dict, rates: dict) -> dict | None:
    books = _page_text(docs["D15"])
    line = lines["SchC.1"]
    if "12,400.00 arrived through Paywell" not in books:
        return None
    if line["value"] != 163700 or facts["ev-0103"]["value"] != 151300 or facts["ev-0127"]["value"] != 12400:
        return None
    duplicated = 12400
    category = rates["schc_profit"]
    return _finding(
        "independent-1099k-double-count",
        "Card receipts added on top of book income",
        "Schedule C gross receipts are $163,700, which is book income of $151,300 plus the Paywell 1099-K of $12,400. D15 says that $12,400 is the card portion of Atlas Outdoor Gear payments already included in sales.",
        "warning",
        ["D14", "D15", "D21", "SchC.1"],
        _tax_effect(
            _dollars(duplicated, category["federal_per_dollar"]),
            _dollars(duplicated, category["california_per_dollar"]),
            "The $12,400 already included in book sales, times the v3 Schedule C profit rate. That rate includes self-employment tax and the QBI interaction defined for this category.",
        ),
    )


def _federal_estimate(data: dict, lines: dict) -> dict | None:
    line = lines["F1040.26"]
    if line["value"] != 13000 or "qa-41" not in line["sources"]:
        return None
    january = [
        txn for snap in data["tax_agency_records"]["irs_account_transcript_2025"]
        for txn in snap["transactions"]
        if txn["date"] == "2026-01-15" and txn["code"] == "670"
    ]
    if not january or january[0]["amount"] != 3000:
        return None
    return _finding(
        "independent-federal-estimate",
        "Federal estimate uses the questionnaire, not the transcript",
        "Form 1040 line 26 is $13,000. Three $3,000 payments are on the EFTPS sheet. The fourth amount is questionnaire answer qa-41, $4,000. The IRS transcript shows a January 15 payment of $3,000.",
        "warning",
        ["D67", "F1040.26", "qa-41"],
        _tax_effect(
            0,
            0,
            "Line 26 is $1,000 higher than the IRS transcript. That changes the balance due. It does not change the tax, so the partner threshold does not apply.",
        ),
    )


def _california_estimate_year(facts: dict, lines: dict) -> dict | None:
    line = lines["F540NR.72"]
    year = facts["ev-1076"]
    if line["value"] != 14000 or year["field"] != "pay5_year" or str(year["value"]) != "2024":
        return None
    if "ev-1076" not in line["sources"]:
        return None
    return _finding(
        "independent-california-estimate-year",
        "California credits a payment designated 2024",
        "Form 540NR line 72 is $14,000 and includes the September 15 payment of $3,500 whose year field is 2024. The FTB account holds that payment as a 2024 credit. The 2025 payments are the other three amounts of $3,500.",
        "warning",
        ["D68", "F540NR.72"],
        _tax_effect(
            0,
            0,
            "The $3,500 payment is held by the FTB as a 2024 credit. Including it on the 2025 return changes the California balance. It does not change the tax.",
        ),
    )


def _vehicle_donation(facts: dict, lines: dict, rates: dict) -> dict | None:
    claimed = lines["F8283.A1.vehicle"]["value"]
    box = next(
        (fact for fact in facts.values() if fact["document_id"] == "D66" and fact["field"] == "box4c"),
        None,
    )
    if claimed != 6000 or box is None or box["value"] != 2900:
        return None
    overstated = 6000 - 2900
    category = rates["itemized"]
    return _finding(
        "independent-vehicle-proceeds",
        "Vehicle donation uses $6,000 instead of sale proceeds",
        "Form 8283 deducts $6,000 from the questionnaire. Form 1098-C says the charity sold the Subaru and box 4c gross proceeds are $2,900.",
        "warning",
        ["D66", "qa-39", "F8283.A1.vehicle"],
        _tax_effect(
            _dollars(overstated, abs(category["federal_per_dollar"])),
            _dollars(overstated, abs(category["california_per_dollar"])),
            "The deduction is $3,100 above box 4c proceeds. The tax change uses the v3 itemized-deduction rate.",
        ),
    )


def _self_employed_health(data: dict, lines: dict, rates: dict) -> dict | None:
    line = lines["Sch1.17"]
    answer = next(item["answer"] for item in data["client"]["questionnaire"] if item["id"] == "qa-25")
    if line["value"] != 14400 or "qa-25" in line["sources"] or "family coverage" not in answer:
        return None
    return _finding(
        "independent-se-health",
        "Self-employed health insurance deducted despite employer coverage",
        "Schedule 1 line 17 deducts $14,400 from the premium statement. Questionnaire qa-25 says both of Ngozi's employers offered family coverage. That answer is not a source on the line.",
        "warning",
        ["D25", "qa-25", "Sch1.17"],
        _tax_effect(
            _dollars(14400, abs(rates["adjustment"]["federal_per_dollar"])),
            _dollars(14400, abs(rates["adjustment"]["california_per_dollar"])),
            "If the $14,400 deduction is disallowed, the v3 adjustment rate applies. That rate does not capture the QBI change, so the federal figure is incomplete.",
        ),
    )


def _hvac_repair(docs: dict, data: dict, lines: dict) -> dict | None:
    note = lines["SchE.14A"].get("note") or ""
    invoice = _page_text(docs["D47"])
    scenario = next((item for item in data["what_if"]["alternatives"] if item["id"] == "hvac_improvement"), None)
    if "11,000.00" not in note or "heat pump" not in invoice or scenario is None:
        return None
    federal = scenario["federal"]["total_tax_change"]
    california = scenario["california"]["total_tax_change"]
    return _finding(
        "independent-hvac",
        "Heat-pump replacement is inside repairs",
        f"Schedule E includes the $11,000 Fremont Way invoice in repairs. The invoice is a full heat-pump replacement with a permit. The packet's hvac_improvement alternative raises federal tax by {federal} and California tax by {california}.",
        "warning",
        ["D47", "D46", "SchE.14A"],
        _tax_effect(
            float(federal),
            float(california),
            "Copied from the packet what_if result hvac_improvement. This is the engine's precomputed alternative, not a new calculation.",
        ),
    )


def _spotify(docs: dict, lines: dict, rates: dict) -> dict | None:
    detail = _page_text(docs["D15"])
    if "Spotify Family 216.00" not in detail or lines["SchC.27a.1"]["value"] != 6850:
        return None
    return _finding(
        "independent-spotify",
        "Spotify Family is inside software expense",
        "D15 includes Spotify Family at $216 in software and subscriptions of $6,850, and Schedule C deducts the full account. The March 26 call says that charge is personal.",
        "info",
        ["D15", "SchC.27a.1", "call-01"],
        _tax_effect(
            _dollars(216, rates["schc_profit"]["federal_per_dollar"]),
            _dollars(216, rates["schc_profit"]["california_per_dollar"]),
            "The $216 Spotify Family charge is inside the software deduction. The tax change uses the v3 Schedule C profit rate.",
        ),
    )


def _dependent_ssn(data: dict, facts: dict) -> dict | None:
    theo = next(person for person in data["household"]["people"] if person["id"] == "theo")
    card = next(fact for fact in facts.values() if fact["document_id"] == "D71" and fact["field"] == "ssn")
    if theo["ssn"] == card["value"]:
        return None
    return _finding(
        "independent-theo-ssn",
        "Dependent SSN on the organizer does not match the card",
        "Theo's organizer SSN and the Social Security card in D71 are different. Federal e-file was rejected with R0000-504-02 and accepted the next day, after the card arrived. v3 was computed before that correction.",
        "warning",
        ["D71", "household:theo"],
    )


def _unread_broker_page(docs: dict, facts: dict, version: dict) -> dict | None:
    page = docs["D31"]["pages"][-1]["printed_content"]
    warned = any(diag["code"] == "BROKER_SUMMARY_DETAIL_MISMATCH" for diag in version["diagnostics"])
    extracted = any(fact["document_id"] == "D31" and fact["field"] == "M18_proceeds" for fact in facts.values())
    if "proceeds 250.00" not in page or extracted or not warned:
        return None
    return _finding(
        "independent-meridian-page-32",
        "Unread brokerage page explains the $250 gap",
        "D31 page 32 prints Ironwood REIT lot M18 with proceeds of $250.00 and basis of $310.00. No extracted value exists for that lot. The engine warning that summary proceeds exceed the lots by $250 is this page.",
        "warning",
        ["D31", "D30"],
    )
