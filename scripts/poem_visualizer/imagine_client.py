"""
Thin wrapper around the xAI Grok Imagine REST API (image + video).

Uses requests + XAI_API_KEY. Optional for Phase 1: if the key is missing
or a call fails, the CLI still saves prompts and carries on gracefully.

XAI_API_KEY resolution order:
  1. Already-set process environment variable (wins)
  2. Value from a .env file, if found (see _load_dotenv_if_present)

How to create a .env file:
  Copy scripts/poem_visualizer/.env.example to either this package folder
  or the repo root, rename it to .env, and put your real key in:
      XAI_API_KEY=xai-...
  Never commit .env (it is gitignored at the repo root).

Docs (as of scaffolding):
  POST https://api.x.ai/v1/images/generations
  POST https://api.x.ai/v1/videos/generations  (async; poll GET /v1/videos/{id})
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - surfaced as a friendly error at call time
    requests = None  # type: ignore

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional until pip install
    load_dotenv = None  # type: ignore


DEFAULT_BASE_URL = "https://api.x.ai/v1"
DEFAULT_IMAGE_MODEL = "grok-imagine-image-quality"
DEFAULT_VIDEO_MODEL = "grok-imagine-video"
# Official Imagine image-generation docs: n is 1–10 on /v1/images/generations.
MAX_IMAGE_N = 10

# Avoid re-scanning the filesystem on every from_env() call in one process
_DOTENV_LOADED = False


def _load_dotenv_if_present() -> None:
    """
    Load the first .env found, without overriding existing env vars.

    Search order (first hit wins):
      1. scripts/poem_visualizer/.env  (next to this package)
      2. repo root /.env
      3. current working directory /.env

    Prefer export XAI_API_KEY=... in the shell if already set — load_dotenv
    uses override=False so the process env always wins.
    """
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True

    if load_dotenv is None:
        return

    package_dir = Path(__file__).resolve().parent
    candidates = [
        package_dir / ".env",
        package_dir.parents[1] / ".env",  # repo root (…/poem_visualizer → scripts → root)
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if path.is_file():
            # override=False: keep any XAI_API_KEY already in the environment
            load_dotenv(path, override=False)
            return


@dataclass
class ImagineResult:
    """Outcome of an optional API call."""

    ok: bool
    url: Optional[str] = None
    urls: List[str] = field(default_factory=list)
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class ImagineClient:
    """
    Minimal Grok Imagine client.

    Prefer constructing via ImagineClient.from_env() so missing keys
    are handled without exceptions at import time.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        image_model: str = DEFAULT_IMAGE_MODEL,
        video_model: str = DEFAULT_VIDEO_MODEL,
        timeout: float = 120.0,
    ) -> None:
        if requests is None:
            raise RuntimeError(
                "The 'requests' package is required for API calls. "
                "Install with: pip install requests"
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.image_model = image_model
        self.video_model = video_model
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> Optional["ImagineClient"]:
        """
        Return a client if XAI_API_KEY is available, else None.

        Loads .env (if present) first; existing environment variables win.
        Missing key or missing requests → None (CLI skips live generation).
        """
        _load_dotenv_if_present()
        key = os.environ.get("XAI_API_KEY", "").strip()
        if not key:
            return None
        if requests is None:
            return None
        return cls(api_key=key)

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Image
    # ------------------------------------------------------------------

    def generate_image(
        self,
        prompt: str,
        *,
        aspect_ratio: str = "9:16",
        n: int = 1,
    ) -> ImagineResult:
        """
        Text-to-image via /v1/images/generations.

        One HTTP request. When the API honors ``n`` > 1, ``urls`` holds every
        returned still and ``url`` is the first (backward compatible).
        Call :meth:`collect_image_urls` if you also want sequential backfill
        when a batch returns fewer URLs than requested.
        """
        n = _clamp_image_n(n)
        payload: Dict[str, Any] = {
            "model": self.image_model,
            "prompt": prompt,
            "n": n,
        }
        # aspect_ratio is supported by Imagine; include when set
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio

        try:
            resp = requests.post(
                f"{self.base_url}/images/generations",
                headers=self._headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            return ImagineResult(ok=False, error=f"Image request failed: {exc}")

        if resp.status_code >= 400:
            return ImagineResult(
                ok=False,
                error=f"Image API HTTP {resp.status_code}: {_safe_body(resp)}",
                raw=_try_json(resp),
            )

        data = _try_json(resp) or {}
        urls = _extract_image_urls(data)
        if not urls:
            return ImagineResult(
                ok=False,
                error="Image API returned no URL (unexpected response shape).",
                raw=data,
            )
        return ImagineResult(ok=True, url=urls[0], urls=urls, raw=data)

    def collect_image_urls(
        self,
        prompt: str,
        *,
        aspect_ratio: str = "9:16",
        n: int = 1,
    ) -> ImagineResult:
        """
        Gather up to ``n`` still URLs for the same prompt + aspect ratio.

        Official Imagine docs (``/v1/images/generations``) accept ``n`` 1–10
        and return one entry per image in ``data[]``. This helper:

        1. Issues one batch request with that ``n``.
        2. If the batch fails or returns fewer URLs than asked (some
           deployments ignore ``n`` and emit a single still), fills the
           remainder with sequential ``n=1`` calls.

        ``url`` is the first collected still; ``urls`` is the full list.
        ``error`` may still be set when ok=True if a later fill failed
        after at least one URL was collected.
        """
        n = _clamp_image_n(n)
        urls: List[str] = []
        errors: List[str] = []
        raw: Optional[Dict[str, Any]] = None

        batch = self.generate_image(prompt, aspect_ratio=aspect_ratio, n=n)
        raw = batch.raw
        if batch.ok:
            urls = _unique_urls(batch.urls or ([batch.url] if batch.url else []))
        elif batch.error:
            errors.append(batch.error)

        # Remaining slots after the batch (or a full sequential pass if
        # a multi-image batch produced nothing). A failed n=1 request is
        # not retried here — same as generate_image.
        remaining = n - len(urls)
        if remaining > 0 and n == 1 and not batch.ok:
            remaining = 0
        for _ in range(remaining):
            extra = self.generate_image(prompt, aspect_ratio=aspect_ratio, n=1)
            if raw is None:
                raw = extra.raw
            if extra.ok:
                for u in extra.urls or ([extra.url] if extra.url else []):
                    if u and u not in urls:
                        urls.append(u)
                        if len(urls) >= n:
                            break
            elif extra.error:
                errors.append(extra.error)
                # Keep going — one failed single should not drop later draws.

        err = "; ".join(e for e in errors if e) or None
        if urls:
            return ImagineResult(ok=True, url=urls[0], urls=urls[:n], error=err, raw=raw)
        return ImagineResult(
            ok=False,
            error=err or "Image API returned no URL.",
            raw=raw,
        )

    # ------------------------------------------------------------------
    # Video (async start + poll)
    # ------------------------------------------------------------------

    def generate_video(
        self,
        prompt: str,
        *,
        duration: int = 8,
        aspect_ratio: str = "9:16",
        resolution: str = "720p",
        poll_interval: float = 5.0,
        max_wait: float = 600.0,
        image_url: Optional[str] = None,
    ) -> ImagineResult:
        """
        Text-to-video (or image-to-video if image_url is set).

        Starts a job on /v1/videos/generations, then polls
        GET /v1/videos/{request_id} until done / failed / timeout.
        """
        payload: Dict[str, Any] = {
            "model": self.video_model,
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }
        if image_url:
            payload["image"] = {"url": image_url}

        try:
            resp = requests.post(
                f"{self.base_url}/videos/generations",
                headers=self._headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            return ImagineResult(ok=False, error=f"Video start failed: {exc}")

        if resp.status_code >= 400:
            return ImagineResult(
                ok=False,
                error=f"Video API HTTP {resp.status_code}: {_safe_body(resp)}",
                raw=_try_json(resp),
            )

        start_data = _try_json(resp) or {}
        request_id = start_data.get("request_id")
        if not request_id:
            return ImagineResult(
                ok=False,
                error="Video API returned no request_id.",
                raw=start_data,
            )

        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            try:
                poll = requests.get(
                    f"{self.base_url}/videos/{request_id}",
                    headers={"Authorization": self._headers["Authorization"]},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                return ImagineResult(ok=False, error=f"Video poll failed: {exc}")

            data = _try_json(poll) or {}
            status = (data.get("status") or "").lower()

            if status == "done":
                url = (data.get("video") or {}).get("url")
                if not url:
                    return ImagineResult(
                        ok=False,
                        error="Video done but no URL in response.",
                        raw=data,
                    )
                return ImagineResult(ok=True, url=url, raw=data)

            if status in {"failed", "expired"}:
                err = data.get("error") or {}
                msg = err.get("message") if isinstance(err, dict) else None
                return ImagineResult(
                    ok=False,
                    error=msg or f"Video generation {status}.",
                    raw=data,
                )

            time.sleep(poll_interval)

        return ImagineResult(
            ok=False,
            error=f"Video generation timed out after {int(max_wait)}s "
                  f"(request_id={request_id}).",
        )


def _try_json(resp: Any) -> Optional[Dict[str, Any]]:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _safe_body(resp: Any, limit: int = 400) -> str:
    try:
        text = resp.text or ""
    except Exception:
        return "(unreadable body)"
    text = text.strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _clamp_image_n(n: int) -> int:
    try:
        value = int(n)
    except (TypeError, ValueError):
        return 1
    return max(1, min(value, MAX_IMAGE_N))


def _unique_urls(urls: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for url in urls:
        if not isinstance(url, str):
            continue
        cleaned = url.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def _extract_image_urls(data: Dict[str, Any]) -> List[str]:
    """
    Collect every image URL from common response shapes:

      { "data": [ { "url": "..." }, { "url": "..." } ] }   # OpenAI / xAI
      { "url": "..." }
      { "images": [ { "url": "..." } ] }                  # occasional alias

    Official Imagine docs return one ``data[]`` entry per requested ``n``.
    """
    found: List[str] = []
    items = data.get("data")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                found.append(item["url"])
    if not found and isinstance(data.get("url"), str):
        found.append(data["url"])
    images = data.get("images")
    if not found and isinstance(images, list):
        for item in images:
            if isinstance(item, str):
                found.append(item)
            elif isinstance(item, dict) and isinstance(item.get("url"), str):
                found.append(item["url"])
    return _unique_urls(found)


def _extract_image_url(data: Dict[str, Any]) -> Optional[str]:
    """First URL only — kept for callers that still expect a single still."""
    urls = _extract_image_urls(data)
    return urls[0] if urls else None
