import os
import pandas as pd
import google.auth
from google.cloud import bigquery
import gspread
from google.oauth2 import service_account

# 1. SETUP: Credentials and IDs
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "dcs-system-494410-5488af32c0c7.json"
PROJECT_ID = "dcs-system-494410"  
DATASET_ID = "Designers_system"
T1_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.Master Order Sheet"
T2_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.T2_Design_Inventory"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1fTgGLR4YLRtFsXdmtSd_qk0d3KaZLy5Y9PbpmWsHvok/edit"

# Authorize for BigQuery, Drive, and Sheets
scopes = [
    "https://www.googleapis.com/auth/bigquery",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]
credentials, _ = google.auth.default(scopes=scopes)

# Build Clients
bq_client = bigquery.Client(project=PROJECT_ID, credentials=credentials)
gc = gspread.authorize(credentials)
spreadsheet = gc.open_by_url(SHEET_URL)

# --- MAPPINGS ---
product_codes = { "BANGLE": "BG", "CHOKER": "CK", "NECKLACE": "NK", "BRACELET": "BR", "EARRINGS": "ER", "JHUMKA": "JH", "HARAM": "HR", "BELT": "BT", "PENDENT": "PD", "BAJUBAND": "BJ", "TOPS": "TP", "CHANDBALI": "CB", "RING": "RG", "HARAM CUM BELT": "HRBT", "NEW": "NW", "FULL SET": "FS" }
concept_codes = { "TRADITIONAL + PAN MQ + COMPOSITE + STEPPING": "TRF", "OPEN CLOSE": "OPC", "COMPOSITE": "COM", "FLORAL + HIGHLIGHT": "FRL", "PAN MQ (SINGLE DOUBLE ROUND)": "PANMQ", "TRADITIONAL REGULAR": "TR", "LAYERS": "LAY", "MODERN / CONTEMPORARY": "MOC", "COLOURSTONE": "COL", "TAAR SPREADLOOK": "TSL", "DIFFERENT": "DIF", "FULL SET": "FS" }
designer_mapping = {"BHAVIKA": "D02", "KAUSHIK": "D03", "SUMIT": "D04", "RAJKUMAR": "D05", "GOPAL": "D08", "AYAN": "D09", "HARSH": "D10", "SHRADDHA": "D11", "SUBRATO": "D13", "BISWAJIT": "D14", "PRAGATI": "D15", "SHUBHADEEP": "D16"}

def update_google_sheets(t2_rows):
    print("Updating Google Sheets (Compilation and Designer Tabs)...")
    
    # 1. Update COMPILATION Tab
    try:
        comp_sheet = spreadsheet.worksheet("COMPILATION")
        
        # PROTECTION LOGIC: Read current manual entries before clearing
        current_comp_values = comp_sheet.get_all_values()
        manual_overrides = {}
        
        # Create a map of existing manual entries from Column I and J
        # Row 0 is header, so we start from Row 1
        for row in current_comp_values[1:]:
            if len(row) >= 10:
                d_no = str(row[1]).strip() # Design_no is Column B
                manual_overrides[d_no] = {
                    "admin": str(row[8]).strip(), # Column I
                    "archive": str(row[9]).strip() # Column J
                }

        comp_sheet.batch_clear(["A2:J2500"]) 
        
        comp_data = []
        for r in t2_rows:
            d_no = r['design_no']
            
            # If user has manually typed something, keep it. Otherwise use script default.
            final_admin = manual_overrides.get(d_no, {}).get("admin") or r['admin_status_manual']
            final_archive = manual_overrides.get(d_no, {}).get("archive") or r['archive_manual']

            comp_data.append([
                r['designer_code'], d_no, r['budget'], r['order_date'], 
                r['order_type'], r['priority'], r['remark'], r['status'],
                final_admin, final_archive
            ])
            
        if comp_data:
            comp_sheet.update(range_name="A2", values=comp_data)
            print("✅ COMPILATION tab updated with protection for Column I & J.")
    except Exception as e:
        print(f"❌ Error updating COMPILATION: {e}")

    # 2. Update Designer Tabs (Starts Row 4)
    name_lookup = {v: k for k, v in designer_mapping.items()}
    designer_groups = {}
    for row in t2_rows:
        if row['is_archived']: continue 
        d_name = name_lookup.get(row['designer_code'])
        if d_name:
            if d_name not in designer_groups: designer_groups[d_name] = []
            designer_groups[d_name].append([row['design_no'], row['budget'], row['order_date'], row['order_type'], row['priority'], row['remark'], row['status']])

    for d_name, data in designer_groups.items():
        try:
            ws = spreadsheet.worksheet(d_name)
            ws.batch_clear(["A4:G1000"]) 
            ws.update(range_name="A4", values=data)
            print(f"✅ Tab {d_name} updated.")
        except Exception:
            print(f"⚠️ Tab {d_name} not found. Skipping...")

