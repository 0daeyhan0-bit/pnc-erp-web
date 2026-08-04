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
_ASSY_PROCS = _PROC_WELD | _PROC_FASTEN | {"61", "83"}   # 용접·은납·체결계열·포장(대표 조립공정군, 라벨/추가용)
def _lt90(code):
    """율(91/92/93/98/99) 제외한 실공정(proc<90)인지 — carrier엔 조립공정 외 가공공정(예:53)도 귀속되므로 전체 보존 대상."""
    try: return int(str(code).strip()) < 90
    except Exception: return bool(str(code).strip())   # 비숫자 코드는 실공정으로 간주

@router.get("/api/cost/proc/get")
def cost_proc_get(node: str = Query(..., description="공정 편집 대상 품목(어셈블리/SUB/부품)")):
    """전 공정군 편집목록. 가공=node own(p_item=''), 조립(용접/체결/포장)=용접봉 carrier별(p_item=node) **carrier별로 분리** 반환.
       ★엔진은 carrier별로 독립 계상(다중경로 walk) → 절대 carrier 통합/이동 금지. 레거시 w_cs_esti_010의 용접봉 행별 편집과 동일 모델."""
    node = node.strip()
    # 공정 카탈로그(코드→이름·정렬)
    cat = {}
    cn = _conn(); c2 = cn.cursor()
    try:
        c2.execute("SELECT PROC_CODE,ISNULL(PROC_DESC,''),ISNULL(SORT_SEQ,0) FROM CS_M_PROC WHERE ISNULL(TRY_CONVERT(int,PROC_CODE),99)<90 AND ISNULL(USE_FLAG,'1')<>'0' ORDER BY ISNULL(SORT_SEQ,0),PROC_CODE")
        for r in c2.fetchall():
            pc = str(r[0]).strip()
            cat[pc] = {"name": str(r[1]).strip(), "seq": int(r[2] or 0), "group": _proc_group(pc), "is_assy": pc in _ASSY_PROCS}
    finally:
        cn.close()
    def _catrow(pc, wq, uph, cg):
        m = cat.get(pc, {"name": pc, "group": _proc_group(pc), "is_assy": pc in _ASSY_PROCS})
        return {"proc_code": pc, "name": m["name"], "group": m["group"], "is_assy": m["is_assy"],
                "work_qty": wq, "prod_uph": uph, "calc_gubun": cg}
    nx = _nx(); cur = nx.cursor()
    try:
        # 가공(own): p_item='' 조립외 공정 (91/92/93/98/99 율 제외)
        cur.execute("SELECT proc_code,ISNULL(work_qty,0),ISNULL(prod_uph,0),ISNULL(calc_gubun,'') FROM nx.routing WHERE item_code=? AND ISNULL(p_item,'')='' AND ISNULL(work_qty,0)>0 AND ISNULL(TRY_CONVERT(int,proc_code),99)<90", node)
        own = [_catrow(str(r[0]).strip(), float(r[1] or 0), float(r[2] or 0), (str(r[3]).strip() or "3")) for r in cur.fetchall()]
        own.sort(key=lambda x: cat.get(x["proc_code"], {}).get("seq", 999))
        # 용접봉 carrier 목록(proc_weld). 각 carrier의 조립공정을 carrier별 분리 반환(통합 금지)
        carriers = []
        try:
            cur.execute("SELECT weld_item, ISNULL(use_qty,0), ISNULL(pipe_diam,0), ISNULL(unit_qty,0), ISNULL(loss_factor,1.5), ISNULL(meta_ok,0) FROM nx.proc_weld WHERE parent_item=? ORDER BY use_qty DESC, weld_item", node)
            cw = [(str(r[0]).strip(), float(r[1] or 0), float(r[2] or 0), float(r[3] or 0), float(r[4] or 1.5), int(r[5] or 0)) for r in cur.fetchall() if str(r[0]).strip()]
        except Exception:
            cw = []
        for wi, uq, pd, un, lf, mok in cw:
            cur.execute("SELECT proc_code,ISNULL(work_qty,0),ISNULL(prod_uph,0),ISNULL(calc_gubun,'') FROM nx.routing WHERE p_item=? AND item_code=? AND ISNULL(work_qty,0)>0 AND ISNULL(TRY_CONVERT(int,proc_code),99)<90 ORDER BY sort_seq,proc_code", node, wi)
            aprocs = [_catrow(str(r[0]).strip(), float(r[1] or 0), float(r[2] or 0), (str(r[3]).strip() or "3")) for r in cur.fetchall()]
            carriers.append({"weld_item": wi, "use_qty": uq, "pipe_diam": pd, "unit_qty": un, "loss_factor": lf, "meta_ok": mok, "procs": aprocs})
        cur.execute("SELECT ISNULL(diam,0) FROM nx.item WHERE item_code=?", node)
        r = cur.fetchone(); pdiam = float(r[0] or 0) if r else 0.0
    finally:
        nx.close()
    # 카탈로그(추가용): 가공공정군 / 조립공정군 분리 목록
    catalog = [dict(proc_code=pc, **{k: v for k, v in m.items() if k != "seq"}) for pc, m in sorted(cat.items(), key=lambda kv: kv[1]["seq"])]
    return {"node": node, "pipe_diam": pdiam, "own_procs": own, "carriers": carriers, "catalog": catalog,
            "has_own": bool(own), "has_carrier": bool(carriers)}

