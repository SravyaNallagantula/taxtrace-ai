"""Turn a source reference into something a reviewer can open."""
from __future__ import annotations

from backend.masking import present
from backend.runtime import RT


def resolve_source(ref: str, version: str, reveal: bool) -> dict:
    facts = RT.facts
    if ref in facts:
        fact = facts[ref]
        document = RT.docs[fact["document_id"]]
        value = fact["value"]
        if fact["value_type"] in ("ssn", "account_number"):
            value = present(value, reveal)
        return {
            "type": "extracted_fact",
            "ref": ref,
            "document_id": document["id"],
            "document_title": document["title"],
            "page": fact["page"],
            "field": fact["field"],
            "label": fact["label"],
            "value": value,
            "confidence": fact["confidence"],
            "position": fact["position"],
        }
    if ref in RT.answers:
        answer = RT.answers[ref]
        return {
            "type": "questionnaire",
            "ref": ref,
            "document_title": answer.question,
            "value": present(answer.answer, reveal),
        }
    if ref in RT.messages:
        message = RT.messages[ref]
        return {
            "type": "message",
            "ref": ref,
            "document_title": f"{message.from_name} to {message.to_name}",
            "value": present(message.text, reveal),
        }
    if ref in RT.calls:
        call = RT.calls[ref]
        return {
            "type": "call_note",
            "ref": ref,
            "document_title": f"Call on {call['date'][:10]}",
            "value": present(" ".join(call["notes"]), reveal),
        }
    if ref.startswith("py:"):
        return _pointer("prior_year", "Prior-year records", ref, RT.data["prior_years"], ref[3:], reveal)
    if ref.startswith("agency:"):
        return _pointer("agency_record", "Tax agency records", ref, RT.data["tax_agency_records"], ref[7:], reveal)
    if ref.startswith("ref:param."):
        return _dotted("engine_parameter", ref, RT.data["engine_reference"]["parameters"], ref[len("ref:param."):], reveal)
    if ref.startswith("ref:fx."):
        return _dotted("exchange_rate", ref, RT.data["engine_reference"]["parameters"]["fx"], ref[len("ref:fx."):], reveal)
    if ref.startswith("household:"):
        person = RT.people.get(ref.split(":", 1)[1])
        if person:
            return {
                "type": "household",
                "ref": ref,
                "document_title": person.name,
                "value": present(person.ssn, reveal),
                "field": person.role,
            }
    if ref.startswith("asset:"):
        asset_id = ref.split(":", 1)[1]
        asset = next((item for item in RT.versions[version]["assets"] if item.get("asset_id") == asset_id), None)
        if asset:
            return {"type": "asset", "ref": ref, "document_title": asset.get("description", asset_id), "value": asset.get("federal")}
    if ref.startswith("timeline:"):
        event_id = ref.split(":", 1)[1]
        event = next((item for item in RT.data["timeline"] if item["id"] == event_id), None)
        if event:
            return {"type": "timeline", "ref": ref, "document_title": event["event"], "value": event.get("detail")}
    if ref.startswith("doc:"):
        document_id = ref.split(":", 1)[1].split("#", 1)[0]
        document = RT.docs.get(document_id)
        if document:
            page = ref.split("#page", 1)[1] if "#page" in ref else None
            return {
                "type": "document_page",
                "ref": ref,
                "document_id": document_id,
                "document_title": document["title"],
                "page": int(page) if page and page.isdigit() else None,
            }
    return {"type": "other_reference", "ref": ref}


def _pointer(kind: str, title: str, ref: str, document: object, pointer: str, reveal: bool) -> dict:
    value = walk_pointer(document, pointer)
    shown = value if isinstance(value, (int, float, str, bool)) or value is None else None
    return {
        "type": kind,
        "ref": ref,
        "document_title": title,
        "field": pointer,
        "value": present(shown, reveal) if isinstance(shown, str) else shown,
    }


def _dotted(kind: str, ref: str, document: object, path: str, reveal: bool) -> dict:
    pointer = "/" + "/".join(path.split("."))
    return _pointer(kind, "Engine reference", ref, document, pointer, reveal)


def walk_pointer(document: object, pointer: str):
    if not pointer.startswith("/"):
        pointer = "/" + pointer
    node = document
    for raw in pointer.split("/")[1:]:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node
