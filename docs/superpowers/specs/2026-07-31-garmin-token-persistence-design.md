# Garmin Token Persistence (Design)

**Date:** 2026-07-31
**Status:** Approved design, ready for implementation planning

## Problem

The app is deployed on **Streamlit Community Cloud** (`https://garmin-dashboard.streamlit.app/`)
so it can be used from a phone. Login now fails with:

```
HTTPSConnectionPool(host='connectapi.garmin.com', ...): Max retries exceeded with url:
/oauth-service/oauth/preauthorized?...  (Caused by ResponseError('too many 429 error responses'))
```

HTTP 429 = rate-limited. The SSO ticket step succeeds (credentials + no MFA wall), but the
follow-up OAuth token exchange is throttled. Root causes specific to the hosting platform:

- **Shared egress IP:** all Streamlit Community Cloud apps share outbound IPs, and Garmin
  rate-limits by IP. The throttling reflects aggregate traffic on that IP, not just this app.
- **Ephemeral filesystem:** Streamlit Cloud wipes runtime-written files on every cold
  start/reboot/redeploy, so every cold start forces a fresh, multi-step SSO login — the exact
  flow being 429'd. Writing tokens to local disk (`data/…`) does **not** survive.

The app's login code was **not** changed by prior work (verified: `app.py` and
`utils/garmin_utils.py` are byte-identical to before SP2). This is the pre-existing
unofficial-API fragility surfacing.

## Goal

Restore reliable, phone-accessible login on the existing Streamlit Cloud URL by **eliminating
the SSO login handshake at runtime** — resume from a pre-minted, durable token instead.

## Key facts (verified against installed libraries)

- `garminconnect==0.2.26`: `Garmin.login(tokenstore=None)`. With a `tokenstore` it calls
  `garth.loads(blob)` (string >512 chars) or `garth.load(dir)` to **resume** — no SSO. Without,
  it does a full `garth.login(user, pass)` (the throttled path).
- `garth` Client exposes `dump`/`dumps` (save) and `load`/`loads` (resume).
- The saved **OAuth1 token is valid ~1 year**; garth auto-refreshes the short-lived OAuth2 from
  it, so a resumed session keeps working without re-login until OAuth1 expires or the Garmin
  password changes.
- `Garmin(email=None, password=None, ...)` constructs with no args (for the resume path).
- **Streamlit secrets persist** across cold starts on Streamlit Cloud (unlike the disk).
- `.streamlit/secrets.toml` is already in `.gitignore`.

## Usage model

"Basically my personal dashboard" — one owner identity; the few other viewers just look at the
owner's data. So a **single durable owner token** is sufficient. No per-user token handling.

## Solution

Mint the owner's Garmin token **once, locally** (from the owner's home IP, so the mint never
touches the shared/throttled Streamlit IP), store the token blob in **Streamlit Cloud secrets**,
and have the hosted app **resume from it** — skipping the SSO handshake entirely. On the phone:
open the URL → already authenticated → data loads.

### Components

1. **`scripts/mint_garmin_token.py`** (new, run locally).
   - Reads `GARMIN_EMAIL` / `GARMIN_PASSWORD` from environment (or `.env` via the existing
     `python-dotenv` dependency). Never hardcode or print the password.
   - Performs a full `Garmin(email, password).login()` from the local machine.
   - Prints `client.garth.dumps()` (the base64 token blob) plus copy-paste instructions for the
     Streamlit Cloud secret. Optionally also writes it to a local gitignored file for convenience.
   - This is the ONLY place a full SSO login runs, and it is off the shared IP.

2. **`utils/garmin_utils.py` — `login_to_garmin` reworked to token-first** (keeps
   `@st.cache_resource(ttl=3600)`):
   - Signature becomes `login_to_garmin(username=None, password=None, token_blob=None)`.
   - **Token path:** if `token_blob` is provided, `g = Garmin(); g.login(token_blob)` (garth
     `loads` resume) → return client. No SSO.
   - **Credential fallback:** else if `username`+`password`, `Garmin(username, password).login()`
     → return client (local dev / re-mint scenarios).
   - **On failure, raise** (do not return `None`). `st.cache_resource` does not cache raised
     exceptions, so a failed login can be retried immediately rather than being cached for the
     TTL (fixes a latent bug in the current return-`None` behaviour).
   - A small **pure, testable helper** classifies exceptions:
     `classify_login_error(exc) -> "rate_limited" | "auth" | "other"` — `"rate_limited"` when the
     message/args indicate HTTP 429 or a urllib3 `MaxRetryError`/`RetryError` mentioning 429.
     This has no Streamlit/network dependency and is unit-tested.

