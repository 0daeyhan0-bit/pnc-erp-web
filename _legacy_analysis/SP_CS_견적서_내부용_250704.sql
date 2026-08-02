





-- =============================================
-- Author:		<Author,,Name>
-- Create date: <Create Date,,>
-- Description:	<Description,,>
-- =============================================
CREATE PROCEDURE [dbo].[SP_CS_견적서(내부용)_250704]
	@AS_ITEM_CODE				varchar(20),
	@AS_COST_APPLY_YMD		varchar(6)
AS
BEGIN
/* 
	begin
		exec dbo.[SP_CS_견적서(내부용)] 'AJR30001402', '241105'
	end

	DECLARE	@AS_ITEM_CODE				VARCHAR(20)
	DECLARE	@AS_COST_APPLY_YMD		VARCHAR(6)

	SET @AS_ITEM_CODE			= 'AJR30001402'
	SET @AS_COST_APPLY_YMD	= '241105'
*/

	-- SET NOCOUNT ON added to prevent extra result sets from
	-- interfering with SELECT statements.
	SET NOCOUNT OFF;

	DECLARE	@LS_FROM_YYMM		VARCHAR(4)
	DECLARE	@LI_LEVEL_MAX		INT
	DECLARE	@LI_LEVEL			INT
	DECLARE	@LS_ITEM_GROUP		VARCHAR(1)

	SET @LS_FROM_YYMM = SUBSTRING(CONVERT(VARCHAR,DATEADD(MONTH, -2, CONVERT(DATETIME,@AS_COST_APPLY_YMD,12)),12),1,4)

	SELECT @LS_ITEM_GROUP = ITEM_LGROUP
	  FROM PR_M_ITEM 
	 WHERE ITEM_CODE = @AS_ITEM_CODE

	IF object_id('tempdb..#TEMP_BOM') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_BOM;
	END

	IF object_id('tempdb..#TEMP_EXCHANGE') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_EXCHANGE;
	END

	IF object_id('tempdb..#TEMP_MAT') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_MAT;
	END


	select   max(us_bas)  as us_bas,
				max(yen_bas)  as yen_bas,
				max(eur_bas)  as eur_bas
		INTO #TEMP_EXCHANGE
		from (
				SELECT top 1
						T1.BAS as us_bas,   
						0 as yen_bas,
						0 as eur_bas
					FROM FI_M_EXCHANGE T1
				WHERE T1.EXCH_YMD <= @AS_COST_APPLY_YMD
					and t1.currency_tag = 'USD'
				order by T1.EXCH_YMD desc

				union all
		
				SELECT top 1
						0 as us_bas,   
						T1.BAS as yen_bas,
						0 as eur_bas
					FROM FI_M_EXCHANGE T1
				WHERE T1.EXCH_YMD <= @AS_COST_APPLY_YMD
					and t1.currency_tag = 'YEN'
				order by T1.EXCH_YMD desc

				union all
		
				SELECT top 1
						0 as us_bas,   
						0 as yen_bas,
						T1.BAS as eur_bas
					FROM FI_M_EXCHANGE T1
				WHERE T1.EXCH_YMD <= @AS_COST_APPLY_YMD
					and t1.currency_tag = 'EUR'
				order by T1.EXCH_YMD desc
			) t




	BEGIN
 		WITH CTE_BOM(assy_item_code, item_code, db_item_code, work_code, in_cust_code, level_num, bom_seq, mat_code, mat_work_code, mat_in_cust_code, parent_in_cust_code, use_qty, upper_use_qty, cum_use_qty, cum_mat_code,
							item_desc, item_spec, item_class, item_lgroup, item_sgroup, item_diam, item_thick, item_length, metal_gubun, pipe_kind, item_weight, unit, gravity, cost_gubun, lme_except_flag)
		AS (
			/*앵커멤버-생산계획*/
				select
						c.item_code as assy_item_code,
						c.item_code as item_code,
						iif(c.SILVER_SOLDER>'',c.item_code,'') as db_item_code,
						c.work_code,
						c.in_cust_code,
						convert(int,0)	as level_num,
						convert(smallint,0)	as bom_seq,
						c.item_code 	as mat_code,
						c.work_code 	as mat_work_code,
						c.in_cust_code as mat_in_cust_code,
						convert(varchar(10),'')	as parent_in_cust_code,
						convert(numeric(18,4),1) as use_qty, 
						convert(numeric(18,4),1) as upper_use_qty, 
						convert(numeric(18,4),1) as cum_use_qty,
						convert(varchar(200),'00' + c.item_code) as cum_mat_code,
						c.item_desc,
						c.item_spec,
						c.item_class,
						c.item_lgroup,
						c.item_sgroup,
						c.item_diam,
						c.item_thick,
						c.item_length,
						c.metal_gubun,
						CONVERT(VARCHAR(2),'') AS PIPE_KIND,
						CONVERT(DECIMAL(18,4),0) AS item_weight,
						c.unit,

						(SELECT CONVERT(DECIMAL(18,2),OTHER_CHAR1) FROM CM_M_MASTER_DETAIL WHERE KIND_CODE = 'PR019' AND DETAIL_CODE = c.metal_gubun) AS gravity,
						convert(varchar(10),ISNULL(C.COST_GUBUN,'')) as cost_gubun,
						'0' as lme_except_flag

				 from pr_m_item c
				where c.ITEM_CODE	= @AS_ITEM_CODE
		    
				union all
 
				/* 재귀멤버 - BOM 하위추출 */
				select cb.assy_item_code,
						b.item_code,
						iif(m.SILVER_SOLDER>'',b.item_code,'') as db_item_code,
						c.work_code,
						c.in_cust_code,
						convert(int, cb.level_num + 1) as level_num,
						ISNULL(b.bom_seq,0),
						b.mat_code,
						m.work_code				as mat_work_code,
						m.in_cust_code			as mat_in_cust_code,
						convert(varchar(10),cb.mat_in_cust_code) as parent_in_cust_code,

						convert(numeric(18,4),b.use_qty) as use_qty,
						convert(numeric(18,4),cb.cum_use_qty) as upper_use_qty,
						convert(numeric(18,4),case when cb.cum_use_qty = 0 then 0
  												else CONVERT(NUMERIC(18,4), cb.cum_use_qty*b.use_qty) end) as cum_use_qty,		

						convert(varchar(200),cb.cum_mat_code + right('0' + convert(varchar, ISNULL(b.bom_seq,0)),2) + substring(b.mat_code + space(30), 1, 30)) as cum_mat_code,
						m.ITEM_DESC,
						m.ITEM_SPEC,
						m.item_class,
						m.item_lgroup,
						m.item_sgroup,
						m.ITEM_DIAM,
						m.ITEM_THICK,
						m.ITEM_LENGTH,
						m.metal_gubun,
						CONVERT(VARCHAR(2),'') AS PIPE_KIND,
						CONVERT(DECIMAL(18,4),0) AS item_weight,
						m.unit,
		   						
						(SELECT CONVERT(DECIMAL(18,2),OTHER_CHAR1) FROM CM_M_MASTER_DETAIL WHERE KIND_CODE = 'PR019' AND DETAIL_CODE = m.metal_gubun) AS gravity,
						ISNULL(m.cost_gubun,'') AS COST_GUBUN,
						isnull(b.lme_except_flag,'0') as lme_except_flag
				from CTE_BOM cb
				join CS_M_ITEM_BOM b				 on cb.mat_code	= b.item_code
				join pr_m_item c 					 on b.item_code	= c.item_code
				join pr_m_item m 					 on b.mat_code 	= m.item_code
			  where isnull(b.CS_CALC_EXCEPT_FLAG,'0') <> '1'
			    and cb.cost_gubun <> '5'		/*직납단가면 해당 품목의 단가를 사용하고 하위는 풀지 않는다.*/
			)	

		SELECT A.*
				,CONVERT(DECIMAL(18,4),0) as won_mat_cost				/*원소재비용*/
				,CONVERT(DECIMAL(18,4),0) as won_mat_cost_sub		/*협력사 원소재비용*/
				,CONVERT(DECIMAL(18,4),0) as jai_cost
				,CONVERT(DECIMAL(18,4),0) as jai_cost_sub				/*협력사 원소재비에 따른 재료비*/
				,CONVERT(VARCHAR(30),'') as mat_in_cust_desc
				,'0' as bottom_flag											/*재료비계산을 위한 BASE데이터 구분*/
		INTO #TEMP_BOM
		FROM CTE_BOM A
	END


	UPDATE #TEMP_BOM
		SET ITEM_WEIGHT = ROUND((ITEM_DIAM - ITEM_THICK) * ITEM_THICK * 3.141592 * ITEM_LENGTH * GRAVITY / 1000000, 4)
	 WHERE ITEM_DIAM > 0



	UPDATE A
		SET WON_MAT_COST = ISNULL((select top 1 round(tot_cost,4) from CS_M_METERIAL_COST where metal_gubun = a.metal_gubun
																											and apply_yyyymm  < '20'+@AS_COST_APPLY_YMD
																											and item_diam = a.item_diam
																											and item_thick = a.item_thick
																											order by apply_yyyymm desc),0)					/*원소재비용*/
			,WON_MAT_COST_SUB = ISNULL((select top 1 round(tot_cost,4) - round(tot_cost_sub,4) from CS_M_METERIAL_COST where metal_gubun = a.metal_gubun
																															and apply_yyyymm  < '20'+@AS_COST_APPLY_YMD
																															and item_diam = a.item_diam
																															and item_thick = a.item_thick
																															order by apply_yyyymm desc),0)	/*협력사 원소재비용*/
		FROM #TEMP_BOM A
	  WHERE ITEM_WEIGHT > 0





	/*하위데이터가 존재할 경우 단가는 하위에서 가져온다.*/
	UPDATE A
		SET COST_GUBUN = ''
	  FROM #TEMP_BOM A
	 WHERE (SELECT COUNT(*) FROM #TEMP_BOM WHERE ITEM_CODE = A.MAT_CODE) > 1
	   --AND LEVEL_NUM = 0



	/*사용자재추출*/
	--SELECT DISTINCT MAT_CODE, CONVERT(DECIMAL(18,4),0) AS MAT_COST, IIF(MAT_WORK_CODE='P2','2228',MAT_IN_CUST_CODE) AS IN_CUST_CODE
	SELECT DISTINCT MAT_CODE, CONVERT(DECIMAL(18,4),0) AS MAT_COST, MAT_IN_CUST_CODE AS IN_CUST_CODE
	  INTO #TEMP_MAT
	  FROM #TEMP_BOM
	 WHERE COST_GUBUN not in ('3', '4')		/*3=소재단가,4=직접입력(현재미사용)*/
	   AND COST_GUBUN > ''

	
	--/*3개월 입고에서 제일 마지막에 입고된 업체*/
	--UPDATE T
	--	SET IN_CUST_CODE = ISNULL((SELECT TOP 1 A.CUST_CODE
	--										 FROM (
	--												SELECT A.MAINT_YMD, A.CUST_CODE
	--													FROM PU_T_STOCK_MAINT	A
	--													join #TEMP_MAT m on a.mat_code = m.MAT_CODE
	--												  WHERE A.MAINT_YMD		BETWEEN @LS_FROM_YYMM AND @AS_COST_APPLY_YMD
	--													 AND A.MAINT_TAG		in ('9','S','C','G','H')		/*9=개별입고, S=세트입고, C=가공입고, G=축관입고, H=5팀입고*/
	--													 AND ((ISNULL(A.INSP_FLAG,'N')	IN ('','N'))	 OR ( ISNULL(A.INSP_FLAG,'N')  in ('S','F') AND A.INSP_PROC_YMD >= '' ))	
	--													 AND A.MAT_CODE = T.MAT_CODE

	--												UNION

	--												SELECT A.MAINT_YMD, A.CUST_CODE
	--													FROM PU_T_STOCK_MAINT_C	A
	--													join #TEMP_MAT m on a.mat_code = m.MAT_CODE
	--												  WHERE A.MAINT_YMD		BETWEEN @LS_FROM_YYMM AND @AS_COST_APPLY_YMD
	--													 AND A.DIVISION		in ('P')								/*P = 수입*/
	--													 AND A.MAT_CODE = T.MAT_CODE
	--												) A
	--										ORDER BY A.MAINT_YMD DESC
	--										),'')
	--  FROM #TEMP_MAT T
	-- WHERE IN_CUST_CODE = ''


	--/*3개월 입고가 없으면 단가마스터에 최종 적용일 업체*/
	--UPDATE T
	--	SET IN_CUST_CODE = ISNULL((SELECT TOP 1 A.CUST_CODE
	--										 FROM PR_M_ITEM_COST A
	--										WHERE A.ITEM_CODE = T.MAT_CODE
	--										  AND COST_TAG = '1'
	--										  AND COST_APPLY_YMD <= @AS_COST_APPLY_YMD
	--										ORDER BY A.COST_APPLY_YMD DESC, A.MAIN_FLAG DESC),'')
	--  FROM #TEMP_MAT T
	-- WHERE IN_CUST_CODE = ''

	
	/*입고분 체크한 거래처의 단가를 가져온다.*/
	UPDATE T
		SET MAT_COST = ISNULL((select top 1 ITEM_COST * case currency when 'USD' then h.us_bas
																		when 'EUR' then h.eur_bas
																		when 'YEN' then h.yen_bas
																		else 1 end
										from PR_M_ITEM_COST 
										where item_code = T.MAT_CODE
										and cust_code = T.IN_CUST_CODE
										and cost_tag  = '1'
										and cost_apply_ymd <= @AS_COST_APPLY_YMD
										order by cost_apply_ymd desc),0)
	  FROM #TEMP_MAT T,
			 #TEMP_EXCHANGE H
	 WHERE IN_CUST_CODE > ''



	/*계산한 단가 및 구매업체를 세팅한다.*/
	UPDATE A
		SET WON_MAT_COST = ISNULL(T.MAT_COST,A.WON_MAT_COST)
			,MAT_IN_CUST_CODE = IIF(T.IN_CUST_CODE>'',T.IN_CUST_CODE,A.MAT_IN_CUST_CODE)
			,MAT_IN_CUST_DESC = (select cust_desc from cm_m_cust where cust_code=IIF(T.IN_CUST_CODE>'',T.IN_CUST_CODE,A.MAT_IN_CUST_CODE))
	  FROM #TEMP_BOM A
	  LEFT MERGE JOIN #TEMP_MAT T ON A.MAT_CODE = T.MAT_CODE


	/*재료비는 최말단 부품에만 발생시킨다.*/
	UPDATE A
		SET JAI_COST = isnull(CASE COST_GUBUN WHEN '3' THEN WON_MAT_COST * ITEM_WEIGHT * USE_QTY ELSE WON_MAT_COST * USE_QTY END,0)
			,JAI_COST_SUB = isnull(CASE WHEN ITEM_WEIGHT > 0 THEN WON_MAT_COST_SUB * ITEM_WEIGHT * USE_QTY ELSE 0 END,0)
			,BOTTOM_FLAG = '1'
	  FROM #TEMP_BOM A
	 WHERE COST_GUBUN > ''
	   AND NOT EXISTS (SELECT 1 FROM #TEMP_BOM WHERE LEVEL_NUM = A.LEVEL_NUM + 1 AND ITEM_CODE = A.MAT_CODE)









	UPDATE A
		SET PIPE_KIND = ISNULL(S.PIPE_KIND,'')
	  FROM #TEMP_BOM A
	  LEFT JOIN pr_m_item_sub S on A.mat_code = s.item_code


	IF object_id('tempdb..#TEMP_PROC_DTL') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_PROC_DTL;
	END

	SELECT A.*
			,B.PROC_CODE, P.R_SORT_SEQ, B.WORK_QTY, B.PROD_UPH, B.COST_GUBUN AS CALC_GUBUN
			,CONVERT(DECIMAL(18,4),CASE B.COST_GUBUN WHEN '3' THEN IIF(B.PROD_UPH * B.WORK_QTY=0, 0, ROUND(L.LABOR_COST / B.PROD_UPH * B.WORK_QTY, 0))
																  WHEN '7' THEN 0																			--세척
																  WHEN '8' THEN A.ITEM_WEIGHT * B.PROD_UPH * B.WORK_QTY						--중량
																  WHEN '9' THEN B.PROD_UPH * B.WORK_QTY											--적용율 (일반관리비, 이윤 등)
																  ELSE 0 END) AS PROD_AMT
	  INTO #TEMP_PROC_DTL
	  FROM #TEMP_BOM A
	  LEFT JOIN (SELECT * FROM CS_T_ITEM_PROC 
					  WHERE ISNULL(PROC_CODE,'') NOT IN ('91', '92', '93')		--91=일반관리비, 92=운반비, 93=이윤
						) B ON A.DB_ITEM_CODE = B.P_ITEM_CODE AND A.MAT_CODE = B.ITEM_CODE
	  LEFT JOIN (SELECT *, ROW_NUMBER() OVER (ORDER BY SORT_SEQ, PROC_CODE) AS R_SORT_SEQ
						FROM CS_M_PROC
					  WHERE ITEM_LGROUP IN (@LS_ITEM_GROUP, 'J')
						 AND PROC_CODE NOT IN ('91','92','93','98','99')) P ON B.PROC_CODE = P.PROC_CODE
	  ,(SELECT TOP 1 A.APPLY_YYYYMM, A.LABOR_COST_TAG        ,A.LABOR_COST FROM CS_M_LABOR_COST_RATE A
		  WHERE A.APPLY_YYYYMM <= CONVERT(VARCHAR,GETDATE(),112)
		  ORDER BY A.APPLY_YYYYMM DESC) L
	 ORDER BY CUM_MAT_CODE, P.SORT_SEQ, B.PROC_CODE
	
	 
	--일반관리비	
	INSERT INTO #TEMP_PROC_DTL
	SELECT A.*
			,B.PROC_CODE, P.R_SORT_SEQ, B.WORK_QTY, B.PROD_UPH, B.COST_GUBUN AS CALC_GUBUN
			,CONVERT(DECIMAL(18,4),B.PROD_UPH) AS PROD_AMT										--적용율 (일반관리비, 운반비, 이윤 등)
	  FROM #TEMP_BOM A
	  JOIN CS_T_ITEM_PROC B ON A.DB_ITEM_CODE = B.P_ITEM_CODE AND A.MAT_CODE = B.ITEM_CODE
	  LEFT JOIN (SELECT *, ROW_NUMBER() OVER (ORDER BY SORT_SEQ, PROC_CODE) AS R_SORT_SEQ
						FROM CS_M_PROC
					  WHERE ITEM_LGROUP IN (@LS_ITEM_GROUP, 'J')
						 AND PROC_CODE NOT IN ('91','92','93','98','99')) P ON B.PROC_CODE = P.PROC_CODE
	  ,(SELECT TOP 1 A.APPLY_YYYYMM, A.LABOR_COST_TAG        ,A.LABOR_COST FROM CS_M_LABOR_COST_RATE A
		  WHERE A.APPLY_YYYYMM <= CONVERT(VARCHAR,GETDATE(),112)
		  ORDER BY A.APPLY_YYYYMM DESC) L
	 WHERE B.PROC_CODE IN ('91', '92', '93')		--91=일반관리비, 92=운반비, 93=이윤
--	   AND B.COST_GUBUN = '9'
	 ORDER BY CUM_MAT_CODE, P.SORT_SEQ, B.PROC_CODE





	IF object_id('tempdb..#TEMP_RESULT') IS NOT NULL
	BEGIN
		DROP TABLE #TEMP_RESULT;
	END


	SELECT CUM_MAT_CODE
			,MAX(LEVEL_NUM) AS C_ITEM_LEVEL
			,MAX(ASSY_ITEM_CODE) AS ITEM_CODE
			,MAX(ITEM_CODE) AS P_ITEM_CODE
			,MAX(MAT_CODE) AS C_ITEM_CODE
			,MAX(ITEM_DESC) AS C_ITEM_DESC
			,MAX(ITEM_SPEC) AS C_ITEM_SPEC
			,MAX(ITEM_DIAM) AS C_ITEM_DIAM
			,MAX(ITEM_THICK) AS C_ITEM_THICK
			,MAX(ITEM_LENGTH) AS C_ITEM_LENGTH
			,MAX(PIPE_KIND) AS C_PIPE_KIND
			,MAX(METAL_GUBUN) AS C_METAL_GUBUN
			,MAX(CUM_USE_QTY) AS CUM_USE_QTY
			,MAX(UPPER_USE_QTY) AS UPPER_USE_QTY
			,MAX(USE_QTY) AS USE_QTY
			,MAX(MAT_IN_CUST_CODE) AS CUST_CODE
			,'' AS WORK_CODE
			,0 AS SALE_COST
			,MAX(JAI_COST) AS PUR_COST
			,0 AS SAGUB_COST
			,MAX(WON_MAT_COST) AS WON_MAT_COST
			,MAX(JAI_COST) AS JAI_COST
			,MAX(JAI_COST_SUB) AS JAI_COST_SUB
			,'' AS CUST_TYPE
			,0 AS ITEM_ST
			,0 AS ITEM_SINGLE_ST
			,MAX(ITEM_WEIGHT) AS TOT_WEIGHT
			,MAX(MAT_IN_CUST_DESC) AS CUST_DESC
			,MAX(ITEM_CLASS) AS ITEM_CLASS
			,MAX(ITEM_LGROUP) AS ITEM_LGROUP
			,MAX(ITEM_SGROUP) AS ITEM_SGROUP
			,MAX(UNIT) AS UNIT
			,MAX(COST_GUBUN) AS COST_GUBUN
			,0 AS LG_COST
			,MAX(IIF(LEVEL_NUM=1,MAT_CODE,'')) AS PART_NO2
			,MAX(IIF(LEVEL_NUM=2,MAT_CODE,'')) AS PART_NO3
			,MAX(IIF(LEVEL_NUM=3,MAT_CODE,'')) AS PART_NO4
			,MAX(IIF(LEVEL_NUM=4,MAT_CODE,'')) AS PART_NO5
			,MAX(IIF(LEVEL_NUM=5,MAT_CODE,'')) AS PART_NO6

			,MAX(IIF(R_SORT_SEQ=1, WORK_QTY, 0)) AS WORK_QTY01
			,MAX(IIF(R_SORT_SEQ=2, WORK_QTY, 0)) AS WORK_QTY02
			,MAX(IIF(R_SORT_SEQ=3, WORK_QTY, 0)) AS WORK_QTY03
			,MAX(IIF(R_SORT_SEQ=4, WORK_QTY, 0)) AS WORK_QTY04
			,MAX(IIF(R_SORT_SEQ=5, WORK_QTY, 0)) AS WORK_QTY05
			,MAX(IIF(R_SORT_SEQ=6, WORK_QTY, 0)) AS WORK_QTY06
			,MAX(IIF(R_SORT_SEQ=7, WORK_QTY, 0)) AS WORK_QTY07
			,MAX(IIF(R_SORT_SEQ=8, WORK_QTY, 0)) AS WORK_QTY08
			,MAX(IIF(R_SORT_SEQ=9, WORK_QTY, 0)) AS WORK_QTY09
			,MAX(IIF(R_SORT_SEQ=10, WORK_QTY, 0)) AS WORK_QTY10
			,MAX(IIF(R_SORT_SEQ=11, WORK_QTY, 0)) AS WORK_QTY11
			,MAX(IIF(R_SORT_SEQ=12, WORK_QTY, 0)) AS WORK_QTY12
			,MAX(IIF(R_SORT_SEQ=13, WORK_QTY, 0)) AS WORK_QTY13
			,MAX(IIF(R_SORT_SEQ=14, WORK_QTY, 0)) AS WORK_QTY14
			,MAX(IIF(R_SORT_SEQ=15, WORK_QTY, 0)) AS WORK_QTY15
			,MAX(IIF(R_SORT_SEQ=16, WORK_QTY, 0)) AS WORK_QTY16
			,MAX(IIF(R_SORT_SEQ=17, WORK_QTY, 0)) AS WORK_QTY17
			,MAX(IIF(R_SORT_SEQ=18, WORK_QTY, 0)) AS WORK_QTY18
			,MAX(IIF(R_SORT_SEQ=19, WORK_QTY, 0)) AS WORK_QTY19
			,MAX(IIF(R_SORT_SEQ=20, WORK_QTY, 0)) AS WORK_QTY20
			,MAX(IIF(R_SORT_SEQ=21, WORK_QTY, 0)) AS WORK_QTY21
			,MAX(IIF(R_SORT_SEQ=22, WORK_QTY, 0)) AS WORK_QTY22
			,MAX(IIF(R_SORT_SEQ=23, WORK_QTY, 0)) AS WORK_QTY23
			,MAX(IIF(R_SORT_SEQ=24, WORK_QTY, 0)) AS WORK_QTY24
			,MAX(IIF(R_SORT_SEQ=25, WORK_QTY, 0)) AS WORK_QTY25
			,MAX(IIF(R_SORT_SEQ=26, WORK_QTY, 0)) AS WORK_QTY26
			,MAX(IIF(R_SORT_SEQ=27, WORK_QTY, 0)) AS WORK_QTY27
			,MAX(IIF(R_SORT_SEQ=28, WORK_QTY, 0)) AS WORK_QTY28
			,MAX(IIF(R_SORT_SEQ=29, WORK_QTY, 0)) AS WORK_QTY29
			,MAX(IIF(R_SORT_SEQ=30, WORK_QTY, 0)) AS WORK_QTY30
			,MAX(IIF(R_SORT_SEQ=31, WORK_QTY, 0)) AS WORK_QTY31
			,MAX(IIF(R_SORT_SEQ=32, WORK_QTY, 0)) AS WORK_QTY32
			,MAX(IIF(R_SORT_SEQ=33, WORK_QTY, 0)) AS WORK_QTY33
			,MAX(IIF(R_SORT_SEQ=34, WORK_QTY, 0)) AS WORK_QTY34
			,MAX(IIF(R_SORT_SEQ=35, WORK_QTY, 0)) AS WORK_QTY35
			,MAX(IIF(R_SORT_SEQ=36, WORK_QTY, 0)) AS WORK_QTY36
			,MAX(IIF(R_SORT_SEQ=37, WORK_QTY, 0)) AS WORK_QTY37
			,MAX(IIF(R_SORT_SEQ=38, WORK_QTY, 0)) AS WORK_QTY38
			,MAX(IIF(R_SORT_SEQ=39, WORK_QTY, 0)) AS WORK_QTY39
			,MAX(IIF(R_SORT_SEQ=40, WORK_QTY, 0)) AS WORK_QTY40
			,MAX(IIF(R_SORT_SEQ=41, WORK_QTY, 0)) AS WORK_QTY41
			,MAX(IIF(R_SORT_SEQ=42, WORK_QTY, 0)) AS WORK_QTY42
			,MAX(IIF(R_SORT_SEQ=43, WORK_QTY, 0)) AS WORK_QTY43
			,MAX(IIF(R_SORT_SEQ=44, WORK_QTY, 0)) AS WORK_QTY44
			,MAX(IIF(R_SORT_SEQ=45, WORK_QTY, 0)) AS WORK_QTY45
			,MAX(IIF(R_SORT_SEQ=46, WORK_QTY, 0)) AS WORK_QTY46
			,MAX(IIF(R_SORT_SEQ=47, WORK_QTY, 0)) AS WORK_QTY47
			,MAX(IIF(R_SORT_SEQ=48, WORK_QTY, 0)) AS WORK_QTY48
			,MAX(IIF(R_SORT_SEQ=49, WORK_QTY, 0)) AS WORK_QTY49
			,MAX(IIF(R_SORT_SEQ=50, WORK_QTY, 0)) AS WORK_QTY50
			,SUM(IIF(R_SORT_SEQ>=1 AND R_SORT_SEQ<=50,WORK_QTY,0)) AS TOT_WORK_QTY

			,MAX(PROC_CODE01) AS PROC_CODE01
			,MAX(PROC_CODE02) AS PROC_CODE02
			,MAX(PROC_CODE03) AS PROC_CODE03
			,MAX(PROC_CODE04) AS PROC_CODE04
			,MAX(PROC_CODE05) AS PROC_CODE05
			,MAX(PROC_CODE06) AS PROC_CODE06
			,MAX(PROC_CODE07) AS PROC_CODE07
			,MAX(PROC_CODE08) AS PROC_CODE08
			,MAX(PROC_CODE09) AS PROC_CODE09
			,MAX(PROC_CODE10) AS PROC_CODE10
			,MAX(PROC_CODE11) AS PROC_CODE11
			,MAX(PROC_CODE12) AS PROC_CODE12
			,MAX(PROC_CODE13) AS PROC_CODE13
			,MAX(PROC_CODE14) AS PROC_CODE14
			,MAX(PROC_CODE15) AS PROC_CODE15
			,MAX(PROC_CODE16) AS PROC_CODE16
			,MAX(PROC_CODE17) AS PROC_CODE17
			,MAX(PROC_CODE18) AS PROC_CODE18
			,MAX(PROC_CODE19) AS PROC_CODE19
			,MAX(PROC_CODE20) AS PROC_CODE20
			,MAX(PROC_CODE21) AS PROC_CODE21
			,MAX(PROC_CODE22) AS PROC_CODE22
			,MAX(PROC_CODE23) AS PROC_CODE23
			,MAX(PROC_CODE24) AS PROC_CODE24
			,MAX(PROC_CODE25) AS PROC_CODE25
			,MAX(PROC_CODE26) AS PROC_CODE26
			,MAX(PROC_CODE27) AS PROC_CODE27
			,MAX(PROC_CODE28) AS PROC_CODE28
			,MAX(PROC_CODE29) AS PROC_CODE29
			,MAX(PROC_CODE30) AS PROC_CODE30
			,MAX(PROC_CODE31) AS PROC_CODE31
			,MAX(PROC_CODE32) AS PROC_CODE32
			,MAX(PROC_CODE33) AS PROC_CODE33
			,MAX(PROC_CODE34) AS PROC_CODE34
			,MAX(PROC_CODE35) AS PROC_CODE35
			,MAX(PROC_CODE36) AS PROC_CODE36
			,MAX(PROC_CODE37) AS PROC_CODE37
			,MAX(PROC_CODE38) AS PROC_CODE38
			,MAX(PROC_CODE39) AS PROC_CODE39
			,MAX(PROC_CODE40) AS PROC_CODE40
			,MAX(PROC_CODE41) AS PROC_CODE41
			,MAX(PROC_CODE42) AS PROC_CODE42
			,MAX(PROC_CODE43) AS PROC_CODE43
			,MAX(PROC_CODE44) AS PROC_CODE44
			,MAX(PROC_CODE45) AS PROC_CODE45
			,MAX(PROC_CODE46) AS PROC_CODE46
			,MAX(PROC_CODE47) AS PROC_CODE47
			,MAX(PROC_CODE48) AS PROC_CODE48
			,MAX(PROC_CODE49) AS PROC_CODE49
			,MAX(PROC_CODE50) AS PROC_CODE50

			,MAX(PROC_DESC01) AS PROC_DESC01
			,MAX(PROC_DESC02) AS PROC_DESC02
			,MAX(PROC_DESC03) AS PROC_DESC03
			,MAX(PROC_DESC04) AS PROC_DESC04
			,MAX(PROC_DESC05) AS PROC_DESC05
			,MAX(PROC_DESC06) AS PROC_DESC06
			,MAX(PROC_DESC07) AS PROC_DESC07
			,MAX(PROC_DESC08) AS PROC_DESC08
			,MAX(PROC_DESC09) AS PROC_DESC09
			,MAX(PROC_DESC10) AS PROC_DESC10
			,MAX(PROC_DESC11) AS PROC_DESC11
			,MAX(PROC_DESC12) AS PROC_DESC12
			,MAX(PROC_DESC13) AS PROC_DESC13
			,MAX(PROC_DESC14) AS PROC_DESC14
			,MAX(PROC_DESC15) AS PROC_DESC15
			,MAX(PROC_DESC16) AS PROC_DESC16
			,MAX(PROC_DESC17) AS PROC_DESC17
			,MAX(PROC_DESC18) AS PROC_DESC18
			,MAX(PROC_DESC19) AS PROC_DESC19
			,MAX(PROC_DESC20) AS PROC_DESC20
			,MAX(PROC_DESC21) AS PROC_DESC21
			,MAX(PROC_DESC22) AS PROC_DESC22
			,MAX(PROC_DESC23) AS PROC_DESC23
			,MAX(PROC_DESC24) AS PROC_DESC24
			,MAX(PROC_DESC25) AS PROC_DESC25
			,MAX(PROC_DESC26) AS PROC_DESC26
			,MAX(PROC_DESC27) AS PROC_DESC27
			,MAX(PROC_DESC28) AS PROC_DESC28
			,MAX(PROC_DESC29) AS PROC_DESC29
			,MAX(PROC_DESC30) AS PROC_DESC30
			,MAX(PROC_DESC31) AS PROC_DESC31
			,MAX(PROC_DESC32) AS PROC_DESC32
			,MAX(PROC_DESC33) AS PROC_DESC33
			,MAX(PROC_DESC34) AS PROC_DESC34
			,MAX(PROC_DESC35) AS PROC_DESC35
			,MAX(PROC_DESC36) AS PROC_DESC36
			,MAX(PROC_DESC37) AS PROC_DESC37
			,MAX(PROC_DESC38) AS PROC_DESC38
			,MAX(PROC_DESC39) AS PROC_DESC39
			,MAX(PROC_DESC40) AS PROC_DESC40
			,MAX(PROC_DESC41) AS PROC_DESC41
			,MAX(PROC_DESC42) AS PROC_DESC42
			,MAX(PROC_DESC43) AS PROC_DESC43
			,MAX(PROC_DESC44) AS PROC_DESC44
			,MAX(PROC_DESC45) AS PROC_DESC45
			,MAX(PROC_DESC46) AS PROC_DESC46
			,MAX(PROC_DESC47) AS PROC_DESC47
			,MAX(PROC_DESC48) AS PROC_DESC48
			,MAX(PROC_DESC49) AS PROC_DESC49
			,MAX(PROC_DESC50) AS PROC_DESC50


			,MAX(IIF(R_SORT_SEQ=1, PROD_AMT, 0)) AS PROD_AMT01
			,MAX(IIF(R_SORT_SEQ=2, PROD_AMT, 0)) AS PROD_AMT02
			,MAX(IIF(R_SORT_SEQ=3, PROD_AMT, 0)) AS PROD_AMT03
			,MAX(IIF(R_SORT_SEQ=4, PROD_AMT, 0)) AS PROD_AMT04
			,MAX(IIF(R_SORT_SEQ=5, PROD_AMT, 0)) AS PROD_AMT05
			,MAX(IIF(R_SORT_SEQ=6, PROD_AMT, 0)) AS PROD_AMT06
			,MAX(IIF(R_SORT_SEQ=7, PROD_AMT, 0)) AS PROD_AMT07
			,MAX(IIF(R_SORT_SEQ=8, PROD_AMT, 0)) AS PROD_AMT08
			,MAX(IIF(R_SORT_SEQ=9, PROD_AMT, 0)) AS PROD_AMT09
			,MAX(IIF(R_SORT_SEQ=10, PROD_AMT, 0)) AS PROD_AMT10
			,MAX(IIF(R_SORT_SEQ=11, PROD_AMT, 0)) AS PROD_AMT11
			,MAX(IIF(R_SORT_SEQ=12, PROD_AMT, 0)) AS PROD_AMT12
			,MAX(IIF(R_SORT_SEQ=13, PROD_AMT, 0)) AS PROD_AMT13
			,MAX(IIF(R_SORT_SEQ=14, PROD_AMT, 0)) AS PROD_AMT14
			,MAX(IIF(R_SORT_SEQ=15, PROD_AMT, 0)) AS PROD_AMT15
			,MAX(IIF(R_SORT_SEQ=16, PROD_AMT, 0)) AS PROD_AMT16
			,MAX(IIF(R_SORT_SEQ=17, PROD_AMT, 0)) AS PROD_AMT17
			,MAX(IIF(R_SORT_SEQ=18, PROD_AMT, 0)) AS PROD_AMT18
			,MAX(IIF(R_SORT_SEQ=19, PROD_AMT, 0)) AS PROD_AMT19
			,MAX(IIF(R_SORT_SEQ=20, PROD_AMT, 0)) AS PROD_AMT20
			,MAX(IIF(R_SORT_SEQ=21, PROD_AMT, 0)) AS PROD_AMT21
			,MAX(IIF(R_SORT_SEQ=22, PROD_AMT, 0)) AS PROD_AMT22
			,MAX(IIF(R_SORT_SEQ=23, PROD_AMT, 0)) AS PROD_AMT23
			,MAX(IIF(R_SORT_SEQ=24, PROD_AMT, 0)) AS PROD_AMT24
			,MAX(IIF(R_SORT_SEQ=25, PROD_AMT, 0)) AS PROD_AMT25
			,MAX(IIF(R_SORT_SEQ=26, PROD_AMT, 0)) AS PROD_AMT26
			,MAX(IIF(R_SORT_SEQ=27, PROD_AMT, 0)) AS PROD_AMT27
			,MAX(IIF(R_SORT_SEQ=28, PROD_AMT, 0)) AS PROD_AMT28
			,MAX(IIF(R_SORT_SEQ=29, PROD_AMT, 0)) AS PROD_AMT29
			,MAX(IIF(R_SORT_SEQ=30, PROD_AMT, 0)) AS PROD_AMT30
			,MAX(IIF(R_SORT_SEQ=31, PROD_AMT, 0)) AS PROD_AMT31
			,MAX(IIF(R_SORT_SEQ=32, PROD_AMT, 0)) AS PROD_AMT32
			,MAX(IIF(R_SORT_SEQ=33, PROD_AMT, 0)) AS PROD_AMT33
			,MAX(IIF(R_SORT_SEQ=34, PROD_AMT, 0)) AS PROD_AMT34
			,MAX(IIF(R_SORT_SEQ=35, PROD_AMT, 0)) AS PROD_AMT35
			,MAX(IIF(R_SORT_SEQ=36, PROD_AMT, 0)) AS PROD_AMT36
			,MAX(IIF(R_SORT_SEQ=37, PROD_AMT, 0)) AS PROD_AMT37
			,MAX(IIF(R_SORT_SEQ=38, PROD_AMT, 0)) AS PROD_AMT38
			,MAX(IIF(R_SORT_SEQ=39, PROD_AMT, 0)) AS PROD_AMT39
			,MAX(IIF(R_SORT_SEQ=40, PROD_AMT, 0)) AS PROD_AMT40
			,MAX(IIF(R_SORT_SEQ=41, PROD_AMT, 0)) AS PROD_AMT41
			,MAX(IIF(R_SORT_SEQ=42, PROD_AMT, 0)) AS PROD_AMT42
			,MAX(IIF(R_SORT_SEQ=43, PROD_AMT, 0)) AS PROD_AMT43
			,MAX(IIF(R_SORT_SEQ=44, PROD_AMT, 0)) AS PROD_AMT44
			,MAX(IIF(R_SORT_SEQ=45, PROD_AMT, 0)) AS PROD_AMT45
			,MAX(IIF(R_SORT_SEQ=46, PROD_AMT, 0)) AS PROD_AMT46
			,MAX(IIF(R_SORT_SEQ=47, PROD_AMT, 0)) AS PROD_AMT47
			,MAX(IIF(R_SORT_SEQ=48, PROD_AMT, 0)) AS PROD_AMT48
			,MAX(IIF(R_SORT_SEQ=49, PROD_AMT, 0)) AS PROD_AMT49
			,MAX(IIF(R_SORT_SEQ=50, PROD_AMT, 0)) AS PROD_AMT50

			,CONVERT(DECIMAL(18,4),SUM(IIF(R_SORT_SEQ>=1 AND R_SORT_SEQ<=50,PROD_AMT,0))) * MAX(IIF(UNIT='EA',USE_QTY,1)) AS GAGONG_AMT
			,CONVERT(DECIMAL(18,4),MAX(IIF(PROC_CODE='91', PROD_AMT, 0))) AS ILBAN_RATE
			,CONVERT(DECIMAL(18,4),MAX(IIF(PROC_CODE='93', PROD_AMT, 0))) AS PROFIT_RATE
			,CONVERT(DECIMAL(18,4),0) AS ILBAN_AMT
			,CONVERT(DECIMAL(18,4),MAX(IIF(PROC_CODE='92', PROD_AMT, 0))) AS UNBAN_AMT
			,CONVERT(DECIMAL(18,4),0) AS PROFIT_AMT
			,CONVERT(DECIMAL(18,4),0) AS LME_CHA_AMT
			,CONVERT(DECIMAL(18,4),0) AS TOT_AMT
			,'0' AS SUM_FLAG
			,MAX(A.LME_EXCEPT_FLAG) AS LME_EXCEPT_FLAG
			,MAX(A.BOTTOM_FLAG) AS BOTTOM_FLAG
	  INTO #TEMP_RESULT
	  FROM #TEMP_PROC_DTL A
			,(SELECT  MAX(IIF(R_SORT_SEQ=1, PROC_CODE, '')) AS PROC_CODE01
						,MAX(IIF(R_SORT_SEQ=2, PROC_CODE, '')) AS PROC_CODE02
						,MAX(IIF(R_SORT_SEQ=3, PROC_CODE, '')) AS PROC_CODE03
						,MAX(IIF(R_SORT_SEQ=4, PROC_CODE, '')) AS PROC_CODE04
						,MAX(IIF(R_SORT_SEQ=5, PROC_CODE, '')) AS PROC_CODE05
						,MAX(IIF(R_SORT_SEQ=6, PROC_CODE, '')) AS PROC_CODE06
						,MAX(IIF(R_SORT_SEQ=7, PROC_CODE, '')) AS PROC_CODE07
						,MAX(IIF(R_SORT_SEQ=8, PROC_CODE, '')) AS PROC_CODE08
						,MAX(IIF(R_SORT_SEQ=9, PROC_CODE, '')) AS PROC_CODE09
						,MAX(IIF(R_SORT_SEQ=10, PROC_CODE, '')) AS PROC_CODE10
						,MAX(IIF(R_SORT_SEQ=11, PROC_CODE, '')) AS PROC_CODE11
						,MAX(IIF(R_SORT_SEQ=12, PROC_CODE, '')) AS PROC_CODE12
						,MAX(IIF(R_SORT_SEQ=13, PROC_CODE, '')) AS PROC_CODE13
						,MAX(IIF(R_SORT_SEQ=14, PROC_CODE, '')) AS PROC_CODE14
						,MAX(IIF(R_SORT_SEQ=15, PROC_CODE, '')) AS PROC_CODE15
						,MAX(IIF(R_SORT_SEQ=16, PROC_CODE, '')) AS PROC_CODE16
						,MAX(IIF(R_SORT_SEQ=17, PROC_CODE, '')) AS PROC_CODE17
						,MAX(IIF(R_SORT_SEQ=18, PROC_CODE, '')) AS PROC_CODE18
						,MAX(IIF(R_SORT_SEQ=19, PROC_CODE, '')) AS PROC_CODE19
						,MAX(IIF(R_SORT_SEQ=20, PROC_CODE, '')) AS PROC_CODE20
						,MAX(IIF(R_SORT_SEQ=21, PROC_CODE, '')) AS PROC_CODE21
						,MAX(IIF(R_SORT_SEQ=22, PROC_CODE, '')) AS PROC_CODE22
						,MAX(IIF(R_SORT_SEQ=23, PROC_CODE, '')) AS PROC_CODE23
						,MAX(IIF(R_SORT_SEQ=24, PROC_CODE, '')) AS PROC_CODE24
						,MAX(IIF(R_SORT_SEQ=25, PROC_CODE, '')) AS PROC_CODE25
						,MAX(IIF(R_SORT_SEQ=26, PROC_CODE, '')) AS PROC_CODE26
						,MAX(IIF(R_SORT_SEQ=27, PROC_CODE, '')) AS PROC_CODE27
						,MAX(IIF(R_SORT_SEQ=28, PROC_CODE, '')) AS PROC_CODE28
						,MAX(IIF(R_SORT_SEQ=29, PROC_CODE, '')) AS PROC_CODE29
						,MAX(IIF(R_SORT_SEQ=30, PROC_CODE, '')) AS PROC_CODE30
						,MAX(IIF(R_SORT_SEQ=31, PROC_CODE, '')) AS PROC_CODE31
						,MAX(IIF(R_SORT_SEQ=32, PROC_CODE, '')) AS PROC_CODE32
						,MAX(IIF(R_SORT_SEQ=33, PROC_CODE, '')) AS PROC_CODE33
						,MAX(IIF(R_SORT_SEQ=34, PROC_CODE, '')) AS PROC_CODE34
						,MAX(IIF(R_SORT_SEQ=35, PROC_CODE, '')) AS PROC_CODE35
						,MAX(IIF(R_SORT_SEQ=36, PROC_CODE, '')) AS PROC_CODE36
						,MAX(IIF(R_SORT_SEQ=37, PROC_CODE, '')) AS PROC_CODE37
						,MAX(IIF(R_SORT_SEQ=38, PROC_CODE, '')) AS PROC_CODE38
						,MAX(IIF(R_SORT_SEQ=39, PROC_CODE, '')) AS PROC_CODE39
						,MAX(IIF(R_SORT_SEQ=40, PROC_CODE, '')) AS PROC_CODE40
						,MAX(IIF(R_SORT_SEQ=41, PROC_CODE, '')) AS PROC_CODE41
						,MAX(IIF(R_SORT_SEQ=42, PROC_CODE, '')) AS PROC_CODE42
						,MAX(IIF(R_SORT_SEQ=43, PROC_CODE, '')) AS PROC_CODE43
						,MAX(IIF(R_SORT_SEQ=44, PROC_CODE, '')) AS PROC_CODE44
						,MAX(IIF(R_SORT_SEQ=45, PROC_CODE, '')) AS PROC_CODE45
						,MAX(IIF(R_SORT_SEQ=46, PROC_CODE, '')) AS PROC_CODE46
						,MAX(IIF(R_SORT_SEQ=47, PROC_CODE, '')) AS PROC_CODE47
						,MAX(IIF(R_SORT_SEQ=48, PROC_CODE, '')) AS PROC_CODE48
						,MAX(IIF(R_SORT_SEQ=49, PROC_CODE, '')) AS PROC_CODE49
						,MAX(IIF(R_SORT_SEQ=50, PROC_CODE, '')) AS PROC_CODE50

						,MAX(IIF(R_SORT_SEQ=1, PROC_DESC, '')) AS PROC_DESC01
						,MAX(IIF(R_SORT_SEQ=2, PROC_DESC, '')) AS PROC_DESC02
						,MAX(IIF(R_SORT_SEQ=3, PROC_DESC, '')) AS PROC_DESC03
						,MAX(IIF(R_SORT_SEQ=4, PROC_DESC, '')) AS PROC_DESC04
						,MAX(IIF(R_SORT_SEQ=5, PROC_DESC, '')) AS PROC_DESC05
						,MAX(IIF(R_SORT_SEQ=6, PROC_DESC, '')) AS PROC_DESC06
						,MAX(IIF(R_SORT_SEQ=7, PROC_DESC, '')) AS PROC_DESC07
						,MAX(IIF(R_SORT_SEQ=8, PROC_DESC, '')) AS PROC_DESC08
						,MAX(IIF(R_SORT_SEQ=9, PROC_DESC, '')) AS PROC_DESC09
						,MAX(IIF(R_SORT_SEQ=10, PROC_DESC, '')) AS PROC_DESC10
						,MAX(IIF(R_SORT_SEQ=11, PROC_DESC, '')) AS PROC_DESC11
						,MAX(IIF(R_SORT_SEQ=12, PROC_DESC, '')) AS PROC_DESC12
						,MAX(IIF(R_SORT_SEQ=13, PROC_DESC, '')) AS PROC_DESC13
						,MAX(IIF(R_SORT_SEQ=14, PROC_DESC, '')) AS PROC_DESC14
						,MAX(IIF(R_SORT_SEQ=15, PROC_DESC, '')) AS PROC_DESC15
						,MAX(IIF(R_SORT_SEQ=16, PROC_DESC, '')) AS PROC_DESC16
						,MAX(IIF(R_SORT_SEQ=17, PROC_DESC, '')) AS PROC_DESC17
						,MAX(IIF(R_SORT_SEQ=18, PROC_DESC, '')) AS PROC_DESC18
						,MAX(IIF(R_SORT_SEQ=19, PROC_DESC, '')) AS PROC_DESC19
						,MAX(IIF(R_SORT_SEQ=20, PROC_DESC, '')) AS PROC_DESC20
						,MAX(IIF(R_SORT_SEQ=21, PROC_DESC, '')) AS PROC_DESC21
						,MAX(IIF(R_SORT_SEQ=22, PROC_DESC, '')) AS PROC_DESC22
						,MAX(IIF(R_SORT_SEQ=23, PROC_DESC, '')) AS PROC_DESC23
						,MAX(IIF(R_SORT_SEQ=24, PROC_DESC, '')) AS PROC_DESC24
						,MAX(IIF(R_SORT_SEQ=25, PROC_DESC, '')) AS PROC_DESC25
						,MAX(IIF(R_SORT_SEQ=26, PROC_DESC, '')) AS PROC_DESC26
						,MAX(IIF(R_SORT_SEQ=27, PROC_DESC, '')) AS PROC_DESC27
						,MAX(IIF(R_SORT_SEQ=28, PROC_DESC, '')) AS PROC_DESC28
						,MAX(IIF(R_SORT_SEQ=29, PROC_DESC, '')) AS PROC_DESC29
						,MAX(IIF(R_SORT_SEQ=30, PROC_DESC, '')) AS PROC_DESC30
						,MAX(IIF(R_SORT_SEQ=31, PROC_DESC, '')) AS PROC_DESC31
						,MAX(IIF(R_SORT_SEQ=32, PROC_DESC, '')) AS PROC_DESC32
						,MAX(IIF(R_SORT_SEQ=33, PROC_DESC, '')) AS PROC_DESC33
						,MAX(IIF(R_SORT_SEQ=34, PROC_DESC, '')) AS PROC_DESC34
						,MAX(IIF(R_SORT_SEQ=35, PROC_DESC, '')) AS PROC_DESC35
						,MAX(IIF(R_SORT_SEQ=36, PROC_DESC, '')) AS PROC_DESC36
						,MAX(IIF(R_SORT_SEQ=37, PROC_DESC, '')) AS PROC_DESC37
						,MAX(IIF(R_SORT_SEQ=38, PROC_DESC, '')) AS PROC_DESC38
						,MAX(IIF(R_SORT_SEQ=39, PROC_DESC, '')) AS PROC_DESC39
						,MAX(IIF(R_SORT_SEQ=40, PROC_DESC, '')) AS PROC_DESC40
						,MAX(IIF(R_SORT_SEQ=41, PROC_DESC, '')) AS PROC_DESC41
						,MAX(IIF(R_SORT_SEQ=42, PROC_DESC, '')) AS PROC_DESC42
						,MAX(IIF(R_SORT_SEQ=43, PROC_DESC, '')) AS PROC_DESC43
						,MAX(IIF(R_SORT_SEQ=44, PROC_DESC, '')) AS PROC_DESC44
						,MAX(IIF(R_SORT_SEQ=45, PROC_DESC, '')) AS PROC_DESC45
						,MAX(IIF(R_SORT_SEQ=46, PROC_DESC, '')) AS PROC_DESC46
						,MAX(IIF(R_SORT_SEQ=47, PROC_DESC, '')) AS PROC_DESC47
						,MAX(IIF(R_SORT_SEQ=48, PROC_DESC, '')) AS PROC_DESC48
						,MAX(IIF(R_SORT_SEQ=49, PROC_DESC, '')) AS PROC_DESC49
						,MAX(IIF(R_SORT_SEQ=50, PROC_DESC, '')) AS PROC_DESC50
				FROM (SELECT *, ROW_NUMBER() OVER (ORDER BY SORT_SEQ, PROC_CODE) AS R_SORT_SEQ
						  FROM CS_M_PROC
						 WHERE ITEM_LGROUP IN (@LS_ITEM_GROUP, 'J')
						   AND PROC_CODE NOT IN ('91','92','93','98','99')) B) B
	 GROUP BY CUM_MAT_CODE




	/*계산결과 상위레벨로 SUM하여 올리기*/	
	BEGIN
		/*LEVEL MAX 구하기*/
		SELECT @LI_LEVEL_MAX = ISNULL(MAX(C_ITEM_LEVEL),0)
		  FROM #TEMP_RESULT


		SET @LI_LEVEL = @LI_LEVEL_MAX
		WHILE @LI_LEVEL > 0
		BEGIN
			/*합계 계산*/
			UPDATE #TEMP_RESULT
				SET TOT_AMT = JAI_COST + (GAGONG_AMT + ILBAN_AMT + UNBAN_AMT + PROFIT_AMT)
			 WHERE C_ITEM_LEVEL = @LI_LEVEL

			SET @LI_LEVEL = @LI_LEVEL - 1

			UPDATE A
				SET JAI_COST = (SELECT ISNULL(SUM(JAI_COST),0) FROM #TEMP_RESULT
									  WHERE C_ITEM_LEVEL = @LI_LEVEL + 1
										AND CUM_MAT_CODE LIKE A.CUM_MAT_CODE + '%' ) * IIF(UNIT='EA',USE_QTY,1)
					,GAGONG_AMT = GAGONG_AMT + (SELECT ISNULL(SUM(GAGONG_AMT),0) FROM #TEMP_RESULT
														  WHERE C_ITEM_LEVEL = @LI_LEVEL + 1
															AND CUM_MAT_CODE LIKE A.CUM_MAT_CODE + '%' ) * IIF(UNIT='EA',USE_QTY,1)
			  FROM #TEMP_RESULT A
			 WHERE A.C_ITEM_LEVEL = @LI_LEVEL
			   AND EXISTS (SELECT 1 FROM #TEMP_RESULT 
								 WHERE C_ITEM_LEVEL = @LI_LEVEL + 1
									AND CUM_MAT_CODE LIKE A.CUM_MAT_CODE + '%' )
		END
	END



	/*일반관리비 계산 = (재료비 + 가공비 * 7%*/
	UPDATE #TEMP_RESULT
		SET ILBAN_AMT = ROUND(ILBAN_RATE * (JAI_COST + GAGONG_AMT), 0)
	 WHERE ILBAN_RATE > 0


	/*이윤 계산 = (가공비 + 일반관리비 * 8%*/
	UPDATE #TEMP_RESULT
		SET PROFIT_AMT = ROUND(PROFIT_RATE * (GAGONG_AMT + ILBAN_AMT), 0)
	 WHERE PROFIT_RATE > 0

	--강제삭제. 목선화 사원 요청. 25/06/18
	/*
	/*LME차를 계산한다.*/
	UPDATE #TEMP_RESULT
		SET LME_CHA_AMT = JAI_COST_SUB
	 WHERE COST_GUBUN = '2'
	   AND LME_EXCEPT_FLAG <> '1'
	   AND TOT_WEIGHT > 0
	*/

	/*계산결과 상위레벨로 SUM하여 올리기*/	
	BEGIN
		/*LEVEL MAX 구하기*/
		SELECT @LI_LEVEL_MAX = ISNULL(MAX(C_ITEM_LEVEL),0)
		  FROM #TEMP_RESULT


		SET @LI_LEVEL = @LI_LEVEL_MAX
		WHILE @LI_LEVEL > 0
		BEGIN
			/*합계 계산*/
			UPDATE #TEMP_RESULT
				SET TOT_AMT = JAI_COST + (GAGONG_AMT + ILBAN_AMT + UNBAN_AMT + PROFIT_AMT)
			 WHERE C_ITEM_LEVEL = @LI_LEVEL

			SET @LI_LEVEL = @LI_LEVEL - 1

			UPDATE A
				SET ILBAN_AMT = ILBAN_AMT + (SELECT ISNULL(SUM(ILBAN_AMT),0) FROM #TEMP_RESULT
														WHERE C_ITEM_LEVEL = @LI_LEVEL + 1
														  AND CUM_MAT_CODE LIKE A.CUM_MAT_CODE + '%' ) * IIF(UNIT='EA',USE_QTY,1)
					,UNBAN_AMT = UNBAN_AMT + (SELECT ISNULL(SUM(UNBAN_AMT),0) FROM #TEMP_RESULT
													   WHERE C_ITEM_LEVEL = @LI_LEVEL + 1
														  AND CUM_MAT_CODE LIKE A.CUM_MAT_CODE + '%' ) * IIF(UNIT='EA',USE_QTY,1)
					,PROFIT_AMT = PROFIT_AMT + (SELECT ISNULL(SUM(PROFIT_AMT),0) FROM #TEMP_RESULT
														  WHERE C_ITEM_LEVEL = @LI_LEVEL + 1
															AND CUM_MAT_CODE LIKE A.CUM_MAT_CODE + '%' ) * IIF(UNIT='EA',USE_QTY,1)
			  FROM #TEMP_RESULT A
			 WHERE A.C_ITEM_LEVEL = @LI_LEVEL
			   AND EXISTS (SELECT 1 FROM #TEMP_RESULT 
								 WHERE C_ITEM_LEVEL = @LI_LEVEL + 1
									AND CUM_MAT_CODE LIKE A.CUM_MAT_CODE + '%' )
		END
	END

	

	/*LG단가*/
	UPDATE #TEMP_RESULT
	   SET TOT_AMT = JAI_COST + (GAGONG_AMT + ILBAN_AMT + UNBAN_AMT + PROFIT_AMT),
		　　LG_COST = ISNULL((SELECT TOP 1 ITEM_COST FROM PR_M_ITEM_COST WHERE ITEM_CODE = A.ITEM_CODE
																   AND CUST_CODE IN ('1010', '1020', '1030')
																   AND COST_APPLY_YMD <= @AS_COST_APPLY_YMD
																 ORDER BY COST_APPLY_YMD DESC),0)
	  FROM #TEMP_RESULT A
	 WHERE C_ITEM_LEVEL = 0




	/*최종결과*/
	SELECT A.*
			,SUM(IIF(BOTTOM_FLAG='1' AND A.ITEM_SGROUP IN ('110','120','130','220'),JAI_COST,0) * A.UPPER_USE_QTY) OVER (PARTITION BY '')	AS WON_JAI_AMT		/*원자재 재료비*/
			,SUM(IIF(BOTTOM_FLAG='1' AND A.ITEM_SGROUP IN ('230','910'),JAI_COST,0) * A.UPPER_USE_QTY) OVER (PARTITION BY '')	AS BU_JAI_AMT		/*부자재 재료비*/
			,SUM(IIF(BOTTOM_FLAG='1' AND A.ITEM_SGROUP IN ('310'),JAI_COST,0) * A.UPPER_USE_QTY) OVER (PARTITION BY '')			AS SA_JAI_AMT		/*사급 재료비*/
			,M.SILVER_SOLDER
	  FROM #TEMP_RESULT A
	  JOIN PR_M_ITEM M ON A.C_ITEM_CODE = M.ITEM_CODE
	 ORDER BY CUM_MAT_CODE

END
