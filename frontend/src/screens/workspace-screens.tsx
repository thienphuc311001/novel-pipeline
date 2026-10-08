import { useState } from "react";
import { ChevronDown, FolderOpen, Save, Settings2 } from "lucide-react";
import { api } from "@/lib/api";
import type { Settings, Workspace } from "@/lib/types";
import { settingsSchema } from "@/lib/schemas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { AssetField, Confirm, Field, Toggle } from "@/components/workflow";
import { More } from "@/components/wizard";

const settingSections: { title: string; fields: [string, string][] }[] = [
  {
    title: "Nhập bản thảo",
    fields: [
      ["encoding_chain", "Thứ tự mã hóa (mỗi dòng một giá trị)"],
      ["last_input_dir", "Thư mục nhập gần nhất"],
      ["auto_insert_headers", "Chèn tiêu đề chương còn thiếu"],
      ["auto_insert_prefix", "Mẫu tiêu đề chèn — dùng {n}"],
      ["continuous_numbering", "Đánh số liên tục"],
      ["merge_order_notes", "Ghi chú thứ tự ghép"],
    ],
  },
  {
    title: "Tiêu đề chương & chuẩn hóa",
    fields: [
      ["chapter_prefix", "Mẫu chương chuẩn — dùng {n}"],
      ["zero_pad", "Số chữ số đệm 0"],
      ["header_separator", "Ký tự ngăn tiêu đề"],
      ["keep_original_headers", "Giữ tiêu đề gốc"],
      ["detect_vietnamese", "Nhận diện tiêu đề tiếng Việt"],
      ["detect_english", "Nhận diện tiêu đề tiếng Anh"],
      ["detect_chinese", "Nhận diện tiêu đề tiếng Trung"],
      ["detect_plain_numbered", "Nhận diện tiêu đề chỉ có số"],
      ["use_custom_chapter_regex", "Dùng regex tùy chỉnh"],
      ["custom_chapter_regex", "Regex tiêu đề tùy chỉnh"],
      ["dedupe_chapters", "Loại chương trùng"],
      ["prefer_vietnamese", "Ưu tiên bản tiếng Việt khi trùng"],
      ["enforce_period", "Chuẩn hóa dấu chấm"],
      ["normalize_spacing", "Chuẩn hóa khoảng trắng"],
    ],
  },
  {
    title: "Làm sạch văn bản TTS",
    fields: [
      ["remove_control_chars", "Loại ký tự điều khiển"],
      ["remove_html", "Loại HTML"],
      ["unescape_html_entities", "Giải mã HTML entities"],
      ["quote_mode", "Xử lý dấu nháy"],
      ["bracket_mode", "Xử lý dấu ngoặc"],
      ["bracket_pairs", "Cặp ngoặc — mỗi dòng một cặp"],
      ["custom_quote_chars", "Dấu nháy tùy chỉnh"],
      ["symbol_map_enabled", "Thay ký hiệu bằng từ"],
      ["drop_empty_lines", "Bỏ dòng trống"],
    ],
  },
  {
    title: "Chunk & xuất tệp",
    fields: [
      ["min_chunk_chars", "Số ký tự chunk tối thiểu"],
      ["max_chunk_chars", "Số ký tự chunk tối đa"],
      ["chunk_by_chapters", "Chia chunk trong từng chương"],
      ["export_encoding", "Mã hóa tệp xuất"],
      ["filename_template", "Mẫu tên tệp — dùng {tag}"],
      ["zip_include_manifest", "Kèm manifest trong ZIP"],
      ["zip_folder_per_range", "Tạo thư mục ZIP theo khoảng chương"],
    ],
  },
  {
    title: "TTS & intro kênh",
    fields: [
      ["tts_voice", "Giọng Edge-TTS"],
      ["tts_max_concurrency", "Số yêu cầu TTS đồng thời"],
      ["tts_timeout_seconds", "Timeout mỗi yêu cầu (giây)"],
      ["tts_retry_count", "Số lần thử lại"],
      ["channel_intro_enabled", "Bật lời giới thiệu kênh"],
      ["channel_intro_text", "Nội dung intro kênh"],
      ["channel_intro_voice", "Giọng intro (trống = giọng truyện)"],
    ],
  },
  {
    title: "Thumbnail & nhật ký",
    fields: [
      ["thumbnail_jpeg_quality", "Chất lượng thumbnail JPEG"],
      ["qr_image_path", "Ảnh QR mặc định"],
      ["max_log_lines", "Số dòng nhật ký tối đa"],
    ],
  },
];
export function SettingsScreen({ w }: { w: Workspace }) {
  const advanced = w.draft.settingsJson;
  const [jsonError, setJsonError] = useState("");
  const settings = w.draft.settings ?? w.settings;
  if (!settings) return <section className="step-card"><div className="step-head"><h1>Đang tải thiết lập…</h1></div></section>;
  const update = (key: string, value: Settings[string]) => w.setDraft({ settings: { ...settings, [key]: value } });
  const edits = Object.fromEntries(Object.entries(settings).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(w.settings?.[key])));
  const changed = Object.keys(edits).length;
  const saveSettings = async () => {
    const saved = await w.perform(() => api.settingsSave(edits), "Đã lưu thiết lập.");
    if (saved) {
      w.setDraft({ settings: saved });
      await w.refresh();
    }
  };
  return (
    <section className="step-card">
      <header className="step-head"><h1>Thiết lập</h1><p>Chỉ mở phần cần đổi. Áp dụng cho tác vụ chạy sau khi lưu.</p></header>
      <div className="step-body">
        {settingSections.map(section => (
          <details key={section.title} className="settings-section">
            <summary>{section.title}<ChevronDown className="size-4" aria-hidden="true" /></summary>
            <div className="grid gap-4 p-4 md:grid-cols-2">
              {section.fields.filter(([key]) => key in settings).map(([key, label]) => {
                const value = settings[key];
                if (typeof value === "boolean") return <Toggle key={key} label={label} checked={value} disabled={w.busy} onChange={next => update(key, next)} />;
                return (
                  <Field key={key} label={label} hint={key === "tts_voice" ? "Ví dụ vi-VN-HoaiMyNeural hoặc vi-VN-NamMinhNeural." : undefined}>{id => {
                    if (["quote_mode", "bracket_mode"].includes(key))
                      return (
                        <select id={id} className="select" value={String(value)} disabled={w.busy} onChange={event => update(key, event.target.value)}>
                          <option value="keep">Giữ nguyên</option>
                          <option value="strip">Bỏ ký hiệu, giữ nội dung</option>
                          <option value="remove">Loại toàn bộ đoạn</option>
                        </select>
                      );
                    if (Array.isArray(value)) return <Textarea id={id} value={value.join("\n")} disabled={w.busy} onChange={event => update(key, event.target.value.split("\n"))} />;
                    if (key === "channel_intro_text") return <Textarea id={id} value={String(value)} disabled={w.busy} onChange={event => update(key, event.target.value)} />;
                    return (
                      <Input id={id} type={typeof value === "number" ? "number" : "text"} step={typeof value === "number" ? 1 : undefined} value={String(value)} disabled={w.busy}
                        onChange={event => {
                          if (typeof value === "number") {
                            const number = event.target.valueAsNumber;
                            if (Number.isFinite(number)) update(key, number);
                          } else update(key, event.target.value);
                        }} />
                    );
                  }}</Field>
                );
              })}
            </div>
          </details>
        ))}
        <details className="settings-section">
          <summary>YouTube OAuth<ChevronDown className="size-4" aria-hidden="true" /></summary>
          <div className="p-4">
            <AssetField label="OAuth Desktop client JSON" value={String(settings.youtube_client_secrets_path ?? "")} onChange={path => update("youtube_client_secrets_path", path)} workspace={w} accept=".json,application/json" />
          </div>
        </details>
        <More title="Sửa cấu hình JSON đầy đủ">
          <Field label="Settings JSON" hint="Áp dụng vào bản nháp rồi bấm Lưu.">{id => (
            <Textarea id={id} className="min-h-96 font-mono text-sm" value={advanced ?? JSON.stringify(settings, null, 2)} disabled={w.busy}
              onChange={event => { w.setDraft({ settingsJson: event.target.value }); setJsonError(""); }} />
          )}</Field>
          {jsonError && <p role="alert" className="error-box">{jsonError}</p>}
          <Button variant="outline" disabled={w.busy} onClick={() => {
            try {
              w.setDraft({ settings: settingsSchema.parse(JSON.parse(advanced ?? JSON.stringify(settings))), settingsJson: null });
              setJsonError("");
            } catch (cause) {
              setJsonError(cause instanceof Error ? cause.message : String(cause));
            }
          }}><Settings2 aria-hidden="true" />Áp dụng JSON</Button>
        </More>
      </div>
      <footer className="step-foot">
        <span className="step-note">{changed ? `${changed} thay đổi chưa lưu` : "Không có thay đổi"}</span>
        <Button size="lg" disabled={w.busy || !changed} onClick={() => void saveSettings()}><Save aria-hidden="true" />Lưu thiết lập</Button>
      </footer>
    </section>
  );
}

