# MeritGate — Candidate Examination Portal

A runnable, self-hosted examination project with candidate and administrator workspaces, timed multiple-choice exams, server-scored results, browser monitoring signals, human review, and private MinIO report storage.

This project treats “qualification” as passing an assessment inside your organization. It does not determine statutory election eligibility or submit anything to an election authority.

## What your five requirements can actually achieve

| Requirement | Included browser behavior | Server control | Stronger device control |
|---|---|---|---|
| No tab switching | Logs `visibilitychange` / focus loss and warns the candidate | Stores received events and routes results to review | Managed exam computers and a configured lockdown browser |
| No screenshots | Watermark, print stylesheet, best-effort shortcut signals, copy/print deterrence | Auditable reports and review; no claim to detect all screenshots | OS capture restrictions through a supported lockdown client; validate per OS |
| User ID/password | Login required; no public self-registration | Scrypt password hashes, signed HttpOnly session cookie, RBAC, Redis login throttles | Managed identity / MFA can be added separately |
| No screen sharing | The portal does not initiate capture; `Permissions-Policy: display-capture=()` | Cannot discover or stop an external sharing application | Lockdown client, managed process/network policy, supervised environment |
| No minimizing/maximizing | Fullscreen entry, fullscreen-exit overlay, resize/visibility signals | Original timer continues; records reported signals | OS kiosk restrictions through a configured lockdown browser |

**A regular website cannot guarantee the first, second, fourth or fifth restriction.** Browser event reporting is untrusted and can be suppressed or forged. The server never treats a browser header, user agent, fullscreen flag, or a JavaScript event as proof of device lockdown. The downloadable application includes the browser mode above. It does **not** include a native lockdown client or Safe Exam Browser attestation integration. See [docs/SECURITY.md](docs/SECURITY.md).

## Included functionality

- Candidate ID/password login; administrator-created accounts and password resets.
- Administrator dashboard, examination draft editor, explicit publish approval, candidate assignment.
- Draft editing; published question sets, pass marks and durations are immutable.
- 1–100 MCQs, four distinct options per question, durations from 1–180 minutes.
- Persisted randomized question order per attempt; one attempt per assigned exam.
- Answer keys stay server-side; deterministic scoring never depends on an LLM.
- Server-owned deadline, autosave per answer, clear answer, question palette, countdown.
- Fixed deadline across refreshes, disconnections, session recovery and client clock changes.
- One active attempt per account; tab identifier binding prevents accidental cross-tab access. It is not hardware identity.
- Fullscreen instructions, monitoring notice and consent acknowledgment before starting.
- Best-effort tab/focus/fullscreen/copy/paste/print/resize/offline event reporting, event deduplication.
- Offline pending answers/events kept in the same tab's sessionStorage and retried while time remains. **Only answers accepted by the server before the deadline count.**
- Heartbeat every 10 seconds; gap over 60 seconds flags review. Background worker checks deadlines every 10 seconds; all relevant requests also check the deadline.
- All completed results require administrator release by default. A valid attempt below the pass mark remains not qualified.
- Human approval/disqualification with required notes; candidate-visible result/review note.
- Admin session recovery revokes the old login and releases the tab binding, preserving answers/deadline and requiring review.
- CSV result exports stored in a private MinIO bucket, downloaded through an authenticated administrator endpoint.
- Activity log of administrative actions and exam lifecycle events.
- Optional Gemma question drafting with schema validation; drafts require human fact/answer verification and manual publication.
- FastAPI Swagger interface and automated API integration tests.

## Stack

| Component | Choice | Purpose |
|---|---|---|
| Frontend | HTML, CSS, JavaScript | Responsive candidate/admin UI; no Node build required |
| API | Python 3.11, FastAPI, Pydantic | Authentication, exam lifecycle, validation |
| Database | PostgreSQL 16, SQLAlchemy 2 | Accounts, exams, assignments, attempts, answers, events and audit records |
| Redis | Redis 7 | Shared atomic sign-in rate limits |
| Object storage | MinIO | Private generated result CSV files |
| Optional AI | Ollama `gemma3:4b` via OpenAI-compatible API | Admin-only question suggestions |
| Reverse proxy | Nginx | One browser origin and browser security headers |
| Local deployment | Docker Compose | Reproducible service configuration and durable named volumes |

