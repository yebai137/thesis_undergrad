#include "elevator_batch.h"

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

typedef struct elevator_batch_curve_point {
    float score;
    uint8_t is_true_positive;
} elevator_batch_curve_point;

typedef struct elevator_batch_class_eval {
    elevator_batch_curve_point *points;
    size_t point_count;
    size_t point_capacity;
} elevator_batch_class_eval;

struct elevator_batch_eval_context {
    elevator_batch_summary summary;
    elevator_batch_class_eval classes[ELEVATOR_BATCH_CLASS_COUNT];
};

static const char *g_elevator_batch_class_names[ELEVATOR_BATCH_CLASS_COUNT] = {
    "person",
    "ebike",
};

static void elevator_batch_timing_add(elevator_frame_timing *dst, const elevator_frame_timing *src)
{
    if (dst == NULL || src == NULL) {
        return;
    }

    dst->frame_proc_ms += src->frame_proc_ms;
    dst->prepare_ms += src->prepare_ms;
    dst->preprocess_ms += src->preprocess_ms;
    dst->input_update_ms += src->input_update_ms;
    dst->model_execute_ms += src->model_execute_ms;
    dst->output_fetch_ms += src->output_fetch_ms;
    dst->postprocess_ms += src->postprocess_ms;
    dst->temporal_ms += src->temporal_ms;
    dst->render_prepare_ms += src->render_prepare_ms;
    dst->render_ms += src->render_ms;
    dst->osd_ms += src->osd_ms;
}

static void elevator_batch_timing_average(elevator_frame_timing *dst,
    const elevator_frame_timing *src, uint64_t count)
{
    if (dst == NULL || src == NULL || count == 0) {
        return;
    }

    dst->frame_proc_ms = src->frame_proc_ms / (double)count;
    dst->prepare_ms = src->prepare_ms / (double)count;
    dst->preprocess_ms = src->preprocess_ms / (double)count;
    dst->input_update_ms = src->input_update_ms / (double)count;
    dst->model_execute_ms = src->model_execute_ms / (double)count;
    dst->output_fetch_ms = src->output_fetch_ms / (double)count;
    dst->postprocess_ms = src->postprocess_ms / (double)count;
    dst->temporal_ms = src->temporal_ms / (double)count;
    dst->render_prepare_ms = src->render_prepare_ms / (double)count;
    dst->render_ms = src->render_ms / (double)count;
    dst->osd_ms = src->osd_ms / (double)count;
}

static int elevator_batch_write_timing_json(FILE *stream, const elevator_frame_timing *timing)
{
    if (stream == NULL || timing == NULL) {
        return -1;
    }

    return fprintf(stream,
        "{\"frame_proc_ms\":%.3f,\"prepare_ms\":%.3f,\"preprocess_ms\":%.3f,"
        "\"input_update_ms\":%.3f,\"model_execute_ms\":%.3f,\"output_fetch_ms\":%.3f,"
        "\"postprocess_ms\":%.3f,\"temporal_ms\":%.3f,\"render_prepare_ms\":%.3f,"
        "\"render_ms\":%.3f,\"osd_ms\":%.3f}",
        timing->frame_proc_ms, timing->prepare_ms, timing->preprocess_ms,
        timing->input_update_ms, timing->model_execute_ms, timing->output_fetch_ms,
        timing->postprocess_ms, timing->temporal_ms, timing->render_prepare_ms,
        timing->render_ms, timing->osd_ms) < 0 ? -1 : 0;
}

static uint32_t elevator_batch_clip_u32(int64_t value)
{
    if (value < 0) {
        return 0;
    }
    if ((uint64_t)value > UINT32_MAX) {
        return UINT32_MAX;
    }
    return (uint32_t)value;
}

static uint32_t elevator_batch_round_u32(double value)
{
    if (!isfinite(value) || value <= 0.0) {
        return 0;
    }
    return elevator_batch_clip_u32((int64_t)llround(value));
}

static int elevator_batch_has_jpeg_extension(const char *name)
{
    const char *ext;

    if (name == NULL) {
        return 0;
    }
    ext = strrchr(name, '.');
    if (ext == NULL) {
        return 0;
    }
    return (strcasecmp(ext, ".jpg") == 0 || strcasecmp(ext, ".jpeg") == 0) ? 1 : 0;
}

