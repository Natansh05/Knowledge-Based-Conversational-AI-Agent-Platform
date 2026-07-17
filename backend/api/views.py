from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.decorators import api_view, permission_classes
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Avg, Q
from django.db.models.functions import TruncDay
from collections import Counter, defaultdict
from itertools import chain

from users.serializer import UserSerializer
from chat.models import ChatSession, ChatMessage
from documents.models import Document, DocumentChunk
from users.models import User


class CookieTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        # Call the original view to get token data
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            # Update last_login for the authenticated user
            user = self.user if hasattr(self, 'user') else request.user

            # In SimpleJWT, self.user may not exist, so extract from serializer
            if hasattr(self, 'serializer_class'):
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                user = serializer.user

            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])

            # Extract tokens
            access = response.data.get("access")
            refresh = response.data.get("refresh")

            # Return response with cookies
            res = Response({"detail": "Login successful"})

            res.set_cookie(
                key="access_token",
                value=access,
                httponly=True,
                secure=False,  # True in production (HTTPS)
                samesite="Lax",
                max_age = 60 * 11,  # 30 minutes
            )

            res.set_cookie(
                key="refresh_token",
                value=refresh,
                httponly=True,
                secure=False, # True in production (HTTPS)
                samesite="Lax",
                max_age = 60 * 60 * 24 * 7,  # 7 days
            )

            return res

        return response
    

class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh = request.COOKIES.get("refresh_token")

        if not refresh:
            return Response({"detail": "No refresh token"}, status=401)

        request.data["refresh"] = refresh
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            access = response.data.get("access")

            res = Response({"detail": "Token refreshed"})

            res.set_cookie(
                key="access_token",
                value=access,
                httponly=True,
                secure=False,
                samesite="Lax",
            )

            return res

        return response
    

class LogoutView(APIView):

    def post(self, request,tenant_slug=''):
        res = Response({"detail": "Logged out"})
        res.delete_cookie("access_token")
        res.delete_cookie("refresh_token")
        return res
    
