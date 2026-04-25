import streamlit as st
import pandas as pd
import os
import json
from google.cloud import bigquery
from google.oauth2 import service_account

# 1. SETUP: Page Config
st.set_page_config(page_title="DCS Factory Dashboard", layout="wide", page_icon="💎")

# 2. SETUP: Credentials (Smart Logic for Cloud vs. Local)
scopes = [
    "https://www.googleapis.com/auth/bigquery",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]

@st.cache_resource
def get_bq_client():
    if "gcp_service_account" in st.secrets:
        # We are on Streamlit Cloud - Use the Secrets Vault
        info = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        return bigquery.Client(credentials=credentials, project=info["project_id"])
    else:
        # We are on your Local Computer - Use the JSON file
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "dcs-system-494410-5488af32c0c7.json"
        return bigquery.Client()

# Initialize the client
try:
    client = get_bq_client()
except Exception as e:
    st.error(f"Authentication Error: {e}")
    st.stop()

# 3. SETTINGS: Database Details
PROJECT_ID = "dcs-system-494410"  
DATASET_ID = "Designers_system"
TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.T2_Design_Inventory"

# 4. DATA FETCHING (Cached for performance)
@st.cache_data(ttl=60) # Refreshes every minute
def load_data():
    query = f"SELECT * FROM `{TABLE_ID}` WHERE is_archived = FALSE"
    query_job = client.query(query)
    df = query_job.to_dataframe()
    return df

# Load data into the app
try:
    df = load_data()
except Exception as e:
    st.error(f"Error connecting to BigQuery: {e}")
    st.stop()

# 5. SIDEBAR: Navigation & Filters
st.sidebar.title("💎 DCS Workshop")
st.sidebar.subheader("Navigation Portal")

# Get unique designers for the dropdown
designers = sorted(df['designer_code'].unique().tolist())
# Map codes back to names if possible, otherwise use codes
view_selection = st.sidebar.selectbox("Select View:", ["Total Factory Summary"] + designers)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Refresh Dashboard"):
    st.cache_data.clear()
    st.rerun()

# 6. MAIN CONTENT
if view_selection == "Total Factory Summary":
    st.title("🏭 Total Factory Summary")
    
    # Global Metrics
    total_designs = len(df)
    completed = len(df[df['status'] == 'COMPLETED'])
    pending = total_designs - completed
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Active Designs", total_designs)
    m2.metric("✅ Completed", completed)
    m3.metric("⏳ Pending", pending)
    
    st.markdown("### 📊 Master Compilation")
    # Clean display of columns
    display_cols = ['design_no', 'designer_code', 'order_type', 'priority', 'status', 'order_date']
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

else:
    # --- INDIVIDUAL DESIGNER VIEW ---
    st.title(f"🛠️ Designer Portal: {view_selection}")
    
    designer_df = df[df['designer_code'] == view_selection]
    
    # Designer Metrics
    d_total = len(designer_df)
    d_comp = len(designer_df[designer_df['status'] == 'COMPLETED'])
    d_pend = d_total - d_comp
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Assigned Designs", d_total)
    c2.metric("Finished", d_comp)
    c3.metric("Remaining", d_pend)
    
    st.markdown("---")
    st.subheader("📋 Current Work List")

    # Status Styling logic
    def highlight_status(val):
        color = '#dcfce7' if val == 'COMPLETED' else '#fef2f2'
        return f'background-color: {color}'

    # Filter columns for cleaner view
    designer_display = designer_df[['design_no', 'order_type', 'priority', 'budget', 'status', 'remark']]
    
    st.dataframe(
        designer_display.style.map(highlight_status, subset=['status']), 
        use_container_width=True, 
        hide_index=True
    )

# 7. FOOTER
st.sidebar.caption(f"Last updated: {pd.Timestamp.now().strftime('%H:%M:%S')}")