static int elevator_batch_compare_items(const void *lhs, const void *rhs)
{
    const elevator_batch_image_item *left = (const elevator_batch_image_item *)lhs;
    const elevator_batch_image_item *right = (const elevator_batch_image_item *)rhs;

    return strcmp(left->image_name, right->image_name);
}

static int elevator_batch_make_parent_dirs(const char *path)
{
    char temp[512];
    size_t len;
    size_t idx;

    if (path == NULL) {
        return -1;
    }

    len = strlen(path);
    if (len == 0 || len >= sizeof(temp)) {
        return -1;
    }

    memcpy(temp, path, len + 1);
    for (idx = 1; idx < len; ++idx) {
        if (temp[idx] != '/') {
            continue;
        }
        temp[idx] = '\0';
        if (mkdir(temp, 0755) != 0 && errno != EEXIST) {
            return -1;
        }
        temp[idx] = '/';
    }

    if (mkdir(temp, 0755) != 0 && errno != EEXIST) {
        return -1;
    }
    return 0;
}

static int elevator_batch_join_path(char *dst, size_t dst_size, const char *lhs, const char *rhs)
{
    int needs_slash;

    if (dst == NULL || lhs == NULL || rhs == NULL) {
        return -1;
    }

    needs_slash = (lhs[0] != '\0' && lhs[strlen(lhs) - 1] != '/') ? 1 : 0;
    if (snprintf(dst, dst_size, "%s%s%s", lhs, needs_slash ? "/" : "", rhs) >= (int)dst_size) {
        return -1;
    }
    return 0;
}

static int elevator_batch_basename_stem(const char *name, char *stem, size_t stem_size)
{
    const char *ext;
    size_t len;

    if (name == NULL || stem == NULL || stem_size == 0) {
        return -1;
    }

    ext = strrchr(name, '.');
    len = (ext != NULL) ? (size_t)(ext - name) : strlen(name);
    if (len + 1 > stem_size) {
        return -1;
    }
    memcpy(stem, name, len);
    stem[len] = '\0';
    return 0;
}

static float elevator_batch_rect_iou(const elevator_rect *lhs, const elevator_rect *rhs)
{
    uint32_t inter_x1;
    uint32_t inter_y1;
    uint32_t inter_x2;
    uint32_t inter_y2;
    uint32_t inter_width;
    uint32_t inter_height;
    uint64_t inter_area;
    uint64_t lhs_area;
    uint64_t rhs_area;
    uint64_t union_area;

    if (lhs == NULL || rhs == NULL) {
        return 0.0f;
    }

    inter_x1 = (lhs->x1 > rhs->x1) ? lhs->x1 : rhs->x1;
    inter_y1 = (lhs->y1 > rhs->y1) ? lhs->y1 : rhs->y1;
    inter_x2 = (lhs->x2 < rhs->x2) ? lhs->x2 : rhs->x2;
    inter_y2 = (lhs->y2 < rhs->y2) ? lhs->y2 : rhs->y2;
    if (inter_x2 <= inter_x1 || inter_y2 <= inter_y1) {
        return 0.0f;
    }

    inter_width = inter_x2 - inter_x1;
    inter_height = inter_y2 - inter_y1;
    inter_area = (uint64_t)inter_width * (uint64_t)inter_height;
    lhs_area = (uint64_t)(lhs->x2 - lhs->x1) * (uint64_t)(lhs->y2 - lhs->y1);
    rhs_area = (uint64_t)(rhs->x2 - rhs->x1) * (uint64_t)(rhs->y2 - rhs->y1);
    union_area = lhs_area + rhs_area - inter_area;
    if (union_area == 0) {
        return 0.0f;
    }
    return (float)inter_area / (float)union_area;
}

static int elevator_batch_append_curve_point(elevator_batch_class_eval *cls, float score, uint8_t is_tp)
{
    elevator_batch_curve_point *grown;
    size_t next_capacity;

    if (cls == NULL) {
        return -1;
    }

    if (cls->point_count == cls->point_capacity) {
        next_capacity = (cls->point_capacity == 0) ? 64 : cls->point_capacity * 2;
        grown = (elevator_batch_curve_point *)realloc(cls->points,
            next_capacity * sizeof(elevator_batch_curve_point));
        if (grown == NULL) {
            return -1;
        }
        cls->points = grown;
        cls->point_capacity = next_capacity;
    }

    cls->points[cls->point_count].score = score;
    cls->points[cls->point_count].is_true_positive = is_tp;
    cls->point_count++;
    return 0;
}

