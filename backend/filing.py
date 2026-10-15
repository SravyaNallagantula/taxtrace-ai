"""Filing gate from firm.starter_standards.

Three rules:

- A verified or blocked decision records the authority it relied on.
- An open review note blocks filing.
- Due diligence is documented for a credit this return actually claims.

The packet line stays unchanged. Completing Form 8867 means a verified
workpaper note on F8867.status, not a rewrite of the engine output.
"""
from __future__ import annotations


class AuthorityRequired(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def authority_choices(standards: dict) -> list[dict]:
    labels = {
        "agreed_to_source_document": "Agreed to the source document",
        "recalculated": "Recalculated",
        "confirmed_with_client": "Confirmed with the client",
        "agreed_to_prior_year": "Agreed to the prior-year return",
        "agreed_to_third_party_record": "Agreed to a third-party record",
    }
    return [
        {"id": code, "label": labels.get(code, code.replace("_", " "))}
        for code in standards["verification_types"]
    ]


def check_authority(status: str, authority: str | None, standards: dict) -> str | None:
    allowed = set(standards["verification_types"])
    if authority and authority not in allowed:
        raise AuthorityRequired("That authority is not one of the firm's verification types.")
    if status in {"verified", "blocked"} and authority not in allowed:
        raise AuthorityRequired(
            "A verified or blocked decision records the authority it relies on. "
            "Choose a verification type from the firm standards."
        )
    return authority or None


def _amount(line: dict | None) -> float | None:
    if line is None:
        return None
    value = line.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _item(item_id: str, name: str, claimed: bool, line_key: str | None, amount: float | None, detail: str) -> dict:
    return {
        "id": item_id,
        "name": name,
        "claimed": claimed,
        "line_key": line_key,
        "amount": amount,
        "detail": detail,
    }


def due_diligence_items(lines: dict, filing_status: str) -> list[dict]:
    ctc = lines.get("F8812.5")
    odc = lines.get("F8812.7")
    aotc = lines.get("F8863.7")
    credit = lines.get("F1040.19")
    ctc_amount = _amount(ctc)
    odc_amount = _amount(odc)
    aotc_amount = _amount(aotc)
    credit_amount = _amount(credit)
    eic = [line for line in lines.values() if "earned income credit" in str(line.get("label", "")).lower()]
    return [
        _item(
            "child_tax_credit",
            "Child tax credit",
            ctc_amount is not None and ctc_amount > 0,
            "F8812.5" if ctc else None,
            ctc_amount,
            (
                f"Form 8812 line 5 is ${ctc_amount:,.0f} for qualifying children under 17. "
                f"Form 1040 line 19 reports ${credit_amount:,.0f} after phase-out."
            ) if ctc_amount is not None and credit_amount is not None else "v3 has no child tax credit computation.",
        ),
        _item(
            "credit_for_other_dependents",
            "Credit for other dependents",
            odc_amount is not None and odc_amount > 0,
            "F8812.7" if odc else None,
            odc_amount,
            (
                f"Form 8812 line 7 is ${odc_amount:,.0f}. It is inside the same phase-out as the child tax credit."
            ) if odc_amount is not None else "v3 has no credit for other dependents.",
        ),
        _item(
            "american_opportunity_credit",
            "American opportunity credit",
            aotc_amount is not None and aotc_amount > 0,
            "F8863.7" if aotc else None,
            aotc_amount,
            "v3 has no American opportunity credit line." if aotc_amount is None
            else "Form 8863 line 7, the credit after phase-out, is 0. Due diligence applies when that credit is claimed." if aotc_amount == 0
            else f"Form 8863 line 7 is ${aotc_amount:,.0f}.",
        ),
        _item(
            "earned_income_credit",
            "Earned income credit",
            any(_amount(line) not in (None, 0) for line in eic),
            eic[0]["key"] if eic else None,
            _amount(eic[0]) if eic else None,
            "v3 has no earned income credit line." if not eic else eic[0]["label"],
        ),
        _item(
            "head_of_household",
            "Head of household",
            filing_status == "head_of_household",
            None,
            None,
            f"The organizer filing status is {filing_status.replace('_', ' ')}.",
        ),
    ]


def filing_readiness(lines: dict, reviews: list[dict], filing_status: str, standards: dict) -> dict:
    items = due_diligence_items(lines, filing_status)
    claimed = [item for item in items if item["claimed"]]
    checklist = lines.get("F8867.status")
    checklist_review = next((row for row in reviews if row["line_key"] == "F8867.status"), None)
    documented = checklist_review is not None and checklist_review["status"] == "verified" and bool(checklist_review.get("authority"))
    blockers = []
    for row in reviews:
        if row["status"] in {"needs_review", "blocked"}:
            if row.get("invalidated_reason"):
                message = row["invalidated_reason"] + " Open review notes block filing."
            else:
                message = f"{row['line_key']} has an open {row['status'].replace('_', ' ')} note. Open review notes block filing."
            blockers.append({
                "id": f"open-note:{row['line_key']}",
                "kind": "open_note",
                "line_key": row["line_key"],
                "message": message,
            })
        elif row["status"] == "verified" and not row.get("authority"):
            blockers.append({
                "id": f"missing-authority:{row['line_key']}",
                "kind": "missing_authority",
                "line_key": row["line_key"],
                "message": f"{row['line_key']} is verified without an authority. A judgment records the record it relied on.",
            })
    if claimed and not documented:
        names = " and ".join(item["name"].lower() for item in claimed)
        engine_value = checklist["value"] if checklist else "missing"
        blockers.append({
            "id": "due-diligence",
            "kind": "due_diligence",
            "line_key": "F8867.status",
            "message": (
                f"This return claims the {names}. "
                f"Form 8867 in the engine output is \"{engine_value}\". "
                "Filing waits until a reviewer or partner verifies that line and records the authority relied on."
            ),
        })
    if blockers:
        summary = "Filing stays blocked while a review note is open, a judgment has no authority, or a claimed credit has no documented due diligence."
    else:
        summary = "Open notes are cleared, judgments name their authority, and due diligence is documented for every credit this return claims."
    return {
        "ready": not blockers,
        "summary": summary,
        "blockers": blockers,
        "verification_types": authority_choices(standards),
        "due_diligence": {
            "checklist_line": "F8867.status",
            "engine_status": checklist["value"] if checklist else None,
            "workpaper_status": checklist_review["status"] if checklist_review else None,
            "documented": documented,
            "items": items,
        },
    }
