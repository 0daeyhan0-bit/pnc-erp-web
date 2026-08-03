# -*- coding: utf-8 -*-
"""원가(cost) 도메인 라우터 — 견적원가조회(esti)·실원가/내부원가(cost/nx,sil,nae)·비교·재생성.
   app.py에서 분리. 공유헬퍼는 common.py에서 import."""
import os
from fastapi import APIRouter, Query, Body, HTTPException, Response
from common import (_conn, _nx, _num, _run_sp, _shape, _get_cost_engine, _reset_cost_engine,
                    _COST_LOCK, SP_SIL, SP_NAE, _HERE, NxCostEngine)

router = APIRouter()

def _esti_agg_from_nx(eng, item, ymd):
    """nx 원가엔진(NxCostEngine) 결과 → 레거시 esti agg 구조(프론트 estiToRow 호환).
    ※레거시 SP EXECUTE 권한 부재로 nx엔진(검증완료 실원가)으로 대체(B안).
      재료비 원/부/사급 분해(WON/BU/SA)와 내부용 별도산식은 nx엔진에 없어 0/실원가값으로 채움."""
    r = eng.silwon(item, ymd)
    try: lme = eng.lme_total(item, ymd)
    except Exception: lme = 0.0
    return {
        "WON_JAI_AMT": 0.0, "BU_JAI_AMT": 0.0, "SA_JAI_AMT": 0.0,   # nx엔진: 재료비 원/부/사급 미분해
        "JAI_COST": _num(r.get('jae')),
        "GAGONG_AMT": _num(r.get('gagong')),
        "ILBAN_AMT": _num(r.get('ilban')),
        "UNBAN_AMT": _num(r.get('unban')),
        "PROFIT_AMT": _num(r.get('profit')),
        "LME_CHA_AMT": _num(lme),
        "TOT_AMT": _num(r.get('silwon')),
        "LG_COST": _num(r.get('lg')),
        "SONIK": _num(r.get('sonik')),
    }

@router.get("/api/esti")
def esti(item: str = Query(..., description="품번 (PART-NO)"),
         ymd: str = Query('260630', description="단가기준일 YYMMDD")):
    """견적원가(실원가·내부용) — nx 원가엔진으로 라이브 산출(레거시 SP 미사용, B안).
    내부용 별도 SP엔진이 없어 nae=sil(검증완료 실원가) 동일값으로 반환."""
    item = item.strip(); ymd = ymd.strip()
    if not item:
        raise HTTPException(400, "item(품번) 필요")
    if NxCostEngine is None:
        raise HTTPException(500, "nx_cost_engine 로드 실패")
    eng = NxCostEngine()
    try:
        agg = _esti_agg_from_nx(eng, item, ymd)
    except Exception as e:
        raise HTTPException(500, f"nx엔진 오류: {e}")
    finally:
        eng.close()
    shaped = {"rows": [], "agg": agg}
    # sil(실원가)·nae(내부용) 동일 nx엔진 결과. 내부용 별도산식 부재 — 프론트 렌더 유지용.
    return {"item": item, "ymd": ymd, "sil": shaped, "nae": shaped}


# ===================== nx 원가엔진 (durable, 라이브 nx테이블 재계산) =====================
@router.get("/api/cost/nx")
def cost_nx(item: str = Query(..., description="품번"),
            ymd: str = Query('260630', description="단가기준일 YYMMDD")):
    """검증완료 nx 원가엔진으로 실원가·손익 라이브 산출(스냅샷 아님)."""
    if NxCostEngine is None:
        raise HTTPException(500, "nx_cost_engine 로드 실패")
    item = item.strip(); ymd = ymd.strip()
    if not item: raise HTTPException(400, "item(품번) 필요")
    eng = NxCostEngine()
    try:
        r = eng.silwon(item, ymd)
        return {"item": item, "ymd": ymd, "nx": r}
    except Exception as e:
        raise HTTPException(500, f"nx엔진 오류: {e}")
    finally:
        eng.close()

