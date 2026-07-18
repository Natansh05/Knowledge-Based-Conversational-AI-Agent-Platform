from django.db import models
from users.models import User
from pgvector.django import VectorField, HnswIndex

# Create your models here.
class Document(models.Model):
    name = models.CharField(max_length=255)
    s3_key = models.CharField(max_length=500)
    file_type = models.CharField(max_length=50)
    file_size = models.BigIntegerField(default=0)

    status = models.CharField(
        choices=[('uploaded', 'Uploaded'), ('processing', 'Processing'), ('ready', 'Ready'), ('failed', 'Failed')],
        max_length=52, default='uploaded'
    )

    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    last_modified_at = models.DateTimeField(auto_now=True)

    accessible_by = models.ManyToManyField(User, related_name="accessible_documents", blank=True)
    meta_data = models.JSONField(blank=True, default=dict)

class DocumentChunk(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks"
    )
    chunk_index = models.IntegerField()
    text = models.TextField()
    embedding = VectorField(
        # using all-MiniLM-L6-v2
        # dimensions=384,

        # using all-mpnet-base-v2
        dimensions=768,
        null=True
    )
    meta_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["chunk_index"]
        unique_together = ["document", "chunk_index"]
        indexes = [
            models.Index(fields=["document"], name="document_chunk_document_idx"),
            HnswIndex(
                name="doc_chunk_emb_hnsw_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]