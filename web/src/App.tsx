import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Download,
  Film,
  Folder,
  Layers,
  Plus,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Upload,
  WifiOff,
  X,
} from "lucide-react";
import {
  api,
  upload,
  content,
  defaultRecipe,
  timecode,
  usd,
  type Asset,
  type Job,
  type Quote,
  type Recipe,
  type System,
  type Point,
  type Subject,
} from "./api";
import { Button, Sheet } from "./ui";
import { Viewer } from "./Viewer";
import { DepthContour } from "./DepthContour";

const stages = ["prepare", "review", "generate", "export"] as const;
function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
function UploadButton({
  label,
  accept,
  onFile,
  disabled = false,
}: {
  label: string;
  accept: string;
  onFile: (f: File) => void;
  disabled?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <Button disabled={disabled} onClick={() => input.current?.click()}>
        <Upload size={15} />
        {label}
      </Button>
      <input
        ref={input}
        type="file"
        accept={accept}
        className="sr-only"
        tabIndex={-1}
        aria-label={label}
        onChange={(e) => {
          if (e.target.files?.[0]) onFile(e.target.files[0]);
          e.target.value = "";
        }}
      />
    </>
  );
}
function Theme() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem("theme") || "system",
  );
  useEffect(() => {
    const q = matchMedia("(prefers-color-scheme: dark)");
    const apply = () =>
      (document.documentElement.dataset.theme =
        theme === "system" ? (q.matches ? "dark" : "light") : theme);
    apply();
    q.addEventListener("change", apply);
    localStorage.setItem("theme", theme);
    return () => q.removeEventListener("change", apply);
  }, [theme]);
  return (
    <select
      aria-label="Color theme"
      className="theme-select"
      value={theme}
      onChange={(e) => setTheme(e.target.value)}
    >
      <option value="system">System theme</option>
      <option value="light">Light theme</option>
      <option value="dark">Dark theme</option>
    </select>
  );
}
export function App() {
  const client = useQueryClient();
  const [connected, setConnected] = useState(true);
  useEffect(() => {
    const events = new EventSource("/api/events");
    events.onopen = () => setConnected(true);
    events.onerror = () => setConnected(false);
    events.onmessage = () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["job"] });
    };
    return () => events.close();
  }, [client]);
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand" aria-label="OpenJutsu projects">
          <Layers size={23} />
          <span>OpenJutsu</span>
          <span className="alpha">alpha</span>
        </Link>
        <nav aria-label="Main navigation">
          <NavLink to="/" end>
            <Folder size={16} />
            Projects
          </NavLink>
          <NavLink to="/recipes">
            <Layers size={16} />
            Recipes
          </NavLink>
          <NavLink to="/settings">
            <Settings2 size={16} />
            Settings
          </NavLink>
        </nav>
        <div className="header-right">
          {!connected && (
            <span className="connection" role="status">
              <WifiOff size={15} />
              Reconnecting
            </span>
          )}
          <Theme />
        </div>
      </header>
      <Routes>
        <Route path="/" element={<Projects />} />
        <Route path="/recipes" element={<Projects recipes />} />
        <Route path="/settings" element={<Settings />} />
        <Route
          path="/studio/:id/:stage"
          element={<Studio connected={connected} />}
        />
        <Route
          path="*"
          element={
            <p className="page">
              <Link to="/">Return to projects</Link>
            </p>
          }
        />
      </Routes>
    </div>
  );
}
function Projects({ recipes = false }: { recipes?: boolean }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [error, setError] = useState("");
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api<Job[]>("/jobs"),
    refetchInterval: 5000,
  });
  const templates = useQuery({
    queryKey: ["recipes"],
    queryFn: () =>
      api<{ id: string; name: string; recipe: Recipe }[]>("/recipes"),
    enabled: recipes,
  });
  const selected = useRef<Recipe | undefined>(undefined);
  const create = useMutation({
    mutationFn: async (file: File) => {
      const asset = await upload(file);
      if (asset.kind !== "video" || asset.metadata.duration < 4)
        throw Error("Choose a video at least four seconds long.");
      const recipe = {
        ...(selected.current || defaultRecipe),
        start: 0,
        end: Math.min(5, asset.metadata.duration),
      };
      return api<Job>("/jobs", {
        source: asset.id,
        name: file.name.replace(/\.[^.]+$/, ""),
        budget_usd: 0,
        recipe,
      });
    },
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      navigate(`/studio/${job.id}/prepare`);
    },
    onError: (e) => setError(e.message),
  });
  return (
    <main className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR LOCAL STUDIO</p>
          <h1>{recipes ? "Reusable recipes" : "Projects"}</h1>
          <p className="muted">
            {recipes
              ? "Start from reviewed settings. Bind references and select subjects for each new clip."
              : "Prepare locally. Review every frame. Choose what leaves your PC."}
          </p>
        </div>
        <UploadButton
          label={create.isPending ? "Importing…" : "New project"}
          accept="video/*,.mkv,.mov"
          disabled={create.isPending}
          onFile={(f) => {
            selected.current = undefined;
            create.mutate(f);
          }}
        />
      </div>
      {error && (
        <p role="alert" className="alert">
          {error}
        </p>
      )}
      {jobs.error && (
        <p role="alert" className="alert">
          Backend unavailable. Launch OpenJutsu, then reconnect.
        </p>
      )}
      {recipes ? (
        <div className="project-list">
          {templates.data?.map((t) => (
            <div className="project-row" key={t.id}>
              <Layers size={22} />
              <div>
                <strong>{t.name}</strong>
                <p>
                  {t.recipe.mode} · {t.recipe.end - t.recipe.start}s ·{" "}
                  {t.recipe.subjects.length} subjects
                </p>
              </div>
              <UploadButton
                label="Use recipe"
                accept="video/*,.mkv"
                disabled={create.isPending}
                onFile={(f) => {
                  selected.current = t.recipe;
                  create.mutate(f);
                }}
              />
            </div>
          ))}
          {templates.data?.length === 0 && (
            <p className="empty-list">
              Save a recipe from the studio to reuse its settings.
            </p>
          )}
        </div>
      ) : (
        <div className="project-list">
          {jobs.data?.map((job) => (
            <Link
              className="project-row"
              key={job.id}
              to={`/studio/${job.id}/${job.stage || "prepare"}`}
            >
              <img
                src={`/api/assets/${job.source}/content?poster=true`}
                alt=""
              />
              <div>
                <strong>{job.name}</strong>
                <p>
                  {timecode(job.recipe.end - job.recipe.start)} ·{" "}
                  {job.recipe.mode} · revision {job.revision}
                </p>
              </div>
              <span className="status">{job.status.replaceAll("_", " ")}</span>
              <ChevronRight size={18} />
            </Link>
          ))}
          {jobs.data?.length === 0 && (
            <div className="project-empty">
              <div className="empty-mark">
                <DepthContour frozen={false} />
                <Film size={32} />
              </div>
              <h2>Your next scene starts here</h2>
              <p>
                Import a 4–30 second clip, or trim a longer recording.
                <br />
                Your originals and processing stay on this computer.
              </p>
              <UploadButton
                label="Import video"
                accept="video/*,.mkv,.mov"
                onFile={(f) => create.mutate(f)}
                disabled={create.isPending}
              />
              <p className="small">
                Cloud generation needs your own provider account and spending
                limit.
              </p>
            </div>
          )}
        </div>
      )}
    </main>
  );
}

