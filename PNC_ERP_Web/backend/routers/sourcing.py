# -*- coding: utf-8 -*-
"""sourcing 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 조달경로(SUB변형) 그룹 — 접미사 품번을 '동일결과 SUB' 그룹으로 묶어 조달처 배분 =================
# 모델: Assy의 SUB가 여러 조달처(생산처)로 제작되며 레거시는 품번접미사로 복제. 동일결과(자식set)로 그룹핑,
#       생산처(IN_CUST_CODE)=실제 조달처. 다조달처 그룹은 유효기간+배분%(합100%)로 편성 라우팅. nx.procgroup_alloc
import re as _re
_MK = {"1": "자체", "2": "외주(유상사급)", "3": "매입", "": "미지정"}

def _base_of(code):
    return _re.sub(r'\(.*?\)', '', code).split('-')[0].strip()

def _jac(a, b):
    if not a and not b: return 1.0
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)

def _ensure_procgroup_tbl(cur):
    cur.execute("""IF OBJECT_ID('nx.procgroup_alloc') IS NULL CREATE TABLE nx.procgroup_alloc(
        variant_item varchar(120) PRIMARY KEY, base_item varchar(30), group_key varchar(80),
        vendor_code varchar(10), vendor_name varchar(80), is_new bit DEFAULT 0,
        apply_from date, apply_to date, alloc_ratio decimal(9,4), is_active bit DEFAULT 1,
        priority int, upd_dt datetime DEFAULT getdate())""")
    for col, ddl in [("vendor_code", "varchar(10)"), ("vendor_name", "varchar(80)"), ("is_new", "bit")]:
        cur.execute(f"IF COL_LENGTH('nx.procgroup_alloc','{col}') IS NULL ALTER TABLE nx.procgroup_alloc ADD {col} {ddl}")

@router.get("/api/procgroup/vendors")
def procgroup_vendors(q: str = Query("")):
    """조달처(거래처) 검색 — 새 조달처 후보 추가용"""
    q = q.strip()
    cn = _conn(); cur = cn.cursor()
    try:
        like = f"%{q}%"
        cur.execute("""SELECT TOP 40 CUST_CODE, ISNULL(CUST_DESC,'') FROM CM_M_CUST
            WHERE CUST_CODE LIKE ? OR CUST_DESC LIKE ? ORDER BY CUST_DESC""", like, like)
        return {"rows": [{"code": r[0], "nm": r[1]} for r in cur.fetchall()]}
    finally:
        cn.close()

@router.get("/api/procgroup/get")
def procgroup_get(base: str = Query(...), ymd: str = Query("")):
    """base Assy의 변형들을 '동일결과 SUB' 그룹으로 묶어 조달처 후보 반환 + 저장된 배분 병합."""
    base = base.strip()
    if not base:
        raise HTTPException(400, "base 품번 필요")
    ay = _d6(ymd) if ymd else ""
    cn = _conn(); cur = cn.cursor()
    try:
        # 변형 마스터
        # 레거시 개발품목BOM관리(w_cs_master_120)와 동일하게 전 변형 표기(status 필터 제거).
        # 실제 생산단은 아래 nk>0(현재유효 BOM 보유)로 자동 선별 → (CI적용)/예상가 더미 자동제외.
        cur.execute("""SELECT i.ITEM_CODE, ISNULL(i.ITEM_DESC,''), ISNULL(i.IN_CUST_CODE,''),
              ISNULL(cu.CUST_DESC,''), ISNULL(i.MAKE_TYPE,''), ISNULL(i.ITEM_STATUS,'')
            FROM PR_M_ITEM i LEFT JOIN CM_M_CUST cu ON cu.CUST_CODE=i.IN_CUST_CODE
            WHERE i.ITEM_CODE LIKE ?""", base + '%')
        vs = []
        for ic, nm, cc, cnm, mk, st in cur.fetchall():
            if _base_of(ic) != base and ic != base:
                continue
            vs.append({"item": ic, "nm": nm, "cust_code": cc, "cust": (cnm or ("자체" if not cc else cc)),
                       "mk": mk, "mk_label": _MK.get(mk, mk), "status": st})
        if not vs:
            return {"base": base, "groups": [], "msg": "변형 없음(활성품목)"}
        # 각 변형 BOM 자식 set (현재유효 또는 지정일)
        for v in vs:
            if ay:
                cur.execute("""SELECT MAT_CODE, ISNULL(SAGUB_FLAG,'0') FROM CS_M_ITEM_BOM
                    WHERE ITEM_CODE=? AND FROM_APPLY_YMD<=? AND TO_APPLY_YMD>=?""", v["item"], ay, ay)
            else:
                cur.execute("""SELECT MAT_CODE, ISNULL(SAGUB_FLAG,'0') FROM CS_M_ITEM_BOM
                    WHERE ITEM_CODE=? AND TO_APPLY_YMD>='260601'""", v["item"])
            ch = cur.fetchall()
            v["_kset"] = frozenset(x[0] for x in ch)
            v["nk"] = len(v["_kset"]); v["sag"] = sum(1 for x in ch if x[1] == '1')
            v["is_self"] = (v["item"] == base)
        prod = [v for v in vs if v["nk"] > 0]  # 실제 생산단(BOM 보유)
        # 사용여부 신호: as-built BOM 트리(현재 실제 투입경로) + 26년 확정입고
        cur.execute("SELECT ITEM_CODE, MAT_CODE FROM CS_M_ITEM_BOM WHERE TO_APPLY_YMD>='260601'")
        _ch = {}
        for p, m in cur.fetchall(): _ch.setdefault(p, set()).add(m)
        tree = {base}; stack = [base]
        while stack:
            x = stack.pop()
            for k in _ch.get(x, ()):
                if k not in tree: tree.add(k); stack.append(k)
        for v in vs:
            v["in_tree"] = v["item"] in tree
            # ★현행 = 실입고(recv>0). 개발(조달경로 통합검토 subvariant/get)과 동일 기준(동일 쿼리: 태그무관·MAINT_QTY>0·260101~)
            q = cur.execute("""SELECT ISNULL(SUM(MAINT_QTY),0) FROM PU_T_STOCK_MAINT
                WHERE UPPER(LTRIM(RTRIM(MAT_CODE)))=? AND MAINT_YMD>='260101' AND MAINT_QTY>0""", v["item"].upper()).fetchone()
            v["recv"] = float(q[0] or 0)
            v["used"] = v["recv"] > 0   # 현행=실입고만(개발과 일치). in_tree(BOM경로) 과다판정 제거
            v["mk_conflict"] = (v["mk"] == '3' and v["sag"] > 0)  # 매입인데 사급자식有 = 분류오류 의심
        # 클러스터: 자식 Jaccard>=0.75
        used = [False] * len(prod); clusters = []
        for i in range(len(prod)):
            if used[i]: continue
            cl = [i]; used[i] = True
            for j in range(i + 1, len(prod)):
                if not used[j] and _jac(prod[i]["_kset"], prod[j]["_kset"]) >= 0.75:
                    cl.append(j); used[j] = True
            clusters.append(cl)
    finally:
        cn.close()
    # 저장된 배분 병합
    nx = _nx(); ncur = nx.cursor()
    try:
        _ensure_procgroup_tbl(ncur)
        ncur.execute("""SELECT variant_item, group_key, ISNULL(vendor_code,''), ISNULL(vendor_name,''),
            ISNULL(is_new,0), CONVERT(varchar(10),apply_from,23), CONVERT(varchar(10),apply_to,23),
            alloc_ratio, is_active FROM nx.procgroup_alloc WHERE base_item=?""", base)
        saved = {}; synth = {}
        for r in ncur.fetchall():
            rec = {"group_key": r[1], "vendor_code": r[2], "vendor_name": r[3], "is_new": bool(r[4]),
                   "apply_from": r[5], "apply_to": r[6],
                   "alloc_ratio": float(r[7]) if r[7] is not None else None,
                   "is_active": bool(r[8]) if r[8] is not None else True}
            saved[r[0]] = rec
            if rec["is_new"]:
                synth.setdefault(r[1], []).append((r[0], rec))
    finally:
        nx.close()
    groups = []
    for gi, cl in enumerate(clusters, 1):
        members = [prod[k] for k in cl]
        gkey = f"{base}#{min(m['item'] for m in members)}"
        out_members = []
        for m in members:
            s = saved.get(m["item"], {})
            out_members.append({
                "item": m["item"], "nm": m["nm"], "cust": m["cust"], "cust_code": m["cust_code"],
                "mk": m["mk"], "mk_label": m["mk_label"], "sag": m["sag"], "nk": m["nk"],
                "is_self": m["is_self"], "is_new": False,
                "used": m["used"], "in_tree": m["in_tree"], "recv": m["recv"], "mk_conflict": m["mk_conflict"],
                "apply_from": s.get("apply_from"), "apply_to": s.get("apply_to"),
                # 현행 100% 단일운영 시스템에서 이관 → 저장전 기본값 = 현행(사용중)만 활성
                "alloc_ratio": s.get("alloc_ratio"), "is_active": s.get("is_active", m["used"]),
            })
        # 신규 조달처 후보(가상 — 품번복제 없이 거래처만) 병합
        for (vi, rec) in synth.get(gkey, []):
            out_members.append({
                "item": vi, "nm": "＋신규 조달처", "cust": rec["vendor_name"] or rec["vendor_code"],
                "cust_code": rec["vendor_code"], "mk": "2", "mk_label": "외주(유상사급)", "sag": 0,
                "nk": members[0]["nk"], "is_self": False, "is_new": True,
                "used": True, "in_tree": False, "recv": 0.0, "mk_conflict": False,
                "apply_from": rec["apply_from"], "apply_to": rec["apply_to"],
                "alloc_ratio": rec["alloc_ratio"], "is_active": rec["is_active"],
            })
        if not out_members:
            continue   # 빈 그룹 방지
        custs = sorted(set(m["cust"] for m in out_members))
        groups.append({"group_key": gkey, "gi": gi, "nk": members[0]["nk"],
                       "multi_source": len(custs) >= 2, "custs": custs, "members": out_members})
    # 다조달처(배분대상) 우선 정렬
    groups.sort(key=lambda g: (not g["multi_source"], g["gi"]))
    base_nm = next((v["nm"] for v in vs if v["item"] == base), "")
    return {"base": base, "base_nm": base_nm, "n_variants": len(vs), "n_prod": len(prod),
            "n_groups": len(groups), "groups": groups,
            "msg": ("" if groups else "개발(조달경로 통합검토)에서 이 품번의 조달경로를 아직 포함하지 않았습니다. 개발에서 후보를 ➕포함하면 여기 표시됩니다.")}

@router.post("/api/procgroup/save")
def procgroup_save(payload: dict = Body(...)):
    """조달그룹 배분 저장. 검증: 각 그룹의 활성 조달처 배분합=100%(겹치는 기간마다). 위반시 미기록."""
    base = str(payload.get("base", "")).strip()
    rows = payload.get("rows", []) or []
    # 그룹별 활성 배분 수집 → 검증
    bygroup = {}
    norm = []
    for r in rows:
        vi = str(r.get("variant_item", "")).strip()
        if not vi: continue
        gk = str(r.get("group_key", "")).strip()
        vc = str(r.get("vendor_code", "")).strip()
        vn = str(r.get("vendor_name", "")).strip()
        isnew = 1 if r.get("is_new") else 0
        af = _d(r.get("apply_from")) or "2000-01-01"
        at = _d(r.get("apply_to"))
        act = bool(r.get("is_active"))
        ratio = r.get("alloc_ratio"); ratio = float(ratio) if (ratio not in (None, "", "null")) else None
        norm.append((vi, base, gk, vc, vn, isnew, af, at, 1 if act else 0, ratio))
        if act and ratio is not None:   # 배분참여 = 활성+배분% 입력된 것만(미유효/공란 제외)
            bygroup.setdefault(gk, []).append((af, at, ratio))
    errs = []
    for gk, profs in bygroup.items():
        if len(profs) >= 1:  # 배분값 입력된 조달처들: 유효기간 겹치는 구간마다 합=100%
            errs += [f"[{gk}] {e}" for e in _validate_alloc(profs)]
    if errs:
        return {"ok": False, "errors": list(dict.fromkeys(errs))}
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_procgroup_tbl(cur)
        for (vi, bs, gk, vc, vn, isnew, af, at, act, ratio) in norm:
            cur.execute("DELETE FROM nx.procgroup_alloc WHERE variant_item=?", vi)
            cur.execute("""INSERT INTO nx.procgroup_alloc(variant_item,base_item,group_key,vendor_code,vendor_name,is_new,apply_from,apply_to,alloc_ratio,is_active,upd_dt)
                VALUES(?,?,?,?,?,?,?,?,?,?,getdate())""", vi, bs, gk, vc, vn, isnew, af, at, ratio, act)
        return {"ok": True, "count": len(norm)}
    finally:
        nx.close()


# ============ 공통 SUB 통합 검토화면(nx.sub_variant_map) + 사급·현행 정합 ============
@router.get("/api/subvariant/bases")
def subvariant_bases(q: str = Query("")):
    """통합대상 베이스 목록(다변형). q=품번검색."""
    nx = _nx(); cur = nx.cursor()
    try:
        like = f"%{q.strip()}%"
        cur.execute("""SELECT m.base_item, COUNT(*) nv, COUNT(DISTINCT m.common_sub) ng,
              SUM(CAST(m.is_current AS int)) cur, MAX(ISNULL(i.item_name,'')) nm
            FROM nx.sub_variant_map m LEFT JOIN nx.item i ON i.item_code=m.base_item
            WHERE m.base_item LIKE ? GROUP BY m.base_item ORDER BY COUNT(*) DESC""", like)
        rows = [{"base": r[0], "nv": r[1], "ng": r[2], "cur": r[3], "nm": r[4]} for r in cur.fetchall()]
        return {"rows": rows[:200]}
    finally:
        nx.close()

@router.get("/api/subvariant/get")
def subvariant_get(base: str = Query(...)):
    """베이스의 -S그룹 + 멤버(공급처·현행·구분·사급부품·오분류경고) + 저장된 승인."""
    base = base.strip()
    nx = _nx(); ncur = nx.cursor()
    try:
        ncur.execute("""SELECT struct_group, common_sub, variant_item, vendor_code, ISNULL(vendor_name,''),
              n_child, is_current FROM nx.sub_variant_map WHERE base_item=? ORDER BY struct_group, variant_item""", base)
        recs = ncur.fetchall()
        # 승인상태
        ncur.execute("""IF OBJECT_ID('nx.subvariant_approve') IS NULL CREATE TABLE nx.subvariant_approve(
            common_sub NVARCHAR(35) PRIMARY KEY, approved BIT, note NVARCHAR(200), approver NVARCHAR(30), upd_dt datetime DEFAULT getdate())""")
        ncur.execute("SELECT common_sub, approved, ISNULL(note,'') FROM nx.subvariant_approve")
        appr = {r[0]: {"approved": bool(r[1]), "note": r[2]} for r in ncur.fetchall()}
        # 조달경로 포함(nx 전용, 마이그레이션 안전) — 담당이 후보 변형을 조달경로로 포함
        ncur.execute("""IF OBJECT_ID('nx.sourcing_path','U') IS NULL CREATE TABLE nx.sourcing_path(
            base_item NVARCHAR(60), variant_item NVARCHAR(60), vendor NVARCHAR(60), included BIT DEFAULT 1,
            note NVARCHAR(200), upd_dt datetime DEFAULT getdate(), CONSTRAINT PK_nx_sourcing_path PRIMARY KEY(base_item, variant_item))""")
        ncur.execute("SELECT LTRIM(RTRIM(variant_item)), included FROM nx.sourcing_path WHERE base_item=?", base)
        incl = {str(r[0]).strip(): bool(r[1]) for r in ncur.fetchall()}
        # ★후보별 공정 = 개발 지정 정본(nx.routing=CS_T_ITEM_PROC=품목별 공정관리)만. 협력사견적(coop)은 '그냥 견적(단가)'이라 공정 기준 아님.
        #   proc_code≥90=관리/운반/이윤 제외, work_qty>0=개발이 실제 지정한 공정.
        rtcode = {}
        try:
            ncur.execute("""SELECT r.item_code, r.proc_code FROM nx.routing r
                JOIN nx.sub_variant_map m ON m.variant_item=r.item_code AND m.base_item=?
                WHERE ISNULL(r.proc_code,'')<>'' AND ISNULL(TRY_CONVERT(int,r.proc_code),0)<90
                AND ISNULL(TRY_CONVERT(float,r.work_qty),0)>0 ORDER BY r.item_code, r.sort_seq""", base)
            for r in ncur.fetchall(): rtcode.setdefault(str(r[0]).strip(), []).append(str(r[1]).strip())
        except Exception:
            pass
        # 저장된 조달 프로파일(유효기간·배분%·활성) — 조달 프로파일 화면 편집값
        prof = {}
        try:
            _ensure_procgroup_tbl(ncur)
            ncur.execute("""SELECT LTRIM(RTRIM(variant_item)), CONVERT(varchar(10),apply_from,23),
                CONVERT(varchar(10),apply_to,23), alloc_ratio, is_active FROM nx.procgroup_alloc WHERE base_item=?""", base)
            for r in ncur.fetchall():
                prof[str(r[0]).strip()] = {"apply_from": r[1], "apply_to": r[2],
                    "alloc_ratio": (float(r[3]) if r[3] is not None else None),
                    "is_active": (bool(r[4]) if r[4] is not None else None)}
        except Exception:
            pass
    finally:
        nx.close()
    if not recs:
        return {"base": base, "groups": [], "msg": "통합대상 아님(단일변형)"}
    items = [r[2] for r in recs]
    # live 보강: 구분(MAKE_TYPE)·사급부품
    cn = _conn(); cur = cn.cursor()
    try:
        mk = {}; nm = {}
        for i in range(0, len(items), 900):
            ch = items[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(MAKE_TYPE,''), ISNULL(ITEM_DESC,'') FROM PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ch)
            for r in cur.fetchall(): mk[r[0]] = r[1]; nm[r[0]] = r[2]
        sag = {}
        for i in range(0, len(items), 900):
            ch = items[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"""SELECT LTRIM(RTRIM(ITEM_CODE)), LTRIM(RTRIM(MAT_CODE)) FROM CS_M_ITEM_BOM
                WHERE ITEM_CODE IN ({ph}) AND SAGUB_FLAG='1' AND TO_APPLY_YMD>='260601'""", *ch)
            for r in cur.fetchall(): sag.setdefault(r[0], []).append(r[1])
        # 변형별 실입고(2026, MAINT_QTY>0) — 현행 판정을 플래그 대신 실거래로 (레거시 is_current 오표시 정정)
        recv = {}
        try:
            up = [x.upper() for x in items]
            for i in range(0, len(up), 900):
                ch = up[i:i+900]; ph = ",".join("?" * len(ch))
                cur.execute(f"""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), SUM(MAINT_QTY), MAX(MAINT_YMD)
                    FROM PU_T_STOCK_MAINT WHERE UPPER(LTRIM(RTRIM(MAT_CODE))) IN ({ph})
                    AND MAINT_YMD>='260101' AND MAINT_QTY>0 GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))""", *ch)
                for r in cur.fetchall(): recv[r[0]] = {"qty": float(r[1] or 0), "last": str(r[2] or "")}
        except Exception:
            pass
        # 공정코드→이름(CS_M_PROC): nx.routing proc_code 라벨(컷팅/면취/CNC…)
        pname = {}
        try:
            allc = sorted({c for lst in rtcode.values() for c in lst})
            for i in range(0, len(allc), 900):
                ch = allc[i:i+900]; ph = ",".join("?" * len(ch))
                cur.execute(f"SELECT PROC_CODE, PROC_DESC FROM CS_M_PROC WHERE PROC_CODE IN ({ph})", *ch)
                for r in cur.fetchall(): pname[str(r[0]).strip()] = str(r[1]).strip()
        except Exception:
            pass
    finally:
        cn.close()
    # 그룹 구성
    gmap = {}
    for sg, csub, vi, vc, vn, nch, iscur in recs:
        g = gmap.setdefault(csub, {"struct_group": sg, "common_sub": csub, "n_child": nch, "members": [],
                                    "approved": appr.get(csub, {}).get("approved", False), "note": appr.get(csub, {}).get("note", "")})
        mkc = mk.get(vi, ""); slist = sag.get(vi, []); rv = recv.get(vi.upper(), {})
        ops = [pname.get(c, c) for c in rtcode.get(str(vi).strip(), [])]   # ★개발 정본(품목별 공정관리)만. 협력사견적은 공정 기준 아님
        g["members"].append({
            "variant": vi, "nm": nm.get(vi, ""), "vendor": vn or ("자체" if not vc else vc), "vendor_code": vc,
            "mk": mkc, "mk_label": _MK.get(mkc, mkc), "sag_parts": slist, "sag_cnt": len(slist),
            "mk_conflict": (mkc == '3' and len(slist) > 0), "is_current": bool(iscur),
            "recv_qty": rv.get("qty", 0), "recv_last": rv.get("last", ""), "real_current": rv.get("qty", 0) > 0,
            "included": incl.get(str(vi).strip(), False),
            "ops": ops, "proc_sig": "|".join(ops),
            "needs_proc": True,
            # 조달 프로파일 편집값(유효기간·배분%·활성). 저장 전엔 None
            "apply_from": prof.get(str(vi).strip(), {}).get("apply_from"),
            "apply_to": prof.get(str(vi).strip(), {}).get("apply_to"),
            "alloc_ratio": prof.get(str(vi).strip(), {}).get("alloc_ratio"),
            "prof_active": prof.get(str(vi).strip(), {}).get("is_active")})
    groups = list(gmap.values())
    for g in groups:
        g["vendors"] = sorted(set(m["vendor"] for m in g["members"]))
        g["multi"] = len(g["vendors"]) >= 2  # 통합가치=다공급처
    groups.sort(key=lambda g: (not g["multi"], g["struct_group"]))
    return {"base": base, "base_nm": nm.get(base, "") or next((m["nm"] for g in groups for m in g["members"]), ""),
            "n_variants": len(items), "n_groups": len(groups), "groups": groups}

@router.post("/api/subvariant/approve")
def subvariant_approve(payload: dict = Body(...)):
    """담당 승인: -S그룹의 '동일결과' 통합 승인/보류 + 사유."""
    csub = str(payload.get("common_sub", "")).strip()
    if not csub:
        raise HTTPException(400, "common_sub 필요")
    approved = 1 if payload.get("approved") else 0
    note = str(payload.get("note", "")).strip()[:200]
    user = (str(payload.get("user", "")).strip() or "담당")[:30]
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""IF OBJECT_ID('nx.subvariant_approve') IS NULL CREATE TABLE nx.subvariant_approve(
            common_sub NVARCHAR(35) PRIMARY KEY, approved BIT, note NVARCHAR(200), approver NVARCHAR(30), upd_dt datetime DEFAULT getdate())""")
        cur.execute("DELETE FROM nx.subvariant_approve WHERE common_sub=?", csub)
        cur.execute("INSERT INTO nx.subvariant_approve(common_sub,approved,note,approver,upd_dt) VALUES(?,?,?,?,getdate())",
                    csub, approved, note, user)
        return {"ok": True}
    finally:
        nx.close()

