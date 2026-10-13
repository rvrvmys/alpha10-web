"""Streamlit page for subscribers: enter the password, see the Alpha10 Google Sheet.
The password and the Sheet ID live only in Streamlit secrets; the app downloads the Sheet on the server and shows
its rows, so the Google link never reaches anyone's browser."""
import hmac
import io
import re

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Alpha10", layout="wide")


def check_password() -> bool:
    if st.session_state.get("ok"):
        return True
    st.title("Enter password to continue")
    with st.form("login"):
        pw = st.text_input("Password", type="password")
        go = st.form_submit_button("Open")
    if go:
        if hmac.compare_digest(pw.encode(), st.secrets["password"].encode()):
            st.session_state.ok = True
            st.rerun()
        st.error("Incorrect password. Please try again.")
    return False


class SheetError(Exception):
    """A load failure whose message is safe to show (it never contains the Sheet ID or URL)."""


def sheet_id_from(value: str) -> str:
    # Accept either the bare ID or a full Google Sheets URL pasted into Secrets.
    m = re.search(r"/d/([\w-]+)", value)
    return (m.group(1) if m else value).strip()


@st.cache_data(ttl=300, show_spinner=False)
def load_sheet(sheet_id: str) -> dict[str, pd.DataFrame]:
    # Works while the Sheet is shared "Anyone with the link: Viewer"; only this server ever sees the ID.
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    try:
        r = requests.get(url, timeout=30)
    except requests.RequestException as exc:
        raise SheetError(f"The app server could not reach Google ({type(exc).__name__}).") from None
    ctype = r.headers.get("Content-Type", "")
    if r.status_code == 404:
        raise SheetError("Google says no Sheet has this ID. Check sheet_id in the app's Secrets.")
    if r.status_code in (401, 403) or "text/html" in ctype:
        raise SheetError(
            "Google asked the app to sign in, so the Sheet is not public to the app. In the Sheet: Share > "
            "General access > 'Anyone with the link' (Viewer); and in Share > settings (gear) keep "
            "'Viewers and commenters can see the option to download, print, and copy' ticked."
        )
    if r.status_code != 200 or not ctype.startswith("application/vnd.openxmlformats"):
        raise SheetError(f"Google answered with HTTP {r.status_code} ({ctype.split(';')[0] or 'no type'}).")
    return pd.read_excel(io.BytesIO(r.content), sheet_name=None)


if check_password():
    st.title(st.secrets.get("title", "Alpha10"))
    try:
        with st.spinner("Loading…"):
            tabs = load_sheet(sheet_id_from(st.secrets["sheet_id"]))
    except SheetError as exc:
        st.error(f"Could not load the sheet: {exc}")
        st.stop()
    except Exception as exc:
        print(f"load_sheet failed: {exc!r}")  # app log only: the message may contain the Sheet URL
        st.error(f"Could not load the sheet ({type(exc).__name__}). Please try again in a few minutes.")
        st.stop()
    tabs = {n: df.dropna(how="all").dropna(axis=1, how="all") for n, df in tabs.items()}
    tabs = {n: df for n, df in tabs.items() if not df.empty}
    if not tabs:
        st.info("The sheet is empty.")
    elif len(tabs) == 1:
        st.dataframe(next(iter(tabs.values())), hide_index=True, width="stretch")
    else:
        for tab, df in zip(st.tabs(list(tabs)), tabs.values()):
            with tab:
                st.dataframe(df, hide_index=True, width="stretch")
    st.caption("Updates every 5 minutes.")
