"""Tests for run-time credential prompting (PROJECT_SPEC.md section 11)."""

from __future__ import annotations

import pytest

from nettopo.ingest import credentials as credentials_module
from nettopo.ingest.credentials import CredentialError, Credentials, prompt_credentials


@pytest.fixture
def tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(credentials_module.sys.stdin, "isatty", lambda: True)


def _answer_prompts(monkeypatch: pytest.MonkeyPatch, *secrets: str) -> None:
    answers = iter(secrets)
    monkeypatch.setattr(credentials_module.getpass, "getpass", lambda _prompt: next(answers))


def test_secrets_never_appear_in_the_repr() -> None:
    """A `Credentials` logged at DEBUG -- directly or inside another object -- must not leak."""
    rendered = repr(Credentials(username="netops", password="hunter2", enable_password="en4ble"))

    assert "hunter2" not in rendered
    assert "en4ble" not in rendered
    assert "netops" in rendered


def test_an_explicit_user_skips_the_username_prompt(
    monkeypatch: pytest.MonkeyPatch, tty: None
) -> None:
    _answer_prompts(monkeypatch, "pw", "en")
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: pytest.fail("username must not be asked for")
    )

    assert prompt_credentials(username="netops").username == "netops"


def test_the_os_login_is_the_default_username(monkeypatch: pytest.MonkeyPatch, tty: None) -> None:
    _answer_prompts(monkeypatch, "pw", "en")
    monkeypatch.setattr(credentials_module.getpass, "getuser", lambda: "israel")
    monkeypatch.setattr("builtins.input", lambda _prompt: "")  # accept the default

    assert prompt_credentials().username == "israel"


def test_an_empty_enable_password_means_the_network_does_not_use_enable(
    monkeypatch: pytest.MonkeyPatch, tty: None
) -> None:
    _answer_prompts(monkeypatch, "pw", "")

    assert prompt_credentials(username="netops").enable_password is None


def test_without_a_terminal_it_refuses_rather_than_echoing_the_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`getpass` falls back to an echoing prompt with no TTY; that is worse than failing."""
    monkeypatch.setattr(credentials_module.sys.stdin, "isatty", lambda: False)

    with pytest.raises(CredentialError, match="needs a terminal"):
        prompt_credentials(username="netops")
