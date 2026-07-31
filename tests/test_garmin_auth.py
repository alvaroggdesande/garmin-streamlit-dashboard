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
