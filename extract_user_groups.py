#!/usr/bin/env python3
"""
Extract user groups from Open WebUI database.
Connects to the database and displays all groups with their members.
"""

import os
import sys
import json
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Try to import Open WebUI modules for database connection
try:
    # Add Open WebUI backend to path if needed
    openwebui_backend = Path("/home/mark/projects/05_florise/open-webui/backend")
    if openwebui_backend.exists():
        sys.path.insert(0, str(openwebui_backend))
    
    from open_webui.env import DATABASE_URL, DATA_DIR
    from open_webui.models.groups import Group, GroupModel
    from open_webui.internal.db import get_db
    USE_OPENWEBUI_MODULES = True
except ImportError as e:
    print(f"Warning: Could not import Open WebUI modules: {e}")
    print("Will attempt direct database connection...")
    USE_OPENWEBUI_MODULES = False
    # Default database path
    DATA_DIR = Path(os.getenv("DATA_DIR", "/home/mark/projects/05_florise/open-webui/backend/data"))
    DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR}/webui.db")


def get_all_groups_with_users():
    """Extract all groups and their user members from the database."""
    
    if USE_OPENWEBUI_MODULES:
        # Use Open WebUI's database connection
        print(f"Connecting to database using Open WebUI modules...")
        print(f"Database URL: {DATABASE_URL}")
        
        groups_data = []
        with get_db() as db:What? 
            groups = db.query(Group).order_by(Group.name).all()
            
            for group in groups:
                user_ids = group.user_ids if group.user_ids else []
                groups_data.append({
                    'id': group.id,
                    'name': group.name,
                    'description': group.description or '',
                    'user_ids': user_ids,
                    'user_count': len(user_ids),
                    'created_at': group.created_at,
                    'updated_at': group.updated_at
                })
        
        return groups_data
    else:
        # Direct database connection
        print(f"Connecting directly to database...")
        print(f"Database URL: {DATABASE_URL}")
        
        # Handle SQLCipher encrypted databases
        if DATABASE_URL.startswith("sqlite+sqlcipher://"):
            database_password = os.environ.get("DATABASE_PASSWORD")
            if not database_password:
                raise ValueError("DATABASE_PASSWORD is required for encrypted SQLite database")
            
            import sqlcipher3
            db_path = DATABASE_URL.replace("sqlite+sqlcipher://", "").lstrip("/")
            conn = sqlcipher3.connect(db_path, check_same_thread=False)
            conn.execute(f"PRAGMA key = '{database_password}'")
            
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, name, description, 
                       user_ids, created_at, updated_at
                FROM "group"
                ORDER BY name
            """)
            
            groups_data = []
            for row in cursor.fetchall():
                user_ids_json = row[4] if row[4] else '[]'
                try:
                    user_ids = json.loads(user_ids_json) if isinstance(user_ids_json, str) else user_ids_json
                except:
                    user_ids = []
                
                groups_data.append({
                    'id': row[0],
                    'name': row[2] if row[2] else '',
                    'description': row[3] if row[3] else '',
                    'user_ids': user_ids,
                    'user_count': len(user_ids),
                    'created_at': row[5],
                    'updated_at': row[6]
                })
            
            conn.close()
            return groups_data
        
        # Standard SQLite or PostgreSQL connection
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            # Query all groups
            result = session.execute(text("""
                SELECT id, user_id, name, description, 
                       user_ids, created_at, updated_at
                FROM "group"
                ORDER BY name
            """))
            
            groups_data = []
            for row in result:
                user_ids_json = row[4] if row[4] else '[]'
                try:
                    user_ids = json.loads(user_ids_json) if isinstance(user_ids_json, str) else user_ids_json
                except:
                    user_ids = []
                
                groups_data.append({
                    'id': row[0],
                    'name': row[2] if row[2] else '',
                    'description': row[3] if row[3] else '',
                    'user_ids': user_ids,
                    'user_count': len(user_ids),
                    'created_at': row[5],
                    'updated_at': row[6]
                })
            
            return groups_data
        finally:
            session.close()


def print_groups(groups_data):
    """Print groups in a readable format."""
    if not groups_data:
        print("\nNo groups found in the database.")
        return
    
    print(f"\n{'='*80}")
    print(f"Found {len(groups_data)} group(s) in the database")
    print(f"{'='*80}\n")
    
    for i, group in enumerate(groups_data, 1):
        print(f"Group {i}: {group['name']}")
        print(f"  ID: {group['id']}")
        if group['description']:
            print(f"  Description: {group['description']}")
        print(f"  Members: {group['user_count']} user(s)")
        
        if group['user_ids']:
            print(f"  User IDs:")
            for user_id in group['user_ids']:
                print(f"    - {user_id}")
        else:
            print(f"  User IDs: (none)")
        
        print()


def main():
    """Main function."""
    try:
        groups_data = get_all_groups_with_users()
        print_groups(groups_data)
        
        # Optionally save to JSON file
        output_file = Path("user_groups_export.json")
        with open(output_file, 'w') as f:
            json.dump(groups_data, f, indent=2)
        print(f"\nGroups exported to: {output_file}")
        
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

