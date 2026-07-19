from agent.models import Agent
from rag.processors.retriever import retrieve_for_queries
from rag.processors.chunker import build_context
from rag.llm.base import GeminiProvider
from rag.processors.embeddings import is_query_allowed, generate_embeddings
from rag.processors.query_rewriter import QueryRewriter
from rag.processors import semantic_cache


def generate_agent_answer(agent_id, question, history):
    agent = Agent.objects.get(id=agent_id)

    # 1. Guardrail: reject disallowed queries early (not cached).
    if not is_query_allowed(question):
        answer = generate_fallback_llm(agent, question, history, agent.system_prompt)
        return {"answer": answer, "chunk_ids": [], "chunk_scores": []}

    # 2. Query understanding: resolve follow-up references into a self-contained
    #    query, split genuine multi-part questions into sub-queries, and surface
    #    negation. Cheap (small model) and degrades to the raw question on failure.
    transform = QueryRewriter().transform(question, history)
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
    query_embedding = generate_embeddings([transform.standalone_query])[0]
    if cacheable:
        cached = semantic_cache.lookup(agent, query_embedding, knowledge_version)
        if cached:
            print("SEMANTIC CACHE HIT")
            return cached
        print("SEMANTIC CACHE MISS")

    # 4. Retrieval: decompose-and-merge over the sub-queries, reranked against
    #    the standalone query.
    retrieval = retrieve_for_queries(
        transform.sub_queries, transform.standalone_query, agent,
        exclusions=transform.exclusions,
    )
    status = retrieval.get("status", "low")
    chunks = retrieval.get("chunks", [])
    chunk_ids = retrieval.get("chunk_ids", [])
    chunk_scores = retrieval.get("chunk_scores", [])

    print(retrieval)

    # 5. Routing logic.
    if status == "low" or (status == "high" and not chunks):
        answer = generate_fallback_llm(agent, question, history, agent.system_prompt)
        return {"answer": answer, "chunk_ids": [], "chunk_scores": []}

    if status in ("partial", "ambiguous"):
        answer = generate_clarification_llm(agent, question, chunks, history)
        return {"answer": answer, "chunk_ids": chunk_ids, "chunk_scores": chunk_scores}

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
    answer = provider.generate(
        system_prompt=agent.system_prompt,
        question=prompt,
        history=[]
    )

    result = {"answer": answer, "chunk_ids": chunk_ids, "chunk_scores": chunk_scores}
    if answer and cacheable:
        semantic_cache.store(
            agent, transform.standalone_query, query_embedding, result,
            knowledge_version,
        )
    return result


def generate_fallback_llm(agent, question, history, system_prompt=None, top_score=None):
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

    return provider.generate(
        system_prompt=final_system_prompt,
        question=prompt,
        history=[]  # keep stateless for fallback
    )

def generate_clarification_llm(agent, question, chunks, history):
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
    return provider.generate(
        system_prompt="You are a helpful assistant that guides users to clarify their questions.",
        question=prompt,
        history=history
    )