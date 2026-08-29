/* ===== PNC ERP screens.etc.js — 협력사/경영/시스템 SCREEN (app.js 분할, 순수이동) ===== */

/* 시스템관리 > 마감관리 — 일/월마감 현황(잠금상태) + 실행·취소. 실제 마감은 쓰기라 운영DB(읽기전용)엔 불가 → 신규DB/백엔드에서 */
SCREEN.close=(c)=>{
  /* 시스템관리 > 마감관리 — 일/월 마감 실행·해제·현황.
     ★마감 = ①그 시점 잔량을 스냅샷으로 확정(freeze) + ②잠금(그 기간 재고이동 전표 CRUD 차단).
       정본 = nx.period_close(잠금) + nx.stock_snapshot(확정) · 백엔드 /api/close/*
       ※구 /api/live/closestatus 는 레거시 임시테이블(PU_T_MONTH_STOCK_WH_DAILY, 조회시 TRUNCATE)의
         MAX() 를 '최종마감'으로 표시해 부정확 → 사용하지 않는다. */
  const API=API_BASE;
  const DOM=[['MAT','자재'],['PRD','생산'],['SAL','영업']];
  let dom='MAT', st=null, cal=null, busy=false;
  // ★입력값은 상태로 보존 — draw() 가 innerHTML 을 통째로 다시 그리므로, 값을 DOM 에서만 읽으면
  //   마감 실행 후 대상일/대상월/조회월이 오늘·이번달로 리셋된다(게이트D에서 실제 발생).
  let dday=nowCD(), dmon=nowCM(), calm=nowCM();
  const fmtYm=y=>{y=(''+(y||''));return y.length>=4?('20'+y.slice(0,2)+'-'+y.slice(2,4)):'-';};
  const fmtYmd=y=>{y=(''+(y||''));return y.length>=6?('20'+y.slice(0,2)+'/'+y.slice(2,4)+'/'+y.slice(4,6)):'-';};
  const ymIn=v=>(''+(v||'')).slice(2).replace('-','');
  const ymdIn=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  const who=()=>{try{return (PERM&&PERM.userId)||'web';}catch(e){return 'web';}};   // ★PERM 필드명은 userId — 'user' 로 읽으면 항상 'web' 이 되어 백엔드 권한게이트에 차단됨(2026-08-27 수정)
  // ★C5 권한 게이트 — 마감/해제는 회계 확정/되돌리기라 명시 권한자만. 백엔드가 최종 판정(403)하고, 여기선 오조작 방지용 UI 차단.
  // ★백엔드 _assert_can_close 와 동일 규칙(deny by default). PERM.isAdmin() 은 쓰지 않는다 —
  //   core.js currentUser() 가 미등록 사용자를 '시스템관리자'로 기본 반환(fail-open)해서 게이트가 열림.
  const canClose=()=>{try{
    const u=(typeof getUsers==='function')?getUsers().find(x=>x.id===PERM.userId):null;
    if(u&&(u.roles||[]).includes('시스템관리자'))return true;
    const pm=(PERM.perms[PERM.userId]||{})['close']; return !!(pm&&pm.edit);
  }catch(e){return false;}};
  const call=async(path,body)=>{
    if(busy)return null; busy=true;
    try{
      const r=await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json();
      if(!r.ok){alert('실패 — '+(j.detail||r.status));return null;}
      alert(j.msg||'완료'); return j;
    }catch(e){alert('통신 실패: '+e.message);return null;}
    finally{busy=false; load();}
  };
  const load=async()=>{
    try{
      const r=await fetch(API+'/api/close/status'); st=await r.json();
      const r2=await fetch(API+'/api/close/calendar?domain='+dom+'&ym='+ymIn(calm)); cal=await r2.json();
    }catch(e){ st=null; }
    draw();
  };
  const draw=()=>{
    if(!st){c.innerHTML='<div class="page-title">마감관리</div><div class="empty" style="padding:40px">마감현황을 불러오지 못했습니다 — 백엔드 확인</div>';return;}
    const asof=fmtYmd(st.asof), rows=st.rows||[];
    const domNm=(DOM.find(d=>d[0]===dom)||['',''])[1];
    let h='';
    h+='<div class="page-title">마감관리</div>';
    h+='<div class="page-sub">일/월 마감 실행·해제 · 기준일 '+esc(asof)+' · <b>마감 = 확정 + 잠금</b>(그 시점 잔량을 스냅샷으로 확정하고, 그 기간 재고이동 전표는 생성·수정·삭제 불가)</div>';
    h+='<div class="grid-wrap" style="max-height:300px;overflow:auto;margin-bottom:14px"><table class="tbl fit"><thead>';
    h+='<tr><th>영역</th><th class="center">마감유형</th><th class="center">최종 마감</th><th class="center">스냅샷</th><th class="center">마감자</th><th class="center">마감일시</th></tr></thead><tbody>';
    rows.forEach(r=>{
      const last = r.last ? esc(r.ptype==='M'?fmtYm(r.last):fmtYmd(r.last)) : '<span style="color:#c0392b">없음</span>';
      const snap = r.snap_ready ? '<span class="badge b-green">확정</span>' : '<span class="badge b-red">2단계</span>';
      h+='<tr><td><b>'+esc(r.domain_nm)+'</b></td><td class="center">'+esc(r.ptype_nm)+'</td><td class="center">'+last+'</td>'
       + '<td class="center">'+snap+'</td><td class="center">'+esc(r.user||'')+'</td>'
       + '<td class="center" style="font-size:11px">'+esc((r.dt||'').slice(0,19))+'</td></tr>';
    });
    h+='</tbody></table></div>';
    h+='<div class="page-sub" style="font-weight:700;margin:6px 0">마감 실행 / 해제</div>';
    h+='<div class="toolbar"><label class="tl">영역</label><select class="inp" id="dom">'
     + DOM.map(d=>'<option value="'+d[0]+'"'+(dom===d[0]?' selected':'')+'>'+d[1]+'</option>').join('')+'</select>';
    h+='<label class="tl" style="margin-left:8px">일마감 대상일</label><input type="date" class="inp" id="dday" value="'+dday+'" style="min-width:135px">';
    h+=canClose()?'<button class="btn" id="runday">일마감 실행</button><button class="btn ghost" id="canday">일마감 해제</button>':'<span style="color:#c0392b;font-size:12px">🔒 마감 권한 없음</span>';
    h+='<span style="width:14px"></span>';
    h+='<label class="tl">월마감 대상월</label><input type="month" class="inp" id="dmon" value="'+dmon+'" style="min-width:120px">';
    h+=(canClose()?'<button class="btn" id="runmon">월마감 실행</button><button class="btn ghost" id="canmon">월마감 해제</button>':'')+'</div>';
    h+='<div class="page-sub" style="color:var(--muted);margin:4px 0 10px">마감은 <b>순서대로</b>만 됩니다(직전 기간이 마감돼 있어야 함). 해제는 <b>최근 기간부터</b> 역순 — 후속 기간이 마감돼 있으면 거부됩니다.'
     + (st.mat_daily_max?(' · 자재 일별잔량 최신 <b>'+esc(fmtYmd(st.mat_daily_max))+'</b> (일마감은 이 데이터가 있는 날만 가능)'):'')+'</div>';
    h+='<div class="page-sub" style="font-weight:700;margin:16px 0 6px">일자별 마감 캘린더 <span style="font-weight:400;color:var(--muted)">— '+esc(domNm)+'</span></div>';
    h+='<div class="toolbar" style="border:none;padding:0;margin-bottom:8px"><label class="tl">조회월</label>'
     + '<input type="month" class="inp" id="calm" value="'+calm+'" style="min-width:120px">'
     + '<span style="font-size:12px;color:var(--muted)">마감완료 · 미마감 · 파란테두리=오늘 · 날짜 클릭 = 그 날 일마감 실행/해제</span></div>';
    h+='<div class="grid-wrap" style="overflow:auto;border:none"><table class="cal"><thead><tr>'
     + ['일','월','화','수','목','금','토'].map(d=>'<th>'+d+'</th>').join('')+'</tr></thead><tbody id="calbody"></tbody></table></div>';
    c.innerHTML=h;
    renderCal();
    const g=id=>c.querySelector(id);
    g('#dom').onchange=e=>{dom=e.target.value;load();};
    g('#dday').onchange=e=>{dday=e.target.value;};
    g('#dmon').onchange=e=>{dmon=e.target.value;};
    g('#calm').onchange=e=>{calm=e.target.value;load();};
    if(g('#runday'))g('#runday').onclick=()=>call('/api/close/run',{domain:dom,ptype:'D',period:ymdIn(dday),user:who()});
    if(g('#canday'))g('#canday').onclick=()=>{if(confirm('일마감을 해제합니다. 확정 스냅샷도 함께 제거됩니다.'))call('/api/close/cancel',{domain:dom,ptype:'D',period:ymdIn(dday),user:who()});};
    if(g('#runmon'))g('#runmon').onclick=()=>call('/api/close/run',{domain:dom,ptype:'M',period:ymIn(dmon),user:who()});
    if(g('#canmon'))g('#canmon').onclick=()=>{if(confirm('월마감을 해제합니다. 확정 스냅샷도 함께 제거됩니다.'))call('/api/close/cancel',{domain:dom,ptype:'M',period:ymIn(dmon),user:who()});};
    attachResizers(c);
  };
  const renderCal=()=>{
    const p=calm.split('-'), Y=+p[0], M=+p[1];
    const ymm=String(Y).slice(2)+String(M).padStart(2,'0');
    const closedDays=new Set((cal&&cal.closed_days)||[]), monthClosed=!!(cal&&cal.month_closed);
    const asofYmd=''+(st.asof||'');
    const first=new Date(Y,M-1,1).getDay(), days=new Date(Y,M,0).getDate();
    let cells=[]; for(let i=0;i<first;i++)cells.push('<td class="empty"></td>');
    for(let d=1;d<=days;d++){
      const ymd=ymm+String(d).padStart(2,'0');
      const closed=monthClosed||closedDays.has(ymd);
      const future=ymd>asofYmd, today=ymd===asofYmd;
      const dow=(first+d-1)%7;
      const cls=[dow===0?'sun':'',dow===6?'sat':'',closed?'closed':(future?'future':'open'),today?'today':''].filter(Boolean).join(' ');
      const mk=closed?('<div class="mk">'+(monthClosed?'월마감':'마감')+'</div>'):(future?'':'<div class="mk">미마감</div>');
      cells.push('<td class="'+cls+'" data-day="'+ymd+'"><span class="dn">'+d+'</span>'+mk+'</td>');
    }
    while(cells.length%7)cells.push('<td class="empty"></td>');
    let html=''; for(let i=0;i<cells.length;i+=7)html+='<tr>'+cells.slice(i,i+7).join('')+'</tr>';
    c.querySelector('#calbody').innerHTML=html;
    c.querySelectorAll('.cal td[data-day]').forEach(td=>td.onclick=()=>{
      const y=td.dataset.day, isC=td.classList.contains('closed');
      if(isC&&monthClosed){alert('월마감으로 잠긴 날입니다 — 월마감을 먼저 해제하세요.');return;}
      if(isC){ if(confirm(fmtYmd(y)+' 일마감을 해제합니다.'))call('/api/close/cancel',{domain:dom,ptype:'D',period:y,user:who()}); }
      else   { if(confirm(fmtYmd(y)+' 일마감을 실행합니다.'))call('/api/close/run',{domain:dom,ptype:'D',period:y,user:who()}); }
    });
  };
  c.innerHTML='<div class="page-title">마감관리</div><div class="empty" style="padding:40px">'+SPIN+'마감현황 로딩…</div>';
  load();
};

/* 시스템관리 > 권한관리 — master-detail: 우 사용자리스트 클릭 → 좌 그 사용자의 부문별/프로그램별 조회·수정 그리드 */
SCREEN.perm=(c)=>{
  const progs=allPrograms();
  const users0=getUsers();
  let selUid=(users0.find(u=>!(u.roles||[]).includes('시스템관리자'))||users0[0]||{}).id;
  const draw=()=>{
    const users=getUsers();
    c.innerHTML=`
      <div class="page-title">🔑 권한관리</div>
      <div class="page-sub">오른쪽 <b>사용자 클릭</b> → 왼쪽에 그 사용자의 <b>부문별·프로그램별 조회/수정 권한</b> · 시스템관리자=전권(설정불가) · <b>조회 해제 시 그 메뉴는 사이드바에서 숨김</b> · 기본=조회O·수정X · 저장(브라우저 임시)</div>
      <div style="display:flex;gap:14px;align-items:flex-start">
        <div style="flex:0 0 340px;width:340px">
          <div class="sum-box" style="margin-bottom:8px"><span class="k">사용자</span> <b id="ucnt">${users.length}</b> 명 <span style="color:var(--muted);font-size:12px">(클릭하여 선택)</span></div>
          <div class="toolbar" style="margin-bottom:6px"><input class="inp" id="q" placeholder="이름·ID·부서 검색" style="width:100%"></div>
          <div class="grid-wrap" style="max-height:560px;overflow:auto"><div id="ulist"></div></div>
        </div>
        <div style="flex:1 1 auto;min-width:0" id="detail"></div>
      </div>`;
    const renderList=()=>{
      const q=(c.querySelector('#q').value||'').toLowerCase();
      const vis=users.filter(u=>!q||(''+u.id+u.nm+(u.dept||'')+(u.partner||'')).toLowerCase().includes(q));
      c.querySelector('#ucnt').textContent=vis.length;
      c.querySelector('#ulist').innerHTML=vis.map(u=>{const adm=(u.roles||[]).includes('시스템관리자');const on=u.id===selUid;
        return `<div class="urow" data-uid="${esc(u.id)}" style="padding:8px 10px;border-bottom:1px solid var(--line);cursor:pointer;${on?'background:#eef4ff;border-left:3px solid var(--brand,#2a6df4)':'border-left:3px solid transparent'}">
          <div style="font-weight:600">${esc(u.nm)} <span style="color:#bbb;font-weight:400;font-size:12px">${esc(u.id)}</span>${adm?' <span class="badge">전권</span>':''}${PERM.userId===u.id?' <span class="badge" style="background:#2e7d32;color:#fff;border:none">로그인</span>':''}</div>
          <div style="font-size:11px;color:var(--muted)">${esc(u.type||'')}·${esc(u.dept||u.partner||'-')} · ${esc((u.roles||[]).join('/')||'-')}</div></div>`;}).join('')||`<div class="empty" style="padding:24px">해당 사용자 없음</div>`;
      c.querySelectorAll('.urow').forEach(r=>r.onclick=()=>{selUid=r.dataset.uid;renderList();renderDetail();});
    };
    const renderDetail=()=>{
      const box=c.querySelector('#detail');
      const u=users.find(x=>x.id===selUid);
      if(!u){box.innerHTML='<div class="empty" style="padding:60px">오른쪽에서 사용자를 선택하세요.</div>';return;}
      const admin=(u.roles||[]).includes('시스템관리자');
      const pm=PERM.perms[selUid]=PERM.perms[selUid]||{};
      // ★역할(부서) 기본권한 반영 — 실제 로그인 시 권한과 동일하게 표시(자재는 자재만 체크)
      const roleHas=(sid)=>(u.roles||[]).some(r=>(ROLE_MOD[r]||[]).includes(_sid2mod(sid)));
      const effView=(sid)=>admin||(pm[sid]&&pm[sid].view!==undefined?pm[sid].view:roleHas(sid));
      const effEdit=(sid)=>admin||(pm[sid]&&pm[sid].edit!==undefined?pm[sid].edit:roleHas(sid));
      const nv=progs.filter(p=>effView(p.id)).length;
      const ne=progs.filter(p=>effEdit(p.id)).length;
      box.innerHTML=`
        <div class="sum-box" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
          <b style="font-size:15px">${esc(u.nm)}</b>
          <span style="color:var(--muted);font-size:12px">${esc(u.id)} · ${esc(u.type||'')}·${esc(u.dept||u.partner||'-')} · 역할 ${esc((u.roles||[]).join('/')||'-')}</span>
          <span style="margin-left:auto"><span class="k">조회</span> <b id="dnv">${nv}</b> · <span class="k">수정</span> <b id="dne">${ne}</b> / 전체 ${progs.length}</span>
        </div>
        <div class="toolbar">
          ${admin?'<span class="badge">시스템관리자 = 전권(설정 불가)</span>':`<button class="btn" id="psave">💾 저장</button>`}
          <div class="spacer"></div>
          <button class="btn ${PERM.userId===selUid?'':'ghost'}" id="plogin">${PERM.userId===selUid?'✅ 현재 로그인':'🔓 이 사용자로 로그인'}</button></div>
        <div class="grid-wrap" style="max-height:500px;overflow:auto"><table class="tbl fit"><thead><tr><th>부문</th><th>프로그램</th><th class="center" style="width:64px">조회</th><th class="center" style="width:64px">수정</th></tr></thead><tbody id="ptb"></tbody></table></div>`;
      const rendGrid=()=>{
        let html='';
        MODULES.forEach(m=>{const subs=m.subs||[];subs.forEach((s,idx)=>{const v=effView(s.id),e=effEdit(s.id);
          html+=`<tr>${idx===0?`<td rowspan="${subs.length}" style="background:#fafbff;font-weight:600;vertical-align:top;white-space:nowrap">${esc(m.nm)}</td>`:''}
            <td><b>${esc(s.nm)}</b> <span style="color:#ccc;font-size:11px">${esc(s.id)}</span></td>
            <td class="center"><input type="checkbox" data-p="${s.id}" data-a="view" ${v?'checked':''} ${admin?'disabled':''}></td>
            <td class="center"><input type="checkbox" data-p="${s.id}" data-a="edit" ${e?'checked':''} ${admin?'disabled':''}></td></tr>`;});});
        box.querySelector('#ptb').innerHTML=html;
        if(!admin)box.querySelectorAll('#ptb input').forEach(cb=>cb.onchange=()=>{const pid=cb.dataset.p,a=cb.dataset.a;pm[pid]=pm[pid]||{};pm[pid][a]=cb.checked;if(a==='edit'&&cb.checked)pm[pid].view=true;if(a==='view'&&!cb.checked)pm[pid].edit=false;rendGrid();updCnt();});
      };
      const updCnt=()=>{box.querySelector('#dnv').textContent=progs.filter(p=>effView(p.id)).length;box.querySelector('#dne').textContent=progs.filter(p=>effEdit(p.id)).length;};
      rendGrid();
      box.querySelector('#plogin').onclick=()=>{PERM.setUser(selUid);try{buildTree();updateHeaderUser();}catch(_){}renderList();renderDetail();};
      if(!admin){
        box.querySelector('#psave').onclick=async(ev)=>{const bt=ev.target;const t0=bt.textContent;bt.textContent='저장중…';bt.disabled=true;
          let ok=false;try{const r=await PERM.savePerms();ok=!r||r.ok!==false&&(r.status?r.ok:true);}catch(_){ok=false;}
          if(PERM.userId===selUid){try{buildTree();}catch(_){}}bt.textContent=t0;bt.disabled=false;
          alert(ok?u.nm+' 권한 저장 완료 — 서버 반영(전 PC 동일 적용).':u.nm+' 권한 로컬 저장됨(서버 저장 실패 — 네트워크 확인).');};
      }
    };
    c.querySelector('#q').onkeyup=renderList;
    renderList(); renderDetail();
  };
  draw();
};

