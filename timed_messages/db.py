from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def get_engine(database_url: str):
    return create_engine(database_url)
