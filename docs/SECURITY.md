# Security boundaries and stronger examination mode

## Browser mode supplied in this project

A normal web page can ask for fullscreen, observe visibility/focus changes and block some page interactions. It cannot disable browser/OS controls, reliably detect a screenshot, inspect all running applications, prevent another application from screen sharing, identify a second phone/camera, or stop a candidate from modifying JavaScript. These limits apply even when the server records the events.

`Permissions-Policy: display-capture=()` limits this document's own `getDisplayMedia()` call where supported. It does not forbid Teams/Zoom/OBS/another browser tab from capturing the exam. The page's keyboard listeners see only events delivered to the page; OS-reserved screenshot shortcuts may never be delivered. Print CSS and disabled context menus are deterrents, not content protection. Once a question reaches a candidate's device, the web server cannot make it impossible to copy.

A fullscreen-exit overlay pauses interaction on the displayed page; it does not pause the server clock. Focus and resize signals can arise from normal browser behavior, accessibility tools or system dialogs. Technical signals are never a verdict. All outcomes require human release by default.

## Controls actually enforced by the API

- Password validation uses salted scrypt hashes. No plaintext passwords are stored in database records.
- JWT sessions use an explicit algorithm, expiry and database-backed session ID. Logout, reset and recovery revoke prior sessions.
- Session cookies are HttpOnly and SameSite=Strict; Secure is configurable for HTTPS. Cross-site write requests and unapproved Origin values are rejected. API callers without browser Origin headers still require authenticated cookies and authorization.
- Role checks protect all admin operations. Candidates see only their assigned published exams and own bound attempts. Correct answer indices are never included in candidate question responses.
- Single-attempt unique constraints and PostgreSQL row locks protect write consistency. The tab UUID is an extra concurrency binding, not cryptographic hardware identity. It can be copied by a determined user; duplicated browser tabs may clone sessionStorage.
- Deadlines are created by the server, stored once and checked on writes. A changed client clock, missing timer, replayed answer or late reconnect cannot extend a deadline.
- Known browser event types are validated. Event UUID deduplication prevents a retried event from increasing the count twice. Events per attempt are capped at 1,000; the client queue retains at most 100 unsent events.
- MinIO is private. Authenticated owner-admin report downloads are proxied; CSV cells that could trigger spreadsheet formulas are escaped.
- No shared answer-content cache exists. Redis is for rate limiting only.

These controls protect exam state but cannot convert an untrusted browser into a locked device. A malicious client can suppress telemetry and still send heartbeats. Mandatory admin review alone does not solve that problem.

## If all five restrictions are mandatory

Deploy on supervised managed devices with a tested lockdown browser such as Safe Exam Browser. Configure supported policies for application switching, window controls, screenshot capture and remote sessions, and validate them on every supported OS/version. Lockdown policy behavior is platform-specific and cannot prevent a second physical camera.

The supplied project does not claim to verify Safe Exam Browser. Installing it and changing a user agent is not server attestation. A real integration needs documented client configuration, allowed URL/resource policy, configured Browser Exam Key/Config Key request verification as appropriate for the selected SEB integration, approved configuration lifecycle, recovery procedure and end-to-end acceptance testing. Do not deploy a simplistic `X-Is-Lockdown: true` header gate as proof of security.

Reference documentation:

- Fullscreen user-exit behavior: https://developer.mozilla.org/en-US/docs/Web/API/Fullscreen_API/Guide
- Visibility signals: https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API
- Screen capture policy scope: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/display-capture
- Safe Exam Browser platform overview: https://safeexambrowser.org/about_overview_en.html
- SEB integration documentation: https://safeexambrowser.org/developer/seb-integration.html

## Network deployment

Local Compose binds the website and administrative consoles to loopback. For access by remote candidates, put the site behind an HTTPS reverse proxy; configure the exact public origin in `CORS_ORIGINS`, `COOKIE_SECURE=true`, and an explicit trusted-proxy topology. Keep API, PostgreSQL, Redis and MinIO S3 ports private. Adminer and the MinIO console are administrative tools, not candidate interfaces. Use an unprivileged bucket-scoped MinIO application account instead of root credentials.

Disable demo seeding for a fresh real deployment; remove sample records/accounts from existing test environments before using real candidate information. Secrets generated by `init_env.py` are not included in the distribution. Changing an environment secret is not the same as rotating an already initialized database/account password.

Define retention for database events, answers, audit records and CSV reports. This reference project retains them until explicitly removed; it does not set MinIO lifecycle expiration or automate deletion. Back up PostgreSQL and MinIO together, restrict administrator access, and establish an appeal/review procedure. The database audit log is not immutable against a privileged database operator.
