"""
Database models and initialization for LLM Deployment System.

This module defines the database schema using SQLAlchemy and provides
utilities for database operations.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import json
import uuid

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    Boolean, Float, ForeignKey, JSON, Enum, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from utils.config import config
from utils.logger import get_logger

logger = get_logger(__name__)

Base = declarative_base()


class TaskStatus(str, Enum):
    """Enumeration of task statuses."""
    PENDING = "pending"
    SENT = "sent"
    RECEIVED = "received"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationStatus(str, Enum):
    """Enumeration of evaluation statuses."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class Submission(Base):
    """Model for storing student submissions and API endpoints."""

    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    endpoint = Column(String(500), nullable=False)
    secret = Column(String(255), nullable=False)
    github_username = Column(String(255))
    github_repo_url = Column(String(500))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    tasks = relationship("Task", back_populates="submission", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('email', 'endpoint', name='unique_submission'),
    )


class Task(Base):
    """Model for storing tasks sent to students."""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)

    # Task identification
    task_id = Column(String(255), nullable=False, unique=True, index=True)  # e.g., "captcha-solver-a1b2c"
    round = Column(Integer, nullable=False)  # 1 or 2
    nonce = Column(String(255), nullable=False, unique=True)

    # Task content
    brief = Column(Text, nullable=False)
    checks = Column(JSON, nullable=False)  # List of check strings
    attachments = Column(JSON, default=list)  # List of attachment objects

    # Task lifecycle
    status = Column(String(50), default="pending")
    sent_at = Column(DateTime)
    received_at = Column(DateTime)

    # Response data
    status_code = Column(Integer)  # HTTP status code from student's API
    error_message = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    submission = relationship("Submission", back_populates="tasks")
    repos = relationship("Repository", back_populates="task", cascade="all, delete-orphan")


class Repository(Base):
    """Model for storing repository information submitted by students."""

    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)

    # Repository details
    repo_url = Column(String(500), nullable=False)
    commit_sha = Column(String(40), nullable=False)  # Git commit SHA
    pages_url = Column(String(500))  # GitHub Pages URL

    # Timing
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    task = relationship("Task", back_populates="repos")
    evaluations = relationship("Evaluation", back_populates="repository", cascade="all, delete-orphan")


class Evaluation(Base):
    """Model for storing evaluation results."""

    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)

    # Evaluation details
    check_name = Column(String(255), nullable=False)  # Name of the specific check
    status = Column(String(50), nullable=False)
    score = Column(Float)  # Score for this check (0.0 to 1.0)
    reason = Column(Text)  # Explanation of the result
    logs = Column(JSON)  # Detailed logs from the evaluation

    # Metadata
    evaluated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    duration_seconds = Column(Float)  # How long the evaluation took

    # Relationships
    repository = relationship("Repository", back_populates="evaluations")


class TaskTemplate(Base):
    """Model for storing task templates used to generate tasks."""

    __tablename__ = "task_templates"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(String(100), nullable=False, unique=True, index=True)  # e.g., "captcha-solver"

    # Template content
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Round 1 configuration
    brief_template = Column(Text, nullable=False)
    checks_template = Column(JSON, nullable=False)  # List of check templates
    attachments_template = Column(JSON, default=list)

    # Round 2 configuration (optional)
    round2_brief_template = Column(Text)
    round2_checks_template = Column(JSON)
    round2_attachments_template = Column(JSON)

    # Template metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Seed configuration for randomization
    seed_config = Column(JSON, default=dict)  # Configuration for seed generation