/* 시스템관리 > 사용자관리 — 계정(ID/PW/이름/구분/부서/직책/역할복수/협력사/이메일/연락처/상태) */
SCREEN.users=(c)=>{
  // ★정본 = nx.app_user (2026-08-29). localStorage 는 더 이상 계정의 근거가 아니다.
  //   비밀번호는 서버가 내주지 않는다 — pw_set(설정여부)만 온다.
  const load=async()=>{try{const r=await fetch(API_BASE+'/api/perm/users');
    if(!r.ok)return null; const j=await r.json(); return Array.isArray(j.users)?j.users:null;}catch(e){return null;}};
  let users=[], editMode=false, loadErr='';
  const CT=['내부','협력사'], ST=['사용','정지'];
  const cols=[{f:'id',h:'ID'},{f:'pw',h:'비밀번호',pw:1},{f:'nm',h:'이름'},{f:'type',h:'구분',sel:CT},{f:'dept',h:'부서'},{f:'pos',h:'직책'},{f:'roles',h:'역할',roles:1},{f:'partner',h:'협력사'},{f:'email',h:'이메일'},{f:'tel',h:'연락처'},{f:'status',h:'상태',sel:ST}];
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">👤 사용자관리</div>
     <div class="page-sub">계정 정본 = <b>nx.app_user</b> · 비밀번호는 <b>PBKDF2 해시</b>로 저장되며 화면에 나오지 않습니다 ·
       <b>비밀번호를 비워두면 기존 비밀번호가 그대로 유지</b>됩니다(바꿀 때만 입력) ·
       계정을 지우려면 <b>상태를 '정지'</b>로 두세요(목록에서 빼는 것으로는 지워지지 않습니다) ·
       협력사 칸 = <b>거래처코드</b> · 프로그램별 권한은 「권한관리」${loadErr?` · <span class="neg">${esc(loadErr)}</span>`:''}</div>
     <div class="toolbar"><input class="inp" id="q" placeholder="ID·이름·부서·협력사">
       ${editMode?`<button class="btn" id="add">➕ 추가</button><button class="btn" id="save">💾 저장</button><button class="btn ghost" id="cancel">✖ 취소</button>`:(PERM.canEdit('users')?`<button class="btn" id="edit">✎ 수정</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc(PERM.label())})</span>`)}
       <div class="spacer"></div><span class="rowcount" id="cnt"></span></div>
     <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl fit"><thead><tr>${cols.map(cc=>`<th>${cc.h}</th>`).join('')}${editMode?'<th class="center">삭제</th>':''}</tr></thead><tbody id="tb"></tbody></table></div>`;
    const disp=(cc,u)=>{ if(cc.pw)return u.pw_set?'설정됨':'<span class="neg">미설정</span>';
      if(cc.roles)return (u.roles||[]).map(r=>`<span class="badge">${esc(r)}</span>`).join(' ');
      return esc(''+(u[cc.f]||'')); };
    const editCell=(cc,u,i)=>{
      if(cc.sel)return `<select data-i="${i}" data-f="${cc.f}">${cc.sel.map(o=>`<option ${u[cc.f]===o?'selected':''}>${esc(o)}</option>`).join('')}</select>`;
      if(cc.roles)return `<div style="min-width:150px">${ROLES.map(r=>`<label style="margin-right:6px;white-space:nowrap;font-size:11px"><input type="checkbox" data-i="${i}" data-role="${esc(r)}" ${(u.roles||[]).includes(r)?'checked':''}>${esc(r)}</label>`).join('')}</div>`;
      if(cc.pw)return `<input data-i="${i}" data-f="pw" type="password" value="" placeholder="비우면 유지" style="width:95px">`;
      return `<input data-i="${i}" data-f="${cc.f}" value="${esc(''+(u[cc.f]||''))}" style="width:${cc.f==='email'?150:95}px">`;
    };
    const rend=()=>{
      const q=(c.querySelector('#q').value||'').toLowerCase();
      const vis=users.map((u,i)=>({u,i})).filter(({u})=>!q||(''+u.id+u.nm+u.dept+u.partner).toLowerCase().includes(q));
      c.querySelector('#tb').innerHTML=vis.map(({u,i})=>`<tr>${cols.map(cc=>`<td>${editMode?editCell(cc,u,i):disp(cc,u)}</td>`).join('')}${editMode?`<td class="center"><button class="btn xs ghost" data-del="${i}">✕</button></td>`:''}</tr>`).join('')||`<tr><td colspan="${cols.length+1}" class="empty">없음</td></tr>`;
      if(editMode){
        c.querySelectorAll('#tb input[data-f],#tb select[data-f]').forEach(el=>el.onchange=()=>{users[+el.dataset.i][el.dataset.f]=el.value;});
        c.querySelectorAll('#tb input[data-role]').forEach(el=>el.onchange=()=>{const u=users[+el.dataset.i];u.roles=u.roles||[];const r=el.dataset.role;if(el.checked){if(!u.roles.includes(r))u.roles.push(r);}else u.roles=u.roles.filter(x=>x!==r);});
        // ★목록에서 빼도 서버는 계정을 지우지 않는다(그래야 화면이 일부만 보냈을 때 계정이 증발하지 않는다).
        //   그래서 삭제 버튼은 **상태를 '정지'** 로 바꾼다 — 실제로 로그인이 막히는 방법이다.
        c.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>{const u=users[+b.dataset.del];
          u.status=(u.status==='정지')?'사용':'정지'; rend();});
      }
      c.querySelector('#cnt').textContent=`${users.length}명 (내부 ${users.filter(u=>u.type==='내부').length}·협력사 ${users.filter(u=>u.type==='협력사').length}) · ${editMode?'✎수정중':'읽기전용'}`;
    };
    if(editMode){
      c.querySelector('#add').onclick=()=>{users.push({id:'',pw:'',nm:'',type:'내부',dept:'',pos:'',roles:['조회전용'],partner:'',email:'',tel:'',status:'사용',pw_set:false});rend();};
      c.querySelector('#save').onclick=async()=>{
        let msg='';
        try{const r=await PERM.saveUsersToServer(users); const j=await r.json();
          msg=r.ok&&j.ok?`저장되었습니다 — 신규 ${j.new} · 수정 ${j.updated} · 비밀번호 변경 ${j.pw_changed}건`
                        :`저장 실패 — ${(j&&j.detail)||'백엔드 확인 필요'}`;}
        catch(e){msg='저장 실패 — 서버에 연결하지 못했습니다.';}
        editMode=false; users=(await load())||users; draw(); alert(msg);};
      c.querySelector('#cancel').onclick=async()=>{users=(await load())||users;editMode=false;draw();};
    } else if(c.querySelector('#edit')) c.querySelector('#edit').onclick=()=>{editMode=true;draw();};
    c.querySelector('#q').onkeyup=rend;
    rend();
  };
  draw();
  // 최초 진입 시 서버에서 정본을 읽는다
  (async()=>{const u=await load();
    if(u)users=u; else loadErr='서버에서 계정을 읽지 못했습니다(권한 또는 연결 확인).';
    draw();})();
};
SCREEN.setinreq=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const yy=s=>s?s.slice(2).replace(/-/g,""):"";
  const addd=(s,n)=>{const d=new Date(s);d.setDate(d.getDate()+n);return iso(d);};
  const now=new Date();
  const ST={"00":"요청","10":"발행","20":"출발","30":"입고대기","40":"검사중","90":"입고완료","99":"반품"};
  const STCOL={"00":"#8aa0bd","10":"#2e86de","20":"#e67e22","30":"#f39c12","40":"#9b59b6","90":"#27ae60","99":"#c0392b"};
  const badge=s=>`<span style="padding:2px 7px;border-radius:4px;font-size:11px;background:${STCOL[s]||"#8aa0bd"};color:#fff">${ST[s]||s}</span>`;
  let st={rows:[],custs:[],cust:"",base:iso(now),period:2,jiknab:4,qty:{},chk:{},groups:[],sortKey:"",sortDir:1,loading:false};
  const load=async()=>{
    st.loading=true;draw();
    const to=addd(st.base,Math.max(+st.period||2,+st.jiknab||4)-1);
    try{const r=await fetch(`${API}/api/setin/list?cust=${encodeURIComponent(st.cust)}&fr=${yy(st.base)}&to=${yy(to)}&limit=2000`);
      const j=await r.json();st.rows=j.rows||[];st.custs=j.custs||[];st.qty={};st.chk={};}
    catch(e){st.rows=[];st.custs=[];}
    st.loading=false;draw();
  };
  const issue=async(cancel)=>{
    const items=[];
    (st.groups||[]).forEach(g=>{if(st.chk[g.key])g.rows.forEach(r=>items.push({sheet:r.sheet_no,qty:r.input_req_qty}));});
    if(!items.length)return alert("발행할 도번을 체크하세요.");
    try{const r=await fetch(`${API}/api/setin/issue`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items,cancel:cancel?1:0})});
      const j=await r.json();
      if(!cancel&&j.barcode){try{const iv=await(await fetch(`${API}/api/setin/invoice?barcode=${j.barcode}`)).json();openInvoice(iv);}catch(e){}}
      alert(`${j.action} 완료: ${j.count}건`);await load();}
    catch(e){alert("실패: "+e.message);}
  };
  const openInvoice=(iv)=>{
    const bc=_barcodeDataURL(iv.raw);
    const party=p=>`<table class="pt"><tr><td class="k">등록번호</td><td>${esc(p.biz)}</td></tr><tr><td class="k">상 호</td><td>${esc(p.nm)}</td></tr><tr><td class="k">대 표 자</td><td>${esc(p.owner)}</td></tr><tr><td class="k">주 소</td><td>${esc(p.addr)}</td></tr><tr><td class="k">TEL</td><td>${esc(p.tel)}</td></tr><tr><td class="k">Fax</td><td>${esc(p.fax)}</td></tr></table>`;
    const items=iv.rows.map((x,i)=>`<tr><td>${i+1}</td><td>${esc(x.doban)}</td><td>${esc(x.jado)}</td><td class="l">${esc(x.nm)}</td><td class="r">${won(x.qty)}</td><td>${x.insp==="1"?"유검사":""}</td><td></td></tr>`).join("");
    const copy=title=>`<div class="cp"><div class="tt">거 래 명 세 표</div><div class="sb">${title}</div>
      <div class="mt"><span>출고일자 : ${esc(iv.ymd)}</span><span>PAGE:1/1</span></div>
      <table class="pi"><tr><td class="vl">공급자</td><td>${party(iv.supplier)}</td><td class="vl">공급<br>받는자</td><td>${party(iv.buyer)}</td></tr></table>
      <table class="it"><thead><tr><th>No.</th><th>Assy P/No.</th><th>하위 P/No.</th><th>품명</th><th>수량</th><th>검사</th><th>비고</th></tr></thead>
      <tbody>${items}<tr class="tot"><td colspan="4" class="r">합 계</td><td class="r">${won(iv.total)}</td><td></td><td></td></tr></tbody></table>
      <div class="ft"><div class="bc"><img src="${bc}"><div class="bt">${esc(iv.barcode)}</div></div>
        <table class="sp"><tr><td>자재팀</td><td>품질팀</td></tr><tr><td class="bx"></td><td class="bx"></td></tr></table></div></div>`;
    const w=window.open("","_blank","width=1240,height=880");
    if(!w)return alert("팝업 차단됨 — 팝업 허용 후 다시 발행하세요.");
    w.document.write(`<html><head><title>거래명세표 ${esc(iv.barcode)}</title><meta charset="utf-8"><style>
      body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:8px;font-size:11px;color:#000}
      .wrap{display:flex;gap:10px}.cp{flex:1;border:1.5px solid #000;padding:6px}
      .tt{text-align:center;font-size:20px;font-weight:700;letter-spacing:5px}.sb{text-align:center;font-size:12px;margin:1px 0 3px}
      .mt{display:flex;justify-content:space-between;font-size:11px;margin:2px 0}
      table{border-collapse:collapse;width:100%}.pi td{border:1px solid #000;padding:1px 3px;vertical-align:middle}
      .vl{width:16px;text-align:center;font-weight:700;background:#f2f2f2;font-size:10px;line-height:1.1}
      .pt{border:none}.pt td{border:none;padding:1px 3px}.pt .k{width:54px;background:#f7f7f7;font-weight:600;white-space:nowrap}
      .it th,.it td{border:1px solid #000;padding:2px 4px;text-align:center}.it .l{text-align:left}.it .r{text-align:right}
      .it thead th{background:#eaeaea}.tot td{font-weight:700;background:#f7f7f7}
      .ft{display:flex;justify-content:space-between;align-items:flex-end;margin-top:6px}
      .bc img{height:56px;display:block}.bt{font-family:monospace;font-size:13px;font-weight:700;margin-top:2px}
      .sp{width:210px}.sp td{border:1px solid #000;text-align:center;padding:2px}.sp .bx{height:40px}
      @media print{.noprint{display:none}}</style></head>
      <body><div class="noprint" style="margin-bottom:6px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button></div>
      <div class="wrap">${copy("공급자")}${copy("공급받는자")}</div></body></html>`);
    w.document.close();
  };
  const dlab=d=>d?`${+d.slice(2,4)}/${+d.slice(4,6)}`:"";  // 260727→7/27
  const draw=()=>{
    // ── 도번 단위 그룹화 + 일자별 생산계획 ──
    const gm={};
    st.rows.forEach(r=>{const k=(r.in_cust_code||"")+"|"+r.item_code;
      if(!gm[k])gm[k]={key:k,cust:r.in_cust_code,custnm:r.custnm||r.in_cust_code,doban:r.item_code,itemnm:r.itemnm,jadolist:r.jadolist||"",jcnt:r.jcnt,insp:r.insp_flag,status:r.status,req:0,daily:{},rows:[]};
      const gg=gm[k];gg.req+=(+r.input_req_qty||0);gg.daily[r.input_ymd]=(gg.daily[r.input_ymd]||0)+(+r.input_req_qty||0);gg.rows.push(r);
      if(r.status!=="00")gg.status=r.status;});
    st.groups=Object.values(gm);
    if(st.sortKey){const k=st.sortKey,d=st.sortDir||1;st.groups.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return (nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    const days=[...new Set(st.rows.map(r=>r.input_ymd))].sort();
    const chkn=st.groups.filter(g=>st.chk[g.key]).length;
    const totreq=st.groups.reduce((a,g)=>a+g.req,0);
    const totdel=st.groups.reduce((a,g)=>a+(+((st.qty[g.key]!=null?st.qty[g.key]:g.req))||0),0);
    // 자도번 축약: 앞번호(마지막 -세그먼트 제외)가 같으면 -[1,2,3]로 묶음
    const jl=s=>{const a=(s||"").split(",").filter(Boolean);if(!a.length)return "";const m={};a.forEach(cd=>{const g2=cd.match(/^(.*)-([^-]+)$/);if(g2){(m[g2[1]]=m[g2[1]]||[]).push(g2[2]);}else{m[cd]=m[cd]||[];}});return Object.entries(m).map(([b,t])=>t.length?b+"-["+t.join(",")+"]":b).join(" · ");};
    c.innerHTML=`
     <div class="page-title">🧾 거래명세서 발행</div>
     <div class="page-sub">협력사가 요청수량에 <b>납품수량 입력 → 완성분 체크 → 송장발행</b> · 여러 도번을 하나의 <b>SET바코드</b>로 묶어 거래명세표 인쇄 · 우측=일자별 생산계획 · 레거시 <code>w_pr_outside_420</code></div>
     <div class="toolbar">
       <label class="tl">협력사</label>
       <select class="inp" id="si-cust" style="width:auto"><option value="">전체</option>
         ${st.custs.map(o=>`<option value="${esc(o.code)}" ${st.cust===o.code?"selected":""}>${esc(o.nm||o.code)} (${o.n})</option>`).join("")}</select>
       <label class="tl" style="margin-left:8px">기준일자</label><input class="inp" type="date" id="si-base" value="${esc(st.base)}">
       <label class="tl" style="margin-left:8px">기간(협력사)</label><input class="inp" id="si-period" value="${esc(st.period)}" style="width:44px;text-align:center">일
       <label class="tl" style="margin-left:6px">직납</label><input class="inp" id="si-jiknab" value="${esc(st.jiknab)}" style="width:44px;text-align:center">일
       <button class="btn" id="si-go">🔍 조회</button>
       <button class="btn" id="si-issue" style="background:#2e86de;color:#fff">🧾 송장발행 (${chkn})</button>
       <button class="btn" id="si-cancel">발행취소</button>
       ${st.loading?'<span style="color:var(--muted)">조회중…</span>':""}
     </div>
     <div class="panel"><div class="panel-h">요청 목록 — 완성된 것만 체크 후 [송장발행]</div><div class="panel-b" style="padding:0">
       <div class="grid-wrap" style="max-height:560px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th class="center"><input type="checkbox" id="si-all"></th><th data-key="custnm">작업처</th><th data-key="doban">도번</th><th data-key="itemnm">품명</th><th class="center">구분</th><th data-key="jadolist">자도번 LIST</th>
         <th class="num">LOT수량</th><th class="num">자재수량</th><th class="num">완료수량</th><th class="num" data-key="req">요청수량</th><th class="num" style="width:56px">납품수량</th>
         ${days.map(d=>`<th class="num">${dlab(d)}</th>`).join("")}<th class="center" data-key="insp">검사</th><th class="center" data-key="status">상태</th></tr></thead>
       <tbody>${st.groups.map(g=>{const ed=(g.status==="00"||g.status==="10");return `<tr>
         <td class="center"><input type="checkbox" class="si-ck" data-k="${esc(g.key)}" ${st.chk[g.key]?"checked":""} ${ed?"":"disabled"}></td>
         <td>${esc(g.custnm)}</td><td><b>${esc(g.doban)}</b></td>
         <td class="cap" style="max-width:150px;overflow:hidden;text-overflow:ellipsis" title="${esc(g.itemnm||"")}">${esc(g.itemnm||"")}</td>
         <td class="center">세트입고</td>
         <td><div style="max-width:250px;max-height:46px;overflow-y:auto;white-space:normal;word-break:break-all;line-height:1.3" title="${esc(jl(g.jadolist))}">${esc(jl(g.jadolist))}</div></td>
         <td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num qty">${won(g.req)}</td>
         <td class="num" style="background:#eafaea;width:56px"><input class="inp si-qty" data-k="${esc(g.key)}" value="${st.qty[g.key]!=null?st.qty[g.key]:g.req}" style="width:48px;text-align:right;background:#eafaea" ${ed?"":"disabled"}></td>
         ${days.map(d=>`<td class="num" style="${g.daily[d]?"background:#fff8d6":""}">${g.daily[d]?won(g.daily[d]):""}</td>`).join("")}
         <td class="center">${g.insp==="1"?'<span class="bdg sagub">검사</span>':"-"}</td>
         <td class="center">${badge(g.status)}</td></tr>`;}).join("")||`<tr><td colspan="${11+days.length+2}" style="padding:16px;color:var(--muted)">조회 결과 없음 (기준일자·기간 확인)</td></tr>`}
       <tr class="grandtot"><td></td><td>합계</td><td>${st.groups.length}건</td><td></td><td></td><td></td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">${won(totreq)}</td><td class="num">${won(totdel)}</td>${days.map(d=>`<td class="num">${won(st.groups.reduce((a,g)=>a+(g.daily[d]||0),0))}</td>`).join("")}<td></td><td></td></tr>
       </tbody></table></div></div></div>`;
    const g=id=>c.querySelector(id);
    g("#si-cust").onchange=e=>st.cust=e.target.value;
    g("#si-base").onchange=e=>st.base=e.target.value;
    g("#si-period").oninput=e=>st.period=e.target.value;
    g("#si-jiknab").oninput=e=>st.jiknab=e.target.value;
    g("#si-go").onclick=load;
    g("#si-issue").onclick=()=>issue(false);
    g("#si-cancel").onclick=()=>issue(true);
    const all=g("#si-all");if(all)all.onclick=e=>{st.groups.forEach(gg=>{if(gg.status==="00"||gg.status==="10")st.chk[gg.key]=e.target.checked;});draw();};
    c.querySelectorAll(".si-ck").forEach(x=>x.onchange=e=>{st.chk[e.target.dataset.k]=e.target.checked;const b=c.querySelector("#si-issue");if(b)b.textContent=`🧾 송장발행 (${st.groups.filter(gg=>st.chk[gg.key]).length})`;});
    c.querySelectorAll(".si-qty").forEach(x=>x.oninput=e=>{st.qty[e.target.dataset.k]=e.target.value;});
    // UI규칙7: 모든 컬럼 우측경계 드래그=너비조절 + data-key 컬럼 더블클릭=정렬
    c.querySelectorAll("thead th").forEach(th=>{addResizer(th);const k=th.dataset.key;if(k){th.style.cursor="pointer";th.title="더블클릭하여 정렬 · 우측 경계 드래그로 너비조절";th.ondblclick=()=>{st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;draw();};}});
  };
  load();
};

/* 협력사 > 거래명세서 발행 (레거시 w_pr_outside_420) — 레거시 SP_LIVE 라이브 직독 + 510창 완료배분.
   전 컬럼(Line No·자도번LIST·사급·LOT·계획·완료·요청·납품/포장/SERIAL/HEAT 입력·출하/생산실적·세트/입고대기/ASSY재고·일자별).
   완료수량=출하+완제품재고+세트/입고대기 재고배분(도번 공유풀). 발행=nx.deliv_issue 기록(라이브 미기록·하드룰). */
SCREEN.deliv420=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${+((''+s).slice(2,4))}/${+((''+s).slice(4,6))}`:s;
  // ★일자컬럼 = 레거시 420 과 동일: 일자+요일(27목), 토/일은 배경색(레거시 29토·30일 주황).
  const wlab=y=>{if(!y||(''+y).length<6)return dcol(y);const s=''+y;const dt=new Date(2000+ +s.slice(0,2),+s.slice(2,4)-1,+s.slice(4,6));return `${s.slice(4,6)}${'일월화수목금토'[dt.getDay()]}`;};
  const wkbg=y=>{if(!y||(''+y).length<6)return '';const s=''+y;const d=new Date(2000+ +s.slice(0,2),+s.slice(2,4)-1,+s.slice(4,6)).getDay();
    return d===0?' style="background:#ffd9c2"':(d===6?' style="background:#ffe9d6"':'');};
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  const ST={"00":"요청","10":"발행","90":"발행완료"}, STC={"00":"#8aa0bd","10":"#2e86de","90":"#27ae60"};
  // gubun: 'order'(주문, 기본) | 'ganpan'(일반간판) — 레거시 라디오. dnp=직납 일수. inymd=입고일자.
  // ★기준일 = 마지막 계획업로드의 일자축 첫날(planBaseIso, 2026-08-28 사용자 확정).
  //   요청수량이 계획 기준이라 당일로 잡으면 재편성 전 기준이 되어 어긋난다.
  //   ※입고일자(inymd)는 실제 입고일이므로 당일 그대로 둔다.
  let F={cust:'',from:planBaseIso(),days:2,dnp:2,inymd:iso(T),gubun:'order',item:'',part:'',sort:'doban',
         deliv:{},pack:{},serial:{},heat:{},chk:{}}, data={dates:[],rows:[],cnt:0,sum:{}}, custs=[], loading=false, busy=false, msg='';
  const toOf=()=>_isoAddDays(F.from,Math.max(1,(+F.days||5))-1);
  // ── 스티커/프린터 설정(localStorage 저장) — 레거시 스티커설정=라벨규격·프린터설정=프린터선택 대응 ──
  const LBLKEY='deliv420_label';
  const LBL=Object.assign({w:100,h:50,copies:1,printer:'(브라우저 인쇄 대화상자에서 선택)'},
    (()=>{try{return JSON.parse(localStorage.getItem(LBLKEY)||'{}');}catch(e){return {};}})());
  const saveLbl=()=>{try{localStorage.setItem(LBLKEY,JSON.stringify(LBL));}catch(e){}};
  const fetchInvoice=async(bc)=>{
    const r=await fetch(`${API}/api/partner/deliv420/invoice?barcode=${encodeURIComponent(bc)}`);
    if(!r.ok){let m='발행 명세 조회 실패';try{m=(await r.json()).detail||m;}catch(e){}throw new Error(m);}
    return r.json();};
  const loadCusts=async()=>{try{const r=await fetch(`${API}/api/partner/workcenters?src=legacy`);custs=(await r.json()).rows||[];}catch(e){custs=[];}};
  const load=async()=>{
    if(loading)return;                              // 중복요청 가드
    if(!F.cust){msg='협력사(자도번작업처)를 먼저 선택하세요.';data={dates:[],rows:[],cnt:0,sum:{}};draw();return;}
    loading=true;msg='';draw();
    // ★gigan = 근무일 기준 기간(백엔드가 to_ymd 를 근무일로 재계산·휴무만큼 자동연장). to_ymd 는 하위호환.
    const qs=new URLSearchParams({cust:F.cust,from_ymd:F.from,to_ymd:toOf(),item:F.item,matcode:F.part,gigan:Math.max(1,+F.days||2)});
    try{const r=await fetch(`${API}/api/partner/deliv420?${qs}`);data=await r.json();F.deliv={};F.pack={};F.serial={};F.heat={};F.chk={};}
    catch(e){msg='백엔드 연결 실패';data={dates:[],rows:[],cnt:0,sum:{}};}
    loading=false;draw();};
  // 선택행(체크·납품수량>0) 수집
  const collect=(rows)=>{const items=[];rows.forEach(r=>{if(F.chk[r.assy]){const dv=Number(F.deliv[r.assy]!=null?F.deliv[r.assy]:r.deliv)||0;
    items.push({assy:r.assy,deliver_qty:dv,pack_qty:Number(F.pack[r.assy]!=null?F.pack[r.assy]:r.pack)||0,serial_no:F.serial[r.assy]||'',heat_no:F.heat[r.assy]||''});}});return items;};
  const issue=async(rows)=>{
    if(busy)return; const items=collect(rows); if(!items.length)return alert('완성분(체크)을 선택하고 납품수량을 확인하세요.');
    busy=true;
    try{
      const pv=await(await fetch(`${API}/api/partner/deliv420/issue`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cust:F.cust,from_ymd:F.from,to_ymd:toOf(),gigan:Number(F.days)||2,
        base_from:data.base_from||'',base_to:data.base_to||'',items,preview:1})})).json();
      if(!pv.ok){alert(pv.msg||'발행 불가');return;}
      if(!confirm(`발행 미리보기\n건수 ${pv.count} · 총 납품수량 ${nf(pv.total_qty)}\n\n확정 발행할까요? (nx.deliv_issue 기록 · 라이브 미기록)`))return;
      const rr=await(await fetch(`${API}/api/partner/deliv420/issue`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cust:F.cust,from_ymd:F.from,to_ymd:toOf(),gigan:Number(F.days)||2,
        base_from:data.base_from||'',base_to:data.base_to||'',items,preview:0})})).json();
      if(!rr.ok){alert(rr.msg||'발행 실패');return;}
      alert(`발행 완료 · 바코드 ${rr.barcode} · ${rr.count}건 · 납품 ${nf(rr.total_qty)}\n(nx.deliv_issue 기록)`);
      // ★발행 후 자동 출력 — 레거시 납품처리 1클릭 = ①거래명세표 ②납품표 ③출하검사성적서
      //   (2026-08-27 사용자 확인). ③은 검사품(insp='1')만 나온다.
      //   ★SVC(A/S용)는 예외로 **분리 출력** + 제목에 SVC 표시(레거시 동일).
      if(rr.barcode){try{const iv=await fetchInvoice(rr.barcode);
          printSet(iv);}
        catch(e){alert('발행은 완료됐으나 인쇄 팝업 실패: '+e.message+'\n[거래명세표]/[스티커] 버튼으로 발행번호 '+rr.barcode+' 재출력 가능합니다.');}}
      await load();
    }catch(e){alert('발행 오류: '+e.message);}finally{busy=false;}
  };
  const cancelIssue=async()=>{const bc=prompt('발행취소할 바코드 번호를 입력하세요');if(!bc)return;
    try{const rr=await(await fetch(`${API}/api/partner/deliv420/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({barcode:bc.trim()})})).json();
      alert(rr.ok?`취소 ${rr.cancelled}건`:(rr.msg||'실패'));await load();}catch(e){alert('오류: '+e.message);}};
  // ── 거래명세표 인쇄 (레거시 dw_pr_outside_020_p1 서식 · 공급자=협력사/공급받는자=당사 · SET바코드 Code39) ──
  const openDelivInvoice=(iv)=>{
    if(!iv||!iv.rows||!iv.rows.length)return alert('발행 명세가 없습니다.');
    const bc=_barcodeDataURL(iv.code);          // Code39: *SET+발행번호*
    // ★레거시 거래명세표 서식(2026-08-27 실물 확인):
    //   컬럼 = No. · Assy P/No. · 하위 P/No. · 품명 · 수 량 · 검사 · 비고
    //   ·**20행 고정**(빈행 포함) · 합계행 · 하단 = SET바코드 + 자재팀/품질팀 결재란
    //   ·공급자/공급받는자 정보는 등록번호·상호·대표자·주소·TEL·Fax
    const party=p=>`<table class="pt">`
      +`<tr><td class="k">등록번호</td><td>${esc(p.biz)}</td></tr>`
      +`<tr><td class="k">상&nbsp;&nbsp;&nbsp; 호</td><td>${esc(p.nm)}</td></tr>`
      +`<tr><td class="k">대 표 자</td><td>${esc(p.owner)}</td></tr>`
      +`<tr><td class="k">주&nbsp;&nbsp;&nbsp; 소</td><td>${esc(p.addr)}</td></tr>`
      +`<tr><td class="k">TEL</td><td>${esc(p.tel)}</td></tr>`
      +`<tr><td class="k">Fax</td><td>${esc(p.fax||'')}</td></tr></table>`;
    // ★20행 초과 시 페이지 분할(2026-08-27 사용자 요청). 바코드·합계는 모든 페이지 동일.
    const ROWN=20;
    const pages=[];
    for(let s=0;s<Math.max(1,iv.rows.length);s+=ROWN) pages.push(iv.rows.slice(s,s+ROWN));
    const PN=pages.length;
    const bodyOf=(pg,pi)=>{
      const out=[];
      pg.forEach((x,i)=>{
        out.push(`<tr><td>${pi*ROWN+i+1}</td><td>${esc(x.doban)}</td><td class="l">${esc(x.sub||'')}</td>`
          +`<td class="l" title="${esc(x.nm)}">${esc(x.nm)}</td><td class="r">${nf(x.qty)}</td>`
          +`<td>${esc(x.insp||'')}</td><td>${esc(x.note||'')}</td></tr>`);
      });
      for(let i=pg.length;i<ROWN;i++)
        out.push(`<tr><td>${pi*ROWN+i+1}</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>`);
      return out.join('');
    };
    const _sv=iv.svcmark?` <span class="svcm">[${esc(iv.svcmark)}]</span>`:'';   // ★SVC 분리표시
    const copy=(title,pg,pi)=>`<div class="cp"><div class="tt">거래명세표${_sv}</div><div class="sb">${title}</div>
      <div class="mt"><span>출고일자 : ${esc(iv.ymd)}</span><span>PAGE:${pi+1}/${PN}</span></div>
      <table class="pi"><tr><td class="vl">공<br>급<br>자</td><td>${party(iv.supplier)}</td><td class="vl">공<br>급<br>받<br>는<br>자</td><td>${party(iv.buyer)}</td></tr></table>
      <table class="it"><colgroup><col style="width:26px"><col style="width:104px"><col style="width:104px"><col><col style="width:46px"><col style="width:34px"><col style="width:42px"></colgroup>
      <thead><tr><th>No.</th><th>Assy P/No.</th><th>하위 P/No.</th><th>품명</th><th>수 량</th><th>검사</th><th>비고</th></tr></thead>
      <tbody>${bodyOf(pg,pi)}<tr class="tot"><td colspan="4" class="r">합계</td><td class="r">${nf(iv.total)}</td><td colspan="2"></td></tr></tbody></table>
      <div class="ft"><div class="bc"><div class="bt">${esc(iv.barcode)}</div><img src="${bc}"></div>
        <table class="sp"><tr><td>자재팀</td><td>품질팀</td></tr><tr><td class="bx"></td><td class="bx"></td></tr></table></div></div>`;
    const w=window.open('','_blank','width=1240,height=900');
    if(!w)return alert('팝업 차단됨 — 팝업 허용 후 다시 시도하세요.');
    w.document.write(`<html><head><title>거래명세표${iv.svcmark?' ['+esc(iv.svcmark)+']':''} ${esc(iv.barcode)}</title><meta charset="utf-8"><style>
      @page{size:A4 landscape;margin:6mm}
      .svcm{color:#c00;font-weight:700}
      body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:6px;font-size:10.5px;color:#000}
      .wrap{display:flex;gap:12px}.cp{flex:1;padding:2px}
      .tt{text-align:center;font-size:19px;font-weight:700;letter-spacing:3px;text-decoration:underline}
      .sb{text-align:center;font-size:11px;margin:2px 0 4px}
      .mt{display:flex;justify-content:space-between;font-size:10.5px;margin:2px 0}
      /* ★table-layout:fixed 필수 — 없으면 브라우저가 내용에 맞춰 폭을 재배분해
         품명이 두 줄로 깨지고 행 높이가 들쭉날쭉해진다(레거시는 전 행 균일). */
      table{border-collapse:collapse;width:100%;table-layout:fixed}
      .pi{table-layout:fixed}
      .pi td{border:1px solid #000;padding:0;vertical-align:middle}
      .pi>tbody>tr>td:nth-child(2),.pi>tbody>tr>td:nth-child(4){width:calc(50% - 15px)}
      .vl{width:15px;text-align:center;font-weight:600;font-size:10px;line-height:1.15}
      .pt{border:none;table-layout:fixed}.pt td{border:1px solid #000;padding:2px 4px;height:19px}
      .pt .k{width:56px;text-align:center;white-space:nowrap;font-size:10px}
      /* 주소는 두 줄까지 허용(레거시 동일), 나머지는 한 줄 고정 */
      .pt td:not(.k){overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .pt tr:nth-child(4) td:not(.k){white-space:normal;line-height:1.25;height:30px}
      .it th,.it td{border:1px solid #000;padding:1px 3px;text-align:center;height:18px;
        overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .it .l{text-align:left}.it .r{text-align:right}
      .it thead th{font-weight:700}
      .tot td{font-weight:700}
      .ft{display:flex;justify-content:space-between;align-items:flex-end;margin-top:4px}
      .bc{border:1.5px solid #000;padding:3px 6px;min-width:210px}
      .bc img{height:34px;display:block;width:100%}
      .bt{font-family:'맑은 고딕',monospace;font-size:12px;font-weight:700;margin-bottom:2px}
      .sp{width:200px}.sp td{border:1px solid #000;text-align:center;padding:2px;font-size:10.5px}
      .sp .bx{height:34px}
      @media print{.noprint{display:none}}</style></head>
      <body><div class="noprint" style="margin-bottom:6px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button>
        <span style="margin-left:8px;color:#555;font-size:11px">${esc(iv.barcode)} · ${iv.rows.length}건 · ${PN}페이지</span></div>
      ${pages.map((pg,pi)=>`<div class="wrap"${pi?' style="page-break-before:always"':''}>${copy('공급자',pg,pi)}${copy('공급받는자',pg,pi)}</div>`).join('')}</body></html>`);
    w.document.close();
  };
  // ── ★납품표 인쇄 (레거시 2번 출력물) — 페이지당 4장(2×2) 카드형 ──
  //   레거시 실물(2026-08-27):
  //     ┌──── PNC_260806_00:05  납품표 ────┐
  //     │ 업체명   │ 대원산업              │
  //     │ 모도번   │ AJJ76418705           │
  //     │ 작업처   │ 대 원 산 업           │
  //     │ 자도번   │ AJJ76418705(1)검      │
  //     │ 입고셋트 │ 26                    │
  //     │ 납품일   │ 26/08/27(목)          │
  //     │ 입고구분 │ 세트                  │
  //     │ 표준포장수│ 26        1 / 1      │
  //     │ 생산계획 │ 26/08/26  LG 26/08/26 │
  const openDelivNote=(iv)=>{
    if(!iv||!iv.rows||!iv.rows.length)return alert('발행 명세가 없습니다.');
    const DOW='일월화수목금토';
    const ymdD=(s)=>{const d=String(s||'').replace(/\D/g,'');
      if(d.length<8)return String(s||'');
      const dt=new Date(+d.slice(0,4),+d.slice(4,6)-1,+d.slice(6,8));
      return `${d.slice(2,4)}/${d.slice(4,6)}/${d.slice(6,8)}(${DOW[dt.getDay()]})`;};
    const nd=ymdD(iv.ymd);
    // 도번 행만(하위 자재행 제외) — 납품표는 도번 단위
    const list=iv.rows.filter(x=>x.doban);
    const jl=(x)=>{const a=(x.subs||[]).slice(0,6);return a.length?a.join('<br>'):esc(x.doban)+'(1)';};
    const card=(x)=>x?`<table class="nt">
        <tr><td class="ttl" colspan="2">${esc(iv.title||'')}&nbsp;&nbsp; 납품표</td></tr>
        <tr><th>업체명</th><td class="c">${esc(iv.custnm)}</td></tr>
        <tr><th>모도번</th><td class="c big">${esc(x.doban)}</td></tr>
        <tr><th>작업처</th><td class="c big">${esc(x.wc||iv.custnm)}</td></tr>
        <tr><th>자도번</th><td class="c sm jd">${jl(x)}</td></tr>
        <tr><th>입고셋트</th><td class="c big">${nf(x.qty)}</td></tr>
        <tr><th>납품일</th><td class="c">${esc(nd)}</td></tr>
        <tr><th>입고구분</th><td class="c b">${esc(x.gubun||'세트')}</td></tr>
        <tr><th>표준포장수</th><td class="c"><span class="lf">${nf(x.pack||x.qty)}</span><span class="rt">1 / 1</span></td></tr>
        <tr><th>생산계획</th><td class="c"><span class="lf">${esc(x.plan_ymd||'')}</span><span class="rt">LG ${esc(x.lg_ymd||'')}</span></td></tr>
      </table>`:`<table class="nt blank"><tr><td class="ttl" colspan="2">${esc(iv.title||'')}&nbsp;&nbsp; 납품표</td></tr>
        ${['업체명','모도번','작업처','자도번','입고셋트','납품일','입고구분','표준포장수','생산계획']
          .map(k=>`<tr><th>${k}</th><td></td></tr>`).join('')}</table>`;
    // 4장 단위 페이지
    const PG=[]; for(let i=0;i<list.length;i+=4) PG.push(list.slice(i,i+4));
    if(!PG.length) PG.push([]);
    const w=window.open('','_blank','width=900,height=1000');
    if(!w)return alert('팝업 차단됨 — 팝업 허용 후 다시 시도하세요.');
    w.document.write(`<html><head><title>납품표${iv.svcmark?' ['+esc(iv.svcmark)+']':''} ${esc(iv.barcode)}</title><meta charset="utf-8"><style>
      @page{size:A4;margin:8mm}
      body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:0;font-size:12px;color:#000}
      .pgw{display:grid;grid-template-columns:1fr 1fr;gap:10px;page-break-inside:avoid}
      .nt{border-collapse:collapse;width:100%;table-layout:fixed;border:1.5px solid #000}
      .nt th,.nt td{border:1px solid #000;padding:3px 6px;height:22px;font-size:12px}
      .nt th{width:74px;text-align:center;font-weight:700;background:#fff}
      .ttl{text-align:center;font-weight:700;font-size:13px;height:22px;border-bottom:1.5px solid #000}
      .c{text-align:center}.big{font-size:17px;font-weight:700;letter-spacing:1px}
      .b{font-weight:700}.sm{font-size:10px}
      .jd{height:56px;vertical-align:middle;line-height:1.35}
      .lf{float:left}.rt{float:right}
      .blank td{color:#fff}
      @media print{.np{display:none}}
    </style></head><body>
      <div class="np" style="margin:0 0 10px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button>
        <span style="margin-left:8px;color:#555;font-size:12px">납품표 · ${esc(iv.custnm)} · ${list.length}건 · ${PG.length}페이지</span></div>
      ${PG.map((pg,pi)=>`<div class="pgw"${pi?' style="page-break-before:always"':''}>
         ${[0,1,2,3].map(k=>card(pg[k])).join('')}</div>`).join('')}
      </body></html>`);
    w.document.close();
  };
  // ── ★출하검사성적서 인쇄 (레거시 3번 출력물) — 페이지당 2장 ──
  //   ★검사품(insp='1')만 출력한다. 무검사는 성적서가 없다.
  //   레거시 실물: 회사명·Assy P/NO·단품 P/NO·검사일자 / 검사방법·Lot Size·측정기명·검사원
  //                / 검사항목·규격치·검사수준·X1~X5·시료수·불량수·판정
  //                / 구조외관·치수(4행) / 확인내용·특이사항·IQC판정
  const openInspSheet=(iv)=>{
    const list=(iv.rows||[]).filter(x=>x.doban&&x.insp==='검사');
    if(!list.length)return;              // 검사품 없으면 조용히 건너뜀(레거시 동일)
    const sheet=(x)=>`
      <table class="is">
        <tr><td class="tt" colspan="10">출 하 검 사 성 적 서${iv.svcmark?` <span class="svcm">[${esc(iv.svcmark)}]</span>`:''}</td>
            <th class="gj" rowspan="2">결<br>제</th><th>담당</th><th>Q.A팀장</th></tr>
        <tr><td class="bx"></td><td class="bx"></td></tr>
      </table>
      <table class="is2">
        <tr><th>회사명</th><td>${esc(iv.custnm)}</td><th>Assy P/NO</th><td>${esc(x.doban)}</td>
            <th>단품 P/NO</th><td>${esc((x.subs&&x.subs[0]||'').split('(')[0]||x.doban)}</td>
            <th>검사일자</th><td></td></tr>
        <tr><th>검사방법</th><td>보통검사</td><th>Lot Size</th><td>${nf(x.qty)} EA</td>
            <th>측정기명</th><td>VC / HG / 줄자</td><th>검사원</th><td></td></tr>
      </table>
      <table class="is3">
        <tr><th>검사항목</th><th>규격치</th><th>검사수준</th><th>X1</th><th>X2</th><th>X3</th><th>X4</th><th>X5</th><th>시료수</th><th>불량수</th><th>판정</th></tr>
        <tr><th class="v">구조외관</th><td>결함없을것</td><td>G-1 2.5</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
        ${[1,2,3,4].map(()=>`
        <tr><th class="v" rowspan="2">치수</th><td>S-1 2.5</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
        <tr><td>유외치분석</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>`).join('')}
      </table>
      <table class="is4">
        <tr><th>확 인 내 용</th><th>특 이 사 항</th><th>IQC판정</th><th>검사원</th></tr>
        <tr><td class="l sm">·검사항목 지정 유/무<br>·검사항목 검사 유/무<br>·시방항목 확인 유/무<br>·4M변경&nbsp; 확인 유/무</td>
            <td class="l sm">※ 구조·외관검사 점검항목<br>&nbsp;&nbsp; Pipe 내·외부 이물없을 것(플라이트, 면부 확인)<br>
               &nbsp;&nbsp;&nbsp;&nbsp; → 합지 세척관리 확인<br>&nbsp;&nbsp; Pipe 내·외관 찍힘, 눌림, 스크래치 없을 것.</td>
            <td></td><td></td></tr>
      </table>`;
    const PG=[]; for(let i=0;i<list.length;i+=2) PG.push(list.slice(i,i+2));
    const w=window.open('','_blank','width=900,height=1100');
    if(!w)return alert('팝업 차단됨 — 팝업 허용 후 다시 시도하세요.');
    w.document.write(`<html><head><title>출하검사성적서${iv.svcmark?' ['+esc(iv.svcmark)+']':''} ${esc(iv.barcode)}</title><meta charset="utf-8"><style>
      @page{size:A4;margin:8mm}
      .svcm{color:#c00;font-weight:700;font-size:14px;letter-spacing:0}
      body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:0;font-size:11px;color:#000}
      .sh{page-break-inside:avoid;margin-bottom:14px}
      table{border-collapse:collapse;width:100%;table-layout:fixed}
      .is td,.is th,.is2 td,.is2 th,.is3 td,.is3 th,.is4 td,.is4 th{border:1px solid #000;padding:2px 4px;height:19px;text-align:center}
      .tt{font-size:17px;font-weight:700;letter-spacing:6px;height:34px;border:none;border-bottom:none}
      .is{border:none}.is td.tt{border:none}
      .gj{width:22px;font-size:10px;line-height:1.2}
      .is th{font-weight:700}
      .bx{height:26px}
      .is2 th{width:64px;font-size:10px}
      .is3 th{font-size:10px}.is3 .v{font-weight:700}
      .is4 th{height:20px}.is4 .l{text-align:left;vertical-align:top;height:70px}
      .sm{font-size:9.5px;line-height:1.45}
      @media print{.np{display:none}}
    </style></head><body>
      <div class="np" style="margin:0 0 10px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button>
        <span style="margin-left:8px;color:#555;font-size:11px">출하검사성적서 · 검사품 ${list.length}건 · ${PG.length}페이지</span></div>
      ${PG.map((pg,pi)=>`<div${pi?' style="page-break-before:always"':''}>
         ${pg.map(x=>`<div class="sh">${sheet(x)}</div>`).join('')}</div>`).join('')}
      </body></html>`);
    w.document.close();
  };
  // ── ★납품처리 1클릭 = 3종 출력 (SVC 분리) ──
  //   레거시: 거래명세표 → 납품표 → 출하검사성적서 순으로 발행.
  //   ★예외 — SVC(A/S용)는 같은 발행번호라도 **별도 출력물**로 분리하고 제목에 「SVC」를 표시한다.
  //     판정 = 백엔드 rows[].svc (계획 LINE_NO='SVC').
  const printSet=(iv)=>{
    if(!iv||!iv.rows||!iv.rows.length)return alert('발행 명세가 없습니다.');
    const pick=(f,tag)=>{
      const rs=iv.rows.filter(f); if(!rs.length)return null;
      // 합계는 도번 행만(하위 자재행은 중복 집계 방지)
      const tot=rs.filter(x=>x.doban).reduce((s,x)=>s+(Number(x.qty)||0),0);
      return Object.assign({},iv,{rows:rs,total:tot,count:rs.length,
        title:(iv.title||'')+(tag?' '+tag:''), svcmark:tag||''});
    };
    const grp=[pick(x=>!x.svc,''), pick(x=>!!x.svc,'SVC')].filter(Boolean);
    grp.forEach(g=>{ openDelivInvoice(g); openDelivNote(g); openInspSheet(g); });
  };
  // ── 스티커(라벨) 인쇄 — 도번당 1매(설정 매수만큼) · 필드: 거래처·발행일자·도번·품명·규격·수량·SERIAL·HEAT·발행번호 + Code39 바코드 ──
  const openSticker=(iv)=>{
    if(!iv||!iv.rows||!iv.rows.length)return alert('발행 명세가 없습니다.');
    const bc=_barcodeDataURL(iv.code);
    const cp=Math.max(1,Math.min(20,+LBL.copies||1));
    const labels=[];iv.rows.forEach(x=>{for(let k=0;k<cp;k++)labels.push(x);});
    const cell=x=>`<div class="lbl">
      <div class="hd"><span class="cu">${esc(iv.custnm)}</span><span class="dt">${esc(iv.ymd)}</span></div>
      <div class="do">${esc(x.doban)}</div>
      <div class="nm" title="${esc(x.nm)}">${esc(x.nm)}${x.spec?' · '+esc(x.spec):''}</div>
      <div class="rw"><span>수량 <b>${nf(x.qty)}</b> ${esc(x.unit)}</span><span>발행번호 ${esc(iv.raw)}</span></div>
      <div class="rw"><span>SERIAL ${esc(x.serial||'-')}</span><span>HEAT ${esc(x.heat||'-')}</span></div>
      <div class="bc"><img src="${bc}"><div class="bt">${esc(iv.barcode)}</div></div></div>`;
    const w=window.open('','_blank','width=760,height=900');
    if(!w)return alert('팝업 차단됨 — 팝업 허용 후 다시 시도하세요.');
    w.document.write(`<html><head><title>스티커 ${esc(iv.barcode)} (${labels.length}매)</title><meta charset="utf-8"><style>
      @page{size:${(+LBL.w||100)}mm ${(+LBL.h||50)}mm;margin:0}
      body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:0;color:#000;background:#e9edf3}
      .lbl{width:${(+LBL.w||100)}mm;height:${(+LBL.h||50)}mm;box-sizing:border-box;padding:3mm;border:1px dashed #999;background:#fff;margin:6px auto;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden}
      .hd{display:flex;justify-content:space-between;font-size:10px;font-weight:600;border-bottom:1px solid #000;padding-bottom:1px}
      .do{font-size:17px;font-weight:800;letter-spacing:.5px;margin-top:1mm}
      .nm{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .rw{display:flex;justify-content:space-between;font-size:10px;margin-top:.5mm}.rw b{font-size:12px}
      .bc{text-align:center;margin-top:1mm}.bc img{height:12mm;max-width:100%}.bt{font-family:monospace;font-size:11px;font-weight:700}
      @media print{.noprint{display:none}.lbl{border:none;margin:0;page-break-after:always}}</style></head>
      <body><div class="noprint" style="text-align:center;padding:6px"><button onclick="window.print()">🖨️ 스티커 인쇄 (${labels.length}매 · ${(+LBL.w||100)}×${(+LBL.h||50)}mm)</button> <button onclick="window.close()">닫기</button> <span style="font-size:11px;color:#555">프린터: ${esc(LBL.printer)}</span></div>
      ${labels.map(cell).join('')}</body></html>`);
    w.document.close();
  };
  // ── 스티커설정(라벨규격·매수) / 프린터설정 — 경량 모달 ──
  const closeModal=()=>{const m=document.getElementById('d4-modal');if(m)m.remove();};
  const openModal=(html)=>{closeModal();const d=document.createElement('div');d.id='d4-modal';
    d.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:9999;display:flex;align-items:center;justify-content:center';
    d.innerHTML=`<div style="background:#fff;border-radius:10px;padding:18px 20px;min-width:320px;box-shadow:0 10px 40px rgba(0,0,0,.3);font-size:13px">${html}</div>`;
    d.onclick=e=>{if(e.target===d)closeModal();};document.body.appendChild(d);return d;};
  const openLabelSetup=()=>{
    const d=openModal(`<div style="font-weight:700;font-size:15px;margin-bottom:10px">🏷️ 스티커 라벨 설정</div>
      <label class="tl">라벨 규격</label>
      <select id="ml-preset" class="inp" style="width:100%;margin:4px 0 10px">
        <option value="">직접 입력</option><option value="100x50">100 × 50 mm</option><option value="100x30">100 × 30 mm</option>
        <option value="90x40">90 × 40 mm</option><option value="70x40">70 × 40 mm</option><option value="60x40">60 × 40 mm</option></select>
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <div><label class="tl">가로(mm)</label><input id="ml-w" class="inp" value="${esc(LBL.w)}" style="width:80px;text-align:right"></div>
        <div><label class="tl">세로(mm)</label><input id="ml-h" class="inp" value="${esc(LBL.h)}" style="width:80px;text-align:right"></div>
        <div><label class="tl">도번당 매수</label><input id="ml-c" class="inp" value="${esc(LBL.copies)}" style="width:70px;text-align:right"></div></div>
      <div style="text-align:right"><button class="btn" id="ml-cancel">취소</button> <button class="btn" id="ml-save" style="background:#2e86de;color:#fff">저장</button></div>`);
    const q=id=>d.querySelector(id);
    q('#ml-preset').onchange=e=>{const v=e.target.value;if(v){const [w,h]=v.split('x');q('#ml-w').value=w;q('#ml-h').value=h;}};
    q('#ml-cancel').onclick=closeModal;
    q('#ml-save').onclick=()=>{LBL.w=Math.max(20,+q('#ml-w').value||100);LBL.h=Math.max(15,+q('#ml-h').value||50);
      LBL.copies=Math.max(1,Math.min(20,+q('#ml-c').value||1));saveLbl();closeModal();
      alert(`스티커 라벨 설정 저장 — ${LBL.w}×${LBL.h}mm · 도번당 ${LBL.copies}매`);};
  };
  const openPrinterSetup=()=>{
    const d=openModal(`<div style="font-weight:700;font-size:15px;margin-bottom:8px">🖨️ 프린터 설정</div>
      <div style="font-size:12px;color:#555;line-height:1.5;margin-bottom:10px">웹 환경에서는 실제 프린터 선택이 <b>브라우저 인쇄 대화상자</b>에서 이루어집니다(스티커=라벨 프린터, 거래명세표=일반 프린터 지정).<br>아래는 화면 표시용 프린터 이름입니다.</div>
      <label class="tl">프린터 이름(표시용)</label><input id="mp-name" class="inp" value="${esc(LBL.printer)}" style="width:100%;margin:4px 0 12px">
      <div style="text-align:right"><button class="btn" id="mp-cancel">취소</button> <button class="btn" id="mp-save" style="background:#2e86de;color:#fff">저장</button></div>`);
    d.querySelector('#mp-cancel').onclick=closeModal;
    d.querySelector('#mp-save').onclick=()=>{LBL.printer=d.querySelector('#mp-name').value.trim()||'(브라우저 인쇄 대화상자에서 선택)';saveLbl();closeModal();};
  };
  // 발행번호(바코드) 입력받아 재출력 — 스티커는 단독, 그 외는 3종 세트(SVC 분리)
  const reprint=async(kind)=>{const bc=prompt('발행번호(바코드)를 입력하세요');if(!bc)return;
    try{const iv=await fetchInvoice(bc.trim());(kind==='sticker'?openSticker:printSet)(iv);}
    catch(e){alert('출력 실패: '+e.message);}};
  // ★자재부품표 인쇄 — 레거시 양식(2026-08-27 사용자 확인).
  //   레거시는 가로 표가 아니라 **카드형 라벨**이다. 한 장에 3매, 매수만큼 반복.
  //     ┌──────── (주)피앤씨인더스트리  부 품 표 ────────┐
  //     │ 모도번(작업처) │                              │
  //     │ 자도번         │                              │
  //     │ 납품일 │ 년 월 일        │ 수량   │           │
  //     │ 업체명 │ 대원산업        │ 검사여부│          │
  //     │        │                 │ 검사확인│    (인)  │
  //   빈양식 = 업체명만 채우고 나머지 공란(수기 기입용).
  //   자재부품표 = 체크한 도번의 값을 채운다.
  const printView=(rows,blank)=>{
    const sel=blank?[]:rows.filter(r=>F.chk[r.assy]);
    if(!blank&&!sel.length)return alert('출력할 도번(체크)을 선택하세요.');
    const custName=(custs.find(w=>w.cc===F.cust)||{}).nm||F.cust;
    // 납품일 26년 08월 27일 (레거시 표기)
    const ymdK=(s)=>{const d=String(s||'').replace(/\D/g,'');
      return d.length>=6?`${d.slice(-6,-4)}년 ${d.slice(-4,-2)}월 ${d.slice(-2)}일`:'';};
    const card=(mo,ja,ymd,qty,insp)=>`
      <table class="pt">
        <tr><td class="ttl" colspan="4">(주)피앤씨인더스트리&nbsp; 부 품 표</td></tr>
        <tr><th class="h2">모도번<br>(작업처)</th><td class="big" colspan="3">${esc(mo||'')}</td></tr>
        <tr><th class="h">자도번</th><td class="big" colspan="3">${esc(ja||'')}</td></tr>
        <tr><th class="h">납품일</th><td class="big">${ymd?esc(ymd):'년&nbsp;&nbsp;&nbsp; 월&nbsp;&nbsp;&nbsp; 일'}</td>
            <th class="h s">수량</th><td class="big">${qty?nf(qty):''}</td></tr>
        <tr><th class="h" rowspan="2">업체명</th><td class="big" rowspan="2">${esc(custName)}</td>
            <th class="h s">검사여부</th><td class="big">${esc(insp||'')}</td></tr>
        <tr><th class="h s">검사확인</th><td class="v r">(인)</td></tr>
      </table>`;
    const ymd=ymdK(F.inymd||'');
    let cards;
    if(blank){
      cards=Array.from({length:9}).map(()=>card('','','',0,'')).join('');
    }else{
      // ★도번 1장이 아니라 **하위 자도번마다 1장**(레거시 동일).
      //   매수는 팝업으로 받는다 — 업체 배포용이라 여러 장 뽑는다.
      const n=parseInt(prompt('출력 매수(자도번 1건당)','1')||'0',10);
      if(!n||n<1)return;
      const out=[];
      sel.forEach(r=>{
        const mo=`${r.assy} (${r.workcenter||r.work_center||''})`;
        const qty=(F.deliv[r.assy]!=null?F.deliv[r.assy]:r.deliv);
        const insp=(r.insp==='1'?'검사':'무검사');
        // 자도번LIST 를 개별 자도번으로 분해(없으면 도번 자체 1장)
        const jl=(r.mat_list||'').split(',').map(s=>s.trim()).filter(Boolean);
        const list=jl.length?jl:[r.assy];
        list.forEach(ja=>{ for(let i=0;i<n;i++) out.push(card(mo,ja,ymd,qty,insp)); });
      });
      cards=out.join('');
    }
    const w=window.open('','_blank','width=900,height=1000'); if(!w)return alert('팝업 차단됨 — 허용 후 다시 시도.');
    w.document.write(`<html><head><title>${blank?'부품표(빈양식)':'부품표'} ${esc(custName)}</title><meta charset="utf-8">
      <style>
        @page{size:A4;margin:10mm}
        body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:0;font-size:13px}
        .pt{border-collapse:collapse;width:100%;table-layout:fixed;margin-bottom:14px;page-break-inside:avoid}
        .pt td,.pt th{border:1.5px solid #000;padding:5px 7px;height:30px}
        .ttl{text-align:center;font-weight:700;font-size:15px;border-bottom:1.5px solid #000;height:26px}
        .h{width:70px;text-align:center;font-weight:700;font-size:12px}
        .h2{width:70px;text-align:center;font-weight:700;font-size:12px;line-height:1.25}
        .s{width:80px}
        .big{text-align:center;font-weight:700;font-size:20px;letter-spacing:6px}
        .v{text-align:left}.r{text-align:right;padding-right:12px}
        @media print{.np{display:none}}
      </style></head><body>
      <div class="np" style="margin:0 0 10px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button>
        <span style="margin-left:8px;color:#555;font-size:12px">${blank?'빈양식':'자재부품표'} · ${esc(custName)} · ${(cards.match(/class="pt"/g)||[]).length}매</span></div>
      ${cards}
      </body></html>`); w.document.close();
  };
  const draw=()=>{
    const dates=data.dates||[];
    let rows=(data.rows||[]).slice();
    // 정렬 토글: 도번별 / 시간별(라인→도번)
    if(F.sort==='time') rows.sort((a,b)=>String(a.line||'').localeCompare(String(b.line||''),'ko')||String(a.assy).localeCompare(String(b.assy),'ko'));
    else rows.sort((a,b)=>String(a.workcenter||'').localeCompare(String(b.workcenter||''),'ko')||String(a.assy).localeCompare(String(b.assy),'ko'));
    const custOpts=custs.map(w=>`<option value="${esc(w.nm||w.cc)}"></option>`).join('');
    const custName=(custs.find(w=>w.cc===F.cust)||{}).nm||'';
    const itS=new Map(); rows.forEach(r=>{if(r.assy&&!itS.has(r.assy))itS.set(r.assy,r.nm||'');});
    const itemOpts=[...itS].slice(0,500).map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('');
    const ptS=new Set(); rows.forEach(r=>(r.mat_list||'').split(/[,\r\n]/).forEach(x=>{const m=x.split('{')[0].split('[')[0].trim();if(m)ptS.add(m);}));
    const partOpts=[...ptS].sort().slice(0,500).map(v=>`<option value="${esc(v)}"></option>`).join('');
    // 고정컬럼 수(빈 결과 colspan용) = 앞 16 + 일자 뒤 5 = 21.
    //   앞 16: SEQ·작업처·도번·LineNo·구분·자도번LIST·사급·LOT·자재·완료·요청·[체크]·납품·포장·검사·상태
    //   뒤  5: 입고대기·세트재고·생산실적·ASSY재고·출하실적 (2026-08-28 일자 뒤로 이동)
    const FIX=21;
    const S=data.sum||{};
    const badge=s=>`<span style="padding:1px 5px;border-radius:3px;font-size:10px;background:${STC[s]||'#8aa0bd'};color:#fff">${ST[s]||s}</span>`;
    // 일자셀=완료/계획+색(가공4주간 동일 표준): 생산완료 노랑·출하완료 주황·키팅완료 녹
    const dcell=(r,d)=>{const pl=Number((r.days&&r.days[d])||0),dn=Number((r.donedays&&r.donedays[d])||0),bg=(r.colors&&r.colors[d])||'';if(!pl&&!dn)return '<td class="num" style="color:#dfe6ef">·</td>';
      return `<td class="num" style="white-space:nowrap${bg?';background:'+bg:''}">${nf(dn)}/${nf(pl)}</td>`;};
    const gPlan={},gDone={};rows.forEach(r=>dates.forEach(d=>{gPlan[d]=(gPlan[d]||0)+Number((r.days&&r.days[d])||0);gDone[d]=(gDone[d]||0)+Number((r.donedays&&r.donedays[d])||0);}));
    const chkn=rows.filter(r=>F.chk[r.assy]).length;
    // ★table-layout:fixed + colgroup — 조회 후에도 컬럼폭 고정(auto 재계산 방지). CW=23개 고정컬럼 + 일자.
    // ★레거시 순서(2026-08-27): SEQ·자도번작업처·작업처·도번·LineNo·구분·품명·자도번LIST·사급
    //   ·LOT·계획·완료·요청 → [체크] → 납품·포장·SERIAL·HEAT·품목정보 → 실적/재고 → 일자
    //   체크박스는 요청수량 바로 뒤(납품수량 앞) = 레거시 위치.
    //   SEQ·자도번작업처·작업처·도번·LineNo·구분·품명·자도번LIST·사급·LOT·자재·완료·요청
    //   ·[체크]·납품·포장·SERIAL·HEAT·품목정보·출하실적·생산실적·세트재고·입고대기·ASSY재고·검사·상태 = 26
    // ★SERIAL-NO·HEAT-NO·품목정보·품명 제거(2026-08-27) → 26 → 22개
    //   SEQ·자도번작업처·작업처·도번·LineNo·구분·자도번LIST·사급·LOT·자재·완료·요청
    //   ·[체크]·납품·포장·출하실적·생산실적·세트재고·입고대기·ASSY재고·검사·상태
    //   ★폭 확대(2026-08-27 사용자 요청): 헤더가 잘려 보이던 칸들
    //     SEQ 28→40 · Line No 44→62 · 납품수량 52→62 · ASSY재고 54→64
    //   ★자도번작업처 삭제(작업처와 같은 값) → 22→21개, 작업처 66→110 확대
    //   ★2026-08-28 재배치: 실적/재고 5종을 **일자 뒤로** 옮기고 검사칸을 넓혔다.
    //     앞(고정 16) = SEQ·작업처·도번·LineNo·구분·자도번LIST·사급·LOT·자재·완료·요청
    //                   ·[체크]·납품·포장·검사(38→52)·상태
    //     뒤(일자 뒤 5) = 입고대기·세트재고·생산실적·ASSY재고·출하실적
    const CW=[40,110,96,62,56,300,38,52,52,52,52,  30,  62,52,  52,52], DW=48;
    const TW=[54,54,54,64,54];                       // 일자 뒤 5개 폭
    const totalW=CW.reduce((a,b)=>a+b,0)+dates.length*DW+TW.reduce((a,b)=>a+b,0);
    const colg=`<colgroup>${CW.map(w=>`<col style="width:${w}px">`).join('')}`
      +`${dates.map(()=>`<col style="width:${DW}px">`).join('')}`
      +`${TW.map(w=>`<col style="width:${w}px">`).join('')}</colgroup>`;
    // 합계행(2026-08-28 재배치 반영):
    //   계(1)+건수(2~7=6칸) + LOT·자재·완료·요청(8~11) + 체크(12) + 납품·포장(13~14) + 검사·상태(15~16)
    //   + 일자 + 입고대기·세트재고·생산실적·ASSY재고·출하실적(5)
    const _sumBy=f=>rows.reduce((a,r)=>a+(Number(r[f])||0),0);
    const grand=rows.length?`<tr class="grandtot"><td class="center"><b>계</b></td><td colspan="6">${nf(data.cnt)}건</td>`
      +`<td class="num"><b>${nf(S.lot||0)}</b></td><td class="num"><b>${nf(S.plan||0)}</b></td>`
      +`<td class="num" style="color:#1c7c3a"><b>${nf(S.done||0)}</b></td><td class="num"><b>${nf(S.req||0)}</b></td>`
      // ★납품수량 합계 = **체크한 행**의 합. 종전엔 발행분(S.issued)이라 무엇을 고른 건지 몰랐다.
      +`<td class="center">${(()=>{const n=rows.filter(r=>F.chk[r.assy]).length;return n?`<b style="color:#1c7c3a">${n}</b>`:'';})()}</td>`
      +`<td class="num" title="체크한 행의 납품수량 합계"><b style="color:#1c7c3a">${(()=>{
          let s=0;rows.forEach(r=>{if(F.chk[r.assy])s+=Number(F.deliv[r.assy]!=null?F.deliv[r.assy]:r.deliv)||0;});
          return s?nf(s):'';})()}</b></td><td colspan="3"></td>`
      +`${dates.map(d=>`<td class="num" style="white-space:nowrap"><b>${nf(gDone[d]||0)}/${nf(gPlan[d]||0)}</b></td>`).join('')}`
      +`<td class="center"><b>${nf(_sumBy('ireq'))}</b></td><td class="center"><b>${nf(_sumBy('iset_stk'))}</b></td>`
      +`<td class="center" style="color:#8e44ad"><b>${nf(_sumBy('prod'))}</b></td>`
      +`<td class="center"><b>${nf(_sumBy('assy_stock'))}</b></td>`
      +`<td class="center" style="color:#2e86de"><b>${nf(_sumBy('sale'))}</b></td></tr>`:'';
    // ★스크롤 1개(CLAUDE.md §3) — 화면 루트를 flex 컬럼으로, 표 영역만 스크롤.
    //   제목·안내·버튼·조건 2줄은 flex:0 0 auto 로 고정한다.
    c.style.cssText='display:flex;flex-direction:column;height:100%;min-height:0;overflow:hidden';
    c.innerHTML=`
     <div class="page-title" style="flex:0 0 auto">🧾 거래명세서 발행 <span style="font-size:12px;color:var(--muted);font-weight:400">레거시 w_pr_outside_420 · 웹편성(nx) 직독 · 발행=nx</span></div>
     <div class="page-sub" style="flex:0 0 auto;margin-bottom:6px">완료된 도번 <b>체크 → 납품/포장 입력 → [납품처리]</b>(발행은 <b>nx.deliv_issue</b>에만 기록). 완료수량=출하+완제품재고+세트/입고대기 재고배분(도번 공유풀). 요청수량=계획−완료−발행분.
       <span style="margin-left:6px;font-size:11px">일자셀=<b>완료/계획</b> · <span style="background:#ffff00;padding:0 5px;border-radius:3px">생산완료</span> <span style="background:#fac090;padding:0 5px;border-radius:3px">출하완료</span> <span style="background:#669900;color:#fff;padding:0 5px;border-radius:3px">키팅완료</span></span>${data.note?'<br>ℹ '+esc(data.note):''}</div>
     <!-- ★레거시 w_pr_outside_420 배치(2026-08-27): 출력버튼줄 / 조건 2줄.
          기간=납품일자 기준 조회일수, 직납=직납품 별도 일수(레거시 동일 개념). -->
     <div class="toolbar">
       <button class="btn" id="d4-prt">🖨️ 자재부품표</button>
       <button class="btn" id="d4-blank">빈양식</button>
       <button class="btn" id="d4-issue" style="background:#2e86de;color:#fff" ${busy?'disabled':''}>📦 납품처리 (${chkn})</button>
       <button class="btn" id="d4-sticker" title="발행번호로 스티커(바코드) 재출력">🏷️ 스티커</button>
       <button class="btn" id="d4-invoice" title="발행번호로 거래명세표 재출력">🧾 거래명세표</button>
       <button class="btn" id="d4-cancel">발행취소</button>
       <div class="spacer"></div>
       <span class="rowcount">${nf(data.cnt||0)}건 · 완료 <b>${nf(S.done||0)}</b>/계획 ${nf(S.plan||0)} · 발행 ${nf(S.issued||0)}</span>
       ${loading?'<span style="color:var(--muted)">조회중…</span>':''}
     </div>
     <!-- ★조건문 2줄 배치(2026-08-27 — 레거시 거래명세서발행 화면 동일).
            1줄 = 기준일자 · 구분 · 기간 · 직납 · 입고일자
            2줄 = 도번 · 자도번 · 자도번작업처[코드🔍이름] · 정렬 + 조회
            라벨은 레거시처럼 회색칸(.tl)으로 폭을 맞춘다. -->
     <style>
      .d4-r{display:flex;align-items:center;gap:6px;margin-top:2px;flex-wrap:nowrap}
      .d4-r .tl{background:#eaf0f8;border:1px solid #cdd9e8;border-radius:4px;
        padding:3px 8px;font-size:12px;color:#33507d;font-weight:600;text-align:center;
        white-space:nowrap;min-width:66px}
     </style>
     <div class="toolbar d4-r">
       <label class="tl">기준일자</label>${legacyDateHTML('d4-base',F.from)}
       <label class="tl">구분</label>
       <span style="display:inline-flex;gap:10px;padding:0 4px">
         <label style="font-size:12px;display:inline-flex;align-items:center;gap:3px;cursor:pointer"><input type="radio" name="d4gb" id="d4-gb-g" value="ganpan" ${F.gubun==='ganpan'?'checked':''}>일반간판</label>
         <label style="font-size:12px;display:inline-flex;align-items:center;gap:3px;cursor:pointer"><input type="radio" name="d4gb" id="d4-gb-o" value="order" ${F.gubun!=='ganpan'?'checked':''}>주문</label></span>
       <label class="tl">기간</label><input class="inp" id="d4-days" value="${esc(F.days)}" style="width:48px;min-width:48px;text-align:center" title="납품일자 기준 조회일수"><span style="font-size:12px;color:#5a6b80">일</span>
       <label class="tl">직납</label><input class="inp" id="d4-dnp" value="${esc(F.dnp)}" style="width:48px;min-width:48px;text-align:center" title="직납품 조회일수(레거시 '직납')"><span style="font-size:12px;color:#5a6b80">일</span>
       <label class="tl" style="margin-left:10px">입고일자</label>${legacyDateHTML('d4-in',F.inymd)}
       <div class="spacer"></div>
     </div>
     <div class="toolbar d4-r">
       <label class="tl">도번</label><input class="inp" id="d4-item" list="d4l-item" value="${esc(F.item)}" style="width:130px;min-width:130px" placeholder="도번(ASSY)/품명" autocomplete="off"><datalist id="d4l-item">${itemOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="d4-part" list="d4l-part" value="${esc(F.part)}" style="width:130px;min-width:130px" placeholder="자도번" autocomplete="off"><datalist id="d4l-part">${partOpts}</datalist>
       <!-- ★자도번작업처 = 레거시처럼 [코드][🔍][업체명] — 필수라 강조 -->
       <label class="tl" style="color:#1c47a0;background:#dceaff;border-color:#9dc0ea;min-width:88px">자도번작업처</label>
       <input class="inp" id="d4-custcode" value="${esc(F.cust)}" placeholder="코드" autocomplete="off" title="자도번작업처 코드 — 직접 입력 후 Enter" style="width:74px;min-width:74px;text-align:center;background:${F.cust?'#eaf3ff':'#fff7e6'};border:2px solid ${F.cust?'#7fa8e8':'#f0b429'};font-weight:700">
       <button class="btn" id="d4-custfind" title="업체 찾기" style="padding:0 7px;min-width:28px">🔍</button>
       <input class="inp" id="d4-cust" list="d4l-cust" value="${esc(custName)}" placeholder="거래처명" autocomplete="off" title="필수 — 협력사를 선택해야 조회됩니다" style="width:150px;min-width:150px;background:${F.cust?'#eaf3ff':'#fff7e6'};border:2px solid ${F.cust?'#7fa8e8':'#f0b429'};font-weight:600"><datalist id="d4l-cust">${custOpts}</datalist>
       <button class="btn" id="d4-search" style="margin-left:4px">🔍 조회</button>
       <div class="spacer"></div>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <!-- ★flex:0 1 auto + max-height:100% (4787a13 확정) — 고정 max-height 는 표 아래 여백을 남긴다. -->
     <div class="grid-wrap" style="flex:0 1 auto;min-height:0;max-height:100%;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px;white-space:nowrap;table-layout:fixed;width:${totalW}px">${colg}<thead><tr>
       <!-- ★품명·자도번작업처 제거 · 헤더 전부 가운데 정렬(2026-08-27 사용자 요청)
            자도번작업처와 작업처가 같은 값이라 작업처만 남기고 폭을 넓혔다. -->
       <th class="center">SEQ</th><th class="center">작업처</th><th class="center">도번</th><th class="center">Line No</th><th class="center">구분</th><th class="center">자도번LIST</th><th class="center">사급</th>
       <th class="center">LOT수량</th><th class="center">자재수량</th><th class="center">완료수량</th><th class="center">요청수량</th>
       <th class="center"><input type="checkbox" id="d4-all"></th>
       <!-- ★SERIAL-NO·HEAT-NO·품목정보 제거(2026-08-27 사용자 요청) -->
       <th class="center">납품수량</th><th class="center">포장수량</th>
       <th class="center">검사</th><th class="center">상태</th>
       ${dates.map(d=>`<th class="center"${wkbg(d)}>${esc(wlab(d))}</th>`).join('')}
       <!-- ★실적/재고 5종은 **일자 뒤로** 이동(2026-08-28 사용자요청).
            순서 = 입고대기 · 세트재고 · 생산실적 · ASSY재고 · 출하실적 -->
       <th class="center">입고대기</th><th class="center">세트재고</th><th class="center">생산실적</th><th class="center">ASSY재고</th><th class="center">출하실적</th>
       </tr></thead>
      <tbody>${loading?spinRow(FIX+dates.length):(rows.length?(rows.map((r,ri)=>{const ed=(r.status!=='90'&&Number(r.req)>0);
        // ★납품수량은 **체크했을 때만** 채운다(2026-08-28 사용자요청).
        //   종전엔 조회 즉시 r.deliv(=요청수량 기본값)가 전 행에 찍혀 있어
        //   무엇을 고른 건지 구분이 안 됐다. 체크 → 요청수량 자동채움, 해제 → 비움.
        //   사용자가 직접 고친 값(F.deliv)은 그대로 유지한다.
        const ckd=!!F.chk[r.assy];
        const dv=ckd?(F.deliv[r.assy]!=null?F.deliv[r.assy]:r.deliv):'';
        const pk=ckd?(F.pack[r.assy]!=null?F.pack[r.assy]:r.pack):'';return `<tr>
        <td class="num" style="color:#8aa0bd">${ri+1}</td>
        <td class="center"><b>${esc(r.workcenter||r.work_center||r.in_cust||'')}</b></td>
        <td class="center"><b>${esc(r.assy)}</b></td><td class="center">${esc(r.line||'')}</td>
        <td class="center">${esc(r.gubun||'')}</td>
        <td><div style="width:100%;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.mat_list||'')}">${esc(r.mat_list||'')}</div></td>
        <td class="center">${r.sagub_list?'<span class="bdg sagub" style="font-size:10px" title="'+esc(r.sagub_list)+'">사급</span>':''}</td>
        <td class="num">${nf(r.lot)}</td><td class="num">${nf(r.plan)}</td>
        <td class="num" style="color:#1c7c3a"><b>${nf(r.done)}</b></td>
        <td class="num"><b>${nf(r.req)}</b></td>
        <!-- ★이미 체크된 행은 disabled 를 걸지 않는다(2026-08-28) — 걸면 해제가 안 된다.
             ed(=상태<>90 · 요청>0)는 '새로 체크할 수 있는가' 조건일 뿐이다. -->
        <td class="center"><input type="checkbox" class="d4-ck" data-k="${esc(r.assy)}" ${ckd?'checked':''} ${(ed||ckd)?'':'disabled'}></td>
        <!-- 체크된 행이면 무조건 입력 가능(ed 와 무관) -->
        <td class="num" style="background:${ckd?'#eafaea':'#f5f7fa'};padding:1px 2px"><input class="inp d4-dv" data-k="${esc(r.assy)}" value="${dv}" ${ckd?'':'disabled'} title="${ckd?'납품수량':'완성분을 체크하면 입력됩니다'}" style="width:40px;min-width:0;height:24px;text-align:right;background:${ckd?'#eafaea':'#f5f7fa'};padding:1px 3px;font-size:11px"></td>
        <td class="num" style="background:${ckd?'#eafaea':'#f5f7fa'};padding:1px 2px"><input class="inp d4-pk" data-k="${esc(r.assy)}" value="${pk}" ${ckd?'':'disabled'} style="width:40px;min-width:0;height:24px;text-align:right;background:${ckd?'#eafaea':'#f5f7fa'};padding:1px 3px;font-size:11px"></td>
        <td class="center">${r.insp==='1'?'<span class="bdg sagub">검사</span>':''}</td>
        <!-- ★상태 = **요청수량이 있는 행만** 표시(2026-08-28). 요청 0 인데 '요청' 뱃지가
             전 행에 붙어 있어 무엇이 실제 대상인지 구분이 안 됐다. -->
        <td class="center">${Number(r.req)>0?badge(r.status):''}</td>
        ${dates.map(d=>dcell(r,d)).join('')}
        <!-- ★실적/재고 5종 = 일자 뒤 · 입고대기·세트재고·생산실적·ASSY재고·출하실적 · 전부 가운데정렬 -->
        <td class="center">${nf(r.ireq)}</td>
        <td class="center">${nf(r.iset_stk)}</td>
        <td class="center" style="color:#8e44ad">${nf(r.prod)}</td>
        <td class="center">${nf(r.assy_stock)}</td>
        <td class="center" style="color:#2e86de">${nf(r.sale)}</td>
        </tr>`;}).join('')+grand):`<tr><td colspan="${FIX+dates.length}" class="empty">협력사·기준일자 선택 후 조회하세요.</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    // ★자도번작업처 = [코드][🔍][업체명] 연동(2026-08-27 레거시 동일).
    const sync=()=>{const cn=g('#d4-cust').value.trim(), ccd=(g('#d4-custcode')||{value:''}).value.trim();
      const byNm=custs.find(w=>(w.nm||w.cc)===cn);
      if(byNm) F.cust=byNm.cc; else if(ccd) F.cust=ccd; else if(!cn) F.cust='';
      F.days=g('#d4-days').value||2;F.item=g('#d4-item').value.trim();F.part=g('#d4-part').value.trim();
      const dn=g('#d4-dnp');if(dn)F.dnp=dn.value||2;
      const gg=g('#d4-gb-g');F.gubun=(gg&&gg.checked)?'ganpan':'order';
      const so=g('#d4-sort');if(so)F.sort=so.value;};
    bindLegacyDate(c,'d4-base',()=>F.from,(v)=>{F.from=v;});
    bindLegacyDate(c,'d4-in',()=>F.inymd,(v)=>{F.inymd=v;});
    g('#d4-search').onclick=()=>{sync();load();};
    ['#d4-gb-g','#d4-gb-o'].forEach(id=>{const el=g(id);if(el)el.onchange=()=>{sync();load();};});
    const so=g('#d4-sort');if(so)so.onchange=()=>{sync();draw();};
    ['#d4-cust','#d4-custcode','#d4-item','#d4-part','#d4-days','#d4-dnp'].forEach(id=>{const el=g(id);if(el)el.onkeyup=e=>{if(e.key==='Enter'){sync();load();}};});
    // 코드 ↔ 업체명 양방향 채움
    const cCode=g('#d4-custcode');
    if(cCode)cCode.onchange=()=>{const w=custs.find(x=>x.cc===cCode.value.trim());if(w)g('#d4-cust').value=w.nm||w.cc;};
    const cName=g('#d4-cust');
    if(cName)cName.onchange=()=>{const w=custs.find(x=>(x.nm||x.cc)===cName.value.trim());if(w&&cCode)cCode.value=w.cc;};
    const cFind=g('#d4-custfind');
    if(cFind)cFind.onclick=()=>{if(cName){cName.focus();cName.select();}};
    g('#d4-issue').onclick=()=>issue(rows);
    g('#d4-cancel').onclick=cancelIssue;
    g('#d4-prt').onclick=()=>printView(rows,false);
    g('#d4-blank').onclick=()=>printView(rows,true);
    g('#d4-invoice').onclick=()=>reprint('invoice');
    // ★스티커설정·프린터설정 버튼은 툴바에서 뺐다(레거시 대조·2026-08-27). 기능은 유지 —
    //   스티커 버튼 우클릭 = 라벨규격/매수 설정, Shift+클릭 = 프린터 설정.
    const stk=g('#d4-sticker');
    if(stk){ stk.onclick=e=>{ if(e.shiftKey)openPrinterSetup(); else reprint('sticker'); };
             stk.oncontextmenu=e=>{ e.preventDefault(); openLabelSetup(); };
             stk.title='발행번호로 스티커 재출력 · 우클릭=스티커설정 · Shift+클릭=프린터설정'; }
    // ★전체선택 — 켤 땐 대상행(요청>0)만, 끌 땐 **체크된 것 전부** 해제한다.
    //   (해제 때도 ed 조건을 걸면 요청이 0으로 바뀐 행이 체크된 채 남는다)
    const all=g('#d4-all');
    if(all){
      const _sel=rows.filter(r=>F.chk[r.assy]).length;
      const _tgt=rows.filter(r=>r.status!=='90'&&Number(r.req)>0).length;
      all.checked=_tgt>0&&_sel>=_tgt;                 // 전부 골랐으면 체크 표시
      all.indeterminate=_sel>0&&_sel<_tgt;            // 일부만 골랐으면 중간 표시
      all.onclick=e=>{
        const on=e.target.checked;
        rows.forEach(r=>{
          if(on){ if(r.status!=='90'&&Number(r.req)>0)F.chk[r.assy]=true; }
          else  { delete F.chk[r.assy];delete F.deliv[r.assy];delete F.pack[r.assy]; }
        });
        // ★스크롤 보존 — draw()는 전체 재렌더라 그냥 부르면 맨 위로 튄다(2026-08-28).
        const gw=c.querySelector('.grid-wrap');
        const sy=gw?gw.scrollTop:0, sx=gw?gw.scrollLeft:0;
        draw();
        const gw2=c.querySelector('.grid-wrap');
        if(gw2){gw2.scrollTop=sy;gw2.scrollLeft=sx;}};
    }
    // ★체크 → 그 행의 납품/포장수량 칸을 열고 기본값(요청수량)을 채운다. 해제 → 비우고 잠근다.
    //   값이 체크 상태에 따라 달라지므로 그 행만 다시 그린다(전체 draw 는 스크롤이 튄다).
    c.querySelectorAll('.d4-ck').forEach(x=>x.onchange=e=>{
      const k=e.target.dataset.k, on=e.target.checked;
      F.chk[k]=on;
      if(!on){delete F.deliv[k];delete F.pack[k];}      // 해제 시 입력값도 초기화
      const tr=e.target.closest('tr');
      const r=rows.find(v=>v.assy===k);
      if(tr&&r){
        const dvEl=tr.querySelector('.d4-dv'), pkEl=tr.querySelector('.d4-pk');
        const bg=on?'#eafaea':'#f5f7fa';
        if(dvEl){dvEl.value=on?(F.deliv[k]!=null?F.deliv[k]:r.deliv):'';dvEl.disabled=!on;
                 dvEl.style.background=bg;dvEl.parentElement.style.background=bg;
                 dvEl.title=on?'납품수량':'완성분을 체크하면 입력됩니다';}
        if(pkEl){pkEl.value=on?(F.pack[k]!=null?F.pack[k]:r.pack):'';pkEl.disabled=!on;
                 pkEl.style.background=bg;pkEl.parentElement.style.background=bg;}
        // ★preventScroll — 그냥 focus() 하면 브라우저가 그 칸을 보이게 하려고 스크롤을 옮긴다.
        if(on&&dvEl){try{dvEl.focus({preventScroll:true});}catch(_){dvEl.focus();}dvEl.select();}
      }
      const b=g('#d4-issue');if(b)b.textContent=`📦 납품처리 (${rows.filter(r=>F.chk[r.assy]).length})`;
      // 헤더 전체선택 표시 갱신(전부/일부/없음)
      const ah=g('#d4-all');
      if(ah){const s=rows.filter(v=>F.chk[v.assy]).length,
                   t=rows.filter(v=>v.status!=='90'&&Number(v.req)>0).length;
             ah.checked=t>0&&s>=t; ah.indeterminate=s>0&&s<t;}});
    c.querySelectorAll('.d4-dv').forEach(x=>x.oninput=e=>{F.deliv[e.target.dataset.k]=e.target.value;});
    c.querySelectorAll('.d4-pk').forEach(x=>x.oninput=e=>{F.pack[e.target.dataset.k]=e.target.value;});
    c.querySelectorAll('.d4-sn').forEach(x=>x.oninput=e=>{F.serial[e.target.dataset.k]=e.target.value;});
    c.querySelectorAll('.d4-hn').forEach(x=>x.oninput=e=>{F.heat[e.target.dataset.k]=e.target.value;});
    c.querySelectorAll('thead th').forEach(th=>addResizer(th));
  };
  // ★계획 기준일(마지막 업로드 일자축 첫날) 반영 후 그린다 — 2026-08-28
  planBase().then(b=>{if(b&&b.iso)F.from=b.iso;}).catch(()=>{})
    .then(()=>loadCusts()).then(draw);
};

