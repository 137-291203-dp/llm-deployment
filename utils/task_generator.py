"""
Task generation system for LLM Deployment System.

This module handles creating randomized tasks based on templates,
with seed generation for reproducible but varied task instances.
"""

import json
import random
import hashlib
import base64
import uuid
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

# Simplified imports - adjust based on your project structure
try:
    from config import Config
    from logger import setup_logger
    logger = setup_logger('task_generator', 'task_generator.log')
except ImportError:
    # Fallback for standalone usage
    import logging
    logger = logging.getLogger(__name__)
    
    class Config:
        API_HOST = os.getenv('API_HOST', 'http://localhost')
        API_PORT = os.getenv('EVAL_SERVER_PORT', '5001')


class SeedGenerator:
    """Generates seeds for task randomization."""

    @staticmethod
    def generate_seed(email: str, date_string: str) -> str:
        """Generate a deterministic seed based on email and date."""
        # Create a hash from email and date for deterministic but unique seeds
        seed_data = f"{email}:{date_string}"
        seed_hash = hashlib.sha256(seed_data.encode()).hexdigest()
        return seed_hash[:16]  # Use first 16 characters

    @staticmethod
    def generate_random_data(seed: str, data_type: str = "string", length: int = 10) -> Any:
        """Generate random data based on seed."""
        # Create a new Random instance to avoid affecting global state
        rng = random.Random(seed)

        if data_type == "string":
            chars = "abcdefghijklmnopqrstuvwxyz0123456789"
            return ''.join(rng.choice(chars) for _ in range(length))
        
        elif data_type == "number":
            return rng.randint(1000, 99999)
        
        elif data_type == "csv_data":
            # Generate sample CSV data for sales example
            products = ["Product A", "Product B", "Product C", "Product D"]
            rng.shuffle(products)
            csv_data = "Product,Sales,Region\n"
            total = 0
            for product in products[:rng.randint(2, 4)]:
                sales = rng.randint(100, 1000)
                region = rng.choice(["North", "South", "East", "West"])
                csv_data += f"{product},{sales},{region}\n"
                total += sales
            return csv_data, total
        
        elif data_type == "markdown":
            # Generate sample markdown content
            content = f"""# Sample Markdown Content

This is a sample markdown file generated for task {seed[:8]}.

## Features

- Random seed: {seed}
- Generated at: {datetime.now().isoformat()}
- Contains various markdown elements

### Code Example

```python
def hello_world():
    print("Hello, World!")
    return "success"
```

### Lists

1. Item one
2. Item two
3. Item three

- Bullet item A
- Bullet item B
- Bullet item C

> This is a blockquote with some **bold** and *italic* text.

| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Data 1   | Data 2   | Data 3   |
| Data 4   | Data 5   | Data 6   |
"""
            return content
        
        elif data_type == "json":
            # Generate sample JSON data
            return {
                "currencies": {
                    "USD": 1.0,
                    "EUR": 0.85,
                    "GBP": 0.73,
                    "JPY": 110.0,
                    "CAD": 1.25
                },
                "metadata": {
                    "seed": seed,
                    "generated_at": datetime.now().isoformat()
                }
            }

        return None


