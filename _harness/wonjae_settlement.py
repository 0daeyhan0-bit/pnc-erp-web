# -*- coding: utf-8 -*-
"""원소재(동) 정산 엔진 — 협력사 확정입고의 동 소비를 geom×소요량×입고수량으로 산출.
   정본: 소요량=BOM(PR_M_ITEM_BOM), 치수=PR_M_ITEM(Φ/T/L), geom공식(검증완료 ×0.02809).
   진짜매입 판정 = COST_TAG='1' 매입단가 거래처=입고거래처.
   담당 파이프 수불 자료의 '입고중량(KG)'을 재현/검증하는 것이 목표.

   사용:
     from wonjae_settlement import CopperSettlement
     eng = CopperSettlement()
     res = eng.by_vendor('2606' 형태의 yymm 아님 주의: '2606'=26년6월), custs=[...])
"""
import sys
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness")
from nx_cost_engine import _nx

CU_DENSITY_K = 0.02809 * 0.001   # (π×8.94/1000)/1000, kg/mm³-length 계수 (검증: 파일중량 일치)
COOP_CUST = {'2148':'대원산업','2096':'미래정밀','2306':'명진산업','2048':'중앙정밀','2068':'이젠터',
             '2266':'케이비','2142':'세광산업','233':'썬텍코리아','2028':'썬텍','2067':'MTS','2250':'수테크'}

def geom(d, t, l):
    """동관 단위 중량(kg) = (Φ-T)×T×L×0.02809×0.001. 캐필러리(Φ<3)도 계산."""
    try:
        d, t, l = float(d), float(t), float(l)
    except (TypeError, ValueError):
        return 0.0
    if d and t and l and t > 0 and d > t and l > 0:
        return (d - t) * t * l * CU_DENSITY_K
    return 0.0


class CopperSettlement:
    def __init__(self):
        self.cn = _nx(); self.cur = self.cn.cursor()
        self.L = "PARTNER_ERP.dbo."
        self._pur = None     # 매입단가 거래처 map
        self._dim = {}       # 품목 치수 캐시
        self._bom = {}       # Assy→[(child,useqty)] 캐시

    # 매입단가(COST_TAG='1') 거래처 map (진짜매입 판정)
    def _purmap(self):
        if self._pur is None:
            self.cur.execute(f"SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), LTRIM(RTRIM(ISNULL(CUST_CODE,''))) "
                             f"FROM {self.L}PR_M_ITEM_COST WHERE COST_TAG='1'")
            m = {}
            for ic, cc in self.cur.fetchall():
                m.setdefault(str(ic).strip(), set()).add(str(cc).strip())
            self._pur = m
        return self._pur

    def _dims(self, code):
        """품목 Φ/T/L (PR_M_ITEM). 캐시."""
        if code not in self._dim:
            self.cur.execute(f"SELECT ITEM_DIAM, ITEM_THICK, ITEM_LENGTH FROM {self.L}PR_M_ITEM "
                             f"WHERE LTRIM(RTRIM(ITEM_CODE))=?", code)
            r = self.cur.fetchone()
            self._dim[code] = (r[0], r[1], r[2]) if r else (None, None, None)
        return self._dim[code]

    def _children(self, code):
        """Assy 직하위 [(child, use_qty)] (PR_M_ITEM_BOM, 유효일자 무시=최신구성). 캐시."""
        if code not in self._bom:
            self.cur.execute(f"SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), ISNULL(USE_QTY,1) "
                             f"FROM {self.L}PR_M_ITEM_BOM WHERE LTRIM(RTRIM(ITEM_CODE))=?", code)
            self._bom[code] = [(str(m).strip(), float(q or 1)) for m, q in self.cur.fetchall()]
        return self._bom[code]

    def unit_copper(self, code, _depth=0):
        """품목 1개당 동 중량(kg). 단품=geom(자기치수). Assy=Σ(하위 unit_copper×소요). 재귀."""
        d, t, l = self._dims(code)
        g = geom(d, t, l)
        if g > 0:               # 자기 치수 있으면 단품 동관
            return g
        if _depth > 6:
            return 0.0
        kids = self._children(code)
        return sum(self.unit_copper(ch, _depth + 1) * q for ch, q in kids)

    def receipts(self, yymm, custs=None):
        """해당 월(yymm='2606') 확정입고(진짜매입)만: (품목,거래처,입고수량합)."""
        custs = list(custs or COOP_CUST.keys())
        ph = ",".join("?" * len(custs))
        ym = "26" + yymm[2:] if len(yymm) == 4 else yymm  # 방어
        f, t = yymm + "01", yymm + "31"
        self.cur.execute(f"""SELECT UPPER(LTRIM(RTRIM(A.MAT_CODE))) ic, LTRIM(RTRIM(A.CUST_CODE)) cc, SUM(A.MAINT_QTY) q
            FROM {self.L}PU_T_STOCK_MAINT A
            WHERE A.MAINT_TAG IN ('9','S','C','G','H') AND A.MAINT_QTY>0 AND A.MAINT_YMD BETWEEN ? AND ?
              AND LTRIM(RTRIM(A.CUST_CODE)) IN ({ph})
              AND ((ISNULL(A.INSP_FLAG,'N') IN ('','N')) OR (ISNULL(A.INSP_FLAG,'N') IN ('S','F')))
            GROUP BY UPPER(LTRIM(RTRIM(A.MAT_CODE))), LTRIM(RTRIM(A.CUST_CODE))""", f, t, *custs)
        return [(str(r[0]).strip(), str(r[1]).strip(), float(r[2] or 0)) for r in self.cur.fetchall()]

    def by_vendor(self, yymm, custs=None, real_only=True):
        """협력사별 동 소비(kg) 집계 + 품목 detail. 동소비=unit_copper×입고수량."""
        pur = self._purmap()
        agg = {}          # cc -> {copper, items, skipped_nonpur}
        detail = []
        for ic, cc, q in self.receipts(yymm, custs):
            is_pur = cc in pur.get(ic, set())
            if real_only and not is_pur:
                a = agg.setdefault(cc, {"copper": 0.0, "items": 0, "nonpur": 0})
                a["nonpur"] += 1
                continue
            uc = self.unit_copper(ic)
            cop = uc * q
            a = agg.setdefault(cc, {"copper": 0.0, "items": 0, "nonpur": 0})
            a["copper"] += cop; a["items"] += 1
            detail.append((cc, ic, round(uc, 5), q, round(cop, 3), is_pur))
        return agg, detail

    def close(self):
        try: self.cn.close()
        except Exception: pass


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    eng = CopperSettlement()
    agg, detail = eng.by_vendor("2606")
    print("=== 26년 6월 협력사별 동 소비(kg) — 엔진 산출 ===")
    for cc, a in sorted(agg.items(), key=lambda x: -x[1]["copper"]):
        print(f"  {COOP_CUST.get(cc, cc):<10}({cc:<5}) 동소비 {a['copper']:>12,.1f}kg · 매입품목 {a['items']:>4} · 매입아님 {a['nonpur']:>4}")
    print(f"\n품목 detail 표본 12:")
    for cc, ic, uc, q, cop, isp in detail[:12]:
        print(f"  {COOP_CUST.get(cc, cc):<8}{ic:<18} 단위동{uc:>8} ×수량{int(q):>6} = {cop:>10}kg")
    eng.close()
