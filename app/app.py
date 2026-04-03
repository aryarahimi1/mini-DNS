# @greptileai

import asyncio
import logging

from fastapi import FastAPI, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

from app.schemas import DNSRecordInput, DNSRecordResponse, ResolveResponse, RecordItem, RecordListResponse, DeleteResponse
from app.db import DNSRecord, async_session_maker, get_async_session, create_db_and_tables
from app.dns_logic import validate_hostname, validate_ipv4_address, check_cname_conflict, check_duplicate_record, resolve_cname, filter_expired, cleanup_expired_records

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 60


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

    if record.type == "A" and not validate_ipv4_address(record.value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid IPv4 address")

    if record.type == "CNAME" and not validate_hostname(record.value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CNAME target hostname")

    # check if there is a CNAME conflict
    if await check_cname_conflict(db, record.hostname, record.type):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CNAME conflict")

    # check if no duplicate in the records
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
async def resolve_hostname(hostname: str, db: AsyncSession = Depends(get_async_session)):
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
        resolved_ips = await resolve_cname(db, cname_record.value)

        return ResolveResponse(
            hostname=hostname,
            resolvedIps=resolved_ips,
            recordType="CNAME",
            pointsTo=cname_record.value,
        )

    ips = []
    for r in records:
        if r.type == "A":
            ips.append(r.value)

    return ResolveResponse(
        hostname=hostname,
        resolvedIps=ips,
        recordType="A",
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
