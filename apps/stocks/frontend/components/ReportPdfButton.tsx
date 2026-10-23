'use client';

import { useState } from 'react';
import type { ReportPdfSource } from '@/lib/reportPdf';

export default function ReportPdfButton({ report }: { report: ReportPdfSource }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function download() {
    setBusy(true);
    setError(null);
    try {
      const { buildReportPdf, reportPdfFilename } = await import('@/lib/reportPdf');
      const pdf = await buildReportPdf(report);
      await pdf.save(reportPdfFilename(report), { returnPromise: true });
    } catch {
      setError('PDF download failed. Please try again.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button type="button" onClick={download} disabled={busy} aria-busy={busy}
        style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #2563eb',
          background: '#2563eb', color: '#fff', fontWeight: 600,
          cursor: busy ? 'wait' : 'pointer', whiteSpace: 'nowrap' }}>
        {busy ? 'Preparing PDF…' : 'Download PDF'}
      </button>
      {error && <p role="alert" style={{ fontSize: 12, color: 'var(--negative)', margin: '6px 0' }}>{error}</p>}
    </div>
  );
}
