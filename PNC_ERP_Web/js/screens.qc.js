/* ===== PNC ERP screens.qc.js — 품질 SCREEN (app.js 분할, 순수이동) ===== */

/* ===== 품질 반성회의록 CRUD (nx.meeting ← cm_user_meeting_1) — 비용 자동계산 ===== */
/* ===== 품질 반성회일지 (w_pr_input_590 조회 + w_pr_input_595 등록/수정) =====
   ★원천: PR_T_DAILY_ISSUE_REVIEW (+ _FILE 첨부). 레거시 dw 조회쿼리 3종 그대로 이식.
   ★조회 = 라이브 + nx(웹 등록분) 합산 / 쓰기 = nx 만.
     라이브(레거시 작성분)는 웹에서 수정·삭제 불가 — nx 등록분만 가능. */
SCREEN.meeting=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const d2y=s=>(s||'').replace(/-/g,'').slice(2);                 // 2026-08-23 -> 260823
  const y2d=s=>(s&&s.length===6)?`20${s.slice(0,2)}-${s.slice(2,4)}-${s.slice(4,6)}`:'';
  const ymdk=s=>(s&&s.length===6)?`${s.slice(0,2)}/${s.slice(2,4)}/${s.slice(4,6)}`:(s||'');
  const hm=s=>(s&&s.length===4)?`${s.slice(0,2)}:${s.slice(2,4)}`:(s||'');
  const T=new Date();
  const st={from:iso(new Date(T.getTime()-22*864e5)),to:iso(T),q:'',
            rows:[],cnt:0,loading:false,loaded:false,msg:'',
            sel:null,detail:null,dloading:false,chk:new Set(),procs:[]};
  const loadOpts=async()=>{try{const d=await(await fetch(`${API}/api/qareview/opts`)).json();st.procs=d.procs||[];}catch(e){}};
  const load=async()=>{st.loading=true;draw();
    const qs=new URLSearchParams({from_ymd:st.from,to_ymd:st.to,q:st.q,limit:1000});
    try{const r=await fetch(`${API}/api/qareview/list?${qs}`);const d=await r.json();
      st.rows=d.rows||[];st.cnt=d.cnt||0;st.msg='';st.loaded=true;st.chk.clear();
      if(st.sel&&!st.rows.some(x=>x.seq===st.sel)){st.sel=null;st.detail=null;}}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];st.cnt=0;}
    st.loading=false;draw();
    if(!st.sel&&st.rows.length)pick(st.rows[0].seq);};
  const pick=async(seq)=>{
    st.sel=seq;
    c.querySelectorAll('.mt-row').forEach(el=>el.style.background=(+el.dataset.seq===seq)?'#dcebff':'');
    st.dloading=true;renderDetail();
    try{st.detail=await(await fetch(`${API}/api/qareview/detail?seq=${seq}`)).json();}
    catch(e){st.detail=null;}
    st.dloading=false;renderDetail();};
  // 레거시 일지 양식 그대로(보기 전용)
  const paperHtml=()=>{
    if(st.dloading)return `<div style="padding:30px;text-align:center;color:var(--muted)">불러오는 중…</div>`;
    const d=st.detail;
    if(!d||d.detail==null&&!d.seq)return `<div style="padding:30px;text-align:center;color:var(--muted)">← 좌측에서 일지를 선택하세요</div>`;
    const rate=(a,b)=>{a=+a||0;b=+b||0;return b?Math.round(a/b*1000)/10:0;};
    const box=(t,v)=>`<div style="border:1px solid #333;min-height:150px;padding:6px 8px;white-space:pre-wrap;font-size:12px;line-height:1.5">${esc(v||'')}</div>`;
    return `
    <div style="padding:10px 14px;background:#fff">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:8px">
        <table style="border-collapse:collapse;font-size:12px">
          <tr><th style="border:1px solid #333;background:#eef2f7;padding:3px 8px">구 분</th>
              <th style="border:1px solid #333;background:#eef2f7;padding:3px 8px">전체</th>
              <th style="border:1px solid #333;background:#eef2f7;padding:3px 8px">품 질</th>
              <th style="border:1px solid #333;background:#eef2f7;padding:3px 8px">불량수</th>
              <td style="border:1px solid #333;padding:3px 8px;text-align:right">${nf(d.err)} 대</td></tr>
          <tr><th style="border:1px solid #333;background:#eef2f7;padding:3px 8px">당일목표</th>
              <td style="border:1px solid #333;padding:3px 8px;text-align:right">${nf(d.t_target)} 대</td>
              <td style="border:1px solid #333;padding:3px 8px;text-align:right">${nf(d.ppm_target)} ppm</td>
              <th style="border:1px solid #333;background:#eef2f7;padding:3px 8px">총 원</th>
              <td style="border:1px solid #333;padding:3px 8px;text-align:right">${nf(d.inwon)} 명</td></tr>
          <tr><th style="border:1px solid #333;background:#eef2f7;padding:3px 8px">당일실적</th>
              <td style="border:1px solid #333;padding:3px 8px;text-align:right">${nf(d.t_result)} 대</td>
              <td style="border:1px solid #333;padding:3px 8px;text-align:right">${nf(d.ppm_result)} ppm</td>
              <th style="border:1px solid #333;background:#eef2f7;padding:3px 8px">휴 가</th>
              <td style="border:1px solid #333;padding:3px 8px;text-align:right">${nf(d.holiday)} 명</td></tr>
          <tr><th style="border:1px solid #333;background:#eef2f7;padding:3px 8px">달성율</th>
              <td style="border:1px solid #333;padding:3px 8px;text-align:right">${rate(d.t_result,d.t_target)} %</td>
              <td style="border:1px solid #333;padding:3px 8px;text-align:right">${rate(d.ppm_result,d.ppm_target)} %</td>
              <th style="border:1px solid #333;background:#eef2f7;padding:3px 8px">참석인원</th>
              <td style="border:1px solid #333;padding:3px 8px;text-align:right">${nf(d.attend)} 명</td></tr>
        </table>
        <div style="flex:1">
          <div style="font-size:20px;font-weight:800;border-bottom:2px solid #333;display:inline-block;padding:0 8px 2px">Daily Issue Review</div>
          <div style="margin-top:8px;font-size:12px;line-height:1.9">
            <div>★시 간 : <b>${esc(hm(d.hhmm))}</b> &nbsp;&nbsp; ★구 분 : <b>${esc(d.proc_nm||'전체')}</b></div>
            <div>★장 소 : <b>${esc(d.place)}</b> &nbsp;&nbsp; ★작성자 : <b>${esc(d.user_name||d.writer)}</b></div>
            <div>★대 상 : <b>${esc(d.target)}</b> &nbsp;&nbsp; ★작성일 : <b>${esc(ymdk(d.ymd))}</b></div>
          </div>
        </div>
        <table style="border-collapse:collapse;font-size:11px;text-align:center">
          <tr><td rowspan="2" style="border:1px solid #333;padding:3px 5px;background:#eef2f7">결<br>재</td>
              <th style="border:1px solid #333;padding:3px 14px;background:#eef2f7">반 장</th>
              <th style="border:1px solid #333;padding:3px 14px;background:#eef2f7">팀 장</th></tr>
          <tr><td style="border:1px solid #333;height:34px"></td><td style="border:1px solid #333"></td></tr>
        </table>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid #333">
        <div style="border-right:1px solid #333">
          <div style="text-align:center;font-weight:700;background:#eef2f7;border-bottom:1px solid #333;padding:4px">당일 공정 품질 및 Return 불량 현황</div>
          <div style="padding:6px 8px;font-weight:700;font-size:12px">1.당일 공정품질 문제점(전체 Issue)</div>
          ${box('',d.qa_issue)}
          <div style="padding:6px 8px;font-weight:700;font-size:12px">2.당일 Return 불량 Issue 사항</div>
          ${box('',d.rtn_err)}
        </div>
        <div>
          <div style="text-align:center;font-weight:700;background:#eef2f7;border-bottom:1px solid #333;padding:4px">공유 내용 및 파급 전파</div>
          <div style="padding:6px 8px;font-weight:700;font-size:12px">1.4M 변경사항(설비/자재/인원/작업방법)</div>
          ${box('',d.c1)}
          <div style="padding:6px 8px;font-weight:700;font-size:12px">2.자주/순차검사</div>
          ${box('',d.c2)}
          <div style="padding:6px 8px;font-weight:700;font-size:12px">3.전달사항</div>
          ${box('',d.c3)}
          <div style="padding:6px 8px;font-weight:700;font-size:12px">4.공유후 질문사항(인터뷰)</div>
          ${box('',d.c4)}
        </div>
      </div>
      <div style="margin-top:6px;font-size:12px">☞ 첨부파일 ${(d.files||[]).length?`: ${(d.files||[]).map(f=>esc(f.name)).join(', ')}`:'<span style="color:var(--muted)">없음</span>'}</div>
      <div style="margin-top:4px;font-size:11px;color:var(--muted)">
        ${d.editable?'🟢 웹 등록분 — 수정/삭제 가능':'🔴 레거시 작성분 — 웹에서 수정/삭제 불가(조회 전용)'}
        · 등록 ${esc(d.ins_user)} ${esc(d.ins_dt)} · 수정 ${esc(d.upd_user)} ${esc(d.upd_dt)}
      </div>
    </div>`;
  };
  const renderDetail=()=>{const b=c.querySelector('#mt-paper');if(b)b.innerHTML=paperHtml();};
  const draw=()=>{
    c.innerHTML=`
     <style>.mt-tbl th,.mt-tbl td{text-align:center!important}</style>
     <div class="page-title">📝 품질 반성회일지 <span style="font-size:12px;color:var(--muted);font-weight:400">Daily Issue Review · 작성/조회</span></div>
     <div class="page-sub">레거시 <code>w_pr_input_590</code>(조회)+<code>595</code>(등록) 이식 · 원천 <code>PR_T_DAILY_ISSUE_REVIEW</code>. 🔴 라이브 조회 / 🟢 등록은 nx</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:6px;align-items:center">
       <label class="tl">대상기간</label><input class="inp" type="date" id="mt-from" value="${st.from}"> ~ <input class="inp" type="date" id="mt-to" value="${st.to}">
       <label class="tl">검색</label><input class="inp" id="mt-q" value="${esc(st.q)}" style="width:170px" placeholder="작성자/장소/대상" autocomplete="off">
       <button class="btn" id="mt-search">🔍 조회</button>
       <div class="spacer"></div>
       <button class="btn" id="mt-new" style="background:#1c7c3a;color:#fff">➕ 신규</button>
       <button class="btn" id="mt-edit">✏ 수정</button>
       <button class="btn" id="mt-del" style="background:#c0392b;color:#fff">🗑 선택삭제</button>
       <span class="rowcount">일지 <b>${nf(st.cnt)}</b>건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     <div style="display:flex;gap:8px;align-items:stretch">
      <div class="grid-wrap" style="flex:0 0 44%;max-height:calc(100vh - 240px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
       <table class="tbl fit mt-tbl" style="font-size:11px"><thead><tr>
         <th style="width:30px"><input type="checkbox" id="mt-all" title="전체선택"></th>
         <th>SEQ</th><th>작성일자</th><th>시간</th><th>작성자</th><th>장소</th><th>대상</th><th>참석</th><th>출처</th></tr></thead>
       <tbody>${st.loading?spinRow(9):(st.rows.length?st.rows.map((r,i)=>`<tr class="mt-row" data-seq="${r.seq}" style="cursor:pointer${st.sel===r.seq?';background:#dcebff':''}">
         <td class="center">${r.src==='nx'?`<input type="checkbox" class="mt-chk" data-seq="${r.seq}">`:'<span title="레거시 작성분은 삭제 불가" style="color:#c9d3e0">🔒</span>'}</td>
         <td class="center">${i+1}</td><td class="center">${esc(ymdk(r.ymd))}</td><td class="center">${esc(hm(r.hhmm))}</td>
         <td class="center">${esc(r.writer)}</td>
         <td class="center" style="max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.place)}">${esc(r.place)}</td>
         <td class="center" style="max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.target)}">${esc(r.target)}</td>
         <td class="center">${nf(r.attend)}</td>
         <td class="center"><span style="font-size:10px;color:${r.src==='nx'?'#1c7c3a':'#888'}">${esc(r.src)}</span></td></tr>`).join('')
         :`<tr><td colspan="9" class="empty">${st.loaded?'조회 결과 없음':'기간을 지정한 뒤 <b>🔍 조회</b>'}</td></tr>`)}</tbody></table></div>
      <div class="grid-wrap" id="mt-paper" style="flex:1;max-height:calc(100vh - 240px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">${paperHtml()}</div>
     </div>`;
    const g=id=>c.querySelector(id);
    g('#mt-search').onclick=()=>{st.from=g('#mt-from').value;st.to=g('#mt-to').value;st.q=g('#mt-q').value.trim();load();};
    g('#mt-q').onkeyup=e=>{if(e.key==='Enter')g('#mt-search').click();};
    c.querySelectorAll('.mt-row').forEach(el=>el.onclick=e=>{
      if(e.target&&e.target.classList&&e.target.classList.contains('mt-chk'))return;
      pick(+el.dataset.seq);});
    c.querySelectorAll('.mt-chk').forEach(ch=>ch.onclick=e=>e.stopPropagation());
    const all=g('#mt-all');
    if(all)all.onclick=e=>{e.stopPropagation();c.querySelectorAll('.mt-chk').forEach(ch=>ch.checked=all.checked);};
    g('#mt-new').onclick=()=>openReviewModal(st,null,()=>load());
    g('#mt-edit').onclick=()=>{
      if(!st.detail||!st.sel){alert('수정할 일지를 선택하세요.');return;}
      if(!st.detail.editable){alert('레거시에서 작성된 일지는 웹에서 수정할 수 없습니다.');return;}
      openReviewModal(st,st.detail,()=>load());};
    g('#mt-del').onclick=async()=>{
      const seqs=[...c.querySelectorAll('.mt-chk:checked')].map(ch=>+ch.dataset.seq);
      if(!seqs.length){alert('삭제할 일지를 선택하세요(체크박스).');return;}
      if(!confirm(`선택한 일지 ${seqs.length}건을 삭제할까요?`))return;
      try{
        const res=await fetch(`${API}/api/qareview/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seqs})});
        if(!res.ok){let t='';try{t=(await res.json()).detail||'';}catch(e){t=await res.text();}alert('삭제 실패: '+(t||res.status));return;}
        const d=await res.json();alert(d.msg||'');if(d.deleted)load();
      }catch(e){alert('삭제 실패: '+(e&&e.message||e));}};
  };
  draw();
  loadOpts().then(()=>{draw();load();});
};

/* 반성회일지 등록/수정 팝업 (w_pr_input_595) — 레거시 일지 양식 그대로 입력폼으로 */
function openReviewModal(st,cur,onSaved){
  const API=API_BASE;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const y2d=s=>(s&&s.length===6)?`20${s.slice(0,2)}-${s.slice(2,4)}-${s.slice(4,6)}`:iso(new Date());
  const hm=s=>(s&&s.length===4)?`${s.slice(0,2)}:${s.slice(2,4)}`:'00:00';
  const f=cur?{seq:cur.seq,ymd:y2d(cur.ymd),hhmm:hm(cur.hhmm),writer:cur.writer,place:cur.place,target:cur.target,
               proc:cur.proc||'%',t_target:cur.t_target,t_result:cur.t_result,ppm_target:cur.ppm_target,
               ppm_result:cur.ppm_result,err:cur.err,inwon:cur.inwon,holiday:cur.holiday,attend:cur.attend,
               qa_issue:cur.qa_issue,rtn_err:cur.rtn_err,c1:cur.c1,c2:cur.c2,c3:cur.c3,c4:cur.c4}
             :{seq:0,ymd:iso(new Date()),hhmm:'00:00',writer:'',place:'',target:'',proc:'%',
               t_target:0,t_result:0,ppm_target:0,ppm_result:0,err:0,inwon:0,holiday:0,attend:0,
               qa_issue:'',rtn_err:'',c1:'',c2:'',c3:'',c4:''};
  const ov=document.createElement('div');
  ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:9999;display:flex;align-items:center;justify-content:center';
  const num=(k,unit)=>`<input class="inp rv-f" data-k="${k}" type="number" step="any" value="${f[k]||0}" style="width:78px;min-width:0;text-align:right"> ${unit}`;
  const ta=(k,ph)=>`<textarea class="rv-f" data-k="${k}" placeholder="${ph}" style="width:100%;height:88px;border:1px solid #ccd3dc;border-radius:4px;padding:5px 7px;font-size:12px;font-family:inherit;resize:vertical">${esc(f[k]||'')}</textarea>`;
  ov.innerHTML=`<div class="rv-modal" style="background:#fff;border-radius:10px;width:1000px;max-width:97vw;max-height:92vh;display:flex;flex-direction:column;box-shadow:0 10px 40px rgba(0,0,0,.3);font-size:12px;overflow:hidden">
    <style>
      /* ★.inp 전역 min-width:200px 가 표 칸을 밀어내 하단 버튼까지 화면 밖으로 나가는 것을 막는다 */
      .rv-modal .inp,.rv-modal select.inp{min-width:0!important}
      .rv-modal table{max-width:100%}
      .rv-lb{font-weight:700;background:#eef2f7;border:1px solid #333;padding:3px 8px;white-space:nowrap}
      .rv-cell{border:1px solid #333;padding:2px 6px}
    </style>
    <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid #e5e9f0">
      <b style="font-size:14px">📝 품질 반성회일지 ${cur?'수정':'등록'}</b><span id="rv-x" style="cursor:pointer;font-size:18px;color:#888">✕</span></div>
    <div id="rv-msg" style="padding:2px 12px;min-height:15px;font-size:12px"></div>
    <div class="rv-wrap" style="flex:1;min-height:0;overflow:auto;padding:8px 12px">
      <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start;margin-bottom:8px">
        <table style="border-collapse:collapse">
          <tr><td class="rv-lb">구 분</td>
              <td class="rv-cell" colspan="2"><select class="inp rv-f" data-k="proc" style="width:150px">${(st.procs||[]).map(o=>`<option value="${esc(o.code)}"${f.proc===o.code?' selected':''}>${esc(o.nm)}</option>`).join('')}</select></td>
              <td class="rv-lb">불량수</td><td class="rv-cell">${num('err','대')}</td></tr>
          <tr><td class="rv-lb">당일목표</td><td class="rv-cell">${num('t_target','대')}</td><td class="rv-cell">${num('ppm_target','ppm')}</td>
              <td class="rv-lb">총 원</td><td class="rv-cell">${num('inwon','명')}</td></tr>
          <tr><td class="rv-lb">당일실적</td><td class="rv-cell">${num('t_result','대')}</td><td class="rv-cell">${num('ppm_result','ppm')}</td>
              <td class="rv-lb">휴 가</td><td class="rv-cell">${num('holiday','명')}</td></tr>
          <tr><td class="rv-lb">달성율</td><td class="rv-cell" id="rv-rate1" style="text-align:right">0 %</td>
              <td class="rv-cell" id="rv-rate2" style="text-align:right">0 %</td>
              <td class="rv-lb">참석인원</td><td class="rv-cell">${num('attend','명')}</td></tr>
        </table>
        <div style="flex:1;min-width:280px">
          <div style="font-size:18px;font-weight:800;border-bottom:2px solid #333;display:inline-block;padding:0 8px 2px">Daily Issue Review</div>
          <div style="margin-top:8px;display:grid;grid-template-columns:auto 1fr;gap:5px 8px;align-items:center">
            <label class="tl">★시 간</label><input class="inp rv-f" data-k="hhmm" type="time" value="${esc(f.hhmm)}" style="width:110px">
            <label class="tl">★장 소</label><input class="inp rv-f" data-k="place" value="${esc(f.place)}" style="width:100%" placeholder="예: S3라인">
            <label class="tl">★대 상</label><input class="inp rv-f" data-k="target" value="${esc(f.target)}" style="width:100%" placeholder="예: 3라인작업자">
            <label class="tl">★작성자</label><input class="inp rv-f" data-k="writer" value="${esc(f.writer)}" style="width:100%" placeholder="작성자명">
            <label class="tl">★작성일</label><input class="inp rv-f" data-k="ymd" type="date" value="${esc(f.ymd)}" style="width:150px">
          </div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div>
          <div style="text-align:center;font-weight:700;background:#eef2f7;border:1px solid #333;padding:4px">당일 공정 품질 및 Return 불량 현황</div>
          <div style="padding:5px 0 3px;font-weight:700">1.당일 공정품질 문제점(전체 Issue)</div>${ta('qa_issue','')}
          <div style="padding:5px 0 3px;font-weight:700">2.당일 Return 불량 Issue 사항</div>${ta('rtn_err','')}
        </div>
        <div>
          <div style="text-align:center;font-weight:700;background:#eef2f7;border:1px solid #333;padding:4px">공유 내용 및 파급 전파</div>
          <div style="padding:5px 0 3px;font-weight:700">1.4M 변경사항(설비/자재/인원/작업방법)</div>${ta('c1','')}
          <div style="padding:5px 0 3px;font-weight:700">2.자주/순차검사</div>${ta('c2','')}
          <div style="padding:5px 0 3px;font-weight:700">3.전달사항</div>${ta('c3','')}
          <div style="padding:5px 0 3px;font-weight:700">4.공유후 질문사항(인터뷰)</div>${ta('c4','')}
        </div>
      </div>
    </div>
    <div style="flex:0 0 auto;display:flex;gap:8px;justify-content:flex-end;align-items:center;padding:8px 12px;border-top:1px solid #e5e9f0;background:#fff">
      <span style="margin-right:auto;font-size:11px;color:#666">※ 등록분은 nx 에 저장됩니다(라이브 원본은 변경하지 않습니다).</span>
      <button class="btn" id="rv-save" style="background:#1c47a0;color:#fff">✔ 저장</button>
      <button class="btn" id="rv-close">닫기</button></div>
  </div>`;
  const q=s=>ov.querySelector(s);
  const msg=(t,ok)=>{q('#rv-msg').innerHTML=t?`<span style="color:${ok?'#1c7c3a':'#c0392b'}">${esc(t)}</span>`:'';};
  const rate=()=>{const r=(a,b)=>{a=+a||0;b=+b||0;return b?Math.round(a/b*1000)/10:0;};
    q('#rv-rate1').textContent=r(f.t_result,f.t_target)+' %';
    q('#rv-rate2').textContent=r(f.ppm_result,f.ppm_target)+' %';};
  // ★oninput 으로 즉시 반영 — onchange 만 쓰면 입력 직후 저장을 누를 때 값이 안 잡힌다(2026-08-23)
  const syncOne=el=>{const k=el.dataset.k;f[k]=(el.type==='number')?(+el.value||0):el.value;};
  const syncAll=()=>ov.querySelectorAll('.rv-f').forEach(syncOne);
  ov.querySelectorAll('.rv-f').forEach(el=>{
    const h=()=>{syncOne(el);
      const k=el.dataset.k;
      if(k==='t_target'||k==='t_result'||k==='ppm_target'||k==='ppm_result')rate();};
    el.oninput=h; el.onchange=h;});
  q('#rv-x').onclick=q('#rv-close').onclick=()=>ov.remove();
  q('#rv-save').onclick=async()=>{
    syncAll();                                  // 저장 직전 DOM 값을 한번 더 수거(포커스 유지 상태 대비)
    if(!String(f.writer||'').trim()){msg('작성자를 입력하세요.',false);
      const w=ov.querySelector('.rv-f[data-k="writer"]');if(w)w.focus();return;}
    q('#rv-save').disabled=true;
    try{
      const body={...f,ymd:String(f.ymd||'').replace(/-/g,'').slice(2),
                  hhmm:String(f.hhmm||'').replace(':',''),user:'웹'};
      const res=await fetch(`${API}/api/qareview/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(!res.ok){let t='';try{t=(await res.json()).detail||'';}catch(e){t=await res.text();}
        msg('저장 실패: '+(t||res.status),false);return;}
      const d=await res.json();
      if(d.ok){msg(`✔ ${d.msg}`,true);setTimeout(()=>{ov.remove();if(typeof onSaved==='function')onSaved();},700);}
      else msg(d.msg||'저장 실패',false);
    }catch(e){msg('저장 실패: '+(e&&e.message||e),false);}
    finally{const b=q('#rv-save');if(b)b.disabled=false;}
  };
  document.body.appendChild(ov); rate();
}
SCREEN.qcerror=(c)=>{
  wrShell(c,{sid:'qcerror',
    title:`🚫 품질불량관리 <span style="font-size:12px;color:var(--muted);font-weight:400">공정 불량 발생·조치 이력(등록·수정·삭제)</span>`,
    sub:`레거시 <code>w_qa_input_020</code> 전체 컬럼(옆스크롤). 🔴 라이브(<code>QA_T_ERROR</code>) 조회 + 🟢 등록·수정은 nx(<code>qc_error</code>) · ➕신규·수정은 팝업 · 코드→이름`,
    nxOnly:true,
    cfg:{
      listEp:'/api/qc/error/list', saveEp:'/api/qc/error/save', delEp:'/api/qc/error/delete', days:30,
      // ★src='all' — 레거시(QA_T_ERROR) + nx(qc_error) 합산 조회. 'nx' 로 두면 웹 등록분만 보여 0건이었다(2026-08-23)
      dateLabel:'불량기간', filters:qcFilters, buildQS:F=>qcQS(F,'all'),
      sum:d=>`불량수량합 <b>${_wnf(d.sum_err)}</b>`,
      // ★필수는 P/No 뿐 — 레거시 w_qa_input_025 도 P/No 만 필수(2026-08-23 확인)
      cols:qcCols, modal:true, modalTitle:'불량관리 Maint', modalWidth:980, modalCols:2,
      form:[
        {k:'error_ymd',label:'불량일자',type:'date',width:140},
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
        {k:'error_desc',label:'불량내용',width:700,full:1},{k:'color',label:'색깔',type:'select',opts:QC_COLOR,width:80},
        {k:'lot_qty',label:'생산수량(Lot)',type:'num',width:100},{k:'error_qty',label:'불량수량',type:'num',width:90},{k:'real_error_qty',label:'실발생불량',type:'num',width:90},
        {k:'scrap_weight',label:'스크랩중량(kg)',type:'num',width:100},
        {k:'error_cause',label:'원인',width:700,full:1},{k:'progress_stats',label:'진행상황',width:700,full:1},{k:'charge_name',label:'담당',width:80},
        {k:'water_flag',label:'수몰여부',type:'select',opts:QC_YN,width:90},
        {k:'reinsp_flag',label:'재검사여부',type:'select',opts:QC_YN,width:90},
        {k:'finish_flag',label:'완료여부',type:'select',opts:QC_YN,width:90},
      ],
      newRow:F=>({id:null,error_ymd:F.to,error_tag:'8',division:'',cust_line:'',pg_reg:'',item_code:'',work_code:'P2',proc_code:'',mach_code:'',partner_code:'',inspector:'',error_member:'',error_item1:'',error_item2:'',error_item3:'',error_desc:'',color:'1',lot_qty:'',error_qty:'',real_error_qty:'',scrap_weight:'',error_cause:'',progress_stats:'',charge_name:'',water_flag:'0',reinsp_flag:'0',finish_flag:'0'}),
      fromRow:r=>({id:r.ID,error_ymd:_y6(r.error_ymd),error_tag:r.tag,division:r.division,cust_line:r.cust_line,cust_line__nm:r.cust_line,pg_reg:r.pg_reg,item_code:r.item_code,work_code:r.work_code,proc_code:r.proc_code,proc_code__nm:r.part_nm,mach_code:r.mach_code,mach_code__nm:r.mach_nm,partner_code:r.partner_code,partner_code__nm:r.partner_nm,inspector:r.inspector,error_member:r.error_member,error_item1:r.ei1,error_item2:r.ei2,error_item3:r.ei3,error_desc:r.error_desc,color:r.color||'1',lot_qty:r.lot_qty,error_qty:r.error_qty,real_error_qty:r.real_qty,scrap_weight:r.scrap_weight,error_cause:r.error_cause,progress_stats:r.progress,charge_name:r.charge,water_flag:r.water_flag?'1':'0',reinsp_flag:r.reinsp_flag?'1':'0',finish_flag:r.finish_flag?'1':'0'}),
      toBody:f=>{const b={...f,user:'웹사용자'};Object.keys(b).forEach(k=>{if(k.endsWith('__nm'))delete b[k];});return b;},
      // ★첨부파일 3종(레거시 w_qa_input_025: 첨부파일#1·대책서#1·대책서#2)
      //   파일 실체는 기존 문서저장소(nx.doc + NAS) 재사용, qc_error 는 doc_id 만 보관.
      //   ※신규건은 id 가 없어 첨부 불가 → 저장 후 다시 열어 첨부하라고 안내한다.
      modalExtra:f=>qcFileBoxHtml(f),
      modalExtraBind:(root,f,reload)=>qcFileBoxBind(root,f,reload),
    }
  });
};

/* ===== 품질불량 첨부파일 3칸 (모달 확장영역) ===== */
const QC_SLOTS=[{k:'attach',t:'첨부파일#1'},{k:'plan1',t:'대책서#1'},{k:'plan2',t:'대책서#2'}];
function qcFileBoxHtml(f){
  const rows=QC_SLOTS.map(s=>`
    <tr data-slot="${s.k}">
      <td style="padding:4px 8px 4px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;width:104px">${s.t}</td>
      <td style="padding:3px 0">
        <div style="display:flex;align-items:center;gap:6px">
          <input type="file" class="qcf-file" data-slot="${s.k}" style="font-size:11px;max-width:230px">
          <span class="qcf-cur" data-slot="${s.k}" style="font-size:11px;color:#456;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">—</span>
          <button type="button" class="btn ghost qcf-del" data-slot="${s.k}" style="padding:1px 8px;font-size:11px" disabled>파일삭제</button>
        </div>
      </td>
    </tr>`).join('');
  return `<div style="margin-top:10px;border-top:1px solid #e2e8f2;padding-top:8px">
     <div style="font-weight:600;font-size:12px;color:#33507d;margin-bottom:4px">📎 첨부파일
       <span style="font-weight:400;color:#7a8aa0;font-size:11px">— 칸당 파일 1개(다시 올리면 교체) · 파일명 클릭=내려받기</span></div>
     ${f&&f.id?'':'<div style="color:#c0392b;font-size:11px;margin-bottom:4px">※ 신규 등록건은 먼저 [저장] 한 뒤 다시 열어서 첨부하세요.</div>'}
     <table style="border-collapse:collapse;width:100%">${rows}</table>
     <div id="qcf-msg" style="font-size:11px;margin-top:4px"></div></div>`;
}
function qcFileBoxBind(root,f,reload){
  const API=API_BASE;
  const q=s=>root.querySelector(s), qa=s=>[...root.querySelectorAll(s)];
  const msg=(t,ok)=>{const e=q('#qcf-msg');if(e)e.innerHTML=`<span style="color:${ok?'#1c7c3a':'#c0392b'}">${esc(t)}</span>`;};
  const id=f&&f.id;
  if(!id){qa('.qcf-file').forEach(el=>el.disabled=true);return;}
  const kb=n=>n>=1048576?(n/1048576).toFixed(1)+'MB':Math.max(1,Math.round(n/1024))+'KB';
  const paint=async()=>{
    try{
      const d=await (await fetch(`${API}/api/qc/error/files?id=${id}`)).json();
      QC_SLOTS.forEach(s=>{
        const info=(d.files||{})[s.k]||{}, cur=q(`.qcf-cur[data-slot="${s.k}"]`), del=q(`.qcf-del[data-slot="${s.k}"]`);
        if(!cur)return;
        if(info.doc_id){
          cur.innerHTML=`<a href="${API}/api/doc/download?src=doc&key=${info.doc_id}" target="_blank"
             title="${esc(info.filename)} · ${kb(info.size)} · ${esc(info.user)} ${esc(info.dt)}">${esc(info.filename)}</a>
             <span style="color:#7a8aa0">(${kb(info.size)})</span>`;
          if(del)del.disabled=false;
        }else{cur.textContent='—';if(del)del.disabled=true;}
      });
    }catch(e){msg('첨부 조회 실패',false);}
  };
  qa('.qcf-file').forEach(el=>el.onchange=async()=>{
    const fl=el.files&&el.files[0]; if(!fl)return;
    const fd=new FormData();
    fd.append('file',fl); fd.append('id',id); fd.append('slot',el.dataset.slot); fd.append('user','웹사용자');
    msg('업로드 중…',true); el.disabled=true;
    try{
      const r=await fetch(`${API}/api/qc/error/file_upload`,{method:'POST',body:fd});
      const d=await r.json();
      if(d.ok){msg(`✔ ${d.filename} 첨부 완료`,true);el.value='';await paint();}
      else msg(d.detail||d.errors||'업로드 실패',false);
    }catch(e){msg('업로드 실패: '+(e&&e.message||e),false);}
    finally{el.disabled=false;}
  });
  qa('.qcf-del').forEach(b=>b.onclick=async()=>{
    if(!confirm('이 첨부파일을 삭제하시겠습니까?'))return;
    b.disabled=true;
    try{
      const d=await (await fetch(`${API}/api/qc/error/file_delete`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:id,slot:b.dataset.slot})})).json();
      if(d.ok){msg('✔ 삭제되었습니다.',true);await paint();}
      else msg(d.errors||'삭제 실패',false);
    }catch(e){msg('삭제 실패',false);}
  });
  paint();
}
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