static int elevator_batch_compare_curve_desc(const void *lhs, const void *rhs)
{
    const elevator_batch_curve_point *left = (const elevator_batch_curve_point *)lhs;
    const elevator_batch_curve_point *right = (const elevator_batch_curve_point *)rhs;

    if (left->score < right->score) {
        return 1;
    }
    if (left->score > right->score) {
        return -1;
    }
    if (left->is_true_positive < right->is_true_positive) {
        return 1;
    }
    if (left->is_true_positive > right->is_true_positive) {
        return -1;
    }
    return 0;
}

static double elevator_batch_compute_ap50(const elevator_batch_class_eval *cls, uint64_t gt_total)
{
    double *precision = NULL;
    double *recall = NULL;
    double ap = 0.0;
    uint64_t cum_tp = 0;
    uint64_t cum_fp = 0;
    size_t idx;

    if (cls == NULL || gt_total == 0 || cls->point_count == 0) {
        return 0.0;
    }

    precision = (double *)calloc(cls->point_count, sizeof(double));
    recall = (double *)calloc(cls->point_count, sizeof(double));
    if (precision == NULL || recall == NULL) {
        free(precision);
        free(recall);
        return 0.0;
    }

    for (idx = 0; idx < cls->point_count; ++idx) {
        if (cls->points[idx].is_true_positive != 0) {
            cum_tp++;
        } else {
            cum_fp++;
        }
        precision[idx] = (cum_tp + cum_fp) == 0 ? 0.0 : (double)cum_tp / (double)(cum_tp + cum_fp);
        recall[idx] = (double)cum_tp / (double)gt_total;
    }

    for (idx = cls->point_count; idx > 1; --idx) {
        if (precision[idx - 2] < precision[idx - 1]) {
            precision[idx - 2] = precision[idx - 1];
        }
    }

    for (idx = 0; idx <= 100; ++idx) {
        double threshold = (double)idx / 100.0;
        double best_precision = 0.0;
        size_t point_idx;

        for (point_idx = 0; point_idx < cls->point_count; ++point_idx) {
            if (recall[point_idx] >= threshold && precision[point_idx] > best_precision) {
                best_precision = precision[point_idx];
            }
        }
        ap += best_precision;
    }

    free(precision);
    free(recall);
    return ap / 101.0;
}

static void elevator_batch_json_write_string(FILE *stream, const char *value)
{
    const unsigned char *cursor = (const unsigned char *)value;

    fputc('"', stream);
    if (cursor != NULL) {
        while (*cursor != '\0') {
            switch (*cursor) {
                case '\\':
                case '"':
                    fputc('\\', stream);
                    fputc((int)*cursor, stream);
                    break;
                case '\n':
                    fputs("\\n", stream);
                    break;
                case '\r':
                    fputs("\\r", stream);
                    break;
                case '\t':
                    fputs("\\t", stream);
                    break;
                default:
                    if (*cursor < 0x20U) {
                        fprintf(stream, "\\u%04x", (unsigned int)*cursor);
                    } else {
                        fputc((int)*cursor, stream);
                    }
                    break;
            }
            cursor++;
        }
    }
    fputc('"', stream);
}

