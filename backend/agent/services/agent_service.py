from agent.models import Agent
from rag.processors.retriever import retrieve_chunks
from rag.processors.chunker import build_context
from rag.llm.base import GeminiProvider
from rag.processors.embeddings import is_query_allowed

from agent.services.utils.cache import generate_cache_key, get_cache, set_cache


def generate_agent_answer(agent_id, question, history):
    # 1.Cache
    cache_key = generate_cache_key(agent_id, question)
    cached_response = get_cache(cache_key)
    if cached_response:
        print("CACHE HIT")
        if isinstance(cached_response, str):  # handle legacy cache entries
            return {"answer": cached_response, "chunk_ids": [], "chunk_scores": []}
        return cached_response

    print("CACHE MISS")

    agent = Agent.objects.get(id=agent_id)
    provider = GeminiProvider()

    # 2.Guardrail: check if query is allowed
    if not is_query_allowed(question):
        answer = generate_fallback_llm(agent, question, history, agent.system_prompt)
        result = {"answer": answer, "chunk_ids": [], "chunk_scores": []}
        if answer:
            set_cache(cache_key, result)
        return result

    # 3.Retrieval
    retrieval = retrieve_chunks(question, agent)
    status = retrieval.get("status", "low")
    chunks = retrieval.get("chunks", [])
    top_score = retrieval.get("top_score", 0.0)
    chunk_ids = retrieval.get("chunk_ids", [])
    chunk_scores = retrieval.get("chunk_scores", [])

    print(retrieval)

    # 4.Routing Logic
    if status == "low":
        answer = generate_fallback_llm(agent, question, history, agent.system_prompt)
        result = {"answer": answer, "chunk_ids": [], "chunk_scores": []}
        if answer:
            set_cache(cache_key, result)
        return result

    elif status in ["partial", "ambiguous"]:
        answer = generate_clarification_llm(agent, question, chunks, history)
        result = {"answer": answer, "chunk_ids": chunk_ids, "chunk_scores": chunk_scores}
        if answer:
            set_cache(cache_key, result)
        return result

    elif status == "high":
        # Handle edge case: no chunks
        if not chunks:
            answer = generate_fallback_llm(agent, question, history, agent.system_prompt)
            result = {"answer": answer, "chunk_ids": [], "chunk_scores": []}
            if answer:
                set_cache(cache_key, result)
            return result

        # Build context safely
        context = build_context(chunks) if chunks else ""

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

        answer = provider.generate(
            system_prompt=agent.system_prompt,
            question=prompt,
            history=[]
        )

        result = {"answer": answer, "chunk_ids": chunk_ids, "chunk_scores": chunk_scores}
        if answer:
            set_cache(cache_key, result)
        return result

    # Safety fallback
    answer = generate_fallback_llm(agent, question, history)
    result = {"answer": answer, "chunk_ids": [], "chunk_scores": []}
    if answer:
        set_cache(cache_key, result)
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