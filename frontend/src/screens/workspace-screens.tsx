import { useState } from "react";
import { Save, Settings2 } from "lucide-react";
import { api } from "@/lib/api";
import type { Settings, Workspace } from "@/lib/types";
import { settingsSchema } from "@/lib/schemas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  AssetField,
  Confirm,
  Field,
  Panel,
  Toggle,
} from "@/components/workflow";

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
      ["font_size", "Cỡ chữ giao diện Qt"],
      ["max_log_lines", "Số dòng nhật ký tối đa"],
    ],
  },
];
export function SettingsScreen({ w }: { w: Workspace }) {
  const advanced = w.draft.settingsJson;
  const [jsonError, setJsonError] = useState("");
  const settings = w.draft.settings ?? w.settings;
  if (!settings)
    return (
      <Panel title="Thiết lập">
        <p className="empty">Đang tải thiết lập từ máy chủ…</p>
      </Panel>
    );
  const update = (key: string, value: Settings[string]) =>
    w.setDraft({ settings: { ...settings, [key]: value } });
  const saveSettings = async () => {
    const edits = Object.fromEntries(
      Object.entries(settings).filter(
        ([key, value]) =>
          JSON.stringify(value) !== JSON.stringify(w.settings?.[key]),
      ),
    );
    const saved = await w.perform(
      () => api.settingsSave(edits),
      "Đã lưu thiết lập.",
    );
    if (saved) {
      w.setDraft({ settings: saved });
      await w.refresh();
    }
  };
  return (
    <div className="space-y-6">
      <Panel
        title="Thiết lập pipeline"
        description="Các thay đổi chỉ có hiệu lực sau khi lưu. Mỗi tác vụ dùng bản thiết lập cố định tại thời điểm bắt đầu; không sửa mặc định desktop chỉ bằng cách mở trang."
      >
        <Button disabled={w.busy} onClick={() => void saveSettings()}>
          <Save aria-hidden="true" />
          Lưu thiết lập
        </Button>
        <p className="text-sm text-muted-foreground">
          Edge-TTS trực tuyến · dữ liệu, đầu ra và phiên được lưu cục bộ.
        </p>
      </Panel>
      {settingSections.map((section) => (
        <Panel key={section.title} title={section.title}>
          <div className="grid gap-5 md:grid-cols-2">
            {section.fields
              .filter(([key]) => key in settings)
              .map(([key, label]) => {
                const value = settings[key];
                if (typeof value === "boolean")
                  return (
                    <Toggle
                      key={key}
                      label={label}
                      checked={value}
                      disabled={w.busy}
                      onChange={(next) => update(key, next)}
                    />
                  );
                return (
                  <Field
                    key={key}
                    label={label}
                    hint={
                      key === "tts_voice"
                        ? "Ví dụ vi-VN-HoaiMyNeural hoặc vi-VN-NamMinhNeural."
                        : undefined
                    }
                  >
                    {(id) => {
                      if (["quote_mode", "bracket_mode"].includes(key))
                        return (
                          <select
                            id={id}
                            className="select"
                            value={String(value)}
                            disabled={w.busy}
                            onChange={(event) =>
                              update(key, event.target.value)
                            }
                          >
                            <option value="keep">Giữ nguyên</option>
                            <option value="strip">
                              Bỏ ký hiệu, giữ nội dung
                            </option>
                            <option value="remove">Loại toàn bộ đoạn</option>
                          </select>
                        );
                      if (Array.isArray(value))
                        return (
                          <Textarea
                            id={id}
                            value={value.join("\n")}
                            disabled={w.busy}
                            onChange={(event) =>
                              update(key, event.target.value.split("\n"))
                            }
                          />
                        );
                      if (key === "channel_intro_text")
                        return (
                          <Textarea
                            id={id}
                            value={String(value)}
                            disabled={w.busy}
                            onChange={(event) =>
                              update(key, event.target.value)
                            }
                          />
                        );
                      return (
                        <Input
                          id={id}
                          type={typeof value === "number" ? "number" : "text"}
                          step={typeof value === "number" ? 1 : undefined}
                          value={String(value)}
                          disabled={w.busy}
                          onChange={(event) => {
                            if (typeof value === "number") {
                              const number = event.target.valueAsNumber;
                              if (Number.isFinite(number)) update(key, number);
                            } else update(key, event.target.value);
                          }}
                        />
                      );
                    }}
                  </Field>
                );
              })}
          </div>
        </Panel>
      ))}
      <Panel title="YouTube OAuth">
        <AssetField
          label="OAuth Desktop client JSON"
          value={String(settings.youtube_client_secrets_path ?? "")}
          onChange={(path) => update("youtube_client_secrets_path", path)}
          workspace={w}
          accept=".json,application/json"
        />
        <p className="text-sm text-muted-foreground">
          Tải client JSON từ Google Cloud cho ứng dụng Desktop. Không dán token
          vào cấu hình.
        </p>
      </Panel>
      <Panel
        title="Cấu hình nâng cao JSON"
        description="Toàn bộ trường hiện có, gồm symbol_map, custom_rules, tts_preprocessing, title_history và các trường tương thích Qt."
      >
        <details>
          <summary className="cursor-pointer font-medium">
            Mở trình soạn cấu hình đầy đủ
          </summary>
          <div className="mt-4 space-y-4">
            <Field
              label="Settings JSON"
              hint="Áp dụng JSON vào bản nháp trước, sau đó Lưu thiết lập. Máy chủ kiểm tra kiểu và trường không được hỗ trợ."
            >
              {(id) => (
                <Textarea
                  id={id}
                  className="min-h-96 font-mono text-sm"
                  value={advanced ?? JSON.stringify(settings, null, 2)}
                  disabled={w.busy}
                  onChange={(event) => {
                    w.setDraft({ settingsJson: event.target.value });
                    setJsonError("");
                  }}
                />
              )}
            </Field>
            {jsonError && (
              <p role="alert" className="error-box">
                {jsonError}
              </p>
            )}
            <Button
              variant="outline"
              disabled={w.busy}
              onClick={() => {
                try {
                  const parsed = settingsSchema.parse(
                    JSON.parse(advanced ?? JSON.stringify(settings)),
                  );
                  w.setDraft({ settings: parsed, settingsJson: null });
                  setJsonError("");
                } catch (cause) {
                  setJsonError(
                    cause instanceof Error ? cause.message : String(cause),
                  );
                }
              }}
            >
              <Settings2 aria-hidden="true" />
              Áp dụng JSON vào bản nháp
            </Button>
          </div>
        </details>
      </Panel>
      <Button disabled={w.busy} onClick={() => void saveSettings()}>
        Lưu tất cả thiết lập
      </Button>
    </div>
  );
}
export function SessionsScreen({ w }: { w: Workspace }) {
  return (
    <div className="space-y-6">
      <Panel
        title="Phiên & bản nháp"
        description="Tự động lưu sau khi bản nháp ổn định và khi pipeline hoàn tất. Phiên giữ đường dẫn đầu ra, lựa chọn nhóm, biểu mẫu và văn bản đang biên tập."
      >
        <p className="break-anywhere text-sm">
          Phiên hiện tại: {w.state?.session_id ?? "Chưa lưu"}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button disabled={w.busy || !w.state} onClick={() => void w.save()}>
            <Save aria-hidden="true" />
            Lưu phiên hiện tại
          </Button>
          <Confirm
            label="Phiên mới"
            title="Bắt đầu phiên mới?"
            description="Bản nháp hiện tại được lưu trước khi mở không gian trống. Các tệp trên ổ đĩa không bị xóa."
            disabled={w.busy || !w.state}
            onConfirm={() => void w.open()}
          />
          <Button
            variant="outline"
            disabled={w.busy}
            onClick={() => void w.refresh()}
          >
            Tải lại danh sách
          </Button>
        </div>
        {w.state?.missing_artifacts.length ? (
          <div className="warning">
            <h3 className="font-medium">Tệp cần khôi phục</h3>
            <ul className="mt-2 space-y-1">
              {w.state.missing_artifacts.map((path) => (
                <li key={path} className="break-anywhere">
                  {path}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Panel>
      <Panel title="Phiên đã lưu">
        {w.sessions.length ? (
          <ul className="divide-y">
            {w.sessions.map((session) => (
              <li
                key={session.id}
                className="flex flex-wrap items-center justify-between gap-3 py-4"
              >
                <div className="min-w-0">
                  <h3 className="font-medium">
                    {session.title || "Bản thảo chưa đặt tên"}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {new Date(session.updated_at).toLocaleString("vi-VN")} ·
                    bước {session.step}
                  </p>
                  <p className="break-anywhere text-xs text-muted-foreground">
                    {session.id}
                  </p>
                </div>
                <Confirm
                  label="Khôi phục"
                  title={`Mở ${session.title || "phiên đã lưu"}?`}
                  description="Phiên hiện tại được lưu trước khi chuyển. Đầu ra được kiểm tra lại theo đường dẫn và fingerprint, tệp thiếu sẽ được cảnh báo."
                  disabled={w.busy || session.id === w.state?.session_id}
                  onConfirm={() => void w.open(session.id)}
                />
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty">
            Chưa có phiên đã lưu. Nhập bản thảo hoặc lưu bản nháp để tạo phiên.
          </p>
        )}
      </Panel>
    </div>
  );
}
