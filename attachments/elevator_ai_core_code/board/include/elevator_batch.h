#ifndef ELEVATOR_BATCH_H
#define ELEVATOR_BATCH_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "elevator_postprocess.h"

#define ELEVATOR_BATCH_CLASS_COUNT 2
#define ELEVATOR_BATCH_MAX_LABELS 256

typedef struct elevator_batch_image_item {
    char image_name[512];
    char image_path[512];
    char label_path[512];
} elevator_batch_image_item;

typedef struct elevator_batch_image_list {
    elevator_batch_image_item *items;
    size_t count;
} elevator_batch_image_list;

typedef struct elevator_batch_gt_box {
    uint32_t class_id;
    elevator_rect rect;
} elevator_batch_gt_box;

typedef struct elevator_batch_image_report {
    char image_name[512];
    char image_path[512];
    char label_path[512];
    char output_path[512];
    uint32_t frame_width;
    uint32_t frame_height;
    uint32_t gt_count[ELEVATOR_BATCH_CLASS_COUNT];
    uint32_t pred_count[ELEVATOR_BATCH_CLASS_COUNT];
    uint32_t tp[ELEVATOR_BATCH_CLASS_COUNT];
    uint32_t fp[ELEVATOR_BATCH_CLASS_COUNT];
    uint32_t fn[ELEVATOR_BATCH_CLASS_COUNT];
    double elapsed_ms;
    elevator_frame_timing timing_ms;
    int success;
    int fallback_used;
} elevator_batch_image_report;

typedef struct elevator_batch_class_summary {
    uint64_t gt;
    uint64_t pred;
    uint64_t tp;
    uint64_t fp;
    uint64_t fn;
    double precision;
    double recall;
    double f1;
    double ap50;
} elevator_batch_class_summary;

typedef struct elevator_batch_summary {
    uint64_t image_count;
    uint64_t success_count;
    uint64_t failure_count;
    uint64_t fallback_count;
    double total_elapsed_ms;
    double average_elapsed_ms;
    elevator_frame_timing total_timing_ms;
    elevator_frame_timing average_timing_ms;
    double map50;
    elevator_batch_class_summary classes[ELEVATOR_BATCH_CLASS_COUNT];
} elevator_batch_summary;

typedef struct elevator_batch_eval_context elevator_batch_eval_context;

int elevator_batch_collect_images(const char *images_dir, const char *labels_dir, uint32_t offset, uint32_t limit,
    elevator_batch_image_list *list, char *errbuf, size_t errbuf_size);
void elevator_batch_free_image_list(elevator_batch_image_list *list);

int elevator_batch_make_output_dir(const char *configured_output_dir, char *output_dir,
    size_t output_dir_size, char *errbuf, size_t errbuf_size);

int elevator_batch_load_yolo_labels(const char *label_path, uint32_t frame_width, uint32_t frame_height,
    elevator_batch_gt_box *boxes, size_t max_boxes, size_t *box_count, char *errbuf, size_t errbuf_size);

elevator_batch_eval_context *elevator_batch_eval_create(void);
void elevator_batch_eval_destroy(elevator_batch_eval_context *ctx);

int elevator_batch_eval_image(elevator_batch_eval_context *ctx, const elevator_batch_gt_box *gt_boxes,
    size_t gt_count, const elevator_detection_result *detections, size_t detection_count, float iou_threshold,
    elevator_batch_image_report *report);
void elevator_batch_eval_mark_failure(elevator_batch_eval_context *ctx, elevator_batch_image_report *report);
void elevator_batch_eval_note_run(elevator_batch_eval_context *ctx, double elapsed_ms, int fallback_used);
void elevator_batch_eval_note_timing(elevator_batch_eval_context *ctx, const elevator_frame_timing *timing_ms);
void elevator_batch_eval_finalize(elevator_batch_eval_context *ctx, elevator_batch_summary *summary);

int elevator_batch_write_per_image_header(FILE *stream);
int elevator_batch_write_per_image_row(FILE *stream, const elevator_batch_image_report *report);
int elevator_batch_write_detections_jsonl(FILE *stream, const elevator_batch_image_report *report,
    const elevator_batch_gt_box *gt_boxes, size_t gt_count, const elevator_detection_result *detections,
    size_t detection_count);
int elevator_batch_write_summary_json(const char *path, const char *images_dir, const char *labels_dir,
    const char *output_dir, uint32_t limit, float score_threshold, float nms_threshold,
    const elevator_batch_summary *summary);

#endif
