"""
Command-line interface for LLM Deployment System.

This module provides a comprehensive CLI for managing the system,
including database operations, task management, and system administration.
"""

import sys
import os

# Add the parent directory to sys.path so we can import from the project root
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

import argparse
import json
from typing import Optional
from datetime import datetime

from utils.config import config
from coreapp.database import db_manager, init_database
from utils.logger import get_logger
from utils.task_generator import get_task_generator
from utils.github_utils import get_github_manager
from utils.db_utils import DatabaseUtils

logger = get_logger(__name__)


class CLI:
    """Main CLI class."""

    def __init__(self):
        self.parser = argparse.ArgumentParser(
            description='LLM Deployment System CLI',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  python cli.py db init                    # Initialize database
  python cli.py db stats                   # Show database statistics
  python cli.py task generate student@example.com  # Generate task for student
  python cli.py task list                  # List all tasks
  python cli.py github validate https://github.com/user/repo  # Validate repo
  python cli.py system status              # Show system status
            """
        )

        self.subparsers = self.parser.add_subparsers(dest='command', help='Available commands')

        # Database commands
        self._setup_db_commands()

        # Task commands
        self._setup_task_commands()

        # GitHub commands
        self._setup_github_commands()

        # System commands
        self._setup_system_commands()

    def _setup_db_commands(self):
        """Setup database-related commands."""
        db_parser = self.subparsers.add_parser('db', help='Database operations')
        db_subparsers = db_parser.add_subparsers(dest='db_command', help='Database commands')

        # db init
        db_subparsers.add_parser('init', help='Initialize database with default data')

        # db stats
        db_subparsers.add_parser('stats', help='Show database statistics')

        # db cleanup
        cleanup_parser = db_subparsers.add_parser('cleanup', help='Clean up old records')
        cleanup_parser.add_argument('--days', type=int, default=30, help='Days to keep (default: 30)')

        # db export
        export_parser = db_subparsers.add_parser('export', help='Export submission data')
        export_parser.add_argument('submission_id', type=int, help='Submission ID to export')
        export_parser.add_argument('--output', '-o', help='Output file (default: stdout)')

    def _setup_task_commands(self):
        """Setup task-related commands."""
        task_parser = self.subparsers.add_parser('task', help='Task operations')
        task_subparsers = task_parser.add_subparsers(dest='task_command', help='Task commands')

        # task generate
        generate_parser = task_subparsers.add_parser('generate', help='Generate a task')
        generate_parser.add_argument('email', help='Student email')
        generate_parser.add_argument('--template', help='Task template ID')
        generate_parser.add_argument('--round', type=int, default=1, choices=[1, 2], help='Round number')

        # task list
        list_parser = task_subparsers.add_parser('list', help='List tasks')
        list_parser.add_argument('--email', help='Filter by email')
        list_parser.add_argument('--status', help='Filter by status')
        list_parser.add_argument('--round', type=int, help='Filter by round')

        # task show
        show_parser = task_subparsers.add_parser('show', help='Show task details')
        show_parser.add_argument('task_id', help='Task ID to show')

    def _setup_github_commands(self):
        """Setup GitHub-related commands."""
        github_parser = self.subparsers.add_parser('github', help='GitHub operations')
        github_subparsers = github_parser.add_subparsers(dest='github_command', help='GitHub commands')

        # github validate
        validate_parser = github_subparsers.add_parser('validate', help='Validate GitHub repository')
        validate_parser.add_argument('repo_url', help='Repository URL to validate')

        # github create-repo
        create_parser = github_subparsers.add_parser('create-repo', help='Create a test repository')
        create_parser.add_argument('name', help='Repository name')
        create_parser.add_argument('--description', default='', help='Repository description')

    def _setup_system_commands(self):
        """Setup system-related commands."""
        system_parser = self.subparsers.add_parser('system', help='System operations')
        system_subparsers = system_parser.add_subparsers(dest='system_command', help='System commands')

        # system status
        system_subparsers.add_parser('status', help='Show system status')

        # system config
        config_parser = system_subparsers.add_parser('config', help='Show configuration')
        config_parser.add_argument('--validate', action='store_true', help='Validate configuration')

    def run(self, args: Optional[list] = None):
        """Run the CLI with provided arguments."""
        parsed_args = self.parser.parse_args(args)

        if not parsed_args.command:
            self.parser.print_help()
            return

        try:
            if parsed_args.command == 'db':
                self._handle_db_command(parsed_args)
            elif parsed_args.command == 'task':
                self._handle_task_command(parsed_args)
            elif parsed_args.command == 'github':
                self._handle_github_command(parsed_args)
            elif parsed_args.command == 'system':
                self._handle_system_command(parsed_args)
            else:
                self.parser.print_help()

        except Exception as e:
            logger.error(f"CLI error: {e}")
            print(f"Error: {e}")
            sys.exit(1)

    def _handle_db_command(self, args):
        """Handle database commands."""
        if args.db_command == 'init':
            print("Initializing database...")
            init_database()
            print("Database initialized successfully")

        elif args.db_command == 'stats':
            with db_manager.get_session() as session:
                stats = DatabaseUtils.get_system_stats(session)
                print("Database Statistics:")
                print(f"  Submissions: {stats['submissions']}")
                print(f"  Tasks: {stats['tasks']}")
                print(f"  Repositories: {stats['repositories']}")
                print(f"  Evaluations: {stats['evaluations']}")
                print(f"  Task completion rate: {stats['task_completion_rate']:.1f}%")
                print(f"  Evaluation completion rate: {stats['evaluation_completion_rate']:.1f}%")

        elif args.db_command == 'cleanup':
            with db_manager.get_session() as session:
                deleted = DatabaseUtils.cleanup_old_records(session, args.days)
                print(f"Cleaned up {deleted} old records")

        elif args.db_command == 'export':
            with db_manager.get_session() as session:
                data = DatabaseUtils.export_submission_data(session, args.submission_id)

                if not data:
                    print(f"No data found for submission {args.submission_id}")
                    return

                if args.output:
                    with open(args.output, 'w') as f:
                        json.dump(data, f, indent=2)
                    print(f"Exported data to {args.output}")
                else:
                    print(json.dumps(data, indent=2))

        else:
            print("Unknown database command")

    def _handle_task_command(self, args):
        """Handle task commands."""
        if args.task_command == 'generate':
            task_generator = get_task_generator()
            task = task_generator.generate_task(
                email=args.email,
                template_id=args.template,
                round_num=args.round
            )

            print(f"Generated task {task['task_id']} for {args.email}:")
            print(f"  Round: {task['round']}")
            print(f"  Brief: {task['brief'][:100]}...")
            print(f"  Checks: {len(task['checks'])} checks")
            print(f"  Attachments: {len(task['attachments'])} attachments")

        elif args.task_command == 'list':
            with db_manager.get_session() as session:
                query = session.query(db_manager.Task)

                if args.email:
                    submission = session.query(db_manager.Submission).filter(
                        db_manager.Submission.email == args.email
                    ).first()
                    if submission:
                        query = query.filter(db_manager.Task.submission_id == submission.id)

                if args.status:
                    query = query.filter(db_manager.Task.status == args.status)

                if args.round:
                    query = query.filter(db_manager.Task.round == args.round)

                tasks = query.all()

                print(f"Found {len(tasks)} tasks:")
                for task in tasks:
                    print(f"  {task.task_id} - {task.status} - Round {task.round} - {task.submission.email}")

        elif args.task_command == 'show':
            task = db_manager.get_task_by_id(args.task_id)
            if not task:
                print(f"Task {args.task_id} not found")
                return

            print(f"Task: {task.task_id}")
            print(f"  Status: {task.status}")
            print(f"  Round: {task.round}")
            print(f"  Email: {task.submission.email}")
            print(f"  Brief: {task.brief}")
            print(f"  Checks: {len(task.checks)}")
            print(f"  Attachments: {len(task.attachments)}")
            print(f"  Sent: {task.sent_at}")
            print(f"  Received: {task.received_at}")

        else:
            print("Unknown task command")

    def _handle_github_command(self, args):
        """Handle GitHub commands."""
        if args.github_command == 'validate':
            try:
                github_manager = get_github_manager()
                validation = github_manager.validate_repository(args.repo_url)

                print(f"Repository validation for {args.repo_url}:")
                print(f"  Valid: {validation.get('valid', False)}")
                if 'error' in validation:
                    print(f"  Error: {validation['error']}")
                if validation.get('valid'):
                    print(f"  License: {validation.get('has_license', False)}")
                    print(f"  README: {validation.get('has_readme', False)}")
                    print(f"  Languages: {list(validation.get('languages', {}).keys())}")
                    print(f"  Pages: {validation.get('pages_enabled', False)}")
                    if validation.get('pages_url'):
                        print(f"  Pages URL: {validation['pages_url']}")

            except Exception as e:
                print(f"GitHub validation failed: {e}")

        elif args.github_command == 'create-repo':
            try:
                github_manager = get_github_manager()
                repo = github_manager.create_repository(
                    name=args.name,
                    description=args.description
                )
                print(f"Created repository: {repo.full_name}")
                print(f"URL: {repo.html_url}")

            except Exception as e:
                print(f"Repository creation failed: {e}")

        else:
            print("Unknown GitHub command")

    def _handle_system_command(self, args):
        """Handle system commands."""
        if args.system_command == 'status':
            print("System Status:")
            print(f"  Database: {'Connected' if db_manager else 'Disconnected'}")
            print(f"  GitHub Integration: {'Enabled' if config.ENABLE_GITHUB_INTEGRATION else 'Disabled'}")
            print(f"  Environment: {config.DEPLOYMENT_ENV}")
            print(f"  Log Level: {config.LOG_LEVEL}")

            # Check for any configuration issues
            issues = config.validate_config()
            if issues:
                print("  Configuration Issues:")
                for issue in issues:
                    print(f"    - {issue}")
            else:
                print("  Configuration: Valid")

        elif args.system_command == 'config':
            if args.validate:
                issues = config.validate_config()
                if issues:
                    print("Configuration issues found:")
                    for key, issue in issues.items():
                        print(f"  {key}: {issue}")
                    sys.exit(1)
                else:
                    print("Configuration is valid!")
            else:
                print("Current Configuration:")
                print(f"  Database URL: {config.DATABASE_URL}")
                print(f"  API Host: {config.API_HOST}")
                print(f"  API Port: {config.API_PORT}")
                print(f"  GitHub Token: {'Set' if config.GITHUB_TOKEN else 'Not set'}")
                print(f"  Log Level: {config.LOG_LEVEL}")

        else:
            print("Unknown system command")


def main():
    """Main entry point for CLI."""
    cli = CLI()
    cli.run()


if __name__ == '__main__':
    main()
