"""
Gemini client — Gemini 3 as primary for all generation tasks.

Primary chain (tried in order until one succeeds):
  gemini-3-flash-preview → gemini-3.5-flash → gemini-3.1-flash-lite → gemini-3.1-flash-lite-preview

Vertex AI 2.5 Flash fallback only when ALL Gemini 3 quota is exhausted.
Embeddings: text-embedding-004 via Vertex AI (no Gemini 3 embedding model available).
"""
from google import genai
from google.genai import types
from backend.config import settings
import logging

logger = logging.getLogger(__name__)

# Gemini 3 models tried in order — all via API key (not available on Vertex AI)
_GEMINI3_CHAIN = [
    "gemini-3-flash-preview",        # primary
    "gemini-3.5-flash",              # fallback 1
    "gemini-3.1-flash-lite",         # fallback 2
    "gemini-3.1-flash-lite-preview", # fallback 3
]

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


async def generate(prompt: str) -> str:
    """Generate text. Tries all Gemini 3 models, falls back to Vertex AI 2.5."""
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
        global last_fallback_reason
        last_fallback_reason = f"All Gemini 3 models exhausted — switching to Vertex AI 2.5 Flash"
        logger.warning("Gemini 3 generate chain failed, falling back to Vertex AI 2.5: %s", e)
        client = _get_vertex_client()
        response = client.models.generate_content(model=settings.GEMINI_MODEL, contents=prompt)
        return response.text


async def generate_json(prompt: str) -> str:
    """JSON generation. Tries all Gemini 3 models, falls back to Vertex AI 2.5."""
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


async def embed(text: str, input_type: str = "query") -> list[float]:
    """
    Generate 1024-dim embedding via MongoDB Voyage AI (voyage-4-large).
    input_type='document' when indexing patterns, 'query' when searching.
    Falls back to Google text-embedding-004 if VOYAGE_API_KEY not configured.
    """
    from backend.config import settings
    if settings.VOYAGE_API_KEY:
        try:
            client = _get_voyage_client()
            result = await client.embed(
                texts=[text],
                model="voyage-4-large",
                input_type=input_type,
            )
            return result.embeddings[0]
        except Exception as e:
            logger.warning("Voyage AI embed failed (%s), falling back to text-embedding-004", e)

    # Fallback: Google text-embedding-004 via Vertex AI
    try:
        client = _get_vertex_client()
        response = client.models.embed_content(model="text-embedding-004", contents=text)
        return response.embeddings[0].values
    except Exception as e:
        logger.warning("Vertex AI embed failed (%s), falling back to API key client", e)
        client = _get_api_key_client()
        response = client.models.embed_content(model="text-embedding-004", contents=text)
        return response.embeddings[0].values


async def generate_json_fast(prompt: str) -> str:
    """Fast JSON scoring — Gemini 3 chain primary, Vertex AI 2.5 fallback.
    thinking_budget=0 on all Gemini 3 models for maximum speed."""
    config_fast = types.GenerateContentConfig(
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    try:
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
        raise last_exc
    except Exception as e:
        global last_fallback_reason
        last_fallback_reason = f"Gemini 3 quota exhausted ({type(e).__name__}) — switching to Vertex AI 2.5 Flash"
        logger.warning("Gemini 3 fast chain failed, falling back to Vertex AI 2.5: %s", e)
        client = _get_vertex_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return response.text


async def generate_json_reasoned(prompt: str) -> str:
    """Deliberate JSON reasoning — Gemini 3 chain with thinking enabled.
    Used for decision auditing where deeper reasoning improves quality."""
    config_think = types.GenerateContentConfig(
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=1024),
    )
    try:
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
        raise last_exc
    except Exception as e:
        logger.warning("Gemini 3 reasoned chain failed, falling back to Vertex AI 2.5: %s", e)
        client = _get_vertex_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return response.text
