import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.db import DNSRecord


def validate_hostname(hostname: str) -> bool:
    if not hostname or len(hostname) > 253:
        return False

    # remove optional trailing dot
    if hostname.endswith("."):
        hostname = hostname[:-1]

    labels = hostname.split(".")
    if len(labels) < 2:
        return False

    pattern = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
    for label in labels:
        if not pattern.match(label):
            return False

    return True


def validate_ipv4_address(ip: str) -> bool:

    parts = ip.split(".")

    if len(parts) != 4:
        return False

    for part in parts:
        if not part.isdigit():
            return False
        if part != str(int(part)):
            return False
        num = int(part)
        if num < 0 or num > 255:
            return False

    return True


def is_record_expired(record: DNSRecord) -> bool:
    now = datetime.now(timezone.utc)
    created = record.created_at.replace(tzinfo=timezone.utc)
    age_seconds = (now - created).total_seconds()
    return age_seconds > record.ttl


def filter_expired(records: list[DNSRecord]) -> list[DNSRecord]:
    active = []
    for record in records:
        if not is_record_expired(record):
            active.append(record)
    return active


async def cleanup_expired_records(session_maker) -> int:
    async with session_maker() as session:
        result = await session.execute(select(DNSRecord))
        all_records = result.scalars().all()
        deleted = 0
        for record in all_records:
            if is_record_expired(record):
                await session.delete(record)
                deleted += 1
        await session.commit()
    return deleted


async def check_cname_conflict(db: AsyncSession, hostname: str, adding_type: str) -> bool:
    result = await db.execute(select(DNSRecord).where(DNSRecord.hostname == hostname))
    existing_records = filter_expired(result.scalars().all())

    if adding_type == "CNAME":
        if len(existing_records) > 0:
            return True

    else:
        for record in existing_records:
            if record.type == "CNAME":
                return True

    return False


async def check_duplicate_record(db: AsyncSession, hostname: str, type: str, value: str) -> bool:
    result = await db.execute(
        select(DNSRecord).where(
            DNSRecord.hostname == hostname,
            DNSRecord.type == type,
            DNSRecord.value == value,
        )
    )
    existing = filter_expired(result.scalars().all())

    if len(existing) > 0:
        return True

    return False


async def resolve_cname(db: AsyncSession, hostname: str, visited: set = None) -> list[str]:

    if visited is None:
        visited = set()

    if hostname in visited:
        raise HTTPException(status_code=400, detail=f"CNAME circular reference detected: {hostname}")

    visited.add(hostname)

    result = await db.execute(select(DNSRecord).where(DNSRecord.hostname == hostname))
    records = filter_expired(result.scalars().all())

    # Look for CNAME record
    cname_record = None
    for record in records:
        if record.type == "CNAME":
            cname_record = record
            break

    if cname_record:
        target_hostname = cname_record.value
        return await resolve_cname(db, target_hostname, visited)

    ips = []
    for record in records:
        if record.type == "A":
            ips.append(record.value)

    return ips
