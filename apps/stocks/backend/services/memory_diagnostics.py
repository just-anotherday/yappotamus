"""Lightweight process-memory diagnostics for structured application logging.

The helper is intentionally dependency-free and safe to call from production
code. On Linux, it reads the current resident set size from ``/proc``. Peak
resident memory is collected through the standard-library ``resource`` module
when available.

Memory values are reported in megabytes.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any

_VM_RSS_RE: re.Pattern[str] = re.compile(
    r"^VmRSS:\s+(?P<value>\d+)\s+kB$",
    re.MULTILINE,
)

_PROC_STATM_RE: re.Pattern[str] = re.compile(
    r"^(?P<size>\d+)\s+(?P<resident>\d+)"
)

_RESERVED_EXTRA_KEYS = {
    "event",
    "action",
    "rss_mb",
    "rss_source",
    "pid",
    "peak_rss_mb",
}

_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "credentials",
    "database_url",
    "db_url",
    "dsn",
    "connection_string",
    "connection_url",
    "model_input",
    "model_output",
    "password",
    "prompt",
    "request_body",
    "response_body",
    "secret",
    "token",
}

# Reserved keys that already appear individually in the plaintext message.
# They are intentionally omitted from the sorted context loop to avoid duplication.
_PLAINTEXT_RESERVED_KEYS = {
    "event",
    "action",
    "rss_mb",
    "rss_source",
    "peak_rss_mb",
    "pid",
}


def _bytes_to_mb(value: int | float) -> float:
    """Convert bytes to megabytes and round for readable logs."""
    return round(float(value) / (1024 * 1024), 2)


def _kilobytes_to_mb(value: int | float) -> float:
    """Convert kibibytes to megabytes and round for readable logs."""
    return round(float(value) / 1024, 2)


def _read_linux_vmrss() -> float | None:
    """Read the current Linux RSS from /proc/self/status."""
    try:
        with open("/proc/self/status", encoding="utf-8") as status_file:
            contents = status_file.read()
    except (OSError, UnicodeError):
        return None

    match = _VM_RSS_RE.search(contents)
    if match is None:
        return None

    try:
        rss_kb = int(match.group("value"))
    except (TypeError, ValueError):
        return None

    return _kilobytes_to_mb(rss_kb)


def _read_linux_statm() -> float | None:
    """Read the current Linux RSS from /proc/self/statm."""
    try:
        with open("/proc/self/statm", encoding="utf-8") as statm_file:
            contents = statm_file.read().strip()
    except (OSError, UnicodeError):
        return None

    match = _PROC_STATM_RE.match(contents)
    if match is None:
        return None

    try:
        resident_pages = int(match.group("resident"))
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (OSError, TypeError, ValueError):
        return None

    if resident_pages < 0 or page_size <= 0:
        return None

    return _bytes_to_mb(resident_pages * page_size)


def _get_current_rss() -> tuple[float | None, str]:
    """Return the current process RSS and the source used."""
    if sys.platform.startswith("linux"):
        rss_mb = _read_linux_vmrss()
        if rss_mb is not None:
            return rss_mb, "proc_status"

        rss_mb = _read_linux_statm()
        if rss_mb is not None:
            return rss_mb, "proc_statm"

    # Current RSS collection is currently supported only on Linux.
    return None, "unavailable"


def _get_peak_rss() -> float | None:
    """Return the process peak RSS in megabytes when supported."""
    try:
        import resource
    except ImportError:
        return None

    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        peak_rss = usage.ru_maxrss
    except (AttributeError, OSError, TypeError, ValueError):
        return None

    if peak_rss is None:
        return None

    try:
        peak_value = float(peak_rss)
    except (TypeError, ValueError):
        return None

    if peak_value < 0:
        return None

    # Linux reports ru_maxrss in KiB. macOS reports it in bytes.
    if sys.platform == "darwin":
        return _bytes_to_mb(peak_value)

    return _kilobytes_to_mb(peak_value)


def _is_sensitive_key(key: str) -> bool:
    """Return whether an extra-field name should be redacted."""
    normalized = key.casefold()

    if normalized in _SENSITIVE_KEYS:
        return True

    sensitive_fragments = (
        "api_key",
        "authorization",
        "cookie",
        "credential",
        "password",
        "secret",
        "token",
    )

    return any(fragment in normalized for fragment in sensitive_fragments)


def _sanitize_extra(extra: dict[str, Any] | None) -> dict[str, Any]:
    """Sanitize caller-provided fields before adding them to logs."""
    if not extra:
        return {}

    sanitized: dict[str, Any] = {}

    for raw_key, value in extra.items():
        key = str(raw_key)

        if key in _RESERVED_EXTRA_KEYS:
            continue

        if _is_sensitive_key(key):
            sanitized[key] = "<redacted>"
            continue

        # Redact URL-shaped string values even under innocent keys.
        if isinstance(value, str):
            lower_value = value.strip().lower()
            if (
                lower_value.startswith("postgresql://")
                or lower_value.startswith("postgresql+asyncpg://")
                or lower_value.startswith("http://")
                or lower_value.startswith("https://")
            ):
                sanitized[key] = "<redacted>"
                continue

        sanitized[key] = value

    return sanitized


def log_memory(
    action: str,
    *,
    logger_to_use: logging.Logger,
    enabled: bool = True,
    include_peak: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Log and return a structured process-memory diagnostic payload.

    Args:
        action:
            Short description of the lifecycle point being measured.
        logger_to_use:
            Logger that receives the structured memory event.
        enabled:
            When false, skip collection and logging entirely.
        include_peak:
            Include process peak RSS when the platform supports it.
        extra:
            Optional structured context. Reserved fields are ignored and
            sensitive values are redacted.

    Returns:
        The structured payload that was logged, or ``None`` when disabled.
    """
    if not enabled:
        return None

    rss_mb, rss_source = _get_current_rss()

    payload: dict[str, Any] = {
        "event": action,
        "action": action,
        "rss_mb": rss_mb,
        "rss_source": rss_source,
        "pid": os.getpid(),
    }

    if include_peak:
        payload["peak_rss_mb"] = _get_peak_rss()

    sanitized_context = _sanitize_extra(extra)
    payload.update(sanitized_context)

    # Build a plaintext message with essential diagnostic values so they are
    # visible in plain-text log consumers (Render, stdout, etc.) while keeping
    # the full structured ``extra`` payload for JSON log collectors.
    msg_parts: list[str] = ["Process memory diagnostic"]

    rss_str = f"rss_mb={rss_mb}" if rss_mb is not None else "rss_mb=unavailable"
    msg_parts.append(rss_str)

    peak_value = payload.get("peak_rss_mb")
    peak_str = f"peak_rss_mb={peak_value}" if peak_value is not None else "peak_rss_mb=unavailable"
    msg_parts.append(peak_str)

    msg_parts.append(f"pid={os.getpid()}")

    event_value = payload.get("event", "process_memory")
    msg_parts.append(f"event={event_value}")

    # Append safe scalar context fields in deterministic (sorted) order,
    # excluding reserved keys that already appear above.  Do NOT mutate
    # ``sanitized_context`` -- it is merged into the structured payload below.
    _PLAINTEXT_SAFE_TYPES = (str, int, float, bool)
    context_fields: list[str] = []
    for key in sorted(sanitized_context.keys()):
        # Skip reserved keys that already appear above.
        if key in _PLAINTEXT_RESERVED_KEYS:
            continue
        value = sanitized_context[key]
        if value is None:
            # Omit None-valued fields from plaintext to keep output compact.
            continue
        if isinstance(value, _PLAINTEXT_SAFE_TYPES):
            str_value = str(value)
            # Guard against accidentally logging oversized payloads.
            if len(str_value) > 200:
                continue
            context_fields.append(f"{key}={str_value}")
        else:
            # Omit complex types from plaintext; they remain in ``extra``.
            pass

    msg_parts.extend(context_fields)

    logger_to_use.info(" ".join(msg_parts), extra=payload)

    return payload
