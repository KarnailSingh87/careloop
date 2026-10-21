"""
Pytest configuration and global fixtures.
Enforces test isolation, hermetic environment, and prevents accidental external AWS side effects.
"""

import pytest


@pytest.fixture(autouse=True)
def hermetic_aws_environment(monkeypatch):
    """
    Ensure no real AWS credentials or endpoints are reached during unit tests.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
