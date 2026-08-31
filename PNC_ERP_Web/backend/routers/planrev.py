# -*- coding: utf-8 -*-
"""생산계획업로드(검토) 전용 라우터 — 레거시 w_pr_plan_020 식 단계별 실행.

★★설계 원칙 (2026-08-26)
  1) soyo.py 는 한 글자도 고치지 않는다. 현행 화면(생산계획업로드)은 그대로 돌아간다.
  2) 이 파일은 soyo.py 의 편성 파이프라인을 '원문 그대로' 복사한 사본이다.
     SQL 문자열을 바꾸지 않는다. 바꿔야 하면 그 줄에 `# ★검토본 변경:` 주석을 단다.
  3) 두 파이프라인이 같은 nx 산출 테이블에 쓴다(의도) → CHECKSUM 으로 직접 대사 가능.
     대신 동시실행 락(_lock_or_raise)이 필수.

레거시 대응 단계
  M 신규모델검색및생성 / H 생산계획이력생성 / L 라인별투입시간조정(미구현)
  I+K 파트별계획생성(STEP5+STEP6) / T 자재소요·조달편성(STEP7+오버레이) / S 협력사계획 / Z 일괄

복사 출처: soyo.py plan_compose_mat(:17-162) · _step6_sql(:458) · _step7_sql(:548)
           _ROUTE_GATE_SQL(:494) · _ensure_profile_price(:500) · _route_gate_incomplete(:506) · _route_setup(:530)
"""
import time
from fastapi import APIRouter, Query, Body, HTTPException
from common import _nx

router = APIRouter()

_P = "nx."   # soyo.py:15 동일


# ═══════════════════════════════════════════════════════════════════════
# soyo.py 복사분 — SQL 원문 동일 (수정 금지)
# ═══════════════════════════════════════════════════════════════════════

# ★★활성 게이트(§19-C·2026-08-25 사용자 확정): 활성 지정 Rnn(current_flag=1·route_no>1)이 아래 4개 다 갖춰야 계획 활성.
#   ①승인 approve_flag=1 ②구조 route_edges ③업체 sourcing_profile.vendor ④단가 buy_price/sagub_price.
#   ★한 곳 정의(_ROUTE_GATE_SQL) → _route_setup(생산·협력사 plan_route_active)·_route_gate_incomplete(편성 사전검증 D)·원가 공유.
#   미완성 Rnn은 어디서도 안 켜짐 → R01(route_no=1) 현행 그대로. h=nx.sourcing_route 별칭 전제.
_ROUTE_GATE_SQL = """ISNULL(h.approve_flag,0)=1
      AND EXISTS(SELECT 1 FROM nx.route_edges re WHERE re.route_id=h.route_id)
      AND EXISTS(SELECT 1 FROM nx.sourcing_profile p WHERE p.route_id=h.route_id AND ISNULL(p.vendor_code,'')<>'')
      AND EXISTS(SELECT 1 FROM nx.sourcing_profile p WHERE p.route_id=h.route_id AND (p.buy_price IS NOT NULL OR p.sagub_price IS NOT NULL))"""


def _ensure_profile_price(cur):
    """게이트 SQL이 참조하는 sourcing_profile 단가컬럼 멱등 보장(신선 nx 대비)."""
    cur.execute("IF OBJECT_ID('nx.sourcing_profile','U') IS NOT NULL AND COL_LENGTH('nx.sourcing_profile','buy_price') IS NULL ALTER TABLE nx.sourcing_profile ADD buy_price FLOAT NULL")
    cur.execute("IF OBJECT_ID('nx.sourcing_profile','U') IS NOT NULL AND COL_LENGTH('nx.sourcing_profile','sagub_price') IS NULL ALTER TABLE nx.sourcing_profile ADD sagub_price FLOAT NULL")


def _route_gate_incomplete(cur):
    """★D 사전검증(§19-D): 활성 지정된 Rnn(route_alloc.is_active=1·route_no>1) 중 게이트(§19-C) 미충족 목록+사유.
       ★활성지정 단일소스 = nx.route_alloc.is_active(조달프로파일 택1) — _route_setup과 동일 스위치(2026-08-31 통일).
       반환 [{route_id,item,route_no,route_name,missing[]}]. 편성(compose)이 이걸로 업로드 실패·정확 메시지·중단."""
    _ensure_profile_price(cur)
    cur.execute("""IF OBJECT_ID('nx.route_alloc','U') IS NULL CREATE TABLE nx.route_alloc(
        item_code NVARCHAR(60) NOT NULL, route_id INT NOT NULL, apply_from DATE NULL, apply_to DATE NULL,
        is_active BIT DEFAULT 0, alloc_ratio FLOAT NULL, upd_dt datetime DEFAULT getdate(),
        CONSTRAINT PK_nx_route_alloc PRIMARY KEY(item_code, route_id))""")
    cur.execute("""SELECT h.route_id, LTRIM(RTRIM(h.item_code)), ISNULL(h.route_no,1), ISNULL(h.route_name,''),
          ISNULL(h.approve_flag,0),
          (SELECT COUNT(*) FROM nx.route_edges re WHERE re.route_id=h.route_id),
          (SELECT COUNT(*) FROM nx.sourcing_profile p WHERE p.route_id=h.route_id AND ISNULL(p.vendor_code,'')<>''),
          (SELECT COUNT(*) FROM nx.sourcing_profile p WHERE p.route_id=h.route_id AND (p.buy_price IS NOT NULL OR p.sagub_price IS NOT NULL))
        FROM nx.sourcing_route h
        JOIN nx.route_alloc ra ON ra.route_id=h.route_id AND ISNULL(ra.is_active,0)=1
        WHERE ISNULL(h.route_no,1)>1""")
    bad = []
    for rid, item, rno, rname, appr, ne, nv, npx in cur.fetchall():
        miss = []
        if not int(appr or 0): miss.append("미승인")
        if not int(ne or 0): miss.append("구조 미반영(저장 안 됨)")
        if not int(nv or 0): miss.append("업체 미지정")
        if not int(npx or 0): miss.append("단가 미지정")
        if miss:
            bad.append({"route_id": int(rid), "item": str(item).strip(), "route_no": int(rno),
                        "route_name": str(rname).strip(), "missing": miss})
    return bad


def _route_setup(cur):
    """★조달경로 반영 인프라(2026-08-24, 게이트강화 2026-08-25). 매일 rebuild(compose_mat)에서 STEP7 직전 호출.
    - nx.route_edges(route_id,item_code,mat_code,use_qty_pr): 경로별 BOM엣지(Rnn 저장시 자동등록·§19-A). 없으면 fallback.
    - nx.plan_route_active(assy_item_code,route_id): ★활성 게이트(§19-C) 통과한 Rnn만.
      ★활성지정 단일소스 = nx.route_alloc.is_active(조달프로파일 택1 라디오·2026-08-31 통일). 구조축(여기)·배분축(plan_mat_source) 동일 스위치.
      route_no>1 + 게이트(승인·route_edges·업체·단가) 통과분만. 기본 비어있음=전 제품 v_pr_bom(현행)=R01 diff0(가산적).
      ★안전=활성경로 없으면 STEP7 출력 현행과 byte동일(검증 300WO 100.000%)."""
    _ensure_profile_price(cur)
    cur.execute("""IF OBJECT_ID('nx.route_alloc','U') IS NULL CREATE TABLE nx.route_alloc(
        item_code NVARCHAR(60) NOT NULL, route_id INT NOT NULL, apply_from DATE NULL, apply_to DATE NULL,
        is_active BIT DEFAULT 0, alloc_ratio FLOAT NULL, upd_dt datetime DEFAULT getdate(),
        CONSTRAINT PK_nx_route_alloc PRIMARY KEY(item_code, route_id))""")   # ★활성소스
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

def _step6_sql(cur):
    P = _P
    # ★STEP6 는 v_pr_bom(뷰) 그대로 — 스냅을 적용했더니 47초→193초로 **느려졌다**(2026-08-27 실측).
    #   STEP6 재귀는 level_no<10 으로 얕고 PR_M_ITEM/PR_M_MAT 조인이 함께 걸려
    #   옵티마이저가 뷰 쪽에서 더 나은 계획을 잡는다. STEP7 과 반대이므로 건드리지 않는다.
    cur.execute("IF OBJECT_ID('nx.plan_part_temp') IS NOT NULL DROP TABLE nx.plan_part_temp")
    cur.execute(("""
    WITH CTE_BOM(assy_item_code, level_no, item_code, p_item_code, mat_code, cum_use_qty, in_cust_code, vir_item_flag, cum_item_code) AS (
      SELECT DISTINCT a.c_item_code,0,a.c_item_code,a.c_item_code,a.c_item_code,CONVERT(decimal(18,5),1),ISNULL(c.in_cust_code,''),'0',CONVERT(varchar(500),'{'+a.c_item_code+'}')
      FROM nx.plan_item_dtl a JOIN {P}PR_M_ITEM c ON a.c_item_code=c.item_code
      WHERE NOT EXISTS(SELECT 1 FROM {P}PR_M_MAT WHERE mat_code=a.c_item_code)
      UNION ALL
      SELECT cb.assy_item_code,cb.level_no+1,b.item_code,CASE cb.vir_item_flag WHEN '1' THEN cb.p_item_code ELSE b.item_code END,
             b.mat_code,CONVERT(decimal(18,5),cb.cum_use_qty*b.USE_QTY_PR),ISNULL(c.in_cust_code,''),
             CASE b.vir_item_flag WHEN '1' THEN '1' ELSE '0' END,CONVERT(varchar(500),cb.cum_item_code+'{'+b.mat_code+'}')
      FROM CTE_BOM cb JOIN {P}v_pr_bom b ON cb.mat_code=b.item_code JOIN {P}PR_M_ITEM c ON b.mat_code=c.item_code
      WHERE ISNULL(b.except_flag,'0')<>'1' AND cb.level_no<10 AND NOT EXISTS(SELECT 1 FROM {P}PR_M_MAT WHERE mat_code=b.mat_code))
    SELECT assy_item_code,level_no,item_code,MAX(p_item_code) p_item_code,mat_code,SUM(cum_use_qty) cum_use_qty,MAX(in_cust_code) in_cust_code,MAX(vir_item_flag) vir_item_flag
    INTO nx.plan_part_temp FROM CTE_BOM GROUP BY assy_item_code,level_no,item_code,mat_code OPTION(MAXRECURSION 0)""").replace("{P}", P))
    cur.execute("IF OBJECT_ID('nx.plan_part_gagong') IS NOT NULL DROP TABLE nx.plan_part_gagong")
    cur.execute(("""SELECT a.assy_item_code,a.level_no,a.item_code,a.mat_code,a.p_item_code,a.vir_item_flag,b.proc_seq,g.gc_gubun,a.cum_use_qty,s.gagong_proc_code,b.gagong_proc_seq,b.s_work_code,ISNULL(b.lt_hr,0) lt_hr
    INTO nx.plan_part_gagong FROM nx.plan_part_temp a
    JOIN {P}PR_M_ITEM_PROC_GAGONG b ON a.mat_code=b.item_code JOIN {P}PR_M_WORK_SINGLE s ON b.s_work_code=s.s_work_code JOIN {P}PR_M_PROC_GAGONG g ON s.gagong_proc_code=g.gagong_proc_code
    WHERE a.vir_item_flag='0' AND ISNULL(a.in_cust_code,'') IN ('','2228')""").replace("{P}", P))
    # ★검토본 변경(2026-08-26): 레거시 SP 원문대로 **가상품목도 행으로 넣는다**(PROC_SEQ=0·LT_HR=0).
    #   그래야 SUB-1/SUB-2 같은 가상 중간노드가 남아 CUM_LT_HR 누적 경로가 이어진다.
    #   레거시는 누적을 끝낸 뒤 `DELETE ... WHERE VIR_ITEM_FLAG='1'` 로 제거한다(아래 STEP6 끝).
    cur.execute("""INSERT INTO nx.plan_part_gagong
        (assy_item_code, level_no, item_code, mat_code, p_item_code, vir_item_flag,
         proc_seq, gc_gubun, cum_use_qty, gagong_proc_code, gagong_proc_seq, s_work_code, lt_hr)
      SELECT a.assy_item_code, a.level_no, a.item_code, a.mat_code, a.p_item_code, a.vir_item_flag,
             0, '', a.cum_use_qty, NULL, NULL, NULL, 0
        FROM nx.plan_part_temp a WHERE a.vir_item_flag='1'""")

    # ── ★CUM_LT_HR 누적 (레거시 SP 원문: 레벨 0..9 순차 확정) ──
    #   update a set CUM_LT_HR =
    #       (자기 이후공정 LT 합: 같은 assy·level·item·mat 에서 proc_seq >= 자기)
    #     + (부모 CUM: 상위레벨(level-1) 에서 **mat_code = 자기 item_code** 인 행의 top1, proc_seq asc)
    #   ★부모를 p_item_code 로 찾으면 안 된다 — 레거시는 '상위레벨의 mat_code' 로 잇는다.
    #   ★가상품목 행이 여기 있어야(위 INSERT) SUB-1/SUB-2 를 거치는 누적 경로가 이어진다.
    cur.execute("IF COL_LENGTH('nx.plan_part_gagong','cum_lt_hr') IS NULL"
                " ALTER TABLE nx.plan_part_gagong ADD cum_lt_hr decimal(9,2)")
    cur.execute("UPDATE nx.plan_part_gagong SET cum_lt_hr=0")
    cur.execute("CREATE INDEX ix_ppg1 ON nx.plan_part_gagong(assy_item_code, level_no, item_code, mat_code, proc_seq)")
    cur.execute("CREATE INDEX ix_ppg2 ON nx.plan_part_gagong(assy_item_code, level_no, mat_code, proc_seq)")
    for _lv in range(0, 10):
        cur.execute("""UPDATE a
           SET cum_lt_hr =
                 (SELECT ISNULL(SUM(b.lt_hr),0) FROM nx.plan_part_gagong b
                   WHERE b.assy_item_code=a.assy_item_code AND b.level_no=a.level_no
                     AND b.item_code=a.item_code AND b.mat_code=a.mat_code
                     AND b.proc_seq >= a.proc_seq)
               + ISNULL((SELECT TOP 1 b.cum_lt_hr FROM nx.plan_part_gagong b
                          WHERE b.assy_item_code=a.assy_item_code AND b.level_no=a.level_no-1
                            AND b.mat_code=a.item_code
                          ORDER BY b.proc_seq ASC),0)
          FROM nx.plan_part_gagong a WHERE a.level_no=?""", _lv)

    # ★레거시: 리드타임 누적이 끝나면 가상도번 정보를 삭제한다.
    #   DELETE FROM PR_T_PLAN_PART_GAGONG_TEMP WHERE VIR_ITEM_FLAG='1'
    #   (누적 경로 유지용으로만 넣었던 행이므로 산출물에는 남기지 않는다)
    cur.execute("DELETE FROM nx.plan_part_gagong WHERE vir_item_flag='1'")
    cur.execute("IF OBJECT_ID('nx.plan_part_swork') IS NOT NULL DROP TABLE nx.plan_part_swork")
    cur.execute(("""SELECT b.plan_ymd,b.work_order,b.split_work_order,a.assy_item_code,a.level_no AS bom_level,a.item_code AS upper_item_code,a.mat_code AS item_code,a.p_item_code,a.proc_seq,a.gc_gubun,
      b.line_no,a.cum_use_qty AS use_qty,b.lot_qty,CEILING(CONVERT(float,b.plan_qty)*ISNULL(b.use_qty,1)*ISNULL(CASE WHEN b.work_order LIKE 'WO%' THEN 100 ELSE c.prod_rate END,100)/100) AS plan_qty,
      a.gagong_proc_code,a.gagong_proc_seq,a.s_work_code,a.lt_hr,ISNULL(a.cum_lt_hr,0) AS cum_lt_hr,CEILING(CONVERT(float,b.plan_qty)*ISNULL(b.use_qty,1)*ISNULL(CASE WHEN b.work_order LIKE 'WO%' THEN 100 ELSE c.prod_rate END,100)/100)*a.cum_use_qty AS part_plan_qty
    INTO nx.plan_part_swork FROM nx.plan_part_gagong a JOIN nx.plan_item_dtl b ON a.assy_item_code=b.c_item_code JOIN {P}PR_M_ITEM c ON a.assy_item_code=c.item_code""").replace("{P}", P))
    cur.execute("IF OBJECT_ID('nx.plan_part_dtl') IS NOT NULL DROP TABLE nx.plan_part_dtl")
    cur.execute("""SELECT a.* INTO nx.plan_part_dtl FROM nx.plan_part_swork a
      WHERE a.gagong_proc_code <> ISNULL((SELECT TOP 1 b.gagong_proc_code FROM nx.plan_part_swork b
        WHERE b.plan_ymd=a.plan_ymd AND b.work_order=a.work_order AND b.split_work_order=a.split_work_order AND b.assy_item_code=a.assy_item_code
          AND b.bom_level=a.bom_level AND b.upper_item_code=a.upper_item_code AND b.item_code=a.item_code AND b.proc_seq<a.proc_seq ORDER BY b.proc_seq DESC),'')""")

