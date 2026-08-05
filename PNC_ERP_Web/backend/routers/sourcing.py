# -*- coding: utf-8 -*-
"""sourcing 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

from common import _d
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

_SCHEMA_READY = False   # ★속도: 스키마 멱등체크는 프로세스당 1회만(매 요청 11 메타 라운드트립 ~104ms 제거). 스키마는 런타임 불변.
def _ensure_route_tbl(cur):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
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
    # ★후보 SUB 계층(멱등) + 후보별 공정배치 테이블
    cur.execute("IF COL_LENGTH('nx.sourcing_route_line','node_kind') IS NULL ALTER TABLE nx.sourcing_route_line ADD node_kind NVARCHAR(10) NOT NULL DEFAULT 'PART'")
    cur.execute("IF COL_LENGTH('nx.sourcing_route_line','parent_line') IS NULL ALTER TABLE nx.sourcing_route_line ADD parent_line INT NULL")
    cur.execute("IF COL_LENGTH('nx.sourcing_route_line','sub_item') IS NULL ALTER TABLE nx.sourcing_route_line ADD sub_item NVARCHAR(60) NULL")
    cur.execute("""IF OBJECT_ID('nx.sourcing_route_proc','U') IS NULL CREATE TABLE nx.sourcing_route_proc(
        rp_id INT IDENTITY(1,1) PRIMARY KEY, route_id INT NOT NULL, node_item NVARCHAR(60) NOT NULL,
        proc_code NVARCHAR(10) NOT NULL, work_qty FLOAT DEFAULT 0, prod_uph FLOAT DEFAULT 0, calc_gubun NVARCHAR(4) NULL,
        ins_dt datetime DEFAULT getdate())""")
    # ★#3 후보 노드별 관경 용접점(용접ST=가공비 / 용접봉 소요량=재료). 내부원가 관경별 용접 팝업 재사용
    cur.execute("""IF OBJECT_ID('nx.sourcing_route_weld','U') IS NULL CREATE TABLE nx.sourcing_route_weld(
        rw_id INT IDENTITY(1,1) PRIMARY KEY, route_id INT NOT NULL, node_item NVARCHAR(60) NOT NULL,
        weld_item NVARCHAR(60) NULL, pipe_diam FLOAT NULL, weld_qty FLOAT DEFAULT 0,
        use_qty FLOAT DEFAULT 0, st FLOAT DEFAULT 0, ins_dt datetime DEFAULT getdate())""")
    # ★후보번호 단조증가(high-water-mark): 삭제해도 route_no 재사용 안 함. item별 마지막 채번번호.
    cur.execute("""IF OBJECT_ID('nx.route_seq','U') IS NULL CREATE TABLE nx.route_seq(
        item_code NVARCHAR(60) PRIMARY KEY, last_no INT NOT NULL DEFAULT 1)""")
    _SCHEMA_READY = True

def _approved_hwm(cur, item):
    """승인 후보 high-water-mark = max(현재 승인후보 route_no, route_seq.last_no, 1).
       ★승인된 번호만 '소진'(재사용 금지). route_seq는 승인 시점에만 bump(생성 시 아님) → 미승인은 재사용 가능."""
    cur.execute("SELECT ISNULL(MAX(route_no),0) FROM nx.sourcing_route WHERE item_code=? AND approve_flag=1", item)
    live_appr = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT last_no FROM nx.route_seq WHERE item_code=?", item)
    r = cur.fetchone(); seq = int(r[0]) if r else 0
    return max(live_appr, seq, 1)

def _peek_route_no(cur, item):
    """다음 채번될 route_no(증가 없이 조회) = 승인hwm 초과 '최소 미사용' 번호.
       미승인 후보 삭제 → 그 번호 즉시 재사용(빈자리 우선). 승인번호(≤hwm)는 소진되어 재사용 안 함. 표시(자동라벨)용."""
    hwm = _approved_hwm(cur, item)
    cur.execute("SELECT route_no FROM nx.sourcing_route WHERE item_code=?", item)
    existing = {int(x[0]) for x in cur.fetchall()}
    n = hwm + 1
    while n in existing:   # 현존 후보(미승인 포함)와 충돌 회피
        n += 1
    return n

def _next_route_no(cur, item):
    """route_no 채번 = 승인hwm 초과 최소 미사용 번호. ★생성 시 route_seq 미변경(승인 시에만 bump).
       미승인 R02 삭제→다음 생성=R02(재사용). 승인 R02(hwm=2)→이후=R03(재사용 안 함)."""
    return _peek_route_no(cur, item)

def _bump_approved_seq(cur, item, route_no):
    """승인 시 route_seq.last_no = max(기존, route_no)로 상향(승인번호 소진 확정)."""
    cur.execute("SELECT last_no FROM nx.route_seq WHERE item_code=?", item)
    r = cur.fetchone(); cur_hwm = int(r[0]) if r else 0
    new_hwm = max(cur_hwm, int(route_no or 0))
    cur.execute("""MERGE nx.route_seq AS t USING (SELECT ? AS item_code, ? AS last_no) AS s
        ON t.item_code=s.item_code
        WHEN MATCHED THEN UPDATE SET last_no=s.last_no
        WHEN NOT MATCHED THEN INSERT(item_code,last_no) VALUES(s.item_code,s.last_no);""", item, new_hwm)
    return new_hwm

def _base_gongsu(item, ymd="260630"):
    """BASE(기본BOM) 공수합 = 내부원가 proc_grid 전노드 work_qty 합. 후보 공수합 게이트 기준."""
    with _COST_LOCK:
        try: pg = _get_cost_engine().proc_grid(item, ymd)
        except Exception: pg = _get_cost_engine(fresh=True).proc_grid(item, ymd)
    return round(sum(float(v.get("wq", 0)) for v in pg.values()), 2)

_BASELINE_CACHE = {}   # ★속도: 현행 실사용 BOM(라이브RO)은 세션 중 불변 → (item)별 in-proc 캐시(TTL 120s). 조회 재호출(선택전환·생성후 재조회) 시 525ms 라이브쿼리 제거.
_BASELINE_TTL = 120.0
def _route_baseline_lines(item):
    """현행(baseline) 경로 라인 = 대상(item)의 실사용 BOM 직하위(level1). 구분: 사급/제작/매입, 공급처=IN_CUST, 치수 보강.
    ★조달후보=SUB/조달대상 단위(하단): 대상별 현행 경로1 = 그 대상의 직하위 구성/공급처.
    ★캐시: 라이브RO(불변 참조데이터) TTL 120s — 정확성 무손상(원가/공수합과 무관·표시/seed용)."""
    import time as _tt
    key = item.strip()
    hit = _BASELINE_CACHE.get(key)
    if hit and (_tt.time() - hit[0]) < _BASELINE_TTL:
        return [dict(l) for l in hit[1]]   # 방어복사(호출측 변형 격리)
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
              AND ISNULL(b.CS_CALC_EXCEPT_FLAG,'0')<>'1'
              AND b.MAT_CODE NOT LIKE 'RAC%' ORDER BY b.BOM_SEQ""", item.strip())
        out = []
        for i, r in enumerate(cur.fetchall(), 1):
            gub = "사급" if str(r.sag) == '1' else ("제작" if str(r.mk) == '1' else "매입")
            out.append({"line_id": 0, "sort_seq": i, "child_item": r.child, "child_name": r.nm, "qty": float(r.q or 0),
                        "gubun": gub, "vendor_code": str(r.cust).strip(), "vendor_name": r.custnm,
                        "is_rawmat": 1 if str(r.metal).strip() else 0, "diam": float(r.diam or 0), "thick": float(r.thick or 0),
                        "len_val": float(r.len or 0), "material": str(r.metal).strip(), "spec": "", "note": ""})
        _BASELINE_CACHE[key] = (_tt.time(), [dict(l) for l in out])
        return out
    finally:
        cn.close()

def _base_flat_lines(item, ymd="260630"):
    """BASE BOM seed = 내부원가 '평면 재료'(cost/nae flatMat와 동일: level>0·mat>0 leaf, 조립 SUB(은납 등) 해체).
       ★현행복사와 달리: 구분=품목 성격(cost_gubun='3'→제작 / 그외→매입), 공급처=공란(업체는 조달프로파일에서 배분).
       ★용접봉(RAC*) 제외 — 공정종속 자재(용접 공정에서 파생), 조달 구성라인(재료)에 미표시. node_kind=PART."""
    with _COST_LOCK:
        try: d = _get_cost_engine().naewon_nodes(item, ymd)
        except Exception: d = _get_cost_engine(fresh=True).naewon_nodes(item, ymd)
    rows = d.get("rows", []) if isinstance(d, dict) else []
    out = []; sq = 0
    for r in rows:
        if int(r.get("level", 0) or 0) <= 0: continue
        if float(r.get("mat", 0) or 0) <= 0: continue        # 재료비 계상 leaf만(=flatMat)
        code = str(r.get("code", "")).strip()
        if not code: continue
        if code.upper().startswith("RAC"): continue          # ★용접봉 제외(공정종속 — 조달 구성라인 아님)
        sq += 1
        metal = str(r.get("metal", "") or "").strip()
        # 제작/매입 판정 = 내부원가 cost_gubun: '3'(소재 절삭 제작, 예 MJU) → 제작 / '2'(매입단가) → 매입.
        # (nx.item make_type는 이 데이터에서 신뢰불가: MJU='2'·부자재='3' 역전 → cost_gubun 사용)
        gub = "제작" if str(r.get("cost_gubun", "") or "") == "3" else "매입"
        out.append({"line_id": 0, "sort_seq": sq, "child_item": code,
                    "child_name": r.get("name") or "", "qty": float(r.get("qty", 0) or 0), "gubun": gub,
                    "vendor_code": "", "vendor_name": "", "is_rawmat": 1 if metal else 0,
                    "diam": float(r.get("diam", 0) or 0), "thick": float(r.get("thick", 0) or 0), "len_val": 0.0,
                    "material": metal, "spec": str(r.get("spec", "") or ""), "note": ""})
    return out

