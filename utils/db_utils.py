"""
Database utility functions for LLM Deployment System.

This module provides helper functions for common database operations.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from coreapp.database import (
    Submission, Task, Repository, Evaluation, TaskTemplate,
    TaskStatus, EvaluationStatus, db_manager
)
from utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseUtils:
    """Utility class for database operations."""

    @staticmethod
    def get_or_create_submission(session: Session, email: str, endpoint: str, secret: str) -> Submission:
        """Get existing submission or create new one."""
        submission = session.query(Submission).filter(
            Submission.email == email,
            Submission.endpoint == endpoint
        ).first()

        if not submission:
            submission = Submission(email=email, endpoint=endpoint, secret=secret)
            session.add(submission)
            session.commit()
            session.refresh(submission)
            logger.info(f"Created new submission for {email}")

        return submission

    @staticmethod
    def get_pending_tasks(session: Session) -> List[Task]:
        """Get all pending tasks."""
        return session.query(Task).filter(Task.status == TaskStatus.PENDING).all()

    @staticmethod
    def get_tasks_for_evaluation(session: Session) -> List[Task]:
        """Get tasks that have repositories submitted and need evaluation."""
        return session.query(Task).filter(
            Task.status == TaskStatus.RECEIVED,
            Task.repos.any()
        ).all()

    @staticmethod
    def get_completed_evaluations(session: Session, repository_id: int) -> List[Evaluation]:
        """Get all completed evaluations for a repository."""
        return session.query(Evaluation).filter(
            Evaluation.repository_id == repository_id,
            Evaluation.status.in_([EvaluationStatus.PASSED, EvaluationStatus.FAILED])
        ).all()

    @staticmethod
    def calculate_repository_score(session: Session, repository_id: int) -> float:
        """Calculate overall score for a repository based on evaluations."""
        evaluations = DatabaseUtils.get_completed_evaluations(session, repository_id)

        if not evaluations:
            return 0.0

        total_score = sum(evaluation.score or 0 for evaluation in evaluations)
        return total_score / len(evaluations)

    @staticmethod
    def get_submission_stats(session: Session, submission_id: int) -> Dict[str, Any]:
        """Get statistics for a submission."""
        tasks = session.query(Task).filter(Task.submission_id == submission_id).all()

        stats = {
            'total_tasks': len(tasks),
            'completed_tasks': len([t for t in tasks if t.status == TaskStatus.COMPLETED]),
            'failed_tasks': len([t for t in tasks if t.status == TaskStatus.FAILED]),
            'total_repositories': 0,
            'average_score': 0.0
        }

        # Count repositories and calculate scores
        repo_scores = []
        for task in tasks:
            stats['total_repositories'] += len(task.repos)
            for repo in task.repos:
                score = DatabaseUtils.calculate_repository_score(session, repo.id)
                repo_scores.append(score)

        if repo_scores:
            stats['average_score'] = sum(repo_scores) / len(repo_scores)

        return stats

    @staticmethod
    def get_system_stats(session: Session) -> Dict[str, Any]:
        """Get overall system statistics."""
        total_submissions = session.query(Submission).count()
        total_tasks = session.query(Task).count()
        total_repositories = session.query(Repository).count()
        total_evaluations = session.query(Evaluation).count()

        # Calculate completion rates
        completed_tasks = session.query(Task).filter(Task.status == TaskStatus.COMPLETED).count()
        completed_evaluations = session.query(Evaluation).filter(
            Evaluation.status.in_([EvaluationStatus.PASSED, EvaluationStatus.FAILED])
        ).count()

        return {
            'submissions': total_submissions,
            'tasks': total_tasks,
            'repositories': total_repositories,
            'evaluations': total_evaluations,
            'task_completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            'evaluation_completion_rate': (completed_evaluations / total_evaluations * 100) if total_evaluations > 0 else 0,
        }

    @staticmethod
    def cleanup_old_records(session: Session, days: int = 30) -> int:
        """Clean up old records older than specified days."""
        cutoff_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # This is a simplified cleanup - in production you might want more sophisticated logic
        deleted_count = 0

        # Note: In a real implementation, you'd want to be more careful about what to delete
        # and potentially archive data instead of deleting it

        session.commit()
        return deleted_count

    @staticmethod
    def export_submission_data(session: Session, submission_id: int) -> Dict[str, Any]:
        """Export all data for a submission for analysis."""
        submission = session.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            return {}

        tasks = []
        for task in submission.tasks:
            task_data = {
                'task_id': task.task_id,
                'round': task.round,
                'status': task.status.value,
                'brief': task.brief,
                'sent_at': task.sent_at.isoformat() if task.sent_at else None,
                'received_at': task.received_at.isoformat() if task.received_at else None,
                'repositories': []
            }

            for repo in task.repos:
                repo_data = {
                    'repo_url': repo.repo_url,
                    'commit_sha': repo.commit_sha,
                    'pages_url': repo.pages_url,
                    'submitted_at': repo.submitted_at.isoformat() if repo.submitted_at else None,
                    'evaluations': []
                }

                for evaluation in repo.evaluations:
                    repo_data['evaluations'].append({
                        'check_name': evaluation.check_name,
                        'status': evaluation.status.value,
                        'score': evaluation.score,
                        'reason': evaluation.reason,
                        'evaluated_at': evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else None
                    })

                task_data['repositories'].append(repo_data)
            tasks.append(task_data)

        return {
            'submission': {
                'id': submission.id,
                'email': submission.email,
                'endpoint': submission.endpoint,
                'created_at': submission.created_at.isoformat() if submission.created_at else None
            },
            'tasks': tasks,
            'stats': DatabaseUtils.get_submission_stats(session, submission_id)
        }


def get_db_utils() -> DatabaseUtils:
    """Get database utilities instance."""
    return DatabaseUtils