int elevator_batch_collect_images(const char *images_dir, const char *labels_dir, uint32_t offset, uint32_t limit,
    elevator_batch_image_list *list, char *errbuf, size_t errbuf_size)
{
    DIR *dir = NULL;
    struct dirent *entry;
    elevator_batch_image_item *items = NULL;
    elevator_batch_image_item *selected_items = NULL;
    size_t count = 0;
    size_t capacity = 0;
    size_t start_idx;
    size_t selected_count;

    if (errbuf != NULL && errbuf_size > 0) {
        errbuf[0] = '\0';
    }
    if (images_dir == NULL || labels_dir == NULL || list == NULL) {
        return -1;
    }

    memset(list, 0, sizeof(*list));
    dir = opendir(images_dir);
    if (dir == NULL) {
        if (errbuf != NULL && errbuf_size > 0) {
            snprintf(errbuf, errbuf_size, "failed to open images dir: %s", images_dir);
        }
        return -1;
    }

    while ((entry = readdir(dir)) != NULL) {
        char stem[512];

        if (entry->d_name[0] == '.') {
            continue;
        }
        if (elevator_batch_has_jpeg_extension(entry->d_name) == 0) {
            continue;
        }
        if (count == capacity) {
            size_t next_capacity = (capacity == 0) ? 64 : capacity * 2;
            elevator_batch_image_item *grown =
                (elevator_batch_image_item *)realloc(items, next_capacity * sizeof(*items));
            if (grown == NULL) {
                closedir(dir);
                free(items);
                if (errbuf != NULL && errbuf_size > 0) {
                    snprintf(errbuf, errbuf_size, "out of memory while collecting images");
                }
                return -1;
            }
            items = grown;
            capacity = next_capacity;
        }

        memset(&items[count], 0, sizeof(items[count]));
        snprintf(items[count].image_name, sizeof(items[count].image_name), "%s", entry->d_name);
        if (elevator_batch_join_path(items[count].image_path, sizeof(items[count].image_path),
                images_dir, entry->d_name) != 0) {
            closedir(dir);
            free(items);
            if (errbuf != NULL && errbuf_size > 0) {
                snprintf(errbuf, errbuf_size, "image path too long: %s", entry->d_name);
            }
            return -1;
        }
        if (elevator_batch_basename_stem(entry->d_name, stem, sizeof(stem)) != 0 ||
            snprintf(items[count].label_path, sizeof(items[count].label_path), "%s/%s.txt",
                labels_dir, stem) >= (int)sizeof(items[count].label_path)) {
            closedir(dir);
            free(items);
            if (errbuf != NULL && errbuf_size > 0) {
                snprintf(errbuf, errbuf_size, "label path too long: %s", entry->d_name);
            }
            return -1;
        }
        count++;
    }
    closedir(dir);

    qsort(items, count, sizeof(*items), elevator_batch_compare_items);
    start_idx = offset < count ? offset : count;
    selected_count = count - start_idx;
    if (limit != 0 && selected_count > limit) {
        selected_count = limit;
    }

    if (selected_count != count) {
        if (selected_count != 0) {
            selected_items = (elevator_batch_image_item *)malloc(selected_count * sizeof(*selected_items));
            if (selected_items == NULL) {
                free(items);
                if (errbuf != NULL && errbuf_size > 0) {
                    snprintf(errbuf, errbuf_size, "out of memory while slicing image list");
                }
                return -1;
            }
            memcpy(selected_items, items + start_idx, selected_count * sizeof(*selected_items));
        }
        free(items);
        items = selected_items;
    }

    list->items = items;
    list->count = selected_count;
    return 0;
}

void elevator_batch_free_image_list(elevator_batch_image_list *list)
{
    if (list == NULL) {
        return;
    }
    free(list->items);
    list->items = NULL;
    list->count = 0;
}

int elevator_batch_make_output_dir(const char *configured_output_dir, char *output_dir,
    size_t output_dir_size, char *errbuf, size_t errbuf_size)
{
    time_t now;
    struct tm local_tm;
    char timestamp[32];

    if (errbuf != NULL && errbuf_size > 0) {
        errbuf[0] = '\0';
    }
    if (output_dir == NULL || output_dir_size == 0) {
        return -1;
    }

    if (configured_output_dir != NULL && configured_output_dir[0] != '\0') {
        if (snprintf(output_dir, output_dir_size, "%s", configured_output_dir) >= (int)output_dir_size) {
            if (errbuf != NULL && errbuf_size > 0) {
                snprintf(errbuf, errbuf_size, "output dir is too long");
            }
            return -1;
        }
    } else {
        now = time(NULL);
        if (localtime_r(&now, &local_tm) == NULL) {
            if (errbuf != NULL && errbuf_size > 0) {
                snprintf(errbuf, errbuf_size, "failed to get local time");
            }
            return -1;
        }
        if (strftime(timestamp, sizeof(timestamp), "%Y%m%d_%H%M%S", &local_tm) == 0) {
            if (errbuf != NULL && errbuf_size > 0) {
                snprintf(errbuf, errbuf_size, "failed to format output timestamp");
            }
            return -1;
        }
        if (snprintf(output_dir, output_dir_size, "/userdata/elevator_ai/runs/batch_%s", timestamp) >=
            (int)output_dir_size) {
            if (errbuf != NULL && errbuf_size > 0) {
                snprintf(errbuf, errbuf_size, "generated output dir is too long");
            }
            return -1;
        }
    }

    if (elevator_batch_make_parent_dirs(output_dir) != 0) {
        if (errbuf != NULL && errbuf_size > 0) {
            snprintf(errbuf, errbuf_size, "failed to create output dir: %s", output_dir);
        }
        return -1;
    }
    return 0;
}

