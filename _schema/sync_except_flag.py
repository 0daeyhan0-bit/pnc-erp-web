# -*- coding: utf-8 -*-
"""BOM 전개제외 플래그 동기화 — nx.bom_line.except_flag ← 라이브 PR_M_ITEM_BOM.EXCEPT_FLAG
   (2026-09-02 신설)

왜 필요한가
  `EXCEPT_FLAG` = **BOM 전개에서 이 링크를 건너뛴다.** 소요엔진이 이 값을 보고
  전개 여부를 정하므로(§1-10), 라이브와 다르면 **자재소요가 통째로 달라진다.**

  실측 2026-09-02 : 불일치 21행 → 자재소요 −16,645(0.6%) 의 주원인.
    예) AJR30073601 : 클린은 `-F&T` 를 실물로 잡고 거기서 멈춤(except 0),
        라이브는 `-F&T` 를 건너뛰고(except 1) `-F&T-1/-2` 를 직접 씀(except 0).
        ⟹ 웹만 하위 8종을 못 뽑았다.

  ★"BOM 링크가 없어서" 가 아니라 **"플래그가 달라서"** 인 경우가 많다.
    링크를 채워 넣기 전에 이 스크립트로 플래그부터 맞춰볼 것
    (실제로 링크 +12 를 넣었지만 전부 except=1 이라 아무 효과가 없었다).

무엇을 바꾸나 — **플래그 한 컬럼만.** 링크 추가/삭제는 sync_clean_item_bom_delta.py 몫.

★안전 원칙
  · 라이브는 **읽기만**(CLAUDE.md §1-1). 쓰기는 nx 뿐.
  · `--apply` 없이는 **조회만**(기본 dry-run).
  · 양쪽에 **다 있는 링크**만 대상. 한쪽에만 있는 링크는 손대지 않는다.
  · 적용 전 **백업 테이블** 생성.
  · ⚠ 반영 후 **편성(④파트별 → ⑤자재소요)을 다시 돌려야** 계획에 반영된다.

사용
    python _schema/sync_except_flag.py            # 조회만(기본)
    python _schema/sync_except_flag.py --apply    # 실제 반영
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
print(' BOM 전개제외 플래그 동기화  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print('=' * 76)

# 양쪽 다 있는 링크 중 플래그가 다른 것
DIFF_FROM = """
  FROM nx.bom_header h WITH(NOLOCK)
  JOIN nx.bom_line c ON c.bom_id = h.bom_id
  JOIN PARTNER_ERP.dbo.PR_M_ITEM_BOM l WITH(NOLOCK)
    ON RTRIM(l.ITEM_CODE) = RTRIM(h.item_code)
   AND RTRIM(l.MAT_CODE)  = RTRIM(c.child_item)
 WHERE CASE WHEN ISNULL(c.except_flag,0)=1 THEN 1 ELSE 0 END
    <> CASE WHEN RTRIM(ISNULL(l.EXCEPT_FLAG,''))='1' THEN 1 ELSE 0 END"""

cur.execute('SELECT COUNT(*)' + DIFF_FROM)
n = int(cur.fetchone()[0] or 0)

cur.execute("""SELECT SUM(CASE WHEN RTRIM(ISNULL(l.EXCEPT_FLAG,''))='1' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN RTRIM(ISNULL(l.EXCEPT_FLAG,''))<>'1' THEN 1 ELSE 0 END)"""
            + DIFF_FROM)
r = cur.fetchone()
on_, off_ = int(r[0] or 0), int(r[1] or 0)

print(f'\n① 불일치 {n:,}행   (라이브에서 제외 {on_:,} · 해제 {off_:,})')

if n == 0:
    print('\n   ✅ 이미 동기 상태입니다.')
    cn.close()
    sys.exit(0)

print(f'\n② 상세 (상위 · 자재 · 클린 → 라이브)')
cur.execute(f"""SELECT TOP {ARG.top} RTRIM(h.item_code), RTRIM(c.child_item),
       CASE WHEN ISNULL(c.except_flag,0)=1 THEN '1' ELSE '0' END,
       CASE WHEN RTRIM(ISNULL(l.EXCEPT_FLAG,''))='1' THEN '1' ELSE '0' END"""
            + DIFF_FROM + ' ORDER BY RTRIM(h.item_code), RTRIM(c.child_item)')
for x in cur.fetchall():
    arrow = '제외' if x[3] == '1' else '해제'
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
bk = 'bk_bomline_exc_' + _dt.datetime.now().strftime('%y%m%d_%H%M')
#    ★nx.bom_line 의 키는 (bom_id, seq) 다 — bom_line_id 같은 대리키는 없다.
cur.execute(f"""SELECT c.bom_id, c.seq, RTRIM(h.item_code) item_code,
                       c.child_item, c.except_flag
                  INTO nx.{bk}
                  FROM nx.bom_line c
                  JOIN nx.bom_header h ON h.bom_id=c.bom_id
                  JOIN PARTNER_ERP.dbo.PR_M_ITEM_BOM l WITH(NOLOCK)
                    ON RTRIM(l.ITEM_CODE)=RTRIM(h.item_code)
                   AND RTRIM(l.MAT_CODE)=RTRIM(c.child_item)
                 WHERE CASE WHEN ISNULL(c.except_flag,0)=1 THEN 1 ELSE 0 END
                    <> CASE WHEN RTRIM(ISNULL(l.EXCEPT_FLAG,''))='1' THEN 1 ELSE 0 END""")
print(f'\n④ 백업 — nx.{bk} ({cur.rowcount:,}행)')

# ── 반영 ───────────────────────────────────────────────────────────
cur.execute("""UPDATE c
                  SET c.except_flag = CASE WHEN RTRIM(ISNULL(l.EXCEPT_FLAG,''))='1'
                                          THEN 1 ELSE 0 END
                  FROM nx.bom_line c
                  JOIN nx.bom_header h ON h.bom_id=c.bom_id
                  JOIN PARTNER_ERP.dbo.PR_M_ITEM_BOM l WITH(NOLOCK)
                    ON RTRIM(l.ITEM_CODE)=RTRIM(h.item_code)
                   AND RTRIM(l.MAT_CODE)=RTRIM(c.child_item)
                 WHERE CASE WHEN ISNULL(c.except_flag,0)=1 THEN 1 ELSE 0 END
                    <> CASE WHEN RTRIM(ISNULL(l.EXCEPT_FLAG,''))='1' THEN 1 ELSE 0 END""")
print(f'⑤ 반영 — {cur.rowcount:,}행 갱신')
cn.commit()

# ── 검증 ───────────────────────────────────────────────────────────
cur.execute('SELECT COUNT(*)' + DIFF_FROM)
left = int(cur.fetchone()[0] or 0)
print(f'\n⑥ 검증 — 잔여 불일치 {left}행')
print('   ' + ('✅ 동기화 완료' if left == 0 else '★아직 남았다 — 확인 필요'))
print(f'   되돌리려면: nx.{bk} 참조')
print('   ⚠ ★편성(④파트별 → ⑤자재소요)을 다시 돌려야 계획에 반영된다.')
cn.close()
