import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "sqlite+aiosqlite:///./dns.db"

engine = create_async_engine(DATABASE_URL, echo=True)
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


class DNSRecord(Base):
    __tablename__ = "dns_records"
    __table_args__ = (
        UniqueConstraint("hostname", "type", "value", name="uq_hostname_type_value"),
        Index("ix_hostname", "hostname"),
        Index("ix_hostname_type", "hostname", "type"),
        CheckConstraint("type IN ('A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS')", name="ck_record_type"),
    )

    id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hostname = Column(String, nullable=False)
    type = Column(String, nullable=False)
    value = Column(String, nullable=False)
    ttl = Column(Integer, nullable=False, default=300)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
