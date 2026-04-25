import os
import google.auth
from googleapiclient.discovery import build
from google.cloud import bigquery

# 1. SETUP: Your exact JSON key filename
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "dcs-system-494410-5488af32c0c7.json"

# 2. SETUP: Project and Database details
PROJECT_ID = "dcs-system-494410"  
DATASET_ID = "Designers_system"
TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.T2_Design_Inventory"

# 3. SETUP: Your Google Drive Folder ID
FOLDER_ID = '10c4vzwiXvYIxTcNS8lND2uMZvOnMtocr'

# Authorize with BigQuery AND Drive
scopes = [
    "https://www.googleapis.com/auth/bigquery", 
    "https://www.googleapis.com/auth/drive.readonly"
]
credentials, _ = google.auth.default(scopes=scopes)

# Build the clients
bq_client = bigquery.Client(project=PROJECT_ID, credentials=credentials)
drive_service = build('drive', 'v3', credentials=credentials)

def run_watcher():
    print("Fetching 'PENDING' designs from BigQuery Vault...")
    
    # Step A: Ask SQL for all pending designs
    query = f"SELECT design_no FROM `{TABLE_ID}` WHERE status = 'PENDING'"
    pending_df = bq_client.query(query).to_dataframe()
    pending_designs = pending_df['design_no'].tolist()

    if not pending_designs:
        print("No pending designs found in the database. Everything is complete!")
        return

    print(f"Found {len(pending_designs)} pending designs. Scanning Google Drive...")

    # Step B: Get all filenames from the Drive Folder
    file_list = []
    page_token = None
    while True:
        results = drive_service.files().list(
            q=f"'{FOLDER_ID}' in parents and trashed=false",
            pageSize=1000,
            fields="nextPageToken, files(id, name)",
            pageToken=page_token
        ).execute()
        
        items = results.get('files', [])
        file_list.extend([item['name'] for item in items])
        
        page_token = results.get('nextPageToken')
        if not page_token:
            break

    print(f"Found {len(file_list)} files in the Drive folder.")

    # Step C: Compare filenames to pending designs
    completed_designs = []
    for d_no in pending_designs:
        # If the exact design number is inside any of the filenames
        if any(d_no in fname for fname in file_list):
            completed_designs.append(d_no)

    # Step D: Update SQL if we found matches
    if completed_designs:
        print(f"Found {len(completed_designs)} new completed designs! Updating SQL Database...")
        
        # Format the list for a SQL query (e.g., 'C61.COM.NK.02.001', 'C61.COM.NK.02.002')
        format_strings = ','.join([f"'{d}'" for d in completed_designs])
        
        update_query = f"""
            UPDATE `{TABLE_ID}`
            SET status = 'COMPLETED'
            WHERE design_no IN ({format_strings})
        """
        bq_client.query(update_query).result() # Execute the update
        
        print("✅ Database successfully updated. Dashboard is now live.")
    else:
        print("No new completed designs found this time. Scanning finished.")

if __name__ == '__main__':
    run_watcher()
    input("\nPress Enter to exit...")