Temporal is unnecessary for short answer saves and deterministic MCQ grading. A small deadline sweeper plus request-time checks handles expiry without placing exam content in workflow history. PPT slide settings, content caching, rendering, GLM and Temporal payload settings from your previous configuration have therefore been removed. Redis never caches candidate grades or answer keys for browser reuse.

## Start on your Mac, Linux or Windows

Prerequisites: Docker Engine with Compose v2 / Docker Desktop, Python 3.9+ for the one-time configuration script, and a desktop browser with Fullscreen API support. On Windows use `py -3` if `python3` is unavailable.

1. Extract this project and open a terminal in the `meritgate` directory.
2. Generate separate random secrets once:

   ```bash
   python3 scripts/init_env.py
   ```

   This creates `.env` without overwriting an existing file. Open it in your editor. `ADMIN_PASSWORD` and `DEMO_CANDIDATE_PASSWORD` contain the generated login passwords. Do not commit or share `.env`.

3. Start all services:

   ```bash
   docker compose up --build -d
   ```

   MinIO is compiled from pinned official community source inside Docker, so the first build can take several minutes on older Intel Macs. No host Go installation is required. See [storage/minio/README.md](storage/minio/README.md).

4. Open **http://localhost:5173**. First-time image pulls and builds need internet access and can take several minutes.

5. Sign in using either:

   | Role | User ID | Password |
   |---|---|---|
   | Administrator | `admin` (or `ADMIN_USERNAME`) | `ADMIN_PASSWORD` from `.env` |
   | Sample candidate | `candidate01` | `DEMO_CANDIDATE_PASSWORD` from `.env` |

   Demo mode creates one assigned 15-minute assessment with eight practice questions. Use separate browser profiles for candidate and admin testing; cookies are shared between tabs in a single profile.

6. Check services if the portal is not ready:

   ```bash
   docker compose ps
   docker compose logs --tail=100 api web
   ```

   API health: **http://localhost:5173/v1/health**. Swagger: **http://localhost:5173/docs**. The UI and API share one origin, so candidate cookies do not need cross-site access.

Stop everything while retaining data:

```bash
docker compose down
```

Start it again:

```bash
docker compose up -d
```

Do not use `docker compose down -v` unless you deliberately want to delete the database, Redis and object-storage volumes.

### MinIO pull fails with unauthorized / access denied

The original package referenced a prebuilt `quay.io/minio/minio` image. The updated
Compose file uses `build: ./storage/minio` and compiles a pinned official community
source release instead. Copy the updated `compose.yaml` and `storage/` directory
into your existing project, preserving `.env`, then run:

```bash
docker compose build minio
docker compose up --build -d
```

This is a container-registry access failure before MinIO starts. The `.env` MinIO
passwords do not authenticate Docker image downloads. Source builds still need
internet access to the base-image registry and Go module sources. The community
repository is archived; this workaround is for local development. Evaluate a
maintained storage distribution/service before production use.

### Ports already in use

The project does not bind PostgreSQL `5432` or Redis `6379` to the host, which avoids conflicts with your other projects. Change `WEB_PORT` or `MINIO_CONSOLE_PORT` in `.env` if `5173` or `9001` is busy. If changing the browser port or hostname, update `CORS_ORIGINS` to the exact URL too, then run `docker compose up -d`. Use the same hostname consistently: `localhost` and `127.0.0.1` have different cookie origins.

## Test the full workflow in the UI

### Administrator

