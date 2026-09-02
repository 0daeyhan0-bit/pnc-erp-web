# -*- coding: utf-8 -*-
"""세트제외 플래그 동기화 — nx.bom_line.set_except ← 라이브 PR_M_ITEM_BOM.SET_EXCEPT_FLAG
   (2026-09-02 신설)

왜 필요한가
  `SET_EXCEPT_FLAG` = **세트입고 시 그 자재를 세트 구성에서 뺀다**(공용품 등).
  레거시에서 이 플래그를 켜고 끄면 클린 BOM 은 따라가지 않아 웹만 옛 상태로 남는다.
  그러면 거래명세서 자도번 전개·세트입고 파생이 레거시와 달라진다.

  실측 2026-09-02 : 불일치 30행 (라이브에서 켬 28 · 끔 2)

무엇을 바꾸나 — **플래그 한 컬럼만.** BOM 링크 자체는 건드리지 않는다.
  ★링크 추가/삭제가 필요하면 `sync_clean_item_bom_delta.py --item <상위품목>` 을 쓴다.

★안전 원칙
  · 라이브는 **읽기만** 한다(CLAUDE.md §1-1). 쓰기는 nx 뿐이다.
  · `--apply` 없이는 **조회만**(기본 dry-run).
  · 양쪽에 **다 있는 링크**만 대상. 한쪽에만 있는 링크는 손대지 않는다
    (그건 링크 동기화 문제라 위 델타 스크립트 몫이다).
  · 적용 전 **백업 테이블**을 만든다(되돌릴 수 있게).

사용
    python _schema/sync_set_except_flag.py            # 조회만(기본)
    python _schema/sync_set_except_flag.py --apply    # 실제 반영
"""
import sys, os, io, argparse, datetime as _dt

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--apply', action='store_true', help='실제 반영(없으면 조회만)')
AP.add_argument('--top', type=int, default=40, help='상세 출력 건수')
ARG = AP.parse_args()

import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
cn = pyodbc.connect(CS, autocommit=False)
cur = cn.cursor()

