"""
bot/utils/ai_helper.py
AI utility functions for easy access across services with comprehensive logging
"""

import asyncio
import logging
from typing import Any

from ..services.ai_service import AIService
from ..services.logging_service import LogLevel

logger = logging.getLogger(__name__)

# Global AI service instance
_ai_service: AIService | None = None
_ai_service_instance: AIService | None = globals().get("_ai_service_instance")  # type: ignore


async def init_ai_service(embed_logger=None) -> AIService:
    """
    Initialize the singleton AIService if not already initialized,
    and return the live instance.
    """
    global _ai_service_instance
    if _ai_service_instance is None:
        svc = AIService()
        await svc.setup(embed_logger)
        _ai_service_instance = svc
        if embed_logger:
            await embed_logger.log_custom(
                service="AI Helper",
                title="AI Service Initialized",
                description="AI helper functions are now available",
                level=embed_logger.__class__.LogLevel.SUCCESS,
                fields={"Service": "AI Helper", "Provider": "Groq", "Status": "✅ Ready"},
            )
    return _ai_service_instance


def get_ai_service() -> AIService | None:
    """Return the live AIService instance (if initialized)."""
    global _ai_service_instance
    return _ai_service_instance


def get_ai_model_registry() -> dict[str, dict[str, Any]]:
    """
    Expose the model registry to cogs for autocomplete and display.
    Returns an empty dict if the service is not ready yet.
    """
    svc = get_ai_service()
    return svc.get_model_registry() if svc else {}


def set_ai_default_model(model_key: str) -> str:
    """
    Set the default model key (friendly key from registry) OR a raw API name.
    Returns the value now stored as default.
    """
    svc = get_ai_service()
    if not svc:
        return model_key
    # If it's a known registry key, store that; otherwise store raw (advanced usage).
    if model_key in svc.get_model_registry():
        svc.default_model = model_key
    else:
        # allow raw api name as an escape hatch
        svc.default_model = model_key
    return svc.default_model


def get_ai_config() -> dict[str, Any]:
    """
    Small snapshot of AI configuration for admin display.
    """
    svc = get_ai_service()
    if not svc:
        return {"service_status": "inactive"}

    reg = svc.get_model_registry()
    current_key = svc.default_model
    info = reg.get(
        current_key,
        {
            "display": current_key,
            "api_name": svc.resolve_model_name(current_key),
            "ctx": None,
            "tps": None,
            "in_price": None,
            "out_price": None,
        },
    )
    return {
        "provider": "Groq",
        "service_status": "active" if svc.groq_api_key else "inactive",
        "default_model_key": current_key,
        "default_model_display": info.get("display", current_key),
        "default_model_api": info.get("api_name", svc.resolve_model_name(current_key)),
        "rate_limit_rpm": svc.requests_per_minute,
        "base_url": svc.groq_base_url,
        "available_models": [
            {
                "key": k,
                "display": v["display"],
                "api_name": v["api_name"],
                "ctx": v.get("ctx"),
                "tps": v.get("tps"),
                "in_price": v.get("in_price"),
                "out_price": v.get("out_price"),
            }
            for k, v in reg.items()
        ],
    }


# Convenience functions for common AI operations


async def ask_ai(
    prompt: str,
    system_context: str | None = None,
    max_length: int = 500,
    creativity: float = 0.7,
) -> str:
    """
    Quick AI prompt - most common use case

    Args:
        prompt: What to ask the AI
        system_context: Context/instructions for AI
        max_length: Maximum response length
        creativity: 0 (focused) to 1 (creative)

    Returns:
        AI response as string
    """
    service = get_ai_service()
    if not service:
        logger.error("AI service not initialized for ask_ai request")
        raise Exception("AI service not initialized")

    try:
        result = await service.quick_prompt(
            prompt=prompt,
            system_prompt=system_context,
            max_tokens=max_length,
            temperature=creativity,
        )

        # Log successful request
        if service.embed_logger:
            await service.embed_logger.log_custom(
                service="AI Helper",
                title="AI Question Processed",
                description="AI helper function completed successfully",
                level=LogLevel.SUCCESS,
                fields={
                    "Function": "ask_ai",
                    "Prompt Length": f"{len(prompt)} chars",
                    "Response Length": f"{len(result)} chars",
                    "System Context": "Yes" if system_context else "No",
                    "Creativity": str(creativity),
                },
            )

        return result
    except Exception as e:
        logger.error(f"ask_ai failed: {e}")
        if service.embed_logger:
            await service.embed_logger.log_error(
                service="AI Helper", error=e, context=f"ask_ai failed - prompt: {prompt[:50]}..."
            )
        raise


