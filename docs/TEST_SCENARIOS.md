# Acceptance scenarios

Use a disposable demo installation. Sign in as admin and candidate in separate browser profiles. Browser signals are best effort; do not label a screenshot test successful merely because a PrintScreen listener fires.

| # | Scenario | Action | Expected outcome |
|---|---|---|---|
| 1 | Login guard | Visit the portal signed out; call `/v1/exams` without cookies | Login screen; API returns 401 |
| 2 | Incorrect credentials | Enter an invalid password | Generic 401; no username-existence disclosure in the message |
| 3 | Login throttling | Send over 10 login requests for an account in 5 minutes | 429, including when credentials are valid; recover after TTL |
| 4 | Role isolation | As candidate request `/v1/admin/attempts` | 403 |
| 5 | Candidate isolation | Use candidate B's cookie to request candidate A's attempt | 404; no attempt data |
| 6 | Publish review | Save a draft, edit it, then publish after human approval | Draft editable; published exam cannot be modified |
| 7 | Assignment | Assign candidate A but not B | Only A sees and can start the published exam |
| 8 | Fullscreen | Start exam, then press Esc | Fullscreen requested before start; exit records a signal and displays return overlay; deadline continues |
| 9 | Tab switch | Switch to another tab, return and sync | Received event shown to admin; no automatic disqualification |
| 10 | Screenshot | Use OS screenshot controls | May succeed in browser mode; stronger device controls needed. Never claim browser capture protection |
| 11 | Screen sharing | Try external Teams/Zoom/OBS sharing in a permitted test environment | Portal cannot reliably detect/block external sharing; validate managed-device policy separately |
| 12 | Resize/minimize | Leave fullscreen and minimize the window | Best-effort visibility/resize events; browser cannot prohibit OS actions |
| 13 | Autosave | Select an answer; see saved status; refresh and resume using the same tab | Server answer restored and deadline unchanged |
| 14 | Offline save | Disconnect, choose an answer, reconnect before deadline, retry sync | Pending answer synced if accepted before deadline; visible failure otherwise |
| 15 | Expiry offline | Remain disconnected beyond the deadline | Server sweeper closes attempt; late answers rejected on reconnect |
| 16 | Clock manipulation | Move local clock forward/backward or edit frontend countdown | Stored server deadline and API rejection unchanged |
| 17 | Tab binding | Start with a different `client_id` while attempt active | 409; identifier is not guaranteed to distinguish a deliberately cloned tab |
| 18 | Concurrent login | Attempt a fresh login while exam session is active | 409 until session recovery/logout or exam closure |
| 19 | Heartbeat gap | Stop connectivity for over 60 seconds, then reconnect | Review flag set; does not prove misconduct or erase answers |
| 20 | Recovery | Admin recovers in-progress attempt with reason; candidate signs in again | Old session revoked; new tab can bind; saved answers and original deadline preserved |
| 21 | Submission replay | Submit twice; then send another answer | Same completed result; answer write rejected |
| 22 | Pass and review | Answer above pass mark, submit, admin approves | Pending review first, then qualified |
| 23 | Below pass mark | Answer below pass mark, submit, admin approves validity | Not qualified; approval does not alter score |
| 24 | Disqualification | Admin rejects a completed attempt with required context | Disqualified; note visible to candidate; audit records decision |
| 25 | Export | Admin exports results and downloads report | CSV stored in private MinIO bucket; candidate cannot download it |
| 26 | Storage outage | Stop MinIO and export | Clear 503; no fake successful download |
| 27 | AI unavailable | Keep Gemma disabled or return malformed model output | Clear 409/502; no questions silently saved or published |
| 28 | Persistence | Restart Compose without deleting volumes | Accounts, exams, answers and reports retained |
| 29 | Cross-origin write | Browser POST with unapproved Origin | 403 |
| 30 | High-stakes device acceptance | Repeat controls on the exact managed OS/lockdown client | Requires separate native device configuration/integration; not delivered by browser mode |

## Automated verification scope

`backend/tests/test_portal.py` exercises the API with a fresh isolated SQLite database, fakeredis with Lua support, and an in-memory MinIO boundary substitute. It verifies 17 integration scenarios, including successful assessment/review, late writes, permissions, event replay, recovery and CSV escaping. The suite can target a disposable PostgreSQL database through `TEST_DATABASE_URL`.

A passing SQLite suite does not establish PostgreSQL locking correctness, Docker image availability, real S3 compatibility, actual Gemma response quality, browser/OS device control, load capacity or deployment readiness. Validate these boundaries on the target environment.