# ★#재설계 공정 분류: 절삭(가공품별 자동귀속) vs 조립(비종속 — 노드배치). 코드셋은 cost.py와 동일.
_PROC_WELD_S = {"51", "28"}
_PROC_FASTEN_S = {"55", "52", "69", "70", "71", "72", "73", "74", "75", "76", "77", "78", "79", "80", "81", "82", "68", "23", "24", "25"}
_PROC_PACK_S = {"61", "83"}
_PROC_ETC_S = {"53", "54", "56"}   # 교정·수몰검사·에어브로잉
def _proc_is_asm(code):
    """비종속(조립) 공정 = 용접/체결/포장/검사 — 노드(ASSY/SUB)에 배치. 그외=절삭(가공품 자동귀속)."""
    return code in _PROC_WELD_S or code in _PROC_FASTEN_S or code in _PROC_PACK_S or code in _PROC_ETC_S
def _proc_group_s(code):
    if code in _PROC_WELD_S: return "용접"
    if code in _PROC_FASTEN_S: return "체결"
    if code in _PROC_PACK_S: return "포장"
    if code in _PROC_ETC_S: return "검사/기타"
    return "절삭"

def _panel_cut_asm(item, ymd="260630"):
    """★SUB재구성·공정배치 패널 데이터 = proc_grid 동일 전개(공수합=BASE 보존)에 '노드 귀속'을 유지.
       반환: (part_cut{부품:{proc:wq}}=절삭 자동귀속, asm{proc:wq}=조립 pool(비종속·노드배치), base_g).
       ★Σ(part_cut)+Σ(asm) == base_gongsu(proc_grid 총합) diff0."""
    ym = "20" + ymd[:4]
    with _COST_LOCK:
        eng = _get_cost_engine()
        try: _ = eng.labor_rate(ym)
        except Exception: eng = _get_cost_engine(fresh=True)
        part_cut = {}; asm = {}
        def walk(node, cum_ea, parent, seen):
            info = eng._load_item(node); cg0 = info['cost_gubun']
            db_item = parent if info['silver'] else ''
            for proc, wq, uph, cg, pit in eng._procs(node):
                if pit != db_item or wq == 0: continue
                w = wq * cum_ea
                if _proc_is_asm(str(proc)):
                    asm[str(proc)] = asm.get(str(proc), 0.0) + w
                else:
                    d = part_cut.setdefault(node, {}); d[str(proc)] = d.get(str(proc), 0.0) + w
            expandable = bool(eng._expandable_nae(node, seen)) if cg0 != '3' else False
            if expandable:
                for c, qty, cx, f, t, lx in eng.lines(node):
                    if cx: continue
                    cinfo = eng._load_item(c)
                    ea = qty if cinfo['unit'] == 'EA' else 1.0
                    walk(c, cum_ea * ea, node, seen | {node})
        walk(item, 1.0, '', set())
    part_cut = {k: {p: round(v, 3) for p, v in d.items()} for k, d in part_cut.items()}
    asm = {p: round(v, 3) for p, v in asm.items()}
    base_g = round(sum(sum(d.values()) for d in part_cut.values()) + sum(asm.values()), 2)
    return part_cut, asm, base_g

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
        next_no = _peek_route_no(cur, item)   # 단조증가 다음 번호(자동라벨 표시용)
        return {"item": item, "item_name": nm, "gubun_opts": _ROUTE_GUBUN, "line_gubun_opts": _LINE_GUBUN,
                "routes": routes, "next_route_no": next_no}
    finally:
        nx.close()

def _route_hdr_errors(p):
    # ★공급처는 후보 헤더에서 받지 않음(업체=조달프로파일에서 배분, 2계층) → vendor 필수검증 제거.
    errs = []
    if not str(p.get("gubun", "")).strip(): errs.append("구분은 필수입니다")
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
        rno = _next_route_no(cur, item)   # ★단조증가 채번(삭제해도 재사용 안 함)
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
        src_kind = str(p.get("source", "")).strip()   # 'blank'=빈 후보 · 'base'=BASE BOM 평면 seed · (그외=기존 규칙)
        # 원본 라인 확보
        if src_kind == 'blank':   # ★빈 상태(수동 구성 시작)
            src_hdr = {"route_name": "빈 후보", "vendor_code": "", "gubun": "자체", "apply_from": None, "note": "빈 상태(수동 구성)"}
            src_lines = []
        elif src_kind == 'base':   # ★BASE BOM(내부원가 평면 재료·조립SUB 해체) seed → SUB 재구성 시작. ≠현행복사
            src_hdr = {"route_name": "BASE BOM", "vendor_code": "", "gubun": "자체", "apply_from": None,
                       "note": "BASE BOM(내부원가 평면 재료·SUB 해체) 가져오기 — 구분=품목성격·공급처 공란"}
            ymd = str(p.get("ymd", "260630")).strip() or "260630"
            bl = _base_flat_lines(item, ymd)
            src_lines = [[l["sort_seq"], l["child_item"], l["child_name"], l["qty"], l["gubun"], l["vendor_code"],
                         l["is_rawmat"], l["diam"], l["thick"], l["len_val"], l["material"], l["spec"], l["note"]] for l in bl]
        elif src_item:   # ★특정 품번의 현행 BOM을 seed로
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
        rno = _next_route_no(cur, item)   # ★단조증가 채번(삭제해도 재사용 안 함)
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
        # ★BASE 복사: 조립 공정(비종속=용접·지그·교정·부품부착·포장)을 ASSY 노드에 시드 → 신규 후보 공수합=BASE로 시작
        # (절삭은 part_cut 자동귀속이라 시드 불필요). 이후 사용자가 SUB로 재배치·차감.
        seeded_asm = 0
        if src_kind == 'base':
            try:
                _pc, _asm, _bg = _panel_cut_asm(item, ymd)
                for pc_code, wq in (_asm or {}).items():
                    if wq and float(wq) != 0:
                        cur.execute("""INSERT INTO nx.sourcing_route_proc(route_id,node_item,proc_code,work_qty,prod_uph,calc_gubun)
                            VALUES(?,?,?,?,0,'')""", nid, item, str(pc_code).strip()[:10], float(wq))
                        seeded_asm += 1
            except Exception:
                pass
        nx.commit()
        return {"ok": True, "route_id": nid, "route_no": rno, "lines": len(src_lines),
                "copied_children": new_children, "suffix": suffix, "seeded_asm": seeded_asm}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()

