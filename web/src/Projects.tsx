import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Film, Layers } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  api,
  defaultRecipe,
  timecode,
  upload,
  type Job,
  type Recipe,
} from "./api";
import { DepthContour } from "./DepthContour";

import { UploadButton } from "./shared";
export function Projects({ recipes = false }: { recipes?: boolean }) {
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
