# -*- coding: utf-8 -*-
"""견적원가관리(esticost)+납품(delivery) 도메인 라우터 — 견적스냅샷·LG BOM전개·원가/손익산출·승인, 납품팩.
   app.py에서 분리. 공유헬퍼는 common.py."""
import math
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException
from common import (_conn, _num, _run_sp, _shape, _d6, _nx, _nx_tx, _b,
                    _get_cost_engine, _reset_cost_engine, _COST_LOCK, NxCostEngine)

router = APIRouter()

# ===================== 견적원가관리 (견적원가조회→개칭, 개발 최중요) =====================
#  설계정본: _schema/ESTI_COST_MGMT_DESIGN.md (대표 2026-07-28 승인)
#  - 원가산출 = nx 원가엔진(NxCostEngine)만.  저장 = 견적 스냅샷(nx.esti_head/bom/gongsu).
#  - 상단품번으로 LG BOM(nx.lg_bom) 전 레벨 전개 → 치수/소요량 편집 → 저장 → 원가/손익 산출.
#  - 승인 게이트: 작성→승인/반려.  ※승인시 품목마스터/nx.bom 승격 + 조달프로파일 후보등록 = phase2(TODO).
#  쓰기는 PARTNER_ERP_TEST3.nx 만(_nx). 라이브 PARTNER_ERP는 읽기전용(_conn).

def _esti_gen_no(cur):
    """견적번호 자동채번: ES + YYMMDD(오늘) + 3자리 일련(당일)."""
    pre = 'ES' + datetime.now().strftime('%y%m%d')
    cur.execute("SELECT MAX(esti_no) FROM nx.esti_head WHERE esti_no LIKE ?", pre + '%')
    mx = cur.fetchone()[0]
    n = (int(mx[-3:]) + 1) if mx else 1
    return pre + str(n).zfill(3)

