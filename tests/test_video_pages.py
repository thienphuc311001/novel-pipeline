"""Exact narration, safe page layout, selective cache, and real sparse MP4 timing."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from media.artifacts import atomic_write_json, sha256_file
from media.tts import TtsChunk, TtsProcessor
from media.video import (AudioProbe, EncoderCandidate, VideoValidationError, build_video_command,
                         probe_audio, validate_rendered_video, verify_vfr_encoder)
from media.video_pages import (DEFAULT_STYLE, load_narration, prepare_video_timeline, render_page,
                               source_fingerprint, validate_timeline_timestamps)
from tests.support import create_narration_fixture


class VideoPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.texts = ['Chương 1', 'Hắn bước vào căn phòng.\n\nÁnh sáng dịu dàng chiếu qua cửa sổ.']
        self.chunks = [TtsChunk(i + 1, t, 1) for i, t in enumerate(self.texts)]
        self.audio = self.root / 'audiobook.mp3'
        self.processor = create_narration_fixture(self.root, self.chunks, self.audio)
        thumb = self.root / 'thumbnail.jpg'
        Image.new('RGB', (1280, 720), (70, 100, 140)).save(thumb)
        self.media = SimpleNamespace(output_dir=str(self.root), title='Đường về cố đô', chapter='Chương 1',
                                     thumbnail_path=str(thumb), audiobook_path=str(self.audio),
                                     tts_manifest_path=str(self.processor.manifest_path))

    def probe(self, path, *args):
        duration = {'chunk_00001.mp3': .737, 'chunk_00002.mp3': 1.213, 'audiobook.mp3': 1.950}[Path(path).name]
        return AudioProbe(duration, 'mp3', 24000, 1)

    def timeline(self, **kwargs):
        with patch('media.video_pages.probe_audio', side_effect=self.probe):
            return prepare_video_timeline(self.media, 'ffprobe', **kwargs)

    def test_exact_text_and_measured_timeline(self):
        timeline = self.timeline()
        self.assertEqual([p.text for p in timeline.pages], self.texts)
        self.assertEqual([p.duration for p in timeline.pages], [.737, 1.213])
        self.assertEqual([p.start for p in timeline.pages], [0, .737])
        self.assertAlmostEqual(timeline.pages[-1].end, 1.950)
        saved = json.loads((self.root / 'video_timeline.json').read_text())
        self.assertEqual(saved['pages'][1]['text'], self.texts[1])
        script = Path(timeline.concat_path).read_text()
        self.assertIn('duration 0.737000000', script)
        self.assertIn('option framerate 1000', script)
        self.assertEqual(script.count("file '"), len(self.chunks) + 1)
        self.assertTrue(source_fingerprint(self.media)['timeline_sha256'])

    def test_selective_cache_and_audio_only_updates(self):
        first = self.timeline()
        with patch('media.video_pages.render_page', wraps=render_page) as render:
            second = self.timeline()
            self.assertEqual(render.call_count, 0)
            self.assertEqual([p.page_path for p in first.pages], [p.page_path for p in second.pages])
        self.chunks[1] = TtsChunk(2, 'Nội dung đã sửa.\n\nĐây là văn bản thực sự gửi TTS.', 1)
        create_narration_fixture(self.root, self.chunks, self.audio)
        with patch('media.video_pages.render_page', wraps=render_page) as render:
            changed = self.timeline()
            self.assertEqual(render.call_count, 1)
            self.assertEqual(changed.pages[0].page_path, first.pages[0].page_path)
            self.assertNotEqual(changed.pages[1].page_path, first.pages[1].page_path)
        # Provenance updated after generating a replacement MP3 with the same request.
        data = json.loads(self.processor.manifest_path.read_text())
        chunk_path = self.processor.audio_dir / 'chunk_00002.mp3'
        chunk_path.write_bytes(b'replacement audio')
        data['chunks']['2']['mp3_sha256'] = sha256_file(chunk_path)
        data['merge']['chunks'][1] = dict(data['chunks']['2'])
        atomic_write_json(self.processor.manifest_path, data)
        def longer(path, *args):
            probe = self.probe(path)
            return replace(probe, duration=probe.duration + (.2 if Path(path).name != 'chunk_00001.mp3' else 0))
        with patch('media.video_pages.probe_audio', side_effect=longer), patch('media.video_pages.render_page') as render:
            retimed = prepare_video_timeline(self.media, 'ffprobe')
            render.assert_not_called()
            self.assertAlmostEqual(retimed.duration, 2.150)

    def test_visual_changes_and_corrupted_cache_repaint(self):
        first = self.timeline()
        Path(first.pages[0].page_path).write_bytes(b'corrupt PNG')
        with patch('media.video_pages.render_page', wraps=render_page) as render:
            self.timeline()
            self.assertEqual(render.call_count, 1)
        with patch('media.video_pages.render_page', wraps=render_page) as render:
            self.timeline(style=replace(DEFAULT_STYLE, brightness=.6))
            self.assertEqual(render.call_count, 2)
        self.media.chapter = 'Chương 1–20'
        with patch('media.video_pages.render_page', wraps=render_page) as render:
            self.timeline()
            self.assertEqual(render.call_count, 2)

    def test_invalid_audio_or_request_provenance_is_rejected(self):
        data = json.loads(self.processor.manifest_path.read_text())
        for mutate in [lambda d: d.update(schema_version=1),
                       lambda d: d['merge'].update(complete=False),
                       lambda d: d['merge'].update(orders=[2, 1]),
                       lambda d: d['chunks']['2'].update(text='different'),
                       lambda d: d['chunks']['2'].update(request_mode='split_fallback')]:
            invalid = json.loads(json.dumps(data))
            mutate(invalid)
            atomic_write_json(self.processor.manifest_path, invalid)
            with self.assertRaisesRegex(VideoValidationError, 'Step 3'):
                load_narration(self.media)
        atomic_write_json(self.processor.manifest_path, data)
        (self.processor.audio_dir / 'chunk_00001.mp3').write_bytes(b'tampered audio')
        with self.assertRaises(VideoValidationError):
            self.timeline()

    def test_mismatched_audio_duration_and_cancellation_fail_before_publication(self):
        def wrong(path, *args):
            probe = self.probe(path)
            return replace(probe, duration=20) if Path(path).name == 'audiobook.mp3' else probe
        with patch('media.video_pages.probe_audio', side_effect=wrong), self.assertRaisesRegex(VideoValidationError, 'duration total'):
            prepare_video_timeline(self.media, 'ffprobe')
        event = Event(); event.set()
        with self.assertRaisesRegex(VideoValidationError, 'cancelled'):
            self.timeline(cancel_event=event)
        self.assertFalse((self.root / 'render_pages').exists())

    def test_input_change_during_page_generation_keeps_old_timeline(self):
        previous = (self.root / 'video_timeline.json').read_bytes()
        def changed_thumbnail(*args, **kwargs):
            layout = render_page(*args, **kwargs)
            Image.new('RGB', (1280, 720), (200, 80, 60)).save(self.media.thumbnail_path)
            return layout
        with patch('media.video_pages.render_page', side_effect=changed_thumbnail):
            with self.assertRaisesRegex(VideoValidationError, 'inputs changed'):
                self.timeline()
        self.assertEqual((self.root / 'video_timeline.json').read_bytes(), previous)

    def test_readable_layout_bounds_and_overflow(self):
        for i, text in enumerate(['Ngắn.', ('Ánh sáng tràn qua cửa sổ. ' * 30)[:700],
                                  'Đoạn đầu.\n\nĐoạn giữa.\n\nĐoạn cuối.', 'a' * 700]):
            layout = render_page(self.media.thumbnail_path, self.root / f'layout{i}.png',
                                 title='Một tựa truyện dài và thanh lịch trong ánh sáng hoàng hôn',
                                 chapter='Chương 601–620', text=text)
            self.assertGreaterEqual(layout['font_size'], 28)  # Relaxing the floor keeps pages that already fit.
            for left, top, right, bottom in layout['text_bounds']:
                self.assertTrue(192 <= left <= right <= 1728)
                self.assertTrue(108 <= top <= bottom <= 972)
        with self.assertRaisesRegex(VideoValidationError, 'readable minimum'):
            render_page(self.media.thumbnail_path, self.root / 'overflow.png', title='Truyện',
                        chapter='Chương 1', text='Một dòng.\n' * 80)
        self.assertFalse((self.root / 'overflow.png').exists())

    def test_paragraph_heavy_chunk_renders_at_the_relaxed_minimum(self):
        """A chunk too tall for 28px must still render instead of blocking Step 4."""
        text = 'Dòng ngắn.\n\n' * 10
        with self.assertRaisesRegex(VideoValidationError, 'readable minimum'):
            render_page(self.media.thumbnail_path, self.root / 'old-floor.png', title='Truyện', chapter='Chương 1',
                        text=text, style=replace(DEFAULT_STYLE, min_body_size=28))
        self.assertFalse((self.root / 'old-floor.png').exists())
        layout = render_page(self.media.thumbnail_path, self.root / 'relaxed-floor.png', title='Truyện',
                             chapter='Chương 1', text=text)
        self.assertLess(layout['font_size'], 28)
        self.assertGreaterEqual(layout['font_size'], DEFAULT_STYLE.min_body_size)
        for left, top, right, bottom in layout['text_bounds']:
            self.assertTrue(192 <= left <= right <= 1728)
            self.assertTrue(108 <= top <= bottom <= 972)

    def test_nonfinite_audio_metadata_rejected(self):
        path = self.processor.audio_dir / 'chunk_00001.mp3'
        for duration in ('nan', 'inf', '-1', '0'):
            def runner(command, timeout):
                return subprocess.CompletedProcess(command, 0, json.dumps({'streams': [
                    {'duration': duration, 'codec_name': 'mp3', 'channels': 1, 'sample_rate': '24000'}]}), '')
            with self.assertRaises(VideoValidationError):
                probe_audio(path, 'ffprobe', runner)

    def test_mp3_playable_duration_uses_exact_packet_ticks_and_padding(self):
        path = self.processor.audio_dir / 'chunk_00001.mp3'
        packets = [{'duration': 368640, 'duration_time': '0.026122'} for _ in range(30)]
        packets[0]['side_data_list'] = [{'skip_samples': 1105, 'discard_padding': 0}]
        packets[-1]['side_data_list'] = [{'skip_samples': 0, 'discard_padding': 300}]
        metadata = {'streams': [{'codec_name': 'mp3', 'sample_rate': 44100, 'channels': 1,
                                'duration': '0.783674', 'time_base': '1/14112000'}], 'packets': packets}
        def runner(command, timeout):
            return subprocess.CompletedProcess(command, 0, json.dumps(metadata), '')
        measured = probe_audio(path, 'ffprobe', runner)
        self.assertAlmostEqual(measured.duration, (30 * 1152 - 1405) / 44100, places=12)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'requires FFmpeg')
class RealVfrTests(unittest.TestCase):
    def test_real_mp3_merge_and_fractional_static_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Truyện ' thử nghiệm"
            root.mkdir()
            texts = ['Chương 1', 'Trang thứ hai.\n\nVăn bản phải khớp chính xác.', 'Trang cuối.']
            sources = {}
            for i, (text, duration) in enumerate(zip(texts, [.737, 1.213, .491])):
                path = root / f'source{i}.mp3'
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    f'sine=frequency={300 + i * 100}:sample_rate=24000:duration={duration}',
                    '-c:a', 'libmp3lame', str(path)], check=True, capture_output=True)
                sources[text] = path
            class Client:
                def __init__(self, text): self.text = text
                async def save(self, path): Path(path).write_bytes(sources[self.text].read_bytes())
            processor = TtsProcessor([TtsChunk(i + 1, t, 1) for i, t in enumerate(texts)],
                root / 'audio_chunks', voice='fixture', client_factory=lambda t, v: Client(t))
            result = processor.run()
            processor.merge(result, root / 'audiobook.mp3')
            thumb = root / 'thumbnail.jpg'
            Image.new('RGB', (1280, 720), (60, 80, 110)).save(thumb)
            media = SimpleNamespace(output_dir=str(root), title='Truyện thử nghiệm', chapter='Chương 1',
                thumbnail_path=str(thumb), audiobook_path=str(root / 'audiobook.mp3'),
                tts_manifest_path=str(processor.manifest_path))
            timeline = prepare_video_timeline(media, 'ffprobe')
            self.assertEqual(len(timeline.pages), 3)
            self.assertEqual([p.text for p in timeline.pages], texts)
            self.assertAlmostEqual(timeline.duration, timeline.audiobook_duration, places=3)
            candidate = EncoderCandidate('libx264', 'CPU', hardware=False, verified=True)
            verify_vfr_encoder('ffmpeg', 'ffprobe', candidate)
            for audio_copy in (True, False):
                output = root / f'video{audio_copy}.mp4'
                command = build_video_command('ffmpeg', candidate, Path(timeline.concat_path),
                                               root / 'audiobook.mp3', output, audio_copy=audio_copy)
                subprocess.run(command, check=True, capture_output=True)
                validate_rendered_video(output, timeline.audiobook_duration, 'ffprobe')
                validate_timeline_timestamps(output, timeline, 'ffprobe')
                audio = probe_audio(output, 'ffprobe')
                self.assertGreaterEqual(audio.duration + .001, timeline.audiobook_duration)
                # Decode at each page start and compare center-region pixels to its PNG.
                # Text differences make a retimed/reordered image sequence observable.
                for page in timeline.pages:
                    decoded = root / 'decoded.png'
                    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(output), '-vf',
                        f"select='eq(n,{page.order - 1})'", '-frames:v', '1', str(decoded)],
                        check=True, capture_output=True)
                    from PIL import ImageChops, ImageStat
                    with Image.open(decoded) as actual, Image.open(page.page_path) as expected:
                        diff = ImageChops.difference(actual.convert('RGB'), expected.convert('RGB'))
                        self.assertLess(sum(ImageStat.Stat(diff).mean) / 3, 4)

            # Exercise the Qt session with asynchronous legacy preparation and
            # with an already prepared grouped timeline; both must remain VFR.
            import os
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtTest import QTest
            from media.video import VideoCapabilities
            from ui.main_window import _VideoRenderSession
            app = QApplication.instance() or QApplication([])
            bad = EncoderCandidate('test_failure', 'test', verified=True)
            caps = VideoCapabilities('ffmpeg', 'ffprobe', 'test', 'Linux', candidates=[bad, candidate])
            def fail_first(*args, **kwargs):
                command = build_video_command(*args, **kwargs)
                if args[1].name == 'test_failure':
                    command[command.index('-c:v') + 1] = 'missing_test_encoder'
                return command
            for prepared in (None, timeline):
                if prepared is not None:
                    prepared = prepare_video_timeline(media, 'ffprobe')
                media.video_path = str(root / 'session.mp4')
                completed, errors = [], []
                session = _VideoRenderSession(caps, media, timeline.audiobook_duration,
                                              audio_copy=None if prepared is None else True, timeline=prepared)
                session.completed.connect(completed.append)
                session.failed.connect(errors.append)
                with patch('media.video.build_video_command', side_effect=fail_first):
                    session.start()
                    for _ in range(1000):
                        app.processEvents()
                        if completed or errors:
                            break
                        QTest.qWait(10)
                self.assertFalse(errors, errors)
                self.assertEqual(len(completed), 1)
                self.assertEqual(completed[0].encoder, 'libx264')
                self.assertEqual(len(completed[0].attempt_errors), 1)
                self.assertEqual(completed[0].source, source_fingerprint(media))
                validate_timeline_timestamps(root / 'session.mp4', session.timeline, 'ffprobe')
                session.deleteLater()
                app.processEvents()

    def test_single_page_holds_to_the_end_at_44100hz(self):
        import wave
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.mp3'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                'sine=frequency=300:sample_rate=44100:duration=0.987', '-c:a', 'libmp3lame', str(source)],
                check=True, capture_output=True)
            wav = root / 'decoded.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), str(wav)], check=True, capture_output=True)
            with wave.open(str(wav)) as decoded:
                actual_duration = decoded.getnframes() / decoded.getframerate()
            self.assertAlmostEqual(probe_audio(source, 'ffprobe').duration, actual_duration, places=10)
            class Client:
                async def save(self, path): Path(path).write_bytes(source.read_bytes())
            processor = TtsProcessor([TtsChunk(1, 'Một trang duy nhất.', 1)], root / 'audio_chunks',
                                     voice='fixture', client_factory=lambda t, v: Client())
            processor.merge(processor.run(), root / 'audiobook.mp3')
            thumb = root / 'thumbnail.jpg'
            Image.new('RGB', (1280, 720), (60, 80, 110)).save(thumb)
            media = SimpleNamespace(output_dir=str(root), title='Truyện', chapter='Chương 1',
                thumbnail_path=str(thumb), audiobook_path=str(root / 'audiobook.mp3'),
                tts_manifest_path=str(processor.manifest_path))
            timeline = prepare_video_timeline(media, 'ffprobe')
            self.assertEqual(len(timeline.pages), 1)
            self.assertAlmostEqual(timeline.pages[0].duration, actual_duration, places=10)
            output = root / 'video.mp4'
            command = build_video_command('ffmpeg', EncoderCandidate('libx264', 'CPU', hardware=False),
                Path(timeline.concat_path), root / 'audiobook.mp3', output, audio_copy=True)
            subprocess.run(command, check=True, capture_output=True)
            validate_timeline_timestamps(output, timeline, 'ffprobe')
            validate_rendered_video(output, actual_duration, 'ffprobe')
