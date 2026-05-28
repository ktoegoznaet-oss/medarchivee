"""Declarative base for all ORM models."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single declarative base shared across all models.

    Used by Alembic as the source of truth for `target_metadata`.
    """
