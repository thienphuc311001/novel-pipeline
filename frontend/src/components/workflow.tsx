import { useId, type ReactNode } from "react";
import { Download, Upload } from "lucide-react";
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
}: {
  title: string;
  description?: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="min-w-0 rounded-xl border bg-card shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b p-5">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
          {description && (
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {aside}
      </header>
      <div className="space-y-5 p-5">{children}</div>
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
    <div className="min-w-0 space-y-2">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children(id)}
      {hint && <p className="text-sm text-muted-foreground">{hint}</p>}
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
  variant?: "outline" | "destructive" | "ghost";
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant={variant} disabled={disabled}>
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
  return (
    <div className="space-y-3">
      <Field
        label={label}
        hint="Nhập đường dẫn tuyệt đối trên máy chạy máy chủ, hoặc tải tệp lên."
      >
        {(id) => (
          <Input
            id={id}
            value={value}
            disabled={workspace.busy}
            onChange={(event) => onChange(event.target.value)}
          />
        )}
      </Field>
      <Field label={`Tải tệp: ${label}`}>
        {(id) => (
          <Input
            id={id}
            type="file"
            accept={accept}
            disabled={workspace.busy}
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              if (files.length)
                void workspace.perform(async () => {
                  const result = await api.upload("assets", files);
                  onChange(result.paths[0]);
                }, "Đã tải tệp lên.");
              event.target.value = "";
            }}
          />
        )}
      </Field>
    </div>
  );
}
export function GroupSelection({ workspace }: { workspace: Workspace }) {
  const groups = workspace.state?.groups ?? [];
  const selected = workspace.draft.selected;
  return (
    <Panel
      title="Hàng đợi nhóm chương"
      description="Chỉ những nhóm được chọn mới được xử lý. Lựa chọn dùng chung cho các bước âm thanh, video và xuất bản."
      aside={
        <span className="badge">
          {
            selected.filter((id) =>
              groups.some((group) => group.group_id === id),
            ).length
          }{" "}
          / {groups.length} đã chọn
        </span>
      }
    >
      {!groups.length ? (
        <p className="empty">
          Chưa có nhóm chương. Hoàn tất bước chuẩn hóa và tạo nhóm trước.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={workspace.busy}
              onClick={() =>
                workspace.setDraft({
                  selected: groups.map((group) => group.group_id),
                })
              }
            >
              Chọn tất cả
            </Button>
            <Button
              variant="ghost"
              disabled={workspace.busy}
              onClick={() => workspace.setDraft({ selected: [] })}
            >
              Bỏ chọn
            </Button>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {groups.map((group) => (
              <div
                key={group.group_id}
                className="min-w-0 rounded-lg border p-3"
              >
                <Toggle
                  label={group.label}
                  checked={selected.includes(group.group_id)}
                  disabled={workspace.busy}
                  onChange={(checked) =>
                    workspace.setDraft({
                      selected: checked
                        ? [...selected, group.group_id]
                        : selected.filter((id) => id !== group.group_id),
                    })
                  }
                />
                <p className="pl-9 text-sm text-muted-foreground">
                  {group.chapters.length} chương ·{" "}
                  {group.state.tts_status ?? "Chưa tạo âm thanh"}
                </p>
                <div className="mt-2 flex flex-wrap gap-2 pl-9">
                  {group.state.thumbnail && (
                    <span className="badge">Thumbnail</span>
                  )}
                  {group.state.audiobook && <span className="badge">MP3</span>}
                  {group.state.video && <span className="badge">Video</span>}
                  {group.state.youtube?.video_id && (
                    <span className="badge">YouTube</span>
                  )}
                </div>
                {group.state.last_error && (
                  <p className="mt-2 text-sm text-destructive">
                    {group.state.last_error}
                  </p>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </Panel>
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
export function GroupDetails({
  group,
  children,
}: {
  group: Group;
  children: ReactNode;
}) {
  return (
    <details className="rounded-lg border bg-card p-4">
      <summary className="cursor-pointer font-medium">
        {group.label}{" "}
        <span className="ml-2 text-sm font-normal text-muted-foreground">
          {group.state.tts_status ?? "Chưa chạy"}
        </span>
      </summary>
      <div className="mt-4 space-y-4">{children}</div>
    </details>
  );
}
export const UploadIcon = Upload;
