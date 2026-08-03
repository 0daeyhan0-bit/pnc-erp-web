# -*- coding: utf-8 -*-
"""Phase1 용접봉 재배치 — nx.proc_weld 신설 + nx.bom_line RAC 이관(값 보존).
용접봉(RAC)을 BOM 구성행에서 공정종속 자재로 분리. use_qty = 기존 bom_line.qty 그대로(재료비 diff0 보장).
cs_calc_except/lme_except/from_ymd/to_ymd 보존(전개·LME 동작 동일). 메타(pipe_diam·weld_st·unit_qty)는 Phase2 동적재계산용.
★bom_line 삭제는 이 스크립트에서 하지 않음(엔진 lines() 주입 후 게이트 통과 확인 뒤 별도 수행). 파괴 없음."""
import sys, os
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
CS = (f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
      f"DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
cn = pyodbc.connect(CS, autocommit=True); c = cn.cursor()

c.execute("""IF OBJECT_ID('nx.proc_weld','U') IS NULL CREATE TABLE nx.proc_weld(
    id INT IDENTITY(1,1) PRIMARY KEY,
    parent_item NVARCHAR(60) NOT NULL,   -- 공정귀속 부모(용접봉이 붙는 어셈블리/SUB)
    weld_item   NVARCHAR(60) NOT NULL,   -- 용접봉 코드(RAC*)
    weld_base   NVARCHAR(40),            -- RAC base(종류) = split('-')[0]
    pipe_diam   FLOAT, weld_st FLOAT, unit_qty FLOAT,   -- 메타(Phase2 동적: use_qty=ST×원단위×1.5)
    use_qty     FLOAT,                    -- ★소요량(=기존 bom_line.qty 보존, 재료비 diff0)
    cs_calc_except BIT DEFAULT 0, lme_except BIT DEFAULT 0,
    from_ymd NVARCHAR(8), to_ymd NVARCHAR(8), tag CHAR(1) DEFAULT 'W', src NVARCHAR(20),
    upd_dt datetime DEFAULT getdate())""")
c.execute("IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_procweld_parent') CREATE INDEX IX_procweld_parent ON nx.proc_weld(parent_item, weld_item)")

# 관경별 원단위(weld_diam 정본): pipe_diam → std_use_qty (은납 무관 최빈/최소)
c.execute("SELECT pipe_diam, MIN(std_use_qty) FROM nx.weld_diam GROUP BY pipe_diam")
UNIT = {round(float(r[0]), 4): float(r[1] or 0) for r in c.fetchall()}
# 부모 관경(nx.item.diam)
c.execute("SELECT item_code, ISNULL(diam,0) FROM nx.item")
IDIAM = {str(r[0]).strip(): float(r[1] or 0) for r in c.fetchall()}
# routing carrier 용접ST 합(용접봉 노드 item_code=RAC, p_item=부모, 용접/은납 51/28 합) — 메타용
c.execute("""SELECT p_item, item_code, SUM(work_qty) FROM nx.routing
    WHERE item_code LIKE 'RAC%' AND proc_code IN ('51','28') AND work_qty>0 GROUP BY p_item, item_code""")
WST = {}
for r in c.fetchall():
    WST[(str(r[0]).strip(), str(r[1]).strip())] = float(r[2] or 0)

# 기존 bom_line RAC 전량(값 보존)
c.execute("""SELECT h.item_code, l.child_item, l.qty, ISNULL(l.cs_calc_except,0), ISNULL(l.lme_except,0),
      ISNULL(l.from_ymd,''), ISNULL(l.to_ymd,'')
    FROM nx.bom_line l JOIN nx.bom_header h ON h.bom_id=l.bom_id WHERE l.child_item LIKE 'RAC%'""")
rows = c.fetchall()
c.execute("DELETE FROM nx.proc_weld")   # 파생테이블 전량 재빌드(원장 아님)
n = 0
for parent, weld, qty, cx, lx, f, t in rows:
    parent = str(parent).strip(); weld = str(weld).strip(); base = weld.split('-')[0]
    diam = IDIAM.get(parent, 0.0)
    unit = UNIT.get(round(diam, 4), 0.0)
    st = WST.get((parent, weld), 0.0)
    c.execute("""INSERT INTO nx.proc_weld(parent_item,weld_item,weld_base,pipe_diam,weld_st,unit_qty,use_qty,
          cs_calc_except,lme_except,from_ymd,to_ymd,tag,src)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,'W','bom_line이관')""",
        parent, weld, base, diam, st, unit, float(qty or 0), int(cx), int(lx), str(f), str(t))
    n += 1

c.execute("SELECT COUNT(*), SUM(CASE WHEN use_qty>0 THEN 1 ELSE 0 END), SUM(CASE WHEN cs_calc_except=1 THEN 1 ELSE 0 END) FROM nx.proc_weld")
r = c.fetchone()
print(f"nx.proc_weld 적재: {r[0]}행 (use_qty>0 {r[1]}, cs_calc_except=1 {r[2]})")
print(f"원본 bom_line RAC: {len(rows)}행 → 이관 {n}행 (누락 {len(rows)-n})")
# 이관 무손실 대조
c.execute("SELECT COUNT(*) FROM nx.bom_line WHERE child_item LIKE 'RAC%'")
print("bom_line RAC(현재, 미삭제):", c.fetchone()[0])
print("migrate_nx_proc_weld OK (bom_line 미삭제 — 엔진 게이트 통과 후 삭제)")
cn.close()