@router.get("/api/cost/sil")
def cost_sil(item: str = Query(..., description="품번"),
             ymd: str = Query('260630', description="단가기준일 YYMMDD"),
             fresh: int = Query(0, description="1=엔진캐시 무시 최신계산(재계산 버튼)")):
    """실원가 — ★현재 매핑된 nx.bom을 지정된 조달방식대로. 사내(INNER_PROD)=소재×중량+가공, 외주완성/구매=매입단가,
       LME 사급차액 소급, 가공비=사내노드만. 레거시 실원가용 SP와 diff0(오라클 검증). 내부원가와 같은 BOM, 계산방식만 다름."""
    if NxCostEngine is None:
        raise HTTPException(500, "nx_cost_engine 로드 실패")
    item = item.strip(); ymd = ymd.strip()
    if not item: raise HTTPException(400, "item(품번) 필요")
    def _compute(eng):
        d = eng.silwon_nodes(item, ymd)
        pg = eng.silwon_proc_grid(item, ymd)   # {proc_code:{wq,amt,uph,cg,labor}} — 합=가공비
        procs = _nae_proc_grid(pg)             # CS_M_PROC 공정명·정렬·그룹 매핑(내부원가와 공유)
        # 거래처(매입처)명 매핑 — nx.partner 우선, CM_M_CUST 폴백
        codes = sorted({r["in_cust"] for r in d["rows"] if r.get("in_cust")})
        vmap = {}
        if codes:
            try:
                for i in range(0, len(codes), 900):
                    ch = codes[i:i + 900]; ph = ",".join("?" * len(ch))
                    eng.cur.execute(f"SELECT partner_code, ISNULL(partner_name,'') FROM nx.partner WHERE partner_code IN ({ph})", *ch)
                    for r in eng.cur.fetchall(): vmap[str(r[0]).strip()] = str(r[1]).strip()
            except Exception:
                pass
            miss = [c for c in codes if not vmap.get(c)]
            if miss:
                try:
                    cn = _conn(); c2 = cn.cursor()
                    try:
                        for i in range(0, len(miss), 900):
                            ch = miss[i:i + 900]; ph = ",".join("?" * len(ch))
                            c2.execute(f"SELECT CUST_CODE, ISNULL(CUST_DESC,'') FROM PARTNER_ERP.dbo.CM_M_CUST WHERE CUST_CODE IN ({ph})", *ch)
                            for r in c2.fetchall(): vmap.setdefault(str(r[0]).strip(), str(r[1]).strip())
                    finally:
                        cn.close()
                except Exception:
                    pass
        for r in d["rows"]:
            r["cust_name"] = vmap.get(r.get("in_cust", ""), "")
        return {"item": item, "ymd": ymd, "rows": d["rows"], "agg": d["agg"],
                "procs": procs, "labor": (procs[0]["labor"] if procs else 0)}
    with _COST_LOCK:
        try:
            return _compute(_get_cost_engine(fresh=bool(fresh)))
        except Exception:
            try:                                    # 커넥션 만료/오류 → 엔진 재생성 1회 재시도
                return _compute(_get_cost_engine(fresh=True))
            except Exception as e2:
                raise HTTPException(500, f"nx엔진 오류: {e2}")