async def moderate_message(content: str) -> dict[str, Any]:
    """
    Check if message content is appropriate

    Args:
        content: Message content to check

    Returns:
        Dict with moderation results:
        {
            "is_appropriate": bool,
            "violations": list,
            "severity": str,
            "reason": str
        }
    """
    service = get_ai_service()
    if not service:
        logger.warning("AI service not available for moderation")
        # Return safe default if service unavailable
        return {
            "is_appropriate": True,
            "violations": [],
            "severity": "low",
            "reason": "AI service unavailable",
        }

    try:
        result = await service.moderate_content(content)

        # Log moderation request
        if service.embed_logger and not result.get("is_appropriate", True):
            await service.embed_logger.log_custom(
                service="AI Helper",
                title="Content Moderation Alert",
                description="AI helper flagged inappropriate content",
                level=LogLevel.WARNING,
                fields={
                    "Function": "moderate_message",
                    "Content Length": f"{len(content)} chars",
                    "Is Appropriate": str(result.get("is_appropriate", True)),
                    "Severity": result.get("severity", "unknown"),
                    "Violations": ", ".join(result.get("violations", [])),
                },
            )

        return result
    except Exception as e:
        logger.error(f"moderate_message failed: {e}")
        if service and service.embed_logger:
            await service.embed_logger.log_error(
                service="AI Helper",
                error=e,
                context=f"moderate_message failed - content length: {len(content)}",
            )
        # Return safe default on error
        return {
            "is_appropriate": True,
            "violations": [],
            "severity": "low",
            "reason": f"Moderation failed: {e}",
        }


async def translate_message(text: str, to_language: str = "english") -> str:
    """
    Translate text to specified language

    Args:
        text: Text to translate
        to_language: Target language

    Returns:
        Translated text
    """
    service = get_ai_service()
    if not service:
        logger.error("AI service not available for translation")
        return text  # Return original if service unavailable

    try:
        result = await service.translate_text(text, to_language)

        # Log translation request
        if service.embed_logger:
            await service.embed_logger.log_custom(
                service="AI Helper",
                title="Translation Completed",
                description="AI helper translated text successfully",
                level=LogLevel.SUCCESS,
                fields={
                    "Function": "translate_message",
                    "Original Length": f"{len(text)} chars",
                    "Translated Length": f"{len(result)} chars",
                    "Target Language": to_language,
                    "Status": "✅ Success",
                },
            )

        return result
    except Exception as e:
        logger.error(f"translate_message failed: {e}")
        if service.embed_logger:
            await service.embed_logger.log_error(
                service="AI Helper",
                error=e,
                context=f"translate_message failed - to {to_language}, length: {len(text)}",
            )
        return text  # Return original on error


async def explain_concept(text: str, context: str = "Discord server") -> str:
    """
    Get AI explanation of a concept

    Args:
        text: Text/concept to explain
        context: Context for explanation

    Returns:
        AI explanation
    """
    service = get_ai_service()
    if not service:
        logger.error("AI service not available for explanation")
        return "AI explanation service unavailable"

    try:
        result = await service.explain_text(text, context)

        # Log explanation request
        if service.embed_logger:
            await service.embed_logger.log_custom(
                service="AI Helper",
                title="Concept Explained",
                description="AI helper generated explanation",
                level=LogLevel.SUCCESS,
                fields={
                    "Function": "explain_concept",
                    "Concept": text[:50] + ("..." if len(text) > 50 else ""),
                    "Context": context,
                    "Explanation Length": f"{len(result)} chars",
                    "Status": "✅ Success",
                },
            )

        return result
    except Exception as e:
        logger.error(f"explain_concept failed: {e}")
        if service.embed_logger:
            await service.embed_logger.log_error(
                service="AI Helper",
                error=e,
                context=f"explain_concept failed - concept: {text[:50]}..., context: {context}",
            )
        return f"Explanation failed: {e}"


