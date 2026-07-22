import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, Text, ForeignKey, JSON, Float
)
from sqlalchemy.orm import relationship
from backend.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    plan = Column(String, default="free")          # free | pro | enterprise
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    gemini_keys = relationship("GeminiKey", back_populates="tenant", cascade="all, delete")
    channels = relationship("Channel", back_populates="tenant", cascade="all, delete")
    jobs = relationship("VideoJob", back_populates="tenant", cascade="all, delete")


class GeminiKey(Base):
    __tablename__ = "gemini_keys"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    api_key = Column(String, nullable=False)
    label = Column(String, default="")
    is_active = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="gemini_keys")


class Channel(Base):
    __tablename__ = "channels"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    channel_name = Column(String, nullable=False)
    niche = Column(String, nullable=False)         # motivasi, edukasi, humor, etc.
    youtube_credentials = Column(JSON, nullable=True)  # OAuth tokens stored as JSON
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="channels")
    jobs = relationship("VideoJob", back_populates="channel", cascade="all, delete")


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    channel_id = Column(String, ForeignKey("channels.id"), nullable=True)

    # Source
    source_type = Column(String, nullable=False)   # upload | url | ai_generate
    source_url = Column(String, nullable=True)
    source_filename = Column(String, nullable=True)

    # Processing config
    niche = Column(String, nullable=True)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    add_subtitles = Column(Boolean, default=True)
    add_music = Column(Boolean, default=False)
    hook_text = Column(String, nullable=True)

    # Output
    output_filename = Column(String, nullable=True)
    script = Column(Text, nullable=True)
    thumbnail_filename = Column(String, nullable=True)

    # Status
    status = Column(String, default="pending")     # pending | processing | done | failed | scheduled
    error_message = Column(Text, nullable=True)
    progress = Column(Float, default=0.0)

    # Schedule
    scheduled_at = Column(DateTime, nullable=True)
    uploaded_at = Column(DateTime, nullable=True)
    youtube_video_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="jobs")
    channel = relationship("Channel", back_populates="jobs")
