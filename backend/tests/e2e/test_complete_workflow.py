"""
End-to-End Tests
================

Complete workflow tests for the lighting system.
"""

import pytest
from httpx import AsyncClient


class TestCompleteWorkflow:
    """End-to-end tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_create_show_with_fixtures_and_cues(
        self,
        client: AsyncClient,
        sample_show_data,
        sample_rig_data,
        sample_fixture_data,
        sample_cue_data,
    ):
        """Test complete workflow: create show, rig, fixtures, and cues."""
        # Step 1: Create fixture in library
        fixture_response = await client.post(
            "/api/fixtures/",
            json=sample_fixture_data
        )
        assert fixture_response.status_code == 201
        fixture_id = fixture_response.json()["id"]

        # Step 2: Create rig
        rig_response = await client.post("/api/rigs/", json=sample_rig_data)
        assert rig_response.status_code == 201
        rig_id = rig_response.json()["id"]

        # Step 3: Add fixtures to rig
        for i in range(4):
            rig_fixture_data = {
                "fixture_id": fixture_id,
                "name": f"Moving Head {i+1}",
                "universe": 0,
                "dmx_address": 1 + (i * 16),  # 16 channels apart
                "position_x": -3.0 + (i * 2),
                "position_y": 4.0,
                "position_z": 0.0,
                "group_name": "front_truss"
            }
            fixture_add_response = await client.post(
                f"/api/rigs/{rig_id}/fixtures",
                json=rig_fixture_data
            )
            assert fixture_add_response.status_code == 201

        # Step 4: Create show
        show_response = await client.post("/api/shows/", json=sample_show_data)
        assert show_response.status_code == 201
        show_id = show_response.json()["id"]

        # Step 5: Create track
        track_response = await client.post(
            f"/api/shows/{show_id}/tracks",
            json={
                "name": "Moving Heads",
                "track_type": "fixture",
                "order": 0,
            }
        )
        assert track_response.status_code == 201
        track_id = track_response.json()["id"]

        # Step 6: Create cues
        cue_times = [0.0, 2.0, 4.0, 6.0]
        for i, start_time in enumerate(cue_times):
            cue_data = {
                **sample_cue_data,
                "name": f"Cue {i+1}",
                "start_time": start_time,
                "track_id": track_id,
            }
            cue_response = await client.post(
                f"/api/shows/{show_id}/cues",
                json=cue_data
            )
            assert cue_response.status_code == 201

        # Step 7: Verify complete show
        final_show = await client.get(f"/api/shows/{show_id}")
        assert final_show.status_code == 200

        show_data = final_show.json()
        assert show_data["name"] == sample_show_data["name"]
        assert len(show_data["tracks"]) == 1
        assert len(show_data["cues"]) == 4

        # Step 8: Verify rig
        final_rig = await client.get(f"/api/rigs/{rig_id}")
        assert final_rig.status_code == 200

        rig_data = final_rig.json()
        assert len(rig_data["fixtures"]) == 4

    @pytest.mark.asyncio
    async def test_duplicate_and_modify_show(
        self,
        client: AsyncClient,
        sample_show_data,
        sample_cue_data,
    ):
        """Test duplicating a show and modifying it."""
        # Create original show
        show_response = await client.post("/api/shows/", json=sample_show_data)
        original_id = show_response.json()["id"]

        # Add cues to original
        for i in range(3):
            await client.post(
                f"/api/shows/{original_id}/cues",
                json={**sample_cue_data, "name": f"Original Cue {i+1}", "start_time": i * 2.0}
            )

        # Duplicate show
        duplicate_response = await client.post(
            f"/api/shows/{original_id}/duplicate",
            params={"new_name": "Modified Version"}
        )
        assert duplicate_response.status_code == 201
        duplicate_id = duplicate_response.json()["id"]

        # Verify duplicate has same cues
        duplicate_cues = await client.get(f"/api/shows/{duplicate_id}/cues")
        assert len(duplicate_cues.json()) == 3

        # Modify duplicate
        await client.put(
            f"/api/shows/{duplicate_id}",
            json={"bpm": 140.0}
        )

        # Verify original is unchanged
        original_check = await client.get(f"/api/shows/{original_id}")
        assert original_check.json()["bpm"] == sample_show_data["bpm"]

        # Verify duplicate is changed
        duplicate_check = await client.get(f"/api/shows/{duplicate_id}")
        assert duplicate_check.json()["bpm"] == 140.0

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check endpoint."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        """Test root endpoint."""
        response = await client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert data["status"] == "running"
