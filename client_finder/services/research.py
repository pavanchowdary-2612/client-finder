import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ..core.security import is_public_http_url
from ..core.settings import settings

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s()./-]{6,}\d)(?!\w)")
CONTACT_WORDS = ("contact", "about", "press", "partnership", "collab")
EDITORIAL_HOST_HINTS = ("news", "magazine", "journal", "times", "daily", "press", "media", "fashionnetwork", "fibre2fashion", "vogue", "elle")
EDITORIAL_PATH_HINTS = ("/article/", "/articles/", "/news/", "/press-release/", "/editorial/", "/magazine/", "/journal/")


def is_editorial_url(url: str, topic: str = "") -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    labels = host.split(".")
    known_publisher = any(hint in labels for hint in EDITORIAL_HOST_HINTS)
    news_article = topic == "news" and any(hint in path for hint in EDITORIAL_PATH_HINTS)
    return known_publisher or news_article


def read_public_page(url: str) -> dict:
    """Read one public HTML page, with URL validation and bounded response size."""
    if not is_public_http_url(url):
        return {"text": "", "emails": [], "phones": [], "links": [], "title": ""}
    try:
        response = requests.get(url, timeout=6, allow_redirects=False, headers={"User-Agent": settings.user_agent})
        if response.is_redirect:
            location = requests.compat.urljoin(url, response.headers.get("location", ""))
            if not is_public_http_url(location):
                return {"text": "", "emails": [], "links": [], "title": ""}
            response = requests.get(location, timeout=6, allow_redirects=False, headers={"User-Agent": settings.user_agent})
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", ""):
            return {"text": "", "emails": [], "links": [], "title": ""}
        soup = BeautifulSoup(response.content[:1_500_000], "html.parser")
        for element in soup(["script", "style", "noscript", "svg"]):
            element.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        site_name = soup.find("meta", attrs={"property": "og:site_name"})
        description = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        text = " ".join(soup.stripped_strings)[:10000]
        emails = set(EMAIL_RE.findall(text))
        phones = set(PHONE_RE.findall(text))
        for anchor in soup.select('a[href^="mailto:"]'):
            emails.update(EMAIL_RE.findall(anchor.get("href", "")[7:]))
        for anchor in soup.select('a[href^="tel:"]'):
            phones.update(PHONE_RE.findall(anchor.get("href", "")[4:]))
        links = []
        for anchor in soup.find_all("a", href=True):
            label = (anchor.get_text(" ", strip=True) + " " + anchor["href"]).lower()
            if any(word in label for word in CONTACT_WORDS):
                target = requests.compat.urljoin(response.url, anchor["href"])
                if urlparse(target).hostname == urlparse(response.url).hostname and is_public_http_url(target):
                    links.append(target.split("#", 1)[0])
        return {
            "text": text,
            "emails": sorted({email.lower() for email in emails}),
            "phones": sorted(phones),
            "links": list(dict.fromkeys(links))[:4],
            "title": title,
            "site_name": site_name.get("content", "").strip() if site_name else "",
            "description": description.get("content", "").strip() if description else "",
        }
    except requests.RequestException:
        return {"text": "", "emails": [], "phones": [], "links": [], "title": ""}


