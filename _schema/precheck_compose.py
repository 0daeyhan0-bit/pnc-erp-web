# -*- coding: utf-8 -*-
"""편성 전 전수 사전점검 — 편성을 돌리기 **전에** 걸릴 것을 모두 찾아낸다 (2026-09-03 신설)

★★★이 스크립트의 성격 = **레거시 대사(분석) 전용. 컷오버 후에는 필요 없다** (대표 확정 2026-09-03)
  레거시가 BOM 을 계속 바꾸므로 웹이 실시간으로 따라갈 수는 없다 — 그건 당연하고, 목표도 아니다.
  이 점검의 목적은 단 하나: **"레거시와 같은 입력을 주면 같은 계획이 나오는가"** 를 검증하기 위해
  대사 직전에 두 쪽 마스터를 같은 상태로 맞추는 것이다.
  ⟹ 컷오버 후에는 **레거시가 은퇴해 맞출 대상 자체가 없다.** BOM·품목·공정의 등록/수정/삭제는
     **웹에서 직접** 한다(§1-9-1). 그러면 여기서 잡는 4종 결함은 구조적으로 발생하지 않는다.
     입력 경로가 웹 하나뿐이기 때문이다.
  ⟹ 그러므로 이 스크립트를 "운영 도구"로 키우지 말 것. sync 를 정교하게 만드는 방향은 **틀렸다**.
     올바른 방향 = 웹의 BOM/품목/공정 **등록·수정·삭제 기능을 완성**하는 것.

왜 필요한가
  2026-09-02~03 계획 대사에서 같은 패턴을 **네 번** 반복했다:
    ①BOM 링크 누락 → 편성 → 대사 → ②품목속성 빈값 발견 → 편성 → 대사
    → ③공정마스터 미러 낡음 발견 → 편성 → 대사 → ④except_flag 불일치 발견 → 편성
  매번 **편성을 돌린 뒤에야** 다음 결함이 드러나 왕복이 4회 발생했다.
  결함 종류는 4가지뿐인데 점검 도구가 흩어져 있어 한 번에 볼 수가 없었다.

이 스크립트가 하는 일
  편성이 실제로 조인하는 경로를 그대로 따라가며, **전개에서 탈락할 품목을 미리 전수 검출**한다.
  라이브를 기준으로 대조하므로 편성을 돌리지 않고도 결과를 예측할 수 있다.

  [1] BOM 링크      라이브 PR_M_ITEM_BOM ↔ nx.bom_line     (계획기간 사용 부모 한정)
  [2] except_flag   라이브 EXCEPT_FLAG   ↔ nx.bom_line     (이중계상의 원인)
  [3] 품목마스터    nx.item 존재 + make_type 등 필수속성 빈값
  [4] 공정마스터    라이브 PR_M_ITEM_PROC_GAGONG ↔ nx.PR_M_ITEM_PROC_GAGONG
  [5] 유령 ASSY     nx.item 에만 있고 라이브에 없는 것이 계획에 유입되는지

  각 항목마다 **고칠 명령**을 함께 출력한다.

라이브는 읽기만 한다(§1-1). 이 스크립트는 아무것도 쓰지 않는다(순수 점검).

사용
    python _schema/precheck_compose.py                    # 계획기간 자동(nx.plan_dtl)
    python _schema/precheck_compose.py --from 260903 --to 261002
"""
import sys, os, io, argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(_HERE, '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--from', dest='lo', default='')
AP.add_argument('--to', dest='hi', default='')
AP.add_argument('--full', action='store_true', help='계획기간 무관 전수(느림)')
ARG = AP.parse_args()

from common import _conn
cn = _conn(); cur = cn.cursor()
NX = 'PARTNER_ERP_TEST3.nx.'
LB = 'PARTNER_ERP.dbo.PR_M_ITEM_BOM'

LO, HI = ARG.lo, ARG.hi
if not LO or not HI:
    cur.execute(f"SELECT MIN(PLAN_YMD), MAX(PLAN_YMD) FROM {NX}plan_dtl WHERE PLAN_YMD>'250101'")
    r = cur.fetchone()
    LO, HI = (LO or (r[0] or '260101')), (HI or (r[1] or '261231'))