def run_migration():
    # --- A. FETCH CURRENT OVERRIDES FROM COMPILATION TAB ---
    print("Reading Admin Overrides from COMPILATION tab...")
    try:
        comp_sheet = spreadsheet.worksheet("COMPILATION")
        existing_comp = comp_sheet.get_all_records()
        overrides = {
            str(r.get('design_no')): {
                'admin_status': str(r.get('Admin_Status', 'ACTIVE')).strip().upper(),
                'archive': str(r.get('Archive', 'NO')).strip().upper(),
                'last_status': str(r.get('status', 'PENDING')) 
            } for r in existing_comp if r.get('design_no')
        }
    except:
        print("⚠️ COMPILATION tab empty. Proceeding with defaults.")
        overrides = {}

    # --- B. FETCH MASTER ORDERS FROM T1 ---
    print("Fetching Master Order data from T1...")
    query_t1 = f"SELECT * FROM `{T1_TABLE_ID}`"
    df_orders = bq_client.query(query_t1).to_dataframe()

    t2_rows = []
    sequence_registry = {}

    for index, row in df_orders.iterrows():
        ord_id = str(row.get('ORD_ID', '')).strip()
        if not ord_id or ord_id.lower() == 'nan': continue

        customer = str(row.get('Customer', '')).strip()
        concept_raw = str(row.get('Concept', '')).strip().upper()
        product_raw = str(row.get('Product', '')).strip().upper()
        designer_raw = str(row.get('Designer', '')).strip().upper()
        
        try: qty = int(row.get('Qty', 0))
        except: qty = 0
        if qty <= 0: continue

        d_code = designer_mapping.get(designer_raw, "D00")
        p_code = product_codes.get(product_raw, "XX")
        c_code = concept_codes.get(concept_raw, "XXX")

        combination_key = f"{customer}.{c_code}.{p_code}.{d_code.replace('D', '')}"
        current_seq = sequence_registry.get(combination_key, 0)

        for q in range(1, qty + 1):
            design_no = f"{combination_key}.{str(current_seq + q).zfill(3)}"
            
            # --- APPLY OVERRIDES ---
            row_override = overrides.get(design_no, {'admin_status': 'ACTIVE', 'archive': 'NO', 'last_status': 'PENDING'})
            
            admin_status = row_override['admin_status']
            archive_flag = row_override['archive']
            
            is_archived = False
            if admin_status == 'CANCELLED' or archive_flag == 'YES':
                is_archived = True

            # If Watcher already marked it COMPLETED, don't let migrate.py flip it back
            final_status = row_override['last_status']
            if final_status != 'COMPLETED':
                if admin_status == 'ON HOLD':
                    final_status = 'ON HOLD'
                else:
                    final_status = 'PENDING'

            raw_date = row.get('Date')
            formatted_date = raw_date.strftime('%Y-%m-%d') if pd.notnull(raw_date) else None
            
            t2_rows.append({
                "design_no": design_no, 
                "parent_order_id": ord_id, 
                "designer_code": d_code,
                "budget": str(row.get('Budget', '')), 
                "order_date": formatted_date,
                "order_type": str(row.get('Order Type', 'Stock')), 
                "priority": str(row.get('Priority', 'REGULAR')).strip().upper(),
                "remark": str(row.get('Remark', '')), 
                "status": final_status, 
                "is_archived": is_archived,
                "admin_status_manual": admin_status,
                "archive_manual": archive_flag
            })
        sequence_registry[combination_key] = current_seq + qty

    # --- C. UPDATE BIGQUERY AND GOOGLE SHEETS ---
    print(f"Uploading {len(t2_rows)} design items to BigQuery...")
    df_t2 = pd.DataFrame(t2_rows)
    cols_to_sql = ["design_no", "parent_order_id", "designer_code", "budget", "order_date", "order_type", "priority", "remark", "status", "is_archived"]
    bq_client.load_table_from_dataframe(df_t2[cols_to_sql], T2_TABLE_ID, job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")).result()
    
    update_google_sheets(t2_rows)
    print("✅ Migration Complete!")

if __name__ == "__main__":
    run_migration()