@router.post("/api/subvariant/include")
def subvariant_include(payload: dict = Body(...)):
    """조달경로 포함 토글(nx.sourcing_path, nx 전용·마이그레이션 안전) — 후보 변형을 이 품번의 조달경로로 포함/제외."""
    base = str(payload.get("base", "")).strip()
    variant = str(payload.get("variant", "")).strip()
    if not base or not variant:
        raise HTTPException(400, "base·variant 필요")
    included = 1 if payload.get("included", True) else 0
    vendor = str(payload.get("vendor", "")).strip()[:60]
    note = str(payload.get("note", "")).strip()[:200]
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""IF OBJECT_ID('nx.sourcing_path','U') IS NULL CREATE TABLE nx.sourcing_path(
            base_item NVARCHAR(60), variant_item NVARCHAR(60), vendor NVARCHAR(60), included BIT DEFAULT 1,
            note NVARCHAR(200), upd_dt datetime DEFAULT getdate(), CONSTRAINT PK_nx_sourcing_path PRIMARY KEY(base_item, variant_item))""")
        cur.execute("DELETE FROM nx.sourcing_path WHERE base_item=? AND variant_item=?", base, variant)
        cur.execute("""INSERT INTO nx.sourcing_path(base_item,variant_item,vendor,included,note,upd_dt)
                       VALUES(?,?,?,?,?,getdate())""", base, variant, vendor, included, note)
        return {"ok": True, "included": bool(included)}
    finally:
        nx.close()


# ================= 조달경로 통합검토 재설계 (route 기반) — nx.sourcing_route(헤더) + nx.sourcing_route_line(라인) =================
# 상단=우리 기준 BOM(전 공정 우리가 만든다, bom/tree real=0). 하단=조달경로 후보 CRUD(경로1=현행 baseline·경로2..=대안).
# 승인게이트: 저장/편집 시 approve_flag=0 → 개발 승인(approve)해야 조달프로파일 후보로 노출(단일 소스 정합).
_ROUTE_GUBUN = ["자체", "매입", "외주유상", "외주무상"]          # 경로 헤더 구분
_LINE_GUBUN = ["제작", "매입", "사급"]                            # 라인 구분

def _ensure_route_tbl(cur):
    cur.execute("""IF OBJECT_ID('nx.sourcing_route','U') IS NULL CREATE TABLE nx.sourcing_route(
        route_id INT IDENTITY(1,1) PRIMARY KEY, item_code NVARCHAR(60) NOT NULL, route_no INT NOT NULL,
        route_name NVARCHAR(80), vendor_code NVARCHAR(20), gubun NVARCHAR(20), current_flag BIT DEFAULT 0,
        approve_flag BIT DEFAULT 0, apply_from DATE, note NVARCHAR(200),
        ins_user NVARCHAR(30), ins_dt datetime DEFAULT getdate(), upd_user NVARCHAR(30), upd_dt datetime DEFAULT getdate())""")
    cur.execute("""IF OBJECT_ID('nx.sourcing_route_line','U') IS NULL CREATE TABLE nx.sourcing_route_line(
        line_id INT IDENTITY(1,1) PRIMARY KEY, route_id INT NOT NULL, sort_seq INT DEFAULT 0,
        child_item NVARCHAR(60), child_name NVARCHAR(120), qty FLOAT, gubun NVARCHAR(20), vendor_code NVARCHAR(20),
        is_rawmat BIT DEFAULT 0, diam FLOAT, thick FLOAT, len_val FLOAT, material NVARCHAR(40),
        spec NVARCHAR(80), note NVARCHAR(200))""")
    # 반려(승인관리) 컬럼 멱등 추가
    cur.execute("IF COL_LENGTH('nx.sourcing_route','reject_flag') IS NULL ALTER TABLE nx.sourcing_route ADD reject_flag BIT DEFAULT 0")
    cur.execute("IF COL_LENGTH('nx.sourcing_route','reject_reason') IS NULL ALTER TABLE nx.sourcing_route ADD reject_reason NVARCHAR(200)")
    cur.execute("IF COL_LENGTH('nx.sourcing_route','reject_user') IS NULL ALTER TABLE nx.sourcing_route ADD reject_user NVARCHAR(30)")
    cur.execute("IF COL_LENGTH('nx.sourcing_route','reject_dt') IS NULL ALTER TABLE nx.sourcing_route ADD reject_dt datetime")

def _route_baseline_lines(item):
    """현행(baseline) 경로 라인 = 대상(item)의 실사용 BOM 직하위(level1). 구분: 사급/제작/매입, 공급처=IN_CUST, 치수 보강.
    ★조달후보=SUB/조달대상 단위(하단): 대상별 현행 경로1 = 그 대상의 직하위 구성/공급처."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""SELECT LTRIM(RTRIM(b.MAT_CODE)) child, CAST(b.USE_QTY AS float) q, ISNULL(b.SAGUB_FLAG,'0') sag,
              ISNULL(m.ITEM_DESC,'') nm, ISNULL(m.MAKE_TYPE,'') mk, ISNULL(m.IN_CUST_CODE,'') cust,
              ISNULL(c.CUST_DESC,'') custnm, ISNULL(m.METAL_GUBUN,'') metal,
              ISNULL(m.ITEM_DIAM,0) diam, ISNULL(m.ITEM_THICK,0) thick, ISNULL(m.ITEM_LENGTH,0) len,
              ISNULL(b.BOM_SEQ,0) sq
            FROM CS_M_ITEM_BOM b
            LEFT JOIN PR_M_ITEM m ON m.ITEM_CODE=b.MAT_CODE
            LEFT JOIN CM_M_CUST c ON c.CUST_CODE=m.IN_CUST_CODE
            WHERE b.ITEM_CODE=? AND b.FROM_APPLY_YMD<='991231' AND b.TO_APPLY_YMD>='260101'
              AND ISNULL(b.CS_CALC_EXCEPT_FLAG,'0')<>'1' ORDER BY b.BOM_SEQ""", item.strip())
        out = []
        for i, r in enumerate(cur.fetchall(), 1):
            gub = "사급" if str(r.sag) == '1' else ("제작" if str(r.mk) == '1' else "매입")
            out.append({"line_id": 0, "sort_seq": i, "child_item": r.child, "child_name": r.nm, "qty": float(r.q or 0),
                        "gubun": gub, "vendor_code": str(r.cust).strip(), "vendor_name": r.custnm,
                        "is_rawmat": 1 if str(r.metal).strip() else 0, "diam": float(r.diam or 0), "thick": float(r.thick or 0),
                        "len_val": float(r.len or 0), "material": str(r.metal).strip(), "spec": "", "note": ""})
        return out
    finally:
        cn.close()

def _custnm_map(cur, codes):
    m = {}
    codes = sorted({str(c).strip() for c in codes if str(c or "").strip()})
    for i in range(0, len(codes), 900):
        ch = codes[i:i+900]; ph = ",".join("?" * len(ch))
        cur.execute(f"SELECT CUST_CODE, ISNULL(CUST_DESC,'') FROM PARTNER_ERP.dbo.CM_M_CUST WHERE CUST_CODE IN ({ph})", *ch)
        for r in cur.fetchall(): m[str(r[0]).strip()] = r[1]
    return m

@router.get("/api/sourcing/routes")
def sourcing_routes(item: str = Query(...), show_unapproved: int = Query(1), for_profile: int = Query(0)):
    """품목의 조달경로 후보 목록. 경로1=현행(baseline, 실사용BOM 파생·읽기전용) 항상 포함. 경로2..=저장된 대안(nx.sourcing_route).
    for_profile=1: approve_flag=1(승인)만 편성가능; show_unapproved=0 이면 미승인 완전제외, =1 이면 미승인도 회색/읽기전용 포함."""
    item = item.strip()
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("""SELECT r.route_id, r.route_no, ISNULL(r.route_name,''), ISNULL(r.vendor_code,''), ISNULL(r.gubun,''),
              r.current_flag, r.approve_flag, CONVERT(varchar(10),r.apply_from,23), ISNULL(r.note,''),
              ISNULL(r.reject_flag,0), ISNULL(r.reject_reason,'')
            FROM nx.sourcing_route r WHERE r.item_code=? ORDER BY r.route_no""", item)
        hdrs = cur.fetchall()
        routes = []
        vcodes = set()
        for h in hdrs:
            rid = int(h[0])
            cur.execute("""SELECT line_id, sort_seq, ISNULL(child_item,''), ISNULL(child_name,''), qty, ISNULL(gubun,''),
                  ISNULL(vendor_code,''), is_rawmat, diam, thick, len_val, ISNULL(material,''), ISNULL(spec,''), ISNULL(note,'')
                FROM nx.sourcing_route_line WHERE route_id=? ORDER BY sort_seq, line_id""", rid)
            lines = []
            for l in cur.fetchall():
                vcodes.add(l[6])
                lines.append({"line_id": int(l[0]), "sort_seq": int(l[1] or 0), "child_item": l[2], "child_name": l[3],
                              "qty": float(l[4] or 0), "gubun": l[5], "vendor_code": str(l[6]).strip(),
                              "is_rawmat": int(l[7] or 0), "diam": float(l[8] or 0), "thick": float(l[9] or 0),
                              "len_val": float(l[10] or 0), "material": l[11], "spec": l[12], "note": l[13]})
            vcodes.add(str(h[3]).strip())
            routes.append({"route_id": rid, "route_no": int(h[1]), "route_name": h[2], "vendor_code": str(h[3]).strip(),
                           "gubun": h[4], "current_flag": bool(h[5]), "approve_flag": bool(h[6]), "apply_from": h[7],
                           "note": h[8], "reject_flag": bool(h[9]), "reject_reason": h[10], "baseline": False, "lines": lines})
        # 현행 baseline 합성(저장된 route_no=1 이 없을 때만) — 읽기전용·자동승인 기준선
        has_saved_current = any(r["current_flag"] or r["route_no"] == 1 for r in routes)
        if not has_saved_current:
            blines = _route_baseline_lines(item)
            for l in blines: vcodes.add(l["vendor_code"])
            routes.insert(0, {"route_id": 0, "route_no": 1, "route_name": "현행(실사용 BOM)", "vendor_code": "",
                              "gubun": "자체", "current_flag": True, "approve_flag": True, "apply_from": None,
                              "note": "레거시 실사용 BOM 파생(기준선·읽기전용). 대안은 [복사]로 생성.",
                              "reject_flag": False, "reject_reason": "", "baseline": True, "lines": blines})
        # 벤더 코드→이름
        vmap = _custnm_map(cur, vcodes)
        for r in routes:
            r["vendor_name"] = vmap.get(r["vendor_code"], r["vendor_code"])
            for l in r["lines"]: l["vendor_name"] = vmap.get(l["vendor_code"], l["vendor_code"])
        cur.execute("SELECT ISNULL(item_name,'') FROM nx.item WHERE item_code=?", item)
        r = cur.fetchone(); nm = r[0] if r else ""
        # 조달프로파일용 필터: 승인분만(선택적으로 미승인 회색포함)
        if for_profile:
            def keep(r):
                if r["approve_flag"]: return True
                return bool(show_unapproved)
            fr = [dict(r, readonly=(not r["approve_flag"])) for r in routes if keep(r)]
            routes = fr
        return {"item": item, "item_name": nm, "gubun_opts": _ROUTE_GUBUN, "line_gubun_opts": _LINE_GUBUN,
                "routes": routes}
    finally:
        nx.close()

def _route_hdr_errors(p):
    errs = []
    if not str(p.get("gubun", "")).strip(): errs.append("구분은 필수입니다")
    if str(p.get("gubun", "")).strip() != "자체" and not str(p.get("vendor_code", "")).strip():
        errs.append("공급처는 필수입니다(자체 제외)")
    if not str(p.get("apply_from", "")).strip(): errs.append("유효일자(적용시작)는 필수입니다")
    return errs

@router.post("/api/sourcing/route/save")
def sourcing_route_save(payload: dict = Body(...)):
    """경로 헤더 추가/수정 → nx.sourcing_route. 필수=구분·공급처(자체제외)·유효일자·현행여부. ★편집 시 approve_flag=0(승인 리셋)."""
    p = payload
    item = str(p.get("item_code", "")).strip()
    if not item: raise HTTPException(400, "item_code 필요")
    errs = _route_hdr_errors(p)
    if errs: return {"ok": False, "errors": errs}
    rid = p.get("route_id")
    gub = str(p.get("gubun", "")).strip()[:20]
    ven = str(p.get("vendor_code", "")).strip()[:20]
    cur_f = 1 if p.get("current_flag") else 0
    apf = _d(p.get("apply_from"))
    note = str(p.get("note", "")).strip()[:200]
    rname = str(p.get("route_name", "")).strip()[:80]
    usr = (str(p.get("user", "")).strip() or "웹사용자")[:30]
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        if rid and int(rid) > 0:
            cur.execute("""UPDATE nx.sourcing_route SET route_name=?, vendor_code=?, gubun=?, current_flag=?,
                  apply_from=?, note=?, approve_flag=0, upd_user=?, upd_dt=getdate() WHERE route_id=?""",
                  rname, ven, gub, cur_f, apf, note, usr, int(rid))
            if cur.rowcount == 0: raise HTTPException(404, f"대상 없음(route_id={rid})")
            return {"ok": True, "route_id": int(rid), "mode": "update", "approve_reset": True}
        cur.execute("SELECT ISNULL(MAX(route_no),1) FROM nx.sourcing_route WHERE item_code=?", item)
        rno = int(cur.fetchone()[0]) + 1
        cur.execute("""INSERT INTO nx.sourcing_route(item_code,route_no,route_name,vendor_code,gubun,current_flag,
              approve_flag,apply_from,note,ins_user) OUTPUT INSERTED.route_id VALUES(?,?,?,?,?,?,0,?,?,?)""",
              item, rno, (rname or f"대안 {rno}"), ven, gub, cur_f, apf, note, usr)
        nid = int(cur.fetchone()[0])
        return {"ok": True, "route_id": nid, "route_no": rno, "mode": "insert"}
    finally:
        nx.close()

@router.post("/api/sourcing/route/copy")
def sourcing_route_copy(payload: dict = Body(...)):
    """경로 복사 → 새 대안 후보(approve_flag=0). 원본=저장경로(source_route_id>0) / 현행 baseline(source_route_id=0)
    / ★특정 품번(source_item): 그 품번의 현행 BOM(실사용) 직하위를 seed로 복사(대상 품목과 달라도 참조복사 가능).
    copy_children=1: 하위품번을 신규 채번(접미사 suffix, 기본 -S{route_no})으로 복제(nx.item 최소등록). =0: 기존 품번 유지."""
    p = payload
    item = str(p.get("item_code", "")).strip()
    if not item: raise HTTPException(400, "item_code 필요")
    src_rid = int(p.get("source_route_id") or 0)
    src_item = str(p.get("source_item", "")).strip()   # 특정 품번에서 복사(현행 BOM seed)
    copy_children = 1 if p.get("copy_children") else 0
    usr = (str(p.get("user", "")).strip() or "웹사용자")[:30]
    nx = _nx_tx(); cur = nx.cursor()   # 헤더+라인 원자적
    try:
        _ensure_route_tbl(cur)
        # 원본 라인 확보
        if src_item:   # ★특정 품번의 현행 BOM을 seed로
            bl = _route_baseline_lines(src_item)
            if not bl: raise HTTPException(404, f"「{src_item}」의 현행 BOM 구성이 없습니다(품번 확인)")
            src_hdr = {"route_name": f"{src_item} 참조복사", "vendor_code": "", "gubun": "자체",
                       "apply_from": None, "note": f"{src_item} 현행 BOM 참조복사"}
            src_lines = [[l["sort_seq"], l["child_item"], l["child_name"], l["qty"], l["gubun"], l["vendor_code"],
                         l["is_rawmat"], l["diam"], l["thick"], l["len_val"], l["material"], l["spec"], l["note"]] for l in bl]
        elif src_rid > 0:
            cur.execute("""SELECT ISNULL(route_name,''), ISNULL(vendor_code,''), ISNULL(gubun,''),
                  CONVERT(varchar(10),apply_from,23), ISNULL(note,'') FROM nx.sourcing_route WHERE route_id=? AND item_code=?""", src_rid, item)
            h = cur.fetchone()
            if not h: raise HTTPException(404, "원본 경로 없음")
            src_hdr = {"route_name": h[0], "vendor_code": h[1], "gubun": h[2], "apply_from": h[3], "note": h[4]}
            cur.execute("""SELECT sort_seq, ISNULL(child_item,''), ISNULL(child_name,''), qty, ISNULL(gubun,''),
                  ISNULL(vendor_code,''), is_rawmat, diam, thick, len_val, ISNULL(material,''), ISNULL(spec,''), ISNULL(note,'')
                FROM nx.sourcing_route_line WHERE route_id=? ORDER BY sort_seq, line_id""", src_rid)
            src_lines = [list(r) for r in cur.fetchall()]
        else:   # 현행 baseline 파생
            src_hdr = {"route_name": "현행 복사", "vendor_code": "", "gubun": "자체", "apply_from": None, "note": "현행(실사용 BOM) 복사"}
            bl = _route_baseline_lines(item)
            src_lines = [[l["sort_seq"], l["child_item"], l["child_name"], l["qty"], l["gubun"], l["vendor_code"],
                         l["is_rawmat"], l["diam"], l["thick"], l["len_val"], l["material"], l["spec"], l["note"]] for l in bl]
        # 새 route_no
        cur.execute("SELECT ISNULL(MAX(route_no),1) FROM nx.sourcing_route WHERE item_code=?", item)
        rno = int(cur.fetchone()[0]) + 1
        suffix = str(p.get("suffix", "") or f"-S{rno}").strip()[:8]
        cur.execute("""INSERT INTO nx.sourcing_route(item_code,route_no,route_name,vendor_code,gubun,current_flag,
              approve_flag,apply_from,note,ins_user) OUTPUT INSERTED.route_id VALUES(?,?,?,?,?,0,0,?,?,?)""",
              item, rno, f"대안 {rno} (복사)", src_hdr["vendor_code"], src_hdr["gubun"],
              _d(src_hdr["apply_from"]), src_hdr["note"], usr)
        nid = int(cur.fetchone()[0])
        new_children = []
        for ln in src_lines:
            child = str(ln[1]).strip()
            if copy_children and child:
                newc = (child + suffix)[:60]
                cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", newc)
                if not cur.fetchone():
                    cur.execute("INSERT INTO nx.item(item_code,item_name,item_type) VALUES(?,?,N'부품')",
                                newc, (str(ln[2]) or child)[:120])
                new_children.append({"old": child, "new": newc})
                child = newc
            cur.execute("""INSERT INTO nx.sourcing_route_line(route_id,sort_seq,child_item,child_name,qty,gubun,
                  vendor_code,is_rawmat,diam,thick,len_val,material,spec,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  nid, ln[0], child, ln[2], ln[3], ln[4], ln[5], ln[6], ln[7], ln[8], ln[9], ln[10], ln[11], ln[12])
        nx.commit()
        return {"ok": True, "route_id": nid, "route_no": rno, "lines": len(src_lines),
                "copied_children": new_children, "suffix": suffix}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()

