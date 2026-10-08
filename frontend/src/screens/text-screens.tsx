import { useEffect, useId, useState } from "react";
import { ArrowDown, ArrowUp, FileText, Upload, WandSparkles, X } from "lucide-react";
import { api } from "@/lib/api";
import type { Grouping, Workspace } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Confirm, Field, MediaLink, OutputDownloads, Toggle } from "@/components/workflow";
import { Chips, DoneCard, More, NextButton, RunButton, StepPage } from "@/components/wizard";

const fileName = (path: string) => path.split(/[\\/]/).pop() ?? path;

export function InputScreen({ w }: { w: Workspace }) {
  const [replacing, setReplacing] = useState(false);
  const dropId = useId();
  const paths = w.draft.paths.split("\n").map(path => path.trim()).filter(Boolean);
  const setPaths = (next: string[]) => w.setDraft({ paths: next.join("\n") });
  const move = (index: number, direction: number) => {
    const reordered = [...paths];
    [reordered[index], reordered[index + direction]] = [reordered[index + direction], reordered[index]];
    setPaths(reordered);
  };
  const start = () => {
    setReplacing(false);
    void w.runSteps([{ action: "import", options: { paths, sort_mode: w.draft.sort } }, { action: "normalize" }]);
  };
  const hasText = Boolean(w.state?.text);

  if (hasText && !replacing)
    return (
      <StepPage title="Bản thảo đã sẵn sàng" primary={<NextButton to="normalize" />}>
        <DoneCard
          title={w.state!.title || fileName(w.state!.source_path) || "Bản thảo"}
          detail={`${w.state!.text.length.toLocaleString("vi-VN")} ký tự · ${w.state!.sources.length} tệp nguồn`}
          action={<Button variant="outline" disabled={w.busy} onClick={() => setReplacing(true)}>Đổi bản thảo</Button>}
        />
        <More title="Xem nội dung gốc"><pre className="text-preview">{w.state!.original_text}</pre></More>
      </StepPage>
    );

  const primary = hasText ? (
    <Confirm variant="default" label="Thay bản thảo" title="Thay bản thảo hiện tại?" description="Nhóm, âm thanh và video của bản thảo cũ sẽ không còn dùng được. Phiên hiện tại được lưu trước." disabled={w.busy || !paths.length} onConfirm={start} />
  ) : (
    <RunButton w={w} label="Nhập bản thảo" disabled={!paths.length} onClick={start} />
  );
  return (
    <StepPage title="Chọn bản thảo" hint="Tệp TXT hoặc ZIP. Có thể chọn nhiều tệp." primary={primary} secondary={replacing ? <Button variant="ghost" onClick={() => setReplacing(false)}>Hủy</Button> : undefined}>
      <label htmlFor={dropId} className="dropzone">
        <Upload aria-hidden="true" />
        <strong>{paths.length ? "Thêm tệp" : "Bấm để chọn tệp"}</strong>
        <input id={dropId} type="file" multiple accept=".txt,.zip" disabled={w.busy} onChange={event => {
          const files = Array.from(event.target.files ?? []);
          if (files.length) void w.perform(async () => setPaths([...paths, ...(await api.upload("inputs", files)).paths]));
          event.target.value = "";
        }} />
      </label>
      {paths.length > 0 && (
        <ol className="file-list">
          {paths.map((path, index) => (
            <li key={`${index}-${path}`}>
              <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate" title={path}>{fileName(path)}</span>
              {paths.length > 1 && <>
                <Button variant="ghost" aria-label="Lên" disabled={w.busy || index === 0} onClick={() => move(index, -1)}><ArrowUp aria-hidden="true" /></Button>
                <Button variant="ghost" aria-label="Xuống" disabled={w.busy || index === paths.length - 1} onClick={() => move(index, 1)}><ArrowDown aria-hidden="true" /></Button>
              </>}
              <Button variant="ghost" aria-label="Bỏ tệp" disabled={w.busy} onClick={() => setPaths(paths.filter((_, i) => i !== index))}><X aria-hidden="true" /></Button>
            </li>
          ))}
        </ol>
      )}
      {paths.length > 1 && (
        <Chips label="Thứ tự ghép" value={w.draft.sort} disabled={w.busy} onChange={sort => w.setDraft({ sort })}
          options={[["natural", "Tự động (1, 2, 10)"], ["selection", "Như danh sách"], ["name", "Theo tên"]]} />
      )}
      <More title="Nhập bằng đường dẫn trên máy">
        <Field label="Mỗi dòng một đường dẫn" hint="TXT, ZIP hoặc thư mục.">{id => (
          <Textarea id={id} rows={3} value={w.draft.paths} disabled={w.busy} placeholder="/home/user/truyen/chuong-01.txt" onChange={event => w.setDraft({ paths: event.target.value })} />
        )}</Field>
      </More>
    </StepPage>
  );
}

