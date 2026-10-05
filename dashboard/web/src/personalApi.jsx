import React, {useCallback, useEffect, useRef, useState} from 'react';

export const today = () => new Intl.DateTimeFormat('en-CA', {timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
export const format = (value, digits = 1) => value == null || value === '' ? 'Sem dado' : Number(value).toLocaleString('pt-BR', {maximumFractionDigits:digits});
export const dayLabel = value => value ? new Date(value.slice(0,10)+'T12:00:00').toLocaleDateString('pt-BR') : 'Sem data';
export const optionalNumber = value => value === '' || value == null ? null : Number(value);
export const array = value => Array.isArray(value) ? value : [];

export function notifyIntegrationChange() {
  window.dispatchEvent(new Event('ascentiq-integrations-changed'));
  try {localStorage.setItem('ascentiq-integrations-updated',String(Date.now()));} catch {}
}

export async function personalApi(path, body) {
  const response = await fetch('/api/'+path, {credentials:'same-origin',cache:'no-store',...(body !== undefined ? {method:'POST',headers:{'Content-Type':'application/json','X-AscentIQ-Request':'1'},body:JSON.stringify(body)} : {})});
  const payload = await response.json().catch(()=>({}));
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event('ascentiq-session-expired'));
    const detail = typeof payload.detail === 'string' ? payload.detail : response.status === 409 ? 'Os dados mudaram. Consulte novamente antes de salvar.' : 'Não foi possível concluir. Confira os campos e tente novamente.';
    const error = new Error(detail); error.status = response.status; throw error;
  }
  return payload;
}

export function usePersonal(day, days = 14) {
  const [value,setValue] = useState(null), [loading,setLoading] = useState(true), [error,setError] = useState('');
  const version = useRef(0);
  const load = useCallback(async()=>{
    const request = ++version.current; setLoading(true); setError('');
    try { const result = await personalApi(`personal?day=${encodeURIComponent(day)}&days=${days}`); if(request === version.current) setValue(result); return result; }
    catch(e) { if(request === version.current) setError(e.message); throw e; }
    finally { if(request === version.current) setLoading(false); }
  },[day,days]);
  useEffect(()=>{setValue(null);load().catch(()=>{});return()=>{version.current++;};},[load]);
  const save = async(kind, record, remove = false)=>{
    try {
      const body = remove ? {id:record.id,revision:value?.state?.revision} : ['profile','preferences'].includes(kind) ? {value:record,revision:value?.state?.revision} : {record,revision:value?.state?.revision};
      await personalApi(`personal/${kind}${remove ? '/remove' : ''}`, body);
      return await load();
    } catch(e) { if(e.status === 409) await load().catch(()=>{}); throw e; }
  };
  return {value,state:value?.state || {},summary:value?.summary || {},loading,error,load,save};
}

export function ErrorNotice({error}) { return error ? <div className="error" role="alert">{error}</div> : null; }
export function StatusNotice({message}) { return message ? <div className="success-note" role="status">{message}</div> : null; }
export function PageHeading({kicker,title,children}) { return <div className="page-title"><div className="eyebrow">{kicker}</div><h1>{title}</h1>{children && <p>{children}</p>}</div>; }
export function PersonalLoading({model}) { return <><ErrorNotice error={model.error}/>{model.loading && <p className="muted" role="status">Consultando seus registros…</p>}{model.error && <button onClick={()=>model.load().catch(()=>{})}>Tentar novamente</button>}</>; }
