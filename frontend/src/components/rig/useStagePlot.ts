/**
 * The stage plot underlay's state for one rig (docs/STAGE_PLOT.md): what the
 * server keeps, the image as an object URL, whether it is shown, and a
 * calibration being made. Gives StageView2D its `underlay`, `onPlanPick` and
 * `pickMarks`, and StagePlotControl its buttons.
 *
 * A failed read of what is stored is taken as "no stage plot": the plan is
 * drawn as it always was.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { refusalText, stagePlotApi } from '../../services/stagePlotApi';
import {
  DEFAULT_OPACITY, calibrationProblem, calibrationTransform, fitTransform, toImage, toPlan,
} from '../../utils/stagePlot';
import type { ImagePoint, Matrix, StagePlotCalibration, StagePlotInfo } from '../../utils/stagePlot';
import { announceStagePlotChange, onStagePlotChange } from '../../utils/stagePlotSync';
import type { PlanPickMark, PlanUnderlay } from './StageView2D';

export type PickStep = 'a' | 'b' | 'origin' | 'done';

export interface CalibrationDraft {
  a: ImagePoint | null;
  b: ImagePoint | null;
  origin: ImagePoint | null;
  /** As typed, in metres. */
  distance: string;
  rotation: number;
}

const EMPTY_DRAFT: CalibrationDraft = { a: null, b: null, origin: null, distance: '', rotation: 0 };

/** Which point the next click on the plan picks. */
export function pickStep(draft: CalibrationDraft): PickStep {
  if (!draft.a) return 'a';
  if (!draft.b) return 'b';
  if (!draft.origin) return 'origin';
  return 'done';
}

/** The draft as a calibration the server takes, or null while a point is missing. */
export function draftCalibration(draft: CalibrationDraft, opacity: number): StagePlotCalibration | null {
  if (!draft.a || !draft.b || !draft.origin) return null;
  return {
    point_a: draft.a, point_b: draft.b, origin: draft.origin,
    distance_m: Number(draft.distance.replace(',', '.')),
    rotation_deg: draft.rotation,
    opacity,
  };
}

export interface StagePlotState {
  info: StagePlotInfo | null;
  present: boolean;
  visible: boolean;
  opacity: number;
  busy: boolean;
  message: { severity: 'error' | 'success' | 'info'; text: string } | null;
  calibrating: boolean;
  draft: CalibrationDraft;
  step: PickStep;
  /** Why the draft cannot be saved yet, or null. */
  draftProblem: string | null;
  underlay: PlanUnderlay | null;
  onPlanPick: ((x: number, z: number) => void) | undefined;
  pickMarks: PlanPickMark[] | undefined;
  upload: (file: File) => Promise<void>;
  remove: () => Promise<void>;
  setVisible: (visible: boolean) => void;
  setOpacity: (opacity: number) => void;
  commitOpacity: (opacity: number) => Promise<void>;
  startCalibrate: () => void;
  cancelCalibrate: () => void;
  repick: () => void;
  setDistance: (distance: string) => void;
  setRotation: (rotation: number) => void;
  saveCalibration: () => Promise<void>;
  clearMessage: () => void;
}

