// ═══════════════════════════════════════════════════════════════════════════
// 생산계획업로드(검토) — 레거시 w_pr_plan_020 식 단계별 실행 화면
//
// ★현행 「생산계획업로드」(screens.prod.js:639 SCREEN.planupload)는 무변경.
//   이 화면은 사본이며 백엔드도 별도(/api/planrev/*, backend/routers/planrev.py).
//   조회·필터·업로드는 현행과 같은 API(/api/plan/list·/api/plan/upload)를 쓴다.
//
// 레거시 모양: 단계 버튼을 순서대로 누르고, 각 버튼 아래 녹색박스에 완료시각(HH:MM:SS).
//   별도 「생산계획일괄작업」 버튼이 전 단계를 자동 실행.
// 웹 확장: 실패=빨강(툴팁에 사유) · 선행이 더 최신=주황(다시 실행 권장) · 실행중=파랑.
//
// ⚠ 두 화면이 같은 nx 산출테이블에 쓴다 → 백엔드 applock 이 동시실행을 막는다(409).
// ═══════════════════════════════════════════════════════════════════════════
SCREEN.planuploadrev=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  // line·sched 는 화면에서 뺐지만(불필요) 서버 파라미터는 빈값으로 유지 — /api/plan/list 무변경
  let F={from:iso(T),to:iso(new Date(T.getTime()+30*864e5)),line:'',sched:'',wo:'',model:'',cr:''};
  let data={dates:[],rows:[],wo_count:0,sum_qty:0,__init:1}, loading=false, msg='', upcr='C', upfile=null;

  // ── 진행 팝업 (레거시 w_progress 재현) ───────────────────────────────────
  //   레거시: 「생산계획UPLOAD 오류체크 중…1236/4193 / 잠시만 기다려 주십시요…」 + 진행바 2줄
  //   단계별 실행은 서버가 한 방에 끝내므로 실제 진척(n/N)을 못 받는다 →
  //   ★과거 소요시간(nx.plan_job_log.elapsed_sec) 으로 예상시간을 잡고 경과/잔여를 보여준다.
  //   ⚠ document.body 에 붙인다(규칙 §3 — .content 안이면 조상 transform 때문에 잘림)
  let PG=null;
  const pgOpen=(title,estSec)=>{
    pgClose();
    const el=document.createElement('div');
    el.id='planrev-progress';
    el.style.cssText='position:fixed;inset:0;z-index:1250;background:rgba(20,28,40,.32);display:flex;align-items:center;justify-content:center';
    el.innerHTML=`
      <div style="min-width:430px;max-width:92vw;background:#fff;border:1px solid #9fb2c8;border-radius:6px;box-shadow:0 10px 34px rgba(0,0,0,.28);font-size:13px">
        <div style="padding:6px 10px;background:#eef3f9;border-bottom:1px solid #d5dfea;font-size:12px;color:#456">(작업 진행)</div>
        <div style="padding:16px 18px 6px">
          <div id="pg-t" style="font-weight:600;color:#1c3a63">${esc(title)}</div>
          <div style="margin-top:6px;color:#666">잠시만 기다려 주십시요<span id="pg-dot">……</span></div>
        </div>
        <div style="padding:4px 18px 16px">
          <div style="font-size:11px;color:#888;margin-bottom:4px">처리진행사항</div>
          <div style="height:15px;background:#eceff3;border:1px solid #cfd8e3;border-radius:2px;overflow:hidden">
            <div id="pg-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#1c7c3a,#37a75a);transition:width .5s linear"></div>
          </div>
          <div style="display:flex;justify-content:space-between;margin-top:5px;font-size:11px;color:#666">
            <span id="pg-el">경과 0초</span><span id="pg-rt">${estSec?('예상 '+pgHms(estSec)):'예상시간 산출중'}</span>
          </div>
        </div>
      </div>`;
    document.body.appendChild(el);
    const t0=Date.now(); let dots=0;
    PG={el,t0,est:estSec||0,timer:setInterval(()=>{
      const s=Math.floor((Date.now()-t0)/1000);
      const q=id=>el.querySelector(id);
      dots=(dots+1)%4; const d=q('#pg-dot'); if(d)d.textContent='…'.repeat(dots+1);
      const e=q('#pg-el'); if(e)e.textContent='경과 '+pgHms(s);
      if(PG.est>0){
        // 예상시간을 넘기면 95%에서 멈춰 '거의 다 됨'을 표시(가짜 100% 금지)
        const p=Math.min(95, Math.round(s/PG.est*100));
        const b=q('#pg-bar'); if(b)b.style.width=p+'%';
        const r=q('#pg-rt'); if(r)r.textContent=(s<PG.est)?('잔여 약 '+pgHms(PG.est-s)):'마무리 중…';
      }else{
        const b=q('#pg-bar'); if(b)b.style.width=((s*3)%90+5)+'%';   // 예상 없으면 흐르는 바
      }
    },500)};
  };
  const pgText=(t)=>{if(!PG)return;const e=PG.el.querySelector('#pg-t');if(e)e.textContent=t;};
  const pgClose=()=>{if(PG){clearInterval(PG.timer);try{PG.el.remove()}catch(e){}PG=null;}};
  const pgHms=(s)=>{s=Math.max(0,Math.round(s));return s<60?s+'초':(Math.floor(s/60)+'분 '+(s%60)+'초');};
  // 과거 소요시간 → 예상시간(초). 없으면 0.
  const estOf=(code)=>{const j=jobs[code]; return (j&&j.status==='OK'&&j.elapsed>0)?j.elapsed:0;};

  // ── 단계 정의 (레거시 순서) ──
  const STEPS=[
    {c:'M', no:'①', nm:'신규모델 검색·생성',  ep:'/api/planrev/step/model',    bg:'#1c47a0'},
    {c:'H', no:'②', nm:'생산계획이력생성',       ep:'/api/planrev/step/history',  bg:'#155e75'},
    {c:'L', no:'③', nm:'라인별 투입시간조정', ep:'/api/planrev/step/linetime', bg:'#b8860b'},
    {c:'K', no:'④', nm:'파트별 계획생성',     ep:'/api/planrev/step/part',     bg:'#1c7c3a'},
    {c:'T', no:'⑤', nm:'자재소요·조달 편성',  ep:'/api/planrev/step/mat',      bg:'#7a4ca0'},
    {c:'S', no:'⑥', nm:'협력사계획 편성',     ep:'/api/planrev/step/coop',     bg:'#a0521c'},
  ];
  const PREV={M:[],H:['M'],L:['M'],K:['M'],T:['K'],S:['T']};   // 낡음 판정용 선행단계
  let jobs={}, jobUp='', planRows=0, running='', srcDt={};   // srcDt={SAC:{hms,rows},RAC:{...}}

  const loadJobs=async()=>{
    try{const r=await fetch(`${API}/api/planrev/job/status`);const j=await r.json();
      jobs=j.steps||{}; jobUp=j.upload_dt||''; planRows=j.plan_rows||0; srcDt=j.src||{};}
    catch(e){jobs={};}
  };
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,line:F.line,sched:F.sched,wo:F.wo,model:F.model,cr:F.cr});
    try{const r=await fetch(`${API}/api/plan/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';data={dates:[],rows:[],wo_count:0,sum_qty:0};}
    loading=false;draw();};

  // 선행단계가 이 단계보다 나중에 성공했으면 '낡음'
  const stale=(code)=>{const me=(jobs[code]||{}).ok_dt; if(!me)return false;
    return (PREV[code]||[]).some(p=>{const q=(jobs[p]||{}).ok_dt; return q&&q>me;});};

  // ★레거시 SAC/RAC 녹색박스 — 구분별 마지막 업로드 시각(CR_FLAG 별 UPLOAD_DT)
  const srcBox=()=>{
    const one=(k)=>{const d=srcDt[k];
      const on=!!(d&&d.hms);
      return `<div title="${on?`${k} 최종 업로드 ${esc(d.dt)} · ${nf(d.rows)}행`:k+' 업로드 이력 없음'}"
        style="display:flex;align-items:center;gap:5px;padding:1px 7px;border-radius:3px;font-family:Consolas,monospace;font-size:11px;
               background:${on?'#12b886':'#f1f3f5'};color:${on?'#fff':'#adb5bd'};border:1px solid ${on?'#0f9d76':'#dde3ea'};min-width:112px">
        <b>${k}</b><span>${on?esc(d.hms):'--:--:--'}</span></div>`;};
    return `<div style="display:flex;flex-direction:column;gap:2px;margin-left:8px">${one('SAC')}${one('RAC')}</div>`;
  };
  const boxOf=(s)=>{
    const j=jobs[s.c];
    if(running===s.c)  return {bg:'#e8f0fe',fg:'#1c47a0',tx:'실행중…',ti:''};
    if(running==='ALL'&&!s.todo) return {bg:'#e8f0fe',fg:'#1c47a0',tx:'대기…',ti:'일괄작업 진행 중'};
    if(!j)             return {bg:'#f1f3f5',fg:'#adb5bd',tx:'미실행',ti:'아직 실행한 적 없습니다'};
    if(j.status!=='OK')return {bg:'#fdeaea',fg:'#c0392b',tx:'실패 '+(j.hms||''),ti:j.err||'실패'};
    if(stale(s.c))     return {bg:'#fff4e0',fg:'#b06a00',tx:'⚠ '+(j.hms||''),
                               ti:'선행단계가 이후에 다시 실행됨 — 이 단계도 다시 실행하는 것이 안전합니다'};
    return {bg:'#e6f4ea',fg:'#1c7c3a',tx:j.hms||'',
            ti:`${j.ymd||''} ${j.hms||''} · ${j.elapsed||0}초 · ${nf(j.rows||0)}행 · ${j.by||''}`};
  };

  const summary=(code,j)=>({
    M:()=>`신규모델 ${nf(j.model_rows)}건`,
    H:()=>`LG계획 ${nf(j.sale_plan_rows)}행 · 이력 ${nf(j.snap_rows)}행 (기준 ${j.base_ymd||''})`,
    K:()=>`품목계획 ${nf(j.item_lines)} · 파트계획 ${nf(j.part_lines)}(제번 ${nf(j.part_work_orders)})`,
    T:()=>`자재소요 ${nf(j.mat_lines)}(제번 ${nf(j.mat_work_orders)}) · 조달 ${nf(j.sourcing_lines)}`,
    S:()=>`자재 ${nf(j.coop_lines)}행 · 작업처 ${nf(j.coop_wc)}`
        +((j.unmapped_wc&&j.unmapped_wc.length)?`\n⚠ 미매핑 작업처 ${j.unmapped_wc.length}종: `
          +j.unmapped_wc.slice(0,8).map(x=>x.wc).join(', '):''),
  }[code]||(()=>''))();

  const runStep=async(code)=>{
    const s=STEPS.find(x=>x.c===code); if(!s||running)return;
    if(s.todo){ // 미구현 스텁도 서버 안내를 그대로 보여준다
      try{const r=await fetch(`${API}${s.ep}`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
        const j=await r.json(); alert('🚧 '+(j.detail||'미구현'));}catch(e){alert('🚧 미구현');}
      return;}
    const done=jobs[code];
    if(done&&done.status==='OK'&&!stale(code)){
      if(!confirm(`${s.no} ${s.nm}\n\n이미 ${done.hms} 에 완료된 단계입니다. 다시 실행할까요?`))return;}
    running=code; draw();
    pgOpen(`${s.no} ${s.nm} 작업 중`, estOf(code));      // ★레거시 w_progress
    try{
      const r=await fetch(`${API}${s.ep}`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({by:(typeof PERM!=='undefined'&&PERM.userId)?PERM.userId:'web'})});
      const j=await r.json();
      pgClose();
      if(!r.ok){
        const d=j.detail||JSON.stringify(j);
        if(r.status===409)      alert('⛔ 실행할 수 없습니다\n\n'+d);
        else if(r.status===400) alert('⛔ 편성 불가\n\n'+d);
        else                    alert(`❌ ${s.no} ${s.nm} 실패\n\n`+d);
      }else{
        // ★레거시: 단계 버튼마다 완료 확인창. (일괄작업은 안 띄운다 — 아래 runAll)
        const w=(j.warns&&j.warns.length)?('⚠ '+j.warns.join('\n⚠ ')+'\n\n'):'';
        alert(`${w}${s.nm} 작업을 완료했습니다.\n\n`+summary(code,j)
              +`\n\n완료시각 ${j.done_hms} · 소요 ${pgHms(j.elapsed)}`);
      }
    }catch(e){pgClose();alert('❌ 실행 실패: '+e);}
    running=''; await loadJobs(); draw();
  };

  const runAll=async()=>{
    if(running)return;
    if(!confirm('생산계획 일괄작업\n\n①신규모델 → ②생산계획이력생성 → ③라인별 투입시간조정 → ④파트별 → ⑤자재소요·조달 → ⑥협력사\n'
      +'를 순차 실행합니다.\n\n'
      +'수 분 걸릴 수 있습니다. 진행할까요?'))return;
    running='ALL'; draw();
    // 예상시간 = 각 단계 과거 소요의 합(없으면 0 → 흐르는 바)
    const estAll=['M','H','L','K','T','S'].reduce((a,c)=>a+estOf(c),0);
    pgOpen('생산계획 일괄작업 진행 중', estAll);
    // ★일괄은 단계별 확인창을 띄우지 않는다(레거시 동일). 대신 팝업 문구로 현재 단계를 알린다.
    //   서버가 한 요청으로 처리하므로 실제 단계 전환은 job/status 폴링으로 감지한다.
    let poll=setInterval(async()=>{
      try{const q=await fetch(`${API}/api/planrev/job/status`);const st=(await q.json()).steps||{};
        const cur=['S','T','K','L','H','M'].find(c=>st[c]&&st[c].status==='OK'&&st[c].ok_dt);
        const nextNm={M:'② 생산계획이력생성',H:'③ 라인별 투입시간조정',L:'④ 파트별 계획생성',
                      K:'⑤ 자재소요·조달 편성',T:'⑥ 협력사계획 편성'}[cur];
        if(nextNm)pgText('일괄작업 — '+nextNm+' 진행 중');
      }catch(e){}
    },5000);
    try{
      const r=await fetch(`${API}/api/planrev/compose_all`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({by:(typeof PERM!=='undefined'&&PERM.userId)?PERM.userId:'web'})});
      const j=await r.json();
      clearInterval(poll); pgClose();
      if(!r.ok) alert('❌ 일괄작업 중단\n\n'+(j.detail||JSON.stringify(j)));
      else alert(`생산계획 일괄작업을 완료했습니다.\n\n`
        +(j.steps||[]).map(s=>`  ${s.name}   ${s.done_hms}   ${pgHms(s.elapsed)}`).join('\n')
        +`\n\n품목 ${nf(j.item_lines)} · 파트 ${nf(j.part_lines)} · 자재 ${nf(j.mat_lines)} · 조달 ${nf(j.sourcing_lines)}`
        +`\n총 소요 ${pgHms(j.elapsed)}`);
    }catch(e){clearInterval(poll);pgClose();alert('❌ 일괄작업 실패: '+e);}
    running=''; await loadJobs(); draw();
  };

  const doUpload=async()=>{
    if(!upfile){alert('업로드할 엑셀 파일을 선택하세요.');return;}
    pgOpen('생산계획UPLOAD 처리 중', 0);
    const b64=await new Promise(res=>{const fr=new FileReader();fr.onload=()=>res(fr.result);fr.readAsDataURL(upfile);});
    try{const r=await fetch(`${API}/api/plan/upload`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cr:upcr,b64})});
      const j=await r.json();
      pgClose();
      if(j.ok){alert(`생산계획 UPLOAD 작업을 완료했습니다.\n\nUPLOAD 건수=${nf(j.total)}\n신규 ${nf(j.inserted)} · 갱신 ${nf(j.updated)} (구분 ${j.cr})`);
        upfile=null;await loadJobs();load();return;}
      alert('업로드 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){pgClose();alert('업로드 실패: '+e);}
    msg='';draw();};

  const draw=()=>{
    const dates=data.dates||[];
    const canW=(typeof PERM!=='undefined')?PERM.canEdit('planupload'):true;
    c.innerHTML=`
     <div class="page-title">🧪 생산계획업로드(검토) <span style="font-size:12px;color:var(--muted);font-weight:400">레거시 w_pr_plan_020 식 단계별 실행 — 검토용</span></div>
     <div class="page-sub">현행 「생산계획업로드」와 <b>병행 운영</b>합니다. 편성 로직은 동일(사본)이고 <b>실행 방식만</b> 단계별로 바꾼 화면입니다.
       단계 버튼을 순서대로 누르면 각 버튼 아래 <b>완료시각</b>이 표시됩니다. BOM이 바뀌면 <b>④→⑤</b>만 다시 실행하면 됩니다.
       <span style="color:#c0392b">⚠ 현행 화면과 <b>동시에</b> 편성하지 마세요(같은 테이블 사용 — 서버가 차단합니다).</span></div>
     <div class="toolbar">
       <label class="tl">계획기간</label><input class="inp" type="date" id="p-from" value="${F.from}"> ~ <input class="inp" type="date" id="p-to" value="${F.to}">
       <label class="tl">W/O</label><input class="inp" id="p-wo" value="${esc(F.wo)}" style="width:100px">
       <label class="tl">모델</label><input class="inp" id="p-model" value="${esc(F.model)}" style="width:120px">
       <label class="tl">구분</label><select class="inp" id="p-cr"><option value=""${F.cr===''?' selected':''}>전체</option><option value="C"${F.cr==='C'?' selected':''}>C</option><option value="R"${F.cr==='R'?' selected':''}>R</option></select>
       <button class="btn" id="p-search">🔍 조회</button>
     </div>
     ${canW?`
     <div class="toolbar" style="margin-top:2px">
       <label class="tl">업로드</label><select class="inp" id="p-upcr"><option value="C"${upcr==='C'?' selected':''}>C(SAC)</option><option value="R"${upcr==='R'?' selected':''}>R(RAC)</option></select>
       <input type="file" id="p-file" accept=".xls,.xlsx" style="width:190px" title="파일명에 sac/rac 가 있으면 구분이 자동 선택됩니다">
       <button class="btn" id="p-upload" style="background:#1c47a0;color:#fff"${running?' disabled':''}>📅 생산계획UPLOAD</button>
       ${srcBox()}
       <div class="spacer"></div>
       <span class="rowcount" style="font-size:11px">계획원본 <b>${nf(planRows)}</b>행</span>
     </div>
     <div style="margin-top:6px;padding:9px 11px;background:#fbfcfe;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
       <div style="display:flex;gap:7px;align-items:flex-start;flex-wrap:wrap">
        <div style="display:flex;flex-direction:column;gap:3px;min-width:152px">
          <button class="btn" id="p-all"${running?' disabled':''}
            style="background:#c0392b;color:#fff;font-size:12px;padding:6px 9px;white-space:nowrap">⚡ 생산계획 일괄작업</button>
          <div style="text-align:center;font-size:11px;color:var(--muted)">${running==='ALL'?'실행 중… (수 분)':'①②④⑤⑥ 순차'}</div>
        </div>
        <div style="width:1px;background:var(--line-2,#c9d3e0);align-self:stretch;margin:0 5px"></div>
        ${STEPS.map(s=>{const b=boxOf(s);const dis=(running&&!s.todo)?' disabled':'';
          return `<div style="display:flex;flex-direction:column;gap:3px;min-width:136px">
            <button class="btn p-step" data-c="${s.c}"${dis}
              style="background:${s.todo?'#e9ecef':s.bg};color:${s.todo?'#868e96':'#fff'};font-size:12px;padding:6px 9px;text-align:left;white-space:nowrap"
              title="${s.todo?'미구현 — 리드타임 당김 이식 대기':s.no+' 실행'}">${s.no} ${esc(s.nm)}${s.todo?' <span style="font-size:10px">(준비중)</span>':''}</button>
            <div title="${esc(b.ti)}" style="background:${b.bg};color:${b.fg};border:1px solid ${b.fg}44;border-radius:4px;
                 text-align:center;font-size:12px;font-family:Consolas,monospace;padding:3px 0;cursor:default">${esc(b.tx)}</div>
          </div>`;}).join('')}
       </div>
       <div style="margin-top:6px;font-size:11px;color:var(--muted)">
         ③은 리드타임 당김이 미구현이라 건너뜁니다(검토 후 별도 작업). ·
         <span style="color:#b06a00">주황</span>=선행단계가 이후 재실행됨(다시 실행 권장) ·
         <span style="color:#c0392b">빨강</span>=실패(박스에 마우스를 올리면 사유)
       </div>
     </div>`:`<div class="toolbar" style="margin-top:2px"><span style="color:#c0392b;font-size:12px">🔒 편성 권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span></div>`}
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="toolbar" style="margin-top:2px"><span class="rowcount">WO <b>${nf(data.wo_count)}</b> · 계획수량합 <b>${nf(data.sum_qty)}</b> · 일자 ${dates.length}개</span></div>
     <div class="grid-wrap" style="max-height:calc(100vh - 420px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr>
       <th>라인</th><th>WORK-ORDER</th><th>모델</th><th>그룹</th><th class="num">Total</th><th class="num">잔량</th>${dates.map(d=>`<th class="num">${dcol(d)}</th>`).join('')}</tr></thead>
      <tbody>${loading?spinRow(6+dates.length):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td class="center">${esc(r.line)}</td><td><b>${esc(r.wo)}</b></td>
        <td class="bcap" title="${esc(r.model)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.model)}</td>
        <td class="center">${esc(r.sched)}</td><td class="num">${nf(r.total)}</td><td class="num">${nf(r.remain)}</td>
        ${dates.map(d=>{const v=(r.days&&r.days[d])||0;return `<td class="num"${v?'':' style="color:#dfe6ef"'}>${v?nf(v):'·'}</td>`;}).join('')}</tr>`).join(''):`<tr><td colspan="${6+dates.length}" class="empty">${data.__init?'조회 조건을 확인하고 🔍조회 를 누르세요.':'조회 결과 없음 — 조건을 바꾸거나 엑셀을 업로드하세요.'}</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#p-search').onclick=()=>{F.from=g('#p-from').value;F.to=g('#p-to').value;
      F.wo=g('#p-wo').value;F.model=g('#p-model').value;F.cr=g('#p-cr').value;load();};
    if(canW){
      const uc=g('#p-upcr'); if(uc)uc.onchange=e=>upcr=e.target.value;
      const uf=g('#p-file'); if(uf)uf.onchange=e=>{
        upfile=e.target.files[0]||null;
        // ★파일명으로 SAC/RAC 자동판정(레거시 동일 기준): lg_sac→C, lg_rac→R
        if(upfile){const fn=(upfile.name||'').toLowerCase();
          const hit=/rac/.test(fn)?'R':(/sac/.test(fn)?'C':'');
          if(hit&&hit!==upcr){upcr=hit;const sel=g('#p-upcr');if(sel)sel.value=hit;
            msg=`파일명에서 ${hit==='C'?'SAC':'RAC'} 로 자동 판정했습니다 — ${upfile.name}`;draw();}
          else if(!hit){msg=`⚠ 파일명에 sac/rac 가 없어 구분을 자동판정하지 못했습니다 — 드롭다운을 확인하세요.`;draw();}
        }};
      const ub=g('#p-upload'); if(ub)ub.onclick=doUpload;
      c.querySelectorAll('.p-step').forEach(b=>b.onclick=()=>runStep(b.getAttribute('data-c')));
      const ab=g('#p-all'); if(ab)ab.onclick=runAll;
    }
    ['#p-wo','#p-model'].forEach(id=>{const el=g(id); if(el)el.onkeyup=e=>{if(e.key==='Enter')g('#p-search').click();};});
  };
  // ★진입 시 자동조회 안 함(사용자 요청 2026-08-26) — 4,564행 조회가 매번 도는 게 무겁다.
  //   단계 상태(완료시각 박스)만 먼저 채우고, 그리드는 [조회] 를 눌러야 뜬다.
  (async()=>{await loadJobs();draw();})();
};


