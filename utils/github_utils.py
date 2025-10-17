"""
GitHub API utilities for LLM Deployment System.

This module provides functions for interacting with the GitHub API,
creating repositories, managing webhooks, and handling GitHub Pages.
"""

import os
import time
import base64
import hashlib
import hmac
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import requests
from github import Github, GithubException
from github.Repository import Repository
from github.GitRef import GitRef

from .config import config
from .logger import get_logger, log_github_action

logger = get_logger(__name__)


class GitHubManager:
    """Manager class for GitHub API operations."""

    def __init__(self, token: Optional[str] = None):
        """Initialize GitHub manager with token."""
        self.token = token or config.GITHUB_TOKEN
        if not self.token:
            raise ValueError("GitHub token is required")

        self.github = Github(self.token)
        self.user = self.github.get_user()

    def create_repository(self, name: str, description: str = "", private: bool = False) -> Repository:
        """Create a new GitHub repository."""
        try:
            repo = self.user.create_repo(
                name=name,
                description=description,
                private=private,
                auto_init=True,
                license_template="mit"
            )

            log_github_action(logger, "create_repo", name, success=True)
            logger.info(f"Created repository: {repo.full_name}")
            return repo

        except GithubException as e:
            log_github_action(logger, "create_repo", name, success=False, error=str(e))
            logger.error(f"Failed to create repository {name}: {e}")
            raise

    def delete_repository(self, repo_name: str) -> bool:
        """Delete a repository."""
        try:
            repo = self.user.get_repo(repo_name)
            repo.delete()
            log_github_action(logger, "delete_repo", repo_name, success=True)
            return True
        except GithubException as e:
            log_github_action(logger, "delete_repo", repo_name, success=False, error=str(e))
            logger.error(f"Failed to delete repository {repo_name}: {e}")
            return False

    def get_repository(self, repo_name: str) -> Optional[Repository]:
        """Get a repository by name."""
        try:
            return self.user.get_repo(repo_name)
        except GithubException:
            return None

    def create_or_update_file(self, repo: Repository, path: str, content: str, message: str, branch: str = "main") -> Dict[str, Any]:
        """Create or update a file in the repository."""
        try:
            # Check if file exists
            try:
                contents = repo.get_contents(path, ref=branch)
                # File exists, update it
                response = repo.update_file(
                    path=path,
                    message=message,
                    content=content,
                    sha=contents.sha,
                    branch=branch
                )
            except GithubException:
                # File doesn't exist, create it
                response = repo.create_file(
                    path=path,
                    message=message,
                    content=content,
                    branch=branch
                )

            logger.info(f"{'Updated' if 'sha' in locals() else 'Created'} file {path} in {repo.full_name}")
            return response

        except GithubException as e:
            logger.error(f"Failed to create/update file {path} in {repo.full_name}: {e}")
            raise

    def create_initial_commit(self, repo: Repository, files: Dict[str, str], branch: str = "main") -> str:
        """Create initial commit with multiple files."""
        try:
            # Create a tree with all files
            tree_elements = []

            for path, content in files.items():
                # Encode content as base64
                encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

                tree_elements.append({
                    'path': path,
                    'mode': '100644',  # Regular file
                    'type': 'blob',
                    'content': encoded_content
                })

            # Get the latest commit SHA for the branch
            try:
                ref = repo.get_git_ref(f"heads/{branch}")
                latest_sha = ref.object.sha
            except GithubException:
                # Branch doesn't exist, get the default branch
                latest_sha = repo.get_branch(repo.default_branch).commit.sha

            # Create tree
            tree = repo.create_git_tree(tree_elements, base_tree=latest_sha)

            # Create commit
            commit_message = "Initial commit: Project setup"
            commit = repo.create_git_commit(
                message=commit_message,
                tree=tree.sha,
                parents=[latest_sha]
            )

            # Update branch reference
            try:
                ref = repo.get_git_ref(f"heads/{branch}")
                ref.edit(commit.sha)
            except GithubException:
                # Create new branch
                repo.create_git_ref(f"refs/heads/{branch}", commit.sha)

            logger.info(f"Created initial commit in {repo.full_name}")
            return commit.sha

        except GithubException as e:
            logger.error(f"Failed to create initial commit in {repo.full_name}: {e}")
            raise

    def enable_github_pages(self, repo: Repository, branch: str = "main", path: str = "/") -> Dict[str, Any]:
        """Enable GitHub Pages for a repository."""
        try:
            # Enable Pages
            pages_config = {
                "source": {
                    "branch": branch,
                    "path": path
                }
            }

            # Update repository settings to enable Pages
            repo.edit(
                has_pages=True,
                pages_config=pages_config
            )

            logger.info(f"Enabled GitHub Pages for {repo.full_name}")
            return {"success": True, "pages_url": f"https://{self.user.login}.github.io/{repo.name}"}

        except GithubException as e:
            logger.error(f"Failed to enable GitHub Pages for {repo.full_name}: {e}")
            raise

    def get_pages_url(self, repo: Repository) -> Optional[str]:
        """Get the GitHub Pages URL for a repository."""
        try:
            pages_info = repo.get_pages_info()
            if pages_info and pages_info.status == "built":
                return pages_info.html_url
        except GithubException:
            pass

        # Fallback to standard Pages URL
        return f"https://{self.user.login}.github.io/{repo.name}"

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify GitHub webhook signature."""
        if not signature.startswith('sha256='):
            return False

        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(f"sha256={expected_signature}", signature)

    def create_webhook(self, repo: Repository, url: str, secret: str, events: List[str] = None) -> Dict[str, Any]:
        """Create a webhook for a repository."""
        if events is None:
            events = ["push", "pull_request", "issues"]

        try:
            webhook = repo.create_webhook(
                name="web",
                config={
                    "url": url,
                    "content_type": "json",
                    "secret": secret
                },
                events=events
            )

            logger.info(f"Created webhook for {repo.full_name}")
            return {"success": True, "webhook_id": webhook.id}

        except GithubException as e:
            logger.error(f"Failed to create webhook for {repo.full_name}: {e}")
            raise

    def get_repo_languages(self, repo: Repository) -> Dict[str, int]:
        """Get programming languages used in repository."""
        try:
            return repo.get_languages()
        except GithubException as e:
            logger.warning(f"Failed to get languages for {repo.full_name}: {e}")
            return {}

    def get_repo_size(self, repo: Repository) -> int:
        """Get repository size in bytes."""
        try:
            return repo.size * 1024  # GitHub returns size in KB
        except GithubException:
            return 0

    def check_license(self, repo: Repository) -> bool:
        """Check if repository has a LICENSE file."""
        try:
            repo.get_license()
            return True
        except GithubException:
            return False

    def check_readme(self, repo: Repository) -> bool:
        """Check if repository has a README file."""
        try:
            readme = repo.get_readme()
            return readme is not None
        except GithubException:
            return False

    def get_commit_count(self, repo: Repository) -> int:
        """Get total number of commits in repository."""
        try:
            commits = repo.get_commits()
            return commits.totalCount
        except GithubException:
            return 0

    def validate_repository(self, repo_url: str) -> Dict[str, Any]:
        """Validate a repository meets basic requirements."""
        try:
            # Extract repo name from URL
            repo_name = repo_url.split('/')[-1].replace('.git', '')

            repo = self.get_repository(repo_name)
            if not repo:
                return {"valid": False, "error": "Repository not found"}

            validation = {
                "valid": True,
                "repo_name": repo.name,
                "has_license": self.check_license(repo),
                "has_readme": self.check_readme(repo),
                "languages": self.get_repo_languages(repo),
                "size": self.get_repo_size(repo),
                "commit_count": self.get_commit_count(repo),
                "pages_enabled": False,
                "pages_url": None
            }

            # Check if Pages is enabled
            try:
                pages_url = self.get_pages_url(repo)
                if pages_url:
                    validation["pages_enabled"] = True
                    validation["pages_url"] = pages_url
            except:
                pass

            return validation

        except Exception as e:
            return {"valid": False, "error": str(e)}


class GitHubUtils:
    """Utility functions for GitHub operations."""

    @staticmethod
    def generate_repo_name(task_id: str, email: str) -> str:
        """Generate a unique repository name from task ID and email."""
        # Create a hash from email for uniqueness while maintaining some readability
        email_hash = hashlib.md5(email.encode()).hexdigest()[:8]
        return f"{task_id}-{email_hash}"

    @staticmethod
    def extract_github_username(repo_url: str) -> str:
        """Extract GitHub username from repository URL."""
        if 'github.com/' in repo_url:
            parts = repo_url.split('github.com/')[1].split('/')
            return parts[0] if len(parts) >= 1 else ''
        return ''

    @staticmethod
    def extract_repo_name(repo_url: str) -> str:
        """Extract repository name from repository URL."""
        if 'github.com/' in repo_url:
            parts = repo_url.split('github.com/')[1].split('/')
            return parts[1].replace('.git', '') if len(parts) >= 2 else ''
        return ''

    @staticmethod
    def is_valid_github_url(url: str) -> bool:
        """Check if URL is a valid GitHub repository URL."""
        return (
            url.startswith('https://github.com/') or
            url.startswith('http://github.com/') or
            url.startswith('git@github.com:')
        )

    @staticmethod
    def format_github_url(username: str, repo_name: str) -> str:
        """Format GitHub repository URL."""
        return f"https://github.com/{username}/{repo_name}"

    @staticmethod
    def format_pages_url(username: str, repo_name: str) -> str:
        """Format GitHub Pages URL."""
        return f"https://{username}.github.io/{repo_name}"

    @staticmethod
    def generate_license_content(project_name: str, year: int = None) -> str:
        """Generate MIT license content."""
        if year is None:
            year = datetime.now().year

        return f"""MIT License

Copyright (c) {year} {project_name}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


# Global GitHub manager instance
_github_manager = None


def get_github_manager() -> GitHubManager:
    """Get the global GitHub manager instance."""
    global _github_manager
    if _github_manager is None:
        _github_manager = GitHubManager()
    return _github_manager


def init_github_manager(token: str) -> GitHubManager:
    """Initialize GitHub manager with token."""
    global _github_manager
    _github_manager = GitHubManager(token)
    return _github_manager
