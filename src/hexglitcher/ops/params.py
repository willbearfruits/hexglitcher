"""Convenience constructors for :class:`ParamSpec` so op definitions stay terse."""
from __future__ import annotations

from typing import Sequence

from ..engine.operation import ParamSpec


def p_int(key, label, default, lo, hi, step=1, help="") -> ParamSpec:
    return ParamSpec(key, label, "int", default, lo, hi, step, None, help)


def p_float(key, label, default, lo, hi, step=0.01, help="") -> ParamSpec:
    return ParamSpec(key, label, "float", default, lo, hi, step, None, help)


def p_bool(key, label, default, help="") -> ParamSpec:
    return ParamSpec(key, label, "bool", default, None, None, None, None, help)


def p_choice(key, label, default, choices: Sequence[str], help="") -> ParamSpec:
    return ParamSpec(key, label, "choice", default, None, None, None, tuple(choices), help)


def p_seed(key="seed", label="Seed", default=0, help="Fixed seed for reproducible randomness") -> ParamSpec:
    return ParamSpec(key, label, "seed", default, 0, 2_147_483_647, 1, None, help)


def p_filepath(key, label, default="", help="") -> ParamSpec:
    return ParamSpec(key, label, "filepath", default, None, None, None, None, help)
