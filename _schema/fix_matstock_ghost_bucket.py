# -*- coding: utf-8 -*-
"""자재재고 유령 버킷 정리 — CUST_CODE 가 'Z99990' 이 아닌 행 (2026-09-01 신설)

무엇을 고치나
  `nx.PU_T_MAT_STOCK_WH` 의 버킷키 CUST_CODE 는 **창고 소유주 'Z99990' 고정**이다
  (라이브 PARTNER_ERP 7,762행이 전부 Z99990 — 실측). 그런데 웹의
  `stock_update`/`stock_delete` 가 원장의 거래처(매입처)를 버킷키로 써서
  UPDATE 가 기존 행을 못 찾고 **새 행을 INSERT** 했다.

      AJR77144307-STS : [Z99990 · IS0001 =  92]   ← 정상
                        [2005   · IS0001 =  -4]   ← ★유령행

  재고조회는 창고 합을 보므로 값이 조용히 −4 만큼 틀어지고,
  음수차단 규칙도 이 행은 잡지 못한다.

코드 수정은 이미 됨
  `backend/routers/stock.py` `_mat_mirror_edit` 이 버킷키를 Z99990 으로 일원화.
  이 스크립트는 **이미 생겨버린 행**을 정리한다.

★안전 원칙 (CLAUDE.md §1-3 — 태그기반 대량삭제 금지)
  · 대상을 **근거키(자재·창고·거래처)로 한 건씩** 특정한다.
  · 삭제가 아니라 **정상 버킷에 합산 후 제거** — 수량을 잃지 않는다.
  · `--apply` 를 주지 않으면 **조회만** 한다(기본 dry-run).
  · 실행 전 대상 전체를 화면에 찍고, 백업 테이블에 남긴다.

사용
    python _schema/fix_matstock_ghost_bucket.py            # 조회만(기본)
    python _schema/fix_matstock_ghost_bucket.py --apply    # 실제 정리
"""
import sys, os, io, argparse, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--apply', action='store_true', help='실제 정리(없으면 조회만)')
ARG = AP.parse_args()

import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
BK = 'nx.bk_matstock_ghost_' + datetime.datetime.now().strftime('%y%m%d_%H%M')

cn = pyodbc.connect(CS, autocommit=False)
cur = cn.cursor()

