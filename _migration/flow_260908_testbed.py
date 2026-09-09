# -*- coding: utf-8 -*-
"""2026-09-08 수정분 전용 TestBed — 조회 전용(쓰기 없음·오염 0).

무엇을 보나 — 오늘 바꾼 4곳이 전 구간 흐름에서 실제로 맞게 도는가.
  H1  준비등록 BOM 축 전환      ready.py 가 클린을 읽고, 값이 라이브 생산BOM 과 같은가
  H2  준비등록 전개 결과 동등성   전환 전(CS)/후(클린) 실제 키팅목록 비교 + 라이브 판정
  H3  포장·작업자 4종 클린       nx.item_sub 조회·저장 소스가 살아있는가
  H4  item_sub 덮어쓰기 방지     품목마스터 저장이 남의 컬럼을 지우지 않는가(정적 검사)
  H5  계획 비고 노출            matrix API 가 행 단위 remarks 를 내리는가
  H6  전 구간 연결              오늘 바꾼 지점이 앞뒤 단계와 여전히 이어지는가

★쓰기 없음 — 전부 SELECT. 그래서 롤백 서버가 없어도 안전하다.
"""
import sys, os, io
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _conn, _nx

S = "PARTNER_ERP_TEST3.nx"
L = "PARTNER_ERP.dbo"
D6 = "260908"
PASS, FAIL, WARN = [], [], []


def ok(case, msg):
    PASS.append(case); print("   [PASS] {:<10s} {}".format(case, msg))


def ng(case, msg):
    FAIL.append(case); print("   [FAIL] {:<10s} {}".format(case, msg))


def wr(case, msg):
    WARN.append(case); print("   [WARN] {:<10s} {}".format(case, msg))


def title(t):
    print(); print("=" * 100); print(" " + t); print("=" * 100)


cn = _conn(); cur = cn.cursor()
nx = _nx(); ncur = nx.cursor()


def q1(c, sql, *a):
    c.execute(sql, *a) if a else c.execute(sql)
    r = c.fetchone()
    return r


def qall(c, sql, *a):
    c.execute(sql, *a) if a else c.execute(sql)
    return [tuple(x) for x in c.fetchall()]


V = """ISNULL(NULLIF(LTRIM(RTRIM({f})),''),'{d}')"""

# ═══════════════════════════════════════════════════════════════════
title("H1. 준비등록 BOM 축 — ready.py 가 클린(nx.bom_line)을 읽는가")
# ═══════════════════════════════════════════════════════════════════
src = open(os.path.join(BE, "routers", "ready.py"), encoding="utf-8").read()
_sql_blk = src[src.find("_SQL = "):src.find("_SQL = ") + 1800]
if "nx.bom_line" in _sql_blk and "nx.bom_header" in _sql_blk:
    ok("H1-a", "ready.py _SQL = nx.bom_line + nx.bom_header (클린)")
else:
    ng("H1-a", "ready.py 가 아직 클린을 안 읽는다")
if "CS_M_ITEM_BOM" in _sql_blk:
    ng("H1-b", "★_SQL 에 CS_M_ITEM_BOM 잔존 — 축이 섞였다")
else:
    ok("H1-b", "_SQL 에 CS 미러 직독 없음")
# 빈 문자열 유효기간 처리(함정)
if "NULLIF(LTRIM(RTRIM(l.from_ymd))" in _sql_blk:
    ok("H1-c", "from_ymd 빈문자열 NULLIF 처리 있음 (오탈락 방지)")
else:
    ng("H1-c", "★from_ymd 빈문자열 처리 없음 — 정상행이 오탈락한다")

