"""
Database models for HomeCast.

Models:
- User: User accounts for the web portal
- Device: Connected HomeKit Mac apps
"""

import uuid
import re
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from sqlalchemy.ext.declarative import declared_attr
from sqlmodel import Field, SQLModel


class BaseModel(SQLModel):
    """Base model with common fields."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc))

    @declared_attr  # type: ignore[misc]
    def __tablename__(cls):
        # Convert CamelCase to snake_case
        name = cls.__name__
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower()


class User(BaseModel, table=True):
    """
    User accounts for the web portal.

    Users sign up with email/password and can connect multiple devices.
    """
    __tablename__ = "users"

    email: str = Field(nullable=False, unique=True, index=True)
    password_hash: str = Field(nullable=False)

    # Profile
    name: Optional[str] = Field(default=None)

    # Status
    is_active: bool = Field(default=True)
    last_login_at: Optional[datetime] = Field(default=None)


class DeviceStatus(str, Enum):
    """Status of a connected device."""
    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"


class Device(BaseModel, table=True):
    """
    Connected HomeKit Mac apps.

    Each device represents a Mac running the HomeCast app
    that connects via WebSocket to relay HomeKit commands.
    """
    user_id: uuid.UUID = Field(
        nullable=False, foreign_key="users.id", index=True)

    # Device identification
    name: str = Field(nullable=False)
    device_id: str = Field(nullable=False, unique=True, index=True,
        description="Unique device identifier from the Mac app")

    # Connection status
    status: str = Field(default=DeviceStatus.OFFLINE.value)
    last_seen_at: Optional[datetime] = Field(default=None)
    instance_id: Optional[str] = Field(default=None, index=True,
        description="Cloud Run instance ID where device is connected")

    # HomeKit info (cached from last connection)
    home_count: int = Field(default=0)
    accessory_count: int = Field(default=0)


class TopicSlot(SQLModel, table=True):
    """
    Pub/Sub topic slots for cross-instance routing.

    Instead of creating a topic per Cloud Run revision, we use a fixed pool
    of topics (e.g., homecast-a, homecast-b, etc.). Each instance claims
    a slot on startup and releases it on shutdown.
    """
    __tablename__ = "topic_slots"

    slot_name: str = Field(primary_key=True)  # e.g., "a", "b", "c"
    instance_id: Optional[str] = Field(default=None, index=True)  # Cloud Run revision ID
    claimed_at: Optional[datetime] = Field(default=None)
    last_heartbeat: Optional[datetime] = Field(default=None)


__all__ = [
    "BaseModel",
    "User",
    "Device",
    "DeviceStatus",
    "TopicSlot",
]