/* 품질 ③: 수입검사(IQC)조회 — 레거시 w_qa_input_160(자재입고검사관리)
   ★2026-09-01 교체: 종전 이 화면은 w_qa_cust_iqc(QA_T_CUST_IQC_HEAD/DTL) 읽기전용이었으나
     실제로 쓰는 것은 **자재입고검사**(유검사품 입고대기 → 검사완료 → 입고확정)라
     대표 지시로 이 메뉴에 담는다. 구 조회화면·API(/api/qc/iqc/*)는 사용처가 없어졌다.
   구현 = SCREEN.matinsp (아래) 위임. */
SCREEN.qciqc=(c)=>SCREEN.matinsp(c);

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


/* ===== 자재입고검사관리 (레거시 w_qa_input_160) — 2026-09-01 신설 =====
   유검사품은 세트입고 시 '입고대기(30)' 로 멈추고 재고파생·사급소진이 보류된다.
   여기서 [검사완료] 하면 30→90 + 재고파생 + 사급소진(입고 시점과 동일 처리).
   ★분석 정본 = _legacy_analysis/QA_INPUT_160_IQC_ANALYSIS.md
   ※UI 는 CLAUDE.md §3 준수 — 아이콘 없음 · 헤더 가운데정렬 · 툴바 한 줄 · 표만 내부스크롤 */
