"""Tests for the client and the command layer, against a fake projector.

Run with ``pytest tests`` or ``python -m unittest discover -s tests -t tests``.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _loader import client as client_module
from fake_projector import FakeProjector

NecClient = client_module.NecClient
NecProjector = client_module.NecProjector
NecError = client_module.NecError
NecNakError = client_module.NecNakError


class ProjectorTestCase(unittest.IsolatedAsyncioTestCase):
    """Bring a fake projector up for every test."""

    async def asyncSetUp(self):
        self.fake = FakeProjector()
        port = await self.fake.start()
        self.client = NecClient("127.0.0.1", port, timeout=2.0)
        self.projector = NecProjector(self.client)

    async def asyncTearDown(self):
        await self.client.close()
        await self.fake.stop()


class TestStaticInformation(ProjectorTestCase):
    """What the integration reads once, at setup."""

    async def test_model_and_serial(self):
        self.assertEqual(await self.projector.model_name(), "NC2000C")
        self.assertEqual(await self.projector.serial_number(), "02A1234EB")

    async def test_projector_type(self):
        self.assertEqual(await self.projector.projector_type(), (0x0C, 0x08, 0x0A))

    async def test_available_ports(self):
        self.assertEqual(
            await self.projector.available_ports(), [0x1A, 0x1B, 0x38, 0x3B]
        )

    async def test_thermal_sensors_not_supported_on_this_model(self):
        with self.assertRaises(NecNakError):
            await self.projector.thermal_sensor_count()

    async def test_thermal_sensors_when_supported(self):
        self.fake.parts_supported = True
        self.assertEqual(await self.projector.thermal_sensor_count(), 2)
        self.assertEqual(await self.projector.thermal_sensor_name(0), "DMD")
        self.assertEqual(await self.projector.temperature_modern(0), 31.2)


class TestStatusParsing(ProjectorTestCase):
    """The values the entities are built from."""

    async def test_running_status(self):
        status = await self.projector.running_status()
        self.assertTrue(status["power_on"])
        self.assertTrue(status["light_on"])
        self.assertEqual(status["process_status"], 0x04)
        self.assertEqual(status["cooling_remaining"], 300)

    async def test_running_status_when_off(self):
        self.fake.power = False
        status = await self.projector.running_status()
        self.assertFalse(status["power_on"])
        self.assertFalse(status["light_on"])

    async def test_mute_status_neutral(self):
        self.assertEqual(
            await self.projector.mute_status(),
            {"douser_closed": False, "picture_mute": False},
        )

    async def test_mute_status_picture_mute_only(self):
        self.fake.picture_mute = True
        status = await self.projector.mute_status()
        self.assertTrue(status["picture_mute"])
        self.assertFalse(status["douser_closed"])

    async def test_mute_status_closed_douser_is_not_picture_mute(self):
        # The projector reports 81H for a closed douser. That must not be
        # mistaken for an electronic picture mute, or the switch lies.
        self.fake.douser_closed = True
        status = await self.projector.mute_status()
        self.assertTrue(status["douser_closed"])
        self.assertFalse(status["picture_mute"])

    async def test_input_status_maps_the_media_block(self):
        status = await self.projector.input_status()
        self.assertEqual(status["port_key"], (0x04, 0x0C))
        self.assertFalse(status["test_pattern"])

    async def test_current_title(self):
        title = await self.projector.current_title()
        self.assertEqual(title["title_name"], "SCOPE 2D")
        self.assertEqual(title["title_number"], 5)
        self.assertEqual(title["preset_number"], 2)

    async def test_errors_are_decoded_to_text(self):
        codes = await self.projector.error_numbers()
        self.assertEqual(codes, [0x2A, 0x2B])
        self.assertEqual(await self.projector.error_string(0x2A), "Douser error")
        self.assertEqual(await self.projector.error_string(0x2B), "Fan 3 stopped")

    async def test_temperatures_legacy_handles_invalid_and_negative(self):
        values = await self.projector.temperatures_legacy(3)
        self.assertEqual(values[0], 24.5)
        self.assertIsNone(values[1])  # 7FFFH means the sensor could not be read
        self.assertEqual(values[2], -5.5)


class TestLampFallback(ProjectorTestCase):
    """Older heads answer a different lamp command than current ones."""

    async def test_modern_command_refused_on_old_head(self):
        with self.assertRaises(NecNakError) as caught:
            await self.projector.light_hours_modern()
        self.assertIn("does not support", str(caught.exception))

    async def test_legacy_command_returns_hours(self):
        self.assertEqual(await self.projector.light_hours_legacy(), 2.0)

    async def test_modern_command_on_a_newer_head(self):
        self.fake.modern_lamp_supported = True
        self.assertEqual(await self.projector.light_hours_modern(), 1234)

    async def test_light_power(self):
        self.assertEqual(await self.projector.light_power(), 87.5)


class TestCommands(ProjectorTestCase):
    """Commands must reach the projector and change its state."""

    async def test_power(self):
        await self.projector.power_off()
        self.assertFalse(self.fake.power)
        await self.projector.power_on()
        self.assertTrue(self.fake.power)

    async def test_douser(self):
        await self.projector.douser_close()
        self.assertTrue(self.fake.douser_closed)
        await self.projector.douser_open()
        self.assertFalse(self.fake.douser_closed)

    async def test_picture_mute_refused_while_douser_is_closed(self):
        await self.projector.douser_close()
        with self.assertRaises(NecNakError):
            await self.projector.picture_mute_on()

    async def test_select_port_sends_switching_object_five(self):
        await self.projector.select_port(0x3B)
        self.assertEqual(self.fake.last_payload(), bytes([0x05, 0x3B]))

    async def test_select_port_rejects_a_port_the_head_refuses(self):
        with self.assertRaises(NecNakError):
            await self.projector.select_port(0x40)

    async def test_macro_is_one_based_for_the_user_zero_based_on_the_wire(self):
        await self.projector.select_macro(2)
        self.assertEqual(self.fake.last_payload(), bytes([0x06, 0x01]))

    async def test_select_title_uses_switching_object_zero(self):
        await self.projector.select_title(7)
        self.assertEqual(self.fake.last_payload(), bytes([0x00, 0x07]))

    async def test_lens_control(self):
        await self.projector.lens_control("focus", 0xFD)
        self.assertEqual(self.fake.last_payload(), bytes([0x01, 0xFD]))


class TestConnectionHandling(ProjectorTestCase):
    """The booth is not a laboratory; the link will misbehave."""

    async def test_connection_is_reused(self):
        await self.projector.model_name()
        await self.projector.model_name()
        self.assertTrue(self.client.connected)

    async def test_reconnects_after_the_projector_drops_the_link(self):
        await self.projector.model_name()
        self.fake.drop_connection = True
        with self.assertRaises(NecError):
            await self.projector.model_name()
        self.assertFalse(self.client.connected)
        # The next call must recover on its own.
        self.assertEqual(await self.projector.model_name(), "NC2000C")

    async def test_unrelated_frame_is_skipped(self):
        self.fake.send_stale_frame = True
        self.assertEqual(await self.projector.model_name(), "NC2000C")

    async def test_silence_times_out_and_closes_the_link(self):
        self.fake.silent = True
        self.client._timeout = 0.2
        with self.assertRaises(NecError):
            await self.projector.model_name()
        self.assertFalse(self.client.connected)

    async def test_unreachable_host_raises_a_readable_error(self):
        await self.fake.stop()
        await self.client.close()
        with self.assertRaises(NecError) as caught:
            await self.projector.model_name()
        self.assertIn("cannot connect", str(caught.exception))

    async def test_unknown_command_is_refused_not_hung(self):
        with self.assertRaises(NecNakError) as caught:
            await self.client.request(0x09, 0x99)
        self.assertEqual(str(caught.exception), "unknown command")


if __name__ == "__main__":
    unittest.main()
