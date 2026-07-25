# evaluation.report
"""Markdown rendering of an evaluation report."""


def _fmt(value, places=3):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


def _ms(stats):
    if not stats:
        return "—"
    return f"{stats['p50']:.0f} / {stats['p95']:.0f}"


def render_markdown(report):
    meta = report.get("meta", {})
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- tenant: `{meta.get('tenant')}`  agent: `{meta.get('agent_id')}`",
        f"- golden set: `{meta.get('golden_set')}` ({meta.get('records', 0)} records)",
        f"- semantic cache: {'disabled' if meta.get('cache_disabled') else 'ENABLED'}",
        "",
    ]

    labels = report.get("label_resolution") or {}
    if labels.get("missing") or labels.get("stale"):
        lines += [
            "> **Label warning** — "
            f"{labels.get('stale', 0)} stale and {labels.get('missing', 0)} missing "
            "labels were excluded. The corpus has changed since the golden set was "
            "built; regenerate it before trusting these numbers.",
            "",
        ]

    # Retrieval ranking, both stages.
    lines += ["## Retrieval ranking", ""]
    stages = report.get("ranking", {})
    if stages:
        metric_names = sorted(
            {name for stage in stages.values() for name in stage}
        )
        header = "| metric | " + " | ".join(stages) + " |"
        lines += [header, "|" + "---|" * (len(stages) + 1)]
        for name in metric_names:
            cells = []
            for stage in stages:
                entry = stages[stage].get(name)
                cells.append(
                    f"{entry['mean']:.3f} (n={entry['n']})" if entry else "—"
                )
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines += [
            "",
            "`ann` is the pgvector candidate order; `rerank` is after the "
            "cross-encoder. A rerank column that does not beat ann means the "
            "cross-encoder is not earning its place on the critical path.",
            "",
            "Metrics are computed over the full pre-truncation candidate list. "
            "The served answer uses at most 4 chunks (usually 2), so @5 and @10 "
            "are undefined on the delivered set.",
            "",
        ]

    # Per-stratum recall.
    strata = report.get("by_query_type", {})
    if strata:
        lines += ["### Recall@5 by query type", "", "| query type | n | recall@5 |",
                  "|---|---|---|"]
        for query_type, scores in sorted(strata.items()):
            entry = scores.get("recall@5")
            lines.append(
                f"| {query_type} | {entry['n'] if entry else 0} | "
                f"{_fmt(entry['mean']) if entry else '—'} |"
            )
        lines.append("")

    # Routing / refusal.
    refusal = report.get("refusal", {})
    if refusal:
        lines += ["## Routing behaviour", ""]
        if "correct_refusal_rate" in refusal:
            lines += [
                f"- **correct refusal rate**: {_fmt(refusal['correct_refusal_rate'])} "
                f"(n={refusal['out_of_scope']['n']} out-of-scope)",
                f"- **false answer rate**: {_fmt(refusal['false_answer_rate'])} "
                "— out-of-scope questions that got a grounded answer",
                f"- clarified instead: {_fmt(refusal['out_of_scope']['clarified'])}",
            ]
        if "missed_answer_rate" in refusal:
            lines.append(
                f"- **missed answer rate**: {_fmt(refusal['missed_answer_rate'])} "
                f"— answerable questions the system refused "
                f"(n={refusal['in_scope']['n']})"
            )
        lines.append("")

    confusion = report.get("status_confusion", {})
    if confusion:
        actuals = sorted({a for row in confusion.values() for a in row})
        lines += ["### Expected vs actual status", "",
                  "| expected | " + " | ".join(actuals) + " |",
                  "|" + "---|" * (len(actuals) + 1)]
        for expected in sorted(confusion):
            row = confusion[expected]
            lines.append(
                f"| {expected} | " +
                " | ".join(str(row.get(a, 0)) for a in actuals) + " |"
            )
        lines.append("")

    # Application metrics.
    app = report.get("application", {})
    if app:
        latency = app.get("latency_ms", {})
        lines += ["## Application metrics", "", "### Latency (ms, p50 / p95)", "",
                  "| stage | p50 / p95 |", "|---|---|"]
        for name in ("total_ms", "rewrite", "embed", "ann_fetch", "rerank",
                     "retrieval_derived_ms", "generation", "cache_lookup",
                     "cache_store", "guardrail"):
            if latency.get(name):
                lines.append(f"| {name} | {_ms(latency[name])} |")
        lines.append("")

        tokens = app.get("tokens", {})
        if tokens:
            lines += ["### Tokens", "", "| call site | calls | prompt | completion | total |",
                      "|---|---|---|---|---|"]
            for label, bucket in sorted(tokens.items()):
                if label == "_all":
                    continue
                lines.append(
                    f"| {label} | {bucket['calls']} | {bucket['prompt']} | "
                    f"{bucket['completion']} | {bucket['total']} |"
                )
            overall = tokens.get("_all", {})
            lines += [
                "",
                f"Mean {overall.get('mean_per_query', 0):.0f} tokens per query "
                f"({overall.get('total', 0)} total).",
                "",
            ]

        cache = app.get("cache", {})
        if cache:
            lines += [
                "### Cache",
                "",
                f"- states: `{cache.get('states')}`",
                f"- hit rate: {_fmt(cache.get('hit_rate'))}",
                "",
                "> Hit rate from an eval run is meaningless — the cache is "
                "disabled so results are reproducible. Measure it from serving "
                "traffic instead.",
                "",
            ]

    # Ragas.
    ragas = report.get("ragas")
    if ragas:
        lines += ["## Ragas", "", "| metric | mean | n |", "|---|---|---|"]
        for name, entry in sorted(ragas.items()):
            lines.append(f"| {name} | {_fmt(entry.get('mean'))} | {entry.get('n')} |")
        lines.append("")
    else:
        lines += ["## Ragas", "",
                  "Not run. Produce `eval_records.json` with `run_eval`, then "
                  "`python manage.py score_ragas`.", ""]

    # Caveats travel with the numbers, not in a separate document.
    lines += [
        "## Caveats",
        "",
        f"- n={meta.get('records', 0)}: confidence intervals are wide. Treat "
        "differences under ~5 points as noise.",
        "- Supporting labels come from the same cross-encoder the pipeline uses "
        "to rerank, so retrieval metrics are mildly flattering to that reranker.",
        "- Ragas metrics are LLM-judged and vary between runs on identical input.",
        "",
    ]

    return "\n".join(lines)