@router.get("/api/cost/nae")
def cost_nae(item: str = Query(..., description="품번"),
             ymd: str = Query('260630', description="단가기준일 YYMMDD"),
             bom: str = Query('nx', description="nx=우리 nx.bom(레거시 내부용 diff0, 기본·정본), lg=LG BOM 참조전개"),
             fresh: int = Query(0, description="1=엔진캐시 무시 최신계산(재계산 버튼)")):
    """내부원가 — ★우리 BOM(nx.bom) 기준(대표 확정). 전공정 우리제작 가정(naewon), 레거시 내부용 diff0.
       bom='lg'면 LG BOM 원본전개(참조용, 우리BOM과 품번/구조 다를 수 있음)."""
    if NxCostEngine is None:
        raise HTTPException(500, "nx_cost_engine 로드 실패")
    item = item.strip(); ymd = ymd.strip()
    if not item: raise HTTPException(400, "item(품번) 필요")
    def _compute(eng):
        if bom == 'lg':
            d = eng.naewon_lg(item, ymd)
            return {"item": item, "ymd": ymd, "bom": bom, "rows": d["rows"], "agg": d["agg"], "procs": []}
        d = eng.naewon_nodes(item, ymd)
        pg = eng.proc_grid(item, ymd)   # {proc_code:{wq,amt,uph,cg,labor}} — 합=가공비
        procs = _nae_proc_grid(pg)      # CS_M_PROC 공정명·정렬·그룹(용접/체결) 매핑
        return {"item": item, "ymd": ymd, "bom": bom, "rows": d["rows"], "agg": d["agg"],
                "procs": procs, "labor": (procs[0]["labor"] if procs else 0)}
    with _COST_LOCK:
        try:
            return _compute(_get_cost_engine(fresh=bool(fresh)))
        except Exception:
            try:                                    # 커넥션 만료/오류 → 엔진 재생성 1회 재시도
                return _compute(_get_cost_engine(fresh=True))
            except Exception as e2:
                raise HTTPException(500, f"nx엔진 오류: {e2}")

# 공정 그룹(보기구분 용접/체결 필터용). 코드 기준(CS_M_PROC): 용접=용접+은납, 체결=부품부착·삽입·체결계열
_PROC_WELD = {"51", "28"}                                                    # 용접, 은납
_PROC_FASTEN = {"55", "52", "69", "70", "71", "72", "73", "74", "75", "76",   # 부품부착·지그삽입·NUT체결·FLARE·CAP·제함·각종삽입
                "77", "78", "79", "80", "81", "82", "68", "23", "24", "25"}   # +SIZING·실링·망삽입·막음(조립성)
def _proc_group(code):
    if code in _PROC_WELD: return "용접"
    if code in _PROC_FASTEN: return "체결"
    if code == "61" or code == "83": return "포장"
    return "가공"

def _nae_proc_grid(pg: dict):
    """proc_grid(코드별 집계)에 CS_M_PROC 공정명·정렬순서·보기구분 그룹을 붙여 정렬 리스트로."""
    if not pg: return []
    names = {}
    try:
        cn = _conn(); c2 = cn.cursor()
        try:
            codes = list(pg.keys())
            for i in range(0, len(codes), 900):
                ch = codes[i:i + 900]; ph = ",".join("?" * len(ch))
                c2.execute(f"SELECT PROC_CODE, ISNULL(PROC_DESC,''), ISNULL(SORT_SEQ,0) FROM CS_M_PROC WHERE PROC_CODE IN ({ph})", *ch)
                for r in c2.fetchall():
                    names[str(r[0]).strip()] = {"nm": str(r[1]).strip(), "seq": int(r[2] or 0)}
        finally:
            cn.close()
    except Exception:
        names = {}
    out = []
    for code, v in pg.items():
        m = names.get(code, {})
        out.append({"code": code, "name": m.get("nm", code), "seq": m.get("seq", 999),
                    "group": _proc_group(code), "wq": v["wq"], "amt": v["amt"],
                    "uph": v["uph"], "cg": v["cg"], "labor": v["labor"]})
    out.sort(key=lambda x: (x["seq"], x["code"]))
    return out

