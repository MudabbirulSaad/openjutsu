import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Download,
  Plus,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router-dom";
import {
  api,
  content,
  timecode,
  upload,
  type Job,
  type Point,
  type Quote,
  type Recipe,
  type Subject,
  type System,
} from "./api";
import { DepthContour } from "./DepthContour";
import { Button, Sheet } from "./ui";
import { Viewer } from "./Viewer";

import {
  Attempts,
  BudgetEditor,
  ExportOptions,
  Generation,
} from "./Generation";
import { Field, UploadButton } from "./shared";
import {
  Assistance,
  BoxEditor,
  PointEditor,
  SpeechRecorder,
} from "./StudioControls";
const stages = ["prepare", "review", "generate", "export"] as const;
export function Studio({ connected }: { connected: boolean }) {
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
    job?.attempts.find(
      (a) => a.status === "succeeded" && a.revision === job.revision,
    );
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
    setRecipe((current) => (current ? { ...current, ...values } : current));
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
                      setRecipe((current) =>
                        current
                          ? {
                              ...current,
                              subjects: current.subjects.map((s) =>
                                s.id === subject.id
                                  ? {
                                      ...s,
                                      references: [...s.references, a.id],
                                    }
                                  : s,
                              ),
                            }
                          : current,
                      );
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
                  !job.available_actions.edit ||
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
            disabled={
              unavailable ||
              !job.available_actions.export ||
              activeAttempt?.id !== job.preview_approval
            }
            onExport={(route, upscaler, quote, pilot) =>
              call("finalize", {
                revision: job.revision,
                attempt_id: activeAttempt?.id,
                route,
                upscaler,
                quote_id: quote?.id,
                operation_id: crypto.randomUUID(),
                pilot,
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
              <span className="step-number" aria-hidden="true">
                {i + 1}
              </span>
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
                  ? `${job.progress.stage} · ${job.progress.cached ? "cached" : job.progress.total ? Math.round(((job.progress.completed || 0) / job.progress.total) * 100) + "%" : "running"}`
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
