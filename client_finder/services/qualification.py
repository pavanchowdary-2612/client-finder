import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

CATEGORY_ALIASES = {
    "clothing": ("clothing", "apparel", "fashion", "garment", "streetwear", "activewear", "fashion label", "fashion brand"),
    "fashion": ("fashion", "clothing", "apparel", "garment", "streetwear", "activewear"),
    "skincare": ("skincare", "skin care", "beauty", "cosmetics"),
    "beauty": ("beauty", "skincare", "cosmetics", "makeup"),
    "jewelry": ("jewelry", "jewellery", "accessories"),
    "footwear": ("footwear", "shoes", "sneakers", "boots"),
    "food": ("food", "beverage", "snack", "restaurant", "food brand"),
    "furniture": ("furniture", "home decor", "interior"),
}
LAUNCH_PATTERNS = (
    r"\b(?:brand|label|company|startup|business|collection|line)\b.{0,100}\b(?:launch(?:ed|ing)?|debut|first collection|release[ds]?)\b",
    r"\b(?:launch(?:ed|ing)?|debut|release[ds]?)\b.{0,100}\b(?:brand|label|company|startup|business|collection|line)\b",
    r"\b(?:first collection|coming soon|pre-launch|upcoming launch|launching soon|recently released)\b",
)
RECENT_TERMS = ("newly launched", "recently launched", "just launched", "recently released", "newly released", "launching soon", "coming soon", "upcoming launch", "this year")


def _category_matches(category: str, text: str) -> list[str]:
    key = category.lower().strip()
    aliases = CATEGORY_ALIASES.get(key, tuple(part for part in re.split(r"\W+", key) if len(part) > 2))
    return [alias for alias in aliases if re.search(rf"\b{re.escape(alias)}\b", text)]


def _publication_is_recent(published_date: str, recency: str) -> tuple[bool, str]:
    if not published_date:
        return False, ""
    try:
        try:
            published = date.fromisoformat(published_date[:10])
        except ValueError:
            published = parsedate_to_datetime(published_date).date()
    except (TypeError, ValueError):
        return False, ""
    months = 6 if "6 months" in recency.lower() else 12
    cutoff = date.today() - timedelta(days=months * 30)
    if cutoff <= published <= date.today():
        return True, published.isoformat()
    return False, published.isoformat()


