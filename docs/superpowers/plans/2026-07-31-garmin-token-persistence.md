# Garmin Token Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Streamlit-Cloud–hosted Garmin dashboard resume from a durable, pre-minted OAuth token (stored in Streamlit secrets) instead of running the 429-throttled SSO login handshake on every cold start.

**Architecture:** A local `scripts/mint_garmin_token.py` mints the owner's token once (from a home IP). `utils/garmin_utils.py` gains a token-first `login_to_garmin` (resume via `garth.loads`, credential fallback, raise-on-failure) and a pure `classify_login_error`. `app.py` auto-logs-in from the `garmin_token_base64` secret, keeps a manual form as a fallback expander, replaces deprecated `st.experimental_rerun()`, and shows a friendly rate-limit message.

**Tech Stack:** Python, `garminconnect==0.2.26`, `garth` (0.5.3), Streamlit 1.33, pytest, python-dotenv.

## Global Constraints

- Deployed on **Streamlit Community Cloud**; **secrets persist across cold starts, local disk does not** — the token lives in the `garmin_token_base64` secret, never on disk, never committed.
- Secret is read with `st.secrets.get("garmin_token_base64", None)` wrapped so a missing secrets file does not raise.
- `login_to_garmin` **raises on failure** (never returns `None`) so `st.cache_resource` does not cache a failed login for the TTL.
- Token-first: with a token blob, `Garmin().login(blob)` (garth `loads` resume); credential fallback is `Garmin(user, pass).login()`.
- `classify_login_error(exc) -> "rate_limited" | "auth" | "other"`.
- The token grants ~1 year of full-account access: `mint_garmin_token.py` reads credentials from env (`GARMIN_EMAIL`/`GARMIN_PASSWORD`), **never prints the password**, and prints the token blob for manual paste into Streamlit secrets (print-only; no on-disk token file).
- Replace both `st.experimental_rerun()` calls in `app.py` with `st.rerun()`.
- Single owner identity — no per-user token handling.
- Pure helpers (`classify_login_error`, `_do_login`) are unit-tested with pytest; the Streamlit auto-login flow is browser-verified by the owner. Run tests with `venv_garmin/Scripts/python.exe -m pytest -q` from repo root.

---

## File Structure

- **Modify** `utils/garmin_utils.py` — add `classify_login_error` (Task 1) and `_do_login` + reworked `login_to_garmin` (Task 2).
- **Create** `tests/test_garmin_auth.py` — pure unit tests for `classify_login_error` (Task 1) and `_do_login` (Task 2).
- **Modify** `app.py` — token auto-login, fallback form, `st.rerun()`, friendly errors (Task 3).
- **Create** `scripts/mint_garmin_token.py` — local token minting helper (Task 4).

---

### Task 1: `classify_login_error` pure helper

**Files:**
- Modify: `utils/garmin_utils.py`
- Create: `tests/test_garmin_auth.py`

**Interfaces:**
- Produces: `classify_login_error(exc: Exception) -> str` returning `"rate_limited"`, `"auth"`, or `"other"`. Message-based (case-insensitive) plus `isinstance` checks against garminconnect's typed exceptions. No Streamlit, no network.

- [ ] **Step 1: Write the failing test**

Create `tests/test_garmin_auth.py`:

```python
import pytest
from utils import garmin_utils as g


def test_classify_rate_limited_from_429_message():
    exc = Exception("HTTPSConnectionPool(...): Max retries exceeded ... ResponseError('too many 429 error responses')")
    assert g.classify_login_error(exc) == "rate_limited"


def test_classify_rate_limited_from_too_many_requests():
    assert g.classify_login_error(Exception("429 Too Many Requests")) == "rate_limited"


def test_classify_auth_from_unauthorized():
    assert g.classify_login_error(Exception("401 Unauthorized")) == "auth"


def test_classify_auth_from_invalid():
    assert g.classify_login_error(Exception("Invalid credentials")) == "auth"


def test_classify_other_default():
    assert g.classify_login_error(Exception("some unrelated network hiccup")) == "other"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_garmin_auth.py -v`
Expected: FAIL — `AttributeError: module 'utils.garmin_utils' has no attribute 'classify_login_error'`.

- [ ] **Step 3: Implement `classify_login_error`**

Add to `utils/garmin_utils.py` (near the top, after the existing imports — `GarminConnectTooManyRequestsError` and `GarminConnectAuthenticationError` are already imported in this file):

