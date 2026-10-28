from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
import re
from urllib.parse import urlparse, urlunparse
import requests

SOCIAL_HOSTS = ("instagram.com", "facebook.com", "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com", "x.com", "twitter.com", "reddit.com", "threads.net")
MARKETPLACE_HOSTS = ("amazon.com", "amazon.in", "flipkart.com", "etsy.com", "myntra.com", "ajio.com")
NON_BRAND_HOSTS = (
    "textilelearner.net", "scribd.com", "wikipedia.org", "tracxn.com", "goodonyou.eco",
    "highsnobiety.com", "substack.com", "nykaafashion.com", "ssense.com", "aashniandco.com", "iconicindia.com",
    "qikink.com", "billoomifashion.com", "indiamart.com", "tradeindia.com", "justdial.com",
    "crunchbase.com", "linkedin.com", "pinterest.com", "youtube.com", "facebook.com",
    "indianstartuptimes.com", "infashionbusiness.com", "fashionnetwork.com", "vogue.com",
    "vogue.in", "harpersbazaar.in", "inc42.com", "yourstory.com", "indianretailer.com",
    "businessoffashion.com", "monocle.com", "theindustry.fashion", "storyboard18.com",
    "moneycontrol.com", "economictimes.indiatimes.com", "timesofindia.indiatimes.com",
    "fibre2fashion.com", "fashionunited.com", "retail.economictimes.indiatimes.com",
    "apps.apple.com", "play.google.com", "linktr.ee", "medium.com", "substack.com",
)
DOMAIN_RE = re.compile(r"(?<![@\w])(?:https?://)?(?:www\.)?([a-z0-9][a-z0-9.-]*\.(?:co\.in|com|in|org|net|co|fashion|shop|store|io))\b", re.I)
LAUNCH_TITLE_RE = re.compile(
    r"^(.{2,70}?)\s+(?:is\s+set\s+to\s+launch|plans?\s+to\s+launch|to\s+launch|"
    r"launch(?:es|ed)?|unveils?|introduces?|makes|made|debut(?:s|ed)?|expands?|enters?)\b",
    re.I,
)


def _publisher_host(host: str) -> bool:
    host = (host or "").lower().removeprefix("www.")
    return any(host == value or host.endswith("." + value) for value in NON_BRAND_HOSTS)


def _launch_brand_name(title: str) -> str:
    title = re.sub(r"^(?:exclusive\s*\|\s*|breaking\s*:\s*)", "", title.strip(), flags=re.I)
    match = LAUNCH_TITLE_RE.search(title)
    if not match:
        return ""
    name = re.sub(r"\s+(?:with|into|in|for|its own line)$", "", match.group(1), flags=re.I).strip(" -:|'")
    if not name or name.casefold().startswith(("the ", "how ", "what ", "why ")):
        return ""
    return name


def _brand_homepage(item: dict, source_url: str) -> tuple[str, str] | None:
    """Use a result's own site, or a first-party domain named in a launch snippet."""
    parsed = urlparse(source_url)
    source_host = (parsed.hostname or "").lower().removeprefix("www.")
    snippet = " ".join((item.get("title", ""), item.get("description", "")))

    def rejected(host: str) -> bool:
        return (any(host == value or host.endswith("." + value) for value in SOCIAL_HOSTS)
                or any(host == value or host.endswith("." + value) for value in MARKETPLACE_HOSTS)
                or any(host == value or host.endswith("." + value) for value in NON_BRAND_HOSTS))

    host = source_host
    scheme = parsed.scheme or "https"
    if not host or rejected(host):
        mentioned_domains = [match.group(1).lower().removeprefix("www.") for match in DOMAIN_RE.finditer(snippet)]
        host = next((value for value in mentioned_domains if not rejected(value)), "")
        if not host:
            return None
        scheme = "https"
    if parsed.path.lower().endswith((".pdf", ".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx")):
        return None
    homepage = urlunparse((scheme, host, "/", "", "", ""))
    return host, homepage


def brave_search(query: str, api_key: str, count: int = 10) -> list[dict]:
    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        params={"q": query, "count": count},
        timeout=25,
    )
    response.raise_for_status()
    return response.json().get("web", {}).get("results", [])


def tavily_search(query: str, api_key: str, count: int = 10, *, topic: str = "general",
                  start_date: str = "", end_date: str = "", strict_date: bool = False) -> list[dict]:
    payload = {
        "query": query,
        "search_depth": "basic",
        "max_results": min(20, max(1, count)),
        "topic": topic,
        "include_answer": False,
        "include_published_date": True,
        "filter_by_published_date": strict_date,
        "include_raw_content": False,
        "include_usage": False,
    }
    if start_date:
        payload["start_date"] = start_date
    if end_date:
        payload["end_date"] = end_date
    response = requests.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("content", ""),
            "published_date": item.get("published_date", ""),
        }
        for item in results
    ]


def search_web(provider: str, query: str, api_key: str, count: int, *, topic: str = "general",
               start_date: str = "", end_date: str = "", strict_date: bool = False) -> list[dict]:
    if provider.lower() == "tavily":
        return tavily_search(query, api_key, count, topic=topic, start_date=start_date,
                             end_date=end_date, strict_date=strict_date)
    if provider.lower() == "brave":
        return brave_search(query, api_key, count)
    raise ValueError(f"Unsupported search provider: {provider}")


