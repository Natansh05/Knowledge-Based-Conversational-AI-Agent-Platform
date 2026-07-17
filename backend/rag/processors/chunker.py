# rag.processors.chunker.py
from langchain_text_splitters import RecursiveCharacterTextSplitter
from documents.models import DocumentChunk


def chunk_text(text):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    chunks = splitter.split_text(text)

    return chunks

def save_chunks(document, chunks):
    DocumentChunk.objects.filter(document=document).delete()

    chunk_objects = []
    for index, chunk in enumerate(chunks):
        chunk_objects.append(
            DocumentChunk(
                document=document,
                chunk_index=index,
                text=chunk,
                meta_data={
                    "length": len(chunk)
                }
            )
        )

    DocumentChunk.objects.bulk_create(chunk_objects, batch_size=500)

def build_context(chunks, max_chars=6000):
    context = ""
    for chunk in chunks:
        if len(context) + len(chunk.text) > max_chars:
            break
        context += chunk.text + "\n\n ------ \n\n"

    return context