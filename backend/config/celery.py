import os
from celery import Celery
from celery.signals import worker_process_init

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("backend")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()


@worker_process_init.connect
def preload_ml_models(**kwargs):
    """
    Warm up the embedding/reranker models once per forked worker process,
    right after fork() completes. They're loaded lazily (see
    rag.processors.embeddings.get_embedding_model and
    rag.processors.retriever.get_reranker) instead of at import time,
    because loading torch-backed models in the master before fork() crashes
    forked children on macOS. This hook just avoids paying that load cost
    on the first task each worker picks up.
    """
    from rag.processors.embeddings import get_embedding_model
    from rag.processors.retriever import get_reranker

    get_embedding_model()
    get_reranker()