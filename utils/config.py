"""
Configuration management for LLM Deployment System.

Handles loading configuration from environment variables, providing defaults,
validating settings, and setting up logging.
"""

import os
import logging
from typing import Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in project root
dotenv_path = Path(__file__).parent.parent / 'config/.env'
load_dotenv(dotenv_path)

logger = logging.getLogger(__name__)


class Config:
    """Application configuration class."""

    # Database Configuration
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///data/deployment.db')

    # Flask Configuration
    FLASK_APP: str = os.getenv('FLASK_APP', 'api_server.py')
    FLASK_ENV: str = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG: bool = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # GitHub Configuration
    GITHUB_TOKEN: str = os.getenv('GITHUB_TOKEN', '')
    GITHUB_WEBHOOK_SECRET: str = os.getenv('GITHUB_WEBHOOK_SECRET', '')

    # API Configuration
    API_HOST: str = os.getenv('API_HOST', '0.0.0.0')
    API_PORT: int = int(os.getenv('API_PORT', '5000'))
    API_WORKERS: int = int(os.getenv('API_WORKERS', '4'))

    # Evaluation Configuration
    EVALUATION_TIMEOUT: int = int(os.getenv('EVALUATION_TIMEOUT', '300'))
    EVALUATION_RETRIES: int = int(os.getenv('EVALUATION_RETRIES', '3'))
    EVALUATION_DELAY_BASE: int = int(os.getenv('EVALUATION_DELAY_BASE', '1'))

    # LLM Configuration
    OPENAI_API_KEY: str = os.getenv('OPENAI_API_KEY', '')
    ANTHROPIC_API_KEY: str = os.getenv('ANTHROPIC_API_KEY', '')

    # Logging Configuration
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: str = os.getenv('LOG_FILE', 'logs/api_server.log')
    LOG_MAX_SIZE: str = os.getenv('LOG_MAX_SIZE', '100MB')
    LOG_BACKUP_COUNT: int = int(os.getenv('LOG_BACKUP_COUNT', '5'))

    # Redis Configuration (for Celery)
    REDIS_URL: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # Celery Configuration
    CELERY_BROKER_URL: str = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND: str = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

    # File Upload Configuration
    MAX_CONTENT_LENGTH: int = int(os.getenv('MAX_CONTENT_LENGTH', '16777216'))  # 16MB
    UPLOAD_FOLDER: str = os.getenv('UPLOAD_FOLDER', 'uploads/')

    # Security Configuration
    CORS_ORIGINS: list = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://localhost:5000').split(',')
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv('RATE_LIMIT_PER_MINUTE', '60'))

    # Deployment Configuration
    DEPLOYMENT_ENV: str = os.getenv('DEPLOYMENT_ENV', 'development')
    DOCKER_REGISTRY: str = os.getenv('DOCKER_REGISTRY', '')
    KUBERNETES_NAMESPACE: str = os.getenv('KUBERNETES_NAMESPACE', 'llm-deployment')

    # Monitoring Configuration
    SENTRY_DSN: str = os.getenv('SENTRY_DSN', '')
    JAEGER_ENDPOINT: str = os.getenv('JAEGER_ENDPOINT', 'http://localhost:14268/api/traces')

    # Backup Configuration
    BACKUP_DIR: str = os.getenv('BACKUP_DIR', 'backups/')
    BACKUP_RETENTION_DAYS: int = int(os.getenv('BACKUP_RETENTION_DAYS', '30'))
    BACKUP_SCHEDULE: str = os.getenv('BACKUP_SCHEDULE', '0 2 * * *')  # Daily at 2 AM

    # Feature Flags
    ENABLE_GITHUB_INTEGRATION: bool = os.getenv('ENABLE_GITHUB_INTEGRATION', 'true').lower() == 'true'
    ENABLE_DOCKER_DEPLOYMENT: bool = os.getenv('ENABLE_DOCKER_DEPLOYMENT', 'false').lower() == 'true'
    ENABLE_KUBERNETES_DEPLOYMENT: bool = os.getenv('ENABLE_KUBERNETES_DEPLOYMENT', 'false').lower() == 'true'
    ENABLE_EMAIL_NOTIFICATIONS: bool = os.getenv('ENABLE_EMAIL_NOTIFICATIONS', 'false').lower() == 'true'
    ENABLE_METRICS_COLLECTION: bool = os.getenv('ENABLE_METRICS_COLLECTION', 'true').lower() == 'true'

    @classmethod
    def get_database_url(cls) -> str:
        """Ensure database directory exists and return URL."""
        if cls.DATABASE_URL.startswith('sqlite:///'):
            db_path = cls.DATABASE_URL.replace('sqlite:///', '')
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return cls.DATABASE_URL

    @classmethod
    def get_log_file_path(cls) -> str:
        """Ensure logs directory exists and return log file path."""
        log_dir = os.path.dirname(cls.LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        return cls.LOG_FILE

    @classmethod
    def validate_config(cls) -> Dict[str, Any]:
        """Validate configuration and return any issues."""
        issues = {}

        # Required secrets for production
        if cls.DEPLOYMENT_ENV == 'production':
            if not cls.SECRET_KEY or cls.SECRET_KEY == 'dev-secret-key-change-in-production':
                issues['SECRET_KEY'] = 'Production deployments must set a secure SECRET_KEY'

            if cls.ENABLE_GITHUB_INTEGRATION and not cls.GITHUB_TOKEN:
                issues['GITHUB_TOKEN'] = 'GitHub integration requires GITHUB_TOKEN in production'

            if not cls.OPENAI_API_KEY and not cls.ANTHROPIC_API_KEY:
                issues['LLM_API_KEY'] = 'At least one LLM API key must be configured'

        # Database must exist
        if not cls.DATABASE_URL:
            issues['DATABASE_URL'] = 'Database URL must be configured'

        # Log level validation
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if cls.LOG_LEVEL.upper() not in valid_log_levels:
            issues['LOG_LEVEL'] = f'LOG_LEVEL must be one of {valid_log_levels}'

        # Port validation
        if not (1 <= cls.API_PORT <= 65535):
            issues['API_PORT'] = 'API_PORT must be between 1 and 65535'

        return issues

    @classmethod
    def is_development(cls) -> bool:
        return cls.FLASK_ENV == 'development'

    @classmethod
    def is_production(cls) -> bool:
        return cls.DEPLOYMENT_ENV == 'production'

    @classmethod
    def get_redis_config(cls) -> Dict[str, str]:
        return {
            'url': cls.REDIS_URL,
            'broker_url': cls.CELERY_BROKER_URL,
            'result_backend': cls.CELERY_RESULT_BACKEND,
        }

    @classmethod
    def get_github_config(cls) -> Dict[str, str]:
        return {
            'token': cls.GITHUB_TOKEN,
            'webhook_secret': cls.GITHUB_WEBHOOK_SECRET,
        }

    @classmethod
    def get_llm_config(cls) -> Dict[str, str]:
        return {
            'openai_api_key': cls.OPENAI_API_KEY,
            'anthropic_api_key': cls.ANTHROPIC_API_KEY,
        }


# Global configuration instance
config = Config()


def get_config() -> Config:
    """Get global config instance."""
    return config


def setup_logging():
    """Configure logging with console and rotating file handler."""
    import logging.config

    log_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'},
            'json': {'format': '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'},
        },
        'handlers': {
            'console': {'level': config.LOG_LEVEL, 'formatter': 'standard', 'class': 'logging.StreamHandler'},
            'file': {
                'level': config.LOG_LEVEL,
                'formatter': 'json',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': config.get_log_file_path(),
                'maxBytes': 100 * 1024 * 1024,
                'backupCount': config.LOG_BACKUP_COUNT,
            },
        },
        'loggers': {
            '': {'handlers': ['console', 'file'], 'level': config.LOG_LEVEL, 'propagate': False}
        }
    }

    logging.config.dictConfig(log_config)
    logger.info("Logging configured successfully")


if __name__ == '__main__':
    issues = config.validate_config()
    if issues:
        print("Configuration issues found:")
        for key, issue in issues.items():
            print(f"  {key}: {issue}")
        exit(1)
    else:
        print("Configuration is valid!")
