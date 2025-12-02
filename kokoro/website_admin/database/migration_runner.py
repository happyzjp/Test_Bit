"""
Database migration system for website_admin module.
Automatically executes SQL migration scripts on service startup.
"""
import os
import re
from pathlib import Path
from sqlalchemy import text
from kokoro.common.database import engine
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)

# Migration scripts directory
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_migration_files():
    """Get all migration SQL files sorted by version number."""
    migration_files = []
    for file_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        # Extract version number from filename (e.g., "001_initial_schema.sql" -> 1)
        match = re.match(r"(\d+)_", file_path.name)
        if match:
            version = int(match.group(1))
            migration_files.append((version, file_path))
    return sorted(migration_files, key=lambda x: x[0])


def get_executed_migrations():
    """Get list of executed migration versions from database."""
    try:
        with engine.connect() as conn:
            # Check if migrations table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'schema_migrations'
                )
            """))
            table_exists = result.scalar()
            
            if not table_exists:
                # Create migrations tracking table
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL,
                        executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.commit()
                return []
            
            # Get executed migrations
            result = conn.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
            return [row[0] for row in result]
    except Exception as e:
        logger.warning(f"Failed to check executed migrations: {e}")
        return []


def mark_migration_executed(version, filename, conn):
    """Mark a migration as executed."""
    try:
        conn.execute(text("""
            INSERT INTO schema_migrations (version, filename) 
            VALUES (:version, :filename)
            ON CONFLICT (version) DO NOTHING
        """), {"version": version, "filename": filename})
    except Exception as e:
        logger.error(f"Failed to mark migration {version} as executed: {e}")
        raise


def execute_migration(version, file_path):
    """Execute a single migration file."""
    logger.info(f"Executing migration {version}: {file_path.name}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        if not sql_content.strip():
            logger.warning(f"Migration {version} is empty, skipping")
            return
        
        with engine.begin() as conn:  # Use begin() for automatic transaction management
            # Execute the entire migration SQL file
            # PostgreSQL supports executing multiple statements in one call
            conn.execute(text(sql_content))
            
            # Mark migration as executed
            mark_migration_executed(version, file_path.name, conn)
            logger.info(f"Migration {version} executed successfully")
            
    except Exception as e:
        logger.error(f"Failed to execute migration {version} ({file_path.name}): {e}")
        raise


def run_migrations():
    """Run all pending migrations."""
    try:
        executed_versions = get_executed_migrations()
        migration_files = get_migration_files()
        
        pending_migrations = [
            (version, file_path) 
            for version, file_path in migration_files 
            if version not in executed_versions
        ]
        
        if not pending_migrations:
            logger.info("No pending migrations found")
            return
        
        logger.info(f"Found {len(pending_migrations)} pending migration(s)")
        
        for version, file_path in pending_migrations:
            execute_migration(version, file_path)
        
        logger.info("All migrations completed successfully")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

