# -*- coding: utf-8 -*-
"""LG전자 LME인정가 (Cost Table 직거래) — nx 3테이블 + 최근 2년(2024.07~2026.07) 마이그레이션.
멱등(IF OBJECT_ID / 재적재 전 해당 근거범위 DELETE). 원천 = LG_FILES/26.06월_동 LME 인정가.xlsx.
- nx.lg_lme_header: 월별 재질 LME(Cu선물/황동현물/Cable)·환율(당월/전월)·직관 premium(152)·할증(1.05).
- nx.lg_lme_gagong: 월별 spec별 국가믹스 원천(베트남·중국 가공비/프리미엄/물류/내륙 + 관세율 + 믹스). 현월만.
- nx.lg_lme_costtable: 월별 spec별 재료비·가공비·원재료가(현월=산식재현, 과거=엑셀값).
재료비: 일반=LME×환율/1000, 직관&P/C=(LME+152)×1.05×환율/1000. 가공비: (중국Price×0.3+베트남Price×0.7)×환율/1000."""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, openpyxl

XLS = r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\LG_FILES\26.06월_동 LME 인정가.xlsx"
CS = (f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
      f"DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
cn = pyodbc.connect(CS, autocommit=True); cur = cn.cursor()

cur.execute("""IF OBJECT_ID('nx.lg_lme_header','U') IS NULL CREATE TABLE nx.lg_lme_header(
    apply_ym CHAR(6) PRIMARY KEY, cu_lme FLOAT, brass_lme FLOAT, cable_lme FLOAT,
    fx_now FLOAT, fx_prev FLOAT, premium FLOAT DEFAULT 152, surcharge FLOAT DEFAULT 1.05,
    upd_user NVARCHAR(30), upd_dt datetime DEFAULT getdate())""")
cur.execute("""IF OBJECT_ID('nx.lg_lme_gagong','U') IS NULL CREATE TABLE nx.lg_lme_gagong(
    apply_ym CHAR(6), gubun NVARCHAR(20), diam FLOAT, thick FLOAT,
    vn_gagong FLOAT, vn_prem FLOAT, vn_mul FLOAT, vn_naeryuk FLOAT,
    cn_gagong FLOAT, cn_prem FLOAT, cn_mul FLOAT, cn_naeryuk FLOAT,
    duty_vn FLOAT DEFAULT 0, duty_cn FLOAT DEFAULT 0.016, mix_cn FLOAT DEFAULT 0.3, mix_vn FLOAT DEFAULT 0.7,
    CONSTRAINT PK_lglme_gagong PRIMARY KEY(apply_ym,gubun,diam,thick))""")
cur.execute("""IF OBJECT_ID('nx.lg_lme_costtable','U') IS NULL CREATE TABLE nx.lg_lme_costtable(
    id INT IDENTITY(1,1) PRIMARY KEY, apply_ym CHAR(6), gubun NVARCHAR(20), diam FLOAT, thick FLOAT,
    p_no NVARCHAR(30), jaeryo FLOAT, gagong FLOAT, wonjae FLOAT, seq INT)""")
cur.execute("IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_lglme_ct') CREATE INDEX IX_lglme_ct ON nx.lg_lme_costtable(apply_ym,seq)")

wb = openpyxl.load_workbook(XLS, data_only=True)
ct = wb["0.Cost Table(직거래)"]; gg = wb["동가공비(직거래)"]
CI = openpyxl.utils.column_index_from_string
def num(v):
    try: return float(v)
    except Exception: return None

# ── 날짜블록 스캔(최근 2년 >= 202407) ──
blocks = []
for c in range(1, ct.max_column + 1):
    v = ct.cell(1, c).value
    m = re.match(r'^(\d{4})\.(\d{2})\.(\d{2})~', str(v or "").strip())
    if m:
        ym = m.group(1) + m.group(2)
        if ym >= "202407":
            blocks.append((ym, c))
print(f"대상 블록(>=202407): {len(blocks)}개 → {[b[0] for b in blocks]}")

# 재적재(근거키=대상 ym 범위)
yms = sorted({b[0] for b in blocks})
ph = ",".join("?" * len(yms))
for t in ("nx.lg_lme_costtable", "nx.lg_lme_header", "nx.lg_lme_gagong"):
    cur.execute(f"DELETE FROM {t} WHERE apply_ym IN ({ph})", *yms)

# ── costtable 적재(블록별 값) ──
KNOWN = ("L/W", "Capi", "직관", "고강도", "P/C", "Cable")
nct = 0
for ym, bc in blocks:
    seq = 0
    for r in range(3, ct.max_row + 1):
        gub = ct.cell(r, bc).value
        diam = num(ct.cell(r, bc + 1).value)
        if not (isinstance(gub, str) and gub.strip() and diam is not None):
            continue
        gub = gub.strip()
        if not any(k in gub for k in KNOWN):
            continue
        thick = num(ct.cell(r, bc + 2).value)
        pno = str(ct.cell(r, bc + 3).value or "").strip()[:30]
        jae = num(ct.cell(r, bc + 4).value)
        gag = num(ct.cell(r, bc + 5).value)
        won = num(ct.cell(r, bc + 6).value)
        seq += 1
        cur.execute("""INSERT INTO nx.lg_lme_costtable(apply_ym,gubun,diam,thick,p_no,jaeryo,gagong,wonjae,seq)
            VALUES(?,?,?,?,?,?,?,?,?)""", ym, gub[:20], diam, thick, pno, jae, gag, won, seq)
        nct += 1
print(f"costtable: {nct}행 적재")

# ── 현월(202607) header ──
CUR = "202607"
cu_lme = num(ct["I35"].value); brass = num(ct["I37"].value); cable = num(ct["I39"].value)
fx_now = num(ct["I36"].value); fx_prev = num(ct["W36"].value)
cur.execute("""INSERT INTO nx.lg_lme_header(apply_ym,cu_lme,brass_lme,cable_lme,fx_now,fx_prev,premium,surcharge,upd_user)
    VALUES(?,?,?,?,?,?,?,?,'migrate')""", CUR, cu_lme, brass, cable, fx_now, fx_prev, 152.0, 1.05)
print(f"header {CUR}: Cu={cu_lme} 황동={brass} Cable={cable} fx={fx_now}/{fx_prev}")

# ── 현월 gagong(동가공비 국가믹스 원천) ──
duty_vn = num(gg["AD3"].value) or 0.0; duty_cn = num(gg["AJ3"].value) or 0.016
COL = {k: CI(k) for k in ("C", "D", "E", "AA", "AB", "AC", "AE", "AG", "AH", "AI", "AK")}
ngg = 0
for r in range(8, gg.max_row + 1):
    gub = gg.cell(r, COL["C"]).value
    diam = num(gg.cell(r, COL["D"]).value)
    if not (isinstance(gub, str) and gub.strip() and diam is not None):
        continue
    thick = num(gg.cell(r, COL["E"]).value)
    vals = {k: (num(gg.cell(r, COL[k]).value) or 0.0) for k in ("AA", "AB", "AC", "AE", "AG", "AH", "AI", "AK")}
    cur.execute("""INSERT INTO nx.lg_lme_gagong(apply_ym,gubun,diam,thick,vn_gagong,vn_prem,vn_mul,vn_naeryuk,
        cn_gagong,cn_prem,cn_mul,cn_naeryuk,duty_vn,duty_cn,mix_cn,mix_vn)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,0.3,0.7)""",
        CUR, gub.strip()[:20], diam, thick, vals["AA"], vals["AB"], vals["AC"], vals["AE"],
        vals["AG"], vals["AH"], vals["AI"], vals["AK"], duty_vn, duty_cn)
    ngg += 1
print(f"gagong {CUR}: {ngg}행 (duty_vn={duty_vn} duty_cn={duty_cn})")

for t in ("nx.lg_lme_header", "nx.lg_lme_gagong", "nx.lg_lme_costtable"):
    cur.execute(f"SELECT COUNT(*) FROM {t}"); print(f"{t}: {cur.fetchone()[0]} rows")
print("migrate_nx_lg_lme OK")
cn.close()
