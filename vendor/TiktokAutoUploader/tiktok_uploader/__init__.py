"""TikTok uploader package.

Keep imports lightweight so local-file uploads do not require the optional
MoviePy/Pytube editing stack or start browser-related modules eagerly.
"""

from . import tiktok
from .Config import Config
from .basics import eprint

__all__ = ["Config", "eprint", "tiktok"]
