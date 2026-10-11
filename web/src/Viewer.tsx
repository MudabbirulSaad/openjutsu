import { useEffect, useRef, useState } from "react";
import {
  Pause,
  Play,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
} from "lucide-react";
import { Button } from "./ui";
import { type Point, timecode } from "./api";
export function normalizedPoint(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
  width: number,
  height: number,
): Point | null {
  const scale = Math.min(rect.width / width, rect.height / height);
  const x =
    (clientX - rect.left - (rect.width - width * scale) / 2) / (width * scale);
  const y =
    (clientY - rect.top - (rect.height - height * scale) / 2) /
    (height * scale);
  return x >= 0 && x <= 1 && y >= 0 && y <= 1 ? { x, y, include: true } : null;
}
export function Viewer({
  url,
  compare,
  frameUrl,
  compareFrameUrl,
  duration,
  width,
  height,
  frame,
  setFrame,
  points,
  annotate,
  onPoint,
  onPlaying,
}: {
  url: string;
  compare?: string;
  frameUrl?: string;
  compareFrameUrl?: string;
  duration: number;
  width: number;
  height: number;
  frame: number;
  setFrame: (n: number) => void;
  points: Point[];
  annotate: boolean;
  onPoint: (p: Point) => void;
  onPlaying: (b: boolean) => void;
}) {
  const first = useRef<HTMLVideoElement>(null),
    second = useRef<HTMLVideoElement>(null);
  const plane = useRef<HTMLDivElement>(null);
  const [contained, setContained] = useState({ width: 0, height: 0 });
  useEffect(() => {
    if (!plane.current) return;
    const observer = new ResizeObserver(([entry]) => {
      const scale = Math.min(
        entry.contentRect.width / width,
        entry.contentRect.height / height,
      );
      setContained({ width: width * scale, height: height * scale });
    });
    observer.observe(plane.current);
    return () => observer.disconnect();
  }, [width, height, annotate, compare]);
  const [playing, setPlaying] = useState(false),
    [muted, setMuted] = useState(false),
    [error, setError] = useState("");
  const frames = Math.max(1, Math.round(duration * 24));
  useEffect(() => {
    setError("");
    setPlaying(false);
    onPlaying(false);
  }, [url]);
  useEffect(() => {
    if (
      !playing &&
      first.current &&
      Math.abs(first.current.currentTime - frame / 24) > 0.005
    )
      first.current.currentTime = frame / 24;
    if (second.current) second.current.currentTime = frame / 24;
  }, [frame, playing, compare]);
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      if (first.current) {
        const t = first.current.currentTime;
        setFrame(Math.min(frames - 1, Math.floor(t * 24)));
        if (second.current && Math.abs(second.current.currentTime - t) > 0.04)
          second.current.currentTime = t;
      }
      raf = requestAnimationFrame(tick);
    };
    if (playing) raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, frames, setFrame]);
  const toggle = async () => {
    if (!first.current) return;
    if (playing) {
      first.current.pause();
      second.current?.pause();
    } else {
      if (first.current.ended) first.current.currentTime = 0;
      try {
        await first.current.play();
        await second.current?.play();
      } catch {
        setError("This preview could not play. Try the frame controls.");
      }
    }
  };
  const seek = (n: number) => {
    first.current?.pause();
    second.current?.pause();
    setFrame(Math.max(0, Math.min(frames - 1, n)));
  };
  const pane = (secondary: boolean) => (
    <div className="video-pane">
      <video
        ref={secondary ? second : first}
        src={secondary ? compare : url}
        playsInline
        preload="metadata"
        muted={secondary || muted}
        onPlay={
          secondary
            ? undefined
            : () => {
                setPlaying(true);
                onPlaying(true);
              }
        }
        onPause={
          secondary
            ? undefined
            : () => {
                setPlaying(false);
                onPlaying(false);
                second.current?.pause();
              }
        }
        onEnded={
          secondary
            ? undefined
            : () => {
                setPlaying(false);
                onPlaying(false);
              }
        }
        onError={() =>
          setError("Preview is unavailable. Reconnect or reprepare this clip.")
        }
      />
      {!playing && (secondary ? compareFrameUrl : frameUrl) && (
        <img
          className="exact-frame"
          src={(secondary ? compareFrameUrl : frameUrl)!}
          alt={secondary ? "Comparison frame" : "Exact indexed review frame"}
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
          onLoad={(e) => {
            e.currentTarget.style.display = "block";
          }}
        />
      )}
      {!secondary && annotate && (
        <div
          className="annotation-plane"
          ref={plane}
          aria-label="Video annotation canvas. Use the coordinate fields for keyboard selection."
          role="img"
          onClick={(e) => {
            if (playing) return;
            const p = normalizedPoint(
              e.clientX,
              e.clientY,
              e.currentTarget.getBoundingClientRect(),
              width,
              height,
            );
            if (p) onPoint(p);
          }}
        >
          <div
            className="points-plane"
            style={{
              width: contained.width,
              height: contained.height,
              flexShrink: 0,
            }}
          >
            {points.map((p, i) => (
              <span
                className={`point ${p.include ? "include" : "exclude"}`}
                key={i}
                style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%` }}
              >
                {i + 1}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
  return (
    <section className="viewer" aria-label="Video preview">
      <div className={`video-stage ${compare ? "comparison" : ""}`}>
        {url ? (
          pane(false)
        ) : (
          <div className="viewer-empty">Import a clip to begin</div>
        )}
        {compare && pane(true)}
      </div>
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      <div className="transport">
        <div className="transport-buttons">
          <Button
            size="icon"
            variant="ghost"
            aria-label="Previous frame"
            onClick={() => seek(frame - 1)}
            disabled={!url}
          >
            <SkipBack size={16} />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label={playing ? "Pause" : "Play"}
            onClick={toggle}
            disabled={!url}
          >
            {playing ? <Pause size={19} /> : <Play size={19} />}
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Next frame"
            onClick={() => seek(frame + 1)}
            disabled={!url}
          >
            <SkipForward size={16} />
          </Button>
          <span className="timecode">
            {timecode(frame / 24)} <span>/ {timecode(duration)}</span>
          </span>
        </div>
        <Button
          size="icon"
          variant="ghost"
          aria-label={muted ? "Unmute" : "Mute"}
          onClick={() => setMuted(!muted)}
        >
          {muted ? <VolumeX size={17} /> : <Volume2 size={17} />}
        </Button>
      </div>
      <div className="timeline">
        <input
          type="range"
          min={0}
          max={frames - 1}
          value={frame}
          aria-label="Timeline frame"
          onChange={(e) => seek(Number(e.target.value))}
        />
        <div className="timeline-labels">
          <span>00:00:00</span>
          <label>
            Frame{" "}
            <input
              type="number"
              min={0}
              max={frames - 1}
              value={frame}
              onChange={(e) => seek(Number(e.target.value))}
            />
          </label>
          <span>{timecode(duration)}</span>
        </div>
      </div>
    </section>
  );
}
