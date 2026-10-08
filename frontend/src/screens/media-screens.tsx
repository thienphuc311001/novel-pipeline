import { useState } from "react";
import { Check, Copy, Image } from "lucide-react";
import { downloadUrl } from "@/lib/api";
import { groupStatus } from "@/lib/pipeline";
import type { Workspace } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Confirm, Field, GroupInspector, MediaLink } from "@/components/workflow";
import { DoneCard, GroupPicker, ImagePick, More, NextButton, PathInput, RunButton, StepPage, selectedIds } from "@/components/wizard";

/** First chapter of the manuscript, ready to copy into an image tool for the thumbnail. */
function FirstChapter({ w }: { w: Workspace }) {
  const [copied, setCopied] = useState(false);
  const text = w.state?.text ?? "";
  const span = w.state?.grouping.headings[0] ?? w.state?.groups[0]?.chapters[0];
  const chapter = span && typeof span.start === "number" && typeof span.end === "number" ? text.slice(span.start, span.end).trim() : "";
  if (!chapter) return null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(chapter);
    } catch {
      // Fallback for browsers that block the async clipboard API.
      const area = document.createElement("textarea");
      area.value = chapter;
      document.body.append(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="first-chapter">
      <div className="first-chapter-head">
        <span className="field-label">Chương đầu tiên <span className="text-xs font-normal text-muted-foreground">· {chapter.length.toLocaleString("vi-VN")} ký tự · dùng để tạo ảnh thumbnail</span></span>
        <Button variant={copied ? "default" : "outline"} onClick={() => void copy()}>
          {copied ? <><Check aria-hidden="true" />Đã copy</> : <><Copy aria-hidden="true" />Copy</>}
        </Button>
      </div>
      <pre className="first-chapter-text">{chapter}</pre>
    </div>
  );
}

function NoGroups() {
  return <StepPage title="Chưa có nhóm chương" back="normalize" primary={<NextButton to="normalize" label="Chia nhóm" />}><p className="text-muted-foreground">Chia bản thảo thành nhóm ở bước 2 trước.</p></StepPage>;
}

export function TtsScreen({ w }: { w: Workspace }) {
  const groups = w.state?.groups ?? [];
  if (!groups.length) return <NoGroups />;
  const selected = selectedIds(w);
  const chosen = groups.filter(group => selected.includes(group.group_id));
  // Done when every group is, or when every selected group is (the user can move on with a partial batch).
  const allDone = groups.every(group => groupStatus(w.state, group, "tts") === "done");
  const ready = allDone || (chosen.length > 0 && chosen.every(group => groupStatus(w.state, group, "tts") === "done"));
  const needThumbnail = chosen.some(group => !group.state.thumbnail?.path);
  const image = w.draft.thumbnail.trim();
  const blocked = !selected.length ? "Chọn ít nhất một nhóm" : needThumbnail && !image ? "Chọn ảnh thumbnail" : undefined;
  const start = () => void w.runSteps([
    ...(image ? [{ action: "thumbnail", options: { group_ids: selected, image_path: image } }] : []),
    { action: "tts", options: { group_ids: selected } },
  ]);
  const voice = String(w.settings?.tts_voice ?? "").replace(/^[a-z]{2}-[A-Z]{2}-|Neural$/g, "");
  return (
    <StepPage title="Tạo âm thanh" hint={voice ? `Giọng đọc: ${voice}` : undefined} back="normalize" note={ready ? undefined : blocked}
      primary={ready ? <NextButton to="video" /> : <RunButton w={w} label={`Tạo âm thanh · ${selected.length} nhóm`} disabled={Boolean(blocked)} onClick={start} />}
      secondary={ready ? <Button variant="outline" disabled={w.busy || Boolean(blocked)} onClick={start}>Chạy lại nhóm đã chọn</Button> : undefined}>
      {allDone && <DoneCard title="Tất cả nhóm đã có âm thanh" />}
      <GroupPicker w={w} stage="tts" />
      <FirstChapter w={w} />
      <ImagePick label="Ảnh thumbnail" w={w} value={w.draft.thumbnail} onChange={thumbnail => w.setDraft({ thumbnail })}
        optional={needThumbnail ? undefined : "Không bắt buộc — nhóm đã chọn đều có thumbnail"} />
      <More>
        <PathInput label="Đường dẫn ảnh thumbnail" value={w.draft.thumbnail} onChange={thumbnail => w.setDraft({ thumbnail })} w={w} />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={w.busy || !selected.length} onClick={() => void w.run("prepare", { group_ids: selected })}>Chỉ lập kế hoạch chunk</Button>
          <Button variant="outline" disabled={w.busy || !selected.length || !image} onClick={() => void w.run("thumbnail", { group_ids: selected, image_path: image })}><Image aria-hidden="true" />Chỉ tạo thumbnail</Button>
          <Confirm label="Ghép âm thanh thiếu chunk…" title="Chấp nhận âm thanh không đầy đủ?" description="Chunk lỗi bị bỏ qua. Bản ghép đánh dấu Partial và không dùng được để tạo video." disabled={w.busy || !selected.length} onConfirm={() => void w.run("merge_partial", { group_ids: selected, allow_partial: true })} />
        </div>
        <TtsInspector w={w} />
      </More>
    </StepPage>
  );
}

