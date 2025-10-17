"""
Round 2 task distribution script for LLM Deployment System.

This script handles distributing round 2 tasks to students who have
completed their round 1 repositories.
"""

import json
import time
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import requests

from .config import config
from .database import db_manager, TaskStatus, EvaluationStatus
from .logger import get_logger, log_request_info
from .task_generator import get_task_generator
from .db_utils import DatabaseUtils

logger = get_logger(__name__)


class Round2Distributor:
    """Handles round 2 task distribution."""

    def __init__(self):
        self.task_generator = get_task_generator()
        self.distribution_log = []

    def get_eligible_students(self) -> List[Dict[str, Any]]:
        """Get students who are eligible for round 2 tasks."""
        eligible_students = []

        try:
            # Get all submissions with completed repositories
            with db_manager.get_session() as session:
                # Get all submissions
                submissions = session.query(db_manager.Submission).all()

                for submission in submissions:
                    # Check if student has completed round 1
                    round1_tasks = DatabaseUtils.get_tasks_by_submission(session, submission.id, round=1)

                    completed_round1 = any(
                        task.status == TaskStatus.RECEIVED and task.repos
                        for task in round1_tasks
                    )

                    if completed_round1:
                        # Check if student already has round 2 tasks
                        round2_tasks = DatabaseUtils.get_tasks_by_submission(session, submission.id, round=2)

                        if not round2_tasks:
                            eligible_students.append({
                                'submission_id': submission.id,
                                'email': submission.email,
                                'endpoint': submission.endpoint,
                                'secret': submission.secret,
                                'github_username': submission.github_username,
                                'github_repo_url': submission.github_repo_url
                            })

            logger.info(f"Found {len(eligible_students)} students eligible for round 2")
            return eligible_students

        except Exception as e:
            logger.error(f"Failed to get eligible students: {e}")
            raise

    def distribute_tasks(self, students: List[Dict[str, Any]], delay: float = 1.0) -> Dict[str, Any]:
        """Distribute round 2 tasks to eligible students."""
        results = {
            'total': len(students),
            'successful': 0,
            'failed': 0,
            'errors': []
        }

        logger.info(f"Starting round 2 distribution to {len(students)} students")

        for i, student in enumerate(students):
            try:
                logger.info(f"Processing student {i+1}/{len(students)}: {student['email']}")

                # Generate round 2 task for student
                task = self.task_generator.generate_task(
                    email=student['email'],
                    round_num=2
                )

                # Send task to student's endpoint
                success = self._send_task_to_student(student, task, delay)

                if success:
                    results['successful'] += 1

                    # Store in database
                    db_task = db_manager.create_task(student['submission_id'], task)
                    db_manager.update_task_status(task['task_id'], TaskStatus.SENT)

                    self.distribution_log.append({
                        'email': student['email'],
                        'task_id': task['task_id'],
                        'status': 'sent',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })

                else:
                    results['failed'] += 1
                    self.distribution_log.append({
                        'email': student['email'],
                        'status': 'failed',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })

            except Exception as e:
                logger.error(f"Error processing student {student['email']}: {e}")
                results['failed'] += 1
                results['errors'].append({
                    'email': student['email'],
                    'error': str(e)
                })

        logger.info(f"Round 2 distribution completed: {results['successful']}/{results['total']} successful")
        return results

    def _send_task_to_student(self, student: Dict[str, Any], task: Dict[str, Any], delay: float) -> bool:
        """Send round 2 task to student's API endpoint."""
        try:
            # Prepare request payload
            payload = {
                'email': student['email'],
                'secret': student['secret']
            }

            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'LLM-Deployment-System/1.0'
            }

            # Send request
            response = requests.post(
                student['endpoint'],
                json=payload,
                headers=headers,
                timeout=30
            )

            # Check response
            if response.status_code == 200:
                logger.info(f"Successfully sent round 2 task to {student['email']}")
                time.sleep(delay)  # Rate limiting
                return True
            else:
                logger.warning(f"Failed to send round 2 task to {student['email']}: HTTP {response.status_code}")
                return False

        except requests.RequestException as e:
            logger.error(f"Request error sending round 2 task to {student['email']}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending round 2 task to {student['email']}: {e}")
            return False

    def save_distribution_log(self, log_file: str = 'round2_distribution_log.json'):
        """Save distribution log to file."""
        try:
            with open(log_file, 'w') as f:
                json.dump(self.distribution_log, f, indent=2)
            logger.info(f"Saved round 2 distribution log to {log_file}")
        except Exception as e:
            logger.error(f"Failed to save round 2 distribution log: {e}")

    def generate_summary_report(self) -> str:
        """Generate a summary report of the round 2 distribution."""
        if not self.distribution_log:
            return "No round 2 distribution data available"

        total = len(self.distribution_log)
        sent = len([log for log in self.distribution_log if log['status'] == 'sent'])
        failed = len([log for log in self.distribution_log if log['status'] == 'failed'])

        report = f"""
Round 2 Task Distribution Summary
================================

Total students eligible: {total}
Successfully sent: {sent}
Failed: {failed}
Success rate: {(sent/total)*100:.1f}%

Timestamp: {datetime.now(timezone.utc).isoformat()}
"""

        return report


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description='Distribute Round 2 tasks to eligible students')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between requests (seconds)')
    parser.add_argument('--log-file', default='round2_distribution_log.json', help='Distribution log file')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without actually sending')
    parser.add_argument('--min-eligible', type=int, default=1, help='Minimum number of eligible students required')

    args = parser.parse_args()

    try:
        distributor = Round2Distributor()

        # Get eligible students
        students = distributor.get_eligible_students()

        if len(students) < args.min_eligible:
            logger.error(f"Only {len(students)} eligible students found, minimum {args.min_eligible} required")
            exit(1)

        if args.dry_run:
            print(f"Dry run: Would process {len(students)} eligible students")
            for student in students[:5]:  # Show first 5
                print(f"  - {student['email']} -> {student['endpoint']}")
            if len(students) > 5:
                print(f"  ... and {len(students) - 5} more")
            return

        # Distribute tasks
        results = distributor.distribute_tasks(students, args.delay)

        # Save log
        distributor.save_distribution_log(args.log_file)

        # Print summary
        print(distributor.generate_summary_report())

        # Exit with appropriate code
        if results['failed'] == 0:
            exit(0)
        else:
            exit(1)

    except Exception as e:
        logger.error(f"Round 2 distribution failed: {e}")
        exit(1)


if __name__ == '__main__':
    main()
