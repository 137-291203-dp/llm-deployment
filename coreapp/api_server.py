"""
Main API server for LLM Deployment System.

This module implements the Flask API server that handles student requests,
task generation, and repository submissions.
"""

import time
import secrets
import threading
from datetime import datetime, timezone

from flask import Flask, request
from flask_cors import CORS
from flask_restx import Api, Resource, fields

from coreapp.database import db_manager, TaskStatus
from utils.logger import get_logger
from utils.task_generator import get_task_generator
from utils.github_utils import get_github_manager, GitHubUtils
from utils.config import config

logger = get_logger(__name__)


class APIServer:
    """Main API server class."""

    def __init__(self):
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = config.SECRET_KEY
        self.app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

        # Enable CORS
        CORS(self.app, origins=config.CORS_ORIGINS)

        # Initialize API with Swagger
        self.api = Api(
            self.app,
            version='1.0',
            title='LLM Deployment System API',
            description='API for student task generation and repository evaluation',
            doc='/docs'
        )

        # Rate limit store
        self.rate_limits = {}

        # Managers
        self.task_generator = get_task_generator()
        self.github_manager = None
        if config.ENABLE_GITHUB_INTEGRATION:
            try:
                self.github_manager = get_github_manager()
            except Exception as e:
                logger.warning(f"Failed to initialize GitHub manager: {e}")

        # Define models
        self._define_models()

        # Setup namespaces
        self._setup_namespaces()

        # Start cleanup thread for rate limits
        self.cleanup_rate_limits()

    def _define_models(self):
        """Define API models for Swagger."""
        self.models = {}

        self.models['task_request'] = self.api.model('TaskRequest', {
            'email': fields.String(required=True),
            'secret': fields.String(required=True)
        })

        self.models['task_response'] = self.api.model('TaskResponse', {
            'email': fields.String,
            'task': fields.String,
            'round': fields.Integer,
            'nonce': fields.String,
            'brief': fields.String,
            'checks': fields.List(fields.String),
            'attachments': fields.List(fields.Raw)
        })

        self.models['repo_submission'] = self.api.model('RepositorySubmission', {
            'email': fields.String(required=True),
            'task': fields.String(required=True),
            'round': fields.Integer(required=True),
            'nonce': fields.String(required=True),
            'repo_url': fields.String(required=True),
            'commit_sha': fields.String(required=True),
            'pages_url': fields.String
        })

        self.models['repo_validation'] = self.api.model('RepositoryValidation', {
            'repo_url': fields.String(required=True)
        })

    def _setup_namespaces(self):
        """Setup API namespaces and endpoints."""
        validate_secret = self._validate_secret
        check_rate_limit = self._check_rate_limit
        task_generator = self.task_generator
        github_manager = self.github_manager
        api_models = self.models

        # Health namespace
        health_ns = self.api.namespace('health', description='Health check operations')

        @health_ns.route('')
        class HealthCheck(Resource):
            def get(self):
                return {
                    'status': 'healthy',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'version': '1.0.0'
                }

        # Main API namespace
        api_ns = self.api.namespace('api', description='Main API operations')

        @api_ns.route('/request')
        class TaskRequest(Resource):
            @api_ns.expect(api_models['task_request'])
            @api_ns.response(200, 'Success', api_models['task_response'])
            @api_ns.response(400, 'Bad Request')
            @api_ns.response(401, 'Unauthorized')
            @api_ns.response(429, 'Rate Limited')
            def post(self):
                data = request.get_json()
                if not data:
                    return {'error': 'No JSON data provided'}, 400

                email = data.get('email')
                secret = data.get('secret')

                if not email or not secret:
                    return {'error': 'Missing required fields'}, 400

                if not validate_secret(email, secret):
                    return {'error': 'Invalid secret'}, 401

                if not check_rate_limit(email):
                    return {'error': 'Rate limit exceeded'}, 429

                try:
                    # Generate task dict
                    task = task_generator.generate_task(email)

                    # Filter out keys not in Task model (like evaluation_url)
                    task_data = {k: v for k, v in task.items() if k != 'evaluation_url'}

                    # Check if submission already exists
                    submission = db_manager.get_submission_by_email(email)
                    if not submission:
                        submission = db_manager.create_submission(
                            email=email,
                            endpoint=data.get('endpoint', ''),
                            secret=secret
                        )

                    db_task = db_manager.create_task(submission.id, task_data)
                    db_manager.update_task_status(db_task.task_id, TaskStatus.SENT)

                    response_data = {
                        'email': email,
                        'task': db_task.task_id,
                        'round': db_task.round,
                        'nonce': db_task.nonce,
                        'brief': db_task.brief,
                        'checks': db_task.checks,
                        'attachments': db_task.attachments
                    }

                    logger.info(f"Generated task {db_task.task_id} for {email}")
                    return response_data, 200

                except Exception as e:
                    logger.exception(f"Failed to generate task for {email}")
                    return {'error': 'Failed to generate task'}, 500

        @api_ns.route('/evaluate')
        class RepositoryEvaluation(Resource):
            @api_ns.expect(api_models['repo_submission'])
            def post(self):
                data = request.get_json()
                if not data:
                    return {'error': 'No JSON data provided'}, 400

                required_fields = ['email', 'task', 'round', 'nonce', 'repo_url', 'commit_sha']
                for f in required_fields:
                    if f not in data:
                        return {'error': f'Missing required field: {f}'}, 400

                task = db_manager.get_task_by_id(data['task'])
                if not task:
                    return {'error': 'Invalid task ID'}, 400

                if task.nonce != data['nonce']:
                    return {'error': 'Invalid nonce'}, 400

                if task.status != TaskStatus.SENT:
                    return {'error': 'Task not in correct state'}, 400

                db_manager.update_task_status(task.task_id, TaskStatus.RECEIVED)

                repo_data = {
                    'repo_url': data['repo_url'],
                    'commit_sha': data['commit_sha'],
                    'pages_url': data.get('pages_url')
                }
                db_manager.create_repository(task.id, repo_data)

                logger.info(f"Received repository submission for task {task.task_id}")
                return {'status': 'received'}, 200

        @api_ns.route('/validate-repo')
        class RepositoryValidation(Resource):
            @api_ns.expect(api_models['repo_validation'])
            def post(self):
                data = request.get_json()
                if not data or 'repo_url' not in data:
                    return {'error': 'Missing repo_url'}, 400

                repo_url = data['repo_url']

                if not GitHubUtils.is_valid_github_url(repo_url):
                    return {'error': 'Invalid GitHub URL'}, 400

                if not github_manager:
                    return {'error': 'GitHub integration not available'}, 503

                validation = github_manager.validate_repository(repo_url)
                return validation, 200

    def _validate_secret(self, email: str, secret: str) -> bool:
        try:
            student = db_manager.get_submission_by_email(email)
            if student and student.secret:
                return secrets.compare_digest(student.secret, secret)
        except Exception:
            logger.exception('Error validating secret')
        return bool(secret and len(secret) >= 8)

    def _check_rate_limit(self, email: str) -> bool:
        current_time = time.time()
        window_start = current_time - 60

        # Clean old entries
        self.rate_limits = {k: v for k, v in self.rate_limits.items() if v['timestamp'] > window_start}

        entry = self.rate_limits.get(email)
        if entry:
            if entry['count'] >= config.RATE_LIMIT_PER_MINUTE:
                return False
            entry['count'] += 1
            entry['timestamp'] = current_time
        else:
            self.rate_limits[email] = {'count': 1, 'timestamp': current_time}
        return True

    def cleanup_rate_limits(self):
        def cleanup():
            while True:
                time.sleep(300)
                current_time = time.time()
                window_start = current_time - 60
                self.rate_limits = {k: v for k, v in self.rate_limits.items() if v['timestamp'] > window_start}

        threading.Thread(target=cleanup, daemon=True).start()

    def run(self, host=None, port=None, debug=None):
        host = host or config.API_HOST
        port = port or config.API_PORT
        debug = debug if debug is not None else config.FLASK_DEBUG
        logger.info(f"Starting API server on {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)


# Global API server instance
api_server = APIServer()


def create_app():
    return api_server.app


if __name__ == '__main__':
    api_server.run()