@router.post("/api/sourcing/route/delete")
def sourcing_route_delete(payload: dict = Body(...)):
    """경로 삭제(헤더+라인). 현행 baseline(route_id=0)은 삭제 불가. 근거키=route_id."""
    rid = int(payload.get("route_id") or 0)
    if rid <= 0: raise HTTPException(400, "현행(기준선)은 삭제할 수 없습니다 — 대안 경로만 삭제 가능")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("SELECT current_flag FROM nx.sourcing_route WHERE route_id=?", rid)
        r = cur.fetchone()
        if not r: raise HTTPException(404, "대상 없음")
        cur.execute("DELETE FROM nx.sourcing_route_line WHERE route_id=?", rid)
        cur.execute("DELETE FROM nx.sourcing_route WHERE route_id=?", rid)
        nx.commit()
        return {"ok": True, "deleted": rid}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()

@router.post("/api/sourcing/route/approve")
def sourcing_route_approve(payload: dict = Body(...)):
    """개발 승인 토글(approve_flag). =1 이라야 조달프로파일 후보로 노출. 현행 baseline(route_id=0)은 항상 승인상태."""
    rid = int(payload.get("route_id") or 0)
    if rid <= 0: return {"ok": True, "approve_flag": True}   # baseline 자동승인
    ap = 1 if payload.get("approve") else 0
    usr = (str(payload.get("user", "")).strip() or "개발")[:30]
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("UPDATE nx.sourcing_route SET approve_flag=?, upd_user=?, upd_dt=getdate() WHERE route_id=?", ap, usr, rid)
        if cur.rowcount == 0: raise HTTPException(404, "대상 없음")
        return {"ok": True, "approve_flag": bool(ap)}
    finally:
        nx.close()

