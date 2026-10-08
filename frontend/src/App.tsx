import { ArrowLeft, AudioLines, Check, FolderOpen, Settings2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { useWorkspace } from "@/hooks/use-workspace";
import type { Screen, Workspace } from "@/lib/types";
import { pipelineSummary, type PipelineScreen } from "@/lib/pipeline";
import { Button } from "@/components/ui/button";
import { JobBar } from "@/components/job-panel";
import { InputScreen, NormalizeScreen } from "@/screens/text-screens";
import { TtsScreen, VideoScreen } from "@/screens/media-screens";
import { YoutubeScreen } from "@/screens/youtube-screen";
import { SessionsScreen, SettingsScreen } from "@/screens/workspace-screens";

const stepLabels: Record<PipelineScreen, string> = {
  input: "Bản thảo", normalize: "Chia nhóm", tts: "Âm thanh", video: "Video", youtube: "YouTube",
};

export default function App() {
  const w = useWorkspace();
  const stages = pipelineSummary(w.state);
  const screen = w.draft.screen;
  const isPipeline = screen !== "sessions" && screen !== "settings";
  const lastStep = useRef<Screen>("input");
  if (isPipeline) lastStep.current = screen;
  useEffect(() => {
    document.getElementById("main-content")?.focus({ preventScroll: true });
  }, [screen]);

  return (
    <div className="app">
      <a className="skip-link" href="#main-content">Bỏ qua điều hướng</a>
      <header className="topbar">
        <a href="#input" className="brand"><span className="brand-mark"><AudioLines className="size-4" aria-hidden="true" /></span><span className="brand-name">Novel Pipeline</span></a>
        <span className="project-name" title={w.state?.title}>{w.state?.title || "Bản thảo mới"}</span>
        <div className="top-actions">
          <span className={`conn ${w.connection === "connected" ? "is-on" : ""}`} title={w.connection === "connected" ? "Đã kết nối máy chủ" : "Đang kết nối lại…"}><span className="conn-dot" /><span className="conn-label">{w.connection === "connected" ? "Đã kết nối" : "Đang kết nối…"}</span></span>
          <a href="#sessions" className={`icon-link ${screen === "sessions" ? "is-active" : ""}`} aria-label="Phiên làm việc" title="Phiên làm việc"><FolderOpen className="size-4" aria-hidden="true" /><span>Phiên</span></a>
          <a href="#settings" className={`icon-link ${screen === "settings" ? "is-active" : ""}`} aria-label="Thiết lập" title="Thiết lập"><Settings2 className="size-4" aria-hidden="true" /><span>Thiết lập</span></a>
        </div>
      </header>
      <nav className="stepper" aria-label="Các bước">
        {stages.map((stage, index) => {
          const current = stage.id === screen;
          const progress = index >= 2 && stage.total > 0 && !stage.done ? `${stage.count}/${stage.total}` : null;
          return (
            <a key={stage.id} href={`#${stage.id}`} className={`step ${current ? "is-current" : ""} ${stage.done ? "is-done" : ""}`} aria-current={current ? "step" : undefined}>
              <span className="step-dot">{stage.done ? <Check className="size-3.5" aria-hidden="true" /> : index + 1}</span>
              <span className="step-label">{stepLabels[stage.id]}{progress && <small>{progress}</small>}</span>
            </a>
          );
        })}
      </nav>
      <main id="main-content" tabIndex={-1} className="main">
        {!isPipeline && <a href={`#${lastStep.current}`} className="back-link"><ArrowLeft className="size-4" aria-hidden="true" />Quay lại các bước</a>}
        {w.error && (
          <div role="alert" className="error-box flex flex-wrap items-center justify-between gap-3">
            <p className="min-w-0 flex-1">{w.error}</p>
            <Button variant="outline" disabled={w.pending} onClick={() => void w.refresh()}>Thử lại</Button>
          </div>
        )}
        {!!w.state?.missing_artifacts.length && <p className="warning">{w.state.missing_artifacts.length} tệp đầu ra bị thiếu trên ổ đĩa. <a className="underline" href="#sessions">Xem chi tiết</a></p>}
        {!w.state ? (
          <section className="step-card"><div className="step-head"><h1>{w.error ? "Máy chủ chưa sẵn sàng" : "Đang tải…"}</h1><p>Trang sẽ tự kết nối lại.</p></div></section>
        ) : <WorkspaceScreen screen={screen} w={w} />}
      </main>
      <div aria-live="polite" aria-atomic="true">{w.notice && <p className="toast">{w.notice}</p>}</div>
      <JobBar w={w} />
    </div>
  );
}

function WorkspaceScreen({ screen, w }: { screen: Screen; w: Workspace }) {
  switch (screen) {
    case "input": return <InputScreen w={w} />;
    case "normalize": return <NormalizeScreen w={w} />;
    case "tts": return <TtsScreen w={w} />;
    case "video": return <VideoScreen w={w} />;
    case "youtube": return <YoutubeScreen w={w} />;
    case "sessions": return <SessionsScreen w={w} />;
    case "settings": return <SettingsScreen w={w} />;
  }
}
