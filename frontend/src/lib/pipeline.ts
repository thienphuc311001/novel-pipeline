import type { Group, Screen, Snapshot } from "./types";

export type PipelineScreen = Exclude<Screen, "sessions" | "settings">;
export interface StageSummary {
  id: PipelineScreen;
  label: string;
  detail: string;
  count: number;
  total: number;
  done: boolean;
}
const actionScreens: Record<string, PipelineScreen> = {
  import: "input",
  normalize: "normalize", edit: "normalize", group: "normalize", export: "normalize",
  prepare: "tts", thumbnail: "tts", tts: "tts", merge_partial: "tts", edit_chunk: "tts",
  video: "video", preview: "video",
  youtube_connect: "youtube", youtube_disconnect: "youtube", upload: "youtube",
  youtube_metadata: "youtube", youtube_retry_thumbnail: "youtube", youtube_retry_playlist: "youtube",
};
export const jobScreen = (action: string): PipelineScreen | undefined => actionScreens[action];

export function pipelineSummary(state: Snapshot | null): StageSummary[] {
  const groups = state?.groups ?? [];
  const exists = (path?: string) => Boolean(path && !state?.missing_artifacts.includes(path));
  const audio = groups.filter(group => group.state.tts_status === "Completed" && exists(group.state.audiobook?.path)).length;
  const video = groups.filter(group => exists(group.state.video?.path)).length;
  const youtube = groups.filter(group => group.state.youtube?.video_id).length;
  const mediaStage = (id: PipelineScreen, label: string, count: number, suffix: string): StageSummary => ({
    id, label, count, total: groups.length,
    done: groups.length > 0 && count === groups.length,
    detail: groups.length ? `${count}/${groups.length} ${suffix}` : "Chưa có nhóm",
  });
  return [
    {id:"input",label:"Bản thảo",count:state?.sources.length ?? 0,total:1,done:Boolean(state?.text),detail:state?.text ? `${state.text.length.toLocaleString("vi-VN")} ký tự` : "Chưa nhập nguồn"},
    {id:"normalize",label:"Chuẩn hóa & nhóm",count:groups.length,total:groups.length,done:groups.length > 0,detail:groups.length ? `${groups.length} nhóm chương` : state?.normalized_text ? "Chờ chia nhóm" : "Chưa chuẩn hóa"},
    mediaStage("tts","Âm thanh",audio,"hoàn tất"),
    mediaStage("video","Video",video,"có MP4"),
    mediaStage("youtube","YouTube",youtube,"có video ID"),
  ];
}

export type GroupStatus = "done" | "error" | "todo";
export type MediaStage = "tts" | "video" | "youtube";
const audioIssues = ["Partial", "TTS Incomplete", "Cancelled"];
export function groupStatus(state: Snapshot | null, group: Group, stage: MediaStage): GroupStatus {
  const exists = (path?: string) => Boolean(path && !state?.missing_artifacts.includes(path));
  const s = group.state;
  if (stage === "tts") {
    if (s.tts_status === "Completed" && exists(s.audiobook?.path)) return "done";
    return s.failures?.length || audioIssues.includes(s.tts_status ?? "") || s.tts_status === "Completed" ? "error" : "todo";
  }
  if (stage === "video") return exists(s.video?.path) ? "done" : s.last_error && groupStatus(state, group, "tts") === "done" ? "error" : "todo";
  return s.youtube?.video_id ? "done" : s.youtube?.status && s.last_error ? "error" : "todo";
}