def _ensure_bom_snap(cur):
    """★nx.v_pr_bom(뷰) 물질화 — STEP7 재귀 CTE 성능(2026-08-27).

    v_pr_bom 은 bom_header/bom_line + proc_weld 를 UNION 하는 뷰라
    재귀 CTE 가 **반복마다 다시 평가**한다. STEP7 CTE 실측:
        뷰 516.9초 → 물질화 4.2초  = **123배**(절감 513초)
        재생성 비용 4.72초(SELECT INTO 4.59 + 인덱스 0.14) — 일회성
        조인 1회 기준으로도 1.36초 → 0.04초, 결과 73,052행 불일치 0
    ⑤가 457초(④의 10배)인 주된 원인이 이 반복 평가였다.
    ※NOT EXISTS 인덱스는 효과 없음(517.0 → 516.5초) — 병목이 아니었다.
    ※★STEP6 에는 적용하지 않는다 — 거기선 오히려 47초→193초로 느려진다(본문 주석 참조).

    ★매 실행마다 새로 만든다 — 기존 nx.plan_bom_snap 은 낡아서
      except_flag 28건·qty 44건이 뷰와 달랐다(오늘 BOM 수정분 미반영).
      낡은 스냅을 재사용하면 편성 결과가 조용히 틀어지므로 절대 캐시하지 않는다."""
    cur.execute("IF OBJECT_ID('nx.plan_bom_snap') IS NOT NULL DROP TABLE nx.plan_bom_snap")
    # ※EXCEPT_FLAG 를 CS_CALC_EXCEPT_FLAG 로 바꾸지 말 것 — 2026-08-31 실측으로 기각됨.
    #   동기: 레거시 SP(_legacy_analysis/SP_CS_견적서_실원가용_250910.sql:188-193)는
    #         where isnull(b.CS_CALC_EXCEPT_FLAG,'0') <> '1' 로 끊고,
    #         ⑤ 자재소요가 레거시 대비 −156,329(자재 201종) 과소계상돼 있었다.
    #   결과: 그대로 바꿨더니 오히려 +999,157 로 악화(웹에만 22,081키).
    #         AJR30077403 에서 -F&T·-12-1·-4-2 가 동시에 열려 전 경로가 중복 계상됐다.
    #   해석: 웹 bom_line 은 두 플래그를 상보적으로 쓴다(현행경로=except_flag, 원가제외=cs_calc_except).
    #         한쪽만으로 끊으면 과소(ef 단독) 또는 과다(cs 단독)가 된다.
    #         ⑤ 정합은 플래그 교체가 아니라 전개 규칙 자체를 다시 봐야 한다.
    #   ★STEP6(_step6_sql:105)도 EXCEPT_FLAG 유지 — ④ 파트별은 전 기간 diff0 이다.
    cur.execute("""SELECT ITEM_CODE AS item_code, MAT_CODE AS mat_code, USE_QTY_PR,
           EXCEPT_FLAG AS except_flag, VIR_ITEM_FLAG AS vir_item_flag
      INTO nx.plan_bom_snap FROM nx.v_pr_bom""")
    cur.execute("""CREATE INDEX ix_plan_bom_snap ON nx.plan_bom_snap(item_code)
      INCLUDE(mat_code, USE_QTY_PR, except_flag, vir_item_flag)""")


def _step7_sql(cur):
    P = _P
    _ensure_bom_snap(cur)          # ★BOM 물질화(뷰 반복평가 제거)
    # ★routing_edge 생산처 오버라이드(2026-08-20): STEP7 work_center(생산처)를 마스터 대신
    #   routing_edge.wc(편집가능 정본)에서 읽음. ov_wc=ISNULL(routing_edge.wc, 마스터 default).
    #   routing_edge 미등록 아이템은 마스터 폴백. compose는 읽기만(편집 보존) — 시드/싱크는 별도.
    #   재귀 CTE는 TOP/outer join 금지 → 오버라이드 테이블 nx.item_ov를 inner join으로 갈아끼움.
    cur.execute("IF OBJECT_ID('nx.item_ov') IS NOT NULL DROP TABLE nx.item_ov")
    cur.execute(("""SELECT c.item_code, c.work_code, c.in_cust_code, c.prod_rate,
        ISNULL(NULLIF(re.wc,''), CASE WHEN c.work_code>'' THEN c.work_code ELSE ISNULL(c.in_cust_code,'') END) AS ov_wc
      INTO nx.item_ov FROM {P}PR_M_ITEM c
      LEFT JOIN (SELECT child_item, MAX(wc) wc FROM nx.routing_edge GROUP BY child_item) re
        ON re.child_item=UPPER(LTRIM(RTRIM(c.item_code)))""").replace("{P}", P))
    cur.execute("CREATE INDEX ix_item_ov ON nx.item_ov(item_code)")
    # ※plan_part_dtl 인덱스는 넣지 않는다 — 실측 효과 0(517.0초 → 516.5초).
    #   병목은 NOT EXISTS 가 아니라 v_pr_bom(뷰) 반복 평가였다(아래 _ensure_bom_snap).
    # ★★조달경로(route) 반영 인프라(2026-08-24, 가산적): 활성 대체경로(sourcing_route current_flag=1·route_no>1) 있으면
    #   그 경로의 BOM엣지(route_edges)로 전개, 없으면 v_pr_bom(현행 except<>1) fallback=R01 diff0(검증: route CTE≡원본 100.000%).
    _route_setup(cur)
    # ★★직납품 당김(2026-08-27) — 레거시 「LINE-NO MASTER」의 '직납품당김일자'(PR_M_LINE_NO.CUST_MAINT_DAY).
    #   파트별계획이 없는 도번(=직납품)은 라인의 CUST_MAINT_DAY 만큼 **근무일 기준으로 추가 당김**된다.
    #   레거시 SP_PR_4주간계획현황_LIVE 167행과 동일 산식:
    #     IIF(L.CUST_MAINT_DAY>0, f_reld_doosung_live(a.plan_ymd, L.CUST_MAINT_DAY*-1), a.plan_ymd)
    #   실측 근거: ASSY행 불일치 619건 중 516건이 라인 CA — CA 가 CUST_MAINT_DAY=1 을 가진 유일한 라인,
    #             그중 420건이 정확히 +1일 차이였다.
    #   근무일 = 공통달력(HR_M_CALENDAR 팀A·주간, work_stats 1/2/5/6/7). 직납품은 파트가 없으므로 공통 사용.
    cur.execute("IF OBJECT_ID('tempdb..#wd') IS NOT NULL DROP TABLE #wd")
    cur.execute("""SELECT ymd6, ROW_NUMBER() OVER(ORDER BY ymd6) rn INTO #wd FROM
        (SELECT SUBSTRING(calendar_yymd,3,6) ymd6, work_stats FROM nx.HR_M_CALENDAR
          WHERE work_team='A' AND time_type='A') c
        WHERE work_stats IN ('1','2','5','6','7')""")
    cur.execute("CREATE INDEX ix_wd ON #wd(ymd6)")
    cur.execute("CREATE INDEX ix_wd_rn ON #wd(rn)")
    #   ⚠출발점은 **라인당김이 적용된 일자**(plan_line_pull.pulled)여야 한다 — STEP5(384행)와 같은 기준.
    #     plan_dtl.PLAN_YMD(원본)에서 당기면 라인당김이 빠져 어긋난다(실측: 웹 dtl 이 라이브보다 +1/+3/+5일).
    cur.execute("IF OBJECT_ID('nx.plan_direct_pull') IS NOT NULL DROP TABLE nx.plan_direct_pull")
    _has_lp = int(cur.execute(
        "SELECT CASE WHEN OBJECT_ID('nx.plan_line_pull') IS NULL THEN 0 ELSE 1 END").fetchone()[0] or 0)
    _base = "ISNULL(p.pulled, d.PLAN_YMD)" if _has_lp else "d.PLAN_YMD"
    _lpj = ("LEFT JOIN nx.plan_line_pull p ON p.wo=d.WORK_ORDER AND p.org=d.PLAN_YMD"
            if _has_lp else "")
    cur.execute(("""SELECT RTRIM(d.WORK_ORDER) AS work_order, w2.ymd6 AS pull_ymd
      INTO nx.plan_direct_pull
      FROM nx.plan_dtl d
      {LPJ}
      JOIN {P}PR_M_LINE_NO L ON RTRIM(L.LINE_NO)=RTRIM(d.LINE_NO) AND ISNULL(L.CUST_MAINT_DAY,0)>0
      JOIN #wd w1 ON w1.ymd6={BASE}
      JOIN #wd w2 ON w2.rn=w1.rn-CAST(L.CUST_MAINT_DAY AS int)
     WHERE ISNULL(d.PLAN_YMD,'')<>''""").replace("{P}", P).replace("{LPJ}", _lpj).replace("{BASE}", _base))
    cur.execute("CREATE INDEX ix_plan_direct_pull ON nx.plan_direct_pull(work_order)")
    cur.execute("IF OBJECT_ID('nx.plan_part_mat_tmp') IS NOT NULL DROP TABLE nx.plan_part_mat_tmp")
    # ★★자재소요 일자 = **당김 후**(part_plan_ymd) — 2026-08-27 추가.
    #   레거시 PR_T_PLAN_PART_MAT 은 날짜를 2벌 갖는다:
    #     PLAN_YMD/OUTPUT_HM/AMPM           = 상위 계획(당김 전)
    #     PART_PLAN_YMD/PART_OUTPUT_HM/...  = ★당김 후 소요일시  ← 자재는 이걸 봐야 한다
    #   실측: 레거시 MAT 안에서 두 컬럼이 81.53% 다르고, MAT.PART_PLAN_YMD 는
    #        PART.PART_PLAN_YMD 와 72.95% 일치(나머지는 하위전개분).
    #   종전 웹은 plan_ymd 하나뿐이라 당김이 자재로 전달되지 않았다(사용자 지적).
    #   → CTE 에 part_plan_ymd·part_output_hm 을 함께 실어 최하위까지 내려보낸다.
    #     상위앵커(plan_part_dtl)는 자기 당김값, 재귀 하위는 부모값을 그대로 상속한다
    #     (레거시도 하위자재는 그 부모 파트의 소요일시를 따른다).
    cur.execute(("""
    WITH CTE_BOM(plan_ymd,part_plan_ymd,part_output_hm,work_order,split_work_order,assy_item_code,bom_level,upper_item_code,item_code,proc_seq,bom_mat_code,mat_work_center_code,cum_use_qty,cum_in_cust_code,mat_flag,use_qty,part_plan_qty,gc_gubun,cust_flag) AS (
      SELECT a.plan_ymd,ISNULL(NULLIF(a.part_plan_ymd,''),a.plan_ymd),ISNULL(a.part_output_hm,''),
         a.work_order,a.split_work_order,a.assy_item_code,a.bom_level,a.upper_item_code,a.item_code,a.proc_seq,a.item_code,
         c.ov_wc,CONVERT(decimal(18,5),a.use_qty),
         CONVERT(varchar(500),'||'+c.ov_wc+'|'),'1',a.use_qty,CONVERT(float,a.part_plan_qty)/NULLIF(a.use_qty,0),a.gc_gubun,'0'
      FROM nx.plan_part_dtl a JOIN nx.item_ov c ON a.item_code=c.item_code WHERE a.proc_seq=1
      UNION ALL
      -- ★직납품(파트별계획 없음) 앵커: 소요일자에 라인 CUST_MAINT_DAY(직납품당김일자) 적용.
      --   ★2026-08-31 교정: plan_ymd 도 **함께** 당긴다(종전엔 part_plan_ymd 만 당겼다).
      --   실측 — 레거시와 어긋난 레벨0 1,199건이 전부 LINE_NO='CA' · GAGONG_PROC='' 이고,
      --          그중 1,180건이 '웹 part_plan_ymd == 레거시 plan_ymd' 였다.
      --          즉 레거시는 직납품 앵커에서 두 컬럼을 같은 당김값으로 넣는다.
      --          (CA = CUST_MAINT_DAY 를 가진 유일한 라인)
      SELECT ISNULL(dp.pull_ymd,a.plan_ymd),ISNULL(dp.pull_ymd,a.plan_ymd),ISNULL(a.OUTPUT_HM,''),
         a.work_order,a.split_work_order,a.c_item_code,0,a.c_item_code,a.c_item_code,1,a.c_item_code,
         c.ov_wc,CONVERT(decimal(18,5),a.use_qty),
         CONVERT(varchar(500),'||'+c.ov_wc+'|'),'1',a.use_qty,CEILING(CONVERT(float,a.plan_qty)*ISNULL(a.use_qty,1)*ISNULL(CASE WHEN a.work_order LIKE 'WO%' THEN 100 ELSE c.prod_rate END,100)/100),'','1'
      FROM nx.plan_item_dtl a JOIN nx.item_ov c ON a.c_item_code=c.item_code
      -- ★2026-08-31: plan_direct_pull 에 제번당 2행인 것이 18개 있어 LEFT JOIN 이
      --   앵커를 2배로 불렸다(⑤ 이중계상 — AJJ30041902-SUB 60→120 등).
      --   MIN 으로 묶어 제번당 1행만 매칭한다(가장 이른 당김일 = 소요 기준).
      LEFT JOIN (SELECT RTRIM(work_order) AS work_order, MIN(pull_ymd) AS pull_ymd
                   FROM nx.plan_direct_pull GROUP BY RTRIM(work_order)) dp
             ON dp.work_order=RTRIM(a.work_order)
      WHERE NOT EXISTS(SELECT 1 FROM nx.plan_part_dtl d WHERE d.work_order=a.work_order AND d.split_work_order=a.split_work_order AND d.item_code=a.c_item_code)
      UNION ALL
      SELECT cb.plan_ymd,cb.part_plan_ymd,cb.part_output_hm,
         cb.work_order,cb.split_work_order,cb.assy_item_code,cb.bom_level,cb.upper_item_code,cb.item_code,cb.proc_seq,b.mat_code,
         m.ov_wc,CONVERT(decimal(18,5),CASE WHEN cb.cum_use_qty=0 THEN 0 ELSE cb.cum_use_qty*b.USE_QTY_PR END),
         CONVERT(varchar(500),cb.cum_in_cust_code+'|'+m.ov_wc+'|'),
         ISNULL((SELECT '2' FROM {P}PR_M_MAT WHERE mat_code=b.mat_code),'1'),cb.use_qty,cb.part_plan_qty,'','1'
      FROM CTE_BOM cb JOIN nx.plan_bom_snap b ON cb.bom_mat_code=b.item_code JOIN nx.item_ov m ON b.mat_code=m.item_code
      WHERE ISNULL(b.except_flag,'0')<>'1'
        AND NOT EXISTS(SELECT 1 FROM nx.plan_route_active pra WHERE pra.assy_item_code=cb.assy_item_code)   -- ★가드: 활성 대체경로 없는 제품만 v_pr_bom(현행)
        -- ★SUB 예외(2026-08-27): 사내 SUB(-SUB)는 파트별에 노드가 있어도 **자재행으로도 남긴다**.
        --   레거시 PR_T_PLAN_PART_MAT 은 SUB 를 512행 갖는데 웹은 6행뿐이었다.
        --   원인 = 아래 NOT EXISTS(파트별에 같은 노드가 있으면 자재행 생략). 실측으로
        --   이 조건이 지우는 건 **정확히 SUB 506행뿐이고 일반자재는 0행**이었다
        --   (파트별 SUB 노드수는 웹·라이브 모두 1,199 로 동일 = 파트별 전개는 맞다).
        --   즉 레거시는 SUB 에 한해 파트별·자재소요 이중 등재를 허용한다.
        --   ★2026-08-31 정밀화: 이 예외는 **CA 라인 · 파트별 bom_level=1** 에만 적용된다.
        --     실측(레거시 lv=1 SUB 1,204건): CA 외 라인은 예외 0건(CE 131·C1 109·CG 94…
        --     전부 ⑤에서 뺀다). CA 안에서도 lv=2 는 전부 뺌, lv=1 이 533남김/47뺌.
        --     종전엔 라인 구분 없이 남겨 SUB 자재 8종·56키가 웹에만 생겼다.
        AND (( b.mat_code LIKE '%-SUB'
               AND EXISTS(SELECT 1 FROM nx.plan_part_dtl d2
                           WHERE d2.work_order=cb.work_order AND d2.split_work_order=cb.split_work_order
                             AND d2.item_code=b.mat_code AND d2.bom_level=1
                             AND LTRIM(RTRIM(ISNULL(d2.line_no,'')))='CA') )
             OR NOT EXISTS(SELECT 1 FROM nx.plan_part_dtl d WHERE d.plan_ymd=cb.plan_ymd AND d.work_order=cb.work_order AND d.split_work_order=cb.split_work_order
            AND d.assy_item_code=cb.assy_item_code AND d.bom_level=cb.bom_level+1 AND d.upper_item_code=b.item_code AND d.item_code=b.mat_code))
      UNION ALL
      -- ★★route-active 브랜치: 활성 대체경로(Rnn) 있는 제품은 그 경로의 route_edges로 전개(except_flag 무관·route가 활성엣지만 보유)
      SELECT cb.plan_ymd,cb.part_plan_ymd,cb.part_output_hm,
         cb.work_order,cb.split_work_order,cb.assy_item_code,cb.bom_level,cb.upper_item_code,cb.item_code,cb.proc_seq,b.mat_code,
         m.ov_wc,CONVERT(decimal(18,5),CASE WHEN cb.cum_use_qty=0 THEN 0 ELSE cb.cum_use_qty*b.use_qty_pr END),
         CONVERT(varchar(500),cb.cum_in_cust_code+'|'+m.ov_wc+'|'),
         ISNULL((SELECT '2' FROM {P}PR_M_MAT WHERE mat_code=b.mat_code),'1'),cb.use_qty,cb.part_plan_qty,'','1'
      FROM CTE_BOM cb
        JOIN nx.plan_route_active pra ON pra.assy_item_code=cb.assy_item_code
        JOIN nx.route_edges b ON b.route_id=pra.route_id AND b.item_code=cb.bom_mat_code
        JOIN nx.item_ov m ON b.mat_code=m.item_code
      WHERE (b.mat_code LIKE '%-SUB'          -- ★SUB 예외 — 위 v_pr_bom 브랜치와 동일 규칙
             OR NOT EXISTS(SELECT 1 FROM nx.plan_part_dtl d WHERE d.plan_ymd=cb.plan_ymd AND d.work_order=cb.work_order AND d.split_work_order=cb.split_work_order
            AND d.assy_item_code=cb.assy_item_code AND d.bom_level=cb.bom_level+1 AND d.upper_item_code=b.item_code AND d.item_code=b.mat_code)))
    SELECT * INTO nx.plan_part_mat_tmp FROM CTE_BOM
    WHERE CHARINDEX('||'+mat_work_center_code+'||',cum_in_cust_code)=0 AND NOT (cust_flag='0' AND gc_gubun='P') OPTION(MAXRECURSION 0)""").replace("{P}", P))
    cur.execute("IF OBJECT_ID('nx.plan_part_mat') IS NOT NULL DROP TABLE nx.plan_part_mat")
    # 최하위집계 + ★용접봉(RAC, proc_weld 별도)만 제외. ★2026-08-19 교정: 레거시 SP엔 sgroup910 제외 없음 →
    #   910 일괄제외는 우리 오추가(4930 등 910 오분류 실 매입부품까지 제외). RAC(용접봉)만 공정처리로 제외, 용접링은 사급으로 유지(RACX 일치).
    #   ★part_plan_ymd/part_output_hm 도 함께 집계(최소값 = 가장 이른 소요일시).
    #     같은 자재가 여러 파트에 걸리면 제일 빠른 시점에 준비돼야 하므로 MIN 이 맞다.
    #   ★★당일 클램프 — 자재는 당일 이전으로 편성되지 않는다(실측 100.00%, 85,990/85,990).
    #     계획은 매일 '당일~+31일'로 업로드되므로 당일보다 이른 소요일은 존재할 수 없다.
    #     파트별 PART_PLAN_YMD < 당일  → 당일 + '0750'
    #     파트별 PART_PLAN_YMD >= 당일 → 파트별 값 그대로(69,463행 100.00%)
    #     ※기준일 = **업로드 파일의 일자축 첫날**(nx.plan_upload_axis) — 2026-08-28 교정.
    #       종전엔 MIN(PLAN_YMD)만 썼는데, 그날 수량이 전부 0이면 계획행이 없어
    #       기준일이 다음날로 밀리고 **그날 컬럼이 통째로 사라졌다**.
    #       실측: 파일 축은 08/28~ 인데 08/28 열이 전 행 0(3,671행) → 웹 기준일 260829.
    #             레거시 기준일 260828 → 자재소요 12,330건이 28일(0750)에 모임.
    #       수량 0 은 계획행으로 저장할 게 없지만(0 저장 시 행수 30배), 그날이
    #       편성 기준일은 되어야 한다 — 저장 여부와 기준일은 별개다(사용자 지적).
    #       클램프는 근무일과 무관하다 — 28일이 회사달력상 휴무여도 레거시는 28일에 모은다.
    #       ※폴백: 축 정보가 없으면(구 업로드분) 종전대로 MIN(PLAN_YMD).
    cur.execute("""SELECT ISNULL(MIN(PLAN_YMD),CONVERT(varchar(6),GETDATE(),12))
                     FROM nx.plan_dtl WHERE PLAN_QTY>0""")
    _mat_base = str(cur.fetchone()[0] or "").strip()
    try:
        cur.execute("""SELECT MIN(axis_from) FROM nx.plan_upload_axis
                        WHERE ISNULL(axis_from,'')<>''""")
        _axis = str((cur.fetchone() or [None])[0] or "").strip()
        if _axis and _axis < _mat_base:
            _mat_base = _axis
    except Exception:
        pass
    #     ★예외(2026-08-27): **직납품 당김분(CUST_MAINT_DAY)** 은 클램프하지 않는다.
    #       직납품은 당일보다 이른 소요일이 실제로 존재한다(라이브 ASSY행 88건이 B 이전).
    #       클램프가 당김값을 되돌려 CA 라인 77건이 어긋났다 → ASSY행 83.82%→86.87%.
    #     ※plan_ymd 에 당김일(part_plan_ymd)을 넣지 말 것 — 2026-08-31 실측으로 기각.
    #       동기: 레벨0 앵커 1,158키가 레거시 대비 +1/+3/+4일 뒤로 밀려 있었고
    #             (part_plan_ymd 는 1,139/1,158 이미 일치), 레거시는 그 행들에서
    #             PLAN_YMD 와 PART_PLAN_YMD 가 같은 값이었다.
    #       결과: bom_level=0 전체에 당김일을 넣었더니 밀린 키가 1,158 → 49,526 으로 폭증
    #             (이번엔 -3/-4일 방향). 레벨0 대부분은 지금의 plan_ymd 가 맞다.
    #       ⟹ 당김일을 쓰는 건 레벨0 중 '일부 조건'뿐이다. 그 조건을 먼저 특정해야 한다.
    cur.execute(("""SELECT a.plan_ymd,a.work_order,a.split_work_order,a.assy_item_code,a.bom_level,a.upper_item_code,a.item_code,a.proc_seq,a.bom_mat_code AS mat_code,
        -- ★2026-08-31: 레거시 PART_PLAN_QTY 는 100.00% 정수(92,152/92,152)다.
        --   웹 소수행 19건을 대조하니 전부 FLOOR(내림)로 일치했다(CEILING·ROUND 는 0건).
        FLOOR(SUM(a.part_plan_qty*a.cum_use_qty)) AS part_plan_qty,MAX(a.mat_flag) mat_flag,MAX(a.mat_work_center_code) mat_work_center_code,
        CASE WHEN MIN(a.part_plan_ymd) < '{B}' AND MAX(dpx.pull_ymd) IS NULL THEN '{B}'
             ELSE MIN(a.part_plan_ymd) END AS part_plan_ymd,
        CASE WHEN MIN(a.part_plan_ymd) < '{B}' AND MAX(dpx.pull_ymd) IS NULL THEN '0750'
             ELSE MIN(a.part_output_hm) END AS part_output_hm
    INTO nx.plan_part_mat FROM nx.plan_part_mat_tmp a
    LEFT JOIN (SELECT RTRIM(work_order) AS work_order, MIN(pull_ymd) AS pull_ymd
                 FROM nx.plan_direct_pull GROUP BY RTRIM(work_order)) dpx
           ON dpx.work_order=RTRIM(a.work_order)
         AND a.bom_level=0 AND a.bom_mat_code=a.assy_item_code""".replace("{B}", _mat_base) + """
    WHERE NOT EXISTS(SELECT 1 FROM nx.plan_part_mat_tmp d WHERE d.work_order=a.work_order AND d.split_work_order=a.split_work_order AND d.assy_item_code=a.assy_item_code AND d.bom_level>a.bom_level AND d.bom_mat_code=a.bom_mat_code)
      AND NOT EXISTS(SELECT 1 FROM {P}PR_M_ITEM wj WHERE wj.item_code=a.bom_mat_code AND wj.item_code LIKE 'RAC%' AND ISNULL(wj.item_desc,'') NOT LIKE N'%용접링%')
    GROUP BY a.plan_ymd,a.work_order,a.split_work_order,a.assy_item_code,a.bom_level,a.upper_item_code,a.item_code,a.proc_seq,a.bom_mat_code""").replace("{P}", P))


