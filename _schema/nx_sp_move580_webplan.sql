/* nx.SP_PR_가공창고_이동계획_WEBPLAN — 가공이동580 '신규DB(웹계획)' 소스 전용.
   레거시 dbo.SP_PR_가공창고_이동계획_260213 의 평문사본에서 계획·재고 원천을 nx 로 치환.
   (SP 가 암호화라 인자로 원천을 못 바꾼다 → 사본 방식. 반환 174컬럼 동일)

   ★계획 3갈래 — 2026-08-27 전부 웹 전환:
     ① 파트별   PR_T_PLAN_PART_COPY  → nx.v_plan_part_copy_new
     ② 품목별   PR_T_PLAN_ITEM_DTL   → nx.v_plan_item_dtl_new
     ③ 예외생산 PR_T_PLAN_INPUT      → nx.v_prod_plan_input_new  (2곳)
   종전엔 ①만 웹이라 레거시 계획이 섞여 파트별계획과 결과가 달랐다.

   ★가공세트재고 — 2026-08-27:
     PU_T_SET_GAGONG_STOCK 만 nx 에 없어 무접두 참조가 PARTNER_ERP_TEST3.dbo 로 빠졌다
     (1,468행/43,113 vs 라이브 1,511행/43,623 → 전표발행 JP_PRINT_QTY 차이).
     nx 에 테이블 신설·라이브 복사 후 nx 를 명시적으로 참조하도록 변경.

   ※SP 는 nx 스키마 소속이라 무접두 테이블은 nx→dbo 순으로 해석된다.
     나머지 재고(pr_t_mat_stock_wh·pu_t_mat_stock_wh·sa_t_item_stock·
     PU_T_STOCK_MAINT_GAGONG_MOVE)는 이미 nx 미러가 있어 그대로 nx 를 읽는다.
     단 미러 sync 지연(테이블별 8분~10시간)이 있어 값이 라이브와 다를 수 있다 — 별도 과제. */
CREATE PROC nx.SP_PR_가공창고_이동계획_WEBPLAN
		@as_from_ymd				varchar(6),
		@as_to_ymd					varchar(6),
		@as_work_code				varchar(10),		/*작업처*/
		@as_pu_part_code			varchar(10),		/*자재창고IS0001*/
		@as_pr_part_code			varchar(10),		/*생산파트창고*/
		@as_sagub_cust_code		varchar(10)			/*사급업체*/
