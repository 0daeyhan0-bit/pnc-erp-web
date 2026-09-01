# -*- coding: utf-8 -*-
"""웹 BOM에만 있는 잘못된 링크 삭제 — ADM74930507 → ADM74930507-STS (2026-09-01)

무엇을 고치나
  웹 `nx.bom_line` 에 레거시·화면에는 없는 링크가 하나 더 있어서
  전개 레벨이 어긋났다.

    ADM74930507-STS 의 상위
      레거시 PR_M_ITEM_BOM   AJR76462726                 (1건)  ← 정답
      웹    v_pr_bom         AJR76462726 + ADM74930507   (2건)  ★후자가 잘못

  편성이 최단경로를 잡아 웹은 lv1(ADM74930507 직하), 레거시는 lv2(AJR76462726 아래)로
  달았다. **수량은 13으로 동일**하므로 발주에는 영향이 없었으나, 파트별계획의
  BOM 레벨이 달라 대사에서 계속 차이로 잡혔다(WO1064179SVC · WO1082876SVC 2제번).

★대상 선정 — 근거키 스코프 (CLAUDE.md §1-3)
  다음 **세 조건을 모두** 만족하는 링크만 지운다:
    ① 웹 bom_line 에 있고 레거시 PR_M_ITEM_BOM 에는 없다
    ② `except_flag=0` — 전개에 실제로 쓰인다
    ③ **현재 편성 결과(plan_part_dtl)에 실제로 나타났다**  ← 이 조건이 핵심

  ③ 이 없으면 대상이 50건으로 불어난다(실측). 그 49건은
    AJR30133610(39) · AJR73364009(9) · AJR30167201(1) 로,
    **레거시 BOM 에 아예 없는 도번**이고 계획·편성 어디에도 안 나타난다
    (plan_part_dtl·plan_part_mat·계획원본 전부 0행). 안 쓰는 BOM 을 건드릴 이유가 없다.
  ⟹ 실제 대상은 ADM74930507 → ADM74930507-STS **1건**.

★안전
  · 삭제 전 백업 테이블에 원본을 남긴다.
  · `--apply` 없이는 조회만 한다(기본 dry-run).
  · 라이브는 읽기만. 쓰기는 nx 뿐.

사용
    python _schema/fix_bom_extra_link.py            # 조회만
    python _schema/fix_bom_extra_link.py --apply    # 실제 삭제
"""
import sys, os, io, argparse, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(_HERE, '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--apply', action='store_true', help='실제 삭제(없으면 조회만)')
ARG = AP.parse_args()

import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
BK = 'nx.bk_bom_extra_' + datetime.datetime.now().strftime('%y%m%d_%H%M')

cn = pyodbc.connect(CS, autocommit=False)
cur = cn.cursor()

print('=' * 74)
print(' 웹 BOM 잉여 링크 삭제  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print('=' * 74)

# ── 대상: 웹에만 있고 · 전개제외가 아니고 · 실제 편성에 나타난 것 ──
TGT = """
  SELECT h.bom_id AS bom_id, l.seq, RTRIM(h.item_code) AS parent, RTRIM(l.child_item) AS child
    FROM nx.bom_line l
    JOIN nx.bom_header h ON h.bom_id = l.bom_id
   WHERE ISNULL(l.except_flag,0) = 0
     AND NOT EXISTS(SELECT 1 FROM nx.PR_M_ITEM_BOM m
                     WHERE RTRIM(m.ITEM_CODE) = RTRIM(h.item_code)
                       AND RTRIM(m.MAT_CODE)  = RTRIM(l.child_item))
     -- ★③ 현재 편성에 실제로 나타난 링크만. 이 조건이 없으면 안 쓰는 BOM 49건까지 걸린다.
     AND EXISTS(SELECT 1 FROM nx.plan_part_dtl p
                 WHERE RTRIM(p.upper_item_code) = RTRIM(h.item_code)
                   AND RTRIM(p.item_code)       = RTRIM(l.child_item))
"""

print('\n① 대상 — 웹에만 있고 전개에 쓰이는 링크')
cur.execute(f"SELECT parent, child, bom_id, seq FROM ({TGT}) t ORDER BY parent, child")
rows = cur.fetchall()
print(f'   {len(rows)}건')
for r in rows:
    print(f'   {r[0]:20s} → {r[1]:22s}  (bom_id={r[2]} seq={r[3]})')
if not rows:
    print('   삭제할 것이 없습니다.')
    cn.close(); sys.exit(0)

print('\n② 레거시에서 그 자재의 진짜 상위 (참고)')
for r in rows:
    cur.execute("""SELECT RTRIM(ITEM_CODE) FROM nx.PR_M_ITEM_BOM WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=?""", r[1])
    ups = [x[0] for x in cur.fetchall()]
    print(f'   {r[1]:22s} 레거시 상위 = {ups if ups else "(없음)"}')

print('\n③ 지우면 소요량이 바뀌나 (같은 자재가 다른 경로로 여전히 전개되는지)')
for r in rows:
    cur.execute("""SELECT COUNT(*) FROM nx.v_pr_bom WITH(NOLOCK)
                    WHERE RTRIM(mat_code)=? AND ISNULL(RTRIM(EXCEPT_FLAG),'0')='0'""", r[1])
    n = int(cur.fetchone()[0] or 0)
    print(f'   {r[1]:22s} 전개 가능한 상위 {n}건'
          + ('  → 지워도 다른 경로로 전개된다' if n > 1 else '  ★유일 경로 — 지우면 전개가 끊긴다'))

if not ARG.apply:
    print('\n※ DRY-RUN 입니다. 실제로 지우려면 --apply 를 붙이세요.')
    cn.close(); sys.exit(0)

print(f'\n④ 백업 → {BK}')
cur.execute(f"""SELECT l.* INTO {BK}
                  FROM nx.bom_line l
                 WHERE EXISTS(SELECT 1 FROM ({TGT}) t
                               WHERE t.bom_id=l.bom_id AND t.seq=l.seq)""")
print(f'    {cur.rowcount}행 백업')

cur.execute(f"""DELETE l FROM nx.bom_line l
                 WHERE EXISTS(SELECT 1 FROM ({TGT}) t
                               WHERE t.bom_id=l.bom_id AND t.seq=l.seq)""")
n = cur.rowcount
cn.commit()
print(f'    삭제 {n}행')

print('\n⑤ 검증')
cur.execute(f"SELECT COUNT(*) FROM ({TGT}) t")
print('   잔여 대상:', cur.fetchone()[0], '건')
cur.execute("""SELECT COUNT(*) FROM nx.v_pr_bom WITH(NOLOCK)
                WHERE RTRIM(mat_code)='ADM74930507-STS'""")
print('   ADM74930507-STS 상위:', cur.fetchone()[0], '건 (레거시와 같으면 1)')
print(f'\n   되돌리려면 {BK} 에서 INSERT')
print('   ⚠ 편성(④ 파트별 → ⑤ 자재소요)을 다시 돌려야 반영됩니다.')
cn.close()
