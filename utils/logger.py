"""
Logging utilities for LLM Deployment System.

This module provides centralized logging configuration and utilities.
"""

import logging
import logging.handlers
import sys
from typing import Optional
from pathlib import Path

from .config import config


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)


def setup_logger(
    name: str,
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> logging.Logger:
    """Setup a logger with file and console handlers."""

    logger = logging.getLogger(name)

    if level is None:
        level = config.LOG_LEVEL

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper()))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))

    # File handler
    if log_file is None:
        log_file = config.get_log_file_path()

    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=100 * 1024 * 1024,  # 100MB
        backupCount=config.LOG_BACKUP_COUNT
    )
    file_handler.setLevel(getattr(logging, level.upper()))

    # Formatter
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    formatter = logging.Formatter(format_string)
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


class LoggerMixin:
    """Mixin class to add logging capabilities to other classes."""

    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class."""
        class_name = self.__class__.__name__
        return get_logger(f"{class_name}")


# Global logger instance
logger = setup_logger(__name__)


def log_request_info(logger: logging.Logger, method: str, path: str, status_code: int, duration: float):
    """Log HTTP request information."""
    logger.info(f"{method} {path} - {status_code} - {duration:.2f}s")


def log_error(logger: logging.Logger, error: Exception, context: Optional[str] = None):
    """Log error with context."""
    if context:
        logger.error(f"Error in {context}: {str(error)}", exc_info=True)
    else:
        logger.error(f"Error: {str(error)}", exc_info=True)


def log_performance(logger: logging.Logger, operation: str, duration: float, **kwargs):
    """Log performance metrics."""
    extra = ' '.join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"Performance: {operation} took {duration:.2f}s {extra}")


def log_github_action(logger: logging.Logger, action: str, repo: str, **kwargs):
    """Log GitHub-related actions."""
    extra = ' '.join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"GitHub {action}: {repo} {extra}")


def log_evaluation(logger: logging.Logger, task_id: str, status: str, **kwargs):
    """Log evaluation-related actions."""
    extra = ' '.join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"Evaluation {task_id}: {status} {extra}")
