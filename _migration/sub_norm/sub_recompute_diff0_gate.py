# -*- coding: utf-8 -*-
"""S6 게이트: sig 재계산이 원가를 안 흔드는지 실측(sandbox·무커밋 롤백).
같은 커넥션에서 ①원가 baseline(표본) ②재계산 sig UPDATE(미커밋) ③원가 재계산 → diff0 확인 → 롤백.
구조근거=엔진이 sub_registry/sub_code_map 미참조(grep 0). 실측으로 확증. 실행: python sub_recompute_diff0_gate.py"""
import sys, os, io, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'New_ERP'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '_harness'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pyodbc, db_client
from nx_cost_engine import NxCostEngine
from collections import defaultdict

cn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
    f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
cur = cn.cursor()

# 표본: 납품제품 25.01~ 중 SUB 보유 조립품 40개(원가 계산 대상)
cur.execute("""SELECT TOP 15 h.item_code FROM nx.bom_header h
    JOIN nx.bom_line l ON l.bom_id=h.bom_id AND l.child_item NOT LIKE 'RAC%'
    WHERE EXISTS(SELECT 1 FROM nx.sale_dtl s WHERE s.item_code=h.item_code AND s.sale_ymd>=?)
    GROUP BY h.item_code HAVING COUNT(*)>=2 ORDER BY NEWID()""", '250101')
items = [(r[0] or '').strip() for r in cur.fetchall()]
YMD = '260630'
print(f"원가 표본: {len(items)}")

def costs(eng):
    out = {}
    for it in items:
        try: out[it] = round(float(eng.material(it, YMD) or 0), 4)
        except Exception as e: out[it] = f"ERR:{e}"
    return out

eng1 = NxCostEngine(cur=cn.cursor())
base = costs(eng1)

# ── sig 교란(미커밋): 전 sub_registry.sig를 유니크 값으로 바꿈 + sub_code_map 일부 repoint ──
#   목적=sig/코드매핑 변경이 원가에 영향 없음 실측(재계산의 최악=전 sig 변경보다 큼). UNIQUE 안전(sub_code로 유니크).
cur.execute("UPDATE nx.sub_registry SET sig='PERTURB:'+sub_code")
nupd = cur.rowcount
# 대표 repoint 시뮬(8분할 대응): 임의 raw 20개를 새 코드로 재지정
cur.execute("SELECT ISNULL(MAX(CAST(SUBSTRING(sub_code,2,10) AS INT)),0) FROM nx.sub_registry WHERE sub_code LIKE 'S[0-9][0-9][0-9][0-9][0-9]'")
nx0 = int(cur.fetchone()[0])
cur.execute("SELECT TOP 20 raw_item FROM nx.sub_code_map ORDER BY raw_item")
for i, r in enumerate(cur.fetchall()):
    ncode = f"S{nx0+1+i:05d}"
    cur.execute("INSERT INTO nx.sub_registry(sub_code,sig) VALUES(?,?)", ncode, f"PERTURB2:{ncode}")
    cur.execute("UPDATE nx.sub_code_map SET sub_code=? WHERE raw_item=?", ncode, (r[0] or '').strip())
print(f"sig 교란 UPDATE: {nupd} · sub_code_map repoint: 20")

eng2 = NxCostEngine(cur=cn.cursor())
after = costs(eng2)

# diff0
diffs = [(it, base[it], after[it]) for it in items if base[it] != after[it]]
print(f"\n원가 diff!=0: {len(diffs)}건")
for it, b, a in diffs[:10]: print(f"  {it}: {b} → {a}")
cn.rollback(); cn.close()
print("\n=== 결과 ===")
print(f"표본 {len(items)} · diff0 {len(items)-len(diffs)}/{len(items)}")
print("✓GATE PASS: sig 재계산 후 원가 불변" if not diffs else "✗FAIL: 원가 변동")
print("✓전 롤백(nx 무변경)")