SCREEN.matinsp=(host)=>{
  const API=API_BASE;
  const d2s=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const date2ymd=s=>{s=String(s||'');return s.length===10?s.slice(2).replace(/-/g,''):'';};   // YYYY-MM-DD→YYMMDD
  const ymd2disp=s=>{s=String(s||'');return s.length===6?`${s.slice(0,2)}/${s.slice(2,4)}/${s.slice(4,6)}`:(s||'');};
  const nfq=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const TAG={'2':'바코드','3':'장부'};
  const ST={'30':'입고대기','40':'검사중','90':'검사완료','99':'반품'};
  const st={rows:[],sel:new Set(),msg:'',busy:false,sortK:'',sortA:false};

  const today=new Date(); const from=new Date();      // ★기본 = 당일(레거시 160 동일)
  host.innerHTML=`
  <div style="display:flex;flex-direction:column;height:100%">
    <div style="flex:0 0 auto">
      <div class="page-title">수입검사(IQC)
        <span style="font-size:12px;color:var(--muted);font-weight:400">유검사품 입고대기 → 검사완료 → 자재 입고확정</span></div>
      <div class="page-sub">세트입고 <b>유검사품</b>은 입고 시 <b>입고대기</b>로 멈추고 재고에 잡히지 않습니다.
        여기서 <b>검사완료</b>해야 자도번 재고파생·협력사 사급소진이 반영됩니다. 레거시 <code>w_qa_input_160</code></div>
      <div class="toolbar" style="display:flex;flex-wrap:nowrap;align-items:center;gap:6px;overflow-x:auto">
        <label style="white-space:nowrap">입고기간</label>
        <input type="date" id="mi-f" class="inp" style="width:140px;min-width:140px" value="${d2s(from)}">
        <span>~</span>
        <input type="date" id="mi-t" class="inp" style="width:140px;min-width:140px" value="${d2s(today)}">
        <label style="white-space:nowrap;margin-left:4px">거래처</label>
        <input id="mi-c" class="inp" style="width:110px;min-width:110px" placeholder="코드/이름">
        <label style="white-space:nowrap">자도번</label>
        <input id="mi-i" class="inp" style="width:120px;min-width:120px" placeholder="도번">
        <label style="white-space:nowrap">검사여부</label>
        <select id="mi-s" class="inp" style="width:100px;min-width:100px">
          <option value="30" selected>입고대기</option>
          <option value="90">검사완료</option>
          <option value="">전체</option>
        </select>
        <button class="btn" id="mi-q">조회</button>
        <button class="btn primary" id="mi-ok">검사완료</button>
        <button class="btn" id="mi-no">검사취소</button>
        <span id="mi-msg" style="margin-left:8px;font-size:12px;color:var(--muted);white-space:nowrap"></span>
      </div>
    </div>
    <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto;margin-top:6px">
      <table class="tbl" id="mi-tbl">
        <thead><tr>
          <th style="width:34px" class="center"><input type="checkbox" id="mi-all"></th>
          <th class="center">상태</th><th class="center">검사일시</th><th class="center">검사자</th>
          <th class="center">입고일자</th><th class="center">입고SEQ</th><th class="center">입고구분</th>
          <th class="center">거래처</th><th class="center">자도번</th><th class="center">품명</th>
          <th class="center">입고수량</th><th class="center">SET바코드</th><th class="center">재고파생</th>
        </tr></thead>
        <tbody id="mi-b"><tr><td colspan="13" class="empty">조회를 누르세요.</td></tr></tbody>
        <tfoot><tr style="position:sticky;bottom:0;background:#eef3fa;font-weight:600">
          <td colspan="10" class="center">합계</td>
          <td class="num" id="mi-sum"></td><td colspan="2" class="center" id="mi-cnt"></td>
        </tr></tfoot>
      </table>
    </div>
  </div>`;

  const $=s=>host.querySelector(s);
  const key=r=>r.ymd+'|'+r.seq;

  const draw=()=>{
    const b=$('#mi-b');
    if(!st.rows.length){b.innerHTML=`<tr><td colspan="13" class="empty">조회 결과 없음</td></tr>`;
      $('#mi-sum').textContent='';$('#mi-cnt').textContent='';return;}
    b.innerHTML=st.rows.map(r=>{
      const k=key(r), on=st.sel.has(k), done=r.stat==='90';
      return `<tr data-k="${esc(k)}" style="${on?'background:#eaf3ff':''}">
        <td class="center"><input type="checkbox" class="mi-ck" data-k="${esc(k)}"${on?' checked':''}></td>
        <td class="center" style="color:${done?'#1c7c3a':'#c0392b'};font-weight:600">${esc(ST[r.stat]||r.stat)}</td>
        <td class="center">${esc(r.insp_dt||'')}</td>
        <td class="center">${esc(r.insp_user||'')}</td>
        <td class="center">${esc(ymd2disp(r.ymd))}</td>
        <td class="num">${esc(r.seq)}</td>
        <td class="center">${esc(TAG[r.tag]||r.tag)}</td>
        <td title="${esc(r.cust)}">${esc(r.cust_nm||r.cust)}</td>
        <td><b>${esc(r.item)}</b></td>
        <td title="${esc(r.item_nm)}" style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.item_nm)}</td>
        <td class="num">${nfq(r.qty)}</td>
        <td class="center">${esc(r.sheet)}</td>
        <td class="center">${r.derived==='1'?'<span style="color:#1c7c3a">O</span>':'<span style="color:#999">—</span>'}</td>
      </tr>`;}).join('');
    $('#mi-sum').textContent=nfq(st.rows.reduce((s,r)=>s+Number(r.qty||0),0));
    $('#mi-cnt').textContent=`${st.rows.length}건 (선택 ${st.sel.size})`;
    b.querySelectorAll('.mi-ck').forEach(el=>el.onclick=e=>{
      const k=e.target.dataset.k;
      if(e.target.checked)st.sel.add(k);else st.sel.delete(k);
      const tr=b.querySelector(`tr[data-k="${CSS.escape(k)}"]`);
      if(tr)tr.style.background=e.target.checked?'#eaf3ff':'';     // ★부분갱신(재렌더 금지 — §3 스크롤 리셋 방지)
      $('#mi-cnt').textContent=`${st.rows.length}건 (선택 ${st.sel.size})`;
    });
  };

  const load=async()=>{
    const q=new URLSearchParams({frm:date2ymd($('#mi-f').value),to:date2ymd($('#mi-t').value),
      cust:$('#mi-c').value.trim(),item:$('#mi-i').value.trim(),stat:$('#mi-s').value});
    $('#mi-msg').textContent='조회중…';
    try{
      const r=await fetch(`${API}/api/setinsp/list?${q}`);
      const j=await r.json();
      if(!r.ok){$('#mi-msg').textContent='조회 실패: '+(j.detail||r.status);return;}
      st.rows=j.rows||[];st.sel.clear();draw();
      $('#mi-msg').textContent=st.msg||'';st.msg='';
    }catch(e){$('#mi-msg').textContent='조회 오류: '+e;}
  };

  const act=async(mode)=>{
    if(st.busy)return;
    const items=st.rows.filter(r=>st.sel.has(key(r))).map(r=>({ymd:r.ymd,seq:r.seq}));
    if(!items.length){alert('처리할 항목을 선택하세요.');return;}
    const nm=mode==='complete'?'검사완료':'검사취소';
    const warn=mode==='complete'
      ? `선택 ${items.length}건을 검사완료 처리합니다.\n자도번 재고가 생기고 협력사 사급이 차감됩니다.\n진행할까요?`
      : `선택 ${items.length}건을 검사취소합니다.\n생성된 재고·사급 기록이 제거되고 입고대기로 돌아갑니다.\n진행할까요?`;
    if(!confirm(warn))return;
    st.busy=true;$('#mi-msg').textContent=nm+' 처리중…';
    try{
      const r=await fetch(`${API}/api/setinsp/${mode}`,{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({items})});
      const j=await r.json();
      if(!r.ok){alert(nm+' 실패: '+(j.detail||JSON.stringify(j)));return;}
      const sk=(j.skipped||[]);
      st.msg=`${nm} ${j.done}건`+(mode==='complete'?` · 재고 ${j.ledger_posted}행`:` · 재고 ${j.ledger_removed}행 제거`)
             +(sk.length?` · 건너뜀 ${sk.length}건`:'');
      if(sk.length)alert('처리하지 못한 항목:\n'+sk.join('\n'));
      await load();
    }catch(e){alert(nm+' 오류: '+e);}
    finally{st.busy=false;}
  };

  $('#mi-q').onclick=load;
  $('#mi-ok').onclick=()=>act('complete');
  $('#mi-no').onclick=()=>act('cancel');
  $('#mi-all').onclick=e=>{
    st.sel.clear();
    if(e.target.checked)st.rows.forEach(r=>st.sel.add(key(r)));
    draw();
  };
  host.querySelectorAll('#mi-c,#mi-i').forEach(el=>el.addEventListener('keydown',ev=>{if(ev.key==='Enter')load();}));
  load();
};
