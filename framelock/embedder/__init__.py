"""Embedding backends. Import the one you want; they share a common interface."""

from .base import Embedder
from .clip import ClipEmbedder

__all__ = ["Embedder", "ClipEmbedder"]
