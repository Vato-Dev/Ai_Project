import os
import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
st.title("Support Request Copilot")
st.caption("Suggestions require human review. The app does not perform external actions.")
api_url = os.getenv("API_URL", "http://localhost:8000")
with st.form("request"):
    subject = st.text_input("Subject", "Cannot reset password")
    text = st.text_area("Request", "The reset link expires immediately after I open it.")
    submitted = st.form_submit_button("Analyze")
if submitted:
    try:
        response = httpx.post(
            api_url + "/api/analyze",
            json={"subject": subject, "text": text},
            timeout=75,
            trust_env=False,
        )
        response.raise_for_status()
        st.json(response.json())
        st.info("Review the suggestion before using it.")
    except httpx.HTTPStatusError as exc:
        st.error(f"API returned {exc.response.status_code}. Check the input or inference server.")
    except httpx.RequestError:
        st.error("API is unreachable. Check API_URL and the backend process.")
