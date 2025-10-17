#!/usr/bin/env python
"""
System Health Check for LLM Deployment System.

This script checks:
1. Environment variables and config loading
2. Database path
3. Logging setup
4. API keys
5. CORS configuration
6. Redis configuration
"""

import sys
from utils.config import config, setup_logging
import logging
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
dotenv_path = Path(__file__).resolve().parent.parent / 'config/.env'
load_dotenv(dotenv_path)

def main():
    print("=== LLM Deployment System Health Check ===\n")

    # 1. Setup logging
    try:
        setup_logging()
        logger = logging.getLogger("health_check")
        logger.info("Logging setup successful")
        print("[OK] Logging setup successful")
    except Exception as e:
        print("[ERROR] Logging setup failed:", e)
        sys.exit(1)

    # 2. Check basic config values
    try:
        print(f"DATABASE_URL: {config.get_database_url()}")
        print(f"FLASK_ENV: {config.FLASK_ENV}")
        print(f"FLASK_DEBUG: {config.FLASK_DEBUG}")
        print(f"CORS_ORIGINS: {config.CORS_ORIGINS}")
        print(f"GITHUB_TOKEN set: {bool(config.GITHUB_TOKEN)}")
        print(f"OPENAI_API_KEY set: {bool(config.OPENAI_API_KEY)}")
        print(f"ANTHROPIC_API_KEY set: {bool(config.ANTHROPIC_API_KEY)}")
        print(f"UPLOAD_FOLDER exists: {os.path.exists(config.UPLOAD_FOLDER)}")
        print(f"Log file path: {config.get_log_file_path()}")
        print("[OK] Config loaded successfully")
    except Exception as e:
        print("[ERROR] Config loading failed:", e)
        sys.exit(1)

    # 3. Validate configuration
    issues = config.validate_config()
    if issues:
        print("[WARNING] Configuration issues found:")
        for key, issue in issues.items():
            print(f"  {key}: {issue}")
    else:
        print("[OK] Configuration validated successfully")

    # 4. Check Redis / Celery config
    try:
        redis_config = config.get_redis_config()
        print(f"Redis URL: {redis_config['url']}")
        print(f"Celery Broker: {redis_config['broker_url']}")
        print(f"Celery Result Backend: {redis_config['result_backend']}")
        print("[OK] Redis/Celery configuration loaded")
    except Exception as e:
        print("[ERROR] Redis/Celery config failed:", e)

    print("\n=== Health Check Complete ===")
    print("If all [OK] checks pass and no critical issues are listed, your environment is ready!")

if __name__ == "__main__":
    main()
