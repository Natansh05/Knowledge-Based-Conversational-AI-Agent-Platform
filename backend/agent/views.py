from rest_framework.permissions import IsAuthenticated
from .models import Agent, Tag
from .serializer import AgentSerializer, TagSerializer
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404

class AgentsView(APIView):
    def get(self, request, tenant_slug=''):
        agents = Agent.objects.all().order_by("-id")

        # Filters
        search = request.GET.get("search")
        tag_param = request.GET.get("tag")
        tags = [int(t) for t in tag_param.split(",") if t.isdigit()]
        status_filter = request.GET.get("status")

        if search:
            agents = agents.filter(name__icontains=search)

        if tags:
            agents = agents.filter(tags__id__in=tags).distinct()

        if status_filter:
            if status_filter.lower() == "active":
                agents = agents.filter(is_active=True)
            elif status_filter.lower() == "inactive":
                agents = agents.filter(is_active=False)

        agents = agents.distinct()

        # Pagination
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 10))
        paginator = Paginator(agents, page_size)
        page_obj = paginator.get_page(page)

        serializer = AgentSerializer(page_obj.object_list, many=True)

        return Response({
            "results": serializer.data,
            "num_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "total_items": paginator.count
        })
    
    # create new agent with POST request
    def post(self, request, tenant_slug=''):
        print(request.data)
        serializer = AgentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AgentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, agent_id=None, tenant_slug=''):
        if agent_id:
            agent = get_object_or_404(Agent, id=agent_id)
            serializer = AgentSerializer(agent)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    # PATCH: update agent
    def patch(self, request, agent_id, tenant_slug=''):
        print(request.data)
        agent = get_object_or_404(Agent, id=agent_id)
        serializer = AgentSerializer(agent, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # DELETE: delete agent
    def delete(self, request, agent_id, tenant_slug=''):
        agent = get_object_or_404(Agent, id=agent_id)
        agent.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class TagView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug=''):
        tags = Tag.objects.all()
        serializer = TagSerializer(tags, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, tenant_slug=''):
        serializer = TagSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