class TaskTemplate:
    """Represents a task template with configuration for rounds."""

    def __init__(self, template_id: str, data: Dict[str, Any]):
        self.template_id = template_id
        self.name = data.get('name', '')
        self.description = data.get('description', '')

        # Round 1 configuration
        self.brief_template = data.get('brief_template', '')
        self.checks_template = data.get('checks_template', [])
        self.attachments_template = data.get('attachments_template', [])

        # Round 2 configuration
        self.round2_brief_template = data.get('round2_brief_template', '')
        self.round2_checks_template = data.get('round2_checks_template', [])
        self.round2_attachments_template = data.get('round2_attachments_template', [])

        # Seed configuration
        self.seed_config = data.get('seed_config', {})
        
        # Cache for computed results (to ensure consistency within a task)
        self._result_cache = {}

    def generate_task(self, seed: str, round_num: int = 1, evaluation_url: str = None) -> Dict[str, Any]:
        """Generate a task instance from this template."""
        # Clear cache for new task generation
        self._result_cache = {}
        
        # Create RNG instance
        rng = random.Random(seed)

        if round_num == 1:
            brief = self._process_template(self.brief_template, seed, rng)
            checks = self._process_checks_template(self.checks_template, seed, rng)
            attachments = self._process_attachments_template(self.attachments_template, seed, rng)
        elif round_num == 2:
            if not self.round2_brief_template:
                raise ValueError(f"Round 2 not configured for template {self.template_id}")
            brief = self._process_template(self.round2_brief_template, seed, rng)
            checks = self._process_checks_template(self.round2_checks_template, seed, rng)
            attachments = self._process_attachments_template(
                self.round2_attachments_template if self.round2_attachments_template else [], 
                seed, 
                rng
            )
        else:
            raise ValueError(f"Invalid round number: {round_num}")

        # Generate task ID
        task_suffix = hashlib.md5(f"{self.template_id}:{seed}".encode()).hexdigest()[:5]
        task_id = f"{self.template_id}-{task_suffix}"
        
        # Generate nonce
        try:
            nonce = str(uuid.uuid7())
        except AttributeError:
            nonce = str(uuid.uuid4())

        # Set evaluation URL
        if evaluation_url is None:
            try:
                evaluation_url = f"{Config.API_HOST}:{Config.API_PORT}/api/evaluate"
            except:
                evaluation_url = "http://localhost:5001/api/evaluate"

        return {
            'task_id': task_id,
            'round': round_num,
            'nonce': nonce,
            'brief': brief,
            'checks': checks,
            'attachments': attachments,
            'evaluation_url': evaluation_url
        }

    def _get_result_value(self, seed: str, rng: random.Random) -> int:
        """Get or compute result value (cached for consistency)."""
        if 'result' not in self._result_cache:
            if 'sales' in self.brief_template.lower():
                _, total = SeedGenerator.generate_random_data(seed, "csv_data")
                self._result_cache['result'] = total
            else:
                self._result_cache['result'] = rng.randint(1000, 9999)
        return self._result_cache['result']

    def _process_template(self, template: str, seed: str, rng: random.Random) -> str:
        """Process template string with seed data."""
        processed = template.replace('{seed}', seed[:8])

        # Handle result replacement
        if '{result}' in processed:
            result = self._get_result_value(seed, rng)
            processed = processed.replace('{result}', str(result))

        return processed

    def _process_checks_template(self, checks: List[str], seed: str, rng: random.Random) -> List[str]:
        """Process checks template with seed data."""
        processed_checks = []

        for check in checks:
            processed = check.replace('{seed}', seed[:8])

            # Handle result replacement in checks
            if '{result}' in processed:
                result = self._get_result_value(seed, rng)
                processed = processed.replace('{result}', str(result))

            processed_checks.append(processed)

        return processed_checks

    def _process_attachments_template(self, attachments: List[Dict], seed: str, rng: random.Random) -> List[Dict]:
        """Process attachments template with seed data."""
        processed_attachments = []

        for attachment in attachments:
            processed = attachment.copy()

            if 'url' in processed and processed['url']:
                url = processed['url']

                if '{seed}' in url or url.startswith('data:text/csv;base64,{seed}'):
                    # Generate CSV data
                    csv_data, _ = SeedGenerator.generate_random_data(seed, "csv_data")
                    encoded_data = base64.b64encode(csv_data.encode()).decode()
                    processed['url'] = f"data:text/csv;base64,{encoded_data}"

                elif url.startswith('data:text/markdown;base64,{seed}'):
                    # Generate markdown data
                    markdown_data = SeedGenerator.generate_random_data(seed, "markdown")
                    encoded_data = base64.b64encode(markdown_data.encode()).decode()
                    processed['url'] = f"data:text/markdown;base64,{encoded_data}"

                elif url.startswith('data:application/json;base64,{seed}'):
                    # Generate JSON data
                    json_data = SeedGenerator.generate_random_data(seed, "json")
                    encoded_data = base64.b64encode(json.dumps(json_data).encode()).decode()
                    processed['url'] = f"data:application/json;base64,{encoded_data}"

            processed_attachments.append(processed)

        return processed_attachments


