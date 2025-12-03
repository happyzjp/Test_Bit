#!/usr/bin/env python3
import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import httpx
import yaml


def load_config():
    config_path = os.getenv("WEBSITE_ADMIN_CONFIG", "config.yml")
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}


def get_task(workflow_id: str, config: dict):
    task_center_url = config.get('task_center', {}).get('url', 'http://localhost:8000')
    api_key = config.get('api', {}).get('key')
    
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{task_center_url}/v1/tasks/{workflow_id}", headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"Task {workflow_id} not found", file=sys.stderr)
        else:
            print(f"Error: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"HTTP Error: {e}", file=sys.stderr)
        sys.exit(1)


def list_tasks(status: str = None, workflow_type: str = None, page: int = 1, page_size: int = 20, config: dict = None):
    task_center_url = config.get('task_center', {}).get('url', 'http://localhost:8000')
    api_key = config.get('api', {}).get('key')
    
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    
    params = {
        "page": page,
        "page_size": page_size
    }
    if status:
        params["status"] = status
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{task_center_url}/v1/tasks", params=params, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            workflows = result.get("workflows", [])
            if workflow_type:
                workflows = [w for w in workflows if w.get("workflow_type") == workflow_type]
            
            return workflows, result.get("pagination", {})
    except httpx.HTTPError as e:
        print(f"HTTP Error: {e}", file=sys.stderr)
        sys.exit(1)


def format_task(task: dict):
    lines = [
        f"Workflow ID: {task.get('workflow_id')}",
        f"Type: {task.get('workflow_type')}",
        f"Status: {task.get('status')}",
    ]
    
    if task.get('announcement_start'):
        lines.append(f"Announcement Start: {task['announcement_start']}")
    if task.get('execution_start'):
        lines.append(f"Execution Start: {task['execution_start']}")
    if task.get('review_start'):
        lines.append(f"Review Start: {task['review_start']}")
    if task.get('reward_start'):
        lines.append(f"Reward Start: {task['reward_start']}")
    if task.get('workflow_end'):
        lines.append(f"Workflow End: {task['workflow_end']}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='Manage KOKORO tasks')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    get_parser = subparsers.add_parser('get', help='Get task by workflow ID')
    get_parser.add_argument('workflow_id', help='Workflow ID')
    get_parser.add_argument('--config', default=None, help='Config file path')
    get_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    list_parser = subparsers.add_parser('list', help='List tasks')
    list_parser.add_argument('--status', help='Filter by status')
    list_parser.add_argument('--type', choices=['text_lora_creation', 'image_lora_creation'],
                            help='Filter by workflow type')
    list_parser.add_argument('--page', type=int, default=1, help='Page number')
    list_parser.add_argument('--page-size', type=int, default=20, help='Page size')
    list_parser.add_argument('--config', default=None, help='Config file path')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.config:
        os.environ['WEBSITE_ADMIN_CONFIG'] = args.config
    
    config = load_config()
    
    if args.command == 'get':
        task = get_task(args.workflow_id, config)
        if args.json:
            print(json.dumps(task, indent=2, default=str))
        else:
            print(format_task(task))
    
    elif args.command == 'list':
        workflows, pagination = list_tasks(
            status=args.status,
            workflow_type=args.type,
            page=args.page,
            page_size=args.page_size,
            config=config
        )
        
        if args.json:
            print(json.dumps({
                "workflows": workflows,
                "pagination": pagination
            }, indent=2, default=str))
        else:
            print(f"Total: {pagination.get('total', 0)} tasks")
            print(f"Page: {pagination.get('page', 1)}/{pagination.get('total_pages', 1)}")
            print()
            for task in workflows:
                print(format_task(task))
                print("-" * 50)


if __name__ == '__main__':
    main()