1. Sign in as admin and select **Candidates → Add candidate**.
2. Enter a name, unique user ID, and password of at least 12 characters. Issue credentials privately.
3. Select **Examinations → Create examination**.
4. Enter the title, duration and pass mark. Paste questions into the JSON editor:

   ```json
   [
     {
       "prompt": "What is 10 percent of 250?",
       "options": ["10", "20", "25", "50"],
       "correct_index": 2
     }
   ]
   ```

   The correct answer uses a **zero-based** index: `0=A`, `1=B`, `2=C`, `3=D`. Save the draft. You can edit it until publication.

5. Select **Publish**, confirm human verification, then select **Assign candidate**.
6. In a different browser profile sign in as the candidate. The exam appears in **My examinations**.
7. After submission, open **Attempts & review → Events** to inspect received signals.
8. Select **Review**, approve the attempt or disqualify with a reason. Approval releases the calculated pass/fail result; it cannot turn a failing score into a pass.
9. Select **Export results** to store and download a CSV report. Open **Activity log** for audit records.

### Candidate

1. Sign in with the assigned candidate credentials.
2. Select **View instructions**, read the monitoring notice and acknowledge it.
3. Select **Enter fullscreen & start**. The deadline starts on the server when the start request succeeds.
4. Choose an answer. Check the top-right save status. Use the numbered question palette, Next/Previous, or Clear answer.
5. Finish with **Submit examination** and confirm. The result shows **Pending review** by default.
6. Return to **My results** after the administrator reviews the attempt.

### Browser controls test

1. During a practice exam, switch tabs, then return. A tab-hidden event should appear in the admin event list after sync.
2. Press Esc to leave fullscreen. The exam overlay asks you to return to fullscreen. The clock keeps running.
3. Attempt copy/paste or right-click inside the exam. These page actions are blocked where the browser allows it, and a signal is queued.
4. Disconnect the network briefly and select an answer. It remains pending in that tab. Reconnect before the deadline and use **Retry sync**. A gap over the configured threshold requires review.
5. Test OS screenshots or external screen sharing: an ordinary browser may still allow them. This is an expected browser limitation, not a successful restriction. Deploy a validated lockdown environment if these must be blocked.

Detailed expected outcomes: [docs/TEST_SCENARIOS.md](docs/TEST_SCENARIOS.md).

### Lost browser or crashed tab

Ask the administrator to select **Attempts & review → Recover** and enter a reason. The candidate can sign in again and resume from the assigned exam card. Recovery revokes the previous session and tab binding. It **does not** extend time, restore unsynced answers from a destroyed tab, reopen a submitted exam, or grant another attempt. An overdue attempt stays closed.

## PostgreSQL, MinIO and Redis access

### PostgreSQL through a UI

```bash
docker compose --profile tools up -d db-admin
```

Open **http://localhost:8081**:

- System: PostgreSQL
- Server: `postgres`
- Username: `POSTGRES_USER` from `.env`
- Password: `POSTGRES_PASSWORD` from `.env`
- Database: `POSTGRES_DB` from `.env`

Inspect `users`, `exams`, `questions`, `enrollments`, `attempts`, `events`, `audit` and `reports`. Do not manually edit live attempt records. Answer keys and password hashes must remain inaccessible to candidates.

### MinIO through a UI

Open **http://localhost:9001**. Username is `MINIO_ACCESS_KEY`; password is `MINIO_SECRET_KEY` from `.env`. The `exam-reports` bucket is created on the first successful report export. Objects are under `reports/`. The bucket is private; no anonymous download policy is configured.

The app connects internally to `minio:9000`. The S3 API is not exposed on a host port. The console is bound to loopback for local administration.

### Redis

Redis has no included web UI. It is used for authentication throttling, not permanent answers. The API health endpoint checks Redis and PostgreSQL. Do not expose Redis publicly. Named-volume persistence is enabled.

## Enable Gemma (optional)

Examinations work without Gemma. On your host, install/run Ollama and fetch the model:

```bash
ollama pull gemma3:4b
ollama serve
```

