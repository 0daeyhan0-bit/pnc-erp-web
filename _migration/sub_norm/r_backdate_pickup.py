# -*- coding: utf-8 -*-
"""★백데이트 UPDATE 픽업 (2026-08-31 신설) — r_delta_sync 윈도우 밖 수정분 반영.

왜 필요한가 (2026-08-31 실측으로 드러난 갭)
  r_delta_sync 는 거래테이블을 **최근 30일 윈도우**로만 재복사한다(dc >= cutoff).
  그래서 **윈도우보다 오래된 전표를 라이브에서 고치면 nx 에 영원히 안 들어온다.**
  자가치유(do_window)는 **행수만** 비교하므로 내용만 바뀐 경우 잡지 못한다
  (CLAUDE.md §A "행수 같아도 내용 다를 수 있음" 이 정확히 이 케이스).

  실측: PU_T_STOCK_MAINT 2607 구간 25행이 어긋나 recon RED.
        2026-08-31 11:26 김미진 님이 w_pu_sale_010 에서 7/30 전표를 손봤고,
        그중 2건은 단가 정정(2,373.50 → 2,412.00)이었다. 나머지 23건은 감사컬럼만.
        ⟹ 금액이 걸린 진짜 수정이라 놓치면 안 된다.

무엇을 하나
  각 거래테이블에서 **윈도우 밖(dc < cutoff)이면서 최근 BACK_DAYS 안에 UPDATE_DATETIME 이 찍힌 행**을
  PK 스코프로 DELETE → 라이브에서 INSERT. **근거키(PK)로만 지운다** — 태그·구간 대량삭제 아님
  ([[feedback-nx-ledger-no-mass-delete]] 준수).

한계 (알고 쓸 것)
  · UPDATE_DATETIME 이 없거나 PK 가 없는 테이블은 **스킵**하고 목록으로 보고한다(조용히 넘기지 않는다).
  · 라이브에서 **삭제**된 과거 행은 이 도구로 안 잡힌다(UPDATE 흔적이 없다). 그건 recon 이 행수로 잡는다.
  · 레거시가 UPDATE_DATETIME 을 안 찍고 고치면 못 잡는다 → 그래서 **recon 이 최종 판정**이다.

DRY 기본. 실행 = `python r_backdate_pickup.py --commit`
읽기 = PARTNER_ERP(RO) · 쓰기 = PARTNER_ERP_TEST3.nx 미러만.
"""
import datetime
import io
import sys

sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client  # noqa: E402
import pyodbc     # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

DRY = ('--commit' not in sys.argv)
WINDOW_DAYS = 30      # r_delta_sync 와 동일해야 한다(그 밖을 줍는 도구이므로)
BACK_DAYS = 30        # 최근 며칠 안에 수정된 것을 주울지
ONLY = None
for i, a in enumerate(sys.argv):
    if a == '--only' and i + 1 < len(sys.argv):
        ONLY = sys.argv[i + 1].upper()
    if a == '--back' and i + 1 < len(sys.argv):
        BACK_DAYS = int(sys.argv[i + 1])

cutoff = (datetime.date.today() - datetime.timedelta(days=WINDOW_DAYS)).strftime('%y%m%d')
since = (datetime.datetime.now() - datetime.timedelta(days=BACK_DAYS)).strftime('%Y-%m-%d 00:00:00')

cn = pyodbc.connect(
    'DRIVER={SQL Server};SERVER=%s,%s;DATABASE=PARTNER_ERP_TEST3;UID=%s;PWD=%s'
    % (db_client.DB_SERVER, db_client.DB_PORT, db_client.DB_USER, db_client.DB_PASSWORD),
    autocommit=False)
c = cn.cursor()

print("=== 백데이트 픽업 (윈도우밖 dc<%s · 최근 %d일 수정분) %s ===" % (cutoff, BACK_DAYS, '[DRY]' if DRY else '[COMMIT]'))

