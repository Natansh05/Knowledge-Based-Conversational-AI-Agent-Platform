# rag.processors.embeddings.py
from functools import lru_cache
from documents.models import DocumentChunk
from celery import group

# Single source of truth for the embedding model. Stored on semantic cache
# entries so that a model swap (different vector space / dimensions) never
# matches stale embeddings. If you change this, also update the VectorField
# dimensions on DocumentChunk / SemanticCacheEntry and re-embed.
EMBEDDING_MODEL_NAME = "all-mpnet-base-v2"


@lru_cache(maxsize=1)
def get_embedding_model():
    """
    Loaded lazily (not at import time) so the model is instantiated inside
    each Celery worker process after fork(), not in the master before it.
    Loading torch-backed models before fork() crashes forked children on
    macOS (torch/objc thread-init vs fork() incompatibility).
    """
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL_NAME)

BLOCKED_PATTERNS = [
    "write code",
    "generate code",
    "python code",
    "tell a joke",
    "make a story",
    "weather",
    "movie recommendation",
    "solve this",
    "translate this",
]


def is_query_allowed(query: str) -> bool:
    q = query.lower()

    for pattern in BLOCKED_PATTERNS:
        if pattern in q:
            return False

    return True

def generate_embeddings(texts):

    embeddings = get_embedding_model().encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True
    )
    return embeddings.tolist()

BATCH_SIZE=64
def embed_document_chunks(document=None, schema_name=None):
    chunk_ids = DocumentChunk.objects.filter(
        document=document,
    ).values_list("id", flat=True)
    from documents.tasks import embed_chunk_batch

    bacthes = [
        chunk_ids[i:i+BATCH_SIZE]
        for i in range(0, len(chunk_ids), BATCH_SIZE)
    ]

    group(
        embed_chunk_batch.s(list(batch), schema_name)
        for batch in bacthes
    ).apply_async()