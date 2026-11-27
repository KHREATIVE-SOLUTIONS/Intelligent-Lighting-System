// Readiness's "Locate these" (docs/READINESS.md): the walkthrough opens on its intro with the named lights,
// lights nothing until Start is pressed, and then starts locate mode with exactly those fixture ids.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import IdentifyWalkthrough from '../components/rig/IdentifyWalkthrough';
import { identifyApi } from '../services/api';

vi.mock('../services/api', () => ({
  rigsApi: { get: vi.fn().mockResolvedValue({}) },
  identifyApi: {
    start: vi.fn(), end: vi.fn().mockResolvedValue(undefined), endOnUnload: vi.fn(), heartbeat: vi.fn(),
  },
}));

const api = vi.mocked(identifyApi);
const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

beforeEach(() => {
  api.start.mockReset();
  api.start.mockRejectedValue(new Error('stop here'));
});
afterEach(cleanup);

describe('IdentifyWalkthrough with named fixtures', () => {
  it('lights nothing on open, then starts locate mode with exactly the named ids', async () => {
    render(
      <IdentifyWalkthrough rigId={7} open onClose={() => {}} stageWidth={10} stageDepth={8}
        unconfirmedCount={5} fixtureIds={[21, 22]} />,
    );
    await flush();

    expect(api.start).not.toHaveBeenCalled();
    expect(screen.getByTestId('identify-named').textContent).toContain('named 2 lights');

    fireEvent.click(screen.getByRole('button', { name: 'Check these 2' }));
    await flush();

    expect(api.start).toHaveBeenCalledWith(7, 'unconfirmed', [21, 22]);
  });

  it('without named fixtures it still offers the guessed ones, as before', async () => {
    render(
      <IdentifyWalkthrough rigId={7} open onClose={() => {}} stageWidth={10} stageDepth={8} unconfirmedCount={5} />,
    );
    await flush();

    expect(screen.queryByTestId('identify-named')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Check the 5 guessed' }));
    await flush();

    expect(api.start).toHaveBeenCalledWith(7, 'unconfirmed');
  });
});