# 대상 = nx 거래테이블 중 라이브에 같은 이름이 있는 것
c.execute("""SELECT t.name FROM sys.tables t
              WHERE t.schema_id=SCHEMA_ID('nx') AND t.name LIKE '%[_]T[_]%'
              ORDER BY t.name""")
cands = [r[0] for r in c.fetchall()]
if ONLY:
    cands = [t for t in cands if t.upper() == ONLY]

skip_nodate, skip_nopk, skip_nolive = [], [], []
total_hit = 0
touched = []

for t in cands:
    # 라이브 존재 + 컬럼
    c.execute("""SELECT COLUMN_NAME, DATA_TYPE FROM PARTNER_ERP.INFORMATION_SCHEMA.COLUMNS
                  WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=?""", t)
    cols = {r[0].upper(): r[1] for r in c.fetchall()}
    if not cols:
        skip_nolive.append(t)
        continue
    if 'UPDATE_DATETIME' not in cols:
        skip_nodate.append(t)
        continue

    # 날짜 컬럼(윈도우 기준) — r_delta_sync 와 같은 우선순위로 고른다
    dc = None
    for cand in ('MAINT_YMD', 'PLAN_YMD', 'SALE_YMD', 'PUR_YMD', 'PROD_YMD', 'INPUT_YMD',
                 'RECEIVING_YMD', 'NEED_BY_YMD', 'MOVE_YMD', 'ERROR_YMD', 'OQC_YMD', 'REV_YYMD',
                 'REAL_INPUT_YMD', 'ISSUE_YMD', 'ORDER_YMD'):
        if cand in cols:
            dc = cand
            break
    if not dc:
        skip_nodate.append(t)
        continue

    # PK
    c.execute("""SELECT k.COLUMN_NAME FROM PARTNER_ERP.INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
                  JOIN PARTNER_ERP.INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                    ON k.CONSTRAINT_NAME=tc.CONSTRAINT_NAME
                 WHERE tc.CONSTRAINT_TYPE='PRIMARY KEY' AND k.TABLE_NAME=? AND k.TABLE_SCHEMA='dbo'
                 ORDER BY k.ORDINAL_POSITION""", t)
    pk = [r[0] for r in c.fetchall()]
    if not pk:
        skip_nopk.append(t)
        continue

    where = "a.%s < '%s' AND a.UPDATE_DATETIME >= '%s'" % (dc, cutoff, since)
    c.execute("SELECT COUNT_BIG(*) FROM PARTNER_ERP.dbo.%s a WHERE %s" % (t, where))
    n = c.fetchone()[0]
    if not n:
        continue

    total_hit += n
    touched.append((t, dc, pk, n))
    print("  %-32s %-14s PK=%-28s 백데이트 %s행" % (t, dc, ",".join(pk), n))

    if not DRY:
        join = " AND ".join("b.%s=a.%s" % (k, k) for k in pk)
        try:
            c.execute("DELETE b FROM nx.%s b JOIN PARTNER_ERP.dbo.%s a ON %s WHERE %s"
                      % (t, t, join, where))
            c.execute("INSERT INTO nx.%s SELECT a.* FROM PARTNER_ERP.dbo.%s a WHERE %s"
                      % (t, t, where))
            cn.commit()
            print("      → 반영 완료")
        except Exception as e:
            cn.rollback()
            print("      ★실패(롤백): %s" % e)

print("\n  대상 %d개 중 백데이트 있는 테이블 %d개 · 총 %s행" % (len(cands), len(touched), total_hit))
if skip_nodate:
    print("  스킵(UPDATE_DATETIME 또는 날짜컬럼 없음) %d개: %s" % (len(skip_nodate), ", ".join(skip_nodate[:8])))
if skip_nopk:
    print("  ★스킵(PK 없음 — 근거키를 못 만들어 손대지 않음) %d개: %s" % (len(skip_nopk), ", ".join(skip_nopk[:8])))
if skip_nolive:
    print("  스킵(라이브에 없음=nx전용) %d개" % len(skip_nolive))
print("  ⟹ %s" % ("DRY — 반영하려면 --commit" if DRY else "반영 완료. recon 으로 GREEN 확인할 것"))
