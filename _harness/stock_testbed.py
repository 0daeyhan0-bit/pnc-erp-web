# -*- coding: utf-8 -*-
"""★공용 재고이동 테스트베드 — 자재/생산/영업 입출고 프로그램 검증 (2026-08-27 신설).

용접봉 백플러시 검증에 쓴 패턴(①시드→②동작→③재고읽기→④불변식검증→⑤롤백)을 일반화.
어떤 입출고 프로그램이든 "재고가 정확히 움직이는지"를 몇 줄로 검증·오염0(전부 롤백).

핵심 3요소:
  1) read_stock(cur, point, item, loc) : 재고점별 잔량 통합 리더 (STOCK_CLOSE_HANDOFF §7-5 소스맵)
  2) sandbox()                          : 쓰기 샌드박스(nx_tx 열고 끝나면 무조건 롤백 → 라이브/nx 오염0)
  3) check_invariant(...)               : 불변식 '기초 + 입 − 출 ± 조정 = 기말' (handoff §7-2)
  + Tracker : 여러 (재고점·품목) 잔량 before/after 캡처·델타 계산
  + seed()  : 테스트용 재고를 stock_ledger에 시드

규칙(handoff §2 준수):
  - 자재(MAT) 가용판정 = mat_stock_daily(§16). 생산창고/준비/사급/생산/완성 = stock_ledger. 영업완성 = SA_T_ITEM_STOCK.
  - 음수재고는 차단(handoff §2-1). 이 하네스는 '검증'용 — 실제 차단 로직은 각 프로그램의 게이트.
  - 라이브 PARTNER_ERP 무접촉. 쓰기는 nx만, 그마저 sandbox면 롤백.

사용 예: 파일 하단 __main__ (용접봉 백플러시 3시연) 참고. import 해서 다른 프로그램 검증에 재사용.
"""
import sys, io, contextlib, datetime
sys.path.insert(0, r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_rdr/PNC_ERP_Web/backend')
import common
from common import _mat_avail, _prod_stock_map

# ── 재고점 소스맵 (STOCK_CLOSE_HANDOFF §7-5) ────────────────────────────────
POINT_SOURCES = {
    'MAT':    '자재 현재고        = nx.mat_stock_daily (이동평균 일마감, §16 정본)',
    'PRODWH': '생산창고(공정) 재고 = SUM(stock_ledger MAT·GAGONG_PROC_CODE=loc)  ← 용접봉 Q1000 등',
    'RDY':    '준비/키팅 재고      = SUM(stock_ledger STOCK_POINT=RDY·ITEM_CODE)',
    'SAG':    '사급 재고          = SUM(stock_ledger STOCK_POINT=SAG·ITEM_CODE)',
    'PRD':    '생산 재고          = SUM(stock_ledger STOCK_POINT=PRD·ITEM_CODE)',
    'ASY':    '완성 재고          = SUM(stock_ledger STOCK_POINT=ASY·ITEM_CODE)',
    'PARTWH': '파트창고 재고       = common._prod_stock_map(by_part) 이력계산(라이브∪nx)  ← loc=파트',
    'FIN':    '영업완성 재고       = nx.SA_T_ITEM_STOCK.STOCK_QTY',
}

def read_stock(cur, point, item, loc=None):
    """재고점별 잔량 통합 리더. point=MAT/PRODWH/RDY/SAG/PRD/ASY/PARTWH/FIN. loc=공정/파트(해당시)."""
    p = str(point).upper()
    if p == 'MAT':
        return float(_mat_avail(cur, item))
    if p == 'PRODWH':
        cur.execute("""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger
            WHERE STOCK_POINT='MAT' AND MAT_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""", item, (loc or ''))
        return float(cur.fetchone()[0] or 0)
    if p in ('RDY', 'SAG', 'PRD', 'ASY'):
        cur.execute("SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE STOCK_POINT=? AND ITEM_CODE=?", p, item)
        return float(cur.fetchone()[0] or 0)
    if p == 'PARTWH':
        return float(_prod_stock_map(cur, by_part=True).get((str(item).upper(), str(loc or '')), 0.0))
    if p == 'FIN':
        cur.execute("SELECT ISNULL(SUM(CAST(STOCK_QTY AS float)),0) FROM nx.SA_T_ITEM_STOCK WHERE ITEM_CODE=?", item)
        return float(cur.fetchone()[0] or 0)
    raise ValueError(f"unknown stock point: {point} (POINT_SOURCES: {list(POINT_SOURCES)})")


@contextlib.contextmanager
def sandbox():
    """쓰기 샌드박스 — nx 쓰기 트랜잭션을 열고 블록 종료 시 무조건 롤백(오염0).
       with sandbox() as (nx, cur): ...  → 안에서 시드/동작/검증하고 나가면 전부 되돌림.
       ※실제 커밋이 필요한 검증(엔드포인트 HTTP)엔 부적합 — 그땐 근거키로 사후정리."""
    nx = common._nx_tx(); cur = nx.cursor()
    try:
        yield nx, cur
    finally:
        try: nx.rollback()
        except Exception: pass
        try: nx.close()
        except Exception: pass


def seed(cur, item, qty, gpc=None, tag='MV', user='TESTBED', wo='TESTBED_SEED'):
    """테스트용 재고 시드 = stock_ledger 1행(+qty). 생산창고면 gpc 지정. sandbox 안에서 쓰면 롤백됨."""
    ymd6 = datetime.datetime.now().strftime('%y%m%d')
    cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd6)
    seq = int(cur.fetchone()[0] or 1)
    cur.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,
          GAGONG_PROC_CODE,WORK_ORDER,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
        VALUES('MAT',?,?,?,'Z99990',?,?,?,?,'테스트베드 시드',?,GETDATE())""",
        ymd6, seq, tag, item, gpc, wo, qty, user)


class Tracker:
    """여러 (재고점·품목·loc) 잔량을 before/after 캡처하고 델타를 낸다.
       t = Tracker(cur); t.watch('생산창고', 'PRODWH', base, 'Q1000'); t.snap('before'); <동작>; t.snap('after'); t.deltas()."""
    def __init__(self, cur):
        self.cur = cur; self.keys = []; self.snaps = {}
    def watch(self, label, point, item, loc=None):
        self.keys.append((label, point, item, loc)); return self
    def snap(self, name):
        self.snaps[name] = {lbl: read_stock(self.cur, p, it, lc) for (lbl, p, it, lc) in self.keys}
        return self.snaps[name]
    def deltas(self, a='before', b='after'):
        return {lbl: round(self.snaps[b][lbl] - self.snaps[a][lbl], 6) for lbl, *_ in self.keys}


def check_invariant(base, inp, out, adj=0.0, end=None, adj_sign='+', tol=1e-6, label=''):
    """불변식: 기초 + 입 − 출 ± 조정 = 기말 (handoff §7-2). adj_sign: 생산480='+', 제품040='-'.
       end=실제 기말. 반환 {ok, calc, end, diff}."""
    calc = base + inp - out + (adj if adj_sign == '+' else -adj)
    diff = (end - calc) if end is not None else None
    ok = (end is not None) and abs(diff) < tol
    return {"ok": ok, "label": label, "calc": round(calc, 6), "end": end,
            "diff": (round(diff, 6) if diff is not None else None)}


def assert_delta(tracker, expected, tol=1e-6):
    """Tracker 델타가 기대치와 일치하는지 검증. expected={label: 기대델타}. 반환 {ok, mismatches}."""
    d = tracker.deltas()
    mism = {k: (d.get(k), v) for k, v in expected.items() if abs((d.get(k, 0) or 0) - v) > tol}
    return {"ok": not mism, "deltas": d, "mismatches": mism}


# ══════════════════════════════════════════════════════════════════════════
# 예제 = 용접봉 백플러시 검증 (2026-08-27 실제 사용분). 다른 프로그램도 이 골격 재사용.
# ══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    from routers.backflush import _weld_consume, _weld_proc_code, _backflush_bom

    print("공용 재고 테스트베드 — 재고점 소스맵:")
    for k, v in POINT_SOURCES.items():
        print(f"  {k:7} {v}")

    print("\n[예제] 용접봉 백플러시 = 생산창고(PRODWH) −차감 검증 (sandbox 롤백)")
    IT = 'AJR30004702'
    with sandbox() as (nx, cur):
        _, weld = _backflush_bom(nx, IT, nx)
        for b in weld:                                # ★전 종 시드(안하면 게이트가 부족으로 차단)
            seed(cur, b, 0.1, gpc=_weld_proc_code(nx, b))
        base = list(weld)[0]; gpc = _weld_proc_code(nx, base)
        t = Tracker(cur).watch('생산창고', 'PRODWH', base, gpc)
        t.snap('before')
        r = _weld_consume(nx, nx, IT, 1.0, 'EX1', 'TESTBED')  # 생산 1개
        t.snap('after')
        exp = -round(weld[base], 6)                   # 기대: −(용접봉 원단위)
        chk = assert_delta(t, {'생산창고': exp})
        print(f"  품목 {IT} 용접봉 {base} 원단위={weld[base]}")
        print(f"  생산 1개 → 생산창고 델타={chk['deltas']['생산창고']} (기대 {exp}) · 일치={chk['ok']}")
    print("  (sandbox 종료 → 롤백, nx 무변경)")
