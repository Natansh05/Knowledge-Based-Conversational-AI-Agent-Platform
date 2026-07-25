# evaluation.dataset.builder
"""
Golden-set construction from a tenant's own ingested documents.

Deliberately not Ragas' TestsetGenerator: that builds its own knowledge graph and
emits question/answer/context text, whereas the ranking metrics need *graded
chunk-level labels* tied to this corpus.

The label-completion step is the part that matters most for metric validity. If
each question were labelled only with the chunk it was generated from, every
query would have exactly one relevant chunk and Recall@k would be systematically
overstated — the retriever would be penalised for surfacing a chunk that does
answer the question but happens not to be the seed. So after generation each
question is scored against the corpus and near-misses are labelled as supporting
evidence.

Known bias, recorded here because it must reach the report: those completion
labels come from the same cross-encoder the pipeline uses to rerank, so retrieval
metrics are mildly flattering to that reranker. Removing the bias requires an LLM
adjudication pass over every candidate, which costs roughly a day.
"""
import json
import logging
import random
import time

from rag.llm.base import GeminiProvider
from rag.processors.embeddings import BLOCKED_PATTERNS, generate_embeddings
from rag.processors.retriever import _fetch_candidates, get_reranker

from evaluation.dataset.schema import (
    GRADE_ANSWERS,
    GRADE_SUPPORTING,
    ChunkLabel,
    GoldenRecord,
)

logger = logging.getLogger(__name__)

# Cross-encoder score above which a non-seed chunk is labelled supporting.
# Intentionally *not* the pipeline's MIN_CHUNK_SCORE: reusing the system's own
# filter threshold to build its ground truth would make the evaluation partly
# circular.
DEFAULT_LABEL_THRESHOLD = 0.5

# Seed chunks shorter than this rarely contain a self-contained fact worth
# asking about, and produce degenerate questions.
MIN_SEED_CHARS = 250


def _blocked(question):
    """
    True if the guardrail would reject this question before retrieval runs.

    `is_query_allowed` is a bare substring blocklist containing common words such
    as "weather" and "solve this". A generated question tripping it short-circuits
    to the fallback LLM and never reaches retrieval, so it would sit in the golden
    set as a permanent, unfixable retrieval failure unrelated to retrieval quality.
    """
    lowered = question.lower()
    return any(pattern in lowered for pattern in BLOCKED_PATTERNS)


def sample_seed_chunks(agent, n, rng):
    """
    Sample chunks round-robin across documents so one large document cannot
    dominate the question set.
    """
    from documents.models import DocumentChunk

    by_document = {}
    chunks = (
        DocumentChunk.objects
        .filter(document_id__in=agent.documents.values_list("id", flat=True))
        .exclude(embedding__isnull=True)
        .only("id", "document_id", "chunk_index", "text")
    )
    for chunk in chunks:
        if len(chunk.text or "") < MIN_SEED_CHARS:
            continue
        by_document.setdefault(chunk.document_id, []).append(chunk)

    if not by_document:
        return []

    for bucket in by_document.values():
        rng.shuffle(bucket)

    selected = []
    document_ids = sorted(by_document)
    position = 0
    while len(selected) < n:
        progressed = False
        for doc_id in document_ids:
            bucket = by_document[doc_id]
            if position < len(bucket):
                selected.append(bucket[position])
                progressed = True
                if len(selected) >= n:
                    break
        if not progressed:
            break
        position += 1

    return selected


_SYSTEM_PROMPT = (
    "You generate evaluation data for a document retrieval system. "
    "You respond with ONLY a JSON object, no prose, no markdown fences."
)

_PROMPTS = {
    "single_hop": """Below is an excerpt from a document.

EXCERPT:
{context}

Write one factual question that this excerpt fully answers, and its answer.

Rules:
- The question must be answerable using ONLY this excerpt.
- The question must be self-contained: no "this document", "the text", "it".
- Ask about a concrete fact, not the document's structure.
- The answer must be short and drawn strictly from the excerpt.

Return JSON: {{"question": "...", "answer": "..."}}""",

    "multi_part": """Below are two excerpts from a knowledge base.

EXCERPT A:
{context}

EXCERPT B:
{context_b}

Write ONE question that genuinely requires both excerpts to answer fully — for
example asking about two related things at once. Then give the combined answer.

Rules:
- The question must need BOTH excerpts; if either alone suffices, rewrite it.
- Self-contained, no references to "the document" or "the text".

Return JSON: {{"question": "...", "answer": "..."}}""",

    "negation": """Below is an excerpt from a document.

EXCERPT:
{context}

Write one question that asks about a topic in this excerpt while explicitly
EXCLUDING a specific named entity or term that appears in it — using wording like
"apart from", "other than", or "excluding". Then give the answer that respects
the exclusion.

Rules:
- The excluded term must be a concrete name or term, not a whole phrase.
- Self-contained, no references to "the document" or "the text".

Return JSON: {{"question": "...", "answer": "...", "excluded": "..."}}""",

    "out_of_scope": """A document assistant covers these topics:

{topics}

Write one question that sounds like it belongs to this general subject area but
is NOT answerable from those topics — it asks for information the knowledge base
plainly does not contain.

Rules:
- Plausible for the domain, but genuinely unanswerable from the topics listed.
- Do NOT ask about the weather, code, jokes, translation, or movies.
- Self-contained and specific.

Return JSON: {{"question": "...", "answer": "This is not covered by the available documents."}}""",
}


