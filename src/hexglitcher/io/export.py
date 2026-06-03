"""Export a rendered document to an image file (full resolution)."""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
from PIL import Image

from ..engine.document import Document
from ..engine.pipeline import RenderEngine

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None


def render_full(doc: Document) -> Optional[np.ndarray]:
    """Render the whole document at native resolution -> RGBA uint8 (or None)."""
    rgba, _ok = RenderEngine().render(doc.snapshot(), max_dim=None)
    return rgba


def export_document(doc: Document, path: str, quality: int = 92) -> None:
    rgba = render_full(doc)
    if rgba is None:
        raise RuntimeError("Nothing to export (no decodable image).")
    im = Image.fromarray(rgba)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg", ".bmp"):
        im = im.convert("RGB")
        im.save(path, quality=quality)
    else:
        im.save(path)


def _apply_sweep(doc: Document, sweep: dict, t: float) -> None:
    """Set the swept op parameter to its interpolated value at position t in [0,1]."""
    try:
        layer = doc.layers[sweep["layer"]]
    except (IndexError, KeyError, TypeError):
        return
    value = sweep["start"] + (sweep["end"] - sweep["start"]) * t
    for op in layer.ops:
        if op.uid == sweep.get("op_uid"):
            spec = op.optype.spec(sweep["param"])
            op.params[sweep["param"]] = (
                int(round(value)) if (spec and spec.kind in ("int", "seed")) else float(value)
            )
            return


def _shared_palette(frames_rgb, colors: int = 256):
    """One adaptive palette derived from a thumbnail montage of every frame.

    Mapping all frames to a single palette is what kills the per-frame colour
    flicker that plagues naive frame-by-frame GIF quantization.
    """
    thumbs = []
    for im in frames_rgb:
        t = im.copy()
        t.thumbnail((144, 144))
        thumbs.append(t)
    w = max(t.width for t in thumbs)
    montage = Image.new("RGB", (w, sum(t.height for t in thumbs)))
    y = 0
    for t in thumbs:
        montage.paste(t, (0, y))
        y += t.height
    return montage.convert("P", palette=Image.Palette.ADAPTIVE, colors=colors)


def export_animation(doc: Document, path: str, frames: int = 24, fps: int = 12,
                     loop: str = "forever", max_dim: Optional[int] = None,
                     sweep: Optional[dict] = None, dither: bool = True,
                     progress=None) -> int:
    """Render an animated GIF from the current stack.

    Without `sweep`, the document **seed** is swept (random-ish variation). With a
    `sweep` dict ``{layer, op_uid, param, start, end}``, that op parameter is
    interpolated start->end across the frames for smooth, intentional motion.
    `loop` is ``"forever" | "once" | "pingpong"``; `max_dim` downscales for a
    smaller file. All frames share one adaptive palette (optionally dithered) so
    colours stay stable. `progress(i, n)` is called per frame. Returns frames written.
    """
    eng = RenderEngine()
    n = max(2, int(frames))
    base_seed = doc.seed
    rgba_frames = []
    for i in range(n):
        t = i / (n - 1)
        snap = doc.snapshot()
        if sweep:
            _apply_sweep(snap, sweep, t)
        else:
            # Advance the doc seed AND every op's own seed param, so randomized
            # ops (which use their own seed) actually vary frame to frame.
            snap.seed = base_seed + i
            for layer in snap.layers:
                for op in layer.ops:
                    if op.params.get("seed") is not None:
                        op.params["seed"] = int(op.params["seed"]) + i
        rgba, _ = eng.render(snap, max_dim=max_dim)
        if rgba is not None:
            rgba_frames.append(rgba)
        if progress:
            progress(i + 1, n)
    if not rgba_frames:
        raise RuntimeError("Nothing to export (no decodable image).")

    rgb = [Image.fromarray(f).convert("RGB") for f in rgba_frames]
    if loop == "pingpong" and len(rgb) > 2:
        rgb = rgb + rgb[-2:0:-1]                     # there-and-back, no duplicated ends
    palette = _shared_palette(rgb)
    d = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    quant = [im.quantize(palette=palette, dither=d) for im in rgb]

    duration = max(20, int(1000 / max(1, fps)))
    quant[0].save(path, save_all=True, append_images=quant[1:], duration=duration,
                  loop=(1 if loop == "once" else 0), optimize=True, disposal=2, format="GIF")
    return len(quant)


