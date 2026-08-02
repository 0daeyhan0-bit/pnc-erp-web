# -*- coding: utf-8 -*-
"""직거래 LME 월연동 판가 자동정본화 — Phase① 대상+동소요량+base 적재.
레거시 w_tc_master_165/090 수작업(Excel 인정가→일괄등록 PR_M_ITEM_COST) 자동화.
- nx.dtrade_lme_index : 월별 직거래 LME index(원/kg) = nx.lg_lme_costtable L/W 재료비(=LME×fx/1000).
- nx.dtrade_price     : 대상 마스터(item·cust·cost_tag·dong_qty·qty_src·base_ym·base_item_cost·base_lme).
  대상 = E/S 판가 정기변동(2602~2607 2회+). 동소요량 = LG 부자재정본(392) 우선 + 역산(판가Δ÷ΔLME) 보완.
  base = 260613 배치(2606) 라이브 item_cost + LME_index(202606). 라이브 PR_M_ITEM_COST 읽기전용.
- nx.dtrade_price_ts  : 계산 판가시계열(엔진 write, Phase②③에서 채움).
멱등: 근거범위 재적재. 산식 판가(월)=base_item_cost + dong_qty×(LME월 − base_LME)."""
import sys, os
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, openpyxl

F = lambda v: float(v) if v is not None else 0.0
def conn(db):
    return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE={db};UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
nx = conn("PARTNER_ERP_TEST3"); nc = nx.cursor()
lv = conn("PARTNER_ERP"); lc = lv.cursor()
BASE_YM = "202606"; BASE_YMD = "260613"; PRED_YMD = "260709"    # base 배치(6월) → 예측/검증 배치(7월)

# ── 테이블 ──
nc.execute("""IF OBJECT_ID('nx.dtrade_lme_index','U') IS NULL CREATE TABLE nx.dtrade_lme_index(
    apply_ym CHAR(6) PRIMARY KEY, lme_index FLOAT, metal NVARCHAR(10) DEFAULT 'CU', upd_dt datetime DEFAULT getdate())""")
nc.execute("""IF OBJECT_ID('nx.dtrade_price','U') IS NULL CREATE TABLE nx.dtrade_price(
    item_code NVARCHAR(60), cust_code NVARCHAR(20), cost_tag CHAR(1), direct_flag BIT DEFAULT 1,
    linkage NVARCHAR(12), dong_qty FLOAT, qty_src NVARCHAR(10), base_ym CHAR(6), base_item_cost FLOAT, base_lme FLOAT,
    main_flag CHAR(1), item_desc NVARCHAR(120), last_ymd CHAR(6), sagub_flag BIT DEFAULT 0, upd_dt datetime DEFAULT getdate(),
    CONSTRAINT PK_dtrade_price PRIMARY KEY(item_code,cust_code,cost_tag))""")
nc.execute("IF COL_LENGTH('nx.dtrade_price','linkage') IS NULL ALTER TABLE nx.dtrade_price ADD linkage NVARCHAR(12)")
nc.execute("IF COL_LENGTH('nx.dtrade_price','last_ymd') IS NULL ALTER TABLE nx.dtrade_price ADD last_ymd CHAR(6)")
nc.execute("IF COL_LENGTH('nx.dtrade_price','sagub_flag') IS NULL ALTER TABLE nx.dtrade_price ADD sagub_flag BIT DEFAULT 0")
nc.execute("""IF OBJECT_ID('nx.dtrade_price_ts','U') IS NULL CREATE TABLE nx.dtrade_price_ts(
    item_code NVARCHAR(60), cust_code NVARCHAR(20), cost_tag CHAR(1), apply_ym CHAR(6),
    lme_index FLOAT, mat_cost_calc FLOAT, item_cost FLOAT, main_flag CHAR(1),
    remarks NVARCHAR(100) DEFAULT N'동가반영(직거래)', computed_dt datetime DEFAULT getdate(),
    CONSTRAINT PK_dtrade_price_ts PRIMARY KEY(item_code,cust_code,cost_tag,apply_ym))""")

# ── LME index(월) = lg_lme_costtable L/W 재료비 평균 ──
nc.execute("DELETE FROM nx.dtrade_lme_index")
nc.execute("""INSERT INTO nx.dtrade_lme_index(apply_ym,lme_index)
    SELECT apply_ym, AVG(CAST(jaeryo AS float)) FROM nx.lg_lme_costtable WHERE gubun='L/W' GROUP BY apply_ym""")
nc.execute("SELECT apply_ym,lme_index FROM nx.dtrade_lme_index")
LME = {r[0]: F(r[1]) for r in nc.fetchall()}
base_lme = LME.get(BASE_YM)
pred_lme = LME.get("202607")
print(f"LME index: base(202606)={base_lme} 예측(202607)={pred_lme} ΔLME={round(pred_lme-base_lme,1)}")

