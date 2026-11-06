'use client';
import { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { researchRequest } from '@/lib/researchApi';
interface Reading { article_id: number; saved: boolean; read: boolean }
const ReadingContext = createContext<{states: Record<number, Reading>; loaded: boolean; error: string; update: (id:number, change:Partial<Reading>)=>Promise<void>} | null>(null);

export function ArticleReadingProvider({children}:{children:React.ReactNode}) {
  const [states,setStates]=useState<Record<number,Reading>>({});
  const [loaded,setLoaded]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=> { let active=true; researchRequest<Reading[]>('/article-state').then(rows=> { if(active) {setStates(Object.fromEntries(rows.map(r=>[r.article_id,r])));setLoaded(true);} }).catch(e=>{if(active)setError(e.message);}); return()=>{active=false;}; },[]);
  const update=useCallback(async(id:number,change:Partial<Reading>)=> {
    const row=await researchRequest<Reading>(`/article-state/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(change)});
    setStates(previous=>({...previous,[id]:row}));
    window.dispatchEvent(new Event('research-reading-updated'));
  },[]);
  return <ReadingContext.Provider value={{states,loaded,error,update}}>{children}</ReadingContext.Provider>;
}

export function ArticleReadingControls({articleId}:{articleId:number}) {
  const context=useContext(ReadingContext);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const pending=useRef(false);
  if(!context) return null;
  const state=context.states[articleId];
  async function change(update:Partial<Reading>) {
    if(pending.current || !context) return;
    pending.current=true;setBusy(true);setError('');
    try {await context.update(articleId,update);} catch(e){setError(e instanceof Error?e.message:'Could not save article state');} finally{pending.current=false;setBusy(false);}
  }
  return <div className="mt-3 border-t border-divider pt-3 text-xs">
    <div className="flex flex-wrap gap-3">
      <button type="button" disabled={!context.loaded||busy} aria-pressed={!!state?.saved} onClick={()=>void change({saved:!state?.saved})} className="underline disabled:opacity-50">{state?.saved?'Saved article ✓':'Save for later'}</button>
      <button type="button" disabled={!context.loaded||busy} aria-pressed={!!state?.read} onClick={()=>void change({read:!state?.read})} className="underline disabled:opacity-50">{state?.read?'Read ✓ · Mark unread':'Mark read'}</button>
      {busy&&<span role="status">Saving…</span>}
    </div>
    {(error||context.error)&&<p role="alert" className="mt-1 text-negative">{error||context.error}</p>}
  </div>;
}
