import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1/chat")

# Read routing params from URL query string (e.g. ?book_id=nfl&page_id=9)
params = st.query_params
book_id = params.get("book_id", "nfl")
page_id = params.get("page_id", "9")

st.set_page_config(page_title="Barbooks AI", page_icon="🏈")
st.title("Barbooks AI Agent 🏈")
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
