import sys

import pytest

from weather_platform.acquisition.cli import EX_CONFIG, run


@pytest.mark.contract
def test_acquisition_cli_reports_contract_only_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["weather-platform-acquisition"])
    assert run() == 0
    assert "live provider transport is disabled" in capsys.readouterr().out


@pytest.mark.contract
def test_acquisition_cli_fails_closed_when_live_transport_is_required(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["weather-platform-acquisition", "--require-live-transport"],
    )
    assert run() == EX_CONFIG
    assert "not enabled" in capsys.readouterr().err
