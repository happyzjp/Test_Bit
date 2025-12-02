#!/usr/bin/env python3
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from kokoro.website_admin.database import init_db, init_data

if __name__ == "__main__":
    print("Initializing website admin database...")
    try:
        init_db()
        print("Database tables created successfully")
        
        print("Creating default data...")
        init_data()
        print("Default data created successfully")
        
        print("Database initialization completed successfully!")
    except Exception as e:
        print(f"Error during database initialization: {e}", file=sys.stderr)
        sys.exit(1)
