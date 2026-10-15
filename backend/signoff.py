"""Sign-off rules from firm.starter_standards.

Sign-off means a review status of verified. A note that stays in
needs_review or blocked is not a sign-off.

Two rules are enforced:

- The assigned preparer cannot sign off work they prepared.
- An adjustment whose federal or California tax effect is over $1,000
  can be signed only by a partner.

Other roles can leave a note. Only the reviewer and the partner can sign.
"""
from __future__ import annotations


class SignoffDenied(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _is_line(ref: str) -> bool:
    if ref.startswith(("doc:", "qa-", "msg-", "call-", "household:", "py:", "agency:", "ev-", "timeline:", "asset:", "ref:")):
        return False
    return "." in ref


def _money(amount: float | None) -> str:
    if amount is None:
        return "not estimated"
    return f"${amount:,.2f}"


def requirements(line_key: str, findings: list[dict]) -> list[dict]:
    matched = []
    for finding in findings:
        effect = finding.get("tax_effect")
        if effect is None:
            continue
        if line_key not in [ref for ref in finding["refs"] if _is_line(ref)]:
            continue
        matched.append({
            "finding_id": finding["id"],
            "title": finding["title"],
            "federal": effect["federal"],
            "california": effect["california"],
            "partner_required": effect["partner_required"],
            "method": effect["method"],
        })
    return matched


def describe(line_key: str, findings: list[dict], staff: dict, assignment: dict) -> dict:
    effects = requirements(line_key, findings)
    preparer = staff[assignment["preparer"]]
    reviewer = staff[assignment["reviewer"]]
    partner = staff[assignment["partner"]]
    partner_required = any(item["partner_required"] for item in effects)
    blocking = next((item for item in effects if item["partner_required"]), None)
    shown = blocking or (effects[0] if effects else None)
    if partner_required and shown is not None:
        summary = (
            f"{preparer.name} prepared this return and cannot sign it off. "
            f"The correction changes federal tax by {_money(shown['federal'])} and California tax by {_money(shown['california'])}. "
            f"A tax effect over $1,000 requires {partner.name}, the partner, to sign."
        )
    elif shown is not None:
        summary = (
            f"{preparer.name} prepared this return and cannot sign it off. "
            f"The computed tax effect is {_money(shown['federal'])} federal and {_money(shown['california'])} California. "
            f"That is within the reviewer's $1,000 limit, so {reviewer.name} can sign."
        )
    else:
        summary = (
            f"{preparer.name} prepared this return and cannot sign it off. "
            f"This line has no computed adjustment over $1,000, so {reviewer.name} can sign."
        )
    return {
        "assigned_preparer": preparer.id,
        "assigned_reviewer": reviewer.id,
        "assigned_partner": partner.id,
        "partner_required": partner_required,
        "summary": summary,
        "method": shown["method"] if shown else None,
        "effects": effects,
    }


def direct_dependents(line_key: str, lines: dict) -> list[str]:
    """Lines that name this line as a calculation input. One step, not the whole return."""
    return sorted(
        key for key, line in lines.items()
        if key != line_key and line_key in (line.get("inputs") or [])
    )


def invalidation_reason(input_line: str) -> str:
    return f"The sign-off was cleared because a later note on {input_line} changed an input this line uses."


def check_signoff(actor_id: str, status: str, line_key: str, findings: list[dict], staff: dict, assignment: dict) -> dict:
    described = describe(line_key, findings, staff, assignment)
    if status != "verified":
        return described
    member = staff[actor_id]
    if actor_id == assignment["preparer"]:
        raise SignoffDenied(f"{member.name} prepared this return. A person may not sign off on work they prepared.")
    if member.role not in {"reviewer", "partner"}:
        role = member.role.replace("_", " ")
        raise SignoffDenied(f"{member.name} is a {role}. Sign-off is done by the reviewer or the partner.")
    if described["partner_required"] and member.role != "partner":
        shown = next(item for item in described["effects"] if item["partner_required"])
        raise SignoffDenied(
            f"The correction on {line_key} changes federal tax by {_money(shown['federal'])} "
            f"and California tax by {_money(shown['california'])}. "
            "A tax effect over $1,000 requires partner sign-off."
        )
    return described
