# rag.processors.semantic_cache
"""
pgvector-backed semantic cache for agent answers.

Unlike the old exact-match Redis cache, a lookup matches any prior question
whose embedding is within a strict cosine distance of the incoming query, so
rewordings of the same question hit the cache. Entries live in the tenant schema
(SemanticCacheEntry is a TENANT_APP model), so they are isolated per organization.

All operations are defensive: a cache failure must never break answering, so
lookups return None and stores swallow errors.
"""
import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from pgvector.django import CosineDistance

from agent.models import SemanticCacheEntry
from rag.processors.embeddings import EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)


def _threshold():
    return getattr(settings, "SEMANTIC_CACHE_DISTANCE_THRESHOLD", 0.08)


def _ttl_seconds():
    return getattr(settings, "SEMANTIC_CACHE_TTL", 1800)


def _enabled():
    return getattr(settings, "SEMANTIC_CACHE_ENABLED", True)


def compute_knowledge_version(agent):
    """
    A content-based fingerprint of the agent's current document set: the id and
    version of each attached document. Changes when a document is added or
    removed (id set changes) or when a document's content changes (version
    bumps). Used to invalidate cached answers derived from older knowledge.

    NOTE: this relies on Document.version being incremented whenever a document's
    content is replaced/re-embedded. See update_document / process_document.
    """
    rows = (
        agent.documents
        .order_by("id")
        .values_list("id", "version")
    )
    raw = ";".join(f"{doc_id}:{version}" for doc_id, version in rows)
    return hashlib.md5(raw.encode()).hexdigest()


def lookup(agent, query_embedding, knowledge_version=None):
    """
    Return the cached response dict for the nearest matching entry, or None.
    A match must be non-expired, from the current embedding model, derived from
    the agent's current document version, and within the distance threshold.
    Bumps hit bookkeeping on a hit.

    Pass `knowledge_version` to reuse a value already computed this request (see
    compute_knowledge_version); it is derived from the agent's documents when
    omitted.
    """
    if not _enabled():
        return None

    if knowledge_version is None:
        knowledge_version = compute_knowledge_version(agent)

    try:
        entry = (
            SemanticCacheEntry.objects
            .filter(
                agent=agent,
                expires_at__gt=timezone.now(),
                embedding_model=EMBEDDING_MODEL_NAME,
                knowledge_version=knowledge_version,
            )
            .annotate(distance=CosineDistance("query_embedding", query_embedding))
            .order_by("distance")
            .first()
        )

        if entry is None or entry.distance > _threshold():
            return None

        # Best-effort hit bookkeeping — don't let it fail the lookup.
        try:
            entry.hit_count = (entry.hit_count or 0) + 1
            entry.last_hit_at = timezone.now()
            entry.save(update_fields=["hit_count", "last_hit_at"])
        except Exception as e:
            logger.warning("semantic_cache hit bookkeeping failed: %s", e)

        return entry.response
    except Exception as e:
        logger.warning("semantic_cache lookup failed: %s", e)
        return None


def store(agent, query, query_embedding, response, knowledge_version=None):
    """
    Persist a response under the given query embedding, and opportunistically
    purge this agent's expired entries. Never raises.

    Pass `knowledge_version` to reuse a value already computed this request;
    it is derived from the agent's documents when omitted.
    """
    if not _enabled():
        return

    if knowledge_version is None:
        knowledge_version = compute_knowledge_version(agent)

    try:
        SemanticCacheEntry.objects.create(
            agent=agent,
            query=query,
            query_embedding=query_embedding,
            response=response,
            knowledge_version=knowledge_version,
            embedding_model=EMBEDDING_MODEL_NAME,
            expires_at=timezone.now() + timedelta(seconds=_ttl_seconds()),
        )

        # Opportunistic cleanup so expired rows don't accumulate without a
        # scheduled job (there is no Celery beat configured yet).
        SemanticCacheEntry.objects.filter(
            agent=agent, expires_at__lte=timezone.now()
        ).delete()
    except Exception as e:
        logger.warning("semantic_cache store failed: %s", e)