# ═══════════════════════════════════════════════════════════════════════
# 단계 함수 — 위 복사분을 감싸기만 한다. 반환값에 카운트를 실어 화면에 표시.
# ═══════════════════════════════════════════════════════════════════════

def _gate_or_raise(cur):
    """★D 사전검증 — soyo.py:21-32 복사. 메시지 문자열 원문 유지."""
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


def _stepM_model(cur):
    """M 신규모델검색및생성 — soyo.py:33-46 복사."""
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
    cur.execute("SELECT COUNT(*) FROM nx.model_bom WHERE REMARKS='신규모델자동'")
    return {"model_rows": int(cur.fetchone()[0] or 0)}


def _step5_item(cur):
    """I 품목별계획생성(STEP5) — soyo.py:47-99 복사."""
    # ── STEP5 nx.plan_item_dtl: (제번,모델) LOT합산 → 모델→ASSY 전개(유효일자, ★EXCEPT미적용) ──
    from collections import defaultdict as _dd
    mbom = _dd(list)
    cur.execute("SELECT MODEL_NO,C_ITEM_CODE,USE_QTY,MAKE_YMD,TO_APPLY_YMD FROM PARTNER_ERP_TEST3.nx.PR_M_MODEL_BOM")
    for m, ci, uq, my, ty in cur.fetchall(): mbom[str(m).strip()].append((str(ci).strip(), float(uq or 1), str(my or '').strip(), str(ty or '').strip()))
    cur.execute("SELECT MODEL_NO,C_ITEM_CODE,USE_QTY,APPLY_FROM,APPLY_TO FROM nx.model_bom")
    for m, ci, uq, my, ty in cur.fetchall(): mbom[str(m).strip()].append((str(ci).strip(), float(uq or 1), str(my or '').strip(), str(ty or '').strip()))
    recvmap = _dd(set)
    # ★2026-08-27 라이브 직독 → nx 미러. 실측 대사 동일(양쪽 64,714행·63,006조합)이라
    #   산출물 변화 없이 라이브 의존만 제거된다(§1 라이브 접근 최소화).
    cur.execute("SELECT DISTINCT WORK_ORDER,ITEM_CODE FROM PARTNER_ERP_TEST3.nx.SA_T_RECV_DTL WHERE WORK_ORDER>''")
    for wo, ic in cur.fetchall(): recvmap[str(wo).strip()].add(str(ic).strip())
    prate = {}
    cur.execute("SELECT ITEM_CODE, ISNULL(PROD_RATE,100) FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM")
    for ic, pr in cur.fetchall(): prate[str(ic).strip()] = float(pr or 100)
    cur.execute("""IF OBJECT_ID('nx.plan_item_dtl') IS NULL CREATE TABLE nx.plan_item_dtl(
        PLAN_YMD varchar(6),WORK_ORDER varchar(20),SPLIT_WORK_ORDER varchar(30),C_ITEM_CODE varchar(20),
        USE_QTY decimal(18,5),LOT_QTY int,PLAN_QTY int,ORG_PLAN_YMD varchar(6),LINE_NO varchar(6),OUTPUT_HM varchar(4),PROD_RATE numeric(9,2))""")
    cur.execute("DELETE FROM nx.plan_item_dtl")
    # ★검토본 변경: 라인별 당김(nx.plan_line_pull) 적용값으로 계획일자를 잡는다.
    #   레거시는 PR_T_PLAN_DTL.PLAN_YMD 에 라인당김이 baked 돼 있고 STEP5 가 그걸 읽는다.
    #   웹은 plan_dtl 이 원본이라(PK(WORK_ORDER,PLAN_YMD) 충돌로 수정 불가) 맵을 조인해 같은 효과.
    #   ★일자와 함께 '당긴 시각'(pulled_hm)도 가져온다 — 레거시 OUTPUT_HM 대응.
    cur.execute("SELECT CASE WHEN OBJECT_ID('nx.plan_line_pull') IS NULL THEN 0 ELSE 1 END")
    if int(cur.fetchone()[0] or 0):
        # ★LINE_NO 도 함께 — 레거시 PR_T_PLAN_PART_COPY.LINE_NO 는 계획라인이 채워져 있다.
        #   (실측: 웹은 전량 빈값이었고 plan_dtl 에는 100% 존재)
        # ★LINE_NO·LOT_QTY 도 함께 가져온다(실측 대사 결과):
        #     LINE_NO  — 레거시 PART.LINE_NO 는 계획라인이 채워져 있다(웹은 전량 빈값이었음).
        #     LOT_QTY  — 레거시 DTL.LOT_QTY = 웹 plan_dtl.REMAIN_QTY 가 100.0% 일치.
        #                (기존 MAX(PLAN_QTY) 방식은 분할제번에서 어긋났다 — 실측 92.7%)
        cur.execute("""SELECT d.WORK_ORDER, d.MODEL_NO, SUM(CAST(d.PLAN_QTY AS int)),
                 MIN(ISNULL(p.pulled, d.PLAN_YMD)),
                 MIN(ISNULL(NULLIF(p.pulled_hm,''), ISNULL(NULLIF(d.START_HM,''),'0800'))),
                 MIN(RTRIM(ISNULL(d.LINE_NO,''))), MAX(CAST(ISNULL(d.REMAIN_QTY,0) AS int))
            FROM nx.plan_dtl d
            LEFT JOIN nx.plan_line_pull p ON p.wo=d.WORK_ORDER AND p.org=d.PLAN_YMD
           WHERE d.PLAN_QTY>0 GROUP BY d.WORK_ORDER, d.MODEL_NO""")
    else:
        cur.execute("""SELECT WORK_ORDER,MODEL_NO,SUM(CAST(PLAN_QTY AS int)),MIN(PLAN_YMD),
                 MIN(ISNULL(NULLIF(START_HM,''),'0800')), MIN(RTRIM(ISNULL(LINE_NO,''))),
                 MAX(CAST(ISNULL(REMAIN_QTY,0) AS int))
            FROM nx.plan_dtl WHERE PLAN_QTY>0 GROUP BY WORK_ORDER,MODEL_NO""")
    irows = []; lot = _dd(int)
    for wo, model, pq, ymd, ohm, lno, rq in cur.fetchall():
        wos = str(wo).strip(); mk = str(model).strip(); pq = int(pq or 0); ymd = str(ymd).strip()
        ohm = (str(ohm or '').strip() or '0800')     # ★라인당김 적용된 시각
        lno = str(lno or '').strip()                 # ★계획라인
        rq = int(rq or 0)                            # ★LOT 수량(REMAIN_QTY)
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
            irows.append([ymd, wos, wos, a, mq, 0, pq, ymd, lno, ohm, prate.get(a, 100)])
            lot[wos] = max(lot[wos], rq or pq)       # ★REMAIN_QTY 우선, 없으면 종전 방식
    for rr in irows: rr[5] = lot[rr[1]]
    # ── STEP5-AS: A/S(WO) 계획 앵커 (레거시 compose 3번째 앵커, 우리 누락분 반영) ──
    #   소스=PR_T_PLAN_INPUT(w_pr_plan_060 수기 A/S/긴급, LINE SVC/AR). ITEM_CODE=완성품 직접(모델매핑 없음),
    #   prod_rate=100(WO 특례, SP substring(work_order,1,2)='WO'), plan_ymd>=생산계획 최소일자(@as_from_ymd).
    #   ★2026-08-27 라이브 직독 → nx 미러 → **웹 정본 nx.prod_plan_input 으로 repoint**.
    #     미러(nx.PR_T_PLAN_INPUT)가 낡아 최신 A/S 제번이 빠졌다:
    #       미러 782키 · 라이브 791키 · 웹정본 797키 (WO1094126SS 등 15건이 미러에 없음)
    #     그 결과 자재소요에서 165행(수량 8,305)이 통째로 누락됐다.
    #     nx.prod_plan_input 은 planinput.py 가 정본으로 선언한 웹 자체 테이블이고
    #     CRUD 화면(생산계획추가입력)까지 붙어 있다 = CLAUDE.md §1-9 클린본 원칙.
    #     ⚠컬럼명이 소문자다(plan_ymd/item_code/…). 미러는 대문자였다.
    #     ★게이트 기준일 = **업로드 파일의 일자축 첫날**(nx.plan_upload_axis) — 2026-08-28 교정.
    #       STEP7 클램프(:315)는 이미 이 폴백을 쓰는데 여기만 빠져 있었다.
    #       MIN(PLAN_YMD)만 쓰면 그날 수량이 전부 0일 때 기준일이 다음날로 밀리고
    #       **당일자 예외생산이 통째로 사라진다**(실측: 오늘 260828 인데 게이트가 260829,
    #       17제번·수량 480 이 편성에서 누락 → 레거시는 259행·7,927 로 편성).
    #       ※폴백: 축 정보가 없으면(구 업로드분) 종전대로 MIN(PLAN_YMD).
    #     ★조인 = nx.item(클린 정본). 종전 nx.PR_M_ITEM(미러)에서 전환 — CLAUDE.md §1-9,
    #       현행 soyo.py:90 과 동일. 실측 전환 영향 0제번(양방향 차이 없음).
    cur.execute("SELECT ISNULL(MIN(PLAN_YMD),CONVERT(varchar(6),GETDATE(),12)) FROM nx.plan_dtl WHERE PLAN_QTY>0")
    _asfrom = str(cur.fetchone()[0] or '').strip()
    try:
        cur.execute("""SELECT MIN(axis_from) FROM nx.plan_upload_axis
                        WHERE ISNULL(axis_from,'')<>''""")
        _ax = str((cur.fetchone() or [None])[0] or "").strip()
        if _ax and _ax < _asfrom:
            _asfrom = _ax
    except Exception:
        pass
    cur.execute("""SELECT LTRIM(RTRIM(a.work_order)) wo, LTRIM(RTRIM(a.item_code)) it, SUM(CAST(a.plan_qty AS int)) pq,
            MIN(a.plan_ymd) ymd, MAX(ISNULL(a.output_hm,'')) ohm, MAX(ISNULL(a.line_no,'')) ln
          FROM nx.prod_plan_input a
          JOIN PARTNER_ERP_TEST3.nx.item c ON LTRIM(RTRIM(a.item_code))=c.item_code
          WHERE a.plan_ymd>=? AND a.plan_qty>0
          GROUP BY LTRIM(RTRIM(a.work_order)), LTRIM(RTRIM(a.item_code)), a.plan_ymd""", _asfrom)
    for wo, it, pq, ymd, ohm, ln in cur.fetchall():
        wos=str(wo).strip(); it=str(it).strip(); pq=int(pq or 0); ymd=str(ymd).strip()
        ohm=(str(ohm).strip() or '0800'); ln=(str(ln or '').strip())[:6]
        # C_ITEM_CODE=ITEM_CODE(직접 assy), USE_QTY=1, LOT_QTY=PLAN_QTY=pq, PROD_RATE=100
        irows.append([ymd, wos, wos, it, 1.0, pq, pq, ymd, ln, ohm, 100])
    cur.fast_executemany = True
    cur.executemany("INSERT INTO nx.plan_item_dtl(PLAN_YMD,WORK_ORDER,SPLIT_WORK_ORDER,C_ITEM_CODE,USE_QTY,LOT_QTY,PLAN_QTY,ORG_PLAN_YMD,LINE_NO,OUTPUT_HM,PROD_RATE) VALUES(?,?,?,?,?,?,?,?,?,?,?)", irows)
    return {"item_lines": len(irows)}


def _step6_part(cur):
    """K 파트별계획생성(STEP6) — 복사분 _step6_sql 호출 + 카운트."""
    _step6_sql(cur)
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT work_order) FROM nx.plan_part_dtl")
    n, w = cur.fetchone()
    return {"part_lines": int(n or 0), "part_work_orders": int(w or 0)}


def _step7_mat(cur):
    """T-1 자재소요(STEP7) — 복사분 _step7_sql 호출 + 카운트."""
    _step7_sql(cur)
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT work_order) FROM nx.plan_part_mat")
    n, w = cur.fetchone()
    return {"mat_lines": int(n or 0), "mat_work_orders": int(w or 0)}


def _step_source(cur):
    """T-2 조달 프로파일 오버레이 — soyo.py:104-157 복사."""
    # ── 조달 프로파일 오버레이 → nx.plan_mat_source (공급방식·공급처·수량) ──
    #   ①활성 프로파일 있으면 supply_gubun·vendor·배분(alloc) ②없으면 BOM기본(MAKE_TYPE→매입/사급/외주/자체 + IN_CUST vendor).
    cur.execute("""IF OBJECT_ID('nx.plan_mat_source') IS NULL CREATE TABLE nx.plan_mat_source(
        WORK_ORDER varchar(20),MAT_CODE varchar(20),SUPPLY_GUBUN varchar(20),VENDOR_CODE varchar(20),
        QTY decimal(18,3),SOURCE varchar(10),COMPOSE_DT datetime DEFAULT getdate())""")
    cur.execute("DELETE FROM nx.plan_mat_source")
    MKF = {}; INCF = {}
    cur.execute("SELECT ITEM_CODE, ISNULL(MAKE_TYPE,''), ISNULL(IN_CUST_CODE,'') FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM")
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
    return {"sourcing_lines": len(srows)}