def discover_candidates(category: str, location: str, recency: str, api_key: str, count: int,
                        provider: str = "tavily") -> list[dict]:
    today = date.today()
    months = 6 if "6 months" in recency.lower() else 12
    start_date = (today - timedelta(days=months * 30)).isoformat()
    end_date = today.isoformat()
    year = today.year
    launch_only = any(term in recency.lower() for term in ("last 6 months", "last year", "upcoming", "recently launched"))
    if launch_only:
        search_phrases = [
            (f"new {category} brands launched in {location} {year} official website", "general", False),
            (f"{location} {category} startup brand launch debut collection {year}", "news", True),
            (f"{location} new {category} label launches India debut {year}", "news", True),
        ]
    else:
        search_phrases = [
            (f"{category} brands in {location} official websites contact", "general", False),
            (f"independent {category} brands {location} official website", "general", False),
            (f"best {category} companies and brands based in {location} brand website", "general", False),
        ]
    found: dict[str, dict] = {}
    launch_followups: dict[str, dict] = {}
    # Search beyond the requested final lead count. Qualification removes articles,
    # directory pages, stale results, and results that only mention the niche.
    candidate_pool = min(36, max(count * 2, 12))
    per_query = max(5, min(20, (candidate_pool + len(search_phrases) - 1) // len(search_phrases)))
    def run_query(spec):
        query, topic, strict_date = spec
        return search_web(provider, query, api_key, per_query, topic=topic,
                          start_date=start_date if topic == "news" else "",
                          end_date=end_date if topic == "news" else "",
                          strict_date=strict_date)

    with ThreadPoolExecutor(max_workers=len(search_phrases)) as pool:
        query_results = list(pool.map(run_query, search_phrases))

    for (query, topic, strict_date), items in zip(search_phrases, query_results):
        for item in items:
            url = item.get("url", "")
            source_host = (urlparse(url).hostname or "").lower().removeprefix("www.")
            is_launch_story = launch_only and topic == "news"
            story_text = " ".join((item.get("title", ""), item.get("description", "")))
            # Search news for launch announcements, then independently search
            # the named brand for its first-party site. Never treat a publisher
            # or social page as the brand's contact website.
            if is_launch_story:
                brand_name = _launch_brand_name(item.get("title", ""))
                if brand_name and re.search(r"\b(launch|debut|new brand|new label|introduc|unveil|expand into|enters?)\w*\b", story_text, re.I):
                    launch_followups.setdefault(brand_name.casefold(), {
                        "name": brand_name,
                        "launch_brand_name": brand_name,
                        "launch_title": item.get("title", "").strip(),
                        "launch_source_url": url,
                        "launch_snippet": item.get("description", "").strip(),
                        "launch_date": item.get("published_date", ""),
                    })
                continue
            target = _brand_homepage(item, url)
            if not target:
                continue
            host, homepage = target
            # A social/listing title can describe the query rather than the
            # business. If it only supplied a first-party domain, use that
            # domain as the provisional name until the homepage identifies it.
            provisional_name = item.get("title", "").strip() if source_host == host else host
            official_home_result = source_host == host and not _publisher_host(host) and urlparse(url).path in ("", "/")
            # Research the brand's homepage instead of returning a product or collection page.
            found.setdefault(host, {
                "name": provisional_name or host,
                "website": homepage,
                "snippet": item.get("description", "").strip(),
                "source_url": url,
                "search_query": query,
                "published_date": item.get("published_date", ""),
                "search_topic": topic,
                "first_party_result": official_home_result,
                "launch_source_url": url if is_launch_story else "",
                "launch_snippet": item.get("description", "").strip() if is_launch_story else "",
                "launch_date": item.get("published_date", "") if is_launch_story else "",
            })

    if launch_followups:
        followup_items = list(launch_followups.values())[:min(12, max(4, count * 2))]

        def find_brand_site(story: dict):
            query = f'"{story["name"]}" {category} official website'
            try:
                results = search_web(provider, query, api_key, 10)
            except requests.RequestException:
                return story, []
            return story, results

        with ThreadPoolExecutor(max_workers=min(6, len(followup_items))) as pool:
            verified_searches = list(pool.map(find_brand_site, followup_items))
        for story, results in verified_searches:
            for item in results:
                target = _brand_homepage(item, item.get("url", ""))
                if not target:
                    continue
                host, homepage = target
                source_host = (urlparse(item.get("url", "")).hostname or "").lower().removeprefix("www.")
                if source_host != host or _publisher_host(host):
                    continue
                # Keep the announcement as dated launch evidence while using
                # only the brand's own result/site text for company verification.
                found.setdefault(host, {
                    "name": story["name"],
                    "website": homepage,
                    "snippet": item.get("description", "").strip(),
                    "first_party_result": True,
                    "source_url": item.get("url", ""),
                    "search_query": f'"{story["name"]}" {category} official website',
                    "published_date": story.get("launch_date", ""),
                    "search_topic": "general",
                    "launch_source_url": story.get("launch_source_url", ""),
                    "launch_brand_name": story.get("launch_brand_name", story.get("name", "")),
                    "launch_title": story.get("launch_title", ""),
                    "launch_snippet": story.get("launch_snippet", ""),
                    "launch_date": story.get("launch_date", ""),
                })
    return list(found.values())[:candidate_pool]
