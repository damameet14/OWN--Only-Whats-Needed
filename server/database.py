"""SQLite database schema and CRUD helpers for OWN."""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional

from server.config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database():
    """Create database tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            mobile TEXT,
            avatar_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            engine TEXT NOT NULL,
            language TEXT NOT NULL,
            size_bytes INTEGER,
            path TEXT NOT NULL,
            is_default BOOLEAN DEFAULT 0,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            video_path TEXT NOT NULL,
            video_duration REAL,
            video_width INTEGER,
            video_height INTEGER,
            thumbnail_path TEXT,
            language TEXT,
            model_id INTEGER REFERENCES models(id),
            subtitle_data TEXT,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()


# ── User CRUD ─────────────────────────────────────────────────────────────────

def get_user(user_id: int = 1) -> Optional[dict]:
    """Get user profile. Default user is id=1."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_or_update_user(name: str, email: str = None, mobile: str = None,
                          avatar_path: str = None, user_id: int = 1) -> dict:
    """Create or update user profile."""
    conn = get_connection()
    existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()

    if existing:
        conn.execute(
            "UPDATE users SET name=?, email=?, mobile=?, avatar_path=? WHERE id=?",
            (name, email, mobile, avatar_path, user_id)
        )
    else:
        conn.execute(
            "INSERT INTO users (id, name, email, mobile, avatar_path) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, email, mobile, avatar_path)
        )

    conn.commit()
    user = dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    conn.close()
    return user


# ── Model CRUD ────────────────────────────────────────────────────────────────

def list_models() -> list[dict]:
    """List all installed models."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM models ORDER BY downloaded_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_model(model_id: int) -> Optional[dict]:
    """Get a specific model by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def register_model(name: str, engine: str, language: str,
                   path: str, size_bytes: int = None,
                   is_default: bool = False) -> dict:
    """Register a model in the database."""
    conn = get_connection()

    # If setting as default, unset others of the same engine
    if is_default:
        conn.execute(
            "UPDATE models SET is_default = 0 WHERE engine = ?", (engine,)
        )

    cursor = conn.execute(
        """INSERT INTO models (name, engine, language, path, size_bytes, is_default)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, engine, language, path, size_bytes, is_default)
    )

    model_id = cursor.lastrowid
    conn.commit()
    model = dict(conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone())
    conn.close()
    return model


def delete_model(model_id: int) -> bool:
    """Delete a model record from the database."""
    conn = get_connection()
    cursor = conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# ── Project CRUD ──────────────────────────────────────────────────────────────

def list_projects() -> list[dict]:
    """List all projects ordered by most recently updated."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM projects ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_project(project_id: int) -> Optional[dict]:
    """Get a specific project by ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_project(title: str, video_path: str,
                   video_duration: float = None,
                   video_width: int = None,
                   video_height: int = None,
                   thumbnail_path: str = None,
                   language: str = None) -> dict:
    """Create a new project."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO projects
           (title, video_path, video_duration, video_width, video_height,
            thumbnail_path, language)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (title, video_path, video_duration, video_width, video_height,
         thumbnail_path, language)
    )
    project_id = cursor.lastrowid
    conn.commit()
    project = dict(conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone())
    conn.close()
    return project


def update_project(project_id: int, **kwargs) -> Optional[dict]:
    """Update project fields. Accepts keyword arguments matching column names."""
    if not kwargs:
        return get_project(project_id)

    kwargs["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [project_id]

    conn = get_connection()
    conn.execute(
        f"UPDATE projects SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    project = dict(conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone())
    conn.close()
    return project


def delete_project(project_id: int) -> bool:
    """Delete a project."""
    conn = get_connection()
    cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# ── Auto-detect existing models ──────────────────────────────────────────────

def scan_existing_models(project_root: str):
    """Check the project root for any existing Vosk model directories
    and register them if not already in the database."""
    conn = get_connection()
    existing_paths = {
        r["path"] for r in
        conn.execute("SELECT path FROM models").fetchall()
    }

    for entry in os.listdir(project_root):
        full_path = os.path.join(project_root, entry)
        if not os.path.isdir(full_path):
            continue
        if not entry.startswith("vosk-model"):
            continue
        if full_path in existing_paths:
            continue

        # Determine language from the model directory name
        # e.g., vosk-model-hi-0.22 → "hi", vosk-model-small-hi-0.22 → "hi"
        parts = entry.replace("vosk-model-", "").split("-")
        # Filter out "small", "big" and version numbers
        lang = "unknown"
        for p in parts:
            if p not in ("small", "big") and not p.replace(".", "").isdigit():
                lang = p
                break

        size = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fnames in os.walk(full_path)
            for f in fnames
        )

        register_model(
            name=entry,
            engine="vosk",
            language=lang,
            path=full_path,
            size_bytes=size,
            is_default=(len(existing_paths) == 0),
        )
        existing_paths.add(full_path)

    conn.close()
