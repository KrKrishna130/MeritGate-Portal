# Verification record

Prepared: 11 November 2026.

## Passed

- 17 API integration tests, run with the distribution's pinned dependencies in a clean Python virtual environment (host Python 3.12).
- JavaScript syntax check with `node --check frontend/app.js`.
- Python module compilation.
- Compose YAML structure and API Dockerfile CMD JSON validation.
- Configuration generator: random credential creation, internally matching database/Redis URLs, and refusal to overwrite an existing `.env`.
- Browser visual inspection: login screen, candidate dashboard, instructions and administrator dashboard.
- Browser interaction with synthetic QA user fixtures: created a draft examination using the real UI/API, verified successful save and its appearance in the examination library. The preview-only fixture bypass is not included in this distribution. Authentication and authorization are tested through the API suite.

## Not verified here

- Full Docker Compose startup: Docker is not available in the build workspace.
- Real PostgreSQL transactions, row-lock behavior, concurrent candidate load, external MinIO storage and report download.
- Real Ollama/Gemma inference and quality of generated questions.
- Live fullscreen examination UI: the cloud preview browser denied the fullscreen request. The application does not bypass that denial. Verify fullscreen entry, exit overlay, autosave and timer display on your target desktop browsers.
- Native screenshot blocking, external screen-sharing restrictions or OS window locking. These are not implemented by this browser project and require a separately configured/validated lockdown environment.

The API test suite uses SQLite, fakeredis with Lua support and a MinIO substitute. It is useful functional evidence, not a claim of production readiness. Use the included acceptance scenarios on the target environment before high-stakes use.

## 12 November 2026: MinIO image-access correction

Replaced the prebuilt Quay MinIO image reference with a local multi-stage Docker
build from pinned official MinIO community source. The MinIO service name, existing
volume, endpoints and credentials are unchanged. Compose structure, Dockerfile JSON
instructions and archive integrity were checked. Docker is still unavailable in the
build workspace, so source compilation and container startup must be verified on the
target machine. The archived community source is intended here for local evaluation;
it is not a maintained production storage recommendation.