print('=' * 76)
print(' 세트제외 플래그 동기화  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print('=' * 76)

# 양쪽 다 있는 링크 중 플래그가 다른 것
DIFF_FROM = """
  FROM nx.bom_header h WITH(NOLOCK)
  JOIN nx.bom_line c ON c.bom_id = h.bom_id
  JOIN PARTNER_ERP.dbo.PR_M_ITEM_BOM l WITH(NOLOCK)
    ON RTRIM(l.ITEM_CODE) = RTRIM(h.item_code)
   AND RTRIM(l.MAT_CODE)  = RTRIM(c.child_item)
 WHERE CASE WHEN ISNULL(c.set_except,0)=1 THEN 1 ELSE 0 END
    <> CASE WHEN RTRIM(ISNULL(l.SET_EXCEPT_FLAG,''))='1' THEN 1 ELSE 0 END"""

cur.execute('SELECT COUNT(*)' + DIFF_FROM)
n = int(cur.fetchone()[0] or 0)

cur.execute("""SELECT SUM(CASE WHEN RTRIM(ISNULL(l.SET_EXCEPT_FLAG,''))='1' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN RTRIM(ISNULL(l.SET_EXCEPT_FLAG,''))<>'1' THEN 1 ELSE 0 END)"""
            + DIFF_FROM)
r = cur.fetchone()
on_, off_ = int(r[0] or 0), int(r[1] or 0)

print(f'\n① 불일치 {n:,}행   (라이브에서 켬 {on_:,} · 끔 {off_:,})')

if n == 0:
    print('\n   ✅ 이미 동기 상태입니다.')
    cn.close()
    sys.exit(0)

print(f'\n② 상세 (상위 · 자재 · 클린 → 라이브)')
cur.execute(f"""SELECT TOP {ARG.top} RTRIM(h.item_code), RTRIM(c.child_item),
       CASE WHEN ISNULL(c.set_except,0)=1 THEN '1' ELSE '0' END,
       CASE WHEN RTRIM(ISNULL(l.SET_EXCEPT_FLAG,''))='1' THEN '1' ELSE '0' END"""
            + DIFF_FROM + ' ORDER BY RTRIM(h.item_code), RTRIM(c.child_item)')
for x in cur.fetchall():
    arrow = '켬' if x[3] == '1' else '끔'
    print(f'   {str(x[0]).strip():<24}{str(x[1]).strip():<24} {x[2]} → {x[3]}  ({arrow})')

# 영향범위
cur.execute("""SELECT COUNT(DISTINCT RTRIM(h.item_code))"""
            + DIFF_FROM +
            """ AND EXISTS(SELECT 1 FROM nx.plan_part_mat m WITH(NOLOCK)
                            WHERE RTRIM(m.assy_item_code)=RTRIM(h.item_code))""")
print(f'\n③ 영향범위 — 자재소요에 등장하는 상위품목 {int(cur.fetchone()[0] or 0):,}종')

if not ARG.apply:
    print('\n※ DRY-RUN 입니다. 실제로 반영하려면 --apply 를 붙이세요.')
    cn.close()
    sys.exit(0)

# ── 백업 ───────────────────────────────────────────────────────────
bk = 'bk_bomline_setexc_' + _dt.datetime.now().strftime('%y%m%d_%H%M')
#    ★nx.bom_line 의 키는 (bom_id, seq) 다 — bom_line_id 같은 대리키는 없다.
cur.execute(f"""SELECT c.bom_id, c.seq, RTRIM(h.item_code) item_code,
                       c.child_item, c.set_except
                  INTO nx.{bk}
                  FROM nx.bom_line c
                  JOIN nx.bom_header h ON h.bom_id=c.bom_id
                  JOIN PARTNER_ERP.dbo.PR_M_ITEM_BOM l WITH(NOLOCK)
                    ON RTRIM(l.ITEM_CODE)=RTRIM(h.item_code)
                   AND RTRIM(l.MAT_CODE)=RTRIM(c.child_item)
                 WHERE CASE WHEN ISNULL(c.set_except,0)=1 THEN 1 ELSE 0 END
                    <> CASE WHEN RTRIM(ISNULL(l.SET_EXCEPT_FLAG,''))='1' THEN 1 ELSE 0 END""")
print(f'\n④ 백업 — nx.{bk} ({cur.rowcount:,}행)')

# ── 반영 ───────────────────────────────────────────────────────────
cur.execute("""UPDATE c
                  SET c.set_except = CASE WHEN RTRIM(ISNULL(l.SET_EXCEPT_FLAG,''))='1'
                                          THEN 1 ELSE 0 END
                  FROM nx.bom_line c
                  JOIN nx.bom_header h ON h.bom_id=c.bom_id
                  JOIN PARTNER_ERP.dbo.PR_M_ITEM_BOM l WITH(NOLOCK)
                    ON RTRIM(l.ITEM_CODE)=RTRIM(h.item_code)
                   AND RTRIM(l.MAT_CODE)=RTRIM(c.child_item)
                 WHERE CASE WHEN ISNULL(c.set_except,0)=1 THEN 1 ELSE 0 END
                    <> CASE WHEN RTRIM(ISNULL(l.SET_EXCEPT_FLAG,''))='1' THEN 1 ELSE 0 END""")
print(f'⑤ 반영 — {cur.rowcount:,}행 갱신')
cn.commit()

# ── 검증 ───────────────────────────────────────────────────────────
cur.execute('SELECT COUNT(*)' + DIFF_FROM)
left = int(cur.fetchone()[0] or 0)
print(f'\n⑥ 검증 — 잔여 불일치 {left}행')
print('   ' + ('✅ 동기화 완료' if left == 0 else '★아직 남았다 — 확인 필요'))
print(f'   되돌리려면: nx.{bk} 참조')
print('   ⚠ 세트입고·거래명세서 자도번 전개에 반영된다(계획 재편성은 불필요).')
cn.close()
