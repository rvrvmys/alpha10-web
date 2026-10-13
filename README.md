# Alpha10 subscriber page

Streamlit app: subscribers enter a password and see the Alpha10 Google Sheet, one tab per page, as images that
keep the Sheet's formatting and charts. The password and Sheet ID live only in Streamlit's Secrets (never in this
repo). The Sheet is exported on the server, so the Google link never reaches anyone's browser, and subscribers get
pictures rather than cells they could copy.

## Deploy (once)
1. Recommended: add a `[gcp_service_account]` section to Secrets (see the example) and share the Sheet with that
   account's `client_email`. The Sheet can then be Restricted, with viewer downloads off. Without a service account
   the Sheet must be "Anyone with the link: Viewer" with downloads allowed; the app reads the tab list from the Sheet's public view (if Google ever changes that page, it falls back to all tabs in one view).
2. share.streamlit.io > Create app > this repo, branch `main`, file `app.py`, pick a custom subdomain.
3. Advanced settings > Secrets: paste `.streamlit/secrets.toml.example` with your real password and Sheet ID.
4. After deploying, click Share and make the app public so subscribers can open it.

Change the password or Sheet any time in the app's Secrets; no code change needed.

## Local run
`pip install -r requirements.txt`, copy the example to `.streamlit/secrets.toml` (git-ignored), then `streamlit run app.py`.
