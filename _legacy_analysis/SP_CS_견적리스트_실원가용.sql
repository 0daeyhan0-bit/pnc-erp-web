










CREATE  PROC [dbo].[SP_CS_견적리스트_실원가용]
		@as_cost_apply_ymd		varchar(6),
		@as_item_code				varchar(20)					
AS
BEGIN
	SET NOCOUNT ON
	SET ANSI_WARNINGS OFF










	BEGIN
		WITH CTE_BOM(prior_item_code, item_code, work_code, in_cust_code, level_num, mat_code, mat_work_code, mat_in_cust_code, parent_in_cust_code, use_qty, cum_use_qty, item_cost, cum_in_cust_code, cum_mat_code,
							item_desc, item_spec, item_diam, item_thick, item_length, metal_gubun, item_weight,item_cost2,lg_weight)
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
						convert(int,1) as use_qty, 
						convert(int,1) as cum_use_qty,
						case when rtrim(c.work_code) > '' or rtrim(c.in_cust_code) in ('','P80000','P92379') then 0 else dbo.f_get_item_cost5(c.item_code, c.in_cust_code, '1', @as_cost_apply_ymd) end as item_cost,
						convert(int, case when rtrim(c.work_code)>'' or rtrim(c.in_cust_code) in ('', 'P80000','P92379') then 0 else 1 end) as cum_in_cust_code,
						convert(varchar(200),'') as cum_mat_code,
						c.item_desc,
						c.item_spec,
						c.item_diam,
						c.item_thick,
						c.item_length,
						c.metal_gubun,
						case when rtrim(c.work_code)>'' or rtrim(c.in_cust_code) in ('','P80000') then 0 else dbo.f_get_weight2(c.item_code,1, c.in_cust_code) end  as item_weight, --동소요량 계산

						case when rtrim(c.work_code) > '' or rtrim(c.in_cust_code) in ('','P80000','P92379') then 0 
							  when rtrim(c.in_cust_code) in ('Z99999') then dbo.f_get_item_proc_cost(c.item_code)*c.item_weight --가공단가 계산 (가공적용가 * 동소요량)
							  else dbo.f_get_item_cost5(c.item_code, c.in_cust_code, '1', convert(varchar,getdate(),12)) end as item_cost2 ,
						c.lg_weight

				 from pr_m_item c
				where c.ITEM_CODE	= @as_item_code
		    
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
						convert(int,b1.use_qty) as use_qty,
						convert(int,case when cb.cum_use_qty = 0 then 0
												else CONVERT(NUMERIC(18,5), cb.cum_use_qty*b1.use_qty) end) as cum_use_qty,		
						case when rtrim(m.work_code)>'' or rtrim(m.in_cust_code) in ('') or cb.cum_in_cust_code > 0 then 0 else dbo.f_get_item_cost5(b1.mat_code, m.in_cust_code, '1', @as_cost_apply_ymd) end as item_cost,

						cb.cum_in_cust_code + cb.cum_in_cust_code * 1 + case when rtrim(m.work_code)>'' or rtrim(m.in_cust_code) in ('', 'P80000','P92379') then 0 else 1 end as cum_in_cust_code,
						convert(varchar(200),cb.cum_mat_code + substring(b1.mat_code + space(30), 1, 30)) as cum_mat_code,
						m.ITEM_DESC,
						m.ITEM_SPEC,
						m.ITEM_DIAM,
						m.ITEM_THICK,
						m.ITEM_LENGTH,
						m.metal_gubun,
						case when rtrim(m.work_code)>'' or rtrim(m.in_cust_code) in ('','P80000','P20413','P96243','P27017') or cb.cum_in_cust_code > 0 then 0 else dbo.f_get_weight2(b1.mat_code,1, m.in_cust_code) end as item_weight, --동소요량 계산
		   
						case when rtrim(m.work_code)>'' or rtrim(m.in_cust_code) in ('') or cb.cum_in_cust_code > 0 then 0 
							  when rtrim(m.in_cust_code) in ('z99999') then dbo.f_get_item_proc_cost(b1.mat_code)*m.item_weight
							 else dbo.f_get_item_cost5(b1.mat_code, m.in_cust_code, '1', convert(varchar,getdate(),12)) end as item_cost2, --가공단가 계산(가공단가*동소요량)
						c.lg_weight
			
				from CTE_BOM cb
				join pr_m_item_bom b1			 on cb.mat_code		= b1.item_code
				join pr_m_item c 					 on b1.item_code	= c.item_code
				join pr_m_item m 					 on b1.mat_code 	= m.item_code
				where cb.level_num < 10
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
				 t.USE_QTY,   
				 t.USE_QTY			  as use_qty2,   
				 t.cum_use_qty		  as cum_use_qty,   
				 t.mat_in_cust_code as cust_code,
				 t.mat_work_code	  as work_code,
				 s.rack_no,
				 t.cum_mat_code	  as a1_item_code,
				 ''					  as a2_item_code,
				 ''					  as a3_item_code,
				 ''					  as a4_item_code,
				 ''					  as a5_item_code,
				 isnull((select top 1 A.ITEM_COST
							  from PR_M_ITEM_COST	A
							 where A.CUST_CODE			= 'P18769'
								and A.ITEM_CODE			= s.item_code
								and A.COST_TAG			in ('R','C') 
								and a.cost_apply_ymd	<= convert(varchar,getdate(),12)
							order by a.cost_apply_ymd desc),0) as sale_cost,
				t.item_cost as pur_cost,
				(case when cu.cust_type = 'L' then dbo.f_get_item_cost5(t.mat_CODE, t.mat_in_cust_code, '1', @as_cost_apply_ymd) else 0 end) as sagub_cost, 
				(case when cu.cust_type = 'L' then 'L' else '' end) as cust_type,
				dbo.f_get_item_assy_sumol_st(t.mat_code,t.mat_work_code) as item_st,
				dbo.f_get_item_single_st(t.mat_code) as item_single_st,
				t.item_weight as tot_weight,
				isnull(ss.EXCEPT_FLAG,'0') as EXCEPT_FLAG,
				isnull(ss.SAGUB_FLAG,'0') as SAGUB_FLAG,
				isnull((case when t.mat_work_code>'' then (select work_desc from pr_m_work where work_code=t.mat_work_code)
														 else (select cust_desc from cm_m_cust where cust_code=t.mat_in_cust_code) end),'000') as cust_desc,
				(case when t.mat_work_code='' and t.mat_in_cust_code > 'Z99990' or t.mat_in_cust_code = 'P27017'
						then isnull(round((SELECT top 1 lme * exch_us from pr_m_base_cost where yymm < convert(varchar,getdate(),12) order by yymm desc) * t.item_weight / 1000,0),0)
						else 0 end) as copper_cost,   --// (LME * 환율 * 중량) / 1000 
				dbo.f_get_processing_assy(t.mat_code) as ASSY_PROCESSING_COST,   
				dbo.f_get_welding(t.mat_code) as WELDING_COST,

				(case when t.mat_work_code <> '' then isnull(round((select top 1 hour_pay from pr_m_base_cost where yymm < convert(varchar,getdate(),12) order by yymm desc) ,0),0) else 0 end) as hour_pay,
				(select rec_rate from pr_m_work where work_code=t.mat_work_code) AS rec_rate,
				(select prod_number from pr_m_work where work_code=t.mat_work_code) as prod_number,
				t.item_cost2 as item_cost2,
				t.lg_weight,
				m.item_class,
				m.item_lgroup,
				m.item_sgroup
		  from CTE_BOM t
		  join pr_m_item m 			 on t.mat_code 	= m.item_code
		  left join cm_m_cust cu	 on m.in_cust_code = cu.cust_code
											 and m.work_code	= ''
		  left join pr_m_item_sub s on s.item_code=t.mat_code
		  left join PR_M_ITEM_BOM_sub ss on ss.item_code=t.item_code
													and ss.mat_code=t.mat_code

	END


	--EXEC [dbo].[SP_PR_CREATE_PLAN_가공공정_파트별_생산계획계산_마지막공정_투입시간기준]  '210903', '210905', 'ABDE', 'P1'


END