AS
BEGIN
	/**
	DECLARE		@as_from_ymd				varchar(6),
					@as_to_ymd					varchar(6),
					@as_work_code				varchar(10),		/*작업처*/
					@as_pu_part_code			varchar(10),		/*자재창고IS0001*/
					@as_pr_part_code			varchar(10),		/*생산파트창고*/
					@as_sagub_cust_code		varchar(10)			/*사급업체*/

	SET @as_from_ymd = '250721'
	SET @as_to_ymd = '250722'
	SET @as_work_code = 'P2'
	SET @as_pu_part_code = 'IS0001'
	SET @as_pr_part_code = ''
	SET @as_sagub_cust_code = '2096'
	**/

	SET NOCOUNT ON
	SET ANSI_WARNINGS OFF

	declare	@LDT_CREATE_DATETIME		datetime

	declare	@db_PLAN_YMD				varchar(6)
	declare	@db_OUTPUT_HM				varchar(4)
	declare	@db_WORK_ORDER				varchar(20)
	declare	@db_SPLIT_WORK_ORDER		varchar(30)
	declare	@db_ASSY_ITEM_CODE		varchar(20)
	declare	@db_BOM_LEVEL				tinyint
	declare	@db_UPPER_ITEM_CODE		varchar(20)
	declare	@db_ITEM_CODE				varchar(20)
	declare	@db_MAT_CODE				varchar(20)
	declare	@db_PROC_SEQ				int
	declare	@db_USE_QTY					int
	declare	@db_PART_PLAN_YMD			varchar(6)
	declare	@db_PART_OUTPUT_HM		varchar(4)
	declare	@db_PART_PLAN_QTY			int
	declare	@db_MAT_USE_QTY			int
	declare	@db_MOVE_FIN_QTY			int
	declare	@db_KIT_WH_STOCK_QTY		int
	
	declare	@db_GAGONG_PROC_CODE		varchar(10)
	declare	@db_GOLE_CODE				varchar(10)
	declare	@db_FINISH_QTY				int
	declare	@db_FINISH_TAG				int
	declare	@db_SALE_QTY				int
	declare	@db_STOCK_QTY				int
	declare	@db_PR_STOCK_QTY			int
	declare	@db_jan_qty					int
	declare	@db_item_st					decimal(18, 3)


	declare	@ls_GAGONG_PROC_CODE		varchar(10)
	declare	@li_BOM_LEVEL				tinyint
	declare	@ls_WORK_CODE				varchar(10)
	declare	@ls_WORK_ORDER				varchar(20)
	declare	@ls_SPLIT_WORK_ORDER		varchar(30)
	declare	@li_PROC_SEQ				int

	declare	@ls_GOLE_CODE				varchar(20)
	declare	@ls_ASSY_ITEM_CODE		varchar(20)
	declare	@ls_UPPER_ITEM_CODE		varchar(20)
	declare	@ls_ITEM_CODE				varchar(20)
	declare	@ls_MAT_CODE				varchar(20)

	declare	@ls_PLAN_YMD				varchar(6)


	declare	@li_SALE_QTY				int
	declare	@li_FINISH_QTY				int
	declare	@li_FINISH_TAG				int
	declare	@li_STOCK_QTY				int
	declare	@li_KIT_WH_STOCK_QTY		int	
	declare	@li_JAN_QTY					int
	declare	@li_READY_QTY				int
	declare	@li_MOVE_FIN_QTY			int
	
	declare	@ld_y_inwon					int
	declare	@ld_prod_rate				decimal(18, 2)


	declare	@ld_2_HOUR					decimal(18, 2)			--7200초
	declare	@ld_work_st					decimal(18, 2)



	IF object_id('tempdb..#TEMP_PART_DTL') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_PART_DTL;
	END
    
	--SELECT  PLAN_YMD, WORK_ORDER, SPLIT_WORK_ORDER, ASSY_ITEM_CODE, BOM_LEVEL, UPPER_ITEM_CODE, ITEM_CODE, PROC_SEQ, 
	--		GC_GUBUN, OUTPUT_HM, LINE_NO, USE_QTY, PLAN_QTY, WORK_CODE, GAGONG_PROC_CODE, GAGONG_PROC_SEQ, JP_PROC_METHOD, 
	--		LT_HR, CUM_LT_HR, PART_PLAN_YMD, PART_OUTPUT_HM, 
	--		PART_PLAN_QTY, 0 AS FINISH_TAG, 16777215 AS COLOR, 0 AS FINISH_QTY, 0 AS SALE_QTY, 
	--		0 AS ASSY_STOCK_QTY, 0 AS FIX_STOCK_QTY, 0 AS SET_STOCK_QTY, 0 AS PR_STOCK_QTY, 0 AS STOCK_QTY, 0 AS PART_STOCK_QTY, 
	--		0 AS JP_PRINT_QTY, CUM_JAN_QTY, CUM_ITEM_CODE, PRIOR_GAGONG_PROC_CODE, PRIOR_GAGONG_PROC_SEQ
	-- INTO    #TEMP_PART_DTL
	-- FROM    PR_T_PLAN_PART_COPY WITH (NOLOCK)
	--WHERE		WORK_CODE = 'P1'
	--  AND		GAGONG_PROC_SEQ = 1;
              

	SELECT * INTO #TEMP_PART_DTL
	  FROM (
				SELECT  PLAN_YMD, WORK_ORDER, SPLIT_WORK_ORDER, ASSY_ITEM_CODE, BOM_LEVEL, UPPER_ITEM_CODE, ITEM_CODE, PROC_SEQ, 
						GC_GUBUN, OUTPUT_HM, LINE_NO, USE_QTY, PLAN_QTY, WORK_CODE, GAGONG_PROC_CODE, GAGONG_PROC_SEQ, JP_PROC_METHOD, 
						LT_HR, CUM_LT_HR, PART_PLAN_YMD, PART_OUTPUT_HM, 
						PART_PLAN_QTY, 0 AS FINISH_TAG, 16777215 AS COLOR, 0 AS FINISH_QTY, 0 AS SALE_QTY, 
						0 AS ASSY_STOCK_QTY, 0 AS FIX_STOCK_QTY, 0 AS SET_STOCK_QTY, 0 AS PR_STOCK_QTY, 0 AS STOCK_QTY, 0 AS PART_STOCK_QTY, 
						0 AS READY_STOCK_QTY, 0 AS JP_PRINT_QTY, 0 AS READY_QTY, CUM_JAN_QTY, CUM_ITEM_CODE, PRIOR_GAGONG_PROC_CODE, PRIOR_GAGONG_PROC_SEQ
				 FROM    PARTNER_ERP_TEST3.nx.v_plan_part_copy_new WITH (NOLOCK)
				WHERE		WORK_CODE = 'P1'
				  AND		GAGONG_PROC_SEQ = 1
				
				UNION ALL

				SELECT  A.PLAN_YMD, A.WORK_ORDER, A.SPLIT_WORK_ORDER, A.C_ITEM_CODE, 0 BOM_LEVEL, A.C_ITEM_CODE, A.C_ITEM_CODE, 0 PROC_SEQ, 
						M.GC_GUBUN, A.OUTPUT_HM, A.LINE_NO, 1 USE_QTY, A.PLAN_QTY * A.USE_QTY, '' WORK_CODE, '' GAGONG_PROC_CODE, 0 GAGONG_PROC_SEQ, '' JP_PROC_METHOD, 
						0 LT_HR, 0 CUM_LT_HR, A.PLAN_YMD AS PART_PLAN_YMD, A.OUTPUT_HM AS PART_OUTPUT_HM, 
						A.PLAN_QTY * A.USE_QTY AS PART_PLAN_QTY, 0 AS FINISH_TAG, 16777215 AS COLOR, 0 AS FINISH_QTY, 0 AS SALE_QTY, 
						0 AS ASSY_STOCK_QTY, 0 AS FIX_STOCK_QTY, 0 AS SET_STOCK_QTY, 0 AS PR_STOCK_QTY, 0 AS STOCK_QTY, 0 AS PART_STOCK_QTY, 
						0 AS READY_STOCK_QTY, 0 AS JP_PRINT_QTY, 0 AS READY_QTY, 0 CUM_JAN_QTY, A.C_ITEM_CODE AS CUM_ITEM_CODE, '' PRIOR_GAGONG_PROC_CODE, 0 PRIOR_GAGONG_PROC_SEQ
				 FROM    PARTNER_ERP_TEST3.nx.v_plan_item_dtl_new A WITH (NOLOCK)   -- ★웹계획(2026-08-27)
				 JOIN		PR_M_ITEM M ON A.C_ITEM_CODE = M.ITEM_CODE
				WHERE		M.IN_CUST_CODE > ''
				  AND		A.PLAN_YMD >= CONVERT(VARCHAR, GETDATE(), 12)
				
				UNION ALL

				SELECT  A.PLAN_YMD, A.WORK_ORDER, A.WORK_ORDER, A.ITEM_CODE, 0 BOM_LEVEL, A.ITEM_CODE, A.ITEM_CODE, 0 PROC_SEQ, 
						M.GC_GUBUN, A.OUTPUT_HM, A.LINE_NO, 1 USE_QTY, A.PLAN_QTY, '' WORK_CODE, '' GAGONG_PROC_CODE, 0 GAGONG_PROC_SEQ, '' JP_PROC_METHOD, 
						0 LT_HR, 0 CUM_LT_HR, A.PLAN_YMD AS PART_PLAN_YMD, A.OUTPUT_HM AS PART_OUTPUT_HM, 
						A.PLAN_QTY AS PART_PLAN_QTY, 0 AS FINISH_TAG, 16777215 AS COLOR, 0 AS FINISH_QTY, 0 AS SALE_QTY, 
						0 AS ASSY_STOCK_QTY, 0 AS FIX_STOCK_QTY, 0 AS SET_STOCK_QTY, 0 AS PR_STOCK_QTY, 0 AS STOCK_QTY, 0 AS PART_STOCK_QTY, 
						0 AS READY_STOCK_QTY, 0 AS JP_PRINT_QTY, 0 AS READY_QTY, 0 CUM_JAN_QTY, A.ITEM_CODE AS CUM_ITEM_CODE, '' PRIOR_GAGONG_PROC_CODE, 0 PRIOR_GAGONG_PROC_SEQ
				 FROM    PARTNER_ERP_TEST3.nx.v_prod_plan_input_new A WITH (NOLOCK)   -- ★웹계획(2026-08-27)
				 JOIN		PR_M_ITEM M ON A.ITEM_CODE = M.ITEM_CODE
				WHERE		M.IN_CUST_CODE > ''
				  AND		A.PLAN_YMD >= CONVERT(VARCHAR, GETDATE(), 12)
				
				UNION ALL

				SELECT  A.PLAN_YMD, A.WORK_ORDER, A.WORK_ORDER, A.ITEM_CODE, 0 BOM_LEVEL, A.ITEM_CODE, A.ITEM_CODE, 0 PROC_SEQ, 
						M.GC_GUBUN, A.OUTPUT_HM, A.LINE_NO, 1 USE_QTY, A.PLAN_QTY, M.WORK_CODE, '' GAGONG_PROC_CODE, 0 GAGONG_PROC_SEQ, '' JP_PROC_METHOD, 
						0 LT_HR, 0 CUM_LT_HR, A.PLAN_YMD AS PART_PLAN_YMD, A.OUTPUT_HM AS PART_OUTPUT_HM, 
						A.PLAN_QTY AS PART_PLAN_QTY, 0 AS FINISH_TAG, 16777215 AS COLOR, 0 AS FINISH_QTY, 0 AS SALE_QTY, 
						0 AS ASSY_STOCK_QTY, 0 AS FIX_STOCK_QTY, 0 AS SET_STOCK_QTY, 0 AS PR_STOCK_QTY, 0 AS STOCK_QTY, 0 AS PART_STOCK_QTY, 
						0 AS READY_STOCK_QTY, 0 AS JP_PRINT_QTY, 0 AS READY_QTY, 0 CUM_JAN_QTY, A.ITEM_CODE AS CUM_ITEM_CODE, '' PRIOR_GAGONG_PROC_CODE, 0 PRIOR_GAGONG_PROC_SEQ
				 FROM    PARTNER_ERP_TEST3.nx.v_prod_plan_input_new A WITH (NOLOCK)   -- ★웹계획(2026-08-27)
				 JOIN		PR_M_ITEM M ON A.ITEM_CODE = M.ITEM_CODE
				WHERE		M.WORK_CODE = 'P2'
				  AND		A.PLAN_YMD >= CONVERT(VARCHAR, GETDATE(), 12)
				) T



	ALTER   TABLE #TEMP_PART_DTL ALTER COLUMN PLAN_YMD VARCHAR(6) NOT NULL;
	ALTER   TABLE #TEMP_PART_DTL ALTER COLUMN WORK_ORDER VARCHAR(20) NOT NULL;
	ALTER   TABLE #TEMP_PART_DTL ALTER COLUMN SPLIT_WORK_ORDER VARCHAR(30) NOT NULL;
	ALTER   TABLE #TEMP_PART_DTL ALTER COLUMN ASSY_ITEM_CODE VARCHAR(20) NOT NULL;
	ALTER   TABLE #TEMP_PART_DTL ALTER COLUMN BOM_LEVEL TINYINT NOT NULL;
	ALTER   TABLE #TEMP_PART_DTL ALTER COLUMN UPPER_ITEM_CODE VARCHAR(20) NOT NULL;
	ALTER   TABLE #TEMP_PART_DTL ALTER COLUMN ITEM_CODE VARCHAR(20) NOT NULL;
	ALTER   TABLE #TEMP_PART_DTL ALTER COLUMN PROC_SEQ SMALLINT NOT NULL;
            
	CREATE  INDEX IDX_TEMP_PART_DTL_01 ON #TEMP_PART_DTL( PLAN_YMD, WORK_ORDER, SPLIT_WORK_ORDER, ASSY_ITEM_CODE, BOM_LEVEL, UPPER_ITEM_CODE, ITEM_CODE, PROC_SEQ ) ;





	--출하실적 적용
	--출하수량세팅
	UPDATE T
		SET SALE_QTY = (select isnull(sum(sale_qty),0) from sa_t_sale_dtl WITH (NOLOCK)  where work_order 		= t.work_order
																												  and split_work_order 	= t.split_work_order
																												  and item_code 			= t.assy_item_code
																												  and finish_flag 		= '0')
	  FROM #TEMP_PART_DTL t WITH (NOLOCK) 


	declare dc1 cursor for
	select t.PLAN_YMD, t.WORK_ORDER, t.SPLIT_WORK_ORDER, t.ASSY_ITEM_CODE, t.BOM_LEVEL, t.UPPER_ITEM_CODE, t.ITEM_CODE, t.PROC_SEQ, 
			t.PART_PLAN_YMD, t.USE_QTY, t.PART_PLAN_QTY,
			(select isnull(sum(sale_qty),0) from sa_t_sale_dtl WITH (NOLOCK)  where work_order 		= t.work_order
																								  and split_work_order 	= t.split_work_order
																								  and item_code 			= t.assy_item_code
																								  and finish_flag 		= '0') as sale_qty
		FROM #TEMP_PART_DTL t WITH (NOLOCK) 
	  where t.PART_PLAN_YMD <= @as_to_ymd
	  order by t.WORK_ORDER, t.SPLIT_WORK_ORDER, t.ASSY_ITEM_CODE, t.BOM_LEVEL, t.UPPER_ITEM_CODE, t.ITEM_CODE, t.PROC_SEQ, t.PLAN_YMD
	open dc1
	fetch from dc1 into @db_PLAN_YMD, @db_WORK_ORDER, @db_SPLIT_WORK_ORDER, @db_ASSY_ITEM_CODE, @db_BOM_LEVEL, @db_UPPER_ITEM_CODE, @db_ITEM_CODE, @db_PROC_SEQ, 							
								@db_PART_PLAN_YMD, @db_USE_QTY, @db_PART_PLAN_QTY, @db_SALE_QTY
	while (@@fetch_status = 0)
	begin
		if     @db_WORK_ORDER = @ls_WORK_ORDER
			and @db_SPLIT_WORK_ORDER = @ls_SPLIT_WORK_ORDER
			and @db_ASSY_ITEM_CODE = @ls_ASSY_ITEM_CODE
			and @db_BOM_LEVEL = @li_BOM_LEVEL
			and @db_UPPER_ITEM_CODE = @ls_UPPER_ITEM_CODE
			and @db_ITEM_CODE = @ls_ITEM_CODE
			and @db_PROC_SEQ = @li_PROC_SEQ
		begin
			SET @db_WORK_ORDER = @ls_WORK_ORDER
		END
		ELSE
		BEGIN
			set @ls_WORK_ORDER = @db_WORK_ORDER
			set @ls_SPLIT_WORK_ORDER = @db_SPLIT_WORK_ORDER
			set @ls_ASSY_ITEM_CODE = @db_ASSY_ITEM_CODE
			set @li_BOM_LEVEL = @db_BOM_LEVEL
			set @ls_UPPER_ITEM_CODE = @db_UPPER_ITEM_CODE
			set @ls_ITEM_CODE = @db_ITEM_CODE
			set @li_PROC_SEQ = @db_PROC_SEQ

			set @li_SALE_QTY = @db_SALE_QTY * @db_USE_QTY
		END

		SET @li_FINISH_QTY = 0

		IF @li_SALE_QTY > 0
		BEGIN
			if @db_PART_PLAN_QTY > @li_SALE_QTY
			BEGIN
				SET @li_FINISH_TAG = NULL
				SET @li_FINISH_QTY = @li_SALE_QTY
				SET @li_SALE_QTY = 0
			END
			ELSE
			BEGIN
				SET @li_FINISH_TAG = 90
				SET @li_FINISH_QTY = @db_PART_PLAN_QTY
				SET @li_SALE_QTY = @li_SALE_QTY - @db_PART_PLAN_QTY
			END

			update #TEMP_PART_DTL
				set FINISH_QTY = @li_FINISH_QTY
					,FINISH_TAG = ISNULL(@li_FINISH_TAG, FINISH_TAG)
			 where PLAN_YMD = @db_PLAN_YMD
				and WORK_ORDER = @db_WORK_ORDER
				and SPLIT_WORK_ORDER = @db_SPLIT_WORK_ORDER
				and ASSY_ITEM_CODE = @db_ASSY_ITEM_CODE
				and BOM_LEVEL = @db_BOM_LEVEL
				and UPPER_ITEM_CODE = @db_UPPER_ITEM_CODE
				and ITEM_CODE = @db_ITEM_CODE
				and PROC_SEQ = @db_PROC_SEQ
		END


		fetch next from dc1 into @db_PLAN_YMD, @db_WORK_ORDER, @db_SPLIT_WORK_ORDER, @db_ASSY_ITEM_CODE, @db_BOM_LEVEL, @db_UPPER_ITEM_CODE, @db_ITEM_CODE, @db_PROC_SEQ, 							
								@db_PART_PLAN_YMD, @db_USE_QTY, @db_PART_PLAN_QTY, @db_SALE_QTY
	end
	close dc1
	DEALLOCATE dc1

	----출하실적 적용 일괄
	--UPDATE A 
	--	SET CUM_JAN_QTY = (SELECT SUM(B.PLAN_QTY) FROM #TEMP_PART_DTL B WHERE A.PLAN_YMD >= B.PLAN_YMD
	--																								AND A.WORK_ORDER = B.WORK_ORDER
	--																								AND A.SPLIT_WORK_ORDER = B.SPLIT_WORK_ORDER
	--																								AND A.ASSY_ITEM_CODE = B.ASSY_ITEM_CODE
	--																								AND A.BOM_LEVEL = B.BOM_LEVEL
	--																								AND A.UPPER_ITEM_CODE = B.UPPER_ITEM_CODE
	--																								AND A.ITEM_CODE = B.ITEM_CODE
	--																								AND A.PROC_SEQ = B.PROC_SEQ)
	--		,SALE_QTY	 = (select isnull(sum(sale_qty),0) from sa_t_sale_dtl where work_order 		= A.work_order
	--															  and split_work_order 	= A.split_work_order
	--															  and item_code 			= A.assy_item_code
	--															  and finish_flag 		= '0') * A.USE_QTY
	--  FROM #TEMP_PART_DTL A



	--UPDATE A
	--	SET FINISH_QTY = CASE WHEN CUM_JAN_QTY < SALE_QTY THEN PLAN_QTY 
	--								 ELSE CASE WHEN (CUM_JAN_QTY - SALE_QTY)<PLAN_QTY THEN PLAN_QTY - (CUM_JAN_QTY - SALE_QTY) ELSE  0 END END
	--  FROM #TEMP_PART_DTL A



	--영업창고 ASSY재고 적용
	set @ls_ASSY_ITEM_CODE = ''
	set @ls_ITEM_CODE = ''

	/*ASSY재고 세팅*/
	UPDATE A
		SET ASSY_STOCK_QTY = (select ISNULL(SUM(stock_qty),0) from sa_t_item_stock WITH (NOLOCK)  where item_code = a.assy_item_code)
	  FROM #TEMP_PART_DTL A

	/*ASSY재고 감안*/
	declare dc1 cursor for
	select t.ASSY_ITEM_CODE, t.BOM_LEVEL, t.UPPER_ITEM_CODE, t.ITEM_CODE, t.PROC_SEQ, t.PLAN_YMD, t.OUTPUT_HM, t.WORK_ORDER, t.SPLIT_WORK_ORDER,
			t.PART_PLAN_YMD, t.USE_QTY, t.PART_PLAN_QTY, t.FINISH_QTY, t.ASSY_STOCK_QTY
		FROM #TEMP_PART_DTL t WITH (NOLOCK) 
	  where t.PART_PLAN_YMD between '' and @as_to_ymd
	  order by t.ASSY_ITEM_CODE, t.UPPER_ITEM_CODE, t.ITEM_CODE, t.PROC_SEQ, t.GAGONG_PROC_CODE, t.part_plan_ymd, t.part_OUTPUT_HM, t.PLAN_YMD, t.OUTPUT_HM, t.WORK_ORDER, t.SPLIT_WORK_ORDER
