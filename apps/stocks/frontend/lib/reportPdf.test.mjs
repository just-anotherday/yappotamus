import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import test from 'node:test';
import { buildReportPdf, reportPdfBlocks, reportPdfFilename } from './reportPdf.ts';

const report = {
  id: 192, ticker: 'SPCX', model_used: 'gpt-6-luna', prompt_version: '3.0',
  created_at: '2026-10-14T15:03:45Z', articles_count: 50,
  report_data: {
    overall_sentiment: 'Bullish', confidence_score: 65,
    executive_summary: 'Revenue grew 12% — outlook remains uncertain. “Quoted source.”',
    needs_more_research: [{ question: 'Verify guidance', source_section: 'outlook' }],
    articles_used: [{ title: 'Quarterly results', url: 'https://example.com/results' }],
    missing: null, optional: [], observed_zero: 0,
  },
};

test('exports nested report content, sources, research gaps and zero values', () => {
  const text = reportPdfBlocks(report).map(block => block.text).join('\n');
  for (const expected of ['SPCX Analysis Report', 'gpt-6-luna', 'Verify guidance',
    'https://example.com/results', 'Observed Zero: 0', 'Missing: Not recorded',
    'None recorded', 'Revenue grew 12% —']) {
    assert.ok(text.includes(expected), expected);
  }
  assert.equal(reportPdfFilename({ ...report, ticker: '../SPCX' }), 'yapvibes-___SPCX-report-192.pdf');
  assert.equal(reportPdfFilename({ ...report, ticker: undefined }), 'yapvibes-market-report-192.pdf');
});

test('generates a real paginated PDF with embedded fonts and retries failed font loads', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false });
  try {
    await assert.rejects(buildReportPdf(report), /Could not load PDF fonts/);
    globalThis.fetch = async url => {
      const data = await readFile(new URL(`../public${url}`, import.meta.url));
      return { ok: true, arrayBuffer: async () => data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) };
    };
    const longReport = { ...report, report_data: { ...report.report_data,
      detailed_outlook: Array.from({ length: 55 }, (_, index) =>
        `Scenario ${index + 1}: ${'Evaluate earnings, valuation, liquidity and source limitations. '.repeat(3)}`),
      final_marker: 'Complete report content ends here.',
    } };
    const pdf = await buildReportPdf(longReport);
    assert.ok(pdf.getNumberOfPages() >= 4);
    const bytes = Buffer.from(pdf.output('arraybuffer'));
    assert.ok(bytes.subarray(0, 5).toString().startsWith('%PDF-'));
    assert.ok(bytes.toString('latin1').includes('/FontFile2'));
    if (process.env.PDF_PREVIEW_PATH) await writeFile(process.env.PDF_PREVIEW_PATH, bytes);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
