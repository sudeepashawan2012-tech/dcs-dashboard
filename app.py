import streamlit as st
import pandas as pd
import os
import json
from google.cloud import bigquery
from google.oauth2 import service_account

# 1. SETUP: Page Config
st.set_page_config(page_title="DCS Dashboard", layout="wide")

# 2. SETUP: Credentials (CLOUD VERSION)
if "gcp_service_account" in st.secrets:
    # We are in the Cloud
    info = st.secrets["gcp_service_account"]
    credentials = service_account.Credentials.from_service_account_info(info)
    client = bigquery.Client(credentials=credentials, project=info["project_id"])
else:
    # We are on your Local Computer
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "dcs-system-494410-5488af32c0c7.json"
    client = bigquery.Client()

PROJECT_ID = "dcs-system-494410"  
DATASET_ID = "Designers_system"
TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.T2_Design_Inventory"
# 3. DATA FETCHING (Cached for speed)
@st.cache_data(ttl=30) 
def load_data():
    # REMOVE the 'client = ...' line from here. 
    # Use the 'client' we already created at the top of the script.
    query = f"SELECT * FROM `{TABLE_ID}` WHERE is_archived = FALSE"
    df = client.query(query).to_dataframe() # This now uses the correct 'client'
    return df

# Load the data
try:
    df = load_data()
except Exception as e:
    st.error(f"Error connecting to Database: {e}")
    st.stop()

# 4. SIDEBAR LOGIC (Designer Selection)
st.sidebar.title("💎 DCS System")
st.sidebar.subheader("Navigation")

# Get unique designers
designers = sorted(df['designer_code'].unique().tolist())
view_selection = st.sidebar.radio("Select View:", ["Total Summary"] + designers)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# 5. MAIN DASHBOARD LOGIC
if view_selection == "Total Summary":
    st.title("Total Factory Summary")
    
    # Calculate global metrics
    total_designs = len(df)
    completed = len(df[df['status'] == 'COMPLETED'])
    pending = total_designs - completed
    
    # Display top metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Active Designs", total_designs)
    col2.metric("Completed", completed)
    col3.metric("Pending", pending)
    
    st.markdown("### Master Compilation")
    # Clean up the dataframe display
    display_df = df[['design_no', 'designer_code', 'order_type', 'priority', 'status', 'order_date']]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

else:
    # Filter data for the specific designer
    st.title(f"Designer Portal: {view_selection}")
    
    designer_df = df[df['designer_code'] == view_selection]
    
    # Calculate designer metrics
    d_total = len(designer_df)
    d_comp = len(designer_df[designer_df['status'] == 'COMPLETED'])
    d_pend = d_total - d_comp
    
    # Display designer metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Assigned", d_total)
    col2.metric("Completed", d_comp)
    col3.metric("Pending", d_pend)
    
    st.markdown("### Active Work Orders")
    
    # Custom styling for status and priority
    def color_status(val):
        color = '#dcfce7' if val == 'COMPLETED' else '#fef2f2'
        return f'background-color: {color}'
    
    styled_df = designer_df[['design_no', 'order_type', 'priority', 'budget', 'status', 'remark']]
    st.dataframe(styled_df.style.map(color_status, subset=['status']), use_container_width=True, hide_index=True)