@router.post("/api/cost/proc/save")
def cost_proc_save(payload: dict = Body(...)):
    """공정 지정 저장 — **carrier별 in-place**(이동/통합 금지). 가공=node own(p_item=''), 조립=각 용접봉 carrier(p_item=node).
       율(91/92/93/98/99)·비대상 carrier·orphan routing 미개입. 용접/은납 ST 변경 시 해당 carrier proc_weld.use_qty(=ΣST×관경원단위×1.5) 재계산. 단가 미변경(마감때만)."""
    node = str(payload.get("node", "")).strip()
    if not node:
        raise HTTPException(400, "node 필요")
    own_rows = payload.get("own_procs", []) or []
    carriers = payload.get("carriers", []) or []
    def _clean(rows):
        return [(str(r.get("proc_code", "")).strip(), float(r.get("work_qty") or 0), float(r.get("prod_uph") or 0),
                 (str(r.get("calc_gubun", "")).strip() or "3"))
                for r in rows if str(r.get("proc_code", "")).strip() and float(r.get("work_qty") or 0) > 0]
    nx = _nx(); cur = nx.cursor()
    try:
        # 가공(own) 교체: item_code=node, p_item='', 조립외(proc<90, non-assy), 율 보존
        own = [k for k in _clean(own_rows) if k[0] not in _ASSY_PROCS]
        cur.execute("DELETE FROM nx.routing WHERE item_code=? AND ISNULL(p_item,'')='' AND ISNULL(TRY_CONVERT(int,proc_code),99)<90", node)
        seq = 0
        for pc, wq, uph, cg in own:
            if pc in _ASSY_PROCS: continue
            cur.execute("INSERT INTO nx.routing(p_item,item_code,proc_code,work_qty,prod_uph,calc_gubun,sort_seq) VALUES('',?,?,?,?,?,?)", node, pc, wq, uph, cg, seq * 10)
            seq += 1
        # carrier별 조립공정 in-place 교체 — 각 carrier의 assy(proc<90)만 삭제·재삽입(율·비대상 carrier 불개입)
        recalcs = []
        for cinfo in carriers:
            wi = str(cinfo.get("weld_item", "")).strip()
            if not wi: continue
            # ★carrier의 proc<90 전체 보존(용접·은납·체결·포장 + 조립귀속 가공공정 예:53). 율(91+)만 불개입.
            arows = [k for k in _clean(cinfo.get("procs", [])) if _lt90(k[0])]
            cur.execute("DELETE FROM nx.routing WHERE p_item=? AND item_code=? AND ISNULL(TRY_CONVERT(int,proc_code),99)<90", node, wi)
            s2 = 0
            for pc, wq, uph, cg in arows:
                cur.execute("INSERT INTO nx.routing(p_item,item_code,proc_code,work_qty,prod_uph,calc_gubun,sort_seq) VALUES(?,?,?,?,?,?,?)", node, wi, pc, wq, uph, cg, s2 * 10)
                s2 += 1
            # 용접/은납 ST(51+28) 변경 → 해당 carrier proc_weld.use_qty 재계산 = ST × 원단위(unit_qty) × loss_factor(배수)
            #   ★스토어드 메타(unit_qty·loss_factor) 사용 · meta_ok=1(재계산 신뢰) 且 ST 변경 시에만 갱신(무변경=정본 use_qty 불변, 드리프트 0)
            #   loss_factor는 프론트에서 carrier별 수정 가능(배수 파라미터). 정본 산식=레거시 전역 1.5.
            new_st = sum(wq for pc, wq, uph, cg in arows if pc in _PROC_WELD)
            lf_in = cinfo.get("loss_factor", None)
            cur.execute("SELECT ISNULL(unit_qty,0),ISNULL(weld_st,0),ISNULL(loss_factor,1.5),ISNULL(meta_ok,0),ISNULL(use_qty,0) FROM nx.proc_weld WHERE parent_item=? AND weld_item=?", node, wi)
            r = cur.fetchone()
            if r:
                unit, cur_st, lf0, mok, use0 = float(r[0] or 0), float(r[1] or 0), float(r[2] or 1.5), int(r[3] or 0), float(r[4] or 0)
                lf = float(lf_in) if (lf_in is not None and str(lf_in).strip() != "") else lf0
                lf_changed = abs(lf - lf0) > 1e-9
                st_changed = abs(new_st - cur_st) > 1e-9
                if mok == 1 and unit > 0 and (st_changed or lf_changed):
                    rc = round(new_st * unit * lf, 6)
                    cur.execute("UPDATE nx.proc_weld SET use_qty=?, weld_st=?, loss_factor=?, upd_dt=getdate() WHERE parent_item=? AND weld_item=?", rc, new_st, lf, node, wi)
                    recalcs.append({"carrier": wi, "weld_st": new_st, "loss_factor": lf, "use_qty": rc, "prev_use_qty": use0})
                elif lf_changed and mok != 1:
                    # 배수만 저장(재계산 불가 carrier — use_qty 정본 보존)
                    cur.execute("UPDATE nx.proc_weld SET loss_factor=? WHERE parent_item=? AND weld_item=?", lf, node, wi)
        _reset_cost_engine()
        return {"ok": True, "own": seq, "carriers": len(carriers), "weld_recalc": recalcs}
    finally:
        nx.close()

