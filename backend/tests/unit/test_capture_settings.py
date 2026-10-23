"""
Unit Tests for the Remembered Capture Choice
============================================

The device the operator picked, and whether capture was left running, survive
a reboot. A missing or broken file means nothing was chosen, never a crash.
"""

from app.services.audio import capture_settings


def test_nothing_chosen_yet(tmp_path):
    assert capture_settings.load(tmp_path) == {"device_name": None, "running": False}


def test_a_choice_survives_a_restart(tmp_path):
    capture_settings.save("Focusrite USB", running=True, data_dir=tmp_path)

    assert capture_settings.load(tmp_path) == {"device_name": "Focusrite USB", "running": True}


def test_stopping_keeps_the_device_and_clears_running(tmp_path):
    capture_settings.save("Focusrite USB", running=True, data_dir=tmp_path)
    capture_settings.set_running(False, data_dir=tmp_path)

    assert capture_settings.load(tmp_path) == {"device_name": "Focusrite USB", "running": False}


def test_a_broken_file_reads_as_nothing_chosen(tmp_path):
    capture_settings.settings_path(tmp_path).write_text("{not json")

    assert capture_settings.load(tmp_path) == {"device_name": None, "running": False}


def test_an_unwritable_place_does_not_raise(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    capture_settings.save("X", running=True, data_dir=blocker)  # parent is a file
