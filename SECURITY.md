# Security Policy

This application is intended for self-hosting. The web dashboard and `/api/status` endpoint are **not authenticated**. Do not expose them publicly without your own authentication or network restrictions.

## Reporting a vulnerability

If the repository's **Security → Report a vulnerability** option is available, use it to report issues privately. Otherwise, contact the repository owner through a private channel rather than opening a public issue containing a proof of concept, user data, or credentials.

Please avoid including live secrets, webhook URLs, browser session cookies, or personal configuration details in reports.

## Credentials

- Put Discord webhooks in a local `.env` file or deployment secrets, never in `.env.example`.
- Never commit `.env`, `config.json`, session captures, or runtime state.
- If a token or webhook leaks, **revoke or rotate it immediately**. Removing it from the latest file does not erase Git history.

## Supported releases

Security fixes are considered for the current default branch. Older snapshots are not separately maintained.
