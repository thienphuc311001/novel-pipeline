import assert from "node:assert/strict";
import test from "node:test";
import { groupStatus, pipelineSummary, jobScreen } from "../src/lib/pipeline.ts";
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
