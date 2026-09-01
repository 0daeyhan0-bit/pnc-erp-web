# -*- coding: utf-8 -*-
"""세트입고 수불이력 미러 보정 — nx.PU_T_STOCK_MAINT ← nx.stock_ledger (2026-09-01 신설)

왜 필요한가
  웹 재고 쓰기는 **3군데**를 채워야 화면까지 이어진다(stock.py:390/418/488 패턴):
      ① nx.stock_ledger        원장(웹 정본)
      ② nx.PU_T_MAT_STOCK_WH   잔량 스냅샷
      ③ nx.PU_T_STOCK_MAINT    수불이력   ← 「자재 입출고현황」·「제품입출고현황」이 읽는 곳
  세트입고 경로(setin.py)에 ③이 없어서, 원장·잔량은 맞는데 **입고 이력이 화면에 안 보였다**.
  2026-09-01 setin.py 에 `_mirror_ins` 를 넣어 앞으로는 자동 기록되지만,
  그 전에 웹으로 입고한 분은 미러가 비어 있다. 이 스크립트가 그 과거분을 채운다.

★안전 원칙
  · 라이브(PARTNER_ERP)는 **건드리지 않는다**(§1-1). 쓰기는 nx 뿐.
  · `--apply` 없이는 조회만(기본 dry-run).
  · 실행 전 백업 테이블 생성.
  · **중복 2중 차단** — 이게 이 스크립트의 핵심이다:
      (a) `INSERT_USER_ID='web'` 인 원장행만 대상  (레거시가 넣은 건 제외)
      (b) 미러에 같은 (일자·자재·TAG·수량)이 이미 있으면 제외
    실측 2026-09-01: 8/31 은 웹·레거시 **양쪽에서 같은 송장을 입고**한 병행운영 기간이라
    웹원장 240행 중 203행이 미러와 중복이었다. 무조건 넣으면 재고가 2배가 된다.
  · SEQ 는 **웹 대역 20000~** 만 쓴다(common.py:496 규약). MAINT_SEQ 는 smallint(≤32767).
  · **잔량(PU_T_MAT_STOCK_WH)은 건드리지 않는다** — 이미 반영돼 있다. 이력만 채운다.

사용
    python _schema/backfill_setin_mirror.py                      # 조회만(기본, 8/31~9/1)
    python _schema/backfill_setin_mirror.py --from 260831 --to 260901 --apply
"""
import sys, os, io, argparse, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(_HERE, '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--from', dest='frm', default='260831', help='시작 YYMMDD')
AP.add_argument('--to', dest='to', default='260901', help='종료 YYMMDD')
AP.add_argument('--apply', action='store_true', help='실제 반영(없으면 조회만)')
ARG = AP.parse_args()

import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
BK = 'nx.bk_pustockmaint_' + datetime.datetime.now().strftime('%y%m%d_%H%M')

cn = pyodbc.connect(CS, autocommit=False)
cur = cn.cursor()

