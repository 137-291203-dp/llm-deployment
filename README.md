# LLM Deployment System

A comprehensive system for LLM-assisted application deployment and evaluation.

## Features

- **Student Task Management**: Distributes coding tasks to students with LLM assistance
- **Repository Evaluation**: Automated evaluation of submitted repositories using static, dynamic, and LLM-based checks
- **GitHub Integration**: Creates repositories, manages GitHub Pages, and validates submissions
- **Multi-round Tasks**: Support for multiple rounds of increasingly complex tasks
- **Comprehensive Logging**: Detailed logging and monitoring of all system activities
- **RESTful API**: Clean API for student submissions and evaluation results

## Quick Start

1. **Setup the system**:
   ```bash
   python core-app/setup.py
   ```

2. **Configure environment**:
   - Copy `config/.env.template` to `config/.env`
   - Update configuration values (GitHub token, API keys, etc.)

3. **Initialize database**:
   ```bash
   python utils/cli.py db init
   ```

4. **Start API server**:
   ```bash
   python core-app/api_server.py
   ```

5. **Distribute tasks**:
   ```bash
   python scripts/round1.py submissions.csv
   ```

## Project Structure

```
llm-deployment-system/
├── core-app/           # Core application files
│   ├── api_server.py   # Main Flask API server
│   ├── evaluation_api.py # Evaluation endpoint
│   ├── evaluate.py     # Repository evaluation
│   ├── setup.py        # System setup script
│   └── database.py     # Database models and manager
├── utils/              # Utility modules
│   ├── config.py       # Configuration management
│   ├── logger.py       # Logging utilities
│   ├── github_utils.py # GitHub API integration
│   ├── task_generator.py # Task template system
│   └── cli.py          # Command-line interface
├── config/             # Configuration files
│   ├── requirements.txt # Python dependencies
│   └── .env.template   # Environment template
├── scripts/            # Distribution scripts
│   ├── round1.py       # Round 1 task distribution
│   └── round2.py       # Round 2 task distribution
└── docs/               # Documentation
```

## API Endpoints

### Student API

- `POST /api/request` - Request a new task
- `POST /api/evaluate` - Submit repository for evaluation

### Admin API

- `GET /evaluate/status/<task_id>` - Get evaluation status
- `GET /evaluate/results/<task_id>` - Get evaluation results

## Configuration

The system uses environment variables for configuration. Key settings:

- `DATABASE_URL` - Database connection string
- `GITHUB_TOKEN` - GitHub personal access token
- `SECRET_KEY` - Flask application secret
- `API_HOST` / `API_PORT` - Server binding
- `LOG_LEVEL` - Logging level

## Development

### Running Tests

```bash
python -m pytest tests/
```

### Database Management

```bash
python utils/cli.py db init      # Initialize database
python utils/cli.py db stats     # Show statistics
python utils/cli.py db cleanup   # Clean old records
```

### Task Management

```bash
python utils/cli.py task generate student@example.com
python utils/cli.py task list --email student@example.com
```

## Deployment

### Docker

```bash
docker build -f docker/Dockerfile -t llm-deployment .
docker-compose up
```

### Kubernetes

```bash
kubectl apply -f k8s/
```

## License

MIT License - see LICENSE file for details.
