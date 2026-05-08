import os
import json
import google.auth
from googleapiclient.discovery import build
from google.cloud import bigquery
import pandas as pd

# 1. SETUP: Identifiers
PROJECT_ID = "dcs-system-494410"  
DATASET_ID = "Designers_system"
TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.T2_Design_Inventory"
FOLDER_ID = '10c4vzwiXvYIxTcNS8lND2uMZvOnMtocr'

# --- THE GITHUB BRIDGE ---
if os.path.exists("dcs-system-494410-5488af32c0c7.json"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "dcs-system-494410-5488af32c0c7.json"
elif "GCP_SA_KEY" in os.environ:
    with open("dcs-system-494410-5488af32c0c7.json", "w") as f:
        f.write(os.environ["GCP_SA_KEY"])
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "dcs-system-494410-5488af32c0c7.json"

# 2. AUTHORIZATION
scopes = ["https://www.googleapis.com/auth/bigquery", "https://www.googleapis.com/auth/drive.readonly"]
credentials, _ = google.auth.default(scopes=scopes)

bq_client = bigquery.Client(project=PROJECT_ID, credentials=credentials)
drive_service = build('drive', 'v3', credentials=credentials)

def run_watcher():
    print("--- Starting Folder Watcher ---")
    print("Step 1: Fetching 'PENDING' designs from BigQuery...")
    query = f"SELECT design_no FROM `{TABLE_ID}` WHERE status = 'PENDING'"
    pending_df = bq_client.query(query).to_dataframe()
    
    if pending_df.empty:
        print("✅ No pending designs found. Factory is up to date!")
        return

    pending_list = pending_df['design_no'].tolist()
    print(f"Checking for {len(pending_list)} pending designs...")

    # Step 2: Fetch all filenames from Google Drive
    results = drive_service.files().list(
        q=f"'{FOLDER_ID}' in parents and trashed=false",
        fields="files(name)",
        pageSize=1000
    ).execute()
    
    drive_files_raw = results.get('files', [])
    print(f"Scanned Drive: Found {len(drive_files_raw)} total images.")

    # Step 3: HYPER-AGGRESSIVE CLEANING
    drive_filenames_clean = [os.path.splitext(f['name'])[0].upper().replace(" ", "") for f in drive_files_raw]

    # --- FIX APPLIED HERE: Variable name is now 'completed_list' everywhere ---
    completed_list = []
    for d_no in pending_list:
        clean_d_no = str(d_no).upper().replace(" ", "")
        
        if any(clean_d_no in fname for fname in drive_filenames_clean):
            print(f"✅ Match Found for: {d_no}")
            completed_list.append(d_no)

    # Step 4: UPDATE BIGQUERY
    if completed_list:
        print(f"Updating {len(completed_list)} items to COMPLETED in SQL...")
        format_ids = ",".join([f"'{i}'" for i in completed_list])
        update_query = f"UPDATE `{TABLE_ID}` SET status = 'COMPLETED' WHERE design_no IN ({format_ids})"
        bq_client.query(update_query).result()
        print("🚀 SQL Database updated successfully.")
    else:
        print("⚠️ Watcher finished: 0 new matches found.")

if __name__ == "__main__":
    run_watcher()
