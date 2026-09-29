from app.core.logging import redact


def test_redacts_sensitive_keys() -> None:
    out = redact(None, "info", {"event": "x", "text": "book words", "Password": "p", "ok": 1})
    assert out["text"] == "[REDACTED]"
    assert out["Password"] == "[REDACTED]"
    assert out["ok"] == 1
