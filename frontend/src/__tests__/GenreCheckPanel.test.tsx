import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import GenreCheckPanel from '../components/dashboard/GenreCheckPanel';
import { genreCheckApi, GenreCheckStatus } from '../services/api';

vi.mock('../services/api', () => ({
  genreCheckApi: {
    status: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    mark: vi.fn(),
  },
}));

const api = vi.mocked(genreCheckApi);
const flush = () => act(async () => {});

const idle: GenreCheckStatus = {
  active: false,
  night: null,
  steering: false,
  guesses: 0,
  marks: 0,
  last_guess: null,
  current_mark: null,
  styles: ['house', 'techno', 'other'],
  model_running: false,
  weights_present: true,
};

const running: GenreCheckStatus = {
  ...idle,
  active: true,
  night: '2026-10-24_220000',
  guesses: 4,
  last_guess: { t: 1, style: 'house', confidence: 0.7 },
};

describe('GenreCheckPanel', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it('starts a check that only listens', async () => {
    api.status.mockResolvedValue(idle);
    api.start.mockResolvedValue(running);
    render(<GenreCheckPanel />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: /start tonight/i }));
    await flush();

    expect(api.start).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/listening only/i)).toBeTruthy();
    expect(screen.getByTestId('genre-guess').textContent).toMatch(/House/);
  });

  it('marks what is playing with one tap', async () => {
    api.status.mockResolvedValue(running);
    api.mark.mockResolvedValue({ ...running, marks: 1, current_mark: { t: 2, style: 'techno' } });
    render(<GenreCheckPanel />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Techno' }));
    await flush();

    expect(api.mark).toHaveBeenCalledWith('techno');
    expect(screen.getByRole('button', { name: 'Techno' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('says the model is missing instead of offering to start', async () => {
    api.status.mockResolvedValue({ ...idle, weights_present: false });
    render(<GenreCheckPanel />);
    await flush();

    expect((screen.getByRole('button', { name: /start tonight/i }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/download_genre_model/)).toBeTruthy();
  });

  it('shows the score when the check is stopped', async () => {
    api.status.mockResolvedValue(running);
    api.stop.mockResolvedValue({
      ...idle,
      report: {
        guesses: 10, judged: 8, accuracy: 0.75, confident_accuracy: 0.8, show_accuracy: 0.9,
        by_style: {}, mistakes: {},
      },
    });
    render(<GenreCheckPanel />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: /stop and score/i }));
    await flush();

    expect(screen.getByTestId('genre-report').textContent).toMatch(/75%.*90%/s);
  });
});
