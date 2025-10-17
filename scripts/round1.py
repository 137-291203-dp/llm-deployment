"""
Round 1 task distribution script for LLM Deployment System.

This script handles distributing round 1 tasks to students based on
their submissions in the Google Form or database.
"""

import csv
import json
import time
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import requests

from .config import config
from .database import db_manager, TaskStatus
from .logger import get_logger, log_request_info
from .task_generator import get_task_generator

logger = get_logger(__name__)


class Round1Distributor:
    """Handles round 1 task distribution."""

    def __init__(self):
        self.task_generator = get_task_generator()
        self.distribution_log = []

    def load_submissions_from_csv(self, csv_file: str) -> List[Dict[str, Any]]:
        """Load student submissions from CSV file."""
        submissions = []

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Validate required fields
                    if not all(k in row for k in ['email', 'endpoint', 'secret']):
                        logger.warning(f"Skipping invalid submission row: {row}")
                        continue

                    submissions.append({
                        'email': row['email'].strip(),
                        'endpoint': row['endpoint'].strip(),
                        'secret': row['secret'].strip(),
                        'github_username': row.get('github_username', '').strip(),
                        'github_repo_url': row.get('github_repo_url', '').strip(),
                        'submitted_at': row.get('timestamp', datetime.now(timezone.utc).isoformat())
                    })

            logger.info(f"Loaded {len(submissions)} submissions from {csv_file}")
            return submissions

        except Exception as e:
            logger.error(f"Failed to load submissions from {csv_file}: {e}")
            raise

    def distribute_tasks(self, submissions: List[Dict[str, Any]], delay: float = 1.0) -> Dict[str, Any]:
        """Distribute tasks to all submissions."""
        results = {
            'total': len(submissions),
            'successful': 0,
            'failed': 0,
            'errors': []
        }

        logger.info(f"Starting distribution to {len(submissions)} submissions")

        for i, submission in enumerate(submissions):
            try:
                logger.info(f"Processing submission {i+1}/{len(submissions)}: {submission['email']}")

                # Check if student already has a round 1 task
                existing_tasks = db_manager.get_tasks_by_submission(
                    db_manager.get_submission_by_email(submission['email']).id,
                    round=1
                )

                if existing_tasks:
                    logger.info(f"Student {submission['email']} already has round 1 tasks, skipping")
                    continue

                # Generate task for student
                task = self.task_generator.generate_task(
                    email=submission['email'],
                    round_num=1
                )

                # Send task to student's endpoint
                success = self._send_task_to_student(submission, task, delay)

                if success:
                    results['successful'] += 1

                    # Store in database
                    db_submission = db_manager.create_submission(
                        email=submission['email'],
                        endpoint=submission['endpoint'],
                        secret=submission['secret'],
                        github_username=submission.get('github_username'),
                        github_repo_url=submission.get('github_repo_url')
                    )

                    db_task = db_manager.create_task(db_submission.id, task)
                    db_manager.update_task_status(task['task_id'], TaskStatus.SENT)

                    self.distribution_log.append({
                        'email': submission['email'],
                        'task_id': task['task_id'],
                        'status': 'sent',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })

                else:
                    results['failed'] += 1
                    self.distribution_log.append({
                        'email': submission['email'],
                        'status': 'failed',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })

            except Exception as e:
                logger.error(f"Error processing submission {submission['email']}: {e}")
                results['failed'] += 1
                results['errors'].append({
                    'email': submission['email'],
                    'error': str(e)
                })

        logger.info(f"Distribution completed: {results['successful']}/{results['total']} successful")
        return results

    def _send_task_to_student(self, submission: Dict[str, Any], task: Dict[str, Any], delay: float) -> bool:
        """Send task to student's API endpoint."""
        try:
            # Prepare request payload
            payload = {
                'email': submission['email'],
                'secret': submission['secret']
            }

            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'LLM-Deployment-System/1.0'
            }

            # Send request
            response = requests.post(
                submission['endpoint'],
                json=payload,
                headers=headers,
                timeout=30
            )

            # Check response
            if response.status_code == 200:
                logger.info(f"Successfully sent task to {submission['email']}")
                time.sleep(delay)  # Rate limiting
                return True
            else:
                logger.warning(f"Failed to send task to {submission['email']}: HTTP {response.status_code}")
                return False

        except requests.RequestException as e:
            logger.error(f"Request error sending task to {submission['email']}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending task to {submission['email']}: {e}")
            return False

    def save_distribution_log(self, log_file: str = 'distribution_log.json'):
        """Save distribution log to file."""
        try:
            with open(log_file, 'w') as f:
                json.dump(self.distribution_log, f, indent=2)
            logger.info(f"Saved distribution log to {log_file}")
        except Exception as e:
            logger.error(f"Failed to save distribution log: {e}")

    def generate_summary_report(self) -> str:
        """Generate a summary report of the distribution."""
        if not self.distribution_log:
            return "No distribution data available"

        total = len(self.distribution_log)
        sent = len([log for log in self.distribution_log if log['status'] == 'sent'])
        failed = len([log for log in self.distribution_log if log['status'] == 'failed'])

        report = f"""
Round 1 Task Distribution Summary
================================

Total submissions processed: {total}
Successfully sent: {sent}
Failed: {failed}
Success rate: {(sent/total)*100:.1f}%

Timestamp: {datetime.now(timezone.utc).isoformat()}
"""

        return report


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description='Distribute Round 1 tasks to students')
    parser.add_argument('csv_file', help='Path to CSV file with student submissions')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between requests (seconds)')
    parser.add_argument('--log-file', default='distribution_log.json', help='Distribution log file')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without actually sending')

    args = parser.parse_args()

    try:
        distributor = Round1Distributor()

        # Load submissions
        submissions = distributor.load_submissions_from_csv(args.csv_file)

        if args.dry_run:
            print(f"Dry run: Would process {len(submissions)} submissions")
            for submission in submissions[:5]:  # Show first 5
                print(f"  - {submission['email']} -> {submission['endpoint']}")
            if len(submissions) > 5:
                print(f"  ... and {len(submissions) - 5} more")
            return

        # Distribute tasks
        results = distributor.distribute_tasks(submissions, args.delay)

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
        logger.error(f"Distribution failed: {e}")
        exit(1)


if __name__ == '__main__':
    main()
