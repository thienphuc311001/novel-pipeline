import { ExternalLink, Upload, Youtube } from "lucide-react";
import type { Metadata, Workspace } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Confirm,
  Field,
  GroupDetails,
  GroupSelection,
  Panel,
  Toggle,
} from "@/components/workflow";

function MetadataForm({ w }: { w: Workspace }) {
  const value = w.draft.metadata;
  const update = (patch: Partial<Metadata>) =>
    w.setDraft({ metadata: { ...value, ...patch } });
  return (
    <div className="space-y-4">
      <Field
        label="Tiêu đề chung"
        hint="Để trống để tự tạo tiêu đề riêng từ tên truyện và nhóm. Tối đa 100 ký tự."
      >
        {(id) => (
          <Input
            id={id}
            maxLength={100}
            value={value.title}
            disabled={w.busy}
            onChange={(event) => update({ title: event.target.value })}
          />
        )}
      </Field>
      <Field
        label="Mô tả"
        hint="Tối đa 5.000 byte UTF-8; máy chủ kiểm tra trước khi gửi."
      >
        {(id) => (
          <Textarea
            id={id}
            rows={5}
            value={value.description}
            disabled={w.busy}
            onChange={(event) => update({ description: event.target.value })}
          />
        )}
      </Field>
      <Field
        label="Bộ tag từ truyện đã tải"
        hint="Tự dùng tag của truyện hiện tại; chọn truyện khác chỉ đổi tag, không đổi tiêu đề."
      >
        {(id) => (
          <select
            id={id}
            className="native-select"
            value={w.draft.tagsEdited ? "manual" : ""}
            disabled={w.busy}
            onChange={(event) => {
              const source = event.target.value;
              const tags = source
                ? (w.state?.youtube_tags.history[source.slice(8)] ?? [])
                : (w.state?.youtube_tags.current ?? []);
              w.setDraft({
                tagsEdited: Boolean(source),
                tagsText: tags.join(", "),
                metadata: { ...value, tags },
              });
            }}
          >
            <option value="">Truyện hiện tại (tự động)</option>
            <option value="manual" disabled>
              Tag tùy chỉnh / đã chọn
            </option>
            {Object.keys(w.state?.youtube_tags.history ?? {}).map((title) => (
              <option key={title} value={`history:${title}`}>
                {title}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field label="Thẻ (phân cách bằng dấu phẩy)">
        {(id) => (
          <Input
            id={id}
            value={w.draft.tagsText}
            disabled={w.busy}
            onChange={(event) =>
              w.setDraft({
                tagsText: event.target.value,
                tagsEdited: true,
                metadata: {
                  ...value,
                  tags: event.target.value
                    .split(",")
                    .map((tag) => tag.trim())
                    .filter(Boolean),
                },
              })
            }
          />
        )}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Danh mục YouTube (ID)">
          {(id) => (
            <Input
              id={id}
              inputMode="numeric"
              value={value.category_id}
              disabled={w.busy}
              onChange={(event) => update({ category_id: event.target.value })}
            />
          )}
        </Field>
        <Field label="Quyền riêng tư">
          {(id) => (
            <select
              id={id}
              className="select"
              value={value.privacy}
              disabled={w.busy}
              onChange={(event) => {
                const privacy = event.target.value;
                if (
                  privacy === "private" ||
                  privacy === "unlisted" ||
                  privacy === "public"
                )
                  update({ privacy });
              }}
            >
              <option value="private">Riêng tư</option>
              <option value="unlisted">Không công khai</option>
              <option value="public">Công khai</option>
            </select>
          )}
        </Field>
        <Field
          label="Playlist ID"
          hint="Để trống nếu không thêm vào danh sách phát."
        >
          {(id) => (
            <Input
              id={id}
              value={value.playlist_id ?? ""}
              disabled={w.busy}
              onChange={(event) =>
                update({ playlist_id: event.target.value || null })
              }
            />
          )}
        </Field>
        <Field
          label="Lịch xuất bản (ISO 8601)"
          hint="Ví dụ 2026-12-01T19:00:00+07:00. Phải ở tương lai và quyền riêng tư là Riêng tư."
        >
          {(id) => (
            <Input
              id={id}
              value={value.publish_at ?? ""}
              disabled={w.busy}
              onChange={(event) =>
                update({ publish_at: event.target.value || null })
              }
            />
          )}
        </Field>
      </div>
      <Toggle
        label="Nội dung dành cho trẻ em"
        checked={value.made_for_kids}
        disabled={w.busy}
        onChange={(made_for_kids) => update({ made_for_kids })}
      />
      <Toggle
        label="Có nội dung tổng hợp / sử dụng AI"
        checked={value.contains_synthetic_media}
        disabled={w.busy}
        onChange={(contains_synthetic_media) =>
          update({ contains_synthetic_media })
        }
      />
    </div>
  );
}
export function YoutubeScreen({ w }: { w: Workspace }) {
  const groups = w.state?.groups ?? [];
  const selected = w.draft.selected.filter((id) =>
    groups.some((group) => group.group_id === id),
  );
  const { title, tags, ...sharedMetadata } = w.draft.metadata;
  const uploadOptions = {
    group_ids: selected,
    metadata: {
      ...sharedMetadata,
      ...(title.trim() ? { title } : {}),
      ...(w.draft.tagsEdited ? { tags } : {}),
    },
    titles: Object.fromEntries(
      Object.entries(w.draft.titles).filter(([, value]) => value.trim()),
    ),
    group_metadata: {},
  };
  const authJob = w.jobs.find(
    (job) =>
      ["youtube_connect", "youtube_disconnect"].includes(job.action) &&
      job.status === "completed",
  );
  return (
    <div className="space-y-6">
      <Panel
        title="Kết nối YouTube"
        description="OAuth mở trình duyệt hệ thống trên máy chạy backend. Token được giữ trong keyring hệ điều hành, không gửi đến giao diện."
      >
        <p className="break-anywhere text-sm">
          OAuth client JSON:{" "}
          {String(
            w.settings?.youtube_client_secrets_path ||
              "Chưa thiết lập — mở Thiết lập để tải JSON hoặc nhập đường dẫn.",
          )}
        </p>
        {authJob && (
          <p className="text-sm">
            Tác vụ xác thực gần nhất:{" "}
            {authJob.action === "youtube_connect"
              ? "Đã kết nối"
              : "Đã ngắt kết nối"}{" "}
            · {new Date(authJob.created_at).toLocaleString("vi-VN")}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={w.busy || !w.settings?.youtube_client_secrets_path}
            onClick={() => void w.run("youtube_connect")}
          >
            <Youtube aria-hidden="true" />
            Kết nối / xác thực
          </Button>
          <Confirm
            label="Ngắt kết nối"
            title="Ngắt tài khoản YouTube?"
            description="Token xác thực sẽ bị xóa khỏi keyring. Các video đã tải lên không bị xóa."
            disabled={w.busy}
            onConfirm={() => void w.run("youtube_disconnect")}
          />
          <Button asChild variant="outline">
            <a href="#settings">Thiết lập OAuth</a>
          </Button>
        </div>
      </Panel>
      <GroupSelection workspace={w} />
      <Panel
        title="Thông tin xuất bản chung"
        description="Áp dụng cho các nhóm đã chọn chưa có phiên upload. Resume dùng metadata đã lưu để tránh thay đổi phiên upload đang dở."
      >
        <MetadataForm w={w} />
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={w.busy || !selected.length}
            onClick={() => void w.run("upload", uploadOptions)}
          >
            <Upload aria-hidden="true" />
            Tải lên / tiếp tục nhóm đã chọn
          </Button>
          <Confirm
            label="Tải lên bản mới…"
            title="Tạo video YouTube trùng mới?"
            description="Thao tác này cố ý tạo một upload mới dù nhóm đã có video hoặc phiên upload. Có thể sinh video trùng và sử dụng hạn mức YouTube. Metadata hiện tại sẽ được dùng."
            disabled={w.busy || !selected.length}
            onConfirm={() =>
              void w.run("upload", { ...uploadOptions, allow_duplicate: true })
            }
          />
        </div>
      </Panel>
      {groups.map((group) => {
        const recorded = group.state.youtube;
        const saved =
          recorded && Object.keys(recorded).length ? recorded : undefined;
        const metadata = saved?.updated_metadata ?? saved?.metadata;
        const override = w.draft.titles[group.group_id] ?? "";
        return (
          <GroupDetails key={group.group_id} group={group}>
            <Field
              label={`Tiêu đề riêng: ${group.label}`}
              hint="Để trống để dùng tiêu đề chung; máy chủ áp dụng quy tắc tiêu đề nhóm."
            >
              {(id) => (
                <Input
                  id={id}
                  maxLength={100}
                  value={override}
                  disabled={w.busy}
                  onChange={(event) =>
                    w.setDraft({
                      titles: {
                        ...w.draft.titles,
                        [group.group_id]: event.target.value,
                      },
                    })
                  }
                />
              )}
            </Field>
            {saved ? (
              <>
                <p className="text-sm">
                  Upload: <strong>{saved.status ?? "Đã ghi nhận"}</strong>
                </p>
                {saved.video_id && (
                  <Button asChild variant="outline">
                    <a
                      href={`https://www.youtube.com/watch?v=${encodeURIComponent(saved.video_id)}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <ExternalLink aria-hidden="true" />
                      Mở video trên YouTube
                    </a>
                  </Button>
                )}
                <div className="flex flex-wrap gap-2">
                  <span className="badge">
                    Thumbnail:{" "}
                    {saved.thumbnail_uploaded ? "đã gửi" : "chưa hoàn tất"}
                  </span>
                  <span className="badge">
                    Playlist:{" "}
                    {saved.playlist_added ? "đã thêm" : "chưa hoàn tất"}
                  </span>
                </div>
                {metadata && (
                  <>
                    <details>
                      <summary className="cursor-pointer font-medium">
                        Metadata đã lưu / phục hồi
                      </summary>
                      <pre className="text-preview mt-3">
                        {JSON.stringify(metadata, null, 2)}
                      </pre>
                    </details>
                    <Button
                      variant="outline"
                      disabled={w.busy}
                      onClick={() =>
                        w.setDraft({
                          metadata: { ...metadata },
                          tagsText: metadata.tags.join(", "),
                          titles: {
                            ...w.draft.titles,
                            [group.group_id]: metadata.title,
                          },
                        })
                      }
                    >
                      Khôi phục metadata vào biểu mẫu
                    </Button>
                  </>
                )}
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    disabled={w.busy || !saved.video_id}
                    onClick={() =>
                      void w.run("youtube_metadata", {
                        group_id: group.group_id,
                        metadata: {
                          ...w.draft.metadata,
                          title: override || w.draft.metadata.title,
                        },
                      })
                    }
                  >
                    Cập nhật metadata video này
                  </Button>
                  <Button
                    variant="outline"
                    disabled={w.busy || !saved.video_id}
                    onClick={() =>
                      void w.run("youtube_retry_thumbnail", {
                        group_id: group.group_id,
                      })
                    }
                  >
                    Gửi lại thumbnail
                  </Button>
                  <Button
                    variant="outline"
                    disabled={
                      w.busy || !saved.video_id || !saved.metadata?.playlist_id
                    }
                    onClick={() =>
                      void w.run("youtube_retry_playlist", {
                        group_id: group.group_id,
                        playlist_id: saved.metadata?.playlist_id,
                      })
                    }
                  >
                    Thêm lại playlist đã lưu
                  </Button>
                </div>
                <p className="text-sm text-muted-foreground">
                  Playlist recovery chỉ dùng ID đã lưu:{" "}
                  {saved.metadata?.playlist_id ?? "Không có"}. Đổi playlist
                  không thuộc thao tác phục hồi.
                </p>
                <details>
                  <summary className="cursor-pointer text-sm">
                    Chi tiết trạng thái phục hồi
                  </summary>
                  <pre className="text-preview mt-3">
                    {JSON.stringify(saved, null, 2)}
                  </pre>
                </details>
              </>
            ) : (
              <p className="empty">
                Nhóm chưa có phiên upload. Tạo video và thumbnail trước khi xuất
                bản.
              </p>
            )}
            {group.state.last_error && (
              <p role="alert" className="error-box">
                {group.state.last_error}
              </p>
            )}
          </GroupDetails>
        );
      })}
    </div>
  );
}
