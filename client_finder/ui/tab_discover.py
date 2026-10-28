import os
import re
import hashlib

import requests
import streamlit as st

from ..integrations.mailer import send_approved_email
from ..integrations.storage import is_suppressed, list_leads, save_leads, update_lead
from ..services.chat_intent import interpret_message
from ..services.drafting import draft_outreach
from ..services.workflow import run_lead_workflow


def _wants_to_send(message: str) -> bool:
    return bool(re.search(
        r"\bsend\b.{0,40}\b(?:email|emails|mail)\b|\b(?:email|mail)\s+(?:them|these|all|the brands)\b",
        message,
        re.I,
    ))


def _extract_brief(message: str, prior: dict) -> dict:
    """Fill a small search brief from natural language and explicit follow-up answers."""
    brief = dict(prior)
    text = message.strip().strip(".!? ")
    lower = text.lower()

    loc = re.search(r"\b(?:in|near|around|within)\s+(.+?)(?=\s*(?:,\s*)?(?:who|that|which|for|needing|need|looking|launched|new|with|top|first|send|email|mail|contact)\b|$)", text, re.I)
    if loc:
        brief["location"] = loc.group(1).strip(" ,.?!")

    # The niche is commonly stated before a location: "find skincare brands in India".
    cat = re.search(r"\b(?:find|search(?:\s+for)?|show(?:\s+me)?|get\s+me|looking\s+for)\s+(.+?)(?=\s+(?:in|near|around|within)\b|$)", text, re.I)
    if cat:
        category = cat.group(1).strip(" ,.?!")
        category = re.sub(r"^(?:(?:the|me|some|new|newly launched|newly released|recent|recently launched|recently released|independent|emerging|local|small|top|best)\s+)+", "", category, flags=re.I)
        category = re.sub(r"\b(?:businesses|companies|brands?|prospects|clients|leads|labels?)$", "", category, flags=re.I).strip()
        if category:
            if category.lower() in {"cloth", "clothes", "apparel", "garments", "fashion"}:
                category = "clothing"
            brief["category"] = category

    offer = re.search(r"\b(?:need|needing|looking\s+for|could\s+use|for|who\s+need|that\s+need)\s+(.+?)(?=\s+(?:in|near|around|launched|new)\b|$)", text, re.I)
    if offer:
        brief["offer"] = offer.group(1).strip(" ,.?!")

    # A short reply answers the one detail the assistant just requested.
    waiting = st.session_state.get("waiting_for")
    if waiting and len(text.split()) <= 8 and not any(re.search(rf"\b{word}\b", lower) for word in ("find", "search", "show", "looking")):
        if waiting == "location" and "location" not in brief:
            brief["location"] = text
        elif waiting == "offer" and "offer" not in brief:
            brief["offer"] = text
        elif waiting == "category" and "category" not in brief:
            brief["category"] = "clothing" if text.lower() in {"cloth", "clothes", "apparel", "garments", "fashion"} else text

    requested_count = re.search(r"\b(?:top|first|show|find)\s+(\d{1,2})\b|\b(\d{1,2})\s+(?:brands|results|leads|ones)\b", lower)
    if requested_count:
        brief["count"] = max(1, min(30, int(requested_count.group(1) or requested_count.group(2))))

    if re.search(r"\b(last\s+year|12\s+months|year)\b", lower):
        brief["recency"] = "launched in the last year"
    elif re.search(r"\b(upcoming|soon)\b", lower):
        brief["recency"] = "upcoming or recently launched"
    elif re.search(r"\b(last\s+6\s+months|6\s+months)\b", lower):
        brief["recency"] = "launched in the last 6 months"
    elif re.search(r"\b(recent|recently launched|recently released|new|newly launched|released)\b", lower):
        brief["recency"] = "launched in the last 6 months"
    return brief


