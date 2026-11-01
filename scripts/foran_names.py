# -*- coding: utf-8 -*-
"""FORAN filename rules.

FORAN derives the extension from the *first* dot.  A name such as
``model_v1.0_work.fsf`` is therefore read as ``.0_work.fsf`` and rejected
with ``DsgAuxFileReader ERROR : Unknown file extension``.

Keep every FORAN-facing file name to letters/digits/underscore/hyphen and
exactly one dot (the extension).  Use these helpers instead of repeating the
sanitising rule in each module.
"""
from __future__ import annotations

from pathlib import Path


def foran_safe_stem(stem: str) -> str:
    """Replace anything that is not alphanumeric, '-' or '_' with '_'."""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in stem)


def foran_safe_filename(filename: str) -> str:
    """Sanitise the stem and keep the final extension.

    ``SN..._v1.0_....fsf`` -> ``SN..._v1_0_....fsf``
    """
    p = Path(filename)
    return foran_safe_stem(p.stem) + p.suffix


def has_extra_dots(filename: str) -> bool:
    """True when the basename has more than one dot (FORAN will misparse)."""
    return Path(filename).name.count(".") > 1


def suggest_foran_name(filename: str) -> str:
    """A safe replacement name for a bad FORAN file name."""
    return foran_safe_filename(filename)
