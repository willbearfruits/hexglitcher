"""Built-in operation library.

Importing a submodule registers its ops into ``OP_REGISTRY`` via the
``@register_op`` decorator. :func:`register_builtin_ops` triggers all imports
once and is idempotent, so call it during startup before building a document.
"""
from __future__ import annotations

_REGISTERED = False


def register_builtin_ops() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    # importing each module runs its @register_op decorators
    from . import byte_ops  # noqa: F401
    from . import audio_ops  # noqa: F401
    from . import inject_ops  # noqa: F401
    from . import format_ops  # noqa: F401
    from . import pixel_ops  # noqa: F401
    _REGISTERED = True


def ops_by_category() -> dict[str, list]:
    """Grouped {category: [OpType,...]} for building the add-op palette."""
    register_builtin_ops()
    from ..engine.operation import OP_REGISTRY
    out: dict[str, list] = {}
    for ot in OP_REGISTRY.values():
        out.setdefault(ot.category, []).append(ot)
    for v in out.values():
        v.sort(key=lambda o: o.label)
    return dict(sorted(out.items()))
