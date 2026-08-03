# -*- coding: utf-8 -*-
"""Phase2 보강 — nx.proc_weld 관경/원단위 메타 보정 + loss_factor(배수) 파라미터화.
정본 산식(W_CS_ESTI_010_ANALYSIS L39-42):
  CS_T_ITEM_WELD.use_qty = std_use_qty(관경별 weld_diam) × weld_qty(용접횟수)
  용접봉 BOM 소요량 = Σ(item_weld.use_qty) × 1.5   ← 1.5는 전역상수(합계에 적용)
∴ proc_weld.use_qty(=bom_line, 정본) = Σ(nx.item_weld.use_qty[parent,weld]) × 1.5
메타 도출(EXACT 키만, 퍼지매핑 금지):
  pipe_diam = 대표관경(weld_qty 최대), unit_qty = Σuse/Σweld_qty(유효원단위), weld_st=라우팅ST(51+28) 우선
역검증: round(weld_st × unit_qty × loss_factor, 4) == round(use_qty,4) → meta_ok=1(재계산 신뢰)
★use_qty(정본)는 절대 변경하지 않음(메타만 채움). 불일치/무매칭은 meta_ok=0 플래그, use_qty 보존.
멱등: 반복 실행 가능(컬럼 존재 검사 + 전량 재계산)."""
import sys
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
from collections import defaultdict

CS = (f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
      f"DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
cn = pyodbc.connect(CS, autocommit=True); c = cn.cursor()

# 1) 컬럼 추가(멱등)
c.execute("IF COL_LENGTH('nx.proc_weld','loss_factor') IS NULL ALTER TABLE nx.proc_weld ADD loss_factor FLOAT NULL")
c.execute("IF COL_LENGTH('nx.proc_weld','meta_ok') IS NULL ALTER TABLE nx.proc_weld ADD meta_ok BIT NULL")
c.execute("UPDATE nx.proc_weld SET loss_factor=1.5 WHERE loss_factor IS NULL")  # 기본 배수 = 레거시 전역상수 1.5

# 2) item_weld 집계(EXACT (item_code,weld_item))
c.execute("SELECT item_code,weld_item,pipe_diam,ISNULL(weld_qty,0),ISNULL(use_qty,0) FROM nx.item_weld")
agg = defaultdict(lambda: {'wq': 0.0, 'use': 0.0, 'diam': (0.0, -1.0)})
for it, wi, pd, wq, use in c.fetchall():
    k = (str(it).strip(), str(wi).strip()); a = agg[k]
    a['wq'] += float(wq); a['use'] += float(use)
    if float(wq) > a['diam'][1]:
        a['diam'] = (float(pd), float(wq))

# 3) 라우팅 용접/은납 ST(51+28) = 사용자가 편집하는 ST(재계산 곱수)
c.execute("""SELECT p_item,item_code,SUM(work_qty) FROM nx.routing
    WHERE item_code LIKE 'RAC%' AND proc_code IN ('51','28') AND work_qty>0 GROUP BY p_item,item_code""")
rst = {(str(r[0]).strip(), str(r[1]).strip()): float(r[2]) for r in c.fetchall()}

# 4) proc_weld 순회 → 메타 채움(use_qty 불변). 계산은 Python, 반영은 스테이징+set기반 UPDATE(연결 안정)
c.execute("SELECT id,parent_item,weld_item,ISNULL(use_qty,0) FROM nx.proc_weld")
rows = [(r[0], str(r[1]).strip(), str(r[2]).strip(), float(r[3])) for r in c.fetchall()]
LF = 1.5
n_valid = n_flag = n_use0 = n_noiw = 0
upd = []   # (id, pipe_diam, unit_qty, weld_st, meta_ok)
for pid, parent, weld, use in rows:
    k = (parent, weld)
    if k in agg and agg[k]['wq'] > 0:
        a = agg[k]
        unit = a['use'] / a['wq']
        diam = a['diam'][0]
        st = rst.get(k, a['wq'])          # 라우팅ST 우선(편집 대상), 없으면 item_weld 합
        exp = st * unit * LF
        ok = (abs(exp - use) < 6e-5) or (round(exp, 4) == round(use, 4))
        upd.append((pid, diam, unit, st, 1 if ok else 0))
        if ok: n_valid += 1
        else:  n_flag += 1
    else:
        # item_weld 무매칭 → 메타 미도출(NULL 유지), use_qty 보존, 플래그
        upd.append((pid, None, None, None, 1 if use == 0 else 0))
        if use == 0: n_use0 += 1
        else: n_noiw += 1

# 스테이징 테이블로 배치 반영
c.execute("IF OBJECT_ID('tempdb..#pwmeta') IS NOT NULL DROP TABLE #pwmeta")
c.execute("CREATE TABLE #pwmeta(id INT PRIMARY KEY, pipe_diam FLOAT NULL, unit_qty FLOAT NULL, weld_st FLOAT NULL, meta_ok BIT)")
cur2 = cn.cursor(); cur2.fast_executemany = True
cur2.executemany("INSERT INTO #pwmeta(id,pipe_diam,unit_qty,weld_st,meta_ok) VALUES(?,?,?,?,?)", upd)
c.execute("""UPDATE p SET p.pipe_diam=COALESCE(m.pipe_diam,p.pipe_diam), p.unit_qty=COALESCE(m.unit_qty,p.unit_qty),
             p.weld_st=COALESCE(m.weld_st,p.weld_st), p.meta_ok=m.meta_ok
             FROM nx.proc_weld p JOIN #pwmeta m ON m.id=p.id""")
c.execute("DROP TABLE #pwmeta")

tot = len(rows)
print(f"proc_weld {tot}행 메타 보정:")
print(f"  meta_ok(재계산 신뢰) = valid {n_valid} + use0무매칭 {n_use0} = {n_valid+n_use0} ({round(100*(n_valid+n_use0)/tot,1)}%)")
print(f"  flag(불일치, use_qty보존): item_weld있음_불일치 {n_flag} + item_weld무매칭_use>0 {n_noiw} = {n_flag+n_noiw} ({round(100*(n_flag+n_noiw)/tot,1)}%)")
c.execute("SELECT SUM(CASE WHEN pipe_diam>0 THEN 1 ELSE 0 END), SUM(CASE WHEN unit_qty>0 THEN 1 ELSE 0 END), SUM(CASE WHEN meta_ok=1 THEN 1 ELSE 0 END) FROM nx.proc_weld")
r = c.fetchone()
print(f"  pipe_diam>0 {r[0]} · unit_qty>0 {r[1]} · meta_ok=1 {r[2]}")
print("migrate_procweld_meta OK — use_qty(정본) 불변, loss_factor 기본 1.5")
cn.close()
