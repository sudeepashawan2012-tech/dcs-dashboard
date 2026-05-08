import os
import google.auth
from googleapiclient.discovery import build
from google.cloud import bigquery
import pandas as pd

# 1. SETUP
PROJECT_ID = "dcs-system-494410"  
DATASET_ID = "Designers_system"
TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.T2_Design_Inventory"
FOLDER_ID = '10c4vzwiXvYIxTcNS8lND2uMZvOnMtocr'

# Use secret key on GitHub, or local file if running at home
if os.path.exists("dcs-system-494410-5488af32c0c7.json"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "dcs-system-494410-5488af32c0c7.json"

scopes = ["https://www.googleapis.com/auth/bigquery", "https://www.googleapis.com/auth/drive.readonly"]
credentials, _ = google.auth.default(scopes=scopes)

bq_client = bigquery.Client(project=PROJECT_ID, credentials=credentials)
drive_service = build('drive', 'v3', credentials=credentials)

def run_watcher():
    print("Scanning BigQuery for Pending designs...")
    query = f"SELECT design_no FROM `{TABLE_ID}` WHERE status = 'PENDING'"
    pending_df = bq_client.query(query).to_dataframe()
    
    if pending_df.empty:
        print("No pending designs found. Factory is up to date!")
        return

    pending_list = pending_df['design_no'].tolist()

    # Get filenames from Drive
    results = drive_service.files().list(
        q=f"'{FOLDER_ID}' in parents and trashed=false",
        fields="files(name)",
        pageSize=1000
    ).execute()
    # ... inside the run_watcher function ...
    drive_files = [f['name'].upper() for f in results.get('files', [])]

    completed_list = []
    for d_no in pending_list:
        clean_d_no = d_no.strip().upper()
        # This checks if the design number is in the filename, ignoring .jpg, .png, etc.
        if any(clean_d_no in fname for fname in drive_files):
            completed_list.append(d_no)

    if completed_list:
        print(f"Found {len(completed_list)} new completions. Updating SQL...")
        format_ids = ",".join([f"'{i}'" for i in completed_list])
        update_query = f"UPDATE `{TABLE_ID}` SET status = 'COMPLETED' WHERE design_no IN ({format_ids})"
        bq_client.query(update_query).result()
        print("✅ Statuses updated successfully.")
    else:
        print("No new matches found in Drive.")

if __name__ == "__main__":
    run_watcher()
