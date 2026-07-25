from agent.models import Agent
from rag.processors.retriever import retrieve_for_queries
from rag.processors.chunker import build_context
from rag.llm.base import GeminiProvider
from rag.processors.embeddings import is_query_allowed, generate_embeddings
from rag.processors.query_rewriter import QueryRewriter
from rag.processors import semantic_cache
from evaluation.trace import span


def _answer_payload(answer, chunk_ids, chunk_scores, status, full_ranking,
                    retrieval=None):
    """
    Build the response dict. The serving shape is exactly the three original
    keys; the evaluation-only diagnostics are added solely under `full_ranking`
    so nothing downstream (chat.views, the semantic cache) sees a changed
    payload in normal operation.
    """
    payload = {
        "answer": answer,
        "chunk_ids": chunk_ids,
        "chunk_scores": chunk_scores,
    }
    if full_ranking:
        retrieval = retrieval or {}
        payload["status"] = status
        payload["top_score"] = retrieval.get("top_score", 0.0)
        payload["avg_score"] = retrieval.get("avg_score", 0.0)
        payload["ranked_chunk_ids"] = retrieval.get("ranked_chunk_ids", [])
        payload["ranked_scores"] = retrieval.get("ranked_scores", [])
        payload["ann_chunk_ids"] = retrieval.get("ann_chunk_ids", [])
    return payload


def generate_agent_answer(agent_id, question, history, trace=None,
                          full_ranking=False):
    """
    `trace` and `full_ranking` are opt-in evaluation hooks. With both omitted the
    behaviour and returned payload are exactly as before: `trace=None` makes every
    span a no-op, and `full_ranking=False` keeps the extra diagnostic keys out of
    the response.
    """
    agent = Agent.objects.get(id=agent_id)

    # 1. Guardrail: reject disallowed queries early (not cached).
    with span(trace, "guardrail"):
        allowed = is_query_allowed(question)
    if not allowed:
        answer = generate_fallback_llm(agent, question, history, agent.system_prompt,
                                       trace=trace)
        return _answer_payload(answer, [], [], "blocked", full_ranking)

    # 2. Query understanding: resolve follow-up references into a self-contained
    #    query, split genuine multi-part questions into sub-queries, and surface
    #    negation. Cheap (small model) and degrades to the raw question on failure.
    with span(trace, "rewrite"):
        transform = QueryRewriter().transform(question, history, trace=trace)
    print(f"QUERY TRANSFORM: {transform}")

    # 3. Semantic cache lookup on the self-contained query. A hit skips the whole
    #    retrieval + generation pipeline. Compute the knowledge version once and
    #    reuse it for both lookup and store below.
    #
    #    Skip the cache entirely for exclusion queries: the cache key is the
    #    standalone_query embedding ("smartphones"), which does NOT encode the
    #    excluded term, so caching would let "smartphones apart from Nokia" and a
    #    plain "smartphones" collide and return each other's answer.
    cacheable = not transform.exclusions
    knowledge_version = semantic_cache.compute_knowledge_version(agent)
    query_embedding = generate_embeddings([transform.standalone_query], trace=trace)[0]
    if cacheable:
        with span(trace, "cache_lookup"):
            cached = semantic_cache.lookup(agent, query_embedding, knowledge_version)
        if cached:
            print("SEMANTIC CACHE HIT")
            if trace is not None:
                trace.record_cache("hit")
            return cached
        print("SEMANTIC CACHE MISS")
        if trace is not None:
            trace.record_cache("miss")
    elif trace is not None:
        # Exclusion queries bypass the cache by design, so they are neither a hit
        # nor a miss — counting them as misses would understate the hit rate.
        trace.record_cache("skipped")

    # 4. Retrieval: decompose-and-merge over the sub-queries, reranked against
    #    the standalone query.
    retrieval = retrieve_for_queries(
        transform.sub_queries, transform.standalone_query, agent,
        exclusions=transform.exclusions, trace=trace, full_ranking=full_ranking,
    )
    status = retrieval.get("status", "low")
    chunks = retrieval.get("chunks", [])
    chunk_ids = retrieval.get("chunk_ids", [])
    chunk_scores = retrieval.get("chunk_scores", [])

    print(retrieval)

    # 5. Routing logic.
    if status == "low" or (status == "high" and not chunks):
        answer = generate_fallback_llm(agent, question, history, agent.system_prompt,
                                       trace=trace)
        return _answer_payload(answer, [], [], status, full_ranking, retrieval)

    if status in ("partial", "ambiguous"):
        answer = generate_clarification_llm(agent, question, chunks, history,
                                            trace=trace)
        return _answer_payload(answer, chunk_ids, chunk_scores, status,
                               full_ranking, retrieval)

    # status == "high" with chunks → answer strictly from context, then cache.
    context = build_context(chunks)

    prompt = f"""
        You must answer STRICTLY using the provided context.

        CONTEXT:
        {context}

        RULES:
        - Answer ONLY from the context above.
        - Do NOT use prior knowledge.
        - Do NOT guess.

        QUESTION:
        {question}
        """

    provider = GeminiProvider()
    with span(trace, "generation"):
        answer = provider.generate(
            system_prompt=agent.system_prompt,
            question=prompt,
            history=[],
            trace=trace,
            label="generation",
        )

    # Cache the serving-shaped payload only. The diagnostic keys added by
    # full_ranking are per-run and must not be persisted into cache entries.
    result = {"answer": answer, "chunk_ids": chunk_ids, "chunk_scores": chunk_scores}
    if answer and cacheable:
        with span(trace, "cache_store"):
            semantic_cache.store(
                agent, transform.standalone_query, query_embedding, result,
                knowledge_version,
            )
    return _answer_payload(answer, chunk_ids, chunk_scores, status, full_ranking,
                           retrieval)


