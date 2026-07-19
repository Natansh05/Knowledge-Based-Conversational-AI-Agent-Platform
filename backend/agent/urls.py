from django.urls import include,path
from .views import AgentView, TagView, AgentsView
urlpatterns = [
    path('',AgentsView.as_view(),name='agents' ),
    path('<int:agent_id>/',AgentView.as_view(),name="agent"),
    path('tags/', TagView.as_view(),name='tags'),
]
