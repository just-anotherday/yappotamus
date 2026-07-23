'use client';

// Status palette (fixed - never themed, never carries meaning by hue alone):
const STATUS = {
  good: '#0ca30c',
  warning: '#fab219',
  critical: '#d03b3b',
};

interface ArticleSelectionMeterProps {
  selected: number;
  max: number;
  available: number;
  onMaxChange: (next: number) => void;
  minMax?: number;
  maxMax?: number;
  step?: number;
}

export default function ArticleSelectionMeter({
  selected,
  max,
  available,
  onMaxChange,
  minMax = 5,
  maxMax = 40,
  step = 5,
}: ArticleSelectionMeterProps) {
  const ratio = max > 0 ? Math.min(selected / max, 1) : 0;
  const fillColor = ratio >= 0.9 ? STATUS.critical : ratio >= 0.6 ? STATUS.warning : STATUS.good;
  const statusLabel = ratio >= 0.9 ? 'At limit' : ratio >= 0.6 ? 'Getting close' : 'Plenty of room';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem' }}>
        <span
          style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#374151' }}
          className="dark:text-gray-300"
        >
          {selected} of {max} articles selected
          <span style={{ fontWeight: 400, color: '#9ca3af' }} className="dark:text-slate-500">
            {' '}({available} available)
          </span>
        </span>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
          <span style={{ fontSize: '0.6875rem', color: '#9ca3af' }} className="dark:text-slate-500">
            Max:
          </span>
          <button
            type="button"
            onClick={() => onMaxChange(Math.max(minMax, max - step))}
            disabled={max <= minMax}
            aria-label="Decrease max selectable articles"
            style={{
              width: 22, height: 22, borderRadius: 6, border: '1px solid #d1d5db',
              background: 'white', color: '#374151', fontSize: '0.875rem', lineHeight: 1,
              cursor: max <= minMax ? 'not-allowed' : 'pointer', opacity: max <= minMax ? 0.4 : 1,
            }}
            className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
          >
            −
          </button>
          <span style={{ fontSize: '0.8125rem', fontWeight: 600, minWidth: 24, textAlign: 'center', color: '#374151' }}
            className="dark:text-gray-200">
            {max}
          </span>
          <button
            type="button"
            onClick={() => onMaxChange(Math.min(maxMax, max + step))}
            disabled={max >= maxMax}
            aria-label="Increase max selectable articles"
            style={{
              width: 22, height: 22, borderRadius: 6, border: '1px solid #d1d5db',
              background: 'white', color: '#374151', fontSize: '0.875rem', lineHeight: 1,
              cursor: max >= maxMax ? 'not-allowed' : 'pointer', opacity: max >= maxMax ? 0.4 : 1,
            }}
            className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
          >
            +
          </button>
        </div>
      </div>

      {/* Track */}
      <div
        role="progressbar"
        aria-valuenow={selected}
        aria-valuemin={0}
        aria-valuemax={max}
        style={{ height: 6, borderRadius: 3, background: '#e5e7eb', overflow: 'hidden' }}
        className="dark:bg-slate-700"
      >
        <div
          style={{
            width: `${ratio * 100}%`,
            height: '100%',
            borderRadius: 3,
            background: fillColor,
            transition: 'width 0.15s ease, background-color 0.15s ease',
          }}
        />
      </div>

      <span style={{ fontSize: '0.6875rem', color: '#9ca3af' }} className="dark:text-slate-500">
        {statusLabel}
      </span>
    </div>
  );
}