def _line_errors(p):
    errs = []
    if not str(p.get("child_item", "")).strip(): errs.append("하위품번은 필수입니다")
    if not str(p.get("child_name", "")).strip(): errs.append("품명은 필수입니다")
    try: q = float(p.get("qty") or 0)
    except Exception: q = 0
    if q <= 0: errs.append("소요량(수량)은 0보다 커야 합니다(계산 필수)")
    g = str(p.get("gubun", "")).strip()
    if not g: errs.append("구분은 필수입니다")
    if g == "매입" and not str(p.get("vendor_code", "")).strip(): errs.append("매입 구분은 공급처가 필수입니다")
    if p.get("is_rawmat"):
        for k, lab in (("diam", "외경"), ("thick", "두께"), ("len_val", "길이"), ("material", "재질")):
            v = p.get(k)
            if k == "material":
                if not str(v or "").strip(): errs.append(f"{lab}은(는) 소재계산 대상 시 필수입니다")
            else:
                try: fv = float(v or 0)
                except Exception: fv = 0
                if fv <= 0: errs.append(f"{lab}은(는) 소재계산 대상 시 필수입니다(>0)")
    return errs

@router.post("/api/sourcing/line/save")
def sourcing_line_save(payload: dict = Body(...)):
    """경로 BOM 라인 추가/수정. 필수=하위품번·품명·소요량(>0)·구분; 매입이면 공급처; 소재계산 대상이면 외경/두께/길이/재질.
    ★라인 편집 시 해당 경로 approve_flag=0(승인 리셋). 현행 baseline(route_id=0)은 편집불가."""
    p = payload
    rid = int(p.get("route_id") or 0)
    if rid <= 0: raise HTTPException(409, "현행(기준선)은 편집할 수 없습니다 — [복사]로 대안 경로를 만들어 편집하세요")
    errs = _line_errors(p)
    if errs: return {"ok": False, "errors": errs}
    lid = int(p.get("line_id") or 0)
    vals = (str(p.get("child_item", "")).strip()[:60], str(p.get("child_name", "")).strip()[:120],
            float(p.get("qty") or 0), str(p.get("gubun", "")).strip()[:20], str(p.get("vendor_code", "")).strip()[:20],
            1 if p.get("is_rawmat") else 0, float(p.get("diam") or 0), float(p.get("thick") or 0),
            float(p.get("len_val") or 0), str(p.get("material", "")).strip()[:40],
            str(p.get("spec", "")).strip()[:80], str(p.get("note", "")).strip()[:200])
    usr = (str(p.get("user", "")).strip() or "웹사용자")[:30]
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        if lid > 0:
            cur.execute("""UPDATE nx.sourcing_route_line SET child_item=?, child_name=?, qty=?, gubun=?, vendor_code=?,
                  is_rawmat=?, diam=?, thick=?, len_val=?, material=?, spec=?, note=? WHERE line_id=?""", *vals, lid)
            if cur.rowcount == 0: raise HTTPException(404, "대상 라인 없음")
            out_lid = lid
        else:
            cur.execute("SELECT ISNULL(MAX(sort_seq),0)+1 FROM nx.sourcing_route_line WHERE route_id=?", rid)
            seq = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO nx.sourcing_route_line(route_id,sort_seq,child_item,child_name,qty,gubun,vendor_code,
                  is_rawmat,diam,thick,len_val,material,spec,note) OUTPUT INSERTED.line_id VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  rid, seq, *vals)
            out_lid = int(cur.fetchone()[0])
        cur.execute("UPDATE nx.sourcing_route SET approve_flag=0, upd_user=?, upd_dt=getdate() WHERE route_id=?", usr, rid)
        return {"ok": True, "line_id": out_lid, "approve_reset": True}
    finally:
        nx.close()

