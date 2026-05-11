import os
import pandas as pd
import google.auth
from google.cloud import bigquery
import gspread
from google.oauth2 import service_account

# 1. SETUP
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "dcs-system-494410-5488af32c0c7.json"
PROJECT_ID = "dcs-system-494410"  
DATASET_ID = "Designers_system"
T1_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.Master Order Sheet"
T2_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.T2_Design_Inventory"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1fTgGLR4YLRtFsXdmtSd_qk0d3KaZLy5Y9PbpmWsHvok/edit"

scopes = ["https://www.googleapis.com/auth/bigquery", "https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
credentials, _ = google.auth.default(scopes=scopes)
bq_client = bigquery.Client(project=PROJECT_ID, credentials=credentials)
gc = gspread.authorize(credentials)
spreadsheet = gc.open_by_url(SHEET_URL)

# MAPPINGS
product_codes = { "BANGLE": "BG", "CHOKER": "CK", "NECKLACE": "NK", "BRACELET": "BR", "EARRINGS": "ER", "JHUMKA": "JH", "HARAM": "HR", "BELT": "BT", "PENDENT": "PD", "BAJUBAND": "BJ", "TOPS": "TP", "CHANDBALI": "CB", "RING": "RG", "HARAM CUM BELT": "HRBT", "NEW": "NW", "FULL SET": "FS" }
concept_codes = { "TRADITIONAL + PAN MQ + COMPOSITE + STEPPING": "TRF", "OPEN CLOSE": "OPC", "COMPOSITE": "COM", "STRUCTURE": "STR", "PAN MQ (SINGLE DOUBLE ROUND)": "PANMQ", "TRADITIONAL REGULAR": "TR", "LAYERS": "LAY", "MODERN / CONTEMPORARY": "MOC", "COLOURSTONE": "COL", "TAAR SPREADLOOK": "TSL", "DIFFERENT": "DIF", "FULL SET": "FS" }
designer_mapping = {"BHAVIKA": "D02", "KAUSHIK": "D03", "SUMIT": "D04", "RAJKUMAR": "D05", "GOPAL": "D08", "AYAN": "D09", "HARSH": "D10", "SHRADDHA": "D11", "SUBRATO": "D13", "BISWAJIT": "D14", "PRAGATI": "D15", "SHUBHADEEP": "D16"}

def update_google_sheets(t2_rows):
    print("Updating Google Sheets (Compilation and Designer Tabs)...")
    
    # 1. Update COMPILATION Tab (Full sync from SQL + Admin Overrides)
    try:
        comp_sheet = spreadsheet.worksheet("COMPILATION")
        current_comp_values = comp_sheet.get_all_values()
        
        # Read Column I and J to protect manual notes
        manual_overrides = {}
        for row in current_comp_values[1:]:
            if len(row) >= 10:
                d_no = str(row[1]).strip()
                manual_overrides[d_no] = {
                    "admin": str(row[8]).strip().upper(),
                    "archive": str(row[9]).strip().upper()
                }

        comp_sheet.batch_clear(["A2:J2500"]) 
        
        comp_data = []
        for r in t2_rows:
            d_no = r['design_no']
            
            # Use Manual entries if they exist, otherwise script defaults
            final_admin = manual_overrides.get(d_no, {}).get("admin") or r['admin_status_manual']
            final_archive = manual_overrides.get(d_no, {}).get("archive") or r['archive_manual']

            # Determine final display status
            display_status = r['status']
            if final_admin == 'ON HOLD': display_status = 'ON HOLD'
            elif final_admin == 'CANCELLED': display_status = 'CANCELLED'

            comp_data.append([
                r['designer_code'], d_no, r['budget'], r['order_date'], 
                r['order_type'], r['priority'], r['remark'], display_status,
                final_admin, final_archive
            ])
            
        if comp_data:
            comp_sheet.update(range_name="A2", values=comp_data)
            print("✅ COMPILATION tab updated.")

        # 2. Update Designer Tabs (Mirroring the COMPILATION status)
        name_lookup = {v: k for k, v in designer_mapping.items()}
        designer_groups = {}
        
        # Group the designs using the processed comp_data
        for r in comp_data:
            d_code = r[0]
            d_name = name_lookup.get(d_code)
            
            if d_name:
                if d_name not in designer_groups: 
                    designer_groups[d_name] = []
                
                # Push columns: Design No, Budget, Date, Type, Priority, Remark, STATUS
                designer_groups[d_name].append([r[1], r[2], r[3], r[4], r[5], r[6], r[7]])

        # Write data to each designer's tab
        for d_name, data in designer_groups.items():
            try:
                ws = spreadsheet.worksheet(d_name)
                ws.batch_clear(["A4:G1000"]) 
                ws.update(range_name="A4", values=data)
                print(f"✅ Tab {d_name} updated with latest status.")
            except Exception as e:
                print(f"⚠️ Could not update tab {d_name}: {e}")

    except Exception as e:
        print(f"❌ Error in update_google_sheets: {e}")

def run_migration():
    # 1. READ CURRENT SQL STATUS (To avoid PENDING overwrite)
    print("Fetching current status from BigQuery...")
    query_current = f"SELECT design_no, status FROM `{T2_TABLE_ID}`"
    sql_status_map = {row.design_no: row.status for row in bq_client.query(query_current)}

    # 2. READ MASTER ORDERS
    print("Fetching Master Order data from T1...")
    df_orders = bq_client.query(f"SELECT * FROM `{T1_TABLE_ID}`").to_dataframe()
    t2_rows = []
    sequence_registry = {}

    for index, row in df_orders.iterrows():
        ord_id = str(row.get('ORD_ID', '')).strip()
        if not ord_id or ord_id.lower() == 'nan': continue

        customer, concept_raw, product_raw, designer_raw = [str(row.get(c, '')).strip().upper() for c in ['Customer', 'Concept', 'Product', 'Designer']]
        try: qty = int(row.get('Qty', 0))
        except: qty = 0
        if qty <= 0: continue

        d_code, p_code, c_code = designer_mapping.get(designer_raw, "D00"), product_codes.get(product_raw, "XX"), concept_codes.get(concept_raw, "XXX")
        combination_key = f"{customer}.{c_code}.{p_code}.{d_code.replace('D', '')}"
        current_seq = sequence_registry.get(combination_key, 0)

        for q in range(1, qty + 1):
            design_no = f"{combination_key}.{str(current_seq + q).zfill(3)}"
            
            # PRESERVE STATUS: If SQL already says COMPLETED, keep it COMPLETED
            current_status = sql_status_map.get(design_no, "PENDING")
            
            t2_rows.append({
                "design_no": design_no, "parent_order_id": ord_id, "designer_code": d_code,
                "budget": str(row.get('Budget', '')), "order_date": row.get('Date').strftime('%Y-%m-%d') if pd.notnull(row.get('Date')) else None,
                "order_type": str(row.get('Order Type', 'Stock')), "priority": str(row.get('Priority', 'REGULAR')).upper(),
                "remark": str(row.get('Remark', '')), "status": current_status, "is_archived": False,
                "admin_status_manual": "ACTIVE", "archive_manual": "NO"
            })
        sequence_registry[combination_key] = current_seq + qty

    # 3. UPLOAD AND SYNC
    if t2_rows:
        print(f"Uploading {len(t2_rows)} design items to BigQuery...")
        df_t2 = pd.DataFrame(t2_rows)
        cols = ["design_no", "parent_order_id", "designer_code", "budget", "order_date", "order_type", "priority", "remark", "status", "is_archived"]
        bq_client.load_table_from_dataframe(df_t2[cols], T2_TABLE_ID, job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")).result()
        update_google_sheets(t2_rows)
        print("✅ Migration Complete!")

if __name__ == "__main__":
    run_migration()
