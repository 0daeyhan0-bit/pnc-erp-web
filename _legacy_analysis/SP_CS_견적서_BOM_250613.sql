







-- =============================================
-- Author:		<Author,,Name>
-- Create date: <Create Date,,>
-- Description:	<Description,,>
-- =============================================
CREATE PROCEDURE [dbo].[SP_CS_견적서(BOM)_250613]
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

	DECLARE	@LS_FROM_YYMM			VARCHAR(4)
	DECLARE	@LI_LEVEL				INT

	SET @LS_FROM_YYMM = SUBSTRING(CONVERT(VARCHAR,DATEADD(MONTH, -2, CONVERT(DATETIME,@AS_COST_APPLY_YMD,12)),12),1,4)

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
		WITH CTE_BOM(prior_item_code, item_code, work_code, in_cust_code, level_num, mat_code, mat_work_code, mat_in_cust_code, parent_in_cust_code, use_qty, upper_cum_use_qty, cum_use_qty, 
							item_cost, cum_in_cust_code, cum_mat_code,
							item_desc, item_spec, item_diam, item_thick, item_length, metal_gubun, item_weight, item_cost2, lg_weight, bom_seq, cs_calc_except_flag, lme_except_flag, update_user_id, update_datetime)
		AS (
			/*앵커멤버-생산계획*/
				select
						c.item_code as prior_item_code,
						c.item_code as item_code,
						c.work_code,
						c.in_cust_code,
						convert(int,0)	as level_num,
						c.item_code 	as mat_code,
						c.work_code 	as mat_work_code,
						c.in_cust_code as mat_in_cust_code,
						convert(varchar(10),'')	as parent_in_cust_code,
						convert(numeric(18,4),1) as use_qty, 
						convert(numeric(18,4),1) as upper_cum_use_qty,
						convert(numeric(18,4),1) as cum_use_qty,
						0 as item_cost,
						convert(int, case when rtrim(c.work_code)>'' or rtrim(c.in_cust_code) in ('', 'P80000','P92379') then 0 else 1 end) as cum_in_cust_code,
						convert(varchar(200),'') as cum_mat_code,
						c.item_desc,
						c.item_spec,
						c.item_diam,
						c.item_thick,
						c.item_length,
						c.metal_gubun,
						dbo.f_get_weight3(c.item_code) as item_weight,		--중량 계산

						0 as item_cost2 ,
						c.lg_weight,
						convert(int, 0) as bom_seq,
						'0' as cs_calc_except_flag,
						'0' as lme_except_flag,
						convert(varchar(20),'') as update_user_id,
						convert(datetime, null) as update_datetime
				 from pr_m_item c
				where c.ITEM_CODE	= @AS_ITEM_CODE
		    
				union all
 
				/* 재귀멤버 - BOM 하위추출 */
			  select cb.prior_item_code,
						b1.item_code,
						c.work_code,
						c.in_cust_code,
						convert(int, cb.level_num + 1) as level_num,
						b1.mat_code,
						m.work_code				as mat_work_code,
						m.in_cust_code			as mat_in_cust_code,
						convert(varchar(10),cb.mat_in_cust_code) as parent_in_cust_code,
						convert(numeric(18,4),b1.use_qty) as use_qty,
						convert(numeric(18,4),cb.cum_use_qty) as upper_cum_use_qty,
						convert(numeric(18,4),case when cb.cum_use_qty = 0 then 0
												else CONVERT(NUMERIC(18,4), cb.cum_use_qty * b1.use_qty) end) as cum_use_qty,		
						0 as item_cost,

						cb.cum_in_cust_code + cb.cum_in_cust_code * 1 + case when rtrim(m.work_code)>'' or rtrim(m.in_cust_code) in ('', 'P80000','P92379') then 0 else 1 end as cum_in_cust_code,
						convert(varchar(200),cb.cum_mat_code + right('0' + convert(varchar(2), iif(b1.bom_seq>0,b1.bom_seq,99)),2) + ' ' + substring(b1.mat_code + space(30), 1, 30)) as cum_mat_code,
						m.ITEM_DESC,
						m.ITEM_SPEC,
						m.ITEM_DIAM,
						m.ITEM_THICK,
						m.ITEM_LENGTH,
						m.metal_gubun,
						dbo.f_get_weight3(b1.mat_code) as item_weight,		--동소요량 계산
		   
						0 as item_cost2,		--가공단가 계산(가공단가*동소요량)
						c.lg_weight,
						convert(int, b1.bom_seq) as bom_seq,
						b1.cs_calc_except_flag,
						b1.lme_except_flag,
						convert(varchar(20),b1.update_user_id) as update_user_id,
						convert(datetime, b1.update_datetime) as update_datetime
			
				from CTE_BOM cb
				join CS_M_ITEM_BOM b1			 on cb.mat_code	= b1.item_code
				join pr_m_item c 					 on b1.item_code	= c.item_code
				join pr_m_item m 					 on b1.mat_code 	= m.item_code
			)	

		select level_num			  as c_item_level,   
				 t.prior_item_code  as item_code,   
				 t.ITEM_CODE		  as P_ITEM_CODE,   
				 t.mat_CODE			  as C_ITEM_CODE,   
				 t.ITEM_DESC		  as c_item_desc,   
				 t.ITEM_SPEC		  as c_item_spec,   
				 t.ITEM_DIAM		  as c_item_diam,   
				 t.ITEM_THICK		  as c_item_thick,   
				 t.ITEM_LENGTH		  as c_item_length,   
				 s.pipe_kind		  as c_pipe_kind,   
				 t.metal_gubun		  as c_metal_gubun,   
				 t.use_qty,   
				 t.use_qty			  as use_qty2,   
				 t.upper_cum_use_qty	as upper_cum_use_qty,   
				 t.cum_use_qty		  as cum_use_qty,   
				 t.mat_in_cust_code as mat_in_cust_code,
				 t.mat_work_code	  as mat_work_code,
				 s.rack_no,
				 t.cum_mat_code	  as a1_item_code,
				 ''					  as a2_item_code,
				 ''					  as a3_item_code,
				 ''					  as a4_item_code,
				 ''					  as a5_item_code,
				 0 as sale_cost,
				t.item_cost as pur_cost,
				0 as sagub_cost, 
				(case when cu.cust_type = 'L' then 'L' else '' end) as cust_type,
				0 as item_st,
				0 as item_single_st,
				t.item_weight as tot_weight,
				isnull(ss.EXCEPT_FLAG,'0') as EXCEPT_FLAG,
				isnull(ss.SAGUB_FLAG,'0') as SAGUB_FLAG,
				isnull((case when t.mat_work_code>'' then (select work_desc from pr_m_work where work_code=t.mat_work_code)
														 else (select cust_desc from cm_m_cust where cust_code=t.mat_in_cust_code) end),'000') as MAT_IN_CUST_DESC,
				0 as copper_cost,
				0 as ASSY_PROCESSING_COST,   
				0 as WELDING_COST,

				(case when t.mat_work_code <> '' then isnull(round((select top 1 hour_pay from pr_m_base_cost where yymm < convert(varchar,getdate(),12) order by yymm desc) ,0),0) else 0 end) as hour_pay,
				(select rec_rate from pr_m_work where work_code=t.mat_work_code) AS rec_rate,
				(select prod_number from pr_m_work where work_code=t.mat_work_code) as prod_number,
				t.item_cost2 as item_cost2,
				t.lg_weight,
				m.item_class,
				m.item_lgroup,
				m.item_sgroup,
				m.unit,
				m.cost_gubun,
				m.item_status,
				m.make_type,
				m.silver_solder,
				m.update_user_id as item_update_user_id,
				m.update_datetime as item_update_datetime,
				round(mc.tot_cost,0) as tot_cost,
				0  as item_cost3,
				t.bom_seq,
				t.cs_calc_except_flag,
				t.lme_except_flag,
				convert(INT, iif(level_num = 1, 700, 400)) as bold_num,
				convert(varchar(1), iif(level_num = 1, '0', '3')) as color_tag,
				t.update_user_id,
				t.update_datetime
		  INTO #TEMP_BOM
		  from CTE_BOM t
		  join pr_m_item m 			 on t.mat_code 	= m.item_code
		  left join cm_m_cust cu	 on m.in_cust_code = cu.cust_code
											 and m.work_code	= ''
		  left join pr_m_item_sub s on s.item_code=t.mat_code
		  left join CS_M_ITEM_BOM_sub ss on ss.item_code=t.item_code
													and ss.mat_code=t.mat_code
		  left join cs_m_meterial_cost mc on t.metal_gubun = mc.metal_gubun
													and substring(mc.apply_yyyymm, 3, 4) like substring(@as_cost_apply_ymd, 1,4)
													and t.item_diam = mc.item_diam
													and t.item_thick = mc.item_thick
		  where t.level_num <= 10
	END



	/*사용자재추출*/
	--SELECT DISTINCT C_ITEM_CODE AS MAT_CODE, 0 AS MAT_COST, IIF(MAT_WORK_CODE='P2','2228',MAT_IN_CUST_CODE) AS IN_CUST_CODE
	SELECT DISTINCT C_ITEM_CODE AS MAT_CODE, 0 AS MAT_COST, MAT_IN_CUST_CODE AS IN_CUST_CODE
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

	
	/*체크한 거래처의 단가를 가져온다.*/
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
		SET ITEM_COST3 = T.MAT_COST
			,MAT_IN_CUST_CODE = T.IN_CUST_CODE
			,MAT_IN_CUST_DESC = ISNULL((select cust_desc from cm_m_cust where cust_code=T.IN_CUST_CODE),'')
	  FROM #TEMP_BOM A
	  INNER MERGE JOIN #TEMP_MAT T ON A.C_ITEM_CODE = T.MAT_CODE





	/*최종결과*/
	SELECT *
	  FROM #TEMP_BOM

END
