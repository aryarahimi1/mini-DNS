from typing import Literal, Optional

from pydantic import BaseModel, Field


class DNSRecordInput(BaseModel):
    type: Literal["A", "CNAME"]
    hostname: str
    value: str
    ttl: int = Field(default=3600, gt=0, le=86400)


class DNSRecordResponse(BaseModel):
    hostname: str
    type: str
    value: str
    createdAt: str


class ResolveResponse(BaseModel):
    hostname: str
    resolvedIps: list[str]
    recordType: str
    pointsTo: Optional[str] = None


class RecordItem(BaseModel):
    type: str
    value: str


class RecordListResponse(BaseModel):
    hostname: str
    records: list[RecordItem]


class DeleteResponse(BaseModel):
    message: str
    deleted: DNSRecordResponse