# ── LG 부자재 정본(392) 동소요량 ──
jr = openpyxl.load_workbook(r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\LG_FILES\26.7월_동부자재 인정가(4개사 통합본).xlsx", data_only=True)["정리"]
LG392 = {}
for r in range(6, jr.max_row + 1):
    b = jr.cell(r, 2).value
    if b: LG392[str(b).strip()] = F(jr.cell(r, 1).value)
print(f"LG392 동소요량: {len(LG392)}품번")

# ── 사급자재(동가) 집합 ──
lc.execute("SELECT DISTINCT LTRIM(RTRIM(MAT_CODE)) FROM CS_M_ITEM_BOM WHERE SAGUB_FLAG='1' AND TO_APPLY_YMD>='260101'")
SAGUB = set(r[0] for r in lc.fetchall())

# ── 전 E/S (item·cust·tag): 변동횟수·최신월·base·예측월값 ──
lc.execute("""WITH h AS (SELECT c.ITEM_CODE,c.CUST_CODE,c.COST_TAG,c.COST_APPLY_YMD,c.ITEM_COST,ISNULL(c.MAIN_FLAG,'') mf,ISNULL(i.ITEM_DESC,'') dsc,
     LAG(c.ITEM_COST) OVER(PARTITION BY c.ITEM_CODE,c.CUST_CODE,c.COST_TAG ORDER BY c.COST_APPLY_YMD,c.INSERT_DATETIME) prev
   FROM PR_M_ITEM_COST c LEFT JOIN PR_M_ITEM i ON i.ITEM_CODE=c.ITEM_CODE WHERE c.COST_TAG IN('E','S'))
  SELECT ITEM_CODE,CUST_CODE,COST_TAG,MAX(mf) mf,MAX(dsc) dsc,
     SUM(CASE WHEN COST_APPLY_YMD BETWEEN '260201' AND '260731' AND prev IS NOT NULL AND ABS(ITEM_COST-prev)>0.5 THEN 1 ELSE 0 END) nchg,
     MAX(COST_APPLY_YMD) last_ymd,
     MAX(CASE WHEN COST_APPLY_YMD=? THEN ITEM_COST END) c7
   FROM h GROUP BY ITEM_CODE,CUST_CODE,COST_TAG""", PRED_YMD)
cand = lc.fetchall()
print(f"E/S 전체(item·cust·tag): {len(cand)}")

def cost_asof(item, cust, tag, ymd):
    lc.execute("""SELECT TOP 1 ITEM_COST FROM PR_M_ITEM_COST WHERE ITEM_CODE=? AND CUST_CODE=? AND COST_TAG=? AND COST_APPLY_YMD<=?
        ORDER BY COST_APPLY_YMD DESC, INSERT_DATETIME DESC""", item, cust, tag, ymd)
    r = lc.fetchone(); return F(r[0]) if r else None

nc.execute("DELETE FROM nx.dtrade_price")
n_dir = n_stale = skip = n_lg = n_inv = 0
dLME = pred_lme - base_lme
for item, cust, tag, mf, dsc, nchg, last_ymd, c7 in cand:
    item = item.strip(); cust = (cust or "").strip(); last_ymd = (last_ymd or "").strip()
    is_sg = 1 if item in SAGUB else 0
    if nchg >= 2:
        # ── 직거래 LME 월연동 ──
        bic = cost_asof(item, cust, tag, BASE_YMD)
        if bic is None or bic <= 0: skip += 1; continue
        dq = None; src = None
        if item in LG392 and LG392[item] > 0:
            dq = LG392[item]; src = "LG392"; n_lg += 1
        elif c7 is not None and dLME:
            dq = round((F(c7) - bic) / dLME, 5)
            if dq > 0: src = "역산"; n_inv += 1
            else: dq = None
        if dq is None: skip += 1; continue
        nc.execute("""INSERT INTO nx.dtrade_price(item_code,cust_code,cost_tag,linkage,dong_qty,qty_src,base_ym,base_item_cost,base_lme,main_flag,item_desc,last_ymd,sagub_flag)
            VALUES(?,?,?,N'직거래LME',?,?,?,?,?,?,?,?,?)""", item, cust, tag, dq, src, BASE_YM, bic, base_lme, (mf or "0"), (dsc or "")[:120], last_ymd, is_sg)
        n_dir += 1
    elif last_ymd and last_ymd <= "260228":
        # ── 사급-only 정체(2602 이후 판가 불변): 대상제외·base 고정, 재계산 안 함 ──
        lic = cost_asof(item, cust, tag, "991231")   # 현재(최신) 고정판가
        if lic is None: skip += 1; continue
        nc.execute("""INSERT INTO nx.dtrade_price(item_code,cust_code,cost_tag,linkage,dong_qty,qty_src,base_ym,base_item_cost,base_lme,main_flag,item_desc,last_ymd,sagub_flag)
            VALUES(?,?,?,N'사급정체',0,N'정체',?,?,NULL,?,?,?,?)""", item, cust, tag, last_ymd[:6], lic, (mf or "0"), (dsc or "")[:120], last_ymd, is_sg)
        n_stale += 1
    else:
        skip += 1   # 중간(변동<2회·정체아님) 제외

print(f"\nnx.dtrade_price 적재: 직거래LME {n_dir}(LG392 {n_lg}·역산 {n_inv}) · 사급정체 {n_stale} · skip {skip}")
for t in ("nx.dtrade_lme_index", "nx.dtrade_price", "nx.dtrade_price_ts"):
    nc.execute(f"SELECT COUNT(*) FROM {t}"); print(f"  {t}: {nc.fetchone()[0]}")
print("migrate_nx_dtrade_price OK")
nx.close(); lv.close()
