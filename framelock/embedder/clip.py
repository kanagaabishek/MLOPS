"""
clip.py — the CLIP EMBEDDER ADAPTER (local, free, offline).

Implements the Embedder port (base.py) using OpenAI's CLIP model
(clip-vit-base-patch32) via HuggingFace transformers. One frame (JPEG bytes) ->
one 512-dim vector in CLIP's shared image/text space. No API key, no billing,
runs on CPU.

This mirrors the `local` backend in the real FrameLock repo
(server/src/embedding_service.py). It satisfies the same interface as any other
embedder, so the matching/storage code never imports this file directly.
"""

from __future__ import annotations

import io

from .base import Embedder

MODEL_NAME = "openai/clip-vit-base-patch32"


class ClipEmbedder(Embedder):
    def __init__(self, model_name: str = MODEL_NAME):
        # Heavy deps (torch, transformers, PIL) are imported lazily so the rest
        # of FrameLock (e.g. the Phase 1 extractor) runs without them installed.
        import torch
        from transformers import CLIPModel, CLIPProcessor

        self._torch = torch
        # Apple Silicon has an "mps" GPU backend; fall back to CPU otherwise.
        self._device = "mps" if torch.backends.mps.is_available() else "cpu"

        self._model = CLIPModel.from_pretrained(model_name).to(self._device)
        self._processor = CLIPProcessor.from_pretrained(model_name)
        self._model.eval()  # inference mode — disables dropout/training behavior

    @property
    def name(self) -> str:
        return "clip-vit-base-patch32"

    @property
    def dim(self) -> int:
        return 512  # CLIP ViT-B/32 produces 512-dimensional vectors

    def embed_image(self, jpeg_bytes: bytes) -> list[float]:
        from PIL import Image

        image = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")

        # The processor resizes/normalizes the image into the tensor CLIP expects.
        inputs = self._processor(images=image, return_tensors="pt").to(self._device)

        # no_grad: we're only running inference, so don't track gradients (faster,
        # less memory). get_image_features runs the vision tower -> one vector.
        with self._torch.no_grad():
            features = self._model.get_image_features(**inputs)

        # L2-normalize so cosine similarity == dot product (what Qdrant wants).
        features = features / features.norm(dim=-1, keepdim=True)

        # Tensor -> flat Python list of floats (keeps callers dependency-free).
        return features.cpu().numpy().flatten().tolist()