@router.get("/api/esticost/expand")
def esticost_expand(item: str = Query(..., description="상위품번(LG BOM model)"),
                    werks: str = Query("", description="DMZ(SAC)/DGZ(RAC), 공란=전체")):
    """LG BOM(nx.lg_bom) 전 레벨 전개 → 편집용 초기 BOM. 치수/중량/단가구분은 nx.item(+라이브 PR_M_ITEM) 보강.
       ※파일 업로드 없이 어제 적재된 nx.lg_bom을 상위품번(model)으로 전개."""
    item = item.strip()
    if not item: raise HTTPException(400, "item(상위품번) 필요")
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["model=?"]; p = [item]
        if werks.strip(): w.append("werks=?"); p.append(werks.strip())
        cur.execute(f"""SELECT stufe, posnr, parent_code, child_code, ISNULL(child_desc,''), ISNULL(child_spec,''),
              CAST(ISNULL(qty,0) AS decimal(18,6)), ISNULL(unit,''), ISNULL(supply_type,''), ISNULL(lowest_flg,''),
              ISNULL(main_mat,''), ISNULL(matkl,'')
            FROM nx.lg_bom WHERE {' AND '.join(w)} ORDER BY stufe, posnr, id""", *p)
        raw = cur.fetchall()
        # parent → children edges
        edges = {}
        for r in raw:
            edges.setdefault(str(r[2]).strip(), []).append({
                "child": str(r[3]).strip(), "desc": r[4], "spec": r[5], "qty": float(r[6] or 0),
                "unit": r[7], "supply": r[8], "lowest": r[9], "main_mat": r[10], "matkl": r[11]})
        # 노드 상세: nx.item 우선, 없으면 라이브 PR_M_ITEM
        codes = {item} | {e["child"] for lst in edges.values() for e in lst} | set(edges.keys())
        codes = {c for c in codes if c}
        info = {}
        cl = list(codes)
        for i in range(0, len(cl), 900):
            chunk = cl[i:i+900]; ph = ",".join("?" * len(chunk))
            cur.execute(f"""SELECT item_code, ISNULL(item_name,''), ISNULL(diam,0), ISNULL(thick,0), ISNULL(length,0),
                  ISNULL(metal_gubun,''), ISNULL(net_weight,0), ISNULL(cost_gubun,''), ISNULL(make_type,''),
                  ISNULL(in_cust,''), ISNULL(unit,'')
                FROM nx.item WHERE item_code IN ({ph})""", *chunk)
            for r in cur.fetchall():
                info[r[0]] = {"nm": r[1], "diam": float(r[2] or 0), "thick": float(r[3] or 0), "length": float(r[4] or 0),
                    "metal": r[5].strip(), "wt": float(r[6] or 0), "cost_gubun": r[7].strip(), "make_type": r[8].strip(),
                    "in_cust": r[9].strip(), "unit": r[10].strip()}
        # 라이브 PR_M_ITEM 보강(nx.item 미보유 코드)
        miss = [c for c in cl if c not in info]
        if miss:
            lc = _conn(); lcur = lc.cursor()
            try:
                for i in range(0, len(miss), 900):
                    chunk = miss[i:i+900]; ph = ",".join("?" * len(chunk))
                    lcur.execute(f"""SELECT ITEM_CODE, ISNULL(item_name,''), ISNULL(diam,0), ISNULL(thick,0),
                          ISNULL(length,0), ISNULL(METAL_GUBUN,''), ISNULL(in_cust,''), ISNULL(MAKE_TYPE,'')
                        FROM PARTNER_ERP_TEST3.nx.item WHERE ITEM_CODE IN ({ph})""", *chunk)
                    for r in lcur.fetchall():
                        info.setdefault(r[0], {"nm": r[1], "diam": float(r[2] or 0), "thick": float(r[3] or 0),
                            "length": float(r[4] or 0), "metal": str(r[5]).strip(), "wt": 0.0, "cost_gubun": "",
                            "make_type": str(r[7]).strip(), "in_cust": str(r[6]).strip(), "unit": ""})
            finally:
                lc.close()
        # nx.bom 보유여부(전개원 존재 참고)
        cur.execute("SELECT 1 FROM nx.bom_header WHERE item_code=?", item)
        has_nxbom = cur.fetchone() is not None
        # 트리 walk
        out = []; seq = [0]; seen = set()
        ti = info.get(item, {})
        out.append({"seq": 0, "level": 0, "parent": "", "item_code": item, "item_name": ti.get("nm", ""),
            "diam": ti.get("diam", 0), "thick": ti.get("thick", 0), "length": ti.get("length", 0),
            "metal_gubun": ti.get("metal", ""), "shape": "", "unit_weight": ti.get("wt", 0),
            "unit_qty": 1, "total_qty": 1, "cost_gubun": ti.get("cost_gubun", ""), "unit": ti.get("unit", ""),
            "in_cust": ti.get("in_cust", ""), "supply": "", "make_type": ti.get("make_type", ""),
            "sagub_flag": 0, "new_flag": 0, "haskids": item in edges})
        def walk(code, lvl, accq):
            if code in seen: return
            seen.add(code)
            for e in edges.get(code, []):
                seq[0] += 1
                ci = info.get(e["child"], {})
                tq = accq * (e["qty"] or 0)
                out.append({"seq": seq[0], "level": lvl, "parent": code, "item_code": e["child"],
                    "item_name": ci.get("nm", "") or e["desc"], "diam": ci.get("diam", 0), "thick": ci.get("thick", 0),
                    "length": ci.get("length", 0), "metal_gubun": ci.get("metal", ""), "shape": "",
                    "unit_weight": ci.get("wt", 0), "unit_qty": e["qty"], "total_qty": tq,
                    "cost_gubun": ci.get("cost_gubun", ""), "unit": ci.get("unit", "") or e["unit"],
                    "in_cust": ci.get("in_cust", ""), "supply": e["supply"], "make_type": ci.get("make_type", ""),
                    "sagub_flag": 1 if e["supply"] in ("Supplier",) else 0, "new_flag": 0,
                    "haskids": e["child"] in edges})
                walk(e["child"], lvl + 1, tq)
            seen.discard(code)
        walk(item, 1, 1.0)
        return {"item": item, "name": ti.get("nm", ""), "rows": out, "count": len(out) - 1,
                "has_nxbom": has_nxbom, "source": "nx.lg_bom"}
    finally:
        cn.close()