@router.post("/api/sourcing/route/delete")
def sourcing_route_delete(payload: dict = Body(...)):
    """경로 삭제(헤더+라인+공정+용접). 현행 baseline(route_id=0)은 삭제 불가.
       ★삭제 가드: 조달프로파일(nx.sourcing_profile)이 이 route_id를 업체매핑 중이면 거부(매핑 해제 후 삭제).
       ★번호 단조증가: route_no는 삭제해도 route_seq에 high-water 유지 → 재사용 안 함. 근거키=route_id."""
    rid = int(payload.get("route_id") or 0)
    if rid <= 0: raise HTTPException(400, "현행(기준선)은 삭제할 수 없습니다 — 대안 경로만 삭제 가능")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("SELECT current_flag FROM nx.sourcing_route WHERE route_id=?", rid)
        r = cur.fetchone()
        if not r: raise HTTPException(404, "대상 없음")
        if int(r[0] or 0) == 1:
            nx.rollback(); return {"ok": False, "guard": "CURRENT", "msg": "현행(실사용) 후보는 삭제할 수 없습니다."}
        # 삭제 가드: 조달프로파일에서 사용(업체 매핑) 중이면 거부
        cur.execute("SELECT COUNT(*) FROM nx.sourcing_profile WHERE route_id=?", rid)
        nprof = int(cur.fetchone()[0] or 0)
        if nprof > 0:
            nx.rollback()
            return {"ok": False, "guard": "IN_USE", "profiles": nprof,
                    "msg": f"조달 프로파일에서 사용 중({nprof}개 업체 매핑) — 매핑 해제 후 삭제하세요."}
        cur.execute("DELETE FROM nx.sourcing_route_weld WHERE route_id=?", rid)
        cur.execute("DELETE FROM nx.sourcing_route_proc WHERE route_id=?", rid)
        cur.execute("DELETE FROM nx.sourcing_route_line WHERE route_id=?", rid)
        cur.execute("DELETE FROM nx.sourcing_route WHERE route_id=?", rid)
        nx.commit()
        return {"ok": True, "deleted": rid}   # route_no는 route_seq(high-water)에 남아 재사용 안 됨
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
        cur.execute("SELECT item_code, route_no FROM nx.sourcing_route WHERE route_id=?", rid)
        r0 = cur.fetchone()
        if not r0: raise HTTPException(404, "대상 없음")
        cur.execute("UPDATE nx.sourcing_route SET approve_flag=?, upd_user=?, upd_dt=getdate() WHERE route_id=?", ap, usr, rid)
        if ap == 1:   # ★승인 시에만 route_seq high-water bump(그 번호 소진→재사용 금지). 미승인은 미변경(삭제 시 재사용).
            _bump_approved_seq(cur, str(r0[0]).strip(), int(r0[1] or 0))
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
              ISNULL(vendor_code,''),is_rawmat,diam,thick,len_val,ISNULL(material,''),ISNULL(spec,''),
              ISNULL(node_kind,'PART'),parent_line,ISNULL(sub_item,'')
            FROM nx.sourcing_route_line WHERE route_id=? ORDER BY sort_seq,line_id""", route_id)
        lines = []; vcodes = {str(h[5]).strip()}
        for l in cur.fetchall():
            vcodes.add(str(l[6]).strip())
            lines.append({"line_id": int(l[0]), "child_item": l[2], "child_name": l[3], "qty": float(l[4] or 0),
                          "gubun": l[5], "vendor_code": str(l[6]).strip(), "is_rawmat": int(l[7] or 0),
                          "diam": float(l[8] or 0), "thick": float(l[9] or 0), "len_val": float(l[10] or 0),
                          "material": l[11], "spec": l[12],
                          "node_kind": str(l[13] or 'PART'), "parent_line": (int(l[14]) if l[14] is not None else None), "sub_item": str(l[15] or '')})
        vmap = _custnm_map(cur, vcodes)
        for l in lines: l["vendor_name"] = vmap.get(l["vendor_code"], l["vendor_code"])
        # 후보별 공정배치(route_proc) + BASE 공수합(게이트 기준)
        cur.execute("SELECT node_item,proc_code,ISNULL(work_qty,0),ISNULL(prod_uph,0),ISNULL(calc_gubun,'') FROM nx.sourcing_route_proc WHERE route_id=?", route_id)
        procs = [{"node_item": str(r[0]).strip(), "proc_code": str(r[1]).strip(), "work_qty": float(r[2] or 0),
                  "prod_uph": float(r[3] or 0), "calc_gubun": str(r[4] or '')} for r in cur.fetchall()]
        hdr = {"route_id": int(h[0]), "item_code": str(h[1]).strip(), "route_no": int(h[2]), "route_name": h[3],
               "gubun": h[4], "vendor_code": str(h[5]).strip(), "vendor_name": vmap.get(str(h[5]).strip(), str(h[5]).strip()),
               "approve_flag": bool(h[6]), "reject_flag": bool(h[7]), "reject_reason": h[8], "apply_from": h[9],
               "note": h[10], "ins_user": h[11]}
        base_g = None; base_procs = []
        try:
            with _COST_LOCK:
                try: pg = _get_cost_engine().proc_grid(str(h[1]).strip(), "260630")
                except Exception: pg = _get_cost_engine(fresh=True).proc_grid(str(h[1]).strip(), "260630")
            base_procs = [{"proc_code": k, "work_qty": round(float(v.get("wq", 0)), 2), "uph": float(v.get("uph", 0)), "cg": str(v.get("cg", ""))}
                          for k, v in pg.items() if float(v.get("wq", 0)) > 0]
            base_procs.sort(key=lambda x: x["proc_code"])
            base_g = round(sum(p["work_qty"] for p in base_procs), 2)
        except Exception:
            base_g = None
        cand_g = round(sum(p["work_qty"] for p in procs), 2)
        # #3 노드별 관경 용접점(용접ST=가공비 / 용접봉 소요량=재료)
        cur.execute("SELECT node_item,ISNULL(weld_item,''),ISNULL(pipe_diam,0),ISNULL(weld_qty,0),ISNULL(use_qty,0),ISNULL(st,0) FROM nx.sourcing_route_weld WHERE route_id=? ORDER BY node_item,rw_id", route_id)
        welds = [{"node_item": str(r[0]).strip(), "weld_item": str(r[1]).strip(), "pipe_diam": float(r[2] or 0),
                  "weld_qty": float(r[3] or 0), "use_qty": float(r[4] or 0), "st": float(r[5] or 0)} for r in cur.fetchall()]
        # ★재설계 패널: 절삭(부품별 자동귀속) + 조립(비종속 pool·노드배치). Σ=base_gongsu diff0.
        part_cut = {}; asm_procs = []
        try:
            pc, asm, bg2 = _panel_cut_asm(str(h[1]).strip(), "260630")
            pcodes = set(asm.keys()) | {p for d in pc.values() for p in d.keys()}
            pnames = {}
            if pcodes:
                cur2 = _conn().cursor()
                try:
                    lst = sorted(pcodes)
                    for i in range(0, len(lst), 900):
                        ch = lst[i:i + 900]; ph = ",".join("?" * len(ch))
                        cur2.execute(f"SELECT PROC_CODE, ISNULL(PROC_DESC,'') FROM CS_M_PROC WHERE PROC_CODE IN ({ph})", *ch)
                        for r in cur2.fetchall(): pnames[str(r[0]).strip()] = str(r[1]).strip()
                finally: cur2.close()
            part_cut = {pt: [{"proc_code": c, "name": pnames.get(c, c), "group": _proc_group_s(c), "wq": w}
                             for c, w in sorted(d.items()) if w > 0] for pt, d in pc.items()}
            part_cut = {pt: v for pt, v in part_cut.items() if v}   # wq>0 있는 부품만
            asm_procs = [{"proc_code": c, "name": pnames.get(c, c), "group": _proc_group_s(c), "wq": w}
                         for c, w in sorted(asm.items()) if w > 0]
            if base_g is None: base_g = bg2
        except Exception:
            pass
        return {"header": hdr, "lines": lines, "procs": procs, "base_procs": base_procs, "welds": welds,
                "part_cut": part_cut, "asm_procs": asm_procs,
                "base_gongsu": base_g, "cand_gongsu": cand_g, "gate_ok": (base_g is None or abs(cand_g - base_g) < 0.5 or cand_g == 0)}
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

# ===================== 후보 SUB 재구성(드래그드롭·공정재배치) =====================
@router.post("/api/sourcing/sub/create")
def sourcing_sub_create(payload: dict = Body(...)):
    """후보 안에서 선택 부품(line_ids)을 신규 SUB로 묶기. SUB 채번(base_child+suffix)→nx.item 최소등록,
       SUB행(node_kind='SUB') 생성 + 선택부품 parent_line=SUB.line_id. 근거키=route_id·line_ids. 승인 리셋."""
    rid = int(payload.get("route_id") or 0)
    line_ids = [int(x) for x in (payload.get("line_ids", []) or []) if str(x).strip().isdigit()]
    base_child = str(payload.get("base_child", "")).strip()
    suffix = (str(payload.get("suffix", "") or "").strip())[:12]   # 빈=자동 _S{nn}, 명시(-은납 등)=공정약칭 계승
    subname = str(payload.get("name", "")).strip()[:120]
    gubun = str(payload.get("gubun", "자체")).strip()[:20]
    if rid <= 0 or not line_ids: raise HTTPException(400, "route_id·line_ids 필요")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        # ★SUB 채번: 명시 suffix 없으면 자동 _S{nn}(언더스코어·제로패딩2) — nx.item+라이브 _S\d 충돌검사→다음번호
        if not suffix or suffix.upper() in ('_S', 'S', 'AUTO'):
            mx = 0; import re as _re3
            cur.execute("SELECT item_code FROM nx.item WHERE item_code LIKE ? ESCAPE '!'", base_child + '!_S%')
            rowsn = [str(r[0]).strip() for r in cur.fetchall()]
            try:
                lc = _conn(); lcur = lc.cursor()
                lcur.execute("SELECT ITEM_CODE FROM PR_M_ITEM WHERE ITEM_CODE LIKE ? ESCAPE '!'", base_child + '!_S%')
                rowsn += [str(r[0]).strip() for r in lcur.fetchall()]; lc.close()
            except Exception: pass
            for cd in rowsn:
                m = _re3.search(r'_S0*(\d+)$', cd)
                if m: mx = max(mx, int(m.group(1)))
            suffix = f"_S{mx+1:02d}"
        subcode = ((base_child + suffix)[:60]) if base_child else None
        if subcode:
            cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", subcode)
            if not cur.fetchone():
                cur.execute("INSERT INTO nx.item(item_code,item_name,item_type) VALUES(?,?,N'제품')", subcode, subname or subcode)
        cur.execute("SELECT ISNULL(MAX(sort_seq),0)+1 FROM nx.sourcing_route_line WHERE route_id=?", rid); sq = int(cur.fetchone()[0])
        cur.execute("""INSERT INTO nx.sourcing_route_line(route_id,sort_seq,child_item,child_name,qty,gubun,node_kind,sub_item)
            OUTPUT INSERTED.line_id VALUES(?,?,?,?,1,?,'SUB',?)""", rid, sq, subcode, (subname or subcode), gubun, subcode)
        subline = int(cur.fetchone()[0])
        ph = ",".join("?" * len(line_ids))
        cur.execute(f"UPDATE nx.sourcing_route_line SET parent_line=?, node_kind='PART' WHERE route_id=? AND line_id IN ({ph})", subline, rid, *line_ids)
        moved = cur.rowcount
        cur.execute("UPDATE nx.sourcing_route SET approve_flag=0, upd_dt=getdate() WHERE route_id=?", rid)
        nx.commit()
        return {"ok": True, "sub_line": subline, "sub_item": subcode, "moved": moved}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()

@router.post("/api/sourcing/sub/dissolve")
def sourcing_sub_dissolve(payload: dict = Body(...)):
    """SUB 해제 — 하위부품 parent_line=NULL 복귀(평면), SUB행 삭제. SUB 노드에 붙은 비종속 공정/용접(node_item=SUB코드)은
       ASSY(대상품번)로 이관해 공수합 보존(절삭은 node_item=부품코드라 부품 따라 자동유지). 근거키=route_id·sub_line. 승인 리셋."""
    rid = int(payload.get("route_id") or 0); subline = int(payload.get("sub_line") or 0)
    if rid <= 0 or subline <= 0: raise HTTPException(400, "route_id·sub_line 필요")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        # SUB 아이템코드 + ASSY(대상품번) 확보(공정 이관용)
        cur.execute("SELECT ISNULL(sub_item,child_item) FROM nx.sourcing_route_line WHERE route_id=? AND line_id=? AND node_kind='SUB'", rid, subline)
        _r = cur.fetchone(); sub_code = (str(_r[0]).strip() if _r and _r[0] is not None else '')
        cur.execute("SELECT item_code FROM nx.sourcing_route WHERE route_id=?", rid)
        _r2 = cur.fetchone(); assy = (str(_r2[0]).strip() if _r2 and _r2[0] is not None else '')
        # 하위부품 평면복귀
        cur.execute("UPDATE nx.sourcing_route_line SET parent_line=NULL WHERE route_id=? AND parent_line=?", rid, subline)
        freed = cur.rowcount
        # SUB 노드 비종속 공정/용접 → ASSY 이관(공수합 보존). 절삭(node_item=부품코드)은 대상 아님.
        moved_proc = moved_weld = 0
        if sub_code and assy and sub_code != assy:
            cur.execute("UPDATE nx.sourcing_route_proc SET node_item=? WHERE route_id=? AND node_item=?", assy, rid, sub_code)
            moved_proc = cur.rowcount
            cur.execute("UPDATE nx.sourcing_route_weld SET node_item=? WHERE route_id=? AND node_item=?", assy, rid, sub_code)
            moved_weld = cur.rowcount
        cur.execute("DELETE FROM nx.sourcing_route_line WHERE route_id=? AND line_id=? AND node_kind='SUB'", rid, subline)
        cur.execute("UPDATE nx.sourcing_route SET approve_flag=0, upd_dt=getdate() WHERE route_id=?", rid)
        nx.commit()
        return {"ok": True, "freed": freed, "moved_proc": moved_proc, "moved_weld": moved_weld}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()

@router.post("/api/sourcing/part/assign")
def sourcing_part_assign(payload: dict = Body(...)):
    """부품 라인을 SUB로 이동/평면복귀(드래그드롭). sub_line>0=해당 SUB 하위로, 0=평면(parent_line=NULL).
       근거키=route_id·line_ids. 재료(구성)만 이동, 공정(route_proc)·공수합 불변. 승인 리셋."""
    rid = int(payload.get("route_id") or 0)
    sub_line = int(payload.get("sub_line") or 0)
    line_ids = [int(x) for x in (payload.get("line_ids", []) or []) if str(x).strip().isdigit()]
    if rid <= 0 or not line_ids: raise HTTPException(400, "route_id·line_ids 필요")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        if sub_line > 0:   # 대상 SUB 유효성(같은 route·SUB)
            cur.execute("SELECT 1 FROM nx.sourcing_route_line WHERE route_id=? AND line_id=? AND node_kind='SUB'", rid, sub_line)
            if not cur.fetchone(): raise HTTPException(404, "대상 SUB 없음")
            if sub_line in line_ids: raise HTTPException(400, "SUB 자신은 이동 불가")
        ph = ",".join("?" * len(line_ids))
        cur.execute(f"UPDATE nx.sourcing_route_line SET parent_line=?, node_kind='PART' WHERE route_id=? AND line_id IN ({ph}) AND node_kind<>'SUB'",
                    (sub_line or None), rid, *line_ids)
        moved = cur.rowcount
        cur.execute("UPDATE nx.sourcing_route SET approve_flag=0, upd_dt=getdate() WHERE route_id=?", rid)
        nx.commit()
        return {"ok": True, "moved": moved, "to": (sub_line or "평면")}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()

@router.post("/api/sourcing/proc/save")
def sourcing_proc_save(payload: dict = Body(...)):
    """후보별 공정배치 저장(nx.sourcing_route_proc 전체교체). ★게이트: Σ(후보 work_qty 전노드) == BASE 공수합(내부원가 proc_grid) diff0.
       불일치 시 저장거부(공수합 보존 강제). BASE nx.routing은 불변. 근거키=route_id. 승인 리셋."""
    rid = int(payload.get("route_id") or 0)
    item = str(payload.get("item_code", "")).strip()
    ymd = str(payload.get("ymd", "260630")).strip() or "260630"
    procs = payload.get("procs", []) or []
    if rid <= 0 or not item: raise HTTPException(400, "route_id·item_code 필요")
    csum = round(sum(float(p.get("work_qty") or 0) for p in procs), 2)
    try: base = _base_gongsu(item, ymd)
    except Exception as e: raise HTTPException(500, f"BASE 공수합 계산오류: {e}")
    if abs(csum - base) > 0.5:
        return {"ok": False, "gate": "FAIL", "cand_gongsu": csum, "base_gongsu": base,
                "msg": f"공수합 불일치 — 후보 {csum} ≠ BASE {base}. 저장 거부(공수합=BASE 보존 필수)."}
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("SELECT 1 FROM nx.sourcing_route WHERE route_id=?", rid)
        if not cur.fetchone(): raise HTTPException(404, "route 없음")
        cur.execute("DELETE FROM nx.sourcing_route_proc WHERE route_id=?", rid)
        n = 0
        for p in procs:
            wq = float(p.get("work_qty") or 0)
            if wq <= 0: continue
            cur.execute("""INSERT INTO nx.sourcing_route_proc(route_id,node_item,proc_code,work_qty,prod_uph,calc_gubun)
                VALUES(?,?,?,?,?,?)""", rid, str(p.get("node_item", "")).strip()[:60], str(p.get("proc_code", "")).strip()[:10],
                wq, float(p.get("prod_uph") or 0), (str(p.get("calc_gubun", "") or "")[:4]))
            n += 1
        cur.execute("UPDATE nx.sourcing_route SET approve_flag=0, upd_dt=getdate() WHERE route_id=?", rid)
        nx.commit()
        return {"ok": True, "gate": "PASS", "cand_gongsu": csum, "base_gongsu": base, "saved": n}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()

# ============ #4 후보(구조) ↔ 업체(조달프로파일) 매핑: 2계층 =============
# 후보 = 공정/구조 단위(sourcing_route). 업체 = 승인후보에 nx.sourcing_profile(route_id)로 vendor·배분%·유효기간 매핑.
@router.get("/api/sourcing/vendors")
def sourcing_vendors(q: str = Query("")):
    """업체 매핑용 거래처 픽커(외주·매입). nx.cust에서 code+name(간소)."""
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["(outside_flag=1 OR in_flag=1)"]; p = []
        if q.strip(): w.append("(cust_code LIKE ? OR cust_name LIKE ?)"); p += [f"%{q.strip()}%"] * 2
        cur.execute(f"SELECT TOP 50 cust_code,cust_name,outside_flag,in_flag FROM nx.cust WHERE {' AND '.join(w)} AND use_flag=1 ORDER BY cust_name", *p)
        return {"rows": [{"code": str(r[0]).strip(), "name": str(r[1] or "").strip(),
                          "role": ("외주" if r[2] else "") + ("·매입" if r[3] else "")} for r in cur.fetchall()]}
    finally:
        nx.close()

# ★계획단가 컬럼(후보/계획 단가 — 정산 아님): sourcing 레이어(nx)에만 저장. 정산 마스터(PR_M_ITEM_COST)는 미접근.
#   buy_price=업체별 매입단가(계획), sagub_price=업체별 사급단가(계획). 후보 원가비교(R01 vs R02)용 참조값.
_PROF_PRICE_READY = False
def _ensure_profile_price_cols(cur):
    """nx.sourcing_profile 계획단가 컬럼 멱등 추가(프로세스당 1회). 근거키=route_id·profile_id 스코프 upsert에서 사용."""
    global _PROF_PRICE_READY
    if _PROF_PRICE_READY:
        return
    cur.execute("IF COL_LENGTH('nx.sourcing_profile','buy_price') IS NULL ALTER TABLE nx.sourcing_profile ADD buy_price FLOAT NULL")
    cur.execute("IF COL_LENGTH('nx.sourcing_profile','sagub_price') IS NULL ALTER TABLE nx.sourcing_profile ADD sagub_price FLOAT NULL")
    _PROF_PRICE_READY = True

@router.get("/api/sourcing/profile/list")
def sourcing_profile_list(route_id: int = Query(0)):
    """승인후보(route_id)에 매핑된 업체(조달프로파일) 목록. route 헤더(승인여부·품번) 동봉.
       업체별 buy_price(매입단가·계획)/sagub_price(사급단가·계획) 포함 — 후보/계획 단가(정산 아님, sourcing 레이어 전용)."""
    if route_id <= 0: raise HTTPException(400, "route_id 필요")
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_profile_price_cols(cur)
        cur.execute("SELECT item_code, route_no, route_name, approve_flag, current_flag FROM nx.sourcing_route WHERE route_id=?", route_id)
        h = cur.fetchone()
        if not h: raise HTTPException(404, "route 없음")
        hdr = {"route_id": route_id, "item_code": str(h[0]).strip(), "route_no": h[1],
               "route_name": str(h[2] or "").strip(), "approve_flag": int(h[3] or 0), "current_flag": int(h[4] or 0)}
        cur.execute("""SELECT p.profile_id,p.vendor_code,ISNULL(c.cust_name,'') vn,p.supply_gubun,p.lme_flag,
              CONVERT(varchar(10),p.apply_from,23),CONVERT(varchar(10),p.apply_to,23),p.is_active,p.is_internal,p.alloc_ratio,p.priority,
              p.buy_price,p.sagub_price
            FROM nx.sourcing_profile p LEFT JOIN nx.cust c ON c.cust_code=p.vendor_code
            WHERE p.route_id=? ORDER BY p.priority, p.profile_id""", route_id)
        rows = [{"profile_id": r[0], "vendor_code": str(r[1] or "").strip(), "vendor_name": str(r[2] or "").strip(),
                 "supply_gubun": str(r[3] or "").strip(), "lme_flag": int(r[4] or 0),
                 "apply_from": r[5], "apply_to": r[6], "is_active": int(r[7] or 0),
                 "is_internal": int(r[8] or 0), "alloc_ratio": (float(r[9]) if r[9] is not None else None),
                 "priority": r[10],
                 "buy_price": (float(r[11]) if r[11] is not None else None),
                 "sagub_price": (float(r[12]) if r[12] is not None else None)} for r in cur.fetchall()]
        # 활성·배분 합(참고)
        act = [(x["apply_from"] or "2000-01-01", x["apply_to"], x["alloc_ratio"]) for x in rows
               if x["is_active"] and not x["is_internal"] and x["alloc_ratio"] is not None]
        alloc_errs = _validate_alloc(act) if act else []
        return {"header": hdr, "rows": rows, "alloc_ok": (len(alloc_errs) == 0), "alloc_errs": alloc_errs}
    finally:
        nx.close()

@router.post("/api/sourcing/profile/save")
def sourcing_profile_save(payload: dict = Body(...)):
    """승인후보(route_id)에 업체 매핑 저장(upsert+delete). ★게이트: route는 승인(approve_flag=1)이어야 매핑 가능.
       활성·배분% 입력행은 유효기간 겹치는 구간마다 배분합=100% 강제(_validate_alloc). 위반시 미기록.
       근거키=route_id·profile_id. rows[] {profile_id(0=신규),vendor_code,supply_gubun,lme_flag,apply_from,apply_to,is_active,is_internal,alloc_ratio,priority,_delete}."""
    rid = int(payload.get("route_id") or 0)
    rows = payload.get("rows", []) or []
    if rid <= 0: raise HTTPException(400, "route_id 필요")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        _ensure_profile_price_cols(cur)
        cur.execute("SELECT item_code, approve_flag FROM nx.sourcing_route WHERE route_id=?", rid)
        h = cur.fetchone()
        if not h: raise HTTPException(404, "route 없음")
        item = str(h[0]).strip()
        if int(h[1] or 0) != 1:
            return {"ok": False, "gate": "NOT_APPROVED", "msg": "승인된 후보만 업체 매핑 가능(먼저 승인하세요)."}
        # 정규화 + 배분검증(활성·비내부·배분% 입력 대상)
        _pfloat = lambda v: (float(v) if (v not in (None, "", "null")) else None)   # 계획단가 파싱(공란=NULL)
        norm = []; act = []
        for r in rows:
            if r.get("_delete"):
                pid = int(r.get("profile_id") or 0)
                if pid > 0: norm.append(("del", pid, None))
                continue
            vc = str(r.get("vendor_code", "")).strip()
            if not vc: continue  # 업체 없는 행 스킵
            pid = int(r.get("profile_id") or 0)
            sg = (str(r.get("supply_gubun", "") or "2")[:4]) or "2"
            lme = 1 if r.get("lme_flag") else 0
            af = _d(r.get("apply_from")) or "2000-01-01"
            at = _d(r.get("apply_to"))
            iact = 1 if r.get("is_active") else 0
            iint = 1 if r.get("is_internal") else 0
            ratio = r.get("alloc_ratio"); ratio = float(ratio) if (ratio not in (None, "", "null")) else None
            prio = r.get("priority"); prio = int(prio) if (prio not in (None, "", "null")) else None
            bp = _pfloat(r.get("buy_price"))       # 매입단가(계획·정산 아님)
            sp = _pfloat(r.get("sagub_price"))     # 사급단가(계획·정산 아님)
            norm.append((pid, vc, sg, lme, af, at, iact, iint, ratio, prio, bp, sp))
            if iact and not iint and ratio is not None:
                act.append((af, at, ratio))
        errs = _validate_alloc(act) if act else []
        if errs:
            nx.rollback()
            return {"ok": False, "gate": "ALLOC", "errors": list(dict.fromkeys(errs))}
        ins = upd = dele = 0
        for rec in norm:
            if rec[0] == "del":
                cur.execute("DELETE FROM nx.sourcing_profile WHERE profile_id=? AND route_id=?", rec[1], rid)
                dele += cur.rowcount; continue
            (pid, vc, sg, lme, af, at, iact, iint, ratio, prio, bp, sp) = rec
            if pid > 0:
                cur.execute("""UPDATE nx.sourcing_profile SET vendor_code=?,supply_gubun=?,lme_flag=?,apply_from=?,apply_to=?,
                      is_active=?,is_internal=?,alloc_ratio=?,priority=?,buy_price=?,sagub_price=? WHERE profile_id=? AND route_id=?""",
                    vc, sg, lme, af, at, iact, iint, ratio, prio, bp, sp, pid, rid)
                upd += cur.rowcount
            else:
                cur.execute("""INSERT INTO nx.sourcing_profile(item_code,profile_name,supply_gubun,vendor_code,lme_flag,
                      apply_from,apply_to,is_active,is_internal,alloc_ratio,priority,route_id,buy_price,sagub_price)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    item, (vc + " 매핑")[:100], sg, vc, lme, af, at, iact, iint, ratio, prio, rid, bp, sp)
                ins += 1
        nx.commit()
        return {"ok": True, "ins": ins, "upd": upd, "del": dele}
    except HTTPException:
        nx.rollback(); raise
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()