export function SessionsScreen({ w }: { w: Workspace }) {
  return (
    <section className="step-card">
      <header className="step-head"><h1>Phiên làm việc</h1><p>Tự động lưu. Chọn một phiên để làm tiếp.</p></header>
      <div className="step-body">
        {w.sessions.length ? (
          <ul className="session-list">
            {w.sessions.map(session => {
              const current = session.id === w.state?.session_id;
              return (
                <li key={session.id} className={current ? "is-current" : ""}>
                  <FolderOpen className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{session.title || "Chưa đặt tên"}</p>
                    <p className="text-xs text-muted-foreground">{new Date(session.updated_at).toLocaleString("vi-VN")}</p>
                  </div>
                  {current ? <span className="badge">Đang mở</span> : (
                    <Confirm label="Mở" title={`Mở ${session.title || "phiên này"}?`} description="Phiên hiện tại được lưu trước khi chuyển." disabled={w.busy} onConfirm={() => void w.open(session.id)} />
                  )}
                </li>
              );
            })}
          </ul>
        ) : <p className="empty">Chưa có phiên nào. Nhập bản thảo để bắt đầu.</p>}
        {!!w.state?.missing_artifacts.length && (
          <More title={`${w.state.missing_artifacts.length} tệp bị thiếu`}>
            <ul className="space-y-1 text-sm">{w.state.missing_artifacts.map(path => <li key={path} className="break-anywhere">{path}</li>)}</ul>
          </More>
        )}
      </div>
      <footer className="step-foot">
        <Button variant="ghost" disabled={w.busy || !w.state} onClick={() => void w.save()}><Save aria-hidden="true" />Lưu ngay</Button>
        <Confirm variant="default" label="Phiên mới" title="Bắt đầu phiên mới?" description="Phiên hiện tại được lưu trước. Tệp trên ổ đĩa không bị xóa." disabled={w.busy || !w.state} onConfirm={() => void w.open()} />
      </footer>
    </section>
  );
}
