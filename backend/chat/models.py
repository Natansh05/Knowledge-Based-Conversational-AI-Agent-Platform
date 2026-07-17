from django.db import models
from agent.models import Agent
from users.models import User

# Create your models here.
class ChatSession(models.Model):
    id = models.BigAutoField(primary_key=True)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="chat_session")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_session")
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.user.username})"
    
class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]

    id = models.BigAutoField(primary_key=True)  # optional, Django adds id automatically
    chat_session = models.ForeignKey(
        'ChatSession',
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    retrieved_chunk_ids = models.JSONField(default=list, blank=True)
    similarity_scores = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."