"""
store.py — the Qdrant FINGERPRINT STORE (Phase 2).

Stores fingerprints as vectors in Qdrant and answers "which registered frame is
closest to this one?" in milliseconds. Each FrameSignature becomes one Qdrant
*point*: a vector + a payload (work_id, timestamp, source_uri) that turns a bare
similarity hit into a meaningful "your content X appears at 00:47".

We use Qdrant's embedded local mode by default (no server needed). To use a real
Qdrant server instead, pass `client=QdrantClient(url="http://localhost:6333")`
— nothing else changes. That swap is the whole point of taking a client in.
"""

from __future__ import annotations

import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from .schema import Fingerprint

# Namespace for deterministic point ids (so re-registering a work overwrites its
# old points instead of duplicating them — idempotent upserts).
_NS = uuid.UUID("00000000-0000-0000-0000-00000000f00d")


class FingerprintStore:
    def __init__(
        self,
        dim: int,
        embedder_name: str,
        client: QdrantClient | None = None,
        location: str = "qdrant_data",
        collection: str = "fingerprints",
    ):
        # No client passed -> embedded local Qdrant persisted to `location`.
        self.client = client or QdrantClient(path=location)
        self.collection = collection
        self.dim = dim
        self.embedder_name = embedder_name
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create the collection once, sized to the embedder's vector dim."""
        names = [c.name for c in self.client.get_collections().collections]
        if self.collection not in names:
            self.client.create_collection(
                self.collection,
                # size MUST equal the embedder's dim; distance MUST match how the
                # vectors were normalized. CLIP vectors are L2-normalized -> Cosine.
                vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
            )

    def register(self, fp: Fingerprint) -> int:
        """Upsert every frame of a fingerprint as a point. Returns count."""
        points = []
        for seq, sig in enumerate(fp.frames):
            # Deterministic id from (work_id, seq) => re-registering is idempotent.
            point_id = str(uuid.uuid5(_NS, f"{fp.work_id}:{seq}"))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=sig.embedding,
                    payload={
                        "work_id": fp.work_id,
                        "timestamp": sig.timestamp,
                        "source_uri": fp.source_uri,
                        "embedder": self.embedder_name,  # guard: never mix spaces
                    },
                )
            )
        self.client.upsert(self.collection, points=points)
        return len(points)

    def search(self, vector: list[float], top_k: int = 5) -> list[dict]:
        """Return the top_k nearest stored frames to `vector`, with scores."""
        result = self.client.query_points(
            self.collection,
            query=vector,
            limit=top_k,
            with_payload=True,
        )
        return [
            {"score": p.score, **p.payload}
            for p in result.points
        ]
