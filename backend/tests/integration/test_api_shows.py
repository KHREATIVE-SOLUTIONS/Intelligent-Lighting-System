"""
Integration Tests for Shows API
===============================
"""

import pytest
from httpx import AsyncClient


class TestShowsAPI:
    """Integration tests for shows endpoints."""

    @pytest.mark.asyncio
    async def test_create_show(self, client: AsyncClient, sample_show_data):
        """Test creating a new show."""
        response = await client.post("/api/shows/", json=sample_show_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_show_data["name"]
        assert data["bpm"] == sample_show_data["bpm"]
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_shows(self, client: AsyncClient, sample_show_data):
        """Test listing shows."""
        # Create a show first
        await client.post("/api/shows/", json=sample_show_data)

        response = await client.get("/api/shows/")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_get_show(self, client: AsyncClient, sample_show_data):
        """Test getting a specific show."""
        # Create a show
        create_response = await client.post("/api/shows/", json=sample_show_data)
        show_id = create_response.json()["id"]

        response = await client.get(f"/api/shows/{show_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == show_id
        assert data["name"] == sample_show_data["name"]

    @pytest.mark.asyncio
    async def test_get_show_not_found(self, client: AsyncClient):
        """Test getting a non-existent show."""
        response = await client.get("/api/shows/99999")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_show(self, client: AsyncClient, sample_show_data):
        """Test updating a show."""
        # Create a show
        create_response = await client.post("/api/shows/", json=sample_show_data)
        show_id = create_response.json()["id"]

        # Update it
        update_data = {"name": "Updated Show Name", "bpm": 140.0}
        response = await client.put(f"/api/shows/{show_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Show Name"
        assert data["bpm"] == 140.0

    @pytest.mark.asyncio
    async def test_delete_show(self, client: AsyncClient, sample_show_data):
        """Test deleting a show."""
        # Create a show
        create_response = await client.post("/api/shows/", json=sample_show_data)
        show_id = create_response.json()["id"]

        # Delete it
        response = await client.delete(f"/api/shows/{show_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = await client.get(f"/api/shows/{show_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_show(self, client: AsyncClient, sample_show_data):
        """Test duplicating a show."""
        # Create a show
        create_response = await client.post("/api/shows/", json=sample_show_data)
        show_id = create_response.json()["id"]

        # Duplicate it
        response = await client.post(
            f"/api/shows/{show_id}/duplicate",
            params={"new_name": "Duplicated Show"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Duplicated Show"
        assert data["id"] != show_id
        assert data["bpm"] == sample_show_data["bpm"]

    @pytest.mark.asyncio
    async def test_show_pagination(self, client: AsyncClient, sample_show_data):
        """Test show list pagination."""
        # Create multiple shows
        for i in range(5):
            show_data = {**sample_show_data, "name": f"Show {i}"}
            await client.post("/api/shows/", json=show_data)

        # Get first page
        response = await client.get("/api/shows/", params={"page": 1, "size": 2})
        data = response.json()

        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["size"] == 2

    @pytest.mark.asyncio
    async def test_show_search(self, client: AsyncClient, sample_show_data):
        """Test searching shows."""
        # Create shows with different names
        await client.post("/api/shows/", json={**sample_show_data, "name": "Rock Show"})
        await client.post("/api/shows/", json={**sample_show_data, "name": "Jazz Night"})

        # Search for "Rock"
        response = await client.get("/api/shows/", params={"search": "Rock"})
        data = response.json()

        assert data["total"] >= 1
        assert any("Rock" in item["name"] for item in data["items"])


class TestCuesAPI:
    """Integration tests for cue endpoints."""

    @pytest.mark.asyncio
    async def test_create_cue(
        self, client: AsyncClient, sample_show_data, sample_cue_data
    ):
        """Test creating a cue."""
        # Create a show first
        show_response = await client.post("/api/shows/", json=sample_show_data)
        show_id = show_response.json()["id"]

        # Create a cue
        response = await client.post(
            f"/api/shows/{show_id}/cues",
            json=sample_cue_data
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_cue_data["name"]
        assert data["show_id"] == show_id

    @pytest.mark.asyncio
    async def test_list_cues(
        self, client: AsyncClient, sample_show_data, sample_cue_data
    ):
        """Test listing cues."""
        # Create show and cue
        show_response = await client.post("/api/shows/", json=sample_show_data)
        show_id = show_response.json()["id"]
        await client.post(f"/api/shows/{show_id}/cues", json=sample_cue_data)

        # List cues
        response = await client.get(f"/api/shows/{show_id}/cues")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_update_cue(
        self, client: AsyncClient, sample_show_data, sample_cue_data
    ):
        """Test updating a cue."""
        # Create show and cue
        show_response = await client.post("/api/shows/", json=sample_show_data)
        show_id = show_response.json()["id"]
        cue_response = await client.post(
            f"/api/shows/{show_id}/cues",
            json=sample_cue_data
        )
        cue_id = cue_response.json()["id"]

        # Update cue
        update_data = {"name": "Updated Cue", "duration": 5.0}
        response = await client.put(
            f"/api/shows/{show_id}/cues/{cue_id}",
            json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Cue"
        assert data["duration"] == 5.0

    @pytest.mark.asyncio
    async def test_delete_cue(
        self, client: AsyncClient, sample_show_data, sample_cue_data
    ):
        """Test deleting a cue."""
        # Create show and cue
        show_response = await client.post("/api/shows/", json=sample_show_data)
        show_id = show_response.json()["id"]
        cue_response = await client.post(
            f"/api/shows/{show_id}/cues",
            json=sample_cue_data
        )
        cue_id = cue_response.json()["id"]

        # Delete cue
        response = await client.delete(f"/api/shows/{show_id}/cues/{cue_id}")
        assert response.status_code == 204
