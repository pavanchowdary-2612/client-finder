import os
import pandas as pd
import streamlit as st

from ..integrations.mailer import send_approved_email
from ..integrations.storage import add_suppression, is_suppressed, list_leads, update_lead

STATUS_OPTIONS = [
    "Needs review",
    "Qualified",
    "Ready to send",
    "Contacted",
    "Replied",
    "Not a fit",
    "Suppressed",
]


def render_pipeline_tab(config: dict) -> None:
    """Render the lead pipeline table, editing form, and approved sending actions."""
    leads = list_leads()
    if not leads:
        st.info("No leads saved. Start with a discovery search.")
        return

    df = pd.DataFrame([{
        "Brand": lead["name"],
        "Fit": lead["fit_score"],
        "Location": lead["location"],
        "Email": lead["contact_email"],
        "Phone": lead.get("contact_phone", ""),
        "Status": lead["status"],
        "Website": lead["website"],
    } for lead in leads])
    st.dataframe(df, use_container_width=True, hide_index=True)

    csv_data = (
        pd.DataFrame(leads)
        .drop(columns=["sources", "fit_reasons"], errors="ignore")
        .to_csv(index=False)
    )
    st.download_button(
        "Download leads as CSV",
        csv_data,
        "client-finder-leads.csv",
        "text/csv",
    )

    sender_email = config.get("sender_email", "")
    sender_name = config.get("sender_name", "")
    business_name = config.get("business_name", "")
    sender_address = config.get("sender_address", "")

    for lead in leads:
        with st.expander(f"{lead['name']}  ·  Fit {lead['fit_score']}  ·  {lead['status']}"):
            col_left, col_right = st.columns([3, 2])

            with col_left:
                st.markdown(f"**Website:** [{lead['website']}]({lead['website']})")
                st.markdown(f"**Search evidence:** {lead.get('evidence') or 'None'}")
                st.markdown(f"**Research notes:** {lead.get('research_notes') or 'No readable page text.'}")
                st.write("**Why it matched:** " + ("; ".join(lead.get("fit_reasons", [])) or "No match signals recorded"))

                if lead.get("sources"):
                    st.markdown("**Sources**")
                    for source in lead["sources"]:
                        st.markdown(f"- [{source['kind']}: {source['url']}]({source['url']})")

                with st.form(f"edit_{lead['id']}"):
                    email_val = st.text_input("Business email", value=lead.get("contact_email", ""))
                    phone_val = st.text_input("Public business phone", value=lead.get("contact_phone", ""))
                    subject_val = st.text_input("Email subject", value=lead.get("draft_subject", ""))
                    draft_val = st.text_area("Outreach draft", value=lead.get("draft", ""), height=230)
                    note_val = st.text_area("Internal notes", value=lead.get("notes", ""), height=70)
                    current_status = lead["status"] if lead["status"] in STATUS_OPTIONS else STATUS_OPTIONS[0]
                    status_val = st.selectbox("Pipeline status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(current_status))
                    saved = st.form_submit_button("Save lead")

                if saved:
                    update_lead(lead["id"], contact_email=email_val, contact_phone=phone_val, draft_subject=subject_val, draft=draft_val, notes=note_val, status=status_val)
                    st.rerun()

            with col_right:
                st.metric("Fit score", f"{lead['fit_score']} / 100")
                if lead.get("contact_email"):
                    st.caption(f"Contact found on: {lead.get('email_source') or 'source not recorded'}")
                if lead.get("contact_phone"):
                    st.markdown(f"[Call {lead['contact_phone']}](tel:{lead['contact_phone']})")
                if lead.get("contact_page"):
                    st.markdown(f"[Contact page]({lead['contact_page']})")
                st.caption(f"Draft type: {lead.get('draft_type') or 'Template draft'}")

                blocked = lead.get("opted_out") or is_suppressed(lead.get("contact_email", ""))
                smtp_host = os.getenv("SMTP_HOST")
                smtp_user = os.getenv("SMTP_USERNAME")
                smtp_pass = os.getenv("SMTP_PASSWORD")
                mail_configured = all((sender_email, sender_address, smtp_host, smtp_user, smtp_pass))

                if blocked:
                    st.error("Suppressed: this contact must not be emailed.")
                elif not lead.get("contact_email"):
                    st.info("Add a published business email before sending.")
                elif lead.get("status") != "Ready to send":
                    st.info("Review the evidence and draft, then set the status to Ready to send to enable email.")
                elif not mail_configured:
                    st.info("Configure SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, sender email, and postal address in `.env` to enable approved email sending.")
                else:
                    approved = st.checkbox(
                        "I reviewed this recipient, the evidence, and the message; send this email.",
                        key=f"approve_{lead['id']}",
                    )
                    if st.button("Send this email", key=f"send_{lead['id']}", type="primary", disabled=not approved):
                        try:
                            send_approved_email(
                                host=smtp_host,
                                port=int(os.getenv("SMTP_PORT", "465")),
                                username=smtp_user,
                                password=smtp_pass,
                                sender_email=sender_email,
                                sender_name=sender_name,
                                recipient=lead["contact_email"],
                                subject=lead.get("draft_subject") or f"{business_name or sender_name or 'Introduction'} × {lead['name']}",
                                body=lead.get("draft", ""),
                                postal_address=sender_address,
                                business_name=business_name,
                            )
                            update_lead(lead["id"], status="Contacted")
                            st.success("Email sent.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Email was not sent: {exc}")

                if lead.get("contact_email") and st.button("Add email to suppression list", key=f"suppress_{lead['id']}"):
                    add_suppression(lead["contact_email"], "Suppressed from lead record")
                    st.rerun()