@router.get("/api/esticost/list")
def esticost_list(q: str = Query(""), status: str = Query("")):
    """저장견적 목록."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = []; p = []
        if q.strip():
            w.append("(h.esti_no LIKE ? OR h.item_code LIKE ? OR h.item_name LIKE ?)")
            p += [f"%{q.strip()}%"] * 3
        if status.strip(): w.append("h.status=?"); p.append(status.strip())
        sql = """SELECT h.esti_no, h.item_code, ISNULL(h.item_name,''), h.base_ymd, h.cost_gubun, h.status,
              ISNULL(h.silwon_amt,0), ISNULL(h.lg_cost,0), ISNULL(h.sonik_amt,0), ISNULL(h.created_by,''),
              CONVERT(varchar(19), h.created_at, 120), (SELECT COUNT(*) FROM nx.esti_bom b WHERE b.esti_no=h.esti_no)
            FROM nx.esti_head h"""
        if w: sql += " WHERE " + " AND ".join(w)
        sql += " ORDER BY h.created_at DESC, h.esti_no DESC"
        cur.execute(sql, *p)
        rows = [{"esti_no": r[0], "item_code": r[1], "item_name": r[2], "base_ymd": r[3], "cost_gubun": r[4],
                 "status": r[5], "silwon": float(r[6] or 0), "lg_cost": float(r[7] or 0), "sonik": float(r[8] or 0),
                 "created_by": r[9], "created_at": r[10], "bom_cnt": r[11]} for r in cur.fetchall()]
        return {"rows": rows}
    finally:
        cn.close()

@router.get("/api/esticost/load")
def esticost_load(esti_no: str = Query(...)):
    """저장견적 상세(head+bom+gongsu)."""
    esti_no = esti_no.strip()
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT esti_no,item_code,ISNULL(item_name,''),base_ymd,cost_gubun,status,ISNULL(model,''),
              ISNULL(jae_amt,0),ISNULL(gagong_amt,0),ISNULL(lme_amt,0),ISNULL(ilban_amt,0),ISNULL(unban_amt,0),
              ISNULL(profit_amt,0),ISNULL(silwon_amt,0),ISNULL(lg_cost,0),ISNULL(sonik_amt,0),ISNULL(remarks,''),
              ISNULL(created_by,''),CONVERT(varchar(19),created_at,120),ISNULL(approved_by,''),
              CONVERT(varchar(19),approved_at,120) FROM nx.esti_head WHERE esti_no=?""", esti_no)
        r = cur.fetchone()
        if not r: raise HTTPException(404, "견적 없음")
        head = {"esti_no": r[0], "item_code": r[1], "item_name": r[2], "base_ymd": r[3], "cost_gubun": r[4],
                "status": r[5], "model": r[6], "jae_amt": float(r[7]), "gagong_amt": float(r[8]),
                "lme_amt": float(r[9]), "ilban_amt": float(r[10]), "unban_amt": float(r[11]),
                "profit_amt": float(r[12]), "silwon_amt": float(r[13]), "lg_cost": float(r[14]),
                "sonik_amt": float(r[15]), "remarks": r[16], "created_by": r[17], "created_at": r[18],
                "approved_by": r[19], "approved_at": r[20]}
        cur.execute("""SELECT seq,level,ISNULL(parent,''),item_code,ISNULL(item_name,''),ISNULL(diam,0),ISNULL(thick,0),
              ISNULL(length,0),ISNULL(metal_gubun,''),ISNULL(shape,''),ISNULL(unit_weight,0),ISNULL(unit_qty,0),
              ISNULL(total_qty,0),ISNULL(cost_gubun,''),ISNULL(raw_cost,0),ISNULL(mat_cost,0),ISNULL(in_cust,''),
              ISNULL(proc_in,''),sagub_flag,new_flag,ISNULL(make_type,'') FROM nx.esti_bom WHERE esti_no=? ORDER BY seq""", esti_no)
        bom = [{"seq": x[0], "level": x[1], "parent": x[2], "item_code": x[3], "item_name": x[4], "diam": float(x[5]),
                "thick": float(x[6]), "length": float(x[7]), "metal_gubun": x[8], "shape": x[9],
                "unit_weight": float(x[10]), "unit_qty": float(x[11]), "total_qty": float(x[12]), "cost_gubun": x[13],
                "raw_cost": float(x[14]), "mat_cost": float(x[15]), "in_cust": x[16], "proc_in": x[17],
                "sagub_flag": int(x[18]), "new_flag": int(x[19]), "make_type": x[20]} for x in cur.fetchall()]
        cur.execute("""SELECT seq,item_code,proc_code,ISNULL(proc_name,''),ISNULL(work_qty,0),ISNULL(uph,0),
              ISNULL(rate,0),ISNULL(calc_gubun,''),ISNULL(amt,0) FROM nx.esti_gongsu WHERE esti_no=? ORDER BY seq""", esti_no)
        gongsu = [{"seq": x[0], "item_code": x[1], "proc_code": x[2], "proc_name": x[3], "work_qty": float(x[4]),
                   "uph": float(x[5]), "rate": float(x[6]), "calc_gubun": x[7], "amt": float(x[8])} for x in cur.fetchall()]
        return {"head": head, "bom": bom, "gongsu": gongsu}
    finally:
        cn.close()

