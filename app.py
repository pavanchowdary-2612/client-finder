from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from client_finder.integrations.storage import init_db
from client_finder.ui.sidebar import render_sidebar
from client_finder.ui.tab_discover import render_discover_tab
from client_finder.ui.tab_pipeline import render_pipeline_tab
from client_finder.ui.tab_suppression import render_suppression_tab

load_dotenv()
init_db()
st.set_page_config(page_title="Client Finder", page_icon="✳", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root { --ink:#17251f; --muted:#75817a; --green:#1d6749; --line:#e8ece8; --wash:#f6f8f5; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; color:var(--ink); }
.stApp { background:#fbfcfa; }
[data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none !important; }
.brandline { display:flex; align-items:center; gap:12px; margin:4px 0 28px; }
.brandmark { width:38px; height:38px; border-radius:13px; display:grid; place-items:center; color:white; background:#1d6749; font-size:19px; }
.brandname { font:800 19px 'Manrope',sans-serif; letter-spacing:-.04em; }
.eyebrow { color:#517260; text-transform:uppercase; letter-spacing:.14em; font-size:11px; font-weight:700; }
.hero h1 { font:800 clamp(30px,4vw,46px) 'Manrope',sans-serif; letter-spacing:-.055em; line-height:1.08; margin:8px 0 10px; }
.hero p { color:#68756d; font-size:16px; max-width:650px; }
.hint { border:1px solid var(--line); background:white; border-radius:14px; padding:12px 14px; color:#55635a; font-size:13px; margin:4px 0 18px; }
.stButton button, .stFormSubmitButton button { border-radius:10px; font-weight:600; }
[data-testid="stChatMessage"] { border:1px solid #edf0ec; border-radius:16px; padding:14px 16px; background:white; }
[data-testid="stChatInput"] { border-color:#dce4dc; border-radius:16px; }
div[data-testid="stMetric"] { background:white; border:1px solid var(--line); padding:14px 16px; border-radius:14px; }
.stTabs [data-baseweb="tab-list"] { gap:8px; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"] { height:48px; }
footer { visibility:hidden; }
</style>
<div class="brandline"><div class="brandmark">✳</div><div class="brandname">Client Finder</div></div>
""", unsafe_allow_html=True)

config = render_sidebar()
chat_tab, leads_tab, suppression_tab = st.tabs(["✳  Find clients", "▤  Lead pipeline", "⊘  Suppression list"])

with chat_tab:
    render_discover_tab(config)
with leads_tab:
    render_pipeline_tab(config)
with suppression_tab:
    render_suppression_tab()

st.caption("Every prospect is researched from public sources. Review evidence before outreach; email sending always requires your approval.")
