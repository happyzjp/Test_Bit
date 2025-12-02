-- Migration 003: Add new fields to tasks table
-- This migration adds fields for task management: task_id, publish_status, start_date, end_date, description, hf_dataset_url, pdf_file_url

-- Add task_id column (user-defined task ID)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tasks' AND column_name = 'task_id'
    ) THEN
        ALTER TABLE tasks ADD COLUMN task_id VARCHAR;
        CREATE INDEX IF NOT EXISTS idx_tasks_task_id ON tasks(task_id);
        RAISE NOTICE 'Added task_id column to tasks table';
    END IF;
END $$;

-- Add publish_status column (draft/published)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tasks' AND column_name = 'publish_status'
    ) THEN
        ALTER TABLE tasks ADD COLUMN publish_status VARCHAR DEFAULT 'draft';
        CREATE INDEX IF NOT EXISTS idx_tasks_publish_status ON tasks(publish_status);
        RAISE NOTICE 'Added publish_status column to tasks table';
    END IF;
END $$;

-- Add start_date column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tasks' AND column_name = 'start_date'
    ) THEN
        ALTER TABLE tasks ADD COLUMN start_date TIMESTAMP WITH TIME ZONE;
        CREATE INDEX IF NOT EXISTS idx_tasks_start_date ON tasks(start_date);
        RAISE NOTICE 'Added start_date column to tasks table';
    END IF;
END $$;

-- Add end_date column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tasks' AND column_name = 'end_date'
    ) THEN
        ALTER TABLE tasks ADD COLUMN end_date TIMESTAMP WITH TIME ZONE;
        CREATE INDEX IF NOT EXISTS idx_tasks_end_date ON tasks(end_date);
        RAISE NOTICE 'Added end_date column to tasks table';
    END IF;
END $$;

-- Add description column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tasks' AND column_name = 'description'
    ) THEN
        ALTER TABLE tasks ADD COLUMN description TEXT;
        RAISE NOTICE 'Added description column to tasks table';
    END IF;
END $$;

-- Add hf_dataset_url column (HuggingFace dataset URL)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tasks' AND column_name = 'hf_dataset_url'
    ) THEN
        ALTER TABLE tasks ADD COLUMN hf_dataset_url VARCHAR;
        RAISE NOTICE 'Added hf_dataset_url column to tasks table';
    END IF;
END $$;

-- Add pdf_file_url column (PDF task file URL)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tasks' AND column_name = 'pdf_file_url'
    ) THEN
        ALTER TABLE tasks ADD COLUMN pdf_file_url VARCHAR;
        RAISE NOTICE 'Added pdf_file_url column to tasks table';
    END IF;
END $$;

