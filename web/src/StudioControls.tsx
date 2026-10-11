import { useEffect, useRef, useState } from "react";
import { content, type Job, type Point } from "./api";
import { Button } from "./ui";

import { Field } from "./shared";
export function PointEditor({ onPoint }: { onPoint: (p: Point) => void }) {
  const [x, setX] = useState(0.5),
    [y, setY] = useState(0.5);
  return (
    <div className="coordinate-editor">
      <Field label="Point X · 0–1">
        <input
          type="number"
          min={0}
          max={1}
          step={0.01}
          value={x}
          onChange={(e) => setX(Number(e.target.value))}
        />
      </Field>
      <Field label="Point Y · 0–1">
        <input
          type="number"
          min={0}
          max={1}
          step={0.01}
          value={y}
          onChange={(e) => setY(Number(e.target.value))}
        />
      </Field>
      <Button
        size="small"
        onClick={() => onPoint({ x, y, include: true })}
        disabled={x < 0 || x > 1 || y < 0 || y > 1}
      >
        Add point
      </Button>
    </div>
  );
}
export function BoxEditor({
  value,
  onBox,
}: {
  value: [number, number, number, number] | null;
  onBox: (box: [number, number, number, number]) => void;
}) {
  const [box, setBox] = useState<[number, number, number, number]>(
    value || [0.2, 0.1, 0.8, 0.9],
  );
  return (
    <details>
      <summary>Bounding box alternative</summary>
      <div className="field-grid">
        {["Left", "Top", "Right", "Bottom"].map((label, i) => (
          <Field label={`${label} · 0–1`} key={label}>
            <input
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={box[i]}
              onChange={(e) =>
                setBox(
                  box.map((n, j) =>
                    j === i ? Number(e.target.value) : n,
                  ) as typeof box,
                )
              }
            />
          </Field>
        ))}
      </div>
      <Button
        size="small"
        disabled={
          box.some((n) => n < 0 || n > 1) ||
          box[0] >= box[2] ||
          box[1] >= box[3]
        }
        onClick={() => onBox(box)}
      >
        Set box on this frame
      </Button>
    </details>
  );
}
export function Assistance({
  artifacts,
  onAppend,
}: {
  artifacts: Job["artifacts"];
  onAppend: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const load = async (key: string) => {
    const result = await fetch(content(artifacts[key].id)).then((r) =>
      r.json(),
    );
    setText(
      key === "transcript" ? result.text : JSON.stringify(result, null, 2),
    );
  };
  if (!artifacts.transcript && !artifacts.descriptions) return null;
  return (
    <section>
      <h2>Prompt assistance</h2>
      {["transcript", "descriptions"]
        .filter((k) => artifacts[k])
        .map((k) => (
          <Button key={k} size="small" onClick={() => void load(k)}>
            Read {k}
          </Button>
        ))}
      {text && (
        <>
          <Field label="Editable suggestion">
            <textarea
              rows={6}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </Field>
          <Button size="small" onClick={() => onAppend(text)}>
            Append to prompt draft
          </Button>
        </>
      )}
      <p className="small">
        Descriptions are suggestions, separate from measured tracking data.
      </p>
    </section>
  );
}
export function SpeechRecorder({
  duration,
  onFile,
}: {
  duration: number;
  onFile: (f: File) => Promise<void>;
}) {
  const recorder = useRef<MediaRecorder | null>(null),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null),
    [recording, setRecording] = useState(false),
    [error, setError] = useState("");
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
      if (recorder.current?.state === "recording") {
        recorder.current.onstop = null;
        recorder.current.stop();
      }
      recorder.current?.stream.getTracks().forEach((t) => t.stop());
    },
    [],
  );
  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const r = new MediaRecorder(stream);
      recorder.current = r;
      const chunks: Blob[] = [];
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        const type = r.mimeType.includes("mp4") ? "m4a" : "webm";
        try {
          await onFile(
            new File(chunks, `recorded-speech.${type}`, { type: r.mimeType }),
          );
        } catch (e) {
          setError((e as Error).message);
        }
      };
      r.start();
      setRecording(true);
      timer.current = setTimeout(() => r.stop(), duration * 1000);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div>
      <Button size="small" disabled={recording} onClick={() => void start()}>
        {recording ? `Recording ${duration}s…` : "Record timed speech"}
      </Button>
      {error && (
        <p role="alert" className="small">
          {error}
        </p>
      )}
    </div>
  );
}