def _show_leads(leads: list[dict], config: dict) -> None:
    if not leads:
        st.info("No brands passed the site and launch checks for this request. Try a broader launch window or remove ‘recently released’ to include established brands.")
        return
    st.markdown(f"### {len(leads)} prospects found")
    outreach_mode = st.session_state.get("outreach_mode", False)
    sender_email = config.get("sender_email", "")
    sender_name = config.get("sender_name", "")
    business_name = config.get("business_name", "")
    sender_address = config.get("sender_address", "")
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_user = os.getenv("SMTP_USERNAME", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "465"))
    except ValueError:
        smtp_port = 465
        st.warning("SMTP_PORT must be a number; using 465 for this session.")
    mail_configured = all((sender_email, sender_address, smtp_host, smtp_user, smtp_pass))

    if outreach_mode:
        st.info("Choose the brands to contact and review each email. Nothing is sent until you confirm below.")
        if not mail_configured:
            st.warning("Email sending needs sender email and postal address in Workspace settings, plus SMTP_HOST, SMTP_USERNAME, and SMTP_PASSWORD in `.env`.")

    selection_generation = st.session_state.get("selection_generation", 0)
    for index, lead in enumerate(leads):
        key = str(lead.get("id") or lead.get("website") or index)
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                title_col, action_col = st.columns([5, 1])
                with title_col:
                    st.markdown(f"#### {lead['name']}")
                with action_col:
                    if st.button("Draft email", key=f"create_draft_{key}", help=f"Generate a personalized email for {lead['name']}."):
                        draft, draft_type = draft_outreach(
                            lead,
                            st.session_state.get("latest_search_offer", ""),
                            config.get("sender_name", ""),
                            config.get("business_name", ""),
                            config.get("llm_key", ""),
                            config.get("model", ""),
                            config.get("llm_provider", "template only"),
                        )
                        lead["draft"] = draft
                        lead["draft_type"] = draft_type
                        lead["draft_subject"] = f"{config.get('business_name') or config.get('sender_name') or 'Introduction'} × {lead['name']}"
                        if lead.get("id"):
                            update_lead(lead["id"], draft_subject=lead["draft_subject"], draft=draft)
                        st.session_state[f"draft_open_{key}"] = True
                        st.session_state[f"draft_version_{key}"] = st.session_state.get(f"draft_version_{key}", 0) + 1
                st.caption(f"{lead.get('location') or 'Location not confirmed'}  ·  {lead.get('status', 'Needs review')}")
                st.write(lead.get("evidence") or "No search snippet was returned.")
                if lead.get("launch_evidence"):
                    st.info(f"Recent launch evidence ({lead.get('launch_date') or 'date not listed'}): {lead['launch_evidence'][:450]}")
                    if lead.get("launch_source_url"):
                        st.markdown(f"[View launch announcement]({lead['launch_source_url']})")
                st.markdown(f"[Visit website]({lead['website']})")
                if lead.get("contact_email"):
                    st.markdown(f"**Public contact:** [{lead['contact_email']}](mailto:{lead['contact_email']})")
                if lead.get("contact_phone"):
                    st.markdown(f"**Phone:** [{lead['contact_phone']}](tel:{lead['contact_phone']})")
                elif lead.get("contact_page"):
                    st.markdown(f"**Phone:** Not published · [Check contact page]({lead['contact_page']})")
                else:
                    st.caption("No public phone number found")
                if not lead.get("contact_email") and not lead.get("contact_phone") and not lead.get("contact_page"):
                    st.caption("No public email or contact page found")
            with right:
                st.metric("Fit", f"{lead['fit_score']}/100")
            with st.expander("Research details"):
                st.markdown(f"**Published business email:** {lead.get('contact_email') or 'Not found'}")
                if lead.get("email_source"):
                    st.markdown(f"**Email source:** [{lead['email_source']}]({lead['email_source']})")
                if lead.get("phone_source"):
                    st.markdown(f"**Phone source:** [{lead['phone_source']}]({lead['phone_source']})")
                st.write("**Fit signals:** " + ("; ".join(lead.get("fit_reasons", [])) or "Limited evidence"))
                draft_method = lead.get("draft_type") or ("Not drafted yet — use Draft email." if not lead.get("draft") else "Template draft")
                st.caption(f"Draft method: {draft_method} Review the evidence before contacting.")

            if st.session_state.get(f"draft_open_{key}"):
                version = st.session_state.get(f"draft_version_{key}", 1)
                with st.expander(f"Email draft for {lead['name']}", expanded=True):
                    subject = st.text_input(
                        "Subject",
                        value=lead.get("draft_subject") or f"{config.get('business_name') or config.get('sender_name') or 'Introduction'} × {lead['name']}",
                        key=f"draft_subject_{key}_{version}",
                    )
                    body = st.text_area(
                        "Message",
                        value=lead.get("draft", ""),
                        height=200,
                        key=f"draft_text_{key}_{version}",
                    )
                    if st.button("Save draft", key=f"save_draft_{key}_{version}"):
                        lead["draft"] = body
                        lead["draft_subject"] = subject
                        if lead.get("id"):
                            update_lead(lead["id"], draft_subject=subject, draft=body)
                        st.success("Draft saved to this lead.")

            if outreach_mode:
                blocked = lead.get("opted_out") or is_suppressed(lead.get("contact_email", ""))
                disabled = blocked or not lead.get("contact_email") or not lead.get("draft") or lead.get("status") == "Contacted"
                reason = "Already contacted" if lead.get("status") == "Contacted" else "Suppressed" if blocked else "No public email" if not lead.get("contact_email") else "Draft email first" if not lead.get("draft") else ""
                st.checkbox(
                    f"Include {lead['name']} ({lead.get('contact_email') or reason})",
                    key=f"send_selected_{selection_generation}_{key}",
                    disabled=disabled,
                )
                if lead.get("contact_email") and lead.get("draft"):
                    with st.expander(f"Review email to {lead['name']}", expanded=True):
                        st.text_input(
                            "Subject",
                            value=lead.get("draft_subject") or f"{business_name or sender_name or 'Introduction'} × {lead['name']}",
                            key=f"send_subject_{key}",
                        )
                        st.text_area(
                            "Message",
                            value=lead.get("draft", ""),
                            height=190,
                            key=f"send_body_{key}",
                        )
                elif lead.get("contact_email"):
                    st.caption("Draft this message with the button beside the brand name before selecting it to send.")

    if outreach_mode:
        selected = [
            lead for index, lead in enumerate(leads)
            if st.session_state.get(f"send_selected_{selection_generation}_{lead.get('id') or lead.get('website') or index}", False)
            and lead.get("contact_email")
            and lead.get("draft")
            and lead.get("status") != "Contacted"
            and not lead.get("opted_out")
            and not is_suppressed(lead.get("contact_email", ""))
        ]
        if selected:
            st.markdown(f"**Ready to send:** {len(selected)} email{'s' if len(selected) != 1 else ''}")
        generation = st.session_state.get("outreach_generation", 0)
        review_parts = []
        for lead in selected:
            lead_key = str(lead.get("id") or lead.get("website"))
            subject = st.session_state.get(f"send_subject_{lead_key}", f"{business_name or sender_name or 'Introduction'} × {lead['name']}")
            body = st.session_state.get(f"send_body_{lead_key}", lead.get("draft", ""))
            review_parts.append(f"{lead_key}|{subject}|{body}")
        review_signature = "\n".join(review_parts)
        approval_key = f"confirm_outreach_{generation}_{hashlib.sha256(review_signature.encode()).hexdigest()[:12]}"
        approved = st.checkbox(
            "I reviewed every selected recipient and message, and approve sending these emails.",
            key=approval_key,
            disabled=not selected or not mail_configured,
        )
        if st.button("Send approved emails", type="primary", disabled=not selected or not mail_configured or not approved):
            sent = []
            failures = []
            for index, lead in enumerate(selected):
                key = str(lead.get("id") or lead.get("website") or index)
                subject = st.session_state.get(f"send_subject_{key}", lead.get("draft_subject") or f"{business_name or sender_name or 'Introduction'} × {lead['name']}")
                body = st.session_state.get(f"send_body_{key}", lead.get("draft", ""))
                try:
                    send_approved_email(
                        host=smtp_host,
                        port=smtp_port,
                        username=smtp_user,
                        password=smtp_pass,
                        sender_email=sender_email,
                        sender_name=sender_name,
                        recipient=lead["contact_email"],
                        subject=subject,
                        body=body,
                        postal_address=sender_address,
                        business_name=business_name,
                    )
                    if lead.get("id"):
                        update_lead(lead["id"], draft_subject=subject, draft=body, status="Contacted")
                    sent.append(lead["name"])
                except Exception as exc:
                    failures.append(f"{lead['name']}: {exc}")
            if sent:
                for lead in st.session_state.get("latest_search", []):
                    if lead.get("name") in sent:
                        lead["status"] = "Contacted"
                st.session_state.chat_messages.append({"role": "assistant", "content": f"Email sent to {len(sent)} brand{'s' if len(sent) != 1 else ''}: {', '.join(sent)}."})
            if failures:
                st.session_state.chat_messages.append({"role": "assistant", "content": "Some emails could not be sent: " + " · ".join(failures)})
            if sent or failures:
                st.session_state.outreach_mode = bool(failures)
                st.rerun()


