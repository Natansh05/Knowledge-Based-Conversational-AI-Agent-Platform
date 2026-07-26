# evaluation.dataset.schema
"""
Golden-set records and their on-disk (JSONL) form.

Labels never store a raw DocumentChunk primary key. `chunker.save_chunks` deletes
and recreates every chunk for a document on re-ingestion, so PKs churn whenever a
document is re-uploaded (documents.views.update_document bumps `version` and
reprocesses). A golden set keyed on PKs would silently start scoring against the
wrong chunks — or against nothing — with no error.

Instead a label is (document_id, chunk_index, text_sha1):

  * document_id + chunk_index is stable across re-ingestion, because chunk_index
    is a plain enumerate() counter over the splitter's output.
  * text_sha1 detects the case that identity cannot: the document was edited, so
    chunk 7 still exists but is no longer the text that was labelled. That label
    is stale and must be reported rather than trusted.
"""
import hashlib
import json
from dataclasses import asdict, dataclass, field

# Grades. nDCG uses these directly, so the distinction is load-bearing:
# with everything graded 1 the metric degenerates toward a smoothed recall.
GRADE_IRRELEVANT = 0
GRADE_SUPPORTING = 1
GRADE_ANSWERS = 2

QUERY_TYPES = ("single_hop", "multi_part", "negation", "out_of_scope")


def text_sha1(text):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


@dataclass
class ChunkLabel:
    document_id: int
    chunk_index: int
    text_sha1: str
    grade: int = GRADE_ANSWERS

    @classmethod
    def from_chunk(cls, chunk, grade=GRADE_ANSWERS):
        return cls(
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            text_sha1=text_sha1(chunk.text),
            grade=grade,
        )

    @property
    def key(self):
        return (self.document_id, self.chunk_index)


@dataclass
class GoldenRecord:
    id: str
    question: str
    query_type: str
    ground_truth_answer: str
    relevant: list = field(default_factory=list)   # list[ChunkLabel]
    expected_status: str = "high"
    history: list = field(default_factory=list)

    def to_json(self):
        data = asdict(self)
        data["relevant"] = [asdict(label) if not isinstance(label, dict) else label
                            for label in self.relevant]
        return data

    @classmethod
    def from_json(cls, data):
        record = cls(**data)
        record.relevant = [ChunkLabel(**label) for label in record.relevant]
        return record


def write_jsonl(path, records, meta=None):
    """
    Write records as JSONL. The first line is a metadata header recording the
    document versions the set was built against, so a later run can tell whether
    the corpus has moved underneath the labels.
    """
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"__meta__": meta or {}}) + "\n")
        for record in records:
            handle.write(json.dumps(record.to_json()) + "\n")


def read_jsonl(path):
    """Return (records, meta)."""
    records = []
    meta = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if "__meta__" in data:
                meta = data["__meta__"]
                continue
            records.append(GoldenRecord.from_json(data))
    return records, meta


def resolve_labels(records):
    """
    Map every label to a live DocumentChunk id.

    Returns (resolved, report) where `resolved` maps record id -> {chunk_id: grade}
    and `report` counts what happened. Stale labels (the chunk exists but its text
    has changed) are excluded from `resolved`: scoring against text that no longer
    matches what a human or model judged would quietly corrupt every metric, so
    they are surfaced as a number the caller is expected to look at.
    """
    from documents.models import DocumentChunk

    wanted = {
        label.key
        for record in records
        for label in record.relevant
    }
    if not wanted:
        return {}, {"matched": 0, "missing": 0, "stale": 0}

    document_ids = {doc_id for doc_id, _ in wanted}
    live = {
        (chunk.document_id, chunk.chunk_index): chunk
        for chunk in DocumentChunk.objects.filter(document_id__in=document_ids)
        .only("id", "document_id", "chunk_index", "text")
    }

    resolved = {}
    report = {"matched": 0, "missing": 0, "stale": 0, "stale_keys": [], "missing_keys": []}

    for record in records:
        mapping = {}
        for label in record.relevant:
            chunk = live.get(label.key)
            if chunk is None:
                report["missing"] += 1
                report["missing_keys"].append(label.key)
                continue
            if text_sha1(chunk.text) != label.text_sha1:
                report["stale"] += 1
                report["stale_keys"].append(label.key)
                continue
            mapping[chunk.id] = label.grade
            report["matched"] += 1
        resolved[record.id] = mapping

    return resolved, report
