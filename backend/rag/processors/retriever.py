# rag.processors.retriever
from functools import lru_cache
from pgvector.django import CosineDistance
from documents.models import DocumentChunk
from agent.models import Agent
from rag.processors.embeddings import generate_embeddings
from chat.models import ChatMessage
from scipy.special import expit

AVG_SIMILARITY_THRESHOLD = 0.3         # "low" boundary
TOP_SIMILARITY_THRESHOLD = 0.6         # "high" zone entry
MIN_CHUNK_SCORE = 0.3                  # filter floor
VERY_HIGH_THRESHOLD = 0.72             # above this, always "high", never "ambiguous"
AMBIGUITY_GAP_THRESHOLD = 0.05         # replaces hardcoded 0.05 — needs a meaningful gap
AMBIGUITY_SECOND_SCORE_MIN = 0.45      # second chunk must be meaningfully high to trigger ambiguous
PARTIAL_GRAY_ZONE_MIN = 0.42           # lower bound for partial-zone ambiguity
PARTIAL_GRAY_ZONE_MAX = 0.60           # upper bound for partial-zone ambiguity


@lru_cache(maxsize=1)
def get_reranker():
    from sentence_transformers import CrossEncoder
    return CrossEncoder('cross-encoder/ms-marco-MiniLM-L-12-v2')


def retrieve_chunks(query, agent, top_k=5, rerank_top_n=20):

    query_embedding = generate_embeddings([query])[0]
    agent_docs = agent.documents.values_list("id",flat=True)
    # print(agent_docs)
    results = (
            DocumentChunk.objects
            .filter(document_id__in=agent_docs)
            .exclude(embedding__isnull=True)
            .annotate(distance=CosineDistance("embedding", query_embedding))
            .order_by("distance")
            .distinct()[:rerank_top_n]
    )

    results = list(results)
    if not results:
        return {
            "status": "low",
            "top_score": 0.0,
            "avg_score": 0.0,
            "chunks": [],
            "chunk_ids": [],
            "chunk_scores": [],
        }
    
    # Rerank with cross encoder
    pairs = [(query, c.text) for c in results]
    scores = get_reranker().predict(pairs)
    norm_scores = expit(scores)  # Convert to 0-1 range

    top_score = norm_scores.max() if len(norm_scores) else 0
    avg_score = norm_scores.mean() if len(norm_scores) else 0

    # sort by reranker score descending
    # reranked_chunks = [chunk for _,chunk in sorted(zip(scores, results), reverse=True)]

    sorted_scores = sorted(norm_scores, reverse=True)

    if len(sorted_scores) > 1:
        score_gap = sorted_scores[0] - sorted_scores[1]
        second_score = sorted_scores[1]
    else:
        # Single chunk: no competitor, so no ambiguity possible
        score_gap = sorted_scores[0]
        second_score = 0.0

    top_score = sorted_scores[0]

    if top_score > VERY_HIGH_THRESHOLD:
        # Very high confidence: always answer, never ambiguous.
        # Two overlapping chunks both scoring above this threshold means the
        # document clearly covers this query — a small gap is just natural
        # variance from chunk overlap, not a sign of ambiguity.
        status = "high"

    elif top_score > TOP_SIMILARITY_THRESHOLD:
        # Moderate-high zone (0.60–0.72): only ambiguous if both the gap is
        # small AND the second chunk is itself meaningfully high — indicating
        # two genuinely competing chunks rather than one clear leader.
        if score_gap < AMBIGUITY_GAP_THRESHOLD and second_score > AMBIGUITY_SECOND_SCORE_MIN:
            status = "ambiguous"
        else:
            status = "high"

    elif avg_score < AVG_SIMILARITY_THRESHOLD:
        # Average score too low — document set has no meaningful coverage.
        status = "low"

    else:
        # Partial zone (avg >= 0.30, top_score 0.30–0.60): only ambiguous if
        # both top and second scores are in the gray zone AND gap is small,
        # indicating the query genuinely matches two different sub-topics.
        in_gray_zone = PARTIAL_GRAY_ZONE_MIN < top_score < PARTIAL_GRAY_ZONE_MAX
        second_in_gray_zone = PARTIAL_GRAY_ZONE_MIN < second_score < PARTIAL_GRAY_ZONE_MAX
        if in_gray_zone and second_in_gray_zone and score_gap < AMBIGUITY_GAP_THRESHOLD:
            status = "ambiguous"
        else:
            status = "partial"

    scored_chunks = sorted(zip(norm_scores, results), key=lambda x: x[0], reverse=True)

    reranked_chunks = [chunk for score, chunk in scored_chunks]
    sorted_scores = [score for score, chunk in scored_chunks]

    if top_score > 0.7:
        top_k = 2
    elif top_score > 0.5:
        top_k = 4
    else:
        top_k = 0

    # Filter and select from already-sorted score-chunk pairs (fixes score/chunk alignment)
    filtered_pairs = [
        (score, chunk)
        for score, chunk in scored_chunks
        if score >= MIN_CHUNK_SCORE
    ]
    selected_pairs = filtered_pairs[:top_k]

    return {
        "status": status,
        "top_score": float(top_score),
        "avg_score": float(avg_score),
        "chunks": [chunk for _, chunk in selected_pairs],
        "chunk_ids": [chunk.id for _, chunk in selected_pairs],
        "chunk_scores": [float(score) for score, _ in selected_pairs],
    }

def get_history(chat):
    messages = ChatMessage.objects.filter(
        chat_session=chat
    ).order_by("created_at")
    messages = messages[:6][::-1]

    history = []
    for msg in messages:
        role = "model" if msg.role == "assistant" else "user"

        history.append({
            "role": role,
            "content": msg.content
        })
    return history

def format_history(history):
    lines = []
    for msg in history:
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)