const sizeOptions: [number, string][] = [[10, "10"], [20, "20"], [25, "25"], [50, "50"]];

export function NormalizeScreen({ w }: { w: Workspace }) {
  const [preview, setPreview] = useState<Grouping | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [numericConfirmed, setNumericConfirmed] = useState(false);
  const normalized = w.state?.normalized_text !== null && Boolean(w.state?.text);
  useEffect(() => {
    setNumericConfirmed(false);
    setPreviewError("");
    if (!normalized || w.busy || !Number.isInteger(w.draft.groupSize) || w.draft.groupSize < 1) return;
    let current = true;
    const timeout = window.setTimeout(() => {
      void api.grouping(w.draft.groupSize)
        .then(result => { if (current) setPreview(result); })
        .catch(cause => { if (current) setPreviewError(cause instanceof Error ? cause.message : String(cause)); });
    }, 300);
    return () => { current = false; window.clearTimeout(timeout); };
  }, [w.draft.groupSize, w.state?.text, normalized, w.busy]);

  if (!w.state?.text)
    return <StepPage title="Chưa có bản thảo" back="input" primary={<NextButton to="input" label="Chọn bản thảo" />}><p className="text-muted-foreground">Quay lại bước 1 để chọn tệp.</p></StepPage>;
  if (!normalized)
    return (
      <StepPage title="Chuẩn hóa bản thảo" hint="Sửa tiêu đề chương và khoảng trắng theo thiết lập." back="input"
        primary={<RunButton w={w} label="Chuẩn hóa" onClick={() => void w.run("normalize")} />}>
        <div className="hero-icon"><WandSparkles aria-hidden="true" /></div>
      </StepPage>
    );

  const groups = w.state.groups;
  const custom = !sizeOptions.some(([size]) => size === w.draft.groupSize);
  const ready = Boolean(preview && !preview.error && preview.headings.length && w.draft.title.trim() &&
    (!preview.requires_numeric_boundaries || (preview.numeric_available && numericConfirmed)));
  // Without a fresh preview (e.g. while a job runs) existing groups count as current.
  const unchanged = groups.length > 0 && (!preview || (w.draft.title.trim() === w.state.title &&
    preview.groups.length === groups.length && preview.groups.every((group, index) => group.range_label === groups[index].range_label)));
  const create = () => void w.run("group", {
    title: w.draft.title.trim(),
    size: w.draft.groupSize,
    method: preview?.requires_numeric_boundaries ? "numeric_boundaries" : "detected_chapters",
    confirmation_fingerprint: preview?.confirmation_fingerprint ?? "",
  });
  const primary = unchanged ? <NextButton to="tts" />
    : groups.length ? <Confirm variant="default" label={`Chia lại thành ${preview?.groups.length ?? "…"} nhóm`} title="Chia lại nhóm chương?" description="Nhóm mới thay thế nhóm hiện có. Tệp đã tạo không bị xóa khỏi ổ đĩa." disabled={w.busy || !ready} onConfirm={create} />
    : <RunButton w={w} label={`Tạo ${preview?.groups.length ?? "…"} nhóm`} disabled={!ready} onClick={create} />;

  return (
    <StepPage title="Chia nhóm chương" hint="Mỗi nhóm thành một audio và một video." back="input" primary={primary}>
      <Field label="Tên truyện">{id => <Input id={id} value={w.draft.title} disabled={w.busy} onChange={event => w.setDraft({ title: event.target.value })} />}</Field>
      <div className="size-row">
        <Chips label="Số chương mỗi nhóm" value={custom ? -1 : w.draft.groupSize} disabled={w.busy} onChange={size => w.setDraft({ groupSize: size === -1 ? 30 : size })}
          options={[...sizeOptions, [-1, "Khác"]]} />
        {custom && <Input aria-label="Số chương tùy chỉnh" className="w-24" type="number" min={1} step={1} value={w.draft.groupSize} disabled={w.busy}
          onChange={event => { const size = event.target.valueAsNumber; if (Number.isInteger(size) && size >= 1) w.setDraft({ groupSize: size }); }} />}
      </div>
      {(previewError || preview?.error) && <p role="alert" className="error-box">{previewError || preview?.error}</p>}
      {preview && !preview.error && (
        <div className="preview-summary">
          <p><strong>{preview.headings.length}</strong> chương <span aria-hidden="true">→</span> <strong>{preview.groups.length}</strong> nhóm</p>
          <div className="range-tags">{preview.groups.map((group, index) => <span key={index}>{group.range_label}</span>)}</div>
        </div>
      )}
      {unchanged && <DoneCard title={`Đã chia ${groups.length} nhóm`} detail="Đổi số chương ở trên nếu muốn chia lại." />}
      {preview?.requires_numeric_boundaries && (
        <div className="warning">
          <p>Số chương bị thiếu hoặc lặp. Nhóm sẽ chia theo số chương.</p>
          <Toggle label="Tôi đã kiểm tra, chia theo số chương" checked={numericConfirmed} onChange={setNumericConfirmed} disabled={w.busy || !preview.numeric_available} />
          {!preview.numeric_available && <p>Không đủ số chương hợp lệ — sửa văn bản trong Nâng cao.</p>}
        </div>
      )}
      {!!preview?.warnings.length && <ul className="warning space-y-1">{preview.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
      <More>
        <TextEditor w={w} />
        {preview && (
          <details className="sub-more"><summary>Danh sách tiêu đề chương ({preview.headings.length})</summary>
            <ul className="mt-2 max-h-72 space-y-1 overflow-y-auto text-sm">{preview.headings.map((heading, index) => <li key={index}><span className="text-muted-foreground">Dòng {heading.line}:</span> {heading.heading}</li>)}</ul>
          </details>
        )}
        <div className="space-y-3">
          <p className="field-label">Xuất văn bản</p>
          <div className="flex flex-wrap gap-2">{(["txt", "json", "zip"] as const).map(format => (
            <Button key={format} variant="outline" disabled={w.busy} onClick={() => void w.run("export", { format })}><FileText aria-hidden="true" />{format.toUpperCase()}</Button>
          ))}</div>
          <OutputDownloads files={w.state.outputs} />
        </div>
        {groups.length > 0 && (
          <div className="space-y-2">
            <p className="field-label">Nhóm hiện có</p>
            <ul className="divide-y rounded-lg border">{groups.map(group => (
              <li key={group.group_id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                <span className="flex-1 text-sm">{group.label}</span>
                <MediaLink path={group.txt_path} label="TXT" />
                <Confirm variant="ghost" label="Xóa" title={`Xóa ${group.label}?`} description="Nhóm bị loại khỏi phiên; tệp đã tạo vẫn còn trên ổ đĩa." disabled={w.busy} onConfirm={() => void w.run("delete_group", { group_id: group.group_id })} />
              </li>
            ))}</ul>
          </div>
        )}
      </More>
    </StepPage>
  );
}

function TextEditor({ w }: { w: Workspace }) {
  return (
    <div className="space-y-3">
      <Field label="Sửa văn bản" hint={`${w.draft.text.length.toLocaleString("vi-VN")} ký tự. Lưu sẽ làm nhóm và đầu ra cũ không còn hợp lệ.`}>{id => (
        <Textarea id={id} className="min-h-64 font-mono text-sm" value={w.draft.text} disabled={w.busy} onChange={event => w.setDraft({ text: event.target.value })} />
      )}</Field>
      <div className="flex flex-wrap gap-2">
        <Confirm label="Lưu văn bản" title="Áp dụng văn bản đã sửa?" description="Nhóm, âm thanh, video phụ thuộc văn bản cũ sẽ không còn hợp lệ." disabled={w.busy || w.draft.text === w.state?.text} onConfirm={() => void w.run("edit", { text: w.draft.text })} />
        <Confirm variant="ghost" label="Chuẩn hóa lại từ bản gốc" title="Chuẩn hóa lại?" description="Văn bản đã sửa và các nhóm phụ thuộc sẽ không còn hợp lệ." disabled={w.busy} onConfirm={() => void w.run("normalize")} />
      </div>
      {!!w.state?.diagnostics.length && <ul className="warning list-inside list-disc space-y-1">{w.state.diagnostics.map((item, index) => <li key={index}>{item.message}</li>)}</ul>}
    </div>
  );
}
