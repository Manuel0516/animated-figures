#!/usr/bin/env python3
"""
Spawn ffmpeg as a frame sink we can pipe raw video into.

Why this exists: the obvious `Popen(..., stderr=PIPE)` deadlocks. ffmpeg writes
progress to stderr, and once the ~64 KB pipe buffer fills with nobody reading
it, ffmpeg blocks on that write forever -- while we sit blocked writing frames
into its stdin. Neither side moves and the render hangs with no error.

So: quiet ffmpeg down (`-nostats -loglevel error`) AND drain whatever it does
emit on a background thread, keeping the tail for error reporting.
"""
import subprocess
import threading
from collections import deque
from pathlib import Path

QUIET_ARGS = ["-nostats", "-loglevel", "error"]


def alpha_decoder_args(path):
    """Input-side flags needed to actually get the alpha channel out of a file.

    WebM/VP9 stores alpha in a side channel, and ffmpeg's *native* vp9 decoder
    silently ignores it -- it reports yuv420p, so the transparent background
    decodes as opaque black and an overlay covers whatever is underneath.
    Only the libvpx-vp9 decoder yields yuva420p. QuickTime formats (qtrle,
    ProRes 4444) carry alpha fine with the default decoder.
    """
    if Path(path).suffix.lower() == ".webm":
        return ["-c:v", "libvpx-vp9"]
    return []


class FfmpegSink:
    """ffmpeg subprocess you write raw frames to, with stderr safely drained."""

    def __init__(self, cmd, tail_lines: int = 40):
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        self._tail = deque(maxlen=tail_lines)
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self):
        for raw in self._proc.stderr:
            line = raw.decode(errors="replace").rstrip()
            if line:
                self._tail.append(line)
        self._proc.stderr.close()

    def write(self, data: bytes) -> None:
        self._proc.stdin.write(data)

    def close(self) -> int:
        """Close stdin, wait for ffmpeg, return its exit code."""
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        code = self._proc.wait()
        self._thread.join(timeout=5)
        return code

    @property
    def errors(self) -> str:
        return "\n".join(self._tail)

    def kill(self) -> None:
        self._proc.kill()
        self._proc.wait()