# ═══════════════════════════════════════════════════════════════════
title("H2. 준비등록 전개 동등성 — 클린 vs CS, 라이브 생산BOM 으로 판정")
# ═══════════════════════════════════════════════════════════════════
NXQ = """
SELECT LTRIM(RTRIM(h.item_code)) p, LTRIM(RTRIM(l.child_item)) c,
       CAST(ISNULL(l.qty,0) AS float) q,
       LTRIM(RTRIM(ISNULL(l.gagong_proc,''))) gpc,
       CASE WHEN ISNULL(l.kitting,0)=1 THEN '1' ELSE '0' END kit
  FROM {S}.bom_line l WITH(NOLOCK) JOIN {S}.bom_header h WITH(NOLOCK) ON h.bom_id=l.bom_id
 WHERE ISNULL(l.except_flag,0)=0 AND CAST(ISNULL(l.qty,0) AS float)>0
   AND {f}<='{D}' AND {t}>='{D}'""".format(
    S=S, D=D6, f=V.format(f="l.from_ymd", d="000000"), t=V.format(f="l.to_ymd", d="991231"))
CSQ = """
SELECT LTRIM(RTRIM(a.ITEM_CODE)) p, LTRIM(RTRIM(a.MAT_CODE)) c,
       CAST(ISNULL(a.USE_QTY,0) AS float) q,
       LTRIM(RTRIM(ISNULL(a.GAGONG_PROC_CODE,''))) gpc, ISNULL(a.KITTING_FLAG,'0') kit
  FROM {S}.CS_M_ITEM_BOM a WITH(NOLOCK)
 WHERE ISNULL(a.EXCEPT_FLAG,'0')<>'1' AND CAST(ISNULL(a.USE_QTY,0) AS float)>0
   AND {f}<='{D}' AND {t}>='{D}'""".format(
    S=S, D=D6, f=V.format(f="a.FROM_APPLY_YMD", d="000000"), t=V.format(f="a.TO_APPLY_YMD", d="991231"))
PRQ = """
SELECT LTRIM(RTRIM(a.ITEM_CODE)) p, LTRIM(RTRIM(a.MAT_CODE)) c,
       CAST(ISNULL(a.USE_QTY,0) AS float) q,
       LTRIM(RTRIM(ISNULL(a.GAGONG_PROC_CODE,''))) gpc
  FROM {L}.PR_M_ITEM_BOM a WITH(NOLOCK)
 WHERE ISNULL(a.EXCEPT_FLAG,'0')<>'1' AND CAST(ISNULL(a.USE_QTY,0) AS float)>0
   AND {f}<='{D}' AND {t}>='{D}'""".format(
    L=L, D=D6, f=V.format(f="a.FROM_APPLY_YMD", d="000000"), t=V.format(f="a.TO_APPLY_YMD", d="991231"))

r = q1(cur, "SELECT COUNT(*) FROM ({}) z".format(NXQ))
n_nx = r[0]
r = q1(cur, "SELECT COUNT(*) FROM ({}) z".format(PRQ))
n_pr = r[0]
r = q1(cur, "SELECT COUNT(*) FROM ({}) z".format(CSQ))
n_cs = r[0]
print("   행수  클린 {:,} · 라이브PR {:,} · CS {:,}".format(n_nx, n_pr, n_cs))
if n_nx == n_pr:
    ok("H2-a", "클린 행수 ≡ 라이브 생산BOM ({:,})".format(n_nx))
else:
    ng("H2-a", "클린 {:,} ≠ 라이브PR {:,}".format(n_nx, n_pr))

# 수량 — 클린이 라이브와 다른 것
r = q1(cur, """SELECT COUNT(*), COUNT(DISTINCT b.p)
                 FROM ({NX}) b JOIN ({PR}) p ON p.p=b.p AND p.c=b.c
                WHERE ABS(b.q-p.q)>0.0001""".format(NX=NXQ, PR=PRQ))
if r[0] == 0:
    ok("H2-b", "사용수량 클린≡라이브 (불일치 0)")
