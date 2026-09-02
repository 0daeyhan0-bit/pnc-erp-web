# -*- coding: utf-8 -*-
"""LG 리시빙파일 업로드 검증 테스트베드 (routers/lgrecv.py).

증명 2가지:
  A. 파싱 정확성(diff0) — GR Status 파일을 실제 파서(_parse_gr_status)로 파싱한 결과가
     라이브 PARTNER_ERP.dbo.SA_T_LG_RECEIVING_DTL(해당 일자·구분)과 (품번,WorkOrder,수량,금액) 다중집합 diff0.
  B. 쓰기 경로 무오염 — 실제 업로드 로직(삭제-교체 INSERT)을 _nx_tx(autocommit=False) 안에서
     실행 → 트랜잭션 내 재조회로 행수/합계 확인 → ROLLBACK(영구반영 0). nx 오염 없음 증명.

사용: python _schema/lgrecv_upload_testbed.py "C:\\path\\GR Status_...xlsx"
  인자 없으면 기본 9/1 파일(Downloads) 사용. 라이브 대조는 GR Date 로 자동 결정한 일자·구분.
"""
import sys, os, glob
from collections import Counter
try:
    sys.stdout.reconfigure(encoding="utf-8")   # 콘솔 cp949 인코딩 에러 방지(한글·em-dash)
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, _BACKEND)
# db_client(자격증명) = repo 밖 sibling
sys.path.insert(0, os.path.join(_HERE, "..", "..", "New_ERP"))

from routers.lgrecv import _parse_gr_status  # 실제 배포 파서
from common import _nx_tx
import db_client


def _live_multiset(ymd, gubun):
    cn = db_client.get_connection(); cur = cn.cursor()
    cur.execute("SELECT item_code,ISNULL(work_order,''),recv_qty,recv_amt "
                "FROM PARTNER_ERP.dbo.SA_T_LG_RECEIVING_DTL WHERE receiving_ymd=? AND gubun=?", ymd, gubun)
    ms = Counter((str(r[0]).strip(), str(r[1]).strip(), int(round(float(r[2] or 0))), round(float(r[3] or 0), 2))
                 for r in cur.fetchall())
    cn.close()
    return ms


def main():
    args = sys.argv[1:]
    if args:
        path = args[0]
    else:
        cands = glob.glob(os.path.expanduser(r"~\Downloads\GR Status_*.xlsx"))
        if not cands:
            print("파일 인자 필요 (GR Status .xlsx)"); return 1
        path = sorted(cands)[0]
    print(f"[파일] {path}")
    with open(path, "rb") as f:
        content = f.read()
    groups, meta = _parse_gr_status(content, os.path.basename(path))
    print(f"[파싱] 유효 {meta['total_rows']}행 · 제외 {meta['skipped']}행 · 구분 {sorted(groups)}")
    for w in meta["warnings"]:
        print(f"  경고: {w}")

    passed = failed = 0
    # ── A. 파싱 diff0 (구분별) ──
    for g, d in sorted(groups.items()):
        parsed = Counter((r["item_code"], r["work_order"], r["recv_qty"], r["recv_amt"]) for r in d["recs"])
        # 파일이 여러 일자를 담을 수 있어 라이브도 같은 일자범위 전체를 합쳐 비교
        live = Counter()
        ymds = sorted({r["receiving_ymd"] for r in d["recs"]})
        for y in ymds:
            live += _live_multiset(y, g)
        op = sum((parsed - live).values()); ol = sum((live - parsed).values())
        ok = (op == 0 and ol == 0)
        print(f"[A/{g}({d['ymd_from']}~{d['ymd_to']})] 파싱 {len(d['recs'])}행 vs 라이브 {sum(live.values())}행 · "
              f"파싱only={op} 라이브only={ol} → {'PASS' if ok else 'FAIL'}")
        passed += ok; failed += (not ok)

    # ── B. 쓰기 경로 무오염 (삭제-교체 → 재조회 → ROLLBACK) ──
    cn = _nx_tx(); cur = cn.cursor()
    try:
        total_ins = 0
        for g, d in sorted(groups.items()):
            cur.execute("DELETE FROM nx.SA_T_LG_RECEIVING_DTL WHERE RECEIVING_YMD BETWEEN ? AND ? AND GUBUN=?",
                        d["ymd_from"], d["ymd_to"], g)
            recs = sorted(d["recs"], key=lambda x: x["receiving_ymd"])
            seq = {}
            for r in recs:
                y = r["receiving_ymd"]; seq[y] = seq.get(y, 0) + 1
                cur.execute("""INSERT INTO nx.SA_T_LG_RECEIVING_DTL
                    (RECEIVING_YMD,GUBUN,RECEIVING_SEQ,ITEM_CODE,RECV_QTY,RECV_COST,RECV_AMT,CURRENCY,CURRENCY_RATE,
                     MKT,WORK_ORDER,ORDER_TYPE,ORDER_NO,DEPARTURE_NO,DEPARTURE_DATE,SUPPLIER_REF_NO,SUBINVENTORY,
                     UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_IP,UPDATE_COMPUTER,UPDATE_WINDOW)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,GETDATE(),?,?,?)""",
                    r["receiving_ymd"], r["gubun"], seq[y], r["item_code"], r["recv_qty"], r["recv_cost"],
                    r["recv_amt"], r["currency"], r["currency_rate"], r["mkt"], r["work_order"], r["order_type"],
                    r["order_no"], r["departure_no"], r["departure_date"], r["supplier_ref_no"], r["subinventory"],
                    "테스트", "", "TB", "lgrecv_tb")
                total_ins += 1
            # 트랜잭션 내 재조회
            cur.execute("SELECT COUNT(*),SUM(RECV_AMT) FROM nx.SA_T_LG_RECEIVING_DTL WHERE RECEIVING_YMD BETWEEN ? AND ? AND GUBUN=?",
                        d["ymd_from"], d["ymd_to"], g)
            cnt, amt = cur.fetchone()
            ok = (cnt == len(d["recs"]) and abs(float(amt or 0) - d["amt"]) < 1)
            print(f"[B/{g}] 삽입 {len(d['recs'])}행 → 재조회 {cnt}행/합계 {float(amt or 0):.0f} (기대 {d['amt']:.0f}) → {'PASS' if ok else 'FAIL'}")
            passed += ok; failed += (not ok)
        cn.rollback()   # ★영구반영 안 함
        print(f"[B] ROLLBACK 완료 — nx 오염 0 (삽입 시도 {total_ins}행 전부 롤백)")
    except Exception as e:
        cn.rollback(); print(f"[B] 예외 → ROLLBACK: {e}"); failed += 1
    finally:
        cn.close()

    print(f"\n=== 결과: PASS {passed} · FAIL {failed} ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