@router.post("/api/sourcing/line/delete")
def sourcing_line_delete(payload: dict = Body(...)):
    """경로 라인 삭제(nx). 삭제 시 해당 경로 approve_flag=0. 근거키=line_id."""
    lid = int(payload.get("line_id") or 0)
    if lid <= 0: raise HTTPException(400, "line_id 필요")
    usr = (str(payload.get("user", "")).strip() or "웹사용자")[:30]
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("SELECT route_id FROM nx.sourcing_route_line WHERE line_id=?", lid)
        r = cur.fetchone()
        if not r: raise HTTPException(404, "대상 없음")
        rid = int(r[0])
        cur.execute("DELETE FROM nx.sourcing_route_line WHERE line_id=?", lid)
        cur.execute("UPDATE nx.sourcing_route SET approve_flag=0, upd_user=?, upd_dt=getdate() WHERE route_id=?", usr, rid)
        return {"ok": True, "deleted": lid}
    finally:
        nx.close()

@router.post("/api/sourcing/child/new")
def sourcing_child_new(payload: dict = Body(...)):
    """신규 하위품번 채번(기존 복사 + 접미사). nx.item 최소등록. 반환=신규코드·품명."""
    base = str(payload.get("base_child", "")).strip()
    suffix = str(payload.get("suffix", "") or "-S1").strip()[:8]
    name = str(payload.get("name", "")).strip()[:120]
    if not base: raise HTTPException(400, "base_child(원본 하위품번) 필요")
    newc = (base + suffix)[:60]
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT ISNULL(item_name,'') FROM nx.item WHERE item_code=?", base)
        r = cur.fetchone()
        bn = name or (r[0] if r else base)
        cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", newc)
        if cur.fetchone(): return {"ok": True, "code": newc, "name": bn, "existed": True}
        cur.execute("INSERT INTO nx.item(item_code,item_name,item_type) VALUES(?,?,N'부품')", newc, bn)
        return {"ok": True, "code": newc, "name": bn, "existed": False}
    finally:
        nx.close()


