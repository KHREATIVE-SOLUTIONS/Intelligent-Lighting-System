import { describe, expect, it } from 'vitest';
import { foldKindFor } from '../components/common/Layout';

describe('foldKindFor', () => {
  it('starts the controls folded on both visualizer routes only', () => {
    expect(foldKindFor('/visualizer')).toBe('visualizer');
    expect(foldKindFor('/rigs/4/visualizer')).toBe('visualizer');
    expect(foldKindFor('/')).toBe('default');
    expect(foldKindFor('/rigs/4/builder')).toBe('default');
  });
});
