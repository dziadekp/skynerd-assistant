"""
Ollama API Client

Async client for local Gemma 3 12B model via Ollama.
"""

import logging
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Async client for Ollama API.

    Uses the local Gemma 3 12B model for AI-powered responses.
    """

    def __init__(self, base_url: str, model: str = "gemma3:12b", timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        """Create the HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def is_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            if not self._client:
                await self.connect()

            response = await self._client.get("/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                # Check if our model is available
                return any(self.model in m for m in models)
            return False
        except Exception as e:
            logger.debug(f"Ollama not available: {e}")
            return False

    async def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: list[dict[str, str]] | None = None,
    ) -> str:
        """
        Send a chat message and get a response.

        Args:
            prompt: The user's message
            system_prompt: Optional system prompt for context
            context: Optional conversation history

        Returns:
            The model's response text
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        messages = []

        # Add system prompt if provided
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Add conversation history
        if context:
            messages.extend(context)

        # Add current user message
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama HTTP error: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise

    async def chat_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream a chat response token by token.

        Args:
            prompt: The user's message
            system_prompt: Optional system prompt for context
            context: Optional conversation history

        Yields:
            Response tokens as they arrive
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if context:
            messages.extend(context)

        messages.append({"role": "user", "content": prompt})

        async with self._client.stream(
            "POST",
            "/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    import json
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content

    async def generate(self, prompt: str) -> str:
        """
        Simple text generation without chat format.

        Args:
            prompt: The prompt to complete

        Returns:
            Generated text
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            response = await self._client.post(
                "/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as e:
            logger.error(f"Ollama generate error: {e}")
            raise


# System prompts for different use cases
ASSISTANT_SYSTEM_PROMPT = """You are SkyNerd, a helpful personal assistant for a busy professional at an accounting practice.

Your personality:
- Professional but friendly
- Concise and action-oriented
- Proactive in offering solutions
- Occasionally witty but never at the expense of clarity

You help with:
- Email triage and prioritization
- Task management and scheduling
- Client relationship reminders
- Calendar awareness
- General productivity questions

When providing information:
- Be concise - busy professionals don't have time for lengthy responses
- Lead with the most important information
- Offer actionable next steps when appropriate
- If you don't know something, say so clearly

Remember: Your user is a professional at an accounting firm who values efficiency."""

QUERY_SYSTEM_PROMPT = """You are a helpful AI assistant answering questions about the user's work data.

Based on the context provided, answer the user's question accurately and concisely.
If the context doesn't contain enough information, say so.

Keep responses brief and actionable."""