int elevator_batch_load_yolo_labels(const char *label_path, uint32_t frame_width, uint32_t frame_height,
    elevator_batch_gt_box *boxes, size_t max_boxes, size_t *box_count, char *errbuf, size_t errbuf_size)
{
    FILE *stream = NULL;
    char line[256];
    size_t count = 0;

    if (errbuf != NULL && errbuf_size > 0) {
        errbuf[0] = '\0';
    }
    if (label_path == NULL || boxes == NULL || box_count == NULL || frame_width == 0 || frame_height == 0) {
        return -1;
    }

    stream = fopen(label_path, "r");
    if (stream == NULL) {
        if (errbuf != NULL && errbuf_size > 0) {
            snprintf(errbuf, errbuf_size, "failed to open label file: %s", label_path);
        }
        return -1;
    }

    while (fgets(line, sizeof(line), stream) != NULL) {
        unsigned int class_id = 0;
        double xc = 0.0;
        double yc = 0.0;
        double w = 0.0;
        double h = 0.0;
        double x1;
        double y1;
        double x2;
        double y2;

        if (line[0] == '\n' || line[0] == '\r' || line[0] == '#') {
            continue;
        }
        if (sscanf(line, "%u %lf %lf %lf %lf", &class_id, &xc, &yc, &w, &h) != 5) {
            fclose(stream);
            if (errbuf != NULL && errbuf_size > 0) {
                snprintf(errbuf, errbuf_size, "invalid label line in %s", label_path);
            }
            return -1;
        }
        if (class_id >= ELEVATOR_BATCH_CLASS_COUNT) {
            continue;
        }
        if (count >= max_boxes) {
            fclose(stream);
            if (errbuf != NULL && errbuf_size > 0) {
                snprintf(errbuf, errbuf_size, "too many gt boxes in %s", label_path);
            }
            return -1;
        }

        x1 = (xc - w / 2.0) * (double)frame_width;
        y1 = (yc - h / 2.0) * (double)frame_height;
        x2 = (xc + w / 2.0) * (double)frame_width;
        y2 = (yc + h / 2.0) * (double)frame_height;
        boxes[count].class_id = class_id;
        boxes[count].rect.x1 = elevator_batch_round_u32(x1);
        boxes[count].rect.y1 = elevator_batch_round_u32(y1);
        boxes[count].rect.x2 = elevator_batch_round_u32(x2);
        boxes[count].rect.y2 = elevator_batch_round_u32(y2);
        if (boxes[count].rect.x2 > frame_width) {
            boxes[count].rect.x2 = frame_width;
        }
        if (boxes[count].rect.y2 > frame_height) {
            boxes[count].rect.y2 = frame_height;
        }
        count++;
    }

    fclose(stream);
    *box_count = count;
    return 0;
}

elevator_batch_eval_context *elevator_batch_eval_create(void)
{
    elevator_batch_eval_context *ctx =
        (elevator_batch_eval_context *)calloc(1, sizeof(elevator_batch_eval_context));

    return ctx;
}

void elevator_batch_eval_destroy(elevator_batch_eval_context *ctx)
{
    size_t class_id;

    if (ctx == NULL) {
        return;
    }
    for (class_id = 0; class_id < ELEVATOR_BATCH_CLASS_COUNT; ++class_id) {
        free(ctx->classes[class_id].points);
        ctx->classes[class_id].points = NULL;
        ctx->classes[class_id].point_count = 0;
        ctx->classes[class_id].point_capacity = 0;
    }
    free(ctx);
}

