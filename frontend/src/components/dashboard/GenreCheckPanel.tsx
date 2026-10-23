import { useCallback, useEffect, useState } from 'react';
import { Box, Button, Chip, Typography } from '@mui/material';
import { genreCheckApi, GenreCheckReport, GenreCheckStatus } from '../../services/api';

export const GENRE_CHECK_POLL_MS = 3000;

const STYLE_LABELS: Record<string, string> = {
  house: 'House',
  techno: 'Techno',
  dnb: 'DnB / Dubstep',
  trance: 'Trance',
  edm: 'EDM',
  hip_hop: 'Hip-hop / R&B',
  latin: 'Latin',
  afro: 'Afro / Reggae',
  open_format: 'Open format',
  rock: 'Rock',
  lounge: 'Lounge',
  other: 'Something else',
  not_music: 'Not music',
};

export const styleLabel = (style: string) => STYLE_LABELS[style] ?? style;

const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? 'n/a' : `${Math.round(value * 100)}%`;

// A real-night check of the genre model. Start it at the top of a gig, tap what
// is playing whenever the music changes, stop it at the end. The model only
// listens unless the box was set to let it steer, so a wrong guess costs
// nothing on the night.
export default function GenreCheckPanel() {
  const [status, setStatus] = useState<GenreCheckStatus | null>(null);
  const [report, setReport] = useState<GenreCheckReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(
    () =>
      genreCheckApi
        .status()
        .then((s) => {
          setStatus(s);
          setError(null);
        })
        .catch(() => setError('Genre check not reachable')),
    []
  );

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(refresh, GENRE_CHECK_POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const run = (action: () => Promise<GenreCheckStatus>, failure: string) => {
    setBusy(true);
    action()
      .then((s) => {
        setStatus(s);
        if (s.report) setReport(s.report);
        setError(null);
      })
      .catch((e) => setError(e?.response?.data?.detail ?? failure))
      .finally(() => setBusy(false));
  };

  const active = status?.active ?? false;
  const guess = status?.last_guess;
  const marked = status?.current_mark?.style;

  return (
    <Box component="div" sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        {active ? (
          <Button variant="outlined" color="warning" disabled={busy}
            onClick={() => run(genreCheckApi.stop, 'Could not stop the check')}>
            Stop and score
          </Button>
        ) : (
          <Button variant="contained" disabled={busy || status?.weights_present === false}
            onClick={() => run(genreCheckApi.start, 'Could not start the check')}>
            Start tonight's check
          </Button>
        )}
        {active && (
          <Chip size="small" color={status?.steering ? 'warning' : 'default'}
            label={status?.steering ? 'Model is steering the show' : 'Listening only'} />
        )}
      </Box>

      {status?.weights_present === false && (
        <Typography variant="body2" color="text.secondary">
          The genre model isn't on this box yet. Run scripts/download_genre_model.py first.
        </Typography>
      )}

      {active && (
        <>
          <Typography variant="body2" data-testid="genre-guess">
            Model hears: <strong>{guess ? styleLabel(guess.style) : 'nothing yet'}</strong>
            {guess && guess.style !== 'unknown' ? ` (${percent(guess.confidence)} sure)` : ''}
            {' · '}You marked: <strong>{marked ? styleLabel(marked) : 'nothing yet'}</strong>
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Tap what's playing whenever the music changes. {status?.guesses ?? 0} guesses, {status?.marks ?? 0} marks so far.
          </Typography>
          <Box component="div" sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {(status?.styles ?? []).map((style) => (
              <Button key={style} size="small" disabled={busy}
                variant={style === marked ? 'contained' : 'outlined'}
                aria-pressed={style === marked}
                onClick={() => run(() => genreCheckApi.mark(style), 'Could not save the mark')}>
                {styleLabel(style)}
              </Button>
            ))}
          </Box>
        </>
      )}

      {report && !active && (
        <Box component="div" data-testid="genre-report">
          <Typography variant="body2">
            Last night's score: model right {percent(report.accuracy)} of {report.judged} judged guesses;
            the show would have been in the right style {percent(report.show_accuracy)} of the time.
          </Typography>
        </Box>
      )}

      {error && (
        <Typography role="alert" variant="body2" color="error.main">
          {error}
        </Typography>
      )}
    </Box>
  );
}
