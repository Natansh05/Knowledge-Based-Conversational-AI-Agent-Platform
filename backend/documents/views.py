from django.shortcuts import render
from core.storage.s3 import S3Client
from core.storage.paths import tenant_document_path
from rest_framework.decorators import permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django_tenants.utils import tenant_context
from .models import Document, DocumentChunk
from .serializer import DocumentSerializer
from rest_framework import status
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from datetime import datetime, timedelta
from .tasks import process_document 
from django.db import connection 
from django.utils import timezone

# s3 views
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_upload_url(request, tenant_slug=None):
    tenant = request.tenant
    filename = request.data["filename"]
    content_type = request.data["content_type"]

    # update in db after uploading to s3 using the file_key returned here
    # everything will be handled in the background using signals and celery tasks

    key = tenant_document_path(tenant.id, filename)
    s3_client = S3Client()
    upload_url = s3_client.generate_upload_url(key,content_type)

    return Response({
        "upload_url": upload_url, 
        "file_key": key
        })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def getAllDocuments(request, tenant_slug=None):
    """
    Get filtered, paginated documents.
    Filters (all optional):
        - search: name search
        - uploaded_by: user id (integer)
        - file_type
        - status
        - start_date, end_date: filter created_at
    Pagination:
        - page
        - page_size
    Ordering:
        - order_by
    """
    # documents = Document.objects.all()
    documents = request.user.accessible_documents.all()
    documents |= Document.objects.filter(uploaded_by=request.user)
    documents = documents.distinct()

    if request.user.role == 1 :
        documents = Document.objects.all()

    # Filters
    search = request.GET.get("search")
    uploaded_by = request.GET.get("uploaded_by")
    file_type_param = request.GET.get("file_type")
    file_type = file_type_param.split(",") if file_type_param else []
    status_filter = request.GET.get("status")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    # Initialize date variables
    start_dt = None
    end_dt = None

    # Search filter
    if search:
        documents = documents.filter(name__icontains=search)

    # Uploaded by filter (convert to int)
    if uploaded_by:
        try:
            uploaded_by = int(uploaded_by)
            documents = documents.filter(uploaded_by__id=uploaded_by)
        except ValueError:
            pass

    # File type filter
    if file_type:
        documents = documents.filter(file_type__in=file_type)

    # Status filter
    if status_filter:
        documents = documents.filter(status=status_filter)

    # Date filters
    if start_date:
        try:
            start_dt = timezone.make_aware(datetime.strptime(start_date, "%Y-%m-%d"))
        except ValueError:
            start_dt = None
    if end_date:
        try:
            end_dt = timezone.make_aware(
                datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)
            )
        except ValueError:
            end_dt = None

    # Apply date filters safely
    if start_dt and end_dt:
        documents = documents.filter(created_at__range=[start_dt, end_dt])
    elif start_dt:
        documents = documents.filter(created_at__gte=start_dt)
    elif end_dt:
        documents = documents.filter(created_at__lte=end_dt)

    # Ordering
    order_by = request.GET.get("order_by", "-created_at")
    documents = documents.order_by(order_by)

    # Pagination
    page = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 10))
    paginator = Paginator(documents, page_size)

    try:
        docs_page = paginator.page(page)
    except PageNotAnInteger:
        docs_page = paginator.page(1)
    except EmptyPage:
        docs_page = paginator.page(paginator.num_pages)

    # Serialize data
    serializer = DocumentSerializer(docs_page, many=True)

    return Response({
        "count": paginator.count,
        "num_pages": paginator.num_pages,
        "current_page": docs_page.number,
        "results": serializer.data
    }, status=status.HTTP_200_OK)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_document(request,tenant_slug=None):

    file = request.FILES.get("file")

    if not file:
        return Response({"error": "No file uploaded"}, status=400)

    tenant = request.tenant

    key = tenant_document_path(tenant.id, file.name)

    s3_client = S3Client()
    s3_client.upload_file(file, key, file.content_type)

    document = Document.objects.create(
        name=file.name,
        s3_key=key,
        file_type=file.content_type,
        file_size=file.size,
        uploaded_by=request.user,
        status="uploaded"
    )
    process_document.delay(document.id, request.tenant.schema_name)

    return Response({
        "message": "File uploaded successfully",
        "document_id": document.id
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_download_url(request, tenant_slug=None):
    document_id = request.GET.get("document_id")
    print(document_id)
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return Response({"error": "Document not found"}, status=404)
    
    if document.status != "ready":
        return Response({"error" : "Document not ready to be downloaded"}, status=400)

    s3_client = S3Client()
    download_url = s3_client.generate_download_url(document.s3_key)

    return Response({
        "download_url": download_url,
        "filename": document.name
    })

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_document(request, tenant_slug=None):
    document_id = request.GET.get("document_id")

    if not document_id:
        return Response({"error": "document_id required"}, status=400)

    try:
        document = Document.objects.get(id=int(document_id))
    except Document.DoesNotExist:
        return Response({"error": "Document not found"}, status=404)

    # Optional: check ownership or permission
    if document.uploaded_by != request.user:
        return Response({"error": "Unauthorized"}, status=403)

    # Delete from S3
    # s3_client = S3Client()
    # try:
    #     s3_client.client.delete_object(Bucket=s3_client.bucket, Key=document.s3_key)
    # except Exception as e:
    #     # Log error, but continue to delete DB record
    #     print(f"S3 deletion error: {e}")

    # Delete from DB
    document.delete()
    DocumentChunk.objects.filter(document_id=document_id).delete()

    return Response({"message": "Document and its chunks deleted successfully"}, status=200)

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_document(request, tenant_slug=None):
    """
    Update document metadata or replace file.
    Request body:
        - document_id (required)
        - name (optional)
        - status (optional)
        - file (optional) -> new file to replace existing
    """
    document_id = request.data.get("document_id")
    if not document_id:
        return Response({"error": "document_id required"}, status=400)

    try:
        document = Document.objects.get(id=int(document_id))
    except Document.DoesNotExist:
        return Response({"error": "Document not found"}, status=404)

    if document.uploaded_by != request.user:
        return Response({"error": "Unauthorized"}, status=403)

    s3_client = S3Client()

    # --- Replace file if provided ---
    new_file = request.FILES.get("file")
    if new_file:
        # Delete old file from S3
        try:
            s3_client.client.delete_object(Bucket=s3_client.bucket, Key=document.s3_key)
        except Exception as e:
            print(f"S3 deletion error: {e}")

        # Upload new file
        tenant = request.tenant
        new_key = tenant_document_path(tenant.id, new_file.name)
        s3_client.upload_file(new_file, new_key, new_file.content_type)

        # Update document fields
        document.s3_key = new_key
        document.file_type = new_file.content_type
        document.file_size = new_file.size
        document.name = new_file.name  # optionally update name to match file

        # Optionally reset status if needed
        document.status = "uploaded"
        DocumentChunk.objects.filter(document_id=document_id).delete()

        # Bump the content version so any semantic-cache answers derived from the
        # old file are invalidated (see rag.processors.semantic_cache.
        # compute_knowledge_version). An explicit `version` in the request below
        # still overrides this if provided.
        document.version = (document.version or 0) + 1

        # Optionally trigger background processing again
        process_document.delay(document.id, tenant.schema_name)

    # --- Update metadata ---
    name = request.data.get("name")
    version = request.data.get("version")
    print(request.data)
    if name:
        document.name = name

    if version is not None:
        try:
            document.version = int(version)
        except ValueError:
            return Response({"error" : "Invalid version"}, status=status.HTTP_400_BAD_REQUEST)

    document.save()

    serializer = DocumentSerializer(document)
    return Response(
        {"message": "Document updated successfully", "document": serializer.data},
        status=status.HTTP_200_OK
    )