async def get_suggestions(topic: str, context: str = "") -> str:
    """
    Get AI suggestions for a topic

    Args:
        topic: Topic to get suggestions for
        context: Additional context

    Returns:
        AI suggestions
    """
    service = get_ai_service()
    if not service:
        logger.error("AI service not available for suggestions")
        return "AI suggestion service unavailable"

    try:
        result = await service.generate_suggestion(topic, context)

        # Log suggestion request
        if service.embed_logger:
            await service.embed_logger.log_custom(
                service="AI Helper",
                title="Suggestions Generated",
                description="AI helper provided suggestions",
                level=LogLevel.SUCCESS,
                fields={
                    "Function": "get_suggestions",
                    "Topic": topic[:50] + ("..." if len(topic) > 50 else ""),
                    "Context": context[:50] + ("..." if len(context) > 50 else ""),
                    "Suggestions Length": f"{len(result)} chars",
                    "Status": "✅ Success",
                },
            )

        return result
    except Exception as e:
        logger.error(f"get_suggestions failed: {e}")
        if service.embed_logger:
            await service.embed_logger.log_error(
                service="AI Helper",
                error=e,
                context=f"get_suggestions failed - topic: {topic[:50]}...",
            )
        return f"Suggestions failed: {e}"


async def smart_reply(
    user_message: str,
    conversation_context: list[str] = None,
    bot_personality: str = "helpful Discord bot",
) -> str:
    """
    Generate contextual reply to user message

    Args:
        user_message: User's message
        conversation_context: Previous messages for context
        bot_personality: How the bot should respond

    Returns:
        AI-generated reply
    """
    service = get_ai_service()
    if not service:
        logger.error("AI service not available for smart reply")
        return "I'm having trouble thinking right now, please try again later!"

    # Build context from conversation
    context_text = ""
    if conversation_context:
        context_text = "\n".join(conversation_context[-5:])  # Last 5 messages

    system_prompt = f"""You are a {bot_personality} on a Discord server.
    
    Previous conversation context:
    {context_text}
    
    Respond naturally and helpfully to the user's message. Keep responses concise (1-2 sentences) unless more detail is specifically requested."""

    try:
        result = await service.quick_prompt(
            prompt=user_message, system_prompt=system_prompt, max_tokens=200, temperature=0.7
        )

        # Log smart reply request
        if service.embed_logger:
            await service.embed_logger.log_custom(
                service="AI Helper",
                title="Smart Reply Generated",
                description="AI helper created contextual response",
                level=LogLevel.SUCCESS,
                fields={
                    "Function": "smart_reply",
                    "User Message Length": f"{len(user_message)} chars",
                    "Context Messages": str(len(conversation_context or [])),
                    "Bot Personality": bot_personality,
                    "Reply Length": f"{len(result)} chars",
                    "Status": "✅ Success",
                },
            )

        return result
    except Exception as e:
        logger.error(f"smart_reply failed: {e}")
        if service.embed_logger:
            await service.embed_logger.log_error(
                service="AI Helper",
                error=e,
                context=f"smart_reply failed - message: {user_message[:50]}..., personality: {bot_personality}",
            )
        return "I'm having trouble generating a response right now, please try again later!"