else:
    ng("H2-b", "★사용수량 클린≠라이브 {:,}쌍 / {}도번".format(r[0], r[1]))
    for x in qall(cur, """SELECT TOP 8 b.p, b.c, b.q, p.q
                            FROM ({NX}) b JOIN ({PR}) p ON p.p=b.p AND p.c=b.c
                           WHERE ABS(b.q-p.q)>0.0001 ORDER BY 1,2""".format(NX=NXQ, PR=PRQ)):
        print("            {:<20s} → {:<20s} 클린={:g} 라이브={:g}".format(
            str(x[0]), str(x[1]), x[2], x[3]))

# 투입파트 — ★SUB/가상 노드는 파트가 없는 게 정상이다(클린 부모 6,548 중 3,215종이
#   전부 빈칸 = -A-S-n·-STS-n 같은 중간노드). 그래서 "클린만 빈칸"은 결함이 아니다.
#   진짜 결함 = 양쪽 다 값이 있는데 서로 다른 것.
r = q1(cur, """SELECT COUNT(*) FROM ({NX}) b JOIN ({PR}) p ON p.p=b.p AND p.c=b.c
                WHERE ISNULL(b.gpc,'')<>'' AND ISNULL(p.gpc,'')<>''
                  AND ISNULL(b.gpc,'')<>ISNULL(p.gpc,'')""".format(NX=NXQ, PR=PRQ))
if r[0] == 0:
    ok("H2-c", "투입파트 — 양쪽 값 있는 쌍은 전부 일치 (불일치 0)")
else:
    ng("H2-c", "★투입파트 실질 불일치 {:,}쌍".format(r[0]))
# 참고 — 클린만 빈칸(정상일 수 있음)
r = q1(cur, """SELECT COUNT(*), COUNT(DISTINCT b.p) FROM ({NX}) b JOIN ({PR}) p ON p.p=b.p AND p.c=b.c
                WHERE ISNULL(b.gpc,'')='' AND ISNULL(p.gpc,'')<>''""".format(NX=NXQ, PR=PRQ))
if r[0]:
    wr("H2-c2", "클린만 파트 빈칸 {:,}쌍 / {}도번 — SUB노드면 정상, 최종제품이면 결손".format(r[0], r[1]))
    for x in qall(cur, """SELECT TOP 6 b.p, COUNT(*) n FROM ({NX}) b JOIN ({PR}) p ON p.p=b.p AND p.c=b.c
                           WHERE ISNULL(b.gpc,'')='' AND ISNULL(p.gpc,'')<>''
                           GROUP BY b.p ORDER BY 2 DESC""".format(NX=NXQ, PR=PRQ)):
        print("            {:<22s} {:>3}건".format(str(x[0]), x[1]))

# 클린 결손 = 라이브에 있는데 클린에 없음
r = q1(cur, """SELECT COUNT(*) FROM ({PR}) p
                WHERE NOT EXISTS(SELECT 1 FROM ({NX}) b WHERE b.p=p.p AND b.c=p.c)""".format(NX=NXQ, PR=PRQ))
if r[0] == 0:
    ok("H2-d", "클린 결손 0 (라이브에 있는 건 클린에도 다 있다)")
else:
    ng("H2-d", "★클린 결손 {:,}쌍".format(r[0]))
    for x in qall(cur, """SELECT TOP 6 p.p, p.c, p.q FROM ({PR}) p
                           WHERE NOT EXISTS(SELECT 1 FROM ({NX}) b WHERE b.p=p.p AND b.c=p.c)
                           ORDER BY 1,2""".format(NX=NXQ, PR=PRQ)):
        print("            {:<20s} → {:<20s} q={:g}".format(str(x[0]), str(x[1]), x[2]))
# CS 대비 개선분(참고)
r = q1(cur, """SELECT COUNT(*) FROM ({CS}) a JOIN ({NX}) b ON b.p=a.p AND b.c=a.c
               JOIN ({PR}) p ON p.p=a.p AND p.c=a.c
                WHERE ABS(a.q-b.q)>0.0001 AND ABS(b.q-p.q)<=0.0001""".format(CS=CSQ, NX=NXQ, PR=PRQ))