def _esti_cost_calc(item, ymd):
    """NxCostEngine 원가/손익 산출(best-effort). 엔진은 nx.bom 기준 → 미등록 품번은 0."""
    if NxCostEngine is None: return None
    eng = NxCostEngine()
    try:
        r = eng.silwon(item, ymd)
        try: r['lme'] = eng.lme_total(item, ymd)
        except Exception: r['lme'] = 0.0
        return r
    except Exception:
        return None
    finally:
        eng.close()

@router.post("/api/esticost/save")
def esticost_save(payload: dict = Body(...)):
    """견적 스냅샷 저장(head+bom+gongsu). esti_no 미지정=신규채번, 지정=전체교체.
       저장시 NxCostEngine으로 원가/손익 캐시(nx.bom 기준, best-effort)."""
    p = payload
    esti_no = str(p.get("esti_no", "") or "").strip()
    item = str(p.get("item_code", "") or "").strip()
    if not item: raise HTTPException(400, "item_code(대상품번) 필요")
    ymd = str(p.get("base_ymd", "") or "260630").strip()
    cost_gubun = str(p.get("cost_gubun", "") or "실원가").strip()
    by = (str(p.get("by", "") or "웹사용자").strip())[:50]
    bom = p.get("bom") or []
    gongsu = p.get("gongsu") or []
    item_name = str(p.get("item_name", "") or "").strip()
    model = str(p.get("model", "") or "").strip()
    remarks = str(p.get("remarks", "") or "").strip()

    def d(v):
        try: return float(v) if v not in (None, "") else None
        except Exception: return None
    def iseq(v, fallback):   # seq=0(최상위)도 유효 → None만 fallback
        try: return int(v) if v is not None and v != "" else fallback
        except Exception: return fallback

    cost = _esti_cost_calc(item, ymd)
    cn = _nx(); cn.autocommit = False; cur = cn.cursor()
    try:
        is_new = not esti_no
        if is_new:
            esti_no = _esti_gen_no(cur)
            cur.execute("""INSERT INTO nx.esti_head(esti_no,item_code,item_name,base_ymd,cost_gubun,status,model,
                  remarks,created_by,created_at) VALUES(?,?,?,?,?,N'작성',?,?,?,GETDATE())""",
                esti_no, item, item_name, ymd, cost_gubun, model, remarks, by)
        else:
            cur.execute("SELECT status FROM nx.esti_head WHERE esti_no=?", esti_no)
            row = cur.fetchone()
            if not row: raise HTTPException(404, "견적 없음")
            # 승인건 재저장 → 재승인 필요(설계: 변경시 재승인). status='작성'으로 회귀.
            st_prev = row[0]
            newst = '작성' if st_prev == '승인' else st_prev
            cur.execute("""UPDATE nx.esti_head SET item_code=?,item_name=?,base_ymd=?,cost_gubun=?,model=?,remarks=?,
                  status=?,updated_at=GETDATE() WHERE esti_no=?""",
                item, item_name, ymd, cost_gubun, model, remarks, newst, esti_no)
        # 원가 캐시
        if cost:
            cur.execute("""UPDATE nx.esti_head SET jae_amt=?,gagong_amt=?,lme_amt=?,ilban_amt=?,unban_amt=?,
                  profit_amt=?,silwon_amt=?,lg_cost=?,sonik_amt=? WHERE esti_no=?""",
                cost.get('jae'), cost.get('gagong'), cost.get('lme'), cost.get('ilban'), cost.get('unban'),
                cost.get('profit'), cost.get('silwon'), cost.get('lg'), cost.get('sonik'), esti_no)
        # BOM 전체교체
        cur.execute("DELETE FROM nx.esti_bom WHERE esti_no=?", esti_no)
        for i, b in enumerate(bom, 1):
            cur.execute("""INSERT INTO nx.esti_bom(esti_no,seq,level,parent,item_code,item_name,diam,thick,length,
                  metal_gubun,shape,unit_weight,unit_qty,total_qty,cost_gubun,raw_cost,mat_cost,in_cust,proc_in,
                  sagub_flag,new_flag,make_type) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                esti_no, iseq(b.get("seq"), i), int(b.get("level") or 0), str(b.get("parent", "") or ""),
                str(b.get("item_code", "") or ""), str(b.get("item_name", "") or ""), d(b.get("diam")),
                d(b.get("thick")), d(b.get("length")), str(b.get("metal_gubun", "") or ""),
                str(b.get("shape", "") or ""), d(b.get("unit_weight")), d(b.get("unit_qty")), d(b.get("total_qty")),
                str(b.get("cost_gubun", "") or ""), d(b.get("raw_cost")), d(b.get("mat_cost")),
                str(b.get("in_cust", "") or ""), str(b.get("proc_in", "") or ""),
                _b(b.get("sagub_flag")), _b(b.get("new_flag")), str(b.get("make_type", "") or ""))
        # 공수 전체교체
        cur.execute("DELETE FROM nx.esti_gongsu WHERE esti_no=?", esti_no)
        for i, g in enumerate(gongsu, 1):
            cur.execute("""INSERT INTO nx.esti_gongsu(esti_no,seq,item_code,proc_code,proc_name,work_qty,uph,rate,
                  calc_gubun,amt) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                esti_no, iseq(g.get("seq"), i), str(g.get("item_code", "") or item),
                str(g.get("proc_code", "") or ""), str(g.get("proc_name", "") or ""), d(g.get("work_qty")),
                d(g.get("uph")), d(g.get("rate")), str(g.get("calc_gubun", "") or ""), d(g.get("amt")))
        cn.commit()
        return {"ok": True, "esti_no": esti_no, "is_new": is_new, "cost": cost}
    except HTTPException:
        cn.rollback(); raise
    except Exception as e:
        cn.rollback(); raise HTTPException(500, f"저장 오류: {e}")
    finally:
        cn.close()

