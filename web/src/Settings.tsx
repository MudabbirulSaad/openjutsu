import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type System } from "./api";
import { Button } from "./ui";

import { Field } from "./shared";
export function Settings() {
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
