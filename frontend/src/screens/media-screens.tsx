import { useState } from "react";
import { Headphones, Image, Play, RefreshCw } from "lucide-react";
import { downloadUrl } from "@/lib/api";
import type { Workspace } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  AssetField,
  Confirm,
  Field,
  GroupDetails,
  GroupSelection,
  MediaLink,
  Panel,
} from "@/components/workflow";

export function TtsScreen({ w }: { w: Workspace }) {
  const groups = w.state?.groups ?? [];
  const selected = w.draft.selected.filter((id) =>
    groups.some((group) => group.group_id === id),
  );
  return (
    <div className="space-y-6">
      <GroupSelection workspace={w} />
      <Panel
        title="Âm thanh & thumbnail"
        description="Lập kế hoạch từ văn bản thực trước khi tạo âm thanh. Tiếp tục tự động dùng lại những chunk còn hợp lệ; nhóm lỗi không ngăn các nhóm tiếp theo."
      >
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={w.busy || !selected.length}
            onClick={() => void w.run("prepare", { group_ids: selected })}
          >
            <Headphones aria-hidden="true" />
            Lập kế hoạch TTS
          </Button>
          <Button
            variant="outline"
            disabled={w.busy || !selected.length}
            onClick={() => void w.run("tts", { group_ids: selected })}
          >
            <RefreshCw aria-hidden="true" />
            Tạo / tiếp tục TTS
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Giọng: {String(w.settings?.tts_voice ?? "Chưa tải thiết lập")} · đồng
          thời: {String(w.settings?.tts_max_concurrency ?? "—")}. Thiết lập được
          cố định khi bắt đầu tác vụ.
        </p>
        <AssetField
          label="Ảnh nguồn thumbnail"
          value={w.draft.thumbnail}
          onChange={(thumbnail) => w.setDraft({ thumbnail })}
          workspace={w}
        />
        <Button
          variant="outline"
          disabled={w.busy || !selected.length || !w.draft.thumbnail.trim()}
          onClick={() =>
            void w.run("thumbnail", {
              group_ids: selected,
              image_path: w.draft.thumbnail,
            })
          }
        >
          <Image aria-hidden="true" />
          Tạo thumbnail cho nhóm đã chọn
        </Button>
        <Confirm
          label="Ghép âm thanh thiếu chunk…"
          title="Chấp nhận âm thanh không đầy đủ?"
          description="Các chunk chưa thành công sẽ bị bỏ qua. Bản ghép được đánh dấu Partial và không được dùng để tạo video. Chỉ tiếp tục khi đã đọc danh sách lỗi bên dưới."
          disabled={w.busy || !selected.length}
          onConfirm={() =>
            void w.run("merge_partial", {
              group_ids: selected,
              allow_partial: true,
            })
          }
        />
      </Panel>
      {groups.map((group) => (
        <GroupDetails key={group.group_id} group={group}>
          <div className="grid gap-4 md:grid-cols-[14rem_1fr]">
            {group.state.thumbnail?.path ? (
              <a
                href={downloadUrl(group.state.thumbnail.path)}
                target="_blank"
                rel="noreferrer"
              >
                <img
                  className="aspect-video w-full rounded-md border object-contain"
                  src={downloadUrl(group.state.thumbnail.path)}
                  alt={`Thumbnail ${group.label}`}
                  loading="lazy"
                />
              </a>
            ) : (
              <p className="empty">Chưa tạo thumbnail</p>
            )}
            <div className="space-y-2">
              <p className="text-sm">
                Kế hoạch: {group.state.tts_plan?.chunks?.length ?? "Chưa lập"}{" "}
                chunk
              </p>
              <p className="text-sm">
                Thành công: {group.state.successful_orders?.length ?? 0} · lỗi:{" "}
                {group.state.failures?.length ?? 0}
              </p>
              {group.state.excluded_chunks?.length ? (
                <p className="warning">
                  Đã loại chunk: {group.state.excluded_chunks.join(", ")}
                </p>
              ) : null}
              <p className="break-anywhere text-xs text-muted-foreground">
                {group.output_dir}
              </p>
              <div className="flex flex-wrap gap-2">
                <MediaLink path={group.state.audiobook?.path} label="Tải MP3" />
                <MediaLink
                  path={group.state.thumbnail?.path}
                  label="Tải thumbnail"
                />
              </div>
            </div>
          </div>
          {group.state.last_error && (
            <p role="alert" className="error-box">
              {group.state.last_error}
            </p>
          )}
          {group.state.tts_plan && (
            <details>
              <summary className="cursor-pointer font-medium">
                Xem kế hoạch và văn bản từng chunk
              </summary>
              <div className="mt-3 space-y-3">
                {Array.isArray(group.state.tts_plan.warnings) && (
                  <ul className="warning">
                    {group.state.tts_plan.warnings.map((warning, index) => (
                      <li key={index}>{String(warning)}</li>
                    ))}
                  </ul>
                )}
                {group.state.tts_plan.chunks?.map((chunk) => (
                  <details key={chunk.order} className="rounded-md border p-3">
                    <summary className="cursor-pointer text-sm">
                      Chunk {chunk.order} · Chương {chunk.chapter ?? "—"} ·{" "}
                      {chunk.text.length} ký tự
                    </summary>
                    <pre className="text-preview mt-3">{chunk.text}</pre>
                  </details>
                ))}
              </div>
            </details>
          )}
          {group.state.failures?.map((failure) => {
            const key = `${group.group_id}:${failure.chunk_number}`;
            return (
              <div
                key={key}
                className="space-y-3 rounded-lg border border-destructive/30 p-4"
              >
                <h3 className="font-medium">
                  Chunk lỗi #{failure.chunk_number}
                </h3>
                <p className="text-sm text-destructive">
                  {failure.error_type}: {failure.error_message}
                </p>
                {failure.failed_part_text && (
                  <details>
                    <summary className="cursor-pointer text-sm">
                      Đoạn bị lỗi
                    </summary>
                    <pre className="text-preview">
                      {failure.failed_part_text}
                    </pre>
                  </details>
                )}
                <Field
                  label="Chỉnh văn bản chunk"
                  hint="Chỉ sửa văn bản hiệu dụng của chunk; bản thảo chuẩn không đổi. Sau khi lưu, chạy lại TTS để tái tạo chunk."
                >
                  {(id) => (
                    <Textarea
                      id={id}
                      value={w.draft.chunkEdits[key] ?? failure.original_text}
                      disabled={w.busy}
                      onChange={(event) =>
                        w.setDraft({
                          chunkEdits: {
                            ...w.draft.chunkEdits,
                            [key]: event.target.value,
                          },
                        })
                      }
                    />
                  )}
                </Field>
                <Button
                  variant="outline"
                  disabled={
                    w.busy ||
                    !(w.draft.chunkEdits[key] ?? failure.original_text).trim()
                  }
                  onClick={() =>
                    void w.run("edit_chunk", {
                      group_id: group.group_id,
                      order: failure.chunk_number,
                      text: w.draft.chunkEdits[key] ?? failure.original_text,
                    })
                  }
                >
                  Lưu chunk #{failure.chunk_number}
                </Button>
                <Button
                  variant="outline"
                  disabled={w.busy}
                  onClick={() =>
                    void w.run("tts", { group_ids: [group.group_id] })
                  }
                >
                  Tiếp tục nhóm này
                </Button>
              </div>
            );
          })}
        </GroupDetails>
      ))}
    </div>
  );
}
export function VideoScreen({ w }: { w: Workspace }) {
  const [previewGroup, setPreviewGroup] = useState("");
  const groups = w.state?.groups ?? [];
  const selected = w.draft.selected.filter((id) =>
    groups.some((group) => group.group_id === id),
  );
  const chosen = groups.some((group) => group.group_id === previewGroup)
    ? previewGroup
    : (selected[0] ?? "");
  const preview =
    w.jobs.find(
      (job) =>
        job.action === "preview" &&
        job.status === "completed" &&
        job.result?.path &&
        job.result?.group_id === chosen,
    );
  const picturesReady = Boolean(w.draft.cover.trim() && w.draft.qr.trim());
  return (
    <div className="space-y-6">
      <GroupSelection workspace={w} />
      <Panel
        title="Thiết kế trang video"
        description="Hai ảnh bắt buộc: bìa và QR. Xem trước được renderer thật tạo từ văn bản hiệu dụng, không phải ảnh minh họa giả."
      >
        <div className="grid gap-6 md:grid-cols-2">
          <AssetField
            label="Ảnh bìa trang video"
            value={w.draft.cover}
            onChange={(cover) => w.setDraft({ cover })}
            workspace={w}
          />
          <AssetField
            label="Ảnh QR"
            value={w.draft.qr}
            onChange={(qr) => w.setDraft({ qr })}
            workspace={w}
          />
        </div>
        <Field label="Nhóm dùng để xem trước">
          {(id) => (
            <select
              className="select"
              id={id}
              value={chosen}
              disabled={w.busy}
              onChange={(event) => setPreviewGroup(event.target.value)}
            >
              <option value="">Chọn nhóm</option>
              {groups.map((group) => (
                <option key={group.group_id} value={group.group_id}>
                  {group.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={w.busy || !chosen || !picturesReady}
            onClick={() =>
              void w.run("preview", {
                group_id: chosen,
                cover_image: w.draft.cover,
                qr_image: w.draft.qr,
              })
            }
          >
            <Image aria-hidden="true" />
            Tạo xem trước thực
          </Button>
          <Button
            disabled={w.busy || !selected.length || !picturesReady}
            onClick={() =>
              void w.run("video", {
                group_ids: selected,
                cover_image: w.draft.cover,
                qr_image: w.draft.qr,
              })
            }
          >
            <Play aria-hidden="true" />
            Tạo video đã chọn
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Máy chủ kiểm tra đầu ra TTS, thumbnail và nguồn trước khi chạy.
          Encoder khả dụng và kết quả xử lý xuất hiện trong nhật ký.
        </p>
        {typeof preview?.result?.path === "string" && (
          <figure className="space-y-2">
            <img
              className="mx-auto aspect-video w-full max-w-4xl rounded-lg border bg-muted object-contain"
              src={downloadUrl(preview.result.path)}
              alt="Trang video thực được renderer tạo"
            />
            <figcaption className="text-sm text-muted-foreground">
              Xem trước gần nhất ·{" "}
              {new Date(preview.created_at).toLocaleString("vi-VN")}. Tạo lại
              sau khi đổi ảnh hoặc văn bản.
            </figcaption>
            <MediaLink
              path={preview.result.path}
              label="Tải ảnh xem trước"
            />
          </figure>
        )}
      </Panel>
      {groups.map((group) => (
        <GroupDetails key={group.group_id} group={group}>
          <div className="flex flex-wrap gap-2">
            <MediaLink path={group.state.video?.path} label="Tải video" />
            <MediaLink
              path={group.state.audiobook?.path}
              label="Tải âm thanh"
            />
          </div>
          {group.state.video?.path && (
            <video
              controls
              preload="metadata"
              className="aspect-video w-full rounded-md bg-muted"
              src={downloadUrl(group.state.video.path)}
              aria-label={`Video ${group.label}`}
            />
          )}
          {group.state.last_error && (
            <p className="error-box">{group.state.last_error}</p>
          )}
          <p className="break-anywhere text-xs text-muted-foreground">
            {group.output_dir}
          </p>
        </GroupDetails>
      ))}
    </div>
  );
}
