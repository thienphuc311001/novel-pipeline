"""Hardware-adaptive FFmpeg helpers for static-image audiobook videos.

This module intentionally has no Qt imports.  Capability discovery and command
construction can therefore be tested with injected command runners, while the
desktop UI owns the asynchronous QProcess used for a full render.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence


class VideoDependencyError(RuntimeError):
    pass


class VideoValidationError(RuntimeError):
    pass


@dataclass
class GpuDevice:
    vendor: str
    model: str
    driver: str = ""
    device: str = ""
    device_type: str = "unknown"


@dataclass
class EncoderCandidate:
    name: str
    backend: str
    device: str = ""
    hardware: bool = True
    verified: bool = False
    error: str = ""
    probe_command: List[str] = field(default_factory=list)


@dataclass
class VideoCapabilities:
    ffmpeg_path: str
    ffprobe_path: str
    ffmpeg_version: str
    system: str
    hwaccels: List[str] = field(default_factory=list)
    listed_h264_encoders: List[str] = field(default_factory=list)
    devices: List[GpuDevice] = field(default_factory=list)
    candidates: List[EncoderCandidate] = field(default_factory=list)
    diagnostics: List[str] = field(default_factory=list)

    @property
    def verified_candidates(self) -> List[EncoderCandidate]:
        return [candidate for candidate in self.candidates if candidate.verified]

    @property
    def selected(self) -> Optional[EncoderCandidate]:
        verified = self.verified_candidates
        return verified[0] if verified else None


@dataclass
class AudioProbe:
    duration: float
    codec: str
    sample_rate: int
    channels: int


@dataclass
class VideoRenderResult:
    output_path: str
    duration: float
    file_size: int
    encoder: str
    backend: str
    render_speed: float
    audio_mode: str
    attempt_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


CommandRunner = Callable[[Sequence[str], float], subprocess.CompletedProcess[str]]


def _default_runner(command: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )


def _run_optional(
    command: Sequence[str],
    runner: CommandRunner,
    *,
    timeout: float = 8.0,
) -> subprocess.CompletedProcess[str] | None:
    try:
        return runner(command, timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def _vendor_name(value: str) -> str:
    lowered = (value or "").lower()
    if "nvidia" in lowered or "0x10de" in lowered or lowered == "10de":
        return "NVIDIA"
    if "intel" in lowered or "0x8086" in lowered or lowered == "8086":
        return "Intel"
    if any(item in lowered for item in ("amd", "ati", "advanced micro", "0x1002")) or lowered == "1002":
        return "AMD"
    if "apple" in lowered:
        return "Apple"
    return (value or "Unknown").strip() or "Unknown"


def _command_output(command: Sequence[str], runner: CommandRunner, timeout: float = 8.0) -> str:
    completed = _run_optional(command, runner, timeout=timeout)
    if completed is None or completed.returncode != 0:
        return ""
    return completed.stdout or ""


def _linux_renderer(runner: CommandRunner) -> tuple[str, str]:
    output = _command_output(["glxinfo", "-B"], runner)
    vendor_match = re.search(r"^\s*Vendor:\s*(.+?)(?:\s*\(|$)", output, re.MULTILINE)
    device_match = re.search(r"^\s*Device:\s*(.+?)(?:\s*\(|$)", output, re.MULTILINE)
    if not device_match:
        device_match = re.search(r"^OpenGL renderer string:\s*(.+)$", output, re.MULTILINE)
    return (
        _vendor_name(vendor_match.group(1) if vendor_match else ""),
        device_match.group(1).strip() if device_match else "",
    )


def _discover_linux_devices(runner: CommandRunner, drm_root: Path) -> List[GpuDevice]:
    devices: List[GpuDevice] = []
    gl_vendor, gl_model = _linux_renderer(runner)
    for render_node in sorted(drm_root.glob("renderD*")):
        device_dir = render_node / "device"
        try:
            vendor_id = (device_dir / "vendor").read_text().strip().removeprefix("0x")
        except OSError:
            vendor_id = ""
        vendor = _vendor_name(vendor_id)
        driver_path = device_dir / "driver"
        try:
            driver = driver_path.resolve().name
        except OSError:
            driver = ""
        model = gl_model if len(list(drm_root.glob("renderD*"))) == 1 else ""
        if not model:
            uevent = ""
            try:
                uevent = (device_dir / "uevent").read_text()
            except OSError:
                pass
            slot_match = re.search(r"^PCI_SLOT_NAME=(.+)$", uevent, re.MULTILINE)
            if slot_match:
                output = _command_output(["lspci", "-s", slot_match.group(1)], runner)
                if ": " in output:
                    model = output.split(": ", 1)[1].split(" (rev", 1)[0].strip()
        if not model:
            model = f"{vendor} GPU"
        if vendor == "Unknown" and gl_vendor != "Unknown":
            vendor = gl_vendor
        lowered = model.lower()
        if any(word in lowered for word in ("integrated", "780m", "uhd", "iris")):
            device_type = "integrated"
        elif vendor in ("AMD", "Intel", "NVIDIA"):
            device_type = "discrete"
        else:
            device_type = "unknown"
        devices.append(
            GpuDevice(vendor, model, driver, str(Path("/dev/dri") / render_node.name), device_type)
        )

    nvidia_output = _command_output(
        ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], runner
    )
    for line in nvidia_output.splitlines():
        if not line.strip():
            continue
        model, _, driver = line.partition(",")
        if not any(device.vendor == "NVIDIA" and device.model == model.strip() for device in devices):
            devices.insert(0, GpuDevice("NVIDIA", model.strip(), driver.strip(), "", "discrete"))
    return devices


def _discover_windows_devices(runner: CommandRunner) -> List[GpuDevice]:
    script = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterCompatibility,DriverVersion,PNPDeviceID | ConvertTo-Json -Compress"
    )
    output = _command_output(["powershell", "-NoProfile", "-Command", script], runner, 12.0)
    try:
        data = json.loads(output) if output else []
    except json.JSONDecodeError:
        data = []
    if isinstance(data, dict):
        data = [data]
    devices = []
    for item in data if isinstance(data, list) else []:
        model = str(item.get("Name") or "Unknown GPU")
        vendor = _vendor_name(str(item.get("AdapterCompatibility") or model))
        kind = "integrated" if vendor == "Intel" or "radeon graphics" in model.lower() else "discrete"
        devices.append(
            GpuDevice(vendor, model, str(item.get("DriverVersion") or ""), str(item.get("PNPDeviceID") or ""), kind)
        )
    return devices


def _discover_macos_devices(runner: CommandRunner) -> List[GpuDevice]:
    output = _command_output(["system_profiler", "SPDisplaysDataType", "-json"], runner, 15.0)
    try:
        entries = json.loads(output).get("SPDisplaysDataType", []) if output else []
    except (json.JSONDecodeError, AttributeError):
        entries = []
    devices = []
    for item in entries:
        model = str(item.get("sppci_model") or item.get("_name") or "Apple GPU")
        vendor = _vendor_name(str(item.get("sppci_vendor") or model))
        devices.append(GpuDevice(vendor, model, str(item.get("spdisplays_gmux-version") or ""), "", "integrated"))
    return devices


def encoder_options(candidate: EncoderCandidate) -> List[str]:
    if candidate.name == "h264_vaapi":
        return ["-c:v", candidate.name, "-profile:v", "high", "-qp", "23"]
    if candidate.name == "h264_nvenc":
        return ["-c:v", candidate.name, "-preset", "p4", "-tune", "hq", "-rc", "constqp", "-qp", "23"]
    if candidate.name == "h264_qsv":
        return ["-c:v", candidate.name, "-preset", "faster", "-global_quality", "23"]
    if candidate.name == "h264_amf":
        return ["-c:v", candidate.name, "-quality", "speed", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23"]
    if candidate.name == "h264_videotoolbox":
        return ["-c:v", candidate.name, "-q:v", "65", "-profile:v", "high"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-tune", "stillimage", "-profile:v", "high"]


def encoder_filter(candidate: EncoderCandidate) -> str:
    base = (
        "scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )
    if candidate.name == "h264_vaapi":
        return base + ",format=nv12,hwupload"
    return base + ",format=yuv420p"


def build_smoke_test_command(ffmpeg_path: str, candidate: EncoderCandidate) -> List[str]:
    command = [str(ffmpeg_path), "-hide_banner", "-loglevel", "error"]
    if candidate.name == "h264_vaapi" and candidate.device:
        command += ["-vaapi_device", candidate.device]
    command += [
        "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=1:d=1",
        "-frames:v", "1", "-an", "-vf", encoder_filter(candidate),
        *encoder_options(candidate), "-g", "60", "-f", "null", "-",
    ]
    return command


def _parse_ffmpeg_discovery(ffmpeg_path: str, runner: CommandRunner) -> tuple[str, List[str], List[str]]:
    version_output = _command_output([ffmpeg_path, "-version"], runner)
    version_line = version_output.splitlines()[0] if version_output else "unknown"
    version_match = re.search(r"ffmpeg version\s+([^\s]+)", version_line, re.IGNORECASE)
    version = version_match.group(1) if version_match else version_line
    hw_output = _command_output([ffmpeg_path, "-hide_banner", "-hwaccels"], runner)
    hwaccels = [
        line.strip() for line in hw_output.splitlines()
        if line.strip() and "Hardware acceleration" not in line
    ]
    encoder_output = _command_output([ffmpeg_path, "-hide_banner", "-encoders"], runner)
    encoders = sorted(set(re.findall(r"^\s*V[\.A-Z]{5}\s+(h264_[\w]+|libx264)\s", encoder_output, re.MULTILINE)))
    return version, hwaccels, encoders


def _candidate_specs(devices: Iterable[GpuDevice], system: str) -> List[EncoderCandidate]:
    devices = sorted(
        devices,
        key=lambda item: 0 if item.device_type == "discrete" else (1 if item.device_type == "integrated" else 2),
    )
    candidates: List[EncoderCandidate] = []
    for device in devices:
        if device.vendor == "NVIDIA":
            candidates.append(EncoderCandidate("h264_nvenc", "NVENC", device.device))
        elif device.vendor == "Intel":
            candidates.append(EncoderCandidate("h264_qsv", "Quick Sync", device.device))
            if system == "Linux" and device.device:
                candidates.append(EncoderCandidate("h264_vaapi", "VA-API", device.device))
        elif device.vendor == "AMD":
            if system == "Linux" and device.device:
                candidates.append(EncoderCandidate("h264_vaapi", "VA-API", device.device))
            elif system == "Windows":
                candidates.append(EncoderCandidate("h264_amf", "AMF", device.device))
        elif device.vendor == "Apple" or system == "Darwin":
            candidates.append(EncoderCandidate("h264_videotoolbox", "VideoToolbox", device.device))
    candidates.append(EncoderCandidate("libx264", "CPU", "", hardware=False))
    unique: List[EncoderCandidate] = []
    keys = set()
    for candidate in candidates:
        key = (
            candidate.name,
            candidate.device if candidate.name == "h264_vaapi" else "",
        )
        if key not in keys:
            keys.add(key)
            unique.append(candidate)
    return unique


def detect_video_capabilities(
    *,
    ffmpeg_path: str | None = None,
    ffprobe_path: str | None = None,
    runner: CommandRunner = _default_runner,
    system_name: str | None = None,
    drm_root: Path = Path("/sys/class/drm"),
    smoke_timeout: float = 15.0,
) -> VideoCapabilities:
    """Discover devices and return only encoders proven by a real test encode."""
    ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    ffprobe = ffprobe_path or shutil.which("ffprobe")
    if not ffmpeg:
        raise VideoDependencyError("FFmpeg was not found on PATH.")
    if not ffprobe:
        raise VideoDependencyError("FFprobe was not found on PATH.")
    system = system_name or platform.system()
    version, hwaccels, listed = _parse_ffmpeg_discovery(ffmpeg, runner)
    if system == "Linux":
        devices = _discover_linux_devices(runner, Path(drm_root))
    elif system == "Windows":
        devices = _discover_windows_devices(runner)
    elif system == "Darwin":
        devices = _discover_macos_devices(runner)
    else:
        devices = []

    capabilities = VideoCapabilities(ffmpeg, ffprobe, version, system, hwaccels, listed, devices)
    for candidate in _candidate_specs(devices, system):
        if candidate.name not in listed:
            candidate.error = "Encoder is not present in this FFmpeg build."
            capabilities.candidates.append(candidate)
            continue
        command = build_smoke_test_command(ffmpeg, candidate)
        candidate.probe_command = command
        completed = _run_optional(command, runner, timeout=smoke_timeout)
        if completed is None:
            candidate.error = "Test encode could not be started or timed out."
        elif completed.returncode == 0:
            candidate.verified = True
        else:
            candidate.error = (completed.stderr or completed.stdout or "Test encode failed.").strip()
        capabilities.candidates.append(candidate)
    if not capabilities.verified_candidates:
        details = "; ".join(f"{item.name}: {item.error}" for item in capabilities.candidates)
        raise VideoDependencyError(f"No working H.264 encoder was found. {details}")
    return capabilities


def probe_audio(path: Path, ffprobe_path: str, runner: CommandRunner = _default_runner) -> AudioProbe:
    path = Path(path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise VideoValidationError(f"Audiobook is missing or empty: {path}")
    command = [
        ffprobe_path, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels,duration:format=duration",
        "-of", "json", str(path),
    ]
    completed = runner(command, 20.0)
    if completed.returncode != 0:
        raise VideoValidationError(completed.stderr.strip() or "FFprobe could not read the audiobook.")
    try:
        data = json.loads(completed.stdout)
        stream = (data.get("streams") or [])[0]
        duration = float(stream.get("duration") or data.get("format", {}).get("duration") or 0)
        codec = str(stream.get("codec_name") or "")
        sample_rate = int(stream.get("sample_rate") or 0)
        channels = int(stream.get("channels") or 0)
    except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as error:
        raise VideoValidationError("FFprobe returned invalid audiobook metadata.") from error
    if duration <= 0 or not codec or channels <= 0:
        raise VideoValidationError("Audiobook has no valid audio stream or duration.")
    return AudioProbe(duration, codec, sample_rate, channels)


def mp3_copy_is_safe(
    audio_path: Path,
    ffmpeg_path: str,
    ffprobe_path: str,
    *,
    runner: CommandRunner = _default_runner,
    temp_dir: Path | None = None,
) -> bool:
    """Verify that this MP3 can be copied into MP4 without re-encoding."""
    probe = probe_audio(audio_path, ffprobe_path, runner)
    if probe.codec != "mp3" or probe.channels not in (1, 2) or probe.sample_rate <= 0:
        return False
    directory = Path(temp_dir) if temp_dir else Path(audio_path).parent
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".audio_copy_probe_", suffix=".mp4", dir=directory)
    os.close(descriptor)
    target = Path(temporary)
    try:
        target.unlink(missing_ok=True)
        command = [
            ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
            "-t", "1", "-i", str(audio_path), "-map", "0:a:0", "-c:a", "copy",
            "-movflags", "+faststart", str(target),
        ]
        completed = runner(command, 20.0)
        return completed.returncode == 0 and target.is_file() and target.stat().st_size > 0
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        target.unlink(missing_ok=True)


def build_video_command(
    ffmpeg_path: str,
    candidate: EncoderCandidate,
    thumbnail_path: Path,
    audiobook_path: Path,
    output_path: Path,
    *,
    audio_copy: bool,
) -> List[str]:
    command = [ffmpeg_path, "-y", "-hide_banner", "-loglevel", "warning", "-nostats"]
    if candidate.name == "h264_vaapi" and candidate.device:
        command += ["-vaapi_device", candidate.device]
    command += [
        "-progress", "pipe:1", "-loop", "1", "-framerate", "1", "-i", str(thumbnail_path),
        "-i", str(audiobook_path), "-map", "0:v:0", "-map", "1:a:0",
        "-vf", encoder_filter(candidate), *encoder_options(candidate),
        "-r", "1", "-g", "60", "-fps_mode", "cfr",
    ]
    if audio_copy:
        command += ["-c:a", "copy"]
    else:
        command += ["-c:a", "aac", "-b:a", "192k"]
    command += [
        "-shortest", "-map_metadata", "-1", "-movflags", "+faststart",
        "-f", "mp4", str(output_path),
    ]
    return command


def parse_progress_line(state: Dict[str, Any], line: str, duration: float) -> Optional[Dict[str, Any]]:
    if "=" not in line:
        return None
    key, value = line.strip().split("=", 1)
    state[key] = value
    if key not in ("progress", "out_time", "out_time_us", "out_time_ms", "speed"):
        return None
    seconds = 0.0
    raw_us = state.get("out_time_us") or state.get("out_time_ms")
    if raw_us:
        try:
            seconds = max(0.0, float(raw_us) / 1_000_000.0)
        except ValueError:
            pass
    elif state.get("out_time"):
        try:
            hours, minutes, seconds_text = str(state["out_time"]).split(":")
            seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds_text)
        except (ValueError, TypeError):
            pass
    speed_text = str(state.get("speed") or "0x").strip().removesuffix("x")
    try:
        speed = max(0.0, float(speed_text))
    except ValueError:
        speed = 0.0
    percentage = min(100.0, (seconds / duration * 100.0) if duration > 0 else 0.0)
    eta = ((duration - seconds) / speed) if speed > 0 and duration > seconds else 0.0
    return {"elapsed": seconds, "percentage": percentage, "speed": speed, "eta": eta}


def probe_video(path: Path, ffprobe_path: str, runner: CommandRunner = _default_runner) -> Dict[str, Any]:
    command = [
        ffprobe_path, "-v", "error", "-show_entries",
        "stream=codec_type,codec_name,width,height:format=duration", "-of", "json", str(path),
    ]
    completed = runner(command, 30.0)
    if completed.returncode != 0:
        raise VideoValidationError(completed.stderr.strip() or "FFprobe could not validate the video.")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise VideoValidationError("FFprobe returned invalid video metadata.") from error


def validate_rendered_video(
    path: Path,
    expected_duration: float,
    ffprobe_path: str,
    runner: CommandRunner = _default_runner,
) -> float:
    path = Path(path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise VideoValidationError("FFmpeg produced an empty video.")
    data = probe_video(path, ffprobe_path, runner)
    streams = data.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not video or video.get("codec_name") != "h264":
        raise VideoValidationError("Output does not contain an H.264 video stream.")
    if (int(video.get("width") or 0), int(video.get("height") or 0)) != (1920, 1080):
        raise VideoValidationError("Output resolution is not 1920×1080.")
    if not audio:
        raise VideoValidationError("Output does not contain an audio stream.")
    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    tolerance = max(2.0, expected_duration * 0.01)
    if duration <= 0 or abs(duration - expected_duration) > tolerance:
        raise VideoValidationError(
            f"Output duration {duration:.2f}s does not match audiobook {expected_duration:.2f}s."
        )
    return duration


def format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
