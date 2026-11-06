'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { researchRequest } from '@/lib/researchApi';
import { formatReportDateTime } from '@/lib/reportPresentation';

interface ReportPoint {overall_sentiment:string;confidence_score:number;created_at:string;id?:number}
export default function ReportChanges({reportId}:{reportId:number}) {
  const [data,setData]=useState<{previous:ReportPoint|null;current:ReportPoint}|null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{let active=true;researchRequest<{previous:ReportPoint|null;current:ReportPoint}>(`/reports/${reportId}/changes`).then(r=>{if(active)setData(r);}).catch(()=>{if(active)setError('Previous report comparison is unavailable.');});return()=>{active=false;};},[reportId]);
  if(error)return <p role="status" className="my-3 text-sm text-muted">{error}</p>;
  if(!data)return <p className="my-3 text-sm text-muted">Loading previous report comparison…</p>;
  const prior=data.previous;
  const delta=prior?data.current.confidence_score-prior.confidence_score:0;
  return <section className="my-4 rounded-xl border border-divider bg-card p-4" aria-label="Changes since previous report">
    <h2 className="text-sm font-semibold">Changed since previous report</h2>
    {!prior?<p className="mt-2 text-sm text-muted">This is the first saved report for this ticker.</p>:<>
      <p className="mt-2 text-sm">Sentiment: {prior.overall_sentiment} → {data.current.overall_sentiment} · Confidence: {delta>0?'+':''}{delta} points ({prior.confidence_score} → {data.current.confidence_score})</p>
      <p className="mt-1 text-xs text-muted">Previous: {formatReportDateTime(prior.created_at)} · This report: {formatReportDateTime(data.current.created_at)}</p>
      <Link href={`/analysis/reports/${prior.id}`} className="mt-2 inline-block text-sm underline">Open previous report</Link>
      <p className="mt-1 text-xs text-muted">Confidence is the model’s assessment, not a measured probability of investment success.</p>
    </>}
  </section>;
}
