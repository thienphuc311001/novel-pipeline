import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { AlertCircle, ArrowLeft, ArrowRight, Check, ChevronDown, ImagePlus, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";
import { groupStatus, type GroupStatus, type MediaStage } from "@/lib/pipeline";
import type { Screen, Workspace } from "@/lib/types";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

/** One wizard step: short title, the few choices, and a single primary action at the bottom. */
export function StepPage({ title, hint, back, primary, secondary, note, children }: {
  title: string;
  hint?: string;
  back?: Screen;
  primary?: ReactNode;
  secondary?: ReactNode;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section className="step-card">
      <header className="step-head">
        <h1>{title}</h1>
        {hint && <p>{hint}</p>}
      </header>
      <div className="step-body">{children}</div>
      <footer className="step-foot">
        {back ? <Button asChild variant="ghost"><a href={`#${back}`}><ArrowLeft aria-hidden="true" />Quay lại</a></Button> : <span />}
        <div className="step-foot-actions">
          {note && <span className="step-note">{note}</span>}
          {secondary}
          {primary}
        </div>
      </footer>
    </section>
  );
}

export function NextButton({ to, label = "Tiếp tục" }: { to: Screen; label?: string }) {
  return <Button asChild size="lg"><a href={`#${to}`}>{label}<ArrowRight aria-hidden="true" /></a></Button>;
}

export function RunButton({ w, label, disabled, onClick }: { w: Workspace; label: string; disabled?: boolean; onClick: () => void }) {
  const running = w.jobs.some(job => ["queued", "running", "stopping"].includes(job.status));
  return (
    <Button size="lg" disabled={w.busy || disabled} onClick={onClick}>
      {running ? <><Loader2 className="animate-spin" aria-hidden="true" />Đang chạy…</> : <>{label}<ArrowRight aria-hidden="true" /></>}
    </Button>
  );
}

export function Chips<T extends string | number>({ label, value, options, onChange, disabled }: {
  label: string;
  value: T;
  options: [T, string][];
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="chips-field" role="radiogroup" aria-label={label}>
      <span className="field-label">{label}</span>
      <div className="chips">
        {options.map(([option, text]) => (
          <button key={String(option)} type="button" role="radio" aria-checked={option === value} className="chip" disabled={disabled} onClick={() => onChange(option)}>
            {option === value && <Check className="size-3.5" aria-hidden="true" />}{text}
          </button>
        ))}
      </div>
    </div>
  );
}

export function More({ title = "Tùy chọn nâng cao", children }: { title?: string; children: ReactNode }) {
  return (
    <details className="more">
      <summary>{title}<ChevronDown className="size-4" aria-hidden="true" /></summary>
      <div className="more-body">{children}</div>
    </details>
  );
}

export function DoneCard({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="done-card">
      <span className="done-icon"><Check className="size-5" aria-hidden="true" /></span>
      <div className="min-w-0 flex-1"><p className="font-semibold">{title}</p>{detail && <p className="text-sm text-muted-foreground">{detail}</p>}</div>
      {action}
    </div>
  );
}

const fileName = (path: string) => path.split(/[\\/]/).pop() ?? path;

/** Compact image chooser: click to upload, or clear. Absolute paths stay available in More. */
export function ImagePick({ label, value, onChange, w, accept = "image/*", optional }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  w: Workspace;
  accept?: string;
  optional?: string;
}) {
  const id = useId();
  return (
    <div className={`image-pick ${value ? "has-value" : ""}`}>
      <label htmlFor={id}>
        {value ? <Check className="size-5" aria-hidden="true" /> : <ImagePlus className="size-5" aria-hidden="true" />}
        <span className="min-w-0">
          <strong>{label}</strong>
          <small>{value ? fileName(value) : optional ?? "Bấm để chọn ảnh"}</small>
        </span>
        <input id={id} type="file" accept={accept} disabled={w.busy} onChange={event => {
          const files = Array.from(event.target.files ?? []);
          if (files.length) void w.perform(async () => onChange((await api.upload("assets", files)).paths[0]));
          event.target.value = "";
        }} />
      </label>
      {value && <button type="button" className="image-clear" aria-label={`Bỏ ${label}`} disabled={w.busy} onClick={() => onChange("")}><X className="size-4" aria-hidden="true" /></button>}
    </div>
  );
}

