'use client';
import {useCallback,useEffect,useState,useRef} from 'react';
import Link from 'next/link';
import {researchRequest} from '@/lib/researchApi';
import {formatReportDateTime} from '@/lib/reportPresentation';
interface Outcome {ticker:string;status:string;report_id?:number;error?:string;failure_kind?:string}
interface Run {id:number;kind:string;parent_id:number|null;status:string;stage:string;current_ticker:string|null;tickers:string[];outcomes:Outcome[];news_counts:{articles_inserted?:number};started_at:string;updated_at:string;finished_at:string|null}
export default function ReportRunStatus({onFinished}:{onFinished:()=>void}) {
  const [data,setData]=useState<{run:Run|null;last_successful_at:string|null}|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const previousRun = useRef<{id:number;status:string}|null>(null);
  const load=useCallback(async()=>{try{setData(await researchRequest('/runs/latest'));setError('');}catch(e){setError(e instanceof Error?e.message:'Unable to load run status');}},[]);
  useEffect(()=>{const first=setTimeout(()=>void load(),0);const timer=setInterval(()=>void load(),15000);return()=>{clearTimeout(first);clearInterval(timer);};},[load]);
  const run=data?.run;
  useEffect(()=>{
    const previous=previousRun.current;
    if(run && previous?.id===run.id && ['queued','running'].includes(previous.status) && !['queued','running'].includes(run.status)) onFinished();
    previousRun.current=run?{id:run.id,status:run.status}:null;
  },[run,onFinished]);
  const active=run?.status==='queued'||run?.status==='running';
  const failed=run?.outcomes.filter(item=>item.status!=='completed')??[];
  const complete=run?.outcomes.filter(item=>item.status==='completed').length??0;
  async function retry(){if(!run||busy)return;setBusy(true);setError('');try{const result=await researchRequest<{tickers:string[]}>(`/runs/${run.id}/retry`,{method:'POST'});setMessage(`Retry queued for ${result.tickers.join(', ')}. It will continue in the background.`);await load();onFinished();}catch(e){setError(e instanceof Error?e.message:'Unable to retry');}finally{setBusy(false);}}
  return <section aria-label="Latest automation run" className="mb-6 rounded-xl border border-divider bg-card p-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">Latest automation run</h2><button onClick={()=>{void load();onFinished();}} className="text-sm underline">Refresh run status</button></div>
    {error&&<p role="alert" className="mt-2 text-sm text-negative">{error}</p>}
    {!data&&!error&&<p role="status" className="mt-2 text-sm">Loading run status…</p>}
    {data&&!run&&<p className="mt-2 text-sm text-muted">No tracked run yet. The next daily run will record its progress here.</p>}
    {run&&<>
      <p role="status" className="mt-2 text-sm">{run.kind==='retry'?'Retry':'Daily run'} · {run.status} · {complete}/{run.tickers.length} reports saved · {failed.length} failed{run.current_ticker?` · Working on ${run.current_ticker}`:` · ${run.stage}`}</p>
      <p className="mt-2 text-xs text-muted">Started {formatReportDateTime(run.started_at)} · Last progress {formatReportDateTime(run.updated_at)}{run.news_counts.articles_inserted!=null?` · ${run.news_counts.articles_inserted} new articles`:''}</p>
      {failed.length>0&&<ul className="mt-3 space-y-1 text-sm">{failed.map(item=><li key={item.ticker}><strong>{item.ticker}</strong>: {item.error||item.failure_kind||'Report failed'}</li>)}</ul>}
      {!active&&(failed.length>0||run.status==='interrupted')&&<button disabled={busy} onClick={()=>void retry()} className="mt-3 rounded-lg bg-action px-4 py-2 text-sm text-white disabled:opacity-50">{busy?'Queuing retry…':'Retry failed reports'}</button>}
      {complete>0&&<details className="mt-3 text-sm"><summary className="cursor-pointer">Saved report results</summary><ul className="mt-2">{run.outcomes.filter(item=>item.report_id).map(item=><li key={item.ticker}><Link className="underline" href={`/analysis/reports/${item.report_id}`}>{item.ticker} report</Link></li>)}</ul></details>}
    </>}
    {data&&<p className="mt-3 text-xs text-muted">Last fully successful tracked run: {data.last_successful_at?formatReportDateTime(data.last_successful_at):'None recorded yet'}</p>}
    {message&&<p role="status" className="mt-2 text-sm">{message}</p>}
  </section>;
}