3. **`app.py` — auto-login from the secret token, manual form as fallback:**
   - On load, read the token blob via `st.secrets.get("garmin_token_base64")`. If present and not
     yet logged in, call `login_to_garmin(token_blob=...)` and populate session state — no form
     interaction needed on the phone.
   - Keep the existing email/password form as a **fallback behind an expander** ("Advanced /
     local login") for local dev or token expiry.
   - Replace both deprecated `st.experimental_rerun()` calls with `st.rerun()` (in-path latent
     breakage on any Streamlit upgrade).
   - On a caught login failure, use `classify_login_error` to show a clear message: for
     `"rate_limited"`, *"Garmin is rate-limiting the shared Streamlit IP. Re-mint your token
     locally and update the secret, or try again later."*; for `"auth"`, an invalid/expired-token
     or bad-credentials message; otherwise a generic failure with the error text.

### Secret

- Streamlit Cloud secret key: `garmin_token_base64` (top-level), value = the `garth.dumps()`
  blob. Accessed with `st.secrets.get("garmin_token_base64")` so a missing secret degrades to the
  fallback form rather than raising.

## Data flow

1. (Once, local) `mint_garmin_token.py` → SSO login from home IP → prints token blob.
2. (Once) Owner pastes the blob into Streamlit Cloud → Settings → Secrets as `garmin_token_base64`.
3. (Each visit) `app.py` reads the secret → `login_to_garmin(token_blob=…)` → `garth.loads`
   resume → cached client → pages fetch data as today. No SSO handshake.

## Error handling

- Token resume failure (expired/invalid/revoked) → raise → `app.py` shows the auth message and
  reveals the fallback form; owner re-mints and updates the secret.
- 429 / `MaxRetryError` → `classify_login_error` → rate-limit message (no raw traceback).
- Missing secret → no raise; fallback form shown.

## Testing

- `tests/test_garmin_auth.py` unit-tests the pure logic only (no network, no Streamlit):
  - `classify_login_error` returns `"rate_limited"` for a fabricated 429/`MaxRetryError`-style
    exception, `"auth"` for an auth-style error, `"other"` otherwise.
  - Any additional pure helper (e.g. selecting token vs credential path) is tested with fakes.
- garth/garminconnect network calls are verified manually via `mint_garmin_token.py` and, per
  repo convention, the Streamlit auto-login flow is browser-verified by the owner.

## Security

- The token grants ~1 year of full account access. It lives only in Streamlit Cloud secrets
  (already gitignored) and, if the mint script writes a local copy, in a gitignored file.
- The mint script reads credentials from env; it never prints or commits the password.
- Revocation: changing the Garmin password invalidates the token; re-mint to restore.

## Out of scope (YAGNI)

- Per-user token handling / multi-tenant auth (usage is single-owner).
- Rehosting off Streamlit Community Cloud (kept as the documented durable fallback if the shared
  IP proves hard-blocked — see Residual risk).
- Reworking the per-day fetch loops / caching (separate concern).

## Residual risk (honest)

Resuming from a token removes the heavy multi-step SSO handshake, but garth's periodic OAuth2
refresh still makes occasional requests from the shared Streamlit IP. That is a small fraction of
the previous traffic, so 429s should become unlikely — but if Garmin has the shared egress IP
hard-blocked, even token refresh could be throttled. The only guaranteed fix in that case is
rehosting to a platform with a dedicated egress IP (and persistent disk, which then also makes
on-disk token storage viable). This spec targets the in-platform fix; rehosting remains the
escalation path.

## Success criteria

- With `garmin_token_base64` set in secrets, opening the app (including on a phone) authenticates
  without a login form and without triggering the SSO handshake; data loads.
- A rate-limit failure shows a clear message, not a raw traceback.
- No `st.experimental_rerun()` remains in `app.py`.
- Pure auth-helper logic is unit-tested; no secrets or tokens are committed.
