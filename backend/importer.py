"""Load the packet JSON into PostgreSQL once.

A second run of the same file does nothing. A different file is refused.
The importer only inserts. Updates and deletes are rejected by database triggers.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text

from backend.db import install_immutability_triggers, session
from backend.models import (
    Base,
    CallNote,
    ClientMessage,
    Diagnostic,
    Document,
    DocumentPage,
    ExtractedValue,
    HouseholdPerson,
    Packet,
    PacketSection,
    QuestionnaireAnswer,
    ReturnLine,
    ReturnLineInput,
    ReturnLineSource,
    ReturnVersion,
    StaffMember,
    TimelineEvent,
    VersionDocument,
)
from backend.db import get_engine

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET = ROOT / "data" / "packet.json"

DOCUMENT_KEYS = {
    "id", "title", "document_type", "issuer", "belongs_to", "tax_year",
    "received_at", "uploaded_by", "file_name", "page_count", "pages",
    "extraction", "marked_corrected",
}
VALUE_KEYS = {
    "id", "document_id", "page", "field", "label", "value", "value_type",
    "text_as_read", "position", "confidence",
}


def packet_path() -> Path:
    return Path(os.environ.get("TAXTRACE_PACKET_PATH", str(DEFAULT_PACKET)))


def init_schema() -> None:
    Base.metadata.create_all(get_engine())
    db = session()
    try:
        db.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS authority TEXT"))
        db.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS invalidated_by TEXT"))
        db.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS invalidated_reason TEXT"))
        db.commit()
        install_immutability_triggers(db)
    finally:
        db.close()


def import_if_needed() -> str:
    path = packet_path()
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw)
    db = session()
    try:
        existing = db.get(Packet, 1)
        if existing:
            if existing.source_sha256 != digest:
                raise RuntimeError(
                    "This database already holds a different packet. "
                    "Original rows are immutable, so the new file was not imported."
                )
            return "already-imported"
        _insert_packet(db, data, digest)
        db.commit()
        return "imported"
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _require_keys(record: dict, allowed: set[str], label: str) -> None:
    extra = set(record) - allowed
    if extra:
        raise ValueError(f"{label} has fields the importer does not store: {sorted(extra)}")


def _insert_packet(db, data: dict, digest: str) -> None:
    for name, body in data.items():
        db.add(PacketSection(name=name, body=body))

    db.add(Packet(
        id=1,
        name=data["packet"]["name"],
        version=data["packet"]["version"],
        generated=data["packet"]["generated"],
        client_id=data["packet"]["client_id"],
        tax_year=data["household"]["tax_year"],
        source_sha256=digest,
        imported_at=datetime.now(timezone.utc),
    ))

    for seq, doc in enumerate(data["documents"]):
        _require_keys(doc, DOCUMENT_KEYS, f"document {doc.get('id')}")
        db.add(Document(
            id=doc["id"],
            seq=seq,
            document_type=doc["document_type"],
            tax_year=doc["tax_year"],
            extraction_status=doc["extraction"]["status"],
        ))
        for page in doc["pages"]:
            db.add(DocumentPage(
                document_id=doc["id"],
                page=page["page"],
                printed_content=page["printed_content"],
            ))

    for seq, fact in enumerate(data["extracted_values"]):
        _require_keys(fact, VALUE_KEYS, f"extracted value {fact.get('id')}")
        db.add(ExtractedValue(
            id=fact["id"],
            seq=seq,
            document_id=fact["document_id"],
            page=fact["page"],
            field=fact["field"],
            label=fact["label"],
            value_json=fact["value"],
            value_type=fact["value_type"],
            text_as_read=fact["text_as_read"],
            confidence=fact["confidence"],
            position=fact["position"],
        ))

    for seq, version in enumerate(data["return_versions"]):
        db.add(ReturnVersion(
            version=version["version"],
            seq=seq,
            computed_at=version["computed_at"],
            trigger=version["trigger"],
            summary=version["summary"],
            tax_effect_rates=version["tax_effect_rates"],
            carryovers_out=version["carryovers_out"],
            assets=version["assets"],
            changes_from_previous=version["changes_from_previous"],
        ))
        db.flush()
        for use_seq, document_id in enumerate(version["documents_used"]):
            db.add(VersionDocument(version=version["version"], document_id=document_id, usage="used", seq=use_seq))
        for sup_seq, document_id in enumerate(version["documents_superseded"]):
            db.add(VersionDocument(version=version["version"], document_id=document_id, usage="superseded", seq=sup_seq))
        for line_seq, line in enumerate(version["lines"]):
            db.add(ReturnLine(
                version=version["version"],
                line_key=line["key"],
                seq=line_seq,
                jurisdiction=line["jurisdiction"],
                form=line["form"],
                line=str(line["line"]),
                label=line["label"],
                value_json=line["value"],
                rule=line["rule"],
                note=line.get("note"),
            ))
            for src_seq, ref in enumerate(line["sources"]):
                db.add(ReturnLineSource(version=version["version"], line_key=line["key"], seq=src_seq, source_ref=ref))
            for in_seq, key in enumerate(line["inputs"]):
                db.add(ReturnLineInput(version=version["version"], line_key=line["key"], seq=in_seq, input_key=key))
        for diag_seq, diag in enumerate(version["diagnostics"]):
            db.add(Diagnostic(
                version=version["version"],
                seq=diag_seq,
                code=diag["code"],
                severity=diag["severity"],
                message=diag["message"],
                refs=diag["refs"],
            ))

    for seq, event in enumerate(data["timeline"]):
        db.add(TimelineEvent(id=event["id"], seq=seq, at=event["at"], event=event["event"], body=event))
    for seq, answer in enumerate(data["client"]["questionnaire"]):
        db.add(QuestionnaireAnswer(
            id=answer["id"], seq=seq, question=answer["question"], answer=str(answer["answer"]),
            answered_by=answer["answered_by"], answered_at=answer["answered_at"],
        ))
    for seq, message in enumerate(data["client"]["messages"]):
        db.add(ClientMessage(
            id=message["id"], seq=seq, sent_at=message["sent_at"],
            from_name=message["from"], to_name=message["to"], text=message["text"],
        ))
    for seq, call in enumerate(data["client"]["call_notes"]):
        db.add(CallNote(id=call["id"], seq=seq, body=call))
    for seq, person in enumerate(data["household"]["people"]):
        db.add(HouseholdPerson(
            id=person["id"], seq=seq, role=person["role"], name=person["name"],
            ssn=person["ssn"], ip_pin=person.get("ip_pin"), body=person,
        ))
    for seq, member in enumerate(data["firm"]["staff"]):
        db.add(StaffMember(
            id=member["id"], seq=seq, name=member["name"], role=member["role"],
            credential=member.get("credential"),
            sensitive_data_clearance=bool(member["sensitive_data_clearance"]),
            active_from=member["active_from"], note=member.get("note"),
        ))


def counts() -> dict[str, int]:
    db = session()
    try:
        def n(model):
            return db.scalar(select(func.count()).select_from(model))
        return {
            "documents": n(Document),
            "extracted_values": n(ExtractedValue),
            "return_lines": n(ReturnLine),
        }
    finally:
        db.close()