print('=' * 78)
print(f' 편성 전 사전점검   계획기간 {LO} ~ {HI}')
print('=' * 78)
print(' 편성을 돌리기 전에 걸릴 것을 미리 찾는다. 아무것도 쓰지 않는다(순수 점검).')

FIX = []   # (제목, 명령)
TOT = 0

# 계획기간에 실제로 쓰이는 부모(ASSY·중간노드) 스코프
SCOPE = f"""
  used AS (SELECT DISTINCT RTRIM(ITEM_CODE) p FROM PARTNER_ERP.dbo.PR_T_PLAN_PART_DTL WITH(NOLOCK)
            WHERE PLAN_YMD BETWEEN '{LO}' AND '{HI}'
           UNION SELECT DISTINCT RTRIM(item_code) FROM {NX}plan_part_dtl WITH(NOLOCK)
            WHERE plan_ymd BETWEEN '{LO}' AND '{HI}')"""
if ARG.full:
    SCOPE = f"  used AS (SELECT DISTINCT RTRIM(ITEM_CODE) p FROM {LB} WITH(NOLOCK))"

# ── [1] BOM 링크 ───────────────────────────────────────────────────────
print('\n[1] BOM 링크 — 라이브에 있는데 nx.bom_line 에 없는 것 (전개가 끊긴다)')
cur.execute(f"""
WITH {SCOPE},
 lv AS (SELECT RTRIM(b.ITEM_CODE) p, RTRIM(b.MAT_CODE) c FROM {LB} b WITH(NOLOCK)
          JOIN used u ON u.p=RTRIM(b.ITEM_CODE)
         WHERE ISNULL(b.TO_APPLY_YMD,'991231')>='{LO}'
         GROUP BY RTRIM(b.ITEM_CODE), RTRIM(b.MAT_CODE)),
 wb AS (SELECT RTRIM(h.item_code) p, RTRIM(bl.child_item) c
          FROM {NX}bom_line bl WITH(NOLOCK) JOIN {NX}bom_header h WITH(NOLOCK) ON h.bom_id=bl.bom_id
         GROUP BY RTRIM(h.item_code), RTRIM(bl.child_item))
SELECT lv.p, COUNT(*) c FROM lv LEFT JOIN wb ON wb.p=lv.p AND wb.c=lv.c
 WHERE wb.p IS NULL GROUP BY lv.p ORDER BY COUNT(*) DESC""")
rows = cur.fetchall()
if rows:
    for x in rows[:15]: print(f'      {x[0]:26} 자식 {x[1]:>3}개 누락')
    if len(rows) > 15: print(f'      … 외 {len(rows)-15}개 부모')
    n = sum(x[1] for x in rows); TOT += n
    print(f'   ★ {len(rows)}개 부모 / {n}개 링크 누락')
    items = ' '.join(f'--item {x[0]}' for x in rows[:8])
    FIX.append(('BOM 링크(누락)', f'python _schema/sync_clean_item_bom_delta.py {items}'))
else:
    print('   ✅ 없음')

# ── [1b] BOM 링크 — 반대방향(웹에만 있음) ─────────────────────────────
#   ★이쪽이 **이중계상**을 만든다. 라이브에서 중간노드(F&T·SUB)가 생기면서
#     직결 링크를 뺐는데 웹에 남아 있으면 같은 자재가 두 경로로 잡힌다(실측 2026-09-03: 224건 정확히 2배).
print('\n[1b] BOM 링크 — 웹에만 있고 라이브에 없는 것 (이중계상의 원인)')
cur.execute(f"""
WITH {SCOPE},
 lv AS (SELECT RTRIM(b.ITEM_CODE) p, RTRIM(b.MAT_CODE) c FROM {LB} b WITH(NOLOCK)
         GROUP BY RTRIM(b.ITEM_CODE), RTRIM(b.MAT_CODE)),
 wb AS (SELECT RTRIM(h.item_code) p, RTRIM(bl.child_item) c
          FROM {NX}bom_line bl WITH(NOLOCK) JOIN {NX}bom_header h WITH(NOLOCK) ON h.bom_id=bl.bom_id
          JOIN used u ON u.p=RTRIM(h.item_code)
         GROUP BY RTRIM(h.item_code), RTRIM(bl.child_item))
SELECT wb.p, COUNT(*) c FROM wb LEFT JOIN lv ON lv.p=wb.p AND lv.c=wb.c
 WHERE lv.p IS NULL GROUP BY wb.p ORDER BY COUNT(*) DESC""")