# ================= 조달후보 승인관리 (개발) — 미승인(approve_flag=0·반려아님) 목록·상세·개별/일괄 승인·반려 =================
@router.get("/api/sourcing/pending")
def sourcing_pending(item: str = Query(""), gubun: str = Query(""), user: str = Query(""),
                     from_ymd: str = Query(""), to_ymd: str = Query(""), include_rejected: int = Query(0)):
    """미승인 조달후보 목록(approve_flag=0). 기본 반려제외(include_rejected=1이면 반려도 포함). 품목·구분·등록자·기간(등록일) 필터."""
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        w = ["r.approve_flag=0", "ISNULL(r.current_flag,0)=0"]; p = []
        if not include_rejected: w.append("ISNULL(r.reject_flag,0)=0")
        if item.strip(): w.append("r.item_code LIKE ?"); p.append(f"%{item.strip()}%")
        if gubun.strip(): w.append("r.gubun=?"); p.append(gubun.strip())
        if user.strip(): w.append("r.ins_user LIKE ?"); p.append(f"%{user.strip()}%")
        if from_ymd.strip(): w.append("CONVERT(varchar(10),r.ins_dt,23)>=?"); p.append(from_ymd.strip()[:10])
        if to_ymd.strip(): w.append("CONVERT(varchar(10),r.ins_dt,23)<=?"); p.append(to_ymd.strip()[:10])
        cur.execute(f"""SELECT r.route_id, r.item_code, ISNULL(r.route_no,0), ISNULL(r.route_name,''), ISNULL(r.gubun,''),
              ISNULL(r.vendor_code,''), ISNULL(r.ins_user,''), CONVERT(varchar(16),r.ins_dt,120), ISNULL(r.reject_flag,0),
              ISNULL(r.reject_reason,''), (SELECT COUNT(*) FROM nx.sourcing_route_line l WHERE l.route_id=r.route_id) nline
            FROM nx.sourcing_route r WHERE {' AND '.join(w)} ORDER BY r.ins_dt DESC, r.route_id DESC""", *p)
        cols = [c[0] for c in cur.description]; recs = cur.fetchall()
        rows = []; vcodes = set(); icodes = set()
        for rr in recs:
            d = {"route_id": int(rr[0]), "item_code": str(rr[1]).strip(), "route_no": int(rr[2]),
                 "route_name": rr[3], "gubun": rr[4], "vendor_code": str(rr[5]).strip(), "ins_user": rr[6],
                 "ins_dt": rr[7], "reject_flag": bool(rr[8]), "reject_reason": rr[9], "n_line": int(rr[10] or 0)}
            vcodes.add(d["vendor_code"]); icodes.add(d["item_code"]); rows.append(d)
        # 코드→이름(품목=live PR_M_ITEM, 공급처=CM_M_CUST)
        vmap = _custnm_map(cur, vcodes)
        imap = {}
        if icodes:
            cn = _conn(); c2 = cn.cursor()
            try:
                il = list(icodes)
                for i in range(0, len(il), 900):
                    ch = il[i:i+900]; ph = ",".join("?" * len(ch))
                    c2.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ch)
                    for r in c2.fetchall(): imap[str(r[0]).strip()] = r[1]
            finally: cn.close()
        for d in rows:
            d["item_name"] = imap.get(d["item_code"], "")
            d["vendor_name"] = vmap.get(d["vendor_code"], d["vendor_code"])
        return {"rows": rows, "cnt": len(rows), "gubun_opts": _ROUTE_GUBUN}
    finally:
        nx.close()

