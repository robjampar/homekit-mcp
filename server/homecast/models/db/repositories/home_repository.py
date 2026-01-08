"""
Repository for Home database operations.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List

from sqlmodel import Session, select

from homecast.models.db.models import Home
from homecast.models.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class HomeRepository(BaseRepository):
    """Repository for home operations."""

    MODEL_CLASS = Home

    @classmethod
    def get_by_prefix(
        cls,
        session: Session,
        home_id_prefix: str
    ) -> Optional[Home]:
        """
        Find a home by its ID prefix (first 8 characters).

        Args:
            session: Database session
            home_id_prefix: First 8 characters of the home UUID (case-insensitive)

        Returns:
            Home if found, None otherwise
        """
        # Get all homes and filter by prefix
        # Note: For large datasets, this could be optimized with a SQL LIKE query
        # but UUIDs stored as binary make prefix matching tricky
        homes = session.exec(select(Home)).all()
        prefix_lower = home_id_prefix.lower()

        for home in homes:
            if str(home.home_id).lower().startswith(prefix_lower):
                return home

        return None

    @classmethod
    def get_by_user(
        cls,
        session: Session,
        user_id: uuid.UUID
    ) -> List[Home]:
        """Get all homes for a user."""
        statement = select(Home).where(Home.user_id == user_id)
        return list(session.exec(statement).all())

    @classmethod
    def upsert_homes(
        cls,
        session: Session,
        user_id: uuid.UUID,
        homes: List[dict]
    ) -> List[Home]:
        """
        Add or update homes for a user.

        Args:
            session: Database session
            user_id: User who owns these homes
            homes: List of home dicts with 'id' and 'name' keys

        Returns:
            List of upserted Home objects
        """
        result = []
        now = datetime.now(timezone.utc)

        for home_data in homes:
            home_id_str = home_data.get("id")
            name = home_data.get("name", "Unknown Home")

            if not home_id_str:
                continue

            try:
                home_id = uuid.UUID(home_id_str)
            except ValueError:
                logger.warning(f"Invalid home ID: {home_id_str}")
                continue

            # Check if home exists
            existing = session.get(Home, home_id)

            if existing:
                # Update existing home
                existing.name = name
                existing.user_id = user_id  # In case ownership changed
                existing.updated_at = now
                session.add(existing)
                result.append(existing)
            else:
                # Create new home
                home = Home(
                    home_id=home_id,
                    name=name,
                    user_id=user_id,
                    updated_at=now
                )
                session.add(home)
                result.append(home)

        session.commit()

        # Refresh all to get current state
        for home in result:
            session.refresh(home)

        logger.info(f"Upserted {len(result)} homes for user {user_id}")
        return result

    @classmethod
    def delete_user_homes(
        cls,
        session: Session,
        user_id: uuid.UUID
    ) -> int:
        """Delete all homes for a user. Returns count deleted."""
        homes = cls.get_by_user(session, user_id)
        count = len(homes)
        for home in homes:
            session.delete(home)
        session.commit()
        return count
