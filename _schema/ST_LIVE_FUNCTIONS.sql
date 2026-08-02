/* ============================================================================
   생산실적 필요ST 라이브 복제 함수 (f_stday_live)  — 2026-08-02
   ----------------------------------------------------------------------------
   배경/근거:
   - 레거시 생산실적현황 010(dw_pr_list_010_l2)·파트별 090(dw_pr_list_090_l1)의
     필요ST = SUM( f_get_item_st_day(item, prod_ymd) * prod_qty ) / 60.
   - f_get_item_st_day 로직: pr_m_item_st_day(날짜버전 ST) 최신 1건이 >0 이면 그 값,
     아니면 폴백 = f_get_item_assy_st(item) + f_get_item_single_st(item).
       * assy_st  = Σ(PR_M_WORK_ASSY.work_st × pr_m_item_assy_rt.work_qty), PROC_GUBUN in ('1','21','31')
       * single_st= 품목외경으로 diam브래킷 선정 후 Σ(PR_M_WORK_SINGLE_ST.work_st × pr_m_item_single_rt.work_qty)
   - ★문제: 원함수 f_get_item_st_day 는 라이브 운영DB(PARTNER_ERP)에 없음(테스트DB에만 존재).
     테스트DB(PARTNER_ERP_TEST/TEST2/TEST3)의 routing 마스터가 라이브와 달라 ST가 어긋남
     (예 S1 07/01: TEST=1749, 라이브=1631 — routing 최근 변경). 웹 백엔드는 PARTNER_ERP(라이브)를
     쓰므로 ST도 반드시 PARTNER_ERP 기준이어야 정합.
   - ★해결: 원함수 로직을 그대로 복제하되 모든 테이블을 PARTNER_ERP.dbo.* 3-part로 읽는
     f_stday_live 를 PARTNER_ERP_TEST3.dbo 에 생성. 원함수와 99/99 완전일치 검증(2026-08-02).
     라이브 010 스크린샷(양산 2924.1, blank 16518.6) 정확 재현.
   - ★주의: 폴백ST(assy+single)는 날짜버전이 없어 routing마스터 변경시 과거일자 ST도 바뀜.
     이는 레거시도 동일한 한계 — 옛 스크린샷과 100% 재현 불가(예 090 S1 1749→1631)는 정상.
   - ★재생성 필요: PARTNER_ERP_TEST3 가 리프레시/복원되면 이 3함수가 사라짐 → 이 파일로 재생성.
     백엔드 app.py 의 /api/prodresult/list·/api/partresult/list 가 이 함수에 의존.
   ============================================================================ */
USE PARTNER_ERP_TEST3;
GO
IF OBJECT_ID('dbo.f_stday_live')     IS NOT NULL DROP FUNCTION dbo.f_stday_live;
IF OBJECT_ID('dbo.f_assy_st_live')   IS NOT NULL DROP FUNCTION dbo.f_assy_st_live;
IF OBJECT_ID('dbo.f_single_st_live') IS NOT NULL DROP FUNCTION dbo.f_single_st_live;
GO
CREATE FUNCTION dbo.f_assy_st_live(@item varchar(20)) RETURNS decimal(18,2) AS
BEGIN
  DECLARE @st decimal(18,2);
  SELECT @st = ISNULL(SUM(a.work_st*b.work_qty),0)
    FROM PARTNER_ERP.dbo.PR_M_ITEM m, PARTNER_ERP.dbo.PR_M_WORK_ASSY a
    JOIN (SELECT * FROM PARTNER_ERP.dbo.pr_m_item_assy_rt WHERE item_code=@item) b ON a.a_work_code=b.a_work_code
   WHERE a.PROC_GUBUN IN ('1','21','31') AND m.ITEM_CODE=@item;
  RETURN @st;
END
GO
CREATE FUNCTION dbo.f_single_st_live(@item varchar(20)) RETURNS decimal(18,2) AS
BEGIN
  DECLARE @diam decimal(18,3), @st decimal(18,2);
  SELECT TOP 1 @diam = a.item_diam
    FROM PARTNER_ERP.dbo.pr_m_item m
    JOIN PARTNER_ERP.dbo.cm_m_cust c ON m.in_cust_code=c.cust_code
    JOIN PARTNER_ERP.dbo.PR_M_WORK_ITEM_DIAM a ON c.gc_gubun=a.work_code
   WHERE m.item_code=@item AND a.item_diam>=m.item_diam ORDER BY a.item_diam ASC;
  SET @diam = ISNULL(@diam,0);
  SELECT @st = ISNULL(SUM(a.work_st*b.work_qty),0)
    FROM (SELECT * FROM PARTNER_ERP.dbo.pr_m_item_single_rt WHERE item_code=@item) b
    JOIN PARTNER_ERP.dbo.pr_m_item m ON b.item_code=m.item_code
    LEFT JOIN PARTNER_ERP.dbo.PR_M_WORK_SINGLE_ST a ON a.s_work_code=b.s_work_code AND a.item_diam=@diam;
  RETURN @st;
END
GO
CREATE FUNCTION dbo.f_stday_live(@item varchar(20), @ymd varchar(6)) RETURNS decimal(18,1) AS
BEGIN
  DECLARE @st decimal(18,1);
  SELECT TOP 1 @st = item_st FROM PARTNER_ERP.dbo.pr_m_item_st_day
   WHERE item_code=@item AND st_ymd<=@ymd ORDER BY st_ymd DESC;
  IF @st > 0 RETURN @st;
  SET @st = dbo.f_assy_st_live(@item) + dbo.f_single_st_live(@item);
  RETURN @st;
END
GO

/* ============================================================================
   f_st_part_day_live — 파트별·날짜별 공정ST 라이브복제 (2026-08-02)
   레거시 f_get_item_st_part_day(item, gagong_proc_code, ymd) 로직을 라이브 PARTNER_ERP.dbo.* 로 복제.
   = pr_m_item_st_day(날짜버전 tot_st, gagong_proc_code별) 최신 st_ymd / 폴백 pr_m_item_proc_gagong.TOT_ST.
   용도: 파트별생산실적현황(w_pr_list_090) 집계/도번 필요ST. 07/01 파트별 11/11 정확일치(S6=5244.1·S5=2563.6·S5-2=1230.6).
   ★TEST3 st_day는 07/16 고정이라 라이브(PARTNER_ERP, 08/02) 사용. 백엔드 partresult_list 가 의존.
   ============================================================================ */
IF OBJECT_ID('dbo.f_st_part_day_live') IS NOT NULL DROP FUNCTION dbo.f_st_part_day_live;
GO
CREATE FUNCTION dbo.f_st_part_day_live(@item varchar(20), @part varchar(20), @ymd varchar(6)) RETURNS decimal(18,1) AS
BEGIN
  DECLARE @st decimal(18,1);
  SELECT TOP 1 @st = ISNULL(SUM(tot_st),0)
    FROM PARTNER_ERP.dbo.pr_m_item_st_day
   WHERE item_code=@item AND gagong_proc_code=@part AND st_ymd<=@ymd
   GROUP BY st_ymd ORDER BY st_ymd DESC;
  IF @st > 0 RETURN @st;
  SELECT @st = ISNULL(SUM(tot_st),0) FROM PARTNER_ERP.dbo.pr_m_item_proc_gagong WHERE item_code=@item AND gagong_proc_code=@part;
  RETURN @st;
END
GO