@router.get("/api/sourcing/route/detail")
def sourcing_route_detail(route_id: int = Query(...)):
    """승인관리 상세: 후보 헤더 + 라인(공급처 코드→이름)."""
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("""SELECT route_id,item_code,ISNULL(route_no,0),ISNULL(route_name,''),ISNULL(gubun,''),ISNULL(vendor_code,''),
              approve_flag,ISNULL(reject_flag,0),ISNULL(reject_reason,''),CONVERT(varchar(10),apply_from,23),ISNULL(note,''),ISNULL(ins_user,'')
            FROM nx.sourcing_route WHERE route_id=?""", route_id)
        h = cur.fetchone()
        if not h: raise HTTPException(404, "대상 없음")
        cur.execute("""SELECT line_id,sort_seq,ISNULL(child_item,''),ISNULL(child_name,''),qty,ISNULL(gubun,''),
              ISNULL(vendor_code,''),is_rawmat,diam,thick,len_val,ISNULL(material,''),ISNULL(spec,'')
            FROM nx.sourcing_route_line WHERE route_id=? ORDER BY sort_seq,line_id""", route_id)
        lines = []; vcodes = {str(h[5]).strip()}
        for l in cur.fetchall():
            vcodes.add(str(l[6]).strip())
            lines.append({"line_id": int(l[0]), "child_item": l[2], "child_name": l[3], "qty": float(l[4] or 0),
                          "gubun": l[5], "vendor_code": str(l[6]).strip(), "is_rawmat": int(l[7] or 0),
                          "diam": float(l[8] or 0), "thick": float(l[9] or 0), "len_val": float(l[10] or 0),
                          "material": l[11], "spec": l[12]})
        vmap = _custnm_map(cur, vcodes)
        for l in lines: l["vendor_name"] = vmap.get(l["vendor_code"], l["vendor_code"])
        hdr = {"route_id": int(h[0]), "item_code": str(h[1]).strip(), "route_no": int(h[2]), "route_name": h[3],
               "gubun": h[4], "vendor_code": str(h[5]).strip(), "vendor_name": vmap.get(str(h[5]).strip(), str(h[5]).strip()),
               "approve_flag": bool(h[6]), "reject_flag": bool(h[7]), "reject_reason": h[8], "apply_from": h[9],
               "note": h[10], "ins_user": h[11]}
        return {"header": hdr, "lines": lines}
    finally:
        nx.close()