@router.get("/api/sourcing/plan_price")
def sourcing_plan_price(item: str = Query(...)):
    """★품목 단가 관리(조회) 연동 — 이 품목의 조달후보 업체별 **계획단가**(nx.sourcing_profile buy_price/sagub_price) 읽기전용.
       정산 매입/판매 단가(PR_M_ITEM_COST 마스터)는 미접근 — 여기 값은 후보 원가비교용 '후보/계획 단가(정산 아님)'.
       반환: routes[{route_id,route_no,route_name,gubun,approve_flag,current_flag,route_alloc{...},vendors[{vendor,alloc,buy_price,sagub_price,...}]}]."""
    item = item.strip()
    if not item: raise HTTPException(400, "item 필요")
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        _ensure_profile_price_cols(cur)
        _ensure_route_alloc_tbl(cur)
        # 이 품목의 저장된 후보(nx.sourcing_route) — 계획단가가 붙는 대상. baseline(합성)은 업체매핑 불가라 제외.
        cur.execute("""SELECT route_id, route_no, ISNULL(route_name,''), ISNULL(gubun,''), approve_flag, current_flag
            FROM nx.sourcing_route WHERE item_code=? ORDER BY route_no""", item)
        hdrs = [{"route_id": int(r[0]), "route_no": int(r[1]), "route_name": r[2], "gubun": r[3],
                 "approve_flag": bool(r[4]), "current_flag": bool(r[5])} for r in cur.fetchall()]
        # route 단위 배분(참고)
        cur.execute("""SELECT route_id, CONVERT(varchar(10),apply_from,23), CONVERT(varchar(10),apply_to,23), is_active, alloc_ratio
            FROM nx.route_alloc WHERE item_code=?""", item)
        ralloc = {int(r[0]): {"apply_from": r[1], "apply_to": r[2],
                              "is_active": (bool(r[3]) if r[3] is not None else None),
                              "alloc_ratio": (float(r[4]) if r[4] is not None else None)} for r in cur.fetchall()}
        # 업체별 계획단가
        rids = [h["route_id"] for h in hdrs]
        vend = {}; vcodes = set()
        if rids:
            ph = ",".join("?" * len(rids))
            cur.execute(f"""SELECT route_id, vendor_code, supply_gubun, is_active, alloc_ratio,
                  CONVERT(varchar(10),apply_from,23), CONVERT(varchar(10),apply_to,23), buy_price, sagub_price, lme_flag
                FROM nx.sourcing_profile WHERE route_id IN ({ph}) ORDER BY priority, profile_id""", *rids)
            for r in cur.fetchall():
                rid = int(r[0]); vc = str(r[1] or "").strip(); vcodes.add(vc)
                vend.setdefault(rid, []).append({"vendor_code": vc, "supply_gubun": str(r[2] or "").strip(),
                    "is_active": int(r[3] or 0), "alloc_ratio": (float(r[4]) if r[4] is not None else None),
                    "apply_from": r[5], "apply_to": r[6],
                    "buy_price": (float(r[7]) if r[7] is not None else None),
                    "sagub_price": (float(r[8]) if r[8] is not None else None), "lme_flag": int(r[9] or 0)})
        vmap = _custnm_map(cur, vcodes)
        out = []; n_vend = 0
        for h in hdrs:
            vs = vend.get(h["route_id"], [])
            for v in vs: v["vendor_name"] = vmap.get(v["vendor_code"], v["vendor_code"])
            n_vend += len(vs)
            out.append({**h, "route_alloc": ralloc.get(h["route_id"]), "vendors": vs})
        return {"item": item, "routes": out, "n_route": len(out), "n_vendor": n_vend,
                "note": "후보/계획 단가(정산 아님) — sourcing 레이어(nx.sourcing_profile). 정산 매입/판매 단가는 별도 마스터(마감 때만 수정)."}
    finally:
        nx.close()

