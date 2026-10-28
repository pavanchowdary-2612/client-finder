"""Integrations package for external services and persistence."""

from .mailer import send_approved_email
from .storage import (
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

__all__ = [
    "send_approved_email",
    "init_db",
    "save_leads",
    "list_leads",
    "get_lead",
    "update_lead",
    "add_suppression",
    "list_suppressed",
    "is_suppressed",
    "delete_leads",
]
