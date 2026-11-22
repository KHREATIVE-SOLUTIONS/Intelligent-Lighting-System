// Console export: where each download lives and what to call the file.
// Pure, so it can be tested without a server. docs/CONSOLE_EXPORT.md describes
// the files themselves.

/** A rig in the database, or a demo venue preset by name. */
export type ConsoleExportTarget = { rigId: number } | { preset: string };

export type ConsoleExportKind = 'ma2-xml' | 'ma2-macro' | 'mvr';

export interface ConsoleExportOption {
  kind: ConsoleExportKind;
  title: string;
  detail: string;
  /** File ending, used when the server names no file. */
  ending: string;
}

export const CONSOLE_EXPORT_OPTIONS: ConsoleExportOption[] = [
  {
    kind: 'ma2-xml',
    title: 'grandMA2 fixture layers (XML)',
    detail: 'Patch, 3D positions and rotations. The fixture types must already be in the show.',
    ending: '_ma2.xml',
  },
  {
    kind: 'ma2-macro',
    title: 'grandMA2 command-line script',
    detail: 'Patch, labels and groups by fixture ID, as text to read and paste.',
    ending: '_ma2_script.txt',
  },
  {
    kind: 'mvr',
    title: 'MVR for MA3D / Capture',
    detail: 'Patch, 3D positions, rotations and groups, with the GDTF files this system holds.',
    ending: '.mvr',
  },
];

/** What the server says an export of a rig holds and leaves out. */
export interface ConsoleExportSummary {
  name: string;
  fixtures: number;
  universes: number[];
  groups: Array<{ name: string; fixtures: number }>;
  unplaced: number;
  position_unconfirmed: number;
  gdtf_embedded: string[];
  gdtf_not_embedded: string[];
  disclaimer: string;
  notes: string[];
  operator_guide: string;
}

function base(target: ConsoleExportTarget): string {
  return 'rigId' in target
    ? `/rigs/${target.rigId}/export`
    : `/venues/presets/${encodeURIComponent(target.preset)}/export`;
}

/** The path of a download, relative to the API root. */
export function consoleExportPath(target: ConsoleExportTarget, kind: ConsoleExportKind): string {
  return `${base(target)}/${kind}`;
}

export function consoleSummaryPath(target: ConsoleExportTarget): string {
  return `${base(target)}/console-summary`;
}

/** The file name out of a Content-Disposition header, or the fallback. */
export function filenameFromDisposition(header: unknown, fallback: string): string {
  if (typeof header !== 'string') return fallback;
  const found = /filename="?([^";]+)"?/i.exec(header);
  const name = found ? found[1].trim() : '';
  // A name is a name, never a path.
  return name && !/[\\/]/.test(name) ? name : fallback;
}

export function fallbackFilename(target: ConsoleExportTarget, kind: ConsoleExportKind): string {
  const stem = 'rigId' in target ? `rig_${target.rigId}` : target.preset;
  const option = CONSOLE_EXPORT_OPTIONS.find((o) => o.kind === kind);
  return `${stem}${option ? option.ending : ''}`;
}

/** One line saying what will be in the files. */
export function summaryHeadline(summary: ConsoleExportSummary): string {
  const universes = summary.universes.length;
  return (
    `${summary.fixtures} fixture${summary.fixtures === 1 ? '' : 's'} on ` +
    `${universes} universe${universes === 1 ? '' : 's'}, ` +
    `${summary.groups.length} group${summary.groups.length === 1 ? '' : 's'}.`
  );
}
