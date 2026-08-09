"""Rule-agnostic canonicalization engine and differential test rig."""

from .engine import Canonicalizer, load_json
from .ruleset import ABSENT, CanonicalizationError, Ruleset

__all__ = ["Canonicalizer", "load_json", "Ruleset", "ABSENT", "CanonicalizationError"]
__version__ = "0.1.0"
