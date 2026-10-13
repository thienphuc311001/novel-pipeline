import assert from "node:assert/strict";
import test from "node:test";
import { groupStatus, pipelineSummary, jobScreen } from "../src/lib/pipeline.ts";
import { draftSchema, screenSchema, snapshotSchema } from "../src/lib/schemas.ts";
import type { Group, Snapshot } from "../src/lib/types.ts";

const snapshot = (groups: Group[] = []): Snapshot => ({
  title: "Truyện", source_path: "", input_directory: "", original_text: "",
  normalized_text: null, text: "", youtube_tags: {current:null, history:{}},
  chapters: [], sources: [], groups, stages: {}, diagnostics: [],
  grouping: {headings:[],groups:[],warnings:[],requires_numeric_boundaries:false,numeric_available:false,confirmation_fingerprint:""},
  outputs: [], session_id:null, ui_state:{}, missing_artifacts:[],
});
const group = (state: Group["state"]): Group => ({
  group_id:"g1", order:1, label:"Chương 1–20",range_label:"1–20",title:"Truyện",
  output_dir:"/tmp/group",txt_path:"/tmp/group/final.txt",start:0,end:100,chapters:[],state,
});

test("empty workspace does not present later stages as complete", () => {
  assert.ok(pipelineSummary(null).every(stage => stage.done === false));
  assert.ok(pipelineSummary(snapshot()).every(stage => stage.done === false));
});
test("partial audio is not counted as completed TTS", () => {
  const stages = pipelineSummary(snapshot([group({tts_status:"Partial",audiobook:{path:"/tmp/partial.mp3"}})]));
  assert.equal(stages[2].count, 0);
  assert.equal(stages[2].done, false);
});
test("missing artifacts are excluded from pipeline counts", () => {
  const state = snapshot([group({tts_status:"Completed",audiobook:{path:"/tmp/a.mp3"},video:{path:"/tmp/v.mp4"}})]);
  state.missing_artifacts = ["/tmp/a.mp3","/tmp/v.mp4"];
  assert.equal(pipelineSummary(state)[2].count, 0);
  assert.equal(pipelineSummary(state)[3].count, 0);
});
test("mixed group completion reports actual stage counts", () => {
  const state = snapshot([group({tts_status:"Completed",audiobook:{path:"/tmp/a.mp3"},video:{path:"/tmp/v.mp4"}}),group({})]);
  const stages = pipelineSummary(state);
  assert.equal(stages[1].done, true);
  assert.equal(stages[2].count, 1);
  assert.equal(stages[2].total, 2);
  assert.equal(stages[2].done, false);
  assert.equal(stages[3].count, 1);
});
test("YouTube video ID is reported without claiming public publication", () => {
  const stages = pipelineSummary(snapshot([group({youtube:{video_id:"abc",status:"uploaded"}})]));
  assert.equal(stages[4].count, 1);
  assert.match(stages[4].detail, /ID/);
});
test("normalization without groups keeps grouping stage incomplete", () => {
  const state = snapshot(); state.text = "Chương 1.\nNội dung"; state.normalized_text = state.text;
  assert.equal(pipelineSummary(state)[0].done, true);
  assert.equal(pipelineSummary(state)[1].done, false);
});
test("jobs point to the appropriate stage, including recovery actions", () => {
  assert.equal(jobScreen("edit_chunk"), "tts");
  assert.equal(jobScreen("preview"), "video");
  assert.equal(jobScreen("youtube_retry_thumbnail"), "youtube");
  assert.equal(jobScreen("export"), "normalize");
  assert.equal(jobScreen("unknown"), undefined);
});
test("group status separates done, failed and untouched groups per stage", () => {
  const done = group({tts_status:"Completed",audiobook:{path:"/tmp/a.mp3"},video:{path:"/tmp/v.mp4"},youtube:{video_id:"abc"}});
  const state = snapshot([done]);
  assert.equal(groupStatus(state, done, "tts"), "done");
  assert.equal(groupStatus(state, done, "video"), "done");
  assert.equal(groupStatus(state, done, "youtube"), "done");
  assert.equal(groupStatus(state, group({}), "tts"), "todo");
  assert.equal(groupStatus(state, group({tts_status:"TTS Incomplete"}), "tts"), "error");
});
test("group status treats a missing MP3 as an error, not done", () => {
  const missing = group({tts_status:"Completed",audiobook:{path:"/tmp/a.mp3"}});
  const state = snapshot([missing]); state.missing_artifacts = ["/tmp/a.mp3"];
  assert.equal(groupStatus(state, missing, "tts"), "error");
});

// Session restoration inputs: a reopened web session and a baseline (desktop schema-v1) session.
const uploadMetadata = {
  title: "", description: "Mô tả chưa upload", tags: ["tag mới chưa upload"], category_id: "22",
  privacy: "private", made_for_kids: false, playlist_id: null, publish_at: null, contains_synthetic_media: true,
};

test("reopened web session keeps the unuploaded tag draft beside saved story tags", () => {
  const webDraft = { screen: "youtube", tagsText: "tag mới chưa upload", tagsEdited: true, selected: ["g2"], metadata: uploadMetadata };
  const state = snapshotSchema.parse({
    ...snapshot(), title: "Bắc Tống", youtube_tags: { current: ["tag đã upload"], history: { "Bắc Tống": ["tag đã upload"] } },
    session_id: "a".repeat(32), ui_state: { tab: 4, web_group_size: 1, web_draft: webDraft },
  });
  const draft = draftSchema.parse(state.ui_state.web_draft);
  assert.equal(draft.screen, "youtube");
  assert.equal(draft.tagsText, "tag mới chưa upload");
  assert.equal(draft.tagsEdited, true);
  assert.deepEqual(draft.selected, ["g2"]);
  assert.deepEqual(draft.metadata?.tags, ["tag mới chưa upload"]);
  assert.equal(draft.metadata?.contains_synthetic_media, true);
  assert.deepEqual(state.youtube_tags.current, ["tag đã upload"]);
});

test("baseline desktop session state remains a valid restoration source", () => {
  const legacy = {
    tab: 4, group_size: 4, custom_size: 1, cover_image: "/tmp/cover.png", qr_image: "/tmp/qr.png",
    panels: { group4: { selected: "g1", checked: ["g1"] }, group5: { selected: "g2", checked: ["g2"] },
      group6: { selected: "g2", checked: ["g2"] } },
    upload_titles: { g2: "Bắc Tống | Chương 2" },
    upload_metadata: uploadMetadata, group_upload_metadata: { ...uploadMetadata, description: "Nhóm" },
  };
  const state = snapshotSchema.parse({ ...snapshot(), ui_state: legacy });
  assert.deepEqual(state.ui_state, legacy);
  // The legacy fields restoreDraft maps (screen by tab, cover/qr, group6 checks, group metadata, titles).
  const draft = draftSchema.parse({
    screen: screenSchema.options[legacy.tab], cover: legacy.cover_image, qr: legacy.qr_image,
    selected: legacy.panels.group6.checked, metadata: legacy.group_upload_metadata, titles: legacy.upload_titles,
  });
  assert.equal(draft.screen, "youtube");
  assert.deepEqual(draft.metadata?.tags, ["tag mới chưa upload"]);
  assert.equal(draft.metadata?.description, "Nhóm");
  assert.deepEqual(draft.titles, { g2: "Bắc Tống | Chương 2" });
  assert.equal(draftSchema.safeParse({ metadata: { tags: "not a list" } }).success, false);
});
