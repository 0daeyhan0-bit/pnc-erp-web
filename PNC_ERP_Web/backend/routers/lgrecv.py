# -*- coding: utf-8 -*-
"""LG 리시빙 파일 업로드 라우터 — 레거시 w_sa_sale_110 "LG리시빙파일 업로드" 이식.

레거시 흐름(w_sa_sale_210/w_sa_sagub_120 동일 로직)을 GR Status(LG PU-SCS) 원본을 직접 먹도록 재구성:
  · 파일 = LG 포털 GR Status 엑셀(헤더 1행: No/GR Date/Time/Material/Order No/Item/Departure No/…/GR Qty/…).
  · 구분(GUBUN) = Departure No 접두로 자동판정 — DMZ→'C'(=SAC, 舊 CAC) · DGZ→'R'(RAC).
    (레거시는 파일명 _CAC_/_RAC_ 로 정하고 Departure 접두로 검증만 했음. 웹은 접두로 바로 판정.)
  · 적재 = nx.SA_T_LG_RECEIVING_DTL (쓰기=nx만, §1). 삭제-교체(멱등): 구분별 (receiving_ymd 최소~최대) 범위 갈아끼움.
  · 레거시 대비 개선 = nx 테이블에 있는 ORDER_NO/ORDER_TYPE/DEPARTURE_NO/DEPARTURE_DATE/SUPPLIER_REF_NO/SUBINVENTORY 도 함께 적재(§6 전 컬럼).

컷오버(flip) 정합:
  · 이 업로드는 **항상 nx 에 쓴다**(flip 무관). 조회(LG리시빙관리 lgrecv·일일현황·매출요약)는 컷오버 flip 이 라이브→nx 로 전환.
    → 컷오버 후: 웹 업로드→nx, 웹 조회→nx 로 단일소스 정합. (_schema/CUTOVER_FLIP_WORKLIST.md 참조)
  · 관세환급(SA_T_CUSTOMS_REFUND, 레거시 wf_refund)은 이번 범위 제외 — 별도 후속.

검증: _schema/lgrecv_upload_testbed.py — 9/1 GR Status 파싱 결과 = 라이브 SA_T_LG_RECEIVING_DTL(260901) diff0.
"""
import io as _io
import datetime as _dt
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from common import _nx_tx

router = APIRouter()

# GR Status 헤더명 → 우리 필드. (레거시 리네임 LG리시빙2 헤더가 아니라 LG 원본 GR Status 헤더를 직접 매핑)
_H = {
    "gr_date":  "GR Date",
    "item":     "Material",
    "qty":      "GR Qty",
    "curr":     "Curr.",
    "rate":     "Curr. Rate",
    "cost":     "PO Unit Price",
    "amt":      "Local GR Amount",      # KRW 환산액(레거시 RECV_AMT 와 diff0 확인). GR Amount 와 KRW 동일.
    "mkt":      "MKT",                  # 1=수출 · 2=내수
    "work":     "Demand P/S Order",     # 접미사 없는 모델코드(라이브 WORK_ORDER 실측=Demand)
    "dep":      "Departure No",         # DMZ→C(SAC) · DGZ→R(RAC)
    "ordno":    "Order No",
    "ordtype":  "Order Type",
    "depdate":  "Departure Date",
    "supref":   "Supplier\nREF No",     # 엑셀 헤더에 줄바꿈 포함
    "sloc":     "SLoc",
}
# 헤더 정규화(공백/개행 제거·대문자)로 비교 — LG 포털 export 의 개행/공백 변동 흡수
def _hn(s):
    return "".join(str(s or "").split()).upper()

_H_NORM = {k: _hn(v) for k, v in _H.items()}


def _compact_ymd8(v):
    """GR Date/Departure Date → YYYYMMDD(8자리). datetime·'2026-09-02 00:00:0'·'20260902' 모두 대응."""
    if isinstance(v, (_dt.datetime, _dt.date)):
        return "%04d%02d%02d" % (v.year, v.month, v.day)
    digits = "".join(ch for ch in str(v or "") if ch.isdigit())
    return digits[:8]


