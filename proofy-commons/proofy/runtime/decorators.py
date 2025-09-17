"""Decorators for test metadata and attributes."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from ..hooks.manager import get_plugin_manager
from .context import get_current_test_context

F = TypeVar("F", bound=Callable[..., Any])


def name(value: str) -> Callable[[F], F]:
    """Decorator to set test display name.

    Args:
        value: Display name for the test

    Returns:
        Decorated function
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = get_current_test_context()
            ctx.name = value

            # Trigger hook
            pm = get_plugin_manager()
            pm.hook.proofy_set_name(test_id=ctx.test_id, name=value)

            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def title(value: str) -> Callable[[F], F]:
    """Decorator to set test title (alias for name).

    Args:
        value: Title for the test

    Returns:
        Decorated function
    """
    return name(value)


def description(text: str) -> Callable[[F], F]:
    """Decorator to set test description.

    Args:
        text: Description text for the test

    Returns:
        Decorated function
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = get_current_test_context()
            ctx.description = text

            # Trigger hook
            pm = get_plugin_manager()
            pm.hook.proofy_set_description(test_id=ctx.test_id, description=text)

            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def severity(level: str) -> Callable[[F], F]:
    """Decorator to set test severity level.

    Args:
        level: Severity level (e.g., 'critical', 'high', 'medium', 'low')

    Returns:
        Decorated function
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = get_current_test_context()
            ctx.severity = level

            # Trigger hook
            pm = get_plugin_manager()
            pm.hook.proofy_set_severity(test_id=ctx.test_id, severity=level)

            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def tags(*tag_list: str) -> Callable[[F], F]:
    """Decorator to add tags to test.

    Args:
        *tag_list: Tags to add to the test

    Returns:
        Decorated function
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = get_current_test_context()

            # Add tags to context
            new_tags = []
            for tag in tag_list:
                if tag not in ctx.tags:
                    ctx.tags.append(tag)
                    new_tags.append(tag)

            # Trigger hook if we added new tags
            if new_tags:
                pm = get_plugin_manager()
                pm.hook.proofy_add_tags(test_id=ctx.test_id, tags=new_tags)

            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def attributes(**attrs: Any) -> Callable[[F], F]:
    """Decorator to attach arbitrary attributes to test.

    Args:
        **attrs: Attributes to add to the test

    Returns:
        Decorated function or class
    """

    def decorator(obj: F) -> F:
        # Handle both functions and classes
        if callable(obj) and not isinstance(obj, type):
            # Function decorator
            @wraps(obj)
            def wrapper(*args: Any, **kwargs_call: Any) -> Any:
                ctx = get_current_test_context()
                ctx.metadata.update(attrs)
                ctx.attributes.update(attrs)

                # Trigger hook
                pm = get_plugin_manager()
                pm.hook.proofy_add_attributes(test_id=ctx.test_id, attributes=attrs)

                return obj(*args, **kwargs_call)

            return wrapper  # type: ignore[return-value]
        else:
            # Class decorator or other object
            obj.__proofy_attributes__ = attrs  # type: ignore[attr-defined]
            return obj  # type: ignore[return-value]

    return decorator


def marker(**attrs: Any) -> Any:
    """Create a framework-specific marker with attributes.

    This decorator integrates with the plugin system to create
    framework-appropriate markers (e.g., pytest marks).

    Args:
        **attrs: Attributes for the marker

    Returns:
        Framework-specific marker object
    """
    pm = get_plugin_manager()
    results = pm.hook.proofy_mark_attributes(attributes=attrs)

    # Return first non-None result, or a simple attributes decorator
    for result in results:
        if result is not None:
            return result

    # Fallback to attributes decorator
    return attributes(**attrs)


# ========== Convenience decorators for common attributes ==========


def critical(func: F) -> F:
    """Mark test as critical severity."""
    return severity("critical")(func)


def high(func: F) -> F:
    """Mark test as high severity."""
    return severity("high")(func)


def medium(func: F) -> F:
    """Mark test as medium severity."""
    return severity("medium")(func)


def low(func: F) -> F:
    """Mark test as low severity."""
    return severity("low")(func)


def smoke(func: F) -> F:
    """Mark test as smoke test."""
    return tags("smoke")(func)


def regression(func: F) -> F:
    """Mark test as regression test."""
    return tags("regression")(func)


def integration(func: F) -> F:
    """Mark test as integration test."""
    return tags("integration")(func)


def unit(func: F) -> F:
    """Mark test as unit test."""
    return tags("unit")(func)