@router.post("/api/sourcing/weld/save")
def sourcing_weld_save(payload: dict = Body(...)):
    """#3 후보 노드별 관경 용접점 저장(내부원가 관경별 용접 팝업 재사용). 스코프=(route_id,node_item) 전체교체(멱등).
       소요량=Σ(std_use[관경]×횟수)×loss(기본1.5)=용접봉 재료 · 내부ST=Σ(std_st×횟수)=용접 가공비.
       ★공수합=BASE는 proc/save 게이트가 최종보증(여기선 ST 산출만·proc_grid 미변경). 근거키=route_id·node_item. 승인 리셋.
       payload {route_id, node_item, loss_factor?, rows:[{weld_item,pipe_diam,weld_qty}]}."""
    rid = int(payload.get("route_id") or 0)
    node = str(payload.get("node_item", "")).strip()
    loss = float(payload.get("loss_factor") or 1.5)
    rows = payload.get("rows", []) or []
    if rid <= 0 or not node: raise HTTPException(400, "route_id·node_item 필요")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("SELECT 1 FROM nx.sourcing_route WHERE route_id=?", rid)
        if not cur.fetchone(): raise HTTPException(404, "route 없음")
        # 관경 표준(대표 MIN='01')
        cur.execute("SELECT pipe_diam,MIN(std_use_qty),MIN(std_st) FROM nx.weld_diam GROUP BY pipe_diam")
        std = {round(float(r[0]), 3): (float(r[1] or 0), float(r[2] or 0)) for r in cur.fetchall()}
        cur.execute("DELETE FROM nx.sourcing_route_weld WHERE route_id=? AND node_item=?", rid, node)
        tot_use = tot_st = 0.0; n = 0
        for r in rows:
            pd = round(float(r.get("pipe_diam") or 0), 3); qty = float(r.get("weld_qty") or 0)
            if pd <= 0 or qty <= 0: continue
            su, ss = std.get(pd, (0.0, 0.0))
            use = round(su * qty * loss, 4); st = round(ss * qty, 4)
            tot_use += use; tot_st += st; n += 1
            cur.execute("""INSERT INTO nx.sourcing_route_weld(route_id,node_item,weld_item,pipe_diam,weld_qty,use_qty,st)
                VALUES(?,?,?,?,?,?,?)""", rid, node[:60], (str(r.get("weld_item", "") or "")[:60]), pd, qty, use, st)
        cur.execute("UPDATE nx.sourcing_route SET approve_flag=0, upd_dt=getdate() WHERE route_id=?", rid)
        nx.commit()
        return {"ok": True, "node_item": node, "rows_saved": n, "total_use_qty": round(tot_use, 4), "total_st": round(tot_st, 2)}
    except HTTPException:
        nx.rollback(); raise
    except Exception:
        nx.rollback(); raise
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