print('=' * 76)
print(' 세트입고 수불이력 미러 보정  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print(f' 기간 {ARG.frm} ~ {ARG.to}')
print('=' * 76)

# ── 대상 = 웹이 넣은 세트입고(S) · 직납출고(B) 중, 미러에 없는 것 ──
SEL = """SELECT l.MAINT_YMD, l.MAINT_SEQ, RTRIM(l.MAT_CODE), CAST(l.MAINT_QTY AS float),
                RTRIM(ISNULL(l.CUST_CODE,'')), RTRIM(ISNULL(l.ITEM_CODE,'')),
                RTRIM(ISNULL(l.MAINT_TAG,'')), RTRIM(ISNULL(l.OUT_WH_GUBUN,'')),
                RTRIM(ISNULL(l.REMARKS,''))
           FROM nx.stock_ledger l WITH(NOLOCK)
          WHERE l.MAINT_YMD BETWEEN ? AND ?
            AND l.MAINT_TAG IN ('S','B')
            AND RTRIM(ISNULL(l.INSERT_USER_ID,''))='web'
            AND (l.MAINT_TAG='S' OR l.REMARKS=N'직납품 영업창고 출고')
            AND NOT EXISTS(SELECT 1 FROM nx.PU_T_STOCK_MAINT p WITH(NOLOCK)
                            WHERE p.MAINT_YMD=l.MAINT_YMD
                              AND RTRIM(p.MAT_CODE)=RTRIM(l.MAT_CODE)
                              AND RTRIM(ISNULL(p.MAINT_TAG,''))=RTRIM(ISNULL(l.MAINT_TAG,''))
                              AND ABS(CAST(p.MAINT_QTY AS float)-CAST(l.MAINT_QTY AS float))<0.001)
          ORDER BY l.MAINT_YMD, l.MAINT_SEQ"""

cur.execute(SEL, ARG.frm, ARG.to)
rows = cur.fetchall()
print(f'\n① 보정대상 {len(rows):,}행')
if not rows:
    print('   ✅ 채울 것이 없습니다(이미 반영됐거나 대상 없음).')
    cn.close(); sys.exit(0)

agg = {}
for r in rows:
    k = (str(r[0]).strip(), str(r[6]).strip())
    a = agg.setdefault(k, [0, 0.0])
    a[0] += 1; a[1] += float(r[3] or 0)
print('   일자 · TAG · 행수 · 수량')
for k in sorted(agg):
    print(f'   {k[0]}  {k[1]}  {agg[k][0]:>5,}  {agg[k][1]:>12,.0f}')

print('\n② 샘플 8건')
for r in rows[:8]:
    print(f'   {r[0]}-{int(r[1]):<5} {str(r[2]):22s} {float(r[3]):>8,.0f} '
          f'{str(r[6])} {str(r[8])[:20]}')

# ── SEQ 여유 확인 (smallint 32767) ──
print('\n③ SEQ 여유 (웹대역 20000~ · smallint 최대 32767)')
need = {}
for r in rows:
    need[str(r[0]).strip()] = need.get(str(r[0]).strip(), 0) + 1
seqmap = {}
bad = False
for y, n in sorted(need.items()):
    cur.execute("""SELECT ISNULL(MAX(MAINT_SEQ),19999) FROM nx.PU_T_STOCK_MAINT WITH(NOLOCK)
                    WHERE MAINT_YMD=? AND MAINT_SEQ>=20000""", y)
    mx = int(cur.fetchone()[0])
    seqmap[y] = mx
    ok = (mx + n) <= 32767
    if not ok: bad = True
    print(f'   {y}: 현재최대 {mx} + {n} = {mx+n}   {"OK" if ok else "★32767 초과 — 중단"}')
if bad:
    print('\n   ★SEQ 한도 초과 — 반영하지 않습니다.')
    cn.close(); sys.exit(1)

if not ARG.apply:
    print('\n※ DRY-RUN 입니다. 실제로 반영하려면 --apply 를 붙이세요.')
    print('   ※잔량(PU_T_MAT_STOCK_WH)은 건드리지 않습니다 — 이미 반영돼 있고 이력만 채웁니다.')
    cn.close(); sys.exit(0)

# ───────────────────────── APPLY ─────────────────────────
print(f'\n④ 백업 → {BK}')
cur.execute(f"""SELECT * INTO {BK} FROM nx.PU_T_STOCK_MAINT
                 WHERE MAINT_YMD BETWEEN ? AND ?""", ARG.frm, ARG.to)
print(f'   {cur.rowcount:,}행 백업(해당 기간)')

print('\n⑤ 반영')
ins = 0
for r in rows:
    ymd, mat, qty = str(r[0]).strip(), str(r[2]).strip(), float(r[3] or 0)
    cust, doban, tag = str(r[4]).strip(), str(r[5]).strip(), str(r[6]).strip()
    owg, rmk = str(r[7]).strip(), str(r[8]).strip()
    seqmap[ymd] = seqmap.get(ymd, 19999) + 1
    sq = seqmap[ymd]
    cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT
            (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,REMARKS,
             WH_CUST_CODE,GAGONG_PROC_CODE,OUT_WH_GUBUN,ITEM_CODE,
             INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
             UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
            VALUES(?,?,?,?,?,?,?,'Z99990','IS0001',?,?,'web',GETDATE(),'backfill',
                   'web',GETDATE(),'backfill')""",
        ymd, sq, tag[:1], (cust or None), mat, qty, (rmk or None),
        (owg or None), (doban or None))
    ins += 1
print(f'   INSERT {ins:,}행')

cn.commit()

print('\n⑥ 검증 — 남은 보정대상')
cur.execute(SEL, ARG.frm, ARG.to)
left = len(cur.fetchall())
print(f'   {left}행   ' + ('✅ 완료' if left == 0 else '★남음'))
cur.execute("""SELECT COUNT(*), ISNULL(SUM(CAST(MAINT_QTY AS float)),0)
                 FROM nx.PU_T_STOCK_MAINT WITH(NOLOCK)
                WHERE MAINT_YMD BETWEEN ? AND ? AND RTRIM(ISNULL(INSERT_WINDOW,''))='backfill'""",
            ARG.frm, ARG.to)
r = cur.fetchone()
print(f'   보정분 확인: {int(r[0]):,}행 · {float(r[1]):,.0f}')
print(f'\n   되돌리려면: DELETE FROM nx.PU_T_STOCK_MAINT WHERE INSERT_WINDOW=\'backfill\'')
print(f'              (또는 백업 {BK} 참조)')
print('   ⚠ 자재 입출고현황을 새로고침하면 입고 이력이 보입니다.')
cn.close()
