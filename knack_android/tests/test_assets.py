from __future__ import annotations

import unittest
import wave
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOUNDS = ("card", "coin", "deal", "jackpot", "knack", "turn", "win")
RANKS = ("7", "8", "9", "10", "bube", "dame", "koenig", "ass")
SUITS = ("herz", "karo", "kreuz", "pik")


class SoundAssetTests(unittest.TestCase):
    def test_android_icon_is_square_512_png(self) -> None:
        payload = (ROOT / "assets" / "icon.png").read_bytes()
        self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", payload[16:24]), (512, 512))

    def test_all_sounds_are_valid_mono_wav_files(self) -> None:
        for name in SOUNDS:
            path = ROOT / "assets" / "sounds" / f"{name}.wav"
            self.assertTrue(path.is_file(), path)
            with wave.open(str(path), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertEqual(audio.getframerate(), 44_100)
                self.assertGreater(audio.getnframes(), 1_000)

    def test_android_build_includes_sound_assets(self) -> None:
        build_spec = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
        self.assertIn("source.include_exts = py,png,wav", build_spec)

    def test_all_card_crops_have_expected_png_dimensions(self) -> None:
        expected_sizes = {
            "large": (120, 168),
            "medium": (72, 101),
            "small": (44, 62),
        }
        names = [f"{rank}_{suit}.png" for rank in RANKS for suit in SUITS]
        names.append("back.png")
        for size_name, expected_size in expected_sizes.items():
            folder = ROOT / "assets" / "cards" / size_name
            self.assertEqual(sorted(path.name for path in folder.glob("*.png")), sorted(names))
            for name in names:
                payload = (folder / name).read_bytes()
                self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", payload[16:24]), expected_size)

    def test_android_build_includes_card_assets(self) -> None:
        build_spec = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
        self.assertIn("source.dir = .", build_spec)
        self.assertIn("png", build_spec)

    def test_table_background_is_valid_and_included_in_build(self) -> None:
        path = ROOT / "assets" / "background" / "table.png"
        payload = path.read_bytes()
        self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", payload[16:24])
        self.assertGreaterEqual(width, 1400)
        self.assertGreaterEqual(height, 880)
        build_spec = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
        self.assertIn("png", build_spec)


if __name__ == "__main__":
    unittest.main()
