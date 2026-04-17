from celery import shared_task
from .models import Document, DocumentChunk
from core.storage.s3 import S3Client
from django_tenants.utils import schema_context
from rag.pipepline import process_document_pipeline
from rag.processors.meta import extract_document_topics

@shared_task
def process_document(document_id, schema_name):

    with schema_context(schema_name):
        doc = Document.objects.get(id=document_id)

        doc.status = "processing"
        doc.save()
        client = S3Client()

        # later
        # download from s3
        file_path = client.download_file(doc.s3_key, doc.name)

        # chunking and embedding 
        process_document_pipeline(doc, file_path)

        # extracting and saving meta data
        extract_and_save_meta(doc)

        doc.status = "ready"
        doc.save()

@shared_task
def extract_and_save_meta(doc):
    """
    Extract topics / keywords from all chunks of the document and save in meta_data.
    """
    # doc = Document.objects.get(id=28)  # refresh from db to get updated chunks
    # 1. Reconstruct full text from chunks
    debug = doc.chunks.all()
    print(debug)
    chunk_texts = doc.chunks.values_list("text", flat=True)
    print(chunk_texts)
    full_text = " ".join(chunk_texts)

    if not full_text.strip():
        doc.meta_data = {"topics": []}
        doc.save()
        return

    # 2. Extract topics using RAKE / TextRank
    topics = extract_document_topics(full_text, top_n=5)  # returns list of keywords/phrases

    # 3. Save in Document.meta_data
    doc.meta_data = {"topics": topics}
    doc.save()

@shared_task
def embed_chunk_batch(chunk_ids):
    chunks = list(
        DocumentChunk.objects.filter(id__in=chunk_ids)
    )

    texts = [c.text for c in chunks]

    from rag.processors.embeddings import generate_embeddings
    embeddings = generate_embeddings(texts)
    for chunk, emb in zip(chunks, embeddings):
        chunk.embedding = emb
    DocumentChunk.objects.bulk_update(
        chunks,
        ["embedding"]
    )