export function PathInput({ label, value, onChange, w }: { label: string; value: string; onChange: (value: string) => void; w: Workspace }) {
  const id = useId();
  return <div className="field"><label htmlFor={id}>{label}</label><Input id={id} value={value} disabled={w.busy} placeholder="/đường/dẫn/tuyệt/đối" onChange={event => onChange(event.target.value)} /></div>;
}

const statusIcon: Record<GroupStatus, ReactNode> = {
  done: <Check className="size-3.5" aria-label="Đã xong" />,
  error: <AlertCircle className="size-3.5" aria-label="Lỗi" />,
  todo: null,
};

/** Tap-to-select chapter groups; the selection is shared across audio, video and YouTube. */
export function GroupPicker({ w, stage }: { w: Workspace; stage: MediaStage }) {
  const groups = w.state?.groups ?? [];
  const selected = w.draft.selected;
  const [query, setQuery] = useState("");
  const status = (id: string) => groupStatus(w.state, groups.find(group => group.group_id === id)!, stage);
  const pending = groups.filter(group => groupStatus(w.state, group, stage) !== "done").map(group => group.group_id);
  const count = groups.filter(group => selected.includes(group.group_id)).length;
  // First visit with nothing selected: preselect the groups this stage still has to do.
  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current || !groups.length) return;
    seeded.current = true;
    if (!count && pending.length) w.setDraft({ selected: pending });
  }, [groups.length, count, pending, w]);
  const search = query.trim().toLocaleLowerCase("vi-VN");
  const visible = search ? groups.filter(group => `${group.label} ${group.range_label}`.toLocaleLowerCase("vi-VN").includes(search)) : groups;
  const toggle = (id: string) => w.setDraft({ selected: selected.includes(id) ? selected.filter(value => value !== id) : [...selected, id] });
  return (
    <div className="picker">
      <div className="picker-head">
        <span className="field-label">Chọn nhóm <span className="picker-count">{count}/{groups.length}</span></span>
        <div className="picker-quick">
          <button type="button" disabled={w.busy} onClick={() => w.setDraft({ selected: groups.map(group => group.group_id) })}>Tất cả</button>
          <button type="button" disabled={w.busy || !pending.length} onClick={() => w.setDraft({ selected: pending })}>Chưa xong ({pending.length})</button>
          <button type="button" disabled={w.busy || !count} onClick={() => w.setDraft({ selected: [] })}>Bỏ chọn</button>
        </div>
      </div>
      {groups.length > 24 && <Input aria-label="Tìm nhóm" placeholder="Tìm nhóm…" value={query} onChange={event => setQuery(event.target.value)} />}
      <div className="picker-grid">
        {visible.map(group => {
          const state = status(group.group_id);
          const on = selected.includes(group.group_id);
          return (
            <button key={group.group_id} type="button" aria-pressed={on} disabled={w.busy} className={`pick is-${state}`} title={group.state.last_error} onClick={() => toggle(group.group_id)}>
              <span className="pick-box">{on && <Check className="size-3.5" aria-hidden="true" />}</span>
              <span className="pick-label">{group.range_label || group.label}</span>
              {statusIcon[state]}
            </button>
          );
        })}
      </div>
      <p className="picker-legend"><span className="is-done"><Check className="size-3" aria-hidden="true" />đã xong</span><span className="is-error"><AlertCircle className="size-3" aria-hidden="true" />lỗi</span></p>
    </div>
  );
}

/** Selected group ids that still exist in the current workspace. */
export function selectedIds(w: Workspace) {
  const groups = w.state?.groups ?? [];
  return w.draft.selected.filter(id => groups.some(group => group.group_id === id));
}
