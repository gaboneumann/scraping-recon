"""
tests/conftest.py
Shared fixtures for the scraping_recon test suite.
"""
import pathlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from bs4 import BeautifulSoup

from models.schemas import ReconReport, TlsDimension

FIXTURES_HTML = pathlib.Path(__file__).parent / "fixtures" / "html"


@pytest.fixture
def html_fixture():
    """Return a callable that reads tests/fixtures/html/{name}.html as str."""
    def _load(name: str) -> str:
        return (FIXTURES_HTML / f"{name}.html").read_text(encoding="utf-8")
    return _load


@pytest.fixture
def soup_fixture():
    """Return a callable that parses html string into BeautifulSoup."""
    def _parse(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")
    return _parse


@pytest.fixture
def respx_mock():
    """Function-scoped respx router — all unmocked requests raise."""
    import respx
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
def make_report():
    """
    Factory that builds a ReconReport with all module fields None-defaulted.
    Required fields: url, timestamp, scan_duration_ms, modules_status.
    """
    def _factory(**kwargs) -> ReconReport:
        base = dict(
            url="https://example.com",
            timestamp=datetime.now(timezone.utc).isoformat(),
            scan_duration_ms=100,
            modules_status=[],
            legal=None,
            classifier=None,
            auth=None,
            api_detector=None,
            pagination=None,
            antibot=None,
            recommender=None,
        )
        base.update(kwargs)
        return ReconReport(**base)
    return _factory


@pytest.fixture
def mock_antibot_externals(monkeypatch):
    """
    Patch all external I/O in antibot and http utils:
    - modules.antibot.subprocess.run → raises FileNotFoundError
    - modules.antibot.run_tls_test  → TlsDimension stub
    - modules.antibot.asyncio.sleep → no-op coroutine
    - utils.http.asyncio.sleep      → no-op coroutine
    """
    _tls_stub = TlsDimension(score=0, sensitivity="NONE", client_results={})

    monkeypatch.setattr(
        "modules.antibot.subprocess.run",
        MagicMock(side_effect=FileNotFoundError("wafw00f not found")),
    )
    monkeypatch.setattr(
        "modules.antibot.run_tls_test",
        AsyncMock(return_value=_tls_stub),
    )
    monkeypatch.setattr(
        "modules.antibot.asyncio.sleep",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "utils.http.asyncio.sleep",
        AsyncMock(return_value=None),
    )
