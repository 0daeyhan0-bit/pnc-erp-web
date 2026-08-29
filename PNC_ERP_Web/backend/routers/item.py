# -*- coding: utf-8 -*-
"""item 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

import re as _re
from common import _ITEM_MAKE, _geom_weight
router = APIRouter()

# ===================== 품목마스터 CRUD (Phase②) — nx.item + item_sub/valve/his =====================
# 근거: _schema/ITEM_MASTER_ANALYSIS.md, nx_item_master_ext.sql, sync_item_master.py
# 코어(nx.item 기존19)=BOM/원가 FK, 업무20컬럼 ADD. 서브=검사/사급/RACK 등. BOM무결성 게이트 내장.
_INSP = {"F": "전수검사", "S": "샘플검사", "N": "무검사"}   # INSP_FLAG (라벨 잠정 — 전산확인)
_ITEM_TYPE = ["원소재", "원자재", "부자재", "서브ASSY", "제품", "완제품"]
# nx.item 관리 컬럼. ★품목마스터는 "품목의 본질"만 관리 — 조달성(매입처/작업장/조달구분)·원가(단가구분)·죽은필드는
# 여기서 제외 → 저장 시 미터치(기존값 보존, 타 프로그램 무영향). 조달은 조달프로파일/BOM, 원가는 원가엔진 소관.
# ★3층 원칙: 품목마스터는 "고정 속성"(이게 뭔가)만. 운영·조달·거래·완제품소속은 전부 분리(저장 미터치, DB 데이터·컬럼 보존).
_IM_BIZ = ["item_status", "pipe_kind", "item_pipe_id"]
_IM_CORE = ["item_name", "item_spec", "item_type", "sgroup", "metal_gubun", "diam", "thick",
            "length", "net_weight", "unit", "status"]
# 분리(저장 미터치, 데이터 보존):
#   조달→sourcing_profile: in_cust, work_code, obtain_gubun, make_type, lg_obtain_flag, pur_lead_time, min_pur_qty
#   원가→원가엔진: cost_gubun / 완제품소속→BOM / 거래→주문: sale_cust, dlvy_except_flag
#   운영정책: safe_stock_qty, kitting_min, set_except_day, sub_mat_flag, sub_mat_wh, prod_rate, proc_gubun, prod_tag,
#            pack_kind, pack_qty, prod_worker, insp_worker / 죽은필드: item_group,item_class,pur_gubun,item_radius,item_pipe_type,item_pipe_material,lgroup,use_gubun
_IM_NUM = {"diam", "thick", "length", "net_weight", "item_pipe_id"}       # decimal
_IM_INT = set()                                                            # smallint (분리로 없음)
_SUB_STR = ["insp_flag", "rack_no", "remarks", "prod_step_memo"]
_SUB_INT = ["pack_qty", "pur_lead_time", "min_pur_qty", "safe_stock_qty"]
_VALVE_F = ["item_od", "item_id", "valve_type", "s_w_type", "h_s_type", "n_s_type", "add_item_type",
            "size1", "size1_limit", "size2", "size2_limit", "size3", "size3_limit", "size4", "size4_limit",
            "size5", "size5_limit", "size6", "size6_limit", "size7", "size7_limit", "size8", "size8_limit"]

# ── 품목 성격(nature) 6그룹 — 소분류 + 공정/BOM 신호로 파생 판정 (실측 24,093건 재분류) ──
_NATURE_MAT = {"210": "1.원소재", "220": "1.원소재",
               "230": "2.부자재/소모품", "240": "2.부자재/소모품", "910": "2.부자재/소모품", "991": "2.부자재/소모품",
               "992": "2.부자재/소모품", "993": "2.부자재/소모품", "310": "3.사급자재"}  # 240=용접봉(2026-08-27 신설, 재고평가 대상)
_NATURE_ALL = ["1.원소재", "2.부자재/소모품", "3.사급자재", "4.가공품", "5.용접·조립품", "6.구매·부품"]
# 제품군(대분류) 표시 순서 — 규모/공정흐름 순 (사용자 지정)
_PROD_GROUP_ORDER = ["튜브(절삭단품)", "완제품ASSY", "원소재", "설치자재", "부자재", "서포터", "사급부품", "소모품", "기타"]
# ★파생방식: 코드(접두어+소분류)가 진실, 제품군/제품계열은 조회시 파생(저장 안 함).
_SG_PRODGROUP = {"110": ("완제품ASSY", "완제품ASSY"), "120": ("완제품ASSY", "SUB ASSY"), "130": ("튜브(절삭단품)", "가공품"),
                 "210": ("원소재", "원소재"), "220": ("원소재", "원자재"), "230": ("부자재", "부자재"), "240": ("부자재", "용접봉"), "310": ("사급부품", "사급"),
                 "910": ("소모품", "소모품"), "991": ("소모품", "생산소모"), "992": ("소모품", "일반소모"), "993": ("소모품", "수불예외")}

def _load_prefix_map(cur):
    try:
        cur.execute("SELECT prefix, prod_group, prod_line FROM nx.item_prefix_map")
        return {str(r[0]).strip().upper(): (r[1], r[2]) for r in cur.fetchall()}
    except Exception:
        return {}

def _derive_class(code, sgroup, pmap):
    """제품군/제품계열 파생: ①문자접두어→사전 ②치수코드(*)→원소재 ③숫자/기타→소분류매핑 ④else 기타."""
    c = str(code or "").strip()
    m = _re.match(r"^([A-Za-z]+)", c)
    p = m.group(1).upper() if m else ""
    if p in pmap: return (str(pmap[p][0] or ""), str(pmap[p][1] or ""))
    if "*" in c: return ("원소재", "소재컷팅(규격)")
    sg = str(sgroup or "").strip()
    if sg in _SG_PRODGROUP: return _SG_PRODGROUP[sg]
    return ("기타", "기타")
# 그룹별 소프트권장(저장은 되나 경고). 하드필수는 전 그룹 공통: 품번·품명·소분류·단위.
_NATURE_SOFT = {"1.원소재": ["metal_gubun", "diam", "thick", "length", "net_weight"],
                "2.부자재/소모품": ["make_type"], "3.사급자재": ["cost_gubun"],
                "4.가공품": ["lgroup", "make_type", "work_code", "diam", "thick", "length"],
                "5.용접·조립품": ["lgroup", "make_type"], "6.구매·부품": []}
_FIELD_LABEL = {"metal_gubun": "재질", "diam": "외경", "thick": "두께", "length": "길이",
                "net_weight": "중량", "make_type": "생산구분", "cost_gubun": "단가구분",
                "lgroup": "대분류", "work_code": "작업장"}

def _item_nature(cur, code, sgroup):
    """성격 6그룹 + active(정리대상) 판정. 소분류 우선 → 용접/조립(BOM부모) → 가공 → 구매·부품."""
    sg = str(sgroup or "").strip()
    if sg in _NATURE_MAT:
        return _NATURE_MAT[sg], 1
    # ★용접 존재판정=nx 용접테이블(nx.proc_weld) 런타임 기준 — 레거시 CS_T_ITEM_WELD 런타임 참조 제거(원칙: 런타임은 nx만)
    cur.execute("""SELECT
        (SELECT TOP 1 1 FROM PARTNER_ERP_TEST3.nx.proc_weld WHERE parent_item=? AND ISNULL(use_qty,0)>0),
        (SELECT TOP 1 1 FROM PARTNER_ERP_TEST3.nx.v_cs_bom WHERE ITEM_CODE=?),
        (SELECT TOP 1 1 FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_PROC_GAGONG WHERE ITEM_CODE=?),
        (SELECT TOP 1 1 FROM PARTNER_ERP_TEST3.nx.v_cs_bom WHERE MAT_CODE=?)""", code, code, code, code)
    w, bp, g, bc = cur.fetchone()
    if w or bp: return "5.용접·조립품", 1
    if g: return "4.가공품", 1
    return "6.구매·부품", (1 if bc else 0)   # BOM자식=실부품(1), 완전고아=정리대상(0)

@router.get("/api/itemmaster/opts")
def itemmaster_opts():
    """품목마스터 드롭다운(코드→이름). 코드마스터 + 하드코드 도메인."""
    cn = _conn(); cur = cn.cursor()
    try:
        def lst(kind): return [{"code": k, "nm": v} for k, v in sorted(_kindmap(cur, kind).items()) if k]
        return {
            "lgroup": lst("PR005"), "sgroup": lst("PR006"), "item_group": lst("PR001"),
            "item_class": lst("PR008"), "pipe_kind": lst("PR021"), "unit": lst("CM002"), "metal": lst("PR019"),
            "make_type": [{"code": k, "nm": v} for k, v in _ITEM_MAKE.items() if k],
            "work_code": [{"code": k, "nm": v} for k, v in _ITEM_WORK.items() if k],
            "cost_gubun": [{"code": "1", "nm": "내부단가"}, {"code": "2", "nm": "구매단가"}, {"code": "3", "nm": "소재단가"}, {"code": "5", "nm": "기타"}],
            "insp_flag": [{"code": k, "nm": v} for k, v in _INSP.items()],
            "item_type": [{"code": t, "nm": t} for t in _ITEM_TYPE],
            "status": [{"code": "사용", "nm": "사용"}, {"code": "중지", "nm": "중지"}],
            "yn": [{"code": "1", "nm": "예"}, {"code": "0", "nm": "아니오"}],
            "nature": [{"code": n, "nm": n} for n in _NATURE_ALL],
            "nature_soft": _NATURE_SOFT, "field_label": _FIELD_LABEL,
        }
    finally:
        cn.close()

@router.get("/api/itemmaster/list")
def itemmaster_list(q: str = Query(""), lgroup: str = Query(""), sgroup: str = Query(""),
                    status: str = Query(""), nature: str = Query(""), prod_group: str = Query(""),
                    use: str = Query("", description="사용여부 필터: ''=전체, '1'=사용중, '0'=사용중지"), limit: int = Query(500)):
    """품목마스터 목록(nx.item + item_sub). 코드→이름 디코드. nature=성격6그룹, prod_group=제품군(접두어) 필터.
       use=사용여부(nx.item.use_flag): LG리시빙 스코프 실사용=1·나머지=0. ISNULL시 사용중(1) 취급."""
    nx = _nx(); cur = nx.cursor()
    cn2 = _conn(); c2 = cn2.cursor()
    try:
        dLG = _kindmap(c2, "PR005"); dSG = _kindmap(c2, "PR006"); dGRP = _kindmap(c2, "PR001")
        dCLS = _kindmap(c2, "PR008"); dPK = _kindmap(c2, "PR021"); dUN = _kindmap(c2, "CM002"); dMT = _kindmap(c2, "PR019")
        c2.execute("SELECT CUST_CODE, ISNULL(CUST_DESC,'') FROM PARTNER_ERP_TEST3.nx.CM_M_CUST")
        dCust = {str(r[0]).strip(): r[1] for r in c2.fetchall()}
        w = ["1=1"]; p = []
        if q.strip(): w.append("(i.item_code LIKE ? OR i.item_name LIKE ?)"); p += [f"%{q.strip()}%"] * 2
        if lgroup.strip(): w.append("i.lgroup=?"); p.append(lgroup.strip())
        if sgroup.strip(): w.append("i.sgroup=?"); p.append(sgroup.strip())
        if status.strip(): w.append("i.status=?"); p.append(status.strip())
        if nature.strip(): w.append("i.nature=?"); p.append(nature.strip())
        if prod_group.strip(): w.append("i.prod_group=?"); p.append(prod_group.strip())
        if use.strip() == "1": w.append("ISNULL(i.use_flag,1)=1")      # 사용중
        elif use.strip() == "0": w.append("ISNULL(i.use_flag,1)=0")    # 사용중지
        cur.execute(f"""SELECT TOP {max(1,min(int(limit),3000))} i.item_code,i.item_name,i.item_spec,i.item_type,
              i.lgroup,i.sgroup,i.item_group,i.item_class,i.pipe_kind,i.unit,i.metal_gubun,i.in_cust,i.work_code,
              i.make_type,i.cost_gubun,i.item_status,i.status,i.diam,i.thick,i.length,i.net_weight,i.item_pipe_id,
              i.prod_rate,i.sub_mat_flag, s.insp_flag, s.rack_no, i.nature, i.active, i.prod_group, i.prod_line, i.use_flag
            FROM nx.item i LEFT JOIN nx.item_sub s ON s.item_code=i.item_code
            WHERE {' AND '.join(w)} ORDER BY i.item_code""", *p)
        rows = []
        for r in cur.fetchall():
            g = lambda i: str(r[i] or "").strip()
            num = lambda i: (float(r[i]) if r[i] is not None else None)
            rows.append({
                "item_code": g(0), "item_name": g(1), "item_spec": g(2), "item_type": g(3),
                "lgroup": dLG.get(g(4), g(4)), "sgroup": dSG.get(g(5), g(5)), "item_group": dGRP.get(g(6), g(6)),
                "item_class": dCLS.get(g(7), g(7)), "pipe_kind": dPK.get(g(8), g(8)), "unit": dUN.get(g(9), g(9)),
                "metal": dMT.get(g(10), g(10)), "in_cust": dCust.get(g(11), g(11)), "work": _ITEM_WORK.get(g(12), g(12)),
                "make_type": _ITEM_MAKE.get(g(13), g(13)), "cost_gubun": g(14), "item_status": g(15),
                "status": g(16) or "사용", "diam": num(17), "thick": num(18), "length": num(19),
                "net_weight": num(20), "pipe_id": num(21), "prod_rate": num(22), "sub_mat_flag": g(23),
                "insp_flag": _INSP.get(g(24), g(24)), "rack_no": g(25),
                "nature": g(26), "active": (1 if (r[27] is None or r[27]) else 0),
                "prod_group": g(28), "prod_line": g(29),
                "use_flag": (1 if (r[30] is None or r[30]) else 0)})
        cur.execute("SELECT DISTINCT prod_group FROM nx.item WHERE prod_group IS NOT NULL")
        pgs = [str(r[0]).strip() for r in cur.fetchall() if r[0]]
        pgs = sorted(pgs, key=lambda g: _PROD_GROUP_ORDER.index(g) if g in _PROD_GROUP_ORDER else 99)
        return {"rows": rows, "cnt": len(rows),
                "lgroups": [{"code": k, "nm": v} for k, v in sorted(dLG.items()) if k],
                "sgroups": [{"code": k, "nm": v} for k, v in sorted(dSG.items()) if k],
                "natures": [{"code": n, "nm": n} for n in _NATURE_ALL],
                "prod_groups": [{"code": g, "nm": g} for g in pgs]}
    finally:
        nx.close(); cn2.close()

@router.post("/api/itemmaster/use_flag")
def itemmaster_use_flag(payload: dict = Body(...)):
    """품목 사용/사용중지 토글(nx.item.use_flag=1 사용/0 사용중지). payload {items:[code..] 또는 item, use:0|1}.
       LG리시빙 스코프 초기시드 후 사용자 수동 토글이 정본. 원가/분석·조회는 이 플래그로 필터."""
    items = payload.get("items")
    if items is None and payload.get("item"): items = [payload["item"]]
    items = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not items: raise HTTPException(400, "item(또는 items) 필요")
    use = 1 if payload.get("use") else 0
    nx = _nx_tx(); cur = nx.cursor()
    try:
        cur.execute("IF COL_LENGTH('nx.item','use_flag') IS NULL ALTER TABLE nx.item ADD use_flag BIT NULL")
        n = 0
        for i in range(0, len(items), 900):
            ch = items[i:i + 900]; ph = ",".join("?" * len(ch))
            cur.execute(f"UPDATE nx.item SET use_flag=? WHERE LTRIM(RTRIM(item_code)) IN ({ph})", use, *ch)
            n += cur.rowcount
        nx.commit()
        return {"ok": True, "updated": n, "use": use}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()

@router.get("/api/itemmaster/get")
def itemmaster_get(item: str = Query(...)):
    """단일 품목 전체(편집 모달용): nx.item 코어+업무 + item_sub + item_valve(설치품)."""
    code = item.strip()
    nx = _nx(); cur = nx.cursor()
    try:
        allc = ["item_code"] + _IM_CORE + [c for c in _IM_BIZ]
        cur.execute(f"SELECT {','.join(allc)},silver_flag,has_gagong,nature,active,prod_group,prod_line,ISNULL(cut_gubun,'') cut_gubun FROM nx.item WHERE item_code=?", code)
        r = cur.fetchone()
        if not r: raise HTTPException(404, "품목 없음")
        cols = [d[0] for d in cur.description]
        item_d = {}
        for k, v in zip(cols, r):
            if isinstance(v, __import__("decimal").Decimal): v = float(v)
            item_d[k] = ("" if v is None else v)
        cur.execute(f"SELECT {','.join(_SUB_STR + _SUB_INT)} FROM nx.item_sub WHERE item_code=?", code)
        rs = cur.fetchone()
        sub_d = dict(zip(_SUB_STR + _SUB_INT, ["" if x is None else x for x in rs])) if rs else {}
        cur.execute(f"SELECT {','.join(_VALVE_F)} FROM nx.item_valve WHERE item_code=?", code)
        rv = cur.fetchone()
        valve_d = dict(zip(_VALVE_F, ["" if x is None else x for x in rv])) if rv else {}
        return {"item": item_d, "sub": sub_d, "valve": valve_d, "has_valve": bool(rv)}
    finally:
        nx.close()

@router.post("/api/itemmaster/save")
def itemmaster_save(payload: dict = Body(...)):
    """품목마스터 등록/수정(nx.item + item_sub + item_valve).
    검증: 필수·공백·품번중복·매입처/작업장 배타. 자동: 내경(diam-thick*2)·make_type4→LG사급.
    품번변경(edit+코드변경): nx.bom/서브 연쇄 + item_his 이력 (BOM 무결성)."""
    p = payload
    code = str(p.get("item_code", "") or "").strip()
    name = str(p.get("item_name", "") or "").strip()
    if not code or not name:
        raise HTTPException(400, "품번·품명은 필수입니다.")
    if code != code.strip() or "  " in code or code != "".join(code.split(" ")) and (code[0] == " " or code[-1] == " "):
        raise HTTPException(400, "품번 앞/뒤에 공백은 사용할 수 없습니다.")
    for k in ("sgroup", "unit"):   # 하드필수(전 그룹 공통): 품번·품명·소분류·단위. 대분류는 성격별 소프트권장으로 이동.
        if not str(p.get(k, "") or "").strip():
            raise HTTPException(400, "소분류·단위는 필수입니다.")
    in_cust = str(p.get("in_cust", "") or "").strip()
    work_code = str(p.get("work_code", "") or "").strip()
    if in_cust and work_code:
        raise HTTPException(400, "매입처(업체)와 작업장은 둘 중 하나만 입력 가능합니다.")

    def sval(k, n=None):
        v = p.get(k)
        if v in (None, ""): return None
        v = str(v).strip()
        return v[:n] if n else v
    def dval(k):
        v = p.get(k)
        try: return float(v) if v not in (None, "") else None
        except Exception: return None
    def ival(k):
        v = p.get(k)
        try: return int(float(v)) if v not in (None, "") else None
        except Exception: return None

    # 내경 자동(외경-두께*2)
    diam, thick = dval("diam"), dval("thick")
    if diam is not None and thick is not None and not p.get("item_pipe_id"):
        p["item_pipe_id"] = round(diam - thick * 2, 4)
    # ★net_weight 자동 재계산(원소재 cg='3': 치수·재질로 기하중량 = 레거시 f_get_weight3).
    #   SP가 저장 중량 무시하고 항상 기하계산 → 편집 시 재계산해야 stale 방지(컷오버 후 CRUD·병행운영 sync 양쪽 정합).
    if str(p.get("cost_gubun", "")).strip() == "3":
        _gw = _geom_weight(p.get("metal_gubun"), diam, thick, dval("length"))
        if _gw is not None:
            p["net_weight"] = _gw
    # make_type=4 → LG사급 자동
    if str(p.get("make_type", "")).strip() == "4":
        p["lg_obtain_flag"] = "1"

    is_edit = bool(p.get("_edit"))
    orig = str(p.get("_orig_code", "") or "").strip() or code
    user = (str(p.get("user", "") or "").strip() or "웹사용자")[:20]

    nx = _nx(); nx.autocommit = False; cur = nx.cursor()
    try:
        cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", code)
        exists = cur.fetchone() is not None
        if not is_edit and exists:
            raise HTTPException(400, "동일한 품번이 이미 등록되어 있습니다.")

        # ── 품번 변경(rename): copy→repoint(BOM/서브)→delete old + 이력 ──
        if is_edit and orig and orig != code:
            if exists:
                raise HTTPException(400, "변경할 품번이 이미 존재합니다.")
            cur.execute("""INSERT INTO nx.item(item_code,item_name,item_type,unit,status,silver_flag,has_gagong)
                SELECT ?,item_name,item_type,unit,status,silver_flag,has_gagong FROM nx.item WHERE item_code=?""", code, orig)
            cur.execute("UPDATE nx.item_sub   SET item_code=? WHERE item_code=?", code, orig)
            cur.execute("UPDATE nx.item_valve SET item_code=? WHERE item_code=?", code, orig)
            cur.execute("UPDATE nx.bom_header SET item_code=? WHERE item_code=?", code, orig)
            cur.execute("UPDATE nx.bom_line   SET child_item=? WHERE child_item=?", code, orig)
            cur.execute("DELETE FROM nx.item WHERE item_code=?", orig)
            cur.execute("INSERT INTO nx.item_his(old_code,new_code,change_dt,user_id) VALUES(?,?,getdate(),?)", orig, code, user)
            exists = True   # 새 코드 행 생성됨

        # ── 성격(품목유형) + 제품군/제품계열 자동파생(코드→이름) + 소프트권장 경고 ──
        sgroup_v = str(p.get("sgroup", "") or "").strip()
        nature, active = _item_nature(cur, code, sgroup_v)
        prod_group, prod_line = _derive_class(code, sgroup_v, _load_prefix_map(cur))   # 파생: 접두어+소분류
        warnings = []
        for f in _NATURE_SOFT.get(nature, []):
            miss = (dval(f) in (None, 0) or dval(f) == 0.0) if f in _IM_NUM else (not str(p.get(f, "") or "").strip())
            if miss: warnings.append(_FIELD_LABEL.get(f, f))

        # ── nx.item 코어+업무 upsert (NOT NULL 컬럼은 미전송 시 기존값 보존/기본값) ──
        _DEF = {"item_type": "제품", "unit": "EA", "status": "사용"}   # NOT NULL 컬럼 기본값
        allcols = _IM_CORE + _IM_BIZ
        rawvals = [dval(c) if c in _IM_NUM else (ival(c) if c in _IM_INT else sval(c, 200)) for c in allcols]
        if exists:
            setcols = [f"{c}=ISNULL(?,{c})" if c in _DEF else f"{c}=?" for c in allcols] + ["nature=?", "active=?", "prod_group=?", "prod_line=?"]
            cur.execute(f"UPDATE nx.item SET {','.join(setcols)} WHERE item_code=?", *rawvals, nature, active, prod_group, prod_line, code)
        else:
            ivals = [(v if v is not None else _DEF[c]) if c in _DEF else v for c, v in zip(allcols, rawvals)]
            cur.execute(f"""INSERT INTO nx.item(item_code,{','.join(allcols)},silver_flag,has_gagong,nature,active,prod_group,prod_line)
                VALUES(?,{','.join(['?']*len(allcols))},0,0,?,?,?,?)""", code, *ivals, nature, active, prod_group, prod_line)

        # ── item_sub upsert (delete→insert) ──
        cur.execute("DELETE FROM nx.item_sub WHERE item_code=?", code)
        sub_vals = [sval(k, 500) for k in _SUB_STR] + [ival(k) for k in _SUB_INT]
        if any(v not in (None, "") for v in sub_vals):
            cur.execute(f"INSERT INTO nx.item_sub(item_code,{','.join(_SUB_STR + _SUB_INT)}) "
                        f"VALUES(?,{','.join(['?']*len(_SUB_STR + _SUB_INT))})", code, *sub_vals)

        # ── item_valve upsert (설치품, 값 있을 때만) ──
        cur.execute("DELETE FROM nx.item_valve WHERE item_code=?", code)
        vv = [sval(k, 400) for k in _VALVE_F]
        if any(v not in (None, "") for v in vv):
            cur.execute(f"INSERT INTO nx.item_valve(item_code,{','.join(_VALVE_F)}) "
                        f"VALUES(?,{','.join(['?']*len(_VALVE_F))})", code, *vv)

        nx.commit()
        return {"ok": True, "mode": ("update" if is_edit else "insert"), "item_code": code,
                "renamed": (is_edit and orig != code), "nature": nature, "warnings": warnings}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()

@router.post("/api/itemmaster/delete")
def itemmaster_delete(payload: dict = Body(...)):
    """삭제 — BOM 무결성 게이트: 단일BOM(nx.bom_header 모 / nx.bom_line 자) 참조 있으면 거부.
    ★단일BOM 통일(2026-08-13): 레거시 PR_M_ITEM_BOM 별도체크 제거(nx.bom_line이 정본)."""
    codes = [str(x).strip() for x in (payload.get("codes", []) or []) if str(x).strip()]
    if not codes: return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        blocked = []
        for code in codes:
            cur.execute("SELECT 1 FROM nx.bom_header WHERE item_code=?", code); a = cur.fetchone()
            cur.execute("SELECT 1 FROM nx.bom_line WHERE child_item=?", code); b = cur.fetchone()
            if a or b: blocked.append(code)
        if blocked:
            return {"ok": False, "errors": [f"{c} : BOM에 사용중이라 삭제할 수 없습니다." for c in blocked]}
        for code in codes:
            cur.execute("DELETE FROM nx.item_sub WHERE item_code=?", code)
            cur.execute("DELETE FROM nx.item_valve WHERE item_code=?", code)
            cur.execute("DELETE FROM nx.item WHERE item_code=?", code)
        return {"ok": True, "deleted": len(codes)}
    finally:
        nx.close()