async def analyze_sentiment(text: str) -> dict[str, Any]:
    """
    Analyze emotional sentiment of text

    Args:
        text: Text to analyze

    Returns:
        Sentiment analysis results
    """
    service = get_ai_service()
    if not service:
        logger.error("AI service not available for sentiment analysis")
        return {"sentiment": "neutral", "confidence": 0, "reason": "Service unavailable"}

    system_prompt = """Analyze the emotional sentiment of the given text.
    Respond with JSON format:
    {
        "sentiment": "positive/negative/neutral",
        "confidence": 0.0-1.0,
        "emotions": ["happy", "sad", "angry", etc],
        "reason": "brief explanation"
    }"""

    try:
        response = await service.quick_prompt(
            prompt=f"Analyze sentiment: {text}",
            system_prompt=system_prompt,
            max_tokens=150,
            temperature=0.3,
        )

        import json

        result = json.loads(response)

        # Log sentiment analysis
        if service.embed_logger:
            await service.embed_logger.log_custom(
                service="AI Helper",
                title="Sentiment Analysis Completed",
                description="AI helper analyzed text sentiment",
                level=LogLevel.SUCCESS,
                fields={
                    "Function": "analyze_sentiment",
                    "Text Length": f"{len(text)} chars",
                    "Sentiment": result.get("sentiment", "unknown"),
                    "Confidence": str(result.get("confidence", 0)),
                    "Emotions": ", ".join(result.get("emotions", [])),
                    "Status": "✅ Success",
                },
            )

        return result
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        if service.embed_logger:
            await service.embed_logger.log_error(
                service="AI Helper",
                error=e,
                context=f"analyze_sentiment failed - text length: {len(text)}",
            )
        return {"sentiment": "neutral", "confidence": 0, "reason": "Analysis failed"}


async def generate_welcome_message(
    username: str, server_context: str = "VSB Discord server"
) -> str:
    """
    Generate personalized welcome message

    Args:
        username: New user's name
        server_context: Information about the server

    Returns:
        Personalized welcome message
    """
    service = get_ai_service()
    if not service:
        logger.error("AI service not available for welcome message")
        return f"Welcome to the server, {username}!"

    system_prompt = f"""Generate a friendly welcome message for a new Discord server member.
    Server context: {server_context}
    Keep it warm, welcoming, and informative about what they can do on the server.
    Maximum 2-3 sentences."""

    try:
        result = await service.quick_prompt(
            prompt=f"Welcome message for new user: {username}",
            system_prompt=system_prompt,
            max_tokens=100,
            temperature=0.8,
        )

        # Log welcome message generation
        if service.embed_logger:
            await service.embed_logger.log_custom(
                service="AI Helper",
                title="Welcome Message Generated",
                description="AI helper created personalized welcome message",
                level=LogLevel.SUCCESS,
                fields={
                    "Function": "generate_welcome_message",
                    "Username": username,
                    "Server Context": server_context,
                    "Message Length": f"{len(result)} chars",
                    "Status": "✅ Success",
                },
            )

        return result
    except Exception as e:
        logger.error(f"generate_welcome_message failed: {e}")
        if service.embed_logger:
            await service.embed_logger.log_error(
                service="AI Helper",
                error=e,
                context=f"generate_welcome_message failed - username: {username}, context: {server_context}",
            )
        return f"Welcome to the server, {username}!"


async def improve_text(
    text: str, instruction: str = "make it clearer and more professional"
) -> str:
    """
    Improve text based on instructions

    Args:
        text: Original text
        instruction: How to improve it

    Returns:
        Improved text
    """
    service = get_ai_service()
    if not service:
        logger.error("AI service not available for text improvement")
        return text

    system_prompt = f"Improve the given text by: {instruction}. Only return the improved version."

    try:
        result = await service.quick_prompt(
            prompt=text, system_prompt=system_prompt, max_tokens=len(text) * 2, temperature=0.5
        )

        # Log text improvement
        if service.embed_logger:
            await service.embed_logger.log_custom(
                service="AI Helper",
                title="Text Improved",
                description="AI helper improved text quality",
                level=LogLevel.SUCCESS,
                fields={
                    "Function": "improve_text",
                    "Original Length": f"{len(text)} chars",
                    "Improved Length": f"{len(result)} chars",
                    "Instruction": instruction,
                    "Improvement Ratio": (
                        f"{len(result)/len(text):.2f}x" if len(text) > 0 else "N/A"
                    ),
                    "Status": "✅ Success",
                },
            )

        return result
    except Exception as e:
        logger.error(f"improve_text failed: {e}")
        if service.embed_logger:
            await service.embed_logger.log_error(
                service="AI Helper",
                error=e,
                context=f"improve_text failed - instruction: {instruction}, text length: {len(text)}",
            )
        return text


