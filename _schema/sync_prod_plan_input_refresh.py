# -*- coding: utf-8 -*-
"""생산계획추가입력 동기화 — nx.prod_plan_input ← 라이브 PR_T_PLAN_INPUT (2026-09-01 신설)

왜 필요한가
  「생산계획추가입력」화면은 웹 정본 `nx.prod_plan_input` 을 쓰고,
  편성(STEP5-AS)은 라이브 `PR_T_PLAN_INPUT` 을 직독한다. 두 소스가 갈려 있어
  **레거시에서 추가계획 일자가 바뀌면 웹만 옛 날짜에 멈춘다.**

    실측 2026-09-01 : 웹 260831 → 라이브 260901  **633건**
                      (미러 nx.PR_T_PLAN_INPUT vs 라이브 = 0건 — 미러는 매일 갱신된다.
                       웹만 별도 스크립트라 안 돌아 뒤처졌다)

  이 상태로 계획을 업로드하면 추가계획 633건이 어제 날짜로 잡혀 불일치가 난다.
  **계획 업로드 전에 이 스크립트를 돌린다.**

기존 `sync_prod_plan_input.py` 와의 차이
  그건 **INSERT 전용**(신규분만)이라 이미 있는 행의 값 변경을 못 따라간다.
  여기서는 ①값 갱신(UPDATE) ②신규 추가(INSERT) ③삭제분 정리를 모두 한다.

★안전 원칙
  · 라이브는 **읽기만** 한다(CLAUDE.md §1-1). 쓰기는 nx 뿐이다.
  · `--apply` 없이는 **조회만** 한다(기본 dry-run).
  · 삭제는 라이브에 없는 행에 한해 **근거키(work_order) 스코프**로만(§1-3).
  · 사용자가 웹에서 직접 넣은 행(`src='web'`)은 **건드리지 않는다** —
    레거시에 없다고 지우면 웹 입력분이 날아간다.

사용
    python _schema/sync_prod_plan_input_refresh.py            # 조회만(기본)
    python _schema/sync_prod_plan_input_refresh.py --apply    # 실제 동기화
"""
import sys, os, io, argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(_HERE, '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--apply', action='store_true', help='실제 동기화(없으면 조회만)')
ARG = AP.parse_args()

import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
LIVE = 'PARTNER_ERP.dbo.PR_T_PLAN_INPUT'

cn = pyodbc.connect(CS, autocommit=False)
cur = cn.cursor()