# ===================== ★재설계: 노드 스코프 공정저장 · SUB 중복검사 · 전체저장 검증 =====================
def _node_procs_map(cur, route_id, node_item):
    """노드(route_id,node_item)의 공정 맵 {proc_code: round(wq,2)} (wq>0만) — SUB 중복검사 서명용."""
    cur.execute("SELECT proc_code, ISNULL(work_qty,0) FROM nx.sourcing_route_proc WHERE route_id=? AND node_item=?", route_id, node_item)
    out = {}
    for r in cur.fetchall():
        wq = round(float(r[1] or 0), 2)
        if wq > 0: out[str(r[0]).strip()] = wq
    return out

def _sub_members(cur, route_id, sub_line):
    """SUB(sub_line) 직속 부품 child_item 셋(RAC 용접봉 제외)."""
    cur.execute("SELECT ISNULL(child_item,'') FROM nx.sourcing_route_line WHERE route_id=? AND parent_line=? AND node_kind<>'SUB'", route_id, sub_line)
    return frozenset(str(r[0]).strip() for r in cur.fetchall()
                     if str(r[0]).strip() and not str(r[0]).upper().startswith("RAC"))

@router.post("/api/sourcing/proc/node_save")
def sourcing_proc_node_save(payload: dict = Body(...)):
    """★노드 스코프 공정 저장 — (route_id, node_item)만 전체교체(다른 노드 불변). BASE 게이트 없음(전체저장 finalize에서 검증).
       payload {route_id, node_item, procs:[{proc_code, work_qty, prod_uph, calc_gubun}]}. work_qty>0만. 승인 리셋.
       ★용접ST(가공비)는 프론트가 용접공정(51) work_qty로 포함(관경별 용접 매트릭스 Σ표준ST×횟수). 용접봉 소요량(재료)은 weld/save 별도."""
    rid = int(payload.get("route_id") or 0)
    node = str(payload.get("node_item", "")).strip()
    procs = payload.get("procs", []) or []
    if rid <= 0 or not node: raise HTTPException(400, "route_id·node_item 필요")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("SELECT 1 FROM nx.sourcing_route WHERE route_id=?", rid)
        if not cur.fetchone(): raise HTTPException(404, "route 없음")
        cur.execute("DELETE FROM nx.sourcing_route_proc WHERE route_id=? AND node_item=?", rid, node)
        n = 0
        for p in procs:
            wq = float(p.get("work_qty") or 0)
            if wq <= 0: continue
            cur.execute("""INSERT INTO nx.sourcing_route_proc(route_id,node_item,proc_code,work_qty,prod_uph,calc_gubun)
                VALUES(?,?,?,?,?,?)""", rid, node[:60], str(p.get("proc_code", "")).strip()[:10],
                wq, float(p.get("prod_uph") or 0), (str(p.get("calc_gubun", "") or "")[:4]))
            n += 1
        cur.execute("UPDATE nx.sourcing_route SET approve_flag=0, upd_dt=getdate() WHERE route_id=?", rid)
        nx.commit()
        node_sum = round(sum(float(p.get("work_qty") or 0) for p in procs if float(p.get("work_qty") or 0) > 0), 2)
        return {"ok": True, "node_item": node, "saved": n, "node_gongsu": node_sum}
    except HTTPException:
        nx.rollback(); raise
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()

@router.get("/api/sourcing/sub/match")
def sourcing_sub_match(route_id: int = Query(...)):
    """★신규 SUB 중복검사 — 이 후보의 각 SUB 노드(부품셋+공정공수)가 기존 SUB(다른 후보/이 후보 포함)와 동일한지.
       동일 판정: 직속 부품 child_item 셋(RAC 제외) 일치 AND 공정 {proc_code:round(wq,2)} 일치.
       반환 matches: [{sub_line, sub_item, member_count, match_code, match_route_id}] — 코드가 다른 동일 SUB만."""
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("SELECT line_id, ISNULL(sub_item,ISNULL(child_item,'')) FROM nx.sourcing_route_line WHERE route_id=? AND node_kind='SUB'", route_id)
        my_subs = [(int(r[0]), str(r[1]).strip()) for r in cur.fetchall()]
        cur.execute("SELECT route_id, line_id, ISNULL(sub_item,ISNULL(child_item,'')) FROM nx.sourcing_route_line WHERE node_kind='SUB'")
        all_subs = [(int(r[0]), int(r[1]), str(r[2]).strip()) for r in cur.fetchall()]
        matches = []
        for (sline, scode) in my_subs:
            mem = _sub_members(cur, route_id, sline)
            if not mem: continue
            prc = _node_procs_map(cur, route_id, scode) if scode else {}
            for (rid2, lid2, scode2) in all_subs:
                if lid2 == sline: continue
                if not scode2 or scode2 == scode: continue   # 같은 코드 = 이미 동일(재사용 불필요)
                if _sub_members(cur, rid2, lid2) != mem: continue
                if _node_procs_map(cur, rid2, scode2) != prc: continue
                matches.append({"sub_line": sline, "sub_item": scode, "member_count": len(mem),
                                "match_code": scode2, "match_route_id": rid2})
                break
        return {"ok": True, "matches": matches}
    finally:
        nx.close()

