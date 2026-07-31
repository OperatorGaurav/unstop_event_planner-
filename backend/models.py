"""
SQLAlchemy ORM models for Unstop Calendar Sync.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    unstop_id = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    date = Column(String)               # ISO date string: "2025-09-14"
    time = Column(String)               # "10:00 AM" or None
    deadline = Column(String)           # Registration deadline
    event_url = Column(String)
    calendar_event_id = Column(String)  # Google Calendar event ID once synced
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "unstop_id": self.unstop_id,
            "title": self.title,
            "date": self.date,
            "time": self.time,
            "deadline": self.deadline,
            "event_url": self.event_url,
            "calendar_event_id": self.calendar_event_id,
            "is_active": self.is_active,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    synced_at = Column(DateTime, default=datetime.utcnow)
    events_added = Column(Integer, default=0)
    events_updated = Column(Integer, default=0)
    events_removed = Column(Integer, default=0)
    status = Column(String, default="success")   # "success" | "error"
    error_message = Column(Text, nullable=True)
