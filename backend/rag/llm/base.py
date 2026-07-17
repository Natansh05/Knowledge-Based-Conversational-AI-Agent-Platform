# rag.llm.base.py
from abc import ABC, abstractmethod
import google.generativeai as genai
from django.conf import settings


class BaseLLMProvider(ABC):

    @abstractmethod
    def generate(self, system_prompt, history, question):
        pass


class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def generate(self, system_prompt, history, question):
        """
        Stateless response generation using Gemini.
        Prevents repetition and re-answering old questions.
        """

        # Correct role mapping
        role_map = {
            "user": "user",
            "assistant": "model"
        }

        formatted_history = [
            {
                "role": role_map.get(msg["role"], "user"),
                "parts": [msg["content"]]
            }
            for msg in history
        ]

        # Strong prompt with strict boundaries
        markdown_prompt = (
            f"{system_prompt}\n\n"

            "STRICT INSTRUCTIONS:\n"
            "- Answer ONLY the latest question.\n"
            "- Do NOT repeat or reference previous questions.\n"
            "- Do NOT summarize chat history.\n"
            "- Ignore any incomplete past queries.\n\n"

            "FORMAT RULES:\n"
            "- Use Markdown.\n"
            "- Use bullet points (-) for lists.\n"
            "- Use numbered lists for steps.\n"
            "- Use headings (##, ###).\n"
            "- Keep answers concise and structured.\n\n"

            f"LATEST QUESTION:\n{question}"
        )

        # Stateless call (NO start_chat)
        response = self.model.generate_content(
            [
                *formatted_history,
                {"role": "user", "parts": [markdown_prompt]}
            ]
        )

        raw_response = response.text if hasattr(response, "text") else str(response)

        return self._force_markdown(raw_response)

    def _force_markdown(self, text: str) -> str:
        """
        Basic post-processing to improve Markdown consistency.
        """
        import re

        # Headings normalization
        text = re.sub(
            r"^(?P<line>[A-Z][^\n]{3,})$",
            r"## \g<line>",
            text,
            flags=re.MULTILINE
        )

        # Normalize numbered lists
        text = re.sub(
            r"^\s*(\d+)\.\s+",
            r"1. ",
            text,
            flags=re.MULTILINE
        )

        # Normalize bullet points
        text = re.sub(
            r"^\s*[*•]\s+",
            "- ",
            text,
            flags=re.MULTILINE
        )

        # Wrap code blocks if needed
        if "```" not in text and ("def " in text or "class " in text):
            text = f"```\n{text}\n```"

        return text