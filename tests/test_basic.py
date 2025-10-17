"""
Basic tests for LLM Deployment System.

This module contains unit tests for the core functionality.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch

from core_app.database import db_manager
from utils.config import config
from utils.task_generator import get_task_generator
from utils.github_utils import GitHubUtils


class TestDatabase:
    """Test database functionality."""

    def test_database_connection(self):
        """Test database connection."""
        with db_manager.get_session() as session:
            result = session.execute("SELECT 1").fetchone()
            assert result[0] == 1

    def test_submission_creation(self):
        """Test submission creation."""
        submission = db_manager.create_submission(
            email="test@example.com",
            endpoint="http://localhost:3000",
            secret="test-secret"
        )
        assert submission.email == "test@example.com"
        assert submission.secret == "test-secret"


class TestTaskGenerator:
    """Test task generation functionality."""

    def test_task_generation(self):
        """Test task generation."""
        generator = get_task_generator()
        task = generator.generate_task("test@example.com")

        assert 'task_id' in task
        assert 'brief' in task
        assert 'checks' in task
        assert 'attachments' in task
        assert task['email'] == 'test@example.com'

    def test_task_templates(self):
        """Test task templates."""
        generator = get_task_generator()
        templates = generator.list_templates()

        assert len(templates) > 0
        assert 'sum-of-sales' in templates


class TestGitHubUtils:
    """Test GitHub utility functions."""

    def test_github_url_validation(self):
        """Test GitHub URL validation."""
        assert GitHubUtils.is_valid_github_url("https://github.com/user/repo")
        assert not GitHubUtils.is_valid_github_url("https://gitlab.com/user/repo")

    def test_repo_name_extraction(self):
        """Test repository name extraction."""
        url = "https://github.com/octocat/Hello-World"
        assert GitHubUtils.extract_github_username(url) == "octocat"
        assert GitHubUtils.extract_repo_name(url) == "Hello-World"


class TestConfig:
    """Test configuration management."""

    def test_config_validation(self):
        """Test configuration validation."""
        issues = config.validate_config()
        # Should not have critical issues in test environment
        critical_issues = [k for k, v in issues.items() if 'must' in v.lower()]
        assert len(critical_issues) == 0


if __name__ == '__main__':
    pytest.main([__file__])
