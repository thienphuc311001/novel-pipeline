import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  Draft,
  Job,
  JobStep,
  JsonObject,
  Screen,
  Settings,
  Snapshot,
  Workspace,
  Session,
} from "@/lib/types";
import { draftSchema, eventSchema, screenSchema } from "@/lib/schemas";

export const screens: Screen[] = [
  "input",
  "normalize",
  "tts",
  "video",
  "youtube",
  "sessions",
  "settings",
];
const defaultDraft: Draft = {
  screen: "input",
  paths: "",
  sort: "natural",
  title: "",
  groupSize: 20,
  text: "",
  thumbnail: "",
  cover: "",
  qr: "",
  selected: [],
  metadata: {
    title: "",
    description: "",
    tags: [],
    category_id: "22",
    privacy: "private",
    made_for_kids: false,
    contains_synthetic_media: false,
    playlist_id: null,
    publish_at: null,
  },
  tagsText: "",
  tagsEdited: false,
  titles: {},
  chunkEdits: {},
  settings: null,
  settingsJson: null,
};
function restoreDraft(
  state: Snapshot,
  settings: Settings,
  useHash = true,
): Draft {
  const legacyTab =
    typeof state.ui_state.tab === "number" &&
    state.ui_state.tab >= 0 &&
    state.ui_state.tab < 5
      ? state.ui_state.tab
      : 0;
  const panels = state.ui_state.panels;
  const panel =
    panels && typeof panels === "object" && !Array.isArray(panels)
      ? (panels as JsonObject)[
          ["group4", "group5", "group6"][Math.max(0, legacyTab - 2)]
        ]
      : undefined;
  const selected =
    panel && typeof panel === "object" && !Array.isArray(panel)
      ? (panel as JsonObject).checked
      : undefined;
  const parsed = draftSchema.safeParse(
    state.ui_state.web_draft ?? {
      screen: screens[legacyTab],
      cover: state.ui_state.cover_image ?? "",
      qr: state.ui_state.qr_image ?? String(settings.qr_image_path ?? ""),
      selected: selected ?? [],
      metadata:
        state.ui_state.group_upload_metadata ?? state.ui_state.upload_metadata,
      titles: state.ui_state.upload_titles ?? defaultDraft.titles,
    },
  );
  if (!parsed.success)
    throw new Error(
      "Bản nháp phiên không đúng cấu trúc. Dữ liệu pipeline vẫn còn trên máy chủ.",
    );
  const draft = parsed.data;
  const hash = screenSchema.safeParse(location.hash.slice(1));
  const legacySizes = [10, 20, 25, 50];
  const legacyIndex = state.ui_state.group_size;
  const legacySize =
    typeof legacyIndex === "number"
      ? legacyIndex === 4 && typeof state.ui_state.custom_size === "number"
        ? state.ui_state.custom_size
        : legacySizes[legacyIndex]
      : undefined;
  const savedScreen =
    draft.screen && screens.indexOf(draft.screen) < 5
      ? draft.screen
      : screens[legacyTab];
  const tagsEdited = draft.tagsEdited ?? Boolean(draft.metadata?.tags.length);
  const tags = tagsEdited
    ? (draft.metadata?.tags ?? [])
    : (state.youtube_tags.current ?? []);
  return {
    ...defaultDraft,
    title: state.title,
    text: state.text,
    qr: String(settings.qr_image_path ?? ""),
    ...draft,
    tagsText: tagsEdited
      ? (draft.tagsText ?? tags.join(", "))
      : tags.join(", "),
    tagsEdited,
    groupSize:
      typeof state.ui_state.web_group_size === "number"
        ? state.ui_state.web_group_size
        : (draft.groupSize ?? legacySize ?? 20),
    screen: useHash && hash.success ? hash.data : savedScreen,
    metadata: { ...defaultDraft.metadata, ...draft.metadata, tags },
    settings: draft.settings ?? settings,
  };
}
export function useWorkspace(): Workspace {
  const [state, setState] = useState<Snapshot | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [draft, updateDraft] = useState<Draft>(defaultDraft);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [connection, setConnection] =
    useState<Workspace["connection"]>("connecting");
  const actionLock = useRef(false);
  const autosave = useRef<Promise<void> | null>(null);
  const draftRef = useRef(draft);
  const stateRef = useRef(state);
  const initialized = useRef(false);
  const dirty = useRef(false);
  const mounted = useRef(true);
  draftRef.current = draft;
  stateRef.current = state;
  const active = jobs.find((job) =>
    ["queued", "running", "stopping"].includes(job.status),
  );
  const busy = Boolean(active) || pending;
  const applyState = useCallback((next: Snapshot) => {
    const previous = stateRef.current;
    setState(next);
    if (previous) {
      updateDraft((old) => {
        const changedStory = next.title !== previous.title;
        const automaticTags = changedStory || !old.tagsEdited;
        const tags = automaticTags
          ? (next.youtube_tags.current ?? [])
          : old.metadata.tags;
        return {
          ...old,
          text: next.text !== previous.text ? next.text : old.text,
          title: changedStory ? next.title : old.title,
          tagsEdited: changedStory ? false : old.tagsEdited,
          metadata: { ...old.metadata, tags },
          tagsText: automaticTags ? tags.join(", ") : old.tagsText,
        };
      });
    }
  }, []);
  const perform = useCallback(
    async <T>(
      operation: () => Promise<T>,
      success?: string,
    ): Promise<T | undefined> => {
      if (actionLock.current) {
        setError("Một yêu cầu đang được xử lý. Vui lòng chờ.");
        return;
      }
      actionLock.current = true;
      setPending(true);
      setError("");
      if (success) setNotice("");
      try {
        if (autosave.current) await autosave.current;
        const result = await operation();
        if (success) setNotice(success);
        return result;
      } catch (cause) {
        setNotice("");
        setError(cause instanceof Error ? cause.message : String(cause));
        return undefined;
      } finally {
        actionLock.current = false;
        if (mounted.current) setPending(false);
      }
    },
    [],
  );
  const refresh = useCallback(async () => {
    await perform(async () => {
      const [next, config, history, stored] = await Promise.all([
        api.state(),
        api.settings(),
        api.jobs(),
        api.sessions(),
      ]);
      applyState(next);
      setSettings(config);
      setJobs(history);
      setSessions(stored);
      if (!initialized.current) {
        updateDraft(restoreDraft(next, config));
        initialized.current = true;
      }
    });
  }, [applyState, perform]);
  const uiPayload = useCallback((): JsonObject => {
    const tab = screens.indexOf(draftRef.current.screen);
    return {
      ...stateRef.current?.ui_state,
      tab: tab < 5 ? tab : (stateRef.current?.ui_state.tab ?? 0),
      web_group_size: draftRef.current.groupSize,
      web_draft: draftRef.current,
    };
  }, []);
  const save = useCallback(async () => {
    await perform(async () => {
      const saved = await api.save(uiPayload());
      dirty.current = false;
      const [next, stored] = await Promise.all([api.state(), api.sessions()]);
      applyState({ ...next, session_id: saved.id });
      setSessions(stored);
    }, "Đã lưu phiên và toàn bộ bản nháp.");
  }, [perform, uiPayload, applyState]);
  const run = useCallback(
    async (action: string, options: JsonObject = {}) =>
      perform(async () => {
        if (
          stateRef.current?.text ||
          !["youtube_connect", "youtube_disconnect"].includes(action)
        ) {
          await api.save(uiPayload());
          dirty.current = false;
        }
        const job = await api.run(action, options);
        setJobs((old) => [job, ...old.filter((row) => row.id !== job.id)]);
        return job;
      }, "Đã bắt đầu."),
    [perform, uiPayload],
  );
  // Client-side chain: start each following step only after the previous job completes.
  const chain = useRef<JobStep[]>([]);
  const chainJob = useRef<string | null>(null);
  const [chainLeft, setChainLeft] = useState(0);
  const runSteps = useCallback(
    async (steps: JobStep[]) => {
      const [first, ...rest] = steps;
      if (!first) return;
      const job = await run(first.action, first.options);
      chain.current = job ? rest : [];
      chainJob.current = job ? job.id : null;
      setChainLeft(job ? rest.length : 0);
    },
    [run],
  );
  useEffect(() => {
    const job = jobs.find((row) => row.id === chainJob.current);
    if (!job || ["queued", "running", "stopping"].includes(job.status)) return;
    const rest = chain.current;
    chainJob.current = null;
    chain.current = [];
    setChainLeft(0);
    // Not cancelled on re-render: the refs are already cleared, so frequent job updates must not drop the next step.
    if (job.status === "completed" && rest.length)
      window.setTimeout(() => void runSteps(rest), 300);
  }, [jobs, runSteps]);
  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(""), 4000);
    return () => window.clearTimeout(timeout);
  }, [notice]);
  const open = useCallback(
    async (id?: string) => {
      await perform(
        async () => {
          if (dirty.current && stateRef.current) await api.save(uiPayload());
          const next = await api.open(id);
          const config = await api.settings();
          setState(next);
          setSettings(config);
          const restored = restoreDraft(next, config, false);
          updateDraft(restored);
          history.replaceState(null, "", `#${restored.screen}`);
          window.scrollTo(0, 0);
          dirty.current = false;
          setSessions(await api.sessions());
        },
        id ? "Đã khôi phục phiên và bản nháp." : "Đã tạo phiên mới.",
      );
    },
    [perform, uiPayload],
  );
  const setDraft = useCallback((update: Partial<Draft>) => {
    dirty.current = true;
    updateDraft((old) => ({ ...old, ...update }));
  }, []);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    const events = new EventSource("/api/events");
    events.onopen = () => {
      setConnection("connected");
      if (!initialized.current && !actionLock.current) void refresh();
    };
    events.onerror = () => setConnection("reconnecting");
    const receive = (event: MessageEvent) => {
      try {
        const payload = eventSchema.parse(JSON.parse(event.data));
        if (payload.state) applyState(payload.state);
        setJobs(payload.jobs);
        setConnection("connected");
      } catch {
        setError(
          "Dữ liệu cập nhật từ máy chủ không hợp lệ. Hãy tải lại trạng thái.",
        );
      }
    };
    events.addEventListener("update", receive);
    return () => {
      mounted.current = false;
      events.removeEventListener("update", receive);
      events.close();
    };
  }, [refresh, applyState]);
  useEffect(() => {
    const onHash = () => {
      const screen = screenSchema.safeParse(location.hash.slice(1));
      if (screen.success) {
        setDraft({ screen: screen.data });
        window.scrollTo(0, 0);
      }
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [setDraft]);
  useEffect(() => {
    if (
      !initialized.current ||
      !dirty.current ||
      busy ||
      error ||
      connection !== "connected"
    )
      return;
    const timeout = window.setTimeout(() => {
      // Background save: does not set `pending`, so controls stay enabled; perform() waits for it.
      if (actionLock.current || autosave.current) return;
      const revision = draftRef.current;
      autosave.current = (async () => {
        try {
          const saved = await api.save(uiPayload());
          if (revision === draftRef.current) dirty.current = false;
          setState((old) => (old ? { ...old, session_id: saved.id } : old));
          setSessions(await api.sessions());
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : String(cause));
        } finally {
          autosave.current = null;
        }
      })();
    }, 1500);
    return () => window.clearTimeout(timeout);
  }, [draft, busy, error, connection, perform, uiPayload]);
  return {
    state,
    jobs,
    settings,
    sessions,
    draft,
    setDraft,
    busy,
    pending,
    error,
    notice,
    connection,
    run,
    runSteps,
    chainLeft,
    perform,
    refresh,
    save,
    open,
  };
}
