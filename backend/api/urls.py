from django.urls import path
from .views import (
    CookieTokenObtainPairView,
    CookieTokenRefreshView,
    LogoutView,
    ApiRootView,
    MeView,
    dashboard_metrics
)
from documents.views import get_download_url, getAllDocuments, upload_document, update_document, delete_document
from django.urls import include

urlpatterns = [
    path("token/", CookieTokenObtainPairView.as_view()),
    path("token/refresh/", CookieTokenRefreshView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("", ApiRootView.as_view(), name="api-root"),
    path("me/", MeView.as_view(), name="me"),

    # Document based paths
    path("upload/", upload_document, name="upload-document"),
    path("docs/",getAllDocuments,name="all-docs"),
    path("docs/download/",get_download_url, name='download-document'),
    path("docs/update/",update_document, name='update-document'),
    path("docs/delete/",delete_document, name='delete-document'),

    # Agent based paths
    path('agent/', include('agent.urls')),

    # Chat based urls
    path('chat/', include('chat.urls')),

    # Metrics
    path("metrics/", dashboard_metrics, name="dashboard-metrics"),
]