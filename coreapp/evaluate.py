"""
Repository evaluation script for LLM Deployment System.

This module implements comprehensive evaluation of student repositories,
including static analysis, dynamic testing, and LLM-based quality checks.
"""

import asyncio
import json
import time
import tempfile
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
import subprocess
from urllib.parse import urlparse

import requests
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup

from utils.config import config
from .database import EvaluationStatus, db_manager
from utils.logger import get_logger, log_evaluation
from utils.github_utils import get_github_manager, GitHubUtils

logger = get_logger(__name__)


class RepositoryEvaluator:
    """Main repository evaluation class."""

    def __init__(self):
        self.github_manager = None
        if config.ENABLE_GITHUB_INTEGRATION:
            try:
                self.github_manager = get_github_manager()
            except Exception as e:
                logger.warning(f"Failed to initialize GitHub manager: {e}")

    def evaluate_repository(self, repo_url: str, commit_sha: str, pages_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """Evaluate a repository comprehensively."""
        logger.info(f"Starting evaluation of repository: {repo_url}")

        evaluation_results = []

        try:
            # 1. Basic repository validation
            repo_validation = self._validate_repository(repo_url, commit_sha)
            evaluation_results.extend(repo_validation)

            # 2. GitHub Pages availability check
            if pages_url:
                pages_check = self._check_pages_availability(pages_url)
                evaluation_results.append(pages_check)

            # 3. Dynamic evaluation using Playwright
            if pages_url:
                dynamic_checks = self._run_dynamic_checks(pages_url)
                evaluation_results.extend(dynamic_checks)

            # 4. Code quality checks (if we can access the repo)
            if self.github_manager:
                code_checks = self._check_code_quality(repo_url, commit_sha)
                evaluation_results.extend(code_checks)

            # 5. README quality check
            readme_check = self._check_readme_quality(repo_url, commit_sha)
            evaluation_results.append(readme_check)

            logger.info(f"Completed evaluation of {repo_url} with {len(evaluation_results)} checks")
            return evaluation_results

        except Exception as e:
            logger.error(f"Error during repository evaluation: {e}")
            # Return error result
            return [{
                'check_name': 'evaluation_error',
                'status': EvaluationStatus.ERROR,
                'score': 0.0,
                'reason': f'Evaluation failed: {str(e)}',
                'logs': {'error': str(e), 'traceback': str(e.__class__.__name__)}
            }]

    def _validate_repository(self, repo_url: str, commit_sha: str) -> List[Dict[str, Any]]:
        """Validate basic repository requirements."""
        results = []

        # Check if repository exists and is accessible
        try:
            if not self.github_manager:
                results.append({
                    'check_name': 'github_integration',
                    'status': EvaluationStatus.ERROR,
                    'score': 0.0,
                    'reason': 'GitHub integration not available',
                    'logs': {}
                })
                return results

            validation = self.github_manager.validate_repository(repo_url)
            if not validation.get('valid'):
                results.append({
                    'check_name': 'repository_exists',
                    'status': EvaluationStatus.FAILED,
                    'score': 0.0,
                    'reason': validation.get('error', 'Repository not accessible'),
                    'logs': validation
                })
            else:
                results.append({
                    'check_name': 'repository_exists',
                    'status': EvaluationStatus.PASSED,
                    'score': 1.0,
                    'reason': 'Repository is accessible',
                    'logs': validation
                })

                # Check for MIT license
                if validation.get('has_license'):
                    results.append({
                        'check_name': 'license_check',
                        'status': EvaluationStatus.PASSED,
                        'score': 1.0,
                        'reason': 'MIT license found',
                        'logs': {}
                    })
                else:
                    results.append({
                        'check_name': 'license_check',
                        'status': EvaluationStatus.FAILED,
                        'score': 0.0,
                        'reason': 'MIT license not found',
                        'logs': {}
                    })

                # Check for README
                if validation.get('has_readme'):
                    results.append({
                        'check_name': 'readme_exists',
                        'status': EvaluationStatus.PASSED,
                        'score': 1.0,
                        'reason': 'README.md found',
                        'logs': {}
                    })
                else:
                    results.append({
                        'check_name': 'readme_exists',
                        'status': EvaluationStatus.FAILED,
                        'score': 0.0,
                        'reason': 'README.md not found',
                        'logs': {}
                    })

        except Exception as e:
            results.append({
                'check_name': 'repository_validation',
                'status': EvaluationStatus.ERROR,
                'score': 0.0,
                'reason': f'Repository validation failed: {str(e)}',
                'logs': {'error': str(e)}
            })

        return results

    def _check_pages_availability(self, pages_url: str) -> Dict[str, Any]:
        """Check if GitHub Pages is accessible."""
        try:
            response = requests.get(pages_url, timeout=10)
            if response.status_code == 200:
                return {
                    'check_name': 'pages_availability',
                    'status': EvaluationStatus.PASSED,
                    'score': 1.0,
                    'reason': f'GitHub Pages accessible (HTTP {response.status_code})',
                    'logs': {
                        'status_code': response.status_code,
                        'response_time': response.elapsed.total_seconds(),
                        'content_length': len(response.content)
                    }
                }
            else:
                return {
                    'check_name': 'pages_availability',
                    'status': EvaluationStatus.FAILED,
                    'score': 0.0,
                    'reason': f'GitHub Pages returned HTTP {response.status_code}',
                    'logs': {'status_code': response.status_code}
                }
        except requests.RequestException as e:
            return {
                'check_name': 'pages_availability',
                'status': EvaluationStatus.FAILED,
                'score': 0.0,
                'reason': f'GitHub Pages not accessible: {str(e)}',
                'logs': {'error': str(e)}
            }

    def _run_dynamic_checks(self, pages_url: str) -> List[Dict[str, Any]]:
        """Run dynamic checks using Playwright."""
        results = []

        try:
            # Run basic dynamic checks
            basic_checks = asyncio.run(self._run_basic_dynamic_checks(pages_url))
            results.extend(basic_checks)

        except Exception as e:
            logger.error(f"Error running dynamic checks for {pages_url}: {e}")
            results.append({
                'check_name': 'dynamic_checks',
                'status': EvaluationStatus.ERROR,
                'score': 0.0,
                'reason': f'Dynamic checks failed: {str(e)}',
                'logs': {'error': str(e)}
            })

        return results

    async def _run_basic_dynamic_checks(self, pages_url: str) -> List[Dict[str, Any]]:
        """Run basic dynamic checks on the webpage."""
        results = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                # Navigate to the page
                await page.goto(pages_url, wait_until='networkidle', timeout=15000)

                # Check if page loads without JavaScript errors
                js_errors = []
                page.on('pageerror', lambda error: js_errors.append(str(error)))

                # Wait a bit for dynamic content
                await page.wait_for_timeout(2000)

                # Basic checks
                if js_errors:
                    results.append({
                        'check_name': 'javascript_errors',
                        'status': EvaluationStatus.FAILED,
                        'score': 0.0,
                        'reason': f'JavaScript errors detected: {len(js_errors)}',
                        'logs': {'errors': js_errors[:5]}  # Limit to first 5 errors
                    })
                else:
                    results.append({
                        'check_name': 'javascript_errors',
                        'status': EvaluationStatus.PASSED,
                        'score': 1.0,
                        'reason': 'No JavaScript errors detected',
                        'logs': {}
                    })

                # Check for console errors
                console_errors = []
                page.on('console', lambda msg: console_errors.append(str(msg)) if msg.type == 'error' else None)

                if console_errors:
                    results.append({
                        'check_name': 'console_errors',
                        'status': EvaluationStatus.FAILED,
                        'score': 0.5,  # Partial score since page still loads
                        'reason': f'Console errors detected: {len(console_errors)}',
                        'logs': {'errors': console_errors[:5]}
                    })

                # Check page title
                title = await page.title()
                if title and len(title.strip()) > 0:
                    results.append({
                        'check_name': 'page_title',
                        'status': EvaluationStatus.PASSED,
                        'score': 1.0,
                        'reason': f'Page has title: {title[:50]}...',
                        'logs': {'title': title}
                    })
                else:
                    results.append({
                        'check_name': 'page_title',
                        'status': EvaluationStatus.FAILED,
                        'score': 0.0,
                        'reason': 'Page missing title',
                        'logs': {}
                    })

                # Check for basic HTML structure
                body_content = await page.content()
                soup = BeautifulSoup(body_content, 'html.parser')

                if soup.body and soup.body.get_text().strip():
                    results.append({
                        'check_name': 'page_content',
                        'status': EvaluationStatus.PASSED,
                        'score': 1.0,
                        'reason': 'Page has content',
                        'logs': {'content_length': len(soup.body.get_text())}
                    })
                else:
                    results.append({
                        'check_name': 'page_content',
                        'status': EvaluationStatus.FAILED,
                        'score': 0.0,
                        'reason': 'Page appears to have no content',
                        'logs': {}
                    })

            except PlaywrightTimeoutError:
                results.append({
                    'check_name': 'page_load',
                    'status': EvaluationStatus.FAILED,
                    'score': 0.0,
                    'reason': 'Page failed to load within timeout',
                    'logs': {'timeout': 15000}
                })
            except Exception as e:
                results.append({
                    'check_name': 'dynamic_checks',
                    'status': EvaluationStatus.ERROR,
                    'score': 0.0,
                    'reason': f'Dynamic checks failed: {str(e)}',
                    'logs': {'error': str(e)}
                })
            finally:
                await browser.close()

        return results

    def _check_code_quality(self, repo_url: str, commit_sha: str) -> List[Dict[str, Any]]:
        """Check code quality metrics."""
        results = []

        try:
            if not self.github_manager:
                return results

            # Get repository info
            repo_name = GitHubUtils.extract_repo_name(repo_url)
            repo = self.github_manager.get_repository(repo_name)

            if not repo:
                return results

            # Check commit count
            commit_count = self.github_manager.get_commit_count(repo)
            if commit_count > 0:
                results.append({
                    'check_name': 'has_commits',
                    'status': EvaluationStatus.PASSED,
                    'score': 1.0,
                    'reason': f'Repository has {commit_count} commits',
                    'logs': {'commit_count': commit_count}
                })
            else:
                results.append({
                    'check_name': 'has_commits',
                    'status': EvaluationStatus.FAILED,
                    'score': 0.0,
                    'reason': 'Repository has no commits',
                    'logs': {}
                })

            # Check repository size
            repo_size = self.github_manager.get_repo_size(repo)
            if repo_size > 0:
                size_mb = repo_size / (1024 * 1024)
                results.append({
                    'check_name': 'repository_size',
                    'status': EvaluationStatus.PASSED,
                    'score': 1.0,
                    'reason': f'Repository size: {size_mb:.1f} MB',
                    'logs': {'size_bytes': repo_size}
                })

            # Check for multiple programming languages (diversity)
            languages = self.github_manager.get_repo_languages(repo)
            if len(languages) > 1:
                results.append({
                    'check_name': 'language_diversity',
                    'status': EvaluationStatus.PASSED,
                    'score': 0.8,
                    'reason': f'Uses {len(languages)} programming languages',
                    'logs': {'languages': list(languages.keys())}
                })
            elif len(languages) == 1:
                results.append({
                    'check_name': 'language_diversity',
                    'status': EvaluationStatus.PASSED,
                    'score': 0.6,
                    'reason': f'Uses {len(languages)} programming language',
                    'logs': {'languages': list(languages.keys())}
                })

        except Exception as e:
            logger.error(f"Error checking code quality: {e}")
            results.append({
                'check_name': 'code_quality',
                'status': EvaluationStatus.ERROR,
                'score': 0.0,
                'reason': f'Code quality check failed: {str(e)}',
                'logs': {'error': str(e)}
            })

        return results

    def _check_readme_quality(self, repo_url: str, commit_sha: str) -> Dict[str, Any]:
        """Check README quality using LLM or basic heuristics."""
        try:
            if not self.github_manager:
                return {
                    'check_name': 'readme_quality',
                    'status': EvaluationStatus.ERROR,
                    'score': 0.0,
                    'reason': 'GitHub integration not available',
                    'logs': {}
                }

            repo_name = GitHubUtils.extract_repo_name(repo_url)
            repo = self.github_manager.get_repository(repo_name)

            if not repo:
                return {
                    'check_name': 'readme_quality',
                    'status': EvaluationStatus.FAILED,
                    'score': 0.0,
                    'reason': 'Repository not accessible',
                    'logs': {}
                }

            # Get README content
            try:
                readme = repo.get_readme()
                readme_content = readme.decoded_content.decode('utf-8')
            except:
                return {
                    'check_name': 'readme_quality',
                    'status': EvaluationStatus.FAILED,
                    'score': 0.0,
                    'reason': 'README.md not found or not accessible',
                    'logs': {}
                }

            # Basic README quality checks
            checks = {
                'has_title': bool(re.search(r'^# .+', readme_content, re.MULTILINE)),
                'has_description': len(readme_content) > 100,
                'has_sections': len(re.findall(r'^## .+', readme_content, re.MULTILINE)) >= 2,
                'has_code_blocks': '```' in readme_content,
                'mentions_setup': any(word in readme_content.lower() for word in ['setup', 'install', 'usage']),
                'mentions_license': 'license' in readme_content.lower()
            }

            # Calculate score based on checks
            passed_checks = sum(checks.values())
            total_checks = len(checks)
            score = passed_checks / total_checks

            # Determine status
            if score >= 0.8:
                status = EvaluationStatus.PASSED
            elif score >= 0.5:
                status = EvaluationStatus.PASSED  # Still pass but lower score
            else:
                status = EvaluationStatus.FAILED

            return {
                'check_name': 'readme_quality',
                'status': status,
                'score': score,
                'reason': f'README quality score: {score:.2f} ({passed_checks}/{total_checks} checks passed)',
                'logs': {
                    'checks': checks,
                    'content_length': len(readme_content),
                    'line_count': len(readme_content.split('\n'))
                }
            }

        except Exception as e:
            return {
                'check_name': 'readme_quality',
                'status': EvaluationStatus.ERROR,
                'score': 0.0,
                'reason': f'README quality check failed: {str(e)}',
                'logs': {'error': str(e)}
            }


def evaluate_repository(repo_url: str, commit_sha: str, pages_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Evaluate a repository and return results."""
    evaluator = RepositoryEvaluator()
    return evaluator.evaluate_repository(repo_url, commit_sha, pages_url)


def run_evaluation_for_task(task_id: str) -> bool:
    """Run evaluation for a specific task."""
    try:
        task = db_manager.get_task_by_id(task_id)
        if not task or not task.repos:
            logger.error(f"No repositories found for task {task_id}")
            return False

        # Get the latest repository submission
        latest_repo = max(task.repos, key=lambda r: r.submitted_at)

        logger.info(f"Running evaluation for task {task_id}, repository {latest_repo.id}")

        # Update task status
        db_manager.update_task_status(task_id, 'evaluating')

        # Run evaluation
        results = evaluate_repository(
            repo_url=latest_repo.repo_url,
            commit_sha=latest_repo.commit_sha,
            pages_url=latest_repo.pages_url
        )

        # Store results
        for result in results:
            db_manager.add_evaluation(latest_repo.id, result)

        # Update task status to completed
        db_manager.update_task_status(task_id, 'completed')

        logger.info(f"Completed evaluation for task {task_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to run evaluation for task {task_id}: {e}")
        db_manager.update_task_status(task_id, 'failed', error_message=str(e))
        return False


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python evaluate.py <repo_url> [commit_sha] [pages_url]")
        sys.exit(1)

    repo_url = sys.argv[1]
    commit_sha = sys.argv[2] if len(sys.argv) > 2 else 'main'
    pages_url = sys.argv[3] if len(sys.argv) > 3 else None

    results = evaluate_repository(repo_url, commit_sha, pages_url)

    print(f"Evaluation completed with {len(results)} checks:")
    for result in results:
        print(f"  {result['check_name']}: {result['status']} (score: {result['score']})")
        print(f"    {result['reason']}")