class SystemConfig(Base):
    """Model for storing system-wide configuration."""

    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True)
    key = Column(String(255), nullable=False, unique=True, index=True)
    value = Column(JSON, nullable=False)
    description = Column(Text)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class DatabaseManager:
    """Database manager class for handling connections and operations."""

    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._setup_database()

    def _setup_database(self):
        """Setup database connection and create tables."""
        try:
            # Create engine
            self.engine = create_engine(
                config.get_database_url(),
                connect_args={"check_same_thread": False} if "sqlite" in config.DATABASE_URL else {},
                pool_pre_ping=True,
                echo=config.FLASK_DEBUG
            )

            # Create tables
            Base.metadata.create_all(bind=self.engine)

            # Create session factory
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

            logger.info(f"Database initialized: {config.DATABASE_URL}")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def get_session(self) -> Session:
        """Get a database session."""
        return self.SessionLocal()

    def create_submission(self, email: str, endpoint: str, secret: str, **kwargs) -> Submission:
        """Create a new submission record."""
        with self.get_session() as session:
            submission = Submission(
                email=email,
                endpoint=endpoint,
                secret=secret,
                **kwargs
            )
            session.add(submission)
            session.commit()
            session.refresh(submission)
            return submission

    def get_submission_by_email(self, email: str) -> Optional[Submission]:
        """Get submission by email."""
        with self.get_session() as session:
            return session.query(Submission).filter(Submission.email == email).first()

    def create_task(self, submission_id: int, task_data: Dict[str, Any]) -> Task:
        """Create a new task record."""
        with self.get_session() as session:
            task = Task(submission_id=submission_id, **task_data)
            session.add(task)
            session.commit()
            session.refresh(task)
            return task

    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """Get task by task_id."""
        with self.get_session() as session:
            return session.query(Task).filter(Task.task_id == task_id).first()

    def get_tasks_by_submission(self, submission_id: int, round: Optional[int] = None) -> List[Task]:
        """Get tasks for a submission, optionally filtered by round."""
        with self.get_session() as session:
            query = session.query(Task).filter(Task.submission_id == submission_id)
            if round is not None:
                query = query.filter(Task.round == round)
            return query.all()

    def update_task_status(self, task_id: str, status: str, **kwargs) -> bool:
        """Update task status and other fields."""
        with self.get_session() as session:
            task = session.query(Task).filter(Task.task_id == task_id).first()
            if not task:
                return False

            task.status = status
            if 'status_code' in kwargs:
                task.status_code = kwargs['status_code']
            if 'error_message' in kwargs:
                task.error_message = kwargs['error_message']
            if status == "sent" and not task.sent_at:
                task.sent_at = datetime.now(timezone.utc)
            if status == "received" and not task.received_at:
                task.received_at = datetime.now(timezone.utc)

            session.commit()
            return True

    def create_repository(self, task_id: int, repo_data: Dict[str, Any]) -> Repository:
        """Create a new repository record."""
        with self.get_session() as session:
            repo = Repository(task_id=task_id, **repo_data)
            session.add(repo)
            session.commit()
            session.refresh(repo)
            return repo

    def get_repositories_by_task(self, task_id: str) -> List[Repository]:
        """Get repositories for a task."""
        with self.get_session() as session:
            task = session.query(Task).filter(Task.task_id == task_id).first()
            if not task:
                return []
            return task.repos

    def add_evaluation(self, repository_id: int, evaluation_data: Dict[str, Any]) -> Evaluation:
        """Add an evaluation result."""
        with self.get_session() as session:
            evaluation = Evaluation(repository_id=repository_id, **evaluation_data)
            session.add(evaluation)
            session.commit()
            session.refresh(evaluation)
            return evaluation

    def get_evaluations_by_repository(self, repository_id: int) -> List[Evaluation]:
        """Get evaluations for a repository."""
        with self.get_session() as session:
            return session.query(Evaluation).filter(Evaluation.repository_id == repository_id).all()

    def get_task_templates(self) -> List[TaskTemplate]:
        """Get all active task templates."""
        with self.get_session() as session:
            return session.query(TaskTemplate).filter(TaskTemplate.is_active == True).all()

    def create_task_template(self, template_data: Dict[str, Any]) -> TaskTemplate:
        """Create a new task template."""
        with self.get_session() as session:
            template = TaskTemplate(**template_data)
            session.add(template)
            session.commit()
            session.refresh(template)
            return template


# Global database manager instance
db_manager = DatabaseManager()