@router.get("/api/weld/get")
def weld_get(node: str = Query(..., description="용접 관경별 조회 대상 노드(제품/SUB)")):
    """노드의 용접봉별 관경별 용접점수(nx.item_weld) 반환 — 내부원가 패널 조립공정(용접) 편집 프리로드."""
    node = node.strip()
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT weld_item, pipe_diam, ISNULL(weld_qty,0), ISNULL(use_qty,0)
            FROM nx.item_weld WHERE item_code=? ORDER BY weld_item, pipe_diam""", node)
        by = {}
        for r in cur.fetchall():
            wi = str(r[0]).strip()
            by.setdefault(wi, []).append({"pipe_diam": float(r[1]), "weld_qty": float(r[2]), "use_qty": float(r[3])})
        # 용접봉 후보(carrier=proc_weld) — item_weld 없어도 용접봉 코드 제시
        cur.execute("SELECT DISTINCT weld_item FROM nx.proc_weld WHERE parent_item=?", node)
        carriers = [str(r[0]).strip() for r in cur.fetchall() if str(r[0]).strip()]
        return {"node": node, "welds": [{"weld_item": k, "rows": v} for k, v in by.items()], "carriers": carriers}
    finally:
        nx.close()

@router.get("/api/weld/diam")
def weld_diam():
    """관경별 표준소요량·표준공수 마스터(대표=silver_solder MIN='01'). 신규BOM 용접공정 입력·미리보기용."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT pipe_diam,MIN(std_use_qty),MIN(std_st) FROM nx.weld_diam GROUP BY pipe_diam ORDER BY pipe_diam")
        return {"rows": [{"pipe_diam": float(r[0]), "std_use_qty": float(r[1] or 0), "std_st": float(r[2] or 0)} for r in cur.fetchall()]}
    finally:
        nx.close()

