"""Tests for the frame format, checked against the documented byte sequences.

Run with ``pytest tests`` or ``python -m unittest discover -s tests -t tests``.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _loader import protocol

# Command frames exactly as printed in "Control Commands for Cinema Projector
# Series 2", rev. 15.0. If any of these change, the projector stops answering.
DOCUMENTED_FRAMES = {
    "POWER ON (015)": ((0x02, 0x00, b""), "02 00 00 00 00 02"),
    "POWER OFF (016)": ((0x02, 0x01, b""), "02 01 00 00 00 03"),
    "PICTURE MUTE ON (020)": ((0x02, 0x10, b""), "02 10 00 00 00 12"),
    "PICTURE MUTE OFF (021)": ((0x02, 0x11, b""), "02 11 00 00 00 13"),
    "LENS MUTE ON (051)": ((0x02, 0x16, b""), "02 16 00 00 00 18"),
    "LENS MUTE OFF (052)": ((0x02, 0x17, b""), "02 17 00 00 00 19"),
    "INPUT TERMINAL (068)": ((0x00, 0xC1, b""), "00 c1 00 00 00 c1"),
    "SETTING REQUEST (078-1)": ((0x00, 0x85, b"\x00"), "00 85 00 00 01 00 86"),
    "RUNNING STATUS (078-2)": ((0x00, 0x85, b"\x01"), "00 85 00 00 01 01 87"),
    "INPUT STATUS (078-3)": ((0x00, 0x85, b"\x02"), "00 85 00 00 01 02 88"),
    "MUTE STATUS (078-4)": ((0x00, 0x85, b"\x03"), "00 85 00 00 01 03 89"),
    "MODEL NAME (078-5)": ((0x00, 0x85, b"\x04"), "00 85 00 00 01 04 8a"),
    "TEMPERATURE (078-204)": ((0x00, 0x85, b"\xe4"), "00 85 00 00 01 e4 6a"),
    "CURRENT TITLE (078-206)": ((0x00, 0x85, b"\xe6"), "00 85 00 00 01 e6 6c"),
    "LAMP INFORMATION 2 (037-2)": ((0x03, 0x94, b""), "03 94 00 00 00 97"),
}


class TestFrameBuilding(unittest.TestCase):
    """The wire format must match the document byte for byte."""

    def test_documented_frames(self):
        for name, (args, expected) in DOCUMENTED_FRAMES.items():
            with self.subTest(command=name):
                self.assertEqual(protocol.build_frame(*args).hex(" "), expected)

    def test_checksum_wraps_to_eight_bits(self):
        self.assertEqual(protocol.checksum(bytes([0xFF, 0xFF])), 0xFE)

    def test_projector_id_and_model_code(self):
        frame = protocol.build_frame(0x02, 0x00, b"", projector_id=0x41, model_code=0x0C)
        self.assertEqual(frame[2], 0x41)
        self.assertEqual(frame[3] >> 4, 0x0C)
        self.assertEqual(frame[-1], protocol.checksum(frame[:-1]))

    def test_long_data_uses_twelve_bit_length(self):
        frame = protocol.build_frame(0x02, 0x00, bytes(300))
        self.assertEqual(frame[3] & 0x0F, 1)
        self.assertEqual(frame[4], 300 - 256)
        self.assertEqual(protocol.data_length(frame[:5]), 300)

    def test_oversized_data_is_rejected(self):
        with self.assertRaises(ValueError):
            protocol.build_frame(0x02, 0x00, bytes(0x1000))


class TestFrameParsing(unittest.TestCase):
    """Responses must be validated before they are trusted."""

    def _response(self, id1=0x20, id2=0x85, data=b"\x01\x02"):
        frame = protocol.build_frame(id1, id2, data, projector_id=0x01, model_code=0x0C)
        return frame[:5], frame[5:]

    def test_round_trip(self):
        header, tail = self._response()
        response = protocol.parse_frame(header, tail)
        self.assertEqual(response.id2, 0x85)
        self.assertEqual(response.data, b"\x01\x02")
        self.assertEqual(response.model_code, 0x0C)
        self.assertFalse(response.is_nak)

    def test_bad_checksum_is_rejected(self):
        header, tail = self._response()
        corrupted = tail[:-1] + bytes([(tail[-1] + 1) & 0xFF])
        with self.assertRaises(ValueError):
            protocol.parse_frame(header, corrupted)

    def test_truncated_frame_is_rejected(self):
        header, tail = self._response()
        with self.assertRaises(ValueError):
            protocol.parse_frame(header, tail[:-1])

    def test_nak_is_recognised_and_decoded(self):
        header, tail = self._response(id1=0xA2, id2=0x00, data=bytes([0x07, 0x00]))
        response = protocol.parse_frame(header, tail)
        self.assertTrue(response.is_nak)
        self.assertEqual(response.error_code, (0x07, 0x00))
        self.assertEqual(response.error_text, "projector is not ready")

    def test_unknown_nak_code_still_produces_text(self):
        header, tail = self._response(id1=0xA2, id2=0x00, data=bytes([0x7E, 0x7F]))
        response = protocol.parse_frame(header, tail)
        self.assertIn("7E", response.error_text)


class TestValueHelpers(unittest.TestCase):
    """The little endian helpers decide whether temperatures make sense."""

    def test_unsigned_and_signed_differ(self):
        raw = bytes([0xC9, 0xFF])
        self.assertEqual(protocol.u16le(raw, 0), 65481)
        self.assertEqual(protocol.s16le(raw, 0), -55)

    def test_u32le(self):
        self.assertEqual(protocol.u32le(bytes([0x20, 0x1C, 0x00, 0x00]), 0), 7200)

    def test_cstring_stops_at_nul(self):
        self.assertEqual(protocol.cstring(b"NC2000C\x00\xff\xff"), "NC2000C")

    def test_cstring_honours_length(self):
        self.assertEqual(protocol.cstring(b"xxSCOPE 2Dyy", 2, 8), "SCOPE 2D")


if __name__ == "__main__":
    unittest.main()
