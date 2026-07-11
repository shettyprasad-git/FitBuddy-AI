"""
services/orchestrate.py
──────────────────────────────────────────────────────────────────────────────
FitBuddy AI – IBM watsonx Orchestrate / watsonx.ai Integration Service

Architecture
────────────
Layer 1 — IBM watsonx Orchestrate External Chat API
            POST https://api.au-syd.watson-orchestrate.cloud.ibm.com/v1/chat
            Body: { "messages": [...], "agent_id": "<ORCHESTRATE_AGENT_ID>" }
            Auth: IAM Bearer token from ORCHESTRATE_API_KEY
            Status: Active once the agent is Published in the WXO UI.
                    Agent GUID: ebea739a-784d-43d1-a90b-5b06d8591404
                    WXO UI: https://au-syd.watson-orchestrate.cloud.ibm.com
                            → Home → FitBuddy AI → Publish

Layer 2 — IBM watsonx.ai Chat Completion API  (active fallback right now)
            POST https://au-syd.ml.cloud.ibm.com/ml/v1/text/chat
            Model: meta-llama/llama-3-3-70b-instruct
            Auth: IAM Bearer token from IBM_CLOUD_API_KEY

Layer 3 — Built-in rule-based fitness knowledge base (always available)

Token caching : IAM tokens are cached in memory until 5 minutes before expiry.

All credentials are read exclusively from environment variables (.env).
No secret value is written in this source file.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

# ── Environment variable names (values loaded at import time) ─────────────────
_IBM_CLOUD_API_KEY    = os.environ.get("IBM_CLOUD_API_KEY", "")
_ORCHESTRATE_API_KEY  = os.environ.get("ORCHESTRATE_API_KEY", "")
_ORCHESTRATE_AGENT_ID = os.environ.get("ORCHESTRATE_AGENT_ID", "")

# The External Chat API base URL is always the regional base — NOT the
# instance-scoped /instances/<id> URL (which is for management APIs only).
# The instance-scoped URL from service credentials is accepted as ORCHESTRATE_URL
# but we extract the base domain automatically.
_ORCHESTRATE_URL_RAW  = os.environ.get(
    "ORCHESTRATE_URL",
    "https://api.au-syd.watson-orchestrate.cloud.ibm.com/instances/2ea226e0-957f-43c9-a8bf-32f354533600",
)
# Strip any /instances/... suffix to get the base domain for the External Chat API
_ORCHESTRATE_BASE_URL = _ORCHESTRATE_URL_RAW.split("/instances/")[0].rstrip("/")

_WATSONX_PROJECT_ID   = os.environ.get("WATSONX_PROJECT_ID", "")

# watsonx.ai regional endpoint (derived from ORCHESTRATE_URL region)
_WATSONX_AI_BASE     = os.environ.get(
    "WATSONX_AI_URL",
    "https://au-syd.ml.cloud.ibm.com",
)
_WATSONX_CHAT_MODEL  = os.environ.get(
    "WATSONX_CHAT_MODEL",
    "meta-llama/llama-3-3-70b-instruct",
)

# IBM Cloud IAM token endpoint (global, region-independent)
_IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"

# ── System prompt injected into every conversation ────────────────────────────
_SYSTEM_PROMPT = (
    "You are FitBuddy AI, an expert personal fitness and wellness coach. "
    "Your role is to provide clear, concise, evidence-based advice on workouts, "
    "nutrition, BMI, calorie tracking, hydration, recovery, and motivation. "
    "Keep responses practical and actionable. "
    "Always encourage users to consult a healthcare professional for medical decisions. "
    "Do not discuss topics unrelated to fitness, wellness, or healthy living."
)

# ── Rule-based fallback knowledge base ───────────────────────────────────────
_FITNESS_KB: dict[str, str] = {
    "weight loss":  "For weight loss, aim for a 300–500 kcal/day deficit via a combination of diet and exercise. Strength train 3×/week to preserve muscle, and do 150+ min of cardio weekly. Focus on whole foods, lean proteins, and vegetables.",
    "muscle gain":  "To build muscle, consume a slight caloric surplus (200–300 kcal) with 1.6–2.2 g of protein per kg of body weight. Follow progressive overload in resistance training and prioritise sleep for recovery.",
    "cardio":       "Aim for 150 min/week of moderate-intensity cardio (brisk walk, cycling) or 75 min/week of vigorous activity (running, HIIT). Cardio strengthens your heart, burns calories, and improves endurance.",
    "workout":      "A balanced routine includes: strength training (2–4×/week), cardiovascular exercise (3–5×/week), flexibility/mobility work (daily), and 1–2 rest days for recovery.",
    "protein":      "Protein is essential for muscle repair and growth. Good sources: chicken breast, eggs, Greek yogurt, lentils, tofu, cottage cheese. Target 0.8–2.2 g per kg of body weight depending on your goal.",
    "sleep":        "Aim for 7–9 hours of quality sleep per night. Growth hormone is released during deep sleep, making it critical for muscle repair, fat loss, and mental well-being.",
    "hydration":    "Drink at least 2 L of water daily. Before exercise: 500 ml. During: 200 ml every 20 min. After: 500 ml. Proper hydration boosts performance by up to 20%.",
    "bmi":          "BMI = weight(kg) ÷ height(m)². Healthy range: 18.5–24.9. Note: BMI doesn't distinguish muscle from fat — use it alongside body-fat percentage for a fuller picture.",
    "nutrition":    "Follow the plate method: ½ plate vegetables & fruits, ¼ lean protein, ¼ whole grains. Limit processed foods, added sugars, and sodium. Eat every 3–4 hours to sustain energy.",
    "motivation":   "Consistency beats perfection. Set small weekly goals, track progress, celebrate wins, and remember why you started. Find a workout buddy or coach to keep you accountable.",
    "beginner":     "Start with 3 days/week: Day 1 — 20-min walk + bodyweight squats & push-ups. Day 2 — rest. Day 3 — yoga or light stretching. Increase intensity gradually over 4–6 weeks.",
    "hiit":         "HIIT alternates 20–40 sec of intense effort with 10–20 sec recovery. It burns more calories in less time and elevates metabolism for up to 24 hours post-workout.",
    "yoga":         "Even 15–20 min/day of yoga improves flexibility, core strength, balance, and mental clarity. It also reduces cortisol, aiding recovery from intense training.",
    "diet":         "Avoid crash diets — they cause muscle loss and slow your metabolism. Instead, create a sustainable 300–500 kcal deficit through a mix of diet and exercise.",
    "calorie":      "Use the Mifflin–St Jeor equation to find your TDEE. Subtract 500 kcal/day for ~0.5 kg/week weight loss, or add 300 kcal/day for lean muscle gain.",
    "water":        "General guideline: 35 ml per kg of body weight per day, adjusted for activity level and climate. Active individuals in hot climates may need 3–4 L daily.",
    "stretch":      "Stretch after every workout while muscles are warm. Hold each stretch 20–30 seconds without bouncing. Focus on hips, hamstrings, chest, and shoulders — commonly tight areas.",
    "recovery":     "Recovery is as important as training. Use foam rolling, contrast showers, adequate sleep, and deload weeks every 4–6 weeks to prevent overtraining and injury.",
    "default":      "I'm FitBuddy AI, your personal fitness and wellness coach powered by IBM watsonx! I can help with workout plans, nutrition guidance, BMI & calorie calculations, hydration targets, and daily motivation. What would you like to work on today?",
}


# ── IAM Token Cache ───────────────────────────────────────────────────────────

class _TokenCache:
    """Thread-safe in-memory IAM token cache with 5-minute pre-expiry buffer."""

    def __init__(self) -> None:
        self._token:   Optional[str] = None
        self._expires: float         = 0.0      # unix timestamp

    def get(self, api_key: str) -> str:
        """Return a valid IAM Bearer token, refreshing if necessary."""
        if not api_key:
            raise ValueError("No IBM Cloud API key configured.")
        now = time.time()
        if self._token and now < self._expires:
            return self._token
        self._token, self._expires = _fetch_iam_token(api_key)
        return self._token

    def invalidate(self) -> None:
        self._token   = None
        self._expires = 0.0


# One cache per key type to avoid mixing Orchestrate and IBM Cloud credentials
_orchestrate_token_cache = _TokenCache()
_ibmcloud_token_cache    = _TokenCache()


def _fetch_iam_token(api_key: str) -> tuple[str, float]:
    """
    Exchange an IBM Cloud API key for a Bearer token via the IAM token endpoint.

    Returns:
        (access_token, expiry_unix_timestamp)

    Raises:
        RuntimeError on HTTP or network errors.
    """
    body = urllib.parse.urlencode({
        "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
        "apikey":     api_key,
    }).encode()
    req = urllib.request.Request(
        _IAM_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload    = json.loads(resp.read())
            token      = payload["access_token"]
            expires_in = int(payload.get("expires_in", 3600))
            # Cache until 5 minutes before actual expiry
            expiry = time.time() + expires_in - 300
            logger.debug("IAM token acquired, expires_in=%d", expires_in)
            return token, expiry
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        raise RuntimeError(f"IAM token exchange failed [{exc.code}]: {detail}") from exc
    except OSError as exc:
        raise RuntimeError(f"IAM token exchange network error: {exc}") from exc


# ── Primary: IBM watsonx Orchestrate External Chat API ───────────────────────

def _call_orchestrate(user_message: str, conversation_history: list[dict]) -> str:
    """
    Send a message to the IBM watsonx Orchestrate External Chat API.

    Endpoint : POST {base}/v1/chat
    Auth     : IBM Cloud IAM Bearer token derived from ORCHESTRATE_API_KEY
    Body     : { "messages": [...], "agent_id": "<ORCHESTRATE_AGENT_ID>" }

    The agent_id is the URL slug of an agent that has been created and deployed
    inside the Orchestrate instance via the WXO UI at:
      https://au-syd.watson-orchestrate.cloud.ibm.com

    Raises RuntimeError (caller falls back to watsonx.ai) when:
      - ORCHESTRATE_API_KEY or ORCHESTRATE_AGENT_ID are not set
      - No agent is deployed yet (500 WXO-PROXY-11112E)
      - Authentication fails (401)
      - Network error
    """
    if not _ORCHESTRATE_API_KEY:
        raise RuntimeError("ORCHESTRATE_API_KEY not configured.")
    if not _ORCHESTRATE_AGENT_ID:
        raise RuntimeError(
            "ORCHESTRATE_AGENT_ID not set. "
            "Create an agent in the WXO UI, then set ORCHESTRATE_AGENT_ID=<agent-slug> in .env."
        )

    token = _orchestrate_token_cache.get(_ORCHESTRATE_API_KEY)

    # Build messages: system prompt + last 10 history turns + new user turn
    messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages.extend(conversation_history[-10:])
    messages.append({"role": "user", "content": user_message})

    # WXO External Chat API:
    # POST https://api.au-syd.watson-orchestrate.cloud.ibm.com/v1/chat
    # Body: { "messages": [...], "agent_id": "<slug>" }
    # The base URL must NOT contain /instances/<id> — that suffix is only
    # for the management API (service credentials "url" field).
    endpoint = _ORCHESTRATE_BASE_URL + "/v1/chat"

    payload = json.dumps({
        "messages": messages,
        "agent_id": _ORCHESTRATE_AGENT_ID,
    }).encode()

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            # WXO External API returns OpenAI-compatible shape
            choices = data.get("choices") or data.get("output", {}).get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            if "response" in data:
                return str(data["response"]).strip()
            raise RuntimeError(f"Unexpected Orchestrate response shape: {list(data.keys())}")
    except urllib.error.HTTPError as exc:
        raw    = exc.read()
        detail = raw.decode(errors="replace")[:300]
        try:
            err_code = json.loads(raw).get("code", "")
        except Exception:
            err_code = ""

        if exc.code == 401:
            _orchestrate_token_cache.invalidate()
            logger.warning("Orchestrate auth error [401] — token invalidated.")
        elif exc.code in (404, 500) and "WXO-PROXY-11112E" in err_code:
            # 500 WXO-PROXY-11112E = no agent deployed / internal routing failure
            # This is expected when the instance has no published agent yet.
            logger.debug(
                "Orchestrate: no agent deployed yet (agent_id=%s). "
                "Deploy an agent in the WXO UI to activate this layer.",
                _ORCHESTRATE_AGENT_ID,
            )
        elif exc.code == 404:
            logger.debug("Orchestrate: agent_id=%s not found [404].", _ORCHESTRATE_AGENT_ID)
        else:
            logger.warning("Orchestrate HTTP error [%d]: %s", exc.code, detail[:80])
        raise RuntimeError(f"Orchestrate API [{exc.code}]: {detail}") from exc
    except OSError as exc:
        raise RuntimeError(f"Orchestrate network error: {exc}") from exc


# ── Secondary: IBM watsonx.ai Chat Completion API ────────────────────────────

def _call_watsonx_ai(user_message: str, conversation_history: list[dict]) -> str:
    """
    Send a message to the IBM watsonx.ai Chat Completion endpoint.

    Uses IBM_CLOUD_API_KEY (account-level key) and WATSONX_PROJECT_ID.
    Model: meta-llama/llama-3-3-70b-instruct (confirmed available in au-syd).

    Args:
        user_message:         The latest user message text.
        conversation_history: List of prior {role, content} dicts.

    Returns:
        The assistant reply text.

    Raises:
        RuntimeError on any error (caller catches and falls back).
    """
    if not _IBM_CLOUD_API_KEY:
        raise RuntimeError("IBM_CLOUD_API_KEY not configured.")
    if not _WATSONX_PROJECT_ID:
        raise RuntimeError("WATSONX_PROJECT_ID not configured.")

    token = _ibmcloud_token_cache.get(_IBM_CLOUD_API_KEY)

    # Build messages: system prompt + trimmed history + new user turn
    messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages.extend(conversation_history[-10:])
    messages.append({"role": "user", "content": user_message})

    endpoint = f"{_WATSONX_AI_BASE.rstrip('/')}/ml/v1/text/chat?version=2024-01-15"
    payload  = json.dumps({
        "model_id":   _WATSONX_CHAT_MODEL,
        "project_id": _WATSONX_PROJECT_ID,
        "messages":   messages,
        "parameters": {
            "max_tokens":  500,
            "temperature": 0.7,
        },
    }).encode()

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data    = json.loads(resp.read())
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("watsonx.ai returned empty choices.")
            content = choices[0].get("message", {}).get("content", "").strip()
            if not content:
                raise RuntimeError("watsonx.ai returned empty content.")
            logger.debug(
                "watsonx.ai OK — model=%s tokens=%s",
                data.get("model_id"),
                data.get("usage", {}).get("total_tokens"),
            )
            return content
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        if exc.code == 401:
            _ibmcloud_token_cache.invalidate()
        raise RuntimeError(f"watsonx.ai Chat API [{exc.code}]: {detail}") from exc
    except OSError as exc:
        raise RuntimeError(f"watsonx.ai network error: {exc}") from exc


# ── Final fallback: rule-based fitness knowledge base ────────────────────────

def _fallback_response(user_message: str) -> str:
    """
    Return a keyword-matched response from the built-in fitness knowledge base.
    This never fails and requires no network or credentials.
    """
    msg_lower = user_message.lower()
    for keyword, response in _FITNESS_KB.items():
        if keyword in msg_lower:
            return response
    return _FITNESS_KB["default"]


# ── Public interface ──────────────────────────────────────────────────────────

def get_chat_response(
    user_message: str,
    conversation_history: Optional[list[dict]] = None,
) -> dict:
    """
    Get an AI response for the given user message.

    Tries each layer in order and falls back gracefully:
      1. IBM watsonx Orchestrate External Chat API  (if ORCHESTRATE_API_KEY set)
      2. IBM watsonx.ai Chat Completion API         (if IBM_CLOUD_API_KEY + WATSONX_PROJECT_ID set)
      3. Built-in rule-based fitness knowledge base  (always available)

    Args:
        user_message:         The user's input text.
        conversation_history: Optional list of prior {role, content} dicts,
                              oldest first. Used to maintain context across turns.

    Returns:
        {
            "response": str,     # The AI reply text
            "source":   str,     # "orchestrate" | "watsonx_ai" | "fallback"
            "error":    str|None # Description of any non-fatal error that caused fallback
        }
    """
    history = conversation_history or []
    errors: list[str] = []

    # ── Layer 1: IBM watsonx Orchestrate ──────────────────────────────────────
    # Guard: skip entirely when ORCHESTRATE_AGENT_ID is not yet set — no point
    # trying the API if we have no agent to route to.
    if _ORCHESTRATE_API_KEY and _ORCHESTRATE_AGENT_ID:
        try:
            reply = _call_orchestrate(user_message, history)
            logger.info("Response via IBM watsonx Orchestrate (agent_id=%s).", _ORCHESTRATE_AGENT_ID)
            return {"response": reply, "source": "orchestrate", "error": None}
        except RuntimeError as exc:
            msg = str(exc)
            # Silent (DEBUG) for known expected states:
            #   - ORCHESTRATE_AGENT_ID not set
            #   - [500] WXO-PROXY-11112E = no agent deployed yet
            #   - [404] agent slug not found
            # Warn only for unexpected errors (auth failure, network, etc.)
            silent = (
                "not set" in msg
                or "[404]" in msg
                or ("[500]" in msg and "11112E" in msg)
            )
            if silent:
                logger.debug("Orchestrate layer skipped: %s", msg.split(":")[0])
            else:
                logger.warning("Orchestrate unavailable — %s", msg)
            errors.append(f"Orchestrate: {msg}")

    # ── Layer 2: IBM watsonx.ai Chat API ─────────────────────────────────────
    if _IBM_CLOUD_API_KEY and _WATSONX_PROJECT_ID:
        try:
            reply = _call_watsonx_ai(user_message, history)
            logger.info("Response via IBM watsonx.ai Chat API.")
            return {
                "response": reply,
                "source":   "watsonx_ai",
                "error":    "; ".join(errors) if errors else None,
            }
        except RuntimeError as exc:
            msg = str(exc)
            logger.warning("watsonx.ai unavailable — %s", msg)
            errors.append(f"watsonx.ai: {msg}")

    # ── Layer 3: Built-in fallback ────────────────────────────────────────────
    reply = _fallback_response(user_message)
    logger.info("Response via built-in fallback knowledge base.")
    return {
        "response": reply,
        "source":   "fallback",
        "error":    "; ".join(errors) if errors else None,
    }


def health_check() -> dict:
    """
    Probe each configured integration layer and return a status dict.
    Safe to call at startup or from a /health endpoint.

    Returns:
        {
            "orchestrate":  "ready" | "agent_not_published" | "auth_error" | "not_configured",
            "orchestrate_agent_id": str,
            "watsonx_ai":   "ready" | "auth_error" | "not_configured",
            "fallback":     "ready"
        }
    """
    status: dict[str, str] = {"fallback": "ready"}

    # ── Orchestrate ────────────────────────────────────────────────────────────
    if _ORCHESTRATE_API_KEY and _ORCHESTRATE_AGENT_ID:
        status["orchestrate_agent_id"] = _ORCHESTRATE_AGENT_ID
        try:
            _orchestrate_token_cache.get(_ORCHESTRATE_API_KEY)
            # IAM token is fine — probe the chat endpoint with a minimal payload
            token = _orchestrate_token_cache.get(_ORCHESTRATE_API_KEY)
            payload = json.dumps({
                "messages": [{"role": "user", "content": "ping"}],
                "agent_id": _ORCHESTRATE_AGENT_ID,
            }).encode()
            req = urllib.request.Request(
                _ORCHESTRATE_BASE_URL + "/v1/chat",
                data=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type":  "application/json",
                    "Accept":        "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            status["orchestrate"] = "ready"
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                code = json.loads(raw).get("code", "")
            except Exception:
                code = ""
            if e.code in (500, 404) and "11112E" in code:
                status["orchestrate"] = (
                    "agent_not_published — "
                    "go to https://au-syd.watson-orchestrate.cloud.ibm.com, "
                    "open FitBuddy AI agent and click Publish"
                )
            elif e.code == 401:
                status["orchestrate"] = "auth_error (check ORCHESTRATE_API_KEY)"
            else:
                status["orchestrate"] = f"http_error_{e.code}"
        except RuntimeError as exc:
            status["orchestrate"] = f"auth_error: {exc}"
        except OSError as exc:
            status["orchestrate"] = f"network_error: {exc}"
    elif _ORCHESTRATE_API_KEY and not _ORCHESTRATE_AGENT_ID:
        status["orchestrate"]          = "agent_id_missing — set ORCHESTRATE_AGENT_ID in .env"
        status["orchestrate_agent_id"] = "(not set)"
    else:
        status["orchestrate"]          = "not_configured"
        status["orchestrate_agent_id"] = "(not set)"

    # ── watsonx.ai ─────────────────────────────────────────────────────────────
    if _IBM_CLOUD_API_KEY and _WATSONX_PROJECT_ID:
        try:
            _ibmcloud_token_cache.get(_IBM_CLOUD_API_KEY)
            status["watsonx_ai"] = f"ready (model: {_WATSONX_CHAT_MODEL})"
        except RuntimeError as exc:
            status["watsonx_ai"] = f"auth_error: {exc}"
    else:
        status["watsonx_ai"] = "not_configured"

    return status


def log_startup_status() -> None:
    """Log a clear summary of AI layer readiness at application startup."""
    s = health_check()
    logger.info("━" * 60)
    logger.info("FitBuddy AI — Integration Status")
    logger.info("  Layer 1  Orchestrate : %s", s.get("orchestrate", "?"))
    logger.info("           Agent ID    : %s", s.get("orchestrate_agent_id", "?"))
    logger.info("  Layer 2  watsonx.ai  : %s", s.get("watsonx_ai", "?"))
    logger.info("  Layer 3  Fallback KB : %s", s.get("fallback", "?"))
    logger.info("━" * 60)
