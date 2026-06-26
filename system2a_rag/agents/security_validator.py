"""
security_validator.py — Secure RSS retrieval guard for the RAG ingestion pipeline.

Enforces a strict domain whitelist derived from NEWS_SOURCES before any
HTTP request is made.  Handles redirect chains, URL normalization, and
SSL certificate validation.  Every blocked request is logged as a
structured JSON entry.

Security model
--------------
1. URL normalization — lowercase hostname, strip trailing slashes and fragments.
2. Domain whitelist — only hostnames present in NEWS_SOURCES are allowed.
3. Redirect-safe fetch — automatic redirects are DISABLED; each redirect
   hop is validated against the whitelist before following.
4. SSL enforcement — verify=True always; certificate errors are never silenced.
5. Structured security log — every blocked request is recorded with time,
   requested URL, redirect target (if any), and reason.

Usage
-----
    validator = SecurityValidator(NEWS_SOURCES)
    response  = validator.safe_fetch(url)   # raises SecurityError if blocked
"""

import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

import requests
from requests.exceptions import SSLError

# ---------------------------------------------------------------------------
# Logging — security events go to their own named logger so they can be
# directed to a dedicated file or SIEM without touching the root logger.
# ---------------------------------------------------------------------------
security_logger = logging.getLogger("security.validator")

if not security_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    security_logger.addHandler(handler)
    security_logger.setLevel(logging.WARNING)
    security_logger.propagate = False


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class SecurityError(Exception):
    """Raised when a URL or redirect violates the security policy."""


# ---------------------------------------------------------------------------
# SecurityValidator
# ---------------------------------------------------------------------------

