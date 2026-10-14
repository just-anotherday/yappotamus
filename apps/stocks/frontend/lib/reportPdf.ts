import type { jsPDF } from 'jspdf';

export interface ReportPdfSource {
  id: number;
  ticker?: string;
  report_data: unknown;
  created_at?: string | null;
  last_updated?: string | null;
  report_date?: string | null;
  model_used?: string | null;
  prompt_version?: string | null;
  articles_count?: number;
  overall_sentiment?: string;
  confidence_score?: number | null;
}

export interface ReportPdfBlock {
  text: string;
  heading: boolean;
  depth: number;
}

function label(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
}

/** Keep every stored report field, including nested research gaps and references. */
export function reportPdfBlocks(report: ReportPdfSource): ReportPdfBlock[] {
  const blocks: ReportPdfBlock[] = [];
  const add = (text: string, heading = false, depth = 0) => blocks.push({ text, heading, depth });
  add(`${report.ticker || 'Market'} Analysis Report`, true);
  add(`Record ID: ${report.id}`);
  const date = report.created_at || report.last_updated || report.report_date;
  if (date) add(`Report date (as recorded): ${date}`);
  if (report.model_used) add(`Model: ${report.model_used}`);
  if (report.prompt_version) add(`Prompt version: ${report.prompt_version}`);
  if (report.articles_count != null) add(`Articles supplied: ${report.articles_count}`);
  if (report.overall_sentiment) add(`Overall sentiment: ${report.overall_sentiment}`);
  // Preserve the stored score; historical market reports may use a different scale.
  if (report.confidence_score != null) add(`Confidence score (as recorded): ${report.confidence_score}`);

  function visit(value: unknown, key: string, depth: number): void {
    if (value === null || value === undefined) {
      add(`${key}: Not recorded`, false, depth);
    } else if (Array.isArray(value)) {
      add(key, true, depth);
      if (!value.length) add('None recorded', false, depth + 1);
      value.forEach((item, index) => visit(item, `${index + 1}`, depth + 1));
    } else if (typeof value === 'object') {
      if (key) add(key, true, depth);
      Object.entries(value).forEach(([name, item]) => visit(item, label(name), depth + 1));
    } else {
      add(`${key}: ${String(value)}`, false, depth);
    }
  }
  visit(report.report_data, 'Report', 0);
  add('AI-generated analysis. Always conduct your own research before making investment decisions.');
  return blocks;
}

let fonts: Promise<string[]> | undefined;
function loadFonts(): Promise<string[]> {
  if (!fonts) {
    fonts = Promise.all(['Regular', 'Bold'].map(async style => {
      const response = await fetch(`/fonts/NotoSans-${style}.ttf`);
      if (!response.ok) throw new Error('Could not load PDF fonts');
      const bytes = new Uint8Array(await response.arrayBuffer());
      let binary = '';
      for (let offset = 0; offset < bytes.length; offset += 8192) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
      }
      return btoa(binary);
    })).catch(error => {
      fonts = undefined;
      throw error;
    });
  }
  return fonts;
}

export function reportPdfFilename(report: ReportPdfSource): string {
  const ticker = (report.ticker || 'market').replace(/[^a-zA-Z0-9_-]/g, '_');
  return `yapvibes-${ticker}-report-${report.id}.pdf`;
}

export async function buildReportPdf(report: ReportPdfSource): Promise<jsPDF> {
  const [{ jsPDF }, fontData] = await Promise.all([import('jspdf'), loadFonts()]);
  const pdf = new jsPDF({ unit: 'pt', format: 'a4', compress: true });
  ['Regular', 'Bold'].forEach((style, index) => {
    pdf.addFileToVFS(`NotoSans-${style}.ttf`, fontData[index]);
    pdf.addFont(`NotoSans-${style}.ttf`, 'NotoSans', style === 'Bold' ? 'bold' : 'normal');
  });
  const width = pdf.internal.pageSize.getWidth();
  const height = pdf.internal.pageSize.getHeight();
  const margin = 44;
  let y = 56;
  pdf.setProperties({ title: `${report.ticker || 'Market'} report ${report.id}`, author: 'YapVibes' });
  for (const block of reportPdfBlocks(report)) {
    const indent = Math.min(block.depth, 4) * 10;
    pdf.setFont('NotoSans', block.heading ? 'bold' : 'normal');
    pdf.setFontSize(block.heading ? 12 : 10);
    pdf.setTextColor(block.heading ? '#172554' : '#243247');
    const lines: string[] = pdf.splitTextToSize(block.text, width - margin * 2 - indent);
    if (block.heading) {
      // Reserve room for the heading and at least the first body line.
      if (y + lines.length * 16 + 20 > height - 54) { pdf.addPage(); y = 56; }
      y += 8;
    }
    for (const line of lines) {
      if (y > height - 54) { pdf.addPage(); y = 56; }
      pdf.text(line, margin + indent, y);
      y += 16;
    }
    y += 5;
  }
  const pages = pdf.getNumberOfPages();
  for (let page = 1; page <= pages; page++) {
    pdf.setPage(page);
    pdf.setFont('NotoSans', 'normal');
    pdf.setFontSize(8);
    pdf.setTextColor('#64748b');
    pdf.text('YapVibes | Stock Analysis', margin, 28);
    pdf.text(`Report ${report.id} | Page ${page} of ${pages}`, width - margin, height - 25, { align: 'right' });
  }
  return pdf;
}
