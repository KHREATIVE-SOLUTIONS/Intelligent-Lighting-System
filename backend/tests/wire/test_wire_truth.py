"""
Wire truth: every row of "What works (measured)", section 4 of
docs/ASSESSMENT_AND_ROADMAP_2026-11.md, asserted from captured Art-Net.

One scripted run feeds every test here (see lifecycle.py). The figures in the
comments are what the November audit measured; the bounds are looser than those
figures so the tier trips on a regression, not on a busy machine. The exact
numbers of each run are written to wire_truth.json in the --wire-out directory.

Run:  pytest tests/wire --wire
"""
import asyncio

import pytest

from . import lifecycle

pytestmark = pytest.mark.wire

FPS = 40.0


@pytest.fixture(scope="module")
def m(wire_config) -> dict:
    measured = asyncio.run(lifecycle.run_lifecycle(wire_config))
    print(f"\nwire measurements: {wire_config.out / 'wire_truth.json'}")
    return measured


def _universes(analysis: dict) -> list:
    return analysis["transport"].values()


# ---- Fresh install, nothing patched --------------------------------------
def test_fresh_install_sends_nothing(m):
    """Audit: 0 packets in 5 s. A box with no rig must not talk to a venue's network."""
    assert m["fresh_install"]["packets"] == 0


# ---- Unauthenticated access ------------------------------------------------
def test_guarded_routes_are_real_routes(m):
    """A 401 from a path that does not exist proves nothing, so check the paths."""
    missing = [route for route, exists in m["guarded_routes_exist"].items() if not exists]
    assert not missing, f"probed routes are not in the app's route table: {missing}"


def test_unauthenticated_requests_are_refused(m):
    """Audit: rigs, blackout, raw DMX and strobe routes all 401."""
    statuses = m["unauthenticated"]["routes"]
    assert statuses and all(code == 401 for code in statuses.values()), statuses


def test_audio_websocket_refuses_a_missing_token(m):
    assert m["unauthenticated"]["audio_websocket_without_token"].startswith("refused")


def test_health_without_a_token_is_liveness_only(m):
    """Audit: /health gives liveness only. Targets and rig state need a session."""
    health = m["unauthenticated"]["health"]
    assert health["status_code"] in (200, 503)
    assert set(health["body"]) == {"status"}, health["body"]


# ---- First-run setup -------------------------------------------------------
def test_first_run_setup_with_the_console_code(m):
    """Audit: console setup code, then password, then token."""
    assert m["unauthenticated"]["auth_status"]["configured"] is False
    after = m["auth_status_after_setup"]
    assert after["configured"] is True and after["authenticated"] is True, after


# ---- Template to live rig --------------------------------------------------
def test_venue_templates_are_seeded(m):
    """Audit: 10 seeded templates."""
    assert len(m["templates"]) >= 10
    assert m["template"] in m["templates"]


def test_rig_from_template_is_live_without_a_restart(m):
    """Audit: apply plus activate puts the rig on stage with no restart."""
    live = m["rig_live"]
    assert live["fixtures"] > 0
    assert live["seconds_from_activate_to_first_frame"] is not None, "no Art-Net after activate"
    assert live["seconds_from_activate_to_first_frame"] <= 2.0
    assert live["no_audio_yet"]["universes_on_wire"] == live["universes_patched"]


# ---- Art-Net validity ------------------------------------------------------
def test_every_packet_is_valid_artnet(m):
    """Audit: correct header, version 14, 512-slot frames; 0 malformed in ~8,000."""
    assert m["total_packets"] > 3000
    assert m["capture_anomalies"] == {}, m["capture_anomalies"]
    assert m["packets_by_slot_count"] == {"512": m["total_packets"]}, m["packets_by_slot_count"]


def test_sequence_numbers_run_1_to_255_without_a_break(m):
    """Audit: sequence 1-255. 0 would tell a node to ignore ordering."""
    for uni in _universes(m["music"]):
        assert uni["seq_min"] == 1 and uni["seq_max"] == 255, uni
        assert uni["seq_breaks"] == 0, uni


def test_art_net_goes_to_loopback_and_is_not_broadcast(m):
    """The harness's own safety line: this tier must never reach a real rig."""
    detail = m["feed_lost"]["health"]["dmx_detail"]
    assert detail["target_ip"] == "127.0.0.1", detail
    assert detail["broadcast"] is False, detail


# ---- Frame rate ------------------------------------------------------------
def test_frame_rate_is_40_fps_under_music(m):
    """Audit: 40.0 fps; gaps alternate ~16 and ~31 ms; one 112 ms gap in four minutes.

    The soak holds the strict "no gap over 100 ms" line. This is a stall tripwire.
    """
    for uni in _universes(m["music"]):
        assert abs(uni["fps"] - FPS) <= 1.0, uni
        assert uni["gap_ms_p99"] <= 60.0, uni
        assert uni["gap_ms_max"] <= 250.0, uni


