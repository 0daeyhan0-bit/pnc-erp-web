# -*- coding: utf-8 -*-
"""비양산품목(가정) 자동판정 — 읽기전용(라이브 PARTNER_ERP RO). 정본 불변.
룰: 최근24개월(2024-08~2026-08) 생산실적 0 + BOM비어있음 → '비양산품목(가정)'.
 BOM비어있음 민감도 3정의: (A)BOM자식없음 (B)routing없음 (C)CS_T_ITEM_WELD없음.
대상: 원천갭 802부모(proc_weld meta_ok=0·use>0·CS_T_ITEM_WELD EXACT 부재) + AJR34909302 포착검증.
verdict: 생산실적0→'비양산품목(가정)', 생산실적有→'양산중_조치필요'. 두성 이관은 note 참고만."""
import sys, io, csv
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
from collections import defaultdict
def L(): return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
def N(): return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
lv = L().cursor(); nx = N().cursor()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
CUT = '240801'   # 최근24개월 시작(yymmdd)

# 생산실적: 최근24개월 실적有 집합 + 전체 최종생산일
lv.execute("SELECT ITEM_CODE, MAX(PROD_YMD) FROM PR_T_PROD_DTL GROUP BY ITEM_CODE")
LASTPROD = {str(r[0]).strip(): str(r[1]).strip() for r in lv.fetchall()}
lv.execute("SELECT DISTINCT ITEM_CODE FROM PR_T_PROD_DTL WHERE PROD_YMD >= ? AND ISNULL(PROD_QTY,0)<>0", CUT)
PROD24 = set(str(r[0]).strip() for r in lv.fetchall())
# BOM 자식수(정의A) — 레거시 PR_M_ITEM_BOM (부모=ITEM_CODE, 자식=MAT_CODE)
lv.execute("SELECT ITEM_CODE, COUNT(*) FROM PR_M_ITEM_BOM GROUP BY ITEM_CODE")
BOMCNT = {str(r[0]).strip(): int(r[1]) for r in lv.fetchall()}
# routing(정의B) — PR_M_ITEM_PROC_GAGONG 보유
lv.execute("SELECT DISTINCT ITEM_CODE FROM PR_M_ITEM_PROC_GAGONG")
HASROUTE = set(str(r[0]).strip() for r in lv.fetchall())
# CS weld(정의C)
lv.execute("SELECT DISTINCT P_ITEM_CODE FROM CS_T_ITEM_WELD")
HASWELD = set(str(r[0]).strip() for r in lv.fetchall())
# 품명·상태·거래처·등록시점
nx.execute("SELECT item_code, ISNULL(item_name,'') FROM nx.item"); NAME = {str(r[0]).strip(): str(r[1]).strip() for r in nx.fetchall()}
lv.execute("SELECT ITEM_CODE, ISNULL(ITEM_STATUS,''), ISNULL(IN_CUST_CODE,''), INSERT_DATETIME FROM PR_M_ITEM")
STAT={};INCUST={};REG={}
for r in lv.fetchall():
    ic=str(r[0]).strip(); STAT[ic]=str(r[1]).strip(); INCUST[ic]=str(r[2]).strip(); REG[ic]=(r[3].strftime('%Y-%m') if r[3] else '')
# 두성 거래처코드(참고)
DOOSUNG=set()
try:
    lv.execute("SELECT CUST_CODE FROM CM_M_CUST WHERE CUST_NAME LIKE '%두성%'")
    DOOSUNG=set(str(r[0]).strip() for r in lv.fetchall())
except Exception:
    try:
        lv.execute("SELECT PARTNER_CODE FROM PU_M_PARTNER WHERE PARTNER_NAME LIKE '%두성%'")
        DOOSUNG=set(str(r[0]).strip() for r in lv.fetchall())
    except Exception: pass

# 대상: 원천갭 802부모
nx.execute("SELECT DISTINCT parent_item FROM nx.proc_weld WHERE ISNULL(meta_ok,0)=0 AND use_qty>0")
gapparents = sorted(set(str(r[0]).strip() for r in nx.fetchall() if str(r[0]).strip() not in HASWELD))

