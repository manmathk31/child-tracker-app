# AGENTS.md — ChildTrack Repository Conventions

This file governs how any coding agent (or human) works in this repository. It applies to **every session**, not just the initial build. If `CHILDTRACK_MASTER_BUILD_PROMPT.md` tells you *what* to build and in what order, this file tells you *how* to work in this codebase day to day. Read this before every task, not just once.

If anything here conflicts with a specific task instruction, the task instruction wins for that task only — but flag the conflict instead of silently overriding a rule.

---

## 1. Project Context (quick reference)

- **Product**: ChildTrack — indoor child-tracking and safety monitoring platform for schools, using ESP32 wearables, Wi-Fi RSSI fingerprinting, FastAPI backend, Jinja2 + vanilla JS frontend.
- **Status**: Real product, actively built in phases. Treat all code as production code, not a prototype.
- **Full spec**: see `CHILDTRACK_MASTER_BUILD_PROMPT.md` and `docs/DATA_MODEL.md`, `docs/API.md`, `docs/ESP32_PROTOCOL.md`.

---

## 2. Absolute Rules (never violate these)

1. **No demo/mock/seed data presented as real functionality.** Test fixtures live only in `tests/` and are clearly named as fixtures. The running app always reflects real DB state, including correct empty states.
2. **No hardcoded school-specific values** (zone names, thresholds, BSSIDs, student data) anywhere outside the database or admin-configurable settings.
3. **No secrets in the repo.** `.env` is gitignored; only `.env.example` (with placeholder values) is committed. If a secret is ever accidentally committed, treat it as compromised — rotate it, don't just delete the commit.
4. **No bare `except:`** and no silently swallowed exceptions. Every caught exception is either handled meaningfully or re-raised as a typed exception from `core/exceptions.py`, and logged.
5. **No business logic in route handlers.** Routes validate input (via Pydantic) and delegate to `services/`. If you find yourself writing an `if`/query inside a router beyond basic orchestration, move it to a service.
6. **No direct SQL string interpolation.** Always use SQLAlchemy's parameterized queries/ORM.
7. **Never commit directly to `main`.** All work happens on a branch and lands via PR, even for solo development — this keeps history reviewable and bisectable.
8. **Never merge with a red test suite or a failing migration.**

---

## 3. Coding Conventions

### Python / FastAPI
- Python 3.11+. Type hints on every function signature, including return types.
- Formatting: `black` + `isort`, enforced (run before every commit, or wire as a pre-commit hook).
- Linting: `ruff` (or `flake8` + `pylint` if preferred) — zero warnings on new code.
- Naming: `snake_case` for functions/variables/files, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- One domain per file/module (students, devices, zones, etc.) — mirror the structure across `models/`, `schemas/`, `services/`, `routers/`.
- Docstrings (Google or NumPy style, pick one and stay consistent) on every service function and every non-trivial function — explain *why*, not just *what*, when the logic isn't obvious (especially in `localization_service.py`).
- Pydantic schemas are the single source of truth for API request/response shape — never return raw ORM objects from a router.
- Async all the way down in the request path: no blocking I/O inside `async def` routes/services.

### Templates / Frontend
- Jinja2 templates: shared layout in `base.html`, page-specific templates extend it, reusable pieces (cards, nav, empty-state, status badge) live in `templates/components/` and are `{% include %}`'d, never copy-pasted.
- CSS: use the design-token file (colors, spacing, radius, shadow) — no magic hex codes scattered in templates or inline `style=` attributes except for truly one-off cases.
- JS: vanilla, one file per feature area under `static/js/` (e.g. `fingerprint_collection.js`, `live_dashboard.js`), no inline `<script>` blocks with real logic in templates beyond trivial wiring.
- Every fetch() call handles the error case in the UI (toast/inline message), not just the happy path.

### Database
- Every schema change goes through an Alembic migration — never hand-edit the DB, never rely on `create_all` outside local scratch testing.
- Migration filenames/messages are descriptive (`add_alerts_table`, not `update`).
- Foreign key behavior (`RESTRICT`/soft-delete) must be explicit and match Section 3 of the master prompt's data model — don't default to `CASCADE` without a documented reason.
- Add indexes for any column used in a `WHERE`/`ORDER BY` on a hot path (ingestion, live dashboard, alert queries).

---

## 4. Git Workflow

