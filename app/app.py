import asyncio
import logging

from fastapi import FastAPI, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

from app.schemas import DNSRecordInput, DNSRecordResponse, ResolveResponse, RecordItem, RecordListResponse, DeleteResponse
from app.db import DNSRecord, async_session_maker, get_async_session, create_db_and_tables
from app.dns_logic import (
    validate_hostname,
    validate_ipv4_address,
    validate_ipv6_address,
    validate_mx_value,
    validate_txt_value,
    check_cname_conflict,
    check_duplicate_record,
    resolve_cname,
    filter_expired,
    cleanup_expired_records,
)

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 60

VALID_QUERY_TYPES = {"A", "AAAA", "CNAME", "MX", "TXT", "NS"}

RECORD_VALIDATORS = {
    "A": (validate_ipv4_address, "Invalid IPv4 address"),
    "AAAA": (validate_ipv6_address, "Invalid IPv6 address"),
    "CNAME": (validate_hostname, "Invalid CNAME target hostname"),
    "MX": (validate_mx_value, "Invalid MX value (expected: '<priority> <hostname>', e.g. '10 mail.example.com')"),
    "TXT": (validate_txt_value, "Invalid TXT value (must be 1-512 printable characters)"),
    "NS": (validate_hostname, "Invalid NS target hostname"),
}


async def ttl_cleanup_task():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            deleted = await cleanup_expired_records(async_session_maker)
            if deleted:
                logger.info(f"TTL cleanup: removed {deleted} expired record(s)")
        except Exception as e:
            logger.error(f"TTL cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    task = asyncio.create_task(ttl_cleanup_task())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)


@app.post("/api/dns", response_model=DNSRecordResponse)
async def add_dns_record(record: DNSRecordInput, db: AsyncSession = Depends(get_async_session)):

    if not validate_hostname(record.hostname):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid hostname")

    validator, error_msg = RECORD_VALIDATORS[record.type]
    if not validator(record.value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    if await check_cname_conflict(db, record.hostname, record.type):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CNAME conflict")

    if await check_duplicate_record(db, record.hostname, record.type, record.value):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate record")

    dns_record = DNSRecord(
        hostname=record.hostname,
        type=record.type,
        value=record.value,
        ttl=record.ttl,
    )

    db.add(dns_record)
    await db.commit()
    await db.refresh(dns_record)

    return DNSRecordResponse(
        hostname=dns_record.hostname,
        type=dns_record.type,
        value=dns_record.value,
        createdAt=str(dns_record.created_at),
    )


@app.get("/api/dns/{hostname}", response_model=ResolveResponse)
async def resolve_hostname(
    hostname: str,
    type: str = Query(default="A"),
    db: AsyncSession = Depends(get_async_session),
):
    if type not in VALID_QUERY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid query type. Must be one of: {', '.join(sorted(VALID_QUERY_TYPES))}",
        )

    result = await db.execute(select(DNSRecord).where(DNSRecord.hostname == hostname))
    records = filter_expired(result.scalars().all())

    if not records:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hostname not found")

    cname_record = None
    for r in records:
        if r.type == "CNAME":
            cname_record = r
            break

    if cname_record:
        resolved_values = await resolve_cname(db, cname_record.value, type)

        return ResolveResponse(
            hostname=hostname,
            values=resolved_values,
            recordType="CNAME",
            pointsTo=cname_record.value,
        )

    values = [r.value for r in records if r.type == type]

    return ResolveResponse(
        hostname=hostname,
        values=values,
        recordType=type,
    )

@app.get("/api/dns/{hostname}/records", response_model=RecordListResponse)

async def get_dns_records(hostname: str, db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(select(DNSRecord).where(DNSRecord.hostname == hostname))
    records = filter_expired(result.scalars().all())

    if not records:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hostname not found")
    
    records_list = []

    for r in records:
        records_list.append(RecordItem(type=r.type, value=r.value))

    return RecordListResponse(
        hostname=hostname,
        records=records_list,
    )

@app.delete("/api/dns/{hostname}", response_model=DeleteResponse)
async def delete_dns_record(hostname: str, type: str = Query(...), value: str = Query(...), db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(
        select(DNSRecord).where(
            DNSRecord.hostname == hostname,
            DNSRecord.type == type,
            DNSRecord.value == value,
        )
    )
    record = result.scalars().first()

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    deleted = DNSRecordResponse(
        hostname=record.hostname,
        type=record.type,
        value=record.value,
        createdAt=str(record.created_at),
    )

    await db.delete(record)
    await db.commit()

    return DeleteResponse(message="Record deleted successfully", deleted=deleted)
