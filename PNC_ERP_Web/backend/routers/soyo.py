# -*- coding: utf-8 -*-
"""soyo 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)
try:
    import nx_soyo_engine as _soyo      # 통일 소요엔진(CLAUDE §1-10) — common.py가 _harness를 sys.path에 추가
except Exception:
    _soyo = None

router = APIRouter()

# ================= ★자재소요 정본 엔진 (레거시 STEP5→6→7 충실이식, 수량100%·총량1.00000x 검증) =================
# STEP5 nx.plan_item_dtl(LOT합산·모델→ASSY 유효일자, EXCEPT미적용) → STEP6 nx.plan_part_dtl(10레벨BOM+가공공정 공정전이)
#  → STEP7 nx.plan_part_mat(사급중단 NOT EXISTS PART_DTL + 최하위집계 + charindex중복 + 용접봉sgroup910 제외=공정처리).
# 검증: 설계2건(용접봉·체결SUB이중계상)제외시 웹 vs 레거시 PR_T_PLAN_PART_MAT 수량완전일치100%. [[newerp-plan-soyo-verify]]
_P = "nx."   # ★nx전환 확정(2026-08-12). ★단일BOM 통일(2026-08-13): BOM소스=nx.v_pr_bom(nx.bom_line 단일원본 위 호환뷰, except_flag=PR정합·cs_calc_except=원가). 가공/품목 마스터는 nx복제 유지. r_bomline_soyo_reconcile.py로 소요 PR수렴 검증.

@router.post("/api/plan/compose_mat")
def plan_compose_mat(payload: dict = Body(...)):
    """★은퇴한 편성 경로 — 실행 금지(2026-08-31 가드).

       왜 막는가(실측 사고):
         이 경로와 planrev.py 는 **같은 nx.plan_part_dtl 에 쓰는데 컬럼 구성이 다르다**.
           soyo    19개 컬럼
           planrev 27개 컬럼 (+OUTPUT_HM·AMPM·CUM_LT_HR·PART_PLAN_YMD·PART_OUTPUT_HM·PART_AMPM)
         편성이 테이블을 DROP 후 재생성하므로, 이 경로를 한 번 돌리면 컬럼 6개가 사라지고
         그 컬럼을 참조하는 뷰 nx.v_plan_part_copy_new 가 깨진다
         → 파트별 생산계획(410)·준비실적처리(키팅)·가공생산진척(420) 조회 불가.
         (2026-08-31 실측: 이 함수를 직접 호출해 410 이 "백엔드 연결 실패"로 막혔다)

       정본 = 생산계획업로드[검토] 화면 → planrev.py (/api/planrev/step/*, /compose_all).
       화면도 2026-08-28 에 메뉴에서 숨겨졌다(core.js: SCREEN.planupload).

       되살리려면: 아래 raise 를 지우기 전에 STEP6 이 위 6개 컬럼을 함께 만들도록
                   맞추고, v_plan_part_copy_new 로 검증할 것.
    """
    raise HTTPException(410,
        "은퇴한 편성 경로입니다 — 「생산계획업로드[검토]」 화면을 사용하세요.\n\n"
        "이 경로로 편성하면 nx.plan_part_dtl 의 컬럼 6개(OUTPUT_HM·AMPM·CUM_LT_HR·"
        "PART_PLAN_YMD·PART_OUTPUT_HM·PART_AMPM)가 사라져 뷰 v_plan_part_copy_new 가 깨지고, "
        "파트별 생산계획·준비실적처리(키팅)·가공생산진척 조회가 막힙니다.")

    nx = _nx(); cur = nx.cursor()
    try:
        # ── ★D 사전검증(§19-D·2026-08-25): 활성 지정된 대체경로(Rnn)가 게이트(승인·구조·업체·단가) 미충족이면
        #    생산계획 편성 자체를 중단(어떤 DML도 전·plan_part_mat 미접촉) + 어느 품번/경로가 무엇이 빠졌는지 정확히 통지.
        #    활성 지정 Rnn 없거나(=현행 R01만) 전부 완비면 통과 → 정상 편성. 협력사계획은 plan_part_mat 재사용이라 자연 차단.
        _gate_bad = _route_gate_incomplete(cur)
        if _gate_bad:
            _lines = ["· 품번 {} 경로 R{:02d}{}: {}".format(
                          b["item"], b["route_no"],
                          "(" + b["route_name"] + ")" if b["route_name"] else "",
                          ", ".join(b["missing"])) for b in _gate_bad]
            raise HTTPException(400, "생산계획 편성 불가 — 활성 지정된 대체경로(Rnn) {}건이 미완성입니다.\n".format(len(_gate_bad))
                + "아래 경로를 완료(승인·업체·단가 등록)하거나 현행(R01)로 되돌린 뒤 다시 편성하세요:\n"
                + "\n".join(_lines))
        # ── STEP M 신규모델생성(주문⋈계획 제번조인, use=CEILING(order/lot), 3중제외) ──
        cur.execute("DELETE FROM nx.model_bom WHERE REMARKS='신규모델자동'")
        cur.execute("""INSERT INTO nx.model_bom(MODEL_NO,C_ITEM_CODE,USE_QTY,APPLY_FROM,APPLY_TO,REMARKS,INS_DT)
            SELECT p.model_no, r.item_code,
               MAX(CASE WHEN r.order_qty<p.lot THEN 1 ELSE CEILING(CAST(r.order_qty AS float)/NULLIF(p.lot,0)) END),
               MIN(p.plan_ymd),'999999','신규모델자동',getdate()
            FROM (SELECT RTRIM(MODEL_NO) model_no,WORK_ORDER,MAX(TOTAL_QTY) lot,MIN(PLAN_YMD) plan_ymd
                  FROM nx.plan_dtl WHERE ISNULL(MODEL_NO,'')>'' GROUP BY RTRIM(MODEL_NO),WORK_ORDER) p
            JOIN (SELECT RTRIM(ITEM_CODE) item_code,WORK_ORDER,SUM(ORDER_QTY) order_qty
                  FROM nx.recv_dtl WHERE ISNULL(ITEM_CODE,'')>'' GROUP BY RTRIM(ITEM_CODE),WORK_ORDER) r ON p.WORK_ORDER=r.WORK_ORDER
            WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.PR_M_MODEL_BOM b WHERE b.MODEL_NO=p.model_no AND b.C_ITEM_CODE=r.item_code)
              AND NOT EXISTS(SELECT 1 FROM nx.model_bom m WHERE m.MODEL_NO=p.model_no AND m.C_ITEM_CODE=r.item_code)
              AND NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.PR_M_MODEL_BOM_EXCEPT e WHERE e.MODEL_NO=p.model_no AND e.C_ITEM_CODE=r.item_code)
            GROUP BY p.model_no,r.item_code""")
        # ── STEP5 nx.plan_item_dtl: (제번,모델) LOT합산 → 모델→ASSY 전개(유효일자, ★EXCEPT미적용) ──
        from collections import defaultdict as _dd
        mbom = _dd(list)
        cur.execute("SELECT MODEL_NO,C_ITEM_CODE,USE_QTY,MAKE_YMD,TO_APPLY_YMD FROM PARTNER_ERP_TEST3.nx.PR_M_MODEL_BOM")
        for m, ci, uq, my, ty in cur.fetchall(): mbom[str(m).strip()].append((str(ci).strip(), float(uq or 1), str(my or '').strip(), str(ty or '').strip()))
        cur.execute("SELECT MODEL_NO,C_ITEM_CODE,USE_QTY,APPLY_FROM,APPLY_TO FROM nx.model_bom")
        for m, ci, uq, my, ty in cur.fetchall(): mbom[str(m).strip()].append((str(ci).strip(), float(uq or 1), str(my or '').strip(), str(ty or '').strip()))
        recvmap = _dd(set)
        cur.execute("SELECT DISTINCT WORK_ORDER,ITEM_CODE FROM PARTNER_ERP_TEST3.nx.sa_t_recv_dtl WHERE WORK_ORDER>''")
        for wo, ic in cur.fetchall(): recvmap[str(wo).strip()].add(str(ic).strip())
        prate = {}
        cur.execute("SELECT ITEM_CODE, ISNULL(PROD_RATE,100) FROM PARTNER_ERP_TEST3.nx.item")
        for ic, pr in cur.fetchall(): prate[str(ic).strip()] = float(pr or 100)
        cur.execute("""IF OBJECT_ID('nx.plan_item_dtl') IS NULL CREATE TABLE nx.plan_item_dtl(
            PLAN_YMD varchar(6),WORK_ORDER varchar(20),SPLIT_WORK_ORDER varchar(30),C_ITEM_CODE varchar(20),
            USE_QTY decimal(18,5),LOT_QTY int,PLAN_QTY int,ORG_PLAN_YMD varchar(6),LINE_NO varchar(6),OUTPUT_HM varchar(4),PROD_RATE numeric(9,2))""")
        cur.execute("DELETE FROM nx.plan_item_dtl")
        cur.execute("SELECT WORK_ORDER,MODEL_NO,SUM(CAST(PLAN_QTY AS int)),MIN(PLAN_YMD) FROM nx.plan_dtl WHERE PLAN_QTY>0 GROUP BY WORK_ORDER,MODEL_NO")
        irows = []; lot = _dd(int)
        for wo, model, pq, ymd in cur.fetchall():
            wos = str(wo).strip(); mk = str(model).strip(); pq = int(pq or 0); ymd = str(ymd).strip()
            cand = mbom.get(mk); assys = None
            if cand:
                best = {}
                for a, mq, my, ty in cand:
                    if (not my or my <= ymd) and (not ty or ty >= ymd):
                        if a not in best or my > best[a][1]: best[a] = (mq, my)
                assys = [(a, best[a][0]) for a in best]
            if not assys:
                rc = recvmap.get(wos); assys = [(a, 1.0) for a in rc] if rc else None
            if not assys: continue
            for a, mq in assys:
                irows.append([ymd, wos, wos, a, mq, 0, pq, ymd, '', '0800', prate.get(a, 100)]); lot[wos] = max(lot[wos], pq)
        for rr in irows: rr[5] = lot[rr[1]]
        # ── STEP5-AS: A/S(WO) 계획 앵커 (레거시 compose 3번째 앵커, 우리 누락분 반영) ──
        #   소스=라이브 PR_T_PLAN_INPUT(w_pr_plan_060 수기 A/S/긴급, LINE SVC/AR). ITEM_CODE=완성품 직접(모델매핑 없음),
        #   prod_rate=100(WO 특례, SP substring(work_order,1,2)='WO'), plan_ymd>=생산계획 최소일자(@as_from_ymd).
        #   ★병행기간=라이브 직독(주문 sa_t_recv_dtl 직독과 동일 패턴). 컷오버 후=웹 A/S입력→nx.plan_input.
        cur.execute("SELECT ISNULL(MIN(PLAN_YMD),CONVERT(varchar(6),GETDATE(),12)) FROM nx.plan_dtl WHERE PLAN_QTY>0")
        _asfrom = str(cur.fetchone()[0] or '').strip()
        cur.execute("""SELECT LTRIM(RTRIM(a.WORK_ORDER)) wo, LTRIM(RTRIM(a.ITEM_CODE)) it, SUM(CAST(a.PLAN_QTY AS int)) pq,
                MIN(a.PLAN_YMD) ymd, MAX(ISNULL(a.OUTPUT_HM,'')) ohm, MAX(ISNULL(a.LINE_NO,'')) ln
              FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_INPUT a
              JOIN PARTNER_ERP_TEST3.nx.item c ON LTRIM(RTRIM(a.ITEM_CODE))=c.ITEM_CODE
              WHERE a.PLAN_YMD>=? AND a.PLAN_QTY>0
              GROUP BY LTRIM(RTRIM(a.WORK_ORDER)), LTRIM(RTRIM(a.ITEM_CODE)), a.PLAN_YMD""", _asfrom)
        for wo, it, pq, ymd, ohm, ln in cur.fetchall():
            wos=str(wo).strip(); it=str(it).strip(); pq=int(pq or 0); ymd=str(ymd).strip()
            ohm=(str(ohm).strip() or '0800'); ln=(str(ln or '').strip())[:6]
            # C_ITEM_CODE=ITEM_CODE(직접 assy), USE_QTY=1, LOT_QTY=PLAN_QTY=pq, PROD_RATE=100
            irows.append([ymd, wos, wos, it, 1.0, pq, pq, ymd, ln, ohm, 100])
        cur.fast_executemany = True
        cur.executemany("INSERT INTO nx.plan_item_dtl(PLAN_YMD,WORK_ORDER,SPLIT_WORK_ORDER,C_ITEM_CODE,USE_QTY,LOT_QTY,PLAN_QTY,ORG_PLAN_YMD,LINE_NO,OUTPUT_HM,PROD_RATE) VALUES(?,?,?,?,?,?,?,?,?,?,?)", irows)
        # ── STEP6 nx.plan_part_dtl: 10레벨 BOM전개 → 가공공정 → 공정전이지점 ──
        _step6_sql(cur)
        # ── STEP7 nx.plan_part_mat: 사급중단+최하위집계+charindex+용접봉(sgroup910)제외 ──
        _step7_sql(cur)
        # ── 조달 프로파일 오버레이 → nx.plan_mat_source (공급방식·공급처·수량) ──
        #   ①활성 프로파일 있으면 supply_gubun·vendor·배분(alloc) ②없으면 BOM기본(MAKE_TYPE→매입/사급/외주/자체 + IN_CUST vendor).
        cur.execute("""IF OBJECT_ID('nx.plan_mat_source') IS NULL CREATE TABLE nx.plan_mat_source(
            WORK_ORDER varchar(20),MAT_CODE varchar(20),SUPPLY_GUBUN varchar(20),VENDOR_CODE varchar(20),
            QTY decimal(18,3),SOURCE varchar(10),COMPOSE_DT datetime DEFAULT getdate())""")
        cur.execute("DELETE FROM nx.plan_mat_source")
        MKF = {}; INCF = {}
        cur.execute("SELECT ITEM_CODE, ISNULL(MAKE_TYPE,''), ISNULL(in_cust,'') FROM PARTNER_ERP_TEST3.nx.item")
        for ic, mkt, inc in cur.fetchall(): ic = str(ic).strip(); MKF[ic] = str(mkt).strip(); INCF[ic] = str(inc).strip()
        PRF = {}       # 현행경로(route_id 0/무관) 프로파일: item -> [(sg,v,al)]
        PRF_ALT = {}   # 대안경로(route_id>0) 프로파일: (route_id,item) -> [(sg,v,al)]
        cur.execute("SELECT item_code, supply_gubun, ISNULL(vendor_code,''), ISNULL(alloc_ratio,100), ISNULL(route_id,0) FROM nx.sourcing_profile WHERE is_active=1 AND is_internal=0")
        for ic, sg, v, al, rid in cur.fetchall():
            ic = str(ic).strip(); rid = int(rid or 0)
            (PRF_ALT.setdefault((rid, ic), []) if rid else PRF.setdefault(ic, [])).append((str(sg).strip(), str(v).strip(), float(al or 100)))
        _MKMAP = {'1': '자체', '2': '외주가공', '3': '매입', '4': '유상사급', '5': '외주완성'}  # '자체'=프로파일 라벨과 통일
        # ★경로 배분(nx.route_alloc, 규칙 §8·§9): 조립품(assy)별 활성경로 × route%로 부품수요 분해. ★총량 보존.
        #   현행경로(R01/route_id=0)=기존 로직(프로파일/BOM기본, 업체 재분할은 자동발주 order_vendor 담당).
        #   대안경로(R02+)=route별 프로파일 or 경로헤더 공급처, SOURCE='경로대안'(자동발주 order_vendor 재분할 제외 표식).
        ROUTE = {}     # assy -> [(rid, ratio, iscur)]
        cur.execute("""SELECT LTRIM(RTRIM(a.item_code)), a.route_id, a.alloc_ratio,
              CASE WHEN a.route_id=0 THEN 1 WHEN EXISTS(SELECT 1 FROM nx.sourcing_route r
                 WHERE r.route_id=a.route_id AND (r.current_flag=1 OR r.route_no=1)) THEN 1 ELSE 0 END
            FROM nx.route_alloc a WHERE a.is_active=1 AND a.alloc_ratio IS NOT NULL""")
        for ic, rid, rt, isc in cur.fetchall(): ROUTE.setdefault(str(ic).strip(), []).append((int(rid), float(rt), bool(isc)))
        RHV = {}       # 대안경로 rid -> (헤더공급처, 구분)
        alt_rids = sorted({rid for lst in ROUTE.values() for (rid, _, isc) in lst if not isc and rid != 0})
        if alt_rids:
            rph = ",".join("?" * len(alt_rids))
            cur.execute(f"SELECT route_id, ISNULL(vendor_code,''), ISNULL(gubun,'') FROM nx.sourcing_route WHERE route_id IN ({rph})", *alt_rids)
            for rid, v, g in cur.fetchall(): RHV[int(rid)] = (str(v or '').strip(), str(g or '').strip() or '외주가공')
        cur.execute("SELECT work_order, ISNULL(assy_item_code,''), mat_code, SUM(CAST(part_plan_qty AS float)) FROM nx.plan_part_mat GROUP BY work_order, assy_item_code, mat_code")
        srows = []
        for wo, assy, mat, qty in cur.fetchall():
            wo = str(wo).strip(); assy = str(assy or '').strip(); mat = str(mat).strip(); qty = float(qty or 0)
            routes = ROUTE.get(assy) or [(0, 100.0, True)]
            rsum = sum(rt for _, rt, _ in routes) or 100.0
            for (rid, rt, isc) in routes:
                q = qty * (rt / rsum)
                if isc:                                   # 현행경로: 기존 로직
                    ps = PRF.get(mat)
                    if ps:
                        for sg, v, al in ps: srows.append((wo, mat, sg, v, q * al / 100.0, '프로파일'))
                    else:
                        srows.append((wo, mat, _MKMAP.get(MKF.get(mat, ''), '미지정'), INCF.get(mat, ''), q, 'BOM기본'))
                else:                                     # 대안경로(R02+)
                    pa = PRF_ALT.get((rid, mat))
                    if pa:
                        for sg, v, al in pa: srows.append((wo, mat, sg, v, q * al / 100.0, '경로대안'))
                    else:
                        hv, hg = RHV.get(rid, ('', '외주가공'))
                        srows.append((wo, mat, hg, hv, q, '경로대안'))
        cur.fast_executemany = True
        cur.executemany("INSERT INTO nx.plan_mat_source(WORK_ORDER,MAT_CODE,SUPPLY_GUBUN,VENDOR_CODE,QTY,SOURCE) VALUES(?,?,?,?,?,?)", srows)
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT work_order) FROM nx.plan_part_mat")
        n, woc = cur.fetchone()
        return {"ok": True, "item_lines": len(irows), "mat_lines": int(n), "mat_work_orders": int(woc), "sourcing_lines": len(srows)}
    finally:
        nx.close()

@router.get("/api/plan/sourcing")
def plan_sourcing(mode: str = Query("gubun"), gubun: str = Query(""), vendor: str = Query(""),
                  mat: str = Query(""), wo: str = Query("")):
    """조달 소요 조회. mode=gubun(공급방식별 집계)·vendor(공급처별)·detail(제번×자재 명세)."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.plan_mat_source') IS NULL SELECT 1 WHERE 1=0")
        w = ["1=1"]; p = []
        if gubun.strip(): w.append("s.SUPPLY_GUBUN=?"); p.append(gubun.strip())
        if vendor.strip(): w.append("s.VENDOR_CODE=?"); p.append(vendor.strip())
        if mat.strip(): w.append("s.MAT_CODE LIKE ?"); p.append(f"%{mat.strip()}%")
        if wo.strip(): w.append("s.WORK_ORDER LIKE ?"); p.append(f"%{wo.strip()}%")
        wh = " AND ".join(w)
        try:
            if mode == "vendor":
                cur.execute(f"""SELECT s.SUPPLY_GUBUN, s.VENDOR_CODE, ISNULL(cu.CUST_DESC,'') vname,
                    COUNT(DISTINCT s.MAT_CODE) mats, SUM(s.QTY) qty FROM nx.plan_mat_source s
                    LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu ON s.VENDOR_CODE COLLATE DATABASE_DEFAULT=cu.CUST_CODE COLLATE DATABASE_DEFAULT
                    WHERE {wh} GROUP BY s.SUPPLY_GUBUN, s.VENDOR_CODE, cu.CUST_DESC ORDER BY SUM(s.QTY) DESC""", p)
            elif mode == "detail":
                cur.execute(f"""SELECT TOP 2000 s.WORK_ORDER, s.MAT_CODE, ISNULL(it.item_name,'') mname, s.SUPPLY_GUBUN,
                    s.VENDOR_CODE, ISNULL(cu.CUST_DESC,'') vname, s.QTY, s.SOURCE FROM nx.plan_mat_source s
                    LEFT JOIN PARTNER_ERP_TEST3.nx.item it ON s.MAT_CODE COLLATE DATABASE_DEFAULT=it.ITEM_CODE COLLATE DATABASE_DEFAULT
                    LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu ON s.VENDOR_CODE COLLATE DATABASE_DEFAULT=cu.CUST_CODE COLLATE DATABASE_DEFAULT
                    WHERE {wh} ORDER BY s.QTY DESC""", p)
            else:  # gubun
                cur.execute(f"""SELECT s.SUPPLY_GUBUN, COUNT(DISTINCT s.MAT_CODE) mats, SUM(s.QTY) qty,
                    SUM(CASE WHEN s.SOURCE='프로파일' THEN s.QTY ELSE 0 END) prof_qty FROM nx.plan_mat_source s
                    WHERE {wh} GROUP BY s.SUPPLY_GUBUN ORDER BY SUM(s.QTY) DESC""", p)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            return {"ok": True, "mode": mode, "rows": rows}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200], "rows": []}
    finally:
        nx.close()

def _forecast_plan_gn(cur, b, t):
    """★계획 → gross(차감전=계획) + net(차감후=계획−기출고) 을 도번×일자로 반환.
       레거시 생산계획진척(dw_pr_plan_020) 정본: 남은예상 = 계획 − 기출고(sa_t_sale_dtl.sale_qty − sa_t_item_move move_tag='3'),
       키=제번(work_order)+도번(item_code), finish_flag='0', 일자셀 앞(이른날)에서부터 출고량 소진.
       소스=sa_t_plan_item_dtl(u1, 제번+분할제번+도번 보유)+pr_t_plan_input(u4, 제번+도번). 반환: (days:set, gross:{item:{ymd:q}}, net:{item:{ymd:q}}).
       [[newerp-coop-plan-delivery-formulas]]"""
    from collections import defaultdict
    tc = " AND PLAN_YMD<=?" if t else ""
    params = ([b, t, b, t] if t else [b, b])
    cur.execute(f"""
      SELECT WORK_ORDER wo, LTRIM(RTRIM(C_ITEM_CODE)) it, PLAN_YMD ymd, SUM(CAST(PLAN_QTY AS float)) q
        FROM sa_t_plan_item_dtl WHERE PLAN_YMD>=?{tc} GROUP BY WORK_ORDER, LTRIM(RTRIM(C_ITEM_CODE)), PLAN_YMD
      UNION ALL
      SELECT WORK_ORDER wo, LTRIM(RTRIM(ITEM_CODE)) it, PLAN_YMD ymd, SUM(CAST(PLAN_QTY AS float)) q
        FROM pr_t_plan_input WHERE PLAN_YMD>=?{tc} GROUP BY WORK_ORDER, LTRIM(RTRIM(ITEM_CODE)), PLAN_YMD""", *params)
    plan = defaultdict(lambda: defaultdict(float))   # (wo,item) -> {ymd: qty}
    for wo, it, ymd, q in cur.fetchall():
        plan[(str(wo or '').strip(), str(it).strip())][str(ymd).strip()] += float(q or 0)
    # 기출고 = sale_qty(finish_flag='0') − 출하반품(move_tag='3') by (work_order, item_code)
    ship = defaultdict(float)
    cur.execute("""SELECT WORK_ORDER, LTRIM(RTRIM(ITEM_CODE)), SUM(CAST(SALE_QTY AS float))
        FROM sa_t_sale_dtl WHERE FINISH_FLAG='0' GROUP BY WORK_ORDER, LTRIM(RTRIM(ITEM_CODE))""")
    for wo, it, q in cur.fetchall():
        ship[(str(wo or '').strip(), str(it).strip())] += float(q or 0)
    cur.execute("""SELECT FR_WORK_ORDER, LTRIM(RTRIM(ITEM_CODE)), SUM(CAST(MOVE_QTY AS float))
        FROM sa_t_item_move WHERE MOVE_TAG='3' AND FR_FINISH_FLAG='0' GROUP BY FR_WORK_ORDER, LTRIM(RTRIM(ITEM_CODE))""")
    for wo, it, q in cur.fetchall():
        ship[(str(wo or '').strip(), str(it).strip())] -= float(q or 0)
    # 소진: 제번별 기출고를 이른 일자부터 계획에서 차감
    gross = defaultdict(lambda: defaultdict(float)); net = defaultdict(lambda: defaultdict(float)); days = set()
    for (wo, it), dmap in plan.items():
        s = ship.get((wo, it), 0.0)
        if s < 0: s = 0.0
        for ymd in sorted(dmap):
            q = dmap[ymd]; days.add(ymd)
            gross[it][ymd] += q
            if s >= q: s -= q; rem = 0.0
            else: rem = q - s; s = 0.0
            net[it][ymd] += rem
    return days, gross, net

@router.get("/api/sales/forecast")
def sales_forecast(base: str = Query(""), to: str = Query("")):
    """★영업예상매출현황 라이브 API (레거시 dw_pr_plan_190 재현, 정적스냅샷 대체).
       소스=sa_t_plan_item_dtl(union1)+pr_t_plan_input(union4). 단가=pr_m_item_cost(COST_TAG in S/E=LG판매가, 품목단위 최신, cust무관) KRW.
       gross=차감전(=라이브190). net=차감후=gross − union4(pr_t_plan_input)의 첫계획일 과대분 제거. [[nextgen-erp-sales-forecast-190]]"""
    cn = _conn(); cur = cn.cursor()
    try:
        b = _d6(base) if base.strip() else None
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd')")
        today = str(cur.fetchone()[0])
        b = b or today
        t = _d6(to) if to.strip() else None    # ★기간 종료일. 미지정 시 기본=시작일+1개월(far-future 오염 데이터 방지·기간뷰 기본).
        if not t:
            try:
                import calendar as _cal
                from datetime import datetime as _dt
                d0 = _dt.strptime('20' + b, '%Y%m%d')
                _mo = d0.month % 12 + 1; _yr = d0.year + (1 if d0.month == 12 else 0)
                _dy = min(d0.day, _cal.monthrange(_yr, _mo)[1])
                t = _dt(_yr, _mo, _dy).strftime('%y%m%d')
            except Exception:
                t = None
        tc = " AND PLAN_YMD<=?" if t else ""
        # union1(sa_t_plan_item_dtl) + union4(pr_t_plan_input), item×ymd×src · 기간 base~to
        cur.execute(f"""
          SELECT C_ITEM_CODE item, PLAN_YMD ymd, 'u1' src, SUM(CAST(PLAN_QTY AS float)) q
            FROM sa_t_plan_item_dtl WHERE PLAN_YMD>=?{tc} GROUP BY C_ITEM_CODE, PLAN_YMD
          UNION ALL
          SELECT ITEM_CODE item, PLAN_YMD ymd, 'u4' src, SUM(CAST(PLAN_QTY AS float)) q
            FROM pr_t_plan_input WHERE PLAN_YMD>=?{tc} GROUP BY ITEM_CODE, PLAN_YMD""",
          *([b, t, b, t] if t else [b, b]))
        src = [(str(a).strip(), str(y).strip(), str(s).strip(), float(qq or 0)) for a, y, s, qq in cur.fetchall()]
        if not src:
            return {"base": b, "to": (t or b), "days": [], "rows": []}
        base_ymd = min(y for _, y, _, _ in src)  # 첫 계획일(차감 기준)
        # 단가: COST_TAG in (S,E) 최신 COST_APPLY_YMD, 품목단위(cust무관)
        cur.execute("""SELECT c.ITEM_CODE, c.ITEM_COST FROM pr_m_item_cost c
            JOIN (SELECT ITEM_CODE, MAX(COST_APPLY_YMD) mx FROM pr_m_item_cost WHERE COST_TAG IN('S','E') GROUP BY ITEM_CODE) m
              ON c.ITEM_CODE=m.ITEM_CODE AND c.COST_APPLY_YMD=m.mx WHERE c.COST_TAG IN('S','E')""")
        cost = {}
        for ic, ct in cur.fetchall():
            k = str(ic).strip()
            if k not in cost: cost[k] = float(ct or 0)
        cur.execute("SELECT ITEM_CODE, ISNULL(item_name,''), ISNULL(WORK_CODE,'') FROM PARTNER_ERP_TEST3.nx.item")
        nmm = {}; wcm = {}
        for ic, d, wc in cur.fetchall(): k = str(ic).strip(); nmm[k] = d; wcm[k] = str(wc).strip()
        # 절삭/설치 구분 = nx.item.cut_gubun(품목마스터 속성, 크로스DB). 절삭/설치/분지관/이지링크.
        cutm = {}
        try:
            cur.execute("SELECT item_code, ISNULL(cut_gubun,'') FROM PARTNER_ERP_TEST3.nx.item WHERE cut_gubun>''")
            for ic, g0 in cur.fetchall(): cutm[str(ic).strip().upper()] = str(g0).strip()
        except Exception:
            pass
        agg = {}; days = set()
        for item, ymd, s, qty in src:
            _cut = cutm.get(item.upper(), '')
            if _cut not in ('절삭', '설치'):   # ★절삭/설치만 표시(이지링크·분지관·미분류 제외, 사용자 2026-08-20)
                continue
            days.add(ymd)
            g = agg.get(item)
            if not g:
                g = {"item": item, "nm": nmm.get(item, ""), "wc": wcm.get(item, ""), "cost": cost.get(item, 0),
                     "cut": _cut, "gdays": {}, "ndays": {}}
                agg[item] = g
            g["gdays"][ymd] = g["gdays"].get(ymd, 0) + qty
            if not (s == 'u4' and ymd == base_ymd):   # ★차감: pr_t_plan_input(u4) 첫날분 제외 (레거시190 정본) — 절삭 검증치 보존
                g["ndays"][ymd] = g["ndays"].get(ymd, 0) + qty
        # ★설치(영업 수동계획=pr_t_plan_input)는 위 차감으로 통째 제거됨 → 잔량=Σ_WO(계획−출하실적 SA_T_SALE_DTL)로 재설정. 절삭(LG계획 u1)은 무영향. (사용자 2026-08-20: "출고하고 남은 것만")
        _seol = [it for it in agg if agg[it]["cut"] == '설치']
        if _seol:
            try:
                cur.execute(f"""SELECT x.ITEM_CODE, SUM(CASE WHEN x.pq-x.sh>0 THEN x.pq-x.sh ELSE 0 END) rem FROM (
                    SELECT p.ITEM_CODE, p.WORK_ORDER, SUM(CAST(p.PLAN_QTY AS float)) pq, ISNULL(MAX(s.sh),0) sh
                      FROM pr_t_plan_input p
                      LEFT JOIN (SELECT WORK_ORDER, SUM(CAST(ISNULL(SALE_QTY,0) AS float)) sh FROM sa_t_sale_dtl GROUP BY WORK_ORDER) s ON s.WORK_ORDER=p.WORK_ORDER
                     WHERE p.PLAN_YMD>=?{tc} GROUP BY p.ITEM_CODE, p.WORK_ORDER) x GROUP BY x.ITEM_CODE""",
                    *([b, t] if t else [b]))
                _rem = {str(a).strip(): float(q or 0) for a, q in cur.fetchall()}
                for it in _seol:
                    g = agg[it]; _pday = min(g["gdays"]) if g["gdays"] else base_ymd
                    g["ndays"] = {_pday: _rem.get(it, 0)}   # 설치 잔량(계획−출하)을 계획일에 배치
            except Exception:
                pass
        rows = []
        for g in agg.values():
            gq = sum(g["gdays"].values()); nq = sum(g["ndays"].values()); c = g["cost"]
            g["gq"] = gq; g["nq"] = nq; g["gamt"] = round(gq * c); g["namt"] = round(nq * c)
            rows.append(g)
        return {"base": base_ymd, "to": (t or (max(days) if days else b)), "days": sorted(days), "rows": rows,
                "gross_amt": round(sum(r["gamt"] for r in rows)), "net_amt": round(sum(r["namt"] for r in rows))}
    finally:
        cn.close()

@router.get("/api/sales/forecast_sagub")
def sales_forecast_sagub(base: str = Query(""), to: str = Query("")):
    """★예상 LG사급금액 (영업예상매출현황 '예상 LG사급금액' 구분) — LG사급 2종 중 '사급부품'(원소재 동은 별도).
       사급부품 = 소분류 'LG사급'(ITEM_SGROUP='310'). 완제품 개당 사급금액 = Σ(BOM 사급부품 소요 × COSP 사급가).
       COSP = 품목단가관리 '사급가(업로드)' = nx.price_item(price_type='매입', vendor='LG') 최신(LG 청구 실단가).
       예상금액 = 계획완제품(sa_t_plan_item_dtl u1 + pr_t_plan_input u4) 수량 × 개당사급금액, 일자별.
       gross=차감전, net=차감후(u4 첫계획일 과대분 제거, 라이브190과 동일). 셀=수량, 금액=수량×개당사급금액.
       사급/매출≈35.5%(설치제외 ~40%, 사용자검증). [[nextgen-erp-sales-forecast-190]] [[newerp-install-product-consignment]]"""
    cn = _conn(); cur = cn.cursor()
    try:
        b = _d6(base) if base.strip() else None
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd')"); today = str(cur.fetchone()[0])
        b = b or today
        t = _d6(to) if to.strip() else None
        if not t:
            try:
                import calendar as _cal
                from datetime import datetime as _dt
                d0 = _dt.strptime('20' + b, '%Y%m%d')
                _mo = d0.month % 12 + 1; _yr = d0.year + (1 if d0.month == 12 else 0)
                _dy = min(d0.day, _cal.monthrange(_yr, _mo)[1])
                t = _dt(_yr, _mo, _dy).strftime('%y%m%d')
            except Exception:
                t = None
        tc = " AND PLAN_YMD<=?" if t else ""
        # ★단가 = 완제품 개당 예상 LG사급금액 = Σ(사급부품[소분류310] 소요 × 사급가 COSP), '통째'(사급부품은 분해 안 함).
        #   ★OSP 실측 대사(2026-08-14): material_split(분해)는 실제 사급 대비 과소(15.4↔OSP 21.4억). 사급부품을 통째로 사급가 곱해야 실제 OSP와 정합.
        #   소요=CS_M_ITEM_BOM(조달경로변형 배제), 사급가=nx.price_item(매입/LG) 조회당일 최신. nx.item_sagub_cost 캐시(rebuild=CS×COSP).
        cur.execute("SELECT LTRIM(RTRIM(item_code)), CAST(sa_cost AS float), ISNULL(asof_ymd,'') FROM PARTNER_ERP_TEST3.nx.item_sagub_cost WHERE sa_cost>0")
        sac = {}; asof = ""
        for ic, sc, af in cur.fetchall():
            sac[str(ic).strip()] = float(sc or 0)
            if af and not asof: asof = str(af).strip()
        # 계획 완제품 × 일자 × src (영업예상매출과 동일 소스)
        cur.execute(f"""
          SELECT C_ITEM_CODE item, PLAN_YMD ymd, 'u1' src, SUM(CAST(PLAN_QTY AS float)) q
            FROM sa_t_plan_item_dtl WHERE PLAN_YMD>=?{tc} GROUP BY C_ITEM_CODE, PLAN_YMD
          UNION ALL
          SELECT ITEM_CODE item, PLAN_YMD ymd, 'u4' src, SUM(CAST(PLAN_QTY AS float)) q
            FROM pr_t_plan_input WHERE PLAN_YMD>=?{tc} GROUP BY ITEM_CODE, PLAN_YMD""",
          *([b, t, b, t] if t else [b, b]))
        src = [(str(a).strip(), str(y).strip(), str(s).strip(), float(qq or 0)) for a, y, s, qq in cur.fetchall()]
        src = [r for r in src if r[0] in sac]   # 사급비 보유 완제품만
        if not src:
            return {"base": b, "to": (t or b), "days": [], "rows": [], "gross_amt": 0, "net_amt": 0,
                    "n_parts": 0, "asof": asof, "priced": len(sac)}
        base_ymd = min(y for _, y, _, _ in src)
        cur.execute("SELECT ITEM_CODE, ISNULL(item_name,''), ISNULL(WORK_CODE,'') FROM PARTNER_ERP_TEST3.nx.item")
        nmm = {}; wcm = {}
        for ic, d, wc in cur.fetchall(): k = str(ic).strip(); nmm[k] = d; wcm[k] = str(wc).strip()
        cutm = {}
        try:
            cur.execute("SELECT item_code, ISNULL(cut_gubun,'') FROM PARTNER_ERP_TEST3.nx.item WHERE cut_gubun>''")
            for ic, g0 in cur.fetchall(): cutm[str(ic).strip().upper()] = str(g0).strip()
        except Exception:
            pass
        agg = {}; days = set()
        for item, ymd, s, qty in src:
            days.add(ymd)
            g = agg.get(item)
            if not g:
                g = {"item": item, "nm": nmm.get(item, ""), "wc": wcm.get(item, ""), "cost": sac.get(item, 0),
                     "cut": cutm.get(item.upper(), ""), "gdays": {}, "ndays": {}}
                agg[item] = g
            g["gdays"][ymd] = g["gdays"].get(ymd, 0) + qty
            if not (s == 'u4' and ymd == base_ymd):
                g["ndays"][ymd] = g["ndays"].get(ymd, 0) + qty
        rows = []
        for g in agg.values():
            gq = sum(g["gdays"].values()); nq = sum(g["ndays"].values()); c = g["cost"]
            g["gq"] = gq; g["nq"] = nq; g["gamt"] = round(gq * c); g["namt"] = round(nq * c)  # 금액 = 수량 × 개당사급금액
            rows.append(g)
        rows.sort(key=lambda r: -r["gamt"])
        return {"base": base_ymd, "to": (t or (max(days) if days else b)), "days": sorted(days), "rows": rows,
                "gross_amt": round(sum(r["gamt"] for r in rows)), "net_amt": round(sum(r["namt"] for r in rows)),
                "n_parts": len(rows), "asof": asof, "priced": len(sac)}
    finally:
        cn.close()

@router.post("/api/sales/forecast_sagub/rebuild")
def sales_forecast_sagub_rebuild():
    """완제품별 개당 예상 LG사급금액 = Σ(사급부품[소분류310] 소요 × 사급가 COSP) '통째' 캐시 재계산 → nx.item_sagub_cost.
       ★OSP 실측 대사(2026-08-14): 사급부품을 분해(material_split)하면 실제보다 과소 → 통째로 사급가 곱해야 실제 OSP 정합.
       소요=CS_M_ITEM_BOM(조달경로변형 배제), 사급가=nx.price_item(매입/LG) 조회당일 최신. 대상=계획완제품(260101+) 중 사급부품 보유. 수분 소요."""
    nx = _nx(); cur = nx.cursor()
    try:
        import time as _t
        asof = _t.strftime('%y%m%d')
        cur.execute("""IF OBJECT_ID('nx.item_sagub_cost') IS NULL
            CREATE TABLE nx.item_sagub_cost(item_code varchar(50) PRIMARY KEY, sa_cost float, asof_ymd varchar(8), upd_dt datetime)""")
        cur.execute("SELECT DISTINCT UPPER(LTRIM(RTRIM(ITEM_CODE))) FROM PARTNER_ERP_TEST3.nx.item WHERE LTRIM(RTRIM(sgroup))='310'")
        sag = set(x[0] for x in cur.fetchall())   # ★대문자(엔진 stop_set·반환 대문자 정합)
        cur.execute("SELECT it,price FROM (SELECT UPPER(LTRIM(RTRIM(item_code))) it,price,ROW_NUMBER() OVER(PARTITION BY item_code ORDER BY apply_ymd DESC) rn FROM nx.price_item WHERE price_type=N'매입' AND vendor_code='LG') x WHERE rn=1")
        cosp = {a: float(b or 0) for a, b in cur.fetchall()}
        # ★후보 = 계획 완제품 전체(260101+). 구 ad-hoc bom_line 재귀CTE 후보필터는 소요엔진(v_pr_bom)과
        #   불일치로 일부 완제품 누락(실측 ADM72950707 사급 532,650 누락) → 폐기. 사급부품 도달 여부는
        #   엔진 sagub_parts_soyo가 정확 판정(비도달=빈dict=0). §1-10 완전 준수(후보찾기도 엔진 소스).
        #   ★컷오버 flip: 계획 원천도 nx로(레거시 동결 대비).
        cur.execute("""SELECT DISTINCT item FROM (
            SELECT UPPER(LTRIM(RTRIM(C_ITEM_CODE))) item FROM PARTNER_ERP_TEST3.nx.sa_t_plan_item_dtl WHERE PLAN_YMD>='260101'
            UNION SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) FROM PARTNER_ERP_TEST3.nx.pr_t_plan_input WHERE PLAN_YMD>='260101') u
            WHERE item IS NOT NULL AND item<>''""")
        cand = [str(r[0]).strip().upper() for r in cur.fetchall()]
        # ★소요엔진 이관(CLAUDE §1-10, 2026-08-29): 사급부품 소요 = nx_soyo_engine.sagub_parts_soyo
        #   (v_pr_bom·except≠1·310 사급부품 도달 시 '통째' 계상·정지). 구 ad-hoc CS_M_ITEM_BOM 재귀CTE는
        #   변형SUB 이중계상 + cs_calc(원가축) 오혼입 → 폐기. 옆에짓고 검증(514 후보): 502 동일·12 과다분 제거
        #   (변형SUB 이중계상 11 + flag축 1[AJR30073601 except_flag=1 외주완성=우리사급 아님])·총 −0.41%.
        eng = _get_cost_engine(); _soyo.warm_vpr(eng); _memo = {}
        done = 0; nz = 0; tot = 0.0
        for it in cand:
            pm = _soyo.sagub_parts_soyo(eng, it, sag, _memo)   # {310부품(대문자): 소요개수} — 하위 사급부품만
            unit = sum(per * cosp[p] for p, per in pm.items() if p in cosp)
            if it in sag:                          # ★완제품 자체가 310 사급부품(직접 계획분·스페어 등)이면 자신 COSP '통째' 포함
                unit += cosp.get(it, 0.0)          #   (sagub_parts_soyo는 하위만 계상→자기자신 누락=under-count 보정, 실측 91/93 옛값=자기COSP 일치)
            cur.execute("""MERGE nx.item_sagub_cost t USING (SELECT ? item_code) s ON t.item_code=s.item_code
                WHEN MATCHED THEN UPDATE SET sa_cost=?, asof_ymd=?, upd_dt=getdate()
                WHEN NOT MATCHED THEN INSERT(item_code,sa_cost,asof_ymd,upd_dt) VALUES(?,?,?,getdate());""",
                it, unit, asof, it, unit, asof)
            done += 1; tot += unit
            if unit > 0: nz += 1
        nx.commit()
        return {"ok": True, "asof": asof, "computed": done, "with_sagub": nz, "sum_unit_sacost": round(tot)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    finally:
        nx.close()

def _step6_sql(cur):
    """★은퇴 — 직접 호출 금지(2026-08-31 2차 가드).

       1차 가드는 엔드포인트 plan_compose_mat 에만 걸어 두었는데, 이 **내부 함수는
       그대로 노출**돼 있어 스크립트에서 직접 부르면 그대로 실행됐다.
       실제로 그날 09:09 정상 편성(27컬럼) 이후 작업로그에 아무 기록 없이
       nx.plan_part_dtl 이 19컬럼으로 되돌아가 파트별 생산계획(410)이 0건이 됐다
       (편성 로그를 남기지 않는 = 웹 편성 화면이 아닌 경로로 불렸다는 뜻).
       → 함수 진입에서 막는다. 정본은 planrev._step6_sql(27컬럼).

       ※같은 이유로 _step7_sql 도 planrev 쪽을 쓸 것."""
    raise RuntimeError(
        "은퇴한 편성 함수입니다(soyo._step6_sql) — planrev 를 쓰세요.\n"
        "이 함수는 nx.plan_part_dtl 을 19컬럼으로 재생성해 뷰 v_plan_part_copy_new 를 깨뜨리고, "
        "파트별 생산계획·준비실적처리(키팅)·가공생산진척 조회를 막습니다.\n"
        "정본 = routers/planrev.py 의 _step6_sql (27컬럼) · 화면 「생산계획업로드[검토]」")

    P = _P
    _route_setup(cur)   # ★P6: plan_route_active(활성 R02) 준비 — 공정 route-aware 오버레이용. STEP7도 재호출(멱등·동일결과)
    cur.execute("IF OBJECT_ID('nx.plan_part_temp') IS NOT NULL DROP TABLE nx.plan_part_temp")
    cur.execute(("""
    WITH CTE_BOM(assy_item_code, level_no, item_code, p_item_code, mat_code, cum_use_qty, in_cust_code, vir_item_flag, cum_item_code) AS (
      SELECT DISTINCT a.c_item_code,0,a.c_item_code,a.c_item_code,a.c_item_code,CONVERT(decimal(18,5),1),ISNULL(c.in_cust,''),'0',CONVERT(varchar(500),'{'+a.c_item_code+'}')
      FROM nx.plan_item_dtl a JOIN {P}item c ON a.c_item_code=c.item_code
      WHERE NOT EXISTS(SELECT 1 FROM {P}PR_M_MAT WHERE mat_code=a.c_item_code)
      UNION ALL
      SELECT cb.assy_item_code,cb.level_no+1,b.item_code,CASE cb.vir_item_flag WHEN '1' THEN cb.p_item_code ELSE b.item_code END,
             b.mat_code,CONVERT(decimal(18,5),cb.cum_use_qty*b.USE_QTY_PR),ISNULL(c.in_cust,''),
             CASE b.vir_item_flag WHEN '1' THEN '1' ELSE '0' END,CONVERT(varchar(500),cb.cum_item_code+'{'+b.mat_code+'}')
      FROM CTE_BOM cb JOIN {P}v_pr_bom b ON cb.mat_code=b.item_code JOIN {P}item c ON b.mat_code=c.item_code
      WHERE ISNULL(b.except_flag,'0')<>'1' AND cb.level_no<10 AND NOT EXISTS(SELECT 1 FROM {P}PR_M_MAT WHERE mat_code=b.mat_code))
    SELECT assy_item_code,level_no,item_code,MAX(p_item_code) p_item_code,mat_code,SUM(cum_use_qty) cum_use_qty,MAX(in_cust_code) in_cust_code,MAX(vir_item_flag) vir_item_flag
    INTO nx.plan_part_temp FROM CTE_BOM GROUP BY assy_item_code,level_no,item_code,mat_code OPTION(MAXRECURSION 0)""").replace("{P}", P))
    cur.execute("IF OBJECT_ID('nx.plan_part_gagong') IS NOT NULL DROP TABLE nx.plan_part_gagong")
    # ★P6 공정 route-aware(생산정보 route별 소비): 활성 route(plan_route_active)를 가진 ASSY의 부품이
    #   그 route의 생산정보(route_proc_gagong)를 보유하면 그것을, 아니면 현행 PR_M_ITEM_PROC_GAGONG를 사용.
    #   ★identity-safe: 활성 route 없으면(plan_route_active 비면) CASE=0 → route_id=0(=PR_M_ITEM_PROC_GAGONG)만 조인
    #     = 현행과 byte동일(route_proc_gagong 행은 route_id>0라 CASE=0에 미매치). 검증=P6 diff0 게이트.
    cur.execute(("""SELECT a.assy_item_code,a.level_no,a.item_code,a.mat_code,a.p_item_code,a.vir_item_flag,b.proc_seq,g.gc_gubun,a.cum_use_qty,s.gagong_proc_code,b.gagong_proc_seq,b.s_work_code,ISNULL(b.lt_hr,0) lt_hr
    INTO nx.plan_part_gagong FROM nx.plan_part_temp a
    LEFT JOIN nx.plan_route_active pra ON pra.assy_item_code=a.assy_item_code
    JOIN (
        SELECT item_code, CAST(0 AS INT) route_id, proc_seq, s_work_code, gagong_proc_seq, lt_hr FROM {P}PR_M_ITEM_PROC_GAGONG
        UNION ALL
        SELECT item_code, route_id, proc_seq, s_work_code, gagong_proc_seq, lt_hr FROM nx.route_proc_gagong
    ) b ON a.mat_code=b.item_code
       AND b.route_id = CASE WHEN pra.route_id IS NOT NULL
             AND EXISTS(SELECT 1 FROM nx.route_proc_gagong x WHERE x.route_id=pra.route_id AND x.item_code=a.mat_code)
           THEN pra.route_id ELSE 0 END
    JOIN {P}PR_M_WORK_SINGLE s ON b.s_work_code=s.s_work_code JOIN {P}PR_M_PROC_GAGONG g ON s.gagong_proc_code=g.gagong_proc_code
    WHERE a.vir_item_flag='0' AND ISNULL(a.in_cust_code,'') IN ('','2228')""").replace("{P}", P))
    cur.execute("IF OBJECT_ID('nx.plan_part_swork') IS NOT NULL DROP TABLE nx.plan_part_swork")
    cur.execute(("""SELECT b.plan_ymd,b.work_order,b.split_work_order,a.assy_item_code,a.level_no AS bom_level,a.item_code AS upper_item_code,a.mat_code AS item_code,a.p_item_code,a.proc_seq,a.gc_gubun,
      b.line_no,a.cum_use_qty AS use_qty,b.lot_qty,CEILING(CONVERT(float,b.plan_qty)*ISNULL(b.use_qty,1)*ISNULL(CASE WHEN b.work_order LIKE 'WO%' THEN 100 ELSE c.prod_rate END,100)/100) AS plan_qty,
      a.gagong_proc_code,a.gagong_proc_seq,a.s_work_code,a.lt_hr,CEILING(CONVERT(float,b.plan_qty)*ISNULL(b.use_qty,1)*ISNULL(CASE WHEN b.work_order LIKE 'WO%' THEN 100 ELSE c.prod_rate END,100)/100)*a.cum_use_qty AS part_plan_qty
    INTO nx.plan_part_swork FROM nx.plan_part_gagong a JOIN nx.plan_item_dtl b ON a.assy_item_code=b.c_item_code JOIN {P}item c ON a.assy_item_code=c.item_code""").replace("{P}", P))
    cur.execute("IF OBJECT_ID('nx.plan_part_dtl') IS NOT NULL DROP TABLE nx.plan_part_dtl")
    cur.execute("""SELECT a.* INTO nx.plan_part_dtl FROM nx.plan_part_swork a
      WHERE a.gagong_proc_code <> ISNULL((SELECT TOP 1 b.gagong_proc_code FROM nx.plan_part_swork b
        WHERE b.plan_ymd=a.plan_ymd AND b.work_order=a.work_order AND b.split_work_order=a.split_work_order AND b.assy_item_code=a.assy_item_code
          AND b.bom_level=a.bom_level AND b.upper_item_code=a.upper_item_code AND b.item_code=a.item_code AND b.proc_seq<a.proc_seq ORDER BY b.proc_seq DESC),'')""")

# ★★활성 게이트(§19-C·2026-08-25 사용자 확정): 활성 지정 Rnn(current_flag=1·route_no>1)이 아래 4개 다 갖춰야 계획 활성.
#   ①승인 approve_flag=1 ②구조 route_edges ③업체 sourcing_profile.vendor ④단가 buy_price/sagub_price.
#   ★한 곳 정의(_ROUTE_GATE_SQL) → _route_setup(생산·협력사 plan_route_active)·_route_gate_incomplete(편성 사전검증 D)·원가 공유.
#   미완성 Rnn은 어디서도 안 켜짐 → R01(route_no=1) 현행 그대로. h=nx.sourcing_route 별칭 전제.
_ROUTE_GATE_SQL = """ISNULL(h.approve_flag,0)=1
      AND EXISTS(SELECT 1 FROM nx.route_edges re WHERE re.route_id=h.route_id)
      AND EXISTS(SELECT 1 FROM nx.sourcing_profile p WHERE p.route_id=h.route_id AND ISNULL(p.vendor_code,'')<>'')
      AND EXISTS(SELECT 1 FROM nx.sourcing_profile p WHERE p.route_id=h.route_id AND (p.buy_price IS NOT NULL OR p.sagub_price IS NOT NULL))
      AND EXISTS(SELECT 1 FROM nx.route_proc_gagong rp WHERE rp.route_id=h.route_id)"""


def _ensure_profile_price(cur):
    """게이트 SQL이 참조하는 sourcing_profile 단가컬럼 멱등 보장(신선 nx 대비)."""
    cur.execute("IF OBJECT_ID('nx.sourcing_profile','U') IS NOT NULL AND COL_LENGTH('nx.sourcing_profile','buy_price') IS NULL ALTER TABLE nx.sourcing_profile ADD buy_price FLOAT NULL")
    cur.execute("IF OBJECT_ID('nx.sourcing_profile','U') IS NOT NULL AND COL_LENGTH('nx.sourcing_profile','sagub_price') IS NULL ALTER TABLE nx.sourcing_profile ADD sagub_price FLOAT NULL")


def _ensure_route_proc(cur):
    """★P4 게이트/STEP6이 참조하는 route별 생산정보(생산 ST축 route확장) 테이블 멱등 보장.
       prodinfo.py _ensure_route_proc와 동일 스키마(route_id+품번+proc_seq 키). 게이트/편성 파싱 안전."""
    cur.execute("""IF OBJECT_ID('nx.route_proc_gagong') IS NULL CREATE TABLE nx.route_proc_gagong(
        route_id INT, item_code varchar(20), proc_seq tinyint, work_code varchar(10), gagong_proc_code varchar(10),
        s_work_code smallint, mach_code varchar(10), work_qty decimal(18,5), std_size varchar(100), mix_gagong tinyint,
        gagong_proc_flag varchar(1), gagong_proc_seq tinyint, ready_st decimal(18,5), mach_ct decimal(18,5), inwon tinyint,
        human_st decimal(18,5), tot_st decimal(18,5), jp_proc_method varchar(1), lt_hr decimal(18,5), key_id int,
        upd_user varchar(30), upd_at datetime DEFAULT getdate(),
        CONSTRAINT pk_route_proc_gagong PRIMARY KEY(route_id, item_code, proc_seq))""")


def _route_gate_incomplete(cur):
    """★D 사전검증(§19-D): 활성 지정된 Rnn(route_alloc.is_active=1·route_no>1) 중 게이트(§19-C) 미충족 목록+사유.
       ★활성지정 단일소스 = nx.route_alloc.is_active(조달프로파일 택1) — _route_setup과 동일 스위치.
       반환 [{route_id,item,route_no,route_name,missing[]}]. 편성(compose)이 이걸로 업로드 실패·정확 메시지·중단."""
    _ensure_profile_price(cur)
    _ensure_route_proc(cur)   # ★P4: 생산정보 존재 게이트가 참조 — 파싱 안전
    cur.execute("""IF OBJECT_ID('nx.route_alloc','U') IS NULL CREATE TABLE nx.route_alloc(
        item_code NVARCHAR(60) NOT NULL, route_id INT NOT NULL, apply_from DATE NULL, apply_to DATE NULL,
        is_active BIT DEFAULT 0, alloc_ratio FLOAT NULL, upd_dt datetime DEFAULT getdate(),
        CONSTRAINT PK_nx_route_alloc PRIMARY KEY(item_code, route_id))""")
    cur.execute("""SELECT h.route_id, LTRIM(RTRIM(h.item_code)), ISNULL(h.route_no,1), ISNULL(h.route_name,''),
          ISNULL(h.approve_flag,0),
          (SELECT COUNT(*) FROM nx.route_edges re WHERE re.route_id=h.route_id),
          (SELECT COUNT(*) FROM nx.sourcing_profile p WHERE p.route_id=h.route_id AND ISNULL(p.vendor_code,'')<>''),
          (SELECT COUNT(*) FROM nx.sourcing_profile p WHERE p.route_id=h.route_id AND (p.buy_price IS NOT NULL OR p.sagub_price IS NOT NULL)),
          (SELECT COUNT(*) FROM nx.route_proc_gagong rp WHERE rp.route_id=h.route_id)
        FROM nx.sourcing_route h
        JOIN nx.route_alloc ra ON ra.route_id=h.route_id AND ISNULL(ra.is_active,0)=1
        WHERE ISNULL(h.route_no,1)>1""")
    bad = []
    for rid, item, rno, rname, appr, ne, nv, npx, nproc in cur.fetchall():
        miss = []
        if not int(appr or 0): miss.append("미승인")
        if not int(ne or 0): miss.append("구조 미반영(저장 안 됨)")
        if not int(nv or 0): miss.append("업체 미지정")
        if not int(npx or 0): miss.append("단가 미지정")
        if not int(nproc or 0): miss.append("생산정보 미등록")   # ★P4 요구5: R02 생산정보 필수(없으면 편성 불가)
        if miss:
            bad.append({"route_id": int(rid), "item": str(item).strip(), "route_no": int(rno),
                        "route_name": str(rname).strip(), "missing": miss})
    return bad


def _route_setup(cur):
    """★조달경로 반영 인프라(2026-08-24, 게이트강화 2026-08-25, ★활성소스 통일 2026-08-31). 매일 rebuild(compose_mat)에서 STEP7 직전 호출.
    - nx.route_edges(route_id,item_code,mat_code,use_qty_pr): 경로별 BOM엣지(Rnn 저장시 자동등록·§19-A). 없으면 fallback.
    - nx.plan_route_active(assy_item_code,route_id): ★활성 게이트(§19-C) 통과한 Rnn만.
      ★활성지정 단일소스 = nx.route_alloc.is_active(조달프로파일 택1 라디오). 구조축(여기)·배분축(plan_mat_source)이 동일 스위치를 본다.
      (이전엔 sourcing_route.current_flag로 게이팅했으나 그 컬럼을 켜는 R02 UI가 없어 반영불가 + plan_mat_source에선 current_flag=1이 'R01 취급'으로 겹침
       → route_alloc.is_active로 통일. 조달프로파일 택1이 곧 계획 활성.) route_no>1 + 게이트(승인·route_edges·업체·단가·생산정보) 통과분만.
      기본 비어있음=전 제품 v_pr_bom(현행) 그대로=R01 diff0(가산적). ★안전=활성경로 없으면 STEP7 출력 현행과 byte동일(검증 300WO 100.000%)."""
    _ensure_profile_price(cur)
    _ensure_route_proc(cur)   # ★P4: _ROUTE_GATE_SQL이 route_proc_gagong 참조 — 파싱 안전
    cur.execute("""IF OBJECT_ID('nx.route_alloc','U') IS NULL CREATE TABLE nx.route_alloc(
        item_code NVARCHAR(60) NOT NULL, route_id INT NOT NULL, apply_from DATE NULL, apply_to DATE NULL,
        is_active BIT DEFAULT 0, alloc_ratio FLOAT NULL, upd_dt datetime DEFAULT getdate(),
        CONSTRAINT PK_nx_route_alloc PRIMARY KEY(item_code, route_id))""")   # ★활성소스 — 없으면 활성경로 0 = R01 현행 diff0
    # ★타입=plan_part_dtl.item_code(varchar20)·v_pr_bom.mat_code(varchar20) 정합(재귀CTE 앵커 타입일치 필수). nvarchar 쓰면 STEP7 재귀 타입불일치 오류.
    cur.execute("""IF OBJECT_ID('nx.route_edges','U') IS NULL CREATE TABLE nx.route_edges(
        route_id INT NOT NULL, item_code varchar(20) NOT NULL, mat_code varchar(20) NOT NULL,
        use_qty_pr FLOAT NOT NULL DEFAULT 1, CONSTRAINT ix_route_edges UNIQUE(route_id,item_code,mat_code))""")
    cur.execute("IF OBJECT_ID('nx.plan_route_active','U') IS NOT NULL DROP TABLE nx.plan_route_active")
    cur.execute("""SELECT DISTINCT UPPER(LTRIM(RTRIM(h.item_code))) AS assy_item_code, MIN(h.route_id) AS route_id
        INTO nx.plan_route_active FROM nx.sourcing_route h
        JOIN nx.route_alloc ra ON ra.route_id=h.route_id AND ISNULL(ra.is_active,0)=1
        WHERE ISNULL(h.route_no,1)>1
          AND """ + _ROUTE_GATE_SQL + """
        GROUP BY UPPER(LTRIM(RTRIM(h.item_code)))""")
    cur.execute("IF OBJECT_ID('nx.plan_route_active','U') IS NOT NULL AND NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='ix_pra') CREATE INDEX ix_pra ON nx.plan_route_active(assy_item_code)")

def _step7_sql(cur):
    """★은퇴 — 직접 호출 금지(2026-08-31 2차 가드). _step6_sql 과 같은 이유.
       정본 = routers/planrev.py 의 _step7_sql."""
    raise RuntimeError(
        "은퇴한 편성 함수입니다(soyo._step7_sql) — planrev 를 쓰세요.\n"
        "정본 = routers/planrev.py · 화면 「생산계획업로드[검토]」")

    P = _P
    # ★routing_edge 생산처 오버라이드(2026-08-20): STEP7 work_center(생산처)를 마스터 대신
    #   routing_edge.wc(편집가능 정본)에서 읽음. ov_wc=ISNULL(routing_edge.wc, 마스터 default).
    #   routing_edge 미등록 아이템은 마스터 폴백. compose는 읽기만(편집 보존) — 시드/싱크는 별도.
    #   재귀 CTE는 TOP/outer join 금지 → 오버라이드 테이블 nx.item_ov를 inner join으로 갈아끼움.
    cur.execute("IF OBJECT_ID('nx.item_ov') IS NOT NULL DROP TABLE nx.item_ov")
    cur.execute(("""SELECT c.item_code, c.work_code, c.in_cust, c.prod_rate,
        ISNULL(NULLIF(re.wc,''), CASE WHEN c.work_code>'' THEN c.work_code ELSE ISNULL(c.in_cust,'') END) AS ov_wc
      INTO nx.item_ov FROM {P}item c
      LEFT JOIN (SELECT child_item, MAX(wc) wc FROM nx.routing_edge GROUP BY child_item) re
        ON re.child_item=UPPER(LTRIM(RTRIM(c.item_code)))""").replace("{P}", P))
    cur.execute("CREATE INDEX ix_item_ov ON nx.item_ov(item_code)")
    # ★★조달경로(route) 반영 인프라(2026-08-24, 가산적): 활성 대체경로(sourcing_route current_flag=1·route_no>1) 있으면
    #   그 경로의 BOM엣지(route_edges)로 전개, 없으면 v_pr_bom(현행 except<>1) fallback=R01 diff0(검증: route CTE≡원본 100.000%).
    _route_setup(cur)
    cur.execute("IF OBJECT_ID('nx.plan_part_mat_tmp') IS NOT NULL DROP TABLE nx.plan_part_mat_tmp")
    cur.execute(("""
    WITH CTE_BOM(plan_ymd,work_order,split_work_order,assy_item_code,bom_level,upper_item_code,item_code,proc_seq,bom_mat_code,mat_work_center_code,cum_use_qty,cum_in_cust_code,mat_flag,use_qty,part_plan_qty,gc_gubun,cust_flag) AS (
      SELECT a.plan_ymd,a.work_order,a.split_work_order,a.assy_item_code,a.bom_level,a.upper_item_code,a.item_code,a.proc_seq,a.item_code,
         c.ov_wc,CONVERT(decimal(18,5),a.use_qty),
         CONVERT(varchar(500),'||'+c.ov_wc+'|'),'1',a.use_qty,CONVERT(float,a.part_plan_qty)/NULLIF(a.use_qty,0),a.gc_gubun,'0'
      FROM nx.plan_part_dtl a JOIN nx.item_ov c ON a.item_code=c.item_code WHERE a.proc_seq=1
      UNION ALL
      SELECT a.plan_ymd,a.work_order,a.split_work_order,a.c_item_code,0,a.c_item_code,a.c_item_code,1,a.c_item_code,
         c.ov_wc,CONVERT(decimal(18,5),a.use_qty),
         CONVERT(varchar(500),'||'+c.ov_wc+'|'),'1',a.use_qty,CEILING(CONVERT(float,a.plan_qty)*ISNULL(a.use_qty,1)*ISNULL(CASE WHEN a.work_order LIKE 'WO%' THEN 100 ELSE c.prod_rate END,100)/100),'','1'
      FROM nx.plan_item_dtl a JOIN nx.item_ov c ON a.c_item_code=c.item_code
      WHERE NOT EXISTS(SELECT 1 FROM nx.plan_part_dtl d WHERE d.work_order=a.work_order AND d.split_work_order=a.split_work_order AND d.item_code=a.c_item_code)
      UNION ALL
      SELECT cb.plan_ymd,cb.work_order,cb.split_work_order,cb.assy_item_code,cb.bom_level,cb.upper_item_code,cb.item_code,cb.proc_seq,b.mat_code,
         m.ov_wc,CONVERT(decimal(18,5),CASE WHEN cb.cum_use_qty=0 THEN 0 ELSE cb.cum_use_qty*b.USE_QTY_PR END),
         CONVERT(varchar(500),cb.cum_in_cust_code+'|'+m.ov_wc+'|'),
         ISNULL((SELECT '2' FROM {P}PR_M_MAT WHERE mat_code=b.mat_code),'1'),cb.use_qty,cb.part_plan_qty,'','1'
      FROM CTE_BOM cb JOIN {P}v_pr_bom b ON cb.bom_mat_code=b.item_code JOIN nx.item_ov m ON b.mat_code=m.item_code
      WHERE ISNULL(b.except_flag,'0')<>'1'
        AND NOT EXISTS(SELECT 1 FROM nx.plan_route_active pra WHERE pra.assy_item_code=cb.assy_item_code)   -- ★가드: 활성 대체경로 없는 제품만 v_pr_bom(현행)
        AND NOT EXISTS(SELECT 1 FROM nx.plan_part_dtl d WHERE d.plan_ymd=cb.plan_ymd AND d.work_order=cb.work_order AND d.split_work_order=cb.split_work_order
            AND d.assy_item_code=cb.assy_item_code AND d.bom_level=cb.bom_level+1 AND d.upper_item_code=b.item_code AND d.item_code=b.mat_code)
      UNION ALL
      -- ★★route-active 브랜치: 활성 대체경로(Rnn) 있는 제품은 그 경로의 route_edges로 전개(except_flag 무관·route가 활성엣지만 보유)
      SELECT cb.plan_ymd,cb.work_order,cb.split_work_order,cb.assy_item_code,cb.bom_level,cb.upper_item_code,cb.item_code,cb.proc_seq,b.mat_code,
         m.ov_wc,CONVERT(decimal(18,5),CASE WHEN cb.cum_use_qty=0 THEN 0 ELSE cb.cum_use_qty*b.use_qty_pr END),
         CONVERT(varchar(500),cb.cum_in_cust_code+'|'+m.ov_wc+'|'),
         ISNULL((SELECT '2' FROM {P}PR_M_MAT WHERE mat_code=b.mat_code),'1'),cb.use_qty,cb.part_plan_qty,'','1'
      FROM CTE_BOM cb
        JOIN nx.plan_route_active pra ON pra.assy_item_code=cb.assy_item_code
        JOIN nx.route_edges b ON b.route_id=pra.route_id AND b.item_code=cb.bom_mat_code
        JOIN nx.item_ov m ON b.mat_code=m.item_code
      WHERE NOT EXISTS(SELECT 1 FROM nx.plan_part_dtl d WHERE d.plan_ymd=cb.plan_ymd AND d.work_order=cb.work_order AND d.split_work_order=cb.split_work_order
            AND d.assy_item_code=cb.assy_item_code AND d.bom_level=cb.bom_level+1 AND d.upper_item_code=b.item_code AND d.item_code=b.mat_code))
    SELECT * INTO nx.plan_part_mat_tmp FROM CTE_BOM
    WHERE CHARINDEX('||'+mat_work_center_code+'||',cum_in_cust_code)=0 AND NOT (cust_flag='0' AND gc_gubun='P') OPTION(MAXRECURSION 0)""").replace("{P}", P))
    cur.execute("IF OBJECT_ID('nx.plan_part_mat') IS NOT NULL DROP TABLE nx.plan_part_mat")
    # 최하위집계 + ★용접봉(RAC, proc_weld 별도)만 제외. ★2026-08-19 교정: 레거시 SP엔 sgroup910 제외 없음 →
    #   910 일괄제외는 우리 오추가(4930 등 910 오분류 실 매입부품까지 제외). RAC(용접봉)만 공정처리로 제외, 용접링은 사급으로 유지(RACX 일치).
    cur.execute(("""SELECT a.plan_ymd,a.work_order,a.split_work_order,a.assy_item_code,a.bom_level,a.upper_item_code,a.item_code,a.proc_seq,a.bom_mat_code AS mat_code,
        SUM(a.part_plan_qty*a.cum_use_qty) AS part_plan_qty,MAX(a.mat_flag) mat_flag,MAX(a.mat_work_center_code) mat_work_center_code
    INTO nx.plan_part_mat FROM nx.plan_part_mat_tmp a
    WHERE NOT EXISTS(SELECT 1 FROM nx.plan_part_mat_tmp d WHERE d.work_order=a.work_order AND d.split_work_order=a.split_work_order AND d.assy_item_code=a.assy_item_code AND d.bom_level>a.bom_level AND d.bom_mat_code=a.bom_mat_code)
      AND NOT EXISTS(SELECT 1 FROM {P}item wj WHERE wj.item_code=a.bom_mat_code AND wj.item_code LIKE 'RAC%' AND ISNULL(wj.item_name,'') NOT LIKE N'%용접링%')
    GROUP BY a.plan_ymd,a.work_order,a.split_work_order,a.assy_item_code,a.bom_level,a.upper_item_code,a.item_code,a.proc_seq,a.bom_mat_code""").replace("{P}", P))

def _routing_edge_sync(cur):
    """★routing_edge 생산처(wc) 정기 시드/싱크 (편집 보존 + 신규 반영). compose는 읽기만·이 함수만 씀.
    모델: wc_live=라이브 PR_M_ITEM 시드(매싱크 갱신), wc_user=사용자 편집(NULL=미편집), 유효 wc=COALESCE(wc_user,wc_live).
      → 미편집 엣지는 라이브 생산처 자동 추종, 편집 엣지는 보존. 신규 엣지(v_pr_bom 증가분)는 라이브 기준 시드로 INSERT."""
    # 1) 편집추적 컬럼 보장
    cur.execute("IF COL_LENGTH('nx.routing_edge','wc_live') IS NULL ALTER TABLE nx.routing_edge ADD wc_live varchar(20)")
    cur.execute("IF COL_LENGTH('nx.routing_edge','wc_user') IS NULL ALTER TABLE nx.routing_edge ADD wc_user varchar(20)")
    # 2) 신규 엣지 INSERT (v_pr_bom엔 있고 routing_edge엔 없는 것) — 라이브 마스터 기준 시드, wc_user=NULL
    cur.execute("""INSERT INTO nx.routing_edge(parent_item,child_item,seq,gubun,vendor_seed,route_id,src_except,src_sagub,wc_live,wc)
      SELECT UPPER(LTRIM(RTRIM(b.item_code))), UPPER(LTRIM(RTRIM(b.mat_code))), b.BOM_SEQ,
        CASE WHEN ISNULL(b.EXCEPT_FLAG,'0')='1' THEN N'전개제외'
             WHEN ISNULL(b.SAGUB_FLAG,'0')='1' THEN N'사급'
             WHEN ISNULL(ci.make_type,'')='1' THEN N'제작' ELSE N'매입' END,
        CASE WHEN ISNULL(b.EXCEPT_FLAG,'0')='1' THEN ISNULL(pi.in_cust,'') ELSE ISNULL(ci.in_cust,'') END,
        1, ISNULL(b.EXCEPT_FLAG,'0'), ISNULL(b.SAGUB_FLAG,'0'),
        CASE WHEN ci.work_code>'' THEN ci.work_code ELSE ISNULL(ci.in_cust,'') END,
        CASE WHEN ci.work_code>'' THEN ci.work_code ELSE ISNULL(ci.in_cust,'') END
      FROM nx.v_pr_bom b
      LEFT JOIN nx.item ci ON UPPER(LTRIM(RTRIM(ci.item_code)))=UPPER(LTRIM(RTRIM(b.mat_code)))
      LEFT JOIN nx.item pi ON UPPER(LTRIM(RTRIM(pi.item_code)))=UPPER(LTRIM(RTRIM(b.item_code)))
      WHERE NOT EXISTS(SELECT 1 FROM nx.routing_edge re WHERE re.parent_item=UPPER(LTRIM(RTRIM(b.item_code)))
        AND re.child_item=UPPER(LTRIM(RTRIM(b.mat_code))) AND re.seq=b.BOM_SEQ)""")
    new_cnt = cur.rowcount
    # 3) wc_live 라이브 갱신 (편집 무관, child 생산처=work_code||in_cust)
    cur.execute("""UPDATE re SET re.wc_live = CASE WHEN it.work_code>'' THEN it.work_code ELSE ISNULL(it.in_cust,'') END
      FROM nx.routing_edge re JOIN nx.item it ON UPPER(LTRIM(RTRIM(it.item_code)))=re.child_item""")
    # 4) 유효 wc = COALESCE(wc_user, wc_live) — 편집 보존
    cur.execute("UPDATE nx.routing_edge SET wc = ISNULL(NULLIF(LTRIM(RTRIM(wc_user)),''), wc_live)")
    return int(new_cnt or 0)

@router.post("/api/routing/sync")
def routing_sync():
    """routing_edge 생산처 시드/싱크(멱등). 편집(wc_user) 보존, 미편집은 라이브 추종, 신규 엣지 INSERT."""
    nx = _nx(); cur = nx.cursor()
    try:
        new_cnt = _routing_edge_sync(cur)
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN ISNULL(LTRIM(RTRIM(wc_user)),'')<>'' THEN 1 ELSE 0 END) FROM nx.routing_edge")
        tot, edited = cur.fetchone()
        return {"ok": True, "new_edges": new_cnt, "total_edges": int(tot or 0), "edited_edges": int(edited or 0)}
    finally:
        nx.close()

@router.get("/api/plan/part")
def plan_part(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
              part: str = Query(""), assy: str = Query("")):
    # ★정본 파이프라인 전환: nx.plan_part(구 단일패스 98%) → nx.plan_part_mat(레거시 STEP5→6→7 100%검증).
    #   자도번(파트)=mat_code, 작업처=mat_work_center_code, 소요=part_plan_qty.
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.plan_part_mat') IS NULL SELECT 1 WHERE 1=0")
        w = ["1=1"]; p = []
        if from_ymd: w.append("pp.PLAN_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("pp.PLAN_YMD<=?"); p.append(_d6(to_ymd))
        if wc.strip():   w.append("pp.MAT_WORK_CENTER_CODE=?"); p.append(wc.strip())
        if part.strip(): w.append("pp.MAT_CODE LIKE ?"); p.append(f"%{part.strip()}%")
        if assy.strip(): w.append("pp.ASSY_ITEM_CODE LIKE ?"); p.append(f"%{assy.strip()}%")
        try:
            cur.execute(f"""SELECT pp.PLAN_YMD, pp.ASSY_ITEM_CODE, pp.MAT_CODE, pp.MAT_WORK_CENTER_CODE,
                  COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE) wcnm, ISNULL(i.item_name,'') nm,
                  SUM(CAST(pp.PART_PLAN_QTY AS float)) q
                FROM nx.plan_part_mat pp
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK w ON w.WORK_CODE COLLATE DATABASE_DEFAULT=pp.MAT_WORK_CENTER_CODE COLLATE DATABASE_DEFAULT
                LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu ON cu.CUST_CODE COLLATE DATABASE_DEFAULT=pp.MAT_WORK_CENTER_CODE COLLATE DATABASE_DEFAULT
                LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.ITEM_CODE COLLATE DATABASE_DEFAULT=pp.MAT_CODE COLLATE DATABASE_DEFAULT
                WHERE {' AND '.join(w)}
                GROUP BY pp.PLAN_YMD, pp.ASSY_ITEM_CODE, pp.MAT_CODE, pp.MAT_WORK_CENTER_CODE,
                  COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE), i.item_name""", *p)
        except Exception:
            return {"dates": [], "rows": [], "part_count": 0, "sum_qty": 0, "note": "편성 먼저 실행(/compose_mat)"}
        cols = [d[0] for d in cur.description]; raw = [dict(zip(cols, r)) for r in cur.fetchall()]
        dates = sorted({r["PLAN_YMD"] for r in raw})
        keyed = {}
        for r in raw:
            k = (r["ASSY_ITEM_CODE"], r["MAT_CODE"], r["MAT_WORK_CENTER_CODE"])
            g = keyed.get(k)
            if not g:
                g = {"assy": r["ASSY_ITEM_CODE"], "part": r["MAT_CODE"], "nm": r["nm"], "wc": r["MAT_WORK_CENTER_CODE"],
                     "wcnm": r["wcnm"], "sg": "", "days": {}, "tot": 0}
                keyed[k] = g
            q = float(r["q"] or 0); g["days"][r["PLAN_YMD"]] = g["days"].get(r["PLAN_YMD"], 0) + q; g["tot"] += q
        rows = sorted(keyed.values(), key=lambda x: (x["wcnm"] or "", x["part"]))
        return {"dates": dates, "rows": rows, "part_count": len(rows), "sum_qty": sum(float(r["q"] or 0) for r in raw)}
    finally:
        nx.close()
