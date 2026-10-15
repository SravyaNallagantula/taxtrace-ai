"""Read-only view of the packet, rebuilt from PostgreSQL at startup."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.db import session
from backend.models import (
    CallNote,
    ClientMessage,
    Document,
    ExtractedValue,
    HouseholdPerson,
    Packet,
    PacketSection,
    QuestionnaireAnswer,
    ReturnLine,
    ReturnVersion,
    StaffMember,
    TimelineEvent,
)


class Runtime:
    def load(self) -> None:
        db = session()
        try:
            packet = db.get(Packet, 1)
            if packet is None:
                raise RuntimeError("PostgreSQL has no packet. Import did not run.")
            sections = {row.name: row.body for row in db.scalars(select(PacketSection))}
            documents = self._documents(db)
            values = self._values(db)
            versions = self._versions(db)
            self.packet = {
                "name": packet.name,
                "version": packet.version,
                "generated": packet.generated,
                "client_id": packet.client_id,
                "tax_year": packet.tax_year,
                "source_sha256": packet.source_sha256,
            }
            self.data = {
                **sections,
                "documents": documents,
                "extracted_values": values,
                "return_versions": versions,
                "timeline": [row.body for row in db.scalars(select(TimelineEvent).order_by(TimelineEvent.seq))],
            }
            self.docs = {doc["id"]: doc for doc in documents}
            self.facts = {fact["id"]: fact for fact in values}
            self.versions = {item["version"]: item for item in versions}
            self.lines = {
                item["version"]: {line["key"]: line for line in item["lines"]}
                for item in versions
            }
            self.staff = {row.id: row for row in db.scalars(select(StaffMember).order_by(StaffMember.seq))}
            self.answers = {
                row.id: row for row in db.scalars(select(QuestionnaireAnswer).order_by(QuestionnaireAnswer.seq))
            }
            self.messages = {row.id: row for row in db.scalars(select(ClientMessage).order_by(ClientMessage.seq))}
            self.calls = {row.id: row.body for row in db.scalars(select(CallNote).order_by(CallNote.seq))}
            self.people = {row.id: row for row in db.scalars(select(HouseholdPerson).order_by(HouseholdPerson.seq))}
        finally:
            db.close()

    def _documents(self, db) -> list[dict]:
        rows = db.scalars(
            select(Document).options(selectinload(Document.pages)).order_by(Document.seq)
        ).all()
        archive = {
            doc["id"]: doc
            for doc in db.scalar(select(PacketSection).where(PacketSection.name == "documents")).body
        }
        result = []
        for row in rows:
            original = archive[row.id]
            if original["document_type"] != row.document_type or original["tax_year"] != row.tax_year:
                raise RuntimeError(f"{row.id} does not match the archived document")
            if original["extraction"]["status"] != row.extraction_status:
                raise RuntimeError(f"{row.id} extraction status does not match the archive")
            pages = [{"page": page.page, "printed_content": page.printed_content} for page in row.pages]
            if pages != original["pages"]:
                raise RuntimeError(f"{row.id} pages do not match the archive")
            result.append(original)
        archived = db.scalar(select(PacketSection).where(PacketSection.name == "documents")).body
        if [row.id for row in rows] != [doc["id"] for doc in archived]:
            raise RuntimeError("Document order does not match the archive")
        return result

    def _values(self, db) -> list[dict]:
        rows = db.scalars(select(ExtractedValue).order_by(ExtractedValue.seq)).all()
        return [
            {
                "id": row.id,
                "document_id": row.document_id,
                "page": row.page,
                "field": row.field,
                "label": row.label,
                "value": row.value_json,
                "value_type": row.value_type,
                "text_as_read": row.text_as_read,
                "position": row.position,
                "confidence": row.confidence,
            }
            for row in rows
        ]

    def _versions(self, db) -> list[dict]:
        rows = db.scalars(
            select(ReturnVersion)
            .options(
                selectinload(ReturnVersion.lines).selectinload(ReturnLine.sources),
                selectinload(ReturnVersion.lines).selectinload(ReturnLine.inputs),
                selectinload(ReturnVersion.diagnostics),
                selectinload(ReturnVersion.documents),
            )
            .order_by(ReturnVersion.seq)
        ).all()
        built = []
        for row in rows:
            lines = []
            for line in sorted(row.lines, key=lambda item: item.seq):
                item = {
                    "key": line.line_key,
                    "jurisdiction": line.jurisdiction,
                    "form": line.form,
                    "line": line.line,
                    "label": line.label,
                    "value": line.value_json,
                    "rule": line.rule,
                    "inputs": [entry.input_key for entry in sorted(line.inputs, key=lambda item: item.seq)],
                    "sources": [entry.source_ref for entry in sorted(line.sources, key=lambda item: item.seq)],
                }
                if line.note is not None:
                    item["note"] = line.note
                lines.append(item)
            links = sorted(row.documents, key=lambda item: (item.usage, item.seq))
            built.append({
                "version": row.version,
                "computed_at": row.computed_at,
                "trigger": row.trigger,
                "documents_used": [link.document_id for link in links if link.usage == "used"],
                "documents_superseded": [link.document_id for link in links if link.usage == "superseded"],
                "summary": row.summary,
                "tax_effect_rates": row.tax_effect_rates,
                "carryovers_out": row.carryovers_out,
                "assets": row.assets,
                "diagnostics": [
                    {"code": diag.code, "severity": diag.severity, "message": diag.message, "refs": diag.refs}
                    for diag in sorted(row.diagnostics, key=lambda item: item.seq)
                ],
                "changes_from_previous": row.changes_from_previous,
                "lines": lines,
            })
        return built


RT = Runtime()
