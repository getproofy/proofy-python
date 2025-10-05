"""
Example conftest.py showing best practices for run attributes.

This file demonstrates how to set run attributes in a real project.
Save this as conftest.py in your test directory.
"""

import os
import platform
from datetime import datetime

import proofy
import pytest


def pytest_sessionstart(session):
    """
    Configure run attributes at the start of the test session.

    This hook runs after pytest_configure but before any tests are collected.
    It's the ideal place to set run attributes.
    """

    # --- Environment Information ---
    environment = os.getenv("TEST_ENV", "local")
    proofy.add_run_attributes(
        environment=environment,
        test_mode=os.getenv("TEST_MODE", "full"),
    )

    # --- Application Version ---
    # Import your application version
    try:
        # from myapp import __version__ as app_version
        app_version = "1.2.3"  # Replace with actual import
    except ImportError:
        app_version = "unknown"

    proofy.add_run_attributes(
        app_version=app_version,
    )

    # --- CI/CD Information ---
    # GitHub Actions
    if os.getenv("GITHUB_ACTIONS"):
        proofy.add_run_attributes(
            ci_provider="github_actions",
            ci_run_id=os.getenv("GITHUB_RUN_ID", ""),
            ci_run_number=os.getenv("GITHUB_RUN_NUMBER", ""),
            repository=os.getenv("GITHUB_REPOSITORY", ""),
            branch=os.getenv("GITHUB_REF_NAME", ""),
            commit_sha=os.getenv("GITHUB_SHA", "")[:7],  # Short SHA
            actor=os.getenv("GITHUB_ACTOR", ""),
            workflow=os.getenv("GITHUB_WORKFLOW", ""),
        )

    # GitLab CI
    elif os.getenv("GITLAB_CI"):
        proofy.add_run_attributes(
            ci_provider="gitlab",
            ci_pipeline_id=os.getenv("CI_PIPELINE_ID", ""),
            ci_job_id=os.getenv("CI_JOB_ID", ""),
            repository=os.getenv("CI_PROJECT_PATH", ""),
            branch=os.getenv("CI_COMMIT_REF_NAME", ""),
            commit_sha=os.getenv("CI_COMMIT_SHORT_SHA", ""),
            actor=os.getenv("GITLAB_USER_LOGIN", ""),
        )

    # Jenkins
    elif os.getenv("JENKINS_URL"):
        proofy.add_run_attributes(
            ci_provider="jenkins",
            ci_build_number=os.getenv("BUILD_NUMBER", ""),
            ci_job_name=os.getenv("JOB_NAME", ""),
            branch=os.getenv("GIT_BRANCH", ""),
            commit_sha=os.getenv("GIT_COMMIT", "")[:7],
            build_url=os.getenv("BUILD_URL", ""),
        )

    # CircleCI
    elif os.getenv("CIRCLECI"):
        proofy.add_run_attributes(
            ci_provider="circleci",
            ci_build_number=os.getenv("CIRCLE_BUILD_NUM", ""),
            repository=os.getenv("CIRCLE_PROJECT_REPONAME", ""),
            branch=os.getenv("CIRCLE_BRANCH", ""),
            commit_sha=os.getenv("CIRCLE_SHA1", "")[:7],
            workflow_id=os.getenv("CIRCLE_WORKFLOW_ID", ""),
        )

    # --- Test Execution Configuration ---
    # Pytest configuration
    parallel_mode = session.config.getoption("-n", default=None)
    proofy.add_run_attributes(
        parallel_execution="true" if parallel_mode else "false",
        worker_count=str(parallel_mode) if parallel_mode else "1",
        pytest_version=pytest.__version__,
    )

    # Test markers (if you want to track which markers were selected)
    markers = session.config.option.markexpr if hasattr(session.config.option, "markexpr") else None
    if markers:
        proofy.set_run_attribute("test_markers", markers)

    # --- Execution Metadata ---
    proofy.add_run_attributes(
        executed_at=datetime.now().isoformat(),
        executed_by=os.getenv("USER", os.getenv("USERNAME", "unknown")),
        hostname=platform.node(),
    )

    # --- Custom Project-Specific Attributes ---
    # Add any project-specific metadata here
    if environment == "production":
        proofy.add_run_attributes(
            warning="production_test",
            requires_approval="true",
        )

    # Database configuration (if applicable)
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        # Don't log full connection string, just the database type
        db_type = db_url.split("://")[0] if "://" in db_url else "unknown"
        proofy.set_run_attribute("database_type", db_type)

    # API endpoint being tested
    api_endpoint = os.getenv("API_ENDPOINT", os.getenv("API_BASE_URL", ""))
    if api_endpoint:
        proofy.set_run_attribute("api_endpoint", api_endpoint)


def pytest_sessionfinish(session, exitstatus):
    """
    Optional: Add final attributes at the end of the session.

    Note: Run is already finished at this point, so these attributes
    won't be sent to the server. This is just for demonstration.
    """
    pass


# --- Fixtures for accessing run attributes in tests ---


@pytest.fixture(scope="session")
def run_environment():
    """Fixture providing the test environment."""
    return proofy.get_run_attributes().get("environment", "unknown")


@pytest.fixture(scope="session")
def run_attributes():
    """Fixture providing all run attributes."""
    return proofy.get_run_attributes()
