import os
import glob
import re

base_dir = r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석\src_extracted"

module_stats = {}
all_tables = set()
dw_sql_patterns = []

for mod_dir in sorted(glob.glob(os.path.join(base_dir, "*"))):
    if not os.path.isdir(mod_dir):
        continue
    mod_name = os.path.basename(mod_dir)
    files = glob.glob(os.path.join(mod_dir, "*"))
    
    srw_count = len([f for f in files if f.endswith('.srw')])
    srd_count = len([f for f in files if f.endswith('.srd')])
    sru_count = len([f for f in files if f.endswith('.sru')])
    srf_count = len([f for f in files if f.endswith('.srf')])
    other_count = len(files) - (srw_count + srd_count + sru_count + srf_count)
    
    module_stats[mod_name] = {
        'total': len(files),
        'srw': srw_count,
        'srd': srd_count,
        'sru': sru_count,
        'srf': srf_count,
        'other': other_count
    }
    
    # Scan DataWindow files for SQL tables
    for fpath in files:
        if fpath.endswith('.srd'):
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    # Find table names (e.g., FROM table_name, JOIN table_name)
                    tables = re.findall(r'(?:from|join|update|into)\s+([a-zA-Z0-9_]+)', content, re.IGNORECASE)
                    for t in tables:
                        if len(t) > 3 and not t.upper() in ('SELECT', 'WHERE', 'AND', 'OR', 'ON', 'AS', 'SET', 'VALUES'):
                            all_tables.add(t.upper())
            except Exception:
                pass

print("=== Module Statistics Summary ===")
total_all_files = 0
for mod, stat in module_stats.items():
    total_all_files += stat['total']
    print("{:<28}: Total {:<4} (Window:{:<3}, DataWindow:{:<3}, UserObject:{:<3}, Function:{:<2})".format(
        mod, stat['total'], stat['srw'], stat['srd'], stat['sru'], stat['srf']
    ))

print("\nTotal Extracted Source Files Across All Modules: {}".format(total_all_files))
print("Total Unique Database Tables Identified in DataWindows: {}".format(len(all_tables)))
print("Sample Identified DB Tables:", sorted(list(all_tables))[:30])