@router.post("/api/sourcing/route/finalize")
def sourcing_route_finalize(payload: dict = Body(...)):
    """★전체 저장 검증(순서) — (1)SUB 재사용 적용(reuse_map: {sub_line:기존코드}) (2)공수합=BASE diff0 (3)부품수=BASE 일치.
       실패 시 거부(변경 롤백)+사유. commit=1·통과 시 확정(라인/공정은 증분저장돼 있어 reuse 반영·게이트 통과가 곧 확정).
       payload {route_id, item_code, ymd?, reuse_map?{sub_line:code}, commit?}. RAC(용접봉)은 부품수/공수합에서 제외(공정종속)."""
    rid = int(payload.get("route_id") or 0)
    item = str(payload.get("item_code", "")).strip()
    ymd = str(payload.get("ymd", "260630")).strip() or "260630"
    reuse_map = payload.get("reuse_map", {}) or {}
    commit = bool(payload.get("commit"))
    if rid <= 0 or not item: raise HTTPException(400, "route_id·item_code 필요")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("SELECT 1 FROM nx.sourcing_route WHERE route_id=?", rid)
        if not cur.fetchone(): raise HTTPException(404, "route 없음")
        errors = []
        # (1) SUB 재사용 — 이 후보 SUB 라인 코드를 기존코드로 교체(라인·공정·용접 node_item 갱신)
        reused = []
        for k, newcode in (reuse_map.items() if isinstance(reuse_map, dict) else []):
            try: sline = int(k)
            except Exception: continue
            newcode = str(newcode or "").strip()
            if sline <= 0 or not newcode: continue
            cur.execute("SELECT ISNULL(sub_item,ISNULL(child_item,'')) FROM nx.sourcing_route_line WHERE route_id=? AND line_id=? AND node_kind='SUB'", rid, sline)
            r0 = cur.fetchone()
            if not r0: continue
            oldcode = str(r0[0]).strip()
            if oldcode == newcode: continue
            cur.execute("UPDATE nx.sourcing_route_line SET child_item=?, sub_item=?, child_name=? WHERE route_id=? AND line_id=?", newcode, newcode, newcode, rid, sline)
            cur.execute("UPDATE nx.sourcing_route_proc SET node_item=? WHERE route_id=? AND node_item=?", newcode, rid, oldcode)
            cur.execute("UPDATE nx.sourcing_route_weld SET node_item=? WHERE route_id=? AND node_item=?", newcode, rid, oldcode)
            reused.append({"sub_line": sline, "old": oldcode, "new": newcode})
        # (2) 공수합=BASE: Σ(part_cut BASE 자동귀속) + Σ(sourcing_route_proc 전노드 조립)
        try: base = _base_gongsu(item, ymd)
        except Exception as e: raise HTTPException(500, f"BASE 공수합 계산오류: {e}")
        try:
            pc, _asm, _bg = _panel_cut_asm(item, ymd)
            cut_sum = round(sum(sum(d.values()) for d in pc.values()), 2)
        except Exception:
            cut_sum = 0.0
        cur.execute("SELECT ISNULL(SUM(work_qty),0) FROM nx.sourcing_route_proc WHERE route_id=?", rid)
        proc_sum = round(float(cur.fetchone()[0] or 0), 2)
        cand = round(cut_sum + proc_sum, 2)
        gongsu_ok = abs(cand - base) < 0.5
        if not gongsu_ok:
            errors.append(f"공수합 {cand} ≠ BASE {base} (절삭 {cut_sum} + 조립 {proc_sum}) — 차이 {round(cand - base, 2)}")
        # (3) 부품수 = BASE 부품수 (RAC 제외)
        try:
            base_parts = frozenset(str(l["child_item"]).strip() for l in _base_flat_lines(item, ymd)
                                   if l.get("child_item") and not str(l["child_item"]).upper().startswith("RAC"))
        except Exception:
            base_parts = frozenset()
        cur.execute("SELECT ISNULL(child_item,'') FROM nx.sourcing_route_line WHERE route_id=? AND node_kind<>'SUB'", rid)
        route_parts = frozenset(str(r[0]).strip() for r in cur.fetchall()
                                if str(r[0]).strip() and not str(r[0]).upper().startswith("RAC"))
        missing = sorted(base_parts - route_parts)
        extra = sorted(route_parts - base_parts)
        part_ok = (len(missing) == 0 and len(extra) == 0)
        if not part_ok:
            if missing: errors.append(f"미배치(BASE 有·후보 無) {len(missing)}건: {', '.join(missing[:8])}{'…' if len(missing) > 8 else ''}")
            if extra: errors.append(f"BASE에 없는 부품 {len(extra)}건: {', '.join(extra[:8])}{'…' if len(extra) > 8 else ''}")
        ok = gongsu_ok and part_ok
        if ok and commit:
            cur.execute("UPDATE nx.sourcing_route SET upd_dt=getdate() WHERE route_id=?", rid)
            nx.commit()
        else:
            nx.rollback()   # 검증전용(commit=0) 또는 실패 → reuse 변경 롤백
        return {"ok": ok, "gongsu_ok": gongsu_ok, "part_ok": part_ok, "cand_gongsu": cand, "base_gongsu": base,
                "cut_sum": cut_sum, "proc_sum": proc_sum, "base_part_count": len(base_parts), "route_part_count": len(route_parts),
                "missing": missing, "extra": extra, "reused": reused, "committed": bool(ok and commit), "errors": errors}
    except HTTPException:
        nx.rollback(); raise
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()


