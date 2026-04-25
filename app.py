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
concept_codes = { "TRADITIONAL + PAN MQ + COMPOSITE + STEPPING": "TRF", "OPEN CLOSE": "OPC", "COMPOSITE": "COM", "FLORAL + HIGHLIGHT": "FRL", "PAN MQ (SINGLE DOUBLE ROUND)": "PANMQ", "TRADITIONAL REGULAR": "TR", "LAYERS": "LAY", "MODERN / CONTEMPORARY": "MOC", "COLOURSTONE": "COL", "TAAR SPREADLOOK": "TSL", "MISCELLANEOUS": "MISC", "FULL SET": "FS" }
designer_mapping = {"BHAVIKA": "D02", "KAUSHIK": "D03", "SUMIT": "D04", "RAJKUMAR": "D05", "GOPAL": "D08", "AYAN": "D09", "HARSH": "D10", "SHRADDHA": "D11", "SUBRATO": "D13", "BISWAJIT": "D14", "PRAGATI": "D15", "SHUBHADEEP": "D16"}

def update_google_sheets(t2_rows):
    print("Updating Google Sheets (Compilation and Designer Tabs)...")
    
    # 1. Update COMPILATION Tab (Starts Row 2)
    try:
        comp_sheet = spreadsheet.worksheet("COMPILATION")
        comp_sheet.batch_clear(["A2:H2000"]) 
        comp_data = [[r['designer_code'], r['design_no'], r['budget'], r['order_date'], r['order_type'], r['priority'], r['remark'], r['status']] for r in t2_rows]
        if comp_data:
            comp_sheet.update(range_name="A2", values=comp_data)
            print("✅ COMPILATION tab updated.")
    except Exception as e:
        print(f"❌ Error updating COMPILATION: {e}")

    # 2. Update Designer Tabs (Starts Row 4)
    name_lookup = {v: k for k, v in designer_mapping.items()}
    designer_groups = {}
    for row in t2_rows:
        d_name = name_lookup.get(row['designer_code'])
        if d_name:
            if d_name not in designer_groups: designer_groups[d_name] = []
            designer_groups[d_name].append([row['design_no'], row['budget'], row['order_date'], row['order_type'], row['priority'], row['remark'], row['status']])

    for d_name, data in designer_groups.items():
        try:
            ws = spreadsheet.worksheet(d_name)
            ws.batch_clear(["A4:G2000"]) 
            ws.update(range_name="A4", values=data)
            print(f"✅ Tab {d_name} updated (Row 4+).")
        except Exception:
            print(f"⚠️ Tab {d_name} not found. Skipping...")

def run_migration():
    print("Fetching Master Order data from T1...")
    query = f"SELECT * FROM `{T1_TABLE_ID}`"
    df_orders = bq_client.query(query).to_dataframe()

    t2_rows = []
    sequence_registry = {}

    print("Processing orders and generating design numbers...")
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
            raw_date = row.get('Date')
            formatted_date = raw_date.strftime('%Y-%m-%d') if pd.notnull(raw_date) else None
            
            raw_priority = str(row.get('Priority', '')).strip().upper()
            priority = raw_priority if raw_priority in ['HIGH', 'REGULAR'] else 'REGULAR'

            t2_rows.append({
                "design_no": design_no, "parent_order_id": ord_id, "designer_code": d_code,
                "budget": str(row.get('Budget', '')), "order_date": formatted_date,
                "order_type": str(row.get('Order Type', 'Stock')), "priority": priority,
                "remark": str(row.get('Remark', '')), "status": "PENDING", "is_archived": False
            })
        sequence_registry[combination_key] = current_seq + qty

    print(f"Generated {len(t2_rows)} design items. Uploading to BigQuery...")
    df_t2 = pd.DataFrame(t2_rows)
    bq_client.load_table_from_dataframe(df_t2, f"{PROJECT_ID}.{DATASET_ID}.T2_Design_Inventory", job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")).result()
    
    # Final step: Write to Google Sheets
    update_google_sheets(t2_rows)
    print("✅ Migration Complete! All systems updated.")

if __name__ == "__main__":
    run_migration()
    input("\nPress Enter to exit...")