int elevator_batch_eval_image(elevator_batch_eval_context *ctx, const elevator_batch_gt_box *gt_boxes,
    size_t gt_count, const elevator_detection_result *detections, size_t detection_count, float iou_threshold,
    elevator_batch_image_report *report)
{
    size_t class_id;

    if (ctx == NULL || report == NULL || gt_boxes == NULL || detections == NULL) {
        return -1;
    }

    for (class_id = 0; class_id < ELEVATOR_BATCH_CLASS_COUNT; ++class_id) {
        size_t pred_count = 0;
        size_t gt_count_class = 0;
        size_t pred_idx;
        size_t gt_idx;
        size_t matched_gt_count = 0;
        size_t gt_indices[ELEVATOR_BATCH_MAX_LABELS];
        uint8_t gt_matched[ELEVATOR_BATCH_MAX_LABELS];
        elevator_detection_result preds[ELEVATOR_MAX_DETECTIONS];

        memset(gt_indices, 0, sizeof(gt_indices));
        memset(gt_matched, 0, sizeof(gt_matched));
        for (gt_idx = 0; gt_idx < gt_count; ++gt_idx) {
            if (gt_boxes[gt_idx].class_id != class_id) {
                continue;
            }
            if (gt_count_class >= ELEVATOR_BATCH_MAX_LABELS) {
                return -1;
            }
            gt_indices[gt_count_class++] = gt_idx;
        }

        for (pred_idx = 0; pred_idx < detection_count; ++pred_idx) {
            if (detections[pred_idx].class_id != class_id) {
                continue;
            }
            if (pred_count >= ELEVATOR_MAX_DETECTIONS) {
                return -1;
            }
            preds[pred_count++] = detections[pred_idx];
        }

        report->gt_count[class_id] = (uint32_t)gt_count_class;
        report->pred_count[class_id] = (uint32_t)pred_count;
        ctx->summary.classes[class_id].gt += gt_count_class;
        ctx->summary.classes[class_id].pred += pred_count;

        for (pred_idx = 0; pred_idx < pred_count; ++pred_idx) {
            float best_iou = 0.0f;
            size_t best_gt_idx = SIZE_MAX;

            for (gt_idx = 0; gt_idx < gt_count_class; ++gt_idx) {
                float iou;

                if (gt_matched[gt_idx] != 0) {
                    continue;
                }
                iou = elevator_batch_rect_iou(&preds[pred_idx].rect, &gt_boxes[gt_indices[gt_idx]].rect);
                if (iou > best_iou) {
                    best_iou = iou;
                    best_gt_idx = gt_idx;
                }
            }

            if (best_gt_idx != SIZE_MAX && best_iou >= iou_threshold) {
                gt_matched[best_gt_idx] = 1;
                matched_gt_count++;
                report->tp[class_id]++;
                ctx->summary.classes[class_id].tp++;
                if (elevator_batch_append_curve_point(&ctx->classes[class_id], preds[pred_idx].score, 1) != 0) {
                    return -1;
                }
            } else {
                report->fp[class_id]++;
                ctx->summary.classes[class_id].fp++;
                if (elevator_batch_append_curve_point(&ctx->classes[class_id], preds[pred_idx].score, 0) != 0) {
                    return -1;
                }
            }
        }

        report->fn[class_id] = (uint32_t)(gt_count_class - matched_gt_count);
        ctx->summary.classes[class_id].fn += report->fn[class_id];
    }

    report->success = 1;
    ctx->summary.success_count++;
    ctx->summary.image_count++;
    return 0;
}

void elevator_batch_eval_mark_failure(elevator_batch_eval_context *ctx, elevator_batch_image_report *report)
{
    if (ctx == NULL || report == NULL) {
        return;
    }
    report->success = 0;
    ctx->summary.failure_count++;
    ctx->summary.image_count++;
}

void elevator_batch_eval_note_run(elevator_batch_eval_context *ctx, double elapsed_ms, int fallback_used)
{
    if (ctx == NULL) {
        return;
    }
    ctx->summary.total_elapsed_ms += elapsed_ms;
    if (fallback_used != 0) {
        ctx->summary.fallback_count++;
    }
}

void elevator_batch_eval_note_timing(elevator_batch_eval_context *ctx, const elevator_frame_timing *timing_ms)
{
    if (ctx == NULL || timing_ms == NULL) {
        return;
    }
    elevator_batch_timing_add(&ctx->summary.total_timing_ms, timing_ms);
}

