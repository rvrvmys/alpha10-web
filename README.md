# Alpha10 subscriber page

Streamlit app: subscribers enter a password and see the Alpha10 Google Sheet as tables. The password and the
Sheet ID live only in Streamlit's Secrets (never in this repo), and the Sheet is downloaded on the server, so the
Google link never reaches anyone's browser.

## Deploy (once)
1. Keep the Sheet shared as "Anyone with the link: Viewer".
2. share.streamlit.io > Create app > this repo, branch `main`, file `app.py`, pick a custom subdomain.
3. Advanced settings > Secrets: paste `.streamlit/secrets.toml.example` with your real password and Sheet ID.
4. After deploying, click Share and make the app public so subscribers can open it.

Change the password or Sheet any time in the app's Secrets; no code change needed.

## Local run
`pip install -r requirements.txt`, copy the example to `.streamlit/secrets.toml` (git-ignored), then `streamlit run app.py`.