@router.post("/api/sourcing/route/approve_bulk")
def sourcing_route_approve_bulk(payload: dict = Body(...)):
    """일괄 승인(개발). route_ids[] approve_flag=1 + reject 해제. 근거키=route_id 목록."""
    ids = [int(x) for x in (payload.get("route_ids", []) or []) if str(x).strip().isdigit()]
    usr = (str(payload.get("user", "")).strip() or "개발")[:30]
    if not ids: return {"ok": True, "approved": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        ph = ",".join("?" * len(ids))
        cur.execute(f"UPDATE nx.sourcing_route SET approve_flag=1, reject_flag=0, reject_reason=NULL, upd_user=?, upd_dt=getdate() WHERE route_id IN ({ph})", usr, *ids)
        return {"ok": True, "approved": cur.rowcount}
    finally:
        nx.close()

@router.post("/api/sourcing/route/reject")
def sourcing_route_reject(payload: dict = Body(...)):
    """반려(개발): approve_flag=0 유지 + reject_flag=1 + 사유 기록. 조달프로파일 미노출. 근거키=route_id."""
    rid = int(payload.get("route_id") or 0)
    reason = str(payload.get("reason", "")).strip()[:200]
    usr = (str(payload.get("user", "")).strip() or "개발")[:30]
    if rid <= 0: raise HTTPException(400, "route_id 필요")
    if not reason: raise HTTPException(400, "반려 사유는 필수입니다")
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("UPDATE nx.sourcing_route SET approve_flag=0, reject_flag=1, reject_reason=?, reject_user=?, reject_dt=getdate() WHERE route_id=?",
                    reason, usr, rid)
        if cur.rowcount == 0: raise HTTPException(404, "대상 없음")
        return {"ok": True, "route_id": rid}
    finally:
        nx.close()
