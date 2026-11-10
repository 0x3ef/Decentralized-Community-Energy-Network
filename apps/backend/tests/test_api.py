"""Real database/API authorization and wallet proof of possession."""

from uuid import uuid4
import pytest
from httpx import AsyncClient, ASGITransport
from eth_account import Account
from eth_account.messages import encode_defunct
from src.main import app


@pytest.mark.asyncio
async def test_signup_home_membership_and_wallet_challenge():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        suffix = uuid4().hex[:7]
        assert (await client.get("/health")).status_code == 200
        assert (
            await client.post("/api/v1/communities", json={"name": "Unauthorized"})
        ).status_code in (401, 403)
        signup = await client.post(
            "/api/v1/auth/signup",
            json={
                "username": suffix,
                "email": suffix + "@example.com",
                "first_name": "Demo",
                "last_name": "Member",
                "password": "test-password-123",
            },
        )
        assert signup.status_code == 201, signup.text
        assert "password_hash" not in signup.json()["user"]
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": suffix + "@example.com", "password": "test-password-123"},
        )
        assert login.status_code == 200, login.text
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        community = await client.post(
            "/api/v1/communities", json={"name": "API Community"}
        )
        assert community.status_code == 201, community.text
        cid = community.json()["id"]
        home = await client.post(
            "/api/v1/home/",
            json={"name": "Consumer", "address": "Demo address", "city": "Cali"},
        )
        assert home.status_code == 201, home.text
        node = await client.post(
            f"/api/v1/communities/{cid}/nodes",
            json={"home_id": home.json()["home"]["id"]},
        )
        assert node.status_code == 403, node.text
        assert (await client.get(f"/api/v1/communities/{cid}/nodes")).status_code == 403
        meter = await client.post(
            "/api/v1/device/device",
            json={
                "home_id": home.json()["home"]["id"],
                "device_code": "SM-" + suffix,
                "device_type": "SMART_METER",
                "mqtt_client_id": "meter-" + suffix,
            },
        )
        assert meter.status_code == 201, meter.text
        address = Account.create()
        challenge = await client.post(
            "/api/v1/communities/wallet/challenge", json={"address": address.address}
        )
        assert challenge.status_code == 200, challenge.text
        proof = {
            "address": address.address,
            "nonce": challenge.json()["nonce"],
            "signature": Account.sign_message(
                encode_defunct(text=challenge.json()["message"]), address.key
            ).signature.hex(),
        }
        verified = await client.post("/api/v1/communities/wallet/verify", json=proof)
        assert verified.status_code == 200, verified.text
        assert verified.json()["is_verified"]
        assert (
            await client.post("/api/v1/communities/wallet/verify", json=proof)
        ).status_code == 422
        assert (
            await client.get(f"/api/v1/communities/{uuid4()}/statement")
        ).status_code == 403
