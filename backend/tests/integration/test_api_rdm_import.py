"""
RDM import, as the app sends it
===============================

`rigsApi.importRdmDevices` (frontend/src/services/api.ts) posts the stored
devices' row ids as a bare JSON list and names the rig in the `rig_id` query
parameter. These tests post exactly that and check the devices land in the rig.

No RDM hardware or network: the devices are rows written straight into the
database, as a scan would store them.
"""

import pytest
from httpx import AsyncClient

from app.models.rdm_device import RDMDevice


async def _rig(client: AsyncClient, sample_rig_data, name: str) -> int:
    response = await client.post("/api/rigs/", json={**sample_rig_data, "name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _devices(db_session, *rows: dict) -> list[int]:
    devices = [RDMDevice(**row) for row in rows]
    db_session.add_all(devices)
    await db_session.flush()
    return [d.id for d in devices]


WASH = dict(
    uid_manufacturer=0x4D41, uid_device=1, manufacturer_label="Acme",
    model_description="Wash 7", device_label="SR wash", dmx_footprint=8,
    dmx_address=17, universe=1,
)
SPOT = dict(
    uid_manufacturer=0x4D41, uid_device=2, manufacturer_label="Acme",
    model_description="Spot 3", device_label=None, dmx_footprint=16,
    dmx_address=101, universe=1,
)


@pytest.mark.asyncio
async def test_import_as_the_app_sends_it_adds_the_devices_to_the_rig(
    client: AsyncClient, db_session, sample_rig_data
):
    rig_id = await _rig(client, sample_rig_data, "RDM import rig")
    ids = await _devices(db_session, WASH, SPOT)

    # Exactly the request the frontend makes: body is the list, rig in the query.
    response = await client.post("/api/rdm/import", json=ids, params={"rig_id": rig_id})
    assert 200 <= response.status_code < 300, response.text
    assert response.json() == {"imported": 2}

    rig = (await client.get(f"/api/rigs/{rig_id}")).json()
    patched = sorted((f["name"], f["universe"], f["dmx_address"]) for f in rig["fixtures"])
    assert patched == [("SR wash", 1, 17), ("Spot 3", 1, 101)]

    # The list the dialog reads shows both as imported now.
    listed = (await client.get("/api/rdm/devices")).json()["saved_devices"]
    assert {d["id"]: d["is_imported"] for d in listed if d["id"] in ids} == {ids[0]: True, ids[1]: True}


@pytest.mark.asyncio
async def test_a_device_already_imported_is_not_added_twice(
    client: AsyncClient, db_session, sample_rig_data
):
    rig_id = await _rig(client, sample_rig_data, "RDM import twice")
    ids = await _devices(db_session, {**WASH, "uid_device": 11})

    first = await client.post("/api/rdm/import", json=ids, params={"rig_id": rig_id})
    again = await client.post("/api/rdm/import", json=ids, params={"rig_id": rig_id})
    assert first.json() == {"imported": 1}
    assert again.json() == {"imported": 0}
    rig = (await client.get(f"/api/rigs/{rig_id}")).json()
    assert len(rig["fixtures"]) == 1


@pytest.mark.asyncio
async def test_the_shape_the_app_used_to_send_is_refused(
    client: AsyncClient, db_session, sample_rig_data
):
    """The old body, {device_uids: [...], rig_id}, never matched the route."""
    rig_id = await _rig(client, sample_rig_data, "RDM old shape")
    response = await client.post(
        "/api/rdm/import", json={"device_uids": ["4d41:00000001"], "rig_id": rig_id}
    )
    assert response.status_code == 422
