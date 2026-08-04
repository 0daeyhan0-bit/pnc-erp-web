# -*- coding: utf-8 -*-
"""①그룹(LG有·양산중·CS원천없음) 관경별 용접횟수 역산 — 읽기전용(역산·검증만, nx 쓰기 금지). 정본 불변.
두 제약 동시만족:
  소요량: Σ(std_use[관경]×횟수) × 1.5 == use_qty(정본)
  횟수합: Σ횟수 == routing 용접ST(51/28 work_qty = 총 용접포인트 count)  ★routingST=count(std_st아님)
후보 관경 = BOM 자식(Tube 등)의 실제 외경 + weld_diam 14관경. 조합탐색(정수 횟수).
재현OK = 소요량·횟수합 둘 다 round4 일치. 아니면 애매(사유표기)."""
import sys, io, re, csv
from itertools import product
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
from collections import defaultdict
def L(): return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
def N(): return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
lv = L().cursor(); nx = N().cursor()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
CUT = '240801'
def basew(x): return re.sub(r'(-\d+)+$', '', x)
def basep(x): return re.sub(r'(-(?:SUB\d*|S\d+|은납\d*|J\d+|\d+))+$', '', x)

# 표준 마스터(관경별 std_use/std_st, 대표=MIN=일반코드)
nx.execute("SELECT pipe_diam,MIN(std_use_qty),MIN(std_st) FROM nx.weld_diam GROUP BY pipe_diam")
DIAMS = []; STDU = {}; STDS = {}
for r in nx.fetchall():
    d = round(float(r[0]), 2); DIAMS.append(d); STDU[d] = float(r[1]); STDS[d] = float(r[2])
DIAMS.sort()
nx.execute("SELECT item_code, ISNULL(item_name,'') FROM nx.item"); NAME = {str(r[0]).strip(): str(r[1]).strip() for r in nx.fetchall()}
# LG 용접봉 집합(①판정)
nx.execute("SELECT parent_code,child_code FROM nx.lg_bom WHERE child_code LIKE 'RAC%'")
LGset = set()
for r in nx.fetchall():
    p = str(r[0]).strip(); w = str(r[1]).strip(); LGset.add((p, basew(w))); LGset.add((basep(p), basew(w)))
# routing 용접ST(51/28)
nx.execute("SELECT p_item,item_code,SUM(work_qty) FROM nx.routing WHERE item_code LIKE 'RAC%' AND proc_code IN ('51','28') AND work_qty>0 GROUP BY p_item,item_code")
RST = {(str(r[0]).strip(), str(r[1]).strip()): float(r[2]) for r in nx.fetchall()}
lv.execute("SELECT DISTINCT P_ITEM_CODE FROM CS_T_ITEM_WELD"); HASWELD = set(str(r[0]).strip() for r in lv.fetchall())
lv.execute("SELECT DISTINCT ITEM_CODE FROM PR_T_PROD_DTL WHERE PROD_YMD>=? AND ISNULL(PROD_QTY,0)<>0", CUT); PROD24 = set(str(r[0]).strip() for r in lv.fetchall())

# BOM 자식의 실제 외경 후보(자식 diam)
def child_diams(p):
    nx.execute("SELECT bom_id FROM nx.bom_header WHERE item_code=?", p); r = nx.fetchone()
    ds = set()
    if r:
        nx.execute("SELECT child_item FROM nx.bom_line WHERE bom_id=?", r[0])
        for x in nx.fetchall():
            c = str(x[0]).strip()
            nx.execute("SELECT ISNULL(diam,0) FROM nx.item WHERE item_code=?", c); rr = nx.fetchone()
            if rr and rr[0]:
                d = round(float(rr[0]), 2)
                # weld_diam 관경으로 스냅(가장 가까운)
                near = min(DIAMS, key=lambda z: abs(z - d))
                if abs(near - d) < 0.6: ds.add(near)
    return ds

def m4(a, b): return abs(a - b) < 6e-5 or round(a, 4) == round(b, 4)

