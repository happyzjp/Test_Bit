# Website Admin Database Initialization

This directory contains database initialization scripts for the Website Admin module.

## Structure

```
database/
├── __init__.py              # Exports init_db and init_data functions
├── init_db.py               # Database initialization functions
├── migrations/              # SQL migration scripts
│   ├── __init__.py
│   ├── 001_initial_schema.sql    # Initial table schema
│   └── 002_default_templates.sql # Default task templates
└── README.md                # This file
```

## Database Tables

The Website Admin module uses the following database tables:

### 1. task_templates
Stores task templates for quick task creation.

**Columns:**
- `id` - Primary key
- `name` - Template name (unique)
- `description` - Template description
- `workflow_type` - Type of workflow (text_lora_creation or image_lora_creation)
- `workflow_spec` - JSON specification for the workflow
- `announcement_duration` - Announcement phase duration (days)
- `execution_duration` - Execution phase duration (days)
- `review_duration` - Review phase duration (days)
- `reward_duration` - Reward phase duration (days)
- `is_active` - Whether the template is active
- `created_at` - Creation timestamp
- `updated_at` - Last update timestamp

### 2. task_history
Stores history of all task creation attempts.

**Columns:**
- `id` - Primary key
- `workflow_id` - Workflow ID
- `workflow_type` - Type of workflow
- `workflow_spec` - JSON specification for the workflow
- `announcement_duration` - Announcement phase duration
- `execution_duration` - Execution phase duration
- `review_duration` - Review phase duration
- `reward_duration` - Reward phase duration
- `created_by` - User who created the task
- `status` - Task status (pending, success, failed)
- `task_center_response` - Response from task center
- `is_success` - Whether the task was created successfully
- `error_message` - Error message if creation failed
- `created_at` - Creation timestamp

### 3. operation_logs
Stores operation logs for auditing.

**Columns:**
- `id` - Primary key
- `operation_type` - Type of operation
- `operation_target` - Target of the operation
- `operator` - User who performed the operation
- `request_data` - Request data (JSON)
- `response_data` - Response data (JSON)
- `status` - Operation status (success, failed)
- `error_message` - Error message if operation failed
- `ip_address` - IP address of the requester
- `user_agent` - User agent string
- `created_at` - Creation timestamp

## Initialization Methods

### Method 1: Using Python Script (Recommended)

```bash
python kokoro/website_admin/scripts/init_database.py
```

This script will:
1. Create all database tables
2. Insert default task templates

### Method 2: Using SQL Migrations

If you prefer to use SQL directly:

```bash
# Connect to your PostgreSQL database
psql -U kokoro -d kokoro

# Run migrations in order
\i kokoro/website_admin/database/migrations/001_initial_schema.sql
\i kokoro/website_admin/database/migrations/002_default_templates.sql
```

### Method 3: Automatic Initialization

The database is automatically initialized when the Website Admin service starts:

```bash
cd kokoro/website_admin
uvicorn main:app --host 0.0.0.0 --port 8001
```

The service will:
1. Create tables on startup (if they don't exist)
2. Initialize default templates (if they don't exist)

## Default Templates

The initialization script creates 4 default templates:

1. **text_lora_new_default** - Default template for new text LoRA training
2. **text_lora_incremental_default** - Default template for incremental text LoRA training
3. **image_lora_new_default** - Default template for new image LoRA training
4. **image_lora_incremental_default** - Default template for incremental image LoRA training

## Functions

### `init_db()`
Creates all database tables. Safe to call multiple times (uses `IF NOT EXISTS`).

### `init_data()`
Inserts default task templates. Safe to call multiple times (checks for existing templates).

## Usage in Code

```python
from kokoro.website_admin.database import init_db, init_data

# Create tables
init_db()

# Insert default data
init_data()
```

## Notes

- All tables use PostgreSQL JSONB type for JSON fields
- Indexes are created for frequently queried columns
- Timestamps use timezone-aware TIMESTAMP WITH TIME ZONE
- Default templates can be customized or disabled via `is_active` flag

