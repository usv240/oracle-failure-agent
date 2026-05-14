"""Gemini client using google-genai SDK — Vertex AI with API key fallback."""
from google import genai
from google.genai import types
from backend.config import settings
import logging

logger = logging.getLogger(__name__)

_vertex_client = None
_api_key_client = None


def _get_vertex_client() -> genai.Client:
    global _vertex_client
    if _vertex_client is None:
        _vertex_client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_PROJECT_ID,
            location=settings.GOOGLE_LOCATION,
        )
    return _vertex_client


def _get_api_key_client() -> genai.Client:
    global _api_key_client
    if _api_key_client is None:
        _api_key_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _api_key_client


async def generate(prompt: str) -> str:
    try:
        client = _get_vertex_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        return response.text
    except Exception as e:
        logger.warning("Vertex AI failed (%s), falling back to API key", e)
        client = _get_api_key_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        return response.text


async def generate_json(prompt: str) -> str:
    """Ask Gemini for a JSON response."""
    config = types.GenerateContentConfig(response_mime_type="application/json")
    try:
        client = _get_vertex_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text
    except Exception as e:
        logger.warning("Vertex AI failed (%s), falling back to API key", e)
        client = _get_api_key_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text


async def embed(text: str) -> list[float]:
    """Generate a 768-dim embedding using text-embedding-004 via Vertex AI."""
    try:
        client = _get_vertex_client()
        response = client.models.embed_content(
            model="text-embedding-004",
            contents=text,
        )
        return response.embeddings[0].values
    except Exception as e:
        logger.warning("Vertex AI embed failed (%s), falling back to API key", e)
        client = _get_api_key_client()
        response = client.models.embed_content(
            model="text-embedding-004",
            contents=text,
        )
        return response.embeddings[0].values


async def generate_json_fast(prompt: str) -> str:
    """Ask Gemini for a JSON response with thinking disabled (fast scoring path)."""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    try:
        client = _get_vertex_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text
    except Exception as e:
        logger.warning("Vertex AI fast call failed (%s), falling back to API key", e)
        client = _get_api_key_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return response.text