If Ollama is already running, do not start a second server. Docker must be able to reach Ollama on `host.docker.internal:11434`; an Ollama process listening only on `127.0.0.1` may need its listening address adjusted for Docker networking. Restrict access with the host firewall.

Set in `.env`:

```dotenv
GEMMA_ENABLED=true
GEMMA_BASE_URL=http://host.docker.internal:11434/v1
GEMMA_API_KEY=not-needed
GEMMA_MODEL=gemma3:4b
LLM_TIMEOUT_SECONDS=120
```

Then:

```bash
docker compose up -d api
```

In the exam draft editor enter a topic and select **Draft 3 questions with Gemma**. Verify every fact and correct answer. Invalid responses fail safely and do not create/publish an exam. Local CPU inference, particularly on an 8 GB Intel iMac, can exceed the timeout; use the manual JSON editor or raise both `LLM_TIMEOUT_SECONDS` and Nginx `proxy_read_timeout` as needed. No candidate answers or grades are sent to Gemma.

## Configuration that matters

| Variable | Default/example | Effect |
|---|---|---|
| `REQUIRE_ADMIN_RESULT_REVIEW` | `true` | Every completed attempt awaits human release. If false, only flagged attempts wait; browser signals remain untrusted. |
| `REVIEW_EVENT_THRESHOLD` | `3` | Received distinct events at/above threshold flag review. Not a misconduct verdict. |
| `HEARTBEAT_GAP_SECONDS` | `60` | Missing heartbeat interval flags review; does not reset the exam. |
| `COOKIE_SECURE` | `false` locally | Set true behind HTTPS for network deployment. |
| `CORS_ORIGINS` | local browser URLs | Explicit allowed origins for browser access/writes. |
| `SEED_DEMO` | `true` | Initial local demo account/exam. Set false for a fresh non-demo deployment. |
| `GEMMA_ENABLED` | `false` | Optional admin-only question generation. |
| `MINIO_OUTPUT_BUCKET` | `exam-reports` | Private report bucket. |

Changing `.env` does not reset database passwords or existing account passwords. PostgreSQL initialization variables only apply to an empty database volume. Admin/candidate bootstrap also preserves existing accounts. Reset candidate passwords from the admin UI; see the recovery command below for the initial administrator.

Recover the bootstrap admin password using the value currently in `.env` (this revokes that admin's sessions):

```bash
docker compose exec api python -m app.reset_admin
```

## Tests

From `backend`:

```bash
python3 -m venv .venv
# macOS/Linux
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
```

On Windows activate `.venv\Scripts\activate` instead. Tests use an isolated in-memory SQLite database and mocked Redis/MinIO boundaries by default. They exercise authentication/RBAC, question-key secrecy, deadlines, scoring/review, event deduplication, recovery, draft immutability, CSRF origin checks, login throttling, report authorization and AI failure handling.

For the same suite against a **disposable, empty test PostgreSQL database**:

```bash
TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST:5432/meritgate_test' python -m pytest -q
```

**The test fixture drops/recreates application tables in that database. Never point it at real exam data.** Separate real PostgreSQL concurrency/load testing, real MinIO upload/download checks and OS/browser acceptance tests are needed before high-stakes use.

## Production scope

This is a functional reference implementation for local evaluation and further hardening. The supplied Compose binds the portal and admin consoles to loopback. It is not deployed to a public host.

Before a real competitive examination, validate an appropriate lockdown browser/device policy if device restrictions are mandatory; run real PostgreSQL/MinIO and concurrent-client tests; arrange HTTPS, identity verification, supervised procedures, backups, data retention and accessibility accommodations. No webcam surveillance or automatic misconduct classifier is included. Browser technical events must be interpreted in context.

The initial schema is created explicitly by `python -m app.bootstrap` at container startup. Version 1 has no schema migration system; add reviewed migrations before upgrading an installation with real candidate records. The activity log is application-controlled database history, not a tamper-proof external ledger. There is no automatic expiry of database records or MinIO reports.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/SECURITY.md](docs/SECURITY.md) for boundaries and deployment design.
