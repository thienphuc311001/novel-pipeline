import { z } from "zod";
import type {
  Draft,
  Group,
  Grouping,
  Job,
  LogLine,
  Metadata,
  OutputFile,
  Session,
  Settings,
  Snapshot,
} from "./types";

type ResponseSchema<T> = z.ZodType<T, z.ZodTypeDef, unknown>;
const object = z.record(z.unknown());
export const metadataSchema: ResponseSchema<Metadata> = z.object({
  title: z.string(),
  description: z.string().default(""),
  tags: z.array(z.string()).default([]),
  category_id: z.string().default("22"),
  privacy: z.enum(["private", "unlisted", "public"]).default("private"),
  made_for_kids: z.boolean().default(false),
  contains_synthetic_media: z.boolean().default(false),
  playlist_id: z.string().nullable().default(null),
  publish_at: z.string().nullable().default(null),
});
export const settingsSchema: ResponseSchema<Settings> = z.record(
  z.union([
    z.string(),
    z.number(),
    z.boolean(),
    z.array(z.string()),
    object,
    z.array(object),
  ]),
);
const groupSchema: ResponseSchema<Group> = z
  .object({
    group_id: z.string(),
    order: z.number(),
    label: z.string(),
    range_label: z.string(),
    title: z.string(),
    output_dir: z.string(),
    txt_path: z.string(),
    start: z.number(),
    end: z.number(),
    chapters: z.array(
      z
        .object({
          heading: z.string().optional(),
          number: z.number().optional(),
          start: z.number().optional(),
          end: z.number().optional(),
        })
        .passthrough(),
    ),
    state: z
      .object({
        tts_status: z.string().optional(),
        last_error: z.string().optional(),
        failures: z
          .array(
            z
              .object({
                chunk_number: z.number(),
                original_text: z.string(),
                failed_part_text: z.string().optional(),
                error_type: z.string(),
                error_message: z.string(),
              })
              .passthrough(),
          )
          .optional(),
        successful_orders: z.array(z.number()).optional(),
        excluded_chunks: z.array(z.number()).optional(),
        tts_plan: z
          .object({
            chunks: z
              .array(
                z
                  .object({
                    order: z.number(),
                    text: z.string(),
                    chapter: z.number().optional(),
                  })
                  .passthrough(),
              )
              .optional(),
            plan_id: z.string().optional(),
          })
          .passthrough()
          .optional(),
        thumbnail: z.object({ path: z.string() }).passthrough().optional(),
        audiobook: z.object({ path: z.string() }).passthrough().optional(),
        video: z.object({ path: z.string() }).passthrough().optional(),
        youtube: z
          .object({
            status: z.string().optional(),
            video_id: z.string().optional(),
            metadata: metadataSchema.optional(),
            updated_metadata: metadataSchema.optional(),
            thumbnail_uploaded: z.boolean().optional(),
            playlist_added: z.boolean().optional(),
          })
          .passthrough()
          .optional(),
      })
      .passthrough(),
  })
  .passthrough();
export const groupingSchema: ResponseSchema<Grouping> = z.object({
  headings: z
    .array(
      z
        .object({
          number: z.number(),
          heading: z.string(),
          line: z.number(),
          start: z.number(),
          end: z.number(),
        })
        .passthrough(),
    )
    .default([]),
  groups: z
    .array(
      z
        .object({
          label: z.string().optional(),
          range_label: z.string(),
          chapters: z.array(z.unknown()).optional(),
          start: z.number(),
          end: z.number(),
        })
        .passthrough(),
    )
    .default([]),
  warnings: z.array(z.string()).default([]),
  requires_numeric_boundaries: z.boolean().default(false),
  numeric_available: z.boolean().default(false),
  confirmation_fingerprint: z.string().default(""),
  error: z.string().optional(),
});
export const outputSchema: ResponseSchema<OutputFile> = z.object({
  path: z.string(),
  name: z.string(),
  size: z.number(),
});
export const snapshotSchema: ResponseSchema<Snapshot> = z.object({
  title: z.string(),
  source_path: z.string(),
  input_directory: z.string(),
  original_text: z.string(),
  normalized_text: z.string().nullable(),
  text: z.string(),
  youtube_tags: z.object({
    current: z.array(z.string()).nullable(),
    history: z.record(z.array(z.string())),
  }),
  chapters: z.array(z.unknown()),
  sources: z.array(object),
  groups: z.array(groupSchema),
  stages: z.record(
    z
      .object({ status: z.string().optional(), message: z.string().optional() })
      .passthrough(),
  ),
  diagnostics: z.array(
    z
      .object({ message: z.string(), severity: z.string().optional() })
      .passthrough(),
  ),
  grouping: groupingSchema,
  outputs: z.array(outputSchema),
  session_id: z.string().nullable(),
  ui_state: object,
  missing_artifacts: z.array(z.string()),
});
export const jobSchema: ResponseSchema<Job> = z.object({
  id: z.string(),
  action: z.string(),
  status: z.enum([
    "queued",
    "running",
    "stopping",
    "completed",
    "failed",
    "cancelled",
  ]),
  created_at: z.string(),
  finished_at: z.string().nullable(),
  progress: z.object({
    done: z.number(),
    total: z.number(),
    message: z.string(),
  }),
  error: z.string().nullable(),
  result: object.nullable(),
});
export const sessionSchema: ResponseSchema<Session> = z.object({
  id: z.string(),
  title: z.string(),
  updated_at: z.string(),
  step: z.union([z.string(), z.number()]),
});
export const logSchema: ResponseSchema<LogLine> = z.object({
  sequence: z.number(),
  timestamp: z.string(),
  level: z.string(),
  message: z.string(),
});
export const screenSchema = z.enum([
  "input",
  "normalize",
  "tts",
  "video",
  "youtube",
  "sessions",
  "settings",
]);
export const draftSchema: ResponseSchema<Partial<Draft>> = z.object({
  screen: screenSchema.optional(),
  paths: z.string().optional(),
  sort: z.enum(["natural", "selection", "name"]).optional(),
  title: z.string().optional(),
  groupSize: z.number().int().positive().optional(),
  text: z.string().optional(),
  thumbnail: z.string().optional(),
  cover: z.string().optional(),
  qr: z.string().optional(),
  selected: z.array(z.string()).optional(),
  metadata: metadataSchema.optional(),
  titles: z.record(z.string()).optional(),
  chunkEdits: z.record(z.string()).optional(),
  settings: settingsSchema.nullable().optional(),
  settingsJson: z.string().nullable().optional(),
  tagsText: z.string().optional(),
  tagsEdited: z.boolean().optional(),
});
export const eventSchema = z.object({
  state: snapshotSchema.optional(),
  jobs: z.array(jobSchema),
  state_revision: z.number().optional(),
});
export const pathsSchema = z.object({ paths: z.array(z.string()) });
export const savedSessionSchema = z.object({ id: z.string() });