def qualify_candidate(lead: dict, category: str, location: str, recency: str) -> tuple[bool, int, list[str]]:
    # Search snippets can contain unrelated query terms. Validate niche evidence
    # and brand identity against the candidate's own homepage and contact pages.
    snippet = lead.get("snippet", "").lower()
    launch_snippet = (lead.get("launch_evidence") or lead.get("launch_snippet") or "").lower()
    # Qualify using first-party page content, never the candidate title (which
    # may just echo a search query or social-media topic).
    brand_text = " ".join([lead.get("evidence", ""), lead.get("research_notes", "")]).lower()
    text = f"{snippet} {launch_snippet} {brand_text}"
    category_matches = _category_matches(category, brand_text)
    has_category = bool(category_matches)
    launch_text = launch_snippet or snippet
    launch_event = any(re.search(pattern, launch_text) for pattern in LAUNCH_PATTERNS)
    launch_title = lead.get("launch_title", "")
    launch_brand_name = lead.get("launch_brand_name", "")
    if launch_title and launch_brand_name:
        named_action = re.search(
            rf"{re.escape(launch_brand_name)}.{{0,100}}\b(?:launch(?:es|ed|ing)?|debut(?:s|ed)?|makes?.{{0,20}}debut|enters?|expands?)\b",
            launch_title,
            re.I,
        )
        launch_event = launch_event or bool(named_action)
    launch_is_market_entry = bool(re.search(r"\b(?:in|into)\s+india\b|india\s+(?:debut|launch|entry)|first\s+(?:store|location)\s+in\s+india", launch_text, re.I))
    published_date = lead.get("launch_date") or lead.get("published_date", "")
    is_recent, publication_date = _publication_is_recent(published_date, recency)
    has_recent_language = any(term in f"{launch_text} {brand_text}" for term in RECENT_TERMS)
    launch_required = any(term in recency.lower() for term in ("last 6 months", "last year", "upcoming", "recently launched"))
    upcoming = any(term in f"{launch_text} {brand_text}" for term in ("coming soon", "upcoming launch", "launching soon", "pre-launch"))
    if not publication_date:
        is_recent = has_recent_language or ("upcoming" in recency.lower() and upcoming)

    reasons = []
    if has_category:
        reasons.append("Category evidence: " + ", ".join(category_matches[:4]))
    if launch_event:
        reasons.append("Recent market entry announced" if launch_is_market_entry else "Recent brand/label launch announced")
    if publication_date:
        reasons.append(("Recent source date: " if is_recent else "Source date outside requested window: ") + publication_date)
    elif is_recent:
        reasons.append("Text says the brand is newly/recently launched or upcoming; date needs review")
    # Search snippets often repeat query terms and are not proof of where a
    # business operates. Confirm geography from the brand's own pages/contact.
    first_party_text = brand_text
    official_search_text = (lead.get("first_party_search_evidence") or "").lower()
    launch_location_match = bool(launch_text) and location.lower() in launch_text
    location_match = (
        location.lower() in first_party_text
        or (bool(lead.get("first_party_result")) and location.lower() in official_search_text)
        or (launch_required and launch_event and launch_location_match)
    )
    if location.strip().lower() == "india":
        host = (lead.get("website", "").lower().split("//")[-1].split("/")[0].removeprefix("www."))
        phone_digits = re.sub(r"\D", "", lead.get("contact_phone", ""))
        location_match = location_match or host.endswith(".in") or "₹" in first_party_text or " inr " in f" {first_party_text} " or phone_digits.startswith("91") or "india" in official_search_text or (launch_required and launch_event and "india" in launch_text)
    if location_match:
        reasons.append("Location confirmed on the brand site, its search listing, or a dated launch announcement")
    else:
        reasons.append("Location not confirmed from brand-owned evidence")
    if lead.get("contact_email"):
        reasons.append("Published contact email found on the brand's own pages")
    elif lead.get("contact_page"):
        reasons.append("Brand contact page found; no email address was published")

    if not launch_required:
        reasons = [reason for reason in reasons if not reason.startswith(("Explicit brand/label launch", "Recent source date:", "Source date outside"))]
        if has_category:
            reasons.append("Brand matches the requested category")

    # General brand searches should return established businesses too. A launch
    # event and date are required only when the user's request includes that constraint.
    non_brand_signals = (
        "reference guide for textiles", "textile knowledge among the students", "fashion magazine",
        "fashion news", "fashion media", "freelance journalist", "fashion journalism",
        "encyclopedia", "fashion and beauty ratings", "print on demand platform",
        "custom apparel manufacturer", "venture capital", "multi-brand retailer",
        "premium international brands like", "best curation", "curation presents labels",
        "apparel franchise", "clothing franchise", "supplier of apparel",
    )
    business_signals = ("brand", "our story", "about us", "our collection", "collections", "shop now", "shop online", "designed by")
    is_brand_site = any(signal in brand_text for signal in business_signals) or bool(lead.get("first_party_result") and has_category)
    is_non_brand_site = any(signal in brand_text for signal in non_brand_signals)
    if is_brand_site:
        reasons.append("First-party brand or collection content found")
    eligible = has_category and is_brand_site and not is_non_brand_site and not lead.get("is_editorial_source", False) and location_match
    if launch_required:
        eligible = eligible and (launch_event or has_recent_language) and is_recent
    score = (55 if has_category else 0) + (10 if launch_event else 0)
    score += 20 if lead.get("contact_email") else 10 if lead.get("contact_page") else 0
    score += 15 if location_match else 0
    return eligible, min(score, 100), reasons


def score_candidate(lead: dict, category: str, location: str) -> tuple[int, list[str]]:
    eligible, score, reasons = qualify_candidate(lead, category, location, "launched in the last year")
    return score, reasons


def enrich_lead(lead: dict, category: str, location: str, recency: str = "launched in the last year") -> dict:
    eligible, score, reasons = qualify_candidate(lead, category, location, recency)
    lead.update({
        "category": category,
        "location": location,
        "fit_score": score,
        "fit_reasons": reasons,
        "qualified": eligible,
        "found_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "Needs review",
    })
    return lead
