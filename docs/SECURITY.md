# Security

How Budget Buddy protects your data when it runs on your own machine (for
example a Mac mini at home), how changes get from GitHub to that machine
safely, and the gaps that remain. Everything here describes what the code does
today; the tests that check it are named where they exist.

## At a glance

| Area | What protects it |
|------|------------------|
| Data on disk | Database encrypted with SQLCipher (AES-256) using your `DB_PASSPHRASE` |
| Who can reach the app | Your network only; nothing is published to the internet. Recommended: Tailscale |
| Who can sign in | Accounts with bcrypt-hashed passwords; one-time invite links; admins manage access |
| Sessions | Signed, `HttpOnly`, `SameSite=Lax` cookies that expire after 7 days and end when the password changes |
| Forged requests | Cross-origin `POST`/`PUT`/`PATCH`/`DELETE` are rejected |
| What leaves the machine | Nothing by default. Only Plaid (if connected), Claude (if you choose it) and GitHub (updates) |
| Getting updates | Code reaches the Mac only from `main` on GitHub, after automated tests pass |

## 1. Your data on disk

- **Encrypted database.** All data lives in one SQLite file
  (`data/budget_buddy.db`) encrypted with [SQLCipher](https://www.zetetic.net/sqlcipher/)
  (256-bit AES). Without `DB_PASSPHRASE` the file is unreadable.
- **The app warns about weak setup.** If `DB_PASSPHRASE` is still the built-in
  default, or `SECRET_KEY` is missing, the app logs a loud warning at startup
  (`app/config.py`).
- **Secrets stay out of git.** `DB_PASSPHRASE`, `SECRET_KEY` and API keys live
  in `.env`, which `.gitignore` excludes. No database file is tracked in git.
- **Bank tokens.** Plaid access tokens are stored inside the encrypted
  database. They are not encrypted a second time, so anyone holding both the
  database and `DB_PASSPHRASE` can read them.
- **Backups** (Settings → Backup) contain:
  - `budget_buddy.db`: still encrypted with `DB_PASSPHRASE`. The copy is
    re-opened and every table's row count checked before it's handed out.
  - `budget-buddy-data.xlsx`: **not encrypted**, for reading without the app.
    Plaid access tokens and password hashes are left out
    (`tests/test_backup.py`). Store the zip somewhere private.
- **Keep `DB_PASSPHRASE` somewhere other than the Mac mini** (e.g. a password
  manager). Without it, neither the live database nor a backup can be opened.

## 2. Who can reach the app

Budget Buddy is a web server on port 8000. It doesn't open router ports or
contact any relay service itself, so it's only reachable from networks you put
it on.

- **By default it listens on every network interface** (`0.0.0.0:8000`) over
  plain HTTP. Any device on your home network can reach the sign-in page, and
  traffic on the local network is not encrypted.
- **Recommended setup: Tailscale.** Reach it at your Tailscale name
  (e.g. `https://<your-mac>.<tailnet>.ts.net`). Traffic between your devices is
  end-to-end encrypted by WireGuard, and only devices you've added to your
  tailnet can connect. Use `tailscale serve` for an HTTPS address. To invite
  someone, share the node with them in Tailscale.
- **Tighten it further** once you use Tailscale: run the app on `127.0.0.1`
  only, so it's reachable through `tailscale serve` and not directly from the
  home network. Set `BUDGET_BUDDY_HOST=127.0.0.1` for `deploy.sh` and
  `scripts/restart.sh`, and use `--host 127.0.0.1` in the launchd plist.
- **When served over HTTPS**, set `COOKIE_SECURE=true` in `.env` so the browser
  only sends the session cookie over encrypted connections.
- **Never forward port 8000 on your router.** The app is designed for a
  trusted network, not the open internet.
- `GET /healthz` answers without signing in (for monitoring). It returns only
  the app version.

## 3. Accounts and sign-in

- **Passwords** are hashed with bcrypt and never stored or logged in plain
  text. New and changed passwords must be at least 8 characters.
- **The first account** is created on first launch and is an admin. After
  that, setup is closed (`/api/auth/setup` refuses once any account exists).
- **Invites** (Settings → Users, admins only) are one-time links: valid 7 days,
  single use, revocable. Only a SHA-256 hash of the token is stored; the link
  itself is shown once to the admin who made it.
- **Password reset links** are made by an admin for a specific account. They
  are valid 24 hours and single use, and a newer link cancels older ones.
- **Forgotten password with no other admin:** run
  `scripts/reset_password.py` on the Mac mini. This requires access to that
  machine and its `.env`, which is the proof it's you.
- **Admin guardrails:** admins can't deactivate or demote themselves, and there
  is always at least one active admin.
- **Everyone with an account sees the same books.** There are no per-user
  permissions yet (see Known gaps).

Tested in `tests/test_accounts.py`.

## 4. Sessions

- The session cookie is signed with `SECRET_KEY` (itsdangerous), so it can't be
  forged or edited. It is `HttpOnly` (page scripts can't read it) and
  `SameSite=Lax`, and it expires after 7 days.
- It carries a fingerprint of the account's password hash. **Changing or
  resetting a password signs that account out on every other device**, and
  deactivating an account signs it out immediately.
- Changing `SECRET_KEY` signs everyone out.

## 5. Request protection

- **Every API endpoint requires a signed-in user** except: sign-in, sign-out,
  first-time setup, the one-time invite/reset links, `/healthz`, and the web
  app's own files. A test enumerates every endpoint and fails if any other one
  is reachable without signing in
  (`tests/test_security.py::test_every_other_endpoint_requires_sign_in`).
- **Admin-only actions** (managing users, invites, reset links) check the admin
  role on the server, not just in the web page.
- **Cross-site request forgery:** state-changing requests whose `Origin` is a
  different site are rejected with 403 (`CSRF_PROTECT`, on by default), on top
  of the `SameSite=Lax` cookie (`tests/test_security.py`).
- **Excel import** limits uploads to 10 MB and shows every change for approval
  before writing anything.

## 6. What leaves the machine

By default, nothing. Data only leaves when you turn on one of these:

| Service | When | What is sent |
|---------|------|--------------|
| Plaid | Only if you connect a bank (needs `PLAID_CLIENT_ID`/`PLAID_SECRET`) | Requests for your accounts and transactions |
| Anthropic (Claude) | Only if you pick Claude in Settings → AI provider | Statement text, budget files and summaries sent for parsing and insights |
| Ollama | Default AI provider; runs on the Mac itself | Nothing leaves the machine |
| GitHub | When you check for or install updates | A `git fetch`/`git pull` of this repository; no data from the app |

There is no analytics or telemetry.

## 7. How code gets to the Mac mini

1. **Changes go through pull requests** on GitHub. Each one runs CI
   (`.github/workflows/ci.yml`): the backend test suite (including the
   security tests above) plus the frontend lint and production build. A
   change is merged into `main` only after CI passes.
2. **The Mac mini only installs from `main`.** `deploy.sh` (also used by
   Settings → Update now) runs `git pull origin main` over HTTPS from GitHub.
3. **Pinned dependencies.** Python packages are pinned to exact versions in
   `requirements.txt`, and frontend packages are locked by
   `frontend/package-lock.json`.
4. **A failed update doesn't half-deploy.** `deploy.sh` stops at the first
   error, prints `==> FAILED at line N`, and does not restart, so the previous
   version keeps running. The Settings page shows the failure.
5. **You can see what's running.** The bottom-left corner shows the running
   version. Settings shows whether files on the Mac differ from GitHub
   ("modified locally") and whether an update needs a restart.

**Protect the GitHub account.** Anyone who can push to `main` controls what
the Mac mini runs on its next update. Use two-factor authentication on GitHub,
and consider branch protection on `main` that requires CI to pass.

## Known gaps

Being upfront about what isn't covered yet:

- **Outdated dependencies with published vulnerabilities** (audited
  2026-11-23 with `pip-audit` and `npm audit`):
  - Python: `starlette` (the web framework under FastAPI), `python-multipart`
    (file uploads), `pypdf` and `pdfminer.six` (PDF statement parsing),
    `requests`, `python-dotenv`, and `pytest` (tests only).
  - Frontend: `react-router` (moderate). The rest are build-time tools that
    don't ship in the app.

  Only signed-in users on your network can reach the affected code, which
  limits the risk, but these should be upgraded and a dependency audit added
  to CI.
- **No sign-in rate limiting or lockout.** Repeated password guesses aren't
  slowed down. Keeping the app off the open internet (Tailscale only) is the
  main defense; use strong passwords.
- **Plain HTTP on the home network** unless you restrict the app to Tailscale
  as described above.
- **No per-user permissions:** every account can see and edit everything.
- **Plaid tokens** rely on the database encryption only.
- **API documentation** at `/docs` is visible without signing in. It describes
  the endpoints but returns no data; every data endpoint still requires
  sign-in.

## Checklist for a new install

- [ ] Strong random `DB_PASSPHRASE` and `SECRET_KEY` in `.env`
      (`python3 -c "import secrets; print(secrets.token_hex(32))"`), saved in a
      password manager
- [ ] `.env` not committed (`git status` shows it as ignored)
- [ ] No router port forwarding to port 8000
- [ ] Reach it through Tailscale; optionally bind to `127.0.0.1` and use
      `tailscale serve`
- [ ] `COOKIE_SECURE=true` if served over HTTPS
- [ ] Two-factor authentication on the GitHub account that owns the repo
- [ ] Download a backup from Settings → Backup and store it privately
