import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class DatabaseClient:
    def __init__(self, db_path: str = "weaveit.db"):
        """Initialize SQLite database connection"""
        self.db_path = Path(db_path)
        self.connection: Optional[sqlite3.Connection] = None
        
    def connect(self):
        """Connect to SQLite database"""
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row  # Access columns by name
        self._create_tables()
        
    def _create_tables(self):
        """Create database tables if they don't exist"""
        cursor = self.connection.cursor()
        
        # Create working_projects table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS working_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                state_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, project_id)
            )
        """)
        
        # Create index on user_id for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_working_projects_user_id 
            ON working_projects(user_id)
        """)
        
        # Create artifacts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                uri TEXT NOT NULL,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index on user_id for artifacts
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_artifacts_user_id 
            ON artifacts(user_id)
        """)
        
        self.connection.commit()
    
    def cleanup_old_projects(self, days: int = 30):
        """Delete working_projects not updated in specified days"""
        cursor = self.connection.cursor()
        cutoff_date = datetime.now() - timedelta(days=days)
        
        cursor.execute("""
            DELETE FROM working_projects 
            WHERE updated_at < ?
        """, (cutoff_date,))
        
        self.connection.commit()
        return cursor.rowcount
    
    def upsert_working_project(
        self,
        user_id: str,
        project_id: str,
        title: str,
        state_dict: dict
    ):
        """Insert or update a working project"""
        cursor = self.connection.cursor()
        state_json = json.dumps(state_dict)
        
        cursor.execute("""
            INSERT INTO working_projects (user_id, project_id, title, state_json, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, project_id) DO UPDATE SET
                title = excluded.title,
                state_json = excluded.state_json,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, project_id, title, state_json))
        
        self.connection.commit()
    
    def get_user_projects(self, user_id: str):
        """Get all working projects for a user"""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT project_id, title, state_json, updated_at
            FROM working_projects
            WHERE user_id = ?
            ORDER BY updated_at DESC
        """, (user_id,))
        
        rows = cursor.fetchall()
        return [
            {
                'project_id': row['project_id'],
                'title': row['title'],
                'state': json.loads(row['state_json']) if row['state_json'] else {},
                'updated_at': row['updated_at']
            }
            for row in rows
        ]
    
    def create_artifact(
        self,
        user_id: str,
        artifact_type: str,
        uri: str,
        metadata_dict: dict = None
    ):
        """Create a new artifact record"""
        cursor = self.connection.cursor()
        metadata_json = json.dumps(metadata_dict) if metadata_dict else None
        
        cursor.execute("""
            INSERT INTO artifacts (user_id, artifact_type, uri, metadata_json, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, artifact_type, uri, metadata_json))
        
        self.connection.commit()
        return cursor.lastrowid
    
    def get_user_artifacts(self, user_id: str, artifact_type: str = None):
        """Get artifacts for a user, optionally filtered by type"""
        cursor = self.connection.cursor()
        
        if artifact_type:
            cursor.execute("""
                SELECT id, artifact_type, uri, metadata_json, created_at
                FROM artifacts
                WHERE user_id = ? AND artifact_type = ?
                ORDER BY created_at DESC
            """, (user_id, artifact_type))
        else:
            cursor.execute("""
                SELECT id, artifact_type, uri, metadata_json, created_at
                FROM artifacts
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))
        
        rows = cursor.fetchall()
        return [
            {
                'id': row['id'],
                'artifact_type': row['artifact_type'],
                'uri': row['uri'],
                'metadata': json.loads(row['metadata_json']) if row['metadata_json'] else {},
                'created_at': row['created_at']
            }
            for row in rows
        ]
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()


# Global database client instance
db_client = DatabaseClient()
