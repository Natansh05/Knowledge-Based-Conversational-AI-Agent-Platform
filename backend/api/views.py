from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from users.serializer import UserSerializer

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