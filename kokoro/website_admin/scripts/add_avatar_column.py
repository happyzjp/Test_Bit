#!/usr/bin/env python3
"""
Manual script to add avatar column to users table.
Run this if the migration system fails to add the column.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from kokoro.common.database import engine
from sqlalchemy import text
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)

def add_avatar_column():
    """Add avatar column to users table."""
    try:
        with engine.begin() as conn:
            # Check if column exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'avatar'
            """))
            exists = result.fetchone() is not None
            
            if exists:
                logger.info("Avatar column already exists in users table")
                return True
            
            # Add the column
            logger.info("Adding avatar column to users table...")
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar VARCHAR(255)"))
            logger.info("Avatar column added successfully")
            return True
            
    except Exception as e:
        logger.error(f"Failed to add avatar column: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    print("Adding avatar column to users table...")
    if add_avatar_column():
        print("✓ Avatar column added successfully!")
        sys.exit(0)
    else:
        print("✗ Failed to add avatar column")
        sys.exit(1)

