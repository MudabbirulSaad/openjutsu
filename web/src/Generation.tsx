import { Download, Sparkles } from "lucide-react";
import { useState } from "react";
import { usd, type Job, type Quote, type System } from "./api";
import { Button } from "./ui";

import { Field } from "./shared";
export function BudgetEditor({
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
export function Generation({
  job,
  quotes,
  disabled,
  onGenerate,
  finish,
  onFinish,
}: {
  job: Job;
  quotes: Quote[];
  disabled: boolean;
  onGenerate: (q: Quote, pilot: boolean) => void;
  finish: string;
  onFinish: (value: string) => void;
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
      <Field label="Finished output plan">
        <select value={finish} onChange={(e) => onFinish(e.target.value)}>
          <option value="upscale">1080p · local upscale</option>
          <option value="native">1080p · native continuation</option>
          <option value="original">Original preview resolution</option>
        </select>
      </Field>
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
          <span>
            {usd(quote.finished_estimate)}
            <small>finished API</small>
          </span>
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
          Preview {usd(q.estimate)} · reservation {usd(q.reserve / 1e6)} ·
          finished API estimate {usd(q.finished_estimate)}. Local time/energy
          and creative retries are additional. Native continuation needs a fresh
          quote and separate qualification.
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
export function Attempts({
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
      {[...job.attempts].reverse().map((a, i) => (
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
            {a.actual !== undefined && a.actual !== null
              ? ` · ${usd(a.actual / 1e6)}`
              : " · billing unsettled"}
          </p>
          {a.error && <p className="small error-text">{a.error}</p>}
          {a.status === "unknown_submission" && (
            <Reconciliation onSubmit={(body) => onReconcile(a.id, body)} />
          )}{" "}
          {["succeeded", "failed"].includes(a.status) &&
            !!a.remote_id &&
            !a.settled && (
              <Receipt
                onSubmit={(cost) =>
                  onReconcile(a.id, { actual_cost_usd: cost })
                }
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
export function ExportOptions({
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
  onExport: (
    route: string,
    upscaler: string,
    quote?: Quote,
    pilot?: boolean,
  ) => void;
}) {
  const [route, setRoute] = useState("upscale"),
    [upscaler, setUpscaler] = useState("seedvr2"),
    [pilot, setPilot] = useState(false);
  const q = native.find((q) => q.eligible);
  const blocked =
    route === "native"
      ? !q || (!q.qualified && !pilot)
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
      {route === "native" && q && !q.qualified && (
        <label className="check">
          <input
            type="checkbox"
            checked={pilot}
            onChange={(e) => setPilot(e.target.checked)}
          />
          Run a paid native-continuation pilot
        </label>
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
        onClick={() => onExport(route, upscaler, q, pilot)}
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
