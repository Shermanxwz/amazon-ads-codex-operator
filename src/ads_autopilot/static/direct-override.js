const directDurationNames={"30m":"30 分钟","1h":"1 小时","2h":"2 小时","permanent":"永久"};
let directOverrideState=null;
function directRemainingText(state){
  if(!state?.armed)return '未授权';
  if(state.permanent)return '永久授权 · 直到你切回其他模式';
  const seconds=Math.max(0,Number(state.remaining_seconds||0));
  const m=Math.floor(seconds/60),s=seconds%60;
  return `${m}分${String(s).padStart(2,'0')}秒后自动回到 ${state.return_mode||'observe'}`;
}
function renderDirectOverride(state){
  directOverrideState=state||{};
  const armed=!!state?.armed,active=!!state?.command_active;
  const pill=$('direct-override-pill'),copy=$('direct-override-copy'),timer=$('direct-override-timer');
  if(pill)pill.textContent=armed?(active?'DIRECT COMMAND RUNNING':'OWNER DIRECT ARMED'):'OFF';
  if(copy)copy.textContent=armed?'授权窗口已打开。你现在可以直接对 Codex 说特殊 Sponsored Products 操作；AI 只能在这个窗口内通过 direct cycle 使用全面广告权限，普通定时周期仍使用日常策略。':'未打开主人直令窗口。AI 仍按日常 Owner Policy 与预算边界运行。';
  if(timer)timer.textContent=directRemainingText(state);
  if(armed){$('mode-pill').textContent=active?'DIRECT RUNNING':'OWNER DIRECT';$('mode-copy').textContent=`主人直令窗口：${directDurationNames[state.duration]||state.duration}。Emergency Stop、密封执行、一次性 grant、独立验证与账户/profile 身份边界仍然有效。`;}
}
async function loadDirectOverride(){if($('app')?.hidden)return;try{renderDirectOverride(await api('/api/direct-override'))}catch{}}
document.querySelectorAll('[data-direct-duration]').forEach(b=>b.addEventListener('click',async()=>{
  const duration=b.dataset.directDuration;const permanent=duration==='permanent';
  const msg=permanent?'确认开启永久 Owner Direct Override？该授权不会自动到期，直到你主动切回全托管/仅观察/暂停，或触发 Emergency Stop。':`确认开启 ${directDurationNames[duration]||duration} Owner Direct Override？窗口内你可以直接口头指令 Codex 执行特殊广告操作。`;
  if(!confirm(msg))return;
  try{const d=await api('/api/direct-override/arm',{method:'POST',body:JSON.stringify({duration})});renderDirectOverride(d.direct_override||{});notice(`Owner Direct Override 已开启：${directDurationNames[duration]||duration}`);await refresh();await loadDirectOverride();}catch(e){notice(e.message,true)}
}));
$('direct-override-clear')?.addEventListener('click',async()=>{if(!confirm('确认退出 Owner Direct Override，并回到授权前的运行模式？'))return;try{const d=await api('/api/direct-override/clear',{method:'POST',body:'{}'});renderDirectOverride(d.direct_override||{});notice('Owner Direct Override 已关闭');await refresh();await loadDirectOverride()}catch(e){notice(e.message,true)}});
const baseRender=render;render=function(d,audit){baseRender(d,audit);renderDirectOverride(d.owner?.direct_override||{})};
$('refresh')?.addEventListener('click',()=>setTimeout(loadDirectOverride,50));document.querySelectorAll('[data-mode]').forEach(b=>b.addEventListener('click',()=>setTimeout(loadDirectOverride,50)));$('emergency-stop')?.addEventListener('click',()=>setTimeout(loadDirectOverride,50));$('emergency-clear')?.addEventListener('click',()=>setTimeout(loadDirectOverride,50));
setTimeout(loadDirectOverride,0);
setInterval(()=>{if(directOverrideState?.armed&&!directOverrideState.permanent&&directOverrideState.remaining_seconds!=null){directOverrideState={...directOverrideState,remaining_seconds:Math.max(0,Number(directOverrideState.remaining_seconds)-1)};const timer=$('direct-override-timer');if(timer)timer.textContent=directRemainingText(directOverrideState);}},1000);
setInterval(loadDirectOverride,10000);
