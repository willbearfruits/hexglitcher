"""The operation model: domains, parameter specs, the registry, and instances.

An :class:`OpType` is the *static definition* of a kind of operation, registered
once at import time. An :class:`Operation` is a *parameterized instance* sitting
in a layer's op-stack. Operations belong to one of two :class:`OpDomain` values:

* ``BYTE``  — runs before decode, transforms the raw file bytes (region-scoped).
* ``PIXEL`` — runs after decode, transforms the decoded RGBA image (numpy array).

The decode step that separates the two domains is implicit in the pipeline; it is
not itself an operation in the stack.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional

import numpy as np

if TYPE_CHECKING:  # avoid import cycles; these are only type hints
    from ..formats.base import FormatBackend


class OpDomain(Enum):
    BYTE = "byte"
    PIXEL = "pixel"


# ── Parameter specification ────────────────────────────────────────────────────
# A ParamSpec drives both validation and (later) automatic widget generation in
# the params panel, so a new op gets a UI for free.

# kinds: "int" | "float" | "bool" | "choice" | "hex" | "seed" | "filepath" | "text"

@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    kind: str
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    choices: Optional[tuple] = None
    help: str = ""

    def clamp(self, value: Any) -> Any:
        if self.kind in ("int", "float", "seed") and value is not None:
            if self.min is not None:
                value = max(self.min, value)
            if self.max is not None:
                value = min(self.max, value)
            if self.kind in ("int", "seed"):
                value = int(value)
            else:
                value = float(value)
        return value


# ── Operation contexts ─────────────────────────────────────────────────────────
# Passed to an op's apply() so it has everything it needs without reaching into
# globals. Kept tiny and copyable.

@dataclass
class ByteContext:
    rng: np.random.Generator
    fmt: "FormatBackend"
    region: tuple[int, int]          # (start, end) absolute, resolved & clamped
    total_size: int                  # length of the full byte buffer
    load_external: Callable[[str], bytes] = lambda p: b""


@dataclass
class PixelContext:
    rng: np.random.Generator
    proxy: bool = False              # True when rendering a fast downscaled preview


# apply signatures (by domain):
#   BYTE:  fn(region: bytearray, params: dict, ctx: ByteContext) -> bytes | bytearray | None
#          (return new region bytes, or None to mutate `region` in place; length may change)
#   PIXEL: fn(img: np.ndarray, params: dict, ctx: PixelContext) -> np.ndarray
#          (img is HxWx4 uint8 RGBA; return the transformed array)
ApplyFn = Callable[..., Any]


@dataclass
class OpType:
    """Static, registered definition of an operation kind."""
    type_id: str
    label: str
    domain: OpDomain
    category: str
    params: tuple[ParamSpec, ...]
    apply: ApplyFn
    help: str = ""
    randomizable: bool = False       # has a 'seed' param worth re-rolling

    def default_params(self) -> dict:
        return {p.key: p.default for p in self.params}

    def spec(self, key: str) -> Optional[ParamSpec]:
        for p in self.params:
            if p.key == key:
                return p
        return None


# ── Registry ─────────────────────────────────────────────────────────────────

OP_REGISTRY: dict[str, OpType] = {}


def register_op(
    type_id: str,
    label: str,
    domain: OpDomain,
    category: str,
    params: tuple[ParamSpec, ...] = (),
    help: str = "",
    randomizable: bool = False,
) -> Callable[[ApplyFn], ApplyFn]:
    """Decorator registering an op's apply function as a new :class:`OpType`."""
    def deco(fn: ApplyFn) -> ApplyFn:
        if type_id in OP_REGISTRY:
            raise ValueError(f"duplicate op type_id: {type_id!r}")
        OP_REGISTRY[type_id] = OpType(
            type_id=type_id, label=label, domain=domain, category=category,
            params=tuple(params), apply=fn, help=help, randomizable=randomizable,
        )
        return fn
    return deco


def get_optype(type_id: str) -> OpType:
    return OP_REGISTRY[type_id]


# ── Operation instance ─────────────────────────────────────────────────────────

@dataclass
class Operation:
    """A parameterized op sitting in a layer's stack (non-destructive)."""
    type_id: str
    params: dict = field(default_factory=dict)
    enabled: bool = True
    # Byte-domain only: (start, end) byte offsets to act on. None = whole body
    # (the format's safe zone between header and footer). Values may be negative
    # to count from EOF, or fractional floats in [0,1] for proportional offsets.
    region: Optional[tuple] = None
    name: str = ""
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        # Fill any missing params with defaults; drop unknown keys.
        ot = self.optype
        merged = ot.default_params()
        for k, v in self.params.items():
            if k in merged:
                spec = ot.spec(k)
                merged[k] = spec.clamp(v) if spec else v
        self.params = merged

    @property
    def optype(self) -> OpType:
        return OP_REGISTRY[self.type_id]

    @property
    def domain(self) -> OpDomain:
        return self.optype.domain

    def display_name(self) -> str:
        return self.name or self.optype.label

    def identity(self) -> tuple:
        """Everything that affects this op's output — folded into the cache hash."""
        return (self.type_id, self.params, self.region)

    # serialization ----------------------------------------------------------
    def to_dict(self) -> dict:
        d = {"type_id": self.type_id, "params": self.params, "enabled": self.enabled}
        if self.region is not None:
            d["region"] = list(self.region)
        if self.name:
            d["name"] = self.name
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Operation":
        region = d.get("region")
        return cls(
            type_id=d["type_id"],
            params=dict(d.get("params", {})),
            enabled=bool(d.get("enabled", True)),
            region=tuple(region) if region is not None else None,
            name=d.get("name", ""),
        )
