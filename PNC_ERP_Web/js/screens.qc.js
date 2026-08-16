/* ===== PNC ERP screens.qc.js — 품질 SCREEN (app.js 분할, 순수이동) ===== */

/* ===== 품질 반성회의록 CRUD (nx.meeting ← cm_user_meeting_1) — 비용 자동계산 ===== */
SCREEN.meeting=(host)=>{
  const API=API_BASE;
  const st={rows:[],cnt:0,q:'',from:'',to:'',form:null,sel:new Set(),msg:''};
  const A=[1,2,3,4,5];
  const calcPay=(f)=>{const mc=parseInt(f.member_count),du=parseInt(f.duration_min);
    return (!isNaN(mc)&&!isNaN(du))?Math.round((mc+1)*du*358.3):(parseInt(f.pay_amount)||0);};
  const load=async()=>{
    const qs=new URLSearchParams({q:st.q,from_ymd:st.from,to_ymd:st.to,limit:300});
    try{const r=await fetch(`${API}/api/meeting/list?${qs}`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    render();
  };
  const render=()=>{
    const editing=st.form!==null, f=st.form||{};
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('meeting'):true;
    const pay=editing?calcPay(f):0;
    host.innerHTML=`
     <div class="page-title">📝 품질 반성회의록 <span style="font-size:12px;color:var(--muted);font-weight:400">회의 기록·조치사항 · nx.meeting</span></div>
     <div class="page-sub">회의 기록·조치사항 관리. <b>비용 = (참석인원+1) × 소요시간(분) × 358.3</b> 자동계산. 원천 <code>cm_user_meeting_1</code>.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">회의일자</label><input class="inp" id="mt-from" value="${esc(st.from)}" placeholder="YYYYMM" style="width:90px"> ~ <input class="inp" id="mt-to" value="${esc(st.to)}" placeholder="YYYYMM" style="width:90px">
       <label class="tl">검색</label><input class="inp" id="mt-q" value="${esc(st.q)}" placeholder="제목/작성자/참석자" style="width:170px">
       <button class="btn" id="mt-search">🔍 조회</button>
       ${ed?`<button class="btn" id="mt-new" style="background:#1c7c3a;color:#fff">➕ 신규</button>
       <button class="btn" id="mt-del">🗑 선택삭제</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${editing?`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:760px;max-width:97vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>회의록 ${f.meeting_id?'수정':'신규'}</b><span id="mt-x" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
           <div style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:6px 8px;align-items:center;font-size:12px">
             <label style="color:#33507d;font-weight:600;text-align:right">회의일자</label><input class="inp mf" data-k="meeting_ymd" value="${esc(f.meeting_ymd||'')}" placeholder="YYYYMMDD">
             <label style="color:#33507d;font-weight:600;text-align:right">유형</label><input class="inp mf" data-k="meeting_type" value="${esc(f.meeting_type||'')}" placeholder="반성/아침조회 등">
             <label style="color:#33507d;font-weight:600;text-align:right">제목<span style="color:#c0392b">*</span></label><input class="inp mf" data-k="subject" value="${esc(f.subject||'')}" style="grid-column:span 3">
             <label style="color:#33507d;font-weight:600;text-align:right">작성자</label><input class="inp mf" data-k="organizer" value="${esc(f.organizer||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">참석자</label><input class="inp mf" data-k="member" value="${esc(f.member||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">참석인원</label><input class="inp mf" type="number" data-k="member_count" value="${esc(f.member_count||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">소요시간(분)</label><input class="inp mf" type="number" data-k="duration_min" value="${esc(f.duration_min||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">비용(자동)</label><input class="inp" id="mt-pay" value="${won(pay)}" readonly style="background:#eef2f7;grid-column:span 3">
           </div>
           <div style="margin-top:10px"><label style="color:#33507d;font-weight:600;font-size:12px">회의 내용</label>
             <textarea class="inp mf" data-k="note" style="width:100%;min-height:70px;box-sizing:border-box">${esc(f.note||'')}</textarea></div>
           <div style="margin-top:6px"><label style="color:#33507d;font-weight:600;font-size:12px">회의 내용 2</label>
             <textarea class="inp mf" data-k="note2" style="width:100%;min-height:50px;box-sizing:border-box">${esc(f.note2||'')}</textarea></div>
           <div style="margin-top:10px;font-weight:600;color:#33507d;font-size:12px">조치사항</div>
           <table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr style="color:#8aa0bd">
             <th style="width:24px">#</th><th style="text-align:left">조치내용</th><th style="width:110px">담당자</th><th style="width:100px">기한</th></tr></thead>
             <tbody>${A.map(n=>`<tr>
               <td class="center mut">${n}</td>
               <td><input class="inp mf" data-k="action${n}_desc" value="${esc(f['action'+n+'_desc']||'')}" style="width:100%;box-sizing:border-box"></td>
               <td><input class="inp mf" data-k="action${n}_person" value="${esc(f['action'+n+'_person']||'')}" style="width:100%;box-sizing:border-box"></td>
               <td><input class="inp mf" data-k="action${n}_due" value="${esc(f['action'+n+'_due']||'')}" style="width:100%;box-sizing:border-box"></td></tr>`).join('')}</tbody></table>
         </div>
         <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
           <span style="color:#c0392b;font-size:11px">* 제목은 필수. 비용은 인원·시간 입력 시 자동계산됩니다.</span>
           <span><button class="btn" id="mt-save" style="background:#1b6ec2;color:#fff">💾 저장</button> <button class="btn" id="mt-cancel">닫기</button></span></div>
       </div></div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr><th style="width:26px"></th>
        <th>회의일자</th><th>유형</th><th>제목</th><th>작성자</th><th>참석자</th><th class="num">인원</th><th class="num">시간(분)</th><th class="num">비용</th><th style="width:46px">작업</th></tr></thead>
      <tbody>${st.rows.length?st.rows.map((r,i)=>`<tr>
        <td class="center">${ed?`<input type="checkbox" class="mt-chk" data-id="${r.meeting_id}" ${st.sel.has(r.meeting_id)?'checked':''}>`:''}</td>
        <td>${esc(r.meeting_ymd)}</td><td>${esc(r.meeting_type)}</td>
        <td class="cap" title="${esc(r.subject)}" style="max-width:220px;overflow:hidden;text-overflow:ellipsis">${esc(r.subject)}</td>
        <td>${esc(r.organizer)}</td><td class="cap" title="${esc(r.member)}" style="max-width:120px;overflow:hidden;text-overflow:ellipsis">${esc(r.member)}</td>
        <td class="num">${esc(r.member_count)}</td><td class="num">${esc(r.duration_min)}</td><td class="num">${won(r.pay_amount||0)}</td>
        <td class="center">${ed?`<button class="btn mt-edit" data-idx="${i}" style="padding:1px 6px;font-size:10px">수정</button>`:''}</td></tr>`).join(''):`<tr><td colspan="10" class="empty">조회 결과 없음${ed?' (➕신규로 등록)':''}</td></tr>`}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#mt-search').onclick=()=>{st.q=g('#mt-q').value;st.from=g('#mt-from').value;st.to=g('#mt-to').value;load();};
    g('#mt-q').onkeyup=e=>{if(e.key==='Enter')g('#mt-search').click();};
    if(ed){
      g('#mt-new').onclick=()=>{st.form={meeting_ymd:'',subject:''};render();};
      g('#mt-del').onclick=()=>del([...st.sel]);
      host.querySelectorAll('.mt-chk').forEach(ch=>ch.onclick=()=>{const id=+ch.dataset.id;ch.checked?st.sel.add(id):st.sel.delete(id);});
      host.querySelectorAll('.mt-edit').forEach(b=>b.onclick=()=>{st.form=Object.assign({},st.rows[+b.dataset.idx]);render();});
    }
    attachResizers(host);
    if(editing){
      g('#mt-cancel').onclick=g('#mt-x').onclick=()=>{st.form=null;render();};
      g('#mt-save').onclick=save;
      host.querySelectorAll('.mf').forEach(el=>{el.oninput=()=>{st.form[el.dataset.k]=el.value;
        if(el.dataset.k==='member_count'||el.dataset.k==='duration_min'){const pe=g('#mt-pay');if(pe)pe.value=won(calcPay(st.form));}};});
    }
  };
  const save=async()=>{
    const f=st.form;
    if(!String(f.subject||'').trim()){alert('회의 제목은 필수입니다');return;}
    try{const r=await fetch(`${API}/api/meeting/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(f)});
      const j=await r.json();
      if(r.ok&&j.ok){st.msg=(j.mode==='insert'?'✅ 등록완료':'✅ 수정완료')+` (비용 ${won(j.pay_amount||0)})`;st.form=null;await load();}
      else alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 오류: '+e);}
  };
  const del=async(ids)=>{if(!ids.length){alert('삭제할 행을 체크하세요');return;}
    if(!confirm(ids.length+'건을 삭제하시겠습니까?'))return;
    try{const r=await fetch(`${API}/api/meeting/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})});
      const j=await r.json();st.msg='🗑 '+j.deleted+'건 삭제완료';st.sel.clear();await load();}
    catch(e){alert('삭제 오류: '+e);}
  };
  load();
};
SCREEN.qcerror=(c)=>{
  wrShell(c,{sid:'qcerror',
    title:`🚫 품질불량관리 <span style="font-size:12px;color:var(--muted);font-weight:400">공정 불량 발생·조치 이력(등록·수정·삭제)</span>`,
    sub:`레거시 <code>w_qa_input_020</code> 전체 컬럼(옆스크롤). 원장=<code>nx.qc_error</code>(레거시 이관완료) · ➕신규·수정은 팝업 · 코드→이름`,
    nxOnly:true,
    cfg:{
      listEp:'/api/qc/error/list', saveEp:'/api/qc/error/save', delEp:'/api/qc/error/delete', days:30,
      dateLabel:'불량기간', filters:qcFilters, buildQS:F=>qcQS(F,'nx'),
      sum:d=>`불량수량합 <b>${_wnf(d.sum_err)}</b>`,
      cols:qcCols, modal:true, modalTitle:'불량관리 Maint', modalWidth:600, allReq:true,
      form:[
        {k:'error_ymd',label:'불량일자',type:'date',required:1,width:140},
        {k:'error_tag',label:'불량구분',type:'select',opts:QC_TAG,width:110},
        {k:'division',label:'사업부',type:'select',opts:QC_BIZ,width:80},
        {k:'cust_line',label:'고객사라인',type:'auto',optKind:'line',width:140},
        {k:'pg_reg',label:'전산등록',type:'select',opts:QC_PGREG,width:100},
        {k:'item_code',label:'P/No',required:1,search:1,width:160},
        {k:'work_code',label:'작업처',type:'select',opts:QC_WORK,width:90},
        {k:'proc_code',label:'생산파트',type:'auto',optKind:'part',width:160},{k:'mach_code',label:'생산설비',type:'auto',optKind:'mach',width:160},
        {k:'partner_code',label:'협력사',type:'auto',optKind:'partner',width:160},
        {k:'inspector',label:'검사자',width:100},{k:'error_member',label:'원인자',width:100},
        {k:'error_item1',label:'불량항목1',width:100},{k:'error_item2',label:'불량항목2',width:100},{k:'error_item3',label:'불량항목3',width:120},
        {k:'error_desc',label:'불량내용',width:260},{k:'color',label:'색깔',type:'select',opts:QC_COLOR,width:80},
        {k:'lot_qty',label:'생산수량(Lot)',type:'num',width:100},{k:'error_qty',label:'불량수량',type:'num',width:90},{k:'real_error_qty',label:'실발생불량',type:'num',width:90},
        {k:'scrap_weight',label:'스크랩중량(kg)',type:'num',width:100},
        {k:'error_cause',label:'원인',width:180},{k:'progress_stats',label:'진행상황',width:140},{k:'charge_name',label:'담당',width:80},
        {k:'water_flag',label:'수몰여부',type:'select',opts:QC_YN,width:90},
        {k:'reinsp_flag',label:'재검사여부',type:'select',opts:QC_YN,width:90},
        {k:'finish_flag',label:'완료여부',type:'select',opts:QC_YN,width:90},
      ],
      newRow:F=>({id:null,error_ymd:F.to,error_tag:'8',division:'',cust_line:'',pg_reg:'',item_code:'',work_code:'P2',proc_code:'',mach_code:'',partner_code:'',inspector:'',error_member:'',error_item1:'',error_item2:'',error_item3:'',error_desc:'',color:'1',lot_qty:'',error_qty:'',real_error_qty:'',scrap_weight:'',error_cause:'',progress_stats:'',charge_name:'',water_flag:'0',reinsp_flag:'0',finish_flag:'0'}),
      fromRow:r=>({id:r.ID,error_ymd:_y6(r.error_ymd),error_tag:r.tag,division:r.division,cust_line:r.cust_line,cust_line__nm:r.cust_line,pg_reg:r.pg_reg,item_code:r.item_code,work_code:r.work_code,proc_code:r.proc_code,proc_code__nm:r.part_nm,mach_code:r.mach_code,mach_code__nm:r.mach_nm,partner_code:r.partner_code,partner_code__nm:r.partner_nm,inspector:r.inspector,error_member:r.error_member,error_item1:r.ei1,error_item2:r.ei2,error_item3:r.ei3,error_desc:r.error_desc,color:r.color||'1',lot_qty:r.lot_qty,error_qty:r.error_qty,real_error_qty:r.real_qty,scrap_weight:r.scrap_weight,error_cause:r.error_cause,progress_stats:r.progress,charge_name:r.charge,water_flag:r.water_flag?'1':'0',reinsp_flag:r.reinsp_flag?'1':'0',finish_flag:r.finish_flag?'1':'0'}),
      toBody:f=>{const b={...f,user:'웹사용자'};Object.keys(b).forEach(k=>{if(k.endsWith('__nm'))delete b[k];});return b;},
    }
  });
};
SCREEN.qcspec=(c)=>{
  const scols=[
    {h:'접수일',cls:'center',fmt:r=>_d8disp(r.rev_ymd)},
    {h:'순번',k:'rev_no',cls:'num'},
    {h:'ECO',k:'eco'},
    {h:'PART NO',si:1,fmt:r=>`<b>${esc(r.item_code)}</b>`},
    {h:'품명',k:'nm',cap:1,title:'nm'},
    {h:'시방기호',k:'mark',cls:'center'},
    {h:'시방내용',k:'rdesc',cap:1,title:'rdesc'},
    {h:'발행일',cls:'center',fmt:r=>_d8disp(r.issue)},
    {h:'부서',k:'dept',cls:'center'},{h:'담당',k:'charge',cls:'center'},
    {h:'적용일',cls:'center',fmt:r=>_d8disp(r.apply_ymd)},
    {h:'적용구분',cls:'center',fmt:r=>_atypeNm(r.atype)},
    {h:'적용재고',k:'apply_stock',cap:1,title:'apply_stock'},
    {h:'도면파일',cap:1,title:'drawing',fmt:r=>r.drawing?`<span class="sp-file" data-ry="${esc(r.rev_ymd)}" data-rn="${esc(r.rev_no)}" data-kind="도면" style="cursor:pointer;color:#1c47a0;text-decoration:underline">📎 ${esc(r.drawing)}</span>`:''},
    {h:'시방서파일',cap:1,title:'specs',fmt:r=>r.specs?`<span class="sp-file" data-ry="${esc(r.rev_ymd)}" data-rn="${esc(r.rev_no)}" data-kind="시방서" style="cursor:pointer;color:#1c47a0;text-decoration:underline">📎 ${esc(r.specs)}</span>`:''},
    {h:'원가변경',cls:'center',fmt:r=>r.cost_f?'✔':''},
    {h:'LG원가변경',cls:'center',fmt:r=>r.lg_cost_f?'✔':''},
    {h:'BOM변경',cls:'center',fmt:r=>r.bom_f?'✔':''},
    {h:'비고',k:'remarks',cap:1,title:'remarks'},
  ];
  const HFORM=[
    {k:'rev_ymd',label:'접수일',type:'date'},{k:'rev_no',label:'순번',type:'num'},
    {k:'eco_no',label:'ECO번호'},{k:'item_code',label:'PART NO',type:'auto',optKind:'item',showCode:1},
    {k:'rev_mark',label:'시방기호'},{k:'issue_ymd',label:'발행일',type:'date'},
    {k:'dept_name',label:'부서'},{k:'charge_name',label:'담당'},{k:'apply_ymd',label:'적용일',type:'date'},
    {k:'apply_type',label:'적용구분',type:'select',opts:[{v:'1',t:'즉시적용'},{v:'2',t:'재고소진후'},{v:'3',t:'지정일'}]},
    {k:'cost_change',label:'원가변경',type:'select',opts:QC_YN},{k:'bom_change',label:'BOM변경',type:'select',opts:QC_YN},
    {k:'rev_desc',label:'시방내용',w:320},{k:'remarks',label:'비고',optional:1,w:220},
  ];
  /* 좌:시방목록 + 우:적용대상 마스터-디테일. opt={src,editable} */
  const specView=(body,opt)=>{
    opt=opt||{}; const editable=!!opt.editable&&((typeof PERM!=='undefined')?PERM.canEdit('qcspec'):true), src=opt.src||'legacy';   // 수정권한 게이트(규칙#16)
    const API=API_BASE;
    const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
    const T=new Date();
    let F={from:iso(new Date(T.getTime()-(editable?400:60)*864e5)),to:iso(T),item:''};
    let data={rows:[],cnt:0}, sel=null, ap={rows:[]}, loading=false, aload=false, msg='', form=null;
    const load=async()=>{loading=true;sel=null;ap={rows:[]};draw();
      try{const r=await fetch(`${API}/api/qc/spec/list?`+new URLSearchParams({from_ymd:F.from,to_ymd:F.to,item:F.item,src}));data=await r.json();msg='';}
      catch(e){msg='백엔드 연결 실패';data={rows:[],cnt:0};}
      loading=false;draw();};
    const pick=async(r)=>{sel=r;aload=true;draw();
      try{const q=new URLSearchParams({rev_ymd:r.rev_ymd,rev_no:r.rev_no,item:r.item_code,src:r.src||src});ap=await fetch(`${API}/api/qc/spec/apply?${q}`).then(x=>x.json());}catch(e){ap={rows:[]};}
      aload=false;draw();};
    const newForm=()=>({id:null,rev_ymd:iso(T).replace(/-/g,'').slice(2),rev_no:'',eco_no:'',item_code:'',item_code__nm:'',rev_mark:'',issue_ymd:'',dept_name:'품질',charge_name:'',apply_ymd:'',apply_type:'1',cost_change:'0',bom_change:'0',rev_desc:'',remarks:''});
    const editForm=(r)=>({id:r.ID,_ry:r.rev_ymd,_rn:r.rev_no,rev_ymd:_d8disp(r.rev_ymd).replace(/\//g,''),rev_no:r.rev_no,eco_no:r.eco,item_code:r.item_code,item_code__nm:r.item_code,rev_mark:r.mark,issue_ymd:_d8disp(r.issue).replace(/\//g,''),dept_name:r.dept,charge_name:r.charge,apply_ymd:_d8disp(r.apply_ymd).replace(/\//g,''),apply_type:r.atype||'1',cost_change:r.cost_f?'1':'0',bom_change:r.bom_f?'1':'0',rev_desc:r.rdesc,remarks:r.remarks||''});
    const saveHdr=async()=>{
      for(const f of HFORM){if(!f.optional&&!String(form[f.k]??'').trim()){alert(f.label+' 은(는) 필수입니다');return;}}
      const b={...form,user:'웹사용자'};Object.keys(b).forEach(k=>{if(k.endsWith('__nm'))delete b[k];});
      try{const r=await fetch(`${API}/api/qc/spec/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});const j=await r.json();if(j.ok){form=null;await load();}else alert('저장 실패: '+JSON.stringify(j));}catch(e){alert('저장 오류: '+e);}};
    const delHdr=async(r)=>{if(!r||!r.ID){alert('nx 등록건만 삭제 가능');return;}if(!confirm('이 시방을 삭제할까요?'))return;
      await fetch(`${API}/api/qc/spec/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[r.ID]})});await load();};
    const addApply=async(mode)=>{if(!sel||!sel.ID){alert('nx 시방을 먼저 선택하세요');return;}
      const b={rev_ymd:sel.rev_ymd,rev_no:sel.rev_no,user:'웹사용자'};
      if(mode==='base'){const bs=prompt('베이스 품번 입력 (예: AJR301337)');if(!bs)return;const t=prompt('접미 끝번호 (기본 09)','9');b.base=bs.trim();b.from=1;b.to=parseInt(t||'9')||9;}
      else{const it=prompt('추가할 품번');if(!it)return;b.items=[it.trim()];}
      try{const j=await(await fetch(`${API}/api/qc/spec/apply/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json();if(j.ok)pick(sel);else alert('추가 실패: '+JSON.stringify(j));}catch(e){alert(e);}};
    const delApply=async(it)=>{if(!sel)return;if(!confirm(it+' 적용대상 삭제?'))return;
      await fetch(`${API}/api/qc/spec/apply/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rev_ymd:sel.rev_ymd,rev_no:sel.rev_no,items:[it]})});pick(sel);};
    const mfld=(f)=>{const v=form[f.k]??'';
      if(f.type==='select')return `<select class="inp" data-fk="${f.k}" style="min-width:80px;width:auto">${(f.opts||[]).map(o=>`<option value="${esc(o.v)}"${String(o.v)===String(v)?' selected':''}>${esc(o.t)}</option>`).join('')}</select>`;
      if(f.type==='auto'){const nm=form[f.k+'__nm']??'';return `<span style="position:relative;display:inline-block"><input class="inp sp-ac" data-fk="${f.k}" data-kind="${f.optKind}" data-showcode="${f.showCode?1:''}" autocomplete="off" value="${esc(f.showCode?v:(nm||v))}" placeholder="입력하세요" style="width:170px"><div class="wr-acbox" id="sp-acb-${f.k}" style="display:none;position:absolute;left:0;top:100%;z-index:130;min-width:100%;max-height:200px;overflow:auto;background:#fff;border:1px solid #b9d3ef;border-radius:6px;box-shadow:0 6px 16px rgba(0,0,0,.16)"></div></span>`;}
      return `<input class="inp" data-fk="${f.k}" type="${f.type==='date'?'date':'text'}" value="${esc(v)}" placeholder="${f.type==='date'?'':'입력하세요'}" style="width:${f.w||150}px">`;};
    const draw=()=>{
      body.innerHTML=`
       <div class="toolbar">
         <label class="tl">접수기간</label><input class="inp" type="date" id="sp-from" value="${F.from}"> ~ <input class="inp" type="date" id="sp-to" value="${F.to}">
         <label class="tl">PART NO</label><input class="inp" id="sp-item" value="${esc(F.item)}" placeholder="입력하세요" style="width:130px">
         <button class="btn" id="sp-go">🔍 조회</button>
         ${editable?`<button class="btn" id="sp-new" style="background:#1c7c3a;color:#fff">➕ 신규</button>`:''}
         <div class="spacer"></div><span class="rowcount">${won(data.cnt||0)}건</span>
       </div>
       ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
       <div style="display:flex;gap:12px;align-items:flex-start">
        <div style="flex:1.8;min-width:0">
         <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
          <table class="tbl" style="font-size:11px"><thead><tr>${scols.map(cl=>`<th class="${cl.cls||''}">${cl.h}</th>`).join('')}${editable?'<th class="center">편집</th>':''}</tr></thead>
          <tbody>${loading?spinRow(scols.length+(editable?1:0)):((data.rows&&data.rows.length)?data.rows.map((r,i)=>`<tr class="sp-row${sel===r?' sel':''}" data-i="${i}" style="cursor:pointer">${scols.map(cl=>`<td class="${cl.cls||''}" ${cl.si?`data-si="${esc(r.item_code)}"`:''} ${cl.title?`title="${esc(r[cl.title]||'')}"`:''} ${cl.cap?'style="max-width:150px;overflow:hidden;text-overflow:ellipsis"':''}>${cl.fmt?cl.fmt(r):esc(r[cl.k]??'')}</td>`).join('')}${editable?`<td class="center" style="white-space:nowrap">${r.ID?`<button class="btn sp-edit" data-i="${i}" style="padding:0 4px;font-size:10px;line-height:1.5">수정</button><button class="btn sp-del" data-i="${i}" style="padding:0 4px;font-size:10px;line-height:1.5;margin-left:2px">삭제</button>`:'<span style="color:#b7c2d4;font-size:10px">라이브</span>'}</td>`:''}</tr>`).join(''):`<tr><td colspan="${scols.length+(editable?1:0)}" class="empty">조회 결과 없음</td></tr>`)}</tbody></table>
         </div>
        </div>
        <div style="flex:1;min-width:0">
         <div class="summary-bar"><div class="s-item"><b>적용대상</b>${sel?` · ${esc(sel.item_code)} 시방기호<b> ${esc(sel.mark)}</b> (적용 ${_d8disp(sel.apply_ymd)})`:''}</div>${(editable&&sel&&sel.ID)?`<div style="margin-left:auto"><button class="btn" id="ap-base" style="padding:1px 6px">＋베이스확장</button> <button class="btn" id="ap-one" style="padding:1px 6px">＋품번</button></div>`:''}</div>
         <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
          <table class="tbl" style="font-size:11px"><thead><tr><th>PART NO</th><th class="center">적용</th><th class="center">최초입고일</th><th class="center">최초생산일</th><th class="center">최초출하일</th>${(editable&&sel&&sel.ID)?'<th></th>':''}</tr></thead>
          <tbody>${!sel?`<tr><td colspan="6" class="empty">← 좌측 시방을 선택하세요</td></tr>`:(aload?spinRow(6):((ap.rows&&ap.rows.length)?ap.rows.map(a=>`<tr><td data-si="${esc(a.item)}"><b>${esc(a.item)}</b></td><td class="center">${a.apply_flag?'✔':''}</td><td class="center">${_d8disp(a.input_ymd)||'-'}</td><td class="center">${_d8disp(a.prod_ymd)||'-'}</td><td class="center">${_d8disp(a.output_ymd)||'-'}</td>${(editable&&sel&&sel.ID)?`<td class="center"><span class="ap-del" data-it="${esc(a.item)}" style="cursor:pointer;color:#c0392b">✖</span></td>`:''}</tr>`).join(''):`<tr><td colspan="6" class="empty">적용대상 없음${(editable&&sel&&sel.ID)?' (＋베이스확장으로 추가)':''}</td></tr>`))}</tbody></table>
         </div>
         <div class="page-sub" style="margin-top:4px;color:#8aa0bd">※ 최초입고/생산/출하일 = 시스템 자동집계 예정(원본 0% 입력)</div>
        </div>
       </div>
       ${form!==null?`<div style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:26px 10px">
          <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:560px;max-width:96vw">
           <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0"><b>시방변경 ${form.id?'수정':'신규'}</b><span id="hf-x" style="cursor:pointer;font-size:17px">✕</span></div>
           <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto"><table style="border-collapse:collapse;width:100%">${HFORM.map(f=>`<tr><td style="padding:5px 10px 5px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;width:96px">${f.label}${f.optional?'':'<span style="color:#c0392b">*</span>'}</td><td style="padding:4px 0">${mfld(f)}</td></tr>`).join('')}</table>
             ${form.id?`<div style="margin-top:10px;border-top:1px solid #eef;padding-top:8px">
               <div style="font-weight:600;color:#33507d;font-size:12px;margin-bottom:6px">📎 첨부파일 <span style="color:#8aa0bd;font-weight:400">(도면/시방서 · nx 등록건)</span></div>
               <div id="hf-files" style="font-size:12px">불러오는 중...</div>
               <div style="display:flex;gap:6px;align-items:center;margin-top:8px;flex-wrap:wrap;font-size:12px">
                 <span style="color:#33507d;font-weight:600">도면</span><input type="file" id="hf-dwg" style="width:150px"><button class="btn" id="hf-dwg-up" style="padding:2px 8px">⬆</button>
                 <span style="color:#33507d;font-weight:600;margin-left:6px">시방서</span><input type="file" id="hf-spec" style="width:150px"><button class="btn" id="hf-spec-up" style="padding:2px 8px">⬆</button>
               </div></div>`:''}
           </div>
           <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center"><span style="color:#c0392b;font-size:11px">* 필수항목 제외품목들을 사용해보고 전산담당에게 알려주세요.</span><span><button class="btn" id="hf-save" style="background:#1b6ec2;color:#fff">💾 저장</button> <button class="btn" id="hf-cancel">닫기</button></span></div>
          </div></div>`:''}
       <style>.sp-row.sel{background:#e8f0ff}.sp-row:hover{background:#eef4ff}</style>`;
      const g=id=>body.querySelector(id);
      g('#sp-go').onclick=()=>{F.from=g('#sp-from').value;F.to=g('#sp-to').value;F.item=g('#sp-item').value;load();};
      g('#sp-item').onkeyup=e=>{if(e.key==='Enter')g('#sp-go').click();};
      body.querySelectorAll('.sp-row').forEach(el=>el.onclick=(e)=>{if(e.target.closest('.sp-edit,.sp-del,.sp-file'))return;pick(data.rows[+el.dataset.i]);});
      body.querySelectorAll('.sp-file').forEach(el=>el.onclick=async(e)=>{e.stopPropagation();
        const ry=el.dataset.ry,rn=el.dataset.rn,want=el.dataset.kind;
        try{const j=await(await fetch(`${API}/api/qc/spec/files?rev_ymd=${encodeURIComponent(ry)}&rev_no=${encodeURIComponent(rn)}`)).json();
          const f=(j.rows||[]).find(x=>x.kind===want);
          if(f)window.open(`${API}/api/doc/download?src=${encodeURIComponent(f.src)}&key=${encodeURIComponent(f.key)}`,'_blank');
          else alert(want+' 첨부 파일이 없습니다.');}catch(err){alert('다운로드 오류: '+err);}});
      if(editable){
        const nb=g('#sp-new'); if(nb)nb.onclick=()=>{form=newForm();draw();};
        body.querySelectorAll('.sp-edit').forEach(b=>b.onclick=()=>{form=editForm(data.rows[+b.dataset.i]);draw();});
        body.querySelectorAll('.sp-del').forEach(b=>b.onclick=()=>delHdr(data.rows[+b.dataset.i]));
        const ab=g('#ap-base'); if(ab)ab.onclick=()=>addApply('base');
        const ao=g('#ap-one'); if(ao)ao.onclick=()=>addApply('one');
        body.querySelectorAll('.ap-del').forEach(el=>el.onclick=()=>delApply(el.dataset.it));
      }
      if(form!==null){
        g('#hf-x').onclick=()=>{form=null;draw();};g('#hf-cancel').onclick=()=>{form=null;draw();};g('#hf-save').onclick=saveHdr;
        if(form.id){
          const loadFiles=async()=>{const box=g('#hf-files');if(!box)return;
            try{const j=await(await fetch(`${API}/api/qc/spec/files?rev_ymd=${encodeURIComponent(form._ry||'')}&rev_no=${encodeURIComponent(form._rn||'')}`)).json();
              box.innerHTML=(j.rows||[]).length?j.rows.map(f=>`<div style="display:flex;gap:8px;align-items:center;padding:2px 0"><span class="bdg ${f.editable?'ok':'off'}">${esc(f.kind)}</span><span class="hff-dl" data-src="${esc(f.src)}" data-key="${esc(f.key)}" style="cursor:pointer;color:#1c47a0;text-decoration:underline">${esc(f.filename)}</span>${f.editable?`<span class="hff-del" data-id="${esc(f.key)}" style="cursor:pointer;color:#c0392b" title="삭제">✖</span>`:''}</div>`).join(''):'<span style="color:#8aa0bd">첨부 없음</span>';
              box.querySelectorAll('.hff-dl').forEach(a=>a.onclick=()=>window.open(`${API}/api/doc/download?src=${encodeURIComponent(a.dataset.src)}&key=${encodeURIComponent(a.dataset.key)}`,'_blank'));
              box.querySelectorAll('.hff-del').forEach(x=>x.onclick=async()=>{if(!confirm('첨부 삭제?'))return;await fetch(`${API}/api/doc/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({doc_id:+x.dataset.id})});loadFiles();});}
            catch(e){box.innerHTML='<span style="color:#c0392b">파일 조회 실패</span>';}};
          loadFiles();
          const doUp=async(kind,inp)=>{const el=g(inp);if(!el||!el.files[0]){alert('파일을 선택하세요');return;}
            const fd=new FormData();fd.append('file',el.files[0]);fd.append('doc_kind',kind);fd.append('item_code',form.item_code||'');fd.append('rev_ymd',form._ry||'');fd.append('rev_no',form._rn||'');fd.append('user',(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자'));
            try{const j=await(await fetch(`${API}/api/doc/upload`,{method:'POST',body:fd})).json();if(j.ok){el.value='';loadFiles();}else alert('업로드 실패: '+(j.detail||''));}catch(e){alert('업로드 오류: '+e);}};
          const du=g('#hf-dwg-up');if(du)du.onclick=()=>doUp('SPEC_DWG','#hf-dwg');
          const su=g('#hf-spec-up');if(su)su.onclick=()=>doUp('SPEC_SHEET','#hf-spec');
        }
        body.querySelectorAll('[data-fk]').forEach(el=>{if(el.classList.contains('sp-ac'))return;el.oninput=()=>{form[el.dataset.fk]=el.value;};});
        body.querySelectorAll('.sp-ac').forEach(el=>{const fk=el.dataset.fk,kind=el.dataset.kind,sc=!!el.dataset.showcode,box=g('#sp-acb-'+fk);let t=null;
          el.oninput=()=>{if(sc)form[fk]=el.value;else{form[fk+'__nm']=el.value;form[fk]='';}clearTimeout(t);const q=el.value.trim();if(!q){box.style.display='none';return;}
            t=setTimeout(()=>fetch(`${API}/api/qc/opt?kind=${kind}&q=`+encodeURIComponent(q)).then(r=>r.json()).then(j=>{const rows=j.rows||[];box.innerHTML=rows.length?rows.map(x=>`<div class="sp-o" data-code="${esc(x.code)}" data-name="${esc(x.name)}" style="padding:5px 10px;cursor:pointer;font-size:12px;border-bottom:1px solid #f0f3f8"><b>${esc(sc?x.code:x.name)}</b> <span style="color:#9aa8bd;font-size:11px">${esc(sc?x.name:x.code)}</span></div>`).join(''):'<div style="padding:6px 10px;color:#999;font-size:12px">결과 없음</div>';box.style.display='block';box.querySelectorAll('.sp-o').forEach(o=>o.onmousedown=()=>{form[fk]=o.dataset.code;form[fk+'__nm']=o.dataset.name;el.value=sc?o.dataset.code:o.dataset.name;box.style.display='none';});}),180);};
          el.onblur=()=>setTimeout(()=>{if(box)box.style.display='none';},180);});
      }
      specDecorate(body);
    };
    load();
  };
  // 통합뷰(레거시+nx 합집합 단일 프로그램) — 토글 제거. 레거시행=읽기전용, nx행=수정/삭제.
  c.innerHTML=`
    <div class="page-title">📐 시방변경관리 <span style="font-size:12px;color:var(--muted);font-weight:400">ECO/시방개정 이력 · 적용대상(좌:시방 / 우:적용품번)</span></div>
    <div class="page-sub">설계변경(ECO)·시방개정 <b>통합뷰</b> — 📁 미러이력(<code>QA_T_SPEC_REV</code>) + ✏️ nx등록(<code>nx.qc_spec_rev</code>)을 한 목록으로. <b>미러행=읽기전용, nx행=수정·삭제</b> · PART NO의 ✕=시방경보</div>
    <div id="qcspec-body"></div>`;
  specView(c.querySelector('#qcspec-body'), {src:'all', editable:true});
};

/* 품질 ③: 수입검사(IQC)조회 (w_qa_cust_iqc) — QA_T_CUST_IQC_HEAD/DTL 읽기전용 */
SCREEN.qciqc=(c)=>{
  const API=API_BASE;
  c.innerHTML=`<div class="page-title">🔬 수입검사(IQC)조회 <span style="font-size:12px;color:var(--muted);font-weight:400">거래처 수입검사 결과·측정치수</span></div>
   <div class="page-sub">협력사 납품품 수입검사 헤더·상세치수 조회(읽기전용). 원본=<code>QA_T_CUST_IQC_HEAD/DTL</code>. 행을 클릭하면 규격·측정값 상세가 표시됩니다.</div>
   <div id="iqc-body"></div>`;
  qcRead(c.querySelector('#iqc-body'),{
    listEp:'/api/qc/iqc/list', dateLabel:'검사기간', days:120,
    filters:[{k:'item',label:'품번',width:120},{k:'cust',label:'거래처',width:80}],
    buildQS:F=>({from_ymd:F.from,to_ymd:F.to,item:F.item||'',cust:F.cust||''}),
    cols:[
      {h:'검사일자',cls:'center',fmt:r=>_wymd(r.oqc_ymd)},
      {h:'SEQ',k:'oqc_seq',cls:'num'},
      {h:'품번',fmt:r=>`<b>${esc(r.item_code)}</b>`},
      {h:'품명',k:'nm',cap:1,title:'nm'},
      {h:'자재',k:'mat'},
      {h:'거래처',fmt:r=>esc(r.cust_nm||r.cust)},
      {h:'라인',k:'line',cls:'center'},
      {h:'검사수량',cls:'num',fmt:r=>_wnf(r.insp_qty)},
      {h:'판정',cls:'center',fmt:r=>r.ok?'<span style="color:#1c7c3a">합격</span>':'<span style="color:#c0392b">불합격</span>'},
      {h:'불량내용',k:'err_text',cap:1,title:'err_text'},
    ],
    onRow:async(r)=>{const q=new URLSearchParams({ymd:r.oqc_ymd,seq:r.oqc_seq});
      const res=await fetch(`${API}/api/qc/iqc/detail?${q}`);return await res.json();},
    subView:(sub,sel)=>{
      const rows=sub.rows||[];
      return `<div style="background:#f7fafd;border:1px solid #cddaea;border-radius:8px;padding:8px">
        <div style="font-weight:600;margin-bottom:6px">📐 ${esc(sel.item_code)} · ${_wymd(sel.oqc_ymd)} SEQ${sel.oqc_seq} 측정상세 (${rows.length}항목)</div>
        <div class="grid-wrap" style="max-height:300px;overflow:auto;background:#fff;border:1px solid #dce4ee;border-radius:6px">
        <table class="tbl" style="font-size:11px"><thead><tr><th>순번</th><th>규격</th><th>규격2</th><th class="num">측정1</th><th class="num">측정2</th><th class="num">측정3</th><th class="num">측정4</th><th class="num">측정5</th><th class="num">불량</th><th class="center">판정</th></tr></thead>
        <tbody>${rows.length?rows.map(d=>`<tr><td class="center">${esc(d.SPEC_SEQ)}</td><td><b>${esc(d.spec1)}</b></td><td>${esc(d.spec2)}</td>
          <td class="num">${esc(d.v1)}</td><td class="num">${esc(d.v2)}</td><td class="num">${esc(d.v3)}</td><td class="num">${esc(d.v4)}</td><td class="num">${esc(d.v5)}</td>
          <td class="num">${_wnf(d.err)}</td><td class="center">${d.ok?'✔':'✘'}</td></tr>`).join(''):`<tr><td colspan="10" class="empty">측정상세 없음</td></tr>`}</tbody></table></div></div>`;
    },
  });
};

/* ===== 가공스크랩관리 (w_qa_raw_input_100) — 조회 라이브 QA_T_RAW_ERROR ∪ nx.scrap_raw / 쓰기 nx만 ===== */
SCREEN.scrapraw=(host)=>{
  const API=API_BASE;
  const _today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  const _fmtY=(s)=>{s=String(s||'');return s.length>=6?`20${s.slice(0,2)}-${s.slice(2,4)}-${s.slice(4,6)}`:s;};   // YYMMDD→YYYY-MM-DD
  const _kg=(v)=>(+(v||0)).toLocaleString(undefined,{minimumFractionDigits:0,maximumFractionDigits:4});
  const st={rows:[],cnt:0,total_wt:0,from:'',to:'',tag:'',item:'',src:'',
            tags:[],sojes:[],procs:[],works:[],workers:[],form:null,sel:new Set(),msg:''};
  const load=async()=>{
    const qs=new URLSearchParams({from_ymd:st.from,to_ymd:st.to,tag:st.tag,item:st.item,src:st.src});
    try{const r=await fetch(`${API}/api/scrap/list?${qs}`);const j=await r.json();
      st.rows=j.rows||[];st.cnt=j.cnt||0;st.total_wt=j.total_wt||0;
      st.tags=j.tags||[];st.sojes=j.sojes||[];st.procs=j.procs||[];st.works=j.works||[];st.workers=j.workers||[];st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];st.cnt=0;st.total_wt=0;}
    render();
  };
  const _opt=(list,cur,codeKey,nameKey)=>{   // [{code,name}] → <option>; 현재값 없으면 추가
    let ok=false; let h=list.map(o=>{const c=codeKey?o[codeKey]:o;const n=nameKey?o[nameKey]:o;if(String(c)===String(cur||''))ok=true;
      return `<option value="${esc(c)}" ${String(c)===String(cur||'')?'selected':''}>${esc(n)}</option>`;}).join('');
    if(cur&&!ok)h+=`<option value="${esc(cur)}" selected>${esc(cur)}</option>`;
    return h;
  };
  const render=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('scrapraw'):true;
    const editing=st.form!==null, f=st.form||{};
    host.innerHTML=`
     <div class="page-title">🗑 가공스크랩관리 <span style="font-size:12px;color:var(--muted);font-weight:400">가공 스크랩(불량) 중량 기록 · nx.scrap_raw</span></div>
     <div class="page-sub">레거시 <code>w_qa_input_100</code> 그대로. 조회=라이브 <code>QA_T_RAW_ERROR</code> ∪ <code>nx.scrap_raw</code> · 추가·수정·삭제·복사=<b>nx만</b>(라이브 읽기전용). 코드→이름 · 필수=불량일자·스크랩중량.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">불량기간</label><input class="inp" id="sc-from" type="date" value="${esc(st.from)}" style="width:140px"> ~ <input class="inp" id="sc-to" type="date" value="${esc(st.to)}" style="width:140px">
       <label class="tl">구분</label><select class="inp" id="sc-tag" style="width:120px"><option value="">전체</option>${_opt(st.tags,st.tag,'code','name')}</select>
       <label class="tl">품번</label><input class="inp" id="sc-item" value="${esc(st.item)}" placeholder="P/No" style="width:130px">
       <label class="tl">원천</label><select class="inp" id="sc-src" style="width:110px">
         <option value="" ${st.src===''?'selected':''}>합집합</option><option value="L" ${st.src==='L'?'selected':''}>라이브</option><option value="N" ${st.src==='N'?'selected':''}>신규(nx)</option></select>
       <button class="btn" id="sc-search">🔍 조회</button>
       ${ed?`<button class="btn" id="sc-new" style="background:#1c7c3a;color:#fff">➕ 추가</button>
       <button class="btn" id="sc-del">🗑 선택삭제</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음</span>`}
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${editing?_formHtml(f):''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
        <th style="width:26px"></th><th style="width:64px">SEQ</th><th>구분</th><th>불량일자</th><th>P/No</th><th>품명</th>
        <th>작업처</th><th>작업자</th><th>소재항목</th><th>불량내용</th><th>발생공정</th><th class="num">스크랩중량(kg)</th><th style="width:88px">작업</th></tr></thead>
      <tbody>${st.rows.length?st.rows.map((r,i)=>`<tr>
        <td class="center">${(ed&&r.src==='N')?`<input type="checkbox" class="sc-chk" data-id="${esc(r.id)}" ${st.sel.has(r.id)?'checked':''}>`:''}</td>
        <td class="center"><span style="font-size:9px;padding:0 4px;border-radius:3px;color:#fff;background:${r.src==='N'?'#1c7c3a':'#8090a5'}">${r.src==='N'?'신규':'라이브'}</span> ${esc(r.id)}</td>
        <td>${esc((st.tags.find(t=>t.code===String(r.tag))||{}).name||r.tag)}</td>
        <td>${_fmtY(r.ymd)}</td><td><b>${esc(r.item)}</b></td>
        <td class="cap" title="${esc(r.item_desc)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.item_desc)}</td>
        <td title="${esc(r.work)}">${esc(r.work_desc||r.work)}</td><td>${esc(r.worker)}</td><td>${esc(r.soje)}</td>
        <td class="cap" title="${esc(r.err_desc)}" style="max-width:180px;overflow:hidden;text-overflow:ellipsis">${esc(r.err_desc)}</td>
        <td title="${esc(r.pcode)}">${esc(r.proc_desc||r.pcode)}</td><td class="num">${_kg(r.wt)}</td>
        <td class="center">${ed?`${r.src==='N'?`<button class="btn sc-edit" data-idx="${i}" style="padding:1px 5px;font-size:10px">수정</button>`:''}<button class="btn sc-copy" data-idx="${i}" style="padding:1px 5px;font-size:10px">복사</button>`:''}</td></tr>`).join(''):`<tr><td colspan="13" class="empty">조회 결과 없음${ed?' (➕추가로 등록)':''}</td></tr>`}</tbody>
      <tfoot><tr style="position:sticky;bottom:0;background:#eef2f7;font-weight:700;border-top:2px solid #c9d3e0">
        <td></td><td class="center">합계</td><td colspan="9" style="text-align:right">건수 ${won(st.cnt)}건 · 총중량</td><td class="num">${_kg(st.total_wt)}</td><td></td></tr></tfoot></table></div>`;
    const g=s=>host.querySelector(s);
    g('#sc-search').onclick=()=>{st.from=g('#sc-from').value;st.to=g('#sc-to').value;st.tag=g('#sc-tag').value;st.item=g('#sc-item').value;st.src=g('#sc-src').value;st.sel.clear();load();};
    g('#sc-item').onkeyup=e=>{if(e.key==='Enter')g('#sc-search').click();};
    if(ed){
      g('#sc-new').onclick=()=>{st.form={error_ymd:_today(),error_tag:'2',work_code:'P2',proc_code:'',lot_qty:''};render();};
      g('#sc-del').onclick=()=>del([...st.sel]);
      host.querySelectorAll('.sc-chk').forEach(ch=>ch.onclick=()=>{ch.checked?st.sel.add(ch.dataset.id):st.sel.delete(ch.dataset.id);});
      host.querySelectorAll('.sc-edit').forEach(b=>b.onclick=()=>{const r=st.rows[+b.dataset.idx];
        st.form={id:r.id,error_ymd:_fmtY(r.ymd),error_tag:r.tag,item_code:r.item,item_desc:r.item_desc,work_code:r.work,
          error_member_name:r.worker,error_item:r.soje,error_desc:r.err_desc,proc_code:r.pcode,lot_qty:r.wt};render();});
      host.querySelectorAll('.sc-copy').forEach(b=>b.onclick=()=>copy(st.rows[+b.dataset.idx].id));
    }
    attachResizers(host);
    if(editing){
      g('#sc-x').onclick=g('#sc-cancel').onclick=()=>{st.form=null;render();};
      g('#sc-save').onclick=save;
      host.querySelectorAll('.sf').forEach(el=>el.oninput=()=>{st.form[el.dataset.k]=el.value;});
    }
  };
  const _formHtml=(f)=>`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
     <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:620px;max-width:97vw">
       <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
         <b>가공스크랩 ${f.id?'수정 ('+esc(f.id)+')':'추가'}</b><span id="sc-x" style="cursor:pointer;font-size:17px">✕</span></div>
       <div style="padding:14px 16px;display:grid;grid-template-columns:auto 1fr auto 1fr;gap:8px 10px;align-items:center;font-size:12px">
         <label style="color:#33507d;font-weight:600;text-align:right">불량일자<span style="color:#c0392b">*</span></label><input class="inp sf" type="date" data-k="error_ymd" value="${esc(f.error_ymd||'')}">
         <label style="color:#33507d;font-weight:600;text-align:right">구분</label><select class="inp sf" data-k="error_tag">${_opt(st.tags,f.error_tag,'code','name')}</select>
         <label style="color:#33507d;font-weight:600;text-align:right">P/No</label><input class="inp sf" data-k="item_code" value="${esc(f.item_code||'')}" placeholder="품번">
         <label style="color:#33507d;font-weight:600;text-align:right">품명</label><input class="inp sf" data-k="item_desc" value="${esc(f.item_desc||'')}">
         <label style="color:#33507d;font-weight:600;text-align:right">작업처</label><select class="inp sf" data-k="work_code">${_opt(st.works,f.work_code||'P2','code','name')}</select>
         <label style="color:#33507d;font-weight:600;text-align:right">작업자</label><input class="inp sf" list="sc-wk" data-k="error_member_name" value="${esc(f.error_member_name||'')}"><datalist id="sc-wk">${st.workers.map(w=>`<option value="${esc(w)}">`).join('')}</datalist>
         <label style="color:#33507d;font-weight:600;text-align:right">소재항목</label><select class="inp sf" data-k="error_item"><option value="">(선택)</option>${_opt(st.sojes,f.error_item)}</select>
         <label style="color:#33507d;font-weight:600;text-align:right">발생공정</label><select class="inp sf" data-k="proc_code"><option value="">(선택)</option>${_opt(st.procs,f.proc_code,'code','name')}</select>
         <label style="color:#33507d;font-weight:600;text-align:right">스크랩중량(kg)<span style="color:#c0392b">*</span></label><input class="inp sf" type="number" step="0.0001" min="0" data-k="lot_qty" value="${esc(f.lot_qty!==''&&f.lot_qty!=null?f.lot_qty:'')}">
         <label style="color:#33507d;font-weight:600;text-align:right">불량내용</label><input class="inp sf" data-k="error_desc" value="${esc(f.error_desc||'')}" style="grid-column:span 3">
       </div>
       <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
         <span style="color:#c0392b;font-size:11px">* 불량일자·스크랩중량(kg,&gt;0)은 필수. 라이브 자료는 복사 후 편집.</span>
         <span><button class="btn" id="sc-save" style="background:#1b6ec2;color:#fff">💾 저장</button> <button class="btn" id="sc-cancel">닫기</button></span></div>
     </div></div>`;
  const save=async()=>{
    const f=st.form;
    if(!String(f.error_ymd||'').trim()){alert('불량일자는 필수입니다');return;}
    if(!(parseFloat(f.lot_qty)>0)){alert('스크랩중량(kg)은 0보다 커야 합니다');return;}
    try{const r=await fetch(`${API}/api/scrap/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(f)});
      const j=await r.json();
      if(r.ok&&j.ok){st.msg=(j.mode==='insert'?'✅ 등록완료':'✅ 수정완료')+` (${esc(j.id)})`;st.form=null;await load();}
      else alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 오류: '+e);}
  };
  const del=async(ids)=>{if(!ids.length){alert('삭제할 신규(nx) 행을 체크하세요 (라이브는 삭제불가)');return;}
    if(!confirm(ids.length+'건을 삭제하시겠습니까?'))return;
    try{const r=await fetch(`${API}/api/scrap/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})});
      const j=await r.json();if(r.ok&&j.ok){st.msg='🗑 '+j.deleted+'건 삭제완료';st.sel.clear();await load();}else alert('삭제 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('삭제 오류: '+e);}
  };
  const copy=async(id)=>{
    try{const r=await fetch(`${API}/api/scrap/copy`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
      const j=await r.json();if(r.ok&&j.ok){st.msg='📋 복사완료 → '+esc(j.id)+' (신규 nx). 필요시 수정하세요.';await load();}else alert('복사 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('복사 오류: '+e);}
  };
  load();
};
