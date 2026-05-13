import { useEffect, useMemo, useRef, useState } from 'react';
import {
  getTimeline,
  pauseSource,
  playSource,
  seekSource,
} from '../lib/runsApi';
import type { TimelinePoint } from '../lib/types';

interface Props {
  runId: string;
  currentFrame: number;
  tickCount: number;
  paused: boolean;
  onMessage?: (text: string) => void;
}

export default function ReplayScrubber({
  runId,
  currentFrame,
  tickCount,
  paused,
  onMessage,
}: Props) {
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [dragValue, setDragValue] = useState(0);
  const lastSeekAtRef = useRef(0);

  useEffect(() => {
    async function load() {
      try {
        const points = await getTimeline(runId);
        setTimeline(points);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        onMessage?.(`Timeline load failed: ${message}`);
      }
    }
    void load();
  }, [runId, onMessage]);

  const alertFrames = useMemo(
    () => timeline.filter((p) => p.alert_active).map((p) => p.frame),
    [timeline],
  );

  const firstAlertFrame = alertFrames.length > 0 ? alertFrames[0] : null;

  function maybeSeek(frame: number) {
    const now = performance.now();
    if (now - lastSeekAtRef.current < 100) return;
    lastSeekAtRef.current = now;
    seekSource(frame).catch((err: unknown) => {
      const message = err instanceof Error ? err.message : String(err);
      onMessage?.(`Seek failed: ${message}`);
    });
  }

  function handleSeek(frame: number) {
    lastSeekAtRef.current = performance.now();
    seekSource(frame).catch((err: unknown) => {
      const message = err instanceof Error ? err.message : String(err);
      onMessage?.(`Seek failed: ${message}`);
    });
  }

  function handlePlay() {
    playSource().catch((err: unknown) => {
      const message = err instanceof Error ? err.message : String(err);
      onMessage?.(`Play failed: ${message}`);
    });
  }

  function handlePause() {
    pauseSource().catch((err: unknown) => {
      const message = err instanceof Error ? err.message : String(err);
      onMessage?.(`Pause failed: ${message}`);
    });
  }

  function handleSliderChange(e: React.ChangeEvent<HTMLInputElement>) {
    const frame = Number(e.target.value);
    setDragValue(frame);
    if (isDragging) {
      maybeSeek(frame);
    }
  }

  function handlePointerDown() {
    setDragValue(currentFrame);
    setIsDragging(true);
  }

  function handlePointerUp(e: React.PointerEvent<HTMLInputElement>) {
    const frame = Number((e.target as HTMLInputElement).value);
    setIsDragging(false);
    handleSeek(frame);
  }

  const maxFrame = Math.max(0, tickCount - 1);
  const displayFrame = isDragging ? dragValue : currentFrame;

  return (
    <div className="panel replay-scrubber">
      <div className="panel-header">REPLAY TIMELINE</div>

      <div className="replay-scrubber__row">
        <button
          className="replay-scrubber__btn"
          onClick={paused ? handlePlay : handlePause}
        >
          {paused ? '▶' : '⏸'}
        </button>

        {firstAlertFrame !== null && (
          <button
            className="replay-scrubber__btn"
            onClick={() => handleSeek(firstAlertFrame)}
            title="jump to first alert"
          >
            ⚠ ALERT
          </button>
        )}

        <div className="replay-scrubber__track">
          <div className="replay-scrubber__markers">
            {alertFrames.map((frame) => (
              <span
                key={frame}
                className="replay-scrubber__marker"
                style={{
                  left: `${(frame / Math.max(1, tickCount - 1)) * 100}%`,
                }}
              />
            ))}
          </div>
          <input
            type="range"
            min={0}
            max={maxFrame}
            value={displayFrame}
            onChange={handleSliderChange}
            onPointerDown={handlePointerDown}
            onPointerUp={handlePointerUp}
          />
        </div>
      </div>

      <div className="replay-scrubber__meta">
        <span>
          FRAME{' '}
          <span className="replay-scrubber__frame">{displayFrame + 1}</span> /{' '}
          {tickCount}
        </span>
        <span>{paused ? 'PAUSED' : 'PLAYING'}</span>
      </div>
    </div>
  );
}