@router.post("/api/esticost/cost")
def esticost_cost(payload: dict = Body(default=None), esti_no: str = Query(""), item: str = Query(""),
                  ymd: str = Query("260630")):
    """NxCostEngine 원가/손익 산출. esti_no 지정시 헤더의 품번·기준일 사용, 아니면 item·ymd 직접."""
    p = payload or {}
    esti_no = (esti_no or str(p.get("esti_no", "") or "")).strip()
    item = (item or str(p.get("item", "") or "")).strip()
    ymd = (str(p.get("ymd", "") or "") or ymd).strip()
    if esti_no:
        cn = _nx(); cur = cn.cursor()
        try:
            cur.execute("SELECT item_code, base_ymd FROM nx.esti_head WHERE esti_no=?", esti_no)
            r = cur.fetchone()
            if not r: raise HTTPException(404, "견적 없음")
            item, ymd = r[0], (r[1] or ymd)
        finally:
            cn.close()
    if not item: raise HTTPException(400, "esti_no 또는 item 필요")
    cost = _esti_cost_calc(item, ymd)
    if cost is None: raise HTTPException(500, "nx엔진 산출 실패(품번 nx.bom 미등록 가능)")
    return {"item": item, "ymd": ymd, "esti_no": esti_no, "cost": cost}