# Decorator for adding AI capabilities to services
def with_ai_support(func):
    """Decorator to add AI service to function arguments"""

    async def wrapper(*args, **kwargs):
        ai_service = get_ai_service()
        kwargs["ai"] = ai_service
        return await func(*args, **kwargs)

    return wrapper


# Context manager for AI conversations
class AIConversation:
    """Context manager for multi-turn AI conversations"""

    def __init__(self, system_prompt: str = None):
        self.messages = []
        self.system_prompt = system_prompt
        self.service = get_ai_service()
        self.conversation_id = None

    async def __aenter__(self):
        if self.service and self.service.embed_logger:
            import uuid

            self.conversation_id = str(uuid.uuid4())[:8]
            await self.service.embed_logger.log_custom(
                service="AI Helper",
                title="AI Conversation Started",
                description="Multi-turn AI conversation initiated",
                level=self.LogLevel.INFO,
                fields={
                    "Conversation ID": self.conversation_id,
                    "System Prompt": "Yes" if self.system_prompt else "No",
                },
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.service and self.service.embed_logger and self.conversation_id:
            await self.service.embed_logger.log_custom(
                service="AI Helper",
                title="AI Conversation Ended",
                description="Multi-turn AI conversation completed",
                level=self.LogLevel.INFO,
                fields={
                    "Conversation ID": self.conversation_id,
                    "Messages Exchanged": str(len(self.messages)),
                    "Status": "✅ Completed" if exc_type is None else "❌ Error",
                },
            )

    async def say(self, message: str) -> str:
        """Send message and get response"""
        if not self.service:
            return "AI service unavailable"

        # Add user message
        self.messages.append({"role": "user", "content": message})

        # Get AI response
        result = await self.service.generate_response(
            messages=self.messages,
            system_prompt=self.system_prompt,
            max_tokens=500,
            temperature=0.7,
        )

        response = result["content"]

        # Add AI response to conversation
        self.messages.append({"role": "assistant", "content": response})

        # Log conversation turn
        if self.service.embed_logger:
            await self.service.embed_logger.log_custom(
                service="AI Helper",
                title="Conversation Turn",
                description="AI conversation message exchanged",
                level=self.LogLevel.SUCCESS,
                fields={
                    "Conversation ID": self.conversation_id or "unknown",
                    "Turn": str(len(self.messages) // 2),
                    "User Message": f"{len(message)} chars",
                    "AI Response": f"{len(response)} chars",
                    "Total Messages": str(len(self.messages)),
                },
            )

        return response

    def clear_history(self):
        """Clear conversation history"""
        old_count = len(self.messages)
        self.messages = []

        if self.service and self.service.embed_logger:
            asyncio.create_task(
                self.service.embed_logger.log_custom(
                    service="AI Helper",
                    title="Conversation History Cleared",
                    description="AI conversation history was reset",
                    level=self.LogLevel.INFO,
                    fields={
                        "Conversation ID": self.conversation_id or "unknown",
                        "Messages Cleared": str(old_count),
                        "Status": "✅ Cleared",
                    },
                )
            )


# Usage examples for other services:
"""
# In any service, import and use:
from bot.utils.ai_helper import ask_ai, moderate_message, smart_reply

# Simple AI question
answer = await ask_ai("What's the weather like for outdoor events?")

# Content moderation
moderation = await moderate_message(user_message)
if not moderation['is_appropriate']:
    await message.delete()

# Smart reply to user
reply = await smart_reply(
    user_message="I'm confused about the rules",
    bot_personality="helpful moderator bot"
)

# Multi-turn conversation
async with AIConversation("You are a helpful Discord bot") as ai:
    response1 = await ai.say("Hello!")
    response2 = await ai.say("Tell me about this server")
"""
