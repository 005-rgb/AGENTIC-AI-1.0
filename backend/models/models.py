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
    is_reseller = Column(Boolean, default=False)
    parent_tenant_id = Column(String, ForeignKey("tenants.id"), nullable=True)
    brand_name = Column(String, nullable=True)
    brand_logo_url = Column(String, nullable=True)
    brand_color = Column(String, nullable=True)    # #hex
    telegram_chat_id = Column(String, nullable=True)
    whatsapp_number = Column(String, nullable=True)
    bot_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    gemini_keys = relationship("GeminiKey", back_populates="tenant", cascade="all, delete")
    channels = relationship("Channel", back_populates="tenant", cascade="all, delete")
    jobs = relationship("VideoJob", back_populates="tenant", cascade="all, delete")
    hooks = relationship("HookLibrary", back_populates="tenant", cascade="all, delete")
    bot_sessions = relationship("BotSession", back_populates="tenant", cascade="all, delete")
    sub_tenants = relationship("Tenant", foreign_keys=[parent_tenant_id])


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
    niche = Column(String, nullable=False)

    # YouTube (credentials disimpan terenkripsi jika FERNET_KEY di-set)
    youtube_credentials = Column(Text, nullable=True)   # encrypted JSON string
    youtube_channel_id = Column(String, nullable=True)
    subscriber_count = Column(Integer, default=0)
    best_upload_hours = Column(JSON, nullable=True)     # [7, 12, 19]

    # TikTok — Phase 3
    tiktok_credentials = Column(Text, nullable=True)    # encrypted JSON: {access_token, open_id, refresh_token, expires_at}
    tiktok_open_id = Column(String, nullable=True)

    # Meta (Instagram + Facebook) — Phase 3
    meta_credentials = Column(Text, nullable=True)      # encrypted JSON: {access_token, page_id, ig_user_id, expires_at}
    meta_page_id = Column(String, nullable=True)
    meta_ig_user_id = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="channels")
    jobs = relationship("VideoJob", back_populates="channel", cascade="all, delete")


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    channel_id = Column(String, ForeignKey("channels.id"), nullable=True)
    hook_library_id = Column(String, ForeignKey("hook_library.id"), nullable=True)

    # Source
    source_type = Column(String, nullable=False)   # upload | url | ai_generate | text_to_shorts
    source_url = Column(String, nullable=True)
    source_filename = Column(String, nullable=True)

    # Processing config
    niche = Column(String, nullable=True)
    title = Column(String, nullable=True)
    title_variant_b = Column(String, nullable=True)   # A/B testing
    description = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    add_subtitles = Column(Boolean, default=True)
    add_music = Column(Boolean, default=False)
    hook_text = Column(String, nullable=True)

    # Multi-platform: daftar platform target
    platforms = Column(JSON, default=lambda: ["youtube"])

    # A/B Test
    ab_test_active = Column(Boolean, default=False)
    ab_winner = Column(String, nullable=True)   # "a" | "b" | null

    # Output
    output_filename = Column(String, nullable=True)
    script = Column(Text, nullable=True)
    thumbnail_filename = Column(String, nullable=True)

    # Status
    status = Column(String, default="pending")
    # pending | processing | done | failed | scheduled | uploaded
    error_message = Column(Text, nullable=True)
    progress = Column(Float, default=0.0)

    # Schedule
    scheduled_at = Column(DateTime, nullable=True)
    uploaded_at = Column(DateTime, nullable=True)

    # Upload IDs per platform
    youtube_video_id = Column(String, nullable=True)
    youtube_video_id_b = Column(String, nullable=True)   # A/B variant B
    tiktok_video_id = Column(String, nullable=True)
    instagram_media_id = Column(String, nullable=True)
    facebook_video_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="jobs")
    channel = relationship("Channel", back_populates="jobs")
    ab_results = relationship("AbTestResult", back_populates="job", cascade="all, delete")


class HookLibrary(Base):
    __tablename__ = "hook_library"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=True)  # null = global/shared
    niche = Column(String, nullable=False)
    hook_text = Column(Text, nullable=False)
    avg_ctr = Column(Float, nullable=True)
    use_count = Column(Integer, default=0)
    is_approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="hooks")


class AbTestResult(Base):
    __tablename__ = "ab_test_results"

    id = Column(String, primary_key=True, default=gen_uuid)
    job_id = Column(String, ForeignKey("video_jobs.id"), nullable=False)
    variant = Column(String, nullable=False)         # "a" | "b"
    youtube_video_id = Column(String, nullable=False)
    views_48h = Column(Integer, default=0)
    ctr_48h = Column(Float, nullable=True)
    checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("VideoJob", back_populates="ab_results")


class BotSession(Base):
    __tablename__ = "bot_sessions"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    platform = Column(String, nullable=False)        # telegram | whatsapp
    chat_id = Column(String, nullable=False)
    state = Column(String, nullable=True)            # FSM state
    context = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="bot_sessions")


class CompetitorAnalysis(Base):
    __tablename__ = "competitor_analyses"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    channel_url = Column(String, nullable=False)
    channel_name = Column(String, nullable=True)
    result = Column(JSON, nullable=True)             # full analysis JSON
    created_at = Column(DateTime, default=datetime.utcnow)