def get_db() -> DatabaseManager:
    """Get the global database manager instance."""
    return db_manager


def init_database():
    """Initialize the database with default data."""
    logger.info("Initializing database with default data...")

    # Create default task templates
    templates_data = [
        {
            'template_id': 'sum-of-sales',
            'name': 'Sales Summary Application',
            'description': 'Create an app that processes CSV data and displays sales summaries',
            'brief_template': 'Publish a single-page site that fetches data.csv from attachments, sums its sales column, sets the title to "Sales Summary {seed}", displays the total inside #total-sales, and loads Bootstrap 5 from jsdelivr.',
            'checks_template': [
                'js: document.title === `Sales Summary {seed}`',
                'js: !!document.querySelector("link[href*=\'bootstrap\']")',
                'js: Math.abs(parseFloat(document.querySelector("#total-sales").textContent) - {result}) < 0.01'
            ],
            'attachments_template': [
                {
                    'name': 'data.csv',
                    'url': 'data:text/csv;base64,{seed}'
                }
            ],
            'round2_brief_template': 'Add a Bootstrap table #product-sales that lists each product with its total sales and keeps #total-sales accurate after render.',
            'round2_checks_template': [
                'js: document.querySelectorAll("#product-sales tbody tr").length >= 1',
                'js: (() => { const rows = [...document.querySelectorAll("#product-sales tbody tr td:last-child")]; const sum = rows.reduce((acc, cell) => acc + parseFloat(cell.textContent), 0); return Math.abs(sum - {result}) < 0.01; })()'
            ]
        },
        {
            'template_id': 'markdown-to-html',
            'name': 'Markdown to HTML Converter',
            'description': 'Create an app that converts Markdown to HTML with syntax highlighting',
            'brief_template': 'Publish a static page that converts input.md from attachments to HTML with marked, renders it inside #markdown-output, and loads highlight.js for code blocks.',
            'checks_template': [
                'js: !!document.querySelector("script[src*=\'marked\']")',
                'js: !!document.querySelector("script[src*=\'highlight.js\']")',
                'js: document.querySelector("#markdown-output").innerHTML.includes("<h")'
            ],
            'attachments_template': [
                {
                    'name': 'input.md',
                    'url': 'data:text/markdown;base64,{seed}'
                }
            ],
            'round2_brief_template': 'Add tabs #markdown-tabs that switch between rendered HTML in #markdown-output and the original Markdown in #markdown-source while keeping content in sync.',
            'round2_checks_template': [
                'js: document.querySelectorAll("#markdown-tabs button").length >= 2',
                'js: document.querySelector("#markdown-source").textContent.trim().length > 0'
            ]
        },
        {
            'template_id': 'github-user-created',
            'name': 'GitHub User Information',
            'description': 'Create an app that fetches and displays GitHub user information',
            'brief_template': 'Publish a Bootstrap page with form id="github-user-{seed}" that fetches a GitHub username, optionally uses ?token=, and displays the account creation date in YYYY-MM-DD UTC inside #github-created-at.',
            'checks_template': [
                'js: document.querySelector("#github-user-{seed}").tagName === "FORM"',
                'js: document.querySelector("#github-created-at").textContent.includes("20")',
                'js: !!document.querySelector("script").textContent.includes("https://api.github.com/users/")'
            ],
            'round2_brief_template': 'Show an aria-live alert #github-status that reports when a lookup starts, succeeds, or fails.',
            'round2_checks_template': [
                'js: document.querySelector("#github-status").getAttribute("aria-live") === "polite"',
                'js: !!document.querySelector("script").textContent.includes("github-status")'
            ]
        }
    ]

    with db_manager.get_session() as session:
        for template_data in templates_data:
            # Check if template already exists
            existing = session.query(TaskTemplate).filter(
                TaskTemplate.template_id == template_data['template_id']
            ).first()

            if not existing:
                template = TaskTemplate(**template_data)
                session.add(template)
                logger.info(f"Created task template: {template_data['template_id']}")

        session.commit()

    logger.info("Database initialization completed")