def _to_f(v):
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def _parse_gr_status(content, filename=""):
    """GR Status 엑셀 bytes → (groups, meta).
       groups = {gubun: {"ymd_from","ymd_to","recs":[dict,...],"qty","amt"}}
       meta   = {"total_rows","skipped","warnings","preview","unknown_dep"}
       recs 는 적재 직전 형태(seq 미부여). seq 는 upload 시 (gubun,ymd) 단위로 부여."""
    try:
        import openpyxl
    except Exception:
        raise HTTPException(500, "openpyxl 미설치(서버)")
    try:
        wb = openpyxl.load_workbook(_io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(400, f"엑셀 열기 실패: {str(e)[:120]}")
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        raise HTTPException(400, "빈 파일")

    # 헤더행 탐색(상위 5행) — Material·GR Date 를 모두 가진 행
    hdr_i, col = -1, {}
    for i in range(min(5, len(rows))):
        norm = {_hn(c): j for j, c in enumerate(rows[i]) if c not in (None, "")}
        if _H_NORM["item"] in norm and _H_NORM["gr_date"] in norm:
            hdr_i = i
            for key, hn in _H_NORM.items():
                col[key] = norm.get(hn)   # 없으면 None(선택 컬럼 허용)
            break
    if hdr_i < 0:
        raise HTTPException(400, "GR Status 형식 아님 — 'Material'·'GR Date' 헤더를 상위 5행에서 못 찾음")
    # 필수 컬럼 확인
    need = ["gr_date", "item", "qty", "amt", "dep"]
    miss = [_H[k] for k in need if col.get(k) is None]
    if miss:
        raise HTTPException(400, "엑셀에서 필수 컬럼을 못 찾음: " + ", ".join(miss))

    def gv(r, key):
        j = col.get(key)
        return r[j] if (j is not None and j < len(r)) else None

    def gs(r, key, ln=None):
        v = gv(r, key)
        s = "" if v is None else str(v).strip()
        return s[:ln] if ln else s

    groups = {}
    total = skipped = 0
    warnings = []
    unknown_dep = []
    preview = []
    for r in rows[hdr_i + 1:]:
        if not r or not any(x not in (None, "") for x in r):
            continue
        item = gs(r, "item", 20)
        ymd8 = _compact_ymd8(gv(r, "gr_date"))
        # 합계행(Sum/Total) = Material·날짜 비어 skip (레거시 동일 규칙)
        if not item or len(ymd8) < 8:
            skipped += 1
            continue
        ymd = ymd8[2:8]   # YYMMDD (앞 세기 '20' 버림 = 레거시 mid(,3,6))
        dep = gs(r, "dep", 20)
        pre = dep[:3].upper()
        if pre == "DMZ":
            gubun = "C"
        elif pre == "DGZ":
            gubun = "R"
        else:
            unknown_dep.append(dep or "(빈값)")
            skipped += 1
            continue
        total += 1
        rec = {
            "receiving_ymd": ymd,
            "gubun": gubun,
            "item_code": item,
            "recv_qty": int(round(_to_f(gv(r, "qty")))),
            "recv_cost": round(_to_f(gv(r, "cost")), 2),
            "recv_amt": round(_to_f(gv(r, "amt")), 2),
            "currency": gs(r, "curr", 3) or "KRW",
            "currency_rate": round(_to_f(gv(r, "rate")) or 1, 4),
            "mkt": (gs(r, "mkt", 1) or ""),
            "work_order": gs(r, "work", 30),
            "order_type": gs(r, "ordtype", 10),
            "order_no": gs(r, "ordno", 20),
            "departure_no": dep,
            "departure_date": _compact_ymd8(gv(r, "depdate")),
            "supplier_ref_no": gs(r, "supref", 100),
            "subinventory": gs(r, "sloc", 20),
        }
        g = groups.setdefault(gubun, {"ymd_from": ymd, "ymd_to": ymd, "recs": [], "qty": 0, "amt": 0.0})
        g["recs"].append(rec)
        g["ymd_from"] = min(g["ymd_from"], ymd)
        g["ymd_to"] = max(g["ymd_to"], ymd)
        g["qty"] += rec["recv_qty"]
        g["amt"] += rec["recv_amt"]
        if len(preview) < 30:
            preview.append(rec)

    if not groups:
        raise HTTPException(400, "적재할 데이터 행이 없음(합계행만 있거나 Departure 접두가 DMZ/DGZ 아님)")
    if unknown_dep:
        uq = sorted(set(unknown_dep))
        warnings.append(f"Departure 접두가 DMZ/DGZ 아닌 {len(unknown_dep)}행 제외(예: {', '.join(uq[:3])})")
    if len(groups) > 1:
        warnings.append("한 파일에 SAC(DMZ)·RAC(DGZ)가 섞여 있음 — 구분별로 각각 삭제-교체 처리")
    meta = {"total_rows": total, "skipped": skipped, "warnings": warnings,
            "preview": preview, "unknown_dep": sorted(set(unknown_dep))}
    return groups, meta


_GLABEL = {"C": "SAC", "R": "RAC"}   # 표시 라벨(DMZ=SAC·구 CAC / DGZ=RAC). 저장 GUBUN 은 'C'/'R' 유지.


def _summary(groups, meta, filename):
    by = []
    for g, d in sorted(groups.items()):
        by.append({"gubun": g, "label": _GLABEL.get(g, g),
                   "ymd_from": d["ymd_from"], "ymd_to": d["ymd_to"],
                   "rows": len(d["recs"]), "qty": d["qty"], "amt": round(d["amt"], 2)})
    return {"file": filename, "total_rows": meta["total_rows"], "skipped": meta["skipped"],
            "warnings": meta["warnings"], "by_gubun": by,
            "preview": [{**r, "label": _GLABEL.get(r["gubun"], r["gubun"])} for r in meta["preview"]]}


@router.post("/api/lgrecv/parse")
async def lgrecv_parse(file: UploadFile = File(...)):
    """GR Status 엑셀 업로드 → 파싱·검증만(미저장). 미리보기·구분별 요약·경고 반환."""
    content = await file.read()
    groups, meta = _parse_gr_status(content, file.filename or "")
    out = _summary(groups, meta, file.filename or "")
    out["ok"] = True
    out["committed"] = False
    return out


@router.post("/api/lgrecv/upload")
async def lgrecv_upload(file: UploadFile = File(...), user: str = Form(default="웹업로드")):
    """GR Status 엑셀 → nx.SA_T_LG_RECEIVING_DTL 적재(삭제-교체, 구분별 원자적).
       레거시 w_sa_sale_110 업로드 대체. 쓰기=nx만(§1). 관세환급은 제외."""
    content = await file.read()
    groups, meta = _parse_gr_status(content, file.filename or "")

    ins_sql = """INSERT INTO nx.SA_T_LG_RECEIVING_DTL
        (RECEIVING_YMD,GUBUN,RECEIVING_SEQ,ITEM_CODE,RECV_QTY,RECV_COST,RECV_AMT,
         CURRENCY,CURRENCY_RATE,MKT,WORK_ORDER,ORDER_TYPE,ORDER_NO,DEPARTURE_NO,
         DEPARTURE_DATE,SUPPLIER_REF_NO,SUBINVENTORY,
         UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_IP,UPDATE_COMPUTER,UPDATE_WINDOW)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,GETDATE(),?,?,?)"""
    uid = (user or "웹업로드")[:20]
    IP, COMP, WIN = "", "WEB", "lgrecv_upload"

    cn = _nx_tx(); cur = cn.cursor()
    try:
        deleted = 0
        params = []
        for g, d in sorted(groups.items()):
            # 삭제-교체: 이 구분의 (최소~최대 일자) 범위 갈아끼움 (레거시 delete 스코프 동일)
            cur.execute(
                "DELETE FROM nx.SA_T_LG_RECEIVING_DTL WHERE RECEIVING_YMD BETWEEN ? AND ? AND GUBUN=?",
                d["ymd_from"], d["ymd_to"], g)
            deleted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            # seq 는 일자별 1..n (레거시 동일: 일자 바뀌면 리셋). 일자 오름차순 + 파일순 안정정렬.
            recs = sorted(d["recs"], key=lambda x: x["receiving_ymd"])
            seq_by_ymd = {}
            for r in recs:
                ymd = r["receiving_ymd"]
                seq_by_ymd[ymd] = seq_by_ymd.get(ymd, 0) + 1
                params.append((
                    r["receiving_ymd"], r["gubun"], seq_by_ymd[ymd], r["item_code"],
                    r["recv_qty"], r["recv_cost"], r["recv_amt"], r["currency"],
                    r["currency_rate"], r["mkt"], r["work_order"], r["order_type"],
                    r["order_no"], r["departure_no"], r["departure_date"],
                    r["supplier_ref_no"], r["subinventory"], uid, IP, COMP, WIN))
        cur.fast_executemany = True
        cur.executemany(ins_sql, params)
        cn.commit()
    except Exception as e:
        cn.rollback()
        raise HTTPException(500, f"적재 실패(롤백): {str(e)[:200]}")
    finally:
        cn.close()

    out = _summary(groups, meta, file.filename or "")
    out["ok"] = True
    out["committed"] = True
    out["inserted"] = len(params)
    out["deleted"] = deleted
    out["user"] = uid
    return out