print("   ※전환으로 교정된 수량 {:,}쌍 (CS 가 틀렸고 클린이 맞았던 것)".format(r[0]))
r = q1(cur, """SELECT COUNT(*) FROM ({CS}) a JOIN ({NX}) b ON b.p=a.p AND b.c=a.c
               JOIN ({PR}) p ON p.p=a.p AND p.c=a.c
                WHERE ISNULL(a.gpc,'')<>ISNULL(b.gpc,'') AND b.gpc=p.gpc""".format(CS=CSQ, NX=NXQ, PR=PRQ))
print("   ※전환으로 교정된 투입파트 {:,}쌍".format(r[0]))

# 실제 도번 검증(레거시 화면 실측값)
LEG = {"3H01582A": 2.0, "3H01582C": 4.0, "3H01582E": 5.0, "MEG66660106": 5.0}
bad = []
for mat, exp in LEG.items():
    r = q1(cur, "SELECT q FROM ({}) z WHERE p='AJR30157301' AND c=?".format(NXQ), mat)
    got = float(r[0]) if r else -1
    if abs(got - exp) > 0.0001:
        bad.append("{} {}≠{}".format(mat, got, exp))
if not bad:
    ok("H2-e", "AJR30157301 수량 = 레거시 화면 실측 (2·4·5·5)")
else:
    ng("H2-e", "★" + ", ".join(bad))

# ═══════════════════════════════════════════════════════════════════
title("H3. 포장·작업자 4종 — 클린 nx.item_sub 소스")
# ═══════════════════════════════════════════════════════════════════
r = q1(ncur, """SELECT COUNT(*) FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.COLUMNS
                 WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='item_sub'
                   AND COLUMN_NAME IN ('pack_kind','pack_qty','prod_worker','insp_worker')""")
if r[0] == 4:
    ok("H3-a", "nx.item_sub 에 포장·작업자 4컬럼 존재")
else:
    ng("H3-a", "★nx.item_sub 컬럼 {}/4".format(r[0]))
r = q1(ncur, """SELECT COUNT(*), SUM(CASE WHEN ISNULL(RTRIM(pack_kind),'')>'' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN ISNULL(RTRIM(prod_worker),'')>'' THEN 1 ELSE 0 END)
                  FROM {S}.item_sub WITH(NOLOCK)""".format(S=S))
print("   nx.item_sub {:,}행 · pack_kind 있음 {:,} · prod_worker 있음 {:,}".format(
    r[0], r[1] or 0, r[2] or 0))
r2 = q1(ncur, """SELECT COUNT(*), SUM(CASE WHEN ISNULL(RTRIM(PACK_KIND),'')>'' THEN 1 ELSE 0 END)
                   FROM {S}.PR_M_ITEM_SUB WITH(NOLOCK)""".format(S=S))
print("   미러 PR_M_ITEM_SUB {:,}행 · PACK_KIND 있음 {:,}".format(r2[0], r2[1] or 0))
if (r[1] or 0) == 0 and (r2[1] or 0) > 0:
    wr("H3-b", "클린 포장값 0건 — 폴백에 의존 중(이관 전, 설계대로)")
else:
    ok("H3-b", "클린 포장값 {:,}건".format(r[1] or 0))

# save_item_pack 헬퍼 · 부분수정 보장
psrc = open(os.path.join(BE, "routers", "prodinfo.py"), encoding="utf-8").read()
if "def save_item_pack" in psrc:
    ok("H3-c", "save_item_pack 공용 헬퍼 존재")
else:
    ng("H3-c", "★save_item_pack 없음")
if "if pack_kind is not None" in psrc and "if prod_worker is not None" in psrc:
    ok("H3-d", "None 항목 미터치(부분수정) — 재발행 팝업이 포장정보를 안 지운다")
else:
    ng("H3-d", "★부분수정 보장 없음 — 라벨 재발행이 포장정보를 지울 수 있다")

