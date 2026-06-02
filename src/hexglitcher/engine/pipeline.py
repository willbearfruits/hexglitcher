"""The render engine: turn a Document into a composited RGBA image.

Per layer the pipeline runs two domains separated by a decode boundary::

    source bytes ─[BYTE ops]→ corrupted bytes ─[DECODE]→ RGBA ─[PIXEL ops]→ buffer

Prefix caching (darktable-style): each op folds its identity into a running hash
and the output *after* it is cached under that hash. Editing op *i* only
recomputes from *i* onward; a pixel-op edit reuses the (expensive) cached decode.

The engine never raises on bad image data — a failed decode falls back to the
layer's clean original so the UI keeps showing something sensible.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Callable, Optional

import numpy as np

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None

from .blend import composite
from .decode import decode_bytes
from .document import Document
from .hashing import fold
from .layer import Layer, SourceImage
from .operation import ByteContext, Operation, PixelContext
from ..formats.base import FormatBackend


def resolve_region(op: Operation, fmt: FormatBackend, data: bytes) -> tuple[int, int]:
    """Resolve an op's region to absolute ``(start, end)`` offsets.

    ``op.region`` of ``None`` means the format's safe zone (between header and
    footer) — the recommended default. Explicit values may be absolute ints,
    negative (from EOF) or floats in [0,1] (proportional). Explicit regions are
    clamped only to the buffer, letting power users target the header on purpose.
    """
    n = len(data)
    if op.region is None:
        return fmt.safe_zone(data)

    def _resolve(v) -> int:
        if isinstance(v, float) and 0.0 <= v <= 1.0:
            return int(round(v * n))
        if isinstance(v, (int, float)) and v < 0:
            return n + int(v)
        return int(v)

    a, b = _resolve(op.region[0]), _resolve(op.region[1])
    a = max(0, min(a, n))
    b = max(0, min(b, n))
    if b < a:
        a, b = b, a
    return a, b


class RenderEngine:
    """Holds the prefix cache and renders documents.

    One engine instance per open document (or per render worker). The cache is a
    bounded LRU keyed by content/parameter hashes, so it survives across renders
    and gives incremental recompute for free.
    """

    def __init__(self, load_external: Optional[Callable[[str], bytes]] = None,
                 max_cache: int = 96) -> None:
        self._cache: "OrderedDict[str, object]" = OrderedDict()
        self._max_cache = max_cache
        self._load_external = load_external or self._default_loader
        self._ext_cache: dict[str, bytes] = {}

    # cache ------------------------------------------------------------------
    def _get(self, key: str):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _put(self, key: str, value) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_cache:
            self._cache.popitem(last=False)

    def clear_cache(self) -> None:
        self._cache.clear()

    def _default_loader(self, path: str) -> bytes:
        if path not in self._ext_cache:
            try:
                with open(path, "rb") as fh:
                    self._ext_cache[path] = fh.read()
            except Exception:
                self._ext_cache[path] = b""
        return self._ext_cache[path]

    # rng --------------------------------------------------------------------
    @staticmethod
    def _rng_for(op: Operation, doc_seed: int) -> np.random.Generator:
        if "seed" in op.params and op.params["seed"] is not None:
            seed = int(op.params["seed"])
        else:
            seed = (doc_seed * 1000003) ^ (int(op.uid[:8], 16))
        return np.random.default_rng(seed & 0xFFFFFFFF)

    # stages -----------------------------------------------------------------
    def _byte_stage(self, src: SourceImage, layer: Layer, doc_seed: int) -> tuple[bytes, str]:
        data = src.data
        running = "src:" + src.content_hash
        for op in layer.byte_ops():
            running = fold(running, *op.identity())
            key = "b:" + running
            cached = self._get(key)
            if cached is not None:
                data = cached  # type: ignore[assignment]
                continue
            if op.optype.whole_file:
                start, end = 0, len(data)
            else:
                start, end = resolve_region(op, src.fmt, data)
            region = bytearray(data[start:end])
            ctx = ByteContext(
                rng=self._rng_for(op, doc_seed), fmt=src.fmt,
                region=(start, end), total_size=len(data),
                load_external=self._load_external,
            )
            try:
                result = op.optype.apply(region, op.params, ctx)
            except Exception:
                result = None
            new_region = bytes(result) if result is not None else bytes(region)
            data = data[:start] + new_region + data[end:]
            self._put(key, data)
        return data, running

    def _decode_stage(self, data: bytes, byte_hash: str, src: SourceImage) -> tuple[np.ndarray, bool]:
        key = "d:" + byte_hash
        cached = self._get(key)
        if cached is not None:
            img, ok = cached  # type: ignore[misc]
            return img, ok
        img = decode_bytes(data)
        ok = img is not None
        if img is None:
            clean = src.clean_decoded()
            img = clean if clean is not None else np.zeros((16, 16, 4), np.uint8)
        self._put(key, (img, ok))
        return img, ok

    def _pixel_stage(self, img: np.ndarray, byte_hash: str, layer: Layer,
                     doc_seed: int, max_dim: Optional[int]) -> np.ndarray:
        proxy = max_dim is not None
        if proxy:
            img = _downscale(img, max_dim)
        running = byte_hash + (f":proxy{max_dim}" if proxy else ":full")
        for op in layer.pixel_ops():
            running = fold(running, *op.identity())
            key = "p:" + running
            cached = self._get(key)
            if cached is not None:
                img = cached  # type: ignore[assignment]
                continue
            ctx = PixelContext(rng=self._rng_for(op, doc_seed), proxy=proxy)
            try:
                out = op.optype.apply(img, op.params, ctx)
                if out is not None:
                    img = out
            except Exception:
                pass
            self._put(key, img)
        return img

    def _rasterized_source(self, src: SourceImage) -> Optional[SourceImage]:
        """A BMP re-encoding of a source's clean pixels (cached).

        Generic byte corruption breaks brittle formats (PNG/WebP/GIF): the decode
        fails and we'd otherwise show nothing. BMP corrupts visibly and almost never
        fails to decode, so re-running the byte ops on a BMP keeps the glitch
        visible — the 'convert to BMP first' databending rule, applied automatically.
        """
        key = "raster:" + src.content_hash
        cached = self._get(key)
        if cached is not None:
            return cached or None
        out: Optional[SourceImage] = None
        clean = src.clean_decoded()
        if clean is not None and cv2 is not None:
            bgr = cv2.cvtColor(clean, cv2.COLOR_RGBA2BGR)
            ok, enc = cv2.imencode(".bmp", bgr)
            if ok:
                out = SourceImage(data=enc.tobytes(), ext=".bmp", name=src.name)
        self._put(key, out if out is not None else False)
        return out

    def render_layer(self, doc: Document, layer: Layer, target: tuple[int, int],
                     max_dim: Optional[int]) -> tuple[np.ndarray, bool]:
        src = doc.resolve_source(layer.source_id)
        if src is None:
            return np.zeros((target[1], target[0], 4), np.uint8), False
        data, byte_hash = self._byte_stage(src, layer, doc.seed)
        img, ok = self._decode_stage(data, byte_hash, src)
        # If byte corruption broke a brittle format, retry on a BMP rasterization
        # so the glitch stays visible instead of silently falling back to clean.
        if not ok and layer.byte_ops():
            rsrc = self._rasterized_source(src)
            if rsrc is not None:
                data2, byte_hash2 = self._byte_stage(rsrc, layer, doc.seed)
                img2, ok2 = self._decode_stage(data2, byte_hash2, rsrc)
                if ok2:
                    img, ok, byte_hash = img2, True, byte_hash2
        img = self._pixel_stage(img, byte_hash, layer, doc.seed, max_dim)
        img = _resize_to(img, target)
        return img, ok

    def render(self, doc: Document, max_dim: Optional[int] = None) -> tuple[Optional[np.ndarray], bool]:
        """Render the whole document. Returns ``(rgba_uint8, all_layers_decoded_ok)``."""
        cw, ch = doc.canvas_size()
        if cw <= 0 or ch <= 0:
            return None, False
        if max_dim is not None and max(cw, ch) > max_dim:
            scale = max_dim / max(cw, ch)
            target = (max(1, int(cw * scale)), max(1, int(ch * scale)))
        else:
            target = (cw, ch)

        buffers: list[tuple[np.ndarray, str, float, Optional[np.ndarray]]] = []
        all_ok = True
        for layer in doc.layers:
            if not layer.visible:
                continue
            buf, ok = self.render_layer(doc, layer, target, max_dim)
            all_ok = all_ok and ok
            buffers.append((buf, layer.blend, layer.opacity, None))
        if not buffers:
            return None, all_ok
        return composite(buffers), all_ok


# ── resize helpers (cv2 fast path, numpy fallback) ──────────────────────────────

def _downscale(img: np.ndarray, max_dim: int) -> np.ndarray:
    h, w = img.shape[:2]
    if max(h, w) <= max_dim:
        return img
    scale = max_dim / max(h, w)
    return _resize_to(img, (max(1, int(w * scale)), max(1, int(h * scale))))


def _resize_to(img: np.ndarray, target: tuple[int, int]) -> np.ndarray:
    tw, th = target
    h, w = img.shape[:2]
    if (w, h) == (tw, th):
        return img
    if cv2 is not None:
        interp = cv2.INTER_AREA if (tw * th) < (w * h) else cv2.INTER_NEAREST
        return cv2.resize(img, (tw, th), interpolation=interp)
    # numpy nearest-neighbour fallback
    ys = (np.linspace(0, h - 1, th)).astype(np.int64)
    xs = (np.linspace(0, w - 1, tw)).astype(np.int64)
    return img[ys][:, xs]
