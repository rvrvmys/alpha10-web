"""Streamlit page for subscribers: enter the password, see the Alpha10 Google Sheet.
The password and the Sheet ID live only in Streamlit secrets. The app exports each tab to PDF on the server and
shows it as an image, so formatting and charts look as in Google Sheets, the Google link never reaches anyone's
browser, and there is no table to copy."""
import hmac
import html as htmllib
import io
import json
import re

import pypdfium2 as pdfium
from PIL import Image, ImageChops
import requests
import streamlit as st

st.set_page_config(page_title="Alpha10", layout="wide")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
# Landscape, fit each tab to the page width, no gridlines, page numbers or titles: looks like the Sheet on screen.
PDF_OPTS = ("format=pdf&size=A4&portrait=false&fitw=true&gridlines=false&printtitle=false&sheetnames=false"
            "&pagenum=UNDEFINED&top_margin=0.2&bottom_margin=0.2&left_margin=0.2&right_margin=0.2")


class SheetError(Exception):
    """A load failure whose message is safe to show (it never contains the Sheet ID or URL)."""


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


def sheet_id_from(value: str) -> str:
    # Accept either the bare ID or a full Google Sheets URL pasted into Secrets.
    m = re.search(r"/d/([\w-]+)", value)
    return (m.group(1) if m else value).strip()


def auth_headers() -> dict:
    # With a service account in Secrets the Sheet can stay Restricted (shared only with that account).
    # Without one, the Sheet must be "Anyone with the link: Viewer" with downloads allowed for viewers.
    if "gcp_service_account" not in st.secrets:
        return {}
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]),
                                                                  scopes=SCOPES)
    creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}"}


def fetch(url: str, headers: dict, html_ok: bool = False) -> requests.Response:
    try:
        r = requests.get(url, headers=headers, timeout=60)
    except requests.RequestException as exc:
        raise SheetError(f"The app server could not reach Google ({type(exc).__name__}).") from None
    ctype = r.headers.get("Content-Type", "")
    if r.status_code == 404:
        raise SheetError("Google says no Sheet has this ID. Check sheet_id in the app's Secrets.")
    if r.status_code in (401, 403) or ("text/html" in ctype and not html_ok):
        raise SheetError(
            "Google refused the download. With a service account: share the Sheet with its client_email. "
            "Without one: set Share > General access to 'Anyone with the link' (Viewer) and, under the gear, "
            "allow viewers to download, print and copy."
        )
    if r.status_code != 200:
        raise SheetError(f"Google answered with HTTP {r.status_code} ({ctype.split(';')[0] or 'no type'}).")
    return r


def public_tabs(sheet_id: str) -> list[tuple[str, str]]:
    """(title, gid) of each visible tab, read from the Sheet's public HTML view. Empty if Google changes that page."""
    html = fetch(f"https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview", {}, html_ok=True).text
    tabs = re.findall(r'items\.push\(\{name: "((?:[^"\\]|\\.)*)",.*?gid: "(\d+)"', html)
    if not tabs:
        tabs = [(htmllib.unescape(name), gid) for gid, name in re.findall(r'id="sheet-button-(\d+)"[^>]*>\s*<a[^>]*>([^<]+)<', html)]
    out = []
    for name, gid in tabs:
        try:  # names come JS-escaped, e.g. \x26 for &
            name = json.loads('"' + re.sub(r"\\x([0-9a-fA-F]{2})", r"\\u00\1", name) + '"')
        except ValueError:
            pass
        if (name, gid) not in out:
            out.append((name, gid))
    return out


MAX_ZOOM = 2.0  # never enlarge a tab more than this when trimming its blank space


def content_box(img: Image.Image) -> tuple[int, int, int, int] | None:
    diff = ImageChops.difference(img, Image.new("RGB", img.size, "white")).convert("L")
    return diff.point(lambda v: 255 if v > 12 else 0).getbbox()  # ignore near-white noise


def pdf_to_pngs(data: bytes, pad: int = 24) -> list[bytes]:
    """Render each page and crop the blank space around the content, so the tab fills the screen width
    (bigger text). Every page of a tab gets the same left/right edges so its pages line up and share one zoom."""
    pdf = pdfium.PdfDocument(data)
    try:
        imgs = []
        for page in pdf:
            imgs.append(page.render(scale=3).to_pil().convert("RGB"))
            page.close()
    finally:
        pdf.close()
    boxes = [content_box(im) for im in imgs]
    found = [bx for bx in boxes if bx]
    if not found:
        return []
    width = imgs[0].width
    left = max(min(bx[0] for bx in found) - pad, 0)
    right = min(max(bx[2] for bx in found) + pad, width)
    right = min(max(right, left + int(width / MAX_ZOOM)), width)
    pages = []
    for im, bx in zip(imgs, boxes):
        if not bx:
            continue  # blank page
        buf = io.BytesIO()
        im.crop((left, max(bx[1] - pad, 0), right, min(bx[3] + pad, im.height))).save(buf, format="PNG", optimize=True)
        pages.append(buf.getvalue())
    return pages


@st.cache_data(ttl=300, show_spinner=False)
def load_sheet(sheet_id: str) -> dict[str, list[bytes]]:
    """Tab title -> PNG of each PDF page. Only this server ever sees the Sheet ID."""
    headers = auth_headers()
    base = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?{PDF_OPTS}"
    if not headers:
        try:
            tabs = public_tabs(sheet_id)
        except Exception as exc:
            print(f"tab list failed: {exc!r}")  # app log only
            tabs = []
        if not tabs:  # tab list unavailable: show the whole workbook in one view
            return {"": pdf_to_pngs(fetch(base, headers).content)}
        return {name: pdf_to_pngs(fetch(f"{base}&gid={gid}", headers).content) for name, gid in tabs}
    meta = fetch(f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
                 "?fields=sheets.properties(sheetId,title,hidden)", headers).json()
    tabs = {}
    for s in meta.get("sheets", []):
        p = s["properties"]
        if not p.get("hidden"):
            tabs[p["title"]] = pdf_to_pngs(fetch(f"{base}&gid={p['sheetId']}", headers).content)
    return tabs


def show(pages: list[bytes]) -> None:
    for png in pages:
        st.image(png, width="stretch")


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
    if len(tabs) == 1:
        show(next(iter(tabs.values())))
    else:
        for tab, pages in zip(st.tabs(list(tabs)), tabs.values()):
            with tab:
                show(pages)
    st.caption("Updates every 5 minutes.")
