import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1/chat")
_API_BASE = API_URL.removesuffix("/api/v1/chat")

# Read routing params from URL query string (e.g. ?book_id=nfl&page_id=9)
# Default to NFL book page 1 if params are absent
_DEFAULT_BOOK_ID = "nfl"
_DEFAULT_PAGE_ID = "1"

params = st.query_params
book_id = params.get("book_id") or _DEFAULT_BOOK_ID
page_id = params.get("page_id") or _DEFAULT_PAGE_ID

# Reflect defaults back into the URL so the page is shareable/bookmarkable
if params.get("book_id") != book_id or params.get("page_id") != page_id:
    st.query_params["book_id"] = book_id
    st.query_params["page_id"] = page_id

st.set_page_config(page_title="Barbooks AI", page_icon="🏈")
st.title("Barbooks AI Agent 🏈")

# Fetch page info to display the trivia question prominently
_page_ok = False
try:
    page_resp = httpx.get(f"{_API_BASE}/api/v1/page/{book_id}/{page_id}", timeout=10.0)
    if page_resp.status_code == 200:
        page_data = page_resp.json()
        st.header(page_data["title"])
        if page_data.get("description"):
            st.caption(page_data["description"])
        elif page_data.get("category"):
            st.caption(f"Category: {page_data['category']}")
        if page_data.get("data_status") in ("fetch_failed", "no_data"):
            st.warning(
                "Answer data is unavailable for this page"
                " — the source could not be loaded."
                " The host should check the data."
            )
        _page_ok = True
    elif page_resp.status_code == 404:
        st.error("Invalid page — please scan a valid QR code.")
        st.stop()
    else:
        st.warning("Could not load page info. You can still ask questions below.")
        st.caption(f"Book: `{book_id}` · Page: `{page_id}`")
except httpx.RequestError:
    st.warning(
        "Could not connect to the API to load page info."
        " You can still try asking below."
    )
    st.caption(f"Book: `{book_id}` · Page: `{page_id}`")

# Initialize chat history (keyed by book/page so scanning a new QR starts fresh)
session_key = f"messages_{book_id}_{page_id}"
if session_key not in st.session_state:
    st.session_state[session_key] = []

messages = st.session_state[session_key]

# Display chat messages from history on app rerun
for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# React to user input
if prompt := st.chat_input("Ask a question about this page..."):
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    messages.append({"role": "user", "content": prompt})

    # Call FastAPI Backend
    payload = {
        "user_message": prompt,
        "book_id": book_id,
        "page_id": page_id,
    }

    try:
        response = httpx.post(API_URL, json=payload, timeout=30.0)

        if response.status_code == 200:
            data = response.json()
            answer = data.get("answer", "No answer returned.")
            source = data.get("source", "unknown")

            out_msg = f"{answer} *(Source: {source})*"
            # Display assistant response
            with st.chat_message("assistant"):
                st.markdown(out_msg)

            messages.append({"role": "assistant", "content": out_msg})
        elif response.status_code == 422:
            st.error(
                "Input validation failed."
                " Make sure your message is under 150 characters."
            )
        else:
            st.error(f"Error from server: {response.text}")

    except httpx.RequestError as exc:
        st.error(
            f"An error occurred while requesting {exc.request.url!r}."
            " Is the FastAPI backend running?"
        )
