"""
db.py — SQLite engine for the backend. SQLite, not Postgres: Phase 1 is one
backend process talking to one phone during development, which SQLite
handles fine; revisit if/when there are concurrent writers (Phase 4+,
multiple real citizens).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

DB_PATH = Path(__file__).parent / "thirdwave.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