rows = cur.fetchall()
if rows:
    for x in rows[:15]: print(f'      {x[0]:26} 자식 {x[1]:>3}개 잔여')
    if len(rows) > 15: print(f'      … 외 {len(rows)-15}개 부모')
    n = sum(x[1] for x in rows); TOT += n
    print(f'   ★ {len(rows)}개 부모 / {n}개 링크 잔여  (★삭제는 건건이 확인 — 경로 단절 주의)')
    FIX.append(('BOM 링크(잔여)', '동일 스크립트가 --item 스코프 안에서 삭제까지 처리 (경로단절 점검 포함)'))
else:
    print('   ✅ 없음')

# ── [2] except_flag ───────────────────────────────────────────────────
print('\n[2] except_flag — 라이브와 다른 것 (같으면 이중계상/누락이 난다)')
cur.execute(f"""
WITH {SCOPE}
SELECT RTRIM(h.item_code) p, RTRIM(bl.child_item) c,
       RTRIM(ISNULL(CAST(bl.except_flag AS varchar(4)),'0')) w,
       RTRIM(ISNULL(b.EXCEPT_FLAG,'0')) l
  FROM {NX}bom_line bl WITH(NOLOCK) JOIN {NX}bom_header h WITH(NOLOCK) ON h.bom_id=bl.bom_id
  JOIN used u ON u.p=RTRIM(h.item_code)
  JOIN {LB} b WITH(NOLOCK) ON RTRIM(b.ITEM_CODE)=RTRIM(h.item_code)
                          AND RTRIM(b.MAT_CODE)=RTRIM(bl.child_item)
 WHERE RTRIM(ISNULL(CAST(bl.except_flag AS varchar(4)),'0')) <> RTRIM(ISNULL(b.EXCEPT_FLAG,'0'))""")
rows = cur.fetchall()
if rows:
    for x in rows[:15]:
        d = '제외' if x[3] == '1' else '해제'
        print(f'      {x[0]:24} {x[1]:22} {x[2]} → {x[3]} ({d})')
    if len(rows) > 15: print(f'      … 외 {len(rows)-15}행')
    TOT += len(rows)
    print(f'   ★ {len(rows)}행 불일치')
    FIX.append(('except_flag', 'python _schema/sync_except_flag.py --apply'))
else:
    print('   ✅ 없음')

# ── [3] 품목마스터 ────────────────────────────────────────────────────
print('\n[3] 품목마스터 — nx.item 누락 / 필수속성 빈값 (편성 조인에서 탈락한다)')
cur.execute(f"""
WITH {SCOPE},
 need AS (SELECT DISTINCT RTRIM(b.MAT_CODE) it FROM {LB} b WITH(NOLOCK)
            JOIN used u ON u.p=RTRIM(b.ITEM_CODE)
           WHERE ISNULL(b.TO_APPLY_YMD,'991231')>='{LO}'
          UNION SELECT p FROM used)
SELECT n.it, CASE WHEN i.item_code IS NULL THEN 'nx.item 없음' ELSE 'make_type 빈값' END s
  FROM need n LEFT JOIN {NX}item i ON RTRIM(i.item_code)=n.it
 WHERE EXISTS(SELECT 1 FROM PARTNER_ERP.dbo.PR_M_ITEM m WHERE RTRIM(m.ITEM_CODE)=n.it)
   AND (i.item_code IS NULL
        OR ((i.make_type IS NULL OR RTRIM(CAST(i.make_type AS varchar(8)))='')
            AND EXISTS(SELECT 1 FROM PARTNER_ERP.dbo.PR_M_ITEM m
                        WHERE RTRIM(m.ITEM_CODE)=n.it AND RTRIM(ISNULL(m.MAKE_TYPE,''))<>'')))
 ORDER BY n.it""")
