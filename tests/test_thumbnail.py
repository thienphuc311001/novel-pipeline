"""Thumbnail renderer tests without Qt: video frame style over a sharp cover."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from media.thumbnail import (CAPTION_HEIGHT, CAPTION_PADDING, FRAME_INSET, FRAME_RADIUS, HEIGHT, WIDTH,
                             _fit_caption, generate_thumbnail)
from media.text_layout import matching_fallback, measure_length
from media.video_pages import DEFAULT_STYLE, font_paths, scaled_style


class ThumbnailTests(unittest.TestCase):
    def render(self, root, image, *, title="Đường về cố đô", chapter="Chương 1–20"):
        source = root / "cover.png"
        image.save(source)
        return generate_thumbnail(source, root, title=title, chapter=chapter)

    def test_cover_stays_sharp_and_full_bleed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cover = Image.new("RGB", (WIDTH, HEIGHT), (255, 0, 0))
            ImageDraw.Draw(cover).rectangle((WIDTH // 2, 0, WIDTH - 1, HEIGHT - 1), fill=(0, 0, 255))
            output = self.render(root, cover)
            self.assertEqual(output.name, "cover_youtube.jpg")
            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(image.size, (WIDTH, HEIGHT))
                self.assertGreater(image.getpixel((5, 5))[0], 200)
                # The video page blurs its background; the thumbnail must stay sharp.
                row = [image.getpixel((x, 10)) for x in range(WIDTH)]
                self.assertGreater(row[620][0], 200)
                self.assertLess(row[660][0], 40)
                self.assertLessEqual(sum(1 for pixel in row if 20 < pixel[0] < 235), 6)
                # No black banner: the bottom margin keeps the cover colours.
                self.assertEqual(image.getpixel((5, HEIGHT - 5)), (254, 0, 0))
                self.assertEqual(image.getpixel((WIDTH - 5, HEIGHT - 5)), (0, 0, 254))

    def test_caption_band_uses_the_video_frame_palette(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = self.render(root, Image.new("RGB", (WIDTH, HEIGHT), (128, 128, 128)))
            with Image.open(output) as image:
                band = image.getpixel((100, HEIGHT - FRAME_INSET - CAPTION_HEIGHT // 2))
                self.assertLess(max(band), 60)            # dark caption panel over the cover
                self.assertLess(band[0], band[2])         # same blue/black panel palette as a page
                for channel in image.getpixel((100, 300)):
                    self.assertTrue(110 <= channel <= 150, channel)  # cover is neither blurred nor dimmed
                edges = [image.getpixel((x, 300)) for x in range(FRAME_INSET - 12, FRAME_INSET + 9)]
                self.assertGreaterEqual(max(pixel[2] - pixel[0] for pixel in edges), 10)
                band_top = HEIGHT - FRAME_INSET - CAPTION_HEIGHT
                self.assertGreater(HEIGHT - FRAME_INSET, band_top)
                raw = image.crop((0, band_top, WIDTH, HEIGHT - FRAME_INSET)).tobytes()
                lit = sum(1 for index in range(0, len(raw), 3)
                          if raw[index] > 190 and raw[index + 1] > 170 and raw[index + 2] > 210)
                self.assertGreater(lit, 20)               # video-styled title and chapter glyphs

    def test_title_and_chapter_change_the_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cover = Image.new("RGB", (WIDTH, HEIGHT), (40, 60, 90))
            first = self.render(root, cover, title="Đường về cố đô", chapter="Chương 1–20").read_bytes()
            second = self.render(root, cover, title="Bắc Tống", chapter="Chương 21–40").read_bytes()
            self.assertNotEqual(first, second)

    def test_long_title_shrinks_and_unfittable_title_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cover = Image.new("RGB", (WIDTH, HEIGHT), (25, 25, 25))
            output = self.render(root, cover, title=" ".join(["Chuyện"] * 24), chapter="Chương 120–140")
            with Image.open(output) as image:
                self.assertEqual(image.size, (WIDTH, HEIGHT))
            with self.assertRaisesRegex(RuntimeError, "dải thumbnail"):
                self.render(root, cover, title=" ".join(["Chuyện"] * 400), chapter="Chương 1")

    def test_thumbnail_reuses_video_page_style(self):
        style = scaled_style(WIDTH, HEIGHT)
        self.assertEqual(style.frame, (32, 18, 1248, 702))
        self.assertEqual((style.radius, style.padding), (FRAME_RADIUS, CAPTION_PADDING))
        self.assertEqual(scaled_style(DEFAULT_STYLE.width, DEFAULT_STYLE.height), DEFAULT_STYLE)
        self.assertEqual(CAPTION_HEIGHT, 144)
        self.assertLess(FRAME_INSET, DEFAULT_STYLE.frame[0])  # hugs the edge, unlike a video page
        for path in font_paths():
            self.assertTrue(path.is_file(), path)

    def test_chapter_number_uses_the_bold_title_face(self):
        regular, bold = font_paths()
        draw = ImageDraw.Draw(Image.new("RGB", (WIDTH, HEIGHT)))
        title_font, title_lines, _, chapter_font, chapter_lines, _ = _fit_caption(
            draw, "Đường về cố đô", "Chương 120–140", bold, WIDTH, CAPTION_HEIGHT)
        self.assertEqual(str(title_font.path), str(bold))
        self.assertEqual(str(chapter_font.path), str(bold))
        self.assertNotEqual(str(chapter_font.path), str(regular))
        self.assertLessEqual(chapter_font.size, title_font.size)
        self.assertEqual(title_lines, ["Đường về cố đô"])
        self.assertEqual(chapter_lines, ["Chương 120–140"])

    def test_cjk_brackets_draw_real_glyphs_in_the_caption(self):
        """Thumbnail captions get the same CJK fallback as the video pages."""
        _regular, bold = font_paths()
        title, chapter = 'Truyện【Kiếm】', 'Chương 120–140'
        draw = ImageDraw.Draw(Image.new("RGB", (WIDTH, HEIGHT)))
        title_font, _title_lines, title_step, _cfont, _clines, _cstep = _fit_caption(
            draw, title, chapter, bold, WIDTH, CAPTION_HEIGHT)
        fallback = matching_fallback(str(bold), title_font.size)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = self.render(root, Image.new("RGB", (WIDTH, HEIGHT), (30, 30, 30)),
                                 title=title, chapter=chapter)
            with Image.open(output) as image:
                gray = image.convert("L")
                band_top = HEIGHT - FRAME_INSET - CAPTION_HEIGHT
                tx = (WIDTH - measure_length(draw, title, title_font, fallback)) / 2
                prefix = measure_length(draw, "Truyện", title_font, fallback)
                window = gray.crop((int(tx + prefix), band_top + 10, int(tx + prefix) + 46,
                                    band_top + 10 + int(title_step)))
                raw = window.tobytes()
                ink = sum(1 for value in raw if value > 100)
                self.assertGreater(ink, 40, "the 【 bracket drew no ink in the caption band")

    def test_missing_cover_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                generate_thumbnail(root / "missing.png", root, title="Truyện", chapter="Chương 1")


if __name__ == "__main__":
    unittest.main()
