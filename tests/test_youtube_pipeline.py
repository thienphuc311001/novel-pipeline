"""Step 6 input provenance and persistent duplicate-guard regressions."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from media.artifacts import write_step3_artifacts
from pipeline.document import Chunk, PipelineDocument, PipelineStateError, StageKey


class YouTubePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def ready_document(self) -> PipelineDocument:
        document = PipelineDocument()
        document.load_original_input("Chương 1\nNội dung.")
        document.complete_chinese_review("Chương 1\nNội dung.")
        document.set_job_identity("Bắc Tống", "Chương 1")
        document.set_cleaned_output("Chương 1\n\nNội dung.\n")
        document.chunks = [Chunk(1, 1, 1, "Chương 1\nNội dung.", char_count=20)]
        bundle = write_step3_artifacts(
            document, self.root, title=document.job_title,
            chapter=document.job_chapter, chunk_limit=1200,
        )
        document.set_step3_artifacts(bundle)
        job_dir = Path(bundle.output_dir)
        thumbnail = job_dir / "cover_youtube.jpg"
        audiobook = job_dir / f"{bundle.slug}_audiobook.mp3"
        thumbnail.write_bytes(b"jpeg")
        audiobook.write_bytes(b"mp3")
        document.set_thumbnail_output(str(thumbnail))
        document.set_tts_output(
            audio_chunks_dir=str(job_dir / "audio"),
            manifest_path=str(job_dir / "manifest.json"),
            audiobook_path=str(audiobook),
        )
        video = Path(document.require_step4_outputs().video_path)
        video.write_bytes(b"mp4")
        document.set_video_output(str(video), {"encoder": "libx264"})
        return document

    def test_only_current_generated_video_and_thumbnail_are_exposed(self):
        document = self.ready_document()
        bundle = document.require_step5_outputs()
        self.assertEqual(bundle.title, "Bắc Tống")
        self.assertEqual(bundle.chapter, "Chương 1")
        self.assertEqual(bundle.output_dir, document.step3_artifacts.output_dir)
        self.assertEqual(bundle.video_path, document.video_path)
        self.assertEqual(bundle.thumbnail_path, document.thumbnail_path)
        self.assertEqual(bundle.video_fingerprint, document.video_fingerprint)
        self.assertEqual(bundle.thumbnail_fingerprint, document.thumbnail_fingerprint)
        self.assertEqual(StageKey.ORDER[-1], StageKey.YOUTUBE)

        # Returned records cannot mutate the document's provenance in place.
        bundle.video_fingerprint["size"] = 0
        self.assertGreater(document.require_step5_outputs().video_fingerprint["size"], 0)

    def test_final_job_file_names_have_exact_contents_and_cancellable_copy_fallback(self):
        from media.artifacts import publish_job_file_names
        from media.youtube import UploadCancelled

        document = self.ready_document()
        bundle = document.require_step3_artifacts()
        media = document.require_step4_outputs()
        with patch("media.artifacts.os.link", side_effect=OSError("Unsupported")):
            publish_job_file_names(bundle, media, threading.Event())
        job = Path(bundle.output_dir)
        for name, source in (("final.txt", bundle.txt_path), ("final.json", bundle.json_path),
                             ("thumbnail.jpg", media.thumbnail_path), ("audiobook.mp3", media.audiobook_path)):
            self.assertEqual((job / name).read_bytes(), Path(source).read_bytes())
        document.require_step5_outputs()
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(UploadCancelled):
            publish_job_file_names(bundle, media, cancel)
        self.assertFalse(list(job.glob(".*.tmp")))

    def test_missing_empty_modified_or_unrecorded_video_is_rejected(self):
        for invalidity in ("missing", "empty", "modified", "unrecorded"):
            with self.subTest(invalidity=invalidity):
                document = self.ready_document()
                video = Path(document.video_path)
                if invalidity == "missing":
                    video.unlink()
                elif invalidity == "empty":
                    video.write_bytes(b"")
                elif invalidity == "modified":
                    video.write_bytes(b"external edit")
                else:
                    document.video_fingerprint = {}
                with self.assertRaises(PipelineStateError):
                    document.require_step5_outputs()

    def test_external_or_another_job_video_is_rejected_even_with_fingerprint(self):
        document = self.ready_document()
        alternate = self.root / "external.mp4"
        alternate.write_bytes(b"another video")
        document.set_video_output(str(alternate))
        with self.assertRaises(PipelineStateError):
            document.require_step5_outputs()
        document = self.ready_document()
        alternate = Path(document.video_path).with_name("unrelated.mp4")
        alternate.write_bytes(b"unrelated video in same job")
        document.set_video_output(str(alternate))
        with self.assertRaises(PipelineStateError):
            document.require_step5_outputs()

        document = self.ready_document()
        expected = Path(document.video_path)
        expected.unlink()
        expected.symlink_to(self.root / "external.mp4")
        document.set_video_output(str(expected))
        with self.assertRaises(PipelineStateError):
            document.require_step5_outputs()

    def test_video_requires_original_step4_and_step3_provenance(self):
        document = self.ready_document()
        # A caller replacing a fingerprint directly cannot bless an old video
        # as output from a new thumbnail.
        Path(document.thumbnail_path).write_bytes(b"new thumbnail")
        document.thumbnail_fingerprint = document._fingerprint_file(document.thumbnail_path)
        with self.assertRaisesRegex(PipelineStateError, "no longer matches"):
            document.require_step5_outputs()

        document = self.ready_document()
        document.step2_revision += 1
        with self.assertRaisesRegex(PipelineStateError, "stale"):
            document.require_step5_outputs()

        document = self.ready_document()
        Path(document.step3_artifacts.txt_path).write_text("external edit", encoding="utf-8")
        with self.assertRaises(PipelineStateError):
            document.require_step5_outputs()

    def test_clone_keeps_independent_upload_and_provenance_state(self):
        document = self.ready_document()
        state = {"video_id": "abc123", "operations": {"thumbnail": "completed"}}
        document.set_youtube_upload_state(state)
        state["operations"]["thumbnail"] = "failed"
        clone = document.clone()
        self.assertEqual(clone.require_step5_outputs(), document.require_step5_outputs())
        clone.video_fingerprint["size"] = 0
        clone._video_source_fingerprint["thumbnail"]["size"] = 0
        clone.youtube_upload_state["operations"]["thumbnail"] = "failed"
        self.assertGreater(document.video_fingerprint["size"], 0)
        self.assertGreater(document._video_source_fingerprint["thumbnail"]["size"], 0)
        self.assertEqual(document.youtube_upload_state["operations"]["thumbnail"], "completed")

    def test_upstream_and_video_changes_preserve_persistent_duplicate_guard(self):
        for action in ("thumbnail", "audio", "video", "identity", "text", "load"):
            with self.subTest(action=action):
                document = self.ready_document()
                record = Path(document.step3_artifacts.output_dir) / "youtube_upload.json"
                persisted = b'{"video_id":"already_uploaded","status":"completed"}'
                record.write_bytes(persisted)
                document.set_youtube_upload_state({"video_id": "already_uploaded"})
                document.stage(StageKey.YOUTUBE).touch("video", "Uploaded")
                if action == "thumbnail":
                    document.set_thumbnail_output(document.thumbnail_path)
                elif action == "audio":
                    document.set_tts_output(
                        audio_chunks_dir=document.audio_chunks_dir,
                        manifest_path=document.tts_manifest_path,
                        audiobook_path=document.audiobook_path,
                    )
                elif action == "video":
                    document.set_video_output(document.video_path)
                elif action == "identity":
                    document.set_job_identity("New title", "Chương 1")
                elif action == "text":
                    document.set_normalized_edit("Chương 1\nChanged text")
                else:
                    document.load_original_input("new source")
                self.assertEqual(document.youtube_upload_state, {})
                self.assertFalse(document.stage(StageKey.YOUTUBE).ran)
                self.assertEqual(record.read_bytes(), persisted)
                if action != "video":
                    with self.assertRaises(PipelineStateError):
                        document.require_step5_outputs()


if __name__ == "__main__":
    unittest.main()
