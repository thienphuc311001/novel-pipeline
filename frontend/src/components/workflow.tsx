import { useId, useState, type ReactNode } from "react";
import { Download } from "lucide-react";
import { api, downloadUrl } from "@/lib/api";
import type { Group, OutputFile, Workspace } from "@/lib/types";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Checkbox } from "./ui/checkbox";
import {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogCancel,
  AlertDialogAction,
} from "./ui/alert-dialog";

export function Panel({
  title,
  description,
  children,
  aside,
  className = "",
}: {
  title: string;
  description?: string;
  children: ReactNode;
  aside?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`workflow-panel ${className}`}>
      <header className="panel-header">
        <div className="min-w-0">
          <h2>{title}</h2>
          {description && (
            <p className="panel-description">
              {description}
            </p>
          )}
        </div>
        {aside}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
      </label>
      {children(id)}
      {hint && <p className="field-hint">{hint}</p>}
    </div>
  );
}
export function Toggle({
  label,
  checked,
  onChange,
  disabled = false,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <label
      htmlFor={id}
      className="flex min-h-11 cursor-pointer items-center gap-3 rounded-md px-1 text-sm"
    >
      <Checkbox
        id={id}
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onChange(value === true)}
      />
      {label}
    </label>
  );
}
export function Confirm({
  label,
  title,
  description,
  onConfirm,
  disabled = false,
  variant = "outline",
}: {
  label: string;
  title: string;
  description: string;
  onConfirm: () => void;
  disabled?: boolean;
  variant?: "default" | "outline" | "destructive" | "ghost";
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant={variant} size={variant === "default" ? "lg" : "default"} disabled={disabled}>
          {label}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogTitle className="text-lg font-semibold">
          {title}
        </AlertDialogTitle>
        <AlertDialogDescription className="text-sm leading-relaxed text-muted-foreground">
          {description}
        </AlertDialogDescription>
        <div className="flex flex-wrap justify-end gap-2">
          <AlertDialogCancel>Hủy</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Xác nhận</AlertDialogAction>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}
export function AssetField({
  label,
  value,
  onChange,
  workspace,
  accept = "image/*",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  workspace: Workspace;
  accept?: string;
}) {
  const fileId = useId();
  return (
    <div className="space-y-3 rounded-lg border bg-muted/40 p-3">
      <label htmlFor={fileId} className="block text-xs font-semibold">{label}</label>
      {value && <p className="break-anywhere text-xs text-primary">{value.split(/[\\/]/).pop()}</p>}
      <Input
        id={fileId}
        type="file"
        accept={accept}
        disabled={workspace.busy}
        onChange={event => {
          const files = Array.from(event.target.files ?? []);
          if (files.length) void workspace.perform(async () => {
            const result = await api.upload("assets",files);
            onChange(result.paths[0]);
          },"Đã tải tệp lên.");
          event.target.value = "";
        }}
      />
      <details className="disclosure">
        <summary>Nhập đường dẫn tệp</summary>
        <div><Field label={`Đường dẫn: ${label}`} hint="Đường dẫn tuyệt đối đến tệp trên máy.">{id => <Input id={id} value={value} disabled={workspace.busy} onChange={event => onChange(event.target.value)} />}</Field></div>
      </details>
    </div>
  );
}

export function MediaLink({ path, label }: { path?: string; label: string }) {
  return path ? (
    <Button asChild variant="outline">
      <a href={downloadUrl(path)} download>
        <Download aria-hidden="true" />
        {label}
      </a>
    </Button>
  ) : null;
}
export function OutputDownloads({ files }: { files: OutputFile[] }) {
  return !files.length ? (
    <p className="empty">
      Chưa có tệp đầu ra. Tệp đã tạo sẽ xuất hiện tại đây.
    </p>
  ) : (
    <ul className="divide-y">
      {files.map((file) => (
        <li
          key={file.path}
          className="flex flex-wrap items-center justify-between gap-3 py-3"
        >
          <div className="min-w-0">
            <p className="font-medium">{file.name}</p>
            <p className="text-xs text-muted-foreground">
              {(file.size / 1024).toLocaleString("vi-VN", {
                maximumFractionDigits: 1,
              })}{" "}
              KB
            </p>
            <p className="break-anywhere text-xs text-muted-foreground">
              {file.path}
            </p>
          </div>
          <MediaLink path={file.path} label="Tải xuống" />
        </li>
      ))}
    </ul>
  );
}
export function GroupInspector({ workspace, children }: {
  workspace: Workspace;
  children: (group: Group) => ReactNode;
}) {
  const groups = workspace.state?.groups ?? [];
  const [inspected, setInspected] = useState("");
  const current = groups.find(group => group.group_id === inspected)
    ?? groups.find(group => group.state.last_error || group.state.failures?.length)
    ?? groups.find(group => workspace.draft.selected.includes(group.group_id))
    ?? groups[0];
  if (!current) return null;
  return (
    <div className="space-y-4">
      <Field label="Kiểm tra nhóm">{id => (
        <select id={id} className="select" value={current.group_id} onChange={event => setInspected(event.target.value)}>
          {groups.map(group => <option key={group.group_id} value={group.group_id}>{group.label}{group.state.last_error || group.state.failures?.length ? " · có lỗi" : ""}</option>)}
        </select>
      )}</Field>
      <div key={current.group_id} className="space-y-4">{children(current)}</div>
    </div>
  );
}
