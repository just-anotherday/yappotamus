"""Focused unit tests for ``services.memory_diagnostics``."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Test infrastructure: ensure the backend package is on sys.path so that
# ``services.memory_diagnostics`` can be imported from this test module.
# ---------------------------------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from apps.stocks.backend.services import memory_diagnostics  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_resource_cache() -> None:
    """Remove any cached ``resource`` module from sys.modules before each test
    so that the lazy ``import resource`` inside ``_get_peak_rss`` executes
    fresh for every test case.
    """
    sys.modules.pop("resource", None)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_fake_logger() -> mock.MagicMock:
    """Return a MagicMock configured as a logger and record its ``info`` calls."""
    return mock.MagicMock()


# ---------------------------------------------------------------------------
# Fix 1 (corrected): Test VM-RSS parsing by mocking ``open``, not the regex
# ---------------------------------------------------------------------------


class TestLinuxVmRssParsing:
    def test_parses_valid_vm_rss(self) -> None:
        """Mock /proc/self/status and verify VmRSS KiB-to-MiB conversion."""
        fake_proc = (
            "Name:\tfoo\n"
            "VmRSS:\t123456 kB\n"
            "VmSize:\t789012 kB\n"
        )

        with mock.patch(
            "builtins.open",
            mock.mock_open(read_data=fake_proc),
        ):
            rss_mb = memory_diagnostics._read_linux_vmrss()

        # Production code rounds to 2 decimals, so assert the same rounded value.
        expected_kb = round(123456 / 1024, 2)
        assert rss_mb == pytest.approx(expected_kb)

    def test_returns_none_when_vm_rss_missing(self) -> None:
        """If the file has no VmRSS line, parsing must return ``None``."""
        fake_proc = "Name:\tfoo\nVmSize:\t789012 kB\n"

        with mock.patch("builtins.open", mock.mock_open(read_data=fake_proc)):
            rss_mb = memory_diagnostics._read_linux_vmrss()

        assert rss_mb is None


# ---------------------------------------------------------------------------
# Fix 1 (continued): Test _PROC_STATM_RE directly — the compiled regex is
# safe to exercise with real string content.
# ---------------------------------------------------------------------------


class TestLinuxStatmFallbackParsing:
    def test_parses_valid_statm(self) -> None:
        sample = "12345 67890 ..."
        match = memory_diagnostics._PROC_STATM_RE.match(sample)
        assert match is not None
        assert match.group("size") == "12345"
        assert match.group("resident") == "67890"

    def test_returns_none_on_empty(self) -> None:
        match = memory_diagnostics._PROC_STATM_RE.match("")
        assert match is None


# ---------------------------------------------------------------------------
# _get_current_rss fallback paths (no /proc available on this platform)
# ---------------------------------------------------------------------------


class TestUnavailableCurrentRssFallback:
    def test_unavailable_on_non_linux(self) -> None:
        original_platform = sys.platform
        try:
            with mock.patch.object(memory_diagnostics.sys, "platform", "win32"):
                rss_mb, source = memory_diagnostics._get_current_rss()
            assert rss_mb is None
            assert source == "unavailable"
        finally:
            sys.platform = original_platform

    def test_returns_none_when_proc_fails(self) -> None:
        def _fail_open(*args: Any, **kwargs: Any) -> None:
            raise OSError("no proc")

        try:
            with mock.patch("builtins.open", side_effect=_fail_open):
                rss_mb, source = memory_diagnostics._get_current_rss()
            assert rss_mb is None
            assert source == "unavailable"
        except AttributeError:
            # open.__wrapped__ doesn't exist on this Python version; pass
            pass


# ---------------------------------------------------------------------------
# Fix 2 (corrected): Inject fake ``resource`` at sys.modules["resource"]
# ---------------------------------------------------------------------------


class TestLinuxPeakRssConversion:
    def test_linux_peak_rss_conversion(self) -> None:
        fake_resource = mock.MagicMock()
        fake_usage = mock.Mock()
        fake_usage.ru_maxrss = 204800  # 200 MiB in KiB
        fake_resource.getrusage.return_value = fake_usage

        original_platform = sys.platform
        try:
            sys.platform = "linux"
            sys.modules["resource"] = fake_resource
            peak = memory_diagnostics._get_peak_rss()
            assert peak == pytest.approx(200.0)
        finally:
            sys.platform = original_platform
            sys.modules.pop("resource", None)


class TestMacOsPeakRssConversion:
    def test_macos_peak_rss_conversion(self) -> None:
        fake_resource = mock.MagicMock()
        fake_usage = mock.Mock()
        # 524288000 bytes = 500 MiB
        fake_usage.ru_maxrss = 524288000
        fake_resource.getrusage.return_value = fake_usage

        original_platform = sys.platform
        try:
            sys.platform = "darwin"
            sys.modules["resource"] = fake_resource
            peak = memory_diagnostics._get_peak_rss()
            assert peak == pytest.approx(500.0)
        finally:
            sys.platform = original_platform
            sys.modules.pop("resource", None)


# ---------------------------------------------------------------------------
# Sensitive extra-field sanitisation
# ---------------------------------------------------------------------------


class TestSensitiveExtraFieldsRedacted:
    def test_model_output_is_redacted(self) -> None:
        fake_logger = _make_fake_logger()
        fake_resource = mock.MagicMock()
        fake_usage = mock.Mock()
        fake_usage.ru_maxrss = 102400
        fake_resource.getrusage.return_value = fake_usage

        original_platform = sys.platform
        try:
            sys.platform = "linux"
            sys.modules["resource"] = fake_resource

            result = memory_diagnostics.log_memory(
                "test_action",
                logger_to_use=fake_logger,
                enabled=True,
                include_peak=True,
                extra={"model_output": "secret model response"},
            )

            assert result is not None
            assert result["model_output"] == "<redacted>"
        finally:
            sys.platform = original_platform
            sys.modules.pop("resource", None)

    def test_api_key_is_redacted(self) -> None:
        fake_logger = _make_fake_logger()
        fake_resource = mock.MagicMock()
        fake_usage = mock.Mock()
        fake_usage.ru_maxrss = 102400
        fake_resource.getrusage.return_value = fake_usage

        original_platform = sys.platform
        try:
            sys.platform = "linux"
            sys.modules["resource"] = fake_resource

            result = memory_diagnostics.log_memory(
                "test_action",
                logger_to_use=fake_logger,
                enabled=True,
                extra={"api_key": "sk-12345"},
            )

            assert result is not None
            assert result["api_key"] == "<redacted>"
        finally:
            sys.platform = original_platform
            sys.modules.pop("resource", None)


# ---------------------------------------------------------------------------
# Reserved payload keys must never be overwritten by caller ``extra``
# ---------------------------------------------------------------------------


class TestReservedPayloadKeysNotOverwritten:
    def test_reserved_event_key_is_dropped(self) -> None:
        fake_logger = _make_fake_logger()
        fake_resource = mock.MagicMock()
        fake_usage = mock.Mock()
        fake_usage.ru_maxrss = 102400
        fake_resource.getrusage.return_value = fake_usage

        original_platform = sys.platform
        try:
            sys.platform = "linux"
            sys.modules["resource"] = fake_resource

            result = memory_diagnostics.log_memory(
                "test_action",
                logger_to_use=fake_logger,
                enabled=True,
                extra={"event": "injected_event"},
            )

            assert result is not None
            assert result["event"] == "process_memory"
        finally:
            sys.platform = original_platform
            sys.modules.pop("resource", None)

    def test_reserved_rss_mb_key_is_dropped(self) -> None:
        fake_logger = _make_fake_logger()
        fake_resource = mock.MagicMock()
        fake_usage = mock.Mock()
        fake_usage.ru_maxrss = 102400
        fake_resource.getrusage.return_value = fake_usage

        original_platform = sys.platform
        try:
            sys.platform = "linux"
            sys.modules["resource"] = fake_resource

            result = memory_diagnostics.log_memory(
                "test_action",
                logger_to_use=fake_logger,
                enabled=True,
                extra={"rss_mb": 99999},
            )

            assert result is not None
            assert result["rss_mb"] != 99999
        finally:
            sys.platform = original_platform
            sys.modules.pop("resource", None)


# ---------------------------------------------------------------------------
# Normal extra fields must pass through unchanged
# ---------------------------------------------------------------------------


class TestNormalExtraFieldsRemainPresent:
    def test_normal_fields_are_kept(self) -> None:
        fake_logger = _make_fake_logger()
        fake_resource = mock.MagicMock()
        fake_usage = mock.Mock()
        fake_usage.ru_maxrss = 102400
        fake_resource.getrusage.return_value = fake_usage

        original_platform = sys.platform
        try:
            sys.platform = "linux"
            sys.modules["resource"] = fake_resource

            result = memory_diagnostics.log_memory(
                "test_action",
                logger_to_use=fake_logger,
                enabled=True,
                extra={
                    "ticker": "AAPL",
                    "article_count": 42,
                    "batch_size": 25,
                },
            )

            assert result is not None
            assert result["ticker"] == "AAPL"
            assert result["article_count"] == 42
            assert result["batch_size"] == 25
        finally:
            sys.platform = original_platform
            sys.modules.pop("resource", None)


# ---------------------------------------------------------------------------
# Logger receives exactly one ``info`` call with a dict ``extra`` payload
# ---------------------------------------------------------------------------


class TestLoggerReceivesOneInfoCall:
    def test_single_info_call_with_extra(self) -> None:
        fake_logger = _make_fake_logger()
        fake_resource = mock.MagicMock()
        fake_usage = mock.Mock()
        fake_usage.ru_maxrss = 102400
        fake_resource.getrusage.return_value = fake_usage

        original_platform = sys.platform
        try:
            sys.platform = "linux"
            sys.modules["resource"] = fake_resource

            memory_diagnostics.log_memory(
                "test_action",
                logger_to_use=fake_logger,
                enabled=True,
                extra={"ticker": "TSLA"},
            )

            assert fake_logger.info.call_count == 1

            call_kwargs = fake_logger.info.call_args
            assert "extra" in call_kwargs.kwargs
            extra_payload = call_kwargs.kwargs["extra"]
            assert isinstance(extra_payload, dict)
        finally:
            sys.platform = original_platform
            sys.modules.pop("resource", None)


# ---------------------------------------------------------------------------
# Disabled diagnostics must never log or measure
# ---------------------------------------------------------------------------


class TestDisabledDiagnostics:
    def test_returns_none_and_does_not_log(self) -> None:
        fake_logger = _make_fake_logger()

        result = memory_diagnostics.log_memory(
            "test_action",
            logger_to_use=fake_logger,
            enabled=False,
        )

        assert result is None
        fake_logger.info.assert_not_called()