def derive(p, w, use, rst):
    # 후보 관경 = 자식외경 우선, 없으면 전체 14관경
    cand = sorted(child_diams(p)) or DIAMS[:]
    n_use_target = round(use / 1.5, 6)      # = Σ(std_use×횟수)
    rst_i = int(round(rst)) if rst > 0 else 0  # routing 용접ST = 총 용접포인트 count
    sols = []
    # 단일 관경: 횟수 k → k*stdu*1.5==use AND (rst없으면 통과) k==rst
    for d in cand:
        if STDU[d] <= 0: continue
        k = n_use_target / STDU[d]
        if abs(k - round(k)) < 0.01 and round(k) > 0:
            k = round(k)
            if m4(k * STDU[d] * 1.5, use) and (rst_i == 0 or k == rst_i):
                if {d: k} not in sols: sols.append({d: k})
    # 2관경 조합: Σk==rst(있으면) AND Σ(std_use×k)×1.5==use
    if not sols and len(cand) >= 2:
        max_pts = rst_i if rst_i > 0 else 40
        for i in range(len(cand)):
            for j in range(i + 1, len(cand)):
                d1, d2 = cand[i], cand[j]
                if STDU[d2] <= 0: continue
                for k1 in range(0, max_pts + 1):
                    rem_use = n_use_target - k1 * STDU[d1]
                    if rem_use < -1e-9: break
                    k2 = rem_use / STDU[d2]
                    if abs(k2 - round(k2)) < 0.01 and round(k2) >= 0 and (k1 + round(k2)) > 0:
                        k2 = round(k2)
                        cnt_ok = (rst_i == 0) or (k1 + k2 == rst_i)
                        if cnt_ok and m4((k1 * STDU[d1] + k2 * STDU[d2]) * 1.5, use):
                            s = {}
                            if k1: s[d1] = k1
                            if k2: s[d2] = k2
                            if s and s not in sols: sols.append(s)
    return sols, cand

# ①그룹 대상
nx.execute("SELECT parent_item,weld_item,ISNULL(use_qty,0) FROM nx.proc_weld WHERE ISNULL(meta_ok,0)=0 AND use_qty>0")
targets = []
for r in nx.fetchall():
    p = str(r[0]).strip(); w = str(r[1]).strip(); use = float(r[2])
    if p in HASWELD or p not in PROD24: continue
    if (p, basew(w)) in LGset or (basep(p), basew(w)) in LGset:
        targets.append((p, w, use))

rows = []
for p, w, use in targets:
    rst = RST.get((p, w), 0.0)
    sols, cand = derive(p, w, use, rst)
    if len(sols) == 1:
        s = sols[0]
        rec_use = round(sum(STDU[d] * k for d, k in s.items()) * 1.5, 6)
        rec_st = sum(k for d, k in s.items())   # Σ횟수(=총 용접포인트 count) — routingST와 대조
        match = "OK"; derived = " + ".join(f"{d}φ×{k}" for d, k in sorted(s.items()))
        note = "단일해(소요량+횟수 일치)" if rst > 0 else "단일해(routingST없음, 소요량기준)"
    elif len(sols) > 1:
        match = "애매"; derived = " | ".join("+".join(f"{d}φ×{k}" for d, k in sorted(x.items())) for x in sols[:3])
        rec_use = ""; rec_st = ""; note = f"다관경 조합 {len(sols)}개(복수해)"
    else:
        match = "애매"; derived = ""; rec_use = ""; rec_st = ""
        note = f"재현실패(후보관경 {sorted(cand)}, ST={rst})"
    rows.append({"item": p, "item_name": NAME.get(p, ''), "weld_item": w, "use_qty": round(use, 6),
                 "routing_weldST": rst, "derived": derived, "recon_use": rec_use, "recon_st": rec_st,
                 "match": match, "note": note})

for path in [r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\_schema\group1_derive_40.csv",
             r"C:\Users\admin\AppData\Local\Temp\claude\d-----------100-AI-AGENT\02b63e35-1303-4eb0-8eb4-29df63d29c62\scratchpad\group1_derive_40.csv"]:
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["item","item_name","weld_item","use_qty","routing_weldST","derived","recon_use","recon_st","match","note"])
        wr.writeheader()
        for r in sorted(rows, key=lambda x: (x["match"], x["item"])): wr.writerow(r)

ok = [r for r in rows if r["match"] == "OK"]; amb = [r for r in rows if r["match"] == "애매"]
print(f"①그룹 {len(rows)}행 역산:")
print(f"  재현OK(일괄확인 대상): {len(ok)}")
print(f"  애매(하나씩 확인): {len(amb)}")
print(f"\n=== 재현OK 대표 (품번·품명·역산관경×횟수·use_qty·ST) ===")
for r in ok[:10]:
    print(f"  {r['item']} | {r['item_name'][:22]} | {r['weld_item']} | {r['derived']} | use={r['use_qty']}(재현{r['recon_use']}) ST={r['routing_weldST']}(재현{r['recon_st']})")
print(f"\n=== 애매 대표 ===")
for r in amb[:6]:
    print(f"  {r['item']} | {r['item_name'][:20]} | use={r['use_qty']} ST={r['routing_weldST']} | {r['note']}")
print("\nCSV: _schema/group1_derive_40.csv (+scratchpad)")