print('=' * 74)
print(' 생산계획추가입력 동기화  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print('=' * 74)


def n1(q, *a):
    cur.execute(q, *a)
    r = cur.fetchone()
    return int(r[0] or 0) if r else 0


# ── 현황 ───────────────────────────────────────────────────────────
web = n1('SELECT COUNT(*) FROM nx.prod_plan_input WITH(NOLOCK)')
live = n1(f'SELECT COUNT(*) FROM {LIVE} WITH(NOLOCK)')
print(f'\n① 행수   웹 {web:,}  /  라이브 {live:,}')

# 값이 다른 행 (제번 기준 조인)
DIFF = f"""FROM nx.prod_plan_input w
           JOIN {LIVE} l WITH(NOLOCK) ON RTRIM(l.WORK_ORDER)=RTRIM(w.work_order)
          WHERE ISNULL(RTRIM(w.plan_ymd),'')  <> ISNULL(RTRIM(l.PLAN_YMD),'')
             OR ISNULL(RTRIM(w.item_code),'') <> ISNULL(RTRIM(l.ITEM_CODE),'')
             OR ISNULL(CAST(w.plan_qty AS float),0) <> ISNULL(CAST(l.PLAN_QTY AS float),0)
             OR ISNULL(RTRIM(w.line_no),'')   <> ISNULL(RTRIM(l.LINE_NO),'')
             OR ISNULL(RTRIM(w.output_hm),'') <> ISNULL(RTRIM(l.OUTPUT_HM),'')
             OR ISNULL(RTRIM(w.work_code),'') <> ISNULL(RTRIM(l.WORK_CODE),'')
             OR ISNULL(RTRIM(w.prod_tag),'')  <> ISNULL(RTRIM(l.PROD_TAG),'')"""
n_upd = n1('SELECT COUNT(*) ' + DIFF)

n_ins = n1(f"""SELECT COUNT(*) FROM {LIVE} l WITH(NOLOCK)
                WHERE NOT EXISTS(SELECT 1 FROM nx.prod_plan_input w
                                  WHERE RTRIM(w.work_order)=RTRIM(l.WORK_ORDER))""")
# ★웹 입력분(src='web')은 삭제 대상에서 뺀다 — 레거시에 없는 게 정상이다
n_del = n1(f"""SELECT COUNT(*) FROM nx.prod_plan_input w
                WHERE ISNULL(RTRIM(w.src),'') <> 'web'
                  AND NOT EXISTS(SELECT 1 FROM {LIVE} l WITH(NOLOCK)
                                  WHERE RTRIM(l.WORK_ORDER)=RTRIM(w.work_order))""")
n_web_only = n1("""SELECT COUNT(*) FROM nx.prod_plan_input WITH(NOLOCK)
                    WHERE ISNULL(RTRIM(src),'')='web'""")

print(f'\n② 할 일   값갱신 {n_upd:,}행 · 신규 {n_ins:,}행 · 삭제 {n_del:,}행'
      f'   (웹 직접입력 {n_web_only:,}행은 보존)')

if n_upd:
    print('\n③ 값이 달라지는 내용 — 패턴별')
    cur.execute("""SELECT TOP 12 RTRIM(w.plan_ymd), RTRIM(l.PLAN_YMD), COUNT(*) """ + DIFF +
                """ GROUP BY RTRIM(w.plan_ymd), RTRIM(l.PLAN_YMD) ORDER BY COUNT(*) DESC""")
    for r in cur.fetchall():
        mark = '' if r[0] == r[1] else '   ← 일자 변경'
        print(f'    웹 {r[0]} → 라이브 {r[1]}   {r[2]:>6,}건{mark}')

if not ARG.apply:
    print('\n※ DRY-RUN 입니다. 실제로 동기화하려면 --apply 를 붙이세요.')
    cn.close()
    sys.exit(0)

# ── 실행 ───────────────────────────────────────────────────────────
print('\n④ 동기화 실행')

cur.execute(f"""UPDATE w SET w.plan_ymd = RTRIM(l.PLAN_YMD),
                             w.line_no   = RTRIM(l.LINE_NO),
                             w.item_code = RTRIM(l.ITEM_CODE),
                             w.output_hm = RTRIM(l.OUTPUT_HM),
                             w.plan_qty  = l.PLAN_QTY,
                             w.work_code = RTRIM(l.WORK_CODE),
                             w.prod_tag  = RTRIM(l.PROD_TAG),
                             w.remarks   = LTRIM(RTRIM(l.REMARKS)),
                             w.src='sync', w.upd_user='sync', w.upd_dt=GETDATE()
                  FROM nx.prod_plan_input w
                  JOIN {LIVE} l WITH(NOLOCK) ON RTRIM(l.WORK_ORDER)=RTRIM(w.work_order)
                 WHERE ISNULL(RTRIM(w.plan_ymd),'')  <> ISNULL(RTRIM(l.PLAN_YMD),'')
                    OR ISNULL(RTRIM(w.item_code),'') <> ISNULL(RTRIM(l.ITEM_CODE),'')
                    OR ISNULL(CAST(w.plan_qty AS float),0) <> ISNULL(CAST(l.PLAN_QTY AS float),0)
                    OR ISNULL(RTRIM(w.line_no),'')   <> ISNULL(RTRIM(l.LINE_NO),'')
                    OR ISNULL(RTRIM(w.output_hm),'') <> ISNULL(RTRIM(l.OUTPUT_HM),'')
                    OR ISNULL(RTRIM(w.work_code),'') <> ISNULL(RTRIM(l.WORK_CODE),'')
                    OR ISNULL(RTRIM(w.prod_tag),'')  <> ISNULL(RTRIM(l.PROD_TAG),'')""")
print(f'    값갱신 {cur.rowcount:,}행')

cur.execute(f"""INSERT INTO nx.prod_plan_input
                  (plan_ymd,line_no,item_code,output_hm,plan_qty,work_order,work_code,
                   prod_tag,remarks,src,upd_user,upd_dt)
                SELECT RTRIM(l.PLAN_YMD), RTRIM(l.LINE_NO), RTRIM(l.ITEM_CODE), RTRIM(l.OUTPUT_HM),
                       l.PLAN_QTY, RTRIM(l.WORK_ORDER), RTRIM(l.WORK_CODE), RTRIM(l.PROD_TAG),
                       LTRIM(RTRIM(l.REMARKS)), 'sync', 'sync', GETDATE()
                  FROM {LIVE} l WITH(NOLOCK)
                 WHERE NOT EXISTS(SELECT 1 FROM nx.prod_plan_input w
                                   WHERE RTRIM(w.work_order)=RTRIM(l.WORK_ORDER))""")
print(f'    신규   {cur.rowcount:,}행')

cur.execute(f"""DELETE w FROM nx.prod_plan_input w
                 WHERE ISNULL(RTRIM(w.src),'') <> 'web'
                   AND NOT EXISTS(SELECT 1 FROM {LIVE} l WITH(NOLOCK)
                                   WHERE RTRIM(l.WORK_ORDER)=RTRIM(w.work_order))""")
print(f'    삭제   {cur.rowcount:,}행  (웹 직접입력분 제외)')

cn.commit()

# ── 검증 ───────────────────────────────────────────────────────────
left = n1('SELECT COUNT(*) ' + DIFF)
web2 = n1('SELECT COUNT(*) FROM nx.prod_plan_input WITH(NOLOCK)')
print(f'\n⑤ 검증 — 잔여 불일치 {left}행 · 웹 {web2:,} / 라이브 {live:,}')
print('   ' + ('✅ 동기화 완료 — 계획 업로드해도 됩니다'
                if left == 0 else '★아직 남았다 — 확인 필요'))
cn.close()
