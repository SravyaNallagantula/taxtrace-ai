"""Tables for the original packet, plus the workpaper log that we are allowed to change."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Packet(Base):
    __tablename__ = "packet"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    generated: Mapped[str] = mapped_column(Text)
    client_id: Mapped[str] = mapped_column(Text)
    tax_year: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PacketSection(Base):
    """Exact copy of one top-level JSON key. This is the lossless archive."""
    __tablename__ = "packet_sections"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    body: Mapped[Any] = mapped_column(JSONB)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    document_type: Mapped[str] = mapped_column(Text)
    tax_year: Mapped[int] = mapped_column(Integer)
    extraction_status: Mapped[str] = mapped_column(Text)
    pages: Mapped[list[DocumentPage]] = relationship(back_populates="document", order_by="DocumentPage.page")


class DocumentPage(Base):
    __tablename__ = "document_pages"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    page: Mapped[int] = mapped_column(Integer, primary_key=True)
    printed_content: Mapped[str] = mapped_column(Text)
    document: Mapped[Document] = relationship(back_populates="pages")


class ExtractedValue(Base):
    __tablename__ = "extracted_values"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    page: Mapped[int] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    value_json: Mapped[Any] = mapped_column(JSONB)
    value_type: Mapped[str] = mapped_column(Text)
    text_as_read: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    position: Mapped[Any] = mapped_column(JSONB)


class ReturnVersion(Base):
    __tablename__ = "return_versions"
    version: Mapped[str] = mapped_column(String(8), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[str] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(Text)
    summary: Mapped[Any] = mapped_column(JSONB)
    tax_effect_rates: Mapped[Any] = mapped_column(JSONB)
    carryovers_out: Mapped[Any] = mapped_column(JSONB)
    assets: Mapped[Any] = mapped_column(JSONB)
    changes_from_previous: Mapped[Any] = mapped_column(JSONB)
    lines: Mapped[list[ReturnLine]] = relationship(back_populates="return_version", order_by="ReturnLine.seq")
    diagnostics: Mapped[list[Diagnostic]] = relationship(back_populates="return_version", order_by="Diagnostic.seq")
    documents: Mapped[list[VersionDocument]] = relationship(back_populates="return_version", order_by="VersionDocument.seq")


class VersionDocument(Base):
    __tablename__ = "version_documents"
    version: Mapped[str] = mapped_column(ForeignKey("return_versions.version"), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    usage: Mapped[str] = mapped_column(String(16), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    return_version: Mapped[ReturnVersion] = relationship(back_populates="documents")


class ReturnLine(Base):
    __tablename__ = "return_lines"
    version: Mapped[str] = mapped_column(ForeignKey("return_versions.version"), primary_key=True)
    line_key: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    jurisdiction: Mapped[str] = mapped_column(Text)
    form: Mapped[str] = mapped_column(Text)
    line: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    value_json: Mapped[Any] = mapped_column(JSONB)
    rule: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    return_version: Mapped[ReturnVersion] = relationship(back_populates="lines")
    sources: Mapped[list[ReturnLineSource]] = relationship(back_populates="return_line", order_by="ReturnLineSource.seq")
    inputs: Mapped[list[ReturnLineInput]] = relationship(back_populates="return_line", order_by="ReturnLineInput.seq")


class ReturnLineSource(Base):
    __tablename__ = "return_line_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(Text)
    line_key: Mapped[str] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(Integer)
    source_ref: Mapped[str] = mapped_column(Text, index=True)
    return_line: Mapped[ReturnLine] = relationship(
        back_populates="sources",
        primaryjoin="and_(ReturnLine.version==ReturnLineSource.version, ReturnLine.line_key==ReturnLineSource.line_key)",
        foreign_keys="[ReturnLineSource.version, ReturnLineSource.line_key]",
    )
    __table_args__ = (
        UniqueConstraint("version", "line_key", "seq"),
        ForeignKeyConstraint(["version", "line_key"], ["return_lines.version", "return_lines.line_key"]),
    )


class ReturnLineInput(Base):
    __tablename__ = "return_line_inputs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(Text)
    line_key: Mapped[str] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(Integer)
    input_key: Mapped[str] = mapped_column(Text)
    return_line: Mapped[ReturnLine] = relationship(
        back_populates="inputs",
        primaryjoin="and_(ReturnLine.version==ReturnLineInput.version, ReturnLine.line_key==ReturnLineInput.line_key)",
        foreign_keys="[ReturnLineInput.version, ReturnLineInput.line_key]",
    )
    __table_args__ = (
        UniqueConstraint("version", "line_key", "seq"),
        ForeignKeyConstraint(["version", "line_key"], ["return_lines.version", "return_lines.line_key"]),
    )


class Diagnostic(Base):
    __tablename__ = "diagnostics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(ForeignKey("return_versions.version"))
    seq: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    refs: Mapped[Any] = mapped_column(JSONB)
    return_version: Mapped[ReturnVersion] = relationship(back_populates="diagnostics")


class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    at: Mapped[str] = mapped_column(Text)
    event: Mapped[str] = mapped_column(Text)
    body: Mapped[Any] = mapped_column(JSONB)


class QuestionnaireAnswer(Base):
    __tablename__ = "questionnaire_answers"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    answered_by: Mapped[str] = mapped_column(Text)
    answered_at: Mapped[str] = mapped_column(Text)


class ClientMessage(Base):
    __tablename__ = "client_messages"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    sent_at: Mapped[str] = mapped_column(Text)
    from_name: Mapped[str] = mapped_column(Text)
    to_name: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)


class CallNote(Base):
    __tablename__ = "call_notes"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    body: Mapped[Any] = mapped_column(JSONB)


class HouseholdPerson(Base):
    __tablename__ = "household_people"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    ssn: Mapped[str] = mapped_column(Text)
    ip_pin: Mapped[str | None] = mapped_column(Text)
    body: Mapped[Any] = mapped_column(JSONB)


class StaffMember(Base):
    __tablename__ = "staff"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    credential: Mapped[str | None] = mapped_column(Text)
    sensitive_data_clearance: Mapped[bool] = mapped_column(Boolean)
    active_from: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


class Review(Base):
    """Workpaper decision. This table is allowed to change. The packet is not."""
    __tablename__ = "reviews"
    line_key: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    authority: Mapped[str | None] = mapped_column(Text)
    invalidated_by: Mapped[str | None] = mapped_column(Text)
    invalidated_reason: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text)


class SensitiveAccessLog(Base):
    __tablename__ = "sensitive_access_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[str] = mapped_column(Text)
    staff_id: Mapped[str] = mapped_column(Text)
    resource: Mapped[str] = mapped_column(Text)


class StaffQuestion(Base):
    """A preparer/reviewer question. It is not a return line and not a sign-off."""
    __tablename__ = "staff_questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    opened_by: Mapped[str] = mapped_column(Text)
    opened_at: Mapped[str] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[str | None] = mapped_column(Text)
    messages: Mapped[list["StaffMessage"]] = relationship(
        back_populates="question",
        order_by="StaffMessage.id",
    )


class StaffMessage(Base):
    __tablename__ = "staff_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("staff_questions.id"))
    author: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text)
    question: Mapped[StaffQuestion] = relationship(back_populates="messages")


class AdjustmentBatch(Base):
    """A proposed set of documented adjustments. Reversing it does not edit the return."""
    __tablename__ = "adjustment_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text)
    reversed_by: Mapped[str | None] = mapped_column(Text)
    reversed_at: Mapped[str | None] = mapped_column(Text)
    items: Mapped[list["AdjustmentItem"]] = relationship(
        back_populates="batch",
        order_by="AdjustmentItem.id",
    )


class AdjustmentItem(Base):
    __tablename__ = "adjustment_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("adjustment_batches.id"))
    finding_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    federal: Mapped[float] = mapped_column(Float)
    california: Mapped[float | None] = mapped_column(Float)
    partner_required: Mapped[bool] = mapped_column(Boolean)
    method: Mapped[str] = mapped_column(Text)
    batch: Mapped[AdjustmentBatch] = relationship(back_populates="items")