print('=' * 74)
print(' 자재재고 유령 버킷 정리  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print('=' * 74)

# ── 1. 라이브가 정말 Z99990 단일인지 먼저 확인(전제 검증) ───────────
cur.execute("""SELECT ISNULL(RTRIM(CUST_CODE),'(NULL)'), COUNT(*)
                 FROM PARTNER_ERP.dbo.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                GROUP BY ISNULL(RTRIM(CUST_CODE),'(NULL)') ORDER BY COUNT(*) DESC""")
live = cur.fetchall()
print('\n① 라이브 CUST_CODE 분포 (전제: Z99990 단일이어야 한다)')
for r in live:
    print(f'    {r[0]:10s} {r[1]:>8,}행')
if len(live) != 1 or str(live[0][0]).strip() != 'Z99990':
    print('\n★중단 — 라이브가 Z99990 단일이 아니다. 전제가 깨졌으므로 정리하지 않는다.')
    cn.close(); sys.exit(1)

# ── 2. 대상 = CUST_CODE ≠ Z99990 인 행 (근거키로 한 건씩) ──────────
cur.execute("""SELECT RTRIM(MAT_CODE), ISNULL(RTRIM(CUST_CODE),''),
                      ISNULL(RTRIM(GAGONG_PROC_CODE),''), CAST(ISNULL(STOCK_QTY,0) AS float),
                      ISNULL(RTRIM(UPDATE_WINDOW),''), CONVERT(varchar(19), UPDATE_DATETIME, 120)
                 FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                WHERE ISNULL(RTRIM(CUST_CODE),'') <> 'Z99990'
                ORDER BY MAT_CODE""")
targets = cur.fetchall()
print(f'\n② 유령 버킷 대상 {len(targets)}행')
if not targets:
    print('    정리할 것이 없다.')
    cn.close(); sys.exit(0)
for r in targets:
    print(f'    {r[0]:20s} cust={r[1]:8s} wh={r[2]:8s} qty={r[3]:>10,.0f}  {r[4]} {r[5]}')

# ── 3. 각 대상의 정상 버킷(Z99990) 현황 ────────────────────────────
print('\n③ 합산될 정상 버킷(Z99990) 현황')
for r in targets:
    cur.execute("""SELECT CAST(ISNULL(STOCK_QTY,0) AS float) FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=? AND ISNULL(RTRIM(CUST_CODE),'')='Z99990'
                      AND ISNULL(RTRIM(GAGONG_PROC_CODE),'')=?""", r[0], r[2])
    z = cur.fetchone()
    cu = float(z[0]) if z else None
    if cu is None:
        print(f'    {r[0]:20s} wh={r[2]:8s}  정상버킷 없음 → 유령행을 Z99990 으로 **개명**한다')
    else:
        print(f'    {r[0]:20s} wh={r[2]:8s}  {cu:>10,.0f} + ({r[3]:,.0f}) = {cu + r[3]:>10,.0f}')

if not ARG.apply:
    print('\n※ DRY-RUN 입니다. 실제로 정리하려면 --apply 를 붙이세요.')
    cn.close(); sys.exit(0)

# ── 4. 백업 후 정리 (근거키 스코프 · 수량 보존) ────────────────────
print(f'\n④ 백업 → {BK}')
cur.execute(f"""SELECT * INTO {BK} FROM nx.PU_T_MAT_STOCK_WH
                 WHERE ISNULL(RTRIM(CUST_CODE),'') <> 'Z99990'""")
print(f'    {cur.rowcount}행 백업')

moved = renamed = 0
for r in targets:
    mat, cc, gp, qty = r[0], r[1], r[2], float(r[3])
    cur.execute("""SELECT COUNT(*) FROM nx.PU_T_MAT_STOCK_WH
                    WHERE RTRIM(MAT_CODE)=? AND ISNULL(RTRIM(CUST_CODE),'')='Z99990'
                      AND ISNULL(RTRIM(GAGONG_PROC_CODE),'')=?""", mat, gp)
    has_z = int(cur.fetchone()[0] or 0) > 0
    if has_z:
        # 정상 버킷에 합산 후 유령행 제거 — 수량을 잃지 않는다
        cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                          UPDATE_USER_ID='web', UPDATE_DATETIME=GETDATE(),
                          UPDATE_WINDOW='ghostfix'
                        WHERE RTRIM(MAT_CODE)=? AND ISNULL(RTRIM(CUST_CODE),'')='Z99990'
                          AND ISNULL(RTRIM(GAGONG_PROC_CODE),'')=?""", qty, mat, gp)
        cur.execute("""DELETE FROM nx.PU_T_MAT_STOCK_WH
                        WHERE RTRIM(MAT_CODE)=? AND ISNULL(RTRIM(CUST_CODE),'')=?
                          AND ISNULL(RTRIM(GAGONG_PROC_CODE),'')=?""", mat, cc, gp)
        moved += 1
    else:
        # 정상 버킷이 없으면 개명(수량 이동 없음)
        cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET CUST_CODE='Z99990',
                          UPDATE_USER_ID='web', UPDATE_DATETIME=GETDATE(),
                          UPDATE_WINDOW='ghostfix'
                        WHERE RTRIM(MAT_CODE)=? AND ISNULL(RTRIM(CUST_CODE),'')=?
                          AND ISNULL(RTRIM(GAGONG_PROC_CODE),'')=?""", mat, cc, gp)
        renamed += 1

cn.commit()
print(f'    합산·제거 {moved}건 · 개명 {renamed}건')

# ── 5. 검증 ────────────────────────────────────────────────────────
cur.execute("""SELECT COUNT(*) FROM nx.PU_T_MAT_STOCK_WH
                WHERE ISNULL(RTRIM(CUST_CODE),'') <> 'Z99990'""")
left = int(cur.fetchone()[0] or 0)
cur.execute("""SELECT COUNT(*) FROM (
                 SELECT RTRIM(MAT_CODE) m, ISNULL(RTRIM(GAGONG_PROC_CODE),'') g
                   FROM nx.PU_T_MAT_STOCK_WH
                  GROUP BY RTRIM(MAT_CODE), ISNULL(RTRIM(GAGONG_PROC_CODE),'')
                 HAVING COUNT(*) > 1) t""")
dup = int(cur.fetchone()[0] or 0)
print(f'\n⑤ 검증 — 잔여 비-Z99990 {left}행 · (자재,창고) 중복 {dup}건')
print('   ' + ('✅ 정리 완료' if left == 0 and dup == 0 else '★아직 남았다 — 확인 필요'))
print(f'\n   되돌리려면: {BK} 참조')
cn.close()