--	  order by t.ASSY_ITEM_CODE, t.BOM_LEVEL, t.UPPER_ITEM_CODE, t.ITEM_CODE, t.PROC_SEQ, t.PART_PLAN_YMD, t.PART_OUTPUT_HM, t.PLAN_YMD, t.OUTPUT_HM, t.WORK_ORDER, t.SPLIT_WORK_ORDER
	open dc1
	fetch from dc1 into @db_ASSY_ITEM_CODE, @db_BOM_LEVEL, @db_UPPER_ITEM_CODE, @db_ITEM_CODE, @db_PROC_SEQ, @db_PLAN_YMD, @db_OUTPUT_HM, @db_WORK_ORDER, @db_SPLIT_WORK_ORDER, 
								@db_PART_PLAN_YMD, @db_USE_QTY, @db_PART_PLAN_QTY, @db_FINISH_QTY, @db_STOCK_QTY
	while (@@fetch_status = 0)
	begin
		if @ls_ASSY_ITEM_CODE <> @db_ASSY_ITEM_CODE 
			or @li_BOM_LEVEL <> @db_BOM_LEVEL 
			or @ls_UPPER_ITEM_CODE <> @db_UPPER_ITEM_CODE 
			or @ls_ITEM_CODE <> @db_ITEM_CODE 
			or @li_PROC_SEQ <> @db_PROC_SEQ
		begin
			set @ls_ASSY_ITEM_CODE = @db_ASSY_ITEM_CODE
			set @li_BOM_LEVEL = @db_BOM_LEVEL
			set @ls_UPPER_ITEM_CODE = @db_UPPER_ITEM_CODE
			set @ls_ITEM_CODE = @db_ITEM_CODE
			set @li_PROC_SEQ = @db_PROC_SEQ
			set @li_STOCK_QTY = @db_STOCK_QTY * @db_use_qty
		end
		if @li_STOCK_QTY > 0
		begin
			set @li_JAN_QTY = @db_PART_PLAN_QTY - @db_FINISH_QTY

			if @li_JAN_QTY > 0
			BEGIN
				if @li_JAN_QTY > @li_STOCK_QTY
				BEGIN
					SET @li_FINISH_TAG = NULL
					SET @li_FINISH_QTY = @li_STOCK_QTY
					SET @li_STOCK_QTY = 0
				END
				ELSE
				BEGIN
					SET @li_FINISH_TAG = 70
					SET @li_FINISH_QTY = @li_JAN_QTY
					SET @li_STOCK_QTY = @li_STOCK_QTY - @li_JAN_QTY
				END

				update #TEMP_PART_DTL
					set FINISH_QTY = FINISH_QTY + @li_FINISH_QTY
						,FINISH_TAG = ISNULL(@li_FINISH_TAG, FINISH_TAG)
				 where PLAN_YMD = @db_PLAN_YMD
					and WORK_ORDER = @db_WORK_ORDER
					and SPLIT_WORK_ORDER = @db_SPLIT_WORK_ORDER
					and ASSY_ITEM_CODE = @db_ASSY_ITEM_CODE
					and BOM_LEVEL = @db_BOM_LEVEL
					and UPPER_ITEM_CODE = @db_UPPER_ITEM_CODE
					and ITEM_CODE = @db_ITEM_CODE
					and PROC_SEQ = @db_PROC_SEQ
			END
		end
		fetch next from dc1 into @db_ASSY_ITEM_CODE, @db_BOM_LEVEL, @db_UPPER_ITEM_CODE, @db_ITEM_CODE, @db_PROC_SEQ, @db_PLAN_YMD, @db_OUTPUT_HM, @db_WORK_ORDER, @db_SPLIT_WORK_ORDER, 
								@db_PART_PLAN_YMD, @db_USE_QTY, @db_PART_PLAN_QTY, @db_FINISH_QTY, @db_STOCK_QTY
	end
	close dc1
	DEALLOCATE dc1











	IF object_id('tempdb..#TEMP_MAT_STOCK') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_MAT_STOCK;
	END

	--자재창고/공정재고(SUB품의 재고) 적용 및 가공세트재고 적용
	BEGIN
		with T_SUB_CTE(item_code, mat_code, stock_qty, pr_stock_qty, set_stock_qty, FIX_STOCK_QTY)
		AS (
			/*앵커멤버-생산계획*/
			select s.mat_code,
					s.mat_code,
					convert(int,ISNULL(sum(s.stock_qty),0))		as stock_qty,				/*자재재고*/
					convert(int,ISNULL(sum(s.pr_stock_qty),0))	as pr_stock_qty,			/*생산재고*/
					convert(int,ISNULL(sum(s.set_stock_qty),0))	as set_stock_qty,			/*가공세트재고*/
					0															as FIX_STOCK_QTY		/*도번고정재고*/
			  from (
							/*생산파트재고*/
							select A.mat_code, 0 AS stock_qty, A.STOCK_QTY AS PR_STOCK_QTY, 0 as SET_STOCK_QTY, 0 AS FIX_STOCK_QTY
							from (SELECT DISTINCT ITEM_CODE FROM #TEMP_PART_DTL) T
							JOIN pr_t_mat_stock_wh A WITH (NOLOCK) ON T.ITEM_CODE = A.MAT_CODE
							where A.stock_qty <> 0 
							  and A.part_code not in ('P0001', 'P0002')

							union all

							/*사급재고*/
							select a.mat_code, 0 AS stock_qty, A.STOCK_QTY AS PR_STOCK_QTY, 0 as SET_STOCK_QTY, 0 AS FIX_STOCK_QTY
								from PU_T_SAGUB_STOCK A WITH (NOLOCK)
								join pr_m_item M WITH (NOLOCK) on A.MAT_CODE = M.ITEM_CODE
								where M.SAGUB_STOCK_FLAG = '1'
			
							union all
			
							/*자재창고재고*/
							select A.mat_code, A.stock_qty, 0, 0, 0
							from (SELECT DISTINCT ITEM_CODE FROM #TEMP_PART_DTL) T
							JOIN pu_t_mat_stock_wh A WITH (NOLOCK) ON T.ITEM_CODE = A.MAT_CODE
							where A.cust_code	= 'Z99990'
							  and A.stock_qty <> 0
						) S
			 group by s.mat_code
			 having sum(s.stock_qty) <> 0 OR sum(s.PR_STOCK_QTY) <> 0 OR sum(s.SET_STOCK_QTY) <> 0

			union all
	
			/*재귀멤버-BOM하위추출*/
			SELECT cb.item_code,
					b.mat_code,
					0 as stock_qty,
					0 as pr_stock_qty,
					0 as set_stock_qty,
					CONVERT(int, case when cb.FIX_STOCK_QTY <> 0 then cb.FIX_STOCK_QTY else (cb.pr_stock_qty + cb.stock_qty) end * b.use_qty) as FIX_STOCK_QTY
			FROM T_SUB_CTE cb
			join pr_m_item_bom b WITH (NOLOCK)			on cb.mat_code	= b.item_code
			WHERE isnull(b.except_flag,'0') <> '1'
		)	


		SELECT s.item_code, s.mat_code, ISNULL(sum(s.stock_qty),0) as stock_qty, ISNULL(sum(s.pr_stock_qty),0) as pr_stock_qty, ISNULL(sum(s.set_stock_qty),0) as set_stock_qty, ISNULL(sum(s.FIX_STOCK_QTY),0) as FIX_STOCK_QTY
		  INTO #TEMP_MAT_STOCK
		  FROM T_SUB_CTE S
		 group by s.item_code, s.mat_code
	END













	IF object_id('tempdb..#TEMP_BOM_MAT') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_BOM_MAT;
	END
    
	IF object_id('tempdb..#TEMP_BOM_MAT_EXCEPT') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_BOM_MAT_EXCEPT;
	END
    
	IF object_id('tempdb..#TEMP_BOM_ASSY') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_BOM_ASSY;
	END


	/*사내생산출고 대상*/
	IF object_id('tempdb..#TEMP_BOM_MAT_DTL') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_BOM_MAT_DTL;
	END

	/*가공작업 자도번 추출*/
	BEGIN    
		WITH CTE_BOM(item_code, item_gagong_proc_code, mat_code, cum_use_qty, sagub_flag, SET_EXCEPT_FLAG, WH_GAGONG_PROC_CODE, vir_item_flag
						, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, WORK_CODE, ITEM_CLASS)
		AS
			(
				/*앵커멤버*/
				SELECT distinct
						T.item_code,
						T.gagong_proc_code as item_gagong_proc_code,
						T.ITEM_CODE as mat_code,
						convert(NUMERIC(18,5),1) 	as cum_use_qty,
						'0' AS sagub_flag,
						'0' AS SET_EXCEPT_FLAG,
						CONVERT(VARCHAR(10),'IS0001') AS WH_GAGONG_PROC_CODE,
						'0' AS vir_item_flag,
						AM.IN_CUST_CODE																																								AS GOLE_IN_CUST_CODE,			/*최종납품 업체*/
						IIF(AM.IN_CUST_CODE>'','',IIF(AM.WORK_CODE='P2', 'IS0001', (SELECT TOP 1 GAGONG_PROC_CODE FROM PR_M_ITEM_PROC_GAGONG WITH (NOLOCK) WHERE ITEM_CODE = T.ITEM_CODE AND PROC_SEQ = 1)))	AS GOLE_GAGONG_PROC_CODE,		/*최종납품 생산파트*/
						AM.WORK_CODE,
						AM.ITEM_CLASS
				  FROM #TEMP_PART_DTL	T
				  join pr_m_item			am WITH (NOLOCK) on T.item_code = am.item_code
				 where t.proc_seq <= 1
				
				union all
		
				/*재귀멤버-BOM하위추출*/
				SELECT cb.item_code,
						cb.item_gagong_proc_code,
						b.mat_code,
						CONVERT(NUMERIC(18,5), cb.cum_use_qty * b.use_qty) as cum_use_qty,
						b.sagub_flag,
						isnull(b.SET_EXCEPT_FLAG,'0') as SET_EXCEPT_FLAG,
						b.WH_GAGONG_PROC_CODE,
						b.vir_item_flag,
						IIF(CB.VIR_ITEM_FLAG='1', CB.GOLE_IN_CUST_CODE, AM.IN_CUST_CODE)												AS GOLE_IN_CUST_CODE,			/*최종납품 업체*/
						IIF(CB.VIR_ITEM_FLAG='1', CB.GOLE_GAGONG_PROC_CODE, IIF(AM.IN_CUST_CODE>'','',(SELECT GAGONG_PROC_CODE FROM PR_M_ITEM_PROC_GAGONG WITH (NOLOCK) WHERE ITEM_CODE = B.ITEM_CODE AND PROC_SEQ = 1))) AS GOLE_GAGONG_PROC_CODE,		/*최종납품 생산파트*/
						M.WORK_CODE,
						M.ITEM_CLASS
				  FROM CTE_BOM 			cb
				  join pr_m_item_bom 	b WITH (NOLOCK) on cb.mat_code	= b.item_code
				  join pr_m_item 			am WITH (NOLOCK) on b.item_code = am.item_code
				  join pr_m_item 			m WITH (NOLOCK) on b.mat_code 	= m.item_code
				 where isnull(b.except_flag,'0')='0'							/*전개제외*/
				   AND (B.VIR_ITEM_FLAG = '1' OR M.IN_CUST_CODE > '' OR M.WORK_CODE = 'P2' OR NOT EXISTS (SELECT * FROM PR_M_ITEM_PROC_GAGONG WITH (NOLOCK) WHERE ITEM_CODE = B.MAT_CODE))		/*하위품이 사내생산이 아닌 것*/
			)	
		/*대상 상세자재 추출*/
		SELECT * INTO #TEMP_BOM_MAT_DTL
		  from CTE_BOM						A


		/*SET출고자재 추출*/
		select item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, A.MAT_CODE, SUM(A.CUM_USE_QTY) AS USE_QTY
				,MAX(WORK_CODE) AS WORK_CODE, max(item_class) as item_class
				,MAX(ISNULL(B.STOCK_QTY,0) + ISNULL(B.PR_STOCK_QTY,0)) AS STOCK_QTY
		  INTO #TEMP_BOM_MAT
		  from #TEMP_BOM_MAT_DTL						A
		  LEFT JOIN (SELECT MAT_CODE, SUM(STOCK_QTY) AS STOCK_QTY, SUM(PR_STOCK_QTY) AS PR_STOCK_QTY
							FROM #TEMP_MAT_STOCK
						  GROUP BY MAT_CODE)	B ON A.MAT_CODE = B.MAT_CODE
		 where A.WORK_CODE = @as_work_code															/*가공 or 축관*/
		   AND SET_EXCEPT_FLAG <> '1'
			and A.GOLE_GAGONG_PROC_CODE > ''															/*최종투입이 생산파트인 것*/
		   AND isnull(a.vir_item_flag,'0') <> '1'
		 group by item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, A.MAT_CODE


		--/*SET예외출고자재 추출*/
		--select item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, A.MAT_CODE, SUM(A.CUM_USE_QTY) AS USE_QTY
		--		,MAX(WORK_CODE) AS WORK_CODE, max(item_class) as item_class
		--		,MAX(ISNULL(B.STOCK_QTY,0) + ISNULL(B.PR_STOCK_QTY,0)) AS STOCK_QTY
		--  INTO #TEMP_BOM_MAT_EXCEPT
		--  from #TEMP_BOM_MAT_DTL						A
		--  LEFT JOIN #TEMP_MAT_STOCK	B ON A.MAT_CODE = B.MAT_CODE
		-- where A.WORK_CODE = @as_work_code															/*가공 or 축관*/
		--   AND SET_EXCEPT_FLAG = '1'
		--	and (@as_pr_part_code>'' and a.GOLE_GAGONG_PROC_CODE	like @as_pr_part_code			/*투입생산파트*/
		--				or
		--		  @as_pr_part_code='' and a.sagub_flag = '1' and a.GOLE_IN_CUST_CODE like @as_sagub_cust_code)		/*사급업체*/
		--   AND isnull(a.vir_item_flag,'0') <> '1'
		-- group by item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, A.MAT_CODE
	END





	/*사급업체출고 대상*/
	IF object_id('tempdb..#TEMP_BOM_MAT_DTL2') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_BOM_MAT_DTL2;
	END
    
	/*가공작업 자도번 추출*/
	BEGIN
		WITH CTE_BOM(item_code, item_gagong_proc_code, mat_code, cum_use_qty, sagub_flag, SET_EXCEPT_FLAG, WH_GAGONG_PROC_CODE, vir_item_flag
						, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, WORK_CODE, ITEM_CLASS)
		AS
			(
				/*앵커멤버*/
				SELECT distinct
						T.item_code,
						T.gagong_proc_code as item_gagong_proc_code,
						b.mat_code as mat_code,
						convert(NUMERIC(18,5),b.use_qty) 	as cum_use_qty,
						b.sagub_flag,
						isnull(b.SET_EXCEPT_FLAG,'0') as SET_EXCEPT_FLAG,
						IIF(b.WH_GAGONG_PROC_CODE>'',b.WH_GAGONG_PROC_CODE,'IS0001') AS WH_GAGONG_PROC_CODE,
						b.vir_item_flag,
						AM.IN_CUST_CODE																																		AS GOLE_IN_CUST_CODE,			/*최종납품 업체*/
						IIF(AM.IN_CUST_CODE>'','',(SELECT TOP 1 GAGONG_PROC_CODE FROM PR_M_ITEM_PROC_GAGONG WITH (NOLOCK) WHERE ITEM_CODE = B.ITEM_CODE AND PROC_SEQ = 1))	AS GOLE_GAGONG_PROC_CODE,		/*최종납품 생산파트*/
						M.WORK_CODE,
						M.ITEM_CLASS
				  FROM #TEMP_PART_DTL	T
				  join pr_m_item_bom 	b WITH (NOLOCK) on T.ITEM_code = b.item_code
				  join pr_m_item			am WITH (NOLOCK) on b.item_code = am.item_code
				  join pr_m_item			m WITH (NOLOCK) on b.mat_code = m.item_code
				 WHERE isnull(b.except_flag,'0')='0'		/*전개제외*/
				   AND T.ASSY_ITEM_CODE = T.ITEM_CODE
				   and t.proc_seq <= 1
				
				union all
		
				/*재귀멤버-BOM하위추출*/
				SELECT cb.item_code,
						cb.item_gagong_proc_code,
						b.mat_code,
						CONVERT(NUMERIC(18,5), cb.cum_use_qty * b.use_qty) as cum_use_qty,
						b.sagub_flag,
						isnull(b.SET_EXCEPT_FLAG,'0') as SET_EXCEPT_FLAG,
						b.WH_GAGONG_PROC_CODE,
						b.vir_item_flag,
						IIF(CB.VIR_ITEM_FLAG='1', CB.GOLE_IN_CUST_CODE, AM.IN_CUST_CODE)												AS GOLE_IN_CUST_CODE,			/*최종납품 업체*/
						IIF(CB.VIR_ITEM_FLAG='1', CB.GOLE_GAGONG_PROC_CODE, IIF(AM.IN_CUST_CODE>'','',(SELECT GAGONG_PROC_CODE FROM PR_M_ITEM_PROC_GAGONG WITH (NOLOCK) WHERE ITEM_CODE = B.ITEM_CODE AND PROC_SEQ = 1))) AS GOLE_GAGONG_PROC_CODE,		/*최종납품 생산파트*/
						M.WORK_CODE,
						M.ITEM_CLASS
				  FROM CTE_BOM 			cb
				  join pr_m_item_bom 	b WITH (NOLOCK) on cb.mat_code	= b.item_code
				  join pr_m_item 			am WITH (NOLOCK) on b.item_code = am.item_code
				  join pr_m_item 			m WITH (NOLOCK) on b.mat_code 	= m.item_code
				 where isnull(b.except_flag,'0')='0'		/*전개제외*/
			)	
		/*대상 상세자재 추출*/
		SELECT * INTO #TEMP_BOM_MAT_DTL2
		  from CTE_BOM						A


		/*SET출고자재 추출*/
		INSERT INTO #TEMP_BOM_MAT
		select item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, A.MAT_CODE, SUM(A.CUM_USE_QTY) AS USE_QTY
				,MAX(WORK_CODE) AS WORK_CODE, max(item_class) as item_class
				,MAX(ISNULL(B.STOCK_QTY,0) + ISNULL(B.PR_STOCK_QTY,0)) AS STOCK_QTY
		  from #TEMP_BOM_MAT_DTL2		A
		  LEFT JOIN (SELECT MAT_CODE, SUM(STOCK_QTY) AS STOCK_QTY, SUM(PR_STOCK_QTY) AS PR_STOCK_QTY
							FROM #TEMP_MAT_STOCK
						  GROUP BY MAT_CODE)	B ON A.MAT_CODE = B.MAT_CODE
		 where A.WORK_CODE = @as_work_code															/*가공 or 축관*/
		   AND SET_EXCEPT_FLAG = '0'
			and A.GOLE_IN_CUST_CODE > ''																/*최종투입이 사급업체인 것*/
		   AND isnull(a.vir_item_flag,'0') <> '1'
		 group by item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, A.MAT_CODE


		--/*SET예외출고자재 추출*/
		--select item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, A.MAT_CODE, SUM(A.CUM_USE_QTY) AS USE_QTY
		--		,MAX(WORK_CODE) AS WORK_CODE, max(item_class) as item_class
		--		,MAX(ISNULL(B.STOCK_QTY,0) + ISNULL(B.PR_STOCK_QTY,0)) AS STOCK_QTY
		--  INTO #TEMP_BOM_MAT_EXCEPT
		--  from #TEMP_BOM_MAT_DTL						A
		--  LEFT JOIN #TEMP_MAT_STOCK	B ON A.MAT_CODE = B.MAT_CODE
		-- where A.WORK_CODE = @as_work_code															/*가공 or 축관*/
		--   AND SET_EXCEPT_FLAG = '1'
		--	and (@as_pr_part_code>'' and a.GOLE_GAGONG_PROC_CODE	like @as_pr_part_code			/*투입생산파트*/
		--				or
		--		  @as_pr_part_code='' and a.sagub_flag = '1' and a.GOLE_IN_CUST_CODE like @as_sagub_cust_code)		/*사급업체*/
		--   AND isnull(a.vir_item_flag,'0') <> '1'
		-- group by item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, A.MAT_CODE
	END



	/*ASSY그룹화 작업*/
	select item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, MAX(WORK_CODE) AS WORK_CODE, max(item_class) as item_class
			,string_AGG(a.MAT_CODE, ',') AS MAT_LIST
	  INTO #TEMP_BOM_ASSY
	  from (SELECT TOP 1000000 * FROM #TEMP_BOM_MAT
				ORDER BY item_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, MAT_CODE) a
	 group by item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE


	/*
	예외부품에 대한 별도 계획 표시

	INSERT INTO #TEMP_PART_DTL
	SELECT '' PLAN_YMD, '' WORK_ORDER, '' SPLIT_WORK_ORDER, '' ASSY_ITEM_CODE, 0 BOM_LEVEL, '' UPPER_ITEM_CODE, B.MAT_CODE AS ITEM_CODE, 0 PROC_SEQ, 
			'Q' GC_GUBUN, '' OUTPUT_HM, '' LINE_NO, SUM(B.USE_QTY) AS USE_QTY, SUM(PLAN_QTY * B.USE_QTY) AS PLAN_QTY, 
			'' WORK_CODE, B.ITEM_GAGONG_PROC_CODE AS GAGONG_PROC_CODE, 1 GAGONG_PROC_SEQ, MAX(A.JP_PROC_METHOD) AS JP_PROC_METHOD, 
			0 LT_HR, 0 CUM_LT_HR, PART_PLAN_YMD, '' PART_OUTPUT_HM, 
			SUM(PART_PLAN_QTY * B.USE_QTY) AS PART_PLAN_QTY, 0 AS FINISH_TAG, 16777215 AS COLOR, 0 AS FINISH_QTY, 0 AS SALE_QTY, 
			0 AS ASSY_STOCK_QTY, 0 AS FIX_STOCK_QTY, 0 AS PR_STOCK_QTY, 0 AS STOCK_QTY, 0 AS PART_STOCK_QTY, 0 AS PRIOR_JP_FINISH_QTY, 0 AS JP_FINISH_QTY, 
			0 AS READY_STOCK_QTY, 0 AS READY_QTY, CUM_JAN_QTY, CUM_ITEM_CODE, PRIOR_GAGONG_PROC_CODE, PRIOR_GAGONG_PROC_SEQ
	  FROM #TEMP_PART_DTL A
	  JOIN #TEMP_BOM_MAT_EXCEPT B ON A.ASSY_ITEM_CODE = B.ITEM_CODE
	 GROUP BY PLAN_YMD, 
	*/











	--도번고정재고 적용
	BEGIN
		/*도번고정재고 세팅*/
		UPDATE A
			SET FIX_STOCK_QTY = T.FIX_STOCK_QTY
		  FROM #TEMP_PART_DTL A
		  join (SELECT ITEM_CODE, MAT_CODE, SUM(FIX_STOCK_QTY) AS FIX_STOCK_QTY
					 FROM #TEMP_MAT_STOCK
					GROUP BY ITEM_CODE, MAT_CODE) T ON A.UPPER_ITEM_CODE = T.ITEM_CODE AND A.ITEM_CODE = T.MAT_CODE
		 WHERE A.UPPER_ITEM_CODE <> A.ITEM_CODE

		/*도번고정재고 세팅*/
		UPDATE A
			SET FIX_STOCK_QTY = A.FIX_STOCK_QTY + T.FIX_STOCK_QTY
		  FROM #TEMP_PART_DTL A
		  join (SELECT ITEM_CODE, MAT_CODE, SUM(FIX_STOCK_QTY) AS FIX_STOCK_QTY
					 FROM #TEMP_MAT_STOCK
					GROUP BY ITEM_CODE, MAT_CODE) T ON A.ASSY_ITEM_CODE = T.ITEM_CODE AND A.ITEM_CODE = T.MAT_CODE
		 WHERE A.UPPER_ITEM_CODE = A.ITEM_CODE







		set @ls_UPPER_ITEM_CODE = ''
		set @ls_ITEM_CODE = ''

		/*도번고정재고 감안*/
		declare dc1 cursor for
		select t.ITEM_CODE, t.PROC_SEQ, t.PART_PLAN_YMD, t.PART_OUTPUT_HM, t.PLAN_YMD, t.OUTPUT_HM, 
					t.BOM_LEVEL, t.WORK_ORDER, t.SPLIT_WORK_ORDER, t.ASSY_ITEM_CODE, t.UPPER_ITEM_CODE,
					t.USE_QTY, t.PART_PLAN_QTY, t.FINISH_QTY, t.FIX_STOCK_QTY
		  FROM #TEMP_PART_DTL t WITH (NOLOCK) 
		 where t.PART_PLAN_YMD between '' and @as_to_ymd
			AND t.STOCK_QTY + t.PR_STOCK_QTY + t.FIX_STOCK_QTY > 0
		 order by t.UPPER_ITEM_CODE, t.ITEM_CODE, t.GAGONG_PROC_CODE, t.part_plan_ymd, t.part_OUTPUT_HM, t.PLAN_YMD, t.OUTPUT_HM, t.WORK_ORDER, t.SPLIT_WORK_ORDER
		 --order by t.ITEM_CODE, t.PROC_SEQ, t.PART_PLAN_YMD, t.PART_OUTPUT_HM, t.PLAN_YMD, t.OUTPUT_HM, t.BOM_LEVEL, t.WORK_ORDER, t.SPLIT_WORK_ORDER
		open dc1
		fetch from dc1 into @db_ITEM_CODE, @db_PROC_SEQ, @db_PART_PLAN_YMD, @db_PART_OUTPUT_HM, @db_PLAN_YMD, @db_OUTPUT_HM, 
									@db_BOM_LEVEL, @db_WORK_ORDER, @db_SPLIT_WORK_ORDER, @db_ASSY_ITEM_CODE, @db_UPPER_ITEM_CODE,
									@db_USE_QTY, @db_PART_PLAN_QTY, @db_FINISH_QTY, @db_PR_STOCK_QTY
		while (@@fetch_status = 0)
		begin
			if @ls_UPPER_ITEM_CODE <> @db_UPPER_ITEM_CODE 
				or @ls_ITEM_CODE <> @db_ITEM_CODE 
				or @li_PROC_SEQ <> @db_PROC_SEQ
			begin
				set @ls_UPPER_ITEM_CODE = @db_UPPER_ITEM_CODE
				set @ls_ITEM_CODE			= @db_ITEM_CODE
				set @li_PROC_SEQ			= @db_PROC_SEQ
				set @li_STOCK_QTY			= @db_PR_STOCK_QTY
			end
			if @li_STOCK_QTY > 0
			begin
				set @li_JAN_QTY = @db_PART_PLAN_QTY - @db_FINISH_QTY

				if @li_JAN_QTY > 0
				BEGIN
					if @li_JAN_QTY > @li_STOCK_QTY
					BEGIN
						SET @li_FINISH_TAG = NULL
						SET @li_FINISH_QTY = @li_STOCK_QTY
						SET @li_STOCK_QTY = 0
					END
					ELSE
					BEGIN
						SET @li_FINISH_TAG = 70
						SET @li_FINISH_QTY = @li_JAN_QTY
						SET @li_STOCK_QTY = @li_STOCK_QTY - @li_JAN_QTY
					END

					update #TEMP_PART_DTL
						set FINISH_QTY = FINISH_QTY + @li_FINISH_QTY
							,FINISH_TAG = ISNULL(@li_FINISH_TAG, FINISH_TAG)
					 where PLAN_YMD			= @db_PLAN_YMD
						and WORK_ORDER			= @db_WORK_ORDER
						and SPLIT_WORK_ORDER = @db_SPLIT_WORK_ORDER
						and ASSY_ITEM_CODE	= @db_ASSY_ITEM_CODE
						and BOM_LEVEL			= @db_BOM_LEVEL
						and UPPER_ITEM_CODE	= @db_UPPER_ITEM_CODE
						and ITEM_CODE			= @db_ITEM_CODE
						and PROC_SEQ			= @db_PROC_SEQ
				END
			end
			fetch from dc1 into @db_ITEM_CODE, @db_PROC_SEQ, @db_PART_PLAN_YMD, @db_PART_OUTPUT_HM, @db_PLAN_YMD, @db_OUTPUT_HM, 
										@db_BOM_LEVEL, @db_WORK_ORDER, @db_SPLIT_WORK_ORDER, @db_ASSY_ITEM_CODE, @db_UPPER_ITEM_CODE,
										@db_USE_QTY, @db_PART_PLAN_QTY, @db_FINISH_QTY, @db_PR_STOCK_QTY
		end
		close dc1
		DEALLOCATE dc1
	END








	--자재재고 적용
	BEGIN
		/*자재재고 세팅*/
		UPDATE A
			SET STOCK_QTY				= T.STOCK_QTY
				,PR_STOCK_QTY			= T.PR_STOCK_QTY
		  FROM #TEMP_PART_DTL A
		  join (SELECT MAT_CODE, SUM(STOCK_QTY) AS STOCK_QTY, SUM(PR_STOCK_QTY) AS PR_STOCK_QTY
					 FROM #TEMP_MAT_STOCK
					GROUP BY MAT_CODE)	 T ON A.ITEM_CODE = T.MAT_CODE

		set @ls_ITEM_CODE = ''

		/*자재재고 감안*/
		declare dc1 cursor for
		select t.ITEM_CODE, t.PROC_SEQ, t.PART_PLAN_YMD, t.PART_OUTPUT_HM, t.PLAN_YMD, t.OUTPUT_HM, 
					t.BOM_LEVEL, t.WORK_ORDER, t.SPLIT_WORK_ORDER, t.ASSY_ITEM_CODE, t.UPPER_ITEM_CODE,
					t.USE_QTY, t.PART_PLAN_QTY, t.FINISH_QTY, t.STOCK_QTY + t.PR_STOCK_QTY
		  FROM #TEMP_PART_DTL t WITH (NOLOCK) 
		 where t.PART_PLAN_YMD between '' and @as_to_ymd
			AND t.STOCK_QTY + t.PR_STOCK_QTY + t.FIX_STOCK_QTY > 0
		 order by t.ITEM_CODE, t.PROC_SEQ, t.GAGONG_PROC_CODE, t.part_plan_ymd, t.part_OUTPUT_HM, t.PLAN_YMD, t.OUTPUT_HM, t.WORK_ORDER, t.SPLIT_WORK_ORDER
		 --order by t.ITEM_CODE, t.PROC_SEQ, t.PART_PLAN_YMD, t.PART_OUTPUT_HM, t.PLAN_YMD, t.OUTPUT_HM, t.BOM_LEVEL, t.WORK_ORDER, t.SPLIT_WORK_ORDER
		open dc1
		fetch from dc1 into @db_ITEM_CODE, @db_PROC_SEQ, @db_PART_PLAN_YMD, @db_PART_OUTPUT_HM, @db_PLAN_YMD, @db_OUTPUT_HM, 
									@db_BOM_LEVEL, @db_WORK_ORDER, @db_SPLIT_WORK_ORDER, @db_ASSY_ITEM_CODE, @db_UPPER_ITEM_CODE,
									@db_USE_QTY, @db_PART_PLAN_QTY, @db_FINISH_QTY, @db_PR_STOCK_QTY
		while (@@fetch_status = 0)
		begin
			if @ls_ITEM_CODE <> @db_ITEM_CODE 
				or @li_PROC_SEQ <> @db_PROC_SEQ
			begin
				set @ls_ITEM_CODE = @db_ITEM_CODE
				set @li_PROC_SEQ	= @db_PROC_SEQ
				set @li_STOCK_QTY = @db_PR_STOCK_QTY
			end
			if @li_STOCK_QTY > 0
			begin
				set @li_JAN_QTY = @db_PART_PLAN_QTY - @db_FINISH_QTY

				if @li_JAN_QTY > 0
				BEGIN
					if @li_JAN_QTY > @li_STOCK_QTY
					BEGIN
						SET @li_FINISH_TAG = NULL
						SET @li_FINISH_QTY = @li_STOCK_QTY
						SET @li_STOCK_QTY = 0
					END
					ELSE
					BEGIN
						SET @li_FINISH_TAG = 70
						SET @li_FINISH_QTY = @li_JAN_QTY
						SET @li_STOCK_QTY = @li_STOCK_QTY - @li_JAN_QTY
					END

					update #TEMP_PART_DTL
						set FINISH_QTY = FINISH_QTY + @li_FINISH_QTY
							,FINISH_TAG = ISNULL(@li_FINISH_TAG, FINISH_TAG)
					 where PLAN_YMD			= @db_PLAN_YMD
						and WORK_ORDER			= @db_WORK_ORDER
						and SPLIT_WORK_ORDER = @db_SPLIT_WORK_ORDER
						and ASSY_ITEM_CODE	= @db_ASSY_ITEM_CODE
						and BOM_LEVEL			= @db_BOM_LEVEL
						and UPPER_ITEM_CODE	= @db_UPPER_ITEM_CODE
						and ITEM_CODE			= @db_ITEM_CODE
						and PROC_SEQ			= @db_PROC_SEQ
				END
			end
			fetch from dc1 into @db_ITEM_CODE, @db_PROC_SEQ, @db_PART_PLAN_YMD, @db_PART_OUTPUT_HM, @db_PLAN_YMD, @db_OUTPUT_HM, 
										@db_BOM_LEVEL, @db_WORK_ORDER, @db_SPLIT_WORK_ORDER, @db_ASSY_ITEM_CODE, @db_UPPER_ITEM_CODE,
										@db_USE_QTY, @db_PART_PLAN_QTY, @db_FINISH_QTY, @db_PR_STOCK_QTY
		end
		close dc1
		DEALLOCATE dc1
	END








	IF object_id('tempdb..#TEMP_MAT_MOVE_PLAN') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_MAT_MOVE_PLAN;
	END

	BEGIN
			select DISTINCT a.gagong_proc_code,
				'' as part_group_code,
				a.work_order,
				a.split_work_order,
				a.assy_item_code,
				a.upper_item_code,
				a.item_code,
				b.item_desc,
				iif(r.GOLE_IN_CUST_CODE>'',r.GOLE_IN_CUST_CODE,'Z99990') as GOLE_CODE,
				r.GOLE_GAGONG_PROC_CODE,
				r.GOLE_IN_CUST_CODE,
				r.WORK_CODE AS MAT_WORK_CODE,

				a.work_code,
				a.proc_seq,

				a.use_qty,
				a.part_plan_ymd,
				a.part_output_hm,
				a.plan_ymd,
				a.output_hm,
				a.line_no,

				a.part_plan_qty,
				a.finish_qty,
				a.finish_tag,

				a.sale_qty,
				a.assy_stock_qty,
				a.stock_qty,
				a.pr_stock_qty,
				a.FIX_STOCK_QTY,
				a.JP_print_qty,
				wk.prod_rate,
				convert(varchar(10), @as_pu_part_code) as wh_gagong_proc_code,
				(select GAGONG_PROC_DESC FROM PR_M_PROC_GAGONG WITH (NOLOCK) WHERE GAGONG_PROC_CODE = @as_pu_part_code) AS WH_GAGONG_PROC_DESC,

				convert(varchar(30), r.item_class) as item_class,
				r.mat_list

		INTO #TEMP_MAT_MOVE_PLAN

		FROM #TEMP_PART_DTL a
		join #TEMP_BOM_ASSY r on r.item_code						= a.item_code
									and r.item_gagong_proc_code		= a.gagong_proc_code
		join pr_m_item b WITH (NOLOCK) on b.item_code			= a.assy_item_code
		left join PR_M_PROC_GAGONG wk WITH (NOLOCK) on wk.GAGONG_PROC_CODE = a.gagong_proc_code

		WHERE a.part_plan_ymd		between '' and @as_to_ymd
	END








	--SET가능한 자재재고 적용, 이동전표발행분 적용
	BEGIN
		/*가공세트재고 세팅*/
		UPDATE A
			SET JP_PRINT_QTY		= T.STOCK_QTY
		  FROM #TEMP_MAT_MOVE_PLAN A
		  join PARTNER_ERP_TEST3.nx.PU_T_SET_GAGONG_STOCK T WITH (NOLOCK) ON A.ITEM_CODE = T.ITEM_CODE AND A.GOLE_CODE = T.IN_CUST_CODE

		/*이동전표발행분 세팅*/
		UPDATE A
			SET JP_PRINT_QTY		= A.JP_PRINT_QTY + T.SET_QTY
		  FROM #TEMP_MAT_MOVE_PLAN A
		  join (SELECT ITEM_CODE, GOLE_CODE, SUM(SET_QTY) AS SET_QTY
					 FROM (SELECT ITEM_CODE, MAINT_GROUP_SEQ, MAX(IIF(SAGUB_CUST_CODE>'',SAGUB_CUST_CODE,'Z99990')) AS GOLE_CODE, MAX(SET_QTY) AS SET_QTY
							 FROM PU_T_STOCK_MAINT_GAGONG_MOVE WITH (NOLOCK)
							WHERE IN_CONFIRM_FLAG = '0'
							GROUP BY ITEM_CODE, MAINT_GROUP_SEQ) T
					GROUP BY ITEM_CODE, GOLE_CODE) T ON A.ITEM_CODE = T.ITEM_CODE AND A.GOLE_CODE = T.GOLE_CODE

		set @ls_GOLE_CODE = ''
		set @ls_ITEM_CODE = ''
		set @li_PROC_SEQ = 0

		/*파트재고 감안*/
		declare dc1 cursor for
		select t.GOLE_CODE, t.ITEM_CODE, t.PROC_SEQ, t.PART_PLAN_YMD, t.PART_OUTPUT_HM, t.PLAN_YMD, t.OUTPUT_HM, 
					t.WORK_ORDER, t.SPLIT_WORK_ORDER, t.ASSY_ITEM_CODE, t.UPPER_ITEM_CODE,
					t.USE_QTY, t.PART_PLAN_QTY, t.FINISH_QTY, t.JP_PRINT_QTY
		  FROM #TEMP_MAT_MOVE_PLAN t WITH (NOLOCK) 
		 where t.PART_PLAN_YMD between '' and @as_to_ymd
			AND t.JP_PRINT_QTY > 0
		 order by t.GOLE_CODE, t.ITEM_CODE, t.PROC_SEQ, t.PART_PLAN_YMD, t.PART_OUTPUT_HM, t.PLAN_YMD, t.OUTPUT_HM, t.WORK_ORDER, t.SPLIT_WORK_ORDER
		open dc1
		fetch from dc1 into @db_GOLE_CODE, @db_ITEM_CODE, @db_PROC_SEQ, @db_PART_PLAN_YMD, @db_PART_OUTPUT_HM, @db_PLAN_YMD, @db_OUTPUT_HM, 
									@db_WORK_ORDER, @db_SPLIT_WORK_ORDER, @db_ASSY_ITEM_CODE, @db_UPPER_ITEM_CODE,
									@db_USE_QTY, @db_PART_PLAN_QTY, @db_FINISH_QTY, @db_PR_STOCK_QTY
		while (@@fetch_status = 0)
		begin
			if @ls_GOLE_CODE <> @db_GOLE_CODE 
				or @ls_ITEM_CODE <> @db_ITEM_CODE 
				or @li_PROC_SEQ <> @db_PROC_SEQ
			begin
				set @ls_GOLE_CODE = @db_GOLE_CODE
				set @ls_ITEM_CODE = @db_ITEM_CODE
				set @li_PROC_SEQ	= @db_PROC_SEQ
				set @li_STOCK_QTY = @db_PR_STOCK_QTY
			end
			if @li_STOCK_QTY > 0
			begin
				set @li_JAN_QTY = @db_PART_PLAN_QTY - @db_FINISH_QTY

				if @li_JAN_QTY > 0
				BEGIN
					if @li_JAN_QTY > @li_STOCK_QTY
					BEGIN
						SET @li_FINISH_TAG = NULL
						SET @li_FINISH_QTY = @li_STOCK_QTY
						SET @li_STOCK_QTY = 0
					END
					ELSE
					BEGIN
						SET @li_FINISH_TAG = 50
						SET @li_FINISH_QTY = @li_JAN_QTY
						SET @li_STOCK_QTY = @li_STOCK_QTY - @li_JAN_QTY
					END

					update #TEMP_MAT_MOVE_PLAN
						set FINISH_QTY = FINISH_QTY + @li_FINISH_QTY
							,FINISH_TAG = ISNULL(@li_FINISH_TAG, FINISH_TAG)
					 where PLAN_YMD			= @db_PLAN_YMD
						and WORK_ORDER			= @db_WORK_ORDER
						and SPLIT_WORK_ORDER = @db_SPLIT_WORK_ORDER
						and ASSY_ITEM_CODE	= @db_ASSY_ITEM_CODE
						and UPPER_ITEM_CODE	= @db_UPPER_ITEM_CODE
						and ITEM_CODE			= @db_ITEM_CODE
						and PROC_SEQ			= @db_PROC_SEQ
						and GOLE_CODE			= @db_GOLE_CODE
				END
			end
			fetch from dc1 into @db_GOLE_CODE, @db_ITEM_CODE, @db_PROC_SEQ, @db_PART_PLAN_YMD, @db_PART_OUTPUT_HM, @db_PLAN_YMD, @db_OUTPUT_HM, 
										@db_WORK_ORDER, @db_SPLIT_WORK_ORDER, @db_ASSY_ITEM_CODE, @db_UPPER_ITEM_CODE,
										@db_USE_QTY, @db_PART_PLAN_QTY, @db_FINISH_QTY, @db_PR_STOCK_QTY
		end
		close dc1
		DEALLOCATE dc1
	END











	
	BEGIN
		select t.*,
				0 as item_st,
				wk.prod_rate,		
				'0' as prod_calc_flag,
				case finish_tag_00 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_00,
				case finish_tag_01 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_01,
				case finish_tag_02 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_02,
				case finish_tag_03 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_03,
				case finish_tag_04 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_04,
				case finish_tag_05 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_05,
				case finish_tag_06 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_06,
				case finish_tag_07 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_07,
				case finish_tag_08 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_08,
				case finish_tag_09 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_09,
				case finish_tag_10 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_10,
				case finish_tag_11 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_11,
				case finish_tag_12 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_12,
				case finish_tag_13 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_13,
				case finish_tag_14 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_14,
				case finish_tag_15 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_15,
				case finish_tag_16 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_16,
				case finish_tag_17 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_17,
				case finish_tag_18 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_18,
				case finish_tag_19 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_19,
				case finish_tag_20 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_20,
				case finish_tag_21 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_21,
				case finish_tag_22 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_22,
				case finish_tag_23 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_23,
				case finish_tag_24 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_24,
				case finish_tag_25 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_25,
				case finish_tag_26 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_26,
				case finish_tag_27 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_27,
				case finish_tag_28 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_28,
				case finish_tag_29 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_29,
				case finish_tag_30 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_30,
				case finish_tag_31 when 90 then 9486586 when 70 then 65535 when 50 then 39270 when 30 then 12632256 when 10 then 39270 else 16777215 end as color_31,

				convert(varchar(10), @as_pu_part_code) as wh_gagong_proc_code,
				(select GAGONG_PROC_DESC FROM PR_M_PROC_GAGONG WITH (NOLOCK) WHERE GAGONG_PROC_CODE = @as_pu_part_code) AS WH_GAGONG_PROC_DESC,
				ISNULL((select GAGONG_PROC_DESC FROM PR_M_PROC_GAGONG WITH (NOLOCK) WHERE GAGONG_PROC_CODE = T.GOLE_GAGONG_PROC_CODE),'') AS GOLE_GAGONG_PROC_DESC,
				ISNULL((select CUST_DESC FROM CM_M_CUST WITH (NOLOCK) WHERE CUST_CODE = T.GOLE_IN_CUST_CODE),'') AS GOLE_IN_CUST_DESC,
				ISNULL((select WORK_DESC FROM PR_M_WORK WITH (NOLOCK) WHERE WORK_CODE = T.MAT_WORK_CODE),'') AS MAT_WORK_DESC,
				0 as c_height,			
				isnull((select DETAIL_DESC from CM_M_MASTER_DETAIL qq WITH (NOLOCK) where qq.detail_code= t.item_class and qq.KIND_CODE= 'PR008'),'') as item_class_desc
	
		from (
				 select a.gagong_proc_code,
						max(a.part_group_code) as part_group_code,
						'' as work_order,
						'' as split_work_order,
						a.assy_item_code,
						a.upper_item_code,
						a.item_code,
						'' MAT_CODE,
						MAX(a.ITEM_DESC) AS ITEM_DESC,

						a.GOLE_GAGONG_PROC_CODE,
						a.GOLE_IN_CUST_CODE,
						max(a.mat_work_code) as mat_work_code,
						max(a.work_code) as work_code,
						min(a.proc_seq) as proc_seq,

						max(a.use_qty) as use_qty,
						0 as mat_use_qty,
						min(a.part_plan_ymd) as part_plan_ymd,
						min(a.part_output_hm) as part_output_hm,
						min(a.plan_ymd) as plan_ymd,
						min(a.output_hm) as output_hm,
						min(a.line_no) as line_no,

						sum(a.part_plan_qty) as plan_qty,

						sum(case when a.part_plan_ymd < @as_from_ymd then a.part_plan_qty else 0 end)  as plan_qty_00,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 0, 12) then a.part_plan_qty else 0 end) as plan_qty_01,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 1, 12) then a.part_plan_qty else 0 end) as plan_qty_02,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 2, 12) then a.part_plan_qty else 0 end) as plan_qty_03,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 3, 12) then a.part_plan_qty else 0 end) as plan_qty_04,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 4, 12) then a.part_plan_qty else 0 end) as plan_qty_05,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 5, 12) then a.part_plan_qty else 0 end) as plan_qty_06,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 6, 12) then a.part_plan_qty else 0 end) as plan_qty_07,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 7, 12) then a.part_plan_qty else 0 end) as plan_qty_08,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 8, 12) then a.part_plan_qty else 0 end) as plan_qty_09,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 9, 12) then a.part_plan_qty else 0 end) as plan_qty_10,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 10, 12) then a.part_plan_qty else 0 end) as plan_qty_11,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 11, 12) then a.part_plan_qty else 0 end) as plan_qty_12,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 12, 12) then a.part_plan_qty else 0 end) as plan_qty_13,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 13, 12) then a.part_plan_qty else 0 end) as plan_qty_14,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 14, 12) then a.part_plan_qty else 0 end) as plan_qty_15,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 15, 12) then a.part_plan_qty else 0 end) as plan_qty_16,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 16, 12) then a.part_plan_qty else 0 end) as plan_qty_17,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 17, 12) then a.part_plan_qty else 0 end) as plan_qty_18,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 18, 12) then a.part_plan_qty else 0 end) as plan_qty_19,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 19, 12) then a.part_plan_qty else 0 end) as plan_qty_20,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 20, 12) then a.part_plan_qty else 0 end) as plan_qty_21,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 21, 12) then a.part_plan_qty else 0 end) as plan_qty_22,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 22, 12) then a.part_plan_qty else 0 end) as plan_qty_23,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 23, 12) then a.part_plan_qty else 0 end) as plan_qty_24,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 24, 12) then a.part_plan_qty else 0 end) as plan_qty_25,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 25, 12) then a.part_plan_qty else 0 end) as plan_qty_26,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 26, 12) then a.part_plan_qty else 0 end) as plan_qty_27,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 27, 12) then a.part_plan_qty else 0 end) as plan_qty_28,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 28, 12) then a.part_plan_qty else 0 end) as plan_qty_29,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 29, 12) then a.part_plan_qty else 0 end) as plan_qty_30,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 30, 12) then a.part_plan_qty else 0 end) as plan_qty_31,

						sum(a.finish_qty)																																				as finish_qty,
						sum(case when a.part_plan_ymd < @as_from_ymd then a.finish_qty else 0 end) 																as finish_qty_00,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 0, 12) then a.finish_qty else 0 end)   as finish_qty_01,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 1, 12) then a.finish_qty else 0 end)   as finish_qty_02,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 2, 12) then a.finish_qty else 0 end)   as finish_qty_03,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 3, 12) then a.finish_qty else 0 end)   as finish_qty_04,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 4, 12) then a.finish_qty else 0 end)   as finish_qty_05,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 5, 12) then a.finish_qty else 0 end)   as finish_qty_06,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 6, 12) then a.finish_qty else 0 end)   as finish_qty_07,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 7, 12) then a.finish_qty else 0 end)   as finish_qty_08,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 8, 12) then a.finish_qty else 0 end)   as finish_qty_09,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 9, 12) then a.finish_qty else 0 end)   as finish_qty_10,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 10, 12) then a.finish_qty else 0 end)  as finish_qty_11,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 11, 12) then a.finish_qty else 0 end)  as finish_qty_12,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 12, 12) then a.finish_qty else 0 end)  as finish_qty_13,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 13, 12) then a.finish_qty else 0 end)  as finish_qty_14,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 14, 12) then a.finish_qty else 0 end)  as finish_qty_15,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 15, 12) then a.finish_qty else 0 end)  as finish_qty_16,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 16, 12) then a.finish_qty else 0 end)  as finish_qty_17,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 17, 12) then a.finish_qty else 0 end)  as finish_qty_18,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 18, 12) then a.finish_qty else 0 end)  as finish_qty_19,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 19, 12) then a.finish_qty else 0 end)  as finish_qty_20,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 20, 12) then a.finish_qty else 0 end)  as finish_qty_21,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 21, 12) then a.finish_qty else 0 end)  as finish_qty_22,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 22, 12) then a.finish_qty else 0 end)  as finish_qty_23,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 23, 12) then a.finish_qty else 0 end)  as finish_qty_24,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 24, 12) then a.finish_qty else 0 end)  as finish_qty_25,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 25, 12) then a.finish_qty else 0 end)  as finish_qty_26,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 26, 12) then a.finish_qty else 0 end)  as finish_qty_27,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 27, 12) then a.finish_qty else 0 end)  as finish_qty_28,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 28, 12) then a.finish_qty else 0 end)  as finish_qty_29,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 29, 12) then a.finish_qty else 0 end)  as finish_qty_30,
						sum(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 30, 12) then a.finish_qty else 0 end)  as finish_qty_31,

						isnull(min(case when a.part_plan_ymd < @as_from_ymd then a.finish_tag else null end), 0) as finish_tag_00,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 0, 12) then a.finish_tag else null end), 0)  as finish_tag_01,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 1, 12) then a.finish_tag else null end), 0)  as finish_tag_02,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 2, 12) then a.finish_tag else null end), 0)  as finish_tag_03,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 3, 12) then a.finish_tag else null end), 0)  as finish_tag_04,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 4, 12) then a.finish_tag else null end), 0)  as finish_tag_05,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 5, 12) then a.finish_tag else null end), 0)  as finish_tag_06,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 6, 12) then a.finish_tag else null end), 0)  as finish_tag_07,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 7, 12) then a.finish_tag else null end), 0)  as finish_tag_08,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 8, 12) then a.finish_tag else null end), 0)  as finish_tag_09,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 9, 12) then a.finish_tag else null end), 0)  as finish_tag_10,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 10, 12) then a.finish_tag else null end), 0) as finish_tag_11,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 11, 12) then a.finish_tag else null end), 0) as finish_tag_12,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 12, 12) then a.finish_tag else null end), 0) as finish_tag_13,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 13, 12) then a.finish_tag else null end), 0) as finish_tag_14,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 14, 12) then a.finish_tag else null end), 0) as finish_tag_15,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 15, 12) then a.finish_tag else null end), 0) as finish_tag_16,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 16, 12) then a.finish_tag else null end), 0) as finish_tag_17,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 17, 12) then a.finish_tag else null end), 0) as finish_tag_18,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 18, 12) then a.finish_tag else null end), 0) as finish_tag_19,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 19, 12) then a.finish_tag else null end), 0) as finish_tag_20,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 20, 12) then a.finish_tag else null end), 0) as finish_tag_21,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 21, 12) then a.finish_tag else null end), 0) as finish_tag_22,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 22, 12) then a.finish_tag else null end), 0) as finish_tag_23,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 23, 12) then a.finish_tag else null end), 0) as finish_tag_24,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 24, 12) then a.finish_tag else null end), 0) as finish_tag_25,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 25, 12) then a.finish_tag else null end), 0) as finish_tag_26,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 26, 12) then a.finish_tag else null end), 0) as finish_tag_27,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 27, 12) then a.finish_tag else null end), 0) as finish_tag_28,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 28, 12) then a.finish_tag else null end), 0) as finish_tag_29,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 29, 12) then a.finish_tag else null end), 0) as finish_tag_30,
						isnull(min(case a.part_plan_ymd when convert(varchar, convert(datetime, @as_from_ymd, 12) + 30, 12) then a.finish_tag else null end), 0) as finish_tag_31,

						max(a.sale_qty) as sale_qty,
						max(a.assy_stock_qty) as assy_stock_qty,
						max(a.stock_qty) as stock_qty, 
						max(a.pr_stock_qty) as pr_stock_qty, 
						max(a.fix_stock_qty) as fix_stock_qty, 
						max(a.jp_print_qty) as jp_print_qty,

						'' as min_part_plan_ymd_hm,					

						0 AS KIT_WH_STOCK_QTY,			/*자재재고*/
						0 AS WH_STOCK_QTY,				/*가공재고*/
						0 AS STACKER_STOCK_QTY,			/*없음*/
						0 AS OTHER_STOCK_QTY,			/*생산재고*/
						a.item_class,
						max(a.mat_list) as mat_list
					    
					FROM #TEMP_MAT_MOVE_PLAN a
				  group by  a.gagong_proc_code,
						 	a.assy_item_code,
							a.upper_item_code,
							a.item_code,
							a.item_class,
							a.GOLE_GAGONG_PROC_CODE,
							a.GOLE_IN_CUST_CODE

			) t
		left join PR_M_PROC_GAGONG wk WITH (NOLOCK) 	on wk.GAGONG_PROC_CODE = t.gagong_proc_code
	END

END