class TaskGenerator:
    """Main task generator class."""

    def __init__(self):
        self.templates = {}
        self._load_default_templates()

    def _load_default_templates(self):
        """Load default task templates."""
        default_templates = [
            {
                'template_id': 'sum-of-sales',
                'name': 'Sales Summary Application',
                'description': 'Create an app that processes CSV data and displays sales summaries',
                'brief_template': 'Publish a single-page site that fetches data.csv from attachments, sums its sales column, sets the title to "Sales Summary {seed}", displays the total inside #total-sales, and loads Bootstrap 5 from jsdelivr.',
                'checks_template': [
                    'Repo has MIT license',
                    'README.md is professional',
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
                ],
                'round2_attachments_template': []
            },
            {
                'template_id': 'markdown-to-html',
                'name': 'Markdown to HTML Converter',
                'description': 'Create an app that converts Markdown to HTML with syntax highlighting',
                'brief_template': 'Publish a static page that converts input.md from attachments to HTML with marked, renders it inside #markdown-output, and loads highlight.js for code blocks.',
                'checks_template': [
                    'Repo has MIT license',
                    'README.md is professional',
                    'js: !!document.querySelector("script[src*=\'marked\']")',
                    'js: !!document.querySelector("script[src*=\'highlight.js\']") || !!document.querySelector("link[href*=\'highlight.js\']")',
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
                ],
                'round2_attachments_template': []
            },
            {
                'template_id': 'github-user-created',
                'name': 'GitHub User Information',
                'description': 'Create an app that fetches and displays GitHub user information',
                'brief_template': 'Publish a Bootstrap page with form id="github-user-{seed}" that fetches a GitHub username, optionally uses ?token=, and displays the account creation date in YYYY-MM-DD UTC inside #github-created-at.',
                'checks_template': [
                    'Repo has MIT license',
                    'README.md is professional',
                    'js: document.querySelector("#github-user-{seed}").tagName === "FORM"',
                    'js: !!document.querySelector("script").textContent.includes("https://api.github.com/users/")'
                ],
                'attachments_template': [],
                'round2_brief_template': 'Show an aria-live alert #github-status that reports when a lookup starts, succeeds, or fails.',
                'round2_checks_template': [
                    'js: document.querySelector("#github-status").getAttribute("aria-live") === "polite"',
                    'js: !!document.querySelector("script").textContent.includes("github-status")'
                ],
                'round2_attachments_template': []
            }
        ]

        for template_data in default_templates:
            template = TaskTemplate(template_data['template_id'], template_data)
            self.templates[template_data['template_id']] = template

        logger.info(f"Loaded {len(self.templates)} task templates")

    def add_template(self, template_id: str, template_data: Dict[str, Any]):
        """Add a new task template."""
        template = TaskTemplate(template_id, template_data)
        self.templates[template_id] = template
        logger.info(f"Added task template: {template_id}")

    def get_template(self, template_id: str) -> Optional[TaskTemplate]:
        """Get a task template by ID."""
        return self.templates.get(template_id)

    def list_templates(self) -> List[str]:
        """List all available template IDs."""
        return list(self.templates.keys())

    def generate_task(
        self, 
        email: str, 
        template_id: Optional[str] = None, 
        round_num: int = 1,
        evaluation_url: str = None
    ) -> Dict[str, Any]:
        """Generate a task for the given email."""
        # Generate seed based on email and current date/hour for hourly expiration
        date_string = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
        seed = SeedGenerator.generate_seed(email, date_string)

        # Select random template if not specified
        if template_id is None:
            # Use deterministic selection based on email
            template_ids = list(self.templates.keys())
            template_index = int(hashlib.md5(email.encode()).hexdigest(), 16) % len(template_ids)
            template_id = template_ids[template_index]

        template = self.templates.get(template_id)
        if not template:
            raise ValueError(f"Unknown template: {template_id}")

        # Generate task
        task = template.generate_task(seed, round_num, evaluation_url)

        logger.info(f"Generated task {task['task_id']} for {email} using template {template_id}")
        return task

    def generate_task_for_submission(
        self, 
        email: str, 
        round_num: int = 1,
        evaluation_url: str = None
    ) -> Dict[str, Any]:
        """Generate a task for a student submission."""
        return self.generate_task(email, round_num=round_num, evaluation_url=evaluation_url)


# Global task generator instance
_task_generator = None


def get_task_generator() -> TaskGenerator:
    """Get the global task generator instance."""
    global _task_generator
    if _task_generator is None:
        _task_generator = TaskGenerator()
    return _task_generator


def generate_sample_task(
    email: str = "student@example.com", 
    template_id: str = "sum-of-sales"
) -> Dict[str, Any]:
    """Generate a sample task for testing."""
    generator = get_task_generator()
    return generator.generate_task(email, template_id)


if __name__ == "__main__":
    # Test the task generator
    print("Testing Task Generator...")
    print()
    
    generator = get_task_generator()
    
    # List templates
    print("Available templates:")
    for template_id in generator.list_templates():
        template = generator.get_template(template_id)
        print(f"  - {template_id}: {template.name}")
    print()
    
    # Generate sample tasks
    email = "test@example.com"
    print(f"Generating tasks for {email}:")
    print()
    
    for template_id in generator.list_templates():
        task = generator.generate_task(email, template_id, round_num=1)
        print(f"Template: {template_id}")
        print(f"Task ID: {task['task_id']}")
        print(f"Brief: {task['brief'][:100]}...")
        print(f"Checks: {len(task['checks'])} checks")
        print(f"Attachments: {len(task['attachments'])} files")
        print()