# ---- Universe ownership ----------------------------------------------------
@pytest.mark.parametrize("phase", ["music", "feed_lost", "reboot"])
def test_only_the_patched_universe_is_sent(m, phase):
    """Audit: only the patched universe is sent; 0 non-zero channels outside the patch."""
    analysis = {"music": m["music"], "feed_lost": m["feed_lost"]["settled_10_to_22s"],
                "reboot": m["reboot"]["wire"]}[phase]
    assert analysis["universes_on_wire"] == analysis["universes_patched"]
    assert analysis["unpatched_universes_transmitted"] == []
    assert analysis["nonzero_channels_outside_patch"] == 0


# ---- Blackout --------------------------------------------------------------
def test_blackout_is_dark_on_the_next_frame(m):
    """Audit: dark on the next frame. Allowed: frames already on their way at the ack."""
    bo = m["blackout"]
    assert bo["http_status"] == 200
    assert bo["level_before"]["rig_mean"] > 0.02, "the rig was not lit before the blackout"
    assert bo["last_lit_frame_s_after_ack"] <= 0.075, bo


def test_blackout_holds_under_loud_music(m):
    """Audit: 100% dark for 6 s under loud music."""
    bo = m["blackout"]
    assert bo["peak_level_later_than_0.5s"] == 0.0
    assert bo["level_while_latched"]["rig_max"] == 0.0
    assert bo["level_while_latched"]["pct_time_rig_dark"] == 100.0
    assert bo["dimmer_channel_max_while_latched"] == 0


def test_blackout_keeps_frames_flowing_and_heads_tracking(m):
    """Audit: heads keep tracking, frames keep flowing. A node must not time out."""
    bo = m["blackout"]
    for uni in bo["transport_while_latched"].values():
        assert abs(uni["fps"] - FPS) <= 1.0, uni
    move = bo["movement_while_latched"]
    assert move["movers"] > 0
    assert max(move["pan_range_used_pct_max"] or 0, move["tilt_range_used_pct_median"] or 0) > 0, move


def test_light_returns_after_restore(m):
    """Audit: light back 16-46 ms after restore."""
    bo = m["blackout"]
    assert bo["restore_http_status"] == 200
    assert bo["first_light_s_after_restore"] is not None, "the rig stayed dark after restore"
    assert bo["first_light_s_after_restore"] <= 0.5


# ---- Grand master ----------------------------------------------------------
def test_grand_master_scales_the_output(m):
    """Audit: 0.3 scales output to 0.29x. Two windows of live music, so a band."""
    gm = m["grand_master"]
    assert gm["http_status"] == 200
    assert 0.2 <= gm["ratio_rig_mean"] <= 0.4, gm
    assert gm["level_scaled"]["fixture_peak_max"] <= gm["level_set"] + 0.02, gm


def test_grand_master_leaves_movement_alone(m):
    """Audit: movement unaffected."""
    move = m["grand_master"]["movement_scaled"]
    assert max(move["pan_range_used_pct_max"] or 0, move["tilt_range_used_pct_median"] or 0) > 0, move


# ---- Tempo -----------------------------------------------------------------
def test_tempo_is_reported_for_a_128_bpm_track(m):
    """Audit: 127.8 BPM reported for a 128 BPM track."""
    audio = m["music"]["audio"]
    assert audio["analysis_messages"] > 0
    assert abs(audio["bpm_median_second_half"] - 128.0) <= 2.0, audio


# ---- Audio feed lost -------------------------------------------------------
def test_feed_loss_holds_a_steady_look(m):
    """Audit: holds an ambient look at ~22% within ~10 s. Not dark, not flashing."""
    lost = m["feed_lost"]["settled_10_to_22s"]
    assert lost["level"]["rig_mean"] >= 0.05, lost["level"]
    assert lost["level"]["pct_time_rig_dark"] == 0.0, lost["level"]
    assert lost["flash"]["rig_flash_edges"] == 0, lost["flash"]
    for uni in _universes(lost):
        assert abs(uni["fps"] - FPS) <= 1.0, uni


def test_show_recovers_when_music_returns(m):
    """Audit: recovers when music returns. The level moves with the music again."""
    level = m["music_returns"]["level"]
    assert level["rig_max"] - level["rig_min"] >= 0.05, level
    assert level["fixtures_ever_lit"] == level["fixtures_total"], level


# ---- Graceful stop ---------------------------------------------------------
def test_graceful_stop_exits_promptly_and_goes_quiet(m):
    """Audit: exits in 0.7 s and leaves the last look on the node.

    What is left on the node (last look or dark) is a product decision recorded
    in wire_truth.json, not asserted here; G2 owns the look at stop.
    """
    stop = m["graceful_stop"]
    assert stop["seconds_to_exit"] <= 10.0, stop
    assert stop["packets_later_than_0.5s_after_exit"] == 0, stop


# ---- Reboot ----------------------------------------------------------------
def test_reboot_brings_the_rig_back_by_itself(m):
    """Audit: rig comes back by itself; first Art-Net frame 4.1 s after process start."""
    reboot = m["reboot"]
    assert reboot["seconds_to_first_artnet_frame"] is not None, "no Art-Net after the reboot"
    assert reboot["seconds_to_first_artnet_frame"] <= 30.0, reboot
    for uni in _universes(reboot["wire"]):
        assert abs(uni["fps"] - FPS) <= 1.0, uni


def test_operator_password_survives_the_reboot(m):
    assert m["reboot"]["login_http_status"] == 200
