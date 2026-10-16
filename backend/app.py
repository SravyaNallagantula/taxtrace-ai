"""TaxTrace API.

The packet tables are loaded from PostgreSQL and are not updated by these routes.
Review notes and the sensitive-access log live in separate tables.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import os
import secrets

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.checks import independent_findings
from backend.explain import LineNotFound, evaluation_cases, explain_line
from backend.compare import VersionsNotAdjacent, compare_versions
from backend.records import workpaper_records
from backend.reconcile import reconciliation
from backend.db import session
from backend.filing import AuthorityRequired, check_authority, filing_readiness
from backend.importer import import_if_needed, init_schema
from backend.masking import present
from backend.models import AdjustmentBatch, AdjustmentItem, AuditEvent, Review, SensitiveAccessLog, StaffQuestion, StaffMessage
from backend.runtime import RT
from backend.signoff import SignoffDenied, check_signoff, describe, direct_dependents, invalidation_reason
from backend.sources import resolve_source


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_schema()
    import_if_needed()
    RT.load()
    yield


app = FastAPI(
    title="TaxTrace AI",
    version="0.2.0",
    description="Evidence-first tax review. Original packet rows are immutable.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def demo_auth(request, call_next):
    from fastapi.responses import Response

    password = os.environ.get("TAXTRACE_DEMO_PASSWORD")

    # Keep the existing local development application unchanged.
    if not password:
        return await call_next(request)

    # Allow Render to check that the application is healthy.
    if request.url.path == "/api/health":
        return await call_next(request)

    username = os.environ.get("TAXTRACE_DEMO_USER", "reviewer")
    credentials = request.headers.get("authorization", "")

    import base64
    try:
        scheme, encoded = credentials.split(" ", 1)
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        supplied_user, supplied_password = decoded.split(":", 1)
        valid = (
            scheme.lower() == "basic"
            and secrets.compare_digest(supplied_user, username)
            and secrets.compare_digest(supplied_password, password)
        )
    except (ValueError, UnicodeError):
        valid = False

    if not valid:
        return Response(
            status_code=401,
            content="Demo login required",
            headers={"WWW-Authenticate": 'Basic realm="TaxTrace Demo"'},
        )

    return await call_next(request)



class ReviewUpdate(BaseModel):
    status: str
    note: str = Field(min_length=3, max_length=3000)
    actor: str = Field(min_length=1, max_length=100)
    authority: str | None = None


class QuestionCreate(BaseModel):
    author: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=3, max_length=3000)
    line_key: str | None = None


class QuestionReply(BaseModel):
    author: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=3, max_length=3000)


class QuestionResolve(BaseModel):
    author: str = Field(min_length=1, max_length=100)


class AdjustmentCreate(BaseModel):
    author: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=3, max_length=3000)
    finding_ids: list[str] = Field(min_length=1, max_length=20)


class AdjustmentReverse(BaseModel):
    author: str = Field(min_length=1, max_length=100)


class ExplanationRequest(BaseModel):
    line_key: str = Field(min_length=1, max_length=80)
    question: str = Field(default="", max_length=500)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clearance(staff_id: str | None) -> bool:
    if not staff_id:
        return False
    member = RT.staff.get(staff_id)
    if member is None:
        raise HTTPException(422, "Unknown staff id")
    return bool(member.sensitive_data_clearance)


def _log_unmasked(staff_id: str, resource: str) -> None:
    db = session()
    try:
        db.add(SensitiveAccessLog(at=_now(), staff_id=staff_id, resource=resource))
        db.commit()
    finally:
        db.close()


def _staff_name(staff_id: str | None) -> str | None:
    if not staff_id:
        return None
    member = RT.staff.get(staff_id)
    return member.name if member else staff_id


def _staff_role(staff_id: str | None) -> str | None:
    if not staff_id:
        return None
    member = RT.staff.get(staff_id)
    return member.role if member else None


def _require_staff(staff_id: str) -> None:
    if staff_id not in RT.staff:
        raise HTTPException(422, "Unknown staff actor")


def _question_dict(row: StaffQuestion) -> dict:
    return {
        "id": row.id,
        "line_key": row.line_key,
        "status": row.status,
        "opened_by": row.opened_by,
        "opened_by_name": _staff_name(row.opened_by),
        "opened_by_role": _staff_role(row.opened_by),
        "opened_at": row.opened_at,
        "resolved_by": row.resolved_by,
        "resolved_by_name": _staff_name(row.resolved_by),
        "resolved_at": row.resolved_at,
        "messages": [
            {
                "id": message.id,
                "author": message.author,
                "author_name": _staff_name(message.author),
                "author_role": _staff_role(message.author),
                "body": message.body,
                "created_at": message.created_at,
            }
            for message in row.messages
        ],
    }


def _batch_dict(row: AdjustmentBatch) -> dict:
    return {
        "id": row.id,
        "note": row.note,
        "status": row.status,
        "created_by": row.created_by,
        "created_by_name": _staff_name(row.created_by),
        "created_at": row.created_at,
        "reversed_by": row.reversed_by,
        "reversed_by_name": _staff_name(row.reversed_by),
        "reversed_at": row.reversed_at,
        "combined_into_return": False,
        "items": [
            {
                "finding_id": item.finding_id,
                "title": item.title,
                "federal": item.federal,
                "california": item.california,
                "partner_required": item.partner_required,
                "method": item.method,
            }
            for item in row.items
        ],
    }


def _review_dict(row: Review) -> dict:
    return {
        "line_key": row.line_key,
        "status": row.status,
        "note": row.note,
        "authority": row.authority,
        "invalidated_by": row.invalidated_by,
        "invalidated_reason": row.invalidated_reason,
        "actor": row.actor,
        "updated_at": row.updated_at,
        "revision": row.revision,
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "source": "original packet v1.0",
        "storage": "postgresql",
        "packet_sha256": RT.packet["source_sha256"],
    }


@app.get("/api/overview")
def overview(version: str = "v3"):
    current = RT.versions.get(version)
    if not current:
        raise HTTPException(404, "Unknown version")
    db = session()
    try:
        reviews = [_review_dict(row) for row in db.scalars(select(Review))]
    finally:
        db.close()
    return {
        "name": RT.packet["name"],
        "tax_year": RT.packet["tax_year"],
        "versions": [
            {"version": item["version"], "computed_at": item["computed_at"], "trigger": item["trigger"]}
            for item in RT.data["return_versions"]
        ],
        "current_version": version,
        "summary": current["summary"],
        "counts": {
            "documents": len(RT.docs),
            "extracted_values": len(RT.facts),
            "return_lines": len(current["lines"]),
            "diagnostics": len(current["diagnostics"]),
            "reviews": len(reviews),
        },
        "reviews": reviews,
        "staff": [{"id": member.id, "name": member.name, "role": member.role} for member in RT.staff.values()],
    }


@app.get("/api/lines")
def lines(
    version: str = "v3",
    q: str = "",
    form: str = "",
    limit: int = Query(150, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    current = RT.versions.get(version)
    if current is None:
        raise HTTPException(404, "Unknown version")
    needle = q.lower()
    found = [
        line for line in current["lines"]
        if (not form or line["form"] == form)
        and needle in (line["key"] + " " + line["label"] + " " + line["form"]).lower()
    ]
    db = session()
    try:
        reviews = {row.line_key: _review_dict(row) for row in db.scalars(select(Review))}
    finally:
        db.close()
    page = found[offset:offset + limit]
    return {
        "total": len(found),
        "items": [{**line, "sources_count": len(line["sources"]), "review": reviews.get(line["key"])} for line in page],
    }


@app.get("/api/lines/{line_key:path}")
def line(
    line_key: str,
    version: str = "v3",
    x_staff_id: str | None = Header(default=None),
):
    current = RT.lines.get(version, {})
    found = current.get(line_key)
    if not found:
        raise HTTPException(404, "Line not found")
    reveal = _clearance(x_staff_id)
    if reveal:
        _log_unmasked(x_staff_id, f"line:{version}:{line_key}")
    sources = [resolve_source(ref, version, reveal) for ref in found["sources"]]
    inputs = [
        {"key": key, "value": current.get(key, {}).get("value"), "label": current.get(key, {}).get("label")}
        for key in found["inputs"]
    ]
    db = session()
    try:
        row = db.get(Review, line_key)
        review = _review_dict(row) if row else None
    finally:
        db.close()
    return {
        "line": found,
        "sources": sources,
        "inputs": inputs,
        "review": review,
        "signoff": describe(line_key, independent_findings(RT.data), RT.staff, RT.data["firm"]["assignment_at_start"]),
    }


@app.get("/api/documents")
def documents(q: str = "", limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    needle = q.lower()
    found = [
        doc for doc in RT.data["documents"]
        if needle in (doc["id"] + " " + doc["title"] + " " + doc["document_type"]).lower()
    ]
    keys = ("id", "title", "document_type", "issuer", "page_count", "received_at", "extraction")
    return {"total": len(found), "items": [{key: doc[key] for key in keys} for doc in found[offset:offset + limit]]}


@app.get("/api/documents/{document_id}")
def document(document_id: str, x_staff_id: str | None = Header(default=None)):
    original = RT.docs.get(document_id)
    if not original:
        raise HTTPException(404, "Unknown document")
    reveal = _clearance(x_staff_id)
    if reveal:
        _log_unmasked(x_staff_id, f"document:{document_id}")
    facts = []
    for fact in RT.data["extracted_values"]:
        if fact["document_id"] != document_id:
            continue
        value = fact["value"]
        if fact["value_type"] in ("ssn", "account_number"):
            value = present(value, reveal)
        facts.append({**fact, "value": value, "text_as_read": present(fact["text_as_read"], reveal)})
    fact_ids = {fact["id"] for fact in facts}
    uses = [
        {"key": line["key"], "label": line["label"], "value": line["value"]}
        for line in RT.versions["v3"]["lines"]
        if set(line["sources"]) & fact_ids
    ]
    shown = {
        **original,
        "pages": [
            {**page, "printed_content": present(page["printed_content"], reveal)}
            for page in original["pages"]
        ],
    }
    return {"document": shown, "facts": facts, "used_by": uses}


@app.get("/api/extracted-values/{value_id}")
def extracted_value(value_id: str, x_staff_id: str | None = Header(default=None)):
    fact = RT.facts.get(value_id)
    if fact is None:
        raise HTTPException(404, "Unknown extracted value")
    reveal = _clearance(x_staff_id)
    if reveal:
        _log_unmasked(x_staff_id, f"value:{value_id}")
    value = fact["value"]
    if fact["value_type"] in ("ssn", "account_number"):
        value = present(value, reveal)
    return {**fact, "value": value, "text_as_read": present(fact["text_as_read"], reveal)}


@app.get("/api/findings")
def findings():
    version = RT.versions["v3"]
    engine = [
        {
            "id": f"engine-{index}",
            "title": item["code"].replace("_", " ").title(),
            "description": item["message"],
            "severity": item["severity"],
            "source": "engine diagnostic",
            "refs": item["refs"],
        }
        for index, item in enumerate(version["diagnostics"])
    ]
    return {
        "independent": independent_findings(RT.data),
        "engine": engine,
        "reconciliation": reconciliation(RT.data),
    }


@app.post("/api/explanations")
def explanations(body: ExplanationRequest):
    try:
        return explain_line(RT.data, body.line_key, body.question)
    except LineNotFound:
        raise HTTPException(404, "Line not found") from None


@app.get("/api/explanations/eval")
def explanations_eval():
    return evaluation_cases(RT.data)


@app.get("/api/versions")
def versions():
    return [
        {
            "version": item["version"],
            "computed_at": item["computed_at"],
            "trigger": item["trigger"],
            "summary": item["summary"],
            "changes": item["changes_from_previous"],
        }
        for item in RT.data["return_versions"]
    ]


@app.get("/api/versions/compare")
def version_compare(earlier: str, later: str):
    try:
        return compare_versions(
            RT.data["return_versions"],
            earlier,
            later,
            set(RT.lines["v3"]),
        )
    except KeyError:
        raise HTTPException(404, "Unknown version")
    except VersionsNotAdjacent as denied:
        raise HTTPException(422, str(denied)) from denied


@app.get("/api/scenarios")
def scenarios():
    return RT.data["what_if"]["alternatives"]


@app.get("/api/adjustments")
def adjustments():
    db = session()
    try:
        rows = db.scalars(
            select(AdjustmentBatch)
            .options(selectinload(AdjustmentBatch.items))
            .order_by(AdjustmentBatch.id.desc())
        )
        return [_batch_dict(row) for row in rows]
    finally:
        db.close()


@app.post("/api/adjustments")
def propose_adjustment(body: AdjustmentCreate):
    _require_staff(body.author)
    if len(body.finding_ids) != len(set(body.finding_ids)):
        raise HTTPException(422, "Each finding can be in the batch once")
    catalog = {item["id"]: item for item in independent_findings(RT.data)}
    chosen = []
    for finding_id in body.finding_ids:
        finding = catalog.get(finding_id)
        if finding is None:
            raise HTTPException(422, "Unknown finding")
        effect = finding.get("tax_effect")
        if not effect:
            raise HTTPException(422, "That finding has no documented tax effect to propose")
        chosen.append(finding)
    now = _now()
    db = session()
    try:
        batch = AdjustmentBatch(
            note=body.note.strip(),
            status="proposed",
            created_by=body.author,
            created_at=now,
            reversed_by=None,
            reversed_at=None,
        )
        for finding in chosen:
            effect = finding["tax_effect"]
            batch.items.append(AdjustmentItem(
                finding_id=finding["id"],
                title=finding["title"],
                federal=effect["federal"],
                california=effect["california"],
                partner_required=bool(effect["partner_required"]),
                method=effect["method"],
            ))
        db.add(batch)
        db.flush()
        db.add(AuditEvent(
            at=now,
            actor=body.author,
            action="adjustment_proposed",
            target=f"batch:{batch.id}",
            details=body.note.strip(),
        ))
        db.commit()
        db.refresh(batch)
        return _batch_dict(batch)
    finally:
        db.close()


@app.post("/api/adjustments/{batch_id}/reverse")
def reverse_adjustment(batch_id: int, body: AdjustmentReverse):
    _require_staff(body.author)
    now = _now()
    db = session()
    try:
        batch = db.scalar(
            select(AdjustmentBatch)
            .options(selectinload(AdjustmentBatch.items))
            .where(AdjustmentBatch.id == batch_id)
        )
        if batch is None:
            raise HTTPException(404, "Unknown adjustment batch")
        if batch.status == "reversed":
            raise HTTPException(422, "This batch is already reversed")
        batch.status = "reversed"
        batch.reversed_by = body.author
        batch.reversed_at = now
        db.add(AuditEvent(
            at=now,
            actor=body.author,
            action="adjustment_reversed",
            target=f"batch:{batch.id}",
            details="The proposed batch was reversed. Return amounts were left as the engine computed them.",
        ))
        db.commit()
        db.refresh(batch)
        return _batch_dict(batch)
    finally:
        db.close()


@app.get("/api/timeline")
def timeline():
    return RT.data["timeline"]


@app.get("/api/records")
def records():
    return workpaper_records(RT.data)


@app.get("/api/filing")
def filing():
    db = session()
    try:
        reviews = [_review_dict(row) for row in db.scalars(select(Review))]
    finally:
        db.close()
    return filing_readiness(
        RT.lines["v3"],
        reviews,
        RT.data["household"]["filing_status"],
        RT.data["firm"]["starter_standards"],
    )


@app.post("/api/lines/{line_key:path}/review")
def review(line_key: str, body: ReviewUpdate):
    if line_key not in RT.lines["v3"]:
        raise HTTPException(404, "Unknown current-version line")
    if body.status not in {"needs_review", "verified", "blocked"}:
        raise HTTPException(422, "Invalid review status")
    if body.actor not in RT.staff:
        raise HTTPException(422, "Unknown staff actor")
    try:
        authority = check_authority(body.status, body.authority, RT.data["firm"]["starter_standards"])
    except AuthorityRequired as denied:
        raise HTTPException(422, denied.message) from denied
    try:
        check_signoff(
            body.actor,
            body.status,
            line_key,
            independent_findings(RT.data),
            RT.staff,
            RT.data["firm"]["assignment_at_start"],
        )
    except SignoffDenied as denied:
        raise HTTPException(403, denied.message) from denied
    now = _now()
    db = session()
    try:
        prior = db.get(Review, line_key)
        was_verified = prior is not None and prior.status == "verified"
        revision = prior.revision + 1 if prior else 1
        if prior is None:
            prior = Review(
                line_key=line_key,
                status=body.status,
                note=body.note,
                authority=authority,
                invalidated_by=None,
                invalidated_reason=None,
                actor=body.actor,
                updated_at=now,
                revision=revision,
            )
            db.add(prior)
        else:
            prior.status = body.status
            prior.note = body.note
            prior.authority = authority
            prior.actor = body.actor
            prior.updated_at = now
            prior.revision = revision
            if body.status == "verified":
                prior.invalidated_by = None
                prior.invalidated_reason = None
        db.add(AuditEvent(
            at=now,
            actor=body.actor,
            action="review_updated",
            target=line_key,
            details=body.model_dump_json(),
        ))
        invalidated: list[str] = []
        if was_verified and body.status != "verified":
            db.add(AuditEvent(
                at=now,
                actor=body.actor,
                action="signoff_invalidated",
                target=line_key,
                details="A later note replaced the sign-off.",
            ))
        for dependent_key in direct_dependents(line_key, RT.lines["v3"]):
            dependent = db.get(Review, dependent_key)
            if dependent is None or dependent.status != "verified":
                continue
            dependent.status = "needs_review"
            dependent.authority = None
            dependent.invalidated_by = line_key
            dependent.invalidated_reason = invalidation_reason(line_key)
            dependent.updated_at = now
            dependent.revision += 1
            db.add(AuditEvent(
                at=now,
                actor=body.actor,
                action="signoff_invalidated",
                target=dependent_key,
                details=dependent.invalidated_reason,
            ))
            invalidated.append(dependent_key)
        db.commit()
    finally:
        db.close()
    return {
        "line_key": line_key,
        "status": body.status,
        "actor": body.actor,
        "revision": revision,
        "updated_at": now,
        "invalidated": invalidated,
    }


@app.get("/api/questions")
def questions(line_key: str | None = None, status: str | None = None):
    if status is not None and status not in {"open", "resolved"}:
        raise HTTPException(422, "Invalid question status")
    db = session()
    try:
        statement = (
            select(StaffQuestion)
            .options(selectinload(StaffQuestion.messages))
            .order_by(StaffQuestion.id.desc())
        )
        if line_key:
            statement = statement.where(StaffQuestion.line_key == line_key)
        if status:
            statement = statement.where(StaffQuestion.status == status)
        return [_question_dict(row) for row in db.scalars(statement)]
    finally:
        db.close()


@app.post("/api/questions")
def open_question(body: QuestionCreate):
    _require_staff(body.author)
    line_key = body.line_key.strip() if body.line_key else None
    if line_key and line_key not in RT.lines["v3"]:
        raise HTTPException(404, "Unknown current-version line")
    now = _now()
    db = session()
    try:
        question = StaffQuestion(
            line_key=line_key,
            status="open",
            opened_by=body.author,
            opened_at=now,
            resolved_by=None,
            resolved_at=None,
        )
        question.messages.append(StaffMessage(author=body.author, body=body.body.strip(), created_at=now))
        db.add(question)
        db.flush()
        db.add(AuditEvent(
            at=now,
            actor=body.author,
            action="question_opened",
            target=line_key or f"question:{question.id}",
            details=body.body.strip(),
        ))
        db.commit()
        db.refresh(question)
        return _question_dict(question)
    finally:
        db.close()


@app.post("/api/questions/{question_id}/messages")
def reply_to_question(question_id: int, body: QuestionReply):
    _require_staff(body.author)
    now = _now()
    db = session()
    try:
        question = db.scalar(
            select(StaffQuestion)
            .options(selectinload(StaffQuestion.messages))
            .where(StaffQuestion.id == question_id)
        )
        if question is None:
            raise HTTPException(404, "Unknown question")
        question.messages.append(StaffMessage(author=body.author, body=body.body.strip(), created_at=now))
        if question.status == "resolved":
            question.status = "open"
            question.resolved_by = None
            question.resolved_at = None
        db.add(AuditEvent(
            at=now,
            actor=body.author,
            action="question_replied",
            target=question.line_key or f"question:{question.id}",
            details=body.body.strip(),
        ))
        db.commit()
        db.refresh(question)
        return _question_dict(question)
    finally:
        db.close()


@app.post("/api/questions/{question_id}/resolve")
def resolve_question(question_id: int, body: QuestionResolve):
    _require_staff(body.author)
    now = _now()
    db = session()
    try:
        question = db.scalar(
            select(StaffQuestion)
            .options(selectinload(StaffQuestion.messages))
            .where(StaffQuestion.id == question_id)
        )
        if question is None:
            raise HTTPException(404, "Unknown question")
        if question.status == "resolved":
            raise HTTPException(422, "This question is already resolved")
        question.status = "resolved"
        question.resolved_by = body.author
        question.resolved_at = now
        db.add(AuditEvent(
            at=now,
            actor=body.author,
            action="question_resolved",
            target=question.line_key or f"question:{question.id}",
            details=f"Question {question.id} marked resolved",
        ))
        db.commit()
        db.refresh(question)
        return _question_dict(question)
    finally:
        db.close()


@app.get("/api/client-correspondence")
def client_correspondence(x_staff_id: str | None = Header(default=None)):
    reveal = _clearance(x_staff_id)
    messages = [
        {**item, "text": present(item["text"], reveal)}
        for item in RT.data["client"]["messages"]
    ]
    calls = [
        {**call, "notes": [present(note, reveal) for note in call["notes"]]}
        for call in RT.data["client"]["call_notes"]
    ]
    return {"messages": messages, "calls": calls}


@app.get("/api/audit")
def audit(limit: int = Query(50, ge=1, le=200)):
    db = session()
    try:
        rows = db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)).all()
        return [
            {"id": row.id, "at": row.at, "actor": row.actor, "action": row.action, "target": row.target, "details": row.details}
            for row in rows
        ]
    finally:
        db.close()


@app.get("/api/sensitive-access")
def sensitive_access(limit: int = Query(50, ge=1, le=200)):
    db = session()
    try:
        rows = db.scalars(select(SensitiveAccessLog).order_by(SensitiveAccessLog.id.desc()).limit(limit)).all()
        return [{"id": row.id, "at": row.at, "staff_id": row.staff_id, "resource": row.resource} for row in rows]
    finally:
        db.close()


_FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def _frontend_file(resource_path: str) -> FileResponse:
    root = _FRONTEND.resolve()
    candidate = (root / resource_path).resolve() if resource_path else root / "index.html"
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(404, "Not found") from None
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(root / "index.html")


if (_FRONTEND / "index.html").is_file():
    @app.get("/", include_in_schema=False)
    def workspace_home():
        return FileResponse(_FRONTEND / "index.html")

    @app.get("/{resource_path:path}", include_in_schema=False)
    def workspace_file(resource_path: str):
        if resource_path == "api" or resource_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        return _frontend_file(resource_path)
