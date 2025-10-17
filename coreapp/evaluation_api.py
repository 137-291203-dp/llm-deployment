"""
Evaluation API endpoint for LLM Deployment System.

This module implements the evaluation API that receives repository
submissions from students and queues them for evaluation.
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import threading
import queue
import requests

from flask import Flask, request, jsonify, Response
from flask_cors import CORS

from utils.config import config
from .database import db_manager, TaskStatus
from utils.logger import get_logger, log_request_info, log_error, log_evaluation
from utils.github_utils import get_github_manager, GitHubUtils

logger = get_logger(__name__)


class EvaluationAPI:
    """Evaluation API server class."""

    def __init__(self):
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = config.SECRET_KEY
        self.app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

        # Enable CORS
        CORS(self.app, origins=config.CORS_ORIGINS)

        # Setup evaluation queue
        self.evaluation_queue = queue.Queue()
        self.worker_thread = None

        # Setup routes
        self._setup_routes()

        # Initialize managers
        self.github_manager = None
        if config.ENABLE_GITHUB_INTEGRATION:
            try:
                self.github_manager = get_github_manager()
            except Exception as e:
                logger.warning(f"Failed to initialize GitHub manager: {e}")

        # Start evaluation worker
        self.start_worker()

    def _setup_routes(self):
        """Setup API routes."""

        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint."""
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'queue_size': self.evaluation_queue.qsize(),
                'version': '1.0.0'
            })

        @self.app.route('/evaluate', methods=['POST'])
        def handle_evaluation_submission():
            """Handle repository evaluation submissions from students."""
            start_time = time.time()

            try:
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'No JSON data provided'}), 400

                # Validate required fields
                required_fields = ['email', 'task', 'round', 'nonce', 'repo_url', 'commit_sha']
                for field in required_fields:
                    if field not in data:
                        return jsonify({'error': f'Missing required field: {field}'}), 400

                # Validate task exists and nonce matches
                task = db_manager.get_task_by_id(data['task'])
                if not task:
                    return jsonify({'error': 'Invalid task ID'}), 400

                if task.nonce != data['nonce']:
                    return jsonify({'error': 'Invalid nonce'}), 400

                if task.status not in [TaskStatus.SENT, TaskStatus.RECEIVED]:
                    return jsonify({'error': 'Task not in correct state'}), 400

                # Update task status
                db_manager.update_task_status(data['task'], TaskStatus.RECEIVED)

                # Store repository information
                repo_data = {
                    'repo_url': data['repo_url'],
                    'commit_sha': data['commit_sha'],
                    'pages_url': data.get('pages_url')
                }

                repo = db_manager.create_repository(task.id, repo_data)

                # Queue for evaluation
                evaluation_job = {
                    'repository_id': repo.id,
                    'task_id': data['task'],
                    'repo_url': data['repo_url'],
                    'commit_sha': data['commit_sha'],
                    'pages_url': data.get('pages_url'),
                    'submitted_at': datetime.now(timezone.utc).isoformat()
                }

                self.evaluation_queue.put(evaluation_job)

                logger.info(f"Queued evaluation for task {data['task']}, repository {repo.id}")
                log_evaluation(logger, data['task'], 'queued', repository_id=repo.id)
                log_request_info(logger, 'POST', '/evaluate', 200, time.time() - start_time)

                return jsonify({
                    'status': 'received',
                    'repository_id': repo.id,
                    'message': 'Repository submission received and queued for evaluation'
                }), 200

            except Exception as e:
                logger.error(f"Error handling evaluation submission: {e}")
                log_error(logger, e, 'handle_evaluation_submission')
                return jsonify({'error': 'Internal server error'}), 500

        @self.app.route('/evaluate/status/<task_id>', methods=['GET'])
        def get_evaluation_status(task_id: str):
            """Get evaluation status for a task."""
            try:
                task = db_manager.get_task_by_id(task_id)
                if not task:
                    return jsonify({'error': 'Task not found'}), 404

                # Get repository and evaluations
                repos = task.repos
                if not repos:
                    return jsonify({'status': 'no_submission'})

                latest_repo = max(repos, key=lambda r: r.submitted_at)

                evaluations = db_manager.get_evaluations_by_repository(latest_repo.id)
                completed_evaluations = [e for e in evaluations if e.status.value in ['passed', 'failed']]

                if not evaluations:
                    status = 'queued'
                elif len(completed_evaluations) == len(evaluations):
                    status = 'completed'
                else:
                    status = 'evaluating'

                return jsonify({
                    'task_id': task_id,
                    'status': status,
                    'total_checks': len(evaluations),
                    'completed_checks': len(completed_evaluations),
                    'evaluations': [
                        {
                            'check_name': e.check_name,
                            'status': e.status.value,
                            'score': e.score,
                            'reason': e.reason
                        }
                        for e in evaluations
                    ]
                })

            except Exception as e:
                logger.error(f"Error getting evaluation status for {task_id}: {e}")
                return jsonify({'error': 'Internal server error'}), 500

        @self.app.route('/evaluate/results/<task_id>', methods=['GET'])
        def get_evaluation_results(task_id: str):
            """Get detailed evaluation results for a task."""
            try:
                task = db_manager.get_task_by_id(task_id)
                if not task:
                    return jsonify({'error': 'Task not found'}), 404

                repos = task.repos
                if not repos:
                    return jsonify({'error': 'No repositories submitted'}), 404

                latest_repo = max(repos, key=lambda r: r.submitted_at)
                evaluations = db_manager.get_evaluations_by_repository(latest_repo.id)

                results = []
                for evaluation in evaluations:
                    results.append({
                        'check_name': evaluation.check_name,
                        'status': evaluation.status.value,
                        'score': evaluation.score,
                        'reason': evaluation.reason,
                        'logs': evaluation.logs,
                        'evaluated_at': evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else None,
                        'duration_seconds': evaluation.duration_seconds
                    })

                return jsonify({
                    'task_id': task_id,
                    'repository_url': latest_repo.repo_url,
                    'commit_sha': latest_repo.commit_sha,
                    'pages_url': latest_repo.pages_url,
                    'results': results
                })

            except Exception as e:
                logger.error(f"Error getting evaluation results for {task_id}: {e}")
                return jsonify({'error': 'Internal server error'}), 500

        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({'error': 'Not found'}), 404

        @self.app.errorhandler(405)
        def method_not_allowed(error):
            return jsonify({'error': 'Method not allowed'}), 405

        @self.app.errorhandler(413)
        def file_too_large(error):
            return jsonify({'error': 'File too large'}), 413

        @self.app.errorhandler(500)
        def internal_error(error):
            logger.error(f"Internal server error: {error}")
            return jsonify({'error': 'Internal server error'}), 500

    def start_worker(self):
        """Start the evaluation worker thread."""
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.worker_thread = threading.Thread(target=self._evaluation_worker, daemon=True)
            self.worker_thread.start()
            logger.info("Started evaluation worker thread")

    def _evaluation_worker(self):
        """Background worker to process evaluation jobs."""
        logger.info("Evaluation worker started")

        while True:
            try:
                # Get job from queue (blocking)
                job = self.evaluation_queue.get(timeout=1)

                logger.info(f"Processing evaluation job for repository {job['repository_id']}")
                log_evaluation(logger, job['task_id'], 'processing', repository_id=job['repository_id'])

                # Process the evaluation
                self._process_evaluation(job)

                # Mark job as done
                self.evaluation_queue.task_done()

            except queue.Empty:
                # No jobs in queue, continue
                continue
            except Exception as e:
                logger.error(f"Error in evaluation worker: {e}")
                log_error(logger, e, '_evaluation_worker')
                time.sleep(5)  # Wait before retrying

    def _process_evaluation(self, job: Dict[str, Any]):
        """Process a single evaluation job."""
        try:
            from .evaluate import evaluate_repository

            repository_id = job['repository_id']
            repo_url = job['repo_url']
            commit_sha = job['commit_sha']
            pages_url = job['pages_url']

            # Run evaluation
            results = evaluate_repository(
                repo_url=repo_url,
                commit_sha=commit_sha,
                pages_url=pages_url
            )

            # Store results in database
            for result in results:
                db_manager.add_evaluation(repository_id, result)

            logger.info(f"Completed evaluation for repository {repository_id}")
            log_evaluation(logger, job['task_id'], 'completed', repository_id=repository_id)

        except Exception as e:
            logger.error(f"Failed to process evaluation for repository {job['repository_id']}: {e}")
            log_error(logger, e, f"_process_evaluation_{job['repository_id']}")

            # Store error result
            error_result = {
                'check_name': 'system_error',
                'status': 'error',
                'score': 0.0,
                'reason': f'Evaluation failed: {str(e)}',
                'logs': {'error': str(e)}
            }
            db_manager.add_evaluation(job['repository_id'], error_result)


# Global evaluation API instance
evaluation_api = EvaluationAPI()


def get_evaluation_api() -> EvaluationAPI:
    """Get the global evaluation API instance."""
    return evaluation_api


def create_evaluation_app() -> Flask:
    """Create Flask application instance for evaluation API."""
    return evaluation_api.app


if __name__ == '__main__':
    evaluation_api.app.run(host=config.API_HOST, port=config.API_PORT + 1, debug=config.FLASK_DEBUG)
