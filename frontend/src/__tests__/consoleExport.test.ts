import { describe, expect, it } from 'vitest';
import {
  CONSOLE_EXPORT_OPTIONS,
  consoleExportPath,
  consoleSummaryPath,
  fallbackFilename,
  filenameFromDisposition,
  summaryHeadline,
} from '../utils/consoleExport';
import type { ConsoleExportSummary } from '../utils/consoleExport';

describe('console export paths', () => {
  it('reads a database rig from the rig export routes', () => {
    expect(consoleExportPath({ rigId: 12 }, 'ma2-xml')).toBe('/rigs/12/export/ma2-xml');
    expect(consoleExportPath({ rigId: 12 }, 'ma2-macro')).toBe('/rigs/12/export/ma2-macro');
    expect(consoleExportPath({ rigId: 12 }, 'mvr')).toBe('/rigs/12/export/mvr');
    expect(consoleSummaryPath({ rigId: 12 })).toBe('/rigs/12/export/console-summary');
  });

  it('reads a demo preset from the preset export routes', () => {
    expect(consoleExportPath({ preset: 'liv_miami_approx' }, 'mvr')).toBe(
      '/venues/presets/liv_miami_approx/export/mvr',
    );
    expect(consoleSummaryPath({ preset: 'club night/2' })).toBe(
      '/venues/presets/club%20night%2F2/export/console-summary',
    );
  });

  it('offers the three downloads the server has', () => {
    expect(CONSOLE_EXPORT_OPTIONS.map((o) => o.kind)).toEqual(['ma2-xml', 'ma2-macro', 'mvr']);
  });
});

describe('console export file names', () => {
  it('takes the name the server gives', () => {
    expect(
      filenameFromDisposition('attachment; filename="LIV_Miami_approximate_recreation.mvr"', 'x.mvr'),
    ).toBe('LIV_Miami_approximate_recreation.mvr');
    expect(filenameFromDisposition('attachment; filename=rig_3_ma2.xml', 'x.xml')).toBe('rig_3_ma2.xml');
  });

  it('falls back when there is no usable name', () => {
    expect(filenameFromDisposition(undefined, 'rig_3.mvr')).toBe('rig_3.mvr');
    expect(filenameFromDisposition('attachment', 'rig_3.mvr')).toBe('rig_3.mvr');
    expect(filenameFromDisposition('attachment; filename="../../evil.mvr"', 'rig_3.mvr')).toBe('rig_3.mvr');
  });

  it('names a fallback after the rig or the preset', () => {
    expect(fallbackFilename({ rigId: 3 }, 'mvr')).toBe('rig_3.mvr');
    expect(fallbackFilename({ rigId: 3 }, 'ma2-xml')).toBe('rig_3_ma2.xml');
    expect(fallbackFilename({ preset: 'club_night' }, 'ma2-macro')).toBe('club_night_ma2_script.txt');
  });
});

describe('console export summary', () => {
  const summary: ConsoleExportSummary = {
    name: 'LIV',
    fixtures: 131,
    universes: [0, 1, 2, 3],
    groups: [
      { name: 'Dance Floor Spots', fixtures: 22 },
      { name: 'floor_spots', fixtures: 22 },
    ],
    unplaced: 0,
    position_unconfirmed: 0,
    gdtf_embedded: [],
    gdtf_not_embedded: [],
    disclaimer: '',
    notes: [],
    operator_guide: 'docs/CONSOLE_EXPORT.md',
  };

  it('says how much is in the files', () => {
    expect(summaryHeadline(summary)).toBe('131 fixtures on 4 universes, 2 groups.');
  });

  it('counts one of each in the singular', () => {
    expect(
      summaryHeadline({ ...summary, fixtures: 1, universes: [0], groups: [summary.groups[0]] }),
    ).toBe('1 fixture on 1 universe, 1 group.');
  });
});