def _parse_json(raw):
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in response")
    return json.loads(text[start:end + 1])


def _generate_one(provider, query_type, **fields):
    raw = provider.complete(
        prompt=_PROMPTS[query_type].format(**fields),
        system_prompt=_SYSTEM_PROMPT,
    )
    data = _parse_json(raw)
    question = (data.get("question") or "").strip()
    answer = (data.get("answer") or "").strip()
    if not question or not answer:
        raise ValueError("missing question/answer in response")
    return question, answer


def complete_labels(question, agent, seed_chunks, threshold, rerank_top_n=20):
    """
    Label the corpus for one question: seed chunks grade 2, any other chunk the
    cross-encoder scores at or above `threshold` grade 1.
    """
    from scipy.special import expit

    seed_ids = {chunk.id for chunk in seed_chunks}
    labels = [ChunkLabel.from_chunk(chunk, GRADE_ANSWERS) for chunk in seed_chunks]

    embedding = generate_embeddings([question])[0]
    candidates = [
        chunk for chunk in _fetch_candidates(embedding, agent, rerank_top_n)
        if chunk.id not in seed_ids
    ]
    if not candidates:
        return labels

    scores = expit(get_reranker().predict([(question, c.text) for c in candidates]))
    for chunk, score in zip(candidates, scores):
        if float(score) >= threshold:
            labels.append(ChunkLabel.from_chunk(chunk, GRADE_SUPPORTING))

    return labels


def agent_topics(agent, limit=10):
    lines = []
    for document in agent.documents.all()[:limit]:
        topics = (document.meta_data or {}).get("topics", [])
        if topics:
            lines.append(f"- {document.name}: {', '.join(topics)}")
        else:
            lines.append(f"- {document.name}")
    return "\n".join(lines)


def build(agent, counts, label_threshold=DEFAULT_LABEL_THRESHOLD, seed=1234,
          sleep_seconds=0.0, log=logger.info):
    """
    Build golden records for one agent.

    `counts` maps query_type -> how many records to produce. Returns
    (records, stats); generation failures are counted rather than raised, since a
    single malformed model response should not discard an entire run.
    """
    rng = random.Random(seed)
    provider = GeminiProvider()
    topics = agent_topics(agent)

    grounded_needed = sum(
        n for key, n in counts.items() if key != "out_of_scope"
    )
    # Over-sample: some seeds yield blocked or malformed questions.
    seeds = sample_seed_chunks(agent, grounded_needed * 2 + 10, rng)
    if not seeds and grounded_needed:
        raise RuntimeError(
            "No embedded chunks long enough to seed questions. Check that "
            "documents finished embedding (chunks can be saved before their "
            "embeddings land)."
        )

    records = []
    stats = {"generated": 0, "blocked": 0, "failed": 0, "seeds_used": 0}
    cursor = 0

    def next_seed():
        nonlocal cursor
        if cursor >= len(seeds):
            return None
        chunk = seeds[cursor]
        cursor += 1
        stats["seeds_used"] += 1
        return chunk

    for query_type, wanted in counts.items():
        produced = 0
        attempts = 0
        max_attempts = wanted * 3 + 5

        while produced < wanted and attempts < max_attempts:
            attempts += 1
            try:
                if query_type == "out_of_scope":
                    question, answer = _generate_one(
                        provider, query_type, topics=topics
                    )
                    seed_chunks = []
                elif query_type == "multi_part":
                    first, second = next_seed(), next_seed()
                    if first is None or second is None:
                        break
                    question, answer = _generate_one(
                        provider, query_type,
                        context=first.text, context_b=second.text,
                    )
                    seed_chunks = [first, second]
                else:
                    chunk = next_seed()
                    if chunk is None:
                        break
                    question, answer = _generate_one(
                        provider, query_type, context=chunk.text
                    )
                    seed_chunks = [chunk]
            except Exception as exc:
                stats["failed"] += 1
                logger.warning("generation failed (%s): %s", query_type, exc)
                continue

            if _blocked(question):
                # See _blocked(): these can never reach retrieval.
                stats["blocked"] += 1
                continue

            if query_type == "out_of_scope":
                labels = []
                expected_status = "low"
            else:
                labels = complete_labels(question, agent, seed_chunks, label_threshold)
                expected_status = "high"

            records.append(GoldenRecord(
                id=f"{query_type}-{produced:03d}",
                question=question,
                query_type=query_type,
                ground_truth_answer=answer,
                relevant=labels,
                expected_status=expected_status,
            ))
            produced += 1
            stats["generated"] += 1
            log(f"  [{query_type}] {produced}/{wanted}: {question[:70]}")

            if sleep_seconds:
                time.sleep(sleep_seconds)

        if produced < wanted:
            logger.warning(
                "only produced %d/%d %s records", produced, wanted, query_type
            )

    return records, stats