def ymd_fmt(y): return f"20{y[:2]}-{y[2:4]}-{y[4:6]}" if len(y)==6 else y
def classify(p):
    prod24 = p in PROD24
    child = BOMCNT.get(p, 0)
    route = p in HASROUTE
    weld = p in HASWELD
    verdict = "양산중_조치필요" if prod24 else "비양산품목(가정)"
    note=[]
    if REG.get(p,'') and REG[p] <= '2023-12' and REG[p] >= '2022-01': note.append(f"등록{REG[p]}(2022~23)")
    if INCUST.get(p,'') in DOOSUNG: note.append("거래처=두성")
    return prod24, child, route, weld, verdict, "; ".join(note)

rows=[]
for p in gapparents:
    prod24, child, route, weld, verdict, note = classify(p)
    rows.append({"item": p, "item_name": NAME.get(p,''), "last_prod_date": ymd_fmt(LASTPROD.get(p,'')) or '없음',
                 "bom_child_cnt": child, "has_routing": int(route), "has_cs_weld": int(weld),
                 "verdict": verdict, "note": note})

# CSV
for path in [r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\_schema\nonprod_items_candidate.csv",
             r"C:\Users\admin\AppData\Local\Temp\claude\d-----------100-AI-AGENT\02b63e35-1303-4eb0-8eb4-29df63d29c62\scratchpad\nonprod_items_candidate.csv"]:
    with io.open(path,"w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["item","item_name","last_prod_date","bom_child_cnt","has_routing","has_cs_weld","verdict","note"])
        w.writeheader()
        for r in sorted(rows,key=lambda x:(x["verdict"],x["item"])): w.writerow(r)

# 집계
N802=len(rows)
nonprod=[r for r in rows if r["verdict"]=="비양산품목(가정)"]
active=[r for r in rows if r["verdict"]=="양산중_조치필요"]
print(f"=== 원천갭 부모 {N802}개 판정(라벨: 비양산품목(가정)) ===")
print(f"  비양산품목(가정)[최근24개월 생산0]: {len(nonprod)} ({round(100*len(nonprod)/N802,1)}%)")
print(f"  양산중_조치필요[최근24개월 생산有, 원천없음]: {len(active)} ({round(100*len(active)/N802,1)}%)")
# 민감도: 비양산분 중 정의별
dA=sum(1 for r in nonprod if r["bom_child_cnt"]==0)
dB=sum(1 for r in nonprod if r["has_routing"]==0)
dC=sum(1 for r in nonprod if r["has_cs_weld"]==0)
print(f"\n  [비양산({len(nonprod)}) 중 BOM비어있음 정의별]")
print(f"   (A)BOM자식없음: {dA}  (B)routing없음: {dB}  (C)CS_weld없음: {dC}")
# 전체 802 중 정의별(생산실적 무관)
print(f"\n  [원천갭802 전체 정의별 충족]")
print(f"   (A)자식0: {sum(1 for r in rows if r['bom_child_cnt']==0)}  (B)routing無: {sum(1 for r in rows if r['has_routing']==0)}  (C)CS_weld無: {N802}(정의상 전부)")
# 두성/등록시기 교차
doo=[r for r in rows if r["note"]]
print(f"\n  [교차확인] 등록2022~23 또는 거래처두성 단서 보유: {len(doo)} (두성코드={sorted(DOOSUNG) or '미발견'})")
for r in doo[:8]: print(f"     {r['item']} | {r['item_name'][:20]} | {r['note']} | {r['verdict']}")
# AJR34909302 포착검증
p='AJR34909302'; prod24,child,route,weld,verdict,note=classify(p)
print(f"\n=== ★AJR34909302 포착검증 ===")
print(f"   최근24M생산={'있음' if prod24 else '없음(0)'} 최종생산일={ymd_fmt(LASTPROD.get(p,''))or '없음'} | 자식={child} routing={route} CS_weld={weld}")
print(f"   verdict={verdict} | 정의A포착={child==0} 정의B포착={not route} 정의C포착={not weld}")
print("\nCSV: _schema/nonprod_items_candidate.csv (+scratchpad)")
