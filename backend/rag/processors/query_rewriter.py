# rag.processors.query_rewriter
"""
Small-LM query transformation.

Turns a raw (possibly context-dependent, multi-part, or negated) user question
into a self-contained form suitable for retrieval and semantic-cache lookup:

  - Resolves follow-up references ("what about pricing?") into a standalone
    query using conversation history.
  - Splits genuine multi-part questions ("what is X and what isn't covered by
    Y?") into sub-queries so each can be retrieved for independently.
  - Makes negation explicit so it survives embedding/retrieval.

The transform is intentionally backed by a *small* model (see
settings.REWRITER_MODEL) so it is cheap enough to run on every request before
the semantic-cache lookup. It always degrades gracefully: any error or malformed
model output falls back to treating the raw question as a single standalone
query, so a bad response never breaks the answer path.
"""
import json
import logging
from dataclasses import dataclass, field

from django.conf import settings

from rag.llm.base import GeminiProvider
from rag.processors.retriever import format_history

logger = logging.getLogger(__name__)


@dataclass
class QueryTransform:
    standalone_query: str
    sub_queries: list = field(default_factory=list)
    has_negation: bool = False
    # Entities/terms the user explicitly wants excluded from results, e.g.
    # "smartphones apart from Nokia" -> ["Nokia"]. Retrieval drops chunks that
    # match any of these (see retriever.retrieve_for_queries).
    exclusions: list = field(default_factory=list)

    def __post_init__(self):
        # A single-topic question is just one sub-query equal to the standalone
        # query — keeps downstream retrieval uniform (always iterates sub_queries).
        if not self.sub_queries:
            self.sub_queries = [self.standalone_query]


def get_rewriter_provider():
    """The provider used for query transformation — a small/cheap model."""
    return GeminiProvider(model_name=settings.REWRITER_MODEL)


_SYSTEM_PROMPT = (
    "You are a query-understanding assistant for a document retrieval system. "
    "You rewrite user questions so they can be searched effectively. "
    "You respond with ONLY a JSON object, no prose, no markdown fences."
)


def _build_prompt(question, history):
    history_block = ""
    if history:
        history_block = (
            "Conversation so far (for resolving references only):\n"
            f"{format_history(history)}\n\n"
        )

    return f"""{history_block}User's latest question: "{question}"

Rewrite it for document search. Return a JSON object with exactly these keys:
- "standalone_query": the question rewritten to be fully self-contained. Resolve
  any pronouns or references ("it", "that", "what about X") using the
  conversation above. If it is already self-contained, keep it as-is.
- "sub_queries": a list of strings. If the question asks about two or more
  genuinely distinct things, split it into one search query per thing. If it is
  a single-topic question, return a list with just the standalone_query.
- "has_negation": true if the question excludes specific things ("apart from",
  "except", "other than", "not X"), otherwise false.
- "exclusions": a list of the specific entities/terms the user wants excluded
  from the results (e.g. "smartphones apart from Nokia" -> ["Nokia"]). Empty
  list if nothing is excluded. Do NOT put whole phrases here, just the concrete
  names/terms to filter out.

For the standalone_query and sub_queries, describe the topic the user DOES want
positively (e.g. "smartphones apart from Nokia" -> standalone_query
"smartphones"); the excluded terms belong only in "exclusions".

Return ONLY the JSON object."""


def _parse_response(raw, question):
    """Parse the model's JSON, tolerating markdown fences and stray text."""
    text = raw.strip()

    # Isolate the outermost JSON object. This also transparently strips any
    # ```json ... ``` fences or stray prose the model may have added.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in response")

    data = json.loads(text[start:end + 1])

    standalone = (data.get("standalone_query") or question).strip() or question

    sub_queries = data.get("sub_queries") or []
    # Keep only non-empty strings; fall back to the standalone query if none.
    sub_queries = [str(q).strip() for q in sub_queries if str(q).strip()]
    if not sub_queries:
        sub_queries = [standalone]

    exclusions = data.get("exclusions") or []
    exclusions = [str(t).strip() for t in exclusions if str(t).strip()]

    return QueryTransform(
        standalone_query=standalone,
        sub_queries=sub_queries,
        # An explicit exclusion list implies a negation even if the flag is unset.
        has_negation=bool(data.get("has_negation", False)) or bool(exclusions),
        exclusions=exclusions,
    )


class QueryRewriter:
    def __init__(self, provider=None):
        self._provider = provider

    @property
    def provider(self):
        # Lazily construct so importing this module never triggers a provider
        # (and never requires GEMINI_API_KEY just to import).
        if self._provider is None:
            self._provider = get_rewriter_provider()
        return self._provider

    def transform(self, question, history=None):
        """
        Transform a raw question into a QueryTransform. Never raises — on any
        failure it returns the raw question as a single standalone query.
        """
        history = history or []
        try:
            raw = self.provider.complete(
                prompt=_build_prompt(question, history),
                system_prompt=_SYSTEM_PROMPT,
            )
            return _parse_response(raw, question)
        except Exception as e:
            logger.warning("QueryRewriter.transform failed, using raw question: %s", e)
            return QueryTransform(standalone_query=question)
