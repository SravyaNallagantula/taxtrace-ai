"""Compare two adjacent engine versions using the packet's stored diff.

The difference between summary totals is later minus earlier. It is not a new
tax computation, and it is not a combined return.
"""
from __future__ import annotations

from decimal import Decimal


class VersionsNotAdjacent(Exception):
    def __init__(self) -> None:
        super().__init__("Only the stored step from one version to the next can be compared.")


def _delta(later, earlier):
    if isinstance(later, bool) or isinstance(earlier, bool):
        return None
    if not isinstance(later, (int, float)) or not isinstance(earlier, (int, float)):
        return None
    value = Decimal(str(later)) - Decimal(str(earlier))
    if value == value.to_integral():
        return int(value)
    return float(value.quantize(Decimal("0.01")))


def compare_versions(versions: list[dict], earlier: str, later: str, current_keys: set[str]) -> dict:
    order = [item["version"] for item in versions]
    by_version = {item["version"]: item for item in versions}
    if earlier not in by_version or later not in by_version:
        raise KeyError(earlier if earlier not in by_version else later)
    if order.index(later) != order.index(earlier) + 1:
        raise VersionsNotAdjacent
    before = by_version[earlier]
    after = by_version[later]
    labels: dict[str, str] = {}
    for version in (before, after):
        for line in version["lines"]:
            labels[line["key"]] = line["label"]
    changes = []
    counts = {"changed": 0, "added": 0, "removed": 0}
    for item in after["changes_from_previous"]:
        kind = item["change"]
        counts[kind] = counts.get(kind, 0) + 1
        changes.append({
            "key": item["key"],
            "label": labels.get(item["key"]),
            "change": kind,
            "old": item.get("old"),
            "new": item.get("new"),
            "on_current": item["key"] in current_keys,
        })
    difference = {
        side: {
            field: delta
            for field, delta in (
                (field, _delta(after["summary"][side].get(field), before["summary"][side].get(field)))
                for field in after["summary"][side]
                if field in before["summary"][side]
            )
            if delta is not None
        }
        for side in ("federal", "california")
    }
    return {
        "earlier": earlier,
        "later": later,
        "earlier_computed_at": before["computed_at"],
        "later_computed_at": after["computed_at"],
        "earlier_trigger": before["trigger"],
        "later_trigger": after["trigger"],
        "earlier_summary": before["summary"],
        "later_summary": after["summary"],
        "summary_difference": difference,
        "note": "Each difference is the later stored summary minus the earlier stored summary. This is not a new computation.",
        "counts": counts,
        "changes": changes,
    }
