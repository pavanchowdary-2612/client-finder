"""Client Finder - Local Lead Research & Outreach Workspace."""

from .core.security import is_public_http_url
from .core.settings import Settings, settings
from .integrations.mailer import send_approved_email
from .integrations.storage import (
    add_suppression,
    delete_leads,
    get_lead,
    init_db,
    is_suppressed,
    list_leads,
    list_suppressed,
    save_leads,
    update_lead,
)
from .services.discovery import brave_search, tavily_search, discover_candidates
from .services.drafting import draft_outreach
from .services.qualification import enrich_lead, score_candidate
from .services.research import read_public_page, research_candidate
from .services.workflow import run_lead_workflow

__all__ = [
    "settings",
    "Settings",
    "is_public_http_url",
    "run_lead_workflow",
    "discover_candidates",
    "brave_search",
    "tavily_search",
    "research_candidate",
    "read_public_page",
    "score_candidate",
    "enrich_lead",
    "draft_outreach",
    "init_db",
    "save_leads",
    "list_leads",
    "get_lead",
    "update_lead",
    "add_suppression",
    "list_suppressed",
    "is_suppressed",
    "delete_leads",
    "send_approved_email",
]
