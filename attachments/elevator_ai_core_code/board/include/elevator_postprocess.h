#ifndef ELEVATOR_POSTPROCESS_H
#define ELEVATOR_POSTPROCESS_H

#include <stddef.h>
#include <stdint.h>

#define ELEVATOR_MAX_DETECTIONS 64
#define ELEVATOR_MAX_SMOOTH_WINDOW 16
#define ELEVATOR_TEMPORAL_HISTORY_FRAMES 3
#define ELEVATOR_MAX_PERSON_TRACKS 24
#define ELEVATOR_MAX_EBIKE_TRACKS 12

typedef enum elevator_review_surface {
    ELEVATOR_REVIEW_SURFACE_CLEAN = 0,
    ELEVATOR_REVIEW_SURFACE_PUBLIC = 1,
    ELEVATOR_REVIEW_SURFACE_DEBUG = 2,
} elevator_review_surface;

typedef enum elevator_track_state {
    ELEVATOR_TRACK_STATE_NONE = 0,
    ELEVATOR_TRACK_STATE_TENTATIVE = 1,
    ELEVATOR_TRACK_STATE_CONFIRMED = 2,
    ELEVATOR_TRACK_STATE_HELD = 3,
} elevator_track_state;

typedef struct elevator_rect {
    uint32_t x1;
    uint32_t y1;
    uint32_t x2;
    uint32_t y2;
} elevator_rect;

typedef struct elevator_detection_result {
    elevator_rect rect;
    uint32_t class_id;
    float score;
    uint32_t score_percent;
    uint32_t track_id;
    uint8_t track_state;
    uint8_t child_like;
    uint8_t synthetic;
} elevator_detection_result;

typedef struct elevator_count_stats {
    uint32_t person_count;
    uint32_t ebike_count;
    uint32_t smoothed_person_count;
    uint32_t smoothed_ebike_count;
    uint32_t raw_person_count;
    uint32_t confirmed_track_person_count;
    uint32_t tentative_person_count;
    uint32_t held_person_count;
    uint32_t mature_confirmed_person_count;
    uint32_t mature_held_person_count;
    uint32_t public_person_count_from_mature_carry;
    float fps;
} elevator_count_stats;

typedef struct elevator_frame_timing {
    double frame_proc_ms;
    double prepare_ms;
    double preprocess_ms;
    double input_update_ms;
    double model_execute_ms;
    double output_fetch_ms;
    double postprocess_ms;
    double temporal_ms;
    double render_prepare_ms;
    double render_ms;
    double osd_ms;
} elevator_frame_timing;

typedef struct elevator_parse_result {
    elevator_detection_result detections[ELEVATOR_MAX_DETECTIONS];
    size_t detection_count;
    elevator_count_stats stats;
    elevator_frame_timing timing_ms;
} elevator_parse_result;

typedef struct elevator_smoother {
    uint32_t window_size;
    uint32_t index;
    uint32_t filled;
    uint32_t person_history[ELEVATOR_MAX_SMOOTH_WINDOW];
    uint32_t ebike_history[ELEVATOR_MAX_SMOOTH_WINDOW];
    uint64_t last_timestamp_ms;
} elevator_smoother;

typedef struct elevator_temporal_hold {
    uint32_t max_hold_frames;
    uint32_t consecutive_holds;
    uint64_t max_hold_ms;
    uint64_t last_timestamp_ms;
    int has_previous;
    elevator_parse_result previous_result;
    elevator_parse_result history[ELEVATOR_TEMPORAL_HISTORY_FRAMES];
    uint64_t history_timestamp_ms[ELEVATOR_TEMPORAL_HISTORY_FRAMES];
    uint32_t history_index;
    uint32_t history_filled;
    int carry_active;
    elevator_detection_result carry_detection;
    uint32_t carry_frames;
    uint64_t carry_started_ms;
} elevator_temporal_hold;

typedef struct elevator_person_track {
    uint32_t active;
    uint32_t track_id;
    elevator_detection_result detection;
    uint32_t hits;
    uint32_t lost_frames;
    uint64_t last_timestamp_ms;
    uint8_t matched_in_frame;
    uint8_t child_like;
} elevator_person_track;

typedef struct elevator_person_tracker {
    elevator_person_track tracks[ELEVATOR_MAX_PERSON_TRACKS];
    uint32_t next_track_id;
    uint32_t max_lost_frames;
    uint64_t max_lost_ms;
    uint32_t last_public_person_count;
} elevator_person_tracker;

typedef struct elevator_ebike_track {
    uint32_t active;
    uint32_t track_id;
    elevator_detection_result detection;
    uint32_t hits;
    uint32_t lost_frames;
    uint64_t last_timestamp_ms;
    uint8_t matched_in_frame;
} elevator_ebike_track;

typedef struct elevator_ebike_tracker {
    elevator_ebike_track tracks[ELEVATOR_MAX_EBIKE_TRACKS];
    uint32_t next_track_id;
    uint32_t max_lost_frames;
    uint64_t max_lost_ms;
} elevator_ebike_tracker;

void elevator_smoother_reset(elevator_smoother *smoother, uint32_t window_size);
void elevator_smoother_update(elevator_smoother *smoother, uint32_t person_count,
    uint32_t ebike_count, uint64_t timestamp_ms, elevator_count_stats *stats);
void elevator_temporal_hold_reset(elevator_temporal_hold *hold, uint32_t max_hold_frames, uint64_t max_hold_ms);
void elevator_temporal_hold_apply(elevator_temporal_hold *hold, elevator_parse_result *result, uint64_t timestamp_ms,
    uint32_t frame_width, uint32_t frame_height);
void elevator_person_tracker_reset(elevator_person_tracker *tracker, uint32_t max_lost_frames, uint64_t max_lost_ms);
void elevator_person_tracker_apply(elevator_person_tracker *tracker, elevator_parse_result *result, uint64_t timestamp_ms,
    uint32_t frame_width, uint32_t frame_height);
void elevator_ebike_tracker_reset(elevator_ebike_tracker *tracker, uint32_t max_lost_frames, uint64_t max_lost_ms);
void elevator_ebike_tracker_apply(elevator_ebike_tracker *tracker, elevator_parse_result *result, uint64_t timestamp_ms,
    uint32_t frame_width, uint32_t frame_height);
int elevator_review_surface_detection_should_render(elevator_review_surface surface,
    const elevator_detection_result *detection, uint32_t frame_width, uint32_t frame_height);
uint32_t elevator_review_surface_detection_color(elevator_review_surface surface,
    const elevator_detection_result *detection);
int elevator_public_detection_should_render(const elevator_detection_result *detection,
    uint32_t frame_width, uint32_t frame_height);
uint32_t elevator_public_detection_color(const elevator_detection_result *detection);

#define ELEVATOR_EBIKE_FP_CLEANUP_OFF 0
#define ELEVATOR_EBIKE_FP_CLEANUP_SAFE 1
#define ELEVATOR_EBIKE_FP_CLEANUP_FULL 2

int elevator_parse_raw_outputs(const float *count_data, size_t count_len,
    const float *roi_data, size_t roi_stride_floats, size_t roi_plane_count, size_t max_rois,
    uint32_t proc_width, uint32_t proc_height, uint32_t show_width, uint32_t show_height,
    float score_threshold, float nms_threshold, int ebike_fp_cleanup_mode,
    elevator_parse_result *result, char *errbuf, size_t errbuf_size);

#endif
