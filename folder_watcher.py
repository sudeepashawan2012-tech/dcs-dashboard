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
    
    raw_files = results.get('files', [])
    print(f"Scanned {len(raw_files)} files from Drive.")

    completed_list = []
    
    # We loop through every pending design
    for d_no in pending_list:
        # Clean the design number for a "smart match" (Upper case, no spaces)
        clean_d_no = str(d_no).upper().replace(" ", "").strip()
        
        # Check every file in the drive
        for f in raw_files:
            # Clean the filename for comparison (Remove extension, Upper case, no spaces)
            clean_filename = os.path.splitext(f['name'])[0].upper().replace(" ", "").strip()
            
            # EXACT MATCH LOGIC (Like AppScript)
            if clean_d_no == clean_filename:
                print(f"✅ Found Match: {d_no}")
                completed_list.append(d_no)
                break # Stop looking for this design once found
            
            # PARTIAL MATCH LOGIC (Just in case there is extra text in filename)
            elif clean_d_no in clean_filename:
                print(f"✅ Found Partial Match: {d_no} in {f['name']}")
                completed_list.append(d_no)
                break

    # 3. UPDATE BIGQUERY
    if completed_list:
        # Remove duplicates just in case
        completed_list = list(set(completed_list))
        
        print(f"Updating {len(completed_list)} designs in SQL...")
        format_ids = ",".join([f"'{i}'" for i in completed_list])
        update_query = f"UPDATE `{TABLE_ID}` SET status = 'COMPLETED' WHERE design_no IN ({format_ids})"
        bq_client.query(update_query).result()
        print("🚀 SQL Updated successfully.")
    else:
        print("⚠️ No new matches found today.")

if __name__ == "__main__":
    run_watcher()