def render_discover_tab(config: dict) -> None:
    """Chat-first natural-language lead discovery."""
    st.markdown('<div class="hero"><div class="eyebrow">Prospecting, made conversational</div><h1>Who are you looking to meet?</h1><p>Describe the clients you want in plain language. I’ll research prospects and show you the evidence behind each match.</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="hint">Try: “Find independent skincare brands in India that could use product photography.”</div>', unsafe_allow_html=True)

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [{"role": "assistant", "content": "Tell me who you want to find and where. You can mention what you offer too, if it helps me find a better fit."}]
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Keep the result list directly under the conversation and above the input.
    if st.session_state.get("latest_search_ran"):
        st.divider()
        _show_leads(st.session_state.get("latest_search", []), config)

    prompt = st.chat_input("Describe your ideal clients…")
    if prompt:
        prior_brief = st.session_state.get("search_brief", {})
        used_local_fallback = False
        short_answer = st.session_state.get("waiting_for") and len(prompt.split()) <= 2
        current_results_send = st.session_state.get("latest_search_ran") and st.session_state.get("latest_search") and _wants_to_send(prompt)
        if short_answer or current_results_send:
            fallback_brief = _extract_brief(prompt, prior_brief)
            fallback_missing = [] if current_results_send else [key for key in ("category", "location") if not fallback_brief.get(key)]
            fallback_questions = {
                "category": "What kind of businesses should I look for? For example, clothing brands.",
                "location": "Where should I search? You can give me a city, region, or country.",
            }
            interpretation = {
                "brief": fallback_brief,
                "missing_fields": fallback_missing,
                "clarification_question": fallback_questions.get(fallback_missing[0], "") if fallback_missing else "",
                "wants_send": bool(current_results_send),
            }
        else:
            try:
                interpretation = interpret_message(
                    prompt,
                    prior_brief,
                    st.session_state.chat_messages,
                    api_key=config.get("llm_key", ""),
                    provider=config.get("llm_provider", "groq"),
                    model=config.get("model", ""),
                )
            except Exception:
                used_local_fallback = True
                fallback_brief = _extract_brief(prompt, prior_brief)
                fallback_missing = [key for key in ("category", "location") if not fallback_brief.get(key)]
                fallback_questions = {
                    "category": "What kind of businesses should I look for? For example, clothing brands.",
                    "location": "Where should I search? You can give me a city, region, or country.",
                }
                interpretation = {
                    "brief": fallback_brief,
                    "missing_fields": fallback_missing,
                    "clarification_question": fallback_questions.get(fallback_missing[0], "") if fallback_missing else "",
                    "wants_send": _wants_to_send(prompt),
                }

        requested_send = interpretation.get("wants_send", False) or _wants_to_send(prompt)
        latest = st.session_state.get("latest_search", [])
        if st.session_state.get("latest_search_ran") and latest and requested_send:
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            st.session_state.outreach_mode = True
            st.session_state.outreach_generation = st.session_state.get("outreach_generation", 0) + 1
            st.session_state.chat_messages.append({"role": "assistant", "content": "Click Draft email beside each brand you want to contact. Then select recipients, review the messages, and confirm when you’re ready to send."})
            st.rerun()

        st.session_state.outreach_mode = False
        st.session_state.selection_generation = st.session_state.get("selection_generation", 0) + 1
        st.session_state.outreach_generation = st.session_state.get("outreach_generation", 0) + 1
        st.session_state.latest_search = []
        st.session_state.latest_search_ran = False
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        if used_local_fallback and not st.session_state.get("local_fallback_notified", False):
            st.session_state.chat_messages.append({"role": "assistant", "content": "I’m using local chat understanding because no configured AI model is available. It works without an LLM; adding GROQ_API_KEY or OPENAI_API_KEY to `.env` enables more flexible interpretation."})
            st.session_state.local_fallback_notified = True
        elif not used_local_fallback:
            st.session_state.local_fallback_notified = False
        brief = interpretation["brief"]
        st.session_state.search_brief = brief
        missing = interpretation.get("missing_fields", [])
        if missing:
            st.session_state.waiting_for = missing[0]
            question = interpretation.get("clarification_question", "")
            if not question:
                question = "What kind of businesses and location should I search for?"
            st.session_state.chat_messages.append({"role": "assistant", "content": question})
            st.rerun()

        st.session_state.waiting_for = None
        st.session_state.search_brief = {}
        recency = brief.get("recency", "all brands")
        count = brief.get("count", 12)
        offer = brief.get("offer", "")
        target_description = f" that could use **{offer}**" if offer else ""
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": f"I’ll look for up to **{count} {brief['category']} brands** in **{brief['location']}**{target_description} ({recency}). I’ll check each brand’s own site for a public contact.",
        })
        search_key = config.get("search_key", "")
        if not search_key:
            key_env = "TAVILY_API_KEY" if config.get("search_provider") == "tavily" else "BRAVE_SEARCH_API_KEY"
            st.session_state.chat_messages.append({"role": "assistant", "content": f"Add {key_env} to `.env` to enable web search, then send your request again."})
            st.rerun()

        with st.status("Researching prospects…", expanded=True) as progress:
            st.write("Searching the web, checking public business websites, and reviewing fit signals.")

            def show_candidate_progress(index, total, candidate):
                progress.write(f"Checking official site {index} of {total}: {candidate.get('name', 'business')}")

            try:
                leads = run_lead_workflow(
                    category=brief["category"], location=brief["location"], recency=recency,
                    offer=offer, search_key=search_key, count=count,
                    sender_name=config.get("sender_name", ""), business_name=config.get("business_name", ""),
                    llm_key=config.get("llm_key", ""), llm_provider=config.get("llm_provider", "groq"),
                    model=config.get("model", ""), search_provider=config.get("search_provider", "tavily"),
                    progress_callback=show_candidate_progress,
                )
                for lead in leads:
                    if is_suppressed(lead.get("contact_email", "")):
                        lead["status"] = "Suppressed"
                        lead["opted_out"] = True
                save_leads(leads)
                saved_by_website = {lead["website"]: lead for lead in list_leads()}
                for lead in leads:
                    saved = saved_by_website.get(lead["website"])
                    if saved:
                        lead["id"] = saved["id"]
                st.session_state.latest_search = leads
                st.session_state.latest_search_offer = offer
                st.session_state.latest_search_ran = True
                progress.update(label=f"Research complete · {len(leads)} prospects", state="complete")
                st.session_state.chat_messages.append({"role": "assistant", "content": f"Research is complete. I found **{len(leads)}** matching prospects; the results are below."})
                if requested_send:
                    st.session_state.outreach_mode = True
                    st.session_state.outreach_generation = st.session_state.get("outreach_generation", 0) + 1
                    st.session_state.chat_messages.append({"role": "assistant", "content": "You also asked me to email them. Select recipients and review each draft below, then confirm to send."})
            except requests.HTTPError as exc:
                progress.update(label="Search provider error", state="error")
                status_code = getattr(exc.response, "status_code", "Unknown")
                st.session_state.chat_messages.append({"role": "assistant", "content": f"The search provider returned error {status_code}. Check your API key and provider plan."})
            except requests.RequestException as exc:
                progress.update(label="Search connection error", state="error")
                st.session_state.chat_messages.append({"role": "assistant", "content": f"Search could not complete: {exc}"})
            except Exception as exc:
                progress.update(label="Research workflow error", state="error")
                st.session_state.chat_messages.append({"role": "assistant", "content": f"The research workflow stopped: {exc}"})
        st.rerun()

