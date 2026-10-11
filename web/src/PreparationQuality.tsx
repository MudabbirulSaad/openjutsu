import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, content, timecode, type Job } from "./api";
import { Button } from "./ui";

export type QualityFinding = {
  id: string;
  code: string;
  status: "PASS" | "WARNING" | "BLOCKED" | "REVIEWED";
  start: number;
  end: number;
  subject_id: number | null;
  message: string;
  confidence: number | null;
  measurements: Record<string, unknown>;
  reviewable: boolean;
  resolutions: string[];
  review?: { reason: string; resolution: string };
  evidence?: unknown[];
};
export type QualityReport = {
  report_id: string;
  status: string;
  counts: Record<string, number>;
  approval_ready: boolean;
  findings: QualityFinding[];
};

const labels: Record<string, string> = {
  inspected: "Inspected and acceptable",
  preserve_background: "Preserve as background",
  false_detection: "Detector evidence is incorrect",
  requires_replacement: "Needs replacement or correction",
};
export function orderedFindings(findings: QualityFinding[]) {
  const order = { BLOCKED: 0, WARNING: 1, REVIEWED: 2, PASS: 3 };
  return [...findings].sort(
    (a, b) => order[a.status] - order[b.status] || a.start - b.start,
  );
}

export function PreparationQuality({
  job,
  onInspect,
}: {
  job: Job;
  onInspect: (frame: number) => void;
}) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["quality", job.id, job.revision, job.artifacts.quality?.id],
    queryFn: () => api<QualityReport>(`/jobs/${job.id}/quality`),
    retry: false,
    enabled: !!job.artifacts.quality,
  });
  const [limit, setLimit] = useState(12);
  const review = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api(`/jobs/${job.id}/quality-review`, {
        revision: job.revision,
        ...body,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["quality", job.id] });
      client.invalidateQueries({ queryKey: ["job", job.id] });
    },
  });
  const report = query.data;
  return (
    <section className="preparation-quality" aria-labelledby="quality-heading">
      <h2 id="quality-heading">Preparation quality</h2>
      {!report ? (
        <p role="alert">
          {query.error?.message ||
            "A validated quality report is required. Prepare this revision before approval."}
        </p>
      ) : (
        <>
          <div
            tabIndex={-1}
            className="quality-summary"
            role={report.approval_ready ? "status" : "alert"}
          >
            <strong>{report.status}</strong>
            <p>
              {report.counts.BLOCKED} critical or required decisions ·{" "}
              {report.counts.WARNING} warnings · {report.counts.REVIEWED}{" "}
              reviewed
            </p>
            <p>
              {report.approval_ready
                ? "Checks and recorded reviews allow approval."
                : "Correct confirmed defects and record inspection reasons for uncertain findings before approval."}
            </p>
          </div>
          <a
            className="text-link"
            href={content(job.artifacts.quality.id)}
            target="_blank"
            rel="noreferrer"
          >
            Open immutable audit and frame measurements
          </a>
          {review.error && <p role="alert">{review.error.message}</p>}
          {orderedFindings(report.findings)
            .slice(0, limit)
            .map((f) => (
              <Finding
                key={f.id}
                finding={f}
                job={job}
                pending={review.isPending}
                onInspect={onInspect}
                onReview={(resolution, reason) =>
                  review.mutate({
                    report_id: report.report_id,
                    finding_id: f.id,
                    resolution,
                    reason,
                  })
                }
              />
            ))}
          {report.findings.length > limit && (
            <Button onClick={() => setLimit(limit + 20)}>
              Show more findings ({report.findings.length - limit})
            </Button>
          )}
        </>
      )}
    </section>
  );
}

function Finding({
  finding: f,
  job,
  pending,
  onInspect,
  onReview,
}: {
  finding: QualityFinding;
  job: Job;
  pending: boolean;
  onInspect: (frame: number) => void;
  onReview: (resolution: string, reason: string) => void;
}) {
  const [resolution, setResolution] = useState(f.resolutions[0] || "");
  const [reason, setReason] = useState("");
  return (
    <details className="quality-finding" open={f.status === "BLOCKED"}>
      <summary>
        <strong>{f.status}</strong> ·{" "}
        {f.subject_id ? `Subject ${f.subject_id}` : "Cast / background"} ·
        frames {f.start}–{f.end - 1}
      </summary>
      <p className="small">
        {timecode(f.start)}–{timecode(f.end - 1)} ·{" "}
        {f.code.replaceAll("_", " ")}
      </p>
      <p>{f.message}</p>
      <Button size="small" onClick={() => onInspect(f.start)}>
        Inspect frame {f.start} in viewer
      </Button>
      <div className="quality-comparisons">
        {["normalized", "mask", "conditioning"]
          .filter((k) => job.artifacts[k])
          .map((k) => (
            <a
              key={k}
              href={`/api/artifacts/${job.artifacts[k].id}/frames/${f.start}`}
              target="_blank"
              rel="noreferrer"
            >
              <img
                loading="lazy"
                alt={`${k} frame ${f.start}`}
                src={`/api/artifacts/${job.artifacts[k].id}/frames/${f.start}`}
              />
              <span>{k === "normalized" ? "Original" : k}</span>
            </a>
          ))}
      </div>
      <p className="small">
        {f.confidence == null
          ? "Detector confidence unavailable; inspect source evidence."
          : `Evidence confidence ${(100 * f.confidence).toFixed(1)}%`}
      </p>
      {Object.keys(f.measurements).length > 0 && (
        <pre className="quality-measurements">
          {JSON.stringify(f.measurements, null, 2)}
        </pre>
      )}
      {f.evidence && (
        <p className="small">
          {f.evidence.length} observations retained in the audit for this
          interval.
        </p>
      )}
      {f.review && (
        <p className="small">
          Recorded review: {labels[f.review.resolution]} — {f.review.reason}
        </p>
      )}
      {f.reviewable && f.status !== "REVIEWED" ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onReview(resolution, reason);
          }}
        >
          <label>
            Inspection decision
            <select
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
            >
              {f.resolutions.map((r) => (
                <option value={r} key={r}>
                  {labels[r]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Reason and evidence
            <textarea
              required
              minLength={8}
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Describe what you inspected and why this decision applies to every affected frame."
            />
          </label>
          <Button
            size="small"
            type="submit"
            disabled={pending || reason.trim().length < 8}
          >
            Record review
          </Button>
        </form>
      ) : (
        f.status === "BLOCKED" && (
          <p className="small">
            Correction required. This confirmed defect cannot be accepted by a
            review override.
          </p>
        )
      )}
    </details>
  );
}
