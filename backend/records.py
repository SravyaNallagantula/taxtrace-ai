"""Schedules, filing replay, notices, carryovers, and the firm's written standards.

Amounts come from the packet. Nothing here is a new return or a new e-file.
"""
from __future__ import annotations


def schedule_index(lines: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], dict] = {}
    ordered: list[dict] = []
    for line in lines:
        key = (line["form"], line["jurisdiction"])
        group = groups.get(key)
        if group is None:
            group = {"form": line["form"], "jurisdiction": line["jurisdiction"], "line_count": 0}
            groups[key] = group
            ordered.append(group)
        group["line_count"] += 1
    return ordered


def workpaper_records(data: dict) -> dict:
    version = next(item for item in data["return_versions"] if item["version"] == "v3")
    computed_at = version["computed_at"]
    standards = data["firm"]["starter_standards"]
    into = data["prior_years"]["carryovers_into_2025"]
    return {
        "replay": {
            "label": (
                "This is a replay of the packet. v3 is the current engine return. "
                "Approval, e-file, payment, refund, and the examination letter after that date "
                "are the scripted timeline, not a new filing."
            ),
            "computed_at": computed_at,
            "submissions": data["tax_agency_records"]["efile"],
            "events": [item for item in data["timeline"] if item["at"] >= computed_at],
        },
        "notices": data["tax_agency_records"]["notices"],
        "carryovers": {
            "into_2025": into,
            "out_of_2025": version["carryovers_out"],
        },
        "standards": {
            "note": standards["note"],
            "rules": standards["rules"],
            "required_steps": standards["required_steps"],
            "variance_review": standards["variance_review"],
        },
        "schedules": schedule_index(version["lines"]),
    }
