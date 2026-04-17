# rag.processors.retriever
from pgvector.django import CosineDistance
from documents.models import DocumentChunk
from agent.models import Agent
from rag.processors.embeddings import generate_embeddings
from chat.models import ChatMessage
from sentence_transformers import CrossEncoder
from scipy.special import expit

AVG_SIMILARITY_THRESHOLD = 0.3
TOP_SIMILARITY_THRESHOLD = 0.6
MIN_CHUNK_SCORE = 0.3
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-12-v2')
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
    scores = reranker.predict(pairs)
    norm_scores = expit(scores)  # Convert to 0-1 range

    top_score = norm_scores.max() if len(norm_scores) else 0
    avg_score = norm_scores.mean() if len(norm_scores) else 0

    # sort by reranker score descending
    # reranked_chunks = [chunk for _,chunk in sorted(zip(scores, results), reverse=True)]

    if top_score > TOP_SIMILARITY_THRESHOLD:
        status = "high"
    elif avg_score < AVG_SIMILARITY_THRESHOLD:
        status = "low"
    else:
        status = "partial"

    sorted_scores = sorted(norm_scores, reverse=True)

    # wE CAN LOOK FOR AMIBIGUITY BY CHECKING SCORE GAP WHEN CHUKS ARE DISTRIBUTED AROUND THE TOPIC
    # HERE IN CASE OF RECURSIVE CHUNKING, CHUNK SCORES CAN BE OVERLAPPING
    # NEEDS TO DEPEND ON CHUNKING STRATEGY AND VECTOR DB PERFORMANCE


    if len(sorted_scores) > 1:
        score_gap = sorted_scores[0] - sorted_scores[1]
    else:
        score_gap = sorted_scores[0]

    top_score = sorted_scores[0]

    if top_score > TOP_SIMILARITY_THRESHOLD:
        if score_gap < 0.05:
            status = "ambiguous"
        else:
            status = "high"

    elif avg_score < AVG_SIMILARITY_THRESHOLD:
        status = "low"

    elif score_gap < 0.05:
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