### Branch naming
```
<type>/<short-description>
```
Types: `feat`, `fix`, `chore`, `refactor`, `test`, `docs`, `perf`, `security`.
Examples: `feat/zone-creation-api`, `fix/offline-alert-duplicate`, `refactor/localization-service`.

### Commit message format (Conventional Commits)
```
<type>(<scope>): <short summary, imperative mood, no trailing period>

<optional body — why this change, not just what>

<optional footer — Closes #12, BREAKING CHANGE: ...>
```
Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `security`.
Scope: the module/domain touched (`zones`, `fingerprints`, `auth`, `tracking`, `alerts`, `ui`, `db`).

Examples:
```
feat(zones): add zone creation and listing endpoints

Implements the admin zone CRUD flow per Phase 2 of the master prompt.
Includes soft-delete via is_active rather than hard delete, since
zones are referenced by access_points and fingerprints.

Closes #14
```
```
fix(tracking): reject ingestion payloads with unknown device_id

Previously an unrecognized device_id caused an unhandled 500.
Now returns 404 with a clear error body and logs the attempt.
```

Rules:
- One logical change per commit. Don't bundle an unrelated formatting pass into a feature commit.
- Never commit with a message like `wip`, `fix stuff`, `updates` — every commit should be understandable from the message alone, six months later, with no other context.
- Run formatter/linter/tests **before** committing, not after.

### PR template
Every PR description follows this shape (create `.github/pull_request_template.md` with this content so it auto-populates):

```markdown
## Summary
What does this PR do and why? Link to the relevant phase/section of the master prompt if applicable.

## Changes
- Bullet list of concrete changes (models, endpoints, templates, migrations touched)

## Testing
- [ ] New/updated automated tests pass locally
- [ ] Manually verified on desktop viewport
- [ ] Manually verified on mobile viewport (≤768px)
- [ ] Verified with an empty database (correct empty states)
- [ ] Verified with populated data

## Migrations
- [ ] No schema change
- [ ] Schema change included, migration runs cleanly from a fresh DB, downgrade path checked

## Checklist
- [ ] No hardcoded values that should be config/DB-driven
- [ ] No demo/mock data left in non-test code
- [ ] Error paths handled (not just happy path)
- [ ] Logging added for new failure/alert conditions
- [ ] Docs updated (`docs/API.md`, `docs/DATA_MODEL.md`, `docs/ESP32_PROTOCOL.md`) if relevant

## Deferred / Follow-up
Anything deliberately left out of scope for this PR, and why.
```

### Push checklist (run before every push)
1. `black . && isort .` (or configured formatter) — clean diff, no unrelated reformatting noise.
2. `ruff check .` — zero warnings on touched files.
3. `pytest` — full suite green.
4. `alembic upgrade head` against a fresh DB — migrations apply cleanly.
5. Review your own diff once, end to end, before opening the PR — catch leftover debug prints, commented-out code, or stray TODOs.

---

## 5. Testing Expectations

- Every new service function: unit test covering the main case and at least one failure/edge case.
- Every new router endpoint: integration test for the happy path and for at least one 4xx case (validation failure, not-found, forbidden).
- Localization engine changes: always accompanied by a test using a known RSSI vector with an expected zone + confidence band — regression protection is critical here since it's probabilistic logic.
- Alert generation logic: test idempotency explicitly (e.g. offline monitor doesn't create duplicate active alerts).
- Run the full suite locally before pushing — don't rely on CI to catch what you could've caught in ten seconds.

---

## 6. When You're Unsure

- If a requirement in the master prompt is ambiguous, make the most reasonable production-grade decision, document it briefly in the PR description or a `docs/` note, and proceed — don't stall waiting for clarification on minor implementation details.
- If a decision is architecturally significant (e.g. changing the DB choice, swapping the localization algorithm approach, adding a new top-level dependency), stop and flag it before proceeding.
- Never silently deviate from the folder structure, naming conventions, or the "no demo data" rule to save time. If a shortcut seems necessary, say so explicitly instead of taking it quietly.

---

## 7. Definition of Done (applies to every task, not just phases)

A task is done when:
1. Code follows the conventions above.
2. Tests are written and passing.
3. Migrations (if any) apply cleanly from a fresh database.
4. The affected pages work correctly with an empty DB and with real data.
5. Mobile viewport checked.
6. Commit(s) follow the message format, PR follows the template.
7. Relevant `docs/` files are updated.
