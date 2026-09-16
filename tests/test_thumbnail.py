"""Thumbnail renderer tests without Qt."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from media.thumbnail import HEIGHT, WIDTH, bundled_font_path, generate_thumbnail


class ThumbnailTests(unittest.TestCase):
    def test_thumbnail_has_required_shape_band_and_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "cover.png"
            Image.new("RGB", (400, 100), (255, 0, 0)).save(source)
            output = generate_thumbnail(
                source,
                root / "job",
                title="Một tiêu đề rất dài cần được chia thành hai dòng khi cần thiết",
                chapter="Chương 327",
            )
            self.assertEqual(output.name, "cover_youtube.jpg")
            self.assertTrue(output.is_file())
            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (WIDTH, HEIGHT))
                self.assertLess(sum(image.getpixel((5, HEIGHT - 5))), 30)
                self.assertGreater(image.getpixel((5, 5))[0], 180)

    def test_bundled_font_exists(self):
        self.assertTrue(bundled_font_path().is_file())


if __name__ == "__main__":
    unittest.main()