// ═══════════════════════════════════════════════════════════════════════════
// 모델BOM 변경이력 · 제외조건  (레거시 w_pr_master_050 / w_pr_master_070)
//
// ★용도: ① 신규모델 검색·생성(M) 이 만든 (모델→도번) 조합을 확인하고,
//        잘못된 조합을 제외조건에 넣어 다음 편성부터 영구 차단한다.
//        · 삭제만  = 일회성 (다음 편성에서 다시 생성됨)
//        · 제외조건 = 영구 차단 (편성 STEP M 의 3중 NOT EXISTS 중 하나)
// ★쓰기는 nx 만 — 라이브 PARTNER_ERP 는 읽기전용(§1 절대규칙).
// 마스터-디테일 = 좌 모델리스트 / 우 상세. 행클릭은 부분갱신(스크롤 리셋 방지, §3).
// ═══════════════════════════════════════════════════════════════════════════
SCREEN.modelbomhist=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let tab='hist';                                  // hist | except
  let F={ymd:iso(new Date(T.getTime()-30*864e5)), model:'', item:''};
  let rows=[], models=[], sel='', loading=false, msg='', pick=new Set();

  const load=async()=>{
    loading=true;draw();
    try{
      const qs=new URLSearchParams(tab==='hist'
        ?{ymd:F.ymd,model:F.model,item:F.item,limit:500}
        :{model:F.model,item:F.item,limit:2000});
      const r=await fetch(`${API}/api/planrev/modelbom/${tab==='hist'?'hist':'except'}?${qs}`);
      const j=await r.json();
      rows=j.rows||[]; models=j.models||[];
      if(!models.some(m=>m.model===sel))sel=models.length?models[0].model:'';
      msg='';
    }catch(e){rows=[];models=[];msg='조회 실패 — '+e;}
    loading=false;pick.clear();draw();
  };

  const detailRows=()=>rows.filter(r=>r.model===sel);

  // 우측 상세 tbody 만 교체(부분갱신) — 좌측 스크롤 유지
  const detailBody=()=>{
    const d=detailRows();
    if(!d.length)return `<tr><td colspan="${tab==='hist'?9:6}" class="empty">모델을 선택하세요.</td></tr>`;
    return d.map((r,i)=>{
      const k=r.model+'|'+r.item;
      return `<tr data-k="${esc(k)}" style="cursor:pointer">
        <td class="center"><input type="checkbox" class="d-ck" data-k="${esc(k)}"${pick.has(k)?' checked':''}></td>
        <td class="center">${i+1}</td>
        <td><b style="color:#c0392b">${esc(r.item)}</b></td>
        <td class="bcap" title="${esc(r.item_desc||'')}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc(r.item_desc||'')}</td>
        ${tab==='hist'?`<td class="center">${esc(r.make_ymd||'')}</td><td class="center">${esc(r.to_ymd||'')}</td>
        <td class="num">${nf(r.use_qty)}</td><td class="center">${esc(r.wc||'')}</td>`:''}
        <td class="center">${esc(r.by||'')}</td>
        <td class="center" style="font-family:Consolas,monospace;font-size:11px">${esc(r.dt||'')}</td>
        ${tab==='hist'?`<td class="center"><span class="badge" style="background:${r.src==='웹(자동)'?'#7a4ca0':'#8aa0bd'}">${esc(r.src||'')}</span></td>`:
                       `<td class="center" style="font-size:11px;color:var(--muted)">${esc(r.win||'')}</td>`}
      </tr>`;}).join('');
  };
  const syncPick=()=>{
    const n=c.querySelector('#mb-pick'); if(n)n.textContent=pick.size;
    const a=c.querySelector('#ck-all');  if(a){const d=detailRows().length;
      a.checked=d>0&&pick.size>=d; a.indeterminate=pick.size>0&&pick.size<d;}
    // 선택행 하이라이트
    c.querySelectorAll('#mb-right tr[data-k]').forEach(tr=>{
      tr.style.background=pick.has(tr.getAttribute('data-k'))?'#fff4e0':'';});
    // 버튼 활성/개수 — 전체 재렌더 없이 해당 노드만(스크롤 유지)
    [['#b-exc',''],['#b-excd',''],['#b-del','']].forEach(([id])=>{
      const b=c.querySelector(id); if(!b)return;
      b.disabled=!pick.size;
      const sp=b.querySelector('span'); if(sp)sp.textContent=pick.size?` (${pick.size})`:'';
    });
  };
  const wireDetail=()=>{
    c.querySelectorAll('.d-ck').forEach(b=>b.onchange=e=>{
      e.stopPropagation();
      const k=e.target.getAttribute('data-k');
      if(e.target.checked)pick.add(k);else pick.delete(k);
      syncPick();
    });
    // ★행 아무데나 클릭해도 체크 토글(체크박스를 정확히 누를 필요 없게)
    c.querySelectorAll('#mb-right tr[data-k]').forEach(tr=>tr.onclick=e=>{
      if(e.target.classList.contains('d-ck'))return;      // 체크박스 직접클릭은 위에서 처리
      const k=tr.getAttribute('data-k');
      if(pick.has(k))pick.delete(k); else pick.add(k);
      const cb=tr.querySelector('.d-ck'); if(cb)cb.checked=pick.has(k);
      syncPick();
    });
    const a=c.querySelector('#ck-all');
    if(a)a.onchange=e=>{
      const d=detailRows();
      if(e.target.checked)d.forEach(r=>pick.add(r.model+'|'+r.item));
      else d.forEach(r=>pick.delete(r.model+'|'+r.item));
      c.querySelectorAll('.d-ck').forEach(b=>b.checked=pick.has(b.getAttribute('data-k')));
      syncPick();
    };
    syncPick();
  };

  const addExcept=async(drop)=>{
    if(!pick.size){alert('제외할 항목을 체크하세요.');return;}
    const items=[...pick].map(k=>{const [m,i]=k.split('|');return {model:m,item:i};});
    if(!confirm(`제외조건 ${items.length}건을 등록합니다.\n\n`
      +items.slice(0,8).map(x=>`  ${x.model} / ${x.item}`).join('\n')+(items.length>8?`\n  … 외 ${items.length-8}건`:'')
      +`\n\n★등록하면 다음 편성부터 「① 신규모델 검색·생성」에서 영구 제외됩니다.`
      +(drop?`\n★현재 생성된 웹 자동생성분(nx.model_bom)도 함께 삭제합니다.`:'')))return;
    try{
      const r=await fetch(`${API}/api/planrev/modelbom/except_add`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({items,drop_current:!!drop,by:(typeof PERM!=='undefined'&&PERM.userId)?PERM.userId:'web'})});
      const j=await r.json();
      if(!r.ok){alert('❌ '+(j.detail||JSON.stringify(j)));return;}
      alert(`제외조건 등록을 완료했습니다.\n\n등록 ${nf(j.added)}건`+(j.dropped?` · 현재분 삭제 ${nf(j.dropped)}건`:''));
      load();
    }catch(e){alert('❌ 실패: '+e);}
  };
  const delExcept=async()=>{
    if(!pick.size){alert('해제할 항목을 체크하세요.');return;}
    const items=[...pick].map(k=>{const [m,i]=k.split('|');return {model:m,item:i};});
    if(!confirm(`제외조건 ${items.length}건을 해제합니다.\n다시 신규모델생성 대상이 됩니다.`))return;
    try{
      const r=await fetch(`${API}/api/planrev/modelbom/except_del`,{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({items})});
      const j=await r.json();
      if(!r.ok){alert('❌ '+(j.detail||JSON.stringify(j)));return;}
      alert(`제외조건 ${nf(j.deleted)}건을 해제했습니다.`);load();
    }catch(e){alert('❌ 실패: '+e);}
  };

  const draw=()=>{
    const dd=detailRows();
    c.innerHTML=`
     <div class="page-title">🧪 모델BOM 변경이력·제외조건 <span style="font-size:12px;color:var(--muted);font-weight:400">레거시 w_pr_master_050 / 070 — 검토용</span></div>
     <div class="page-sub">「① 신규모델 검색·생성」이 만든 <b>모델→도번</b> 조합을 확인하고, 잘못된 조합을 <b>제외조건</b>에 넣습니다.
       <b style="color:#c0392b">삭제만 하면 다음 편성에서 다시 생성</b>되고, <b style="color:#1c7c3a">제외조건은 영구 차단</b>됩니다.</div>
     <div class="toolbar">
       <button class="btn${tab==='hist'?' on':''}" id="t-hist" style="${tab==='hist'?'background:#1c47a0;color:#fff':''}">📋 변경이력</button>
       <button class="btn${tab==='except'?' on':''}" id="t-exc" style="${tab==='except'?'background:#1c47a0;color:#fff':''}">🚫 제외조건</button>
       <div style="width:12px"></div>
       ${tab==='hist'?`<label class="tl">기준일자</label><input class="inp" type="date" id="f-ymd" value="${F.ymd}">`:''}
       <label class="tl">모델</label><input class="inp" id="f-model" value="${esc(F.model)}" style="width:170px" placeholder="모델명 일부">
       <label class="tl">도번</label><input class="inp" id="f-item" value="${esc(F.item)}" style="width:140px" placeholder="도번 일부">
       <button class="btn" id="f-go">🔍 조회</button>
       <div class="spacer"></div>
       <span class="rowcount">모델 <b>${nf(models.length)}</b> · 행 <b>${nf(rows.length)}</b> · 선택 <b id="mb-pick">${pick.size}</b></span>
     </div>
     <div class="toolbar" style="margin-top:2px;gap:6px">
       ${tab==='hist'
         ?`<span style="font-size:11px;color:var(--muted);padding:0 4px">선택한 조합을</span>
           <button class="btn" id="b-exc" style="background:#c0392b;color:#fff"${pick.size?'':' disabled'}>🚫 제외조건 등록<span style="opacity:.8">${pick.size?` (${pick.size})`:''}</span></button>
           <span style="font-size:11px;color:var(--muted)">또는</span>
           <button class="btn" id="b-excd" style="background:#8a3020;color:#fff"${pick.size?'':' disabled'}
             title="제외조건 등록 + 지금 만들어진 웹 자동생성분(nx.model_bom)도 함께 삭제">🚫 제외 + 현재분 삭제<span style="opacity:.8">${pick.size?` (${pick.size})`:''}</span></button>
           <div class="spacer"></div>
           <span style="font-size:11px;color:var(--muted)">${pick.size?`<b style="color:#c0392b">${pick.size}건 선택됨</b> — 등록하면 다음 편성부터 제외`:'행을 클릭해 선택하세요 (행 아무데나 클릭)'}</span>`
         :`<span style="font-size:11px;color:var(--muted);padding:0 4px">선택한 제외조건을</span>
           <button class="btn" id="b-del" style="background:#1c7c3a;color:#fff"${pick.size?'':' disabled'}>↩ 해제(삭제)<span style="opacity:.8">${pick.size?` (${pick.size})`:''}</span></button>
           <div class="spacer"></div>
           <span style="font-size:11px;color:var(--muted)">${pick.size?`<b style="color:#1c7c3a">${pick.size}건 선택됨</b> — 해제하면 다시 생성 대상`:'행을 클릭해 선택하세요 (행 아무데나 클릭)'}</span>`}
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div style="display:flex;gap:8px;align-items:stretch;flex:1;min-height:0;margin-top:4px">
       <div class="grid-wrap" style="width:330px;flex:0 0 330px;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
         <table class="tbl" style="font-size:11px"><thead><tr><th style="width:34px">SEQ</th><th>모델</th><th class="num" style="width:44px">건</th></tr></thead>
         <tbody id="mb-left">${loading?spinRow(3):(models.length?models.map((m,i)=>`
           <tr class="m-row" data-m="${esc(m.model)}" style="cursor:pointer;${m.model===sel?'background:#e7ecfa':''}">
             <td class="center">${i+1}</td><td><b>${esc(m.model)}</b></td><td class="num">${nf(m.n)}</td></tr>`).join('')
           :`<tr><td colspan="3" class="empty">조회 결과 없음</td></tr>`)}</tbody></table>
       </div>
       <div class="grid-wrap" style="flex:1;min-width:0;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
         <table class="tbl" style="font-size:11px"><thead><tr>
           <th style="width:30px" class="center"><input type="checkbox" id="ck-all" title="전체선택"></th><th style="width:34px">SEQ</th><th>품목번호</th><th>품명</th>
           ${tab==='hist'?`<th style="width:64px">적용일</th><th style="width:64px">TO적용일</th><th class="num" style="width:56px">사용수량</th><th style="width:100px">작업장/업체</th>`:''}
           <th style="width:80px">등록작업자</th><th style="width:130px">등록시각</th>
           <th style="width:${tab==='hist'?'70':'110'}px">${tab==='hist'?'출처':'등록화면'}</th></tr></thead>
         <tbody id="mb-right">${loading?spinRow(tab==='hist'?11:7):detailBody()}</tbody></table>
       </div>
     </div>`;
    const g=id=>c.querySelector(id);
    g('#t-hist').onclick=()=>{if(tab!=='hist'){tab='hist';sel='';load();}};
    g('#t-exc').onclick =()=>{if(tab!=='except'){tab='except';sel='';load();}};
    g('#f-go').onclick=()=>{const y=g('#f-ymd'); if(y)F.ymd=y.value;
      F.model=g('#f-model').value;F.item=g('#f-item').value;load();};
    ['#f-model','#f-item'].forEach(id=>{const el=g(id);if(el)el.onkeyup=e=>{if(e.key==='Enter')g('#f-go').click();};});
    // ★좌측 행클릭 = 부분갱신(전체 재렌더 금지 — 스크롤 리셋 방지, §3)
    c.querySelectorAll('.m-row').forEach(tr=>tr.onclick=()=>{
      sel=tr.getAttribute('data-m'); pick.clear();
      c.querySelectorAll('.m-row').forEach(x=>x.style.background=(x===tr)?'#e7ecfa':'');
      const rb=g('#mb-right'); if(rb){rb.innerHTML=detailBody();wireDetail();}
      const n=g('#mb-pick'); if(n)n.textContent='0';
    });
    const be=g('#b-exc');  if(be)be.onclick=()=>addExcept(false);
    const bd=g('#b-excd'); if(bd)bd.onclick=()=>addExcept(true);
    const bx=g('#b-del');  if(bx)bx.onclick=delExcept;
    wireDetail();
  };
  // 화면 루트를 flex 로(§3 — 페이지 세로스크롤 금지, 표만 내부스크롤)
  c.style.cssText='display:flex;flex-direction:column;height:100%';
  load();
};