/* 협력사 > 자재세트입고관리 (레거시 w_pu_stock_140) — SET바코드 스캔/장부입고 → 세트입고 실적 + 자도번 재고파생(TAG='S'). 반품포함. */
SCREEN.setstock=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const yy=s=>s?s.slice(2).replace(/-/g,""):"";
  const now=new Date();
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const STAT={"00":"요청","10":"발행","20":"출발","30":"입고대기","40":"검사중","90":"입고완료","99":"반품"};
  const scol=s=>({"90":"#1f7a3d","30":"#c67d00","40":"#c67d00","99":"#c0392b"}[s]||"#586174");
  let st={rows:[],cust:"",item:"",fr:iso(new Date(now.getFullYear(),now.getMonth(),1)),to:iso(now),
          scan:"",info:null,mode:"bc",manual:"",sortKey:"",sortDir:1,loading:false,busy:false};
  const load=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/setstock/list?fr=${yy(st.fr)}&to=${yy(st.to)}&cust=${encodeURIComponent(st.cust)}&item=${encodeURIComponent(st.item)}`);
      const j=await r.json();st.rows=j.rows||[];}catch(e){st.rows=[];}
    st.loading=false;draw();};
  const doScan=async()=>{if(!st.scan)return;st.info=null;
    try{const r=await fetch(`${API}/api/setstock/scan?barcode=${encodeURIComponent(st.scan)}`);
      if(!r.ok)throw new Error((await r.json()).detail||r.status);st.info=await r.json();}catch(x){alert(x.message);st.info=null;}
    draw();};
  const doReceive=async()=>{if(st.busy)return;
    const bc=st.mode==="bc"?st.scan:st.manual;if(!bc)return alert(st.mode==="bc"?"SET바코드를 스캔하세요.":"장부입고 번호를 입력하세요.");
    if(!window.confirm(`SET바코드 ${bc}\n입고처리 → 세트입고 실적 기록 + 입고완료분 자도번 재고파생. 진행?`))return;
    st.busy=true;draw();
    try{const r=await fetch(`${API}/api/setstock/receive`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({barcode:bc,tag:st.mode==="bc"?"2":"3",manual:st.mode==="manual"?st.manual:""})});
      const j=await r.json();if(!r.ok)throw new Error(j.detail||r.status);
      alert(`입고완료 — ${j.received}건 처리, 자도번 재고파생 ${j.ledger_posted}행 (${j.barcode})`);st.scan="";st.info=null;st.manual="";await load();}catch(x){alert("입고처리 실패: "+x.message);}
    st.busy=false;draw();};
  const draw=()=>{
    if(st.sortKey){const k=st.sortKey,d=st.sortDir||1;st.rows.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    const totq=st.rows.reduce((a,r)=>a+(+r.maint_qty||0),0);
    const inf=st.info;
    c.innerHTML=`
     <div class="page-title">📦 자재세트입고관리</div>
     <div class="page-sub">협력사 세트 <b>SET바코드 스캔/장부입고</b> → 세트입고 실적 + 입고완료분 <b>자도번 재고파생</b>(TAG='S') · 검사품=입고대기 · 레거시 <code>w_pu_stock_140</code></div>
     <div class="panel" style="border:2px solid #2e86de"><div class="panel-h">세트 입고처리</div><div class="panel-b">
       <div class="toolbar" style="flex-wrap:wrap;gap:8px">
         <label class="tl"><input type="radio" name="sm" ${st.mode==="bc"?"checked":""} id="m-bc"> SET바코드</label>
         <label class="tl"><input type="radio" name="sm" ${st.mode==="manual"?"checked":""} id="m-man"> 장부입고(수동)</label>
         ${st.mode==="bc"
           ?`<input class="inp" id="sc-bc" value="${esc(st.scan)}" placeholder="SET바코드 스캔/입력" style="width:200px"><button class="btn" id="sc-go">🔍 송장조회</button>`
           :`<input class="inp" id="sc-man" value="${esc(st.manual)}" placeholder="장부입고 SET바코드 번호" style="width:200px">`}
         <button class="btn" id="sc-recv" style="background:#27ae60;color:#fff" ${st.busy?"disabled":""}>${st.busy?"처리중…":"📥 입고처리"}</button>
       </div>
       ${inf?`<div style="margin-top:8px;padding:10px;background:var(--soft);border-radius:6px;font-size:13px">
         <b>협력사:</b> ${esc(inf.custnm||inf.cust)} · <b>SET바코드:</b> SET${esc(inf.barcode)} · <b>도번 ${inf.rows.length}종</b>
         <table class="tbl" style="margin-top:6px;white-space:nowrap"><thead><tr><th>도번</th><th>품명</th><th class="num">수량</th><th class="center">자도번수</th><th class="center">상태</th><th class="center">검사</th></tr></thead>
         <tbody>${inf.rows.map(r=>`<tr><td><b>${esc(r.item_code)}</b></td><td class="cap" style="max-width:200px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.itemnm||"")}">${esc(r.itemnm||"")}</td><td class="num">${won(r.qty)}</td><td class="center">${r.jcnt}</td><td class="center" style="color:${scol(r.status)}">${STAT[r.status]||r.status}</td><td class="center">${r.insp==='1'?'검사품':'-'}</td></tr>`).join("")}</tbody></table>
         <div style="margin-top:4px;color:var(--muted);font-size:11px">일반=입고완료(90)→자도번 재고파생 · 검사품=입고대기(30, 검사후 파생)</div></div>`:""}
     </div></div>
     <div class="panel"><div class="panel-h">세트입고 실적 ${st.loading?"(조회중…)":`(${st.rows.length}건)`}</div><div class="panel-b" style="padding:0">
       <div class="toolbar" style="padding:8px 10px">
         <label class="tl">입고기간</label><input class="inp" type="date" id="f-fr" value="${esc(st.fr)}"> ~ <input class="inp" type="date" id="f-to" value="${esc(st.to)}">
         <label class="tl" style="margin-left:8px">도번</label><input class="inp" id="f-item" value="${esc(st.item)}" placeholder="도번" style="width:130px">
         <button class="btn" id="f-go">🔍 조회</button></div>
       <div class="grid-wrap" style="max-height:440px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th data-key="maint_ymd">입고일자</th><th class="num" data-key="maint_seq">SEQ</th><th data-key="custnm">협력사</th><th data-key="item_code">도번</th><th data-key="itemnm">품명</th>
         <th class="num" data-key="maint_qty">입고수량</th><th data-key="sheet_no">SET바코드</th><th class="center" data-key="status">상태</th><th class="center" data-key="derived_flag">재고파생</th><th>구분</th></tr></thead>
       <tbody>${st.rows.map(r=>{const ret=(+r.maint_qty<0);return `<tr>
         <td>${esc(r.maint_ymd)}</td><td class="num">${r.maint_seq}</td><td>${esc(r.custnm||r.cust_code)}</td>
         <td><b>${esc(r.item_code)}</b></td><td class="cap" style="max-width:180px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.itemnm||"")}">${esc(r.itemnm||"")}</td>
         <td class="num qty" style="color:${ret?"#c0392b":"#1f7a3d"}">${won(r.maint_qty)}</td>
         <td>${r.sheet_no?"SET"+esc(r.sheet_no):(r.manual_sheet_no?esc(r.manual_sheet_no)+"(수동)":"")}</td>
         <td class="center" style="color:${scol(r.status)}">${STAT[r.status]||r.status}</td>
         <td class="center">${r.derived_flag==='1'?'✅':'—'}</td><td>${r.maint_tag==='3'?'장부':r.maint_tag==='2'?'바코드':ret?'반품':esc(r.maint_tag)}</td></tr>`;}).join("")||'<tr><td colspan="10" style="padding:16px;color:var(--muted)">입고 실적 없음</td></tr>'}
       <tr class="grandtot"><td colspan="5" class="center">합계 ${st.rows.length}건</td><td class="num">${won(totq)}</td><td colspan="4"></td></tr>
       </tbody></table></div></div></div>`;
    const g=id=>c.querySelector(id);
    g("#m-bc").onclick=()=>{st.mode="bc";draw();};g("#m-man").onclick=()=>{st.mode="manual";draw();};
    if(st.mode==="bc"){const b=g("#sc-bc");b.oninput=x=>st.scan=x.target.value;b.onkeydown=x=>{if(x.key==="Enter")doScan();};g("#sc-go").onclick=doScan;}
    else{g("#sc-man").oninput=x=>st.manual=x.target.value;}
    g("#sc-recv").onclick=doReceive;
    g("#f-fr").onchange=x=>st.fr=x.target.value;g("#f-to").onchange=x=>st.to=x.target.value;g("#f-item").oninput=x=>st.item=x.target.value;g("#f-go").onclick=load;
    c.querySelectorAll("thead th").forEach(th=>{addResizer(th);const k=th.dataset.key;if(k){th.style.cursor="pointer";th.title="더블클릭 정렬·경계드래그 너비조절";th.ondblclick=()=>{st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;draw();};}});
  };
  load();
};
SCREEN.sagubadjust=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const yy=s=>s?s.slice(2).replace(/-/g,""):"";
  const now=new Date();
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  let st={hrows:[],hcusts:[],hcust:"",hmat:"",hsign:"",hsortKey:"",hsortDir:1,hloading:false,
          rows:[],custs:[],cust:"",mat:"",fr:iso(new Date(now.getFullYear(),now.getMonth(),1)),to:iso(now),
          sortKey:"",sortDir:1,edit:null,loading:false};
  const loadHold=async()=>{st.hloading=true;draw();
    try{const r=await fetch(`${API}/api/sagub/holding/list?cust=${encodeURIComponent(st.hcust)}&mat=${encodeURIComponent(st.hmat)}&sign=${st.hsign}`);
      const j=await r.json();st.hrows=j.rows||[];st.hcusts=j.custs||[];}catch(e){st.hrows=[];}
    st.hloading=false;draw();};
  const load=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/sagub/adjust/list?fr=${yy(st.fr)}&to=${yy(st.to)}&cust=${encodeURIComponent(st.cust)}&mat=${encodeURIComponent(st.mat)}`);
      const j=await r.json();st.rows=j.rows||[];st.custs=j.custs||[];}catch(e){st.rows=[];}
    st.loading=false;draw();};
  const save=async()=>{const e=st.edit;if(!e.cust_code||!e.mat_code)return alert("사급업체·자도번을 입력하세요.");
    if(e.maint_qty===""||isNaN(+e.maint_qty))return alert("수정수량(숫자)을 입력하세요.");
    try{const r=await fetch(`${API}/api/sagub/adjust/save`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(e)});
      if(!r.ok)throw new Error((await r.json()).detail||r.status);st.edit=null;await load();}catch(x){alert("저장 실패: "+x.message);}};
  const del=async(id)=>{if(!confirm("이 조정 전표를 삭제할까요?"))return;
    try{await fetch(`${API}/api/sagub/adjust/delete`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})});await load();}catch(x){alert("삭제 실패");}};
  const draw=()=>{
    if(st.hsortKey){const k=st.hsortKey,d=st.hsortDir||1;st.hrows.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    if(st.sortKey){const k=st.sortKey,d=st.sortDir||1;st.rows.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    const htotq=st.hrows.reduce((a,r)=>a+(+r.STOCK_QTY||0),0);
    const totq=st.rows.reduce((a,r)=>a+(+r.maint_qty||0),0);
    const e=st.edit;
    c.innerHTML=`
     <div class="page-title">🛠️ 협력사사급재고관리</div>
     <div class="page-sub">메인=<b>협력사 보유 사급재고 현황</b>(우리가 보낸 사급품 중 미회수 잔량, 정본 레거시 <code>PU_T_SAGUB_STOCK</code> RO) · 잔량=Σ사급출고−Σ(완성/세트입고×BOM소요) · 부가=<b>재고조정</b>(실사± <code>nx.sagub_maint</code>)</div>
     <div class="toolbar">
       <label class="tl">사급업체</label>
       <select class="inp" id="h-cust"><option value="">전체</option>${st.hcusts.map(o=>`<option value="${esc(o.code)}" ${st.hcust===o.code?"selected":""}>${esc(o.nm||o.code)}</option>`).join("")}</select>
       <label class="tl" style="margin-left:8px">자도번</label><input class="inp" id="h-mat" value="${esc(st.hmat)}" placeholder="자도번/품명" style="width:150px">
       <label class="tl" style="margin-left:8px">보유수량</label>
       <select class="inp" id="h-sign"><option value="">전체</option><option value="1" ${st.hsign==="1"?"selected":""}>(+)보유</option><option value="-1" ${st.hsign==="-1"?"selected":""}>(−)마이너스</option><option value="0" ${st.hsign==="0"?"selected":""}>0</option></select>
       <button class="btn" id="h-go">🔍 조회</button>
     </div>
     <div class="panel"><div class="panel-h">협력사 보유 사급재고 ${st.hloading?"(조회중…)":`(${st.hrows.length}건)`} · <span style="font-weight:400;color:var(--muted)">라이브 정본(읽기전용)</span></div><div class="panel-b" style="padding:0">
       <div class="grid-wrap" style="max-height:400px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th data-key="custnm">사급업체</th><th data-key="MAT_CODE">자도번</th><th data-key="matnm">품명</th><th class="center" data-key="item_class">구분</th>
         <th class="num" data-key="STOCK_QTY">보유재고</th><th class="num" data-key="REF_STOCK_QTY">참조수량</th><th data-key="upd_user">최종수정자</th><th data-key="upd_dt">최종수정일시</th><th data-key="upd_win">갱신프로그램</th></tr></thead>
       <tbody>${st.hrows.map(r=>`<tr>
         <td>${esc(r.custnm||r.CUST_CODE)}</td><td><b>${esc(r.MAT_CODE)}</b></td>
         <td class="cap" style="max-width:170px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.matnm||"")}">${esc(r.matnm||"")}</td>
         <td class="center">${r.item_class==='J'?'관리(중량)':'일반'}</td>
         <td class="num qty" style="color:${(+r.STOCK_QTY<0)?"#c0392b":"#1f7a3d"}">${won(r.STOCK_QTY)}</td>
         <td class="num">${r.REF_STOCK_QTY==null?'':won(r.REF_STOCK_QTY)}</td>
         <td>${esc(r.upd_user||"")}</td><td>${esc(String(r.upd_dt||"").slice(0,19).replace("T"," "))}</td>
         <td class="cap" style="max-width:130px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.upd_win||"")}">${esc(r.upd_win||"")}</td></tr>`).join("")||`<tr><td colspan="9" style="padding:16px;color:var(--muted)">${st.hloading?"":"보유 사급재고 없음"}</td></tr>`}
       <tr class="grandtot"><td colspan="4" class="center">합계 ${st.hrows.length}건</td><td class="num">${won(htotq)}</td><td colspan="4"></td></tr>
       </tbody></table></div></div></div>
     <div class="toolbar" style="margin-top:12px">
       <label class="tl">📋 재고조정 &nbsp;수정기간</label><input class="inp" type="date" id="sa-fr" value="${esc(st.fr)}"> ~ <input class="inp" type="date" id="sa-to" value="${esc(st.to)}">
       <label class="tl" style="margin-left:8px">사급업체</label>
       <select class="inp" id="sa-cust"><option value="">전체</option>${st.custs.map(o=>`<option value="${esc(o.code)}" ${st.cust===o.code?"selected":""}>${esc(o.nm||o.code)}</option>`).join("")}</select>
       <label class="tl" style="margin-left:8px">자도번</label><input class="inp" id="sa-mat" value="${esc(st.mat)}" placeholder="자도번(코드/이름)" style="width:150px">
       <button class="btn" id="sa-go">🔍 조회</button>
       <button class="btn" id="sa-add" style="background:#2e86de;color:#fff">➕ 조정추가</button>
     </div>
     ${e?`<div class="panel" style="border:2px solid #2e86de"><div class="panel-h">${e.id?"수정":"신규"} 조정 전표</div><div class="panel-b">
       <div class="toolbar" style="flex-wrap:wrap;gap:8px">
         <label class="tl">사급업체<span style="color:red">*</span></label><input class="inp" id="e-cust" value="${esc(e.cust_code||"")}" placeholder="업체코드" style="width:90px">
         <label class="tl">자도번<span style="color:red">*</span></label><input class="inp" id="e-mat" value="${esc(e.mat_code||"")}" placeholder="자도번" style="width:150px">
         <label class="tl">수정수량<span style="color:red">*</span></label><input class="inp" id="e-qty" value="${esc(e.maint_qty??"")}" placeholder="음수 가능" style="width:100px;text-align:right">
         <label class="tl">비고</label><input class="inp" id="e-rmk" value="${esc(e.remarks||"")}" placeholder="사유" style="width:200px">
         <button class="btn" id="e-save" style="background:#27ae60;color:#fff">💾 저장</button>
         <button class="btn" id="e-cancel">취소</button>
       </div><div style="font-size:11px;color:var(--muted);margin-top:4px">* 필수. 실사 조정(음수=차감). 조정은 nx 원장 기록(컷오버 후 재고 반영).</div></div></div>`:""}
     <div class="panel"><div class="panel-h">재고조정 내역 ${st.loading?"(조회중…)":""}</div><div class="panel-b" style="padding:0">
       <div class="grid-wrap" style="max-height:360px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th data-key="custnm">업체명</th><th data-key="maint_ymd">수정일자</th><th class="num" data-key="maint_seq">수정SEQ</th><th class="center">수정구분</th>
         <th data-key="mat_code">자도번</th><th data-key="matnm">품명</th><th class="num" data-key="maint_qty">수정수량</th><th data-key="remarks">비고</th>
         <th data-key="insert_user_id">작업자</th><th>작업일시</th><th class="center">관리</th></tr></thead>
       <tbody>${st.rows.map(r=>`<tr>
         <td>${esc(r.custnm||r.cust_code)}</td><td>${esc(r.maint_ymd)}</td><td class="num">${r.maint_seq}</td><td class="center">재고조정</td>
         <td><b>${esc(r.mat_code)}</b></td><td class="cap" style="max-width:160px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.matnm||"")}">${esc(r.matnm||"")}</td>
         <td class="num qty" style="color:${(+r.maint_qty<0)?"#c0392b":"#1f7a3d"}">${won(r.maint_qty)}</td><td class="cap" style="max-width:160px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.remarks||"")}">${esc(r.remarks||"")}</td>
         <td>${esc(r.insert_user_id)}</td><td>${esc(String(r.insert_datetime||"").slice(0,19).replace("T"," "))}</td>
         <td class="center"><button class="btn xs sa-ed" data-id="${r.id}">수정</button> <button class="btn xs sa-del" data-id="${r.id}">삭제</button></td></tr>`).join("")||'<tr><td colspan="11" style="padding:16px;color:var(--muted)">조정 내역 없음 — [조정추가]로 등록</td></tr>'}
       <tr class="grandtot"><td colspan="6" class="center">합계 ${st.rows.length}건</td><td class="num">${won(totq)}</td><td colspan="4"></td></tr>
       </tbody></table></div></div></div>`;
    const g=id=>c.querySelector(id);
    g("#h-cust").onchange=x=>st.hcust=x.target.value; g("#h-mat").oninput=x=>st.hmat=x.target.value;
    g("#h-sign").onchange=x=>st.hsign=x.target.value; g("#h-go").onclick=loadHold;
    g("#sa-fr").onchange=x=>st.fr=x.target.value; g("#sa-to").onchange=x=>st.to=x.target.value;
    g("#sa-cust").onchange=x=>st.cust=x.target.value; g("#sa-mat").oninput=x=>st.mat=x.target.value;
    g("#sa-go").onclick=load; g("#sa-add").onclick=()=>{st.edit={cust_code:st.cust||st.hcust||"",mat_code:"",maint_qty:"",remarks:""};draw();};
    if(e){g("#e-cust").oninput=x=>e.cust_code=x.target.value.trim();g("#e-mat").oninput=x=>e.mat_code=x.target.value.trim();
      g("#e-qty").oninput=x=>e.maint_qty=x.target.value;g("#e-rmk").oninput=x=>e.remarks=x.target.value;
      g("#e-save").onclick=save;g("#e-cancel").onclick=()=>{st.edit=null;draw();};}
    c.querySelectorAll(".sa-ed").forEach(x=>x.onclick=()=>{const r=st.rows.find(v=>v.id==x.dataset.id);st.edit={id:r.id,cust_code:r.cust_code,mat_code:r.mat_code,maint_qty:r.maint_qty,remarks:r.remarks||""};draw();});
    c.querySelectorAll(".sa-del").forEach(x=>x.onclick=()=>del(+x.dataset.id));
    c.querySelectorAll("thead th").forEach(th=>{addResizer(th);const k=th.dataset.key;if(!k)return;th.style.cursor="pointer";th.title="더블클릭 정렬·경계드래그 너비조절";
      const isHold=!!(th.closest("table")&&th.closest("table").querySelector("[data-key='STOCK_QTY']"));
      th.ondblclick=()=>{if(isHold){st.hsortDir=(st.hsortKey===k&&st.hsortDir===1)?-1:1;st.hsortKey=k;}else{st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;}draw();};});
  };
  loadHold(); load();
};

/* ===== 협력사: 모델BOM 관리 (w_pr_master_060/020) — 모델→도번(신규모델 등록) ===== */
SCREEN.modelbom=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const ymd=s=>(s&&(''+s).length===6&&s!=='000000'&&s!=='999999')?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s==='999999'?'~':(s==='000000'?'상시':(s||'')));
  let by='model', q='', slist=[], sel='', data={rows:[]}, loading=false, searching=false, msg='', editMode=false, erows=[];
  const search=async()=>{searching=true;draw();
    try{const r=await fetch(`${API}/api/modelbom/search?q=${encodeURIComponent(q)}&by=${by}`);slist=(await r.json()).rows||[];}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';slist=[];}searching=false;draw();};
  const load=async(code)=>{sel=code;editMode=false;loading=true;draw();
    const p=by==='item'?`item=${encodeURIComponent(code)}`:`model=${encodeURIComponent(code)}`;
    try{const r=await fetch(`${API}/api/modelbom/get?${p}`);data=await r.json();}catch(e){data={rows:[]};}loading=false;draw();};
  const startEdit=()=>{editMode=true;erows=data.rows.filter(r=>r.src==='nx').map(r=>({...r}));if(!erows.length)erows=[{item:'',use_qty:1,from:'',to:'',remarks:''}];draw();};
  const addRow=()=>{erows.push({item:'',use_qty:1,from:'',to:'',remarks:''});draw();};
  // ★신규 모델 등록(2026-08-27) — 기존 매핑이 없는 모델은 검색으로 찾을 수 없어
  //   등록 진입점 자체가 없었다. 모델번호를 직접 입력받아 바로 편집모드로 들어간다.
  const newModel=async()=>{
    const m=(prompt('신규 등록할 LG 모델번호를 입력하세요.\n(이미 매핑이 있으면 그 내용을 불러옵니다)','')||'').trim();
    if(!m)return;
    by='model';q=m;sel=m;
    // 기존 매핑이 있으면 nx 등록분을 이어서 편집, 없으면 빈 행 하나로 시작
    try{const r=await fetch(`${API}/api/modelbom/get?model=${encodeURIComponent(m)}`);data=await r.json();}
    catch(e){data={rows:[]};}
    erows=(data.rows||[]).filter(r=>r.src==='nx').map(r=>({...r}));
    if(!erows.length)erows=[{item:'',use_qty:1,from:'',to:'',remarks:''}];
    editMode=true;draw();
    search();            // 좌측 목록 갱신(비동기 — 끝나면 draw 재호출)
  };
  const save=async()=>{
    try{const r=await fetch(`${API}/api/modelbom/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:sel,rows:erows})});
      const j=await r.json();if(j.ok){alert(`모델BOM 저장 완료 — ${j.count}건 (nx 신규등록)`);load(sel);return;}alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 실패: '+e);}};
  const draw=()=>{
    const R=data.rows||[];
    const canW=(typeof PERM!=='undefined')?PERM.canEdit('modelbom'):true;   // 수정권한 게이트(규칙#16)
    c.innerHTML=`
     <div class="page-title">🧬 모델BOM 관리 <span style="font-size:12px;color:var(--muted);font-weight:400">LG모델 → 우리 도번 매핑 (편성 커버리지)</span></div>
     <div class="page-sub">LG 모델번호를 우리 ASSY 도번으로 매핑. 편성(협력사계획)이 이 매핑으로 모델→도번을 전개. 조회=<code>nx.PR_M_MODEL_BOM</code> ∪ <code>nx.model_bom</code>(신규등록). <b>미매핑 신규모델은 좌측 「＋ 신규 모델 등록」</b>으로 추가.</div>
     <div style="display:flex;gap:14px;align-items:flex-start">
      <div style="flex:0 0 300px">
       <div class="toolbar"><select class="inp" id="mb-by"><option value="model"${by==='model'?' selected':''}>모델→도번</option><option value="item"${by==='item'?' selected':''}>도번→모델(역)</option></select>
         <input class="inp" id="mb-q" value="${esc(q)}" placeholder="${by==='item'?'도번':'모델'} 검색" style="width:150px"><button class="btn" id="mb-search">🔍</button></div>
       ${canW?`<div class="toolbar" style="margin-top:2px"><button class="btn" id="mb-new" style="background:#1c7c3a;color:#fff;width:100%">＋ 신규 모델 등록</button></div>
       <div class="page-sub" style="margin:2px 0 6px;font-size:11px;color:#8aa0bd">※ 매핑이 아직 없는 모델은 검색되지 않습니다 — 위 버튼으로 모델번호를 직접 입력해 등록하세요.</div>`:''}
       <div class="grid-wrap" style="max-height:calc(100vh - 240px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
        <table class="tbl" style="font-size:12px"><thead><tr><th>${by==='item'?'도번':'모델'}</th><th class="num">${by==='item'?'모델수':'도번수'}</th></tr></thead>
        <tbody>${searching?spinRow(2):(slist.length?slist.map(s=>`<tr class="mb-row${sel===s.code?' sel':''}" data-c="${esc(s.code)}" style="cursor:pointer"><td><b>${esc(s.code)}</b></td><td class="num">${s.n}</td></tr>`).join(''):`<tr><td colspan="2" class="empty">검색</td></tr>`)}</tbody></table>
       </div>
      </div>
      <div style="flex:1;min-width:0">
       ${sel?`<div class="toolbar"><span style="font-weight:700;color:#1c47a0">${esc(sel)}</span>
         <div class="spacer"></div>${(by==='model'&&canW)?(editMode?`<button class="btn" id="mb-add">＋행추가</button><button class="btn" id="mb-save" style="background:#1c47a0;color:#fff">💾 저장</button><button class="btn ghost" id="mb-cancel">✖ 취소</button>`:`<button class="btn" id="mb-edit">✎ 신규등록/수정(nx)</button>`):(by==='model'?`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`:'')}</div>
        <div class="grid-wrap" style="max-height:calc(100vh - 250px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
         ${(!editMode)?`<table class="tbl" style="font-size:12px"><thead><tr>${by==='item'?'<th>모델</th>':''}<th>도번</th><th>품명</th><th class="num">사용수량</th><th>유효시작</th><th>유효종료</th><th>작업장/업체</th><th>소스</th></tr></thead>
          <tbody>${loading?spinRow(7):(R.length?R.map(r=>`<tr>${by==='item'?`<td><b>${esc(r.model)}</b></td>`:''}<td><b>${esc(r.item)}</b></td><td class="bcap" title="${esc(r.nm)}" style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td><td class="num">${r.use_qty}</td><td class="center">${ymd(r.from)}</td><td class="center">${ymd(r.to)}</td><td class="center">${esc(r.wc)}</td><td class="center"><span style="font-size:10px;color:${r.src==='nx'?'#1c7c3a':'#888'}">${r.src==='nx'?'nx등록':'nx기존'}</span></td></tr>`).join(''):`<tr><td colspan="${by==='item'?8:7}" class="empty">매핑 없음 — ${by==='model'?'신규등록/수정(nx)으로 추가':''}</td></tr>`)}</tbody></table>`
         :`<table class="tbl" style="font-size:12px"><thead><tr><th>도번</th><th class="num">사용수량</th><th>유효시작(YYMMDD)</th><th>유효종료</th><th>비고</th><th>삭제</th></tr></thead>
          <tbody>${erows.map((r,i)=>`<tr><td><input class="ce" data-i="${i}" data-k="item" value="${esc(r.item||'')}" placeholder="도번" style="width:130px"></td>
           <td><input class="ce" type="number" step="any" data-i="${i}" data-k="use_qty" value="${r.use_qty??1}" style="width:60px"></td>
           <td><input class="ce" data-i="${i}" data-k="from" value="${esc(r.from||'')}" placeholder="상시" style="width:90px"></td>
           <td><input class="ce" data-i="${i}" data-k="to" value="${esc(r.to||'')}" placeholder="~무기한" style="width:90px"></td>
           <td><input class="ce" data-i="${i}" data-k="remarks" value="${esc(r.remarks||'')}" style="width:120px"></td>
           <td class="center"><span class="mb-del" data-i="${i}" style="cursor:pointer;color:#c0392b">✖</span></td></tr>`).join('')}</tbody></table>`}
        </div>
        ${editMode?`<div class="page-sub" style="margin-top:6px;color:#8aa0bd">※ 라이브(PR_M_MODEL_BOM)는 읽기전용. 신규모델·추가매핑만 nx.model_bom에 저장되며 편성이 즉시 반영합니다.</div>`:''}`
       :`<div class="empty" style="margin-top:40px">좌측에서 ${by==='item'?'도번':'모델'}을 선택하세요.</div>`}
      </div>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <style>.mb-row.sel{background:#e8f0ff}.mb-row:hover{background:#eef4ff}</style>`;
    const g=id=>c.querySelector(id);
    g('#mb-by').onchange=e=>{by=e.target.value;slist=[];sel='';data={rows:[]};draw();};
    g('#mb-search').onclick=()=>{q=g('#mb-q').value;search();};
    g('#mb-q').onkeyup=e=>{if(e.key==='Enter'){q=e.target.value;search();}};
    c.querySelectorAll('.mb-row').forEach(el=>el.onclick=()=>load(el.dataset.c));
    const nw=g('#mb-new');if(nw)nw.onclick=newModel;
    const ed=g('#mb-edit');if(ed)ed.onclick=startEdit;
    const ad=g('#mb-add');if(ad)ad.onclick=addRow;
    const sv=g('#mb-save');if(sv)sv.onclick=save;
    const cx=g('#mb-cancel');if(cx)cx.onclick=()=>{editMode=false;draw();};
    c.querySelectorAll('.mb-del').forEach(el=>el.onclick=()=>{erows.splice(+el.dataset.i,1);draw();});
    c.querySelectorAll('.ce').forEach(el=>el.oninput=()=>{const i=+el.dataset.i,k=el.dataset.k;erows[i][k]=(el.type==='number')?(el.value===''?null:+el.value):el.value;});
  };
  draw();
};

/* ===== 협력사 ①: 협력사계획현황 (w_pr_outside_040) — nx.plan_part 편성결과 ===== */
SCREEN.partnerplan=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  // ★일자컬럼 = 생산화면(파트별 생산계획)과 동일 형식: 일자+요일(예 27목), 주말은 빨강.
  const wlab=y=>{if(!y||y.length<6)return dcol(y);const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));const dow='일월화수목금토'[dt.getDay()];return `${y.slice(4,6)}${dow}`;};
  const isWkend=y=>{if(!y||y.length<6)return false;const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));return dt.getDay()===0||dt.getDay()===6;};
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  // ★기본 소스=nx(우리편성). 레거시는 1:1 대조용 선택지로 남김(2026-08-27).
  // ★기준일 = **마지막 계획업로드의 일자축 첫날**(planBaseIso, 2026-08-28 사용자 확정).
  //   당일로 잡으면 업로드 전날 기준이 되어, 미출하분이 재편성되며 충당된 재고와 어긋난다.
  let F={from:planBaseIso(),days:31,wc:'',part:'',assy:'',line:'',gubun:'외주',src:'nx'};
  let data={dates:[],rows:[],cnt:0,sum_qty:0,note:''}, wcs=[], loading=false, msg='';
  let rowsCur=[];   // ★헤더 더블클릭 정렬용 영속 행배열(enableSort가 in-place 정렬, tbody만 재렌더)
  const toOf=()=>_isoAddDays(F.from,Math.max(1,(+F.days||31))-1);
  const loadWc=async()=>{try{const r=await fetch(`${API}/api/partner/workcenters?src=${F.src}`);wcs=(await r.json()).rows||[];}catch(e){wcs=[];}};
  const load=async()=>{
    if(loading)return;                              // 중복요청 가드
    if(!F.wc){msg='협력사(자도번작업처)를 먼저 선택하세요. (전체 조회는 무거워 협력사 지정 후 조회합니다)';data={dates:[],rows:[],cnt:0,sum_qty:0,note:''};draw();return;}
    loading=true;msg='';draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:toOf(),wc:F.wc,part:F.part,assy:F.assy,line:F.line,gubun:F.gubun,src:F.src});
    try{const r=await fetch(`${API}/api/partner/planstatus?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';data={dates:[],rows:[],cnt:0,sum_qty:0};}
    loading=false;draw();};
  // 레거시 도번-level(자도번LIST) / nx 자도번-level 를 동일 컬럼으로 정규화
  const norm=(r,i)=>({seq:r.seq||i+1, wc:r.wc, wcnm:r.wcnm||r.wc, line:r.line||'', workcenter:r.workcenter||'',
     // ★nx 소스도 레거시와 같은 그레인(도번=assy 1행) → 자도번LIST 는 그 행의 자재목록(mats). 없으면 종전 part.
     // ★nx 소스도 레거시와 같은 그레인(도번=assy 1행, 제번 합산) → 자도번LIST 는 그 도번의 자재목록(mats).
     assy:r.assy||'', jado:r.mats||r.part||'', matn:r.matn||0, wocnt:r.wocnt||0, sagub:!!r.sagub, lot:(r.lot!=null?r.lot:null),
     matq:(r.matq!=null?r.matq:r.tot), doneq:(r.doneq!=null?r.doneq:null), reqq:(r.reqq!=null?r.reqq:null),
     nm:r.nm||'', spec:r.spec||'', days:r.days||{}, donedays:r.donedays||{}, colors:r.colors||{}, tot:r.tot||0, alloc_note:r.alloc_note||''});
  const draw=()=>{
    const dates=data.dates||[];
    rowsCur=(data.rows||[]).map(norm);
    rowsCur.forEach(r=>dates.forEach(d=>{r['d_'+d]=Number((r.days&&r.days[d])||0);}));   // ★일자(피벗) 정렬용 합성 숫자키
    const rows=rowsCur;
    const pnAssy=new Set(),pnLine=new Set(),pnPart=new Set();
    rows.forEach(r=>{if(r.assy)pnAssy.add(r.assy);if(r.line)pnLine.add(r.line);if(r.jado)pnPart.add((r.jado||'').split('{')[0]);});
    const pnAssyOpts=[...pnAssy].slice(0,400).map(v=>`<option value="${esc(v)}"></option>`).join('');
    const pnLineOpts=[...pnLine].map(v=>`<option value="${esc(v)}"></option>`).join('');
    const pnPartOpts=[...pnPart].slice(0,400).map(v=>`<option value="${esc(v)}"></option>`).join('');
    const wcOpts=wcs.map(w=>`<option value="${esc(w.nm||w.cc)}"></option>`).join('');
    const wcName=(wcs.find(w=>w.cc===F.wc)||{}).nm||'';
    const nn=v=>(v==null?'-':nf(v));
    // 합계행
    const frac=!!data.frac;   // 협력사 지정 시 일자셀=완료/계획+색(가공4주간 동일)
    const sMat=rows.reduce((a,r)=>a+Number(r.matq||0),0), sReq=rows.reduce((a,r)=>a+Number(r.reqq||0),0);
    const gDay={},gDone={}; rows.forEach(r=>dates.forEach(d=>{gDay[d]=(gDay[d]||0)+Number((r.days&&r.days[d])||0);gDone[d]=(gDone[d]||0)+Number((r.donedays&&r.donedays[d])||0);}));
    // 일자셀 렌더: frac=완료/계획+색, 아니면 계획수량
    const dcell=(r,d)=>{const pl=Number((r.days&&r.days[d])||0);if(!frac)return `<td class="num"${pl?'':' style="color:#dfe6ef"'}>${pl?nf(pl):'·'}</td>`;
      const dn=Number((r.donedays&&r.donedays[d])||0),bg=(r.colors&&r.colors[d])||'';if(!pl&&!dn)return '<td class="num" style="color:#dfe6ef">·</td>';
      return `<td class="num" style="white-space:nowrap${bg?';background:'+bg:''}">${nf(dn)}/${nf(pl)}</td>`;};
    const FIX=11;   // ★품목정보 컬럼 제거(2026-08-27 사용자 요청) — 12 → 11
    const gcell=d=>frac?`<td class="num" style="white-space:nowrap"><b>${nf(gDone[d]||0)}/${nf(gDay[d]||0)}</b></td>`:`<td class="num"><b>${nf(gDay[d]||0)}</b></td>`;
    const grandRow=rows.length?`<tr class="grandtot"><td class="center"><b>계</b></td><td class="center" style="color:#33507d">${nf(data.cnt||rows.length)}건</td><td colspan="6"></td><td class="num"><b>${nf(sMat)}</b></td><td class="num">-</td><td class="num"><b>${nf(sReq)}</b></td>${dates.map(d=>gcell(d)).join('')}</tr>`:'';
    const rowTr=r=>`<tr>
        <td class="num" style="color:#8aa0bd">${r.seq}</td>
        <td><b>${esc(r.wcnm)}</b>${r.alloc_note?` <span class="bdg" style="font-size:9px;background:#eaf3ff;color:#1c47a0;border:1px solid #bcd;border-radius:6px;padding:0 4px" title="조달 프로파일 발주업체 배분 반영">${esc(r.alloc_note)}</span>`:''}</td><td class="center">${esc(r.line)}</td><td>${esc(r.workcenter)}</td>
        <td><b>${esc(r.assy)}</b></td>
        <td><div style="width:400px;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.jado)}">${r.matn>1?`<span class="bdg" style="font-size:9px;background:#f2f6fc;color:#41597e;border:1px solid #d3dceb;border-radius:6px;padding:0 4px;margin-right:3px" title="이 도번에 걸린 자재 ${r.matn}종${r.wocnt?` · 제번 ${r.wocnt}건 합산`:''} (수량은 도번 계획수량)">${r.matn}종</span>`:''}${esc(r.jado)}</div></td>
        <td class="center">${r.sagub?'<span class="bdg sagub" style="font-size:10px">사급</span>':''}</td>
        <td class="num">${nn(r.lot)}</td><td class="num"><b>${nn(r.matq)}</b></td>
        <td class="num" style="color:#1c7c3a" title="완료수량 = 출하실적 + 완제품재고 배분 + 세트/입고대기 재고배분 (레거시 SP+510창, 도번 공유풀). 협력사(외주) 지정 시 표시.">${nn(r.doneq)}</td>
        <td class="num">${nn(r.reqq)}</td>
        ${dates.map(d=>dcell(r,d)).join('')}</tr>`;
    const bodyHTML=()=>loading?spinRow(FIX+dates.length):(rowsCur.length?(rowsCur.map(rowTr).join('')+grandRow):`<tr><td colspan="${FIX+dates.length}" class="empty">조회 결과 없음 — 자도번작업처/기준일자/기간을 확인하세요.</td></tr>`);
    // ★<style> 은 반드시 .pn-root 안에 둔다 — 탭 컨테이너(#pg-*, height:100%)의 형제로 두면
    //   블록 박스 하나가 더 쌓여 .pn-root 의 height:100% 와 합쳐져 넘치고, 그만큼 아래가 빈다.
    //   (c52de04 가 잡은 height:100% 체인이 여기서 다시 끊겼던 원인 — 2026-08-27)
    c.innerHTML=`
    <div class="pn-root" style="display:flex;flex-direction:column;height:100%">
    <style>
      /* ★페이지 본문(창) 세로 스크롤 금지 — 그리드만 내부 스크롤. 헤더=sticky top, 합계행=sticky bottom(CLAUDE.md §3) */
      .pn-grid thead th{position:sticky;top:0;z-index:3;background:#eef2f8}
      .pn-grid tr.grandtot td{position:sticky;bottom:0;z-index:2;background:#f0f4fb;box-shadow:0 -1px 0 var(--line-2,#c9d3e0)}
      /* ★그리드 세로폭 확보 — 헤더(제목·툴바·범례)를 압축하고 .content 패딩을 줄여 표에 넘김.
         ⚠음수 margin 으로 패딩을 상쇄하면 height:100% 계산이 어긋나 표 아래가 빈다 →
           .content 에 직접 padding 을 줄이고 화면 루트는 height:100% 그대로 둔다. */
      .pn-head .page-sub{margin-bottom:0}
      .pn-head .toolbar{padding:7px 11px;margin-bottom:6px;gap:7px}
      .pn-head .page-title{font-size:16px}
      /* ★높이 구조는 c52de04 확정 패턴을 그대로 쓴다: 루트 height:100% + 표 flex:1;min-height:0.
         음수 margin·JS 높이계산·부모 flex 변경은 모두 어긋난다(2026-08-27 재확인). */
      .pn-root>style{display:none}   /* flex 자식으로 공간 차지 방지 */
      /* ★전 컬럼 가운데 정렬 — 단 자도번LIST(6)·품목정보(12)는 긴 텍스트라 좌측 유지(2026-08-27 요청).
         숫자칸(.num)도 가운데로 오되 숫자 자릿수는 tabular-nums 로 맞춘다. */
      /* ⚠app.css 의 .tbl .num{text-align:right} 보다 특정도가 높아야 이긴다(.tbl.pn-grid) */
      table.tbl.pn-grid th, table.tbl.pn-grid td{text-align:center}
      table.tbl.pn-grid th:nth-child(6),  table.tbl.pn-grid tbody tr:not(.grandtot) td:nth-child(6),
      table.tbl.pn-grid th:nth-child(12), table.tbl.pn-grid tbody tr:not(.grandtot) td:nth-child(12){text-align:left}
      table.tbl.pn-grid .num{font-variant-numeric:tabular-nums}
    </style>
     <div class="pn-head" style="flex:0 0 auto">
     <div class="page-title" style="margin-bottom:4px">📋 협력사계획현황 <span style="font-size:12px;color:var(--muted);font-weight:400">4주간 계획수량 — 도번·자도번LIST·일자별 (당김 반영)</span>
       <span style="font-size:11px;font-weight:400;margin-left:8px" title="${F.src==='legacy'?'레거시 라이브 PR_T_PLAN_PART_MAT 직독. 당김=PR_M_LINE_NO.CUST_MAINT_DAY(회사근무일).':'웹 편성 결과만 사용(라이브 미참조): 계획업로드→④파트별→⑤자재소요. 기간=소요일자(part_plan_ymd·당김반영), 수량=도번 계획수량(plan_item_dtl). 그레인=레거시 w_pr_outside_410 동일(도번 1행·제번 합산).'}">${F.src==='legacy'?'🔴 <b>레거시 라이브</b>':'🟢 <b>우리편성(nx)</b>'}</span></div>
     <!-- ★조건문 2줄 배치(2026-08-27 사용자 요청 — 레거시 w_pr_outside_410 동일).
            1줄 = 소스 · 기준일자 · 기간   /   2줄 = 도번 · 자도번 · 자도번작업처 · 라인 + 조회
            레거시는 라벨을 회색칸에 넣어 폭을 맞춘다 → .tl 을 고정폭으로 정렬. -->
     <style>
      .pn-head .pn-r{display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:nowrap}
      .pn-head .pn-r .tl{background:#eaf0f8;border:1px solid #cdd9e8;border-radius:4px;
        padding:3px 8px;font-size:12px;color:#33507d;font-weight:600;text-align:center;
        white-space:nowrap;min-width:74px}
     </style>
     <div class="toolbar pn-r" style="margin-top:2px">
       <label class="tl">소스</label>
       <select class="inp" id="pn-src" style="width:auto;min-width:158px">
         <option value="nx" ${F.src==='nx'?'selected':''}>우리편성 (nx)</option>
         <option value="legacy" ${F.src==='legacy'?'selected':''}>레거시 라이브 (당김반영)</option></select>
       <label class="tl">기준일자</label>${legacyDateHTML('pn-base',F.from)}
       <label class="tl">기간</label><input class="inp" id="pn-days" value="${esc(F.days)}" style="width:52px;min-width:52px;text-align:center" title="조회 기간(일). 레거시 4주간 화면 기본=31일"><span style="font-size:12px;color:#5a6b80">일</span>
       <div class="spacer"></div><span class="rowcount">${nf(data.cnt)}건 · 자재수량합 <b>${nf(data.sum_qty)}</b> · 일자 ${dates.length}</span>
     </div>
     <div class="toolbar pn-r">
       <label class="tl">도번</label><input class="inp" id="pn-assy" list="pnl-assy" value="${esc(F.assy)}" style="width:130px;min-width:130px" placeholder="도번(ASSY)" autocomplete="off"><datalist id="pnl-assy">${pnAssyOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="pn-part" list="pnl-part" value="${esc(F.part)}" style="width:130px;min-width:130px" placeholder="자도번" autocomplete="off"><datalist id="pnl-part">${pnPartOpts}</datalist>
       <!-- ★자도번작업처 = 레거시처럼 [코드][🔍][업체명] — 필수 입력이라 강조 -->
       <label class="tl" style="color:#1c47a0;background:#dceaff;border-color:#9dc0ea;min-width:88px">자도번작업처</label>
       <input class="inp" id="pn-wccode" value="${esc(F.wc)}" placeholder="코드" autocomplete="off" title="자도번작업처 코드 — 직접 입력 후 Enter" style="width:74px;min-width:74px;text-align:center;background:${F.wc?'#eaf3ff':'#fff7e6'};border:2px solid ${F.wc?'#7fa8e8':'#f0b429'};font-weight:700">
       <button class="btn" id="pn-wcfind" title="업체 찾기" style="padding:0 7px;min-width:28px">🔍</button>
       <input class="inp" id="pn-wc" list="pnl-wc" value="${esc(wcName)}" placeholder="거래처명" autocomplete="off" title="필수 — 협력사를 선택해야 조회됩니다" style="width:150px;min-width:150px;background:${F.wc?'#eaf3ff':'#fff7e6'};border:2px solid ${F.wc?'#7fa8e8':'#f0b429'};font-weight:600"><datalist id="pnl-wc">${wcOpts}</datalist>
       <button class="btn" id="pn-search" style="margin-left:4px">🔍 조회</button>
       <div class="spacer"></div>
     </div>
     ${(frac||msg||data.note)?`<div class="page-sub" style="font-size:11px;margin:2px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
       ${frac?`<span>일자셀=<b>완료/계획</b> · <span style="background:#ffff00;padding:0 5px;border-radius:3px">생산완료</span> <span style="background:#fac090;padding:0 5px;border-radius:3px">출하완료</span> <span style="background:#669900;color:#fff;padding:0 5px;border-radius:3px">키팅완료</span></span>`:''}
       ${msg?`<span style="color:#c0392b">⚠ ${esc(msg)}</span>`:''}
       ${data.note?`<span style="color:#b8860b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:52%" title="${esc(data.note)}">ℹ ${esc(data.note)}</span>`:''}</div>`:''}
     </div>
     <!-- ★flex:0 1 auto + max-height:100% (4787a13 확정) — flex:1 은 행이 적어도 표를 화면 끝까지
          늘려 표 아래가 흰 여백으로 남는다. 이 값이면 짧으면 내용만큼 줄고, 길면 스크롤된다. -->
     <div class="grid-wrap" style="flex:0 1 auto;min-height:0;max-height:100%;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl pn-grid" style="font-size:11px;white-space:nowrap"><thead><tr>
       <th class="num">SEQ</th><th>자도번작업처</th><th>라인</th><th>작업처</th><th>도번</th><th style="min-width:400px;width:400px">자도번LIST</th><th class="center">사급</th>
       <th class="num">LOT수량</th><th class="num">자재수량</th><th class="num">완료수량</th><th class="num">요청수량</th>
       ${dates.map(d=>`<th class="center"${isWkend(d)?' style="color:#c0392b"':''}>${esc(wlab(d))}</th>`).join('')}</tr></thead>
      <tbody>${bodyHTML()}</tbody></table></div>
    </div>`;
    const g=id=>c.querySelector(id);
    // ★자도번작업처 = [코드][🔍][업체명] 2칸 연동(2026-08-27 레거시 동일).
    //   업체명이 목록에 있으면 그 코드를, 없으면 코드칸 입력값을 쓴다.
    const syncInputs=()=>{
      const wn=g('#pn-wc').value.trim(), wcd=(g('#pn-wccode')||{value:''}).value.trim();
      const byNm=wcs.find(w=>(w.nm||w.cc)===wn);
      if(byNm) F.wc=byNm.cc;
      else if(wcd) F.wc=wcd;                       // 코드 직접 입력
      else if(!wn) F.wc='';
      F.days=g('#pn-days').value||31;F.part=g('#pn-part').value;F.assy=g('#pn-assy').value;};
    // 코드 입력 → 업체명 자동 채움
    const wcCode=g('#pn-wccode');
    if(wcCode)wcCode.onchange=()=>{const cd=wcCode.value.trim();const w=wcs.find(x=>x.cc===cd);
      if(w)g('#pn-wc').value=w.nm||w.cc;};
    // 업체명 선택 → 코드 자동 채움
    const wcName2=g('#pn-wc');
    if(wcName2)wcName2.onchange=()=>{const w=wcs.find(x=>(x.nm||x.cc)===wcName2.value.trim());
      if(w&&wcCode)wcCode.value=w.cc;};
    const wcFind=g('#pn-wcfind');
    if(wcFind)wcFind.onclick=()=>{const el=g('#pn-wc');if(el){el.focus();el.select();}};
    const ssel=g('#pn-src');if(ssel)ssel.onchange=e=>{F.src=e.target.value;F.wc='';loadWc().then(draw);};
    // 레거시 기준일자 위젯: 전일/익일/달력 → 자동 재조회
    bindLegacyDate(c,'pn-base',()=>F.from,(v)=>{F.from=v;syncInputs();load();});
    g('#pn-days').onchange=()=>{syncInputs();load();};
    g('#pn-search').onclick=()=>{syncInputs();load();};
    ['#pn-part','#pn-assy','#pn-wc','#pn-wccode'].forEach(id=>{const el=g(id);if(el)el.onkeyup=e=>{if(e.key==='Enter')g('#pn-search').click();};});
    // ★헤더 더블클릭 정렬(고정 12컬럼 + 일자 피벗) — tbody만 재렌더로 화살표·리사이저 보존. 합계행은 bodyHTML이 항상 맨끝에 붙임.
    if(!loading&&rowsCur.length){
      const KEYS=['seq','wcnm','line','workcenter','assy','jado','sagub','lot','matq','doneq','reqq'].concat(dates.map(d=>'d_'+d));
      enableSort(c,KEYS,()=>rowsCur,()=>{const tb=c.querySelector('tbody');if(tb)tb.innerHTML=bodyHTML();});
    }
  };
  // ★계획 기준일이 아직 캐시에 없으면(첫 진입) 받아서 반영한 뒤 그린다 — 2026-08-28.
  planBase().then(b=>{if(b&&b.iso)F.from=b.iso;}).catch(()=>{})
    .then(()=>loadWc()).then(draw);   // ★자동 전체조회 금지 — 협력사 선택 후 [조회]
};

/* ===== 일일 영업/매입 현황 (경영) — 조회화면(엑셀형). ① 매입/불출/실매입 by 구분 · 마감기준 · 공급가(원) ===== */
SCREEN.dailypurissue=(c)=>{
  const API=API_BASE;
  const _ymd=(d)=>{const p=n=>(''+n).padStart(2,'0');return `${(''+d.getFullYear()).slice(2)}${p(d.getMonth()+1)}${p(d.getDate())}`;};
  const _yst=(()=>{const d=new Date();d.setDate(d.getDate()-1);return _ymd(d);})();   // ★전일(어제)
  let F=null, loading=false, day=_yst;   // ★조회일 기본=전일. 실행 시 자동조회.
  const y2d=y=>(y&&y.length===6)?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';   // YYMMDD→date
  const d2y=d=>d?d.slice(2).replace(/-/g,''):'';                                             // date→YYMMDD
  const load=async(d)=>{loading=true;draw();
    try{const r=await fetch(`${API}/api/live/dailypurissue${d?('?date='+d):''}`);F=await r.json();day=F.date||d||'';}
    catch(e){F=null;}
    loading=false;draw();};
  const sec=(rows,tot,lbl,color)=>{
    let h=`<tr><td colspan="4" style="background:${color};color:#fff;font-weight:700;padding:4px 8px">${lbl}</td></tr>`;
    h+=(rows||[]).map(r=>`<tr><td style="padding-left:16px">${esc(r.gubun)}</td><td class="num">${wonI(r.cum)}</td><td class="num">${wonI(r.day)}</td><td class="num"><b>${wonI(r.tot)}</b></td></tr>`).join('');
    h+=`<tr style="background:#eef2f8;font-weight:700"><td>합계</td><td class="num">${wonI(tot.cum)}</td><td class="num">${wonI(tot.day)}</td><td class="num">${wonI(tot.tot)}</td></tr>`;
    return h;};
  const draw=()=>{
    // 매출요약 행(상반기/하반기/합계) — 0은 '-'
    const mrow=(lbl,o,bold)=>{const d=o||{h1:0,h2:0,tot:0};const z=v=>v?wonI(v):'-';return `<tr${bold?' style="font-weight:700"':''}><td>${lbl}</td><td class="num">${z(d.h1)}</td><td class="num">${z(d.h2)}</td><td class="num">${z(d.tot)}</td></tr>`;};
    c.innerHTML=`
     <div class="page-title">📋 일일 영업/매입 현황 <span style="font-size:12px;color:var(--muted);font-weight:400">확정입고·불출 마감기준 · 구분별 누적/당일/총 · 단위 원(공급가, VAT제외)</span></div>
     <div class="page-sub">조회일 선택 → 마감월초~전일=<b>누적</b>, 조회일=<b>당일</b>, 누적+당일=<b>총</b>. 매입=확정입고(CUST_TYPE+사급원소재), 불출=자재불출, 실매입=매입−불출.</div>
     <div class="toolbar">
       <label class="tl">조회일</label><input type="date" class="inp" id="dp-d" value="${y2d(day)}" style="width:150px">
       <button class="btn" id="dp-go">🔍 조회</button>
       <div class="spacer"></div>
       ${F?`<span class="rowcount">${esc(F.date||'')} 기준</span>`:''}
       <button class="btn xls" id="dp-xls">📥 엑셀</button>
     </div>
     ${loading?`<div style="padding:20px;color:#b8860b">불러오는 중…</div>`:(F?`
     <div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
     <div style="flex:0 0 auto;width:560px;max-width:560px;min-width:340px">
     <div class="grid-wrap" style="max-height:calc(100vh - 240px);overflow:auto"><table class="tbl fit" style="min-width:520px">
       <thead><tr><th style="text-align:left">구분</th><th class="num">누적</th><th class="num">당일</th><th class="num">총</th></tr></thead>
       <tbody>
         ${sec(F.pur,F.pur_tot,'매입','#1c47a0')}
         ${sec(F.out,F.out_tot,'불출(매출)','#8a5a1a')}
         ${sec(F.net,F.net_tot,'실매입 (매입 − 불출)','#1c7c3a')}
       </tbody></table></div>
       </div>
       ${F.sales?(()=>{const CG='<colgroup><col><col style="width:130px"><col style="width:54px"></colgroup>';const TS='width:100%;table-layout:fixed;background:#fff';return `
       <div style="flex:1;min-width:560px;display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
         <!-- 가운데: 재료비 → 사급율 (매출은 우측 '당일 실적'으로 이동·누적매출 패널 삭제) -->
         <div style="flex:1;min-width:280px">
           <div style="font-weight:700;color:#1c47a0;margin-bottom:4px">재료비</div>
           <table class="tbl" style="${TS}">${CG}<tbody>
             ${F.jaemat?`<tr style="font-weight:700;background:#f0f7f0"><td>재료비 <span style="font-weight:400;font-size:10px;color:#888">(기초+매입−기말)</span></td><td class="num">${wonI(F.jaemat.jaemat)}</td><td class="num"><b>${F.jaemat.jaemat_pct}%</b></td></tr>
             <tr><td style="padding-left:16px;color:#555">└ 기초재고 <span style="font-size:10px;color:#888">(7월말)</span></td><td class="num">${wonI(F.jaemat.gicho)}</td><td></td></tr>
             <tr><td style="padding-left:16px;color:#555">└ 매입총액</td><td class="num">${wonI(F.jaemat.pur)}</td><td></td></tr>
             <tr><td style="padding-left:16px;color:#555">└ 기말재고 <span style="font-size:10px;color:#888">(조회일)</span></td><td class="num">${wonI(F.jaemat.gimal)}</td><td></td></tr>
             <tr><td colspan="3" style="border-top:1px solid #dde3ea;font-size:10px;color:#888;padding-top:4px">상세 (매입/실매입/재고조정)</td></tr>`:''}
             <tr><td>매입</td><td class="num">${wonI(F.ratio.pur)}</td><td class="num"><b>${F.ratio.pur_pct}%</b></td></tr>
             <tr><td>실매입(조정전)</td><td class="num">${wonI(F.ratio.net)}</td><td class="num"><b>${F.ratio.net_pct}%</b></td></tr>
             ${(()=>{const J=F.jaego||{};const jc=v=>`color:${(v||0)<0?'#c0392b':'#1c7c3a'}`;const jr=(lb,v)=>`<tr><td style="padding-left:16px;color:#555">└ ${lb}</td><td class="num" style="${jc(v)}">${wonI(v||0)}</td><td></td></tr>`;return `<tr><td colspan="3" style="font-weight:600;color:#333;border-top:1px solid #dde3ea;padding-top:4px">재고조정 <span style="font-weight:400;font-size:10px;color:#888">(조회일 현재고 − 7월말 기초)</span></td></tr>`+jr('용접',J.weld)+jr('가공',J.gagong)+jr('영업',J.sales)+jr('자재',J.mat)+`<tr style="font-weight:700"><td>재고조정 합계</td><td class="num" style="${jc(J.total)}">${wonI(J.total||0)}</td><td></td></tr>`;})()}
             <tr style="font-weight:700"><td>실재고(조정후) <span style="font-weight:400;font-size:10px;color:#888">=실매입+증가</span></td><td class="num">${wonI(F.ratio.silrae)}</td><td class="num"><b>${F.ratio.silrae_pct}%</b></td></tr>
             <tr><td>LG매출액</td><td class="num">${wonI(F.ratio.lg_sales)}</td><td></td></tr>
           </tbody></table>
           <div style="font-weight:700;color:#8a5a1a;margin:10px 0 4px">사급율 <span style="font-weight:400;font-size:10px;color:#888">(LG사급 vs 당사ERP)</span></div>
           <table class="tbl" style="${TS}">${CG}<tbody>
             ${(()=>{const D=F.dae||{};const S=F.sagubyul||{};const dr=(D.dangsa_raw||0)-(D.lg_raw||0);const dp=(D.dangsa_part||0)-(D.lg_part||0);const dc=v=>`color:${(v||0)<0?'#c0392b':'#1c7c3a'}`;return `
             <tr><td>LG사급 − 원소재</td><td class="num">${wonI(D.lg_raw||0)}</td><td class="num"><b>${S.raw_pct}%</b></td></tr>
             <tr><td style="padding-left:12px;color:#555">당사ERP − 원소재</td><td class="num">${wonI(D.dangsa_raw||0)}</td><td></td></tr>
             <tr><td style="padding-left:12px">차액</td><td class="num" style="${dc(dr)}">${wonI(dr)}</td><td></td></tr>
             <tr><td>LG사급 − 부품</td><td class="num">${wonI(D.lg_part||0)}</td><td class="num"><b>${S.part_pct}%</b></td></tr>
             <tr><td style="padding-left:12px;color:#555">당사ERP − 부품</td><td class="num">${wonI(D.dangsa_part||0)}</td><td></td></tr>
             <tr><td style="padding-left:12px">차액</td><td class="num" style="${dc(dp)}">${wonI(dp)}</td><td></td></tr>
             <tr style="font-weight:700;border-top:1px solid #dde3ea"><td>차액 합계</td><td class="num" style="${dc(D.diff)}">${wonI(D.diff||0)}</td><td></td></tr>`;})()}
           </tbody></table>
         </div>
         <!-- 맨 오른쪽: 매출요약 (상반기/하반기/합계, 원·흰배경) -->
         ${F.maechul?`<div style="flex:1;min-width:340px">
           ${F.today?`<div style="font-weight:700;color:#1c7c3a;margin-bottom:4px">당일 실적 <span style="font-weight:400;font-size:10px;color:#888">(조회일 당일)</span></div>
           <table class="tbl" style="${TS}"><colgroup><col><col style="width:150px"></colgroup><tbody>
             <tr><td>매출 − 절삭</td><td class="num">${wonI(F.today.hyeon_cut)}</td></tr>
             <tr><td>매출 − 설치</td><td class="num">${wonI(F.today.hyeon_seol)}</td></tr>
             ${F.today.hyeon_etc?`<tr><td>매출 − 기타</td><td class="num">${wonI(F.today.hyeon_etc)}</td></tr>`:''}
             <tr style="font-weight:700;background:#eef2f8"><td>매출 합계</td><td class="num">${wonI(F.today.sales_hab)}</td></tr>
             <tr><td>사급 − 원소재</td><td class="num">${wonI(F.today.sagub_raw)}</td></tr>
             <tr><td>사급 − 부품</td><td class="num">${wonI(F.today.sagub_part)}</td></tr>
             <tr style="font-weight:700;background:#eef2f8"><td>사급 합계</td><td class="num">${wonI(F.today.sagub_hab)}</td></tr>
           </tbody></table>
           <div style="height:14px"></div>`:''}
           <div style="font-weight:700;color:#1c47a0;margin-bottom:4px">매출요약</div>
           <table class="tbl" style="${TS}"><colgroup><col><col style="width:110px"><col style="width:110px"><col style="width:110px"></colgroup><thead><tr><th style="text-align:left">구분</th><th class="num">상반기</th><th class="num">하반기</th><th class="num">합계</th></tr></thead><tbody>
             ${mrow('현매출(절삭)',F.maechul.hyeon_cut)}
             ${mrow('현매출(설치)',F.maechul.hyeon_seol)}
             ${(F.maechul.hyeon_etc&&F.maechul.hyeon_etc.tot)?mrow('현매출(기타)',F.maechul.hyeon_etc):''}
             ${mrow('현매출(합계)',F.maechul.hyeon_hab,true)}
             ${mrow('추가매출(절삭)',F.maechul.chuga_cut)}
             ${mrow('추가매출(설치)',F.maechul.chuga_seol)}
             ${mrow('총예상매출',F.maechul.chong,true)}
             ${mrow('사급-원재료',F.maechul.sagub_raw)}
             ${mrow('사급-부품(실적)',F.maechul.sagub_part)}
             ${mrow('추가-사급부품(예상)',F.maechul.sagub_part_fc)}
             ${mrow('사급-부품(합계)',F.maechul.sagub_part_sum,true)}
             ${mrow('사급-합계',F.maechul.sagub_hab,true)}
             ${mrow('LG 수금금액',F.maechul.lg_sugum,true)}
           </tbody></table></div>`:''}
       </div>`})():''}
       </div>`:`<div style="padding:20px;color:#8aa0bd">조회일을 선택하고 [조회]를 누르세요.</div>`)}`;
    const gd=()=>d2y(c.querySelector('#dp-d').value);
    c.querySelector('#dp-go').onclick=()=>load(gd());
    c.querySelector('#dp-d').onkeyup=e=>{if(e.key==='Enter')load(gd());};   // Enter로도 조회
    c.querySelector('#dp-xls').onclick=()=>{
      if(!F)return;
      const hd=['섹션','구분','누적','당일','총'];
      const rows=[];
      const push=(sc,list,tot)=>{(list||[]).forEach(r=>rows.push([sc,r.gubun,r.cum,r.day,r.tot]));rows.push([sc,'합계',tot.cum,tot.day,tot.tot]);};
      push('매입',F.pur,F.pur_tot);push('불출',F.out,F.out_tot);push('실매입',F.net,F.net_tot);
      if(F.today){rows.push([]);rows.push(['당일실적','매출-절삭',F.today.hyeon_cut]);rows.push(['당일실적','매출-설치',F.today.hyeon_seol]);rows.push(['당일실적','매출-기타',F.today.hyeon_etc]);rows.push(['당일실적','매출합계',F.today.sales_hab]);rows.push(['당일실적','사급-원소재',F.today.sagub_raw]);rows.push(['당일실적','사급-부품',F.today.sagub_part]);rows.push(['당일실적','사급합계',F.today.sagub_hab]);}
      if(F.jaemat){rows.push([]);rows.push(['재료비','재료비',F.jaemat.jaemat,'',F.jaemat.jaemat_pct+'%']);rows.push(['재료비','기초재고',F.jaemat.gicho]);rows.push(['재료비','매입총액',F.jaemat.pur]);rows.push(['재료비','기말재고',F.jaemat.gimal]);}
      if(F.sales){rows.push([]);
        rows.push(['매출','현매출-절삭',F.sales.hyeon_cut]);rows.push(['매출','현매출-설치',F.sales.hyeon_seol]);
        rows.push(['매출','현매출-기타',F.sales.hyeon_etc]);rows.push(['매출','LG매출합계',F.sales.lg_sales]);
        rows.push(['매입비율','매입/LG매출',F.ratio.pur,'',F.ratio.pur_pct+'%']);rows.push(['매입비율','실매입/LG매출',F.ratio.net,'',F.ratio.net_pct+'%']);
        {const J=F.jaego||{};rows.push(['재고조정','용접(현재고−기초)',J.weld]);rows.push(['재고조정','가공',J.gagong]);rows.push(['재고조정','영업',J.sales]);rows.push(['재고조정','자재',J.mat]);rows.push(['재고조정','합계',J.total]);rows.push(['매입비율','실재고(조정후)',F.ratio.silrae,'',F.ratio.silrae_pct+'%']);}
        {const D=F.dae||{};const S=F.sagubyul||{};const dr=(D.dangsa_raw||0)-(D.lg_raw||0);const dp=(D.dangsa_part||0)-(D.lg_part||0);
          rows.push(['사급율','LG사급-원소재',D.lg_raw,'',S.raw_pct+'%']);rows.push(['사급율','당사ERP-원소재',D.dangsa_raw]);rows.push(['사급율','차액(원소재)',dr]);
          rows.push(['사급율','LG사급-부품',D.lg_part,'',S.part_pct+'%']);rows.push(['사급율','당사ERP-부품',D.dangsa_part]);rows.push(['사급율','차액(부품)',dp]);
          rows.push(['사급율','차액 합계',D.diff]);}
        if(F.maechul){const M=F.maechul;const mr=(lb,k)=>{const v=M[k]||{};rows.push(['매출요약',lb,v.h1,v.h2,v.tot]);};
          mr('현매출(절삭)','hyeon_cut');mr('현매출(설치)','hyeon_seol');mr('현매출(기타)','hyeon_etc');mr('현매출(합계)','hyeon_hab');
          mr('추가매출(절삭)','chuga_cut');mr('추가매출(설치)','chuga_seol');mr('총예상매출','chong');
          mr('사급-원재료','sagub_raw');mr('사급-부품(실적)','sagub_part');mr('추가-사급부품(예상)','sagub_part_fc');
          mr('사급-부품(합계)','sagub_part_sum');mr('사급-합계','sagub_hab');mr('LG수금금액','lg_sugum');}}
      downloadCSV(`일일영업매입현황_${F.date}.csv`,hd,rows);};
  };
  load(day);   // ★실행 시 전일자로 자동조회
};


/* ==== 거래명세표 수정 (협력사) — 레거시 w_pr_outside_030_new 이식 ====
   세트납품서 단위 납품내역 조회 + 수량수정·삭제 + 출력 3종 재발행.
   ★입고완료건(CONFIRM_FLAG='1')은 조회·인쇄만 — 레거시 동일 메시지.
   자도번/사용수량/자재수량 = nx.PU_T_SET_INPUT_REQ_DTL 실적(마스터 유추 아님). */
SCREEN.delivedit=(c)=>{
  const API=API_BASE;
  // ★num 은 전역이 아니다(core.js 의 num 은 _mkMagam 지역) — 여기서 선언
  const num=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const canW=(typeof PERM!=='undefined')?PERM.canEdit('delivedit'):true;
  const _t=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  const y6=(s)=>{const d=(''+(s||'')).replace(/\D/g,'');return d.length>=8?d.slice(2,8):d;};
  const hm=(s)=>{s=''+(s||'');return s.length>=6?`${s.slice(0,2)}:${s.slice(2,4)}:${s.slice(4,6)}`:s;};
  const d6=(s)=>{s=''+(s||'');return s.length===6?`${s.slice(0,2)}/${s.slice(2,4)}/${s.slice(4,6)}`:s;};

  let fr=_t(), to=_t(), cust='', doban='', jado='';   // ★납품기간 기본 = 당일
  let rows=[], loading=false, msg='', cnt=0, heads=0, sheets=0, editable=0;
  let outStmt=true, outTag=true, outInsp=true;
  let custs=[], dobans=[], jados=[];

  const loadCusts=async()=>{try{
    const r=await fetch(`${API}/api/delivedit/custs`);const j=await r.json();
    custs=j.rows||[];}catch(e){custs=[];}};

  // ★도번·자도번 오토컴플리트(§3) — 실제 납품내역에 있는 것만.
  //   기간·거래처가 바뀌면 후보도 그 범위로 좁혀 다시 채운다.
  const loadItems=async()=>{
    const qs=`from_ymd=${y6(fr)}&to_ymd=${y6(to)}&cust=${encodeURIComponent(cust.trim())}`;
    try{
      const [a,b]=await Promise.all([
        fetch(`${API}/api/delivedit/items?kind=doban&${qs}`).then(r=>r.json()),
        fetch(`${API}/api/delivedit/items?kind=jadoban&${qs}`).then(r=>r.json())]);
      dobans=a.rows||[];jados=b.rows||[];
    }catch(e){dobans=[];jados=[];}
  };

  const load=async()=>{loading=true;msg='';draw();
    try{
      const u=`${API}/api/delivedit/list?from_ymd=${y6(fr)}&to_ymd=${y6(to)}`
        +`&cust=${encodeURIComponent(cust.trim())}&doban=${encodeURIComponent(doban.trim())}`
        +`&jadoban=${encodeURIComponent(jado.trim())}`;
      const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();
      rows=j.rows||[];cnt=j.cnt||0;heads=j.heads||0;sheets=j.sheets||0;editable=j.editable||0;
    }catch(e){msg='조회 실패 — '+e.message;rows=[];cnt=heads=sheets=editable=0;}
    loading=false;draw();};

  // ★입고완료건은 조회만(레거시 동일). 미입고건만 수량수정.
  const editQty=async(r)=>{
    if(!canW){alert('권한이 없습니다.');return;}
    if(r.cf==='1'){alert('입고완료건은 조회만 가능합니다.');return;}
    const v=prompt(`납품수량 수정\n\nSET${r.sheet_no} · ${r.doban}\n${r.dnm||''}\n\n현재 ${r.set_qty}`,r.set_qty);
    if(v===null)return;
    const q=Number(v);
    if(!(q>0)){alert('납품수량은 0보다 커야 합니다.');return;}
    try{
      const res=await fetch(`${API}/api/delivedit/update`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({sheet_no:r.sheet_no,cc:r.cc,doban:r.doban,hms:r.hms,qty:q})});
      const j=await res.json().catch(()=>({}));
      if(!res.ok)throw new Error(j.detail||('HTTP '+res.status));
      alert(`수정되었습니다.\n\n${r.doban}  ${j.old_qty} → ${j.new_qty}\n상세 ${j.updated}행 · 헤더 ${j.head_updated}행`);
      load();
    }catch(e){alert('수정 실패\n\n'+e.message);}
  };

  const delRow=async(r)=>{
    if(!canW){alert('권한이 없습니다.');return;}
    if(r.cf==='1'){alert('입고완료건은 조회만 가능합니다.');return;}
    if(!confirm(`납품내역을 삭제하시겠습니까?\n\nSET${r.sheet_no} · ${r.doban}\n세트수량 ${r.set_qty}`))return;
    try{
      const res=await fetch(`${API}/api/delivedit/delete`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({sheet_no:r.sheet_no,cc:r.cc,doban:r.doban,hms:r.hms})});
      const j=await res.json().catch(()=>({}));
      if(!res.ok)throw new Error(j.detail||('HTTP '+res.status));
      alert(`삭제되었습니다. (상세 ${j.deleted}행 · 헤더 ${j.head_deleted}행)`);
      load();
    }catch(e){alert('삭제 실패\n\n'+e.message);}
  };

  // 출력 3종 — 입고완료건도 재발행 가능(레거시 동일)
  const doPrint=async(r)=>{
    const kinds=[];
    if(outStmt)kinds.push(['stmt','거래명세서']);
    if(outTag)kinds.push(['tag','입고태그']);
    if(outInsp)kinds.push(['insp','출하검사성적서']);
    if(!kinds.length){alert('출력구분을 하나 이상 선택하세요.');return;}
    const secs=[];
    for(const [k,nm] of kinds){
      try{
        const u=`${API}/api/delivedit/print?sheet_no=${encodeURIComponent(r.sheet_no)}`
          +`&cc=${encodeURIComponent(r.cc)}&hms=${encodeURIComponent(r.hms)}&kind=${k}`;
        const res=await fetch(u);const j=await res.json();
        if(!res.ok)throw new Error(j.detail||('HTTP '+res.status));
        secs.push(pv(j));
      }catch(e){alert(`${nm} 출력 실패\n\n`+e.message);return;}
    }
    const w=window.open('','_blank');
    if(!w){alert('팝업이 차단되었습니다. 브라우저 설정을 확인하세요.');return;}
    w.document.write(`<!doctype html><html><head><meta charset="utf-8">
      <title>거래명세표 출력 — SET${esc(r.sheet_no)}</title><style>
      @page{size:A4;margin:10mm}
      body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;font-size:12px;color:#111}
      .pg{page-break-after:always}.pg:last-child{page-break-after:auto}
      h2{text-align:center;letter-spacing:6px;margin:0 0 10px}
      .hd{display:flex;gap:18px;font-size:12px;margin-bottom:8px;flex-wrap:wrap}
      table{width:100%;border-collapse:collapse;font-size:11.5px}
      th,td{border:1px solid #666;padding:3px 5px}
      th{background:#eef2f8;text-align:center}
      td.n{text-align:right;font-variant-numeric:tabular-nums}
      td.c{text-align:center}
      tfoot td{font-weight:700;background:#f6f8fc}
      </style></head><body>${secs.join('')}</body></html>`);
    w.document.close();
    setTimeout(()=>{w.focus();w.print();},350);
  };

  const pv=(j)=>`<div class="pg"><h2>${esc(j.title)}</h2>
    <div class="hd"><b>납품처</b> ${esc(j.cnm||j.cc)}
      <b>세트납품서</b> SET${esc(j.sheet_no)}
      <b>납품일자</b> ${esc(d6(j.ymd))} ${esc(hm(j.hms))}</div>
    <table><thead><tr>
      <th style="width:36px">No</th><th>도번</th><th>품명</th><th>규격</th>
      <th style="width:64px">세트수량</th><th>자도번</th><th>자재품명</th>
      <th style="width:52px">사용</th><th style="width:64px">자재수량</th>
    </tr></thead><tbody>
    ${(j.rows||[]).map((x,i)=>`<tr>
      <td class="c">${i+1}</td><td>${esc(x.doban)}</td><td>${esc(x.dnm||'')}</td>
      <td>${esc(x.dspec||'')}</td><td class="n">${num(x.set_qty)}</td>
      <td>${esc(x.jadoban||'')}</td><td>${esc(x.jnm||'')}</td>
      <td class="n">${num(x.use_qty)}</td><td class="n">${num(x.mat_qty)}</td>
    </tr>`).join('')}
    </tbody><tfoot><tr>
      <td colspan="4" class="c">합계 (${j.cnt}건)</td><td class="n">${num(j.sum_set)}</td>
      <td colspan="3"></td><td class="n">${num(j.sum_mat)}</td>
    </tr></tfoot></table></div>`;

  const draw=()=>{
    c.innerHTML=`
     <div style="display:flex;flex-direction:column;height:100%;min-height:0">
     <div class="page-title">📝 거래명세표 수정 <span style="font-size:12px;color:var(--muted);font-weight:400">세트납품 내역 수정·삭제·재출력 · nx</span></div>
     <div class="page-sub">세트납품서 단위 납품내역. <b>입고완료건은 조회·출력만 가능</b>(수정·삭제 불가) — 레거시 <code>w_pr_outside_030_new</code> 동일. 원천 <code>nx.PU_T_SET_INPUT_REQ_DTL</code></div>
     <div class="toolbar">
       <label class="tl">납품기간</label>
       <input type="date" class="inp" id="de-fr" value="${esc(fr)}" style="width:150px">
       <span class="mut">~</span>
       <input type="date" class="inp" id="de-to" value="${esc(to)}" style="width:150px">
       <label class="tl">자도번작업처</label>
       <input class="inp" id="de-cu" list="de-cul" value="${esc(cust)}" placeholder="거래처명/코드" style="width:170px">
       <datalist id="de-cul">${custs.map(x=>`<option value="${esc(x.nm)}">${esc(x.cc)}</option>`).join('')}</datalist>
       <label class="tl">도번</label>
       <input class="inp" id="de-do" list="de-dol" value="${esc(doban)}" placeholder="도번/품명" style="width:140px">
       <datalist id="de-dol">${dobans.map(x=>`<option value="${esc(x.code)}">${esc(x.nm||'')}</option>`).join('')}</datalist>
       <label class="tl">자도번</label>
       <input class="inp" id="de-ja" list="de-jal" value="${esc(jado)}" placeholder="자도번/품명" style="width:140px">
       <datalist id="de-jal">${jados.map(x=>`<option value="${esc(x.code)}">${esc(x.nm||'')}</option>`).join('')}</datalist>
       <button class="btn" id="de-go">🔍 조회</button>
       <div class="spacer"></div>
       <label class="tl">출력구분</label>
       <label class="ck"><input type="checkbox" id="de-o1" ${outStmt?'checked':''}> 거래명세서</label>
       <label class="ck"><input type="checkbox" id="de-o2" ${outTag?'checked':''}> 입고태그</label>
       <label class="ck"><input type="checkbox" id="de-o3" ${outInsp?'checked':''}> 출하검사성적서</label>
       <span class="rowcount">${cnt}건 · 납품서 ${sheets} · 수정가능 <b>${editable}</b></span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap de-wrap"><table class="tbl de-tbl">
      <thead><tr>
        <th style="width:74px">납품일자</th><th style="width:66px">납품일시</th>
        <th style="width:98px">세트납품서번호</th><th style="width:124px">도번</th>
        <th style="width:64px">세트수량</th><th style="width:70px">입고완료</th>
        <th style="width:38px">당일</th><th style="width:140px">자도번</th>
        <th style="width:62px">사용수량</th><th style="width:64px">자재수량</th>
        <th style="width:96px">처리</th>
      </tr></thead>
      <tbody>${loading?spinRow(11):(rows.length?rows.map(r=>{
        const f=r.first, done=r.cf==='1';
        return `<tr class="${f?'de-first':''} ${done?'de-done':''}">
        ${f?`<td class="c" rowspan="${r.span}">${esc(d6(r.ymd))}</td>
             <td class="c" rowspan="${r.span}">${esc(hm(r.hms))}</td>
             <td class="c" rowspan="${r.span}"><b>SET${esc(r.sheet_no)}</b></td>
             <td rowspan="${r.span}" title="${esc(r.dnm||'')}"><b>${esc(r.doban)}</b></td>
             <td class="n" rowspan="${r.span}">${num(r.set_qty)}</td>`:''}
        <td class="c">${done?'<span class="de-bd on">입고완료</span>':'<span class="de-bd">미입고</span>'}</td>
        <td class="c">${esc(r.am_pm||'')}</td>
        <td title="${esc(r.jnm||'')}">${esc(r.jadoban||'')}</td>
        <td class="n">${num(r.use_qty)}</td>
        <td class="n">${num(r.mat_qty)}</td>
        ${f?`<td class="c" rowspan="${r.span}" style="white-space:nowrap">
          <button class="btn de-mini de-ed" data-i="${rows.indexOf(r)}" ${(done||!canW)?'disabled':''} title="${done?'입고완료건은 조회만 가능합니다':'납품수량 수정'}">✎</button>
          <button class="btn de-mini de-dl" data-i="${rows.indexOf(r)}" ${(done||!canW)?'disabled':''} title="${done?'입고완료건은 조회만 가능합니다':'삭제'}">🗑</button>
          <button class="btn de-mini de-pr" data-i="${rows.indexOf(r)}" title="선택한 출력구분으로 인쇄">🖨</button>
        </td>`:''}
      </tr>`;}).join('')
        :`<tr><td colspan="11" class="empty">조회 결과 없음</td></tr>`)}</tbody>
     </table></div>
     </div>
     <style>
       .de-wrap{flex:0 1 auto;min-height:0;max-height:100%;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px;box-shadow:0 3px 12px rgba(30,45,70,.08)}
       .de-tbl{font-size:12px;white-space:nowrap;width:100%}
       .de-tbl th,.de-tbl td{padding:3px 6px;border-bottom:1px solid #e6ecf5}
       .de-tbl thead th{position:sticky;top:0;background:#dbe6f5;z-index:2;border-bottom:1px solid #9db4d4;text-align:center}
       .de-tbl td.n{text-align:right;font-variant-numeric:tabular-nums}
       .de-tbl td.c{text-align:center}
       .de-tbl tr.de-first td{border-top:1px solid #b9cbe4}
       .de-tbl tbody tr:hover td{background:#eaf2fd}
       .de-tbl tr.de-done td{background:#f7f9f7}
       .de-tbl tr.de-done:hover td{background:#eef4ee}
       .de-bd{font-size:11px;padding:1px 7px;border-radius:10px;background:#eee;color:#777}
       .de-bd.on{background:#e5f3e8;color:#2e7d32;font-weight:700}
       .de-mini{padding:1px 6px;font-size:11px}
       .ck{display:inline-flex;align-items:center;gap:3px;font-size:12px;color:#445;margin-right:2px}
     </style>`;
    const g=(id)=>c.querySelector(id);
    // 기간·거래처가 바뀌면 도번/자도번 후보를 그 범위로 다시 채운다(포커스 유지 위해 부분갱신)
    const refill=async()=>{await loadItems();
      const dl=g('#de-dol'), jl=g('#de-jal');
      if(dl)dl.innerHTML=dobans.map(x=>`<option value="${esc(x.code)}">${esc(x.nm||'')}</option>`).join('');
      if(jl)jl.innerHTML=jados.map(x=>`<option value="${esc(x.code)}">${esc(x.nm||'')}</option>`).join('');};
    g('#de-fr').onchange=e=>{fr=e.target.value;refill();};
    g('#de-to').onchange=e=>{to=e.target.value;refill();};
    const cu=g('#de-cu');
    cu.oninput=e=>{cust=e.target.value;};
    cu.onchange=e=>{cust=e.target.value;refill();};   // 목록에서 고르면 후보 재구성
    cu.onkeyup=e=>{if(e.key==='Enter')load();};
    const dv=g('#de-do');dv.oninput=e=>{doban=e.target.value;};
    dv.onchange=e=>{doban=e.target.value;};
    dv.onkeyup=e=>{if(e.key==='Enter')load();};
    const jv=g('#de-ja');jv.oninput=e=>{jado=e.target.value;};
    jv.onchange=e=>{jado=e.target.value;};
    jv.onkeyup=e=>{if(e.key==='Enter')load();};
    g('#de-go').onclick=()=>load();
    g('#de-o1').onchange=e=>{outStmt=e.target.checked;};
    g('#de-o2').onchange=e=>{outTag=e.target.checked;};
    g('#de-o3').onchange=e=>{outInsp=e.target.checked;};
    c.querySelectorAll('.de-ed').forEach(b=>b.onclick=()=>editQty(rows[+b.dataset.i]));
    c.querySelectorAll('.de-dl').forEach(b=>b.onclick=()=>delRow(rows[+b.dataset.i]));
    c.querySelectorAll('.de-pr').forEach(b=>b.onclick=()=>doPrint(rows[+b.dataset.i]));
  };

  draw();
  Promise.all([loadCusts(),loadItems()]).then(()=>{draw();load();});
};
