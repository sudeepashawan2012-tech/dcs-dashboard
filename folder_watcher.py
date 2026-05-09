import os
import json
import google.auth
from googleapiclient.discovery import build
from google.cloud import bigquery
import pandas as pd

# 1. SETUP
PROJECT_ID = "dcs-system-494410"  
DATASET_ID = "Designers_system"
TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.T2_Design_Inventory"
FOLDER_ID = '10c4vzwiXvYIxTcNS8lND2uMZvOnMtocr'

# --- GITHUB BRIDGE ---
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
    print("--- Starting Folder Watcher (AppScript Mirror Mode) ---")
    
    # Fetch Pending from SQL
    query = f"SELECT design_no FROM `{TABLE_ID}` WHERE status = 'PENDING'"
    pending_df = bq_client.query(query).to_dataframe()
    if pending_df.empty:
        print("✅ No pending designs found.")
        return
    pending_list = pending_df['design_no'].tolist()

    # Fetch all filenames from Drive
    results = drive_service.files().list(
        q=f"'{FOLDER_ID}' in parents and trashed=false",
        fields="files(name)",
        pageSize=1000
    ).execute()
    
    # 1. Clean Drive filenames: Remove .jpg, make UPPER, strip all SPACES
    drive_files_clean = [os.path.splitext(f['name'])[0].upper().replace(" ", "").strip() for f in results.get('files', [])]

    completed_list = []
    for d_no in pending_list:
        # 2. Clean SQL Design Number: make UPPER, strip all SPACES
        clean_d_no = str(d_no).upper().replace(" ", "").strip()
        
        # 3. Match: Just like AppScript "includes"
        if any(clean_d_no in fname for fname in drive_files_clean):
            completed_list.append(d_no)
        
        # EXACT MIRROR OF APPSCRIPT: if (fileList[j].includes(designNo))
        match_found = False
        for filename in file_list:
            if design_str in filename:
                match_found = True
                break
        
        if match_found:
            print(f"✅ Found: {design_str}")
            completed_list.append(design_str)

    # 3. UPDATE BIGQUERY
    if completed_list:
        print(f"Updating {len(completed_list)} designs in SQL...")
        # We update in chunks to avoid SQL errors
        format_ids = ",".join([f"'{i}'" for i in completed_list])
        update_query = f"UPDATE `{TABLE_ID}` SET status = 'COMPLETED' WHERE design_no IN ({format_ids})"
        bq_client.query(update_query).result()
        print("🚀 SQL Updated successfully.")
    else:
        print("⚠️ No new matches found today.")

if __name__ == "__main__":
    run_watcher()
