"""
Setup script for LLM Deployment System.

This script initializes the system, creates necessary directories,
installs dependencies, and sets up the database.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional

from utils.config import config
from .database import init_database
from utils.logger import get_logger

logger = get_logger(__name__)


class SetupManager:
    """Manages system setup and initialization."""

    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.system_root = self.project_root / "llm-deployment-system"

    def check_requirements(self) -> List[str]:
        """Check if system requirements are met."""
        issues = []

        # Check Python version
        python_version = sys.version_info
        if python_version < (3, 8):
            issues.append(f"Python {python_version.major}.{python_version.minor} is not supported. Please use Python 3.8 or higher.")

        # Check if we're in the right directory
        if not (self.system_root / "config" / "requirements.txt").exists():
            issues.append("requirements.txt not found. Are you in the correct directory?")

        # Check for git
        try:
            subprocess.run(['git', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            issues.append("Git is not installed or not in PATH")

        return issues

    def create_directories(self) -> bool:
        """Create necessary directories."""
        try:
            directories = [
                self.system_root / "data",
                self.system_root / "logs",
                self.system_root / "backups",
                self.system_root / "uploads",
                self.system_root / "config",
                self.system_root / "core-app",
                self.system_root / "utils",
                self.system_root / "scripts",
                self.system_root / "tests",
                self.system_root / "docs"
            ]

            for directory in directories:
                directory.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created directory: {directory}")

            return True

        except Exception as e:
            logger.error(f"Failed to create directories: {e}")
            return False

    def install_dependencies(self) -> bool:
        """Install Python dependencies."""
        try:
            requirements_file = self.system_root / "config" / "requirements.txt"

            if not requirements_file.exists():
                logger.warning("requirements.txt not found, skipping dependency installation")
                return True

            logger.info("Installing Python dependencies...")
            subprocess.run([
                sys.executable, '-m', 'pip', 'install', '-r', str(requirements_file)
            ], check=True)

            logger.info("Dependencies installed successfully")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during dependency installation: {e}")
            return False

    def setup_environment(self) -> bool:
        """Setup environment files."""
        try:
            env_template = self.system_root / "config" / ".env.template"
            env_file = self.system_root / "config" / ".env"

            if env_template.exists() and not env_file.exists():
                shutil.copy(env_template, env_file)
                logger.info("Created .env file from template")

                # Generate a secure secret key
                import secrets
                secret_key = secrets.token_hex(32)

                # Update the .env file with generated secret
                with open(env_file, 'r') as f:
                    content = f.read()

                content = content.replace(
                    'SECRET_KEY=your-secret-key-here',
                    f'SECRET_KEY={secret_key}'
                )

                with open(env_file, 'w') as f:
                    f.write(content)

                logger.info("Generated secure secret key in .env file")
            else:
                logger.info(".env file already exists or template not found")

            return True

        except Exception as e:
            logger.error(f"Failed to setup environment: {e}")
            return False

    def initialize_database(self) -> bool:
        """Initialize the database."""
        try:
            logger.info("Initializing database...")
            init_database()
            logger.info("Database initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            return False

    def setup_logging(self) -> bool:
        """Setup logging configuration."""
        try:
            # Create logs directory if it doesn't exist
            logs_dir = self.system_root / "logs"
            logs_dir.mkdir(exist_ok=True)

            logger.info("Logging setup completed")
            return True

        except Exception as e:
            logger.error(f"Failed to setup logging: {e}")
            return False

    def run_tests(self) -> bool:
        """Run basic tests to verify installation."""
        try:
            logger.info("Running basic tests...")

            # Test database connection
            from .database import db_manager
            with db_manager.get_session() as session:
                session.execute("SELECT 1")
                logger.info("Database connection test passed")

            # Test task generation
            from .task_generator import get_task_generator
            task_gen = get_task_generator()
            task = task_gen.generate_task("test@example.com")
            logger.info(f"Task generation test passed: {task['task_id']}")

            logger.info("All tests passed")
            return True

        except Exception as e:
            logger.error(f"Tests failed: {e}")
            return False

    def setup_complete(self) -> bool:
        """Mark setup as complete."""
        try:
            complete_file = self.system_root / ".setup_complete"
            complete_file.write_text(f"Setup completed on {datetime.now().isoformat()}\n")
            return True
        except Exception as e:
            logger.error(f"Failed to mark setup complete: {e}")
            return False

    def is_setup_complete(self) -> bool:
        """Check if setup has been completed."""
        complete_file = self.system_root / ".setup_complete"
        return complete_file.exists()

    def run_setup(self, skip_dependencies: bool = False, skip_tests: bool = False) -> bool:
        """Run complete setup process."""
        logger.info("Starting LLM Deployment System setup...")

        # Check requirements
        issues = self.check_requirements()
        if issues:
            logger.error("System requirements not met:")
            for issue in issues:
                logger.error(f"  - {issue}")
            return False

        # Create directories
        if not self.create_directories():
            return False

        # Setup environment
        if not self.setup_environment():
            return False

        # Setup logging
        if not self.setup_logging():
            return False

        # Install dependencies
        if not skip_dependencies and not self.install_dependencies():
            logger.warning("Dependency installation failed, but continuing setup")

        # Initialize database
        if not self.initialize_database():
            return False

        # Run tests
        if not skip_tests and not self.run_tests():
            logger.warning("Tests failed, but setup completed")

        # Mark setup complete
        if not self.setup_complete():
            return False

        logger.info("Setup completed successfully!")
        return True


def main():
    """Main setup function."""
    parser = argparse.ArgumentParser(description='Setup LLM Deployment System')
    parser.add_argument('--project-root', help='Project root directory')
    parser.add_argument('--skip-dependencies', action='store_true', help='Skip dependency installation')
    parser.add_argument('--skip-tests', action='store_true', help='Skip running tests')
    parser.add_argument('--check-only', action='store_true', help='Only check if setup is complete')

    args = parser.parse_args()

    setup_manager = SetupManager(args.project_root)

    if args.check_only:
        if setup_manager.is_setup_complete():
            print("✓ System is already set up")
            return 0
        else:
            print("✗ System setup is not complete")
            return 1

    success = setup_manager.run_setup(
        skip_dependencies=args.skip_dependencies,
        skip_tests=args.skip_tests
    )

    if success:
        print("\n🎉 Setup completed successfully!")
        print("\nNext steps:")
        print("1. Review and update config/.env file with your settings")
        print("2. Set up your GitHub personal access token")
        print("3. Run 'python utils/cli.py system status' to verify everything works")
        print("4. Start the API server with 'python core-app/api_server.py'")
        return 0
    else:
        print("\n❌ Setup failed!")
        return 1


if __name__ == '__main__':
    sys.exit(main())
