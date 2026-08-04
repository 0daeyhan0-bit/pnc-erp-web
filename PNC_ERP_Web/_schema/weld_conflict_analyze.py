# -*- coding: utf-8 -*-
"""견적(CS_T_ITEM_WELD) vs 실원가(PR_M_ITEM_BOM) 용접봉 소요량 불일치 371건 표본+패턴 — 읽기전용, nx 쓰기 금지.
CS 소요량 = Σ(std_use[관경]×횟수)×1.5 (견적 화면 weld grid 원천).
BOM 소요량 = PR_M_ITEM_BOM RAC use_qty (실원가 SP=현 게이트 오라클, 우리 proc_weld와 동일).
차이배수·방향·관경/rod/시기 분포·수정시점(CS vs BOM)·활성도(최근24M 생산) 분석."""
import sys, io, csv
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
from collections import defaultdict, Counter
lv = pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True).cursor()
nx = pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True).cursor()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
nx.execute("SELECT item_code, ISNULL(item_name,'') FROM nx.item"); NAME = {str(r[0]).strip(): str(r[1]).strip() for r in nx.fetchall()}
nx.execute("SELECT pipe_diam,MIN(std_use_qty) FROM nx.weld_diam GROUP BY pipe_diam"); STDU = {round(float(r[0]),2): float(r[1]) for r in nx.fetchall()}

# CS 상세: (node) -> [(diam,qty,use)], 최종수정일
lv.execute("SELECT P_ITEM_CODE,ITEM_CODE,PIPE_DIAM,ISNULL(WELD_QTY,0),ISNULL(ITEM_USE_QTY,0),UPDATE_DATETIME FROM CS_T_ITEM_WELD WHERE ISNULL(WELD_QTY,0)>0")
CSdet = defaultdict(list); CSsum = defaultdict(float); CSupd = {}; CSweld = {}
for r in lv.fetchall():
    p = str(r[0]).strip(); CSdet[p].append((round(float(r[2]),2), int(r[3]), float(r[4]))); CSsum[p] += float(r[4])
    CSweld[p] = str(r[1]).strip()
    if r[5] and (p not in CSupd or r[5] > CSupd[p]): CSupd[p] = r[5]
CS = {k: round(v*1.5, 4) for k, v in CSsum.items()}
# BOM: node -> RAC use_qty, 갱신일
lv.execute("SELECT ITEM_CODE,SUM(USE_QTY),MAX(UPDATE_DATETIME) FROM PR_M_ITEM_BOM WHERE MAT_CODE LIKE 'RAC%' GROUP BY ITEM_CODE")
BOM = {}; BOMupd = {}
for r in lv.fetchall():
    BOM[str(r[0]).strip()] = round(float(r[1] or 0), 4); BOMupd[str(r[0]).strip()] = r[2]
# 활성(최근24M 생산)
lv.execute("SELECT DISTINCT ITEM_CODE FROM PR_T_PROD_DTL WHERE PROD_YMD>='240801' AND ISNULL(PROD_QTY,0)<>0"); PROD24 = set(str(r[0]).strip() for r in lv.fetchall())
lv.execute("SELECT ITEM_CODE,MAX(PROD_YMD) FROM PR_T_PROD_DTL GROUP BY ITEM_CODE"); LAST = {str(r[0]).strip(): str(r[1]).strip() for r in lv.fetchall()}
def ymd(y): return f"20{y[:2]}-{y[2:4]}-{y[4:6]}" if len(y)==6 else '없음'
# 최상위 부모(간이): BOM에서 이 노드를 자식으로 갖는 최상위 추적은 비용↑ → 직상위만
def top_parent(n):
    lv.execute("SELECT TOP 1 ITEM_CODE FROM PR_M_ITEM_BOM WHERE MAT_CODE=?", n); r = lv.fetchone()
    return str(r[0]).strip() if r else ''

both = set(CS) & set(BOM)
conflict = [k for k in both if abs(CS[k]-BOM[k]) >= 6e-4]
rows = []
for k in conflict:
    cs = CS[k]; bm = BOM[k]
    ratio = round(cs/bm, 3) if bm > 0 else None
    detail = "·".join(f"{d}φ×{q}" for d, q, u in sorted(CSdet[k]))
    csu = CSupd.get(k); bmu = BOMupd.get(k)
    newer = "CS최신" if (csu and bmu and csu > bmu) else ("BOM최신" if (csu and bmu and bmu > csu) else "동일/불명")
    rows.append({"node": k, "name": NAME.get(k, ''), "cs_soyo": cs, "bom_soyo": bm,
                 "ratio": ratio if ratio is not None else '', "direction": "CS>BOM" if cs > bm else "CS<BOM",
                 "weld_item": CSweld.get(k, ''), "last_prod": ymd(LAST.get(k, '')), "active": int(k in PROD24),
                 "top_parent": top_parent(k), "cs_detail": detail,
                 "cs_upd": str(csu)[:10] if csu else '', "bom_upd": str(bmu)[:10] if bmu else '', "newer": newer})

for path in [r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\_schema\weld_conflict_371.csv",
             r"C:\Users\admin\AppData\Local\Temp\claude\d-----------100-AI-AGENT\02b63e35-1303-4eb0-8eb4-29df63d29c62\scratchpad\weld_conflict_371.csv"]:
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["node","name","cs_soyo","bom_soyo","ratio","direction","weld_item","last_prod","active","top_parent","cs_detail","cs_upd","bom_upd","newer"])
        w.writeheader()
        for r in sorted(rows, key=lambda x: (-x["active"], x["node"])): w.writerow(r)

# 패턴 분석
n = len(rows)
csbig = sum(1 for r in rows if r["direction"] == "CS>BOM"); cssml = n - csbig
active = sum(1 for r in rows if r["active"])
newer_cs = sum(1 for r in rows if r["newer"] == "CS최신"); newer_bom = sum(1 for r in rows if r["newer"] == "BOM최신")
bomzero = sum(1 for r in rows if r["bom_soyo"] == 0)
ratios = [r["ratio"] for r in rows if isinstance(r["ratio"], float) and r["bom_soyo"] > 0]
rc = Counter(round(x) for x in ratios if x)
print(f"불일치 {n}건 패턴:")
print(f"  방향: CS>BOM {csbig}({round(100*csbig/n)}%) · CS<BOM {cssml} · BOM=0(용접봉없음) {bomzero}")
print(f"  활성(최근24M 생산): {active} ({round(100*active/n)}%)")
print(f"  수정시점: CS최신 {newer_cs} · BOM최신 {newer_bom} · 동일/불명 {n-newer_cs-newer_bom}")
print(f"  배수분포(CS/BOM 반올림): {dict(sorted(rc.items()))}")
print(f"  배수 중앙값 근사: 2배±0.1 {sum(1 for x in ratios if 1.9<=x<=2.1)} · 정수배(2~5) {sum(1 for x in ratios if any(abs(x-m)<0.05 for m in(2,3,4,5)))}")
print("\n=== 대표 28건 (활성 우선) ===")
for r in sorted(rows, key=lambda x: (-x["active"], -(x["cs_soyo"]) ))[:28]:
    print(f"  {r['node']}|{r['name'][:16]}|CS={r['cs_soyo']}({r['cs_detail']})|BOM={r['bom_soyo']}|×{r['ratio']} {r['direction']}|생산{r['last_prod']}{'*활성' if r['active'] else ''}|{r['newer']}")
print("\nCSV: _schema/weld_conflict_371.csv")
