"""Step 3 job-bundle regression coverage."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from media.artifacts import slugify_job_name, write_step3_artifacts
from pipeline.document import Chapter, Chunk, PipelineDocument, PipelineStateError


class Step3ArtifactTests(unittest.TestCase):
    def make_document(self) -> PipelineDocument:
        document = PipelineDocument()
        document.step2_revision = 4
        document.chapters = [
            Chapter(number=1, header_line="Chương 1", text="Nội dung chương một.", char_count=20),
            Chapter(number=2, header_line="Chương 2", text="Nội dung chương hai.", char_count=20),
        ]
        document.set_cleaned_output(
            "Chương 1\n\nNội dung chương một.\n\n\nChương 2\n\nNội dung chương hai.\n"
        )
        document.chunks = [
            Chunk(1, 1, 1, "Chương 1\nNội dung chương một.", char_count=31),
            Chunk(2, 1, 2, "Chương 2\nNội dung chương hai.", char_count=31),
        ]
        document.set_job_identity("Tiểu thuyết: thử", "Chương 1")
        return document

    def test_slug_is_cross_platform_safe_and_unicode_preserving(self):
        self.assertEqual(slugify_job_name("Tiểu thuyết: thử", "Chương 1/2"), "Tiểu_thuyết_thử_Chương_1_2")

    def test_bundle_is_utf8_ordered_and_validated(self):
        document = self.make_document()
        with tempfile.TemporaryDirectory() as directory:
            bundle = write_step3_artifacts(
                document, Path(directory), title=document.job_title, chapter=document.job_chapter, chunk_limit=1200
            )
            document.set_step3_artifacts(bundle)
            self.assertTrue(Path(bundle.txt_path).is_file())
            self.assertTrue(Path(bundle.json_path).is_file())
            self.assertEqual(Path(bundle.txt_path).read_text(encoding="utf-8"), document.cleaned_text)
            data = json.loads(Path(bundle.json_path).read_text(encoding="utf-8"))
            self.assertEqual(data["chunk_settings"]["max_chars"], 1200)
            self.assertTrue(data["chunk_settings"]["headers_spoken"])
            self.assertEqual([item["order"] for item in data["chunks"]], [1, 2])
            self.assertIn("Chương 1", data["chunks"][0]["text"])
            self.assertEqual(document.require_step3_artifacts(), bundle)

            Path(bundle.txt_path).write_text("outside change", encoding="utf-8")
            with self.assertRaises(PipelineStateError):
                document.require_step3_artifacts()

    def test_identity_or_upstream_change_invalidates_bundle_without_deleting_files(self):
        document = self.make_document()
        with tempfile.TemporaryDirectory() as directory:
            bundle = write_step3_artifacts(
                document, Path(directory), title=document.job_title, chapter=document.job_chapter, chunk_limit=1200
            )
            document.set_step3_artifacts(bundle)
            document.set_job_identity("Tên mới", "Chương 1")
            self.assertIsNone(document.step3_artifacts)
            self.assertTrue(Path(bundle.txt_path).exists())

    def test_step4_media_is_fingerprinted_for_step5(self):
        document = self.make_document()
        with tempfile.TemporaryDirectory() as directory:
            bundle = write_step3_artifacts(
                document, Path(directory), title=document.job_title,
                chapter=document.job_chapter, chunk_limit=1200,
            )
            document.set_step3_artifacts(bundle)
            thumbnail = Path(bundle.output_dir) / "cover_youtube.jpg"
            audiobook = Path(bundle.output_dir) / f"{bundle.slug}_audiobook.mp3"
            thumbnail.write_bytes(b"jpeg")
            audiobook.write_bytes(b"mp3")
            document.set_thumbnail_output(str(thumbnail))
            document.set_tts_output(
                audio_chunks_dir=str(Path(bundle.output_dir) / "audio"),
                manifest_path=str(Path(bundle.output_dir) / "manifest.json"),
                audiobook_path=str(audiobook),
            )

            media = document.require_step4_outputs()
            self.assertEqual(media.thumbnail_path, str(thumbnail))
            self.assertEqual(media.audiobook_path, str(audiobook))
            self.assertEqual(media.video_path, str(Path(bundle.output_dir) / f"{bundle.slug}.mp4"))

            audiobook.write_bytes(b"changed")
            with self.assertRaises(PipelineStateError):
                document.require_step4_outputs()


if __name__ == "__main__":
    unittest.main()
