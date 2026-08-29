# -*- coding: utf-8 -*-
"""협력사 사급재고 7월~ 이력 이관 → nx.sagub_maint (단일 원장·멱등).
   협력사입고(+) = tag '5'(사급출고)  = 레거시 PU_T_STOCK_MAINT tag5(부품·용접제외, -qty 부호보존)
   협력사출고(−) = tag 'SC'(세트소진) = 레거시 PU_T_SET_STOCK_MAINT × sagub_parts_soyo(§10)
   ★기초이관(tag9 remarks_src='migration')과 별개. 이 이관은 remarks_src='hist7'(멱등 삭제키).
   ★saleout(사급출고 웹)·setstock(세트입고 웹) 향후분은 실시간 posting → 여기선 7월~ 과거만.
   실행: python _migration/sagub_maint_hist_ingest.py [--commit]
"""
import sys, io, time
sys.path.insert(0, r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_sagub/PNC_ERP_Web/backend')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import common
import nx_soyo_engine as soyo
from nx_cost_engine import NxCostEngine
import pyodbc, db_client

COMMIT = '--commit' in sys.argv
START = "260701"
SRC = "hist7"

def live_cur():
    cs=(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
    return pyodbc.connect(cs, autocommit=True).cursor()

def f(x):
    try: return float(x or 0)
    except: return 0.0

eng = NxCostEngine(); cur = eng.cur; lcur = live_cur()
t0=time.time()

cur.execute("SELECT UPPER(LTRIM(RTRIM(item_code))) FROM nx.item WHERE item_code LIKE 'RAC%' OR item_code LIKE 'BCUP%' OR item_name LIKE '%용접%'")
weld = set(r[0].strip() for r in cur.fetchall())
cur.execute("SELECT DISTINCT UPPER(LTRIM(RTRIM(MAT_CODE))) FROM nx.v_pr_bom WHERE SAGUB_FLAG='1' AND ISNULL(MAT_CODE,'')<>''")
stop_set = set(r[0].strip() for r in cur.fetchall())
print(f"[제외 용접 {len(weld)}] [stop_set {len(stop_set)}]")

# ── 협력사입고(+) = tag5 per (cust,mat,ymd) ──
lcur.execute("""SELECT UPPER(LTRIM(RTRIM(CUST_CODE))), UPPER(LTRIM(RTRIM(MAT_CODE))), MAINT_YMD, SUM(CAST(MAINT_QTY AS float))
    FROM PU_T_STOCK_MAINT WITH(NOLOCK) WHERE MAINT_TAG='5' AND MAINT_YMD>=? AND ISNULL(MAT_CODE,'')<>''
    GROUP BY CUST_CODE, MAT_CODE, MAINT_YMD""", START)
rows=[]   # (ymd, tag, cust, mat, qty)
for c,m,y,q in lcur.fetchall():
    if not c or not m or not y: continue
    m=m.strip()
    if m in stop_set and m not in weld:
        rows.append((str(y).strip(),'5',c.strip(),m,-f(q)))   # 불출 음수 → 보유 +
IN_SUM=sum(r[4] for r in rows); print(f"[협력사입고 tag5] {len(rows)}행 Σ {IN_SUM:,.0f}")

# ── 협력사출고(−) = 세트입고 × 소요, per (cust,part,ymd) ──
soyo.warm_vpr(eng)
lcur.execute("""SELECT UPPER(LTRIM(RTRIM(CUST_CODE))), UPPER(LTRIM(RTRIM(ITEM_CODE))), MAINT_YMD, SUM(CAST(MAINT_QTY AS float))
    FROM PU_T_SET_STOCK_MAINT WITH(NOLOCK) WHERE MAINT_YMD>=? AND ISNULL(ITEM_CODE,'')<>''
    GROUP BY CUST_CODE, ITEM_CODE, MAINT_YMD""", START)
setg=[(r[0].strip(),r[1].strip(),str(r[2]).strip(),f(r[3])) for r in lcur.fetchall() if r[0] and r[1] and r[2]]
memo={}; outg={}
for c,it,y,qty in setg:
    if abs(qty)<1e-9: continue
    for part,per in soyo.sagub_parts_soyo(eng, it, stop_set, memo).items():
        if part in weld: continue
        k=(y,c,part); outg[k]=outg.get(k,0.0)-per*qty
oc=len(rows)
for (y,c,part),q in outg.items():
    rows.append((y,'S',c,part,q))   # 협력사출고=세트소진(단일문자 tag·음수). 수불장은 부호로 입/출 구분
OUT_SUM=sum(r[4] for r in rows[oc:]); print(f"[협력사출고 SC] {len(rows)-oc}행 Σ {OUT_SUM:,.0f}  (경과 {time.time()-t0:.0f}s)")

if COMMIT:
    cur.execute("DELETE FROM nx.sagub_maint WHERE remarks_src=?", SRC); cur.connection.commit()
    # per-ymd seq (기존 max 이후로)
    cur.execute("SELECT maint_ymd, ISNULL(MAX(maint_seq),0) FROM nx.sagub_maint GROUP BY maint_ymd")
    seqmax={r[0].strip():int(r[1]) for r in cur.fetchall() if r[0]}
    payload=[]
    for y,tag,c,m,q in rows:
        s=seqmax.get(y,0)+1; seqmax[y]=s
        rmk='7월이관 협력사입고(사급출고)' if tag=='5' else '7월이관 협력사출고(세트소진)'
        payload.append((y,s,tag,c,m,q,rmk,SRC))
    cur.fast_executemany=True
    cur.executemany("""INSERT INTO nx.sagub_maint(maint_ymd,maint_seq,maint_tag,cust_code,mat_code,maint_qty,remarks,remarks_src,insert_user_id,insert_datetime)
        VALUES(?,?,?,?,?,?,?,?,'hist',getdate())""", payload)
    cur.connection.commit()
    print(f"[적재] sagub_maint +{len(payload)}행(remarks_src={SRC})")
else:
    print("[dry-run] --commit 없으면 미적재")
print(f"(경과 {time.time()-t0:.0f}s)")
