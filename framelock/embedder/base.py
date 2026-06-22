"""
base.py — the EMBEDDER PORT (hexagonal / port-adapter boundary).

This is the ONE place that defines what "an embedder" means to the rest of
FrameLock. Every backend (local CLIP today, Gemini/Vertex later) implements this
exact interface, so the matching code never knows or cares which model produced
a vector. Swapping backends = swapping which class you instantiate; nothing
downstream changes.

Same move as your AgentVCR ModelAdapter and your ZenoHosp Finance GL port.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Embedder(ABC):
    """A backend that turns an image (JPEG bytes) into a vector."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short id of the backend+model, e.g. 'clip-ViT-B-32'.

        Stored alongside vectors so we never accidentally compare vectors from
        two different models (their spaces are incompatible — a CLIP vector and
        a Gemini vector are not comparable even if both are 'similarity 0.9').
        """

    @property
    @abstractmethod
    def dim(self) -> int:
        """The vector length this backend produces (e.g. 512 for CLIP).

        Qdrant must be told the exact dimension when a collection is created,
        so the backend has to advertise it up front.
        """

    @abstractmethod
    def embed_image(self, jpeg_bytes: bytes) -> list[float]:
        """Embed ONE frame. Returns an L2-normalized vector as a plain list.

        We normalize (length = 1) so cosine similarity reduces to a dot product,
        which is what Qdrant computes fastest. Returning a plain list (not a
        numpy array) keeps this layer dependency-free for callers.
        """

    def embed_images(self, jpegs: list[bytes]) -> list[list[float]]:
        """Embed many frames. Default = loop; backends may override for batching.

        A real model call has fixed per-request overhead, so batching N images in
        one call is far faster than N calls. CLIP/Gemini both support it, so this
        default exists only as a correct fallback.
        """
        return [self.embed_image(j) for j in jpegs]
