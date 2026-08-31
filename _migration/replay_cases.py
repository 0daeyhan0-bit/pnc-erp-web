# -*- coding: utf-8 -*-
"""재생 케이스 — 레거시 거래를 **우리 화면 API 로 다시 입력**한다 (TestBed 편입).

대표 지시(2026-09-01)
  "꼭 프로그램을 사용해서 입력을 해야지 문제점들이 나올거야. **데이터만 밀어 넣지마.**"
  "그 재생기는 TEST BED 에 같이 넣는건 어때?"

★하드룰 — 이 파일은 **INSERT/UPDATE 를 한 줄도 하지 않는다.**
  레거시에서 거래를 **읽어** TestBed 케이스(dict)로 바꿀 뿐이고,
  실제 입력은 하네스가 **HTTP 로 우리 라우터를 호출**해서 한다.
  직접 INSERT 는 게이트·유효성·파생계산(원장·수불장·재고)을 전부 건너뛰므로
  **아무것도 검증되지 않는다.** 그게 "데이터 복사"와 "프로그램 입력"의 차이다.

어디에 대고 도나
  `_migration/flow_server.py`(롤백 모드 = commit 무력화) → **오염 0**.
  운영/공유 DB 에 확정되지 않는다.

무엇을 보나
  · 우리 프로그램이 그 입력을 **받아들이는가**(400/500 이면 그 자리가 결함이다)
  · 받아들였다면 **결과가 기대만큼 움직였는가**(probe/delta)
  · 막혔다면 **왜 막혔는가** — 재고 게이트·마감·유효성. 막히는 게 정답인 경우도 있다.

쓰는 법
    set REPLAY_YMD=260831
    python _migration/flow_server.py --port 8099      (다른 창)
    python _migration/flow_scenarios.py --port 8099

지금 붙은 유형 (순차 확대)
  ✅ 생산실적  PR_T_PROD_DTL      → POST /api/procreg/save
  ☐ 키팅      PU_T_READY_STOCK_MAINT → POST /api/kitting/cell-confirm
  ☐ 출하      SA_T_STOCK_MAINT(J)    → POST /api/lgsale/save
  ☐ 자재수불  PU_T_STOCK_MAINT       → POST /api/stock/save
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend'))

# 대표 확정 10종 (2026-08-31 실측 · 생산+출하 거래건수 상위 완제품)
ITEMS = ["MJU63357501", "AJJ75838625", "AJR73965506", "AJR73965505", "AJR73965606",
         "AJR73965607", "AJR30004702", "AJR30077403", "AJR76582506", "AJR76582505"]

LIMIT = int(os.environ.get("REPLAY_LIMIT", "0") or 0)      # 0 = 제한 없음


def _rows(ymd):
    """레거시 생산실적 — **읽기 전용**(라이브 RO 커넥션)."""
    from common import _conn
    inl = ",".join("'" + x + "'" for x in ITEMS)
    cur = _conn().cursor()
    cur.execute("""SELECT WORK_ORDER, SPLIT_WORK_ORDER, LTRIM(RTRIM(ITEM_CODE)), PROD_YMD, PROD_HMS,
                          LINE_NO, PROD_QTY, WORK_CODE, PART_CODE, S_WORK_CODE, FINISH_FLAG
                     FROM PARTNER_ERP.dbo.PR_T_PROD_DTL
                    WHERE PROD_YMD=? AND LTRIM(RTRIM(ITEM_CODE)) IN (%s)
                    ORDER BY PROD_HMS, WORK_ORDER""" % inl, ymd)
    return cur.fetchall()


def build_replay_cases(ymd):
    """레거시 거래 → TestBed 케이스 목록. 여기서 DB 를 쓰지 않는다(읽기만)."""
    out = []
    try:
        rows = _rows(ymd)
    except Exception as e:
        print("  ★재생: 레거시 조회 실패 — %s" % str(e)[:120])
        return out

    for (wo, swo, item, pymd, phms, line, qty, work, part, sw, fin) in rows:
        q = int(float(qty or 0))
        if q == 0:
            continue                      # 수량 0 은 재생 의미 없음
        body = {
            "prod_ymd": str(pymd or "").strip(),
            "prod_hms": str(phms or "").strip(),
            "item_code": item,
            "work_order": str(wo or "").strip(),
            "split_work_order": str(swo or "").strip(),
            "line_no": str(line or "").strip(),
            "part_code": str(part or "").strip(),
            "work_code": str(work or "").strip(),
            "s_work_code": sw,
            "finish_flag": str(fin or "0").strip(),
            "prod_qty": q,
            "user": "replay",
        }
        out.append(dict(
            kind="F",
            name="재생 생산실적 %s x%d (WO %s)" % (item, q, str(wo or "")[:12]),
            method="POST", path="/api/procreg/save",
            probe="공정실적수량", delta=q, mirror=False,
            body=body,
        ))
        if LIMIT and len(out) >= LIMIT:
            break

    print("  재생 케이스 %d건 생성 (생산실적 · %s · 10종)" % (len(out), ymd))
    return out
