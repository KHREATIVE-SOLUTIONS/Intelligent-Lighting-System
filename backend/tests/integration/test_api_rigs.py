"""
Integration Tests for Rigs API
==============================
"""

import pytest
from httpx import AsyncClient


class TestRigsAPI:
    """Integration tests for rigs endpoints."""

    @pytest.mark.asyncio
    async def test_create_rig(self, client: AsyncClient, sample_rig_data):
        """Test creating a new rig."""
        response = await client.post("/api/rigs/", json=sample_rig_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_rig_data["name"]
        assert data["venue"] == sample_rig_data["venue"]
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_rigs(self, client: AsyncClient, sample_rig_data):
        """Test listing rigs."""
        # Create a rig first
        await client.post("/api/rigs/", json=sample_rig_data)

        response = await client.get("/api/rigs/")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_get_rig(self, client: AsyncClient, sample_rig_data):
        """Test getting a specific rig."""
        # Create a rig
        create_response = await client.post("/api/rigs/", json=sample_rig_data)
        rig_id = create_response.json()["id"]

        response = await client.get(f"/api/rigs/{rig_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == rig_id
        assert data["name"] == sample_rig_data["name"]

    @pytest.mark.asyncio
    async def test_update_rig(self, client: AsyncClient, sample_rig_data):
        """Test updating a rig."""
        # Create a rig
        create_response = await client.post("/api/rigs/", json=sample_rig_data)
        rig_id = create_response.json()["id"]

        # Update it
        update_data = {
            "name": "Updated Rig Name",
            "stage_width": 15.0
        }
        response = await client.put(f"/api/rigs/{rig_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Rig Name"
        assert data["stage_width"] == 15.0

    @pytest.mark.asyncio
    async def test_delete_rig(self, client: AsyncClient, sample_rig_data):
        """Test deleting a rig."""
        # Create a rig
        create_response = await client.post("/api/rigs/", json=sample_rig_data)
        rig_id = create_response.json()["id"]

        # Delete it
        response = await client.delete(f"/api/rigs/{rig_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = await client.get(f"/api/rigs/{rig_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_activate_rig(self, client: AsyncClient, sample_rig_data):
        """Test activating a rig."""
        # Create two rigs
        rig1_response = await client.post(
            "/api/rigs/",
            json={**sample_rig_data, "name": "Rig 1"}
        )
        rig1_id = rig1_response.json()["id"]

        rig2_response = await client.post(
            "/api/rigs/",
            json={**sample_rig_data, "name": "Rig 2"}
        )
        rig2_id = rig2_response.json()["id"]

        # Activate rig 2
        response = await client.post(f"/api/rigs/{rig2_id}/activate")

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] == True

        # Check rig 1 is no longer active
        rig1_check = await client.get(f"/api/rigs/{rig1_id}")
        assert rig1_check.json()["is_active"] == False


class TestRigFixturesAPI:
    """Integration tests for rig fixture endpoints."""

    @pytest.mark.asyncio
    async def test_add_fixture_to_rig(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data
    ):
        """Test adding a fixture to a rig."""
        # Create rig
        rig_response = await client.post("/api/rigs/", json=sample_rig_data)
        rig_id = rig_response.json()["id"]

        # Create fixture
        fixture_response = await client.post("/api/fixtures/", json=sample_fixture_data)
        fixture_id = fixture_response.json()["id"]

        # Add fixture to rig
        rig_fixture_data = {
            "fixture_id": fixture_id,
            "name": "Front Left",
            "universe": 0,
            "dmx_address": 1,
            "position_x": -3.0,
            "position_y": 4.0,
            "position_z": 0.0,
        }
        response = await client.post(
            f"/api/rigs/{rig_id}/fixtures",
            json=rig_fixture_data
        )

        assert response.status_code == 201
        data = response.json()
        assert data["fixture_id"] == fixture_id
        assert data["dmx_address"] == 1

    @pytest.mark.asyncio
    async def test_list_rig_fixtures(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data
    ):
        """Test listing fixtures in a rig."""
        # Create rig and add fixture
        rig_response = await client.post("/api/rigs/", json=sample_rig_data)
        rig_id = rig_response.json()["id"]

        fixture_response = await client.post("/api/fixtures/", json=sample_fixture_data)
        fixture_id = fixture_response.json()["id"]

        await client.post(
            f"/api/rigs/{rig_id}/fixtures",
            json={"fixture_id": fixture_id, "dmx_address": 1}
        )

        # List fixtures
        response = await client.get(f"/api/rigs/{rig_id}/fixtures")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_dmx_address_conflict(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data
    ):
        """Test that duplicate DMX addresses are rejected."""
        # Create rig and fixture
        rig_response = await client.post("/api/rigs/", json=sample_rig_data)
        rig_id = rig_response.json()["id"]

        fixture_response = await client.post("/api/fixtures/", json=sample_fixture_data)
        fixture_id = fixture_response.json()["id"]

        # Add first fixture at address 1
        await client.post(
            f"/api/rigs/{rig_id}/fixtures",
            json={"fixture_id": fixture_id, "dmx_address": 1, "universe": 0}
        )

        # Try to add second fixture at same address
        response = await client.post(
            f"/api/rigs/{rig_id}/fixtures",
            json={"fixture_id": fixture_id, "dmx_address": 1, "universe": 0}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_rig_fixture(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data
    ):
        """Test updating a fixture in a rig."""
        # Create rig and add fixture
        rig_response = await client.post("/api/rigs/", json=sample_rig_data)
        rig_id = rig_response.json()["id"]

        fixture_response = await client.post("/api/fixtures/", json=sample_fixture_data)
        fixture_id = fixture_response.json()["id"]

        rig_fixture_response = await client.post(
            f"/api/rigs/{rig_id}/fixtures",
            json={"fixture_id": fixture_id, "dmx_address": 1}
        )
        rig_fixture_id = rig_fixture_response.json()["id"]

        # Update position
        response = await client.put(
            f"/api/rigs/{rig_id}/fixtures/{rig_fixture_id}",
            json={"position_x": 5.0, "position_y": 6.0}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["position_x"] == 5.0
        assert data["position_y"] == 6.0

    @pytest.mark.asyncio
    async def test_remove_fixture_from_rig(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data
    ):
        """Test removing a fixture from a rig."""
        # Create rig and add fixture
        rig_response = await client.post("/api/rigs/", json=sample_rig_data)
        rig_id = rig_response.json()["id"]

        fixture_response = await client.post("/api/fixtures/", json=sample_fixture_data)
        fixture_id = fixture_response.json()["id"]

        rig_fixture_response = await client.post(
            f"/api/rigs/{rig_id}/fixtures",
            json={"fixture_id": fixture_id, "dmx_address": 1}
        )
        rig_fixture_id = rig_fixture_response.json()["id"]

        # Remove fixture
        response = await client.delete(
            f"/api/rigs/{rig_id}/fixtures/{rig_fixture_id}"
        )
        assert response.status_code == 204

        # Verify it's gone
        list_response = await client.get(f"/api/rigs/{rig_id}/fixtures")
        assert len(list_response.json()) == 0