void elevator_batch_eval_finalize(elevator_batch_eval_context *ctx, elevator_batch_summary *summary)
{
    size_t class_id;

    if (ctx == NULL || summary == NULL) {
        return;
    }

    if (ctx->summary.success_count != 0) {
        ctx->summary.average_elapsed_ms = ctx->summary.total_elapsed_ms / (double)ctx->summary.success_count;
        elevator_batch_timing_average(&ctx->summary.average_timing_ms, &ctx->summary.total_timing_ms,
            ctx->summary.success_count);
    }

    for (class_id = 0; class_id < ELEVATOR_BATCH_CLASS_COUNT; ++class_id) {
        elevator_batch_class_summary *cls = &ctx->summary.classes[class_id];

        if (ctx->classes[class_id].point_count != 0) {
            qsort(ctx->classes[class_id].points, ctx->classes[class_id].point_count,
                sizeof(ctx->classes[class_id].points[0]), elevator_batch_compare_curve_desc);
        }

        if (cls->tp + cls->fp != 0) {
            cls->precision = (double)cls->tp / (double)(cls->tp + cls->fp);
        }
        if (cls->tp + cls->fn != 0) {
            cls->recall = (double)cls->tp / (double)(cls->tp + cls->fn);
        }
        if (cls->precision + cls->recall > 0.0) {
            cls->f1 = (2.0 * cls->precision * cls->recall) / (cls->precision + cls->recall);
        }
        cls->ap50 = elevator_batch_compute_ap50(&ctx->classes[class_id], cls->gt);
        ctx->summary.map50 += cls->ap50;
    }
    ctx->summary.map50 /= (double)ELEVATOR_BATCH_CLASS_COUNT;
    *summary = ctx->summary;
}

int elevator_batch_write_per_image_header(FILE *stream)
{
    if (stream == NULL) {
        return -1;
    }
    return fprintf(stream,
        "image_name,success,fallback_used,elapsed_ms,frame_proc_ms,prepare_ms,preprocess_ms,input_update_ms,"
        "model_execute_ms,output_fetch_ms,postprocess_ms,temporal_ms,render_prepare_ms,render_ms,osd_ms,"
        "frame_width,frame_height,"
        "gt_person,gt_ebike,pred_person,pred_ebike,tp_person,tp_ebike,fp_person,fp_ebike,fn_person,fn_ebike,output_path\n") < 0
        ? -1 : 0;
}

int elevator_batch_write_per_image_row(FILE *stream, const elevator_batch_image_report *report)
{
    if (stream == NULL || report == NULL) {
        return -1;
    }
    return fprintf(stream,
        "\"%s\",%d,%d,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,"
        "%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,\"%s\"\n",
        report->image_name, report->success, report->fallback_used, report->elapsed_ms,
        report->timing_ms.frame_proc_ms, report->timing_ms.prepare_ms, report->timing_ms.preprocess_ms,
        report->timing_ms.input_update_ms, report->timing_ms.model_execute_ms,
        report->timing_ms.output_fetch_ms, report->timing_ms.postprocess_ms,
        report->timing_ms.temporal_ms, report->timing_ms.render_prepare_ms,
        report->timing_ms.render_ms, report->timing_ms.osd_ms,
        report->frame_width, report->frame_height,
        report->gt_count[0], report->gt_count[1],
        report->pred_count[0], report->pred_count[1],
        report->tp[0], report->tp[1],
        report->fp[0], report->fp[1],
        report->fn[0], report->fn[1],
        report->output_path) < 0 ? -1 : 0;
}

int elevator_batch_write_detections_jsonl(FILE *stream, const elevator_batch_image_report *report,
    const elevator_batch_gt_box *gt_boxes, size_t gt_count, const elevator_detection_result *detections,
    size_t detection_count)
{
    size_t idx;

    if (stream == NULL || report == NULL || gt_boxes == NULL || detections == NULL) {
        return -1;
    }

    fputc('{', stream);
    fputs("\"image_name\":", stream);
    elevator_batch_json_write_string(stream, report->image_name);
    fputs(",\"image_path\":", stream);
    elevator_batch_json_write_string(stream, report->image_path);
    fputs(",\"label_path\":", stream);
    elevator_batch_json_write_string(stream, report->label_path);
    fputs(",\"output_path\":", stream);
    elevator_batch_json_write_string(stream, report->output_path);
    fprintf(stream,
        ",\"success\":%s,\"fallback_used\":%s,\"elapsed_ms\":%.3f,\"frame_width\":%u,\"frame_height\":%u",
        report->success ? "true" : "false", report->fallback_used ? "true" : "false",
        report->elapsed_ms, report->frame_width, report->frame_height);
    fputs(",\"timing_ms\":", stream);
    if (elevator_batch_write_timing_json(stream, &report->timing_ms) != 0) {
        return -1;
    }
    fputs(",\"ground_truths\":[", stream);
    for (idx = 0; idx < gt_count; ++idx) {
        if (idx != 0) {
            fputc(',', stream);
        }
        fprintf(stream, "{\"class_id\":%u,\"x1\":%u,\"y1\":%u,\"x2\":%u,\"y2\":%u}",
            gt_boxes[idx].class_id, gt_boxes[idx].rect.x1, gt_boxes[idx].rect.y1,
            gt_boxes[idx].rect.x2, gt_boxes[idx].rect.y2);
    }
    fputs("],\"detections\":[", stream);
    for (idx = 0; idx < detection_count; ++idx) {
        if (idx != 0) {
            fputc(',', stream);
        }
        fprintf(stream,
            "{\"class_id\":%u,\"score\":%.6f,\"score_percent\":%u,\"x1\":%u,\"y1\":%u,\"x2\":%u,\"y2\":%u}",
            detections[idx].class_id, detections[idx].score, detections[idx].score_percent,
            detections[idx].rect.x1, detections[idx].rect.y1, detections[idx].rect.x2, detections[idx].rect.y2);
    }
    fputs("]}\n", stream);
    return ferror(stream) != 0 ? -1 : 0;
}

