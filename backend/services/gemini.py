"""
Gemini client — Gemini 3 as primary for ALL generation tasks (scoring, reasoning, agents).

Primary chain (tried in order until one succeeds):
  gemini-3-flash-preview → gemini-3.5-flash → gemini-3.1-flash-lite → gemini-3.1-flash-lite-preview

Vertex AI 2.5 Flash is the fallback only when ALL Gemini 3 models are exhausted.
Embeddings: text-embedding-004 via Vertex AI (no Gemini 3 embedding model available).
"""
from google import genai
from google.genai import types
from backend.config import settings
import logging

logger = logging.getLogger(__name__)

# Gemini 3 models tried in order — primary from ADK_MODEL env var, rest are hardcoded fallbacks
_GEMINI3_FALLBACKS = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
]
_GEMINI3_CHAIN = [settings.ADK_MODEL] + [m for m in _GEMINI3_FALLBACKS if m != settings.ADK_MODEL]

# Tracks which Gemini 3 model is currently active (for /api/health reporting)
active_gemini3_model: str = _GEMINI3_CHAIN[0]

_vertex_client = None
_api_key_client = None

# Set to a reason string when any call falls back to Vertex AI 2.5.
# stream.py reads + clears this after each scoring batch to emit a terminal event.
last_fallback_reason: str | None = None


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


def _try_gemini3(call_fn, config=None):
    """
    Try each Gemini 3 model in the chain until one succeeds.
    Updates active_gemini3_model on success. Returns (response, model_used).
    Raises the last exception if all models fail.
    """
    global active_gemini3_model
    client = _get_api_key_client()
    last_exc = None
    for model in _GEMINI3_CHAIN:
        try:
            kwargs = {"model": model, "contents": None}  # contents injected by caller
            response = call_fn(client, model, config)
            active_gemini3_model = model
            return response
        except Exception as e:
            logger.warning("Gemini 3 model %s failed (%s): %s", model, type(e).__name__, e)
            last_exc = e
    raise last_exc


def _count_gemini_call() -> None:
    """Fire-and-forget telemetry counter for any Gemini/Vertex/embedding call."""
    try:
        from backend.services import telemetry
        telemetry.inc("gemini_call")
    except Exception:
        pass


async def generate(prompt: str) -> str:
    """Generate text. Tries all Gemini 3 models, falls back to Vertex AI 2.5."""
    _count_gemini_call()
    global active_gemini3_model, last_fallback_reason
    try:
        client = _get_api_key_client()
        last_exc = None
        for model in _GEMINI3_CHAIN:
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                active_gemini3_model = model
                return response.text
            except Exception as e:
                logger.warning("Gemini 3 %s generate failed: %s", model, e)
                last_exc = e
        raise last_exc
    except Exception as e:
        last_fallback_reason = "All Gemini 3 models exhausted — switching to Vertex AI 2.5 Flash"
        logger.warning("Gemini 3 generate chain failed, falling back to Vertex AI 2.5: %s", e)
        client = _get_vertex_client()
        response = client.models.generate_content(model=settings.GEMINI_MODEL, contents=prompt)
        return response.text


async def generate_json(prompt: str) -> str:
    """JSON generation. Tries all Gemini 3 models, falls back to Vertex AI 2.5."""
    _count_gemini_call()
    global active_gemini3_model, last_fallback_reason
    config3 = types.GenerateContentConfig(response_mime_type="application/json")
    try:
        client = _get_api_key_client()
        last_exc = None
        for model in _GEMINI3_CHAIN:
            try:
                response = client.models.generate_content(model=model, contents=prompt, config=config3)
                active_gemini3_model = model
                return response.text
            except Exception as e:
                logger.warning("Gemini 3 %s generate_json failed: %s", model, e)
                last_exc = e
        raise last_exc
    except Exception as e:
        last_fallback_reason = f"Gemini 3 quota exhausted ({type(e).__name__}) — switching to Vertex AI 2.5 Flash"
        logger.warning("Gemini 3 generate_json chain failed, falling back to Vertex AI 2.5: %s", e)
        client = _get_vertex_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL, contents=prompt, config=config3)
        return response.text


_voyage_client = None