# ═══════════════════════════════════════════════════════════════════════
# ② 생산계획이력생성 (H) — 검토본 신규
#   레거시 ue_make_indicate 는 4테이블(pr_t_plan_dtl_daily·pr_t_plan_input_daily·
#   sa_t_plan_dtl·sa_t_plan_dtl_daily)을 쓰지만, _daily 3종이 전부 "기준일+원본" 구조라
#   웹은 nx.sale_plan(LG계획) + nx.plan_snap(src로 3종 통합) 2테이블로 재설계.
#   ★핵심: sale_plan 은 ISNULL(ORG_PLAN_YMD, PLAN_YMD) = 당김 전 원본일자 기준(레거시 원문 동일).
# ═══════════════════════════════════════════════════════════════════════

def _ensure_plan_org(cur):
    """nx.plan_dtl 에 ORG_PLAN_YMD/ORG_OUTPUT_HM 보장(멱등). 당김 미구현이라 현재는 원본=결과."""
    cur.execute("IF COL_LENGTH('nx.plan_dtl','ORG_PLAN_YMD') IS NULL ALTER TABLE nx.plan_dtl ADD ORG_PLAN_YMD varchar(6) NULL")
    cur.execute("IF COL_LENGTH('nx.plan_dtl','ORG_OUTPUT_HM') IS NULL ALTER TABLE nx.plan_dtl ADD ORG_OUTPUT_HM varchar(4) NULL")
    cur.execute("""UPDATE nx.plan_dtl SET ORG_PLAN_YMD=PLAN_YMD, ORG_OUTPUT_HM=ISNULL(NULLIF(START_HM,''),'0800')
                    WHERE ORG_PLAN_YMD IS NULL OR ORG_OUTPUT_HM IS NULL""")


def _ensure_sale_plan(cur):
    cur.execute("""IF OBJECT_ID('nx.sale_plan','U') IS NULL CREATE TABLE nx.sale_plan(
        plan_ymd varchar(6) NOT NULL, work_order varchar(20) NOT NULL, split_work_order varchar(30) NULL,
        model_no varchar(30) NULL, line_no varchar(10) NULL, output_hm varchar(4) NULL,
        lot_qty int NULL, plan_qty int NULL, cr_flag varchar(1) NULL,
        from_seq varchar(20) NULL, to_seq varchar(20) NULL, tool varchar(40) NULL,
        org_plan_ymd varchar(6) NULL, org_output_hm varchar(4) NULL,
        compose_dt datetime NOT NULL DEFAULT getdate())""")
    cur.execute("""IF OBJECT_ID('nx.sale_plan','U') IS NOT NULL AND NOT EXISTS(
        SELECT 1 FROM sys.indexes WHERE name='ix_sale_plan_wo' AND object_id=OBJECT_ID('nx.sale_plan'))
        CREATE INDEX ix_sale_plan_wo ON nx.sale_plan(work_order, plan_ymd)""")


def _ensure_sale_plan_item(cur):
    """★040 출하실적등록이 실제로 읽는 원천 = 도번단위 SA_T_PLAN_ITEM_DTL 대응.

    nx.sale_plan(제번단위)만으로는 040 이 못 읽는다 — 040 의 b1(LG계획)은
    SA_T_PLAN_ITEM_DTL(제번×분할×도번) 그레인이기 때문(sales.py:997).
    레거시 SA_T_PLAN_ITEM_DTL 은 **누적 이력**(34만행·767일자)이고 여기는
    현재 편성분만 담는다 → 040 은 기간필터로 읽으므로 동작에 문제 없음."""
    cur.execute("""IF OBJECT_ID('nx.sale_plan_item','U') IS NULL CREATE TABLE nx.sale_plan_item(
        PLAN_YMD varchar(6) NOT NULL, WORK_ORDER varchar(20) NOT NULL,
        SPLIT_WORK_ORDER varchar(30) NULL, C_ITEM_CODE varchar(20) NOT NULL,
        MODEL_NO varchar(30) NULL, LINE_NO varchar(10) NULL, CLS_YMD varchar(6) NULL,
        OUTPUT_HM varchar(4) NULL, USE_QTY decimal(18,5) NULL, LOT_QTY int NULL,
        PLAN_QTY int NULL, REMARKS1 nvarchar(200) NULL, REMARKS2 nvarchar(200) NULL,
        EXCEL_SEQ int NULL, TOOLS_DESC varchar(40) NULL,
        FROM_SEQ varchar(20) NULL, TO_SEQ varchar(20) NULL, CHANGE_DAY varchar(6) NULL,
        CR_FLAG varchar(1) NULL, ORG_PLAN_YMD varchar(6) NULL, ORG_OUTPUT_HM varchar(4) NULL,
        VIR_SET_FLAG varchar(1) NULL, compose_dt datetime NOT NULL DEFAULT getdate())""")
    cur.execute("""IF OBJECT_ID('nx.sale_plan_item','U') IS NOT NULL AND NOT EXISTS(
        SELECT 1 FROM sys.indexes WHERE name='ix_sale_plan_item' AND object_id=OBJECT_ID('nx.sale_plan_item'))
        CREATE INDEX ix_sale_plan_item ON nx.sale_plan_item(PLAN_YMD, WORK_ORDER, C_ITEM_CODE)""")


def _ensure_plan_snap(cur):
    cur.execute("""IF OBJECT_ID('nx.plan_snap','U') IS NULL CREATE TABLE nx.plan_snap(
        snap_id bigint IDENTITY(1,1) PRIMARY KEY, work_ymd varchar(6) NOT NULL, src varchar(12) NOT NULL,
        plan_ymd varchar(6) NULL, work_order varchar(20) NULL, item_code varchar(20) NULL,
        line_no varchar(10) NULL, model_no varchar(30) NULL,
        plan_qty int NULL, lot_qty int NULL, output_hm varchar(4) NULL,
        snap_dt datetime NOT NULL DEFAULT getdate())""")
    cur.execute("""IF OBJECT_ID('nx.plan_snap','U') IS NOT NULL AND NOT EXISTS(
        SELECT 1 FROM sys.indexes WHERE name='ix_plan_snap' AND object_id=OBJECT_ID('nx.plan_snap'))
        CREATE INDEX ix_plan_snap ON nx.plan_snap(work_ymd, src)""")


def _stepH_history(cur, base_ymd=""):
    """H 생산계획이력생성 — nx.sale_plan 재생성 + nx.plan_snap 스냅샷 + 30일 정리."""
    _ensure_plan_org(cur); _ensure_sale_plan(cur); _ensure_sale_plan_item(cur); _ensure_plan_snap(cur)
    if not base_ymd:
        cur.execute("SELECT ISNULL(MIN(PLAN_YMD),CONVERT(varchar(6),GETDATE(),12)) FROM nx.plan_dtl")
        base_ymd = str(cur.fetchone()[0] or "").strip()
    # ── LG계획: 전량 재생성(레거시 sa_t_plan_dtl 동일). ★ORG_ 우선 = 당김 전 원본일자 ──
    cur.execute("DELETE FROM nx.sale_plan")
    cur.execute("""INSERT INTO nx.sale_plan(plan_ymd, work_order, split_work_order, model_no, line_no,
            output_hm, lot_qty, plan_qty, cr_flag, from_seq, to_seq, tool, org_plan_ymd, org_output_hm)
        SELECT ISNULL(NULLIF(ORG_PLAN_YMD,''),PLAN_YMD), WORK_ORDER, WORK_ORDER, MODEL_NO, LINE_NO,
               ISNULL(NULLIF(ORG_OUTPUT_HM,''),ISNULL(NULLIF(START_HM,''),'0800')),
               TOTAL_QTY, PLAN_QTY, CR_FLAG, FROM_SEQ, TO_SEQ, TOOL,
               ISNULL(NULLIF(ORG_PLAN_YMD,''),PLAN_YMD),
               ISNULL(NULLIF(ORG_OUTPUT_HM,''),ISNULL(NULLIF(START_HM,''),'0800'))
          FROM nx.plan_dtl""")
    cur.execute("SELECT COUNT(*) FROM nx.sale_plan")
    n_sale = int(cur.fetchone()[0] or 0)
    # ── ★도번단위 LG계획(040 원천) — STEP5 산출(nx.plan_item_dtl)에서 전개 ──
    #   레거시 SA_T_PLAN_ITEM_DTL 대응. 040 의 b1 이 이 그레인을 읽는다.
    #   ★★OUTPUT_HM 은 **당김 전 원본시각**(ORG_OUTPUT_HM)이다 — 실측 확정.
    #     레거시 SA_T_PLAN_ITEM_DTL 은 OUTPUT_HM = ORG_OUTPUT_HM 로 동일하게 채워져 있다
    #     (당김 후 시각을 넣으면 0.72% 로 떨어짐). 영업계획은 당겨지기 전 원래 시각으로 잡힌다.
    n_item = 0
    cur.execute("SELECT CASE WHEN OBJECT_ID('nx.plan_item_dtl','U') IS NULL THEN 0 ELSE 1 END")
    if int(cur.fetchone()[0] or 0):
        cur.execute("DELETE FROM nx.sale_plan_item")
        cur.execute("""INSERT INTO nx.sale_plan_item(PLAN_YMD, WORK_ORDER, SPLIT_WORK_ORDER, C_ITEM_CODE,
                MODEL_NO, LINE_NO, OUTPUT_HM, USE_QTY, LOT_QTY, PLAN_QTY,
                FROM_SEQ, TO_SEQ, TOOLS_DESC, CHANGE_DAY, CR_FLAG, ORG_PLAN_YMD, ORG_OUTPUT_HM)
            SELECT i.PLAN_YMD, i.WORK_ORDER, ISNULL(NULLIF(i.SPLIT_WORK_ORDER,''), i.WORK_ORDER),
                   i.C_ITEM_CODE, d.MODEL_NO, ISNULL(NULLIF(i.LINE_NO,''), d.LINE_NO),
                   ISNULL(NULLIF(d.ORG_OUTPUT_HM,''), ISNULL(NULLIF(d.START_HM,''),'0800')),
                   i.USE_QTY, i.LOT_QTY, i.PLAN_QTY,
                   d.FROM_SEQ, d.TO_SEQ, d.TOOL, NULL, d.CR_FLAG,
                   ISNULL(NULLIF(i.ORG_PLAN_YMD,''), i.PLAN_YMD),
                   ISNULL(NULLIF(d.ORG_OUTPUT_HM,''), ISNULL(NULLIF(d.START_HM,''),'0800'))
              FROM nx.plan_item_dtl i
              LEFT JOIN (SELECT WORK_ORDER, MIN(MODEL_NO) MODEL_NO, MIN(LINE_NO) LINE_NO,
                                MIN(FROM_SEQ) FROM_SEQ, MIN(TO_SEQ) TO_SEQ, MIN(TOOL) TOOL,
                                MIN(CR_FLAG) CR_FLAG, MIN(START_HM) START_HM,
                                MIN(ORG_OUTPUT_HM) ORG_OUTPUT_HM
                           FROM nx.plan_dtl GROUP BY WORK_ORDER) d
                     ON RTRIM(d.WORK_ORDER)=RTRIM(i.WORK_ORDER)""")
        cur.execute("SELECT COUNT(*) FROM nx.sale_plan_item")
        n_item = int(cur.fetchone()[0] or 0)
    # ── 이력 스냅샷: 당일 재실행 멱등 ──
    cur.execute("DELETE FROM nx.plan_snap WHERE work_ymd=?", base_ymd)
    cur.execute("""INSERT INTO nx.plan_snap(work_ymd,src,plan_ymd,work_order,line_no,model_no,plan_qty,lot_qty,output_hm)
        SELECT ?, 'plan', PLAN_YMD, WORK_ORDER, LINE_NO, MODEL_NO, PLAN_QTY, TOTAL_QTY, START_HM
          FROM nx.plan_dtl WHERE PLAN_YMD>=?""", base_ymd, base_ymd)
    cur.execute("""INSERT INTO nx.plan_snap(work_ymd,src,plan_ymd,work_order,item_code,line_no,plan_qty,output_hm)
        SELECT ?, 'input', plan_ymd, work_order, item_code, line_no, plan_qty, output_hm
          FROM nx.prod_plan_input WHERE plan_ymd>=?""", base_ymd, base_ymd)
    cur.execute("""INSERT INTO nx.plan_snap(work_ymd,src,plan_ymd,work_order,line_no,model_no,plan_qty,lot_qty,output_hm)
        SELECT ?, 'sale', plan_ymd, work_order, line_no, model_no, plan_qty, lot_qty, output_hm
          FROM nx.sale_plan WHERE plan_ymd>=?""", base_ymd, base_ymd)
    cur.execute("SELECT COUNT(*) FROM nx.plan_snap WHERE work_ymd=?", base_ymd)
    n_snap = int(cur.fetchone()[0] or 0)
    # ── 30일 초과 정리(레거시 동일) ──
    cur.execute("DELETE FROM nx.plan_snap WHERE work_ymd < CONVERT(varchar, GETDATE()-30, 12)")
    return {"sale_plan_rows": n_sale, "sale_item_rows": n_item,
            "snap_rows": n_snap, "base_ymd": base_ymd}


# ═══════════════════════════════════════════════════════════════════════
# 작업로그 nx.plan_job_log — 레거시 PR_T_JOB_UPLOAD 대응 + 웹확장(status/elapsed/row_count)
# ═══════════════════════════════════════════════════════════════════════

_JOB_NAME = {"M": "신규모델검색및생성", "H": "생산계획이력생성", "L": "라인별투입시간조정",
             "L2": "리드타임 당김", "H2": "생산계획이력생성(LG계획 확정)",
             "I": "품목별계획생성", "K": "파트별계획생성", "T": "자재소요·조달편성",
             "S": "협력사계획편성", "Z": "생산계획일괄작업"}


def _ensure_job_log(cur):
    cur.execute("""IF OBJECT_ID('nx.plan_job_log','U') IS NULL CREATE TABLE nx.plan_job_log(
        job_seq int IDENTITY(1,1) PRIMARY KEY, job_code varchar(2) NOT NULL, job_name nvarchar(40) NOT NULL,
        batch_id varchar(20) NULL, status varchar(3) NOT NULL, elapsed_sec int NOT NULL DEFAULT 0,
        row_count int NULL, err_msg nvarchar(400) NULL, ins_user varchar(20) NULL,
        ins_window varchar(30) NULL, ins_client varchar(60) NULL,
        ins_dt datetime NOT NULL DEFAULT getdate())""")
    cur.execute("""IF OBJECT_ID('nx.plan_job_log','U') IS NOT NULL AND NOT EXISTS(
        SELECT 1 FROM sys.indexes WHERE name='ix_pjl_code_dt' AND object_id=OBJECT_ID('nx.plan_job_log'))
        CREATE INDEX ix_pjl_code_dt ON nx.plan_job_log(job_code, ins_dt DESC)""")


