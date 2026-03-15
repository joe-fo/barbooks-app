import streamlit as st
import httpx

import os

API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1/chat")

st.set_page_config(page_title="Barbooks AI", page_icon="🏈")
st.title("Barbooks AI Agent 🏈")
st.write("Ask questions about NFL Touchdown Leaders! (Context: `book_id=nfl`, `page_id=touchdown`)")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# React to user input
if prompt := st.chat_input("Ask about the list... (e.g. 'Is Tom Brady on this list?')"):
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Call FastAPI Backend
    payload = {
        "user_message": prompt,
        "book_id": "nfl",
        "page_id": "touchdown"
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
            
            st.session_state.messages.append({"role": "assistant", "content": out_msg})
        elif response.status_code == 422:
            st.error("Input validation failed. Make sure your message is under 150 characters.")
        else:
            st.error(f"Error from server: {response.text}")
            
    except httpx.RequestError as exc:
        st.error(f"An error occurred while requesting {exc.request.url!r}. Is the FastAPI backend running?")
