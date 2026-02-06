"""
MIDI Controller for grandMA2 Fader Wing and other MIDI devices

Captures MIDI input and maps it to lighting control operations.
Supports:
- grandMA2 Fader Wing
- Generic MIDI controllers
- Ableton Push / Launchpad
"""

import threading
import time
from typing import Optional, Callable, Dict, List, Any
from dataclasses import dataclass
from enum import Enum

try:
    import mido
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False
    print("[MIDI] mido not installed. Run: pip install mido python-rtmidi")


class MIDIMessageType(Enum):
    NOTE_ON = 0x90
    NOTE_OFF = 0x80
    CONTROL_CHANGE = 0xB0
    PROGRAM_CHANGE = 0xC0
    PITCH_BEND = 0xE0


@dataclass
class MIDIMapping:
    """Defines how a MIDI control maps to a lighting function."""
    midi_type: MIDIMessageType
    channel: int  # 0-15
    control: int  # CC number or note number
    function: str  # e.g., 'dimmer', 'color_red', 'movement_circle'
    min_value: float = 0.0
    max_value: float = 1.0


# Default mappings for grandMA2 fader wing
GRANDMA2_MAPPINGS = [
    # Faders (typically CC 1-8 on channel 1)
    MIDIMapping(MIDIMessageType.CONTROL_CHANGE, 0, 1, 'master_dimmer'),
    MIDIMapping(MIDIMessageType.CONTROL_CHANGE, 0, 2, 'pan_offset'),
    MIDIMapping(MIDIMessageType.CONTROL_CHANGE, 0, 3, 'tilt_offset'),
    MIDIMapping(MIDIMessageType.CONTROL_CHANGE, 0, 4, 'movement_speed'),
    MIDIMapping(MIDIMessageType.CONTROL_CHANGE, 0, 5, 'strobe_rate'),

    # Executor buttons (notes)
    # Row 1: Colors
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 60, 'color_white'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 61, 'color_red'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 62, 'color_orange'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 63, 'color_yellow'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 64, 'color_green'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 65, 'color_cyan'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 66, 'color_blue'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 67, 'color_purple'),

    # Row 2: Movements
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 72, 'movement_none'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 73, 'movement_circle'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 74, 'movement_sweep'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 75, 'movement_figure8'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 76, 'movement_chase'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 77, 'movement_ballyhoo'),

    # Row 3: Triggers
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 84, 'trigger_strobe'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 85, 'trigger_blackout'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 86, 'trigger_flash'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 87, 'trigger_drop'),
    MIDIMapping(MIDIMessageType.NOTE_ON, 0, 88, 'trigger_buildup'),
]


