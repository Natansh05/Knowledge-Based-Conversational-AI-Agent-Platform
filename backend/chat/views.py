from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rag.processors.retriever import get_history
from .models import ChatSession, ChatMessage
from .serializer import ChatSessionSerializer, ChatMessageSerializer
from agent.models import Agent
from agent.services.agent_service import generate_agent_answer


from rest_framework.exceptions import NotFound

class CreateChatSession(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_slug=''):
        agent_id = request.data.get("agent_id")
        # print(request.data)
        if not agent_id:
            return Response({"error": "agent_id is required"}, status=400)

        try:
            agent = Agent.objects.get(
                id=agent_id,
            )
        except Agent.DoesNotExist:
            raise NotFound("Agent not found")

        chat = ChatSession.objects.create(
            user=request.user,
            agent=agent
        )

        return Response({"id": chat.id})
    
class ListChats(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug=''):

        agent_id = request.query_params.get("agent_id")
        print(agent_id)

        chats = ChatSession.objects.filter(
            user=request.user,
            agent=agent_id
        ).order_by("-created_at")

        serializer = ChatSessionSerializer(chats, many=True)

        return Response(serializer.data)
    

class ChatMessages(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, chat_id, tenant_slug=''):
        chat = ChatSession.objects.get(id=chat_id)

        messages = ChatMessage.objects.filter(
            chat_session=chat
        ).order_by("created_at")

        serializer = ChatMessageSerializer(messages, many=True)

        return Response({
            "chat_id": chat.id,
            "chat_title": chat.title,
            "agent_id": chat.agent.id,
            "messages": serializer.data
        })
    

class SendMessage(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, chat_id, tenant_slug=''):

        message = request.data.get("message")

        chat = ChatSession.objects.get(id=chat_id)
        if not chat.title:
            chat.title = message[:30]
            chat.save()

        # Save user message
        ChatMessage.objects.create(
            chat_session=chat,
            role="user",
            content=message
        )

        history = get_history(chat)
        result = generate_agent_answer(agent_id=chat.agent.id, question=message, history=history)

        answer = result.get("answer", "")
        chunk_ids = result.get("chunk_ids", [])
        chunk_scores = result.get("chunk_scores", [])

        # Save assistant response with chunk tracking
        ChatMessage.objects.create(
            chat_session=chat,
            role="assistant",
            content=answer,
            retrieved_chunk_ids=chunk_ids,
            similarity_scores=chunk_scores,
        )

        return Response({
            "answer": answer
        })  