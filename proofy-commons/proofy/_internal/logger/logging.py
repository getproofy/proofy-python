"""Centralized logging helpers for Proofy packages."""

from __future__ import annotations

import logging
import os

__all__ = ["configure", "get_logger", "is_debug_logging_enabled"]

_LOGGER_NAME = "proofy"
_LOGGER_CONFIGURED = False
_ENV_LEVEL_NAME = "PF_LOG_LEVEL"
_ENV_DEBUG_FLAG = "PFDEBUG"
_DEFAULT_FORMAT = "%(levelname)s %(name)s: %(message)s"
_DEFAULT_DATE_FORMAT = None

_LEVEL_ALIASES: dict[str, int] = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_level(level: int | str | None) -> int:
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        normalized = level.strip().upper()
        if normalized.isdigit():
            return int(normalized)
        if normalized in _LEVEL_ALIASES:
            return _LEVEL_ALIASES[normalized]
    env_level = os.getenv(_ENV_LEVEL_NAME)
    if env_level:
        normalized = env_level.strip().upper()
        if normalized.isdigit():
            return int(normalized)
        if normalized in _LEVEL_ALIASES:
            return _LEVEL_ALIASES[normalized]
    if _is_truthy(os.getenv(_ENV_DEBUG_FLAG)):
        return logging.DEBUG
    return logging.INFO


def configure(level: int | str | None = None, *, force: bool = False) -> logging.Logger:
    """Configure the shared Proofy logger and return it."""
    global _LOGGER_CONFIGURED

    logger = logging.getLogger(_LOGGER_NAME)
    resolved_level = _resolve_level(level)

    if force or not _LOGGER_CONFIGURED:
        logger.setLevel(resolved_level)
        if not logger.handlers:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(resolved_level)
            stream_handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, _DEFAULT_DATE_FORMAT))
            logger.addHandler(stream_handler)
        else:
            for existing_handler in logger.handlers:
                existing_handler.setLevel(resolved_level)
        logger.propagate = False
        _LOGGER_CONFIGURED = True
    else:
        logger.setLevel(resolved_level)
        for existing_handler in logger.handlers:
            existing_handler.setLevel(resolved_level)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger of the shared Proofy logger."""
    configure()

    if not name:
        return logging.getLogger(_LOGGER_NAME)

    if name.startswith(f"{_LOGGER_NAME}.") or name == _LOGGER_NAME:
        logger_name = name
    else:
        logger_name = f"{_LOGGER_NAME}.{name}"

    return logging.getLogger(logger_name)


def is_debug_logging_enabled() -> bool:
    """Return True when the effective Proofy log level is DEBUG or lower."""
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        # Ensure we evaluate with current env without configuring handlers
        resolved_level = _resolve_level(None)
        return resolved_level <= logging.DEBUG
    return logger.getEffectiveLevel() <= logging.DEBUG
