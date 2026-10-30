# Contributing to Apple Stock Watcher

Thank you for helping improve this independent community project.

## Before starting

- Read [README.md](README.md) and review existing issues and pull requests to avoid duplicate work.
- For larger features or changes to Apple's endpoint integration, open an issue first to discuss scope.
- Use your own test data. Never post authentication cookies, Discord webhook URLs, Apple account information or personal store preferences.
- This is an unofficial project. Avoid aggressive polling and follow the applicable service terms.

## Local setup

On Windows CMD:

```bat
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
copy config.example.json config.json
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On macOS and Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
cp config.example.json config.json
.venv/bin/python -m unittest discover -s tests -v
```

The test suite must run offline and must not contact Apple, foreign exchange providers or Discord. Mock network responses for any new unit tests.

## Pull requests

1. Create a small feature branch and keep each pull request focused.
2. Add a regression test when changing stock classification, notifications, persistence, or error handling.
3. Run `python -m compileall -q app.py tests` and `python -m unittest discover -s tests -v`.
4. Explain what changed, why, and what you tested. If changing actual Apple request logic, describe any manual verification separately.
5. Disclose any AI assistance and personally review and test all contributed code.

Please do not commit `.env`, `config.json`, logs, state files or session captures.

## Security

See [SECURITY.md](SECURITY.md) for handling security issues.