function TtsInspector({ w }: { w: Workspace }) {
  return (
    <GroupInspector workspace={w}>{group => (
      <>
        <div className="grid gap-4 sm:grid-cols-[12rem_1fr]">
          {group.state.thumbnail?.path
            ? <img className="aspect-video w-full rounded-md border object-contain" src={downloadUrl(group.state.thumbnail.path)} alt={`Thumbnail ${group.label}`} loading="lazy" />
            : <p className="empty">Chưa có thumbnail</p>}
          <div className="space-y-2 text-sm">
            <p>Chunk: {group.state.tts_plan?.chunks?.length ?? "chưa lập"} · thành công {group.state.successful_orders?.length ?? 0} · lỗi {group.state.failures?.length ?? 0}</p>
            {!!group.state.excluded_chunks?.length && <p className="warning">Đã loại chunk: {group.state.excluded_chunks.join(", ")}</p>}
            <div className="flex flex-wrap gap-2"><MediaLink path={group.state.audiobook?.path} label="MP3" /><MediaLink path={group.state.thumbnail?.path} label="Thumbnail" /></div>
          </div>
        </div>
        {group.state.last_error && <p role="alert" className="error-box">{group.state.last_error}</p>}
        {group.state.failures?.map(failure => {
          const key = `${group.group_id}:${failure.chunk_number}`;
          const text = w.draft.chunkEdits[key] ?? failure.original_text;
          return (
            <div key={key} className="space-y-3 rounded-lg border border-destructive/30 p-4">
              <p className="text-sm font-medium">Chunk #{failure.chunk_number} lỗi — <span className="text-destructive">{failure.error_type}: {failure.error_message}</span></p>
              <Field label="Sửa văn bản chunk" hint="Lưu rồi chạy lại để tạo lại chunk này.">{id => (
                <Textarea id={id} value={text} disabled={w.busy} onChange={event => w.setDraft({ chunkEdits: { ...w.draft.chunkEdits, [key]: event.target.value } })} />
              )}</Field>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" disabled={w.busy || !text.trim()} onClick={() => void w.run("edit_chunk", { group_id: group.group_id, order: failure.chunk_number, text })}>Lưu chunk</Button>
                <Button variant="outline" disabled={w.busy} onClick={() => void w.run("tts", { group_ids: [group.group_id] })}>Chạy lại nhóm này</Button>
              </div>
            </div>
          );
        })}
        {group.state.tts_plan?.chunks && (
          <details className="sub-more"><summary>Xem {group.state.tts_plan.chunks.length} chunk</summary>
            <div className="mt-2 space-y-2">{group.state.tts_plan.chunks.map(chunk => (
              <details key={chunk.order} className="rounded-md border p-2 text-sm"><summary>Chunk {chunk.order} · chương {chunk.chapter ?? "—"} · {chunk.text.length} ký tự</summary><pre className="text-preview mt-2">{chunk.text}</pre></details>
            ))}</div>
          </details>
        )}
      </>
    )}</GroupInspector>
  );
}