export default function useStagePlot(rigId: number | null | undefined, stageWidth: number, stageDepth: number): StagePlotState {
  const [info, setInfo] = useState<StagePlotInfo | null>(null);
  const [href, setHref] = useState<string | null>(null);
  const [visible, setVisible] = useState(true);
  const [opacity, setOpacity] = useState(DEFAULT_OPACITY);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<StagePlotState['message']>(null);
  const [calibrating, setCalibrating] = useState(false);
  const [draft, setDraft] = useState<CalibrationDraft>(EMPTY_DRAFT);
  const hrefRef = useRef<string | null>(null);

  const showImage = useCallback((blob: Blob | null) => {
    if (hrefRef.current) URL.revokeObjectURL(hrefRef.current);
    hrefRef.current = blob ? URL.createObjectURL(blob) : null;
    setHref(hrefRef.current);
  }, []);

  const take = useCallback(async (id: number, next: StagePlotInfo) => {
    setInfo(next);
    setOpacity(next.calibration?.opacity ?? DEFAULT_OPACITY);
    showImage(next.present ? await stagePlotApi.image(id) : null);
  }, [showImage]);

  useEffect(() => {
    let live = true;
    setInfo(null);
    setCalibrating(false);
    setDraft(EMPTY_DRAFT);
    showImage(null);
    if (rigId == null) return undefined;
    (async () => {
      try {
        const next = await stagePlotApi.info(rigId);
        if (live) await take(rigId, next);
      } catch {
        // No stage plot to draw: the plan is as it always was.
      }
    })();
    return () => { live = false; };
  }, [rigId, showImage, take]);

  useEffect(() => () => { if (hrefRef.current) URL.revokeObjectURL(hrefRef.current); }, []);

  // This hook's own changes are announced to the others showing the rig (the 3D view, another tab),
  // and theirs read here, so a plot removed or replaced in one is gone or replaced in the other.
  const self = useRef({}).current;
  useEffect(() => {
    if (rigId == null) return undefined;
    let live = true;
    const off = onStagePlotChange(rigId, self, (change) => {
      (async () => {
        try {
          const next = await stagePlotApi.info(rigId);
          if (!live) return;
          if (change === 'image') {
            await take(rigId, next);
          } else {
            setInfo(next);
            setOpacity(next.calibration?.opacity ?? DEFAULT_OPACITY);
          }
        } catch {
          // Kept as it was: the next visit reads it again.
        }
      })();
    });
    return () => { live = false; off(); };
  }, [rigId, self, take]);

  const present = !!info?.present && !!href;
  const widthPx = info?.width_px ?? 1;
  const heightPx = info?.height_px ?? 1;

  // What the plan is drawn with before the draft has all it needs: the stored calibration, or fitted to the stage.
  const baseMatrix: Matrix = useMemo(
    () => info?.transform?.matrix ?? fitTransform(widthPx, heightPx, stageWidth, stageDepth),
    [info, widthPx, heightPx, stageWidth, stageDepth],
  );
  const preview = calibrating ? draftCalibration(draft, opacity) : null;
  const draftProblem = calibrating
    ? (preview ? calibrationProblem(preview) : 'Click the points on the plan first.')
    : null;
  const matrix: Matrix = preview && !draftProblem ? calibrationTransform(preview).matrix : baseMatrix;

  const underlay: PlanUnderlay | null = present && (visible || calibrating)
    ? { href: href as string, widthPx, heightPx, matrix, opacity }
    : null;

  const step = pickStep(draft);
  // A click is a point only while one is still to be picked, and over a drawn plot.
  const onPlanPick = calibrating && present && step !== 'done'
    ? (x: number, z: number) => {
      const point = toImage(matrix, x, z);
      setDraft((d) => {
        const at = pickStep(d);
        return at === 'done' ? d : { ...d, [at]: point };
      });
    }
    : undefined;

  const pickMarks: PlanPickMark[] | undefined = calibrating
    ? (['a', 'b', 'origin'] as const).flatMap((key) => {
      const point = draft[key];
      if (!point) return [];
      const at = toPlan(matrix, point.x, point.y);
      return [{ x: at.x, z: at.z, label: key === 'origin' ? 'O' : key.toUpperCase() }];
    })
    : undefined;

  const upload = useCallback(async (file: File) => {
    if (rigId == null) return;
    setBusy(true);
    try {
      const next = await stagePlotApi.upload(rigId, file);
      setCalibrating(false);
      setDraft(EMPTY_DRAFT);
      setVisible(true);
      await take(rigId, next);
      announceStagePlotChange(rigId, 'image', self);
      setMessage({ severity: 'success', text: 'Stage plot added. Calibrate it so it lies at the right size.' });
    } catch (error) {
      setMessage({ severity: 'error', text: refusalText(error, 'The stage plot could not be uploaded.') });
    } finally {
      setBusy(false);
    }
  }, [rigId, take, self]);

  const remove = useCallback(async () => {
    if (rigId == null) return;
    setBusy(true);
    try {
      await stagePlotApi.remove(rigId);
      setInfo({ rig_id: rigId, present: false });
      showImage(null);
      setCalibrating(false);
      setDraft(EMPTY_DRAFT);
      announceStagePlotChange(rigId, 'image', self);
      setMessage({ severity: 'info', text: 'Stage plot removed. Nothing else in the rig changed.' });
    } catch (error) {
      setMessage({ severity: 'error', text: refusalText(error, 'The stage plot could not be removed.') });
    } finally {
      setBusy(false);
    }
  }, [rigId, showImage, self]);

  const send = useCallback(async (calibration: StagePlotCalibration) => {
    if (rigId == null) return false;
    setBusy(true);
    try {
      const answer = await stagePlotApi.calibrate(rigId, calibration);
      setInfo((current) => current && { ...current, calibration: answer.calibration, transform: answer.transform });
      announceStagePlotChange(rigId, 'calibration', self);
      return true;
    } catch (error) {
      setMessage({ severity: 'error', text: refusalText(error, 'The calibration could not be saved.') });
      return false;
    } finally {
      setBusy(false);
    }
  }, [rigId, self]);

  const saveCalibration = useCallback(async () => {
    const calibration = draftCalibration(draft, opacity);
    const problem = calibration ? calibrationProblem(calibration) : 'Click the points on the plan first.';
    if (!calibration || problem) {
      setMessage({ severity: 'error', text: problem ?? 'Click the points on the plan first.' });
      return;
    }
    if (await send(calibration)) {
      setCalibrating(false);
      setDraft(EMPTY_DRAFT);
      setMessage({ severity: 'success', text: 'Stage plot calibrated. Drag the amber-ringed fixtures onto it.' });
    }
  }, [draft, opacity, send]);

  // Outside calibration the slider's value is kept with a stored calibration; without one it is only on screen.
  // The value is passed in: for a key press the slider commits in the same tick as it changes, before state has it.
  const commitOpacity = useCallback(async (value: number) => {
    setOpacity(value);
    const stored = info?.calibration;
    if (calibrating || !stored || stored.opacity === value) return;
    await send({ ...stored, opacity: value });
  }, [calibrating, info, send]);

  const startCalibrate = useCallback(() => {
    const stored = info?.calibration;
    setDraft({ ...EMPTY_DRAFT, distance: stored ? String(stored.distance_m) : '', rotation: stored?.rotation_deg ?? 0 });
    setCalibrating(true);
    setMessage(null);
  }, [info]);

  return {
    info,
    present,
    visible,
    opacity,
    busy,
    message,
    calibrating,
    draft,
    step,
    draftProblem,
    underlay,
    onPlanPick,
    pickMarks,
    upload,
    remove,
    setVisible,
    setOpacity,
    commitOpacity,
    startCalibrate,
    cancelCalibrate: () => { setCalibrating(false); setDraft(EMPTY_DRAFT); },
    repick: () => setDraft((d) => ({ ...d, a: null, b: null, origin: null })),
    setDistance: (distance: string) => setDraft((d) => ({ ...d, distance })),
    setRotation: (rotation: number) => setDraft((d) => ({ ...d, rotation })),
    saveCalibration,
    clearMessage: () => setMessage(null),
  };
}