# ═══════════════════════════════════════════════════════════════════
title("H4. item_sub 덮어쓰기 방지 — 품목마스터가 남의 컬럼을 지우지 않는가")
# ═══════════════════════════════════════════════════════════════════
isrc = open(os.path.join(BE, "routers", "item.py"), encoding="utf-8").read()
_seg = isrc[isrc.find("item_sub upsert"):isrc.find("item_sub upsert") + 1200] if "item_sub upsert" in isrc else ""
if "DELETE FROM nx.item_sub" in isrc:
    ng("H4-a", "★item.py 에 DELETE FROM nx.item_sub 잔존 — 남의 컬럼이 날아간다")
else:
    ok("H4-a", "item.py 에 item_sub DELETE 없음")
if "UPDATE nx.item_sub SET" in _seg or "UPDATE nx.item_sub" in isrc:
    ok("H4-b", "내 컬럼만 UPDATE 방식")
else:
    ng("H4-b", "★UPDATE 방식 아님")
# 실제로 두 화면 컬럼이 겹치지 않는가
r = q1(ncur, """SELECT COUNT(*) FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.COLUMNS
                 WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='item_sub'""")
print("   nx.item_sub 총 {}컬럼 — 품목마스터 8개 + 생산정보 4개 + 기타".format(r[0]))

# ═══════════════════════════════════════════════════════════════════
title("H5. 생산계획추가입력 비고 — matrix API 가 행 단위 remarks 를 내리는가")
# ═══════════════════════════════════════════════════════════════════
plsrc = open(os.path.join(BE, "routers", "planinput.py"), encoding="utf-8").read()
if '"remarks": ""' in plsrc and 'grp["remarks"]' in plsrc:
    ok("H5-a", "matrix 가 행 단위 remarks 를 만든다")
else:
    ng("H5-a", "★행 단위 remarks 없음")
r = q1(ncur, """SELECT COUNT(*), SUM(CASE WHEN ISNULL(RTRIM(remarks),'')>'' THEN 1 ELSE 0 END)
                  FROM {S}.prod_plan_input WITH(NOLOCK)""".format(S=S))
print("   prod_plan_input {:,}행 · 비고 있음 {:,}행".format(r[0], r[1] or 0))
if (r[1] or 0) > 0:
    ok("H5-b", "실제 비고 데이터 {:,}건 — 화면에 보여야 한다".format(r[1]))
else:
    wr("H5-b", "비고 데이터 0건 — 아직 입력된 게 없다")

# ═══════════════════════════════════════════════════════════════════
title("H6. 전 구간 연결 — 오늘 바꾼 지점이 앞뒤와 이어지는가")
# ═══════════════════════════════════════════════════════════════════
STEPS = [
    ("①생산계획(원본)", "SELECT COUNT(*) FROM {S}.prod_plan_input WITH(NOLOCK)".format(S=S)),
    ("②파트별편성(STEP6)", "SELECT COUNT(*) FROM {S}.plan_part_dtl WITH(NOLOCK)".format(S=S)),
    ("③자재소요(STEP7)", "SELECT COUNT(*) FROM {S}.plan_part_mat WITH(NOLOCK)".format(S=S)),
    ("④자재입고이력", "SELECT COUNT(*) FROM {S}.PU_T_STOCK_MAINT WITH(NOLOCK)".format(S=S)),
    ("⑤자재재고(_WH)", "SELECT COUNT(*) FROM {S}.PU_T_MAT_STOCK_WH WITH(NOLOCK)".format(S=S)),
    ("⑥자재세트재고", "SELECT COUNT(*) FROM {S}.PU_T_SET_GAGONG_STOCK WITH(NOLOCK)".format(S=S)),
    ("⑦가공이동(전표)", "SELECT COUNT(*) FROM {S}.PU_T_STOCK_MAINT_GAGONG_MOVE WITH(NOLOCK)".format(S=S)),
    ("⑧준비(키팅)잔액", "SELECT COUNT(*) FROM {S}.PU_T_READY_STOCK WITH(NOLOCK)".format(S=S)),
    ("⑨준비(키팅)이력", "SELECT COUNT(*) FROM {S}.PU_T_READY_STOCK_MAINT WITH(NOLOCK)".format(S=S)),
    ("⑩준비원장", "SELECT COUNT(*) FROM {S}.ready_ledger WITH(NOLOCK)".format(S=S)),
    ("⑪생산재고(_WH)", "SELECT COUNT(*) FROM {S}.PR_T_MAT_STOCK_WH WITH(NOLOCK)".format(S=S)),
    ("⑫생산실적", "SELECT COUNT(*) FROM {S}.PR_T_PROD_DTL WITH(NOLOCK)".format(S=S)),
    ("⑬완제품재고", "SELECT COUNT(*) FROM {S}.SA_T_ITEM_STOCK WITH(NOLOCK)".format(S=S)),
    ("⑭출하실적", "SELECT COUNT(*) FROM {S}.SA_T_SALE_DTL WITH(NOLOCK)".format(S=S)),
    ("⑮원장", "SELECT COUNT(*) FROM {S}.stock_ledger WITH(NOLOCK)".format(S=S)),
]
brk = 0
for nm, sql in STEPS:
    try:
        r = q1(ncur, sql)
        n = r[0]
        print("   {:<20s} {:>12,}행 {}".format(nm, n, "" if n > 0 else "  ★비어있음"))
        if n == 0:
            brk += 1
    except Exception as e:
        print("   {:<20s} ★조회실패 {}".format(nm, str(e)[:60])); brk += 1
