# -*- coding: utf-8 -*-
"""협력사 사급부품 수불 원장 nx 적재 (2026-01~, 멱등).
   nx.sagub_parts_ledger = (협력사×사급부품) 일자별 movement.
     tag 'OUT' = 사급출고(우리→협력사, +) · 'SET' = 세트입고 소진(−).
   소스: 입고=live PU_T_STOCK_MAINT tag5(부품·용접제외) / 소진=live PU_T_SET_STOCK_MAINT × sagub_parts_soyo(§10).
   기초0 @2026-01(사용자 확정). 실행: python _migration/sagub_parts_ledger_ingest.py [--commit]
"""
import sys, io, time
sys.path.insert(0, r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_sagub/PNC_ERP_Web/backend')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import common
import nx_soyo_engine as soyo
from nx_cost_engine import NxCostEngine
import pyodbc, db_client

COMMIT = '--commit' in sys.argv
START = "260101"
SRC = "rebuild260829"

def live_cur():
    cs=(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
    return pyodbc.connect(cs, autocommit=True).cursor()

def f(x):
    try: return float(x or 0)
    except: return 0.0

eng = NxCostEngine(); cur = eng.cur; lcur = live_cur()
t0=time.time()

# ── DDL (멱등) ──
cur.execute("""IF OBJECT_ID('nx.sagub_parts_ledger') IS NULL
CREATE TABLE nx.sagub_parts_ledger(
  id int IDENTITY PRIMARY KEY,
  cust_code varchar(20) NOT NULL,
  mat_code  varchar(30) NOT NULL,
  maint_ymd char(6) NOT NULL,
  tag varchar(4) NOT NULL,            -- OUT=사급출고(+) / SET=세트입고소진(-) / ADJ
  qty float NOT NULL,                 -- signed(+보낸/-소진)
  ref_item varchar(30) NULL,          -- 소진: 완제품 도번(대표)
  src varchar(20) NOT NULL,
  remarks nvarchar(200) NULL,
  insert_datetime datetime DEFAULT GETDATE())""")
cur.execute("IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='ix_sagpl_key') CREATE INDEX ix_sagpl_key ON nx.sagub_parts_ledger(cust_code,mat_code,maint_ymd)")
cur.connection.commit()   # DDL 확정

# ── 용접 제외 + stop_set ──
cur.execute("SELECT UPPER(LTRIM(RTRIM(item_code))) FROM nx.item WHERE item_code LIKE 'RAC%' OR item_code LIKE 'BCUP%' OR item_name LIKE '%용접%'")
weld = set(r[0].strip() for r in cur.fetchall())
cur.execute("SELECT DISTINCT UPPER(LTRIM(RTRIM(MAT_CODE))) FROM nx.v_pr_bom WHERE SAGUB_FLAG='1' AND ISNULL(MAT_CODE,'')<>''")
stop_set = set(r[0].strip() for r in cur.fetchall())
print(f"[제외 용접 {len(weld)}] [stop_set {len(stop_set)}]")

# ── 입고(+) rows: tag5 per (cust,mat,ymd), 부품·용접제외 ──
lcur.execute("""SELECT UPPER(LTRIM(RTRIM(CUST_CODE))), UPPER(LTRIM(RTRIM(MAT_CODE))), MAINT_YMD, SUM(CAST(MAINT_QTY AS float))
    FROM PU_T_STOCK_MAINT WITH(NOLOCK) WHERE MAINT_TAG='5' AND MAINT_YMD>=? AND ISNULL(MAT_CODE,'')<>''
    GROUP BY CUST_CODE, MAT_CODE, MAINT_YMD""", START)
in_rows=[]
for c,m,y,q in lcur.fetchall():
    if not c or not m or not y: continue
    m=m.strip()
    if m in stop_set and m not in weld:
        in_rows.append((c.strip(), m, str(y).strip(), 'OUT', -f(q), None))  # tag5 불출=음수 → 협력사 보유 +(반품은 −로 상쇄)
print(f"[입고] {len(in_rows)}행 · Σ {sum(r[4] for r in in_rows):,.0f}")

# ── 소진(−) rows: set_stock_maint per (cust,완제품,ymd) × soyo → part ──
soyo.warm_vpr(eng)
lcur.execute("""SELECT UPPER(LTRIM(RTRIM(CUST_CODE))), UPPER(LTRIM(RTRIM(ITEM_CODE))), MAINT_YMD, SUM(CAST(MAINT_QTY AS float))
    FROM PU_T_SET_STOCK_MAINT WITH(NOLOCK) WHERE MAINT_YMD>=? AND ISNULL(ITEM_CODE,'')<>''
    GROUP BY CUST_CODE, ITEM_CODE, MAINT_YMD""", START)
setg = [(r[0].strip(), r[1].strip(), str(r[2]).strip(), f(r[3])) for r in lcur.fetchall() if r[0] and r[1] and r[2]]
memo={}; outg={}          # (cust,part,ymd) -> [qty(누적·음수), 대표 완제품]
for c,it,y,qty in setg:
    if abs(qty)<1e-9: continue
    for part,per in soyo.sagub_parts_soyo(eng, it, stop_set, memo).items():
        if part in weld: continue
        k=(c,part,y); e=outg.get(k)
        if e: e[0]-=per*qty
        else: outg[k]=[-per*qty, it]
out_rows=[(c,part,y,'SET',v[0],v[1]) for (c,part,y),v in outg.items()]
print(f"[소진] {len(out_rows)}행(집계) · Σ {sum(r[4] for r in out_rows):,.0f}  (경과 {time.time()-t0:.0f}s)")

# ── 적재(멱등) ──
if COMMIT:
    cur.execute("DELETE FROM nx.sagub_parts_ledger WHERE src=?", SRC); cur.connection.commit()
    allr = in_rows + out_rows
    cur.fast_executemany = True
    cur.executemany("""INSERT INTO nx.sagub_parts_ledger(cust_code,mat_code,maint_ymd,tag,qty,ref_item,src,remarks)
        VALUES(?,?,?,?,?,?,?,?)""", [(c,m,y,t,q,ri,SRC,None) for (c,m,y,t,q,ri) in allr])
    cur.connection.commit()
    print(f"[적재] {len(allr)}행 커밋(src={SRC})")
else:
    print("[dry-run] --commit 없으면 미적재")
print(f"(경과 {time.time()-t0:.0f}s)")