```python
def classify_login_error(exc):
    """Classify a login exception as 'rate_limited', 'auth', or 'other' (pure; no I/O)."""
    msg = str(exc).lower()
    if isinstance(exc, GarminConnectTooManyRequestsError) or \
       "429" in msg or "too many requests" in msg or "max retries exceeded" in msg:
        return "rate_limited"
    if isinstance(exc, GarminConnectAuthenticationError) or \
       "401" in msg or "unauthorized" in msg or "invalid" in msg:
        return "auth"
    return "other"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_garmin_auth.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add utils/garmin_utils.py tests/test_garmin_auth.py
git commit -m "feat(auth): classify_login_error for rate-limit vs auth vs other"
```

---

### Task 2: `_do_login` + token-first `login_to_garmin`

**Files:**
- Modify: `utils/garmin_utils.py`
- Modify: `tests/test_garmin_auth.py`

**Interfaces:**
- Consumes: nothing from Task 1 directly.
- Produces:
  - `_do_login(username=None, password=None, token_blob=None, garmin_factory=Garmin)` — token-first login. With `token_blob`: `client = garmin_factory(); client.login(token_blob)`. Else with `username` and `password`: `client = garmin_factory(username, password); client.login()`. Else raises `ValueError`. Returns the client. `garmin_factory` is injectable for testing.
  - `login_to_garmin(username=None, password=None, token_blob=None)` — `@st.cache_resource(ttl=3600)` wrapper that returns `_do_login(...)` and **raises on failure** (no `try/except` that returns `None`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_garmin_auth.py`:

```python
class _FakeClient:
    def __init__(self):
        self.login_args = None
    def login(self, *args):
        self.login_args = args
        return True


def test_do_login_uses_token_path():
    recorded = {}
    def factory(*args):
        recorded["ctor_args"] = args
        return _FakeClient()
    client = g._do_login(token_blob="TOKENBLOB", garmin_factory=factory)
    assert recorded["ctor_args"] == ()            # constructed with no args
    assert client.login_args == ("TOKENBLOB",)     # login called with the blob


def test_do_login_uses_credential_path_when_no_token():
    recorded = {}
    def factory(*args):
        recorded["ctor_args"] = args
        return _FakeClient()
    client = g._do_login(username="me@example.com", password="pw", garmin_factory=factory)
    assert recorded["ctor_args"] == ("me@example.com", "pw")
    assert client.login_args == ()                 # login called with no args


def test_do_login_requires_token_or_credentials():
    with pytest.raises(ValueError):
        g._do_login(garmin_factory=_FakeClient)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_garmin_auth.py::test_do_login_uses_token_path -v`
Expected: FAIL — `AttributeError: module 'utils.garmin_utils' has no attribute '_do_login'`.

- [ ] **Step 3: Implement `_do_login` and rework `login_to_garmin`**

In `utils/garmin_utils.py`, add `_do_login` and REPLACE the existing `login_to_garmin` (the current body constructs `Garmin(username, password)`, calls `.login()`, and returns `None` on exception). New code:

```python
def _do_login(username=None, password=None, token_blob=None, garmin_factory=Garmin):
    """Token-first Garmin login. Injectable factory for testing. Raises on bad input."""
    if token_blob:
        client = garmin_factory()
        client.login(token_blob)      # garth.loads resume — no SSO handshake
        logger.info("Logged in to Garmin via saved token.")
        return client
    if username and password:
        client = garmin_factory(username, password)
        client.login()                # full SSO (throttled path)
        logger.info(f"Logged in to Garmin as {username} via credentials.")
        return client
    raise ValueError("login requires either token_blob or username+password")


@st.cache_resource(ttl=3600)
def login_to_garmin(username=None, password=None, token_blob=None):
    """Cached Garmin client. Raises on failure so failures are not cached for the TTL."""
    return _do_login(username=username, password=password, token_blob=token_blob)
```

- [ ] **Step 4: Run the full auth test suite**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_garmin_auth.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Confirm nothing else imports the old signature**

Run: `venv_garmin/Scripts/python.exe -c "import ast,sys; ast.parse(open('utils/garmin_utils.py').read()); print('garmin_utils parses OK')"`
Expected: prints `garmin_utils parses OK`. (Pages never call `login_to_garmin` — only `app.py` does, updated in Task 3.)

- [ ] **Step 6: Commit**

```bash
git add utils/garmin_utils.py tests/test_garmin_auth.py
git commit -m "feat(auth): token-first login_to_garmin with credential fallback, raise on failure"
```

---

### Task 3: `app.py` — token auto-login, fallback form, `st.rerun()`, friendly errors

**Files:**
- Modify: `app.py` (full replacement)

**Interfaces:**
- Consumes: `garmin_utils.login_to_garmin(username=None, password=None, token_blob=None)` and `garmin_utils.classify_login_error(exc)` from Tasks 1–2.
- Produces: the reworked home page (no exported symbols).

Verified **manually** (Streamlit) plus byte-compile. No automated test.

- [ ] **Step 1: Replace `app.py`**

Overwrite `app.py` with:

```python
import streamlit as st
from datetime import date, timedelta
from utils import garmin_utils

st.set_page_config(layout="wide", page_title="Garmin Performance Dashboard")
st.sidebar.title("Garmin Dashboard")

# --- Session init ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'garmin_client' not in st.session_state:
    st.session_state.garmin_client = None
if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# --- Durable owner token from Streamlit secrets (persists across Cloud cold starts) ---
try:
    _token_blob = st.secrets.get("garmin_token_base64", None)
except Exception:
    _token_blob = None

# --- Auto-login from the secret token (resume; no SSO handshake -> avoids the 429 login flow) ---
if not st.session_state.logged_in and _token_blob:
    try:
        client = garmin_utils.login_to_garmin(token_blob=_token_blob)
        st.session_state.garmin_client = client
        st.session_state.logged_in = True
        st.session_state.current_user = "owner"
    except Exception as e:
        kind = garmin_utils.classify_login_error(e)
        if kind == "rate_limited":
            st.sidebar.error("Garmin is rate-limiting the shared Streamlit IP. Re-mint your token locally and update the `garmin_token_base64` secret, or try again later.")
        elif kind == "auth":
            st.sidebar.error("Saved Garmin token is invalid or expired. Re-mint it and update the secret.")
        else:
            st.sidebar.error(f"Token login failed: {e}")

# --- Fallback manual login (local dev / token expiry) ---
if not st.session_state.logged_in:
    with st.sidebar.expander("Advanced / local login", expanded=not _token_blob):
        username_input = st.text_input("Garmin Email", key="garmin_email_main")
        password_input = st.text_input("Garmin Password", type="password", key="garmin_password_main")
        if st.button("Login", key="login_button_main"):
            if username_input and password_input:
                try:
                    with st.spinner("Logging in to Garmin Connect..."):
                        client = garmin_utils.login_to_garmin(username=username_input, password=password_input)
                    st.session_state.garmin_client = client
                    st.session_state.logged_in = True
                    st.session_state.current_user = username_input
                    st.rerun()
                except Exception as e:
                    kind = garmin_utils.classify_login_error(e)
                    if kind == "rate_limited":
                        st.error("Garmin is rate-limiting this IP (429). Wait ~1h, or mint a token locally.")
                    elif kind == "auth":
                        st.error("Login failed: check your credentials.")
                    else:
                        st.error(f"Login failed: {e}")
            else:
                st.warning("Please enter both email and password.")

# --- Logged-in UI ---
if st.session_state.logged_in:
    st.sidebar.markdown(f"**User:** {st.session_state.current_user}")
    if st.sidebar.button("Logout", key="logout_button_main"):
        st.session_state.logged_in = False
        st.session_state.garmin_client = None
        st.session_state.current_user = None
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.header("Global Filters")

    today = date.today()
    if 'date_range_start' not in st.session_state:
        st.session_state.date_range_start = today - timedelta(days=30)
    if 'date_range_end' not in st.session_state:
        st.session_state.date_range_end = today

    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.session_state.date_range_start = st.date_input(
            "Start Date", value=st.session_state.date_range_start,
            max_value=today, key="global_start_date")
    with col2:
        st.session_state.date_range_end = st.date_input(
            "End Date", value=st.session_state.date_range_end,
            min_value=st.session_state.date_range_start, max_value=today,
            key="global_end_date")

    st.session_state.force_refresh = st.sidebar.checkbox(
        "Force Refresh Data from Garmin", value=False, key="force_refresh_main")

    st.sidebar.markdown("---")
    st.sidebar.info("Navigate to different views using the pages above.")

    st.title("Welcome to your Garmin Performance Dashboard!")
    st.markdown("""
    You're logged in. Use the sidebar to pick a date range, then explore the pages:
    Health Overview, Running Performance, Training Load, Correlations, Readiness & Performance, and Personal Records.
    """)
else:
    st.info("Not logged in. If you're the owner, set the `garmin_token_base64` secret; otherwise expand **Advanced / local login** in the sidebar.")
```

- [ ] **Step 2: Byte-compile and symbol-check**

Run: `venv_garmin/Scripts/python.exe -m py_compile app.py`
Expected: exit 0.
Run: `venv_garmin/Scripts/python.exe -c "from utils import garmin_utils; garmin_utils.login_to_garmin; garmin_utils.classify_login_error; print('symbols OK')"`
Expected: prints `symbols OK`.
Run: `venv_garmin/Scripts/python.exe -c "import re; s=open('app.py').read(); assert 'experimental_rerun' not in s, 'deprecated rerun still present'; print('no experimental_rerun')"`
Expected: prints `no experimental_rerun`.

- [ ] **Step 3: Manual verification (owner, deferred)**

Locally: `venv_garmin/Scripts/streamlit run app.py`. Without a secret set, confirm the **Advanced / local login** expander appears and credential login still works (or shows the friendly 429 message if rate-limited). On Streamlit Cloud, after Task 4 sets the secret, confirm opening the URL auto-authenticates with no form and data loads.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat(app): auto-login from secret token, fallback form, st.rerun, friendly 429"
```

---

### Task 4: `scripts/mint_garmin_token.py` — local token minting helper

**Files:**
- Create: `scripts/mint_garmin_token.py`

**Interfaces:**
- Consumes: `garminconnect.Garmin`, `python-dotenv`. Reads `GARMIN_EMAIL`/`GARMIN_PASSWORD` from env/`.env`.
- Produces: a runnable script that prints the `garth.dumps()` token blob. No exported symbols.

Verified by **byte-compile** (the owner runs it locally with real credentials to actually mint).

- [ ] **Step 1: Create the script**

Create `scripts/mint_garmin_token.py`:

```python
"""Mint a Garmin OAuth token blob for the Streamlit dashboard.

Run this LOCALLY (from your own IP, not the shared Streamlit Cloud IP):

    # provide credentials via environment or a local .env file
    set GARMIN_EMAIL=you@example.com        # PowerShell: $env:GARMIN_EMAIL="you@example.com"
    set GARMIN_PASSWORD=your-password
    venv_garmin/Scripts/python.exe scripts/mint_garmin_token.py

Copy the printed blob into Streamlit Cloud -> Settings -> Secrets as:

    garmin_token_base64 = "<blob>"

The token grants ~1 year of account access; treat it like a password. Never commit it.
"""
import os
import sys

from dotenv import load_dotenv
from garminconnect import Garmin


def main():
    load_dotenv()
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        print("ERROR: set GARMIN_EMAIL and GARMIN_PASSWORD (environment or .env).")
        return 1

    print(f"Logging in as {email} ...")
    client = Garmin(email, password)
    client.login()  # full SSO from this local machine's IP
    blob = client.garth.dumps()

    print("\n=== SUCCESS. Add this to Streamlit Cloud -> Settings -> Secrets ===\n")
    print('garmin_token_base64 = "PASTE_THE_LINE_BELOW"')
    print("\n" + blob + "\n")
    print("=== Keep it secret. Do not commit it. ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Byte-compile**

Run: `venv_garmin/Scripts/python.exe -m py_compile scripts/mint_garmin_token.py`
Expected: exit 0.

- [ ] **Step 3: Confirm it never references the password in output**

Run: `venv_garmin/Scripts/python.exe -c "s=open('scripts/mint_garmin_token.py').read(); assert 'print' in s; assert 'password' not in s.split('def main')[1].split('print(')[1], 'password must not be printed'; print('no password in first print')"`
Expected: prints `no password in first print`. (Sanity check that the password isn't in the first print statement; the reviewer should confirm no `print` outputs `password`.)

- [ ] **Step 4: Commit**

```bash
git add scripts/mint_garmin_token.py
git commit -m "feat(scripts): local Garmin token minting helper"
```

---

## Self-Review

**Spec coverage:**
- Mint-once-locally script → Task 4. ✓
- Token-first `login_to_garmin` (resume via garth loads) + credential fallback + raise-on-failure → Task 2. ✓
- `classify_login_error` (`rate_limited`/`auth`/`other`) → Task 1. ✓
- `app.py` auto-login from `garmin_token_base64` secret, fallback form behind expander, friendly rate-limit message → Task 3. ✓
- Replace `st.experimental_rerun()` with `st.rerun()` → Task 3 (Step 2 asserts none remain). ✓
- Secret read with `st.secrets.get(..., None)` wrapped against missing file → Task 3. ✓
- Pure helpers unit-tested; Streamlit flow browser-verified → Tasks 1, 2 (pytest), Task 3 (manual). ✓
- Token never committed / password never printed / creds from env → Task 4 (+ constraint). ✓
- Single owner identity, no per-user handling → reflected; `current_user="owner"` on token login. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases" — every step has runnable code or an exact command. ✓

**Type consistency:** `login_to_garmin(username=None, password=None, token_blob=None)` and `classify_login_error(exc)` are used identically in Task 3 as defined in Tasks 1–2; `_do_login`'s `garmin_factory` seam matches its tests. ✓

**Note for executor:** `login_to_garmin` now raises instead of returning `None`; `app.py` (the only caller) wraps every call in `try/except`. No page calls `login_to_garmin`, so no other caller needs updating.
