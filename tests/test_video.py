"""Hardware detection and static-video command regression tests."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media.video import (
    EncoderCandidate,
    VideoDependencyError,
    build_video_command,
    detect_video_capabilities,
    mp3_copy_is_safe,
    parse_progress_line,
)


class FakeRunner:
    def __init__(
        self, *, hardware_ok: bool = True, system: str = "Linux",
        gpu_vendor: str = "NVIDIA",
    ):
        self.hardware_ok = hardware_ok
        self.system = system
        self.gpu_vendor = gpu_vendor
        self.commands = []

    def __call__(self, command, timeout):
        command = list(command)
        self.commands.append(command)
        joined = " ".join(command)
        stdout = ""
        stderr = ""
        code = 0
        if "-version" in command:
            stdout = "ffmpeg version test-9.0\n"
        elif "-hwaccels" in command:
            stdout = "Hardware acceleration methods:\nvaapi\nqsv\ncuda\n"
        elif "-encoders" in command:
            stdout = (
                " V....D h264_vaapi VAAPI\n"
                " V....D h264_qsv QSV\n"
                " V....D h264_nvenc NVENC\n"
                " V....D h264_amf AMF\n"
                " V....D h264_videotoolbox VideoToolbox\n"
                " V....D libx264 CPU\n"
            )
        elif command[:2] == ["glxinfo", "-B"]:
            stdout = "Vendor: AMD (0x1002)\nDevice: AMD Radeon 780M Graphics (radeonsi)\n"
        elif command and command[0] == "nvidia-smi":
            code = 1
        elif command and command[0] == "powershell":
            stdout = json.dumps({
                "Name": f"{self.gpu_vendor} Test GPU",
                "AdapterCompatibility": self.gpu_vendor,
                "DriverVersion": "1.2.3",
                "PNPDeviceID": "PCI\\TEST",
            })
        elif command and command[0] == "system_profiler":
            stdout = json.dumps({"SPDisplaysDataType": [{"sppci_model": "Apple M4", "sppci_vendor": "Apple"}]})
        elif command[0] == "ffprobe" and "-select_streams" in command:
            stdout = json.dumps({"frames": [{"best_effort_timestamp_time": str(t)} for t in (0, .137, .508)],
                                 "streams": [{"duration": "0.509"}]})
        elif "-f null -" in joined or ("lavfi" in command and "-fps_mode" in command):
            is_cpu = "libx264" in command
            if not is_cpu and not self.hardware_ok:
                code = 1
                stderr = "hardware initialization failed"
        return subprocess.CompletedProcess(command, code, stdout, stderr)


class VideoTests(unittest.TestCase):
    def make_drm(self, root: Path) -> Path:
        device = root / "renderD128" / "device"
        device.mkdir(parents=True)
        (device / "vendor").write_text("0x1002\n", encoding="utf-8")
        (device / "uevent").write_text("PCI_SLOT_NAME=0000:05:00.0\n", encoding="utf-8")
        return root

    def test_linux_amd_requires_real_probe_before_selecting_vaapi(self):
        with tempfile.TemporaryDirectory() as directory:
            drm = self.make_drm(Path(directory))
            passing = detect_video_capabilities(
                ffmpeg_path="ffmpeg", ffprobe_path="ffprobe", runner=FakeRunner(),
                system_name="Linux", drm_root=drm,
            )
            self.assertEqual(passing.devices[0].model, "AMD Radeon 780M Graphics")
            self.assertEqual(passing.devices[0].device, "/dev/dri/renderD128")
            self.assertEqual(passing.selected.name, "h264_vaapi")

            failing = detect_video_capabilities(
                ffmpeg_path="ffmpeg", ffprobe_path="ffprobe",
                runner=FakeRunner(hardware_ok=False), system_name="Linux", drm_root=drm,
            )
            self.assertFalse(next(item for item in failing.candidates if item.name == "h264_vaapi").verified)
            self.assertEqual(failing.selected.name, "libx264")

    def test_missing_ffmpeg_is_reported_before_detection(self):
        with patch("media.video.shutil.which", return_value=None):
            with self.assertRaises(VideoDependencyError):
                detect_video_capabilities()

    def test_windows_and_macos_build_vendor_specific_candidates(self):
        windows = detect_video_capabilities(
            ffmpeg_path="ffmpeg", ffprobe_path="ffprobe", runner=FakeRunner(system="Windows"),
            system_name="Windows",
        )
        self.assertEqual(windows.devices[0].vendor, "NVIDIA")
        self.assertEqual(windows.selected.name, "h264_nvenc")

        windows_amd = detect_video_capabilities(
            ffmpeg_path="ffmpeg", ffprobe_path="ffprobe",
            runner=FakeRunner(system="Windows", gpu_vendor="AMD"),
            system_name="Windows",
        )
        self.assertEqual(windows_amd.selected.name, "h264_amf")

        windows_intel = detect_video_capabilities(
            ffmpeg_path="ffmpeg", ffprobe_path="ffprobe",
            runner=FakeRunner(system="Windows", gpu_vendor="Intel"),
            system_name="Windows",
        )
        self.assertEqual(windows_intel.selected.name, "h264_qsv")

        macos = detect_video_capabilities(
            ffmpeg_path="ffmpeg", ffprobe_path="ffprobe", runner=FakeRunner(system="Darwin"),
            system_name="Darwin",
        )
        self.assertEqual(macos.devices[0].vendor, "Apple")
        self.assertEqual(macos.selected.name, "h264_videotoolbox")

    def test_render_command_is_static_1080p_and_preserves_audio_when_safe(self):
        candidate = EncoderCandidate("h264_vaapi", "VA-API", "/dev/dri/renderD128", verified=True)
        command = build_video_command(
            "ffmpeg", candidate, Path("timeline.ffconcat"), Path("audio.mp3"), Path("out.mp4"),
            audio_copy=True,
        )
        joined = " ".join(command)
        self.assertIn("-f concat", joined)
        self.assertIn("-fps_mode vfr", joined)
        self.assertNotIn("-r", command)
        self.assertNotIn("-loop", command)
        self.assertIn("scale=1920:1080:force_original_aspect_ratio=decrease", joined)
        self.assertIn("pad=1920:1080", joined)
        self.assertIn("format=nv12,hwupload", joined)
        self.assertIn("-c:v h264_vaapi", joined)
        self.assertIn("-c:a copy", joined)
        self.assertNotIn("-shortest", command)
        self.assertIn("+faststart", command)

        cpu = EncoderCandidate("libx264", "CPU", hardware=False, verified=True)
        cpu_command = build_video_command(
            "ffmpeg", cpu, Path("timeline.ffconcat"), Path("audio.mp3"), Path("out.mp4"),
            audio_copy=False,
        )
        self.assertIn("-b:a 192k", " ".join(cpu_command))
        self.assertIn("format=yuv420p", " ".join(cpu_command))

    def test_progress_parser_reports_percent_speed_and_eta(self):
        state = {}
        parse_progress_line(state, "out_time_us=25000000", 100.0)
        update = parse_progress_line(state, "speed=5.0x", 100.0)
        self.assertAlmostEqual(update["percentage"], 25.0)
        self.assertAlmostEqual(update["speed"], 5.0)
        self.assertAlmostEqual(update["eta"], 15.0)

    def test_mp3_copy_requires_a_successful_mux_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "audio.mp3"
            audio.write_bytes(b"audio")

            def runner(command, _timeout):
                command = list(command)
                if command[0] == "ffprobe":
                    return subprocess.CompletedProcess(
                        command, 0,
                        json.dumps({
                            "streams": [{
                                "codec_name": "mp3", "sample_rate": "24000",
                                "channels": 1, "duration": "2.0",
                            }],
                            "format": {"duration": "2.0"},
                        }),
                        "",
                    )
                Path(command[-1]).write_bytes(b"probe mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            self.assertTrue(
                mp3_copy_is_safe(audio, "ffmpeg", "ffprobe", runner=runner)
            )

            def failed_mux(command, _timeout):
                command = list(command)
                if command[0] == "ffprobe":
                    return runner(command, _timeout)
                return subprocess.CompletedProcess(command, 1, "", "mux failed")

            self.assertFalse(
                mp3_copy_is_safe(audio, "ffmpeg", "ffprobe", runner=failed_mux)
            )


if __name__ == "__main__":
    unittest.main()