class ApiRootView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request,tenant_slug=''):
        return Response({
            "message": f"Welcome to the API root for tenant {request.tenant}. Use /token/ to obtain JWT tokens."
        })
    
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug=''):
        user = request.user
        serializer = UserSerializer(user)
        return Response(serializer.data)
    
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_metrics(request, tenant_slug=''):

    with tenant_context(request.tenant):

        # -------- Usage --------
        total_chats = ChatSession.objects.count()
        total_questions = ChatMessage.objects.filter(role="user").count()
        total_users = User.objects.count()

        seven_days_ago = timezone.now() - timedelta(days=7)
        active_users = (
            ChatSession.objects
            .filter(created_at__gte=seven_days_ago)
            .values("user")
            .distinct()
            .count()
        )

        # -------- Engagement --------
        avg_messages_per_chat = (
            ChatSession.objects
            .annotate(msg_count=Count("messages"))
            .aggregate(avg=Avg("msg_count"))["avg"]
        )

        # Chats per day — last 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)
        chats_per_day_qs = (
            ChatSession.objects
            .filter(created_at__gte=thirty_days_ago)
            .annotate(day=TruncDay("created_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        chats_per_day = [
            {"date": row["day"].date().isoformat(), "chats": row["count"]}
            for row in chats_per_day_qs
        ]

        # Avg questions per chat per agent (two-step: Django can't Avg an annotated Count)
        _session_qs = (
            ChatSession.objects
            .annotate(user_msg_count=Count("messages", filter=Q(messages__role="user")))
            .values("agent_id", "agent__name", "user_msg_count")
        )
        _agent_data = defaultdict(lambda: {"name": "", "total": 0, "count": 0})
        for row in _session_qs:
            aid = row["agent_id"]
            _agent_data[aid]["name"] = row["agent__name"]
            _agent_data[aid]["total"] += row["user_msg_count"]
            _agent_data[aid]["count"] += 1
        questions_per_agent = sorted(
            [
                {
                    "agent_id": aid,
                    "agent__name": d["name"],
                    "avg_questions": round(d["total"] / d["count"], 1) if d["count"] else 0.0,
                }
                for aid, d in _agent_data.items()
            ],
            key=lambda x: x["avg_questions"],
            reverse=True,
        )

        # -------- Agent Usage --------
        agent_usage = list(
            ChatSession.objects
            .values("agent_id", "agent__name")
            .annotate(chat_count=Count("id"))
            .order_by("-chat_count")[:5]
        )

        # -------- Knowledge Base --------
        total_documents = Document.objects.count()
        total_chunks = DocumentChunk.objects.count()

        avg_chunks_per_doc_raw = (
            Document.objects
            .annotate(chunk_count=Count("chunks"))
            .aggregate(avg=Avg("chunk_count"))["avg"]
        )
        avg_chunks_per_doc = round(float(avg_chunks_per_doc_raw), 1) if avg_chunks_per_doc_raw else 0.0

        # -------- RAG Quality (chunk-tracking analytics) --------
        assistant_messages = list(
            ChatMessage.objects
            .filter(role="assistant")
            .values("retrieved_chunk_ids", "similarity_scores")
        )

        total_assistant = len(assistant_messages)
        messages_with_context = [m for m in assistant_messages if m["retrieved_chunk_ids"]]
        success_count = len(messages_with_context)

        success_rate = (
            round(success_count / total_assistant * 100, 1)
            if total_assistant > 0 else 0.0
        )

        all_scores = list(chain.from_iterable(
            m["similarity_scores"]
            for m in messages_with_context
            if m["similarity_scores"]
        ))
        avg_confidence = round(sum(all_scores) / len(all_scores), 4) if all_scores else 0.0

        knowledge_gap_count = ChatMessage.objects.filter(
            role="assistant", retrieved_chunk_ids=[]
        ).count()

        # -------- Document-level analytics --------
        # Build chunk_id → doc_id and doc_id → name lookups
        chunk_id_counter = Counter(
            cid
            for m in messages_with_context
            for cid in m["retrieved_chunk_ids"]
        )

        retrieved_ids = list(chunk_id_counter.keys())
        chunk_to_doc = dict(
            DocumentChunk.objects
            .filter(id__in=retrieved_ids)
            .values_list("id", "document_id")
        )

        doc_id_to_name = dict(
            Document.objects
            .filter(id__in=set(chunk_to_doc.values()))
            .values_list("id", "name")
        )

        # Aggregate chunk hits per document
        doc_retrieval_counts = defaultdict(int)
        for chunk_id, count in chunk_id_counter.items():
            doc_id = chunk_to_doc.get(chunk_id)
            if doc_id:
                doc_retrieval_counts[doc_id] += count

        most_used_documents = sorted(
            [
                {
                    "document_id": doc_id,
                    "name": doc_id_to_name.get(doc_id, "Unknown"),
                    "retrieval_count": count,
                }
                for doc_id, count in doc_retrieval_counts.items()
            ],
            key=lambda x: x["retrieval_count"],
            reverse=True,
        )[:10]

        # Questions answered per document (one answer can reference multiple docs)
        doc_question_counts = defaultdict(int)
        for m in messages_with_context:
            docs_in_message = set()
            for cid in m["retrieved_chunk_ids"]:
                doc_id = chunk_to_doc.get(cid)
                if doc_id:
                    docs_in_message.add(doc_id)
            for doc_id in docs_in_message:
                doc_question_counts[doc_id] += 1

        questions_per_document = sorted(
            [
                {
                    "document_id": doc_id,
                    "name": doc_id_to_name.get(doc_id, "Unknown"),
                    "question_count": count,
                }
                for doc_id, count in doc_question_counts.items()
            ],
            key=lambda x: x["question_count"],
            reverse=True,
        )[:10]

        # Coverage and unused documents
        all_doc_ids = set(Document.objects.values_list("id", flat=True))
        referenced_doc_ids = set(doc_retrieval_counts.keys())
        coverage_pct = (
            round(len(referenced_doc_ids) / len(all_doc_ids) * 100, 1)
            if all_doc_ids else 0.0
        )

        unused_doc_ids = all_doc_ids - referenced_doc_ids
        unused_documents = list(
            Document.objects
            .filter(id__in=unused_doc_ids)
            .values("id", "name")[:20]
        )

    return Response({
        "usage": {
            "total_chats": total_chats,
            "total_questions": total_questions,
            "total_users": total_users,
            "active_users_7d": active_users,
        },
        "knowledge_base": {
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "avg_chunks_per_document": avg_chunks_per_doc,
            "coverage_pct": coverage_pct,
            "most_used_documents": most_used_documents,
            "questions_per_document": questions_per_document,
            "unused_documents": unused_documents,
        },
        "engagement": {
            "avg_messages_per_chat": avg_messages_per_chat,
            "chats_per_day": chats_per_day,
            "questions_per_agent": questions_per_agent,
        },
        "rag_quality": {
            "success_rate_pct": success_rate,
            "avg_confidence": avg_confidence,
            "knowledge_gap_count": knowledge_gap_count,
        },
        "agent_usage": agent_usage,
    })