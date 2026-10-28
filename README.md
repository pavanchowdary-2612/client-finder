# Client Finder

Client Finder is a local lead-research and outreach workspace. It finds candidate businesses, checks public websites for evidence and published business contact details, ranks leads, drafts outreach, and stores the results in a local SQLite database.

## Workflow

1. **Chat:** Describe the businesses, region, and service in plain language. The assistant asks a follow-up if a key detail is missing.
2. **Discovery:** Run three focused web searches through Tavily (default) or Brave Search and deduplicate candidate domains.
3. **Research:** Read each candidate's public website and up to three relevant contact/about pages. Keep source URLs and evidence with the lead.
4. **Qualification:** Apply a visible heuristic fit score and store the matching signals.
5. **Drafting:** Use Groq by default, optionally OpenAI, or the local template fallback. Drafts are editable.
6. **Review:** Manage statuses, notes, evidence, CSV export, and a do-not-contact list.
7. **Sending:** Ask the chat to email the discovered brands, select recipients, review each draft, and confirm the send. Approved messages are sent via SMTP and marked Contacted. Social DMs are not automated.

The app is intentionally organized as a small orchestrated workflow rather than six independently running agents. Its specialist steps are separate modules, which keeps the workflow easy to review and extend.

## Run locally (Windows PowerShell)

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
# Add your API keys and sender details to .env
.\scripts\run.ps1
```

Tavily is the default search provider; add `TAVILY_API_KEY` to `.env`. Brave Search is an optional alternative using `BRAVE_SEARCH_API_KEY`. Groq is the default for flexible chat understanding and AI drafting; add `GROQ_API_KEY` and optionally `GROQ_MODEL`. OpenAI is another option. Chat search and template drafts still work without an LLM key using the local fallback. Configure SMTP SSL settings (normally port 465) only if you want the app to send approved emails. SMTP credentials belong in `.env`, which is ignored by Git.

## Project layout

```text
app.py                       Streamlit main entrypoint
requirements.txt             Python dependencies
data/leads.db                Local SQLite database (git-ignored)
scripts/
  setup.ps1                  Environment setup and dependency installation
  run.ps1                    App launch script
client_finder/
  core/                      Core settings and security (SSRF prevention)
    settings.py
    security.py
  services/                  Business logic & pipeline services
    discovery.py             Tavily / Brave web search and deduplication
    research.py              Web crawling and contact extraction
    qualification.py         Heuristic fit scoring
    drafting.py              AI & template outreach generation
    workflow.py              Orchestrates discovery through drafting
  integrations/              Persistence and external messaging
    storage.py               SQLite database and suppression list
    mailer.py                SMTP email sender
  ui/                        Modular Streamlit user interface components
    sidebar.py               Workspace settings and API keys
    tab_discover.py          Chat-led natural-language search and prospect results
    tab_pipeline.py          CRM pipeline, lead editor, CSV export, and email sender
    tab_suppression.py       Do-not-contact management
```

## Important limits

- Search results and extracted details can be stale or wrong. Inspect the cited source before outreach.
- Fit scores are heuristics, not verified market predictions.
- Only published business contacts are extracted. The system does not guess private addresses.
- Email sending requires a human click for each message and a configured sender identity. The app adds an opt-out line and postal address to the message; you are responsible for applicable marketing and privacy requirements in the recipient's region.
- Instagram and other social DMs are not automated. Use platform-approved integrations and access where available.
- Leads and suppression records are stored locally in `leads.db`. Back it up if you need to preserve the data.
