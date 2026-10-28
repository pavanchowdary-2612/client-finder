from concurrent.futures import ThreadPoolExecutor, as_completed

from .discovery import discover_candidates
from .qualification import enrich_lead
from .research import research_candidate


def run_lead_workflow(category: str, location: str, recency: str, offer: str, search_key: str, count: int,
                      sender_name: str = "", business_name: str = "", llm_key: str = "", model: str = "",
                      llm_provider: str = "openai",
                      search_provider: str = "tavily", progress_callback=None) -> list[dict]:
    candidates = discover_candidates(category, location, recency, search_key, count, search_provider)
    if not candidates:
        return []

    leads = []
    # Different brand sites can be researched concurrently instead of serially.
    with ThreadPoolExecutor(max_workers=min(6, len(candidates))) as pool:
        futures = {pool.submit(research_candidate, candidate, location): candidate for candidate in candidates}
        for index, future in enumerate(as_completed(futures), start=1):
            candidate = futures[future]
            if progress_callback:
                progress_callback(index, len(candidates), candidate)
            try:
                lead = future.result()
            except Exception:
                continue
            lead = enrich_lead(lead, category, location, recency)
            if lead.get("qualified"):
                leads.append(lead)

    # Drafting happens only when the user asks for a particular lead's email.
    return sorted(leads, key=lambda item: item["fit_score"], reverse=True)[:count]