export function VideoScreen({ w }: { w: Workspace }) {
  const [previewGroup, setPreviewGroup] = useState("");
  const groups = w.state?.groups ?? [];
  if (!groups.length) return <NoGroups />;
  const selected = selectedIds(w);
  const chosen = groups.filter(group => selected.includes(group.group_id));
  const noAudio = chosen.filter(group => groupStatus(w.state, group, "tts") !== "done");
  const allDone = groups.every(group => groupStatus(w.state, group, "video") === "done");
  const ready = allDone || (chosen.length > 0 && chosen.every(group => groupStatus(w.state, group, "video") === "done"));
  const pictures = { cover_image: w.draft.cover, qr_image: w.draft.qr };
  const blocked = !selected.length ? "Chọn ít nhất một nhóm" : !w.draft.cover.trim() ? "Chọn ảnh bìa" : !w.draft.qr.trim() ? "Chọn ảnh QR" : noAudio.length ? "Có nhóm chưa có âm thanh" : undefined;
  const start = () => void w.run("video", { group_ids: selected, ...pictures });
  const previewId = groups.some(group => group.group_id === previewGroup) ? previewGroup : selected[0] ?? groups[0].group_id;
  const preview = w.jobs.find(job => job.action === "preview" && job.status === "completed" && job.result?.group_id === previewId && typeof job.result?.path === "string");
  return (
    <StepPage title="Dựng video" back="tts" note={ready ? undefined : blocked}
      primary={ready ? <NextButton to="youtube" /> : <RunButton w={w} label={`Tạo video · ${selected.length} nhóm`} disabled={Boolean(blocked)} onClick={start} />}
      secondary={ready ? <Button variant="outline" disabled={w.busy || Boolean(blocked)} onClick={start}>Tạo lại nhóm đã chọn</Button> : undefined}>
      {allDone && <DoneCard title="Tất cả nhóm đã có video" />}
      <GroupPicker w={w} stage="video" />
      {noAudio.length > 0 && (
        <div className="warning flex flex-wrap items-center justify-between gap-2">
          <span>{noAudio.length} nhóm đã chọn chưa có âm thanh.</span>
          <Button variant="outline" disabled={w.busy} onClick={() => w.setDraft({ selected: selected.filter(id => !noAudio.some(group => group.group_id === id)) })}>Bỏ các nhóm này</Button>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <ImagePick label="Ảnh bìa" w={w} value={w.draft.cover} onChange={cover => w.setDraft({ cover })} />
        <ImagePick label="Ảnh QR" w={w} value={w.draft.qr} onChange={qr => w.setDraft({ qr })} />
      </div>
      <More>
        <div className="grid gap-3 sm:grid-cols-2">
          <PathInput label="Đường dẫn ảnh bìa" value={w.draft.cover} onChange={cover => w.setDraft({ cover })} w={w} />
          <PathInput label="Đường dẫn ảnh QR" value={w.draft.qr} onChange={qr => w.setDraft({ qr })} w={w} />
        </div>
        <div className="space-y-3">
          <p className="field-label">Xem trước một trang video</p>
          <div className="flex flex-wrap gap-2">
            <select aria-label="Nhóm xem trước" className="select max-w-xs" value={previewId} disabled={w.busy} onChange={event => setPreviewGroup(event.target.value)}>
              {groups.map(group => <option key={group.group_id} value={group.group_id}>{group.label}</option>)}
            </select>
            <Button variant="outline" disabled={w.busy || !w.draft.cover.trim() || !w.draft.qr.trim()} onClick={() => void w.run("preview", { group_id: previewId, ...pictures })}><Image aria-hidden="true" />Xem trước</Button>
          </div>
          {typeof preview?.result?.path === "string" && <img className="aspect-video w-full rounded-lg border bg-muted object-contain" src={downloadUrl(preview.result.path)} alt="Xem trước trang video" />}
        </div>
        <GroupInspector workspace={w}>{group => (
          <>
            <div className="flex flex-wrap gap-2"><MediaLink path={group.state.video?.path} label="Tải video" /><MediaLink path={group.state.audiobook?.path} label="Tải âm thanh" /></div>
            {group.state.video?.path && <video controls preload="metadata" className="aspect-video w-full rounded-md bg-muted" src={downloadUrl(group.state.video.path)} aria-label={`Video ${group.label}`} />}
            {group.state.last_error && <p className="error-box">{group.state.last_error}</p>}
            <p className="break-anywhere text-xs text-muted-foreground">{group.output_dir}</p>
          </>
        )}</GroupInspector>
      </More>
    </StepPage>
  );
}
