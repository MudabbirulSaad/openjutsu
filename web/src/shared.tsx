import { Upload } from "lucide-react";
import { useRef, type ReactNode } from "react";
import { Button } from "./ui";

export function Field({
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
export function UploadButton({
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