@router.post("/api/esticost/newitem")
def esticost_newitem(payload: dict = Body(...)):
    """신규품목/외주SUB 자동채번 생성(nx.item 등록). 접두어+일련(6자리).
       ※견적=시뮬레이션. 여기 생성 품목은 nx.item에만 등록, nx.bom 승격은 확정(승인) 시 phase2."""
    p = payload
    name = str(p.get("item_name", "") or "").strip()
    if not name: raise HTTPException(400, "item_name(품명) 필요")
    prefix = (str(p.get("prefix", "") or "").strip().upper() or "NXS")
    item_type = str(p.get("item_type", "") or "S_ASSY").strip()
    unit = str(p.get("unit", "") or "EA").strip()
    base_item = str(p.get("base_item", "") or "").strip()   # 치수 복사 원본(선택)

    def d(v):
        try: return float(v) if v not in (None, "") else None
        except Exception: return None
    diam, thick, length = d(p.get("diam")), d(p.get("thick")), d(p.get("length"))
    metal = str(p.get("metal_gubun", "") or "").strip() or None
    make_type = str(p.get("make_type", "") or "1").strip()   # 기본 자체제작(외주SUB)
    in_cust = str(p.get("in_cust", "") or "").strip() or None
    cost_gubun = str(p.get("cost_gubun", "") or "").strip() or None

    cn = _nx(); cn.autocommit = False; cur = cn.cursor()
    try:
        # 치수 복사(base_item)
        if base_item and (diam is None and thick is None and length is None):
            cur.execute("SELECT ISNULL(diam,0),ISNULL(thick,0),ISNULL(length,0),ISNULL(metal_gubun,'') FROM nx.item WHERE item_code=?", base_item)
            br = cur.fetchone()
            if br:
                diam, thick, length = float(br[0]), float(br[1]), float(br[2])
                metal = metal or (br[3].strip() or None)
        # 채번: prefix + 숫자접미 최대+1 (6자리)
        cur.execute("SELECT item_code FROM nx.item WHERE item_code LIKE ? AND item_code NOT LIKE ?",
                    prefix + '%', prefix + '%[^0-9]%')
        mx = 0; width = 6
        plen = len(prefix)
        for (code,) in cur.fetchall():
            suf = code[plen:]
            if suf.isdigit():
                mx = max(mx, int(suf)); width = max(width, len(suf))
        new_code = prefix + str(mx + 1).zfill(width)
        # 중복 안전 확인
        cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", new_code)
        if cur.fetchone(): raise HTTPException(500, f"채번 충돌 {new_code}")
        cur.execute("""INSERT INTO nx.item(item_code,item_name,item_type,unit,status,silver_flag,has_gagong,
              diam,thick,length,metal_gubun,make_type,in_cust,cost_gubun)
            VALUES(?,?,?,?,N'신규',0,0,?,?,?,?,?,?,?)""",
            new_code, name, item_type, unit, diam, thick, length, metal, make_type, in_cust, cost_gubun)
        cn.commit()
        return {"ok": True, "item_code": new_code, "item_name": name, "item_type": item_type, "unit": unit,
                "diam": diam or 0, "thick": thick or 0, "length": length or 0, "metal_gubun": metal or "",
                "make_type": make_type, "in_cust": in_cust or "", "cost_gubun": cost_gubun or ""}
    except HTTPException:
        cn.rollback(); raise
    except Exception as e:
        cn.rollback(); raise HTTPException(500, f"신규품목 생성 오류: {e}")
    finally:
        cn.close()

@router.post("/api/esticost/approve")
def esticost_approve(payload: dict = Body(...)):
    """승인/반려. status='승인'|'반려'. by=결재자.
       ※phase2(TODO): 승인시 ①신규 SUB를 품목마스터/nx.bom 승격 ②조달프로파일 후보 등록(WHERE status='승인')."""
    p = payload
    esti_no = str(p.get("esti_no", "") or "").strip()
    if not esti_no: raise HTTPException(400, "esti_no 필요")
    action = str(p.get("action", "") or "approve").strip()
    by = (str(p.get("by", "") or "웹사용자").strip())[:50]
    status = '반려' if action in ('reject', '반려') else '승인'
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT 1 FROM nx.esti_head WHERE esti_no=?", esti_no)
        if not cur.fetchone(): raise HTTPException(404, "견적 없음")
        cur.execute("UPDATE nx.esti_head SET status=?,approved_by=?,approved_at=GETDATE() WHERE esti_no=?",
                    status, by, esti_no)
        # TODO(phase2): if status=='승인': 품목마스터/nx.bom 승격 + nx.sourcing 후보등록
        return {"ok": True, "esti_no": esti_no, "status": status}
    finally:
        cn.close()

@router.post("/api/esticost/delete")
def esticost_delete(payload: dict = Body(...)):
    """견적 삭제(head+bom+gongsu)."""
    esti_no = str((payload or {}).get("esti_no", "") or "").strip()
    if not esti_no: raise HTTPException(400, "esti_no 필요")
    cn = _nx(); cn.autocommit = False; cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.esti_gongsu WHERE esti_no=?", esti_no)
        cur.execute("DELETE FROM nx.esti_bom WHERE esti_no=?", esti_no)
        cur.execute("DELETE FROM nx.esti_head WHERE esti_no=?", esti_no)
        n = cur.rowcount
        cn.commit()
        return {"ok": True, "esti_no": esti_no, "deleted": n}
    except Exception as e:
        cn.rollback(); raise HTTPException(500, f"삭제 오류: {e}")
    finally:
        cn.close()


