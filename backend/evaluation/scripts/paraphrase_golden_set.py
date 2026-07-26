"""Paraphrase every question in a golden set, keeping all other fields.

Used to test whether the semantic cache matches *rewordings* (not just exact
repeats): warm the cache with the original set, then run the paraphrased set and
read the hit rate. See evaluation/examples/example_threshold_tuning.md.

    uv run python evaluation/scripts/paraphrase_golden_set.py \
        [--src evaluation/dataset/golden_set.jsonl] \
        [--dst evaluation/dataset/golden_set_paraphrased.jsonl]

Requires the eval dependency group (langchain-google-genai) and GEMINI_API_KEY.
Output is git-ignored (it is derived from private tenant content).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import django

# backend/ is two levels up from this file (evaluation/scripts/<this>).
BACKEND = Path(__file__).resolve().parents[2]
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: E402

PROMPT = (
    "Rephrase the question below so it has the SAME meaning but different "
    "wording (synonyms, reordered clauses). Keep it a single question and keep "
    "any proper nouns. Return ONLY the rephrased question, nothing else.\n\n"
    "Question: {q}"
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="evaluation/dataset/golden_set.jsonl")
    parser.add_argument("--dst",
                        default="evaluation/dataset/golden_set_paraphrased.jsonl")
    parser.add_argument("--model", default="gemini-2.5-flash-lite")
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()

    os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY
    llm = ChatGoogleGenerativeAI(model=args.model, temperature=0.7)

    out, n = [], 0
    for line in open(args.src, encoding="utf-8"):
        if not line.strip():
            continue
        rec = json.loads(line)
        if "__meta__" in rec:
            out.append(rec)
            continue
        original = rec["question"]
        try:
            para = llm.invoke(PROMPT.format(q=original)).content.strip().strip('"')
        except Exception as exc:
            print(f"  paraphrase failed, keeping original: {exc}", file=sys.stderr)
            para = original
        rec["question"] = para
        out.append(rec)
        n += 1
        print(f"[{n}] {original[:50]!r} -> {para[:50]!r}")
        time.sleep(args.sleep)

    with open(args.dst, "w", encoding="utf-8") as fh:
        for rec in out:
            fh.write(json.dumps(rec) + "\n")
    print(f"\nWrote {n} paraphrased questions to {args.dst}")


if __name__ == "__main__":
    main()
