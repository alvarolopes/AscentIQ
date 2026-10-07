import React, {useEffect, useId, useRef, useState} from 'react';
import {createPortal} from 'react-dom';

const dialogs = [];
let previousOverflow = '';
let previousInert = false;
let originFocus = null;
const focusable = 'button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex]:not([tabindex="-1"])';

export function Modal({title,onClose,children,busy=false,dirty=false,className=''}) {
  const id=useId(), panel=useRef(null), triggerRef=useRef(document.activeElement), state=useRef({busy,dirty,onClose});
  const [confirmDiscard,setConfirmDiscard]=useState(false);
  state.current={busy,dirty,onClose};
  function close() {
    if(state.current.busy)return;
    if(state.current.dirty){setConfirmDiscard(true);return;}
    state.current.onClose();
  }
  useEffect(()=>{
    const trigger=triggerRef.current, root=document.getElementById('root');
    if(!dialogs.length){originFocus=trigger;previousOverflow=document.body.style.overflow;previousInert=root?.inert || false;document.body.style.overflow='hidden';if(root)root.inert=true;}
    dialogs.push(id);
    const timer=requestAnimationFrame(()=>{const first=panel.current?.querySelector('[autofocus],'+focusable);(first || panel.current)?.focus();});
    function key(event){
      if(dialogs.at(-1)!==id)return;
      if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();}
      if(event.key==='Tab'){
        const nodes=[...panel.current.querySelectorAll(focusable)].filter(n=>n.getClientRects().length && !n.closest('[hidden]'));
        if(!nodes.length){event.preventDefault();panel.current.focus();return;}
        if(event.shiftKey && (document.activeElement===nodes[0] || document.activeElement===panel.current)){event.preventDefault();nodes.at(-1).focus();}
        else if(!event.shiftKey && document.activeElement===nodes.at(-1)){event.preventDefault();nodes[0].focus();}
      }
    }
    function focus(event){if(dialogs.at(-1)===id && panel.current && !panel.current.contains(event.target))panel.current.focus();}
    document.addEventListener('keydown',key);document.addEventListener('focusin',focus);
    return()=>{cancelAnimationFrame(timer);document.removeEventListener('keydown',key);document.removeEventListener('focusin',focus);const index=dialogs.indexOf(id);if(index>=0)dialogs.splice(index,1);if(!dialogs.length){document.body.style.overflow=previousOverflow;if(root)root.inert=previousInert;const origin=originFocus;originFocus=null;if(origin?.isConnected)origin.focus();}else if(trigger?.isConnected)trigger.focus();};
  },[id]);
  return <>{createPortal(<div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget && dialogs.at(-1)===id)close();}}><section ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={id} aria-busy={busy} className={'modal '+className}><header className="modal-heading"><h2 id={id}>{title}</h2><button type="button" className="icon-button" aria-label={'Fechar '+title} disabled={busy} onClick={close}>✕</button></header><div className="modal-body">{children}</div></section></div>,document.body)}{confirmDiscard&&<Modal title="Descartar rascunho?" onClose={()=>setConfirmDiscard(false)}><p>As alterações ainda não foram salvas.</p><div className="actions"><button type="button" onClick={()=>setConfirmDiscard(false)}>Continuar editando</button><button type="button" className="danger" onClick={()=>{setConfirmDiscard(false);state.current.onClose();}}>Descartar rascunho</button></div></Modal>}</>;
}

export function InfoButton({title='Como interpretar',children}) {
  const [open,setOpen]=useState(false);
  return <><button type="button" className="info-button" aria-label={title} title={title} onClick={()=>setOpen(true)}>i</button>{open&&<Modal title={title} onClose={()=>setOpen(false)}>{children}</Modal>}</>;
}

export function PagedList({items=[],children,renderItem,resetKey='',label='registros',empty=null,pagination,onPageChange,onPageSizeChange}) {
  const [page,setPage]=useState(1), [size,setSize]=useState(10);
  const selectedSize=pagination ? (pagination.page_size===15?15:10) : size;
  const total=pagination?.total ?? items.length, pages=Math.max(1,pagination?.pages ?? Math.ceil(total/selectedSize)), current=Math.min(pagination?.page ?? page,pages);
  useEffect(()=>setPage(1),[resetKey]);
  useEffect(()=>{if(page>pages)setPage(pages);},[page,pages]);
  const visible=pagination ? items.slice(0,selectedSize) : items.slice((current-1)*selectedSize,current*selectedSize);
  const changePage=value=>pagination ? onPageChange?.(value) : setPage(value);
  return <div className="paged-list">{total || !empty ? (typeof children==='function' ? children(visible) : visible.map(renderItem)) : empty}{total>10&&<nav className="pagination" aria-label={'Paginação de '+label}><span className="small muted">{(current-1)*selectedSize+1}–{Math.min((current-1)*selectedSize+visible.length,total)} de {total}</span><div><label>Por página<select aria-label={'Registros por página de '+label} value={selectedSize} onChange={e=>{const count=Number(e.target.value);if(pagination)onPageSizeChange?.(count);else{setSize(count);setPage(1);}}}><option value={10}>10</option><option value={15}>15</option></select></label><button type="button" disabled={current<=1} aria-label={'Página anterior de '+label} onClick={()=>changePage(current-1)}>Anterior</button><span className="small" aria-live="polite">{current} / {pages}</span><button type="button" disabled={current>=pages} aria-label={'Próxima página de '+label} onClick={()=>changePage(current+1)}>Próxima</button></div></nav>}</div>;
}

