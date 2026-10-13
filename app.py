"""Streamlit page for subscribers: enter the password, see the Alpha10 Google Sheet.
The password and the Sheet ID live only in Streamlit secrets; the app downloads the Sheet on the server and shows
its rows, so the Google link never reaches anyone's browser."""
import hmac
import io

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


@st.cache_data(ttl=300, show_spinner=False)
def load_sheet(sheet_id: str) -> dict[str, pd.DataFrame]:
    # Works while the Sheet is shared "Anyone with the link: Viewer"; only this server ever sees the ID.
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    if not r.headers.get("Content-Type", "").startswith("application/vnd.openxmlformats"):
        raise RuntimeError("Google did not return the Sheet; check it is shared 'Anyone with the link'.")
    return pd.read_excel(io.BytesIO(r.content), sheet_name=None)


if check_password():
    st.title(st.secrets.get("title", "Alpha10"))
    try:
        with st.spinner("Loading…"):
            tabs = load_sheet(st.secrets["sheet_id"])
    except Exception as exc:
        print(f"load_sheet failed: {exc}")  # app log only: the message contains the Sheet URL
        st.error("Could not load the sheet right now. Please try again in a few minutes.")
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
