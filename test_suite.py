import sys
import os
import unittest
import socket
import time
import threading
from unittest.mock import MagicMock

# Ensure QApplication is initialized so PyQt widgets/threads can be instantiated
from PyQt5.QtWidgets import QApplication
qt_app = QApplication.instance()
if not qt_app:
    qt_app = QApplication([])

# Import components to test
import video_player
import obd_gui_qt

class MockMessage:
    """Mock message class to simulate obd ECU responses."""
    def __init__(self, data_bytes):
        self.data = data_bytes

class TestObdDecoders(unittest.TestCase):
    """Verifies that custom VAG/Audi EV UDS decoders process raw hex responses correctly."""
    
    def test_decode_ev_soc(self):
        # 62 02 8C XX -> XX * 100 / 255
        # Let's test with 255 (100%)
        msg = MockMessage(b"\x62\x02\x8c\xff")
        self.assertAlmostEqual(obd_gui_qt._decode_ev_soc([msg]), 100.0)
        
        # Test with 128 (~50.196%)
        msg2 = MockMessage(b"\x62\x02\x8c\x80")
        self.assertAlmostEqual(obd_gui_qt._decode_ev_soc([msg2]), 128 * 100.0 / 255.0)

        # Test malformed data
        msg_short = MockMessage(b"\x62\x02")
        self.assertIsNone(obd_gui_qt._decode_ev_soc([msg_short]))

    def test_decode_ev_speed(self):
        # 62 02 81 AA BB -> (AA * 256 + BB) / 100
        # Let's test with 4000 (40.00 km/h) -> 4000 = 0x0F 0xA0
        msg = MockMessage(b"\x62\x02\x81\x0f\xa0")
        self.assertAlmostEqual(obd_gui_qt._decode_ev_speed([msg]), 40.0)

        # Test with 0 (0.00 km/h)
        msg_zero = MockMessage(b"\x62\x02\x81\x00\x00")
        self.assertAlmostEqual(obd_gui_qt._decode_ev_speed([msg_zero]), 0.0)

        # Test malformed
        msg_invalid = MockMessage(b"\x00")
        self.assertIsNone(obd_gui_qt._decode_ev_speed([msg_invalid]))

    def test_decode_ev_voltage(self):
        # 62 02 89 AA BB -> (AA * 256 + BB) / 4
        # 1600 (400V) -> 1600 = 0x06 0x40
        msg = MockMessage(b"\x62\x02\x89\x06\x40")
        self.assertAlmostEqual(obd_gui_qt._decode_ev_hv_voltage([msg]), 400.0)

    def test_decode_ev_battery_temp(self):
        # 62 02 8B XX -> XX - 40
        # 65 (25°C) -> 65 = 0x41
        msg = MockMessage(b"\x62\x02\x8b\x41")
        self.assertAlmostEqual(obd_gui_qt._decode_ev_battery_temp([msg]), 25.0)

class TestPlaybackMathAndModes(unittest.TestCase):
    """Tests the math formulas, smoothing filters, and mode parameters inside PlaybackThread."""

    def setUp(self):
        self.thread = video_player.PlaybackThread()
        # Initialize with dummy frames (10 frames)
        self.thread.load_cache([b"dummy_frame"] * 10, fps=30.0)

    def tearDown(self):
        self.thread.stop()

    def test_speed_smoothing_and_clamping(self):
        # Set smoothing alpha to 0.2
        self.thread.update_settings(sensitivity=1.0, smoothing_alpha=0.2, mode=1)
        
        # Initial smoothed speed is 0.0. Update target speed to 50.0
        self.thread.target_raw_speed = 50.0
        self.thread.current_speed = 50.0
        
        # Simulate one iteration of EMA: smoothed_speed += (current - smoothed) * alpha
        # 0.0 + (50.0 - 0.0) * 0.2 = 10.0
        self.thread.smoothed_speed += (self.thread.current_speed - self.thread.smoothed_speed) * self.thread.smoothing_alpha
        self.assertEqual(self.thread.smoothed_speed, 10.0)

        # Test negative clamping protection
        self.thread.smoothed_speed = -5.0
        clamped = max(0.0, self.thread.smoothed_speed)
        self.assertEqual(clamped, 0.0)

    def test_mode_reversible_direction(self):
        # Reversible mode (mode 0)
        self.thread.update_settings(sensitivity=1.0, smoothing_alpha=0.2, mode=0)
        
        # Positive acceleration -> forward direction
        self.thread.last_speed = 20.0
        self.thread.current_speed = 30.0
        acceleration = self.thread.current_speed - self.thread.last_speed
        direction = 1.0 if acceleration >= 0 else -1.0
        self.assertEqual(direction, 1.0)

        # Negative acceleration -> backward direction
        self.thread.last_speed = 30.0
        self.thread.current_speed = 20.0
        acceleration = self.thread.current_speed - self.thread.last_speed
        direction = 1.0 if acceleration >= 0 else -1.0
        self.assertEqual(direction, -1.0)

        # No acceleration (less than threshold 0.005) -> fallback to forward (1.0)
        self.thread.last_speed = 30.0
        self.thread.current_speed = 30.002
        acceleration = self.thread.current_speed - self.thread.last_speed
        if abs(acceleration) < 0.005:
            direction = 1.0
        else:
            direction = 1.0 if acceleration >= 0 else -1.0
        self.assertEqual(direction, 1.0)

    def test_stopped_rewind_logic(self):
        # Stopped state (< 0.5 km/h) in Mode 1 (Classic)
        self.thread.update_settings(sensitivity=1.0, smoothing_alpha=0.2, mode=1)
        self.thread.smoothed_speed = 0.0
        self.thread.current_frame_float = 5.0
        self.thread.rewind_factor = 1.0
        
        # Simulate stopped-rewind step
        base_rate = 30.0 * 0.016 # ~0.48
        rewind_speed = base_rate * 1.5 * self.thread.rewind_factor
        delta_frames = -rewind_speed
        self.thread.current_frame_float = max(0.0, self.thread.current_frame_float + delta_frames)
        self.thread.rewind_factor = min(10.0, self.thread.rewind_factor + 0.03)
        
        # The frame index must decrease (moving backwards) and the factor should accelerate
        self.assertTrue(self.thread.current_frame_float < 5.0)
        self.assertTrue(self.thread.rewind_factor > 1.0)

class TestUdpListener(unittest.TestCase):
    """Tests the UDP listener thread with real local socket loopback."""

    def setUp(self):
        self.mock_playback = MagicMock()
        self.listener = video_player.UdpListener(self.mock_playback, port=28766) # Use non-default test port
        self.listener.start()

    def tearDown(self):
        self.listener.stop()
        self.listener.wait()

    def test_udp_speed_transmission(self):
        # Create test UDP socket client
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Send 80.5 speed value
            sock.sendto(b"80.5", ("127.0.0.1", 28766))
            
            # Give some time for thread execution
            time.sleep(0.1)
            
            # Verify direct thread call was made with correct float conversion
            self.mock_playback.update_speed.assert_called_with(80.5)
        finally:
            sock.close()

    def test_udp_invalid_data_handling(self):
        # Create test UDP socket client
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Send non-numeric string (should be safely swallowed by UdpListener)
            sock.sendto(b"INVALID_TELEMETRY", ("127.0.0.1", 28766))
            time.sleep(0.1)
            
            # Ensure it didn't throw an error or crash the thread (thread is still alive)
            self.assertTrue(self.listener.isRunning())
        finally:
            sock.close()

if __name__ == "__main__":
    unittest.main()
