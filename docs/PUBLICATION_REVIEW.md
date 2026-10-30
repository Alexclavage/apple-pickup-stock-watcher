# V1 source publication review

Reviewed October 30, 2026: PR #15 at `2af0fa5` versus `main` at `89ca8cb`:
43 changed files, 164 candidate commits. Scope is local source distribution;
this is not a penetration test or public-hosting approval.

## Findings and preparation

1. `save_state()` writes `state*.tmp`, but Git/Docker excluded only `state*.json`.
   Added the temporary-file pattern to both. Docker also lacked `*.log` despite
   `COPY . .`; added it to keep local logs out of images. No such files were tracked.
2. Dashboard, Discord and `/health` still identified the inherited V4.5. All now
   use one `VERSION = "1.0.0"` constant. This prepares source, not a tag or release.
3. Checklist/PR text still called the completed Windows/Apple/Discord checks
   pending. Updated evidence and separated publication from future hosting work.
4. Added V1 notes with distribution, upgrade/rollback and known limitations.

## Secrets, license and packaging

- Inspected tracked tree and reachable history filenames: no `.env`, private
  `config.json`, state/history, backups or key files under the searched names.
  Reviewed environment/config examples; no generated dependency bundles or
  vendored third-party binaries/source found. MIT license is present.
- Scanned **174 reachable blobs across 165 commits**, including the base, for
  Discord webhooks, GitHub tokens, AWS access keys and private-key headers.
  Sole match: the explicit dummy webhook in `tests/test_integration_smoke.py`.
  No live secret identified; pattern matching cannot prove absence of every secret.
- Reviewed dependency major-version bounds (Flask, requests, python-dotenv) and
  successful CI installation. No lockfile, SBOM or comprehensive dependency
  vulnerability audit is provided by this review.
- Required local modules are tracked. Docker installs requirements and starts
  `python app.py`; Compose maps dashboard to host loopback, mounts private config
  read-only and persists state/history. This is static inspection, not runtime proof.

## Security and quality

- Wizard restricts client/host, checks origin/token before mutation/catalog lookup,
  validates fields, backs up and atomically replaces config. Unknown legacy keys
  stay server-side. UI uses DOM text/value assignments and Jinja escaping.
- Catalog URLs use allowlists, bounded response size, caching and cooldowns.
  Apple/Discord HTTP errors redact sensitive request URLs.
- Dashboard is read-only and unauthenticated. Status/history intentionally expose
  product/store preferences locally. Area IDs can encode locations in logs/errors:
  operational outputs must remain private or be redacted before sharing.
- Reviewed batching, store coverage, partial/unknown semantics, persisted-state
  validation, history and notifications with existing regression coverage.
  No further runtime blocker substantiated for this local source-release scope.
- No live Apple/FX/Discord calls, polling worker, Docker service or Railway action
  started in this review. Live validation evidence is user-reported, not rerun here.

Ready for maintainer review once final-head CI passes. Explicit approval is still
required for merge and publication. No automatic merge or deployment is added.