_ENCODER_CACHE: dict = {}


def video_encoder() -> str:
    """Pick a GPU encoder (NVENC) if ffmpeg exposes it, else CPU libx264."""
    if "enc" not in _ENCODER_CACHE:
        import subprocess
        enc = "libx264"
        try:
            out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                                 capture_output=True, text=True, timeout=10)
            if "h264_nvenc" in out.stdout:
                enc = "h264_nvenc"
        except Exception:
            pass
        _ENCODER_CACHE["enc"] = enc
    return _ENCODER_CACHE["enc"]


def export_video(doc: Document, path: str, fps: float = 24.0,
                 frames=None, audio_from=None, progress=None) -> int:
    """Glitch every frame through the stack and stream it to ffmpeg.

    Frames are read sequentially (one capture, no per-frame seek) and each is
    materialized as the source's current frame so the whole pipeline renders it;
    the result is piped as raw video into ffmpeg, which encodes on the GPU
    (h264_nvenc when available) and muxes the original audio back in.
    ``progress(i, n)`` is called per frame. Returns frames written.
    """
    import subprocess
    import tempfile

    if cv2 is None:
        raise RuntimeError("OpenCV is required for video export.")
    cw, ch = doc.canvas_size()
    if cw <= 0 or ch <= 0:
        raise RuntimeError("Nothing to export.")

    from ..engine.layer import SourceImage
    from ..engine.video import SourceVideo

    src_vid = next((s for s in doc.sources.values() if isinstance(s, SourceVideo)), None)
    # Render against a PRIVATE copy of the document so we never mutate the shared
    # source (and its frame cache) while the GUI's render worker may be using it.
    pdoc = doc.snapshot()
    pvid = None
    if src_vid is not None:
        pvid = SourceVideo.from_file(src_vid.path)
        pdoc.sources = {pvid.uid: pvid}
        for layer in pdoc.layers:
            layer.source_id = pvid.uid

    n = int(frames) if frames else doc.frame_count()
    eng = RenderEngine()
    encoder = video_encoder()

    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{cw}x{ch}", "-r", str(float(fps) or 24.0), "-i", "pipe:0"]
    if audio_from:
        cmd += ["-i", audio_from]
    cmd += ["-c:v", encoder, "-pix_fmt", "yuv420p"]
    if audio_from:
        cmd += ["-map", "0:v:0", "-map", "1:a:0?", "-shortest"]
    cmd += [path]

    written = 0
    try:
        with tempfile.TemporaryFile() as errfile:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL, stderr=errfile)
            cap = cv2.VideoCapture(pvid.path) if pvid is not None else None
            try:
                for i in range(n):
                    if cap is not None:
                        ok, frame = cap.read()
                        if not ok:
                            break
                        ok_b, enc = cv2.imencode(".bmp", frame)
                        if ok_b:
                            pvid._frame_cache = {i: SourceImage(data=enc.tobytes(), ext=".bmp",
                                                                name=f"{pvid.name}#{i}")}
                    pdoc.frame = i
                    rgba, _ = eng.render(pdoc)
                    if rgba is None:
                        continue
                    bgr = cv2.cvtColor(np.ascontiguousarray(rgba[..., :3]), cv2.COLOR_RGB2BGR)
                    if bgr.shape[:2] != (ch, cw):
                        bgr = cv2.resize(bgr, (cw, ch))
                    proc.stdin.write(bgr.tobytes())
                    written += 1
                    if progress:
                        progress(i + 1, n)
            finally:
                if cap is not None:
                    cap.release()
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if proc.returncode not in (0, None):
                errfile.seek(0)
                msg = errfile.read().decode("utf-8", "ignore")[-400:]
                raise RuntimeError(f"ffmpeg ({encoder}) failed:\n{msg}")
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg was not found on PATH — install ffmpeg to export video.") from exc
    return written