def _get_voyage_client():
    global _voyage_client
    if _voyage_client is None:
        import voyageai
        from backend.config import settings
        _voyage_client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)
    return _voyage_client


def _adjust_dimension(vector: list[float], target_dim: int = 1024) -> list[float]:
    if len(vector) < target_dim:
        return vector + [0.0] * (target_dim - len(vector))
    elif len(vector) > target_dim:
        return vector[:target_dim]
    return vector


async def embed(text: str, input_type: str = "query") -> list[float]:
    """
    Generate 1024-dim embedding via MongoDB Voyage AI (voyage-4-large).
    input_type='document' when indexing patterns, 'query' when searching.
    Falls back to Google text-embedding-004 if VOYAGE_API_KEY not configured.
    """
    _count_gemini_call()
    from backend.config import settings
    if settings.VOYAGE_API_KEY:
        try:
            import asyncio as _asyncio
            client = _get_voyage_client()
            result = await _asyncio.wait_for(
                client.embed(texts=[text], model=settings.VOYAGE_MODEL, input_type=input_type),
                timeout=15.0,
            )
            return _adjust_dimension(result.embeddings[0])
        except Exception as e:
            logger.warning("Voyage AI embed failed (%s), falling back to %s", e, settings.EMBED_FALLBACK_MODEL)

    # Fallback: Google embedding via Vertex AI
    try:
        client = _get_vertex_client()
        response = client.models.embed_content(model=settings.EMBED_FALLBACK_MODEL, contents=text)
        return _adjust_dimension(response.embeddings[0].values)
    except Exception as e:
        logger.warning("Vertex AI embed failed (%s), falling back to API key client", e)
        client = _get_api_key_client()
        response = client.models.embed_content(model=settings.EMBED_FALLBACK_MODEL, contents=text)
        return _adjust_dimension(response.embeddings[0].values)


async def generate_json_fast(prompt: str) -> str:
    """Fast JSON scoring — Gemini 3 API chain primary, Vertex AI 2.5 Flash fallback.
    thinking_budget=0 on both paths for maximum speed."""
    _count_gemini_call()
    global active_gemini3_model, last_fallback_reason
    config_fast = types.GenerateContentConfig(
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    # Primary: Gemini 3 API key chain
    client = _get_api_key_client()
    last_exc = None
    for model in _GEMINI3_CHAIN:
        try:
            response = client.models.generate_content(
                model=model, contents=prompt, config=config_fast)
            active_gemini3_model = model
            return response.text
        except Exception as e:
            logger.warning("Gemini 3 %s fast failed: %s", model, e)
            last_exc = e

    # Fallback: Vertex AI 2.5 Flash
    last_fallback_reason = f"All Gemini 3 models exhausted — switching to Vertex AI 2.5 Flash"
    logger.warning("Gemini 3 fast chain failed, falling back to Vertex AI 2.5: %s", last_exc)
    try:
        client = _get_vertex_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL, contents=prompt, config=config_fast)
        return response.text
    except Exception as e:
        raise e


async def generate_json_reasoned(prompt: str) -> str:
    """Deliberate JSON reasoning — Gemini 3 API chain primary with thinking enabled.
    Used for decision auditing where deeper reasoning improves quality.
    Falls back to Vertex AI 2.5 Flash if all Gemini 3 models are exhausted."""
    _count_gemini_call()
    global active_gemini3_model, last_fallback_reason
    config_think = types.GenerateContentConfig(
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=1024),
    )
    # Primary: Gemini 3 API key chain with thinking
    client = _get_api_key_client()
    last_exc = None
    for model in _GEMINI3_CHAIN:
        try:
            response = client.models.generate_content(
                model=model, contents=prompt, config=config_think)
            active_gemini3_model = model
            return response.text
        except Exception as e:
            logger.warning("Gemini 3 %s reasoned failed: %s", model, e)
            last_exc = e

    # Fallback: Vertex AI 2.5 Flash with thinking
    last_fallback_reason = f"All Gemini 3 models exhausted — switching to Vertex AI 2.5 Flash"
    logger.warning("Gemini 3 reasoned chain failed, falling back to Vertex AI 2.5: %s", last_exc)
    try:
        client = _get_vertex_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL, contents=prompt, config=config_think)
        return response.text
    except Exception as e:
        raise e
