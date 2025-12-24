import streamlit as st
import requests
import time
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURATION & SESSION STATE ---
st.set_page_config(page_title="QA-Runner", page_icon="🧪", layout="wide")

if "api_url" not in st.session_state:
    st.session_state.api_url = "http://qa-backend:8000"
if "debug_mode" not in st.session_state:
    st.session_state.debug_mode = False
if "log_level" not in st.session_state:
    st.session_state.log_level = "INFO"
if "active_job_id" not in st.session_state:
    st.session_state.active_job_id = None

# --- UI HELPER FUNCTIONS ---
def get_api_endpoint(path):
    return f"{st.session_state.api_url.rstrip('/')}/{path.lstrip('/')}"

def poll_job_status(job_id):
    """Polls the backend for job status and updates progress UI."""
    progress_bar = st.progress(0)
    status_text = st.empty()
    log_area = st.empty()
    
    while True:
        try:
            response = requests.get(get_api_endpoint(f"jobs/{job_id}"))
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "running")
                progress = data.get("progress", 0)
                logs = data.get("logs", [])[-20:] # Letzte 20 Zeilen
                
                # Update UI
                progress_bar.progress(progress / 100)
                status_text.text(f"Status: {status.upper()} ({progress}%)")
                log_area.code("\n".join(logs), language="text")
                
                if status in ["success", "failed"]:
                    return data
            else:
                st.error(f"Error polling job: {response.status_code}")
                break
        except Exception as e:
            st.error(f"Connection error: {e}")
            break
        
        time.sleep(0.5)
    return None

# --- HEADER ---
st.title("🧪 QA-Runner")
st.markdown("---")

# --- TABS ---
tab_files, tab_db, tab_net, tab_dev, tab_settings = st.tabs([
    "📂 Files", "🗄️ Database", "🌐 Network", "💻 Dev", "⚙️ Settings"
])

# --- FILES TAB ---
with tab_files:
    st.header("File Validation Test")
    uploaded_file = st.file_uploader("Upload CSV-Report", type=["csv"])
    
    if st.button("Run Files Test", disabled=uploaded_file is None):
        with st.spinner("Initializing Test..."):
            # Mock API Call for Job Creation
            files = {"file": uploaded_file.getvalue()}
            try:
                # Beispiel-Request an Backend
                resp = requests.post(get_api_endpoint("run/files"), files={"file": uploaded_file})
                if resp.status_code == 202:
                    job_id = resp.json().get("job_id")
                    result = poll_job_status(job_id)
                    
                    if result:
                        st.success("Test Completed!")
                        col1, col2, col3 = st.columns(3)
                        res_data = result.get("result", {})
                        col1.metric("Row Count", res_data.get("row_count", 0))
                        col2.metric("Edge Files Check", "Passed" if res_data.get("edge_check") else "Failed")
                        col3.download_button("Download Logs", "\n".join(result.get("logs", [])), file_name="qa_log.txt")
                        
                        st.subheader("CSV Sample Data")
                        if "sample" in res_data:
                            st.dataframe(pd.DataFrame(res_data["sample"]))
                        
                        with st.expander("Show Raw Result JSON"):
                            st.json(result)
                            st.button("Copy Result", on_click=lambda: st.write("JSON Copied to Clipboard (Simulated)"))
                else:
                    st.error(f"Backend Error: {resp.status_code}")
            except Exception as e:
                st.error(f"Could not connect to Backend: {e}")

# --- DATABASE TAB ---
with tab_db:
    st.header("PostgreSQL Connection Check")
    if st.button("Test PostgreSQL"):
        with st.spinner("Connecting..."):
            try:
                r = requests.get(get_api_endpoint("test/db"), timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    st.success("Connection Established")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Version", data.get("version", "N/A"))
                    c2.metric("Orders Count", data.get("orders_count", 0))
                    c3.metric("Latency", f"{data.get('latency_ms', 0)} ms")
                else:
                    st.error("Database connection failed.")
            except Exception as e:
                st.error(f"Error: {e}")

# --- NETWORK TAB ---
with tab_net:
    st.header("Network Connectivity")
    col_host, col_ip = st.columns(2)
    domain_input = col_host.text_input("Domain", value="google.com")
    ip_input = col_ip.text_input("IP Address", value="8.8.8.8")
    
    c1, c2 = st.columns(2)
    if c1.button("Test Domain"):
        with st.spinner(f"Pinging {domain_input}..."):
            r = requests.post(get_api_endpoint("test/network"), json={"target": domain_input})
            res = r.json()
            st.info(f"Response: {res.get('code')}")
            st.metric("Latency", f"{res.get('latency')} ms")
            st.text_area("Body Preview", res.get("body", "")[:200])

    if c2.button("Test IP"):
        with st.spinner(f"Pinging {ip_input}..."):
            r = requests.post(get_api_endpoint("test/network"), json={"target": ip_input})
            res = r.json()
            st.info(f"Response: {res.get('code')}")
            st.metric("Latency", f"{res.get('latency')} ms")

# --- DEV TAB ---
with tab_dev:
    st.header("Development Environment")
    if st.button("Check Development Environment"):
        try:
            r = requests.get(get_api_endpoint("dev/info"))
            info = r.json()
            
            st.subheader("System Metrics")
            cols = st.columns(4)
            cols[0].write(f"**Hostname:** {info.get('hostname')}")
            cols[1].write(f"**IP:** {info.get('ip')}")
            cols[2].write(f"**CPU:** {info.get('cpu_usage')}%")
            cols[3].write(f"**RAM:** {info.get('ram_usage')}%")
            
            st.info(f"**Docker Context:** {info.get('docker_context', 'N/A')}")
            
            st.subheader("Beweis VPS")
            st.code(info.get("vps_proof", "No proof found."), language="bash")
        except Exception as e:
            st.error(f"Dev Info not available: {e}")

# --- SETTINGS TAB ---
with tab_settings:
    st.header("Application Settings")
    st.session_state.api_url = st.text_input("API URL", value=st.session_state.api_url)
    st.session_state.debug_mode = st.toggle("Debug Mode", value=st.session_state.debug_mode)
    st.session_state.log_level = st.select_slider(
        "Logs Level", 
        options=["DEBUG", "INFO", "WARNING", "ERROR"], 
        value=st.session_state.log_level
    )
    
    if st.session_state.debug_mode:
        st.write("---")
        st.subheader("Session State Debug")
        st.write(st.session_state)

# --- FOOTER ---
st.markdown("---")
st.caption(f"QA-Runner Frontend | v1.29 | Backend: {st.session_state.api_url}")