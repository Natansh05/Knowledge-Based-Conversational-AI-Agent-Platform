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
from django.db.models import Count, Avg

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

        # -------- Knowledge Base --------

        total_documents = Document.objects.count()

        total_chunks = DocumentChunk.objects.count()

        # -------- Engagement --------

        avg_messages_per_chat = (
            ChatSession.objects
            .annotate(msg_count=Count("messages"))
            .aggregate(avg=Avg("msg_count"))["avg"]
        )

        # -------- Agent Usage --------

        agent_usage = (
            ChatSession.objects
            .values("agent_id","agent__name")
            .annotate(chat_count=Count("id"))
            .order_by("-chat_count")[:5]
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
            "total_chunks": total_chunks
        },
        "engagement": {
            "avg_messages_per_chat": avg_messages_per_chat
        },
        "agent_usage": list(agent_usage)
    })