int elevator_batch_write_summary_json(const char *path, const char *images_dir, const char *labels_dir,
    const char *output_dir, uint32_t limit, float score_threshold, float nms_threshold,
    const elevator_batch_summary *summary)
{
    FILE *stream;
    size_t class_id;

    if (path == NULL || summary == NULL) {
        return -1;
    }

    stream = fopen(path, "w");
    if (stream == NULL) {
        return -1;
    }

    fputs("{\n  \"images_dir\": ", stream);
    elevator_batch_json_write_string(stream, images_dir != NULL ? images_dir : "");
    fputs(",\n  \"labels_dir\": ", stream);
    elevator_batch_json_write_string(stream, labels_dir != NULL ? labels_dir : "");
    fputs(",\n  \"output_dir\": ", stream);
    elevator_batch_json_write_string(stream, output_dir != NULL ? output_dir : "");
    fprintf(stream,
        ",\n  \"limit\": %u,\n  \"score_threshold\": %.6f,\n  \"nms_threshold\": %.6f,\n  \"iou_threshold\": 0.500000,\n"
        "  \"image_count\": %llu,\n  \"success_count\": %llu,\n  \"failure_count\": %llu,\n"
        "  \"fallback_count\": %llu,\n  \"total_elapsed_ms\": %.3f,\n  \"average_elapsed_ms\": %.3f,\n"
        "  \"map50\": %.6f,\n  \"timing_ms_average\": ",
        limit, score_threshold, nms_threshold,
        (unsigned long long)summary->image_count,
        (unsigned long long)summary->success_count,
        (unsigned long long)summary->failure_count,
        (unsigned long long)summary->fallback_count,
        summary->total_elapsed_ms, summary->average_elapsed_ms, summary->map50);
    if (elevator_batch_write_timing_json(stream, &summary->average_timing_ms) != 0) {
        fclose(stream);
        return -1;
    }
    fputs(",\n  \"classes\": [\n", stream);

    for (class_id = 0; class_id < ELEVATOR_BATCH_CLASS_COUNT; ++class_id) {
        const elevator_batch_class_summary *cls = &summary->classes[class_id];

        fprintf(stream,
            "    {\n      \"class_id\": %zu,\n      \"class_name\": ", class_id);
        elevator_batch_json_write_string(stream, g_elevator_batch_class_names[class_id]);
        fprintf(stream,
            ",\n      \"gt\": %llu,\n      \"pred\": %llu,\n      \"tp\": %llu,\n      \"fp\": %llu,\n"
            "      \"fn\": %llu,\n      \"precision\": %.6f,\n      \"recall\": %.6f,\n"
            "      \"f1\": %.6f,\n      \"ap50\": %.6f\n    }%s\n",
            (unsigned long long)cls->gt, (unsigned long long)cls->pred,
            (unsigned long long)cls->tp, (unsigned long long)cls->fp,
            (unsigned long long)cls->fn, cls->precision, cls->recall, cls->f1, cls->ap50,
            (class_id + 1 == ELEVATOR_BATCH_CLASS_COUNT) ? "" : ",");
    }
    fputs("  ]\n}\n", stream);
    fclose(stream);
    return 0;
}
