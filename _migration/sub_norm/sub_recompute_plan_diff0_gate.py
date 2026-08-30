# -*- coding: utf-8 -*-
"""S6 게이트(생산계획): sig 재계산이 생산계획 자재소요(plan_explode)를 안 흔드는지 실측.
sandbox 같은 커넥션: ①생산계획 소요 baseline(표본) ②전 sig 유니크 교란+repoint(미커밋) ③재계산 → diff0 → 롤백.
plan_explode=STEP6 plan_part_temp 재현(v_pr_bom·bom_line). sub_registry/sub_code_map 미참조 구조증명의 실측 확증."""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'New_ERP'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '_harness'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pyodbc, db_client
from nx_cost_engine import NxCostEngine
import nx_soyo_engine as SOYO

cn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
    f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
cur = cn.cursor()

cur.execute("""SELECT TOP 12 h.item_code FROM nx.bom_header h
    JOIN nx.bom_line l ON l.bom_id=h.bom_id AND l.child_item NOT LIKE 'RAC%'
    WHERE EXISTS(SELECT 1 FROM nx.sale_dtl s WHERE s.item_code=h.item_code AND s.sale_ymd>=?)
    GROUP BY h.item_code HAVING COUNT(*)>=2 ORDER BY NEWID()""", '250101')
items = [(r[0] or '').strip() for r in cur.fetchall()]
print(f"생산계획 표본: {len(items)}")

def plans(eng):
    out = {}
    for it in items:
        try: out[it] = SOYO.plan_explode(eng, it)
        except Exception as e: out[it] = f"ERR:{e}"
    return out

eng1 = NxCostEngine(cur=cn.cursor())
base = plans(eng1)

# 전 sig 유니크 교란 + sub_code_map 20 repoint(미커밋)
cur.execute("UPDATE nx.sub_registry SET sig='PERTURB:'+sub_code"); nupd = cur.rowcount
cur.execute("SELECT ISNULL(MAX(CAST(SUBSTRING(sub_code,2,10) AS INT)),0) FROM nx.sub_registry WHERE sub_code LIKE 'S[0-9][0-9][0-9][0-9][0-9]'")
nx0 = int(cur.fetchone()[0])
cur.execute("SELECT TOP 20 raw_item FROM nx.sub_code_map ORDER BY raw_item")
for i, r in enumerate(cur.fetchall()):
    ncode = f"S{nx0+1+i:05d}"
    cur.execute("INSERT INTO nx.sub_registry(sub_code,sig,members) VALUES(?,?,1)", ncode, f"PERTURB2:{ncode}")
    cur.execute("UPDATE nx.sub_code_map SET sub_code=? WHERE raw_item=?", ncode, (r[0] or '').strip())
print(f"sig 교란: {nupd} · repoint: 20")

eng2 = NxCostEngine(cur=cn.cursor())
after = plans(eng2)

diffs = []
for it in items:
    if base[it] != after[it]:
        diffs.append(it)
print(f"\n생산계획 소요 diff!=0: {len(diffs)}건")
for it in diffs[:6]:
    b, a = base[it], after[it]
    print(f"  {it}: base {len(b) if isinstance(b,dict) else b} vs after {len(a) if isinstance(a,dict) else a}")
cn.rollback(); cn.close()
print("\n=== 결과 ===")
print(f"표본 {len(items)} · diff0 {len(items)-len(diffs)}/{len(items)}")
print("✓GATE PASS: sig 재계산 후 생산계획 소요 불변" if not diffs else "✗FAIL")
print("✓전 롤백(nx 무변경)")