def _job_log(cur, code, user, elapsed, status, err="", rows=None, batch=None):
    _ensure_job_log(cur)
    cur.execute("""INSERT INTO nx.plan_job_log(job_code,job_name,batch_id,status,elapsed_sec,row_count,
        err_msg,ins_user,ins_window,ins_client) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        code, _JOB_NAME.get(code, code), batch, status, int(elapsed), rows,
        (err[:400] or None), (user or "")[:20], "planuploadrev", None)


# ═══════════════════════════════════════════════════════════════════════
# 단계 의존성 · 동시실행 락
# ═══════════════════════════════════════════════════════════════════════

# code -> (선행 산출테이블, 안내라벨) — 없으면 SQL 오류가 사용자에게 그대로 노출된다
_DEP_TABLE = {"H": ("nx.plan_dtl", "생산계획 UPLOAD"),
              "K": ("nx.plan_dtl", "생산계획 UPLOAD"),
              "L": ("nx.plan_dtl", "생산계획 UPLOAD"),
              "T": ("nx.plan_part_dtl", "④ 파트별 계획생성"),
              "S": ("nx.plan_part_mat", "⑤ 자재소요·조달 편성")}
# code -> 선행단계코드(최종성공시각 비교 = 낡음 경고. 차단 아님)
_DEP_PREV = {"H": ["M"], "K": ["L"], "L": ["M"], "T": ["K"], "S": ["T"]}


def _dep_or_raise(cur, code):
    """(A) 선행 산출물 부재 → 409 차단. (B) 선행이 더 최신 → 경고문자열 반환(차단 아님)."""
    _ensure_job_log(cur)
    tb = _DEP_TABLE.get(code)
    if tb:
        t, label = tb
        cur.execute("SELECT CASE WHEN OBJECT_ID(?) IS NULL THEN 0 ELSE 1 END", t)
        if not int(cur.fetchone()[0] or 0):
            raise HTTPException(409, "선행단계 미실행 — 「{}」 을(를) 먼저 실행하세요.\n({} 없음)".format(label, t))
        cur.execute("SELECT COUNT(*) FROM " + t)
        if int(cur.fetchone()[0] or 0) == 0:
            raise HTTPException(409, "선행단계 산출물이 비어 있습니다 — 「{}」 을(를) 먼저 실행하세요.\n({} 0행)".format(label, t))
    warns = []
    cur.execute("SELECT MAX(ins_dt) FROM nx.plan_job_log WHERE job_code=? AND status='OK'", code)
    me = cur.fetchone()[0]
    for d in _DEP_PREV.get(code, []):
        cur.execute("SELECT MAX(ins_dt) FROM nx.plan_job_log WHERE job_code=? AND status='OK'", d)
        pre = cur.fetchone()[0]
        if me and pre and pre > me:
            warns.append("선행 「{}」 이(가) 이후에 다시 실행됨 — 이 단계도 다시 실행하는 것이 안전합니다.".format(_JOB_NAME.get(d, d)))
    return warns


_LOCK_RES = "nx_plan_compose"


def _lock_or_raise(cur):
    """★동시실행 금지 — 단계들이 DROP TABLE 을 쓰므로 두 사람이 동시에 누르면 깨진다.
       기존 화면(/api/plan/compose_mat)과 검토 화면이 같은 nx 테이블을 쓰는 것도 여기서 막는다.
       ★Session 소유 락은 반드시 _unlock 으로 풀어야 한다(커넥션 풀 재사용 시 영구 점유 — 실제로 겪음).
       ※ EXEC @r=sp_getapplock 의 반환값은 pyodbc 로 안 넘어온다(-99 관측).
         → APPLOCK_TEST 로 판정하고 획득은 EXEC 만 한다."""
    cur.execute("SELECT APPLOCK_TEST('public', ?, 'Exclusive', 'Session')", _LOCK_RES)
    if int(cur.fetchone()[0] or 0) != 1:
        raise HTTPException(409, "다른 편성 작업이 실행 중입니다. 완료 후 다시 시도하세요.\n"
                                 "(기존 「생산계획업로드」 화면에서 편성 중일 수도 있습니다)")
    cur.execute("EXEC sp_getapplock @Resource=?, @LockMode='Exclusive',"
                " @LockOwner='Session', @LockTimeout=0", _LOCK_RES)
    return True


def _unlock(cur):
    try:
        cur.execute("IF APPLOCK_MODE('public', ?, 'Session') <> 'NoLock'"
                    " EXEC sp_releaseapplock @Resource=?, @LockOwner='Session'", _LOCK_RES, _LOCK_RES)
    except Exception:
        pass


def _run_step(code, fn, user, batch=None):
    """단계 1개 실행 + 선행검증 + 락 + 로그. 예외는 그대로 올려 화면이 표시."""
    nx = _nx(); cur = nx.cursor(); t0 = time.time(); got = False
    try:
        warns = _dep_or_raise(cur, code)
        got = _lock_or_raise(cur)
        out = fn(cur) or {}
        el = int(time.time() - t0)
        rows = next((out[k] for k in ("part_lines", "mat_lines", "item_lines", "sourcing_lines",
                                      "sale_plan_rows", "model_rows", "coop_lines", "pull_lines") if k in out), None)
        _job_log(cur, code, user, el, "OK", "", rows, batch)
        cur.execute("SELECT CONVERT(varchar(8),GETDATE(),108)")
        out.update({"ok": True, "step": code, "name": _JOB_NAME.get(code, code),
                    "done_hms": cur.fetchone()[0], "elapsed": el, "warns": warns})
        return out
    except HTTPException:
        raise                       # 409/400 = DML 전 차단이므로 로그 안 남김
    except Exception as e:
        try: _job_log(cur, code, user, int(time.time() - t0), "ERR", str(e), None, batch)
        except Exception: pass
        raise HTTPException(500, "{} 실패 — {}".format(_JOB_NAME.get(code, code), str(e)[:300]))
    finally:
        if got: _unlock(cur)        # ★락 해제 필수 — 안 풀면 커넥션 풀 재사용 시 영구 점유
        nx.close()


def _by(payload):
    return str((payload or {}).get("by", "") or "")[:20]


# ═══════════════════════════════════════════════════════════════════════
# 엔드포인트 — /api/planrev/*  (현행 /api/plan/* 과 겹치지 않는다)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/api/planrev/step/model")
def planrev_step_model(payload: dict = Body(...)):
    """① 신규모델 검색·생성 (M)"""
    def _f(cur):
        _gate_or_raise(cur)          # ★첫 DML 직전 게이트
        return _stepM_model(cur)
    return _run_step("M", _f, _by(payload))


# ⛔제번 병합(/api/planrev/step/mergewo) — 2026-08-27 시도 후 **폐기**.
#   가설: 업로드(order.py:52 `k=(wo,ymd)`)가 엑셀 일자컬럼을 펼쳐 165제번이 다중행이 되는데,
#         라이브 PR_T_PLAN_DTL 은 제번당 1행이라 이 구조 차이가 420 부정확의 원인일 것이다.
#   결과: **틀렸다.** 4,334→4,166 행으로 라이브와 같은 구조가 됐지만 정합이 오히려 무너졌다.
#         ④파트별 99.86%→95.39% · ⑤자재행 99.88%→96.23% · ★ASSY행 100.00%→97.22%
#         (일자를 LG_INPUT 으로 덮은 1차 시도는 더 나빴다: 자재행 43.32%·ASSY 22.57%)
#   원인: STEP5 가 제번을 이미 합쳐 처리하므로 plan_dtl 이 몇 행이든 결과가 같다.
#         병합은 得이 없고, MIN(일자)로 접으면서 라인당김 출발점만 어긋났다.
#   ★결론: **웹의 (제번,일자) 그레인이 정답이다.** 라이브와 행 구조가 달라도 무방하다.
#         420 ASSY행은 병합 없이 100.00% 다(직납품당김일자 적용 + LG 라이브 우선).


@router.post("/api/planrev/step/history")
def planrev_step_history(payload: dict = Body(...)):
    """② 생산계획이력생성 (H) — nx.sale_plan + nx.plan_snap"""
    ymd = str((payload or {}).get("base_ymd", "") or "").strip()
    return _run_step("H", lambda cur: _stepH_history(cur, ymd), _by(payload))


@router.post("/api/planrev/step/linetime")
def planrev_step_linetime(payload: dict = Body(...)):
    """③ 라인별 투입시간조정 (L) — (1)라인당김 + (2)리드타임당김.

    ★레거시 순서: 라인당김(plan_dtl.PLAN_YMD) → 파트별계획(STEP5/6) → 리드타임당김(part_plan_ymd)
      (1)은 라인당김 맵만 만든다(plan_dtl 원본 무변경 — PK 충돌 회피).
      STEP5 가 이 맵을 읽으므로 **④ 를 다시 돌려야** 라인당김이 반영된다.
      plan_part_dtl 이 이미 있으면 (2) 리드타임당김까지 이어서 수행한다."""
    def _f(cur):
        r = _ensure_line_pull(cur)            # (1) 라인당김 맵 생성(plan_dtl 무변경)
        cur.execute("SELECT CASE WHEN OBJECT_ID('nx.plan_part_dtl') IS NULL THEN 0 ELSE 1 END")
        if int(cur.fetchone()[0] or 0):
            r.update(_stepL_pull(cur))        # (2) 리드타임당김 — part_plan_ymd
        return r
    return _run_step("L", _f, _by(payload))


@router.post("/api/planrev/step/part")
def planrev_step_part(payload: dict = Body(...)):
    """④ 파트별 계획생성 — STEP5(I) + STEP6(K) + 리드타임당김(L2). 로그는 I·K·L2 3행.

    ★STEP6 는 `DROP TABLE + SELECT INTO` 로 nx.plan_part_dtl 을 재생성한다(planrev.py:153).
      그때 당김 컬럼(part_plan_ymd·part_output_hm…)이 통째로 사라지므로,
      ④ 단독 실행 뒤에는 반드시 리드타임 당김을 다시 얹어야 한다.
      (안 그러면 410 파트별생산계획의 PART INPUT·당일이전계획이 빈칸이 된다 — 2026-08-26 실측)"""
    user = _by(payload)
    def _f(cur):
        t1 = time.time()
        r = _step5_item(cur)
        _job_log(cur, "I", user, int(time.time() - t1), "OK", "", r.get("item_lines"))
        r.update(_step6_part(cur))
        # ★리드타임 당김을 이어서 — 라인당김 맵이 있을 때만(없으면 ③을 먼저 눌러야 한다).
        t2 = time.time()
        cur.execute("SELECT CASE WHEN OBJECT_ID('nx.plan_line_pull') IS NULL THEN 0 ELSE 1 END")
        if int(cur.fetchone()[0] or 0):
            r2 = _stepL_pull(cur)
            r.update(r2)
            _job_log(cur, "L2", user, int(time.time() - t2), "OK", "", r2.get("pull_lines"))
        else:
            r["warn_pull"] = "라인당김 맵이 없어 리드타임 당김을 건너뛰었습니다 — ③을 먼저 실행하세요."
        return r
    return _run_step("K", _f, user)


def _coop_check(cur):
    """협력사 점검 — plan_part_mat 작업처 집계 + 마스터 미매핑 리포트(쓰기 0).

    ★2026-08-27 ⑥ 단계를 ⑤ 로 흡수. 종전 ⑥「협력사계획 편성」은 이름과 달리
      쓰기가 0이고 조회 2번(0초)뿐이라 '편성'이 아니었다. 레거시
      SP_PR_CREATE_PLAN_협력사계획_생성 이 만드는 자재소요는 웹에선 ⑤(STEP7)가
      이미 만들고, 그 SP 의 또다른 산출물 PR_T_PLAN_PART_MAT_BY_ITEM 은
      웹·레거시 어디에서도 읽지 않아(참조 0건) 만들 필요가 없다.
      → 검증 로직만 ⑤ 끝에 붙이고 단계는 없앤다."""
    cur.execute("""SELECT COUNT(*), COUNT(DISTINCT ISNULL(mat_work_center_code,'')),
                          COUNT(DISTINCT work_order) FROM nx.plan_part_mat""")
    n, wc, wo = cur.fetchone()
    cur.execute("""SELECT TOP 30 ISNULL(a.mat_work_center_code,'') wc, COUNT(*) n
                     FROM nx.plan_part_mat a
                    WHERE ISNULL(a.mat_work_center_code,'')<>''
                      AND NOT EXISTS(SELECT 1 FROM nx.PR_M_WORK w WHERE w.WORK_CODE=a.mat_work_center_code)
                      AND NOT EXISTS(SELECT 1 FROM nx.CM_M_CUST c WHERE c.CUST_CODE=a.mat_work_center_code)
                    GROUP BY ISNULL(a.mat_work_center_code,'') ORDER BY 2 DESC""")
    unmapped = [{"wc": r[0], "n": int(r[1])} for r in cur.fetchall()]
    return {"coop_lines": int(n or 0), "coop_wc": int(wc or 0),
            "coop_work_orders": int(wo or 0), "unmapped_wc": unmapped}


@router.post("/api/planrev/step/mat")
def planrev_step_mat(payload: dict = Body(...)):
    """⑤ 자재소요·조달 편성 — STEP7 + 조달 오버레이 + 협력사 점검(구 ⑥ 흡수)."""
    def _f(cur):
        _gate_or_raise(cur)          # ★라우팅을 실제로 쓰는 단계 → 재검증
        r = _step7_mat(cur)
        r.update(_step_source(cur))
        r.update(_coop_check(cur))   # ★구 ⑥ — 작업처 집계·미매핑 리포트
        return r
    return _run_step("T", _f, _by(payload))


@router.post("/api/planrev/step/coop")
def planrev_step_coop(payload: dict = Body(...)):
    """(폐지) ⑥ 협력사계획 편성 → ⑤ 에 흡수(2026-08-27).
       구 버전 화면·북마크 호환용으로 엔드포인트만 남긴다. 점검 결과를 그대로 반환."""
    return _run_step("S", _coop_check, _by(payload))


@router.post("/api/planrev/compose_all")
def planrev_compose_all(payload: dict = Body(...)):
    """⚡ 일괄작업 — ①②③④⑤⑥ 순차. 중간 실패시 거기서 중단.
       ★③(L)은 두 번 나뉜다: L=라인당김 맵(STEP5 이전) / L2=리드타임당김(STEP6 이후)."""
    user = _by(payload)
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT CONVERT(varchar(14),GETDATE(),120)")
        batch = "".join(ch for ch in str(cur.fetchone()[0]) if ch.isdigit())[:14]
    finally:
        nx.close()
    # ★H(생산계획이력생성)가 만드는 nx.sale_plan_item(040 원천)은 STEP5 산출물을 쓴다.
    #   그래서 K(STEP5/6) 뒤에 H 를 한 번 더 돌려 도번단위 LG계획을 확정한다.
    #   앞의 H 는 제번단위 sale_plan·스냅샷용(당김 전 원본 보존)이라 순서를 유지한다.
    seq = [("M", lambda cur: (_gate_or_raise(cur), _stepM_model(cur))[1]),
           ("H", lambda cur: _stepH_history(cur, "")),
           ("L", _ensure_line_pull),                                     # 라인당김 맵 먼저
           ("K", lambda cur: dict(_step5_item(cur), **_step6_part(cur))),
           ("L2", _stepL_pull),                                          # 그 위에 리드타임당김
           ("H2", lambda cur: _stepH_history(cur, "")),                  # ★040 원천 확정
           # ★T 가 협력사 점검(구 ⑥)까지 포함한다 — 별도 S 단계 호출 없음(2026-08-27).
           ("T", lambda cur: (_gate_or_raise(cur),
                              dict(_step7_mat(cur), **_step_source(cur), **_coop_check(cur)))[1])]
    done = []; t0 = time.time(); agg = {}
    for code, fn in seq:
        r = _run_step(code, fn, user, batch)
        agg.update({k: v for k, v in r.items() if k not in ("ok", "step", "warns")})
        done.append({"code": code, "name": _JOB_NAME.get(code, code),
                     "done_hms": r.get("done_hms"), "elapsed": r.get("elapsed")})
    nx = _nx(); cur = nx.cursor()
    try: _job_log(cur, "Z", user, int(time.time() - t0), "OK", "", None, batch)
    finally: nx.close()
    agg.update({"ok": True, "batch_id": batch, "steps": done, "elapsed": int(time.time() - t0)})
    return agg


@router.get("/api/planrev/job/status")
def planrev_job_status(ymd: str = Query("")):
    """단계별 최종 실행 + 최종 성공시각 + 업로드시각 — 화면 완료시각 박스 소스.

    ★ymd(2026-08-27 요청): 그 **일자에 실행된** 기록만 본다(YYYY-MM-DD 또는 YYMMDD).
      화면 계획기간 시작일을 넘기면 '그 날 무엇을 몇 시에 돌렸는지'가 보인다.
      비우면 종전대로 전체에서 각 단계의 마지막 실행."""
    _d = "".join(ch for ch in str(ymd or "") if ch.isdigit())
    if len(_d) == 6: _d = "20" + _d                     # YYMMDD → YYYYMMDD
    _w = " WHERE CONVERT(varchar(8),ins_dt,112)=?" if len(_d) == 8 else ""
    _p = [_d] if _w else []
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_job_log(cur)
        cur.execute("""SELECT j.job_code, j.job_name, j.status, j.elapsed_sec, j.row_count,
              CONVERT(varchar(8),j.ins_dt,108), CONVERT(varchar(10),j.ins_dt,23),
              ISNULL(j.ins_user,''), ISNULL(j.err_msg,'')
            FROM nx.plan_job_log j
            JOIN (SELECT job_code, MAX(job_seq) mx FROM nx.plan_job_log{} GROUP BY job_code) t
              ON t.job_code=j.job_code AND t.mx=j.job_seq""".format(_w), *_p)
        steps = {r[0]: {"name": r[1], "status": r[2], "elapsed": r[3], "rows": r[4],
                        "hms": r[5], "ymd": r[6], "by": r[7], "err": r[8]} for r in cur.fetchall()}
        cur.execute("""SELECT job_code, CONVERT(varchar(19),MAX(ins_dt),120) FROM nx.plan_job_log{}
            {} status='OK' GROUP BY job_code""".format(_w, "AND" if _w else "WHERE"), *_p)
        for g, dt in cur.fetchall():
            if g in steps: steps[g]["ok_dt"] = dt
        cur.execute("SELECT CONVERT(varchar(19),MAX(UPLOAD_DT),120), COUNT(*) FROM nx.plan_dtl")
        up, n = cur.fetchone()
        # ★SAC/RAC 녹색박스 소스 — CR_FLAG 별 최종 업로드시각·행수(레거시 동일 표기).
        #   C=SAC · R=RAC. 화면(screens.planrev.js)이 j.src 를 읽는다.
        #   ★ymd 를 주면 그 날 업로드분만(단계박스와 같은 기준).
        _wu = " WHERE CONVERT(varchar(8),UPLOAD_DT,112)=?" if len(_d) == 8 else ""
        src = {}
        cur.execute("""SELECT RTRIM(ISNULL(CR_FLAG,'')), CONVERT(varchar(8),MAX(UPLOAD_DT),108),
                 CONVERT(varchar(19),MAX(UPLOAD_DT),120), COUNT(*)
            FROM nx.plan_dtl{} GROUP BY RTRIM(ISNULL(CR_FLAG,''))""".format(_wu), *_p)
        for _cf, _hms, _dt, _n in cur.fetchall():
            _k = {"C": "SAC", "R": "RAC"}.get(str(_cf or "").strip().upper())
            if _k: src[_k] = {"hms": _hms, "dt": _dt, "rows": int(_n or 0)}
        return {"ok": True, "steps": steps, "upload_dt": up, "plan_rows": int(n or 0),
                "src": src, "ymd": (_d[:4] + "-" + _d[4:6] + "-" + _d[6:]) if len(_d) == 8 else ""}
    finally:
        nx.close()


@router.get("/api/planrev/job/log")
def planrev_job_log(limit: int = Query(100), code: str = Query("")):
    """실행이력 목록(최근순) — 레거시 PR_T_JOB_UPLOAD 조회 대응."""
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_job_log(cur)
        w = ""; p = []
        if code.strip(): w = " WHERE job_code=?"; p.append(code.strip())
        cur.execute("""SELECT TOP {} job_seq, job_code, job_name, ISNULL(batch_id,''), status, elapsed_sec,
              ISNULL(row_count,0), ISNULL(err_msg,''), ISNULL(ins_user,''),
              CONVERT(varchar(19),ins_dt,120) FROM nx.plan_job_log{} ORDER BY job_seq DESC""".format(
            max(1, min(int(limit or 100), 500)), w), *p)
        return {"ok": True, "rows": [{"seq": r[0], "code": r[1], "name": r[2], "batch": r[3],
                                      "status": r[4], "elapsed": r[5], "rows": r[6],
                                      "err": r[7], "by": r[8], "dt": r[9]} for r in cur.fetchall()]}
    finally:
        nx.close()


# ═══════════════════════════════════════════════════════════════════════
# 모델BOM 변경이력(w_pr_master_050) · 제외조건(w_pr_master_070)
#   ① 신규모델 검색·생성(M) 이 만든 결과를 확인하고, 잘못 생성된 조합을 제외조건으로 막는 화면.
#   ★삭제 = 일회성(다음 편성에서 다시 생성됨) / 제외조건 = 영구 차단(사용자 확인 2026-08-26)
#   제외조건은 편성 STEP M 의 3중 NOT EXISTS 중 하나로 이미 쓰이고 있다(planrev/soyo 동일).
#   쓰기는 nx 만(라이브 PARTNER_ERP 는 읽기전용) — 미러 nx.PR_M_MODEL_BOM_EXCEPT 에 기록.
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/planrev/modelbom/hist")
def planrev_modelbom_hist(ymd: str = Query(""), model: str = Query(""), item: str = Query(""),
                          limit: int = Query(300)):
    """모델BOM 변경이력 — 기준일자 이후 등록/수정된 (모델, 도번). 좌=모델 / 우=상세.
       ★nx.PR_M_MODEL_BOM(미러) 읽기 + nx.model_bom(웹 자동생성분) 합집합.
         2026-08-27 라이브 직독 → nx 로 전환. 실측 대사 결과 동일(양쪽 62,894행·차집합 0/0)이라
         결과 변화 없이 라이브 의존만 제거된다(§1 라이브는 조회도 최소화)."""
    nx = _nx(); cur = nx.cursor()
    try:
        d8 = "".join(ch for ch in str(ymd or "") if ch.isdigit())
        if len(d8) == 6: d8 = "20" + d8
        w, p = [], []
        if d8: w.append("CONVERT(varchar(8),a.INSERT_DATETIME,112)>=?"); p.append(d8)
        if model.strip(): w.append("a.MODEL_NO LIKE ?"); p.append("%" + model.strip() + "%")
        if item.strip():  w.append("a.C_ITEM_CODE LIKE ?"); p.append("%" + item.strip() + "%")
        wh = (" WHERE " + " AND ".join(w)) if w else ""
        cur.execute("""SELECT TOP {} RTRIM(a.MODEL_NO), RTRIM(a.C_ITEM_CODE), a.MAKE_YMD, a.TO_APPLY_YMD,
              a.USE_QTY, ISNULL(RTRIM(w.WORK_DESC),ISNULL(RTRIM(cu.CUST_DESC),ISNULL(RTRIM(i.WORK_CODE),''))) wc,
              ISNULL(a.INSERT_USER_ID,''), CONVERT(varchar(19),a.INSERT_DATETIME,120),
              ISNULL(a.INSERT_IP,''), ISNULL(a.INSERT_COMPUTER,''), ISNULL(a.INSERT_WINDOW,''),
              ISNULL(a.UPDATE_USER_ID,''), CONVERT(varchar(19),a.UPDATE_DATETIME,120),
              ISNULL(RTRIM(i.ITEM_DESC),'')
            FROM PARTNER_ERP_TEST3.nx.PR_M_MODEL_BOM a WITH(NOLOCK)
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i WITH(NOLOCK) ON i.ITEM_CODE=a.C_ITEM_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK w WITH(NOLOCK) ON w.WORK_CODE=i.WORK_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu WITH(NOLOCK) ON cu.CUST_CODE=i.IN_CUST_CODE
            {} ORDER BY a.INSERT_DATETIME DESC, a.MODEL_NO, a.C_ITEM_CODE""".format(
            max(1, min(int(limit or 300), 3000)), wh), *p)
        rows = [{"model": r[0], "item": r[1], "make_ymd": r[2], "to_ymd": r[3], "use_qty": float(r[4] or 0),
                 "wc": r[5], "by": r[6], "dt": r[7], "ip": r[8], "pc": r[9], "win": r[10],
                 "upd_by": r[11], "upd_dt": r[12], "item_desc": r[13], "src": "nx"}
                for r in cur.fetchall()]
        # 웹 자동생성분(nx.model_bom) — STEP M 산출
        w2, p2 = [], []
        if model.strip(): w2.append("MODEL_NO LIKE ?"); p2.append("%" + model.strip() + "%")
        if item.strip():  w2.append("C_ITEM_CODE LIKE ?"); p2.append("%" + item.strip() + "%")
        wh2 = (" WHERE " + " AND ".join(w2)) if w2 else ""
        cur.execute("""SELECT RTRIM(MODEL_NO), RTRIM(C_ITEM_CODE), APPLY_FROM, APPLY_TO, USE_QTY,
              ISNULL(REMARKS,''), ISNULL(INS_USER,''), CONVERT(varchar(19),INS_DT,120)
            FROM nx.model_bom{} ORDER BY INS_DT DESC""".format(wh2), *p2)
        for r in cur.fetchall():
            rows.append({"model": r[0], "item": r[1], "make_ymd": r[2], "to_ymd": r[3],
                         "use_qty": float(r[4] or 0), "wc": "", "by": r[6], "dt": r[7],
                         "ip": "", "pc": "", "win": r[5], "upd_by": "", "upd_dt": "",
                         "item_desc": "", "src": "웹(자동)"})
        models = {}
        for x in rows: models.setdefault(x["model"], 0); models[x["model"]] += 1
        return {"ok": True, "rows": rows,
                "models": [{"model": k, "n": v} for k, v in sorted(models.items())]}
    finally:
        nx.close()


@router.get("/api/planrev/modelbom/except")
def planrev_modelbom_except(model: str = Query(""), item: str = Query(""), limit: int = Query(1000)):
    """모델BOM 제외조건 — 이 조합은 신규모델생성에서 영구 제외된다."""
    nx = _nx(); cur = nx.cursor()
    try:
        w, p = [], []
        if model.strip(): w.append("a.MODEL_NO LIKE ?"); p.append("%" + model.strip() + "%")
        if item.strip():  w.append("a.C_ITEM_CODE LIKE ?"); p.append("%" + item.strip() + "%")
        wh = (" WHERE " + " AND ".join(w)) if w else ""
        cur.execute("""SELECT TOP {} RTRIM(a.MODEL_NO), RTRIM(a.C_ITEM_CODE),
              ISNULL(a.INSERT_USER_ID,''), CONVERT(varchar(19),a.INSERT_DATETIME,120),
              ISNULL(a.INSERT_IP,''), ISNULL(a.INSERT_COMPUTER,''), ISNULL(a.INSERT_WINDOW,''),
              ISNULL(RTRIM(i.ITEM_DESC),'')
            FROM nx.PR_M_MODEL_BOM_EXCEPT a WITH(NOLOCK)
            LEFT JOIN nx.PR_M_ITEM i WITH(NOLOCK) ON i.ITEM_CODE=a.C_ITEM_CODE
            {} ORDER BY a.MODEL_NO, a.C_ITEM_CODE""".format(
            max(1, min(int(limit or 1000), 5000)), wh), *p)
        rows = [{"model": r[0], "item": r[1], "by": r[2], "dt": r[3], "ip": r[4],
                 "pc": r[5], "win": r[6], "item_desc": r[7]} for r in cur.fetchall()]
        models = {}
        for x in rows: models.setdefault(x["model"], 0); models[x["model"]] += 1
        return {"ok": True, "rows": rows, "cnt": len(rows),
                "models": [{"model": k, "n": v} for k, v in sorted(models.items())]}
    finally:
        nx.close()


@router.post("/api/planrev/modelbom/except_add")
def planrev_modelbom_except_add(payload: dict = Body(...)):
    """제외조건 등록 — (모델, 도번) 조합. 다음 편성부터 신규모델생성에서 빠진다.
       ★쓰기는 nx 만(라이브 읽기전용). 선택적으로 nx.model_bom 의 해당 행도 삭제."""
    items = payload.get("items") or []
    if not items: raise HTTPException(400, "등록할 (모델, 도번) 이 없습니다.")
    by = str(payload.get("by", "") or "")[:20]
    drop = bool(payload.get("drop_current"))    # 현재 생성분도 지울지
    nx = _nx(); cur = nx.cursor()
    try:
        n = 0; dropped = 0
        for it in items:
            m = str(it.get("model", "") or "").strip()
            c = str(it.get("item", "") or "").strip()
            if not m or not c: continue
            cur.execute("""IF NOT EXISTS(SELECT 1 FROM nx.PR_M_MODEL_BOM_EXCEPT
                             WHERE MODEL_NO=? AND C_ITEM_CODE=?)
                  INSERT INTO nx.PR_M_MODEL_BOM_EXCEPT(MODEL_NO,C_ITEM_CODE,INSERT_USER_ID,
                    INSERT_DATETIME,INSERT_IP,INSERT_COMPUTER,INSERT_WINDOW)
                  VALUES(?,?,?,getdate(),'','','planuploadrev')""", m, c, m, c, by)
            n += 1
            if drop:
                cur.execute("DELETE FROM nx.model_bom WHERE MODEL_NO=? AND C_ITEM_CODE=?", m, c)
                dropped += int(cur.rowcount or 0)
        return {"ok": True, "added": n, "dropped": dropped}
    finally:
        nx.close()


@router.post("/api/planrev/modelbom/except_del")
def planrev_modelbom_except_del(payload: dict = Body(...)):
    """제외조건 해제 — 다시 신규모델생성 대상이 된다."""
    items = payload.get("items") or []
    if not items: raise HTTPException(400, "해제할 항목이 없습니다.")
    nx = _nx(); cur = nx.cursor()
    try:
        n = 0
        for it in items:
            m = str(it.get("model", "") or "").strip()
            c = str(it.get("item", "") or "").strip()
            if not m or not c: continue
            cur.execute("DELETE FROM nx.PR_M_MODEL_BOM_EXCEPT WHERE MODEL_NO=? AND C_ITEM_CODE=?", m, c)
            n += int(cur.rowcount or 0)
        return {"ok": True, "deleted": n}
    finally:
        nx.close()


# ═══════════════════════════════════════════════════════════════════════
# ③ 라인별 투입시간조정 (L) — 리드타임 당김. ★검토본 신규(2026-08-26)
#
# 레거시 SP_PR_CREATE_PLAN_파트별계획_생성_파트휴무당김 산식 이식.
#   1일 = 8시간 · 업무시간 08:00~17:00 · 점심 12:00~13:00 제외
#   CUM_LT_HR = 같은 (제번,도번) 안에서 **뒤 공정부터 역누적**
#     실측근거(레거시): seq1 S5 LT=16 → CUM=24 / seq2 S5-2 LT=8 → CUM=8
#     (앞 공정은 뒤 공정이 걸리는 시간만큼 더 일찍 시작해야 하므로)
#   일 당김 = 근무일 달력 기준(휴무일은 건너뜀) → 휴무일에 계획이 안 찍힌다
# ═══════════════════════════════════════════════════════════════════════

def _ensure_workday_tbl(cur):
    """근무일 달력 물질화 — 공통(HR_M_CALENDAR) ∩ 파트(PR_M_PART_CALENDAR) 덮어쓰기.
       파트달력에 값이 있으면 그것이 공통을 이긴다(레거시 f_get_relative_work_day_of_part 와 동일).
       rn = 파트별 근무일 일련번호 → N일 당김 = rn - N 로 O(1) 조회."""
    cur.execute("IF OBJECT_ID('nx.plan_workday') IS NOT NULL DROP TABLE nx.plan_workday")
    cur.execute("""
    WITH cal AS (   -- 공통 근무달력(팀A·주간) : work_stats 1,2,5,6,7 = 근무 / 3,4 = 휴무·휴일
      SELECT SUBSTRING(calendar_yymd,3,6) ymd6, work_stats
        FROM nx.HR_M_CALENDAR WHERE work_team='A' AND time_type='A'),
    part AS (       -- 파트별 달력(있으면 공통을 덮어씀)
      SELECT RTRIM(part_code) part_code, calendar_ymd ymd6, work_stats FROM nx.PR_M_PART_CALENDAR),
    parts AS (SELECT DISTINCT RTRIM(gagong_proc_code) part_code FROM nx.plan_part_dtl
               WHERE ISNULL(gagong_proc_code,'')<>''),
    merged AS (
      SELECT p.part_code, c.ymd6,
             ISNULL(pc.work_stats, c.work_stats) ws       -- ★파트달력 우선
        FROM parts p CROSS JOIN cal c
        LEFT JOIN part pc ON pc.part_code=p.part_code AND pc.ymd6=c.ymd6)
    SELECT part_code, ymd6, ROW_NUMBER() OVER(PARTITION BY part_code ORDER BY ymd6) rn
      INTO nx.plan_workday
      FROM merged WHERE ws IN ('1','2','5','6','7')""")
    cur.execute("CREATE INDEX ix_pwd ON nx.plan_workday(part_code, ymd6)")
    cur.execute("CREATE INDEX ix_pwd_rn ON nx.plan_workday(part_code, rn)")


def _ensure_line_pull(cur):
    """③-1 ★라인별 투입시간 당김 — nx.plan_line_pull 에 (제번,원본일자 → 당긴일자·시각).

    ★사용자 확인: "라인별 당김부터 먼저 계산해서 그래" — 리드타임 당김보다 먼저다.
    레거시 실측:
        ORG_PLAN_YMD=260827 ORG_OUTPUT_HM=1536  (엑셀 원본)
          → PLAN_YMD=260826 OUTPUT_HM=1136      (라인당김 후. STEP5/6 이 이걸 기준으로 편성)
          → PART_PLAN_YMD=260821                 (거기서 리드타임 추가)

    규칙(전부 레거시 데이터 역산):
      1) 근무일 기준. ORG 가 비근무일(토·일·휴무)이면 **그 이후 첫 근무일**에서 센다.
         실측 비근무일 200행: next_wd 73.5% vs prev_wd 26.5%
      2) 시각 = ORG시각 - MAINT_HHMM. 점심 보정 없음(있으면 1.1%, 없으면 38.8%)
      3) 08:00 미만이면 하루 더 당기고 **전일 종업시각**에서 부족분만큼 뺀다.
         종업시각은 근무유형별(아래 WORK_END_BY) — 17:00 + 저녁 0:30 + 잔업N시간.
      4) 결과가 기준일 이전이면 기준일 + '0750'(당일이전계획). 실측 112건 전부 일치.

    ⛔레거시 LG_INPUT_YMD/HM 채택은 **삭제**했다(2026-08-27). 웹은 레거시를 참조하지 않는다.
      ※그 컬럼은 화면 「파트별 생산계획」의 'LG INPUT' 이 아니다 — 대사 기준을 혼동했던 것.
        제번 6I1M0BBK 실측:
          화면 'LG OUTPUT시간' = ORG_PLAN_YMD/ORG_OUTPUT_HM  260827 11:35 (엑셀원본)
          화면 'LG INPUT'      = PLAN_YMD/OUTPUT_HM          260827 07:50 ← ★라인당김 결과
          LG_INPUT_YMD/HM                                    260825 18:05 (화면에 없음·별개)
      대사는 편성 밖 검증 스크립트로 한다. 기준 = 라이브 PLAN_YMD/OUTPUT_HM.

    ★근무유형 코드(HR_M_CALENDAR.work_stats / PR_M_LINE_CALENDAR.WORK_STATS).
      「라인별 달력관리」 화면 코드마스터(7종)와 대조 확정:
        1 = 출근(잔업2시간) → 19:30    2 = 출근(정상근무) → 17:00
        3 = 일요일(휴무)               4 = 휴무
        5 = 출근(잔업3시간) → 20:30    6 = 출근(잔업4시간) → 21:30
        7 = 출근(4시간근무) → 12:00
      라인달력이 공통을 덮어쓴다(예: C1 260829=2, CA 260827=2·260831=4, CG 260827=4).
      carry 보정 실측(1,565건): ORG코드1·전일코드1 → 차이 0 (1,483건 94.8%).
      나머지 82건은 코드조합별 상수 보정(1·2→+37분, 2·1→+51분) — 미해결.

    ⚠ nx.plan_dtl.PLAN_YMD 를 직접 수정하지 않는다 — PK(WORK_ORDER,PLAN_YMD) 충돌
      (레거시는 제번당 1행이라 가능했지만 웹은 (제번,일자) 그레인). 별도 맵을 STEP5 가 참조."""
    DAY_START = 480        # 08:00
    # ★근무유형(WORK_STATS)별 종업시각 — PR_M_LINE_CALENDAR 코드마스터 기준(사용자 확인 2026-08-27).
    #   정상근무 종업 17:00, **17:00~17:30 은 저녁시간이라 잔업 계산에서 제외**한다.
    #     → 잔업 N시간 종업 = 17:00 + 0:30(저녁) + N시간
    #   코드1 잔업2시간 = 19:30  ← 역산 실측 1,581건(99%) 일치
    #   코드2 정상근무  = 17:00
    #   코드3 일요일 / 코드4 휴무 (비근무)
    #   코드5 잔업3시간 = 20:30   코드6 잔업4시간 = 21:30   코드7 4시간근무 = 12:00
    WORK_END_BY = {'1': 1170, '2': 1020, '5': 1230, '6': 1290, '7': 720}
    WORK_END = WORK_END_BY['1']        # 기본값(코드 미상) = 잔업2시간 19:30

    # ★라인별 근무일 달력 — 공통 행을 라인 행이 덮어쓴다(SP f_get_relative_work_day 와 동일).
    #   ★정본 = nx.line_calendar 의 line_no='공통' 행. 미러(HR_M_CALENDAR)는 **폴백**일 뿐.
    #     (2026-08-27 실측: 정본 '공통' 3,926행 · 미러 HR_M_CALENDAR 와 차이 0건 확인)
    #   근무유형 코드는 LG 엑셀에 안 들어오므로 「라인별달력」 화면에서 수기 입력한다
    #   (src='MANUAL', prodinfo.linecal_save). LG 업로드는 work_code 만 갱신하고 코드는 보존.
    _co = []
    try:
        cur.execute("""SELECT CONVERT(varchar(6),cal_ymd,12), ISNULL(work_stats,'')
                         FROM nx.line_calendar
                        WHERE line_no=N'공통' AND ISNULL(work_stats,'')<>''
                        ORDER BY cal_ymd""")
        _co = [(str(r[0]).strip(), str(r[1] or '').strip()) for r in cur.fetchall()]
    except Exception:
        pass
    if not _co:                        # 폴백: 미러 직독(정본이 비었을 때만)
        cur.execute("""SELECT SUBSTRING(calendar_yymd,3,6), work_stats FROM nx.HR_M_CALENDAR
                        WHERE work_team='A' AND time_type='A' ORDER BY calendar_yymd""")
        _co = [(r[0], r[1]) for r in cur.fetchall()]
    # ★정본 = nx.line_calendar (웹 자체). 레거시 미러 nx.PR_M_LINE_CALENDAR 는 여기로 이관됨
    #   (_schema/nx_line_calendar_merge.sql · 2026-08-27 · 18,247행 이관 → 총 18,897행·37라인).
    #   CLAUDE.md §1-9 "마스터 정본 = 재구축 클린본, 레거시 미러 아님".
    #   미러 직독은 폴백으로만 남긴다(정본이 비었을 때).
    _lncal = {}
    _lnhrs = {}                        # ★라인별 LG 가동시간 (line → ymd → work_code)
    try:
        cur.execute("""SELECT line_no, CONVERT(varchar(6),cal_ymd,12),
                              ISNULL(work_stats,''), ISNULL(work_code,'')
                         FROM nx.line_calendar
                        WHERE ISNULL(work_stats,'')<>'' OR ISNULL(work_code,'')<>''""")
        for _ln, _y, _w, _h in cur.fetchall():
            _ln = str(_ln).strip(); _y = str(_y).strip()
            if str(_w or '').strip():
                _lncal.setdefault(_ln, {})[_y] = str(_w).strip()
            if str(_h or '').strip():
                _lnhrs.setdefault(_ln, {})[_y] = str(_h).strip()
    except Exception:
        pass
    if not _lncal:                     # 폴백: 미러 직독
        cur.execute("SELECT RTRIM(LINE_NO), CALENDAR_YMD, WORK_STATS FROM nx.PR_M_LINE_CALENDAR")
        for _ln, _y, _w in cur.fetchall():
            _lncal.setdefault(str(_ln).strip(), {})[str(_y).strip()] = str(_w or '').strip()
    _WORKING = ('1', '2', '5', '6', '7')
    _codict = dict(_co)          # 공통달력 ymd→work_stats (종업시각 판정용)

    # ★LG 라인스케줄 가동시간 → 종업시각(2026-08-27).
    #   nx.line_calendar(LG 엑셀 업로드본)의 work_code 가 실제 가동시간이다(8·11·10.5·9.5·7.5…).
    #   웹 「라인별달력」 화면에 보이는 그 숫자. WORK_STATS(코드 1~7)보다 정밀하다.
    #   ★가동시간 = 8h + 잔업시간. 종업 = 17:00 + 저녁 0:30 + 잔업h (17:00~17:30 저녁 제외)
    #       8    → 잔업0    → 17:00
    #       9.5  → 잔업1.5h → 19:00      10   → 잔업2h   → 19:30
    #       10.5 → 잔업2.5h → 20:00      11   → 잔업3h   → 20:30
    #     ★8h 미만(7·7.5)도 8h 로 본다(사용자 확인 2026-08-27 — "크게 의미 없다").
    #   ★숫자가 아닌 코드(2026-08-27 사용자 확인): 재작업·E·A·B·SKD·CC/지원·rac/이동 등은
    #     **모두 가동일이며 8시간으로 본다**(종업 17:00). 실측으로도 전부 평일이고 공통달력 코드1(근무).
    #     단 'SKD/11'·'생산8/재3' 처럼 숫자가 섞이면 그 숫자를 가동시간으로 쓴다.
    #
    # ══════════════════════════════════════════════════════════════════════════
    # ★★2026-08-27 — 레거시 원문 SP_LG_SCHEDULE 확보로 아래 전부 확정(추정 종료).
    #   보조함수 2개도 평문 확보: f_get_relative_work_day · f_get_end_hhmm_lg_plan
    #
    #   f_get_relative_work_day(라인, 일자, N):
    #       PR_M_LINE_CALENDAR 의 **line_no='공통' 행**을 기준으로 하고
    #       같은 라인 행이 있으면 그 날만 덮어쓴다(ISNULL(b.work_stats, a.work_stats)).
    #       work_stats IN ('1','2','5','6','7') 인 날만 근무일로 세고, @as_ymd 이하에서
    #       역순 N번째(row_num=N)를 돌려준다. 반환 = 일자6 + work_stats1 (7자리).
    #       ⛔**LG 가동시간(work_code)은 어디에도 안 쓴다.** 근무일 판정은 오직 코드.
    #
    #   f_get_end_hhmm_lg_plan(일자, 라인, 코드):
    #       코드1→1930 · 2→1700 · 5→2030 · 6→2130 · 7→1200 · 그외→1700
    #       그리고 **그날 같은 라인 계획의 MAX(ORG_OUTPUT_HM) 이 더 크면 그 값으로 상향**.
    #       (18:03·17:59 같은 종업 이후 시각이 보존되던 이유가 이것)
    # ══════════════════════════════════════════════════════════════════════════

    # ★근무일 달력 = PR_M_LINE_CALENDAR '공통' 행 + 라인 행 덮어쓰기 (SP 원문 그대로).
    #   정본 nx.line_calendar 에 '공통'/라인 코드가 있으면 그것을, 없으면 미러를 읽는다.
    #   ⛔LG 가동시간(work_code)은 근무일·종업시각 **어디에도 쓰지 않는다** —
    #     C1 260912·260919(토)는 가동 8h 가 있어도 '공통'=4(휴무)라 레거시가 건너뛰고,
    #     260829·260905(토)는 C1 행에 코드2 가 있어 근무로 센다. 실측과 정확히 일치.
    _base_cal = dict(_co)                      # ymd → 공통 work_stats (위에서 정본 '공통' 행으로 로드됨)
    _codict = _base_cal                        # 종업시각 판정도 같은 기준
    _cal_ymds = sorted(_base_cal.keys())       # 달력 전체 일자(오름차순)

    _wdcache = {}
    def _wd_of(line):
        """라인별 근무일 목록.

           ★판정 우선순위(2026-08-31 사용자 확정):
             1) **LG 가동시간(work_code)이 있으면 근무일**(정상근무).
                ★공통이 휴무(토요일 등)여도 가동시간이 있으면 근무 — 특근이 이 경우다.
                  7.5 → 8시간근무 · 8 → 정상근무 · 11 → 잔업3시간
                숫자가 아닌 값(E·A·B·SKD·재작업 등)도 "그 날 돌린다"는 뜻이므로 근무.
                ※화면(라인별달력 팝업)은 가동시간이 있으면 근무유형 드롭다운을 잠가
                  "가동 8h 인데 휴무" 같은 모순 데이터가 아예 안 생기게 한다.
                  휴무로 만들려면 **가동시간을 지운다** → 그러면 2)로 내려간다.
             2) 가동시간이 없고 **라인 근무유형(work_stats)이 지정됐으면 그 값**.
                ★공통이 근무여도 라인이 휴무면 휴무 — 그 라인은 그날 안 돌리므로
                  계획이 앞 근무일로 **더 당겨진다**.
             3) 둘 다 없으면 공통 달력을 따른다(수기 라인 C2·C3… 이 여기 해당).

           ⚠하면 안 되는 것(실측 사고):
             "가동시간 없으면 무조건 휴무" — LG 엑셀은 일부 날짜만 담아서
             C1 이 85일만 근무일이 되고 평일 대부분이 죽는다. 가동시간이 없는 날은
             반드시 근무유형·공통으로 내려가야 한다.

           ⛔레거시(f_get_relative_work_day)는 가동시간을 안 보고 work_stats 만 썼다.
             그래서 C1 260912·260919(토)는 가동 8h 가 있어도 휴무로 처리돼 계획이
             260909 로 당겨졌다(실측 29행·125개). 실제 업무는 그 날 가동하므로
             레거시가 틀린 것 — 웹은 가동시간을 정본으로 삼는다."""
        _k = line or ''
        if _k not in _wdcache:
            _ov = _lncal.get(_k, {})
            _hr = _lnhrs.get(_k, {})
            _out = []
            for _y in _cal_ymds:
                if str(_hr.get(_y, '')).strip():
                    # (1) 가동시간 있음 → 근무(정상). 공통이 휴무여도 특근으로 근무.
                    #     화면도 이때 근무유형을 잠가 "가동 8h 인데 휴무" 모순을 못 만든다.
                    _out.append(_y)
                    continue
                _w = str(_ov.get(_y, '')).strip()          # 라인에 직접 지정한 근무유형
                if _w:
                    # (2) 가동시간 없고 근무유형 지정됨 → 그 값(공통이 근무여도 휴무면 휴무)
                    if _w in _WORKING:
                        _out.append(_y)
                    continue
                # (3) 둘 다 없음 → 공통 달력
                if str(_base_cal.get(_y, '')).strip() in _WORKING:
                    _out.append(_y)
            _wdcache[_k] = _out
        return _wdcache[_k]

    # ★종업시각 상향 — f_get_end_hhmm_lg_plan 의 MAX(ORG_OUTPUT_HM) 부분.
    #   (일자, 라인) → 그날 그 라인 계획의 최대 원본시각(분). 코드 기준 종업보다 크면 이걸 쓴다.
    _maxorg = {}
    try:
        # ⚠nx.plan_dtl 의 시각 컬럼은 START_HM 이다(OUTPUT_HM 아님 — 그 이름을 쓰면
        #   쿼리가 예외로 빠져 _maxorg 가 통째로 비고 상향이 죽는다. 2026-08-27 실측 140건)
        # ★제번당 **최소일자 1행**만 집계한다 — SP 맨 앞의 병합 블록과 같은 효과.
        #     ---- 여러일자로 걸쳐잇는 같은 W/O일 경우 1개로 합친다.
        #     update ... set plan_qty = a.plan_qty + b.plan_qty ... / delete ... PLAN_YMD > min_plan_ymd
        #   레거시는 계산 전에 제번을 1행으로 합치므로 MAX 집계에 뒷일자 행이 안 들어간다.
        #   웹은 (제번,일자) 그레인이라 167행이 더 있고, 그대로 MAX 를 잡으면 종업 캡이
        #   과대평가된다(CJ 260910 웹 20:28 vs 레거시 19:32 → 20건 어긋남. 2026-08-27).
        #   ⚠웹 원본은 건드리지 않는다 — 집계할 때만 대표행으로 제한한다.
        cur.execute("""WITH R AS (
                         SELECT ISNULL(NULLIF(ORG_PLAN_YMD,''),PLAN_YMD) ymd,
                                RTRIM(ISNULL(LINE_NO,'')) ln,
                                ISNULL(NULLIF(ORG_OUTPUT_HM,''), START_HM) hm,
                                ROW_NUMBER() OVER(PARTITION BY RTRIM(WORK_ORDER)
                                  ORDER BY ISNULL(NULLIF(ORG_PLAN_YMD,''),PLAN_YMD),
                                           ISNULL(NULLIF(ORG_OUTPUT_HM,''), START_HM)) rn
                           FROM nx.plan_dtl)
                       SELECT ymd, ln, MAX(hm) FROM R WHERE rn=1 GROUP BY ymd, ln""")
        for _y, _l, _hm in cur.fetchall():
            _s = str(_hm or '').strip()
            if len(_s) == 4 and _s.isdigit():
                _maxorg[(str(_y).strip(), str(_l).strip())] = int(_s[:2]) * 60 + int(_s[2:])
    except Exception:
        pass

    def _hrs_end(h):
        """LG 가동시간 → 종업시각(분). 사용자 확정 규칙(2026-08-31):
             7.5 → 8시간근무 · 8 → 정상근무(17:00) · 11 → 잔업3시간(20:30)
           산식 = 17:00 + 저녁 0:30 + 잔업h,  잔업h = 가동시간 − 8 (8 이하는 0).
             8→17:00 · 9.5→19:00 · 10→19:30 · 10.5→20:00 · 11→20:30
           숫자가 아닌 값(E·A·B·SKD·재작업 등)은 가동일이며 8시간으로 본다(17:00).
           'SKD/11'·'생산8/재3' 처럼 숫자가 섞이면 그 숫자를 쓴다."""
        import re as _re
        s = str(h or '').strip()
        if not s:
            return None
        m = _re.search(r'(\d+(?:\.\d+)?)', s)
        if not m:
            return WORK_END_BY['2']            # 문자코드 = 정상근무 17:00
        try:
            v = float(m.group(1))
        except Exception:
            return WORK_END_BY['2']
        ot = max(0.0, v - 8.0)                 # 8h 이하(7·7.5 포함)는 잔업 0
        return int(round(1020 + (30 + ot * 60 if ot > 0 else 0)))

    def _end_of(line, ymd):
        """종업시각(분).
           ★_wd_of 와 **같은 우선순위**를 쓴다(2026-08-31):
             1) LG 가동시간으로 계산(_hrs_end: 7.5·8→17:00 · 11→20:30)
             2) 없으면 라인 근무유형 코드별 고정값(1→19:30 · 2→17:00 …)
             3) 둘 다 없으면 공통 달력 코드
           그날 그 라인 계획의 MAX(ORG_OUTPUT_HM) 이 더 크면 그 값으로 상향(SP 원문 동일)."""
        if not ymd: return WORK_END
        _m = _hrs_end(_lnhrs.get(line or '', {}).get(ymd))
        if _m is None:
            _w = str(_lncal.get(line or '', {}).get(ymd, '')).strip()
            _m = WORK_END_BY.get(_w or str(_base_cal.get(ymd, '1')).strip(), WORK_END_BY['2'])
        _mx = _maxorg.get((ymd, line or ''))
        return _mx if (_mx is not None and _mx > _m) else _m

    _wd = _wd_of('')          # 공통(폴백용)
    _rn = {y: i for i, y in enumerate(_wd)}

    # ⛔레거시 PR_T_PLAN_DTL 조회 삭제(2026-08-27) — **웹은 레거시 데이터를 참조하지 않는다.**
    #   레거시 LG_INPUT_YMD/HM 은 곧 쓰지 않을 데이터이므로 편성 경로에서 완전히 끊는다.
    #   라인당김은 아래 산식만으로 계산한다:
    #     일자 = 라인 근무일 달력에서 (MAINT_DAY + carry) 칸 앞
    #     시각 = 계획시각 − MAINT_HHMM, 08:00 미만이면 하루 더 당기고 전일 종업에서 부족분만큼
    #     종업 = 근무유형별(WORK_END_BY): 17:00 + 저녁 0:30 + 잔업N시간
    #   레거시와의 대사는 편성 밖에서(검증 스크립트로) 한다 — 코드가 답을 베끼지 않게.

    import bisect as _bis

    def _nidx(L, y):
        """y 이상 첫 근무일 인덱스 (y 가 근무일이면 y). L = 그 라인의 근무일 목록."""
        if not L: return 0
        i = _bis.bisect_left(L, y)
        return min(i, len(L) - 1)

    def _mins(hm):
        try:
            if hm and len(hm) == 4 and hm.isdigit(): return int(hm[:2]) * 60 + int(hm[2:])
        except Exception: pass
        return None

    # ★입력 = 원본(ORG_*) — SP 는 @db_org_plan_ymd/@db_org_output_hm 로 계산한다.
    #   (SP 앞부분에서 ORG_* 를 PLAN_*/OUTPUT_* 로 백업해 두고 항상 원본에서 재계산)
    # ★라인마스터도 SP 와 동일하게 **APPLY_YMD <= ORG_PLAN_YMD 중 가장 이른 행**을 쓴다
    #   (SP: TOP 1 ... WHERE APPLY_YMD <= ORG_PLAN_YMD ORDER BY APPLY_YMD).
    cur.execute("""SELECT d.WORK_ORDER, ISNULL(NULLIF(d.ORG_PLAN_YMD,''), d.PLAN_YMD),
             ISNULL(NULLIF(d.ORG_OUTPUT_HM,''), ISNULL(NULLIF(d.START_HM,''),'0800')),
             ISNULL(l.MAINT_DAY,0), ISNULL(l.MAINT_HHMM,''), RTRIM(ISNULL(d.LINE_NO,''))
        FROM nx.plan_dtl d
        OUTER APPLY (SELECT TOP 1 m.MAINT_DAY, m.MAINT_HHMM
                       FROM nx.PR_M_LINE_NO m
                      WHERE RTRIM(m.LINE_NO)=RTRIM(d.LINE_NO)
                        AND m.APPLY_YMD <= ISNULL(NULLIF(d.ORG_PLAN_YMD,''), d.PLAN_YMD)
                      ORDER BY m.APPLY_YMD) l""")
    _src = cur.fetchall()
    # ★편성 기준일 @as_fr_ymd — SP 마지막 블록이 이 날짜로 클램프한다.
    #     if @ls_plan_ymd < @as_fr_ymd → set @ls_plan_ymd=@as_fr_ymd, @ls_output_hm='0750'
    #   원본(ORG_PLAN_YMD) 최소일자를 기준일로 본다. MIN(PLAN_YMD) 은 이미 당겨진 값이라
    #   클램프가 걸리지 않아 07:50 건 115개가 어긋났다(2026-08-27).
    cur.execute("SELECT ISNULL(MIN(ISNULL(NULLIF(ORG_PLAN_YMD,''), PLAN_YMD)),'') FROM nx.plan_dtl")
    _base = str(cur.fetchone()[0] or '').strip()
    _bi = 0

    # ★라인별 강제 하한(SP_LG_SCHEDULE 원문 하드코딩) — 2026-08-27 확정.
    #     /*C1,C3라인은 강제로 17:00으로 변경하여 늦게 작업하도록 강제 편성*/
    #     if @db_line_no in ('C1','C3') and @ls_output_hm < '1700' → '1700'
    #     /*C2라인은 강제로 15:00 … 17.11.29*/  → '1500'
    #   ⛔MD 와 무관한 **라인 이름 예외**다. 종전엔 이걸 "MD>=2 면 17:00 리셋" 으로 추정해
    #     C1(MD=2)에만 우연히 맞고 CP2(MD=2)·SG(MD=3)에서 어긋났다.
    _FLOOR_HM = {'C1': 1020, 'C3': 1020, 'C2': 900}

    _LUNCH = ((1020, 1050), (720, 780))        # 저녁 17:00~17:30 · 점심 12:00~13:00

    _out = []
    for _wo, _org, _shm, _md, _mh, _lno in _src:
        _wo = str(_wo).strip(); _org = str(_org).strip()
        _md = int(_md or 0); _mm = _mins(str(_mh or '').strip()) or 0
        _t0 = _mins(str(_shm or '').strip())
        if _t0 is None: _t0 = DAY_START
        _lk = str(_lno or '').strip()
        _L = _wd_of(_lk)
        if not _L:
            _out.append((_wo, _org, _md, _mm, _org, "%02d%02d" % (_t0 // 60, _t0 % 60)))
            continue

        # (1) 계획일이 휴무면 그 이전 근무일의 종업시각부터 시작 (SP 앞부분).
        #     f_get_relative_work_day(...,0) 이 @as_ymd 이하 첫 근무일을 주므로,
        #     그 값이 원래 일자보다 작으면 = 휴무였다는 뜻.
        _i = _bis.bisect_right(_L, _org) - 1
        if _i < 0:
            _i = 0
            _cur_d = _L[0]
        else:
            _cur_d = _L[_i]
        if _cur_d < _org:                      # 계획일이 휴무 → 이전 근무일 종업으로
            _t0 = max(_t0, _end_of(_lk, _cur_d))

        # (2) 일수 당김 — 근무일 달력에서 MAINT_DAY 칸 앞 (시각은 그대로 들고 감)
        #   ★달력 앞으로 벗어난 경우(_under)를 기억한다. SP 는 @ldt_org_time 을 실제 날짜로
        #     빼므로 기준일보다 앞선 일자가 나오고 최종 블록에서 07:50 으로 클램프된다.
        #     웹은 근무일 리스트 인덱스가 0 에서 멈춰 기준일에 걸터앉으므로,
        #     "0 아래로 내려가려 했다"는 사실 자체를 클램프 조건에 써야 한다.
        _under = False
        if _md > 0:
            _ni = _i - _md
            if _ni < 0: _under = True
            _i = max(0, _ni)
            _cur_d = _L[_i]

        # (3) 시각 당김 — MAINT_HHMM 만큼 그대로 뺀다.
        #   ⛔SP 의 점심(12~13)·저녁(17:00~17:30) 보정 블록은 **실행되지 않는 죽은 코드**다:
        #       if @ldt_org_time > convert(datetime, '17:00') ...
        #     @ldt_org_time 은 날짜가 붙은 datetime(2026-08-27 19:07)인데
        #     convert(datetime,'17:00') 은 **1900-01-01 17:00** 이라 비교가 항상 참/거짓으로
        #     고정된다(1900년보다 크므로 첫 조건은 늘 참, 두 번째 `< 17:30` 은 늘 거짓).
        #     → 결과적으로 보정이 한 번도 적용되지 않는다.
        #   실측 확증: CA(Mmin=360) 6I0M01J8 ORG 19:07 → 레거시 13:07 = 정확히 −6:00,
        #     보정 0분. 보정을 넣었더니 −60분 793건이 어긋났다(2026-08-27).
        _t1 = _t0
        _rest = 0
        if _mm > 0:
            _minus = _mm
            _avail = _t1 - DAY_START           # 그날 08:00 까지 남은 분
            if _minus <= _avail:
                _t1 -= _minus
            else:
                _rest = _minus - _avail        # 전일로 넘길 잔여
                _i = max(0, _i - 1)            # SP: @ldt_org_time - 1 (달력일 −1 → 이후 근무일 보정)
                _cur_d = _L[_i]
                _t1 = 1439                     # 23:59

        # (4) 도착일 종업시각으로 캡 → 남은 잔여분 차감 (SP 후반부)
        _end = _end_of(_lk, _cur_d)
        if _t1 > _end: _t1 = _end
        if _rest > 0: _t1 -= _rest
        if _t1 < 0: _t1 = 0

        # (5) 라인 강제 하한 (C1/C3=17:00 · C2=15:00)
        _fl = _FLOOR_HM.get(_lk)
        if _fl is not None and _t1 < _fl: _t1 = _fl

        _py = _cur_d
        # (6) ★기준일 클램프 — SP 최종 블록. **라인 하한(5)보다 뒤**에 온다.
        #       if @ls_plan_ymd < @as_fr_ymd → @ls_plan_ymd=@as_fr_ymd, @ls_output_hm='0750'
        #     기준일보다 앞으로 당겨진 건은 기준일 07:50(시업 10분전)에 몰아 넣는다.
        #     ⛔순서가 중요하다: C1 하한(17:00)을 먼저 적용해도 이 클램프가 07:50 으로 덮는다.
        if _base and (_py < _base or _under):
            _py, _t1 = max(_py, _base), 470    # 07:50
        _phm = "%02d%02d" % (_t1 // 60, _t1 % 60)
        # ⛔레거시 값 채택 제거(2026-08-27) — **웹 산식 결과를 그대로 쓴다.**
        #   종전엔 여기서 LG_INPUT_YMD/HM 으로 _py/_phm 을 덮어썼다. 그런데 그 컬럼은
        #   화면 「파트별 생산계획」의 'LG INPUT' 이 아니다 — 대사 기준이 틀렸던 것.
        #   ★실측 대응(제번 6I1M0BBK):
        #       화면 'LG OUTPUT시간' = ORG_PLAN_YMD/ORG_OUTPUT_HM  260827 11:35 (엑셀원본)
        #       화면 'LG INPUT'      = PLAN_YMD/OUTPUT_HM          260827 07:50 ← ★라인당김 결과
        #       LG_INPUT_YMD/HM                                    260825 18:05 (화면에 없음·별개)
        _out.append((_wo, _org, _md, _mm, _py, _phm))

    cur.execute("IF OBJECT_ID('nx.plan_line_pull') IS NOT NULL DROP TABLE nx.plan_line_pull")
    cur.execute("""CREATE TABLE nx.plan_line_pull(wo varchar(20), org varchar(6), mday int,
        mmin int, pulled varchar(6), pulled_hm varchar(4))""")
    cur.fast_executemany = True
    cur.executemany("INSERT INTO nx.plan_line_pull(wo,org,mday,mmin,pulled,pulled_hm) VALUES(?,?,?,?,?,?)", _out)
    cur.execute("CREATE INDEX ix_plp ON nx.plan_line_pull(wo, org)")
    _n = len(_out); _p = sum(1 for x in _out if x[4] < x[1])
    return {"line_rows": _n, "line_pulled": _p}


def _stepL_pull(cur):
    """③-2 리드타임 당김 — nx.plan_part_dtl 의 PART_PLAN_YMD·PART_OUTPUT_HM·AMPM 을 채운다.

    ※ 라인별 당김은 _line_pull_plan_dtl() 이 plan_dtl.PLAN_YMD 에 이미 반영했다.
      여기서는 그 위에 리드타임(CUM_LT_HR) 당김만 얹는다(레거시 순서와 동일).
    ★멱등: 매번 CUM_LT_HR 부터 다시 계산하므로 여러 번 눌러도 결과가 같다.
    ★선행: ④ 파트별 계획생성(K) 이 먼저 돌아야 한다(plan_part_dtl 필요)."""
    # ── 0) 당김 결과 컬럼 보장 (원본 plan_part_dtl 은 SELECT INTO 라 없다) ──
    for col, typ in (("cum_lt_hr", "decimal(9,2)"), ("pull_day", "int"), ("pull_hr", "decimal(9,2)"),
                     ("part_plan_ymd", "varchar(6)"), ("part_output_hm", "varchar(4)"),
                     ("output_hm", "varchar(4)"), ("ampm", "varchar(2)"), ("part_ampm", "varchar(2)")):
        cur.execute("IF COL_LENGTH('nx.plan_part_dtl',?) IS NULL"
                    " EXEC('ALTER TABLE nx.plan_part_dtl ADD ' + ? + ' " + typ + "')", col, col)
    _ensure_workday_tbl(cur)

    # ── 1) OUTPUT_HM 시드 = ★③ 라인당김 결과(nx.plan_line_pull) ──
    #   레거시 대응: PR_T_PLAN_PART_DTL.OUTPUT_HM = PR_T_PLAN_DTL.OUTPUT_HM (실측 100.0% 일치).
    #     즉 파트별계획은 **라인당김 후 시각**을 그대로 물려받는다.
    #   ⛔plan_item_dtl 을 시드로 쓰면 안 된다 — 라인당김 반영이 99.6% 에 그쳐
    #     기준일 클램프(07:50) 건들이 옛 시각(1700)으로 남는다.
    #     실측(2026-08-27): 그 0.4% 가 ④ 시각 불일치 281건 + 일자 불일치 다수의 원인이었다.
    #     (레거시 미러 PR_T_PLAN_ITEM_DTL 도 이전 편성분 260826 1700 을 들고 있어 같은 함정)
    #   ★제번당 대표행(최소 org) 기준 — ③ 과 동일 규칙.
    cur.execute("""UPDATE a SET a.output_hm = ISNULL(NULLIF(d.pulled_hm,''),'0800')
                     FROM nx.plan_part_dtl a
                     JOIN (SELECT wo, pulled_hm FROM (
                             SELECT RTRIM(wo) wo, pulled_hm,
                                    ROW_NUMBER() OVER(PARTITION BY RTRIM(wo) ORDER BY org) rn
                               FROM nx.plan_line_pull) x WHERE rn=1) d
                       ON d.wo=RTRIM(a.work_order)""")
    # 폴백: ③ 결과에 없는 제번(A/S 추가계획 등)은 STEP5 시각을 쓴다
    cur.execute("""UPDATE a SET a.output_hm = ISNULL(NULLIF(d.OUTPUT_HM,''),'0800')
                     FROM nx.plan_part_dtl a
                     JOIN (SELECT WORK_ORDER, MAX(ISNULL(NULLIF(OUTPUT_HM,''),'0800')) OUTPUT_HM
                             FROM nx.plan_item_dtl GROUP BY WORK_ORDER) d ON d.WORK_ORDER=a.work_order
                    WHERE ISNULL(a.output_hm,'')=''
                      AND NOT EXISTS (SELECT 1 FROM nx.plan_line_pull p WHERE RTRIM(p.wo)=RTRIM(a.work_order))""")
    cur.execute("UPDATE nx.plan_part_dtl SET output_hm='0800' WHERE ISNULL(output_hm,'')=''")

    # ── 2) CUM_LT_HR ──
    #   ★STEP6(_step6_sql) 이 레거시 SP 원문대로 이미 계산해 plan_part_dtl 에 실어 놓았다.
    #     (가상품목 행을 살려 누적 → 상위레벨 mat_code 로 부모 잇기 → 가상품목 삭제)
    #     여기서는 다시 계산하지 않는다. 없으면 0 으로 두고 당김만 진행.
    cur.execute("IF COL_LENGTH('nx.plan_part_dtl','cum_lt_hr') IS NULL"
                " ALTER TABLE nx.plan_part_dtl ADD cum_lt_hr decimal(9,2)")
    cur.execute("UPDATE nx.plan_part_dtl SET cum_lt_hr=0 WHERE cum_lt_hr IS NULL")

    # ── 3) PULL_DAY / PULL_HR (1일=8시간) + 시각 정규화 ──
    #   업무시간 08:00~17:00, 점심 12:00~13:00. 원본시각이 이 밖이면 먼저 끌어들인다.
    #   ★상위시각이 점심구간(12:00~12:59)일 때의 방향은 pull_hr 유무로 갈린다(실측 확정):
    #       pull_hr=0 → '1300'(다음 작업 시작)   pull_hr≠0 → '1200'(직전 작업 종료)
    #     실측: 13:00 고정 99.66% → 이 분기 적용 99.99%(17,227/17,228).
    cur.execute("""UPDATE nx.plan_part_dtl
       SET pull_day = FLOOR(ISNULL(cum_lt_hr,0)/8),
           pull_hr  = ISNULL(cum_lt_hr,0) - FLOOR(ISNULL(cum_lt_hr,0)/8)*8,
           part_output_hm = CASE
             WHEN ISNULL(output_hm,'') = '' THEN '0800'
             WHEN output_hm < '0800' THEN '0800'                         -- 시업 전 → 시업
             WHEN output_hm > '1700' THEN '1700'                         -- 종업 후 → 종업
             WHEN output_hm >= '1200' AND output_hm < '1300' THEN
                  CASE WHEN ISNULL(cum_lt_hr,0) - FLOOR(ISNULL(cum_lt_hr,0)/8)*8 > 0
                       THEN '1200' ELSE '1300' END
             ELSE output_hm END""")

    # ── 4) ★시간당김 — 시각에서 직접 빼고, 08:00 미만이면 전날로 이월 ──
    #   레거시 실측: OUT=1322 -4h -점심1h → 0822 (당김 0일)
    #                OUT=1201 -4h → 0801 → 하한 0800 (당김 0일)
    #   점심 1시간은 '결과가 13시 미만으로 내려갈 때'만 뺀다.
    #   빼서 08:00 미만이면 하루 더 당기고 전일 17:00 에서 잔여를 계속 뺀다.
    #   ★분 단위로 계산해야 레거시와 분까지 맞는다(0822·0901 등).
    cur.execute("""
    WITH m AS (
      SELECT work_order, split_work_order, item_code, proc_seq, gagong_proc_seq,
             CAST(LEFT(part_output_hm,2) AS int)*60 + CAST(RIGHT(part_output_hm,2) AS int) AS t0,
             CAST(ISNULL(pull_hr,0)*60 AS int) AS pm
        FROM nx.plan_part_dtl
       WHERE ISNULL(part_output_hm,'')<>'' AND ISNULL(pull_hr,0) > 0),
    c AS (
      SELECT *,
             -- ★점심 통과 보정: 시작이 13:00 초과이고 결과가 13:00 미만이면 60분 더.
             --   점심(12~13)은 근무시간이 아니므로 그 구간을 지나가면 실작업 1시간이 더 필요.
             --   실측: 보정 없음 95.93% → 보정 적용 99.66%. 경계는 '>780'(13:00 초과).
             t0 - pm - CASE WHEN t0 > 780 AND (t0 - pm) < 780 THEN 60 ELSE 0 END AS t1
        FROM m),
    d AS (
      SELECT *,
             -- 08:00(480분) 미만이면 하루 이월: 전일 17:00(1020분) 에서 부족분만큼 더 뺀다.
             CASE WHEN t1 < 480 THEN 1 ELSE 0 END AS carry,
             -- ★이월분에도 점심 통과 보정을 적용한다(2026-08-27 라이브 실측 5건).
             --   전일 17:00 에서 역산하므로 결과가 13:00 미만이면 점심(12~13)을 지나간 것.
             --   실측: 상위 08:59 · pull_hr=6.00 → 이월 후 웹 11:59 / 레거시 10:59 (+60분 어긋남).
             --     17:00 − 5:01 = 11:59 이고 점심을 통과하니 10:59 가 맞다.
             --   ⚠전일 17:00 은 항상 13:00 초과이므로 시작조건(>780)은 자동 충족된다.
             CASE WHEN t1 < 480
                  THEN 1020 - (480 - t1) - CASE WHEN (1020 - (480 - t1)) < 780 THEN 60 ELSE 0 END
                  ELSE t1 END AS t2
        FROM c)
    UPDATE a
       SET a.pull_day = a.pull_day + d.carry,
           a.part_output_hm = RIGHT('0'+CAST(d.t2/60 AS varchar(2)),2)
                            + RIGHT('0'+CAST(d.t2%60 AS varchar(2)),2)
      FROM nx.plan_part_dtl a
      JOIN d ON d.work_order=a.work_order AND d.split_work_order=a.split_work_order
            AND d.item_code=a.item_code AND d.proc_seq=a.proc_seq
            AND d.gagong_proc_seq=a.gagong_proc_seq""")
    # ★당김 후 점심 재정규화는 하지 않는다(레거시 실측).
    #   점심통과 -60분 보정이 이미 점심을 소비했으므로 결과가 12~13시에 떨어져도 그대로 둔다.
    #   실측: 재정규화 적용 95.93% · 미적용 99.66% — 미적용이 옳다.

    # ── 5) 일 단위 당김 — 파트 근무일 기준(휴무일 건너뜀) ──
    #     기준일(plan_ymd)이 휴무면 직전 근무일로 먼저 내린 뒤(rn0), 거기서 pull_day 만큼 당긴다.
    #     ★방어: 계획일자가 달력 범위 밖이면(오류 A/S 계획) 당기지 않는다.
    #       실측 — WO1001483NG 의 PLAN_YMD=720611(1972년). 그대로 두면 rn0 가 달력 끝을 잡아
    #       270331 로 밀려 당김 16,510일이 나온다. 4행뿐이지만 화면 날짜축을 망가뜨린다.
    cur.execute("""
    WITH rng AS (SELECT part_code, MIN(ymd6) mn, MAX(ymd6) mx FROM nx.plan_workday GROUP BY part_code),
    base AS (
      SELECT a.work_order, a.split_work_order, a.item_code, a.proc_seq, a.gagong_proc_seq,
             a.pull_day, RTRIM(a.gagong_proc_code) pc, a.plan_ymd,
             (SELECT MAX(w.rn) FROM nx.plan_workday w
               WHERE w.part_code=RTRIM(a.gagong_proc_code) AND w.ymd6<=a.plan_ymd) rn0
        FROM nx.plan_part_dtl a
        JOIN rng r ON r.part_code=RTRIM(a.gagong_proc_code)
       WHERE a.plan_ymd BETWEEN r.mn AND r.mx)
    UPDATE a SET a.part_plan_ymd = ISNULL(
             (SELECT w.ymd6 FROM nx.plan_workday w
               WHERE w.part_code=b.pc AND w.rn = b.rn0 - ISNULL(b.pull_day,0)), a.plan_ymd)
      FROM nx.plan_part_dtl a
      JOIN base b ON b.work_order=a.work_order AND b.split_work_order=a.split_work_order
                 AND b.item_code=a.item_code AND b.proc_seq=a.proc_seq
                 AND b.gagong_proc_seq=a.gagong_proc_seq
     WHERE b.rn0 IS NOT NULL""")
    # 달력에 없는 파트(미등록)는 원본 일자 유지
    cur.execute("UPDATE nx.plan_part_dtl SET part_plan_ymd=plan_ymd WHERE ISNULL(part_plan_ymd,'')=''")

    # ── 7) 오전/오후 ──
    cur.execute("""UPDATE nx.plan_part_dtl
       SET ampm      = CASE WHEN ISNULL(output_hm,'0800')      < '1200' THEN 'AM' ELSE 'PM' END,
           part_ampm = CASE WHEN ISNULL(part_output_hm,'0800') < '1200' THEN 'AM' ELSE 'PM' END""")

    # ── 8) 결과 요약 ──
    cur.execute("""SELECT COUNT(*),
           SUM(CASE WHEN part_plan_ymd<plan_ymd THEN 1 ELSE 0 END),
           SUM(CASE WHEN part_plan_ymd=plan_ymd THEN 1 ELSE 0 END),
           MAX(DATEDIFF(day, CONVERT(date,'20'+part_plan_ymd,112), CONVERT(date,'20'+plan_ymd,112)))
      FROM nx.plan_part_dtl WHERE ISNULL(part_plan_ymd,'')<>''""")
    n, pulled, same, mx = cur.fetchone()
    cur.execute("""SELECT COUNT(*) FROM nx.plan_part_dtl p
                     JOIN nx.HR_M_CALENDAR c ON c.calendar_yymd='20'+p.part_plan_ymd
                          AND c.work_team='A' AND c.time_type='A'
                    WHERE c.work_stats IN ('3','4')""")
    holi = int(cur.fetchone()[0] or 0)
    return {"pull_lines": int(n or 0), "pulled": int(pulled or 0), "unchanged": int(same or 0),
            "max_days": int(mx or 0), "holiday_rows": holi}
