"""AI Middleware — request classification and response summarization."""

from __future__ import annotations

import logging
from typing import Any

from nexus.core.middleware import Middleware
from nexus.core.requests import Request
from nexus.core.responses import Response

logger = logging.getLogger("nexus.ai")


class AIMiddleware(Middleware):
    """
    AI-powered middleware that can:
    - Classify incoming requests by intent
    - Summarize/annotate outgoing responses

    Usage::

        ai = AIEngine(provider="openai", model="gpt-4o-mini", api_key="sk-...")
        app.add_middleware(AIMiddleware(ai, classify=True, summarize=False))
    """

    def __init__(
        self,
        ai: Any,  # AIEngine
        *,
        classify: bool = False,
        summarize: bool = False,
        classification_header: str = "x-nexus-intent",
    ) -> None:
        self.ai = ai
        self.classify = classify
        self.summarize = summarize
        self.classification_header = classification_header

    async def before_request(self, request: Request) -> None:
        if not self.classify:
            return None
        try:
            body = await request.text()
            prompt = (
                f"Classify the intent of this HTTP {request.method} request to {request.path}. "
                f"Body (if POST): {body[:200]}. "
                "Reply with ONE word intent label only."
            )
            result = await self.ai.generate(prompt)
            request._scope["ai_intent"] = result.content.strip()
            logger.debug("AI classified request as: %s", result.content.strip())
        except Exception as exc:
            logger.debug("AI classification skipped: %s", exc)
        return None

    async def after_response(self, request: Request, response: Response) -> Response:
        if not self.summarize:
            return response
        try:
            if hasattr(response, "body") and len(response.body) > 100:

                body_str = response.body[:500].decode(errors="ignore")
                prompt = f"Summarize this API response in 10 words: {body_str}"
                result = await self.ai.generate(prompt)
                response._headers["x-nexus-summary"] = result.content.strip()[:150]
        except Exception as exc:
            logger.debug("AI summarization skipped: %s", exc)
        return response