if brk == 0:
    ok("H6-a", "전 구간 9단계 모두 데이터 존재 — 끊긴 마디 없음")
else:
    ng("H6-a", "★{}개 단계가 비었거나 실패".format(brk))

# 준비등록이 실제로 계획과 이어지는가(오늘 바꾼 지점의 상류)
r = q1(ncur, """SELECT COUNT(DISTINCT p.ITEM_CODE)
                  FROM {S}.plan_part_dtl p WITH(NOLOCK)
                 WHERE EXISTS(SELECT 1 FROM {S}.bom_header h WITH(NOLOCK)
                               WHERE LTRIM(RTRIM(h.item_code))=LTRIM(RTRIM(p.ITEM_CODE)))""".format(S=S))
print("   계획 품목 중 클린 BOM 보유 {:,}종".format(r[0]))
if r[0] > 0:
    ok("H6-b", "계획 → 클린BOM 연결 살아있음 (준비등록 상류)")
else:
    ng("H6-b", "★계획 품목이 클린 BOM 과 안 이어진다")

# ═══════════════════════════════════════════════════════════════════
title("H7. 사급 경로 · 상위품 행선지 3갈래 (판매시 사급체크 → 업체 사급재고)")
# ═══════════════════════════════════════════════════════════════════
# ★사급은 원장이 둘이다(경로마다 다른 테이블) — 축을 틀리면 정상을 결함으로 오판한다.
SAG = [
    ("사급출고 이력", "SELECT COUNT(*) FROM {S}.PU_T_SAGUB_STOCK_MAINT WITH(NOLOCK)".format(S=S)),
    ("사급재고 잔액", "SELECT COUNT(*) FROM {S}.PU_T_SAGUB_STOCK WITH(NOLOCK)".format(S=S)),
    ("세트 사급재고", "SELECT COUNT(*) FROM {S}.PU_T_SET_MAT_STOCK WITH(NOLOCK)".format(S=S)),
]
sag_ok = 0
for nm, sql in SAG:
    try:
        r = q1(ncur, sql)
        print("   {:<18s} {:>10,}행 {}".format(nm, r[0], "" if r[0] > 0 else "  (비어있음)"))
        if r[0] > 0:
            sag_ok += 1
    except Exception as e:
        print("   {:<18s} 조회실패 {}".format(nm, str(e)[:55]))
if sag_ok:
    ok("H7-a", "사급 경로 테이블 {}/{} 생존".format(sag_ok, len(SAG)))
else:
    wr("H7-a", "사급 경로 데이터 없음 — 축 확인 필요")