def generate_fallback_llm(agent, question, history, system_prompt=None, top_score=None,
                          trace=None):
    """
    Generates a fallback response using extracted topics from documents
    instead of just document titles.
    """

    # Get topics from documents
    doc_topics = []
    for doc in agent.documents.all()[:10]:
        topics = doc.meta_data.get("topics", [])
        if topics:
            doc_topics.append(f"{doc.name}: {', '.join(topics)}")
        else:
            doc_topics.append(f"{doc.name}: (no topics extracted)")

    provider = GeminiProvider()
    print(f"Extracted doc topics for fallback: {doc_topics}")

    # Dynamic instruction block
    if top_score is not None and top_score < 0.1:
        instructions = """
        - Politely say you couldn't find an exact answer from the available documents.
        - Do NOT provide suggestions or additional help.
        """
    else:
        instructions = """
        - Politely say you couldn't find an exact answer if you cannot answer from document and prompt given
        - Clearly explain what you CAN help with
        - Suggest an example question if needed
        - Keep it natural and helpful
        - DO NOT answer the original question
        """

    prompt = f"""
    User asked: "{question}"

    This question is outside the scope of the available documents.

    The agent can help with topics extracted from the documents:
    {chr(10).join(doc_topics)}

    Instructions:
    {instructions}
    """

    # Safe system prompt handling
    final_system_prompt = (system_prompt or "") + (
        "\nYou are a helpful assistant that guides users to understand "
        "what topics the agent can assist with based on the documents it has."
    )

    with span(trace, "generation"):
        return provider.generate(
            system_prompt=final_system_prompt,
            question=prompt,
            history=[],  # keep stateless for fallback
            trace=trace,
            label="fallback",
        )

def generate_clarification_llm(agent, question, chunks, history, trace=None):
    """
    Generate clarification prompt when retrieval is partial or ambiguous.
    """
    context_preview = "\n".join([c.text[:200] for c in chunks[:3]]) if chunks else ""

    provider = GeminiProvider()

    prompt = f"""
    User asked: "{question}"

    Some partially relevant information was found:
    {context_preview}

    Instructions:
    - Ask the user to clarify their question
    - Keep it short and helpful
    - Do NOT answer the question
    - Only ask for clarification
    """
    with span(trace, "generation"):
        return provider.generate(
            system_prompt="You are a helpful assistant that guides users to clarify their questions.",
            question=prompt,
            history=history,
            trace=trace,
            label="clarification",
        )