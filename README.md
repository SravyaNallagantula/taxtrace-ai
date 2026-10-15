# TaxTrace AI — Evidence-first tax review prototype

This is the review workspace for the MiraFlores AI "Redesign the Tax Workpaper" case study. The limitations below are still out of scope.

## Implemented
- PostgreSQL stores the original packet. The import runs once. The same file can be loaded again and changes nothing. A different file is refused.
- Database triggers reject updates and deletes on packet tables. Review notes live in separate tables.
- FastAPI reads documents, extracted values, return lines, and source references from PostgreSQL.
- Source references resolve to the extracted field, questionnaire answer, message, call note, prior-year pointer, agency pointer, or engine parameter.
- Independent checks flag the confirmed packet errors, including the RSU basis of $0, the double-counted 1099-K, the estimate mismatches, and Theo's SSN.
- Social Security numbers stay masked. A staff member with clearance can open them, and that view is written to `sensitive_access_log`. Marcus Bell (st-04) has no clearance.
- React/TypeScript interface for the return, documents, findings, scenarios, and timeline.
- Sign-off follows the firm's starter standards. Priya Raman prepared the return and cannot mark a line verified. Daniel Ortiz can sign a line whose computed tax effect is $1,000 or less. A larger federal or California tax effect requires Helen Strand, the partner. The dollar amounts use v3 rates or a named what-if result. They are not a recomputed return.
- A verified or blocked decision records one of the firm's verification types. Open notes block filing. This return claims the child tax credit and the credit for other dependents, so Form 8867 must be verified before filing. The American opportunity credit is phased out to zero. There is no earned income credit line, and the filing status is married filing jointly.
- A sign-off covers that line and the inputs it names. A later note on one of those inputs clears the sign-off and leaves an open note. The cleared line has to be signed again. The return numbers stay as the engine computed them.
- The preparer and the reviewer can ask and answer questions on a return line, or about the engagement. Those messages are stored apart from the return. They do not change an amount, a sign-off, or the filing gate. The ten client messages and the call note from the packet stay read-only.
- Version comparison shows the stored step from v1 to v2 and from v2 to v3, including the difference between the stored summaries. A reviewer can propose a batch of findings that already have a tax effect, then reverse that batch. The effects stay listed one by one. They are not combined into a new return, and the engine amounts stay as computed.
- Schedules list each v3 form and its own lines. Carryovers into 2025 and out of v3 are the packet's figures, including the $3,871 minimum tax credit the engine carried out of v3. Notices and the four e-file submissions are shown as a replay of the packet timeline. The firm's required steps are listed as written and are not marked complete here.
- Opening a source field places a box on the simulated page at the pipeline's synthetic position. Wage, prior-year, questionnaire, engine-parameter, exchange-rate, asset, household, and timeline references resolve to a named source. The packet has no page image, so the box is a position on the page, not a mark inside a scan.
- Prior-year lines that changed by more than 10 percent and more than $1,000 are listed as explanation flags. They are not corrections. Wages, mileage, mortgage interest, the ESPP basis adjustment, and prior-year AGI are shown where the packet amounts agree. The full telephone and internet deduction, and California wages above federal wages, stay open with no tax effect.
- A line explanation is orchestrated with LangGraph. It retrieves the line, its source fields, and a related finding, then checks every citation and amount. A question that tries to override the packet is refused. Text inside the packet that reads as an instruction is withheld. An optional model is used only when `OPENAI_API_KEY` is set; otherwise the retrieved evidence is shown directly. The explanation does not change the return.

## Limitations (important)
- **Not yet** complete workpaper capability. No complete dependency propagation, recomputation, edits/undo, approval invalidation, complex tax schedules, reviewer assignment, real concurrent editing, state-wide allocations, client portal, e-file simulation, notice case assembly, or annual rollover.
- Role switcher is **demo-only**. `X-Staff-Id` is not authentication. Do not publish this with real client data.
- The API does not recompute tax. Dollar effects in the review notes come from the packet's own rates and what-if results.
- The optional model call needs `OPENAI_API_KEY`. The citation check runs either way. There is no separate vector database; retrieval is the line's own fields and the findings that name that line.
- A later note on a line clears a sign-off that uses that line as an input. The e-file screen replays the four submissions stored in the packet. It does not transmit a return.
- Test data is fictional and sourced only from the provided packet.

## Running locally
Python 3.10+ and Node.js 20+ recommended.

**Terminal 1 — database and API**

```bash
cd taxtrace-ai
docker compose up -d
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app:app --reload --port 8000
```

The local database user is `taxtrace`, password `taxtrace`, database `taxtrace`, port 5434. That password is for this laptop only.

API docs: http://localhost:8000/docs

**Terminal 2 — UI**

```bash
cd taxtrace-ai/frontend
npm install
npm run dev
```

Open http://localhost:5173

**One process for the workspace**

The role header is a demonstration, so this build stays on your own machine. Do not put it on the public internet with real taxpayer data.

```bash
docker compose up -d --build web
```

Open http://localhost:8080. That process serves the built page and the API. It uses the same Postgres volume as local development. Port 5434 is unchanged for the database on the host. Stop the packaged app with `docker compose stop web` when you want the development API on port 8000 to be the only writer.

Run tests from project root:

```bash
python -m pytest tests -q
```

With the packaged app on port 8080, the browser check is:

```bash
cd frontend
npm run e2e
```

## Written submission
- [Design brief](docs/design-brief.md)
- [Error report](docs/error-report.md)
- [Submission video script](docs/submission-video.md) — record this on your machine. The script is the shot list. There is no video file in the repository.

## API preview
- `GET /api/overview`
- `GET /api/lines?q=wages`
- `GET /api/lines/F1040.1a`
- `GET /api/documents`
- `GET /api/documents/D09`
- `GET /api/findings` — independent checks, engine diagnostics, prior-year variances, and cross-document ties
- `GET /api/versions`
- `GET /api/scenarios`
- `GET /api/timeline`
- `POST /api/lines/F1040.1a/review` — `{ "status":"needs_review", "note":"Check support", "actor":"st-01" }`
- `GET /api/audit`
- `GET /api/filing`
- `GET /api/questions` and `POST /api/questions` — `{ "author":"st-01", "body":"Check the transcript", "line_key":"F1040.26" }`
- `POST /api/questions/{id}/messages` and `POST /api/questions/{id}/resolve`
- `GET /api/client-correspondence`
- `GET /api/versions/compare?earlier=v2&later=v3`
- `GET /api/adjustments` and `POST /api/adjustments` — `{ "author":"st-01", "note":"Propose the RSU basis", "finding_ids":["independent-rsu-basis"] }`
- `POST /api/adjustments/{id}/reverse`
- `GET /api/records` — schedules, carryovers, notices, the e-file replay, and the firm's written standards
- `GET /api/lines?form=SchC`
- `POST /api/explanations` — `{ "line_key":"F1040.1a", "question":"Where do these wages come from?" }`
- `GET /api/explanations/eval` — citation, injection, and unsupported-amount checks

## Design principle
The JSON packet is immutable engine/source output. Workpaper review information lives separately in persisted state. A reviewer must be able to trace the resulting number to its origin and inspect the evidence without trusting the engine's self-reported confidence.

The review workspace, the packaged app on port 8080, the integration journey, and the written submission are in this repository. Record the video from `docs/submission-video.md` when you present it.