@router.post("/api/weld/save")
def weld_save(payload: dict = Body(...)):
    """용접 공정(관경별 횟수) 저장 → nx.item_weld 생성 + proc_weld 파생 + routing(51/28) 생성. 정본산식=_schema/WELD_PROC_TABLES_SPEC.md.
       payload: {node, weld_item, rows:[{pipe_diam, weld_qty}], loss_factor?(1.5), proc_code?('51'=용접/'28'=은납)}.
       소요량=Σ(std_use[관경]×횟수)×loss_factor · 내부ST=Σ(std_st×횟수) · routing work_qty=Σ횟수, uph=Σ횟수×3600/내부ST.
       스코프: (node, weld_item)만 교체(멱등). node 미존재시 안전하게 거절(BOM 먼저 저장). 단가 미변경."""
    node = str(payload.get("node", "")).strip()
    wi = str(payload.get("weld_item", "")).strip()
    rows = payload.get("rows", []) or []
    if not node or not wi:
        raise HTTPException(400, "node·weld_item 필요")
    proc_code = str(payload.get("proc_code", "51")).strip() or "51"
    if proc_code not in _PROC_WELD:
        raise HTTPException(400, "proc_code는 51(용접) 또는 28(은납)")
    lf = payload.get("loss_factor", None)
    lf = float(lf) if (lf is not None and str(lf).strip() != "") else 1.5
    # 관경별 횟수 정리(중복관경 합산)
    from collections import defaultdict as _dd
    cnt = _dd(float)
    for r in rows:
        try:
            d = round(float(r.get("pipe_diam") or 0), 2); q = float(r.get("weld_qty") or 0)
        except Exception:
            continue
        if d > 0 and q > 0:
            cnt[d] += q
    nx = _nx(); cur = nx.cursor()
    try:
        # 표준값 마스터(대표=MIN=silver_solder '01')
        cur.execute("SELECT pipe_diam,MIN(std_use_qty),MIN(std_st) FROM nx.weld_diam GROUP BY pipe_diam")
        STDU = {}; STDS = {}
        for r in cur.fetchall():
            d = round(float(r[0]), 2); STDU[d] = float(r[1] or 0); STDS[d] = float(r[2] or 0)
        bad = [d for d in cnt if d not in STDU]
        if bad:
            raise HTTPException(400, f"weld_diam에 없는 관경: {bad}")
        sum_use = sum(STDU[d] * q for d, q in cnt.items())
        sum_cnt = sum(cnt.values())
        sum_st = sum(STDS[d] * q for d, q in cnt.items())
        use_qty = round(sum_use * lf, 6)
        unit = round(sum_use / sum_cnt, 8) if sum_cnt else 0.0
        diam_rep = max(cnt.items(), key=lambda kv: kv[1])[0] if cnt else 0.0
        uph = round(sum_cnt * 3600.0 / sum_st, 4) if sum_st > 0 else 0.0
        # 1) item_weld 교체(스코프: node+weld_item)
        cur.execute("DELETE FROM nx.item_weld WHERE item_code=? AND weld_item=?", node, wi)
        for d, q in sorted(cnt.items()):
            cur.execute("INSERT INTO nx.item_weld(item_code,weld_item,pipe_diam,weld_qty,use_qty) VALUES(?,?,?,?,?)",
                        node, wi, d, q, round(STDU[d] * q, 6))
        # 2) proc_weld 파생(스코프: node+weld_item)
        cur.execute("DELETE FROM nx.proc_weld WHERE parent_item=? AND weld_item=?", node, wi)
        if sum_cnt > 0:
            cur.execute("""INSERT INTO nx.proc_weld(parent_item,weld_item,weld_base,pipe_diam,weld_st,unit_qty,use_qty,
                  loss_factor,meta_ok,cs_calc_except,lme_except,tag,src,upd_dt)
                VALUES(?,?,?,?,?,?,?,?,1,0,0,'W','weld_save',getdate())""",
                node, wi, wi.split('-')[0], diam_rep, sum_cnt, unit, use_qty, lf)
        # 3) routing 용접공정(51/28) 교체(스코프: node+weld_item, proc_code)
        cur.execute("DELETE FROM nx.routing WHERE p_item=? AND item_code=? AND proc_code=?", node, wi, proc_code)
        if sum_cnt > 0:
            cur.execute("""INSERT INTO nx.routing(p_item,item_code,proc_code,work_qty,prod_uph,calc_gubun,sort_seq)
                VALUES(?,?,?,?,?,'3',0)""", node, wi, proc_code, sum_cnt, uph)
        _reset_cost_engine()
        return {"ok": True, "node": node, "weld_item": wi, "diams": len(cnt), "total_points": sum_cnt,
                "use_qty": use_qty, "unit_qty": unit, "inner_st": sum_st, "uph": uph, "loss_factor": lf}
    finally:
        nx.close()
