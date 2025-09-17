"""Tests for Proofy hook system."""

import pytest

from proofy.hooks.manager import get_plugin_manager, reset_plugin_manager
from proofy.hooks.specs import hookimpl


class TestPluginManager:
    """Tests for plugin manager functionality."""

    def setup_method(self):
        """Reset plugin manager before each test."""
        reset_plugin_manager()

    def teardown_method(self):
        """Reset plugin manager after each test."""
        reset_plugin_manager()

    def test_singleton_behavior(self):
        """Test that get_plugin_manager returns the same instance."""
        pm1 = get_plugin_manager()
        pm2 = get_plugin_manager()

        assert pm1 is pm2

    def test_hook_registration(self):
        """Test plugin registration and hook calling."""
        pm = get_plugin_manager()

        # Create a test plugin
        class TestPlugin:
            def __init__(self):
                self.calls = []

            @hookimpl
            def proofy_test_start(self, test_id, test_name, test_path):
                self.calls.append(("test_start", test_id, test_name, test_path))

        plugin = TestPlugin()
        pm.register(plugin)

        # Call hook
        pm.hook.proofy_test_start(
            test_id="test_1", test_name="Test 1", test_path="/test1.py"
        )

        # Verify hook was called
        assert len(plugin.calls) == 1
        assert plugin.calls[0] == ("test_start", "test_1", "Test 1", "/test1.py")

    def test_multiple_plugins(self):
        """Test multiple plugins responding to same hook."""
        pm = get_plugin_manager()

        class Plugin1:
            def __init__(self):
                self.calls = []

            @hookimpl
            def proofy_test_finish(self, test_result):
                self.calls.append(f"plugin1_{test_result.name}")

        class Plugin2:
            def __init__(self):
                self.calls = []

            @hookimpl
            def proofy_test_finish(self, test_result):
                self.calls.append(f"plugin2_{test_result.name}")

        plugin1 = Plugin1()
        plugin2 = Plugin2()

        pm.register(plugin1)
        pm.register(plugin2)

        # Mock test result
        class MockResult:
            def __init__(self, name):
                self.name = name

        result = MockResult("test_example")

        # Call hook
        pm.hook.proofy_test_finish(test_result=result)

        # Both plugins should have been called
        assert len(plugin1.calls) == 1
        assert len(plugin2.calls) == 1
        assert plugin1.calls[0] == "plugin1_test_example"
        assert plugin2.calls[0] == "plugin2_test_example"

    def test_hook_with_return_values(self):
        """Test hook that returns values."""
        pm = get_plugin_manager()

        class MarkerPlugin:
            @hookimpl
            def proofy_mark_attributes(self, attributes):
                if "severity" in attributes:
                    return f"marker_for_{attributes['severity']}"
                return None

        plugin = MarkerPlugin()
        pm.register(plugin)

        # Call hook
        results = pm.hook.proofy_mark_attributes(attributes={"severity": "critical"})

        # Should return list with our result
        assert len(results) == 1
        assert results[0] == "marker_for_critical"

    def test_unregister_plugin(self):
        """Test plugin unregistration."""
        pm = get_plugin_manager()

        class TestPlugin:
            def __init__(self):
                self.calls = []

            @hookimpl
            def proofy_test_start(self, test_id, test_name, test_path):
                self.calls.append(test_id)

        plugin = TestPlugin()
        pm.register(plugin)

        # Call hook - should work
        pm.hook.proofy_test_start(
            test_id="test_1", test_name="Test 1", test_path="/test1.py"
        )
        assert len(plugin.calls) == 1

        # Unregister plugin
        pm.unregister(plugin)

        # Call hook again - should not call plugin
        pm.hook.proofy_test_start(
            test_id="test_2", test_name="Test 2", test_path="/test2.py"
        )

        # Should still be 1 (not called after unregister)
        assert len(plugin.calls) == 1
