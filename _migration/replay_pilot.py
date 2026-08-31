# -*- coding: utf-8 -*-
"""재생 파일럿 — 레거시 거래를 **우리 프로그램으로 다시 입력**해 같은 결과가 나오는지 본다.

대표 지시(2026-09-01): "레거시에 입력된 거래 데이터를 신규 ERP 프로그램으로만 입력할 수 있을까?
                        단순 데이터 copy 가 아닌거야. 동일한 결과를 내는지 확인하고 싶다."
                       "오늘 8시부터 30분 단위로" · "가장 많이 사용한 Assy 품번 10종으로 파일럿"

이 파일이 하는 일 (3단계 중 1·3단계)
  --observe   30분마다 호출. 지난 관측 이후 **레거시에 새로 들어온 거래**를 유형별로 집계·나열한다.
              읽기 전용이다(라이브 무접촉·쓰기 없음).
  --baseline  지금까지의 것을 '이미 본 것'으로 표시(관측 시작점 정하기).
  --summary   오늘 누적 집계 = **대조 기준값**(우리 재생 결과와 맞춰볼 숫자).

재생(2단계)은 `--replay` 로 붙일 자리를 비워 뒀다. 재생은 반드시
`_migration/flow_server.py`(롤백 모드 = commit 무력화)에 대고 돌린다 → **오염 0**.

왜 키가 아니라 집계로 비교하나
  우리 프로그램으로 입력하면 MAINT_SEQ 가 레거시와 **다른 번호**로 붙는다(채번이 우리 것이다).
  그래서 키 대조는 전부 불일치로 보인다. 비교 축은 **품번별 수량·금액·재고 증감**이다.

주의
  · 라이브(PARTNER_ERP)는 읽기 전용으로만 만진다(_conn = RO 가드).
  · 상태파일에 '이미 본 PK'를 쌓는다. 지우면 처음부터 다시 본다.
"""
import argparse
import datetime
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend'))
os.chdir(os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend'))
from common import _conn                                    # noqa: E402

STATE = os.path.join(HERE, 'replay_pilot_state.json')

# 대표 확정 10종 (2026-08-31 실측: 생산+출하 거래건수 상위 완제품)
ITEMS = ["MJU63357501", "AJJ75838625", "AJR73965506", "AJR73965505", "AJR73965606",
         "AJR73965607", "AJR30004702", "AJR30077403", "AJR76582506", "AJR76582505"]

# (테이블, PK컬럼들, 일자컬럼, 수량컬럼, 설명)  ※전부 ITEM_CODE 보유 확인함
SRC = [
    ("PR_T_PROD_DTL", ["WORK_ORDER", "SPLIT_WORK_ORDER", "ITEM_CODE", "PROD_YMD", "PROD_HMS"],
     "PROD_YMD", "PROD_QTY", "생산실적(공정별)"),
    ("SA_T_STOCK_MAINT", ["MAINT_YMD", "MAINT_SEQ"], "MAINT_YMD", "MAINT_QTY", "완성이동/출하"),
    ("PU_T_READY_STOCK_MAINT", ["MAINT_YMD", "MAINT_SEQ"], "MAINT_YMD", "MAINT_QTY", "준비(키팅)"),
    ("PU_T_STOCK_MAINT", ["MAINT_YMD", "MAINT_SEQ"], "MAINT_YMD", "MAINT_QTY", "자재수불"),
    ("PR_T_STOCK_MAINT_MAT", ["MAINT_YMD", "MAINT_SEQ"], "MAINT_YMD", "MAINT_QTY", "생산자재"),
    ("PU_T_SET_STOCK_MAINT_GAGONG", ["MAINT_YMD", "MAINT_SEQ"], "MAINT_YMD", "MAINT_QTY", "가공세트"),
]


FORCE_YMD = None          # --ymd 로 지정하면 그 날짜를 본다(어제 데이터로 도구 자체를 시험할 때)


def _today():
    return FORCE_YMD or datetime.date.today().strftime('%y%m%d')


def _load():
    if os.path.exists(STATE):
        return json.load(io.open(STATE, encoding='utf-8'))
    return {"seen": {}, "log": []}


def _save(st):
    io.open(STATE, 'w', encoding='utf-8').write(json.dumps(st, ensure_ascii=False, indent=1))


def _fetch(cur, tab, pk, dc, qty, ymd):
    inl = ",".join("'" + x + "'" for x in ITEMS)
    cols = ",".join(pk) + ",ITEM_CODE," + qty
    cur.execute("SELECT %s FROM PARTNER_ERP.dbo.%s WHERE %s=? AND LTRIM(RTRIM(ITEM_CODE)) IN (%s)"
                % (cols, tab, dc, inl), ymd)
    out = []
    for r in cur.fetchall():
        key = "|".join(str(x).strip() for x in r[:len(pk)])
        out.append((key, str(r[len(pk)]).strip(), float(r[len(pk) + 1] or 0)))
    return out


def observe(mark_seen=True, quiet_new=False):
    st = _load()
    ymd = _today()
    cur = _conn().cursor()
    stamp = datetime.datetime.now().strftime('%H:%M')
    total_new = 0
    lines = []
    for tab, pk, dc, qty, desc in SRC:
        try:
            rows = _fetch(cur, tab, pk, dc, qty, ymd)
        except Exception as e:
            lines.append("    %-28s ★조회실패 %s" % (tab, str(e)[:60]))
            continue
        seen = set(st["seen"].get(tab, []))
        new = [r for r in rows if r[0] not in seen]
        if new:
            total_new += len(new)
            byitem = {}
            for _, it, q in new:
                a = byitem.setdefault(it, [0, 0.0])
                a[0] += 1
                a[1] += q
            detail = " · ".join("%s %d건/%.0f" % (k, v[0], v[1])
                                for k, v in sorted(byitem.items(), key=lambda x: -x[1][0])[:5])
            lines.append("    %-28s %4d행  %s" % (desc, len(new), detail))
        if mark_seen:
            st["seen"][tab] = sorted(seen | {r[0] for r in rows})
    print("  [%s] %s 신규 %d행" % (stamp, ymd, total_new))
    for l in lines:
        print(l)
    if not lines and not quiet_new:
        print("    (신규 없음)")
    if mark_seen:
        st["log"].append({"at": datetime.datetime.now().isoformat(timespec='seconds'),
                          "ymd": ymd, "new": total_new})
        _save(st)
    return total_new


def summary():
    """오늘 누적 = 우리 재생 결과와 맞춰볼 기준값."""
    ymd = _today()
    cur = _conn().cursor()
    print("  === %s 오늘 누적 (레거시 기준값) — 10종 ===" % ymd)
    grand = {}
    for tab, pk, dc, qty, desc in SRC:
        try:
            rows = _fetch(cur, tab, pk, dc, qty, ymd)
        except Exception as e:
            print("    %-28s ★%s" % (desc, str(e)[:60]))
            continue
        if not rows:
            continue
        n = len(rows)
        s = sum(r[2] for r in rows)
        print("    %-28s %5d행  수량합 %12.1f" % (desc, n, s))
        for _, it, q in rows:
            a = grand.setdefault(it, {})
            b = a.setdefault(desc, [0, 0.0])
            b[0] += 1
            b[1] += q
    print()
    print("  --- 품번별 ---")
    for it in ITEMS:
        d = grand.get(it)
        if not d:
            print("    %-14s (거래 없음)" % it)
            continue
        print("    %-14s %s" % (it, " · ".join("%s %d건/%.0f" % (k, v[0], v[1]) for k, v in d.items())))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--observe", action="store_true", help="지난 관측 이후 신규 거래(30분 주기용)")
    ap.add_argument("--baseline", action="store_true", help="현재까지를 '이미 본 것'으로 표시")
    ap.add_argument("--summary", action="store_true", help="오늘 누적 = 대조 기준값")
    ap.add_argument("--ymd", default="", help="날짜 지정(YYMMDD) — 도구 시험용. 미지정=오늘")
    a = ap.parse_args()
    if a.ymd.strip():
        FORCE_YMD = a.ymd.strip()
    if a.baseline:
        if os.path.exists(STATE):
            os.remove(STATE)
        n = observe(mark_seen=True, quiet_new=True)
        print("  ⟹ 기준점 설정 완료(%d행을 '이미 본 것'으로 표시). 이후 --observe 는 신규만 보여준다." % n)
    elif a.summary:
        summary()
    else:
        observe()