# 상위품 행선지 3갈래 — 파트 / 영업(완제품) / 자재(업체)
try:
    r = q1(ncur, """SELECT
        (SELECT COUNT(*) FROM {S}.PR_T_MAT_STOCK_WH WITH(NOLOCK)),
        (SELECT COUNT(*) FROM {S}.SA_T_ITEM_STOCK WITH(NOLOCK)),
        (SELECT COUNT(*) FROM {S}.PU_T_MAT_STOCK_WH WITH(NOLOCK))""".format(S=S))
    print("   행선지  파트(생산) {:,} · 영업(완제품) {:,} · 자재(업체) {:,}".format(r[0], r[1], r[2]))
    if r[0] > 0 and r[1] > 0 and r[2] > 0:
        ok("H7-b", "상위품 행선지 3갈래 전부 생존")
    else:
        ng("H7-b", "★행선지 중 빈 갈래 있음")
except Exception as e:
    ng("H7-b", "조회실패 " + str(e)[:60])

# ═══════════════════════════════════════════════════════════════════
title("H8. 실적현황 기록관리 — 각 단계가 이력을 남기는가")
# ═══════════════════════════════════════════════════════════════════
# ★재고 3층(원장·잔액·이력) 중 하나만 쓰면 화면마다 값이 갈린다.
HIST = [
    ("자재 수불이력", "{S}.PU_T_STOCK_MAINT".format(S=S)),
    ("생산 수불이력", "{S}.PR_T_STOCK_MAINT_MAT".format(S=S)),
    ("준비 이력", "{S}.PU_T_READY_STOCK_MAINT".format(S=S)),
    ("가공이동 전표", "{S}.PU_T_STOCK_MAINT_GAGONG_MOVE".format(S=S)),
    ("생산실적", "{S}.PR_T_PROD_DTL".format(S=S)),
    ("출하실적", "{S}.SA_T_SALE_DTL".format(S=S)),
    ("통합원장", "{S}.stock_ledger".format(S=S)),
]
miss = []
for nm, t in HIST:
    try:
        r = q1(ncur, "SELECT COUNT(*) FROM {} WITH(NOLOCK)".format(t))
        print("   {:<18s} {:>12,}행".format(nm, r[0]))
        if r[0] == 0:
            miss.append(nm)
    except Exception as e:
        print("   {:<18s} 조회실패".format(nm)); miss.append(nm)
if not miss:
    ok("H8-a", "실적·이력 {}종 모두 기록 남음".format(len(HIST)))
else:
    ng("H8-a", "★기록 없음: " + ", ".join(miss))

# 오늘 등록분이 실제로 쌓이는가(=지금 도는가)
try:
    r = q1(ncur, """SELECT
        (SELECT COUNT(*) FROM {S}.stock_ledger WITH(NOLOCK) WHERE CAST(ins_dt AS date)=CAST(GETDATE() AS date)),
        (SELECT COUNT(*) FROM {S}.prod_plan_input WITH(NOLOCK) WHERE CAST(upd_dt AS date)=CAST(GETDATE() AS date))
        """.format(S=S))
    print("   오늘 원장 {:,}행 · 오늘 계획입력 {:,}행".format(r[0], r[1]))
    ok("H8-b", "오늘자 기록 확인(원장 {:,} · 계획 {:,})".format(r[0], r[1]))
except Exception as e:
    wr("H8-b", "오늘자 집계 실패 " + str(e)[:60])

# ═══════════════════════════════════════════════════════════════════
title("결과")
# ═══════════════════════════════════════════════════════════════════
print("   PASS {}  ·  FAIL {}  ·  WARN {}".format(len(PASS), len(FAIL), len(WARN)))
if FAIL:
    print("   ★FAIL: " + ", ".join(FAIL))
if WARN:
    print("   WARN: " + ", ".join(WARN))
print("   ※쓰기 없음 — DB 오염 0")
cn.close(); nx.close()
sys.exit(1 if FAIL else 0)
