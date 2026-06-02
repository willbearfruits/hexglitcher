"""HexGlitcher v3 — non-destructive, layered, realtime image databending.

Architecture in one breath:
  * A :class:`~hexglitcher.engine.document.Document` is an ordered list of
    compositing :class:`~hexglitcher.engine.layer.Layer` objects (bottom→top).
  * Each layer references a source image and carries a non-destructive *op-stack*.
  * Operations live in two domains split at a single DECODE boundary:
    ``BYTE`` ops mangle the raw file bytes (pre-decode); ``PIXEL`` ops transform
    the decoded image (post-decode). See :mod:`hexglitcher.engine.operation`.
  * The :mod:`hexglitcher.engine.pipeline` renders a document with prefix-caching
    (editing op *i* only recomputes from *i* onward) and composites the layers.

Nothing here mutates a loaded file; the original bytes are immutable and the
whole document is a recipe applied on demand.
"""

__version__ = "3.0.0a0"
