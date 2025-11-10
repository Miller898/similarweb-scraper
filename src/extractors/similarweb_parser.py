import json
import logging
import os
from typing import Any, Dict, Optional

import requests

from .traffic_utils import (
    generate_mock_profile,
    normalize_domain,
    utc_now_iso,
)

class SimilarwebParser:
    """
    High-level client that retrieves and normalizes Similarweb-like data
    for a single domain.

    By default it can operate in "mock" mode, which generates deterministic
    synthetic data without contacting any external API. This keeps the
    project runnable out of the box while still producing realistic output.
    """

    def __init__(
        self,
        base_url: str,
        api_key_env: str = "SIMILARWEB_API_KEY",
        timeout: int = 10,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        use_mock_data: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.use_mock_data = use_mock_data

        self.logger = logger or logging.getLogger(self.__class__.__name__)

    # Public API -----------------------------------------------------------

    def get_domain_data(self, domain: str) -> Dict[str, Any]:
        """
        Fetch and normalize analytics data for a single domain.
        In mock mode, returns a deterministic synthetic profile.
        """
        clean_domain = normalize_domain(domain)
        if not clean_domain:
            raise ValueError(f"Invalid domain: {domain!r}")

        if self.use_mock_data or not self._has_api_key():
            self.logger.debug("Using mock traffic profile for %s", clean_domain)
            raw = generate_mock_profile(clean_domain)
            return self._normalize_mock_response(raw)

        self.logger.debug("Fetching real data for %s", clean_domain)
        raw_response = self._fetch_raw_data(clean_domain)
        return self._normalize_real_response(clean_domain, raw_response)

    # Internal helpers -----------------------------------------------------

    def _has_api_key(self) -> bool:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            self.logger.warning(
                "Environment variable %s not set; falling back to mock data.",
                self.api_key_env,
            )
            return False
        return True

    def _fetch_raw_data(self, domain: str) -> Dict[str, Any]:
        """
        Hit a Similarweb-like HTTP API with basic retry logic.

        Note: This is written to be realistic but does not depend on an
        actual API existing. In a production setting you would adjust the
        URL paths and query parameters to match Similarweb's contract.
        """
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"API key not found in environment variable {self.api_key_env}"
            )

        url = f"{self.base_url}/{domain}/overview"
        params = {
            "api_key": api_key,
            "format": "json",
        }

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.get(url, params=params, timeout=self.timeout)
                if 200 <= resp.status_code < 300:
                    return resp.json()
                self.logger.warning(
                    "Non-success status code for %s: %s - body: %s",
                    domain,
                    resp.status_code,
                    resp.text[:300],
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self.logger.warning(
                    "Request error for domain %s (attempt %d/%d): %s",
                    domain,
                    attempt,
                    self.max_retries,
                    exc,
                )

            if attempt < self.max_retries:
                self._sleep_with_backoff(attempt)

        # If we get here, all retries failed
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Failed to retrieve data for {domain}")

    def _sleep_with_backoff(self, attempt: int) -> None:
        import time

        delay = self.backoff_factor * (2 ** (attempt - 1))
        time.sleep(delay)

    # Normalization --------------------------------------------------------

    def _normalize_mock_response(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map mock profile into the documented schema.
        """
        return {
            "domain": raw["domain"],
            "snapshotDate": utc_now_iso(),
            "title": raw["title"],
            "description": raw["description"],
            "category": raw["category"],
            "screenshot": raw["screenshot"],
            "globalRank": raw["global_rank"],
            "countryRank": raw["country_rank"],
            "categoryRank": raw["category_rank"],
            "estimatedMonthlyVisits": raw["estimated_monthly_visits"],
            "bounceRate": f"{raw['bounce_rate']:.4f}",
            "pagesPerVisit": f"{raw['pages_per_visit']:.2f}",
            "visits": str(raw["visits"]),
            "timeOnSite": f"{raw['time_on_site']:.2f}",
            "topCountryShares": raw["top_country_shares"],
            "trafficSources": raw["traffic_sources"],
            "topKeywords": raw["top_keywords"],
            "isDataFromGA": False,
            "competitors": raw["competitors"],
        }

    def _normalize_real_response(self, domain: str, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Example of how you might map a real API response into the
        standardized schema. This implementation is defensive and
        tolerant of missing fields.
        """
        overview = raw.get("overview", {})

        def g(path: str, default: Any = None) -> Any:
            # simple dotted-path getter
            parts = path.split(".")
            cur: Any = raw
            for part in parts:
                if not isinstance(cur, dict):
                    return default
                cur = cur.get(part)
            return cur if cur is not None else default

        estimated_visits = g("traffic.estimated_monthly_visits", {}) or {}
        # Ensure keys are strings and values are ints
        normalized_visits = {
            str(k): int(v) for k, v in estimated_visits.items() if isinstance(v, (int, float))
        }

        top_countries = g("audience.top_countries", []) or []
        norm_countries = []
        for c in top_countries:
            code = c.get("country_code")
            value = c.get("share")
            if code and isinstance(value, (int, float)):
                norm_countries.append(
                    {
                        "CountryCode": code,
                        "Value": float(value),
                    }
                )

        traffic_sources = g("traffic.sources", {}) or {}
        # Keep only simple numeric fractions
        norm_sources: Dict[str, float] = {}
        for key, val in traffic_sources.items():
            if isinstance(val, (int, float)):
                norm_sources[key.title()] = float(val)

        top_keywords_raw = g("traffic.top_keywords", []) or []
        norm_keywords = []
        for kw in top_keywords_raw:
            name = kw.get("keyword") or kw.get("name")
            value = kw.get("visits") or kw.get("value")
            cpc = kw.get("cpc") or 0.0
            if name and isinstance(value, (int, float)):
                norm_keywords.append(
                    {
                        "name": name,
                        "value": int(value),
                        "cpc": float(cpc),
                    }
                )

        # country rank example
        country_rank_raw = g("ranking.country") or {}
        country_rank = {
            "Country": country_rank_raw.get("name", ""),
            "CountryCode": country_rank_raw.get("code", ""),
            "Rank": country_rank_raw.get("rank", 0),
        }

        normalized = {
            "domain": domain,
            "snapshotDate": utc_now_iso(),
            "title": overview.get("title") or g("meta.title") or "",
            "description": overview.get("description") or g("meta.description") or "",
            "category": g("classification.category") or "",
            "screenshot": g("meta.screenshot_url") or "",
            "globalRank": g("ranking.global.rank", 0),
            "countryRank": country_rank,
            "categoryRank": str(g("ranking.category.rank", "")),
            "estimatedMonthlyVisits": normalized_visits,
            "bounceRate": f"{float(g('engagement.bounce_rate', 0.0)):.4f}",
            "pagesPerVisit": f"{float(g('engagement.pages_per_visit', 0.0)):.2f}",
            "visits": str(int(g("engagement.visits", 0))),
            "timeOnSite": f"{float(g('engagement.time_on_site', 0.0)):.2f}",
            "topCountryShares": norm_countries,
            "trafficSources": norm_sources,
            "topKeywords": norm_keywords,
            "isDataFromGA": bool(g("meta.is_from_ga", False)),
            "competitors": g("competition.competitors", []),
        }

        self.logger.debug("Normalized real response for %s: %s", domain, json.dumps(normalized)[:500])
        return normalized