class MIDIController:
    """
    Handles MIDI input from controllers like grandMA2 fader wing.

    Usage:
        midi = MIDIController()
        midi.set_callback(my_handler)
        midi.start()
    """

    def __init__(self, device_name: str = None):
        self.device_name = device_name
        self.running = False
        self.input_port = None
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable] = None
        self.mappings: List[MIDIMapping] = GRANDMA2_MAPPINGS.copy()
        self.manual_controller = None

    def list_devices(self) -> List[str]:
        """List available MIDI input devices."""
        if not MIDO_AVAILABLE:
            return []
        try:
            return mido.get_input_names()
        except Exception as e:
            print(f"[MIDI] Error listing devices: {e}")
            return []

    def set_callback(self, callback: Callable[[str, float], None]):
        """
        Set callback for MIDI events.

        Callback receives: (function_name: str, value: float)
        """
        self._callback = callback

    def set_manual_controller(self, controller):
        """Attach the manual lighting controller."""
        self.manual_controller = controller

    def start(self, device_name: str = None) -> bool:
        """Start listening for MIDI input."""
        if not MIDO_AVAILABLE:
            print("[MIDI] mido not available")
            return False

        if self.running:
            return True

        device = device_name or self.device_name
        devices = self.list_devices()

        if not devices:
            print("[MIDI] No MIDI devices found")
            return False

        # Find matching device or use first available
        target_device = None
        if device:
            for d in devices:
                if device.lower() in d.lower():
                    target_device = d
                    break
        if not target_device:
            target_device = devices[0]

        try:
            self.input_port = mido.open_input(target_device)
            self.running = True
            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            print(f"[MIDI] Listening on: {target_device}")
            return True
        except Exception as e:
            print(f"[MIDI] Failed to open {target_device}: {e}")
            return False

    def stop(self):
        """Stop listening for MIDI input."""
        self.running = False
        if self.input_port:
            try:
                self.input_port.close()
            except:
                pass
        self.input_port = None

    def _listen_loop(self):
        """Background thread for MIDI input."""
        while self.running and self.input_port:
            try:
                for msg in self.input_port.iter_pending():
                    self._process_message(msg)
                time.sleep(0.001)  # 1ms polling
            except Exception as e:
                if self.running:
                    print(f"[MIDI] Error: {e}")
                break

    def _process_message(self, msg):
        """Process a MIDI message."""
        # Determine message type
        if msg.type == 'note_on' and msg.velocity > 0:
            midi_type = MIDIMessageType.NOTE_ON
            control = msg.note
            value = msg.velocity / 127.0
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            midi_type = MIDIMessageType.NOTE_OFF
            control = msg.note
            value = 0.0
        elif msg.type == 'control_change':
            midi_type = MIDIMessageType.CONTROL_CHANGE
            control = msg.control
            value = msg.value / 127.0
        else:
            return  # Ignore other message types

        channel = msg.channel if hasattr(msg, 'channel') else 0

        # Find matching mapping
        for mapping in self.mappings:
            if (mapping.midi_type == midi_type and
                mapping.channel == channel and
                mapping.control == control):

                # Scale value to mapping range
                scaled_value = mapping.min_value + value * (mapping.max_value - mapping.min_value)

                # Execute action
                self._execute_action(mapping.function, scaled_value)

                # Call user callback
                if self._callback:
                    self._callback(mapping.function, scaled_value)

                break

        # Debug output
        print(f"[MIDI] {midi_type.name} ch={channel} ctrl={control} val={value:.2f}")

    def _execute_action(self, function: str, value: float):
        """Execute a lighting control action."""
        if not self.manual_controller:
            return

        mc = self.manual_controller

        # Dimmer
        if function == 'master_dimmer':
            mc.set_global_dimmer(value)

        # Colors
        elif function.startswith('color_'):
            color = function.replace('color_', '')
            mc.set_color_preset(color)

        # Movements
        elif function.startswith('movement_'):
            pattern = function.replace('movement_', '')
            mc.set_movement(pattern)

        # Triggers
        elif function == 'trigger_strobe':
            mc.trigger_strobe(0.5)
        elif function == 'trigger_blackout':
            mc.trigger_blackout()
        elif function == 'trigger_flash':
            mc.trigger_flash()

    def add_mapping(self, mapping: MIDIMapping):
        """Add a custom MIDI mapping."""
        self.mappings.append(mapping)

    def clear_mappings(self):
        """Clear all mappings."""
        self.mappings.clear()

    def load_grandma2_mappings(self):
        """Load default grandMA2 fader wing mappings."""
        self.mappings = GRANDMA2_MAPPINGS.copy()

    def get_status(self) -> Dict[str, Any]:
        """Get MIDI controller status."""
        return {
            'available': MIDO_AVAILABLE,
            'running': self.running,
            'device': self.input_port.name if self.input_port else None,
            'devices': self.list_devices(),
            'mapping_count': len(self.mappings)
        }


# Global instance
_midi_controller: Optional[MIDIController] = None


def get_midi_controller() -> MIDIController:
    """Get or create global MIDI controller instance."""
    global _midi_controller
    if _midi_controller is None:
        _midi_controller = MIDIController()
    return _midi_controller


def set_midi_controller(controller: MIDIController):
    """Set global MIDI controller instance."""
    global _midi_controller
    _midi_controller = controller