@router.get("/api/cost/lgcompare")
def cost_lgcompare(ymd: str = Query('260630', description="단가기준일 YYMMDD"),
                   n: int = Query(20, description="샘플 개수")):
    """LG BOM 내부원가(naewon_lg) vs 오라클(nx.bom naewon=레거시 내부용 diff0) 샘플 대조.
       여러 형태 BOM 샘플링(노드수 단순→복잡) — 재료/가공/내부원가 diff + 판정(일치/불일치 전부 반환)."""
    if NxCostEngine is None:
        raise HTTPException(500, "nx_cost_engine 로드 실패")
    eng = NxCostEngine(); cur = eng.cur
    try:
        cur.execute("""SELECT lb.model, COUNT(*) c FROM (SELECT DISTINCT model FROM nx.lg_bom) lb
            JOIN nx.bom_header h ON h.item_code=lb.model
            JOIN nx.lg_bom g ON g.model=lb.model GROUP BY lb.model ORDER BY c""")
        allm = [r[0] for r in cur.fetchall()]
        step = max(1, len(allm) // max(1, n))
        picks = [allm[i] for i in range(0, len(allm), step)][:n]
        rows = []; npass = 0
        for it in picks:
            try:
                o = eng.naewon(it, ymd); lg = eng.naewon_lg(it, ymd)['agg']
                dj = round(lg['jae'] - o['jae'], 1); dg = round(lg['gagong'] - o['gagong'], 1); dn = round(lg['naewon'] - o['naewon'], 1)
                ok = abs(dj) < 1 and abs(dg) < 1 and abs(dn) < 1
                if ok: npass += 1
                rows.append({"item": it, "jae_leg": round(o['jae']), "jae_lg": round(lg['jae']), "jae_diff": dj,
                    "gag_leg": round(o['gagong']), "gag_lg": round(lg['gagong']), "gag_diff": dg,
                    "nae_leg": round(o['naewon']), "nae_lg": round(lg['naewon']), "nae_diff": dn, "ok": ok})
            except Exception as e:
                rows.append({"item": it, "err": str(e)[:60], "ok": False})
        return {"ymd": ymd, "total": len(picks), "pass": npass, "fail": len(picks) - npass, "rows": rows}
    finally:
        eng.close()

@router.get("/api/cost/compare")
def cost_compare(item: str = Query(..., description="품번"),
                 ymd: str = Query('260630', description="단가기준일 YYMMDD")):
    """레거시 SP(실원가용) vs nx엔진 성분별 대조 — durable 엔진 검증 화면용."""
    item = item.strip(); ymd = ymd.strip()
    if not item: raise HTTPException(400, "item(품번) 필요")
    # 레거시 SP
    sp = {}
    try:
        c, rr = _run_sp(SP_SIL, item, ymd)
        ix = {x: i for i, x in enumerate(c or [])}
        top = next((r for r in rr if str(r[ix.get('C_ITEM_LEVEL', -1)]) == '0'), None)
        def g(f): return _num(top[ix[f]]) if (top is not None and f in ix) else 0.0
        sp = {"jae": g('JAI_COST'), "gagong": g('GAGONG_AMT'), "ilban": g('ILBAN_AMT'),
              "unban": g('UNBAN_AMT'), "profit": g('PROFIT_AMT'), "silwon": g('TOT_AMT'),
              "lg": g('LG_COST'), "sonik": round(g('LG_COST') - g('TOT_AMT'), 2)}
    except Exception as e:
        sp = {"error": str(e)[:100]}
    # nx 엔진
    nx = {}
    if NxCostEngine is not None:
        eng = NxCostEngine()
        try: nx = eng.silwon(item, ymd)
        except Exception as e: nx = {"error": str(e)[:100]}
        finally: eng.close()
    # 성분별 차이
    diff = {}
    if 'error' not in sp and 'error' not in nx:
        for k in ['jae', 'gagong', 'ilban', 'unban', 'profit', 'silwon', 'lg', 'sonik']:
            diff[k] = round((nx.get(k, 0) or 0) - (sp.get(k, 0) or 0), 2)
    return {"item": item, "ymd": ymd, "sp": sp, "nx": nx, "diff": diff}


# ===================== 품목별원가분석 벌크 재계산 (nx엔진, costdata.js 갱신) =====================
import threading, json as _json, time as _time
_COSTDATA_JS = os.path.join(_HERE, '..', 'js', 'costdata.js')   # ...\PNC_ERP_Web\js\costdata.js
_regen = {"running": False, "done": 0, "total": 0, "ymd": "", "error": "", "sec": 0}

def _regen_worker(ymd):
    global _regen
    t0 = _time.time()
    try:
        raw = open(_COSTDATA_JS, 'rb').read().decode('utf-8', 'ignore')
        D = _json.loads(raw.split('window.COSTDATA=', 1)[1].strip().rstrip(';'))
        ci = {c: i for i, c in enumerate(D['cols'])}
        _regen['total'] = len(D['rows'])
        eng = NxCostEngine()
        sales = silamt = impact = 0.0; loss = 0
        for r in D['rows']:
            part = r[ci['part']]; qty = float(r[ci['qty']] or 0)
            try:
                s = eng.silwon(part, ymd); jae = s['jae']; lme = s.get('lme_total') or eng.lme_total(part, ymd)
                osum = (r[ci['s_raw']] or 0) + (r[ci['s_bu']] or 0) + (r[ci['s_lg']] or 0)
                if osum > 0:
                    r[ci['s_raw']] = round((r[ci['s_raw']] or 0)/osum*jae); r[ci['s_bu']] = round((r[ci['s_bu']] or 0)/osum*jae); r[ci['s_lg']] = round((r[ci['s_lg']] or 0)/osum*jae)
                else:
                    r[ci['s_raw']] = round(jae)
                r[ci['s_mat']] = round(jae); r[ci['s_sil']] = round(s['silwon']); r[ci['s_gag']] = round(s['gagong'])
                r[ci['s_ilban']] = round(s['ilban']); r[ci['s_unban']] = round(s['unban']); r[ci['s_profit']] = round(s['profit'])
                r[ci['s_lme']] = round(lme); r[ci['lg']] = round(s['lg']); r[ci['sonik']] = round(s['sonik'])
                r[ci['s_ratio']] = round(jae/s['lg'], 3) if s['lg'] else 0
                r[ci['lgtot']] = round(s['lg']*qty); r[ci['impact']] = round(s['sonik']*qty)
                sales += s['lg']*qty; silamt += s['silwon']*qty; impact += s['sonik']*qty
                if s['sonik'] < 0: loss += 1
            except Exception:
                pass
            _regen['done'] += 1
        eng.close()
        D['base'] = ymd
        D['agg'] = {"cnt": len(D['rows']), "qty": round(sum(float(x[ci['qty']] or 0) for x in D['rows'])),
                    "sales": round(sales), "silamt": round(silamt), "naeamt": D['agg'].get('naeamt', 0),
                    "impact": round(impact), "loss": loss}
        out = '/* nx엔진 재계산 (실원가·LME·LG·손익) · 기준일 ' + ymd + ' · nx_cost_engine.py */\nwindow.COSTDATA=' + _json.dumps(D, ensure_ascii=False, separators=(',', ':')) + ';'
        open(_COSTDATA_JS, 'w', encoding='utf-8').write(out)
    except Exception as e:
        _regen['error'] = str(e)[:200]
    finally:
        _regen['sec'] = round(_time.time() - t0); _regen['running'] = False

@router.post("/api/cost/regen")
def cost_regen(p: dict = Body(...)):
    """costdata.js를 지정 단가일자로 nx엔진 재계산(백그라운드). status로 진행률 폴링."""
    global _regen
    if _regen.get('running'): raise HTTPException(409, "이미 재계산 중")
    if NxCostEngine is None: raise HTTPException(500, "nx엔진 로드 실패")
    ymd = str(p.get('ymd') or '260630').strip()
    _regen = {"running": True, "done": 0, "total": 0, "ymd": ymd, "error": "", "sec": 0}
    threading.Thread(target=_regen_worker, args=(ymd,), daemon=True).start()
    return {"ok": True, "ymd": ymd}

@router.get("/api/cost/regen/status")
def cost_regen_status():
    return _regen


# ===================== 공정 지정(내부원가 수정) — carrier-aware: 가공(node own) + 조립(용접/체결/포장, 용접봉 carrier·p_item=node) =====================
#  ★체결·포장·용접 조립공정 ST는 용접봉(RAC) carrier에 p_item=부모(node)로 저장(레거시 carrier 모델). 여기서 전 공정군 편집.
#   가공공정 = item_code=node, p_item=''  /  조립공정 = item_code=용접봉, p_item=node. calc_gubun 보존. 단가는 마감때만(제외).
_ASSY_PROCS = _PROC_WELD | _PROC_FASTEN | {"61", "83"}   # 용접·은납·체결계열·포장(=carrier 조립공정)

@router.get("/api/cost/proc/get")
def cost_proc_get(node: str = Query(..., description="공정 편집 대상 품목(어셈블리/SUB/부품)")):
    """전 공정군(가공+용접+체결+포장) 편집목록. 가공=node own(p_item=''), 조립=용접봉 carrier(p_item=node) 합산."""
    node = node.strip()
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT proc_code,ISNULL(work_qty,0),ISNULL(prod_uph,0),ISNULL(calc_gubun,'') FROM nx.routing WHERE item_code=? AND ISNULL(p_item,'')=''", node)
        own = {str(r[0]).strip(): {"wq": float(r[1] or 0), "uph": float(r[2] or 0), "cg": (str(r[3]).strip() or "3")} for r in cur.fetchall()}
        # ★엔진이 실제 walk하는 용접봉 carrier = proc_weld[node] 만(orphan routing 제외 → 가공비 정합)
        carriers = []
        try:
            cur.execute("SELECT DISTINCT weld_item FROM nx.proc_weld WHERE parent_item=?", node)
            carriers = [str(r[0]).strip() for r in cur.fetchall() if str(r[0]).strip()]
        except Exception:
            carriers = []
        assy = {}
        if carriers:
            ph = ",".join("?" * len(carriers))
            cur.execute(f"""SELECT proc_code, SUM(work_qty), MAX(ISNULL(prod_uph,0)), MAX(ISNULL(calc_gubun,''))
                FROM nx.routing WHERE p_item=? AND item_code IN ({ph}) AND ISNULL(work_qty,0)>0 GROUP BY proc_code""", node, *carriers)
            assy = {str(r[0]).strip(): {"wq": float(r[1] or 0), "uph": float(r[2] or 0), "cg": (str(r[3]).strip() or "3")} for r in cur.fetchall()}
        # 대표 carrier = proc_weld 소요량 최대(walked)
        carrier = ""
        if carriers:
            cur.execute("SELECT TOP 1 weld_item FROM nx.proc_weld WHERE parent_item=? ORDER BY use_qty DESC, weld_item", node)
            r = cur.fetchone(); carrier = str(r[0]).strip() if r else carriers[0]
        # 관경(원단위 재계산용)
        cur.execute("SELECT ISNULL(diam,0) FROM nx.item WHERE item_code=?", node)
        r = cur.fetchone(); pdiam = float(r[0] or 0) if r else 0.0
    finally:
        nx.close()
    cn = _conn(); c2 = cn.cursor()
    try:
        c2.execute("SELECT PROC_CODE,ISNULL(PROC_DESC,''),ISNULL(SORT_SEQ,0) FROM CS_M_PROC WHERE ISNULL(TRY_CONVERT(int,PROC_CODE),99)<90 AND ISNULL(USE_FLAG,'1')<>'0' ORDER BY ISNULL(SORT_SEQ,0),PROC_CODE")
        procs = []
        for r in c2.fetchall():
            pc = str(r[0]).strip(); g = _proc_group(pc)
            ex = (assy.get(pc) if pc in _ASSY_PROCS else own.get(pc)) or {}
            procs.append({"proc_code": pc, "name": str(r[1]).strip(), "group": g, "is_assy": pc in _ASSY_PROCS,
                          "work_qty": ex.get("wq", 0), "prod_uph": ex.get("uph", 0), "calc_gubun": ex.get("cg", "3")})
    finally:
        cn.close()
    return {"node": node, "carrier": carrier, "pipe_diam": pdiam, "procs": procs,
            "has_own": any(v["work_qty"] > 0 for v in procs if not v["is_assy"]),
            "has_assy": any(v["work_qty"] > 0 for v in procs if v["is_assy"])}

@router.post("/api/cost/proc/save")
def cost_proc_save(payload: dict = Body(...)):
    """공정 지정 저장 — 가공=node own(p_item=''), 조립(용접/체결/포장)=용접봉 carrier(p_item=node). calc_gubun 보존.
       ★용접/은납 ST 변경 시 proc_weld.use_qty(=Σ용접·은납ST×관경원단위×1.5) 자동 재계산. 단가는 미변경(마감때만)."""
    node = str(payload.get("node", "")).strip()
    rows = payload.get("rows", []) or []
    carrier = str(payload.get("carrier", "")).strip()
    if not node:
        raise HTTPException(400, "node 필요")
    keep = [(str(r.get("proc_code", "")).strip(), float(r.get("work_qty") or 0), float(r.get("prod_uph") or 0),
             (str(r.get("calc_gubun", "")).strip() or "3"))
            for r in rows if str(r.get("proc_code", "")).strip() and float(r.get("work_qty") or 0) > 0]
    assy_rows = [k for k in keep if k[0] in _ASSY_PROCS]
    if assy_rows and not carrier:
        raise HTTPException(400, "조립공정(용접/체결/포장) 저장하려면 용접봉(carrier)이 필요합니다 — 이 품목에 용접봉이 없습니다.")
    nx = _nx(); cur = nx.cursor()
    try:
        # 가공(own) 교체: item_code=node, p_item='' , proc<90
        cur.execute("DELETE FROM nx.routing WHERE item_code=? AND ISNULL(p_item,'')='' AND ISNULL(TRY_CONVERT(int,proc_code),99)<90", node)
        # 조립 교체: p_item=node, ★엔진이 walk하는 용접봉(proc_weld) carrier만 정리 후 대표 carrier로 통합(orphan routing 미개입=가공비 정합)
        cur.execute("SELECT DISTINCT weld_item FROM nx.proc_weld WHERE parent_item=?", node)
        wc = [str(r[0]).strip() for r in cur.fetchall() if str(r[0]).strip()]
        if carrier and carrier not in wc: wc.append(carrier)
        if wc:
            ph = ",".join("?" * len(wc))
            cur.execute(f"DELETE FROM nx.routing WHERE p_item=? AND item_code IN ({ph})", node, *wc)
        seq = 0
        for pc, wq, uph, cg in keep:
            if pc in _ASSY_PROCS:
                cur.execute("INSERT INTO nx.routing(p_item,item_code,proc_code,work_qty,prod_uph,calc_gubun,sort_seq) VALUES(?,?,?,?,?,?,?)",
                            node, carrier, pc, wq, uph, cg, seq * 10)
            else:
                cur.execute("INSERT INTO nx.routing(p_item,item_code,proc_code,work_qty,prod_uph,calc_gubun,sort_seq) VALUES('',?,?,?,?,?,?)",
                            node, pc, wq, uph, cg, seq * 10)
            seq += 1
        # ★용접ST 변경 → proc_weld.use_qty 재계산(carrier): Σ(용접51+은납28 ST) × 관경 원단위 × 1.5
        recalc = None
        if carrier:
            weld_st = sum(wq for pc, wq, uph, cg in keep if pc in _PROC_WELD)
            cur.execute("SELECT ISNULL(diam,0) FROM nx.item WHERE item_code=?", node)
            r = cur.fetchone(); pdiam = float(r[0] or 0) if r else 0.0
            cur.execute("SELECT MIN(std_use_qty) FROM nx.weld_diam WHERE ABS(pipe_diam-?)<0.001", pdiam)
            r = cur.fetchone(); unit = float(r[0] or 0) if r and r[0] is not None else 0.0
            if weld_st > 0 and unit > 0:
                recalc = round(weld_st * unit * 1.5, 6)
                cur.execute("UPDATE nx.proc_weld SET use_qty=?, weld_st=?, unit_qty=?, pipe_diam=?, upd_dt=getdate() WHERE parent_item=? AND weld_item=?",
                            recalc, weld_st, unit, pdiam, node, carrier)
        _reset_cost_engine()
        return {"ok": True, "count": seq, "assy": len(assy_rows), "carrier": carrier, "weld_use_qty_recalc": recalc}
    finally:
        nx.close()
