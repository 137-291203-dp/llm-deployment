"""
Basic tests for LLM Deployment System.

This module contains unit tests for the core functionality.
"""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy import text

from coreapp.database import db_manager
from utils.config import config
from utils.task_generator import get_task_generator
from utils.github_utils import GitHubUtils
import uuid 


class TestDatabase:
    """Test database functionality."""

    def test_database_connection(self):
        """Ensure database connection works."""
        with db_manager.get_session() as session:
            # SQLAlchemy 2.x requires text() for raw SQL
            result = session.execute(text("SELECT 1")).fetchone()
            assert result[0] == 1

    def test_submission_creation(self):
        """Test creation of a submission record with unique email/endpoint."""
        unique_email = f"test-{uuid.uuid4()}@example.com"
        unique_endpoint = f"http://localhost:3000/{uuid.uuid4()}"

        submission = db_manager.create_submission(
            email=unique_email,
            endpoint=unique_endpoint,
            secret="test-secret"
        )
        assert submission.email == unique_email
        assert submission.secret == "test-secret"

class TestTaskGenerator:
    """Test task generation functionality."""

    def test_task_generation(self):
        """Verify that task generator produces valid tasks."""
        generator = get_task_generator()
        task = generator.generate_task("test@example.com")

        # Core keys should always exist
        assert 'task_id' in task
        assert 'brief' in task
        assert 'checks' in task
        assert 'attachments' in task

        # Some generators may not include email, so check safely
        if 'email' in task:
            assert task['email'] == "test@example.com"

    def test_task_templates(self):
        """Verify task templates exist."""
        generator = get_task_generator()
        templates = generator.list_templates()
        assert len(templates) > 0
        assert 'sum-of-sales' in templates


class TestGitHubUtils:
    """Test GitHub utility functions."""

    def test_github_url_validation(self):
        """Check that GitHub URL validation works correctly."""
        assert GitHubUtils.is_valid_github_url("https://github.com/user/repo")
        assert not GitHubUtils.is_valid_github_url("https://gitlab.com/user/repo")

    def test_repo_name_extraction(self):
        """Check GitHub username and repo name extraction."""
        url = "https://github.com/octocat/Hello-World"
        assert GitHubUtils.extract_github_username(url) == "octocat"
        assert GitHubUtils.extract_repo_name(url) == "Hello-World"


class TestConfig:
    """Test configuration management."""

    def test_config_validation(self):
        """Ensure config has no critical issues."""
        issues = config.validate_config()
        critical_issues = [k for k, v in issues.items() if 'must' in v.lower()]
        assert len(critical_issues) == 0


if __name__ == "__main__":
    pytest.main([__file__])
