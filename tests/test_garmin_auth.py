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