def research_candidate(candidate: dict, location: str = "") -> dict:
    home = read_public_page(candidate["website"])
    editorial_source = is_editorial_url(candidate["website"], candidate.get("search_topic", ""))
    pages = [(candidate["website"], home)]
    # Never collect a publisher's contact details as if they belong to a brand.
    homepage_text = " ".join((home.get("text", ""), home.get("description", ""), candidate.get("snippet", ""))).lower()
    homepage_confirms_location = bool(location and location.lower() in homepage_text)
    if location.strip().lower() == "india":
        host = (urlparse(candidate["website"]).hostname or "").lower().removeprefix("www.")
        homepage_confirms_location = homepage_confirms_location or host.endswith(".in") or any(
            signal in homepage_text for signal in ("₹", " inr ", "+91")
        )
    if not editorial_source and (not home["emails"] and not home.get("phones") or (location and not homepage_confirms_location)):
        contact_urls = sorted(home["links"], key=lambda link: ("contact" not in link.lower(), "about" not in link.lower()))[:2]
        # Some small business sites omit contact links from the homepage navigation.
        for path in ("/contact", "/contact-us"):
            url = candidate["website"].rstrip("/") + path
            if len(contact_urls) < 2 and url not in contact_urls:
                contact_urls.append(url)
        contact_urls = contact_urls[:2]
        if contact_urls:
            with ThreadPoolExecutor(max_workers=len(contact_urls)) as pool:
                contact_pages = list(pool.map(read_public_page, contact_urls))
            for link, page in zip(contact_urls, contact_pages):
                if page["text"] or page["emails"] or page.get("phones"):
                    pages.append((link, page))
    email_sources = {}
    phone_sources = {}
    # Keep business research notes grounded in the brand's own pages; search snippets
    # can describe an unrelated product or retailer result.
    all_text = [home["text"]]
    sources = [{
        "url": candidate["source_url"],
        "kind": "official website search result",
        "summary": candidate.get("snippet", ""),
        "published_date": "",
    }]
    if candidate.get("launch_source_url"):
        sources.append({
            "url": candidate["launch_source_url"],
            "kind": "launch announcement",
            "summary": " ".join(filter(None, (candidate.get("launch_title", ""), candidate.get("launch_snippet", "")))),
            "published_date": candidate.get("launch_date", ""),
        })
    for url, page in pages:
        all_text.append(page["text"])
        sources.append({"url": url, "kind": "public website", "summary": page["text"][:350]})
        for email in page["emails"]:
            email_sources.setdefault(email, url)
        for raw_phone in page.get("phones", []):
            digits = re.sub(r"\D", "", raw_phone)
            formatted_international = raw_phone.strip().startswith("+") or "(" in raw_phone
            if 10 <= len(digits) <= 13 or (formatted_international and 8 <= len(digits) <= 15):
                phone_sources.setdefault(raw_phone.strip(), url)
    text = " ".join(all_text)
    # Keep qualification evidence first-party. Search snippets are discovery
    # hints only and may describe another business or a social-media query page.
    evidence = home.get("description") or home["text"][:450]
    if not evidence and candidate.get("first_party_result"):
        evidence = candidate.get("snippet", "")
    return {
        **candidate,
        "name": home.get("site_name") or home["title"] or candidate["name"],
        "evidence": evidence,
        "search_evidence": candidate.get("snippet", ""),
        "first_party_search_evidence": candidate.get("snippet", "") if candidate.get("first_party_result") else "",
        "first_party_result": bool(candidate.get("first_party_result")),
        "launch_evidence": " ".join(filter(None, (candidate.get("launch_title", ""), candidate.get("launch_snippet", "")))),
        "launch_title": candidate.get("launch_title", ""),
        "launch_brand_name": candidate.get("launch_brand_name", ""),
        "launch_source_url": candidate.get("launch_source_url", ""),
        "launch_date": candidate.get("launch_date", ""),
        "research_notes": text[:1500],
        "contact_email": "" if editorial_source else next(iter(email_sources), ""),
        "contact_phone": "" if editorial_source else next(iter(phone_sources), ""),
        "phone_source": "" if editorial_source else phone_sources.get(next(iter(phone_sources), ""), ""),
        "other_emails": "" if editorial_source else ", ".join(list(email_sources)[1:]),
        "email_source": "" if editorial_source else email_sources.get(next(iter(email_sources), ""), ""),
        "contact_page": "" if editorial_source else next((s["url"] for s in sources if s["url"] != candidate["source_url"] and any(w in s["url"].lower() for w in CONTACT_WORDS)), ""),
        "is_editorial_source": editorial_source,
        "sources": sources,
    }
