import {
  BookOpen,
  CircleCheck,
  FileInput,
  Headphones,
  Layers3,
  Save,
  Settings,
  Video,
  Wifi,
  WifiOff,
  Youtube,
} from "lucide-react";
import { useWorkspace } from "@/hooks/use-workspace";
import type { Screen, Workspace } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { JobPanel, actionLabels } from "@/components/job-panel";
import { InputScreen, NormalizeScreen } from "@/screens/text-screens";
import { TtsScreen, VideoScreen } from "@/screens/media-screens";
import { YoutubeScreen } from "@/screens/youtube-screen";
import { SessionsScreen, SettingsScreen } from "@/screens/workspace-screens";

const navigation = [
  { id: "input", label: "Bản thảo", icon: FileInput, step: "01" },
  { id: "normalize", label: "Chuẩn hóa & nhóm", icon: Layers3, step: "02" },
  { id: "tts", label: "Âm thanh", icon: Headphones, step: "03" },
  { id: "video", label: "Video", icon: Video, step: "04" },
  { id: "youtube", label: "Xuất bản", icon: Youtube, step: "05" },
  { id: "sessions", label: "Phiên & bản nháp", icon: Save },
  { id: "settings", label: "Thiết lập", icon: Settings },
] as const;
export default function App() {
  const w = useWorkspace();
  const active = w.jobs.find((job) =>
    ["queued", "running", "stopping"].includes(job.status),
  );
  const stage = navigation.find((item) => item.id === w.draft.screen);
  const stageNumber = stage && "step" in stage ? stage.step : null;
  const groups = w.state?.groups ?? [];
  const counts = [
    { label: "Nhóm chương", count: groups.length, icon: Layers3 },
    {
      label: "Âm thanh đã tạo",
      count: groups.filter((group) => group.state.audiobook).length,
      icon: Headphones,
    },
    {
      label: "Video đã tạo",
      count: groups.filter((group) => group.state.video).length,
      icon: Video,
    },
    {
      label: "Đã có YouTube ID",
      count: groups.filter((group) => group.state.youtube?.video_id).length,
      icon: CircleCheck,
    },
  ];
  return (
    <div className="min-h-dvh">
      <a className="skip-link" href="#main-content">
        Bỏ qua điều hướng
      </a>
      <div className="app-grid mx-auto max-w-[1600px]">
        <aside className="sidebar">
          <a href="#input" className="flex items-center gap-3 px-2 py-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <BookOpen className="size-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-base font-bold tracking-tight">
                Novel Pipeline
              </p>
              <p className="text-xs text-muted-foreground">
                Không gian sản xuất cục bộ
              </p>
            </div>
          </a>
          <p className="eyebrow mt-6 hidden px-3 lg:block">
            Quy trình sản xuất
          </p>
          <nav
            aria-label="Quy trình và không gian làm việc"
            className="navigation mt-3"
          >
            {navigation.map((item) => (
              <a
                key={item.id}
                href={`#${item.id}`}
                aria-current={w.draft.screen === item.id ? "page" : undefined}
                className={`nav-item ${w.draft.screen === item.id ? "nav-active" : ""}`}
              >
                <item.icon aria-hidden="true" className="size-4 shrink-0" />
                <span className="min-w-0 flex-1">{item.label}</span>
                {"step" in item && (
                  <span className="text-xs tabular-nums opacity-60">
                    {item.step}
                  </span>
                )}
              </a>
            ))}
          </nav>
          <div className="mt-auto hidden rounded-lg border bg-card p-4 lg:block">
            <p className="text-xs font-semibold">Dữ liệu ở trên máy của bạn</p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              Chuẩn hóa và nhóm chạy offline. TTS và YouTube dùng mạng khi được
              yêu cầu.
            </p>
          </div>
        </aside>
        <div className="min-w-0">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b bg-card px-5 py-4 md:px-8">
            <div className="min-w-0">
              <p className="eyebrow">WORKSPACE</p>
              <p className="break-anywhere mt-1 font-semibold">
                {w.state?.title || "Bản thảo chưa đặt tên"}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={`flex items-center gap-2 text-xs ${w.connection === "connected" ? "text-primary" : "text-destructive"}`}
              >
                {w.connection === "connected" ? (
                  <Wifi className="size-4" aria-hidden="true" />
                ) : (
                  <WifiOff className="size-4" aria-hidden="true" />
                )}
                {w.connection === "connected"
                  ? "Đã kết nối"
                  : w.connection === "connecting"
                    ? "Đang kết nối"
                    : "Mất kết nối · đang thử lại"}
              </span>
              <Button
                variant="outline"
                disabled={w.busy || !w.state}
                onClick={() => void w.save()}
              >
                <Save aria-hidden="true" />
                Lưu phiên
              </Button>
            </div>
          </header>
          <main
            id="main-content"
            tabIndex={-1}
            className="space-y-6 p-4 outline-none md:p-8"
          >
            <div>
              <p className="eyebrow">
                {stageNumber
                  ? `BƯỚC ${stageNumber} / 05`
                  : "KHÔNG GIAN LÀM VIỆC"}
              </p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">
                {stage?.label}
              </h1>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Từ bản thảo đến video — kiểm soát từng nhóm, tiếp tục từ nơi đã
                dừng.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {counts.map((item) => (
                <div
                  key={item.label}
                  className="min-w-0 rounded-xl border bg-card p-4"
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-medium text-muted-foreground">
                      {item.label}
                    </p>
                    <item.icon
                      className="size-4 text-muted-foreground"
                      aria-hidden="true"
                    />
                  </div>
                  <p className="mt-2 text-2xl font-semibold tabular-nums">
                    {w.state ? item.count : "—"}
                  </p>
                </div>
              ))}
            </div>
            <div aria-live="polite" aria-atomic="true">
              {w.notice && <p className="success-box">{w.notice}</p>}
            </div>
            {w.error && (
              <div role="alert" className="error-box">
                <p className="font-medium">Không thể hoàn tất yêu cầu</p>
                <p className="mt-1 break-anywhere">{w.error}</p>
                <Button
                  className="mt-3"
                  variant="outline"
                  disabled={w.pending}
                  onClick={() => void w.refresh()}
                >
                  Thử tải lại trạng thái
                </Button>
              </div>
            )}
            {w.state?.missing_artifacts.length ? (
              <p className="warning">
                Phiên có {w.state.missing_artifacts.length} tệp không còn tồn
                tại. Xem Phiên & bản nháp trước khi tiếp tục.
              </p>
            ) : null}
            {active && (
              <p role="status" className="status-strip">
                <span className="size-2 shrink-0 rounded-full bg-primary" />
                {actionLabels[active.action] ?? active.action}:{" "}
                {active.progress.message || "Đang xử lý"} · thay đổi pipeline
                đang khóa
              </p>
            )}
            {!w.state ? (
              <section className="rounded-xl border bg-card p-8">
                <h2 className="font-semibold">
                  {w.error
                    ? "Máy chủ chưa sẵn sàng"
                    : "Đang tải không gian làm việc…"}
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  Giao diện cần backend tại 127.0.0.1:8000. Giữ trang mở để tự
                  động kết nối lại.
                </p>
                <Button
                  className="mt-4"
                  variant="outline"
                  disabled={w.pending}
                  onClick={() => void w.refresh()}
                >
                  Tải trạng thái
                </Button>
              </section>
            ) : (
              <WorkspaceScreen screen={w.draft.screen} w={w} />
            )}
            <JobPanel w={w} />
            <footer className="flex flex-wrap justify-between gap-2 border-t pt-4 text-xs text-muted-foreground">
              <p>Novel Pipeline · đầu ra được kiểm tra trên máy chủ</p>
              <p>
                {w.pending
                  ? "Đang gửi yêu cầu…"
                  : w.busy
                    ? "Tác vụ đang chạy"
                    : "Sẵn sàng"}{" "}
                · bản nháp tự lưu khi rảnh
              </p>
            </footer>
          </main>
        </div>
      </div>
    </div>
  );
}
function WorkspaceScreen({ screen, w }: { screen: Screen; w: Workspace }) {
  switch (screen) {
    case "input":
      return <InputScreen w={w} />;
    case "normalize":
      return <NormalizeScreen w={w} />;
    case "tts":
      return <TtsScreen w={w} />;
    case "video":
      return <VideoScreen w={w} />;
    case "youtube":
      return <YoutubeScreen w={w} />;
    case "sessions":
      return <SessionsScreen w={w} />;
    case "settings":
      return <SettingsScreen w={w} />;
  }
}