function Studio({ connected }: { connected: boolean }) {
  const { id = "", stage = "prepare" } = useParams();
  const navigate = useNavigate(),
    client = useQueryClient();
  const query = useQuery({
    queryKey: ["job", id],
    queryFn: () => api<Job>(`/jobs/${id}`),
    refetchInterval: connected ? false : 5000,
  });
  const system = useQuery({
    queryKey: ["system"],
    queryFn: () => api<System>("/system"),
    refetchInterval: 5000,
  });
  const job = query.data;
  const [recipe, setRecipe] = useState<Recipe | null>(null),
    [base, setBase] = useState(0),
    [frame, setFrame] = useState(0),
    [playing, setPlaying] = useState(false),
    [tab, setTab] = useState("conditioning"),
    [compare, setCompare] = useState(false),
    [selected, setSelected] = useState(1),
    [exclude, setExclude] = useState(false),
    [attempt, setAttempt] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const busy = useRef(false);
  useEffect(() => {
    if (!job) return;
    if (!recipe) {
      let saved: { revision: number; recipe: Recipe } | null = null;
      try {
        saved = JSON.parse(localStorage.getItem(`draft:${id}`) || "null");
      } catch {}
      setRecipe(saved?.recipe || job.recipe);
      setBase(saved?.revision || job.revision);
    } else if (
      base !== job.revision &&
      JSON.stringify(recipe) === JSON.stringify(job.recipe)
    ) {
      setBase(job.revision);
    }
  }, [job, id, recipe, base]);
  useEffect(() => {
    if (recipe)
      localStorage.setItem(
        `draft:${id}`,
        JSON.stringify({ revision: base, recipe }),
      );
  }, [id, recipe, base]);
  useEffect(() => {
    setFrame(0);
    setPlaying(false);
  }, [stage, id]);
  const dirty =
      !!job &&
      !!recipe &&
      JSON.stringify(job.recipe) !== JSON.stringify(recipe),
    stale = !!job && base !== job.revision;
  const action = useMutation({
    mutationFn: async ({
      path,
      body,
      method = "POST",
      next,
    }: {
      path: string;
      body?: unknown;
      method?: string;
      next?: string;
    }) => {
      if (busy.current) throw Error("An operation is already in progress.");
      busy.current = true;
      try {
        return { result: await api<unknown>(path, body ?? {}, method), next };
      } finally {
        busy.current = false;
      }
    },
    onSuccess: async ({ next }) => {
      await client.invalidateQueries({ queryKey: ["job", id] });
      await client.invalidateQueries({ queryKey: ["quotes", id] });
      setError("");
      if (next) navigate(`/studio/${id}/${next}`);
    },
    onError: (e) => setError(e.message),
  });
  const call = (suffix: string, body?: unknown, next?: string) =>
    action.mutate({ path: `/jobs/${id}/${suffix}`, body, next });
  const save = () => {
    if (!recipe || !job) return;
    action.mutate(
      {
        path: `/jobs/${id}/recipe`,
        body: { revision: base, recipe },
        method: "PUT",
      },
      {
        onSuccess: ({ result }) => {
          const j = result as Job;
          setRecipe(j.recipe);
          setBase(j.revision);
          setNotice("Saved. Preparation approval has been reset.");
        },
      },
    );
  };
  const quotes = useQuery({
    queryKey: ["quotes", id, job?.revision, job?.status],
    queryFn: () => api<Quote[]>(`/jobs/${id}/quotes`),
    enabled: stage === "generate" && !!job?.approval,
    refetchInterval: 60000,
  });
  const activeAttempt =
    job?.attempts.find((a) => a.id === attempt) ||
    job?.attempts.filter((a) => a.status === "succeeded").at(-1);
  const native = useQuery({
    queryKey: ["native", id, activeAttempt?.id],
    queryFn: () =>
      api<Quote[]>(`/jobs/${id}/quotes?parent=${activeAttempt!.id}`),
    enabled: stage === "export" && !!activeAttempt,
    refetchInterval: 60000,
  });
  if (query.isPending || !job || !recipe)
    return (
      <main className="page">
        <p role="status">
          {query.error
            ? "Could not load this project. Reconnect the backend."
            : "Loading your local project…"}
        </p>
        <Link to="/">Projects</Link>
      </main>
    );
  const update = (values: Partial<Recipe>) =>
    setRecipe({ ...recipe, ...values });
  const updateSubject = (subject: Subject) =>
    update({
      subjects: recipe.subjects.map((s) => (s.id === subject.id ? subject : s)),
    });
  const subject =
    recipe.subjects.find((s) => s.id === selected) || recipe.subjects[0];
  const annotation = subject?.annotations.find((a) => a.frame === frame);
  const addPoint = (p: Point) => {
    if (!subject) return;
    const changed = {
      frame,
      points: [...(annotation?.points || []), { ...p, include: !exclude }],
      box: annotation?.box || null,
    };
    updateSubject({
      ...subject,
      annotations: [
        ...subject.annotations.filter((a) => a.frame !== frame),
        changed,
      ].sort((a, b) => a.frame - b.frame),
    });
  };
  const artifacts = Object.fromEntries(
    Object.entries(job.artifacts).filter(
      ([, a]) => a.revision === job.revision,
    ),
  );
  const artifact = artifacts[tab] || artifacts.conditioning;
  const generated = stage === "generate" || stage === "export";
  const chosen =
    generated && activeAttempt?.preview ? activeAttempt.preview : artifact?.id;
  const sourceUrl = `/api/jobs/${id}/source-preview?revision=${job.revision}`;
  const primary =
    stage === "prepare" ? sourceUrl : content(chosen) || sourceUrl;
  const exact =
    stage === "prepare"
      ? `/api/jobs/${id}/source-frames/${frame}?revision=${job.revision}`
      : chosen
        ? `/api/artifacts/${chosen}/frames/${frame}`
        : undefined;
  const duration = job.recipe.end - job.recipe.start,
    source = artifacts.normalized;
  const currentStage = stages.indexOf(stage as (typeof stages)[number]);
  const unavailable = action.isPending || stale || dirty;
  const inspector = (
    <div className="inspector-inner">
      <div className="inspector-heading">
        <span className="eyebrow">{stage.toUpperCase()}</span>
        <span>Revision {job.revision}</span>
      </div>
      {stage === "prepare" && (
        <>
          <section>
            <h2>Source interval</h2>
            <div className="field-grid">
              <Field label="Start · seconds">
                <input
                  type="number"
                  min={0}
                  step={1 / 24}
                  value={recipe.start}
                  disabled={!job.available_actions.edit}
                  onChange={(e) => update({ start: Number(e.target.value) })}
                />
              </Field>
              <Field label="End · seconds">
                <input
                  type="number"
                  min={4}
                  max={job.source_asset.metadata.duration}
                  step={1 / 24}
                  value={recipe.end}
                  disabled={!job.available_actions.edit}
                  onChange={(e) => update({ end: Number(e.target.value) })}
                />
              </Field>
            </div>
            <p className="small">
              4–30 seconds · 24 fps · 960 px working edge.
              <br />
              Save to update the viewer interval.
            </p>
          </section>
          <section>
            <h2>Preparation</h2>
            <Field label="Mode">
              <select
                value={recipe.mode}
                disabled={!job.available_actions.edit}
                onChange={(e) =>
                  update({ mode: e.target.value as Recipe["mode"] })
                }
              >
                <option value="advanced">Advanced · depth subjects</option>
                <option value="fast">Fast · face mesh</option>
                <option value="combined">Combined · depth + mesh</option>
              </select>
            </Field>
            <Field label="Segmentation profile">
              <select
                value={recipe.segmentation}
                disabled={!job.available_actions.edit}
                onChange={(e) =>
                  update({
                    segmentation: e.target.value as Recipe["segmentation"],
                  })
                }
              >
                <option value="sam2-large">SAM 2.1 Large</option>
                <option value="sam2-small">SAM 2.1 Small</option>
                <option value="sam3">SAM 3 · experimental</option>
              </select>
            </Field>
          </section>
          <section>
            <div className="section-title">
              <h2>Subject bindings</h2>
              <Button
                size="small"
                disabled={
                  !job.available_actions.edit ||
                  recipe.subjects.length >= (recipe.mode === "advanced" ? 2 : 1)
                }
                onClick={() => {
                  const n = recipe.subjects.some((s) => s.id === 1) ? 2 : 1;
                  update({
                    subjects: [
                      ...recipe.subjects,
                      {
                        id: n,
                        name: `Subject ${n}`,
                        kind: "fictional",
                        portrait_asset: null,
                        references: [],
                        annotations: [],
                      },
                    ],
                  });
                  setSelected(n);
                }}
              >
                <Plus size={13} />
                Add
              </Button>
            </div>
            <div className="subject-tabs">
              {recipe.subjects.map((s) => (
                <Button
                  key={s.id}
                  size="small"
                  variant={selected === s.id ? "primary" : "secondary"}
                  onClick={() => setSelected(s.id)}
                >
                  {s.name}
                </Button>
              ))}
            </div>
            {subject ? (
              <>
                <Field label="Subject name">
                  <input
                    value={subject.name}
                    maxLength={100}
                    onChange={(e) =>
                      updateSubject({ ...subject, name: e.target.value })
                    }
                  />
                </Field>
                <Field label="Reference category">
                  <select
                    value={subject.kind}
                    onChange={(e) =>
                      updateSubject({
                        ...subject,
                        kind: e.target.value as Subject["kind"],
                      })
                    }
                  >
                    <option value="fictional">Fictional character</option>
                    <option value="human">
                      Real person · authorized portrait
                    </option>
                  </select>
                </Field>
                {subject.kind === "human" && (
                  <Field
                    label="BytePlus portrait asset"
                    hint="Enroll the authorized portrait with the provider. An image upload alone does not authorize a portrait."
                  >
                    <input
                      placeholder="asset://…"
                      value={subject.portrait_asset || ""}
                      onChange={(e) =>
                        updateSubject({
                          ...subject,
                          portrait_asset: e.target.value || null,
                        })
                      }
                    />
                  </Field>
                )}
                <div className="reference-row">
                  {subject.references.map((ref) => (
                    <div key={ref}>
                      <img
                        src={`/api/assets/${ref}/content`}
                        alt={`${subject.name} reference`}
                      />
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Remove reference"
                        onClick={() =>
                          updateSubject({
                            ...subject,
                            references: subject.references.filter(
                              (r) => r !== ref,
                            ),
                          })
                        }
                      >
                        <X size={13} />
                      </Button>
                    </div>
                  ))}
                </div>
                <UploadButton
                  label="Reference photo"
                  accept="image/png,image/jpeg"
                  disabled={subject.references.length >= 8}
                  onFile={async (f) => {
                    try {
                      const a = await upload(f);
                      updateSubject({
                        ...subject,
                        references: [...subject.references, a.id],
                      });
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                />
                <p className="small">
                  Full-body references help replace clothing, hands and
                  silhouette.
                </p>
                <Button
                  size="small"
                  variant="ghost"
                  onClick={() =>
                    update({
                      subjects: recipe.subjects.filter(
                        (s) => s.id !== subject.id,
                      ),
                    })
                  }
                >
                  Remove subject
                </Button>
              </>
            ) : (
              <p className="small">
                Add a subject, bind a reference, then pause at frame 0 and
                select the subject.
              </p>
            )}
          </section>
          {subject && recipe.mode !== "fast" && (
            <section>
              <h2>Correction · frame {frame}</h2>
              <label className="check">
                <input
                  type="checkbox"
                  checked={exclude}
                  onChange={(e) => setExclude(e.target.checked)}
                />
                Exclude selection points
              </label>
              <p className="small">
                Pause and click the subject. Every track needs an anchor at
                frame 0. Add corrections at later frames.
              </p>
              <PointEditor onPoint={addPoint} />
              {annotation && (
                <>
                  <p className="small">
                    {annotation.points.length} points
                    {annotation.box ? " · box selected" : ""}
                  </p>
                  <Button
                    size="small"
                    onClick={() =>
                      updateSubject({
                        ...subject,
                        annotations: subject.annotations.filter(
                          (a) => a.frame !== frame,
                        ),
                      })
                    }
                  >
                    Clear this frame
                  </Button>
                </>
              )}
              <BoxEditor
                value={annotation?.box || null}
                onBox={(box) =>
                  updateSubject({
                    ...subject,
                    annotations: [
                      ...subject.annotations.filter((a) => a.frame !== frame),
                      { frame, points: annotation?.points || [], box },
                    ].sort((a, b) => a.frame - b.frame),
                  })
                }
              />
            </section>
          )}
          <section>
            <h2>Audio & assistance</h2>
            <Field label="Final soundtrack">
              <select
                value={recipe.audio}
                onChange={(e) =>
                  update({ audio: e.target.value as Recipe["audio"] })
                }
              >
                <option value="original">Original soundtrack</option>
                <option value="custom">Custom recorded speech</option>
              </select>
            </Field>
            {recipe.audio === "custom" && (
              <>
                <UploadButton
                  label="Import recorded speech"
                  accept="audio/*,.wav,.mp3"
                  onFile={async (f) => {
                    try {
                      const a = await upload(f);
                      update({ custom_audio: a.id });
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                />
                <SpeechRecorder
                  duration={duration}
                  onFile={async (f) => {
                    const a = await upload(f);
                    update({ custom_audio: a.id });
                  }}
                />
                <p className="small">
                  {recipe.custom_audio
                    ? "Speech imported"
                    : "Choose or record a clip of the same duration."}
                </p>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={recipe.custom_mix_background}
                    onChange={(e) =>
                      update({ custom_mix_background: e.target.checked })
                    }
                  />
                  Mix with separated background
                </label>
              </>
            )}
            <Field label="Conditioning pitch · semitones">
              <input
                type="number"
                min={-12}
                max={12}
                value={recipe.pitch}
                onChange={(e) => update({ pitch: Number(e.target.value) })}
              />
            </Field>
            <label className="check">
              <input
                type="checkbox"
                checked={recipe.transcribe}
                onChange={(e) => update({ transcribe: e.target.checked })}
              />
              Whisper dialogue assistance
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={recipe.describe}
                onChange={(e) => update({ describe: e.target.checked })}
              />
              Qwen environment & motion suggestions
            </label>
          </section>
          <section>
            <Field label="Generation prompt">
              <textarea
                rows={5}
                value={recipe.prompt}
                onChange={(e) => update({ prompt: e.target.value })}
              />
            </Field>
            <Button
              onClick={save}
              disabled={
                !dirty ||
                stale ||
                action.isPending ||
                !job.available_actions.edit
              }
            >
              Save preparation settings
            </Button>
            {stale && (
              <div className="alert">
                The saved revision changed. Your draft is preserved.
                <Button
                  onClick={() => {
                    setRecipe(job.recipe);
                    setBase(job.revision);
                  }}
                >
                  Load latest revision
                </Button>
              </div>
            )}
            {job.required_models.length > 0 && (
              <p className="small">
                Install required models: {job.required_models.join(", ")}.{" "}
                <Link to="/settings">Readiness</Link>
              </p>
            )}
            <Button
              variant="primary"
              disabled={unavailable || !job.available_actions.prepare}
              onClick={() =>
                call("prepare", { revision: job.revision }, "review")
              }
            >
              <Sparkles size={16} />
              Prepare locally
            </Button>
          </section>
        </>
      )}
      {stage === "review" && (
        <>
          <section>
            <h2>Inspect preparation</h2>
            <p className="small">
              Check identity removal, mask edges, background, tracking and
              timing. The upload preview is the conditioning clip.
            </p>
            <label className="check">
              <input
                type="checkbox"
                checked={compare}
                onChange={(e) => setCompare(e.target.checked)}
              />
              Compare with original
            </label>
            <div className="artifact-list">
              {[
                "normalized",
                "mask",
                "depth",
                "composite",
                "mesh",
                "conditioning",
              ]
                .filter((k) => artifacts[k])
                .map((k) => (
                  <button
                    className={tab === k ? "selected" : ""}
                    key={k}
                    onClick={() => setTab(k)}
                  >
                    <span>
                      {k === "normalized" ? "Original · normalized" : k}
                    </span>
                    <Check size={13} />
                  </button>
                ))}
            </div>
            {artifacts.conditioning && (
              <a
                className="text-link"
                href={`${content(artifacts.conditioning.id)}?download=true`}
              >
                <Download size={14} />
                Download exact upload media
              </a>
            )}
          </section>
          <section>
            <h2>Audio review</h2>
            {[
              "original_audio",
              "vocals",
              "pitched",
              "custom_voice",
              "final_audio",
            ]
              .filter((k) => artifacts[k])
              .map((k) => (
                <div className="audio-review" key={k}>
                  <span>{k.replaceAll("_", " ")}</span>
                  <audio controls src={content(artifacts[k].id)} />
                </div>
              ))}
          </section>
          <Assistance
            artifacts={artifacts}
            onAppend={(text) => {
              update({ prompt: `${recipe.prompt}\n${text}` });
              setNotice(
                "Suggestion added to your draft. Save settings and reprepare to approve it.",
              );
            }}
          />
          <section>
            <p className="small">
              Approving binds revision {job.revision} and this conditioning
              artifact. Any recipe change clears approval.
            </p>
            <Button
              variant="primary"
              disabled={unavailable || !job.available_actions.approve}
              onClick={() =>
                call("approve", { revision: job.revision }, "generate")
              }
            >
              <CheckCircle2 size={16} />
              Approve upload preparation
            </Button>
            <Button onClick={() => navigate(`/studio/${id}/prepare`)}>
              Correct preparation
            </Button>
          </section>
        </>
      )}
      {stage === "generate" && (
        <>
          <BudgetEditor
            job={job}
            onSave={(value) =>
              action.mutate({
                path: `/jobs/${id}/budget`,
                body: { budget_usd: value },
                method: "PUT",
              })
            }
          />
          <Generation
            job={job}
            quotes={quotes.data || []}
            disabled={unavailable || !job.available_actions.generate}
            onGenerate={(quote, pilot) =>
              call("previews", {
                revision: job.revision,
                quote_id: quote.id,
                operation_id: crypto.randomUUID(),
                pilot,
              })
            }
          />
          <Attempts
            job={job}
            selected={activeAttempt?.id || ""}
            onSelect={setAttempt}
            onReconcile={(aid, body) =>
              action.mutate({ path: `/attempts/${aid}/reconcile`, body })
            }
            onQualify={(provider, body) =>
              action.mutate({ path: `/providers/${provider}/qualify`, body })
            }
          />
          {activeAttempt && (
            <section>
              <label className="check">
                <input
                  type="checkbox"
                  checked={compare}
                  onChange={(e) => setCompare(e.target.checked)}
                />
                Compare with original
              </label>
              <Button
                variant="primary"
                disabled={
                  unavailable ||
                  activeAttempt.revision !== job.revision ||
                  activeAttempt.status !== "succeeded"
                }
                onClick={() =>
                  call(
                    `approve-preview/${activeAttempt.id}`,
                    { revision: job.revision },
                    "export",
                  )
                }
              >
                Accept this preview
                <ArrowRight size={16} />
              </Button>
            </section>
          )}
        </>
      )}
      {stage === "export" && (
        <>
          <ExportOptions
            job={job}
            attempt={activeAttempt?.id || ""}
            native={native.data || []}
            system={system.data}
            disabled={unavailable || !job.available_actions.export}
            onExport={(route, upscaler, quote) =>
              call("finalize", {
                revision: job.revision,
                attempt_id: activeAttempt?.id,
                route,
                upscaler,
                quote_id: quote?.id,
                operation_id: crypto.randomUUID(),
              })
            }
          />
          <section>
            <h2>Deliverables</h2>
            {["master", "delivery"].map((k) =>
              artifacts[k] ? (
                <a
                  key={k}
                  className="download-link"
                  href={`${content(artifacts[k].id)}?download=true`}
                >
                  <Download size={16} />
                  <span>
                    {k === "master" ? "Native master" : "Browser delivery"}
                    <small>
                      {artifacts[k].metadata.width} ×{" "}
                      {artifacts[k].metadata.height} · {artifacts[k].producer}
                    </small>
                  </span>
                </a>
              ) : null,
            )}
            <a className="text-link" href={`/api/jobs/${id}/bundle`}>
              <Download size={14} />
              Recipe & provenance
            </a>
            <Button onClick={() => call("save-recipe", {})}>
              Save reusable recipe
            </Button>
            <p className="small">
              Upscaling changes resolution. Identity, motion and lips need a new
              generation if they are incorrect.
            </p>
          </section>
        </>
      )}
    </div>
  );
  return (
    <main className="studio">
      <div className="studio-heading">
        <div>
          <Link className="breadcrumb" to="/">
            Projects
          </Link>
          <ChevronRight size={13} />
          <h1>{job.name}</h1>
          <span className="status">{job.status.replaceAll("_", " ")}</span>
        </div>
        <div className="studio-meta">
          <span>{dirty ? "Unsaved changes" : `Revision ${job.revision}`}</span>
          <Sheet
            title="Clip inspector"
            trigger={
              <Button className="inspector-toggle">
                <SlidersHorizontal size={16} />
                Inspector
              </Button>
            }
          >
            {inspector}
          </Sheet>
          {job.available_actions.cancel && (
            <Button size="small" onClick={() => call("cancel", {})}>
              Cancel local work
            </Button>
          )}
        </div>
      </div>
      <nav className="stage-nav" aria-label="Workflow stages">
        {stages.map((s, i) => (
          <NavLink
            key={s}
            to={`/studio/${id}/${s}`}
            className={stage === s ? "active" : ""}
            aria-current={stage === s ? "step" : undefined}
          >
            {i < currentStage ? (
              <CheckCircle2 size={16} />
            ) : i === currentStage ? (
              <Circle size={16} />
            ) : (
              <span className="step-number">{i + 1}</span>
            )}
            <span>{s[0].toUpperCase() + s.slice(1)}</span>
            {i < 3 && <ChevronRight className="stage-chevron" size={14} />}
          </NavLink>
        ))}
      </nav>
      {(error || job.error) && (
        <div className="studio-alert alert" role="alert">
          {error || job.error}
          <Button
            size="icon"
            variant="ghost"
            aria-label="Dismiss operation error"
            onClick={() => setError("")}
          >
            <X size={16} />
          </Button>
        </div>
      )}
      {notice && (
        <p className="studio-notice" role="status">
          {notice}
          <Button
            size="icon"
            variant="ghost"
            aria-label="Dismiss notice"
            onClick={() => setNotice("")}
          >
            <X size={14} />
          </Button>
        </p>
      )}
      <div className="studio-content">
        <div className="workspace">
          <div className="viewer-heading">
            <span>
              {stage === "prepare"
                ? "Original · select subjects"
                : generated
                  ? `${activeAttempt?.provider || "No generation"} · ${activeAttempt?.parent ? "native" : "preview"}`
                  : tab}
            </span>
            <span>
              {compare
                ? "Synchronized comparison"
                : "24 fps · exact paused frames"}
            </span>
          </div>
          <Viewer
            url={primary}
            compare={
              compare ? (source ? content(source.id) : sourceUrl) : undefined
            }
            frameUrl={exact}
            compareFrameUrl={
              compare && source
                ? `/api/artifacts/${source.id}/frames/${frame}`
                : undefined
            }
            duration={duration}
            width={source?.metadata.width || job.source_asset.metadata.width}
            height={source?.metadata.height || job.source_asset.metadata.height}
            frame={frame}
            setFrame={setFrame}
            points={annotation?.points || []}
            annotate={
              stage === "prepare" &&
              recipe.mode !== "fast" &&
              !!subject &&
              job.available_actions.edit
            }
            onPoint={addPoint}
            onPlaying={setPlaying}
          />
          <footer className="workspace-footer">
            <div>
              <DepthContour frozen={playing || !!system.data?.worker_active} />
              <span
                className="worker-dot"
                data-active={system.data?.worker_active}
              />
              <span>
                {job.progress
                  ? `${job.progress.stage} · ${Math.round((job.progress.progress || 0) * 100)}%`
                  : system.data?.gpu.available
                    ? "CUDA preprocessing available"
                    : "Model environment needs setup"}
              </span>
            </div>
            <span>
              {job.recipe.mode} · {timecode(duration)}
            </span>
          </footer>
        </div>
        <aside className="inspector" aria-label="Clip inspector">
          {inspector}
        </aside>
      </div>
    </main>
  );
}

function PointEditor({ onPoint }: { onPoint: (p: Point) => void }) {
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
function BoxEditor({
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
function BudgetEditor({
  job,
  onSave,
}: {
  job: Job;
  onSave: (n: number) => void;
}) {
  const [limit, setLimit] = useState(job.budget_usd);
  return (
    <section>
      <h2>Spending limit</h2>
      <div className="cost-ledger">
        <span>
          Spent<strong>{usd(job.spent_usd)}</strong>
        </span>
        <span>
          Reserved<strong>{usd(job.reserved_usd)}</strong>
        </span>
        <span>
          Limit<strong>{usd(job.budget_usd)}</strong>
        </span>
      </div>
      <Field label="Project limit · USD">
        <input
          type="number"
          min={job.spent_usd + job.reserved_usd}
          max={10000}
          step={0.01}
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
        />
      </Field>
      <Button
        size="small"
        disabled={
          limit === job.budget_usd || limit < job.spent_usd + job.reserved_usd
        }
        onClick={() => onSave(limit)}
      >
        Save limit
      </Button>
      <p className="small">
        Quotes reserve a margin. Unsettled charges stay reserved until a receipt
        is reconciled. Also set a provider account spending cap.
      </p>
    </section>
  );
}
function Generation({
  job,
  quotes,
  disabled,
  onGenerate,
}: {
  job: Job;
  quotes: Quote[];
  disabled: boolean;
  onGenerate: (q: Quote, pilot: boolean) => void;
}) {
  const [selected, setSelected] = useState(""),
    [pilot, setPilot] = useState(false);
  const q =
    quotes.find((q) => q.id === selected) ||
    quotes.find((q) => q.eligible && q.qualified) ||
    quotes[0];
  return (
    <section>
      <h2>Generation route</h2>
      {!job.approval && (
        <p className="small">Approve the reviewed preparation first.</p>
      )}
      {quotes.map((quote) => (
        <label
          className={`quote-row ${quote.id === q?.id ? "selected" : ""}`}
          key={quote.id}
        >
          <input
            type="radio"
            name="provider"
            checked={quote.id === q?.id}
            onChange={() => setSelected(quote.id)}
            disabled={!quote.eligible}
          />
          <span>
            <strong>{quote.provider}</strong>
            <small>
              {quote.reason ||
                (quote.native
                  ? "Draft with native continuation"
                  : "480p edit · local upscale")}
            </small>
          </span>
          <span>{usd(quote.estimate)}</span>
        </label>
      ))}
      {q && !q.qualified && (
        <label className="check">
          <input
            type="checkbox"
            checked={pilot}
            onChange={(e) => setPilot(e.target.checked)}
          />
          Run a paid qualification pilot
        </label>
      )}
      {q && (
        <p className="small">
          Estimate {usd(q.estimate)} · reservation {usd(q.reserve / 1e6)}.
          Native continuation is separately quoted. Creative retries increase
          the finished cost.
        </p>
      )}
      <Button
        variant="primary"
        disabled={
          disabled ||
          !q?.eligible ||
          (!q.qualified && !pilot) ||
          job.budget_usd <
            job.spent_usd + job.reserved_usd + (q?.reserve || 0) / 1e6
        }
        onClick={() => onGenerate(q!, pilot)}
      >
        <Sparkles size={16} />
        Submit {q?.native ? "draft" : "480p preview"}
      </Button>
      <p className="small">Paid requests are never retried automatically.</p>
    </section>
  );
}
function Attempts({
  job,
  selected,
  onSelect,
  onReconcile,
  onQualify,
}: {
  job: Job;
  selected: string;
  onSelect: (id: string) => void;
  onReconcile: (id: string, body: unknown) => void;
  onQualify: (provider: string, body: unknown) => void;
}) {
  return (
    <section>
      <h2>Attempt history</h2>
      {job.attempts.length === 0 && (
        <p className="small">Your generations and costs will appear here.</p>
      )}
      {job.attempts.map((a, i) => (
        <div className="attempt" key={a.id}>
          <button
            className={selected === a.id ? "selected" : ""}
            onClick={() => onSelect(a.id)}
          >
            <span>
              #{i + 1} · {a.provider}
              {a.parent ? " · native" : ""}
            </span>
            <span>{a.status.replaceAll("_", " ")}</span>
          </button>
          <p className="small">
            Revision {a.revision} ·{" "}
            {a.remote_id ? `request ${a.remote_id}` : "No remote ID saved"}
            {a.actual_cost !== undefined
              ? ` · ${usd(a.actual_cost / 1e6)}`
              : " · billing unsettled"}
          </p>
          {a.error && <p className="small error-text">{a.error}</p>}
          {a.status === "unknown_submission" && (
            <Reconciliation onSubmit={(body) => onReconcile(a.id, body)} />
          )}{" "}
          {a.status === "succeeded" && !a.settled && (
            <Receipt
              onSubmit={(cost) => onReconcile(a.id, { actual_cost_usd: cost })}
            />
          )}{" "}
          {a.status === "succeeded" && a.pilot && (
            <PilotReview
              onSubmit={(review) =>
                onQualify(a.provider, { ...review, attempt_id: a.id })
              }
            />
          )}
        </div>
      ))}
    </section>
  );
}
function Reconciliation({ onSubmit }: { onSubmit: (body: unknown) => void }) {
  const [remote, setRemote] = useState(""),
    [verified, setVerified] = useState(false);
  return (
    <div className="reconcile">
      <p className="small">
        Check the provider dashboard before continuing. This reservation is held
        to prevent a duplicate payment.
      </p>
      <Field label="Existing provider request ID">
        <input value={remote} onChange={(e) => setRemote(e.target.value)} />
      </Field>
      <Button
        size="small"
        disabled={!remote}
        onClick={() => onSubmit({ remote_id: remote })}
      >
        Attach existing request
      </Button>
      <label className="check">
        <input
          type="checkbox"
          checked={verified}
          onChange={(e) => setVerified(e.target.checked)}
        />
        I verified that no request was submitted
      </label>
      <Button
        size="small"
        disabled={!verified}
        onClick={() => onSubmit({ confirmed_not_submitted: true })}
      >
        Release uncertain submission
      </Button>
    </div>
  );
}
function Receipt({ onSubmit }: { onSubmit: (cost: number) => void }) {
  const [cost, setCost] = useState(0);
  return (
    <div>
      <Field label="Settled charge · USD">
        <input
          type="number"
          min={0}
          step={0.001}
          value={cost}
          onChange={(e) => setCost(Number(e.target.value))}
        />
      </Field>
      <Button size="small" onClick={() => onSubmit(cost)}>
        Reconcile receipt
      </Button>
    </div>
  );
}
function PilotReview({
  onSubmit,
}: {
  onSubmit: (body: {
    actual_cost_usd: number;
    policy_reviewed: boolean;
    identity: number;
    motion: number;
    temporal: number;
    no_subject_swap: boolean;
    synchronized: boolean;
  }) => void;
}) {
  const [scores, setScores] = useState({ identity: 4, motion: 4, temporal: 4 }),
    [cost, setCost] = useState(0),
    [accepted, setAccepted] = useState(false);
  return (
    <details>
      <summary>Qualify this pilot</summary>
      {Object.entries(scores).map(([k, v]) => (
        <Field label={`${k} · 1–5`} key={k}>
          <input
            type="number"
            min={1}
            max={5}
            value={v}
            onChange={(e) =>
              setScores({ ...scores, [k]: Number(e.target.value) })
            }
          />
        </Field>
      ))}
      <Field label="Actual settled charge · USD">
        <input
          type="number"
          min={0}
          step={0.001}
          value={cost}
          onChange={(e) => setCost(Number(e.target.value))}
        />
      </Field>
      <label className="check">
        <input
          type="checkbox"
          checked={accepted}
          onChange={(e) => setAccepted(e.target.checked)}
        />
        I reviewed authorization and billing; no subject swaps or visible sync
        failures
      </label>
      <Button
        disabled={!accepted || Math.min(...Object.values(scores)) < 4}
        size="small"
        onClick={() =>
          onSubmit({
            ...scores,
            actual_cost_usd: cost,
            policy_reviewed: accepted,
            no_subject_swap: accepted,
            synchronized: accepted,
          })
        }
      >
        Record qualification
      </Button>
    </details>
  );
}
function ExportOptions({
  job,
  attempt,
  native,
  system,
  disabled,
  onExport,
}: {
  job: Job;
  attempt: string;
  native: Quote[];
  system?: System;
  disabled: boolean;
  onExport: (route: string, upscaler: string, quote?: Quote) => void;
}) {
  const [route, setRoute] = useState("original"),
    [upscaler, setUpscaler] = useState("seedvr2");
  const q = native.find((q) => q.eligible && q.qualified);
  const blocked =
    route === "native"
      ? !q
      : route === "upscale"
        ? !system?.models[upscaler]?.ready
        : false;
  return (
    <section>
      <h2>Finalization</h2>
      {!attempt && (
        <p className="small">Accept a successful preview to export.</p>
      )}
      {[
        [
          "original",
          "Original preview resolution",
          "Preserve the accepted generation.",
        ],
        [
          "upscale",
          "Economical · local upscale",
          "SeedVR2 produces 1080p from the accepted preview.",
        ],
        [
          "native",
          "Native · same draft to 1080p",
          q
            ? `${usd(q.estimate)} estimated · original provider/account`
            : native[0]?.reason || "A valid qualified draft is required.",
        ],
      ].map(([value, label, hint]) => (
        <label key={value} className="route-row">
          <input
            type="radio"
            name="finalization"
            value={value}
            checked={route === value}
            onChange={() => setRoute(value)}
          />
          <span>
            <strong>{label}</strong>
            <small>{hint}</small>
          </span>
        </label>
      ))}
      {route === "upscale" && (
        <Field label="Upscaling model">
          <select
            value={upscaler}
            onChange={(e) => setUpscaler(e.target.value)}
          >
            <option value="seedvr2">SeedVR2 · temporal</option>
            <option value="realesrgan">Real-ESRGAN · explicit fallback</option>
          </select>
        </Field>
      )}
      <Button
        variant="primary"
        disabled={
          disabled ||
          blocked ||
          !attempt ||
          (route === "native" &&
            job.budget_usd <
              job.spent_usd + job.reserved_usd + (q?.reserve || 0) / 1e6)
        }
        onClick={() => onExport(route, upscaler, q)}
      >
        <Download size={16} />
        Finalize selected output
      </Button>
      <p className="small">
        The unpitched selected soundtrack is restored. A master and a separate
        browser-compatible delivery are retained.
      </p>
    </section>
  );
}
function Assistance({
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
  if (!artifacts.transcript && !artifacts.description) return null;
  return (
    <section>
      <h2>Prompt assistance</h2>
      {["transcript", "description"]
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
function SpeechRecorder({
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
      recorder.current?.stop();
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
function Settings() {
  const client = useQueryClient();
  const system = useQuery({
    queryKey: ["system"],
    queryFn: () => api<System>("/system"),
  });
  const [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const save = useMutation({
    mutationFn: ({
      key,
      values,
    }: {
      key: string;
      values: Record<string, string>;
    }) => api(`/settings/${key}`, { values }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["system"] });
      setNotice("Saved locally. Credentials are excluded from exports.");
      setError("");
    },
    onError: (e) => setError(e.message),
  });
  return (
    <main className="page settings-page">
      <p className="eyebrow">LOCAL CONFIGURATION</p>
      <h1>Settings</h1>
      {error && (
        <p role="alert" className="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <section>
        <div className="section-title">
          <h2>Compute & model readiness</h2>
          <Button
            onClick={async () => {
              await api("/system?refresh=true");
              void client.invalidateQueries({ queryKey: ["system"] });
            }}
          >
            Refresh readiness
          </Button>
        </div>
        <p>
          {system.data?.gpu.name || "CUDA unavailable"}
          {system.data?.gpu.total_mb
            ? ` · ${Math.round(system.data.gpu.total_mb / 1024)} GB VRAM`
            : ""}
        </p>
        <p className="small">
          Availability checks installed packages and checkpoints. A readiness
          check is not a quality benchmark. See{" "}
          <a
            href="https://github.com/MudabbirulSaad/openjutsu/blob/main/docs/setup/models.md"
            target="_blank"
            rel="noreferrer"
          >
            model installation
          </a>
          .
        </p>
        <div className="model-list">
          {Object.entries(system.data?.models || {}).map(([name, model]) => (
            <div key={name}>
              <span>
                {name}
                <small>{model.license || model.reason}</small>
              </span>
              <span className={model.ready ? "ready" : ""}>
                {model.ready ? "Available" : "Needs installation"}
              </span>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h2>Generation providers</h2>
        <p className="small">
          Each route starts unqualified. Add an account, review its policy, and
          run a budgeted pilot before enabling normal generation.
        </p>
        {["byteplus", "segmind", "argolink"].map((key) => (
          <SecretForm
            key={key}
            name={key}
            configured={!!system.data?.providers[key]?.configured}
            fields={["api_key", "account"]}
            onSave={(values) => save.mutate({ key, values })}
            pending={save.isPending}
          />
        ))}
      </section>
      <section>
        <h2>Private temporary media storage</h2>
        <p className="small">
          Use a private S3-compatible bucket. Access links expire after one
          hour; uploaded objects are removed after 24 hours while the
          application is running. Configure a bucket lifecycle rule as a backup.
        </p>
        <SecretForm
          name="storage"
          configured={!!system.data?.storage_configured}
          fields={["bucket", "endpoint", "access_key", "secret_key", "region"]}
          onSave={(values) => save.mutate({ key: "storage", values })}
          pending={save.isPending}
        />
      </section>
    </main>
  );
}
function SecretForm({
  name,
  configured,
  fields,
  onSave,
  pending,
}: {
  name: string;
  configured: boolean;
  fields: string[];
  onSave: (values: Record<string, string>) => void;
  pending: boolean;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  return (
    <details className="secret-form">
      <summary>
        {name}
        <span>{configured ? "Configured locally" : "Not configured"}</span>
      </summary>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave(values);
          setValues({});
        }}
      >
        {fields.map((field) => (
          <Field key={field} label={field.replaceAll("_", " ")}>
            <input
              autoComplete="off"
              type={field.includes("key") ? "password" : "text"}
              value={values[field] || ""}
              onChange={(e) =>
                setValues({ ...values, [field]: e.target.value })
              }
              placeholder={
                field === "endpoint"
                  ? "https://…"
                  : field === "region"
                    ? "auto"
                    : undefined
              }
            />
          </Field>
        ))}
        <Button
          disabled={pending || !Object.values(values).some(Boolean)}
          type="submit"
        >
          Save {name}
        </Button>
      </form>
    </details>
  );
}
