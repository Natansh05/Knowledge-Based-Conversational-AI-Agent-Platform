from django.db import models
from users.models import User
from pgvector.django import VectorField, HnswIndex
# Create your models here.
class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    

class Agent(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    system_prompt = models.TextField()

    documents = models.ManyToManyField(
        "documents.Document",
        related_name="agents",
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE
    )

    tags = models.ManyToManyField(
        "Tag",
        related_name="agents",
        blank=True
    )

    is_active = models.BooleanField(
        default=True
    )


class SemanticCacheEntry(models.Model):
    """
    A cached agent response keyed by the embedding of a self-contained query.

    Lives in the tenant schema (agent is a TENANT_APP), so entries are naturally
    isolated per organization. Lookups do an approximate-nearest-neighbour search
    over `query_embedding` (HNSW / cosine) and treat a hit as valid only when the
    nearest entry is within a strict distance threshold (see rag.processors.
    semantic_cache). Entries carry an explicit `expires_at` because pgvector rows
    do not auto-expire like Redis keys.
    """
    agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name="cache_entries",
    )
    # The transformed, self-contained query used as the cache key (for debugging
    # / inspection; matching is done on the embedding, not this text).
    query = models.TextField()
    query_embedding = VectorField(dimensions=768)
    # Stored response payload: {"answer": str, "chunk_ids": [...], "chunk_scores": [...]}
    response = models.JSONField()
    # Fingerprint of the agent's documents (ids + versions + last_modified) at the
    # time this answer was cached. A lookup only accepts entries whose version
    # matches the agent's CURRENT documents, so updating/adding/removing a document
    # transparently invalidates answers derived from the old knowledge.
    knowledge_version = models.CharField(max_length=64, db_index=True)
    # Embedding model that produced query_embedding. A lookup only accepts entries
    # from the current model, so swapping models never matches a stale vector space.
    embedding_model = models.CharField(max_length=128)
    hit_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_hit_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["agent"], name="sem_cache_agent_idx"),
            HnswIndex(
                name="sem_cache_emb_hnsw_idx",
                fields=["query_embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self):
        return f"SemanticCacheEntry(agent={self.agent_id}, query={self.query[:40]!r})"
