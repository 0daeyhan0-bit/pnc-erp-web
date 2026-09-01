# -*- coding: utf-8 -*-
"""모델BOM 미러 동기화 — nx.PR_M_MODEL_BOM ← 라이브 (2026-09-01 신설)

왜 필요한가
  편성 STEP5(품목별계획)가 **모델 → ASSY 도번**을 이 테이블로 정한다
  (planrev.py `_step5_item`: `SELECT ... FROM nx.PR_M_MODEL_BOM`).
  미러가 낡으면 **같은 제번인데 웹만 옛 도번**을 달아 파트별계획이 어긋난다.

    실측 2026-09-01 — 09:19 라이브에 100건 신규 + 09:21~09:26 에 38건 적용일자 수정.
      AJR30100101  적용종료  레거시 260901 / 미러 260913
      AJR30100102  적용시작  레거시 260902 / 미러 260914
    → 9/2 계획에 레거시는 새 도번(102), 웹은 옛 도번(101)을 달았다.
      파트별계획 215건이 "도번만 다르고 수량은 같은" 상태가 됐다(수량차 0건).

★안전 원칙
  · 라이브는 **읽기만** 한다(CLAUDE.md §1-1). 쓰기는 nx 뿐.
  · `--apply` 없이는 조회만 한다(기본 dry-run).
  · 실행 전 백업 테이블에 원본을 남긴다.
  · 값갱신(UPDATE) + 신규(INSERT) + 삭제분 정리를 모두 한다
    (INSERT 만 하면 적용일자 변경을 못 따라간다 — 이번 사고의 원인).

사용
    python _schema/sync_model_bom.py            # 조회만
    python _schema/sync_model_bom.py --apply    # 실제 동기화
"""
import sys, os, io, argparse, datetime

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
LIVE = 'PARTNER_ERP.dbo.PR_M_MODEL_BOM'
MIRR = 'nx.PR_M_MODEL_BOM'
BK = 'nx.bk_model_bom_' + datetime.datetime.now().strftime('%y%m%d_%H%M')
KEY = "RTRIM(l.MODEL_NO)=RTRIM(m.MODEL_NO) AND RTRIM(l.C_ITEM_CODE)=RTRIM(m.C_ITEM_CODE)"
VALS = ("ISNULL(RTRIM(m.MAKE_YMD),'')<>ISNULL(RTRIM(l.MAKE_YMD),'')"
        " OR ISNULL(RTRIM(m.TO_APPLY_YMD),'')<>ISNULL(RTRIM(l.TO_APPLY_YMD),'')"
        " OR ISNULL(CAST(m.USE_QTY AS float),0)<>ISNULL(CAST(l.USE_QTY AS float),0)"
        " OR ISNULL(RTRIM(m.VIR_SET_FLAG),'')<>ISNULL(RTRIM(l.VIR_SET_FLAG),'')"
        " OR ISNULL(RTRIM(m.SALE_CUST_CODE),'')<>ISNULL(RTRIM(l.SALE_CUST_CODE),'')")

cn = pyodbc.connect(CS, autocommit=False)
cur = cn.cursor()