# ===================== 납품 포장/적재 (nx.delivery_pack, 쓰기=TEST3) =====================
@router.get("/api/delivery/list")
def delivery_list(item: str = Query(..., description="완제품 품번")):
    item = item.strip()
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT id,seq,ISNULL(pack_item,''),ISNULL(pack_name,''),ISNULL(pack_level,''),
            use_basis,qty_per,units_per,ceiling_flag,is_bom,ISNULL(remarks,'') FROM nx.delivery_pack
            WHERE item_code=? ORDER BY seq,id""", item)
        rows = [{"id": r[0], "seq": r[1], "pack_item": r[2], "pack_name": r[3], "pack_level": r[4],
                 "use_basis": r[5], "qty_per": float(r[6] or 0), "units_per": r[7],
                 "ceiling": bool(r[8]), "is_bom": bool(r[9]), "remarks": r[10]} for r in cur.fetchall()]
        return {"item": item, "rows": rows}
    finally:
        cn.close()

@router.post("/api/delivery/save")
def delivery_save(p: dict = Body(...)):
    item = str(p.get("item_code") or "").strip()
    if not item: raise HTTPException(400, "item_code 필요")
    cn = _nx(); cur = cn.cursor()
    try:
        vals = (item, int(p.get("seq") or 1), (p.get("pack_item") or None), (p.get("pack_name") or None),
                (p.get("pack_level") or None), str(p.get("use_basis") or "개당"), float(p.get("qty_per") or 1),
                (int(p["units_per"]) if p.get("units_per") not in (None, "", 0) else None),
                _b(p.get("ceiling")), _b(p.get("is_bom")), (p.get("remarks") or None), (p.get("upd_user") or "web"))
        pid = p.get("id")
        if pid:
            cur.execute("""UPDATE nx.delivery_pack SET seq=?,pack_item=?,pack_name=?,pack_level=?,use_basis=?,
                qty_per=?,units_per=?,ceiling_flag=?,is_bom=?,remarks=?,upd_user=?,upd_dt=GETDATE()
                WHERE id=?""", (*vals[1:], int(pid)))
        else:
            cur.execute("""INSERT INTO nx.delivery_pack
                (item_code,seq,pack_item,pack_name,pack_level,use_basis,qty_per,units_per,ceiling_flag,is_bom,remarks,upd_user)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", vals)
        cn.commit()
        return {"ok": True}
    except Exception as e:
        cn.rollback(); raise HTTPException(500, f"저장오류: {e}")
    finally:
        cn.close()

@router.post("/api/delivery/delete")
def delivery_delete(p: dict = Body(...)):
    pid = p.get("id")
    if not pid: raise HTTPException(400, "id 필요")
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.delivery_pack WHERE id=?", int(pid)); cn.commit()
        return {"ok": True}
    finally:
        cn.close()

@router.get("/api/delivery/calc")
def delivery_calc(item: str = Query(...), order_qty: float = Query(..., description="발주수량")):
    """발주수량 → 포장자재 소요 산출(use_basis·CEILING)."""
    import math
    item = item.strip()
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT ISNULL(pack_name,pack_item),use_basis,qty_per,units_per,ceiling_flag
            FROM nx.delivery_pack WHERE item_code=? ORDER BY seq,id""", item)
        out = []
        for nm, basis, qper, uper, ceil in cur.fetchall():
            qper = float(qper or 0); uper = int(uper or 0)
            if basis == '개당':
                need = qper * order_qty
            elif basis == '발주당':
                need = qper
            elif uper > 0:  # 박스당/파렛트당: 발주수량/적재수량, ceiling면 올림
                units = order_qty / uper
                units = math.ceil(units) if ceil else units
                need = qper * units
            else:
                need = 0
            out.append({"pack": nm, "basis": basis, "units_per": uper, "need": round(need, 4)})
        return {"item": item, "order_qty": order_qty, "packs": out}
    finally:
        cn.close()
