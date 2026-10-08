import { useEffect, useRef, useState } from "react";
import { Terminal } from "lucide-react";
import { api } from "@/lib/api";
import type { LogLine, Workspace } from "@/lib/types";
import { Button } from "./ui/button";
import { Confirm, Field, Panel, Toggle } from "./workflow";

export const actionLabels: Record<string, string> = {
  import: "Nhập bản thảo",
  normalize: "Chuẩn hóa",
  edit: "Lưu văn bản",
  group: "Nhóm chương",
  prepare: "Lập kế hoạch TTS",
  thumbnail: "Tạo thumbnail",
  tts: "Tạo âm thanh",
  merge_partial: "Ghép âm thanh thiếu chunk",
  edit_chunk: "Sửa chunk",
  delete_group: "Xóa nhóm",
  video: "Tạo video",
  preview: "Xem trước video",
  export: "Xuất tệp",
  youtube_connect: "Kết nối YouTube",
  youtube_disconnect: "Ngắt YouTube",
  upload: "Tải lên YouTube",
  youtube_metadata: "Cập nhật metadata",
  youtube_retry_thumbnail: "Gửi lại thumbnail",
  youtube_retry_playlist: "Phục hồi playlist",
};
export const statusLabels: Record<string, string> = {
  queued: "Đang chờ",
  running: "Đang chạy",
  stopping: "Đang dừng an toàn",
  completed: "Hoàn tất",
  failed: "Thất bại / chưa đầy đủ",
  cancelled: "Đã hủy",
};
export function JobPanel({ w }: { w: Workspace }) {
  const [selected, setSelected] = useState("");
  const [lines, setLines] = useState<LogLine[]>([]);
  const [logError, setLogError] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const logViewport = useRef<HTMLDivElement>(null);
  const active = w.jobs.find((job) =>
    ["queued", "running", "stopping"].includes(job.status),
  );
  const current =
    w.jobs.find((job) => job.id === selected) ?? active ?? w.jobs[0];
  const jobId = current?.id;
  const jobStatus = current?.status;
  useEffect(() => {
    setLines([]);
    setLogError("");
    if (!jobId) return;
    let mounted = true;
    let after = 0;
    let timer: number | undefined;
    const load = async () => {
      try {
        const next = await api.logs(jobId, after);
        if (mounted) {
          if (next.length) {
            after = next[next.length - 1].sequence;
            setLines((old) =>
              [...old, ...next].slice(
                -Number(w.settings?.max_log_lines ?? 2000),
              ),
            );
          }
          setLogError("");
        }
      } catch (cause) {
        if (mounted)
          setLogError(cause instanceof Error ? cause.message : String(cause));
      } finally {
        if (
          mounted &&
          ["queued", "running", "stopping"].includes(jobStatus ?? "")
        )
          timer = window.setTimeout(() => void load(), 1200);
      }
    };
    void load();
    return () => {
      mounted = false;
      window.clearTimeout(timer);
    };
  }, [jobId, jobStatus, w.settings?.max_log_lines]);
  useEffect(() => {
    if (autoScroll && logViewport.current) {
      logViewport.current.scrollTop = logViewport.current.scrollHeight;
    }
  }, [lines, autoScroll]);
  const progress =
    current && current.progress.total > 0
      ? Math.min(
          100,
          Math.max(0, (current.progress.done / current.progress.total) * 100),
        )
      : 0;
  return (
    <Panel
      title="Tác vụ & nhật ký"
      description="Tiến độ trực tiếp từ máy chủ. Dừng tác vụ giữ lại những đầu ra đã hoàn thành và chờ worker thoát an toàn."
      aside={
        <Terminal className="size-5 text-muted-foreground" aria-hidden="true" />
      }
    >
      {!w.jobs.length ? (
        <p className="empty">
          Chưa chạy tác vụ nào. Nhật ký sẽ xuất hiện khi bạn bắt đầu pipeline.
        </p>
      ) : (
        <>
          <Field label="Chọn tác vụ">
            {(id) => (
              <select
                id={id}
                className="select"
                value={current?.id ?? ""}
                onChange={(event) => setSelected(event.target.value)}
              >
                {w.jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {actionLabels[job.action] ?? job.action} ·{" "}
                    {statusLabels[job.status]} ·{" "}
                    {new Date(job.created_at).toLocaleTimeString("vi-VN")}
                  </option>
                ))}
              </select>
            )}
          </Field>
          {current && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">
                  {actionLabels[current.action] ?? current.action}
                </p>
                <span
                  className={`badge ${current.status === "failed" ? "text-destructive" : ""}`}
                >
                  {statusLabels[current.status]}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                {current.progress.message || "Chưa có thông báo tiến độ"}
              </p>
              {current.progress.total > 0 ? (
                <>
                  <progress
                    className="h-2 w-full accent-primary"
                    max={100}
                    value={progress}
                    aria-label="Tiến độ tác vụ"
                  />
                  <p className="text-xs tabular-nums text-muted-foreground">
                    {current.progress.done} / {current.progress.total} ·{" "}
                    {Math.round(progress)}%
                  </p>
                </>
              ) : (
                ["queued", "running", "stopping"].includes(current.status) && (
                  <p className="text-sm" role="status">
                    Đang xử lý · chưa có tổng tiến độ
                  </p>
                )
              )}
              {current.error && (
                <p role="alert" className="error-box">
                  {current.error}
                </p>
              )}
              {current.result && (
                <details>
                  <summary className="cursor-pointer text-sm font-medium">
                    Kết quả / chi tiết từng nhóm
                  </summary>
                  <pre className="text-preview mt-3">
                    {JSON.stringify(current.result, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Toggle
              label="Tự cuộn nhật ký"
              checked={autoScroll}
              onChange={setAutoScroll}
            />
            {active && (
              <Confirm
                label={
                  active.status === "stopping" ? "Đang dừng…" : "Dừng tác vụ"
                }
                title="Dừng sau phần xử lý hiện tại?"
                description="Yêu cầu hủy được chuyển đến worker. Đầu ra hoàn thành được giữ nguyên; tác vụ có thể cần thời gian để thoát mạng hoặc FFmpeg an toàn."
                disabled={active.status === "stopping" || w.pending}
                onConfirm={() =>
                  void w.perform(
                    () => api.stop(active.id),
                    "Đã gửi yêu cầu dừng. Đợi worker thoát an toàn.",
                  )
                }
              />
            )}
            <Button
              variant="ghost"
              disabled={w.pending}
              onClick={() => void w.refresh()}
            >
              Tải lại trạng thái
            </Button>
          </div>
          {logError && (
            <p role="alert" className="error-box">
              Không tải được nhật ký: {logError}
            </p>
          )}
          <div
            ref={logViewport}
            className="log-view max-h-80 overflow-y-auto rounded-lg p-4"
            role="log"
            aria-label="Nhật ký tác vụ"
            aria-live="off"
          >
            {lines.length ? (
              lines.map((line) => (
                <p
                  key={line.sequence}
                  className="break-anywhere whitespace-pre-wrap font-mono text-xs leading-6"
                >
                  <span className="opacity-65">
                    {new Date(line.timestamp).toLocaleTimeString("vi-VN")} [
                    {line.level}]{" "}
                  </span>
                  {line.message}
                </p>
              ))
            ) : (
              <p className="text-sm">Chưa có dòng nhật ký cho tác vụ này.</p>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}
