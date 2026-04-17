# rag.processors.embeddings.py
from sentence_transformers import SentenceTransformer
from documents.models import DocumentChunk
# model = SentenceTransformer("all-MiniLM-L6-v2")
model = SentenceTransformer("all-mpnet-base-v2")
from celery import group

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

    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True
    )
    return embeddings.tolist()

BATCH_SIZE=64
def embed_document_chunks(document=None):
    chunk_ids = DocumentChunk.objects.filter(
        document=document,
    ).values_list("id", flat=True)
    from documents.tasks import embed_chunk_batch

    bacthes = [
        chunk_ids[i:i+BATCH_SIZE]
        for i in range(0, len(chunk_ids), BATCH_SIZE)
    ]

    group(
        embed_chunk_batch.s(batch)
        for batch in bacthes
    ).apply_async()