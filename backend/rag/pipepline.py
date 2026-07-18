from rag.processors.extractor import extract_text
from rag.processors.chunker import chunk_text, save_chunks
from rag.processors.embeddings import embed_document_chunks

def process_document_pipeline(document, file_path, schema_name):
    text = extract_text(file_path)
    chunks = chunk_text(text)
    save_chunks(document,chunks)
    embed_document_chunks(document=document, schema_name=schema_name)