export type JsonObject = Record<string, unknown>;
export interface OutputFile {
  path: string;
  name: string;
  size: number;
}
export interface Chunk {
  order: number;
  text: string;
  chapter?: number;
}
export interface Failure {
  chunk_number: number;
  original_text: string;
  failed_part_text?: string;
  error_type: string;
  error_message: string;
}
export interface Metadata {
  title: string;
  description: string;
  tags: string[];
  category_id: string;
  privacy: "private" | "unlisted" | "public";
  made_for_kids: boolean;
  contains_synthetic_media: boolean;
  playlist_id: string | null;
  publish_at: string | null;
}
export interface Group {
  group_id: string;
  order: number;
  label: string;
  range_label: string;
  title: string;
  output_dir: string;
  txt_path: string;
  start: number;
  end: number;
  chapters: {
    heading?: string;
    number?: number;
    start?: number;
    end?: number;
  }[];
  state: {
    tts_status?: string;
    last_error?: string;
    failures?: Failure[];
    successful_orders?: number[];
    excluded_chunks?: number[];
    tts_plan?: { chunks?: Chunk[]; plan_id?: string; [key: string]: unknown };
    thumbnail?: { path: string };
    audiobook?: { path: string };
    video?: { path: string };
    youtube?: {
      status?: string;
      video_id?: string;
      metadata?: Metadata;
      updated_metadata?: Metadata;
      thumbnail_uploaded?: boolean;
      playlist_added?: boolean;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
}
export interface Grouping {
  headings: {
    number: number;
    heading: string;
    line: number;
    start: number;
    end: number;
  }[];
  groups: {
    label?: string;
    range_label: string;
    chapters?: unknown[];
    start: number;
    end: number;
  }[];
  warnings: string[];
  requires_numeric_boundaries: boolean;
  numeric_available: boolean;
  confirmation_fingerprint: string;
  error?: string;
}
export interface Snapshot {
  title: string;
  source_path: string;
  input_directory: string;
  original_text: string;
  normalized_text: string | null;
  text: string;
  youtube_tags: {
    current: string[] | null;
    history: Record<string, string[]>;
  };
  chapters: unknown[];
  sources: JsonObject[];
  groups: Group[];
  stages: Record<
    string,
    { status?: string; message?: string; [key: string]: unknown }
  >;
  diagnostics: { message: string; severity?: string; [key: string]: unknown }[];
  grouping: Grouping;
  outputs: OutputFile[];
  session_id: string | null;
  ui_state: JsonObject;
  missing_artifacts: string[];
}
export interface Job {
  id: string;
  action: string;
  status:
    | "queued"
    | "running"
    | "stopping"
    | "completed"
    | "failed"
    | "cancelled";
  created_at: string;
  finished_at: string | null;
  progress: { done: number; total: number; message: string };
  error: string | null;
  result: JsonObject | null;
}
export interface LogLine {
  sequence: number;
  timestamp: string;
  level: string;
  message: string;
}
export interface Session {
  id: string;
  title: string;
  updated_at: string;
  step: string | number;
}
export type Settings = Record<
  string,
  string | number | boolean | string[] | JsonObject | JsonObject[]
>;
export type Screen =
  | "input"
  | "normalize"
  | "tts"
  | "video"
  | "youtube"
  | "sessions"
  | "settings";
export interface Draft {
  screen: Screen;
  paths: string;
  sort: "natural" | "selection" | "name";
  title: string;
  groupSize: number;
  text: string;
  thumbnail: string;
  cover: string;
  qr: string;
  selected: string[];
  metadata: Metadata;
  tagsText: string;
  tagsEdited: boolean;
  titles: Record<string, string>;
  chunkEdits: Record<string, string>;
  settings: Settings | null;
  settingsJson: string | null;
}
export interface JobStep {
  action: string;
  options?: JsonObject;
}
export interface Workspace {
  state: Snapshot | null;
  jobs: Job[];
  settings: Settings | null;
  sessions: Session[];
  draft: Draft;
  setDraft: (update: Partial<Draft>) => void;
  busy: boolean;
  pending: boolean;
  error: string;
  notice: string;
  connection: "connecting" | "connected" | "reconnecting";
  run: (action: string, options?: JsonObject) => Promise<Job | undefined>;
  runSteps: (steps: JobStep[]) => Promise<void>;
  chainLeft: number;
  perform: <T>(
    operation: () => Promise<T>,
    success?: string,
  ) => Promise<T | undefined>;
  refresh: () => Promise<void>;
  save: () => Promise<void>;
  open: (id?: string) => Promise<void>;
}