rows = cur.fetchall()
if rows:
    for x in rows[:15]: print(f'      {x[0]:26} {x[1]}')
    if len(rows) > 15: print(f'      … 외 {len(rows)-15}개')
    TOT += len(rows)
    print(f'   ★ {len(rows)}개 품목')
    FIX.append(('품목 속성', '(델타 동기화가 등록 → 속성은 라이브 값으로 채움)'))
else:
    print('   ✅ 없음')

# ── [4] 공정마스터 ────────────────────────────────────────────────────
print('\n[4] 공정마스터 — 미러가 라이브보다 낡음 (공정 조인에서 행이 사라진다)')
cur.execute(f"""
SELECT RTRIM(m.ITEM_CODE), COUNT(*) FROM PARTNER_ERP.dbo.PR_M_ITEM_PROC_GAGONG m WITH(NOLOCK)
 WHERE NOT EXISTS(SELECT 1 FROM {NX}PR_M_ITEM_PROC_GAGONG x WHERE RTRIM(x.item_code)=RTRIM(m.ITEM_CODE))
 GROUP BY RTRIM(m.ITEM_CODE)""")
miss = cur.fetchall()
cur.execute(f"""
WITH l AS (SELECT RTRIM(ITEM_CODE) ic, COUNT(*) c FROM PARTNER_ERP.dbo.PR_M_ITEM_PROC_GAGONG WITH(NOLOCK) GROUP BY RTRIM(ITEM_CODE)),
     n AS (SELECT RTRIM(item_code) ic, COUNT(*) c FROM {NX}PR_M_ITEM_PROC_GAGONG WITH(NOLOCK) GROUP BY RTRIM(item_code))
SELECT l.ic, n.c, l.c FROM l JOIN n ON n.ic=l.ic WHERE l.c<>n.c""")
diff = cur.fetchall()
if miss or diff:
    for x in miss[:10]: print(f'      + {x[0]:26} 공정 {x[1]:>3}행 (미러에 없음)')
    for x in diff[:10]: print(f'      ~ {x[0]:26} 미러 {x[1]:>3} → 라이브 {x[2]:>3}')
    TOT += len(miss) + len(diff)
    print(f'   ★ 누락 {len(miss)}품목 · 불일치 {len(diff)}품목')
    FIX.append(('공정마스터', '(공정 미러 델타 동기화 후 r_has_gagong_sync.py --commit)'))
else:
    print('   ✅ 없음')

# ── [5] 유령 ASSY ─────────────────────────────────────────────────────
print('\n[5] 유령 ASSY — nx.item 에만 있고 라이브에 없는 것이 계획에 들어왔나')
cur.execute(f"""
SELECT RTRIM(a.item_code), COUNT(*) FROM (
  SELECT RTRIM(item_code) item_code FROM {NX}plan_part_dtl WITH(NOLOCK) WHERE plan_ymd BETWEEN '{LO}' AND '{HI}'
  UNION ALL
  SELECT RTRIM(assy_item_code) FROM {NX}plan_part_dtl WITH(NOLOCK) WHERE plan_ymd BETWEEN '{LO}' AND '{HI}'
) a
 WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP.dbo.PR_M_ITEM m WHERE RTRIM(m.ITEM_CODE)=a.item_code)
 GROUP BY RTRIM(a.item_code) ORDER BY COUNT(*) DESC""")
rows = cur.fetchall()
if rows:
    for x in rows[:10]: print(f'      {x[0]:26} 계획 {x[1]:>5}행  ← 라이브 미등록')
    TOT += len(rows)
    print(f'   ★ {len(rows)}개 (웹 자체 등록분이면 정상 — src 확인)')
else:
    print('   ✅ 없음')

# ── 결론 ──────────────────────────────────────────────────────────────
print('\n' + '=' * 78)
if TOT == 0:
    print(' ✅ 사전점검 통과 — 편성을 돌려도 마스터 때문에 빠지는 것은 없다.')
else:
    print(f' ⚠ 총 {TOT}건 — 편성 전에 아래를 처리하면 왕복을 줄일 수 있다.')
    print('\n 고치는 순서:')
    for i, (t, c) in enumerate(FIX, 1):
        print(f'   {i}. {t}')
        print(f'      {c}')
    print('\n   ※ 전부 처리한 뒤 이 스크립트를 다시 돌려 ✅ 를 확인하고 편성한다.')
print('=' * 78)
cn.close()
