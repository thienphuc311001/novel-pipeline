import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, FileText, WandSparkles } from "lucide-react";
import { api } from "@/lib/api";
import type { Grouping, Workspace } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Confirm,
  Field,
  MediaLink,
  OutputDownloads,
  Panel,
  Toggle,
  UploadIcon,
} from "@/components/workflow";

export function InputScreen({ w }: { w: Workspace }) {
  const paths = w.draft.paths
    .split("\n")
    .map((path) => path.trim())
    .filter(Boolean);
  const move = (index: number, direction: number) => {
    const reordered = [...paths];
    [reordered[index], reordered[index + direction]] = [
      reordered[index + direction],
      reordered[index],
    ];
    w.setDraft({ paths: reordered.join("\n") });
  };
  return (
    <div className="space-y-6">
      <Panel
        title="Đưa bản thảo vào không gian làm việc"
        description="TXT hoặc ZIP. Có thể giữ tệp tại vị trí gốc bằng đường dẫn tuyệt đối; tệp tải lên được lưu bền vững trên máy chủ."
      >
        <Field
          label="Tải bản thảo TXT / ZIP"
          hint="Tải lên chỉ thêm đường dẫn. Kiểm tra thứ tự rồi bấm Nhập bản thảo."
        >
          {(id) => (
            <Input
              id={id}
              type="file"
              multiple
              accept=".txt,.zip"
              disabled={w.busy}
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                if (files.length)
                  void w.perform(async () => {
                    const uploaded = await api.upload("inputs", files);
                    w.setDraft({
                      paths: [...paths, ...uploaded.paths].join("\n"),
                    });
                  }, "Đã tải bản thảo lên. Kiểm tra thứ tự trước khi nhập.");
                event.target.value = "";
              }}
            />
          )}
        </Field>
        <Field
          label="Đường dẫn theo thứ tự lựa chọn"
          hint="Mỗi dòng một đường dẫn tuyệt đối TXT, ZIP hoặc thư mục được backend hỗ trợ."
        >
          {(id) => (
            <Textarea
              id={id}
              rows={5}
              value={w.draft.paths}
              disabled={w.busy}
              onChange={(event) => w.setDraft({ paths: event.target.value })}
              placeholder="/home/user/truyen/chuong-01.txt"
            />
          )}
        </Field>
        {paths.length > 0 && (
          <ol className="space-y-2">
            {paths.map((path, index) => (
              <li
                key={`${index}-${path}`}
                className="flex min-w-0 items-center gap-2 rounded-lg border p-2"
              >
                <span className="text-xs tabular-nums text-muted-foreground">
                  {index + 1}
                </span>
                <span className="break-anywhere min-w-0 flex-1 text-sm">
                  {path}
                </span>
                <Button
                  variant="ghost"
                  aria-label={`Đưa tệp ${index + 1} lên`}
                  disabled={w.busy || index === 0}
                  onClick={() => move(index, -1)}
                >
                  <ArrowUp aria-hidden="true" />
                </Button>
                <Button
                  variant="ghost"
                  aria-label={`Đưa tệp ${index + 1} xuống`}
                  disabled={w.busy || index === paths.length - 1}
                  onClick={() => move(index, 1)}
                >
                  <ArrowDown aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ol>
        )}
        <Field label="Cách sắp xếp khi nhập">
          {(id) => (
            <select
              id={id}
              className="select"
              value={w.draft.sort}
              disabled={w.busy}
              onChange={(event) =>
                w.setDraft({ sort: event.target.value as typeof w.draft.sort })
              }
            >
              <option value="natural">Tự nhiên (1, 2, 10)</option>
              <option value="selection">Giữ thứ tự đã chọn</option>
              <option value="name">Theo tên tệp</option>
            </select>
          )}
        </Field>
        {w.state?.text ? (
          <Confirm
            label="Nhập bản thảo mới"
            title="Thay thế bản thảo hiện tại?"
            description="Nội dung và các đầu ra phụ thuộc hiện tại sẽ không còn là đầu ra hợp lệ của bản thảo mới. Phiên hiện tại được lưu trước khi nhập."
            disabled={w.busy || !paths.length}
            onConfirm={() =>
              void w.run("import", { paths, sort_mode: w.draft.sort })
            }
          />
        ) : (
          <Button
            disabled={w.busy || !paths.length}
            onClick={() =>
              void w.run("import", { paths, sort_mode: w.draft.sort })
            }
          >
            <UploadIcon aria-hidden="true" />
            Nhập bản thảo
          </Button>
        )}
      </Panel>
      <Panel title="Bản thảo đang làm việc">
        {w.state?.text ? (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <p className="eyebrow">Nguồn</p>
                <p className="break-anywhere">
                  {w.state.source_path || "Nhiều tệp"}
                </p>
              </div>
              <div>
                <p className="eyebrow">Tệp nguồn</p>
                <p>{w.state.sources.length}</p>
              </div>
              <div>
                <p className="eyebrow">Ký tự</p>
                <p>{w.state.text.length.toLocaleString("vi-VN")}</p>
              </div>
            </div>
            <details>
              <summary className="cursor-pointer text-sm font-medium">
                Xem nội dung gốc
              </summary>
              <pre className="text-preview mt-3">{w.state.original_text}</pre>
            </details>
            <Button asChild variant="outline">
              <a href="#normalize">Tiếp tục: chuẩn hóa</a>
            </Button>
          </>
        ) : (
          <p className="empty">
            Nhập bản thảo đầu tiên để bắt đầu. Mọi số liệu ở đây lấy từ dữ liệu
            thực.
          </p>
        )}
      </Panel>
    </div>
  );
}
export function NormalizeScreen({ w }: { w: Workspace }) {
  const [preview, setPreview] = useState<Grouping | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [previewPending, setPreviewPending] = useState(false);
  const [numericConfirmed, setNumericConfirmed] = useState(false);
  useEffect(() => {
    setPreview(null);
    setNumericConfirmed(false);
    setPreviewError("");
    if (
      !w.state?.text ||
      w.busy ||
      !Number.isInteger(w.draft.groupSize) ||
      w.draft.groupSize < 1
    )
      return;
    let current = true;
    const timeout = window.setTimeout(() => {
      setPreviewPending(true);
      void api
        .grouping(w.draft.groupSize)
        .then((result) => {
          if (current) setPreview(result);
        })
        .catch((cause) => {
          if (current)
            setPreviewError(
              cause instanceof Error ? cause.message : String(cause),
            );
        })
        .finally(() => {
          if (current) setPreviewPending(false);
        });
    }, 350);
    return () => {
      current = false;
      window.clearTimeout(timeout);
    };
  }, [w.draft.groupSize, w.state?.text, w.busy]);
  const canGroup = Boolean(
    preview &&
      !preview.error &&
      preview.headings.length &&
      w.draft.title.trim() &&
      (!preview.requires_numeric_boundaries ||
        (preview.numeric_available && numericConfirmed)),
  );
  return (
    <div className="space-y-6">
      <Panel
        title="Chuẩn hóa và biên tập"
        description="Chuẩn hóa dùng thiết lập hiện tại. Chỉnh sửa văn bản sẽ làm mất tính hợp lệ của nhóm và các đầu ra phụ thuộc."
      >
        {w.state?.normalized_text !== null && w.state?.text ? (
          <Confirm
            label="Chuẩn hóa lại bản thảo…"
            title="Chuẩn hóa lại từ nội dung gốc?"
            description="Văn bản biên tập hiện tại và các nhóm/đầu ra phụ thuộc sẽ mất tính hợp lệ. Thiết lập hiện tại được dùng để chuẩn hóa lại nguồn gốc."
            disabled={w.busy}
            onConfirm={() => void w.run("normalize")}
          />
        ) : (
          <Button
            disabled={w.busy || !w.state?.text}
            onClick={() => void w.run("normalize")}
          >
            <WandSparkles aria-hidden="true" />
            Chuẩn hóa bản thảo
          </Button>
        )}
        <Field
          label="Văn bản dùng để nhóm chương"
          hint={
            w.state?.normalized_text === null
              ? "Chuẩn hóa trước để mở trình biên tập."
              : `${w.draft.text.length.toLocaleString("vi-VN")} ký tự · bản nháp được lưu trong phiên; bấm Lưu văn bản để áp dụng.`
          }
        >
          {(id) => (
            <Textarea
              id={id}
              className="min-h-80 font-mono text-sm"
              value={w.draft.text}
              disabled={w.busy || !w.state || w.state.normalized_text === null}
              onChange={(event) => w.setDraft({ text: event.target.value })}
            />
          )}
        </Field>
        <Confirm
          label="Lưu văn bản"
          title="Áp dụng văn bản đã chỉnh sửa?"
          description="Các nhóm, âm thanh, video và trạng thái xuất bản phụ thuộc vào văn bản trước sẽ mất tính hợp lệ. Tệp cũ không tự động bị xóa."
          disabled={
            w.busy ||
            !w.state ||
            w.state.normalized_text === null ||
            w.draft.text === w.state.text
          }
          onConfirm={() => void w.run("edit", { text: w.draft.text })}
        />
        {w.state?.diagnostics?.length ? (
          <details open>
            <summary className="font-medium">
              Chẩn đoán ({w.state.diagnostics.length})
            </summary>
            <ul className="mt-3 list-inside list-disc space-y-2 text-sm">
              {w.state.diagnostics.map((item, index) => (
                <li key={index}>{item.message}</li>
              ))}
            </ul>
          </details>
        ) : null}
      </Panel>
      <Panel
        title="Nhóm chương"
        description="Xem trước trực tiếp theo kích thước đã chọn. Nếu số chương bị thiếu/lặp, cần xác nhận biên số trước khi tạo nhóm."
      >
        <div className="grid gap-4 sm:grid-cols-[1fr_10rem]">
          <Field label="Tên truyện / dự án">
            {(id) => (
              <Input
                id={id}
                value={w.draft.title}
                disabled={w.busy}
                onChange={(event) => w.setDraft({ title: event.target.value })}
              />
            )}
          </Field>
          <Field label="Chương mỗi nhóm">
            {(id) => (
              <Input
                id={id}
                type="number"
                min={1}
                step={1}
                value={w.draft.groupSize}
                disabled={w.busy}
                onChange={(event) => {
                  const groupSize = event.target.valueAsNumber;
                  if (
                    Number.isFinite(groupSize) &&
                    groupSize >= 1 &&
                    Number.isInteger(groupSize)
                  )
                    w.setDraft({ groupSize });
                }}
              />
            )}
          </Field>
        </div>
        {w.draft.text !== w.state?.text && (
          <p className="warning">
            Bản nháp chưa áp dụng. Xem trước bên dưới dùng văn bản đã lưu.
          </p>
        )}
        {previewPending && (
          <p role="status" className="text-sm text-muted-foreground">
            Đang phân tích biên chương…
          </p>
        )}
        {(previewError || preview?.error) && (
          <p role="alert" className="error-box">
            {previewError || preview?.error}
          </p>
        )}
        {preview && (
          <>
            <p className="text-sm">
              Phát hiện <strong>{preview.headings.length}</strong> tiêu đề ·{" "}
              <strong>{preview.groups.length}</strong> nhóm dự kiến
            </p>
            {preview.warnings.length > 0 && (
              <ul className="warning space-y-1">
                {preview.warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            )}
            {preview.requires_numeric_boundaries && (
              <div className="warning">
                <p>
                  Số chương không liên tục. Tạo nhóm theo biên số thay vì chỉ
                  đếm tiêu đề.
                </p>
                <Toggle
                  label="Tôi đã kiểm tra các biên số và xác nhận cách chia này"
                  checked={numericConfirmed}
                  onChange={setNumericConfirmed}
                  disabled={w.busy || !preview.numeric_available}
                />
                {!preview.numeric_available && (
                  <p>Không đủ biên hợp lệ. Hãy sửa bản thảo trước.</p>
                )}
              </div>
            )}
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {preview.groups.map((group, index) => (
                <div key={index} className="rounded-md border p-3">
                  <p className="font-medium">
                    {group.label || `Chương ${group.range_label}`}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {group.chapters?.length ?? 0} tiêu đề · ký tự {group.start}–
                    {group.end}
                  </p>
                </div>
              ))}
            </div>
            <details>
              <summary className="cursor-pointer text-sm font-medium">
                Kiểm tra tiêu đề và dòng nguồn
              </summary>
              <ul className="mt-3 max-h-80 overflow-y-auto space-y-1 text-sm">
                {preview.headings.map((heading, index) => (
                  <li key={index}>
                    Dòng {heading.line}: {heading.heading}
                  </li>
                ))}
              </ul>
            </details>
          </>
        )}
        <Confirm
          label="Tạo / thay thế nhóm chương"
          title="Tạo nhóm từ văn bản hiện tại?"
          description="Nhóm mới thay thế các nhóm hiện có. Kiểm tra tên truyện, kích thước và biên chương ở trên trước khi tiếp tục."
          disabled={w.busy || !canGroup}
          onConfirm={() =>
            void w.run("group", {
              title: w.draft.title.trim(),
              size: w.draft.groupSize,
              method: preview?.requires_numeric_boundaries
                ? "numeric_boundaries"
                : "detected_chapters",
              confirmation_fingerprint: preview?.confirmation_fingerprint ?? "",
            })
          }
        />
      </Panel>
      <Panel
        title="Xuất văn bản"
        description="Tạo tệp bằng pipeline thật; tải xuống qua danh sách đầu ra được phép."
      >
        <div className="flex flex-wrap gap-2">
          {(["txt", "json", "zip"] as const).map((format) => (
            <Button
              key={format}
              variant="outline"
              disabled={w.busy || !w.state?.text}
              onClick={() => void w.run("export", { format })}
            >
              <FileText aria-hidden="true" />
              Xuất {format.toUpperCase()}
            </Button>
          ))}
        </div>
        <OutputDownloads files={w.state?.outputs ?? []} />
      </Panel>
      {w.state?.groups.map((group) => (
        <Panel
          key={group.group_id}
          title={group.label}
          aside={
            <Confirm
              label="Xóa nhóm"
              title={`Xóa ${group.label}?`}
              description="Nhóm sẽ bị loại khỏi phiên và các hàng đợi; tệp đầu ra đã tạo không bị xóa khỏi ổ đĩa."
              disabled={w.busy}
              onConfirm={() =>
                void w.run("delete_group", { group_id: group.group_id })
              }
            />
          }
        >
          <MediaLink path={group.txt_path} label="Tải văn bản nhóm" />
        </Panel>
      ))}
    </div>
  );
}
