"""Optional Numba acceleration for the hot pixel-op kernels.

Pixel sort is a per-row, span-wise sort — a Python loop that dominates CPU time
on large frames/video. When Numba is available we JIT a tight kernel (10–50×);
otherwise callers fall back to their pure-numpy path. ``cache=True`` persists the
compiled kernel to disk so only the very first run pays the compile cost.
"""
from __future__ import annotations

import numpy as np

try:
    from numba import njit
    HAVE_NUMBA = True
except Exception:  # pragma: no cover
    HAVE_NUMBA = False


if HAVE_NUMBA:

    @njit(cache=True, nogil=True)
    def sort_spans(work, key, mask, reverse):  # noqa: ANN001
        """In-place: within each masked run of a row, sort pixels by `key`."""
        H, W, C = work.shape
        for y in range(H):
            x = 0
            while x < W:
                if not mask[y, x]:
                    x += 1
                    continue
                a = x
                while x < W and mask[y, x]:
                    x += 1
                b = x
                m = b - a
                if m > 1:
                    order = np.argsort(key[y, a:b])
                    tmp = np.empty((m, C), np.uint8)
                    for k in range(m):
                        idx = order[m - 1 - k] if reverse else order[k]
                        for c in range(C):
                            tmp[k, c] = work[y, a + idx, c]
                    for k in range(m):
                        for c in range(C):
                            work[y, a + k, c] = tmp[k, c]
        return work
