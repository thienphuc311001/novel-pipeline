import { ExternalLink, Youtube } from "lucide-react";
import { api } from "@/lib/api";
import { groupStatus } from "@/lib/pipeline";
import type { Metadata, Workspace } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Confirm, Field, GroupInspector, Toggle } from "@/components/workflow";
import { Chips, DoneCard, GroupPicker, ImagePick, More, NextButton, RunButton, StepPage, selectedIds } from "@/components/wizard";

function localInput(iso: string | null) {
  const date = iso ? new Date(iso) : null;
  if (!date || Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function MetadataForm({ w }: { w: Workspace }) {
  const value = w.draft.metadata;
  const update = (patch: Partial<Metadata>) => w.setDraft({ metadata: { ...value, ...patch } });
  const history = Object.keys(w.state?.youtube_tags.history ?? {});
  return (
    <div className="space-y-4">
      <Field label="Tiêu đề chung" hint="Để trống để tự đặt theo tên truyện và nhóm.">{id => (
        <Input id={id} maxLength={100} value={value.title} disabled={w.busy} onChange={event => update({ title: event.target.value })} />
      )}</Field>
      <Field label="Mô tả">{id => (
        <Textarea id={id} rows={4} value={value.description} disabled={w.busy} onChange={event => update({ description: event.target.value })} />
      )}</Field>
      <Field label="Tag (cách nhau bằng dấu phẩy)">{id => (
        <Input id={id} value={w.draft.tagsText} disabled={w.busy} onChange={event => w.setDraft({
          tagsText: event.target.value,
          tagsEdited: true,
          metadata: { ...value, tags: event.target.value.split(",").map(tag => tag.trim()).filter(Boolean) },
        })} />
      )}</Field>
      {history.length > 0 && (
        <Field label="Lấy tag từ truyện khác">{id => (
          <select id={id} className="select" value="" disabled={w.busy} onChange={event => {
            const source = event.target.value;
            const tags = source ? (w.state?.youtube_tags.history[source] ?? []) : (w.state?.youtube_tags.current ?? []);
            w.setDraft({ tagsEdited: Boolean(source), tagsText: tags.join(", "), metadata: { ...value, tags } });
          }}>
            <option value="">— Truyện hiện tại —</option>
            {history.map(title => <option key={title} value={title}>{title}</option>)}
          </select>
        )}</Field>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Playlist ID" hint="Để trống nếu không dùng.">{id => (
          <Input id={id} value={value.playlist_id ?? ""} disabled={w.busy} onChange={event => update({ playlist_id: event.target.value || null })} />
        )}</Field>
        <Field label="Hẹn giờ đăng" hint="Chỉ khi để Riêng tư.">{id => (
          <Input id={id} type="datetime-local" value={localInput(value.publish_at)} disabled={w.busy}
            onChange={event => update({ publish_at: event.target.value ? new Date(event.target.value).toISOString() : null })} />
        )}</Field>
        <Field label="Danh mục (ID)">{id => (
          <Input id={id} inputMode="numeric" value={value.category_id} disabled={w.busy} onChange={event => update({ category_id: event.target.value })} />
        )}</Field>
      </div>
      <Toggle label="Dành cho trẻ em" checked={value.made_for_kids} disabled={w.busy} onChange={made_for_kids => update({ made_for_kids })} />
      <Toggle label="Có nội dung tạo bằng AI" checked={value.contains_synthetic_media} disabled={w.busy} onChange={contains_synthetic_media => update({ contains_synthetic_media })} />
    </div>
  );
}

export function YoutubeScreen({ w }: { w: Workspace }) {
  const groups = w.state?.groups ?? [];
  const selected = selectedIds(w);
  const chosen = groups.filter(group => selected.includes(group.group_id));
  const noVideo = chosen.filter(group => groupStatus(w.state, group, "video") !== "done");
  const allDone = groups.length > 0 && groups.every(group => groupStatus(w.state, group, "youtube") === "done");
  const ready = allDone || (chosen.length > 0 && chosen.every(group => groupStatus(w.state, group, "youtube") === "done"));
  const secrets = String(w.settings?.youtube_client_secrets_path ?? "");
  const lastAuth = w.jobs.find(job => ["youtube_connect", "youtube_disconnect"].includes(job.action) && job.status === "completed");
  const connected = lastAuth?.action === "youtube_connect";
  const { title, tags, ...shared } = w.draft.metadata;
  const uploadOptions = {
    group_ids: selected,
    metadata: { ...shared, ...(title.trim() ? { title } : {}), ...(w.draft.tagsEdited ? { tags } : {}) },
    titles: Object.fromEntries(Object.entries(w.draft.titles).filter(([, value]) => value.trim())),
    group_metadata: {},
  };
  const blocked = !groups.length ? "Chưa có nhóm" : !selected.length ? "Chọn ít nhất một nhóm" : noVideo.length ? "Có nhóm chưa có video" : undefined;

  return (
    <StepPage title="Đăng lên YouTube" back="video" note={ready ? undefined : blocked}
      primary={ready ? <NextButton to="sessions" label="Xong" /> : <RunButton w={w} label={`Tải lên · ${selected.length} video`} disabled={Boolean(blocked)} onClick={() => void w.run("upload", uploadOptions)} />}>
      {!secrets ? (
        <div className="connect-card">
          <Youtube aria-hidden="true" />
          <div className="min-w-0 flex-1"><p className="font-semibold">Kết nối YouTube</p><p className="text-sm text-muted-foreground">Chọn tệp OAuth client JSON (ứng dụng Desktop) từ Google Cloud.</p></div>
          <ImagePick label="Client JSON" optional="Bấm để chọn tệp .json" accept=".json,application/json" w={w} value="" onChange={path => void w.perform(async () => { await api.settingsSave({ youtube_client_secrets_path: path }); await w.refresh(); }, "Đã lưu client JSON.")} />
        </div>
      ) : (
        <div className="connect-card">
          <Youtube aria-hidden="true" />
          <p className="min-w-0 flex-1 font-semibold">{connected ? "Đã kết nối YouTube" : "YouTube"}</p>
          <Button variant={connected ? "ghost" : "outline"} disabled={w.busy} onClick={() => void w.run("youtube_connect")}>{connected ? "Kết nối lại" : "Kết nối"}</Button>
        </div>
      )}
      {allDone && <DoneCard title="Tất cả nhóm đã có video trên YouTube" />}
      {groups.length > 0 && <GroupPicker w={w} stage="youtube" />}
      {noVideo.length > 0 && (
        <div className="warning flex flex-wrap items-center justify-between gap-2">
          <span>{noVideo.length} nhóm đã chọn chưa có video.</span>
          <Button variant="outline" disabled={w.busy} onClick={() => w.setDraft({ selected: selected.filter(id => !noVideo.some(group => group.group_id === id)) })}>Bỏ các nhóm này</Button>
        </div>
      )}
      <Chips label="Hiển thị" value={w.draft.metadata.privacy} disabled={w.busy} onChange={privacy => w.setDraft({ metadata: { ...w.draft.metadata, privacy } })}
        options={[["private", "Riêng tư"], ["unlisted", "Không công khai"], ["public", "Công khai"]]} />
      <More title="Tùy chỉnh tiêu đề, mô tả, tag…"><MetadataForm w={w} /></More>
      <More>
        <div className="flex flex-wrap gap-2">
          <Confirm label="Tải lên bản mới (trùng)…" title="Tạo video YouTube mới?" description="Tạo upload mới dù nhóm đã có video. Có thể sinh video trùng và tốn hạn mức." disabled={w.busy || !selected.length} onConfirm={() => void w.run("upload", { ...uploadOptions, allow_duplicate: true })} />
          {secrets && <Confirm variant="ghost" label="Ngắt kết nối" title="Ngắt tài khoản YouTube?" description="Token bị xóa khỏi keyring. Video đã đăng không bị xóa." disabled={w.busy} onConfirm={() => void w.run("youtube_disconnect")} />}
        </div>
        <GroupInspector workspace={w}>{group => {
          const saved = group.state.youtube && Object.keys(group.state.youtube).length ? group.state.youtube : undefined;
          const metadata = saved?.updated_metadata ?? saved?.metadata;
          const override = w.draft.titles[group.group_id] ?? "";
          return (
            <>
              <Field label="Tiêu đề riêng cho nhóm này" hint="Để trống để dùng tiêu đề chung.">{id => (
                <Input id={id} maxLength={100} value={override} disabled={w.busy} onChange={event => w.setDraft({ titles: { ...w.draft.titles, [group.group_id]: event.target.value } })} />
              )}</Field>
              {group.state.last_error && <p role="alert" className="error-box">{group.state.last_error}</p>}
              {saved ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="badge">{saved.status ?? "Đã ghi nhận"}</span>
                    <span className="badge">Thumbnail {saved.thumbnail_uploaded ? "✓" : "—"}</span>
                    <span className="badge">Playlist {saved.playlist_added ? "✓" : "—"}</span>
                    {saved.video_id && <Button asChild variant="outline"><a href={`https://www.youtube.com/watch?v=${encodeURIComponent(saved.video_id)}`} target="_blank" rel="noreferrer"><ExternalLink aria-hidden="true" />Mở video</a></Button>}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" disabled={w.busy || !saved.video_id} onClick={() => void w.run("youtube_metadata", { group_id: group.group_id, metadata: { ...w.draft.metadata, title: override || w.draft.metadata.title } })}>Cập nhật thông tin</Button>
                    <Button variant="outline" disabled={w.busy || !saved.video_id} onClick={() => void w.run("youtube_retry_thumbnail", { group_id: group.group_id })}>Gửi lại thumbnail</Button>
                    <Button variant="outline" disabled={w.busy || !saved.video_id || !saved.metadata?.playlist_id} onClick={() => void w.run("youtube_retry_playlist", { group_id: group.group_id, playlist_id: saved.metadata?.playlist_id })}>Thêm lại playlist</Button>
                    {metadata && <Button variant="ghost" disabled={w.busy} onClick={() => w.setDraft({ metadata: { ...metadata }, tagsText: metadata.tags.join(", "), titles: { ...w.draft.titles, [group.group_id]: metadata.title } })}>Dùng lại thông tin đã đăng</Button>}
                  </div>
                </div>
              ) : <p className="text-sm text-muted-foreground">Nhóm chưa được tải lên.</p>}
            </>
          );
        }}</GroupInspector>
      </More>
    </StepPage>
  );
}
