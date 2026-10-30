# V1 source publication checklist

Prepared October 30, 2026 for [PR #15](https://github.com/Alexclavage/apple-pickup-stock-watcher/pull/15)
against `main`. Version/tag: **v1.0.0**. Maintainer authorized publication on October 30, 2026.
Scope: MIT-licensed source for local self-hosting. Public hosting and Railway
migration require a separate decision.

## Completed evidence

- [x] Review the 43-file diff at `2af0fa5` against `main` at `89ca8cb` for secrets,
  private/generated files, license, packaging, security and documentation.
  See [publication review](PUBLICATION_REVIEW.md) for findings and limitations.
- [x] MIT license, contributor/security guides and complete runtime source present.
- [x] User validated a clean Windows clone in a new directory, fresh Python 3.14
  environment, dependencies, offline preflight and the then-current 116-test suite
  (113 passed, three JavaScript skips with old Node). This was not a clean OS image.
- [x] Subsequent candidate CI: **124 tests passed in each of four jobs**,
  Python 3.12/3.14 on Windows/Ubuntu, including eight integration-tool tests.
  [Recorded baseline run](https://github.com/Alexclavage/apple-pickup-stock-watcher/actions/runs/41111314716).
- [x] User's real Apple scan: three variants observed across US/CA, 17 distinct
  returned stores, zero coverage issues. Canada had two variants/one store;
  US had one variant/16 stores. This is bounded scan evidence, not universal coverage.
- [x] User confirmed Discord receipt in a private test channel.
- [x] User confirmed wizard listening at `127.0.0.1:8091`; dashboard loopback
  default is present in source and existing offline regression tests.
- [x] Basic wizard save exercised by user. Negative cases, partial/missing coverage
  and alert transitions have offline regression coverage, not live failure injection.
- [x] Private state temporary files excluded from Git/Docker; logs excluded from
  Docker. Version labels aligned to 1.0.0. [V1 notes](RELEASE_NOTES_V1.md) prepared.

These completed validations do not need to be requested from the user again.

## Publication gates

- [x] Final PR head `5cbc6f2` passed 124 tests in each of four jobs:
  [final CI](https://github.com/Alexclavage/apple-pickup-stock-watcher/actions/runs/41119379549).
- [x] Maintainer explicitly authorized merge and `v1.0.0` publication; PR #15 merged.

The authorization covers merge and V1 source publication only. **Do not change
Railway or close the fourteen stacked draft PRs** without a separate owner decision.

## Declared limitations and separate deployment work

- macOS clean installation and Docker runtime start/stop remain unvalidated.
  Ubuntu CI does not establish either. They are declared limitations of the
  source release, not completed claims or requests to repeat Windows testing.
- FR/GB adapters and Apple catalog discovery remain experimental. No claim of
  universal SKU/store, carrier, tax or price correctness.
- Apple schema failures, 429/541 cooldowns, multi-batch partial coverage and
  restart/transition behavior have mocks; live outages/retries are not exhaustive.
- Discord/state/history are best effort, without transactional delivery or outbox.
- Before public hosting: validate authentication or firewall/routing, persistent
  storage, single worker ownership and rollback. Dashboard has no built-in login;
  never expose the setup wizard. Railway migration needs a separate owner decision.
