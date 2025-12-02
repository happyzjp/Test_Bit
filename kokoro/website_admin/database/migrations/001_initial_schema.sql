CREATE TABLE IF NOT EXISTS task_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    workflow_type VARCHAR(50) NOT NULL,
    workflow_spec JSONB NOT NULL,
    announcement_duration VARCHAR(20) DEFAULT '0.25',
    execution_duration VARCHAR(20) DEFAULT '3.0',
    review_duration VARCHAR(20) DEFAULT '1.0',
    reward_duration VARCHAR(20) DEFAULT '0.0',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_task_templates_name ON task_templates(name);
CREATE INDEX IF NOT EXISTS idx_task_templates_workflow_type ON task_templates(workflow_type);
CREATE INDEX IF NOT EXISTS idx_task_templates_is_active ON task_templates(is_active);

CREATE TABLE IF NOT EXISTS task_history (
    id SERIAL PRIMARY KEY,
    workflow_id VARCHAR(255) NOT NULL,
    workflow_type VARCHAR(50) NOT NULL,
    workflow_spec JSONB NOT NULL,
    announcement_duration VARCHAR(20),
    execution_duration VARCHAR(20),
    review_duration VARCHAR(20),
    reward_duration VARCHAR(20),
    created_by VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    task_center_response JSONB,
    is_success BOOLEAN DEFAULT FALSE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_history_workflow_id ON task_history(workflow_id);
CREATE INDEX IF NOT EXISTS idx_task_history_workflow_type ON task_history(workflow_type);
CREATE INDEX IF NOT EXISTS idx_task_history_status ON task_history(status);
CREATE INDEX IF NOT EXISTS idx_task_history_created_at ON task_history(created_at);

CREATE TABLE IF NOT EXISTS operation_logs (
    id SERIAL PRIMARY KEY,
    operation_type VARCHAR(100) NOT NULL,
    operation_target VARCHAR(255),
    operator VARCHAR(255),
    request_data JSONB,
    response_data JSONB,
    status VARCHAR(50) DEFAULT 'success',
    error_message TEXT,
    ip_address VARCHAR(50),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_operation_logs_operation_type ON operation_logs(operation_type);
CREATE INDEX IF NOT EXISTS idx_operation_logs_operation_target ON operation_logs(operation_target);
CREATE INDEX IF NOT EXISTS idx_operation_logs_created_at ON operation_logs(created_at);

