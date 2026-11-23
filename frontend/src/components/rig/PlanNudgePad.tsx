import type { CSSProperties, ReactNode } from 'react';
import { NUDGE_PAD_BUTTON_PX, PAD_LABELS } from './planTouch2d';
import type { PadDirection } from './planTouch2d';

/**
 * The keys of the 2D plan as buttons, for a phone or a tablet at the venue:
 * four arrows that nudge the selection, a 1x / 10x switch that stands for
 * Shift, and Select row and Lay on truss. It only asks: what a tap does is
 * the plan's to say, so a tap and the matching key are the same code
 * (`StageView2D.tsx`, docs/ROOM_SCAN.md).
 *
 * Plain buttons with their sizes written on them, and letters for arrows: a
 * button is a fingertip (44 px) whatever the theme does, and the plan is
 * still the only drawing in its box.
 */
interface PlanNudgePadProps {
  /** Whether a tap goes ten grid steps and not one. */
  tenfold: boolean;
  onTenfoldChange: (tenfold: boolean) => void;
  onNudge: (direction: PadDirection) => void;
  /** Selects the row of the selection, as R does. The button is left out when this is. */
  onSelectRow?: () => void;
  /** Lays the selection along the nearest scanned truss. The button is left out when this is. */
  onLayRow?: () => void;
  /** Lay on truss needs two or more fixtures selected. */
  layRowDisabled?: boolean;
}

const ARROWS: Array<{ direction: PadDirection; glyph: string; column: number; row: number }> = [
  { direction: 'up', glyph: '↑', column: 2, row: 1 },
  { direction: 'left', glyph: '←', column: 1, row: 2 },
  { direction: 'right', glyph: '→', column: 3, row: 2 },
  { direction: 'down', glyph: '↓', column: 2, row: 3 },
];

const BUTTON: CSSProperties = {
  minWidth: NUDGE_PAD_BUTTON_PX,
  minHeight: NUDGE_PAD_BUTTON_PX,
  padding: 0,
  border: '1px solid rgba(144, 164, 174, 0.5)',
  borderRadius: 6,
  background: 'rgba(22, 33, 62, 0.92)',
  color: '#e0e0e0',
  fontSize: 18,
  lineHeight: 1,
  cursor: 'pointer',
  // Taps in quick succession are taps, not a double-tap to zoom.
  touchAction: 'manipulation',
};

const WORD_BUTTON: CSSProperties = { ...BUTTON, fontSize: 12, padding: '0 8px' };

export default function PlanNudgePad({
  tenfold, onTenfoldChange, onNudge, onSelectRow, onLayRow, layRowDisabled = false,
}: PlanNudgePadProps) {
  const cell = (column: number, row: number, child: ReactNode) => (
    <div key={`${column}-${row}`} style={{ gridColumn: column, gridRow: row }}>{child}</div>
  );

  return (
    <div
      data-testid="nudge-pad"
      role="group"
      aria-label="Move the selected fixtures"
      style={{
        position: 'absolute',
        right: 8,
        bottom: 8,
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        padding: 6,
        borderRadius: 8,
        background: 'rgba(26, 26, 46, 0.6)',
        userSelect: 'none',
      }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(3, ${NUDGE_PAD_BUTTON_PX}px)`, gap: 4 }}>
        {ARROWS.map(({ direction, glyph, column, row }) => cell(column, row, (
          <button
            type="button"
            aria-label={PAD_LABELS[direction]}
            style={BUTTON}
            onClick={() => onNudge(direction)}
          >
            <span aria-hidden="true">{glyph}</span>
          </button>
        )))}
        {cell(2, 2, (
          <button
            type="button"
            aria-label="Ten grid steps for each tap"
            aria-pressed={tenfold}
            title={tenfold ? 'Each tap is ten grid steps' : 'Each tap is one grid step'}
            style={{
              ...WORD_BUTTON,
              padding: 0,
              fontWeight: 600,
              ...(tenfold ? { background: '#4fc3f7', color: '#10182c' } : null),
            }}
            onClick={() => onTenfoldChange(!tenfold)}
          >
            {tenfold ? '10x' : '1x'}
          </button>
        ))}
      </div>
      {(onSelectRow || onLayRow) && (
        <div style={{ display: 'flex', gap: 4 }}>
          {onSelectRow && (
            <button
              type="button"
              aria-label="Select the whole row"
              style={{ ...WORD_BUTTON, flex: 1 }}
              onClick={onSelectRow}
            >
              Row
            </button>
          )}
          {onLayRow && (
            <button
              type="button"
              aria-label="Lay the selection on the nearest truss"
              style={{ ...WORD_BUTTON, flex: 1, ...(layRowDisabled ? { opacity: 0.45, cursor: 'default' } : null) }}
              disabled={layRowDisabled}
              onClick={onLayRow}
            >
              On truss
            </button>
          )}
        </div>
      )}
    </div>
  );
}
