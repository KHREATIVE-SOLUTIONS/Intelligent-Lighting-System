import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import StatusBar from '../components/common/StatusBar';
import { useHealthStore } from '../stores/healthStore';

describe('StatusBar', () => {
  beforeEach(() => {
    useHealthStore.setState({
      reachable: true,
      dmx: null,
      capture: null,
      effects: null,
      box: null,
      link: 'connected',
      lastAnalysisAt: Date.now(),
    });
  });
  afterEach(cleanup);

  it('shows all three readings in words, not just colour', () => {
    useHealthStore.setState({
      dmx: { status: 'connected', connected: true, transmitting: true, fps: 40 },
      capture: { available: true, running: true, last_rms: 0.25 },
    });
    render(<StatusBar />);

    expect(screen.getByTestId('status-dmx').textContent).toContain('DMX 40 fps');
    expect(screen.getByTestId('status-audio').textContent).toContain('Audio live');
    expect(screen.getByTestId('status-link').textContent).toContain('Linked');
  });

  it('marks a dead audio feed as down', () => {
    useHealthStore.setState({
      dmx: { status: 'connected', connected: true, transmitting: true, fps: 40 },
      capture: { available: true, running: false },
    });
    render(<StatusBar />);

    const audio = screen.getByTestId('status-audio');
    expect(audio.getAttribute('data-level')).toBe('down');
    expect(audio.textContent).toContain('Audio off');
  });

  it('says the box is offline when nothing answers', () => {
    useHealthStore.setState({ reachable: false });
    render(<StatusBar />);

    expect(screen.getByTestId('status-link').textContent).toContain('Box offline');
    expect(screen.getByTestId('status-dmx').getAttribute('data-level')).toBe('unknown');
  });
});

describe('StatusBar with the box health report', () => {
  afterEach(cleanup);

  it('shows waiting for a rig and a missing database', () => {
    useHealthStore.setState({
      reachable: true,
      dmx: { status: 'connected', connected: true, transmitting: false },
      capture: { available: true, running: true, last_rms: 0.25 },
      box: {
        status: 'degraded',
        services: { database: 'unavailable', audio_input: 'live' },
        dmx_detail: { output_held_until_rig_patched: true },
      },
      link: 'connected',
      lastAnalysisAt: Date.now(),
    });
    render(<StatusBar />);

    const dmx = screen.getByTestId('status-dmx');
    expect(dmx.textContent).toContain('Waiting for rig');
    expect(dmx.getAttribute('aria-label')).toContain('Waiting for a rig to be patched');
    expect(screen.getByTestId('status-database').getAttribute('data-level')).toBe('down');
  });

  it('shows no database pill while the database is fine', () => {
    useHealthStore.setState({ box: { services: { database: 'connected' } } });
    render(<StatusBar />);
    expect(screen.queryByTestId('status-database')).toBeNull();
  });
});
