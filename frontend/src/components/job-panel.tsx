import { useEffect, useRef, useState } from "react";
import { AlertCircle, Loader2, Terminal, X } from "lucide-react";
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
      className="job-panel"
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
          <div className="job-actions">
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
                  <span className="log-time">
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

const resumable = ["tts", "video", "upload", "thumbnail"];

/** Bottom bar: only shows while something runs (or just failed). Full logs open on demand. */
export function JobBar({ w }: { w: Workspace }) {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState("");
  const active = w.jobs.find(job => ["queued", "running", "stopping"].includes(job.status));
  const latest = w.jobs[0];
  const failed = !active && latest?.status === "failed" && latest.id !== dismissed ? latest : undefined;
  const job = active ?? failed;
  const percent = job && job.progress.total > 0 ? Math.round(Math.min(100, (job.progress.done / job.progress.total) * 100)) : null;
  return (
    <>
      {open && (
        <div className="log-sheet" role="dialog" aria-label="Tác vụ & nhật ký">
          <div className="log-sheet-inner">
            <Button variant="ghost" className="log-sheet-close" aria-label="Đóng nhật ký" onClick={() => setOpen(false)}><X aria-hidden="true" /></Button>
            <JobPanel w={w} />
          </div>
        </div>
      )}
      {job ? (
        <div className={`jobbar ${failed ? "is-failed" : ""}`} role="status">
          {failed ? <AlertCircle className="size-5 shrink-0" aria-hidden="true" /> : <Loader2 className="size-5 shrink-0 animate-spin" aria-hidden="true" />}
          <div className="jobbar-copy">
            <p><strong>{actionLabels[job.action] ?? job.action}</strong>{failed ? " — chưa xong" : job.status === "stopping" ? " — đang dừng" : ""}{w.chainLeft > 0 && !failed ? <span className="jobbar-next"> · còn {w.chainLeft} bước</span> : null}</p>
            <p className="jobbar-msg">{failed ? `${failed.error ?? "Có lỗi."}${resumable.includes(failed.action) ? " Bấm chạy lại để làm tiếp phần còn thiếu." : ""}` : job.progress.message || "Đang xử lý…"}</p>
            {!failed && <div className="jobbar-track"><div style={{ width: `${percent ?? 8}%` }} className={percent === null ? "is-indeterminate" : ""} /></div>}
          </div>
          {percent !== null && !failed && <span className="jobbar-pct">{percent}%</span>}
          <Button variant="ghost" onClick={() => setOpen(!open)}>{open ? "Ẩn" : "Chi tiết"}</Button>
          {active && <Confirm variant="ghost" label={active.status === "stopping" ? "Đang dừng…" : "Dừng"} title="Dừng tác vụ?" description="Phần đã xong được giữ lại. Có thể chạy tiếp sau." disabled={active.status === "stopping" || w.pending} onConfirm={() => void w.perform(() => api.stop(active.id), "Đã yêu cầu dừng.")} />}
          {failed && <Button variant="ghost" aria-label="Ẩn thông báo lỗi" onClick={() => setDismissed(failed.id)}><X aria-hidden="true" /></Button>}
        </div>
      ) : w.jobs.length > 0 && (
        <button type="button" className="log-fab" onClick={() => setOpen(!open)}><Terminal className="size-4" aria-hidden="true" />Nhật ký</button>
      )}
    </>
  );
}
