export type Point = { x: number; y: number; include: boolean };
export type Annotation = {
  frame: number;
  points: Point[];
  box: [number, number, number, number] | null;
};
export type Subject = {
  id: number;
  name: string;
  references: string[];
  kind: "human" | "fictional";
  portrait_asset: string | null;
  annotations: Annotation[];
};
export type Recipe = {
  start: number;
  end: number;
  mode: "advanced" | "fast" | "combined";
  subjects: Subject[];
  pitch: number;
  pitch_backend: "librosa" | "rubberband";
  segmentation: "sam2-large" | "sam2-small" | "sam3";
  audio: "original" | "custom";
  custom_audio: string | null;
  custom_mix_background: boolean;
  transcribe: boolean;
  describe: boolean;
  prompt: string;
};
export type Media = {
  width: number;
  height: number;
  duration: number;
  frames: number;
  fps: number;
  has_audio: boolean;
};
export type Asset = {
  id: string;
  name: string;
  kind: string;
  metadata: Media;
  hash: string;
};
export type Artifact = {
  id: string;
  kind: string;
  metadata: Media;
  revision: number;
  producer: string;
  hash: string;
};
export type Attempt = {
  id: string;
  revision: number;
  provider: string;
  status: string;
  error?: string;
  remote_id?: string;
  draft_id?: string;
  draft_expires?: number;
  artifact?: string;
  preview?: string;
  actual_cost?: number;
  reservation: number;
  settled?: boolean;
  pilot: boolean;
  parent?: string;
  progress?: number;
  poll_error?: string;
};
export type Job = {
  id: string;
  name: string;
  source: string;
  source_asset: Asset;
  status: string;
  stage: string;
  revision: number;
  recipe: Recipe;
  artifacts: Record<string, Artifact>;
  attempts: Attempt[];
  approval: unknown;
  preview_approval: string | null;
  budget_usd: number;
  spent_usd: number;
  reserved_usd: number;
  required_models: string[];
  available_actions: Record<string, boolean>;
  progress?: { stage: string; progress: number };
  error?: string;
};
export type Model = {
  ready: boolean;
  package?: boolean;
  checkpoint?: boolean;
  license?: string;
  reason?: string;
};
export type System = {
  gpu: { available: boolean; name?: string; total_mb?: number };
  models: Record<string, Model>;
  worker_active: boolean;
  providers: Record<
    string,
    {
      configured: boolean;
      native: boolean;
      portraits: boolean;
      qualified: boolean;
    }
  >;
  storage_configured: boolean;
  benchmarks: {
    stage: string;
    seconds: number;
    peak_mb: number;
    cached?: boolean;
  }[];
};
export type Quote = {
  id: string;
  provider: string;
  eligible: boolean;
  qualified: boolean;
  reason: string | null;
  estimate: number;
  reserve: number;
  native: boolean;
  expires: number;
  parent?: string;
};
export async function api<T>(
  path: string,
  body?: unknown,
  method = "POST",
): Promise<T> {
  const response = await fetch(
    `/api${path}`,
    body === undefined
      ? undefined
      : {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : JSON.stringify(result.detail || response.statusText),
    );
  }
  return response.json();
}
export async function upload(file: File): Promise<Asset> {
  const data = new FormData();
  data.append("file", file);
  const response = await fetch("/api/assets", { method: "POST", body: data });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Import failed");
  return result;
}
export const content = (artifact?: string) =>
  artifact ? `/api/artifacts/${artifact}/content` : "";
export function timecode(seconds: number) {
  const frames = Math.max(0, Math.round(seconds * 24));
  return `${Math.floor(frames / 1440)
    .toString()
    .padStart(2, "0")}:${Math.floor((frames / 24) % 60)
    .toString()
    .padStart(2, "0")}:${(frames % 24).toString().padStart(2, "0")}`;
}
export const usd = (value: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 3,
  }).format(value);
export const defaultRecipe: Recipe = {
  start: 0,
  end: 5,
  mode: "advanced",
  subjects: [],
  pitch: 3,
  pitch_backend: "librosa",
  segmentation: "sam2-large",
  audio: "original",
  custom_audio: null,
  custom_mix_background: false,
  transcribe: false,
  describe: false,
  prompt:
    "Replace the selected characters completely using the reference images. Preserve movement, camera timing, background, and vocal synchronization.",
};
