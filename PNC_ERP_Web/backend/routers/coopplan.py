# -*- coding: utf-8 -*-
"""coopplan 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 협력사 ①: 협력사계획현황 (w_pr_outside_040) — nx.plan_part 편성결과 =================
@router.get("/api/partner/workcenters")
def partner_workcenters(src: str = Query("nx")):
    """자도번작업처(협력사/내부공정) 목록. src=legacy → 라이브 PR_T_PLAN_PART_MAT(레거시 협력사계획, 당김 반영).
       src=nx(기본) → 우리 편성 nx.plan_part_mat."""
    if src == "legacy":
        cn = _conn(); cur = cn.cursor()
        try:
            cur.execute("""SELECT pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE) nm, COUNT(*) n
                FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_MAT pp
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK w ON w.WORK_CODE=pp.MAT_WORK_CENTER_CODE
                LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu ON cu.CUST_CODE=pp.MAT_WORK_CENTER_CODE
                WHERE pp.MAT_WORK_CENTER_CODE>'' GROUP BY pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE)
                ORDER BY COUNT(*) DESC""")
            return {"rows": [{"cc": r[0], "nm": r[1], "n": r[2]} for r in cur.fetchall()]}
        finally:
            cn.close()
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.plan_part_mat') IS NULL SELECT 1 WHERE 1=0")
        C = " COLLATE DATABASE_DEFAULT"
        try:
            cur.execute(f"""SELECT pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE) nm, COUNT(*) n
                FROM nx.plan_part_mat pp
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK w ON w.WORK_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu ON cu.CUST_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                WHERE pp.MAT_WORK_CENTER_CODE>'' GROUP BY pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE)
                ORDER BY COUNT(*) DESC""")
            return {"rows": [{"cc": r[0], "nm": r[1], "n": r[2]} for r in cur.fetchall()]}
        except Exception:
            return {"rows": []}
    finally:
        nx.close()

def _qint(v):
    f = float(v or 0)
    return int(f) if f == int(f) else round(f, 2)

# ================= ★완료수량(fulfillment) 엔진 — 레거시 SP + 510 창 충실이식 =================
# 원천: nx.dbo.[SP_PR_4주간계획현황_LIVE](레거시 SP_PR_4주간계획현황_251126을 LIVE 읽기용으로 이식.
#   PARTNER_ERP.dbo 로 전 테이블 한정=라이브 직독, 쓰기0. 당김 f_reld_doosung_live=라이브 HR_M_CALENDAR).
# 완료수량 c_fin = 출하(sale) + 완제품재고 배분(prod, ASSY재고 공유풀) + 세트/입고대기 재고배분(공유풀).
#   레거시 창(w_pr_outside_510.srw ue_set_dd_color/생산수량적용/자재수량적용) 로직을 파이썬 재현.
#   ★재고는 c_item_code(도번) 단위 공유풀 — 여러 제번이 나눠 소진(과다계상 방지). 일자-major 배분.
_SPL = "SP_PR_4주간계획현황_LIVE"

def _sp_live_rows(cur, cust, from_ymd, to_ymd, flag, item="%", matcode="%", workcode="%"):
    """SP_LIVE 1회 실행 → base grid 행 dict 리스트(라이브 직독)."""
    cur.execute("SET NOCOUNT ON; EXEC dbo.[" + _SPL + "] ?,?,?,?,?,?,?",
                from_ymd, to_ymd, flag, item, matcode, workcode, cust)
    cols = rows = None
    while True:
        if cur.description:
            cols = [c[0] for c in cur.description]; rows = cur.fetchall()
        if not cur.nextset(): break
    if not cols: return []
    ix = {c: i for i, c in enumerate(cols)}
    def G(r, c): return r[ix[c]] if c in ix else None
    out = []
    for r in rows:
        days = [int(G(r, 'plan_qty_%02d' % i) or 0) for i in range(1, 32)]
        minidx = next((i for i, d in enumerate(days) if d > 0), 99)
        out.append({'wo': str(G(r, 'work_order') or ''), 'swo': str(G(r, 'split_work_order') or ''),
            'assy': str(G(r, 'c_item_code') or ''), 'cust': str(G(r, 'mat_in_cust_code') or ''),
            'line': str(G(r, 'line_no') or ''), 'output_hm': str(G(r, 'output_hm') or ''),
            'excel': int(G(r, 'excel_seq') or 0), 'minidx': minidx,
            'plan': int(G(r, 'plan_qty') or 0), 'days': days, 'over': int(G(r, 'over_plan_qty') or 0),
            'lot': float(G(r, 'lot_qty') or 0), 'use': float(G(r, 'use_qty') or 1), 'rate': float(G(r, 'prod_rate') or 100),
            'sale': int(G(r, 'sale_qty') or 0), 'assy_stock': int(G(r, 'assy_stock_qty') or 0),
            'iset_stk': int(G(r, 'input_set_qty') or 0), 'ireq': int(G(r, 'input_req_qty') or 0),
            'work_center': str(G(r, 'work_center') or ''), 'work_code': str(G(r, 'work_code') or ''),
            'in_cust': str(G(r, 'in_cust_code') or ''),
            'model': str(G(r, 'model_no') or ''), 'nm': '', 'lot_qty': int(G(r, 'lot_qty') or 0),
            'insp': str(G(r, 'insp_flag') or '0'), 'pack': int(G(r, 'pack_qty') or 0),
            'mat_list': str(G(r, 'mat_list') or ''), 'sagub_list': str(G(r, 'sagub_list') or '')})
    return out

# 날짜셀 색상 = 가공-4주간(SCREEN.gagongplan4w)과 동일 규칙: 출하완료 주황·생산완료 노랑·재고배분 녹.
_TAGCOLOR = {90: '#fac090', 70: '#ffff00', 50: '#669900'}

def _sim510(rows):
    """레거시 w_pr_outside_510 창 배분 로직 이식 → 각 행에 c_fin(완료)·c_input(요청)·prod 세팅.
       재고=도번(cust,assy) 공유풀, 일자-major 순차배분. (출하+완제품재고+세트/입고대기).
       ★일자셀용: done_days[31](일자별 완료 배분량)·color_days[31](배분원천 색=가공4주간과 동일)."""
    from collections import defaultdict
    for r in rows:
        pd = r['days']; iset = [0]*31; dd = [0]*31; tg = [0]*31
        ll_lot = math.ceil(r['lot']*r['use']*r['rate']/100.0); allplan = r['plan']+r['over']
        if ll_lot < allplan: ll_lot = allplan
        q = r['sale'] - (ll_lot - allplan)               # 지난계획 차감 후 출하 적용 → 주황(90)
        for i in range(31):
            if q <= 0: break
            if pd[i] > 0:
                if q >= pd[i]: give = pd[i]; iset[i] = pd[i]; q -= pd[i]
                else:
                    give = max(0, q - iset[i]); iset[i] = max(iset[i], q); q = 0
                if give > 0: dd[i] += give; tg[i] = max(tg[i], 90)
        r['iset'] = iset; r['dd'] = dd; r['tg'] = tg; r['prod'] = 0
    g = defaultdict(list)
    for r in rows: g[(r['cust'], r['assy'])].append(r)
    # 완제품재고(ASSY) 공유풀 배분 → 노랑(70)
    for k, rs in g.items():
        rs.sort(key=lambda r: (r['minidx'], r['line'], r['output_hm'], r['swo'], r['excel']))
        pool = max((r['assy_stock'] for r in rs), default=0)
        for i in range(31):
            if pool <= 0: break
            for r in rs:
                if pool <= 0: break
                need = r['days'][i] - r['iset'][i]
                if need > 0:
                    give = min(need, pool); r['prod'] += give; r['iset'][i] += give
                    r['dd'][i] += give; r['tg'][i] = max(r['tg'][i], 70); pool -= give
    for r in rows:
        r['c_fin'] = r['prod'] + r['sale']; r['c_input'] = max(0, r['plan'] - r['c_fin'])
    # 세트재고+입고대기 공유풀 배분(완료 가산·요청 차감) → 녹(50)
    for k, rs in g.items():
        rs.sort(key=lambda r: (r['minidx'], r['line'], r['output_hm'], r['swo'], r['excel']))
        pool = max((r['iset_stk'] + r['ireq'] for r in rs), default=0)
        for i in range(31):
            if pool <= 0: break
            for r in rs:
                if pool <= 0: break
                if r['days'][i] > 0:
                    need = r['days'][i] - r['iset'][i]
                    if need > 0:
                        give = min(need, pool); r['iset'][i] += give
                        r['c_fin'] += give; r['c_input'] = max(0, r['c_input'] - give)
                        r['dd'][i] += give; r['tg'][i] = max(r['tg'][i], 50); pool -= give
    for r in rows:
        r['done_days'] = r['dd']; r['color_days'] = [_TAGCOLOR.get(t, '') for t in r['tg']]
    return rows

_FUT_CACHE = {}  # (cust,from,to,item,matcode,workcode) -> (ts, per_key, rows). SP_LIVE 무거움(교차DB) → 단기 캐시.
_FUT_TTL = 180

def _fulfillment(cust, from_ymd, to_ymd, item="%", matcode="%", workcode="%"):
    """★cust(협력사) 완료수량 — 빠른 경로: PR_T_PLAN_PART_MAT(BOM전개완료·mat_work_center_code 인덱스, 라이브 직독)에서
       도번(ASSY) 계획그리드를 얻고 + 스코프 조인(출하/재고/세트/입고대기)만 조회 → _sim510.
       ★재귀 SP(SP_LIVE) 미사용(전 협력사×BOM전개=16s/flag). 이 경로는 선택협력사만 스캔=수초.
       완료수량 값(도번별)은 SP경로와 동일(재고 공유풀 총량은 일자버킷과 무관). base grid=라이브 검증.
       반환: (per_key, rows) — per_key[(swo,assy)]=(c_fin,c_input,plan)."""
    import datetime as _dt
    ck = (cust, from_ymd, to_ymd, item, matcode, workcode)
    hit = _FUT_CACHE.get(ck)
    if hit and (time.time() - hit[0]) < _FUT_TTL:
        return hit[1], hit[2]
    def _d2(s): return _dt.date(2000+int(s[:2]), int(s[2:4]), int(s[4:6]))
    base = _d2(from_ymd)
    dayidx = {(base + _dt.timedelta(days=i)).strftime('%y%m%d'): i for i in range(31)}
    def _bkt(ymd):
        if ymd <= from_ymd: return 0            # 기준일 이전 누적=day1
        return dayidx.get(ymd)                  # 없으면 None(31일 밖)
    cn = _conn(); cur = cn.cursor()
    try:
        wsel = ["mat_work_center_code=?", "plan_ymd<=?"]; wp = [cust, to_ymd]
        if item and item != "%":    wsel.append("assy_item_code LIKE ?"); wp.append(item)
        if matcode and matcode != "%": wsel.append("mat_code LIKE ?"); wp.append(matcode)
        # 도번(ASSY) 계획그리드: (wo,swo,assy,plan_ymd) 배치별 MAX(plan_qty). 사급=mat_flag 2 존재.
        #   ★PART_MAT.plan_qty는 이미 회수율(CEILING×rate/100) 반영된 발주값(정상도번). SVC 소수도번만 raw(무시가능 4/44208).
        cur.execute(f"""SELECT work_order, split_work_order, assy_item_code, plan_ymd,
              MAX(CAST(plan_qty AS float)) pq, MAX(CAST(lot_qty AS float)) lot, MAX(CAST(use_qty AS float)) uq,
              MAX(ISNULL(line_no,'')) line, MAX(ISNULL(output_hm,'')) ohm, MAX(CASE WHEN mat_flag='2' THEN 1 ELSE 0 END) sg
            FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_MAT
            WHERE {' AND '.join(wsel)}
            GROUP BY work_order, split_work_order, assy_item_code, plan_ymd""", *wp)
        keyed = {}
        for r in cur.fetchall():
            wo, swo, assy, pym = str(r[0] or ''), str(r[1] or ''), str(r[2] or ''), str(r[3] or '')
            bi = _bkt(pym)
            if bi is None: continue
            k = (wo, swo, assy)
            g = keyed.get(k)
            if not g:
                g = {'wo': wo, 'swo': swo, 'assy': assy, 'cust': cust, 'line': str(r[7] or ''), 'output_hm': str(r[8] or ''),
                     'excel': 0, 'days': [0]*31, 'plan': 0, 'lot': 0.0, 'use': 1.0, 'over': 0, 'rate': 100.0,
                     'sale': 0, 'assy_stock': 0, 'iset_stk': 0, 'ireq': 0, 'work_center': '', 'work_code': '', 'in_cust': '',
                     'model': '', 'nm': '', 'lot_qty': 0, 'insp': '0', 'pack': 0, 'mat_list': '', 'sagub_list': '', 'sagub': 0}
                keyed[k] = g
            q = int(float(r[4] or 0)); g['days'][bi] += q; g['plan'] += q   # PART_MAT.plan_qty(회수율 baked)
            g['lot'] = max(g['lot'], float(r[5] or 0)); g['use'] = max(g['use'], float(r[6] or 1))
            if int(r[9] or 0): g['sagub'] = 1
        rows = list(keyed.values())
        for g in rows:
            g['minidx'] = next((i for i, d in enumerate(g['days']) if d > 0), 99)
            g['lot_qty'] = int(g['lot'])
        # 스코프 조인 배치조회
        assys = sorted({g['assy'] for g in rows if g['assy']})
        wos = sorted({g['wo'] for g in rows if g['wo']})
        today = _dt.date.today().strftime('%y%m%d')
        def _chunks(seq, n=900):
            for i in range(0, len(seq), n): yield seq[i:i+n]
        sale = {}; move = {}; astk = {}; z99 = {}; sset = {}; sreq = {}; mstr = {}; msub = {}; over = {}
        aset = set(assys)
        # 출하/이동=work_order 인덱스로 스코프(item_code는 인덱스 없어 풀스캔 → wo 스코프가 훨씬 빠름). item은 파이썬 필터.
        for ch in _chunks(wos):
            ph = ",".join("?"*len(ch))
            cur.execute(f"SELECT work_order, split_work_order, item_code, SUM(sale_qty) FROM PARTNER_ERP_TEST3.nx.SA_T_SALE_DTL WHERE finish_flag='0' AND work_order IN ({ph}) GROUP BY work_order, split_work_order, item_code", *ch)
            for r in cur.fetchall():
                if str(r[2]) in aset: sale[(str(r[0]), str(r[1]), str(r[2]))] = float(r[3] or 0)
            cur.execute(f"SELECT fr_work_order, fr_split_work_order, item_code, SUM(move_qty) FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_MOVE WHERE fr_finish_flag='0' AND MOVE_TAG='3' AND fr_work_order IN ({ph}) GROUP BY fr_work_order, fr_split_work_order, item_code", *ch)
            for r in cur.fetchall():
                if str(r[2]) in aset: move[(str(r[0]), str(r[1]), str(r[2]))] = float(r[3] or 0)
        for ch in _chunks(assys):
            ph = ",".join("?"*len(ch))
            cur.execute(f"SELECT item_code, SUM(stock_qty) FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK WHERE item_code IN ({ph}) GROUP BY item_code", *ch)
            for r in cur.fetchall(): astk[str(r[0])] = float(r[1] or 0)
            cur.execute(f"SELECT mat_code, SUM(stock_qty) FROM PARTNER_ERP_TEST3.nx.PU_T_MAT_STOCK_WH WHERE cust_code='Z99990' AND mat_code IN ({ph}) GROUP BY mat_code", *ch)
            for r in cur.fetchall(): z99[str(r[0])] = float(r[1] or 0)
            cur.execute(f"SELECT item_code, SUM(stock_qty) FROM PARTNER_ERP_TEST3.nx.PU_T_SET_MAT_STOCK WHERE in_cust_code=? AND item_code IN ({ph}) GROUP BY item_code", cust, *ch)
            for r in cur.fetchall(): sset[str(r[0])] = float(r[1] or 0)
            cur.execute(f"SELECT item_code, SUM(input_req_qty) FROM PARTNER_ERP_TEST3.nx.PU_T_SET_INPUT_REQ WHERE in_cust_code=? AND input_ymd=? AND confirm_flag='0' AND item_code IN ({ph}) GROUP BY item_code", cust, today, *ch)
            for r in cur.fetchall(): sreq[str(r[0])] = float(r[1] or 0)
            cur.execute(f"SELECT ITEM_CODE, ISNULL(PROD_RATE,100), ISNULL(IN_CUST_CODE,''), ISNULL(WORK_CODE,''), ISNULL(ITEM_DESC,'') FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ch)
            for r in cur.fetchall(): mstr[str(r[0])] = (float(r[1] or 100), str(r[2] or ''), str(r[3] or ''), str(r[4] or ''))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(INSP_FLAG,'0'), ISNULL(PACK_QTY,0) FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_SUB WHERE ITEM_CODE IN ({ph})", *ch)
            for r in cur.fetchall(): msub[str(r[0])] = (str(r[1] or '0'), int(r[2] or 0))
        # 자도번LIST(레거시 f_find_cust_mat_list2 = PR_M_CUST_MAT_LIST 조회, '(1)' 제거)
        matlist = {}
        for ch in _chunks(assys):
            ph = ",".join("?"*len(ch))
            cur.execute(f"SELECT ITEM_CODE, REPLACE(ISNULL(MAX(MAT_LIST),''),'(1)','') FROM PARTNER_ERP_TEST3.nx.PR_M_CUST_MAT_LIST WHERE CUST_CODE=? AND ITEM_CODE IN ({ph}) GROUP BY ITEM_CODE", cust, *ch)
            for r in cur.fetchall(): matlist[str(r[0])] = str(r[1] or '')
        # over_plan_qty(기준기간 이후 계획) — 스코프(wo). lot_overhang 계산에만 사용.
        try:
            for ch in _chunks(wos):
                ph = ",".join("?"*len(ch))
                cur.execute(f"""SELECT a.work_order, a.split_work_order, b.c_item_code,
                      SUM(CEILING(CONVERT(float,a.plan_qty)*ISNULL(b.use_qty,1)*ISNULL(c.prod_rate,100)/100))
                    FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_DTL a JOIN PARTNER_ERP_TEST3.nx.PR_M_MODEL_BOM b ON a.model_no=b.model_no
                    JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM c ON b.c_item_code=c.item_code
                    WHERE a.plan_ymd>? AND a.work_order IN ({ph})
                    GROUP BY a.work_order, a.split_work_order, b.c_item_code""", to_ymd, *ch)
                for r in cur.fetchall(): over[(str(r[0]), str(r[1]), str(r[2]))] = int(float(r[3] or 0))
        except Exception:
            over = {}
    finally:
        cn.close()
    # 행 조립
    for g in rows:
        a = g['assy']
        g['sale'] = int((sale.get((g['wo'], g['swo'], a), 0)) - (move.get((g['wo'], g['swo'], a), 0)))
        m = mstr.get(a);
        if m: g['rate'], g['in_cust'], g['work_code'], g['nm'] = m
        stk = astk.get(a, 0)
        if g['in_cust'] == cust and not g['work_code']:   # 직납품=자재창고(Z99990) 가산
            stk += z99.get(a, 0)
        g['assy_stock'] = int(stk)
        g['iset_stk'] = int(sset.get(a, 0)) if not (g['in_cust'] == cust and not g['work_code']) else 0  # 직납품 세트재고 미사용
        g['ireq'] = int(sreq.get(a, 0))
        sub = msub.get(a)
        if sub: g['insp'], g['pack'] = sub
        g['over'] = over.get((g['wo'], g['swo'], a), 0)
        g['mat_list'] = matlist.get(a, '')
        g['sagub_list'] = ''   # 레거시 성능상 미표시(f_find_cust_sagub_list 주석).
    _sim510(rows)
    per_key = {}
    for r in rows:
        k = (r['swo'], r['assy'])
        pf, pi, pp = per_key.get(k, (0, 0, 0))
        per_key[k] = (pf + r['c_fin'], pi + r['c_input'], pp + r['plan'])
    if len(_FUT_CACHE) > 40: _FUT_CACHE.clear()
    _FUT_CACHE[ck] = (time.time(), per_key, rows)
    return per_key, rows

def _planstatus_legacy(from_ymd, to_ymd, wc, part, assy, line, gubun):
    """★레거시 4주간 계획수량(w_pr_outside_410) 충실재현 — 라이브 PR_T_PLAN_PART_MAT 직독(읽기전용).
       원천 dw_pr_outside_040_t1 계열. 행 grain=도번(자도번작업처×제번×라인×assy_item_code), 일자매트릭스=part_plan_ymd(협력사 당김 CUST_MAINT_DAY 반영), 값=part_plan_qty.
       컬럼(레거시 동일): SEQ·자도번작업처·라인·작업처·도번·자도번LIST·사급·LOT수량·자재수량·완료수량·요청수량·품목정보·일자별.
       당김은 협력사계획_생성 SP가 part_plan_ymd에 baked(f_get_relative_work_day_doosung). 완료수량=레거시 라이브 실적조인 원천 미확정(담당확인)."""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        d6f = _d6(from_ymd) if from_ymd else None
        d6t = _d6(to_ymd) if to_ymd else None
        if d6t: w.append("pp.part_plan_ymd<=?"); p.append(d6t)
        if wc.strip():   w.append("pp.mat_work_center_code=?"); p.append(wc.strip())
        if part.strip(): w.append("pp.mat_code LIKE ?"); p.append(f"%{part.strip()}%")
        if assy.strip(): w.append("pp.assy_item_code LIKE ?"); p.append(f"%{assy.strip()}%")
        if line.strip(): w.append("pp.line_no=?"); p.append(line.strip())
        if gubun == "외주":   w.append("(pp.work_code IS NULL OR pp.work_code='')")   # 거래처(협력사)만
        elif gubun == "자체": w.append("pp.work_code>''")                              # 내부공정(P1/P2)
        where = " AND ".join(w)
        # ★협력사 유형별 묶기(사용자확정 2026-08-15): 절삭협력사(CM_M_CUST.CUST_TYPE=6·PR011)=도번 롤업 / 나머지=자도번 롤업.
        gmode = 'mat'
        if wc.strip():
            try:
                cur.execute("SELECT ISNULL(CUST_TYPE,'') FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=?", wc.strip())
                _ct = cur.fetchone(); gmode = 'assy' if (_ct and str(_ct[0]).strip() == '6') else 'mat'
            except Exception:
                pass
        CAP_PARTS = 40000
        # 부품(자도번) 레벨 raw → 파이썬에서 도번 단위 롤업(자도번LIST·일자매트릭스). 값=part_plan_qty(자재), 요청=plan_qty(발주).
        cur.execute(f"""SELECT TOP {CAP_PARTS} pp.mat_work_center_code wc, pp.split_work_order wo, ISNULL(pp.line_no,'') line,
              pp.assy_item_code assy, pp.mat_code mat, pp.mat_flag matflag,
              CAST(pp.lot_qty AS float) lot, CAST(pp.plan_qty AS float) planq, CAST(pp.part_plan_qty AS float) partq,
              pp.part_plan_ymd ppy
            FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_MAT pp
            WHERE {where}
            ORDER BY pp.mat_work_center_code, pp.split_work_order, pp.assy_item_code, pp.mat_code""", *p)
        cols = [d[0] for d in cur.description]; raw = [dict(zip(cols, r)) for r in cur.fetchall()]
        capped = len(raw) >= CAP_PARTS
        base = d6f or (min((r["ppy"] for r in raw if r["ppy"]), default=None))
        def _bucket(ppy):
            return base if (base and ppy and ppy <= base) else ppy
        # 기준일 + 캘린더일 연속전개(빈 일자컬럼 포함). base..d6t.
        dates = {_bucket(r["ppy"]) for r in raw if r["ppy"]}
        if base and d6t:
            import datetime as _dt
            try:
                cu = _dt.date(2000+int(base[:2]), int(base[2:4]), int(base[4:6]))
                end = _dt.date(2000+int(d6t[:2]), int(d6t[2:4]), int(d6t[4:6])); n = 0
                while cu <= end and n < 45:
                    dates.add(cu.strftime('%y%m%d')); cu += _dt.timedelta(days=1); n += 1
            except Exception:
                pass
        dates = sorted(dates)
        keyed = {}
        if gmode == 'assy':
            # ★절삭협력사 = 도번(assy) 단위 롤업 — 제번·라인·자도번 전부 합침(레거시 1도번=1행). lot/요청=제번별 max 합.
            for r in raw:
                k = (r["wc"], r["assy"])
                g = keyed.get(k)
                if not g:
                    g = {"wc": r["wc"], "wo": "", "line": "", "assy": r["assy"], "lookup": r["assy"],
                         "lot": 0.0, "reqq": 0.0, "matq": 0.0, "sagub": False, "parts": {}, "days": {}, "tot": 0.0,
                         "_wolot": {}, "_woreq": {}, "_lines": set()}
                    keyed[k] = g
                wo = str(r["wo"] or "")
                g["_wolot"][wo] = max(g["_wolot"].get(wo, 0.0), float(r["lot"] or 0))
                g["_woreq"][wo] = max(g["_woreq"].get(wo, 0.0), float(r["planq"] or 0))
                if str(r["line"] or "").strip(): g["_lines"].add(str(r["line"]).strip())
                pq = float(r["partq"] or 0); g["matq"] += pq
                if str(r["matflag"] or "") == "2": g["sagub"] = True
                mc = str(r["mat"] or "").strip()
                if mc: g["parts"][mc] = g["parts"].get(mc, 0.0) + pq
                d = _bucket(r["ppy"]); g["days"][d] = g["days"].get(d, 0.0) + pq; g["tot"] += pq
            rows = list(keyed.values())
            for g in rows:
                g["lot"] = sum(g.pop("_wolot").values())
                # ★자재수량=도번 계획수량(Σ제번 plan_qty) — 레거시 410 정의. 자도번 part_plan_qty 합(과다) 아님.
                g["matq"] = sum(g.pop("_woreq").values()); g["reqq"] = g["matq"]
                g["line"] = ",".join(sorted(g.pop("_lines"))) or ""
        else:
            # ★부자재/기타 = 자도번(mat) 단위 롤업 — 여러 도번/제번에 걸친 같은 자도번 합침. 도번컬럼=속한 도번들.
            for r in raw:
                mc = str(r["mat"] or "").strip()
                if not mc: continue
                k = (r["wc"], mc)
                g = keyed.get(k)
                if not g:
                    g = {"wc": r["wc"], "wo": "", "line": "", "assy": "", "lookup": mc, "matcode": mc,
                         "lot": 0.0, "reqq": 0.0, "matq": 0.0, "sagub": False, "parts": {}, "days": {}, "tot": 0.0,
                         "_assys": set(), "_lines": set()}
                    keyed[k] = g
                if str(r["assy"] or "").strip(): g["_assys"].add(str(r["assy"]).strip())
                if str(r["line"] or "").strip(): g["_lines"].add(str(r["line"]).strip())
                pq = float(r["partq"] or 0); g["matq"] += pq
                if str(r["matflag"] or "") == "2": g["sagub"] = True
                d = _bucket(r["ppy"]); g["days"][d] = g["days"].get(d, 0.0) + pq; g["tot"] += pq
            rows = list(keyed.values())
            for g in rows:
                al = sorted(g.pop("_assys"))
                g["assy"] = ", ".join(al[:6]) + ("…" if len(al) > 6 else "")   # 도번 컬럼=이 자도번이 속한 도번들
                g["line"] = ",".join(sorted(g.pop("_lines"))) or ""
                g["parts"] = {g["matcode"]: g["matq"]}   # 자도번LIST=자도번 자신
                g["lot"] = g["matq"]; g["reqq"] = g["matq"]   # 자도번 단위: LOT/요청은 도번-level이라 자재수량으로 표기
        # 배치 이름조회: 자도번작업처(work/cust), 도번(assy) 마스터(작업처·품명·규격)
        def _batch(codes, sql):
            m = {}; codes = sorted({c for c in codes if c})
            for i in range(0, len(codes), 900):
                ch = codes[i:i+900]; ph = ",".join("?" * len(ch))
                cur.execute(sql.format(ph=ph), *ch)
                for rr in cur.fetchall(): m[str(rr[0]).strip()] = rr
            return m
        wccodes = {g["wc"] for g in rows}; assycodes = {g["lookup"] for g in rows}   # lookup=도번(assy모드) or 자도번(mat모드)
        workm = _batch(wccodes, "SELECT WORK_CODE, WORK_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_WORK WHERE WORK_CODE IN ({ph})")
        custm = _batch(wccodes, "SELECT CUST_CODE, CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE IN ({ph})")
        # 도번 마스터(작업처=assy의 work/incust, 품명, 규격)
        assym = _batch(assycodes, "SELECT ITEM_CODE, ISNULL(ITEM_DESC,''), ISNULL(WORK_CODE,''), ISNULL(IN_CUST_CODE,''), ISNULL(ITEM_SPEC,''), ISNULL(ITEM_DIAM,0), ISNULL(ITEM_THICK,0), ISNULL(ITEM_LENGTH,0) FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE IN ({ph})")
        # assy 작업처 코드도 이름 필요 → 추가 조회
        awc = {str(v[2]).strip() for v in assym.values() if str(v[2]).strip()}
        aic = {str(v[3]).strip() for v in assym.values() if str(v[3]).strip()}
        workm2 = _batch(awc, "SELECT WORK_CODE, WORK_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_WORK WHERE WORK_CODE IN ({ph})")
        custm2 = _batch(aic, "SELECT CUST_CODE, CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE IN ({ph})")
        def nm_of(code):
            c = str(code or "").strip()
            if c in workm: return workm[c][1]
            if c in custm: return custm[c][1]
            if c in workm2: return workm2[c][1]
            if c in custm2: return custm2[c][1]
            return c
        for g in rows:
            g["wcnm"] = nm_of(g["wc"])
            am = assym.get(str(g["lookup"]).strip())
            if am:
                g["nm"] = am[1]
                awcc = str(am[2]).strip(); aicc = str(am[3]).strip()
                g["workcenter"] = nm_of(awcc) if awcc else (nm_of(aicc) if aicc else "")
                spec = str(am[4]).strip()
                if not spec:
                    dd, tt, ll = float(am[5] or 0), float(am[6] or 0), float(am[7] or 0)
                    if dd or tt or ll: spec = f"Ø{_qint(dd)}×{_qint(tt)}×{_qint(ll)}"
                g["spec"] = spec
            else:
                g["nm"] = ""; g["workcenter"] = ""; g["spec"] = ""
            items = sorted(g["parts"].items())
            g["part"] = ", ".join(f"{mc}{{{_qint(q)}}}" for mc, q in items)  # 자도번LIST(도번{수량})
            g["jcnt"] = len(items)
            g["lot"] = _qint(g["lot"]); g["reqq"] = _qint(g["reqq"]); g["matq"] = _qint(g["matq"])
            g["doneq"] = None   # ⚠ 완료수량: 레거시 라이브 실적조인 원천 미확정 → 담당확인(추측채움 금지)
            g["days"] = {k2: _qint(v2) for k2, v2 in g["days"].items()}; g["tot"] = _qint(g["tot"])
            g.pop("parts", None)
        rows.sort(key=lambda x: (x["wcnm"] or "", x["line"], x["assy"]))
        for i, g in enumerate(rows, 1): g["seq"] = i
        note = "레거시 4주간 계획수량(w_pr_outside_410)·라이브 PR_T_PLAN_PART_MAT 직독(당김반영). 묶기=" + ("도번(절삭협력사)" if gmode == 'assy' else "자도번(부자재/기타)") + "."
        dates_out = dates; frac = False
        # ★완료수량(fulfillment): 절삭협력사(도번 롤업)만 — 도번(swo,assy) 실적을 assy(도번)로 제번합산. 자도번모드는 도번-level이라 미표시(계획만).
        if gmode == 'assy' and gubun == "외주" and wc.strip() and d6t:
            try:
                import datetime as _dtp
                fut_from = base or d6f or d6t
                per_key, _m = _fulfillment(wc.strip(), fut_from, d6t)
                fb = _dtp.date(2000+int(fut_from[:2]), int(fut_from[2:4]), int(fut_from[4:6]))
                tb = _dtp.date(2000+int(d6t[:2]), int(d6t[2:4]), int(d6t[4:6]))
                ndays = min(31, (tb - fb).days + 1) if tb >= fb else 31
                axis = [(fb + _dtp.timedelta(days=i)).strftime('%y%m%d') for i in range(ndays)]
                # assy(도번) 단위 집계 — 제번(swo) 합산
                pk_assy = {}
                for (swo, a), v in per_key.items():
                    e = pk_assy.setdefault(str(a), [0.0, 0.0, 0.0])
                    e[0] += v[0]; e[1] += v[1]; e[2] += v[2]
                fmap = {}
                for fr in _m:
                    a = str(fr["assy"]); e = fmap.get(a)
                    if not e: e = {"pl": [0]*31, "dn": [0]*31, "tg": [0]*31}; fmap[a] = e
                    for i in range(31):
                        e["pl"][i] += fr["days"][i]; e["dn"][i] += fr["done_days"][i]
                        if fr["tg"][i] > e["tg"][i]: e["tg"][i] = fr["tg"][i]
                nmatch = 0
                for g in rows:
                    hit = pk_assy.get(str(g["assy"]))
                    if hit is not None:
                        g["doneq"] = _qint(hit[0]); g["reqq"] = _qint(hit[1]); nmatch += 1
                    else:
                        g["doneq"] = 0
                    fm = fmap.get(str(g["assy"]))
                    if fm:
                        g["days"] = {axis[i]: _qint(fm["pl"][i]) for i in range(ndays) if fm["pl"][i]}
                        g["donedays"] = {axis[i]: _qint(fm["dn"][i]) for i in range(ndays) if fm["dn"][i]}
                        g["colors"] = {axis[i]: _TAGCOLOR.get(fm["tg"][i], '') for i in range(ndays) if fm["pl"][i]}
                    else:
                        g["days"] = {}; g["donedays"] = {}; g["colors"] = {}
                dates_out = axis; frac = True
                note += f" 완료수량=출하+완제품재고+세트/입고대기 재고배분(레거시 SP+510창, 매칭 {nmatch}/{len(rows)}건). 일자셀=완료/계획+색."
            except Exception as e:
                note += f" ⚠완료수량 계산 오류: {str(e)[:90]}"
        elif gmode == 'mat':
            note += " (자도번 묶기: 완료수량은 도번단위라 미표시 · 계획수량만 표시)"
        else:
            note += " 완료수량=협력사(외주) 지정 시 표시(레거시는 협력사별 화면)."
        if capped: note = f"⚠ 부품 {CAP_PARTS:,}행 상한 — 자도번작업처/제번으로 좁히세요. " + note
        return {"dates": dates_out, "rows": rows, "cnt": len(rows), "frac": frac,
                "sum_qty": _qint(sum(g["matq"] for g in rows)), "note": note}
    finally:
        cn.close()

@router.get("/api/partner/planstatus")
def partner_planstatus(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
                       part: str = Query(""), assy: str = Query(""), line: str = Query(""),
                       gubun: str = Query("외주"), src: str = Query("nx")):
    """협력사(납품업체)별 자도번 일자계획. gubun: 외주(협력사=CUST, 기본)/자체(내부공정=WORK)/전체.
       src=legacy → 라이브 PR_T_PLAN_PART_MAT(레거시 4주간 계획수량 w_pr_outside_410, 당김반영) 직독.
       src=nx(기본) → 우리 편성 nx.plan_part_mat(레거시 STEP5→6→7 100%검증). 가공처=mat_work_center_code, 자도번=mat_code."""
    if src == "legacy":
        return _planstatus_legacy(from_ymd, to_ymd, wc, part, assy, line, gubun)
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.plan_part_mat') IS NULL SELECT 1 WHERE 1=0")
        C = " COLLATE DATABASE_DEFAULT"
        w = ["1=1"]; p = []
        if from_ymd: w.append("pp.PLAN_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("pp.PLAN_YMD<=?"); p.append(_d6(to_ymd))
        if wc.strip():   w.append("pp.MAT_WORK_CENTER_CODE=?"); p.append(wc.strip())
        if part.strip(): w.append("pp.MAT_CODE LIKE ?"); p.append(f"%{part.strip()}%")
        if assy.strip(): w.append("pp.ASSY_ITEM_CODE LIKE ?"); p.append(f"%{assy.strip()}%")
        if line.strip(): w.append("pd.LINE_NO=?"); p.append(line.strip())
        if gubun == "외주":   w.append("w.WORK_CODE IS NULL AND cu.CUST_CODE IS NOT NULL")  # 거래처(협력사)만
        elif gubun == "자체": w.append("w.WORK_CODE IS NOT NULL")                            # 내부공정(P1/P2)
        # ★정본 nx.plan_part_mat은 자재단위라 행수가 큼(외주 5만+) → 브라우저 과부하 방지: 자도번(part)×가공처 단위로 먼저 집계(일자는 유지)
        #   후 상한(CAP). 필터(가공처/제번/자도번) 걸면 좁혀짐.
        CAP = 4000
        try:
            cur.execute(f"""SELECT TOP {CAP} pp.PLAN_YMD, pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE) wcnm,
                  pp.WORK_ORDER, pp.ASSY_ITEM_CODE, pp.MAT_CODE, ISNULL(i.ITEM_DESC,'') nm,
                  ISNULL(pd.LINE_NO,'') line, ISNULL(pd.MODEL_NO,'') model, SUM(CAST(pp.PART_PLAN_QTY AS float)) q
                FROM nx.plan_part_mat pp
                LEFT JOIN (SELECT WORK_ORDER, MAX(LINE_NO) LINE_NO, MAX(MODEL_NO) MODEL_NO FROM nx.plan_dtl GROUP BY WORK_ORDER) pd ON pd.WORK_ORDER=pp.WORK_ORDER
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK w ON w.WORK_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu ON cu.CUST_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE{C}=pp.MAT_CODE{C}
                WHERE {' AND '.join(w)}
                GROUP BY pp.PLAN_YMD, pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE),
                  pp.WORK_ORDER, pp.ASSY_ITEM_CODE, pp.MAT_CODE, i.ITEM_DESC, pd.LINE_NO, pd.MODEL_NO
                ORDER BY wcnm, pp.WORK_ORDER, pp.MAT_CODE""", *p)
        except Exception as e:
            return {"dates": [], "rows": [], "cnt": 0, "sum_qty": 0, "note": "편성 먼저 실행(생산계획업로드 → 🧾자재소요·조달 편성). 오류: " + str(e)[:120]}
        cols = [d[0] for d in cur.description]; raw = [dict(zip(cols, r)) for r in cur.fetchall()]
        capped = len(raw) >= CAP
        dates = sorted({r["PLAN_YMD"] for r in raw})
        keyed = {}
        for r in raw:
            k = (r["MAT_WORK_CENTER_CODE"], r["WORK_ORDER"], r["ASSY_ITEM_CODE"], r["MAT_CODE"])
            g = keyed.get(k)
            if not g:
                g = {"wc": r["MAT_WORK_CENTER_CODE"], "wcnm": r["wcnm"], "wo": r["WORK_ORDER"], "assy": r["ASSY_ITEM_CODE"],
                     "part": r["MAT_CODE"], "nm": r["nm"], "line": r["line"], "model": r["model"], "days": {}, "tot": 0}
                keyed[k] = g
            q = float(r["q"] or 0); g["days"][r["PLAN_YMD"]] = g["days"].get(r["PLAN_YMD"], 0) + q; g["tot"] += q
        rows = sorted(keyed.values(), key=lambda x: (x["wcnm"] or "", x["line"], x["wo"], x["part"]))
        note = f"⚠ 결과가 많아 상위 {CAP}건만 표시했습니다. 협력사(가공처)·제번·자도번으로 필터하세요." if capped else ""
        return {"dates": dates, "rows": rows, "cnt": len(rows), "sum_qty": sum(float(r["q"] or 0) for r in raw), "note": note}
    finally:
        nx.close()


# ================= 협력사 ②: 거래명세서 발행 조회 (w_pr_outside_420) — 레거시 SP_LIVE 동일 =================
def _ensure_deliv_issue(cur):
    """발행 기록 테이블(nx만·라이브 미기록). 레거시 PU_T_SET_INPUT_REQ 대응 신규 nx 테이블."""
    cur.execute("""IF OBJECT_ID('nx.deliv_issue') IS NULL CREATE TABLE nx.deliv_issue(
        issue_seq int IDENTITY(1,1) PRIMARY KEY,
        issue_ymd varchar(6), barcode_no varchar(20), cust_code varchar(10), item_code varchar(20),
        deliver_qty decimal(18,2) DEFAULT 0, pack_qty decimal(18,2) DEFAULT 0,
        serial_no varchar(50), heat_no varchar(50), status varchar(2) DEFAULT '10',
        ins_dt datetime DEFAULT getdate(), ins_user varchar(20))""")

def _deliv420_rows(cust, from_ymd, to_ymd, item="%", matcode="%"):
    """레거시 dw_pr_outside_420_t1 동일 데이터: SP_LIVE(라이브 직독)+510창 완료배분 → 도번(cust,assy) 병합행.
       전 컬럼: 자도번작업처·자도번LIST·사급·LOT·계획·완료·요청·출하실적·생산실적·세트재고·입고대기·ASSY재고·일자별."""
    import datetime as _dt
    per_key, rows = _fulfillment(cust, from_ymd, to_ymd, item, matcode)
    # 도번(cust,assy) 병합 (레거시 모도번별 합치기)
    mg = {}
    for r in rows:
        k = (r["cust"], r["assy"])
        m = mg.get(k)
        if not m:
            m = {"cust": r["cust"], "assy": r["assy"], "work_center": r["work_center"], "work_code": r["work_code"],
                 "in_cust": r["in_cust"], "line": r["line"], "model": r["model"], "mat_list": r["mat_list"], "sagub_list": r["sagub_list"],
                 "lot": 0, "plan": 0, "done": 0, "req": 0, "sale": 0, "prod": 0, "assy_stock": r["assy_stock"],
                 "iset_stk": r["iset_stk"], "ireq": r["ireq"], "input_mat": 0, "pack": 0, "insp": r["insp"],
                 "days": [0]*31, "dn": [0]*31, "tg": [0]*31, "swos": []}
            mg[k] = m
        if r["line"] and not m["line"]: m["line"] = r["line"]
        # LOT수량=도번별 제번(split) 합(레거시 510 모도번 합치기 f_set_addnumber=SUM). MAX 아님.
        m["lot"] += r["lot_qty"]; m["plan"] += r["plan"]; m["done"] += r["c_fin"]
        m["req"] += r["c_input"]; m["sale"] += r["sale"]; m["prod"] += r["prod"]
        m["pack"] = max(m["pack"], r["pack"])
        if r["mat_list"] and not m["mat_list"]: m["mat_list"] = r["mat_list"]
        if r["sagub_list"] and not m["sagub_list"]: m["sagub_list"] = r["sagub_list"]
        for i in range(31):
            m["days"][i] += r["days"][i]; m["dn"][i] += r["done_days"][i]
            if r["tg"][i] > m["tg"][i]: m["tg"][i] = r["tg"][i]
        m["swos"].append(r["swo"])
    merged = list(mg.values())
    # 일자 라벨(idx1=기준일 이전누적, idx i=from+(i-1) 캘린더). 표시범위=from..to.
    def d2(s): return _dt.date(2000+int(s[:2]), int(s[2:4]), int(s[4:6]))
    fb = d2(from_ymd); tb = d2(to_ymd)
    ndays = min(31, (tb - fb).days + 1) if tb >= fb else 31
    dates = [(fb + _dt.timedelta(days=i)).strftime('%y%m%d') for i in range(ndays)]
    # 이름/규격/협력사명 배치조회(라이브)
    cn = _conn(); cur = cn.cursor()
    try:
        assys = sorted({m["assy"] for m in merged if m["assy"]})
        nmm = {}
        for i in range(0, len(assys), 900):
            ch = assys[i:i+900]; ph = ",".join("?"*len(ch))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,''), ISNULL(ITEM_SPEC,'') FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ch)
            for rr in cur.fetchall(): nmm[str(rr[0]).strip()] = (rr[1], rr[2])
        custnm = _custnm_map(cur, {cust})
        wccodes = {m["work_code"] or m["in_cust"] for m in merged}
        wcnm = {}
        wcodes = sorted({c for c in wccodes if c})
        for i in range(0, len(wcodes), 900):
            ch = wcodes[i:i+900]; ph = ",".join("?"*len(ch))
            cur.execute(f"SELECT WORK_CODE, WORK_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_WORK WHERE WORK_CODE IN ({ph})", *ch)
            for rr in cur.fetchall(): wcnm[str(rr[0]).strip()] = rr[1]
            cur.execute(f"SELECT CUST_CODE, CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE IN ({ph})", *ch)
            for rr in cur.fetchall(): wcnm.setdefault(str(rr[0]).strip(), rr[1])
    finally:
        cn.close()
    # 발행분(nx.deliv_issue) 반영 — 발행완료 수량 차감·상태(라이브 미기록·nx만).
    issued = {}
    try:
        nx = _nx(); nc = nx.cursor()
        _ensure_deliv_issue(nc)
        nc.execute("SELECT item_code, SUM(deliver_qty) FROM nx.deliv_issue WHERE cust_code=? AND status<>'99' GROUP BY item_code", cust)
        for rr in nc.fetchall(): issued[str(rr[0]).strip()] = float(rr[1] or 0)
        nx.close()
    except Exception:
        issued = {}
    out = []
    for m in merged:
        nm, spec = nmm.get(str(m["assy"]).strip(), ("", ""))
        d = {ymd: _qint(m["days"][i]) for i, ymd in enumerate(dates) if m["days"][i]}
        dn = {ymd: _qint(m["dn"][i]) for i, ymd in enumerate(dates) if m["dn"][i]}
        cl = {ymd: _TAGCOLOR.get(m["tg"][i], '') for i, ymd in enumerate(dates) if m["days"][i]}
        wcc = m["work_code"] or m["in_cust"]
        iss = issued.get(str(m["assy"]).strip(), 0.0)
        req0 = m["req"]; remain = max(0.0, req0 - iss)
        out.append({"cust": m["cust"], "custnm": custnm.get(m["cust"], m["cust"]), "assy": m["assy"], "line": m["line"],
            "nm": nm, "spec": spec, "workcenter": m["work_center"] or wcnm.get(wcc, wcc),
            "mat_list": m["mat_list"], "sagub_list": m["sagub_list"], "lot": _qint(m["lot"]),
            "plan": _qint(m["plan"]), "done": _qint(m["done"]), "req": _qint(remain), "req_org": _qint(req0),
            "issued": _qint(iss), "status": ("90" if iss >= req0 and iss > 0 else ("10" if iss > 0 else "00")),
            "sale": _qint(m["sale"]), "prod": _qint(m["prod"]), "assy_stock": _qint(m["assy_stock"]),
            "iset_stk": _qint(m["iset_stk"]), "ireq": _qint(m["ireq"]), "input_mat": 0,
            "pack": _qint(m["pack"]), "insp": m["insp"], "deliv": _qint(remain), "days": d, "donedays": dn, "colors": cl})
    out.sort(key=lambda x: (x["workcenter"] or "", x["line"] or "", x["assy"]))
    return {"dates": dates, "rows": out, "cnt": len(out),
            "sum": {"lot": _qint(sum(x["lot"] for x in out)), "plan": _qint(sum(x["plan"] for x in out)),
                    "done": _qint(sum(x["done"] for x in out)), "req": _qint(sum(x["req"] for x in out)),
                    "issued": _qint(sum(x["issued"] for x in out))}}

@router.get("/api/partner/deliv420")
def partner_deliv420(cust: str = Query(...), from_ymd: str = Query(""), to_ymd: str = Query(""),
                     item: str = Query(""), matcode: str = Query("")):
    """거래명세서 발행 조회 — 레거시 w_pr_outside_420 동일(SP_LIVE 라이브 직독+510 완료배분).
       cust=협력사코드(필수). from/to=기준일자~horizon. 완료수량=출하+완제품재고+세트/입고대기 재고배분."""
    if not cust.strip():
        return {"dates": [], "rows": [], "cnt": 0, "note": "협력사를 선택하세요."}
    d6f = _d6(from_ymd) if from_ymd else None
    d6t = _d6(to_ymd) if to_ymd else None
    if not d6f or not d6t:
        # 기본: 라이브 최소 계획일자 ~ +4근무일 horizon
        cn = _conn(); cur = cn.cursor()
        try:
            cur.execute("SELECT MIN(plan_ymd) FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_DTL WHERE plan_ymd>'000000'")
            mn = cur.fetchone()[0]
        finally:
            cn.close()
        d6f = d6f or mn
        if not d6t:
            import datetime as _dt2
            b = _dt2.date(2000+int(d6f[:2]), int(d6f[2:4]), int(d6f[4:6])) + _dt2.timedelta(days=6)
            d6t = b.strftime('%y%m%d')
    it = f"%{item.strip()}%" if item.strip() else "%"
    mc = f"%{matcode.strip()}%" if matcode.strip() else "%"
    try:
        res = _deliv420_rows(cust.strip(), d6f, d6t, it, mc)
        res["note"] = f"레거시 거래명세서(w_pr_outside_420) 동일 · SP_LIVE 라이브 직독 · 완료=출하+완제품재고+세트/입고대기 재고배분(510창). 기준 {d6f}~{d6t}."
        return res
    except Exception as e:
        return {"dates": [], "rows": [], "cnt": 0, "note": f"⚠ 조회 오류: {str(e)[:150]}"}

@router.post("/api/partner/deliv420/issue")
def partner_deliv420_issue(body: dict = Body(...)):
    """거래명세서 발행(납품처리) — ★nx.deliv_issue에만 기록(라이브 PU_T_SET_INPUT_REQ 미기록, 하드룰).
       body={cust, from_ymd, to_ymd, items:[{assy, deliver_qty, pack_qty, serial_no, heat_no}], preview:0/1}.
       검증: deliver_qty>요청수량(잔량) 차단·음수 차단. preview=1이면 검토용(무기록). 확정 시 바코드 채번·INSERT."""
    cust = str(body.get("cust", "")).strip()
    items = body.get("items", []) or []
    preview = _b(body.get("preview", 0))
    if not cust: return {"ok": False, "msg": "협력사를 선택하세요."}
    if not items: return {"ok": False, "msg": "발행할 도번(완성분)을 선택하세요."}
    # 잔여 요청수량 검증용 재조회(라이브, 읽기전용)
    d6f = _d6(body.get("from_ymd", "")) or None
    d6t = _d6(body.get("to_ymd", "")) or None
    if not d6f or not d6t:
        cn = _conn(); cur = cn.cursor()
        try:
            cur.execute("SELECT MIN(plan_ymd) FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_DTL WHERE plan_ymd>'000000'"); mn = cur.fetchone()[0]
        finally: cn.close()
        import datetime as _di
        d6f = d6f or mn
        d6t = d6t or (_di.date(2000+int(d6f[:2]), int(d6f[2:4]), int(d6f[4:6])) + _di.timedelta(days=6)).strftime('%y%m%d')
    res = _deliv420_rows(cust, d6f, d6t)
    remain = {str(r["assy"]).strip(): float(r["req"] or 0) for r in res["rows"]}  # 잔여 요청(발행분 차감 후)
    packmap = {str(r["assy"]).strip(): float(r["pack"] or 0) for r in res["rows"]}
    plan = []; errs = []
    for it in items:
        a = str(it.get("assy", "")).strip()
        try: q = float(it.get("deliver_qty", 0) or 0)
        except Exception: q = 0.0
        if not a: continue
        if q < 0: errs.append(f"{a}: 납품수량 음수 불가"); continue
        if q == 0: continue
        rq = remain.get(a)
        if rq is None: errs.append(f"{a}: 조회 결과에 없음(기준일/기간 확인)"); continue
        if q > rq + 0.001: errs.append(f"{a}: 납품수량 {q:g} > 요청(잔량) {rq:g} 초과"); continue
        plan.append({"assy": a, "deliver_qty": q,
                     "pack_qty": float(it.get("pack_qty", packmap.get(a, 0)) or 0),
                     "serial_no": str(it.get("serial_no", "") or "")[:50], "heat_no": str(it.get("heat_no", "") or "")[:50]})
    if errs:
        return {"ok": False, "msg": "발행 불가: " + " / ".join(errs[:8]), "errs": errs}
    if not plan:
        return {"ok": False, "msg": "발행할 유효 수량이 없습니다(납품수량 입력·잔량 확인)."}
    if preview:
        return {"ok": True, "preview": True, "count": len(plan),
                "total_qty": _qint(sum(p["deliver_qty"] for p in plan)), "items": plan}
    # 확정 발행: nx.deliv_issue INSERT (그룹 트랜잭션)
    import datetime as _di2
    ymd = _di2.date.today().strftime('%y%m%d')
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_deliv_issue(cur)
        cur.execute("SELECT ISNULL(MAX(CAST(barcode_no AS int)),700000)+1 FROM nx.deliv_issue WHERE ISNUMERIC(barcode_no)=1")
        bc = str(cur.fetchone()[0])
        for p in plan:
            cur.execute("""INSERT INTO nx.deliv_issue(issue_ymd, barcode_no, cust_code, item_code, deliver_qty, pack_qty, serial_no, heat_no, status, ins_user)
                VALUES(?,?,?,?,?,?,?,?, '10', ?)""",
                ymd, bc, cust, p["assy"], p["deliver_qty"], p["pack_qty"], p["serial_no"], p["heat_no"], str(body.get("user", "web")))
        nx.commit()
        return {"ok": True, "barcode": bc, "count": len(plan), "total_qty": _qint(sum(p["deliver_qty"] for p in plan))}
    except Exception as e:
        nx.rollback(); return {"ok": False, "msg": f"발행 오류(롤백): {str(e)[:150]}"}
    finally:
        nx.close()

@router.post("/api/partner/deliv420/cancel")
def partner_deliv420_cancel(body: dict = Body(...)):
    """발행취소 — 해당 바코드 발행행 status='99'(nx만)."""
    bc = str(body.get("barcode", "")).strip()
    if not bc: return {"ok": False, "msg": "바코드가 필요합니다."}
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_deliv_issue(cur)
        cur.execute("UPDATE nx.deliv_issue SET status='99' WHERE barcode_no=? AND status<>'99'", bc)
        return {"ok": True, "cancelled": cur.rowcount}
    finally:
        nx.close()

def _fmtbiz(b):
    """사업자등록번호 000-00-00000 포맷."""
    b = "".join(ch for ch in str(b or "") if ch.isdigit())
    return f"{b[:3]}-{b[3:5]}-{b[5:]}" if len(b) == 10 else (str(b or "").strip())

@router.get("/api/partner/deliv420/invoice")
def partner_deliv420_invoice(barcode: str = Query(...)):
    """거래명세표+스티커 데이터 — 하나의 발행바코드(nx.deliv_issue.barcode_no)에 묶인 도번 명세.
       레거시 dw_pr_outside_020_p1(입고 거래명세표) 서식 동일: 공급자(협력사)/공급받는자(당사)+품목명세+SET바코드.
       바코드=Code39, 값='SET'+발행번호(레거시 compute_105 동일). 스티커 라벨필드=도번·품명·수량·SERIAL·HEAT·발행번호·거래처·일자."""
    import datetime as _dtv
    bc = str(barcode).strip()
    bcnum = "".join(ch for ch in bc if ch.isdigit())      # SET700001 · 700001 모두 허용
    if not bcnum:
        raise HTTPException(400, "발행번호(바코드)가 필요합니다.")
    nx = _nx(); ncur = nx.cursor()
    try:
        _ensure_deliv_issue(ncur)
        ncur.execute("""SELECT cust_code, item_code, deliver_qty, pack_qty, ISNULL(serial_no,''), ISNULL(heat_no,''), issue_ymd, status
            FROM nx.deliv_issue WHERE barcode_no=? AND status<>'99' ORDER BY item_code""", bcnum)
        drows = ncur.fetchall()
    finally:
        nx.close()
    if not drows:
        raise HTTPException(404, f"발행번호 {bc} 명세 없음(취소분 제외).")
    cust = str(drows[0][0]).strip()
    issue_ymd = str(drows[0][6] or "").strip()
    ymd_disp = (f"20{issue_ymd[:2]}-{issue_ymd[2:4]}-{issue_ymd[4:6]}" if len(issue_ymd) == 6
                else _dtv.date.today().strftime('%Y-%m-%d'))
    cn = _conn(); cur = cn.cursor()
    try:
        # 공급자 = 협력사(cust) · 공급받는자 = 당사(CM_M_COMPANY)  ← 레거시 020_p1 배치와 동일
        cur.execute("""SELECT ISNULL(BUSINESS_NO,''),ISNULL(CUST_DESC,''),ISNULL(OWNER_NAME,''),
            LTRIM(ISNULL(ADDRESS,'')+' '+ISNULL(ADDRESS_DTL,'')),ISNULL(PHONE_NO,''),ISNULL(FAX_NO,''),
            ISNULL(BUSI_TYPE,''),ISNULL(BUSI_KIND,'') FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=?""", cust)
        s = cur.fetchone() or ('',)*8
        supplier = {"biz": _fmtbiz(s[0]), "nm": (s[1] or '').strip(), "owner": (s[2] or '').strip(),
                    "addr": (s[3] or '').strip(), "tel": (s[4] or '').strip(), "fax": (s[5] or '').strip(),
                    "btype": (s[6] or '').strip(), "bkind": (s[7] or '').strip()}
        cur.execute("""SELECT TOP 1 ISNULL(BUSINESS_NO,''),ISNULL(COMPANY_DESCK,''),ISNULL(OWNER_NAME,''),
            LTRIM(ISNULL(ADDRESS,'')+' '+ISNULL(ADDRESS_DTL,'')),ISNULL(PHONE_NO,''),ISNULL(FAX_NO,''),
            ISNULL(BUSI_TYPE,''),ISNULL(BUSI_KIND,'') FROM PARTNER_ERP_TEST3.nx.CM_M_COMPANY""")
        b = cur.fetchone() or ('',)*8
        buyer = {"biz": _fmtbiz(b[0]), "nm": (b[1] or '').strip(), "owner": (b[2] or '').strip(),
                 "addr": (b[3] or '').strip(), "tel": (b[4] or '').strip(), "fax": (b[5] or '').strip(),
                 "btype": (b[6] or '').strip(), "bkind": (b[7] or '').strip()}
        # 품목명/규격 배치조회(라이브)
        assys = sorted({str(r[1]).strip() for r in drows if r[1]})
        nmm = {}
        for i in range(0, len(assys), 900):
            ch = assys[i:i+900]; ph = ",".join("?"*len(ch))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,''), ISNULL(ITEM_SPEC,''), ISNULL(UNIT,'EA') FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ch)
            for rr in cur.fetchall(): nmm[str(rr[0]).strip()] = (rr[1], rr[2], rr[3])
    finally:
        cn.close()
    rows = []; tot = 0.0
    for cc, item, dq, pk, sn, hn, iy, stt in drows:
        item = str(item).strip()
        nm, spec, unit = nmm.get(item, ("", "", "EA"))
        q = float(dq or 0); tot += q
        rows.append({"doban": item, "nm": (nm or '').strip(), "spec": (spec or '').strip(),
                     "unit": (unit or 'EA').strip(), "qty": _qint(q), "pack": _qint(pk or 0),
                     "serial": (sn or '').strip(), "heat": (hn or '').strip()})
    return {"barcode": "SET" + bcnum, "raw": bcnum, "code": "SET" + bcnum, "ymd": ymd_disp,
            "custnm": supplier["nm"] or cust, "cust": cust,
            "supplier": supplier, "buyer": buyer, "rows": rows, "total": _qint(tot), "count": len(rows)}
