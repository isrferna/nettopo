"""The collection failure policy (PROJECT_SPEC.md section 11).

Collection is serial and stops at the first error. The point of that is what it prevents:
a mistyped password presented to two hundred devices is an account lockout, and on a
TACACS-backed network it locks the operator out of everything. These tests therefore
assert on how many devices were *contacted*, because a policy about not doing something
cannot be checked by looking at what was produced.
"""

from __future__ import annotations

import pytest
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException
from tests.conftest import FakeConnection, FakeNetmiko

from nettopo.ingest.credentials import Credentials
from nettopo.ingest.live import LiveDataSource, Outcome

CREDENTIALS = Credentials(username="netops", password="secret", enable_password="enable")
NO_ENABLE_CREDENTIALS = Credentials(username="netops", password="secret", enable_password=None)

TEN_TARGETS = [f"10.0.0.{index}" for index in range(1, 11)]


@pytest.mark.parametrize(
    "error",
    [
        NetmikoAuthenticationException("authentication failed"),
        NetmikoTimeoutException("connection timed out"),
        OSError("no route to host"),
        RuntimeError("something unforeseen"),
    ],
)
def test_the_first_error_stops_the_run(fake_netmiko: FakeNetmiko, error: Exception) -> None:
    """Every kind of error ends the run -- only the enable case is exempt."""
    fake_netmiko.connect_errors["10.0.0.3"] = error

    result = LiveDataSource(TEN_TARGETS, CREDENTIALS).collect()

    # Three devices contacted, seven never touched: the assertion that matters.
    assert fake_netmiko.attempts == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
    assert [outcome.outcome for outcome in result.outcomes[:3]] == [
        Outcome.OK,
        Outcome.OK,
        Outcome.FAILED,
    ]
    assert all(outcome.outcome is Outcome.SKIPPED for outcome in result.outcomes[3:])
    assert not result.succeeded


def test_a_wrong_password_costs_exactly_one_authentication_attempt(
    fake_netmiko: FakeNetmiko,
) -> None:
    """The lockout protection, stated as the number it is meant to bound.

    A concurrent collector could not pass this: with several workers in flight, that many
    devices present the bad password before the first rejection is even seen.
    """
    for target in TEN_TARGETS:
        fake_netmiko.connect_errors[target] = NetmikoAuthenticationException("bad password")

    result = LiveDataSource(TEN_TARGETS, CREDENTIALS).collect()

    assert len(fake_netmiko.attempts) == 1
    assert result.counts_by_status()["skipped"] == 9


def test_a_rejected_enable_secret_stops_the_run_too(fake_netmiko: FakeNetmiko) -> None:
    """A wrong enable secret is a credential, and can feed the same lockout counter."""
    fake_netmiko.devices["10.0.0.1"] = FakeConnection(
        host="10.0.0.1",
        outputs=dict(fake_netmiko.default_outputs),
        privileged=False,
        enable_error=ValueError("Failed to enter enable mode"),
    )

    result = LiveDataSource(TEN_TARGETS, CREDENTIALS).collect()

    assert fake_netmiko.attempts == ["10.0.0.1"]
    assert result.outcomes[0].outcome is Outcome.FAILED


def test_a_device_needing_enable_without_one_is_skipped_and_the_run_continues(
    fake_netmiko: FakeNetmiko,
) -> None:
    """The single tolerated failure.

    It says nothing about the network's health -- only about what the operator typed at
    the prompt -- so it must not end a run the way an unreachable device does.
    """
    fake_netmiko.devices["10.0.0.2"] = FakeConnection(
        host="10.0.0.2", outputs=dict(fake_netmiko.default_outputs), privileged=False
    )

    result = LiveDataSource(TEN_TARGETS, NO_ENABLE_CREDENTIALS).collect()

    assert fake_netmiko.attempts == TEN_TARGETS  # every device was still contacted
    assert result.outcomes[1].outcome is Outcome.NO_ENABLE
    assert result.outcomes[1].capture is None  # nothing to write for it
    assert result.counts_by_status() == {"ok": 9, "no-enable": 1, "failed": 0, "skipped": 0}
    assert not result.succeeded  # tolerated, but still an incomplete capture set


def test_a_skipped_device_writes_no_capture(fake_netmiko: FakeNetmiko) -> None:
    """`on_capture` must not fire for a device that was never collected."""
    fake_netmiko.devices["10.0.0.1"] = FakeConnection(
        host="10.0.0.1", outputs=dict(fake_netmiko.default_outputs), privileged=False
    )
    written: list[str] = []

    LiveDataSource(["10.0.0.1"], NO_ENABLE_CREDENTIALS).collect(
        on_capture=lambda target, _capture: written.append(target)
    )

    assert written == []


def test_captures_reach_the_callback_before_a_later_device_fails(
    fake_netmiko: FakeNetmiko,
) -> None:
    """A run that dies at device 3 must keep what devices 1 and 2 already cost."""
    fake_netmiko.connect_errors["10.0.0.3"] = NetmikoTimeoutException("unreachable")
    written: list[str] = []

    LiveDataSource(TEN_TARGETS, CREDENTIALS).collect(
        on_capture=lambda target, _capture: written.append(target)
    )

    assert written == ["10.0.0.1", "10.0.0.2"]


def test_enable_required_is_caught_before_the_broad_handler(fake_netmiko: FakeNetmiko) -> None:
    """Asserted directly: the wrong ordering makes the one tolerated failure fatal.

    `EnableRequired` is an `Exception`, so a broad handler placed first would swallow it
    and end every run against a network whose devices ask for enable -- a regression that
    would look like "collection stopped on device 1" and nothing more.
    """
    for target in TEN_TARGETS:
        fake_netmiko.devices[target] = FakeConnection(
            host=target, outputs=dict(fake_netmiko.default_outputs), privileged=False
        )

    result = LiveDataSource(TEN_TARGETS, NO_ENABLE_CREDENTIALS).collect()

    assert all(outcome.outcome is Outcome.NO_ENABLE for outcome in result.outcomes)
    assert len(fake_netmiko.attempts) == len(TEN_TARGETS)


def test_a_failure_records_the_exception_type_for_the_report(fake_netmiko: FakeNetmiko) -> None:
    fake_netmiko.connect_errors["10.0.0.1"] = NetmikoTimeoutException("connection timed out")

    result = LiveDataSource(["10.0.0.1"], CREDENTIALS).collect()

    assert "NetmikoTimeoutException" in result.outcomes[0].detail
    assert "connection timed out" in result.outcomes[0].detail


def test_no_credential_ever_appears_in_a_failure_detail(fake_netmiko: FakeNetmiko) -> None:
    """Failure text is logged and written to the report, so it must carry no secrets."""
    fake_netmiko.connect_errors["10.0.0.1"] = NetmikoAuthenticationException(
        "Authentication to device failed"
    )

    result = LiveDataSource(["10.0.0.1"], CREDENTIALS).collect()

    assert "secret" not in result.outcomes[0].detail
    assert "enable" not in result.outcomes[0].detail
