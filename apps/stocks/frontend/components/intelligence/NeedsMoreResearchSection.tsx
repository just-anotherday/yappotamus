import { formatResearchSourceSection, hasNeedsMoreResearch } from '@/lib/reportPresentation';
import type { NeedsMoreResearchItem } from '@/types/stock';

interface NeedsMoreResearchSectionProps {
  items?: NeedsMoreResearchItem[];
  compact?: boolean;
}

export default function NeedsMoreResearchSection({
  items,
  compact = false,
}: NeedsMoreResearchSectionProps) {
  if (!hasNeedsMoreResearch(items)) return null;
  const researchItems = items ?? [];

  return (
    <section
      aria-label="Needs More Research"
      data-report-section="needs-more-research"
      style={{ marginBottom: compact ? 0 : 32 }}
    >
      <div
        style={{
          padding: compact ? 16 : 24,
          background: 'var(--card-bg)',
          border: '1px solid #94a3b8',
          borderRadius: 12,
        }}
      >
        <h2
          style={{
            margin: 0,
            color: 'var(--text-primary)',
            fontSize: compact ? 15 : 18,
            fontWeight: 700,
          }}
        >
          Needs More Research
        </h2>
        <p style={{ margin: '6px 0 16px', color: 'var(--text-muted)', fontSize: compact ? 12 : 13, lineHeight: 1.5 }}>
          These questions were separated from the validated analysis because additional evidence is needed.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {researchItems.map(item => (
            <article
              key={item.id}
              data-research-question
              style={{
                padding: compact ? 12 : 16,
                background: 'var(--section-bg)',
                border: '1px solid var(--card-border)',
                borderLeft: '4px solid #64748b',
                borderRadius: 8,
                overflowWrap: 'anywhere',
              }}
            >
              <div style={{ marginBottom: 8 }}>
                <span
                  style={{
                    display: 'inline-block',
                    padding: '2px 8px',
                    background: 'var(--card-bg)',
                    border: '1px solid var(--card-border)',
                    borderRadius: 999,
                    color: 'var(--text-muted)',
                    fontSize: 11,
                    fontWeight: 600,
                  }}
                >
                  {formatResearchSourceSection(item.source_section)}
                </span>
              </div>
              <p style={{ margin: 0, color: 'var(--text-primary)', fontSize: compact ? 13 : 15, fontWeight: 650, lineHeight: 1.55 }}>
                {item.research_question}
              </p>
              <p style={{ margin: '8px 0 0', color: 'var(--text-secondary)', fontSize: compact ? 12 : 13, lineHeight: 1.55 }}>
                <strong>Evidence needed:</strong> {item.missing_evidence}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