# ===================== 후보 실원가 (route/cost) — NxCostEngine 재사용, 마스터와 diff0 =====================
def _route_proc_names(codes):
    """공정코드→이름(CS_M_PROC) — 후보 공정표시용."""
    out = {}
    codes = sorted({str(c).strip() for c in codes if str(c or "").strip()})
    if not codes: return out
    cn = _conn(); cur = cn.cursor()
    try:
        for i in range(0, len(codes), 900):
            ch = codes[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT PROC_CODE, ISNULL(PROC_DESC,'') FROM CS_M_PROC WHERE PROC_CODE IN ({ph})", *ch)
            for r in cur.fetchall(): out[str(r[0]).strip()] = str(r[1]).strip()
    finally:
        cn.close()
    return out

@router.get("/api/sourcing/route/cost")
def sourcing_route_cost(route_id: int = Query(..., description="후보 route_id(>0). 현행 baseline(route_id=0)은 마스터 /api/cost/sil 사용"),
                        ymd: str = Query("260630", description="단가기준일 YYMMDD")):
    """★후보 실원가 산출 — NxCostEngine(무수정) 재사용, 마스터 실원가와 **동일 산식**.
       재료비/가공비/일반관리/운반/이윤/LME/실원가/LG판가/손익 = eng.silwon(대상품목) — 마스터 /api/cost/sil 과 diff0.
       ★설계근거(실측): 후보=BOM구조/공정 재배치 계층이며 조달(업체·매입가·사급)은 **조달프로파일 계층**(별도 연동). 부품셋·공수합=BASE 게이트(route/finalize)로 보존 강제 →
         구조·조달 불변이면 실원가 = 마스터(diff0 by construction). BASE 복사 후보의 route/cost == 마스터 실원가(앵커 5722) diff0.
       반환: cost(마스터와 동일필드) + current(현행=동일 대상 실원가) + diff(현행대비, 구조후보는 0) + rows(silwon_nodes) + procs(silwon_proc_grid) + structure(후보 구조 lines/subs/procs)."""
    if NxCostEngine is None:
        raise HTTPException(500, "nx_cost_engine 로드 실패")
    ymd = (ymd or "260630").strip() or "260630"
    rid = int(route_id or 0)
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_tbl(cur)
        cur.execute("""SELECT item_code, ISNULL(route_no,0), ISNULL(route_name,''), ISNULL(current_flag,0),
              ISNULL(approve_flag,0), ISNULL(gubun,'') FROM nx.sourcing_route WHERE route_id=?""", rid)
        h = cur.fetchone()
        if not h: raise HTTPException(404, f"후보 route_id={rid} 없음")
        item = str(h[0]).strip(); route_no = int(h[1]); route_name = h[2]
        approve_flag = bool(h[4]); route_gubun = h[5]
        # 후보 구조(표시용) — 라인(SUB 계층)·공정·용접
        cur.execute("""SELECT line_id, ISNULL(sort_seq,0), ISNULL(child_item,''), ISNULL(child_name,''), qty, ISNULL(gubun,''),
              ISNULL(vendor_code,''), ISNULL(node_kind,'PART'), parent_line, ISNULL(sub_item,''), ISNULL(is_rawmat,0), ISNULL(material,'')
            FROM nx.sourcing_route_line WHERE route_id=? ORDER BY sort_seq, line_id""", rid)
        slines = [{"line_id": int(r[0]), "seq": int(r[1] or 0), "child_item": str(r[2]).strip(), "child_name": r[3],
                   "qty": float(r[4] or 0), "gubun": str(r[5] or ""), "vendor_code": str(r[6]).strip(),
                   "node_kind": str(r[7] or 'PART'), "parent_line": (int(r[8]) if r[8] is not None else None),
                   "sub_item": str(r[9] or ''), "is_rawmat": int(r[10] or 0), "material": str(r[11] or "")} for r in cur.fetchall()]
        cur.execute("SELECT node_item, proc_code, ISNULL(work_qty,0), ISNULL(calc_gubun,'') FROM nx.sourcing_route_proc WHERE route_id=? ORDER BY node_item, proc_code", rid)
        sprocs = [{"node_item": str(r[0]).strip(), "proc_code": str(r[1]).strip(), "work_qty": float(r[2] or 0), "calc_gubun": str(r[3] or "")} for r in cur.fetchall()]
        cur.execute("SELECT node_item, ISNULL(weld_item,''), ISNULL(pipe_diam,0), ISNULL(weld_qty,0), ISNULL(use_qty,0), ISNULL(st,0) FROM nx.sourcing_route_weld WHERE route_id=? ORDER BY node_item", rid)
        swelds = [{"node_item": str(r[0]).strip(), "weld_item": str(r[1]).strip(), "pipe_diam": float(r[2] or 0),
                   "weld_qty": float(r[3] or 0), "use_qty": float(r[4] or 0), "st": float(r[5] or 0)} for r in cur.fetchall()]
        n_sub = sum(1 for l in slines if l["node_kind"] == 'SUB')
    finally:
        nx.close()

    def _compute(eng):
        cand = eng.silwon(item, ymd)
        try: lme = eng.lme_total(item, ymd)
        except Exception: lme = 0.0
        sn = eng.silwon_nodes(item, ymd)
        pg = eng.silwon_proc_grid(item, ymd)
        return cand, lme, sn, pg
    with _COST_LOCK:
        try:
            cand, lme, sn, pg = _compute(_get_cost_engine())
        except Exception:
            try:
                cand, lme, sn, pg = _compute(_get_cost_engine(fresh=True))
            except Exception as e2:
                raise HTTPException(500, f"nx엔진 오류: {e2}")
    # 후보 원가 = 대상 실원가(마스터 동일 산식). LME 필드 명시.
    cost = {"jae": cand["jae"], "gagong": cand["gagong"], "ilban": cand["ilban"], "unban": cand["unban"],
            "profit": cand["profit"], "lme": round(lme, 2), "silwon": cand["silwon"], "lg": cand["lg"], "sonik": cand["sonik"]}
    # 현행(R01) = 동일 대상 실원가(구조/조달 불변 기준선). diff = 후보 − 현행.
    current = dict(cost)
    diff = {k: round((cost.get(k, 0) or 0) - (current.get(k, 0) or 0), 2) for k in cost}
    # 공정 그리드(이름 매핑) — silwon_proc_grid
    pnm = _route_proc_names(list(pg.keys()) + [p["proc_code"] for p in sprocs])
    def _grp(code):
        if code in ("51", "28"): return "용접"
        if code in ("61", "83"): return "포장"
        if code in _PROC_FASTEN_S: return "체결"
        return "가공"
    procs = [{"code": p, "name": pnm.get(p, p), "group": _grp(p), "wq": v["wq"], "amt": v["amt"],
              "uph": v["uph"], "cg": v["cg"], "labor": v["labor"]} for p, v in pg.items()]
    procs.sort(key=lambda x: (x["group"], x["code"]))
    # 후보 공정에 이름 부여(구조 표시용)
    for p in sprocs: p["name"] = pnm.get(p["proc_code"], p["proc_code"])
    return {"route_id": rid, "route_no": route_no, "route_name": route_name, "item_code": item, "ymd": ymd,
            "approve_flag": approve_flag, "route_gubun": route_gubun,
            "cost": cost, "current": current, "diff": diff,
            "rows": sn.get("rows", []), "procs": procs,
            "structure": {"lines": slines, "n_sub": n_sub, "procs": sprocs, "welds": swelds},
            "diff0": all(abs(v) < 0.5 for v in diff.values()),
            "note": ("후보 원가 = 대상품목 실원가(NxCostEngine, 마스터와 동일 산식·diff0). "
                     "후보는 BOM구조·공정 재배치 계층 — 조달(업체·매입가·사급 배분)은 조달프로파일 계층에서 반영. "
                     "부품셋·공수합=BASE 보존(route/finalize 게이트)이므로 구조·조달 불변이면 실원가는 현행과 동일.")}


# ===================== 조달 프로파일 = route 단위 배분(nx.route_alloc) =====================
# ★계층 구분: 이 배분은 '후보(R01 현행 vs R02..) 간 배정' = route 단위(다른 계층).
#   후보 '내부 업체분배'(vendor·배분%·유효기간)는 nx.sourcing_profile(위 profile/list·profile/save)로 별도.
# 조달 프로파일 화면은 이 route_alloc 만 편집(단일 소스). 승인 후보(approve_flag=1, baseline=R01 자동승인)만 활성 허용.
_ROUTE_ALLOC_READY = False
def _ensure_route_alloc_tbl(cur):
    global _ROUTE_ALLOC_READY
    if _ROUTE_ALLOC_READY:
        return
    cur.execute("""IF OBJECT_ID('nx.route_alloc','U') IS NULL CREATE TABLE nx.route_alloc(
        item_code NVARCHAR(60) NOT NULL, route_id INT NOT NULL, apply_from DATE NULL, apply_to DATE NULL,
        is_active BIT DEFAULT 0, alloc_ratio FLOAT NULL, upd_dt datetime DEFAULT getdate(),
        CONSTRAINT PK_nx_route_alloc PRIMARY KEY(item_code, route_id))""")
    _ROUTE_ALLOC_READY = True

def _profile_routes(cur, item, show_unapproved=1):
    """조달 프로파일 편집용 승인 후보 목록(현행 R01 baseline 포함) — sourcing_routes(for_profile) 헤더 로직 재사용(라인 미조회, 경량).
       반환: [{route_id, route_no, route_name, gubun, vendor_code, vendor_name, current_flag, approve_flag,
               route_apply_from, reject_flag, baseline, readonly}]. approve_flag=0(미승인)은 show_unapproved=1 이면 회색(readonly)로 포함."""
    _ensure_route_tbl(cur)
    cur.execute("""SELECT r.route_id, r.route_no, ISNULL(r.route_name,''), ISNULL(r.vendor_code,''), ISNULL(r.gubun,''),
          r.current_flag, r.approve_flag, CONVERT(varchar(10),r.apply_from,23), ISNULL(r.reject_flag,0)
        FROM nx.sourcing_route r WHERE r.item_code=? ORDER BY r.route_no""", item)
    routes = []; vcodes = set()
    for h in cur.fetchall():
        routes.append({"route_id": int(h[0]), "route_no": int(h[1]), "route_name": h[2],
                       "vendor_code": str(h[3]).strip(), "gubun": h[4], "current_flag": bool(h[5]),
                       "approve_flag": bool(h[6]), "route_apply_from": h[7], "reject_flag": bool(h[8]),
                       "baseline": False})
        vcodes.add(str(h[3]).strip())
    # 현행 baseline 합성(저장된 route_no=1/현행이 없을 때만) — 읽기전용·자동승인 기준선(=조회 routes와 동일 규칙)
    has_saved_current = any(r["current_flag"] or r["route_no"] == 1 for r in routes)
    if not has_saved_current:
        routes.insert(0, {"route_id": 0, "route_no": 1, "route_name": "현행(실사용 BOM)", "vendor_code": "",
                          "gubun": "자체", "current_flag": True, "approve_flag": True, "route_apply_from": None,
                          "reject_flag": False, "baseline": True})
    vmap = _custnm_map(cur, vcodes)
    for r in routes:
        r["vendor_name"] = vmap.get(r["vendor_code"], r["vendor_code"])
    def keep(r):
        return True if r["approve_flag"] else bool(show_unapproved)
    return [dict(r, readonly=(not r["approve_flag"])) for r in routes if keep(r)]

@router.get("/api/sourcing/route/alloc")
def sourcing_route_alloc_get(item: str = Query(...), show_unapproved: int = Query(1)):
    """승인 조달경로 후보(R01 현행 + R02..) + 저장된 route 단위 배분(nx.route_alloc) 조인.
       저장 없으면 기본=현행(R01/current) 활성 100%·나머지 비활성. 미승인 후보=회색(readonly, 활성 불가)."""
    item = item.strip()
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_route_alloc_tbl(cur)
        routes = _profile_routes(cur, item, show_unapproved)
        cur.execute("""SELECT route_id, CONVERT(varchar(10),apply_from,23), CONVERT(varchar(10),apply_to,23),
              is_active, alloc_ratio FROM nx.route_alloc WHERE item_code=?""", item)
        saved = {int(r[0]): {"apply_from": r[1], "apply_to": r[2],
                             "is_active": (bool(r[3]) if r[3] is not None else None),
                             "alloc_ratio": (float(r[4]) if r[4] is not None else None)} for r in cur.fetchall()}
        has_saved = len(saved) > 0
        cur.execute("SELECT ISNULL(item_name,'') FROM nx.item WHERE item_code=?", item)
        rr = cur.fetchone(); nm = rr[0] if rr else ""
        out = []
        for r in routes:
            s = saved.get(r["route_id"])
            if s is None:
                is_cur = r["current_flag"] or r["route_no"] == 1
                dflt_active = bool(is_cur) and not has_saved   # 저장 이력 없을 때만 현행 기본활성
                s = {"apply_from": None, "apply_to": None, "is_active": dflt_active,
                     "alloc_ratio": (100.0 if dflt_active else None)}
            out.append({**r,
                        "apply_from": s["apply_from"], "apply_to": s["apply_to"],
                        "is_active": (bool(s["is_active"]) if s["is_active"] is not None else False),
                        "alloc_ratio": s["alloc_ratio"]})
        act = [(x["apply_from"] or "2000-01-01", x["apply_to"], x["alloc_ratio"])
               for x in out if x["is_active"] and x["alloc_ratio"] is not None]
        alloc_errs = _validate_alloc(act) if act else []
        return {"item": item, "item_name": nm, "routes": out, "has_saved": has_saved,
                "alloc_ok": (len(alloc_errs) == 0), "alloc_errs": alloc_errs}
    finally:
        nx.close()

@router.post("/api/sourcing/route/alloc/save")
def sourcing_route_alloc_save(payload: dict = Body(...)):
    """route 단위 배분 저장. 검증: (1)승인 후보만 활성 허용(baseline R01 포함) (2)유효기간 겹치는 활성 배분합=100%
       (활성 1개=단일이면 100 자동/생략 허용). upsert. 근거키=item_code·route_id 스코프(대량삭제 금지).
       payload {item, rows:[{route_id, apply_from, apply_to, is_active, alloc_ratio}]}."""
    item = str(payload.get("item", "")).strip()
    rows = payload.get("rows", []) or []
    if not item:
        raise HTTPException(400, "item 필요")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_route_alloc_tbl(cur)
        approved = {r["route_id"]: r for r in _profile_routes(cur, item, show_unapproved=1)}
        norm = []; act = []; errs = []
        for r in rows:
            try:
                rid = int(r.get("route_id"))
            except Exception:
                continue
            af = _d(r.get("apply_from")) or None
            at = _d(r.get("apply_to")) or None
            iact = 1 if r.get("is_active") else 0
            ratio = r.get("alloc_ratio"); ratio = float(ratio) if (ratio not in (None, "", "null")) else None
            if iact:   # 승인 후보만 활성 허용(미존재/미승인 거부)
                info = approved.get(rid)
                if info is None or not info["approve_flag"]:
                    errs.append(f"route_id={rid}: 미승인/미존재 후보는 활성 배정 불가")
                    continue
            norm.append((rid, af, at, iact, ratio))
            if iact and ratio is not None:
                act.append((af or "2000-01-01", at, ratio))
        if errs:
            nx.rollback(); return {"ok": False, "gate": "APPROVE", "errors": list(dict.fromkeys(errs))}
        alloc_errs = _validate_alloc(act) if act else []
        if alloc_errs:
            nx.rollback(); return {"ok": False, "gate": "ALLOC", "errors": list(dict.fromkeys(alloc_errs))}
        for (rid, af, at, iact, ratio) in norm:   # 근거키 스코프 upsert(대량삭제 금지)
            cur.execute("DELETE FROM nx.route_alloc WHERE item_code=? AND route_id=?", item, rid)
            cur.execute("""INSERT INTO nx.route_alloc(item_code,route_id,apply_from,apply_to,is_active,alloc_ratio,upd_dt)
                VALUES(?,?,?,?,?,?,getdate())""", item, rid, af, at, iact, ratio)
        nx.commit()
        return {"ok": True, "count": len(norm)}
    except HTTPException:
        nx.rollback(); raise
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()
