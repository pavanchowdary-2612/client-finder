import pandas as pd
import streamlit as st

from ..integrations.storage import add_suppression, list_suppressed


def render_suppression_tab() -> None:
    """Render the suppression (do not contact) list and addition form."""
    st.subheader("Do not contact")
    st.caption("Suppressed email addresses are excluded from sending and marked on matching leads.")

    with st.form("suppress_manual"):
        suppress_email = st.text_input("Email address")
        suppress_reason = st.text_input("Reason (optional)")
        add = st.form_submit_button("Suppress address")

    if add:
        if "@" in suppress_email:
            add_suppression(suppress_email, suppress_reason)
            st.success("Address added to the suppression list.")
            st.rerun()
        else:
            st.error("Enter a valid email address.")

    blocked = list_suppressed()
    if blocked:
        st.dataframe(pd.DataFrame(blocked), use_container_width=True, hide_index=True)
    else:
        st.info("No suppressed addresses yet.")