class SecurityValidator:
    """
    Validates, normalises, and safely fetches RSS URLs.

    Args:
        news_sources : The NEWS_SOURCES dict mapping source names → RSS URLs.
                       The whitelist is derived automatically from this dict.
        max_redirects: Maximum number of redirect hops to follow (default 3).
                       Prevents infinite redirect loops.
        timeout      : HTTP request timeout in seconds (default 10).
    """

    def __init__(
        self,
        news_sources: dict[str, str],
        max_redirects: int = 3,
        timeout: int = 10,
    ) -> None:
        self.timeout       = timeout
        self.max_redirects = max_redirects

        # Build whitelist from the RSS URL hostnames in NEWS_SOURCES.
        # Normalise immediately so comparison is always apples-to-apples.
        self._whitelist: frozenset[str] = frozenset(
            self._extract_hostname(url)
            for url in news_sources.values()
            if url  # skip any accidental empty strings
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def safe_fetch(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        """
        Validate ``url`` and perform a security-hardened HTTP GET.

        - Normalises the URL before any check.
        - Rejects URLs whose hostname is not in the whitelist.
        - Disables automatic redirects and manually validates each hop.
        - Never disables SSL verification.

        Args:
            url     : The RSS feed URL to fetch.
            headers : Optional HTTP headers (e.g. User-Agent).

        Returns:
            The final ``requests.Response`` object after all redirect hops.

        Raises:
            SecurityError : URL or any redirect hop fails whitelist check.
            SSLError      : SSL certificate validation fails.
        """
        current_url = self.normalize_url(url)
        self._assert_whitelisted(current_url, redirect_target=None)

        hops = 0
        while hops <= self.max_redirects:
            try:
                response = requests.get(
                    current_url,
                    headers=headers or {},
                    timeout=self.timeout,
                    allow_redirects=False,   # ← manual redirect control
                    verify=True,             # ← SSL: NEVER disable
                )
            except SSLError as exc:
                self._log_blocked(
                    requested_url=url,
                    redirect_target=current_url if current_url != url else None,
                    reason=f"SSL certificate validation failed: {exc}",
                )
                raise

            # Not a redirect — we are done.
            if response.status_code not in (301, 302, 307, 308):
                return response

            # Redirect — validate the Location header before following.
            location = response.headers.get("Location", "").strip()
            if not location:
                self._log_blocked(
                    requested_url=url,
                    redirect_target=None,
                    reason=f"Redirect {response.status_code} with missing Location header",
                )
                raise SecurityError(
                    f"Redirect {response.status_code} from {current_url} "
                    f"has no Location header."
                )

            # Resolve relative redirects against the current URL.
            resolved = self._resolve_redirect(current_url, location)
            normalised_target = self.normalize_url(resolved)

            try:
                self._assert_whitelisted(
                    normalised_target,
                    redirect_target=normalised_target,
                    original_url=url,
                )
            except SecurityError:
                # _assert_whitelisted already logged; re-raise.
                raise

            current_url = normalised_target
            hops += 1

        self._log_blocked(
            requested_url=url,
            redirect_target=current_url,
            reason=f"Exceeded maximum redirect hops ({self.max_redirects})",
        )
        raise SecurityError(
            f"Exceeded {self.max_redirects} redirect hops starting from {url}."
        )

    def is_allowed(self, url: str) -> bool:
        """
        Return True if ``url``'s hostname is in the whitelist.

        A convenience predicate for callers that want to check without
        fetching (e.g. pre-filtering link lists).
        """
        try:
            hostname = self._extract_hostname(self.normalize_url(url))
            return hostname in self._whitelist
        except Exception:
            return False

    @staticmethod
    def normalize_url(url: str) -> str:
        """
        Normalise a URL for safe comparison.

        Transformations applied:
        - Scheme preserved (https / http).
        - Hostname lowercased.
        - Path trailing slash removed.
        - Fragment (#...) stripped entirely.
        - Query string preserved (RSS feeds use ?sectionId=... etc.).

        Args:
            url: Raw URL string.

        Returns:
            Normalised URL string.
        """
        parsed = urlparse(url.strip())
        normalised = parsed._replace(
            scheme   = parsed.scheme.lower(),
            netloc   = parsed.hostname.lower() if parsed.hostname else parsed.netloc.lower(),
            path     = parsed.path.rstrip("/"),
            fragment = "",          # strip fragments
        )
        return urlunparse(normalised)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assert_whitelisted(
        self,
        url: str,
        redirect_target: str | None,
        original_url: str | None = None,
    ) -> None:
        """
        Raise SecurityError and log if ``url``'s hostname is not whitelisted.

        Args:
            url             : The URL to check (already normalised).
            redirect_target : The redirect destination (None for initial URL).
            original_url    : The original requested URL (for log context).
        """
        hostname = self._extract_hostname(url)

        if hostname not in self._whitelist:
            reason = (
                "Redirect outside trusted whitelist"
                if redirect_target
                else "Domain not in trusted whitelist"
            )
            self._log_blocked(
                requested_url=original_url or url,
                redirect_target=redirect_target,
                reason=reason,
            )
            raise SecurityError(
                f"BLOCKED — hostname '{hostname}' is not in the trusted whitelist. "
                f"URL: {url}"
            )

    @staticmethod
    def _extract_hostname(url: str) -> str:
        """
        Parse and return the lowercase hostname from a URL.

        Args:
            url: Any URL string.

        Returns:
            Lowercase hostname (e.g. 'arabic.rt.com').

        Raises:
            ValueError: If the URL has no parseable hostname.
        """
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError(f"Cannot extract hostname from URL: {url!r}")
        return hostname.lower()

    @staticmethod
    def _resolve_redirect(base_url: str, location: str) -> str:
        """
        Resolve a potentially relative redirect Location against ``base_url``.

        Args:
            base_url : The URL that returned the redirect response.
            location : The raw Location header value.

        Returns:
            An absolute URL string.
        """
        if location.startswith("http://") or location.startswith("https://"):
            return location
        # Relative redirect — combine scheme+host from base with the path.
        parsed_base = urlparse(base_url)
        if location.startswith("/"):
            return f"{parsed_base.scheme}://{parsed_base.netloc}{location}"
        # Relative path — not common for RSS but handle it safely.
        base_path = parsed_base.path.rsplit("/", 1)[0]
        return f"{parsed_base.scheme}://{parsed_base.netloc}{base_path}/{location}"

    @staticmethod
    def _log_blocked(
        requested_url: str,
        redirect_target: str | None,
        reason: str,
    ) -> None:
        """
        Emit a structured JSON security-event log entry.

        Log format (matches the spec):
        {
            "time": "ISO-8601 UTC timestamp",
            "requested_url": "...",
            "redirect_target": "... or null",
            "reason": "..."
        }
        """
        entry = {
            "time":            datetime.now(tz=timezone.utc).isoformat(),
            "requested_url":   requested_url,
            "redirect_target": redirect_target,
            "reason":          reason,
        }
        security_logger.warning(json.dumps(entry, ensure_ascii=False))