print('=' * 74)
print(' 모델BOM 동기화  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print('=' * 74)


def n1(q):
    cur.execute(q)
    r = cur.fetchone()
    return int(r[0] or 0) if r else 0


mir = n1(f'SELECT COUNT(*) FROM {MIRR} WITH(NOLOCK)')
liv = n1(f'SELECT COUNT(*) FROM {LIVE} WITH(NOLOCK)')
print(f'\n① 행수   미러 {mir:,}  /  라이브 {liv:,}')

n_upd = n1(f"""SELECT COUNT(*) FROM {MIRR} m WITH(NOLOCK)
                 JOIN {LIVE} l WITH(NOLOCK) ON {KEY}
                WHERE {VALS}""")
n_ins = n1(f"""SELECT COUNT(*) FROM {LIVE} l WITH(NOLOCK)
                WHERE NOT EXISTS(SELECT 1 FROM {MIRR} m WITH(NOLOCK) WHERE {KEY})""")
n_del = n1(f"""SELECT COUNT(*) FROM {MIRR} m WITH(NOLOCK)
                WHERE NOT EXISTS(SELECT 1 FROM {LIVE} l WITH(NOLOCK) WHERE {KEY})""")
print(f'\n② 할 일   값갱신 {n_upd:,}행 · 신규 {n_ins:,}행 · 삭제 {n_del:,}행')

if n_upd:
    print('\n③ 값이 달라지는 내용 (앞 10건)')
    cur.execute(f"""SELECT TOP 10 RTRIM(m.MODEL_NO), RTRIM(m.C_ITEM_CODE),
                           RTRIM(ISNULL(m.MAKE_YMD,'')), RTRIM(ISNULL(l.MAKE_YMD,'')),
                           RTRIM(ISNULL(m.TO_APPLY_YMD,'')), RTRIM(ISNULL(l.TO_APPLY_YMD,''))
                      FROM {MIRR} m WITH(NOLOCK) JOIN {LIVE} l WITH(NOLOCK) ON {KEY}
                     WHERE {VALS}""")
    print('    모델 · 도번 · 시작(미러→라이브) · 종료(미러→라이브)')
    for r in cur.fetchall():
        print(f'    {r[0]:22s} {r[1]:16s} {r[2]}→{r[3]}  {r[4]}→{r[5]}')

if not (n_upd or n_ins or n_del):
    print('\n   ✅ 이미 동기 상태입니다.')
    cn.close(); sys.exit(0)

if not ARG.apply:
    print('\n※ DRY-RUN 입니다. 실제로 동기화하려면 --apply 를 붙이세요.')
    cn.close(); sys.exit(0)

print(f'\n④ 백업 → {BK}')
cur.execute(f'SELECT * INTO {BK} FROM {MIRR}')
print(f'    {cur.rowcount:,}행 백업')

cur.execute(f"""UPDATE m SET m.MAKE_YMD=l.MAKE_YMD, m.TO_APPLY_YMD=l.TO_APPLY_YMD,
                             m.USE_QTY=l.USE_QTY, m.VIR_SET_FLAG=l.VIR_SET_FLAG,
                             m.SALE_CUST_CODE=l.SALE_CUST_CODE, m.PROD_AVG_FLAG=l.PROD_AVG_FLAG,
                             m.UPDATE_USER_ID='sync', m.UPDATE_DATETIME=GETDATE()
                  FROM {MIRR} m JOIN {LIVE} l WITH(NOLOCK) ON {KEY}
                 WHERE {VALS}""")
print(f'    값갱신 {cur.rowcount:,}행')

cur.execute(f"""INSERT INTO {MIRR}(MODEL_NO,C_ITEM_CODE,MAKE_YMD,TO_APPLY_YMD,USE_QTY,
                                    PROD_AVG_FLAG,SALE_CUST_CODE,VIR_SET_FLAG,
                                    INSERT_USER_ID,INSERT_DATETIME)
                SELECT l.MODEL_NO,l.C_ITEM_CODE,l.MAKE_YMD,l.TO_APPLY_YMD,l.USE_QTY,
                       l.PROD_AVG_FLAG,l.SALE_CUST_CODE,l.VIR_SET_FLAG,'sync',GETDATE()
                  FROM {LIVE} l WITH(NOLOCK)
                 WHERE NOT EXISTS(SELECT 1 FROM {MIRR} m WHERE {KEY})""")
print(f'    신규   {cur.rowcount:,}행')

cur.execute(f"""DELETE m FROM {MIRR} m
                 WHERE NOT EXISTS(SELECT 1 FROM {LIVE} l WITH(NOLOCK) WHERE {KEY})""")
print(f'    삭제   {cur.rowcount:,}행')

cn.commit()

left_u = n1(f"SELECT COUNT(*) FROM {MIRR} m WITH(NOLOCK) JOIN {LIVE} l WITH(NOLOCK) ON {KEY} WHERE {VALS}")
left_i = n1(f"SELECT COUNT(*) FROM {LIVE} l WITH(NOLOCK) WHERE NOT EXISTS(SELECT 1 FROM {MIRR} m WITH(NOLOCK) WHERE {KEY})")
mir2 = n1(f'SELECT COUNT(*) FROM {MIRR} WITH(NOLOCK)')
print(f'\n⑤ 검증 — 잔여 값차 {left_u} · 누락 {left_i} · 미러 {mir2:,} / 라이브 {liv:,}')
print('   ' + ('✅ 동기화 완료' if (left_u == 0 and left_i == 0) else '★아직 남았다'))
print(f'\n   되돌리려면: {BK} 참조')
print('   ⚠ 편성(①④⑤)을 다시 돌려야 계획에 반영됩니다.')
cn.close()
