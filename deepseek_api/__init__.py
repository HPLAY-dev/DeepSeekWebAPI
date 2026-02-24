"""
DeepSeek API Python 3

Unofficial wrapper of DeepSeek Web API
"""

from .api import DeepSeekAPI, DeepSeekHashV1Solver
from .utils import parse_completion

__version__ = "1.0.0"
__all__ = ["DeepSeekAPI", "DeepSeekHashV1Solver", "parse_completion"]