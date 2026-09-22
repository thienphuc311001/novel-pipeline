"""True page pixels with both required pictures in their header slots."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw

from media.video import VideoValidationError
from media.video_pages import (DEFAULT_STYLE, SIDE_PANEL_GAP, paste_side_image, render_page,
                               side_panel_boxes)
from tests.support import create_narration_fixture, create_visuals_fixture


class SidePanelGeometryTests(unittest.TestCase):
    def test_slots_are_fixed_305_squares_flush_in_the_frame_corners(self):
        from media.video_pages import SIDE_PANEL_SIZE
        left_frame, top_frame, right_frame, bottom_frame = DEFAULT_STYLE.frame
        column = min(DEFAULT_STYLE.body_width, right_frame - left_frame - 72 * 2)
        column_x = (1920 - column) // 2
        left, right = side_panel_boxes(DEFAULT_STYLE, 402, 1002)
        self.assertEqual(SIDE_PANEL_SIZE, 305)
        self.assertEqual(left[2] - left[0], 305)
        self.assertEqual(left[2] - left[0], left[3] - left[1])  # 1:1
        self.assertEqual(right[2] - right[0], left[2] - left[0])
        self.assertEqual(right[3] - right[1], left[3] - left[1])
        self.assertEqual(left[0], left_frame)
        self.assertEqual(left[2], left_frame + 305)
        self.assertEqual(right[0], right_frame - 305)
        self.assertEqual(right[2], right_frame)
        # Both slots sit flush in the frame top corners.
        self.assertEqual(left[1], top_frame)
        self.assertEqual(right[1], left[1])
        for box in (left, right):
            self.assertTrue(left_frame <= box[0] and box[2] <= right_frame)
            self.assertTrue(top_frame <= box[1] and box[3] <= bottom_frame)
        # The measured body band no longer moves the slots (kept for compat).
        self.assertEqual(side_panel_boxes(DEFAULT_STYLE),
                         side_panel_boxes(DEFAULT_STYLE, 402, 1002))


class SidePanelRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        thumb = self.root / "thumbnail.jpg"
        Image.new("RGB", (1280, 720), (70, 100, 140)).save(thumb)
        self.thumbnail = str(thumb)
        self.text = "Hắn bước vào căn phòng.\n\nÁnh sáng dịu dàng chiếu qua cửa sổ."
        cover = self.root / "cover.png"
        Image.new("RGB", (400, 400), (200, 30, 30)).save(cover)
        qr = self.root / "qr.png"
        self._qr(qr)
        self.cover_path, self.qr_path = str(cover), str(qr)

    @staticmethod
    def _qr(path, size=250):
        image = Image.new("RGB", (size, size), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, size - 21, size - 21), fill="black")
        draw.rectangle((40, 40, size - 41, size - 41), fill="white")
        draw.rectangle((60, 60, size - 61, size - 61), fill="black")
        image.save(path)

    def render(self, output="page.png", **kwargs):
        arguments = {"title": "Đường về cố đô", "chapter": "Chương 12", "text": self.text,
                     "left_image": self.cover_path, "right_image": self.qr_path}
        arguments.update(kwargs)
        return render_page(self.thumbnail, self.root / output, **arguments)

    def test_cover_and_qr_keep_their_pixels_without_background(self):
        layout = self.render()
        cover, qr = layout["side_images"]["cover"], layout["side_images"]["qr"]
        self.assertEqual(cover["source"], [400, 400])
        self.assertEqual(cover["drawn"], [305, 305])
        self.assertEqual(cover["radius"], DEFAULT_STYLE.radius)
        self.assertIsNone(cover["card"])
        self.assertEqual(qr["drawn"], [305, 305])
        self.assertEqual(qr["quiet_zone"], 0.0)
        self.assertIsNone(qr["card"])
        with Image.open(self.root / "page.png") as page:
            page = page.convert("RGB")
            self.assertEqual(page.getpixel((DEFAULT_STYLE.frame[0] + 100, cover["box"][1] + 100)), (200, 30, 30))
            # Corners rounded like the frame: the box corner shows the panel, not the picture.
            self.assertNotEqual(page.getpixel((cover["box"][0] + 2, cover["box"][1] + 2)), (200, 30, 30))
            # QR keeps its own pixels: center stays dark, corner follows the frame curve.
            center = ((qr["box"][0] + qr["box"][2]) // 2, (qr["box"][1] + qr["box"][3]) // 2)
            self.assertLess(sum(page.getpixel(center)), 300)
            self.assertNotEqual(page.getpixel((qr["box"][0] + 2, qr["box"][1] + 2)), (255, 255, 255))

    def test_wide_cover_is_letterboxed_instead_of_cropped(self):
        wide = self.root / "wide.png"
        Image.new("RGB", (400, 200), (30, 150, 30)).save(wide)
        layout = self.render("wide.png", left_image=str(wide))
        self.assertEqual(layout["side_images"]["cover"]["drawn"], [305, 152])
        with Image.open(self.root / "wide.png") as page:
            page = page.convert("RGB")
            box = layout["side_images"]["cover"]["box"]
            self.assertEqual(page.getpixel((box[0] + 100, box[1] + 140)), (30, 150, 30))
            # Letterbox margin above the strip: flat panel, clear of the frame glow.
            margin = page.getpixel((box[0] + 100, box[1] + 60))
            self.assertEqual(margin, page.getpixel((box[0] + 105, box[1] + 60)))
            self.assertLess(sum(margin), 120)

    def test_transparent_qr_has_no_card_just_composited_pixels(self):
        alpha = self.root / "alpha.png"
        image = Image.new("RGBA", (250, 250), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((20, 20, 230, 230), fill=(0, 0, 0, 255))
        image.save(alpha)
        layout = self.render("alpha.png", right_image=str(alpha))
        qr = layout["side_images"]["qr"]
        self.assertIsNone(qr["card"])
        self.assertEqual(qr["drawn"], [305, 305])
        with Image.open(self.root / "alpha.png") as page:
            page = page.convert("RGB")
            box = qr["box"]
            self.assertLess(sum(page.getpixel(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2))), 300)
    def test_pictures_never_intersect_the_text_column(self):
        layout = self.render()
        cover_box = layout["side_images"]["cover"]["box"]
        qr_box = layout["side_images"]["qr"]["box"]
        content_width = DEFAULT_STYLE.frame[2] - DEFAULT_STYLE.frame[0] - DEFAULT_STYLE.padding * 2
        column_x = (1920 - min(DEFAULT_STYLE.body_width, content_width)) // 2
        self.assertLessEqual(cover_box[2], column_x - SIDE_PANEL_GAP)
        self.assertGreaterEqual(qr_box[0], column_x + min(DEFAULT_STYLE.body_width, content_width) + SIDE_PANEL_GAP)
        for left, _top, right, _bottom in layout["text_bounds"]:
            self.assertGreaterEqual(left, column_x)
            self.assertLessEqual(right, column_x + 1150)

    def test_text_layout_is_identical_with_or_without_pictures(self):
        plain = render_page(self.thumbnail, self.root / "plain.png", title="Truyện", chapter="Chương 1",
                            text=self.text)
        with_pictures = self.render("with.png", title="Truyện", chapter="Chương 1")
        plain.pop("side_images"), with_pictures.pop("side_images")
        self.assertEqual(plain, with_pictures)

    def test_missing_picture_is_reported_instead_of_silently_skipped(self):
        with self.assertRaisesRegex(VideoValidationError, "Cannot open page image"):
            paste_side_image(Image.new("RGBA", (64, 64)), self.root / "missing.png", (0, 0, 64, 64))


class SidePanelTimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        from media.tts import TtsChunk
        self.audio = self.root / "audiobook.mp3"
        self.processor = create_narration_fixture(
            self.root, [TtsChunk(1, "Chương đầu tiên.", 1)], self.audio)
        thumb = self.root / "thumbnail.jpg"
        Image.new("RGB", (1280, 720), (60, 80, 110)).save(thumb)
        self.visuals = create_visuals_fixture(self.root)
        from types import SimpleNamespace
        self.media = SimpleNamespace(output_dir=str(self.root), title="Truyện", chapter="Chương 1",
                                     thumbnail_path=str(thumb), audiobook_path=str(self.audio),
                                     tts_manifest_path=str(self.processor.manifest_path),
                                     cover_image_path=self.visuals["cover"],
                                     qr_image_path=self.visuals["qr"])

    def probe(self, path, *args):
        from media.video import AudioProbe
        return AudioProbe(1.0, "mp3", 24000, 1)

    def test_both_picture_inputs_are_required_before_any_page(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from media.video_pages import prepare_video_timeline
        with patch("media.video_pages.probe_audio", side_effect=self.probe):
            timeline = prepare_video_timeline(self.media, "ffprobe")
            self.assertEqual(len(timeline.pages), 1)
            self.assertTrue(Path(timeline.pages[0].page_path).is_file())
        for attribute in ("cover_image_path", "qr_image_path"):
            sibling = SimpleNamespace(**{**self.media.__dict__, attribute: ""})
            with patch("media.video_pages.probe_audio", side_effect=self.probe), \
                    self.assertRaisesRegex(VideoValidationError, "requires both page images"):
                prepare_video_timeline(sibling, "ffprobe")

    def test_changing_a_picture_repaints_and_updates_the_source_fingerprint(self):
        from PIL import ImageDraw
        from unittest.mock import patch
        from media.video_pages import prepare_video_timeline, source_fingerprint
        with patch("media.video_pages.probe_audio", side_effect=self.probe):
            first = prepare_video_timeline(self.media, "ffprobe")
            with Image.open(self.visuals["qr"]) as qr:
                changed = qr.convert("RGB")
                ImageDraw.Draw(changed).rectangle((0, 0, 60, 60), fill=(200, 30, 30))
                changed.save(self.visuals["qr"])
            second = prepare_video_timeline(self.media, "ffprobe")
            self.assertNotEqual(first.pages[0].page_path, second.pages[0].page_path)
            hashes = source_fingerprint(self.media)["side_images"]
            self.assertIn("cover", hashes)
            self.assertIn("qr", hashes)
            self.assertNotEqual(hashes["qr"], hashes["cover"])


class VideoPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.thumbnail = self.root / "thumbnail.jpg"
        Image.new("RGB", (1280, 720), (70, 100, 140)).save(self.thumbnail)
        self.visuals = create_visuals_fixture(self.root)
        from ui.video_preview import VideoPreviewDialog, build_page_preview, first_page_text
        self.dialog_cls = VideoPreviewDialog
        self.build_page_preview = build_page_preview
        self.first_page_text = first_page_text

    def test_build_page_preview_renders_a_real_full_frame(self):
        path, note = self.build_page_preview(
            self.root / "work", thumbnail=str(self.thumbnail), title="Truyện", chapter="Chương 1",
            text="Một đoạn mẫu.", cover_image=self.visuals["cover"], qr_image=self.visuals["qr"])
        self.assertEqual(note, "")
        self.assertTrue(path.is_file())
        with Image.open(path) as page:
            self.assertEqual(page.size, (1920, 1080))

    def test_build_page_preview_falls_back_to_sample_text(self):
        path, note = self.build_page_preview(
            self.root / "work", thumbnail=str(self.thumbnail), title="Truyện", chapter="Chương 1",
            text="x " * 20000, cover_image=self.visuals["cover"], qr_image=self.visuals["qr"])
        self.assertIn("sample paragraph shown", note)
        self.assertTrue(path.is_file())

    def test_first_page_text_uses_the_plan_or_the_sample(self):
        self.assertEqual(self.first_page_text(self.root)[2], "sample text (no TTS plan yet)")

    def test_dialog_shows_the_whole_rendered_frame(self):
        dialog = self.dialog_cls()
        dialog.open_for(lambda: (self.thumbnail, "caption line"))
        self.addCleanup(dialog.close)
        self.assertFalse(dialog._pixmap.isNull())
        self.assertEqual(dialog.caption.text(), "caption line")


if __name__ == "__main__":
    unittest.main()
