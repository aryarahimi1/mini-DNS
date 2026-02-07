"""Integration tests for DNS API endpoints."""

import asyncio

import pytest
from httpx import AsyncClient


# ── Helper ─────────────────────────────────────────────────────────


async def add_record(client: AsyncClient, hostname: str, rtype: str, value: str, ttl: int = 3600):
    """Shortcut to POST a DNS record."""
    return await client.post("/api/dns", json={
        "type": rtype,
        "hostname": hostname,
        "value": value,
        "ttl": ttl,
    })


# ── POST /api/dns  ─────────────────────────────────────────────────


class TestAddRecord:

    async def test_add_a_record(self, client: AsyncClient):
        resp = await add_record(client, "example.com", "A", "192.168.1.1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hostname"] == "example.com"
        assert data["type"] == "A"
        assert data["value"] == "192.168.1.1"
        assert "createdAt" in data

    async def test_add_cname_record(self, client: AsyncClient):
        resp = await add_record(client, "alias.example.com", "CNAME", "example.com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "CNAME"
        assert data["value"] == "example.com"

    async def test_add_multiple_a_records(self, client: AsyncClient):
        resp1 = await add_record(client, "example.com", "A", "192.168.1.1")
        resp2 = await add_record(client, "example.com", "A", "192.168.1.2")
        assert resp1.status_code == 200
        assert resp2.status_code == 200

    async def test_reject_invalid_hostname(self, client: AsyncClient):
        resp = await add_record(client, "not valid!", "A", "192.168.1.1")
        assert resp.status_code == 400
        assert "Invalid hostname" in resp.json()["detail"]

    async def test_reject_invalid_ipv4(self, client: AsyncClient):
        resp = await add_record(client, "example.com", "A", "999.999.999.999")
        assert resp.status_code == 400
        assert "Invalid IPv4" in resp.json()["detail"]

    async def test_reject_ipv4_with_leading_zeros(self, client: AsyncClient):
        resp = await add_record(client, "example.com", "A", "01.02.03.04")
        assert resp.status_code == 400

    async def test_reject_invalid_cname_target(self, client: AsyncClient):
        resp = await add_record(client, "alias.example.com", "CNAME", "!!!bad!!!")
        assert resp.status_code == 400
        assert "Invalid CNAME target" in resp.json()["detail"]

    async def test_reject_cname_when_a_exists(self, client: AsyncClient):
        await add_record(client, "example.com", "A", "192.168.1.1")
        resp = await add_record(client, "example.com", "CNAME", "other.com")
        assert resp.status_code == 409
        assert "CNAME conflict" in resp.json()["detail"]

    async def test_reject_a_when_cname_exists(self, client: AsyncClient):
        await add_record(client, "example.com", "CNAME", "other.com")
        resp = await add_record(client, "example.com", "A", "192.168.1.1")
        assert resp.status_code == 409
        assert "CNAME conflict" in resp.json()["detail"]

    async def test_reject_duplicate_a_record(self, client: AsyncClient):
        await add_record(client, "example.com", "A", "192.168.1.1")
        resp = await add_record(client, "example.com", "A", "192.168.1.1")
        assert resp.status_code == 409
        assert "Duplicate" in resp.json()["detail"]

    async def test_reject_second_cname_same_hostname(self, client: AsyncClient):
        await add_record(client, "alias.example.com", "CNAME", "example.com")
        resp = await add_record(client, "alias.example.com", "CNAME", "example.com")
        assert resp.status_code == 409

    async def test_reject_invalid_record_type(self, client: AsyncClient):
        resp = await client.post("/api/dns", json={
            "type": "MX",
            "hostname": "example.com",
            "value": "mail.example.com",
        })
        assert resp.status_code == 422  # Pydantic validation error

    async def test_reject_ttl_zero(self, client: AsyncClient):
        resp = await add_record(client, "example.com", "A", "192.168.1.1", ttl=0)
        assert resp.status_code == 422

    async def test_reject_ttl_negative(self, client: AsyncClient):
        resp = await add_record(client, "example.com", "A", "192.168.1.1", ttl=-100)
        assert resp.status_code == 422

    async def test_reject_ttl_too_large(self, client: AsyncClient):
        resp = await add_record(client, "example.com", "A", "192.168.1.1", ttl=100000)
        assert resp.status_code == 422


# ── GET /api/dns/{hostname}  (resolve) ─────────────────────────────


class TestResolveHostname:

    async def test_resolve_a_record(self, client: AsyncClient):
        await add_record(client, "example.com", "A", "192.168.1.1")
        resp = await client.get("/api/dns/example.com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hostname"] == "example.com"
        assert data["recordType"] == "A"
        assert "192.168.1.1" in data["resolvedIps"]
        assert data["pointsTo"] is None

    async def test_resolve_multiple_a_records(self, client: AsyncClient):
        await add_record(client, "example.com", "A", "192.168.1.1")
        await add_record(client, "example.com", "A", "192.168.1.2")
        resp = await client.get("/api/dns/example.com")
        assert resp.status_code == 200
        ips = resp.json()["resolvedIps"]
        assert len(ips) == 2
        assert "192.168.1.1" in ips
        assert "192.168.1.2" in ips

    async def test_resolve_cname_to_a(self, client: AsyncClient):
        await add_record(client, "example.com", "A", "192.168.1.1")
        await add_record(client, "alias.example.com", "CNAME", "example.com")
        resp = await client.get("/api/dns/alias.example.com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recordType"] == "CNAME"
        assert data["pointsTo"] == "example.com"
        assert "192.168.1.1" in data["resolvedIps"]

    async def test_resolve_cname_chain(self, client: AsyncClient):
        """a.example.com -> b.example.com -> c.example.com (A: 10.0.0.1)"""
        await add_record(client, "c.example.com", "A", "10.0.0.1")
        await add_record(client, "b.example.com", "CNAME", "c.example.com")
        await add_record(client, "a.example.com", "CNAME", "b.example.com")
        resp = await client.get("/api/dns/a.example.com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recordType"] == "CNAME"
        assert data["pointsTo"] == "b.example.com"
        assert "10.0.0.1" in data["resolvedIps"]

    async def test_resolve_circular_cname(self, client: AsyncClient):
        """a.example.com -> b.example.com -> a.example.com (circular)"""
        await add_record(client, "a.example.com", "CNAME", "b.example.com")
        await add_record(client, "b.example.com", "CNAME", "a.example.com")
        resp = await client.get("/api/dns/a.example.com")
        assert resp.status_code == 400
        assert "circular" in resp.json()["detail"].lower()

    async def test_resolve_not_found(self, client: AsyncClient):
        resp = await client.get("/api/dns/nonexistent.example.com")
        assert resp.status_code == 404

    async def test_resolve_cname_target_not_found(self, client: AsyncClient):
        """CNAME points to a hostname with no records — resolves to empty IPs."""
        await add_record(client, "alias.example.com", "CNAME", "missing.example.com")
        resp = await client.get("/api/dns/alias.example.com")
        assert resp.status_code == 200
        assert resp.json()["resolvedIps"] == []


# ── GET /api/dns/{hostname}/records  ───────────────────────────────


class TestListRecords:

    async def test_list_a_records(self, client: AsyncClient):
        await add_record(client, "example.com", "A", "192.168.1.1")
        await add_record(client, "example.com", "A", "192.168.1.2")
        resp = await client.get("/api/dns/example.com/records")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hostname"] == "example.com"
        assert len(data["records"]) == 2
        values = [r["value"] for r in data["records"]]
        assert "192.168.1.1" in values
        assert "192.168.1.2" in values

    async def test_list_cname_record(self, client: AsyncClient):
        await add_record(client, "alias.example.com", "CNAME", "example.com")
        resp = await client.get("/api/dns/alias.example.com/records")
        assert resp.status_code == 200
        records = resp.json()["records"]
        assert len(records) == 1
        assert records[0]["type"] == "CNAME"
        assert records[0]["value"] == "example.com"

    async def test_list_not_found(self, client: AsyncClient):
        resp = await client.get("/api/dns/nonexistent.example.com/records")
        assert resp.status_code == 404


# ── DELETE /api/dns/{hostname}  ────────────────────────────────────


class TestDeleteRecord:

    async def test_delete_specific_a_record(self, client: AsyncClient):
        await add_record(client, "example.com", "A", "192.168.1.1")
        await add_record(client, "example.com", "A", "192.168.1.2")
        resp = await client.delete("/api/dns/example.com", params={"type": "A", "value": "192.168.1.1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Record deleted successfully"
        assert data["deleted"]["value"] == "192.168.1.1"

        # Verify only one record remains
        list_resp = await client.get("/api/dns/example.com/records")
        assert len(list_resp.json()["records"]) == 1
        assert list_resp.json()["records"][0]["value"] == "192.168.1.2"

    async def test_delete_cname_record(self, client: AsyncClient):
        await add_record(client, "alias.example.com", "CNAME", "example.com")
        resp = await client.delete("/api/dns/alias.example.com", params={"type": "CNAME", "value": "example.com"})
        assert resp.status_code == 200

        # Verify it's gone
        list_resp = await client.get("/api/dns/alias.example.com/records")
        assert list_resp.status_code == 404

    async def test_delete_not_found(self, client: AsyncClient):
        resp = await client.delete("/api/dns/example.com", params={"type": "A", "value": "1.2.3.4"})
        assert resp.status_code == 404

    async def test_delete_wrong_value(self, client: AsyncClient):
        await add_record(client, "example.com", "A", "192.168.1.1")
        resp = await client.delete("/api/dns/example.com", params={"type": "A", "value": "10.0.0.1"})
        assert resp.status_code == 404

    async def test_delete_missing_query_params(self, client: AsyncClient):
        resp = await client.delete("/api/dns/example.com")
        assert resp.status_code == 422  # missing required query params


# ── TTL Expiration ─────────────────────────────────────────────────


class TestTTLExpiration:

    async def test_expired_record_not_resolved(self, client: AsyncClient):
        """Record with 1s TTL should expire after waiting 2 seconds."""
        await add_record(client, "example.com", "A", "192.168.1.1", ttl=1)
        await asyncio.sleep(2)
        resp = await client.get("/api/dns/example.com")
        assert resp.status_code == 404

    async def test_expired_record_not_listed(self, client: AsyncClient):
        """Expired records should not appear in record listings."""
        await add_record(client, "example.com", "A", "192.168.1.1", ttl=1)
        await asyncio.sleep(2)
        resp = await client.get("/api/dns/example.com/records")
        assert resp.status_code == 404

    async def test_active_record_still_resolved(self, client: AsyncClient):
        """Record with long TTL should still be resolvable."""
        await add_record(client, "example.com", "A", "192.168.1.1", ttl=3600)
        resp = await client.get("/api/dns/example.com")
        assert resp.status_code == 200
        assert "192.168.1.1" in resp.json()["resolvedIps"]

    async def test_can_add_after_cname_expires(self, client: AsyncClient):
        """After a CNAME expires, adding a new A record should succeed (no conflict)."""
        await add_record(client, "example.com", "CNAME", "other.com", ttl=1)
        await asyncio.sleep(2)
        resp = await add_record(client, "example.com", "A", "192.168.1.1")
        assert resp.status_code == 200
