"""Required Step 4 page pictures: byte-identical copies and a strict record."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from media.artifacts import sha256_file
from media.video import VideoValidationError
from media.visuals import (VISUALS_DIRNAME, available_images, image_summary, load_visuals,
                           prune_visuals, record_visuals, recorded_sources)


class VisualRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.cover = self.sources / "cover.png"
        self.qr = self.sources / "qr.jpg"
        Image.new("RGB", (400, 400), (200, 30, 30)).save(self.cover)
        Image.new("RGB", (250, 250), "white").save(self.qr)

    def test_records_byte_identical_copies_with_hashes(self):
        record = record_visuals(self.root, self.cover, self.qr)
        copies = {role: self.root / record[role]["file"] for role in ("cover", "qr")}
        self.assertEqual({path.name for path in copies.values()}, {"cover.png", "qr.jpg"})
        self.assertEqual(copies["cover"].read_bytes(), self.cover.read_bytes())
        self.assertEqual(copies["qr"].read_bytes(), self.qr.read_bytes())
        self.assertEqual(record["cover"]["sha256"], sha256_file(copies["cover"]))
        self.assertEqual(record["cover"]["width"], 400)
        self.assertEqual(record["cover"]["source"], str(self.cover.resolve()))
        loaded = load_visuals(self.root)
        self.assertEqual(loaded["cover"]["path"], str(copies["cover"].resolve()))
        self.assertEqual(loaded["qr"]["sha256"], sha256_file(copies["qr"]))

    def test_re_recording_replaces_previous_files(self):
        first = record_visuals(self.root, self.cover, self.qr)
        other = self.sources / "other.jpeg"
        Image.new("RGB", (100, 200), "blue").save(other)
        second = record_visuals(self.root, other, self.qr)
        self.assertNotEqual(second["cover"]["sha256"], first["cover"]["sha256"])
        self.assertFalse((self.root / first["cover"]["file"]).exists())
        load_visuals(self.root)

    def test_missing_inputs_fail_with_the_create_video_step_name(self):
        with self.assertRaisesRegex(VideoValidationError, "QR"):
            record_visuals(self.root, self.cover, self.root / "missing.png")
        with self.assertRaisesRegex(VideoValidationError, "Add image in the Create Video step"):
            load_visuals(self.root)
        record_visuals(self.root, self.cover, self.qr)
        (self.root / "visuals" / "qr.jpg").write_bytes(b"tampered")
        with self.assertRaisesRegex(VideoValidationError, "changed or was deleted"):
            load_visuals(self.root)

    def test_unreadable_format_is_refused(self):
        text = self.sources / "cover.txt"
        text.write_text("not an image", encoding="utf-8")
        with self.assertRaisesRegex(VideoValidationError, "Unsupported"):
            record_visuals(self.root, text, self.qr)
        empty = self.sources / "empty.png"
        empty.write_bytes(b"")
        with self.assertRaisesRegex(VideoValidationError, "Empty"):
            record_visuals(self.root, empty, self.qr)

    def test_lenient_readers_never_raise_and_prune_clears_everything(self):
        self.assertEqual(available_images(self.root), {"cover": "", "qr": ""})
        self.assertEqual(recorded_sources(self.root), {"cover": "", "qr": ""})
        self.assertEqual(image_summary(""), "Not selected")
        record_visuals(self.root, self.cover, self.qr)
        recorded = recorded_sources(self.root)
        self.assertEqual(recorded, {"cover": str(self.cover.resolve()), "qr": str(self.qr.resolve())})
        self.assertIn("400×400", image_summary(self.root / f"{VISUALS_DIRNAME}/cover.png"))
        prune_visuals(self.root)
        self.assertEqual(available_images(self.root), {"cover": "", "qr": ""})
        self.assertFalse((self.root / VISUALS_DIRNAME).exists() and any((self.root / VISUALS_DIRNAME).iterdir()))
        self.assertFalse((self.root / "visuals.json").exists())


if __name__ == "__main__":
    unittest.main()
