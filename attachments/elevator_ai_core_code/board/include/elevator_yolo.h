#ifndef ELEVATOR_YOLO_H
#define ELEVATOR_YOLO_H

#include "elevator_postprocess.h"

#include <stddef.h>
#include <stdint.h>

#define ELEVATOR_PATH_MAX 512

typedef enum elevator_run_mode {
    ELEVATOR_RUN_MODE_HELP = 0,
    ELEVATOR_RUN_MODE_FILE = 1,
    ELEVATOR_RUN_MODE_CAMERA = 2,
    ELEVATOR_RUN_MODE_BATCH = 3,
} elevator_run_mode;

typedef enum elevator_playback_timing_mode {
    ELEVATOR_PLAYBACK_TIMING_SOURCE = 0,
} elevator_playback_timing_mode;

typedef enum elevator_ebike_cleanup_cli_mode {
    ELEVATOR_EBIKE_CLEANUP_CLI_AUTO = -1,
    ELEVATOR_EBIKE_CLEANUP_CLI_OFF = ELEVATOR_EBIKE_FP_CLEANUP_OFF,
    ELEVATOR_EBIKE_CLEANUP_CLI_SAFE = ELEVATOR_EBIKE_FP_CLEANUP_SAFE,
    ELEVATOR_EBIKE_CLEANUP_CLI_FULL = ELEVATOR_EBIKE_FP_CLEANUP_FULL,
} elevator_ebike_cleanup_cli_mode;

typedef struct elevator_runtime_config {
    elevator_run_mode mode;
    char input_path[ELEVATOR_PATH_MAX];
    char images_dir[ELEVATOR_PATH_MAX];
    char labels_dir[ELEVATOR_PATH_MAX];
    char output_dir[ELEVATOR_PATH_MAX];
    char model_path[ELEVATOR_PATH_MAX];
    float score_threshold;
    float nms_threshold;
    uint32_t smooth_window;
    uint32_t rtsp_port;
    uint32_t offset;
    uint32_t limit;
    int ebike_cleanup_mode;
    elevator_review_surface review_surface;
    elevator_playback_timing_mode timing_mode;
    int single_shot;
    float source_fps;
    uint32_t source_frame_count;
    uint32_t source_duration_ms;
    int osd_enable;
} elevator_runtime_config;

typedef struct elevator_file_drain_snapshot {
    uint32_t left_stream_bytes;
    uint32_t left_stream_frames;
    uint32_t left_decoded_frames;
    uint64_t processed_frame_count;
} elevator_file_drain_snapshot;

typedef struct elevator_file_drain_state {
    uint32_t stable_polls;
    uint32_t idle_elapsed_ms;
    uint32_t last_left_stream_bytes;
    uint32_t last_left_stream_frames;
    uint32_t last_left_decoded_frames;
    uint64_t last_processed_frame_count;
    int initialized;
} elevator_file_drain_state;

typedef enum elevator_file_drain_decision {
    ELEVATOR_FILE_DRAIN_DECISION_CONTINUE = 0,
    ELEVATOR_FILE_DRAIN_DECISION_READY = 1,
    ELEVATOR_FILE_DRAIN_DECISION_TIMED_OUT = 2,
} elevator_file_drain_decision;

void elevator_config_init(elevator_runtime_config *config);
int elevator_parse_cli(int argc, char **argv, elevator_runtime_config *config,
    char *errbuf, size_t errbuf_size);
void elevator_print_usage(const char *prog_name);

int elevator_run_file(const elevator_runtime_config *config);
int elevator_run_camera(const elevator_runtime_config *config);
int elevator_run_batch(const elevator_runtime_config *config);
void elevator_request_stop(void);
int elevator_file_mode_prefers_frame_feed(const elevator_runtime_config *config);
int elevator_file_mode_prefers_playback_display(const elevator_runtime_config *config);

static inline elevator_file_drain_decision elevator_file_drain_step(
    elevator_file_drain_state *state,
    const elevator_file_drain_snapshot *snapshot,
    uint32_t poll_ms,
    uint32_t idle_timeout_ms,
    uint32_t stable_polls_required)
{
    int drained;
    int progress;

    if (state == NULL || snapshot == NULL || stable_polls_required == 0) {
        return ELEVATOR_FILE_DRAIN_DECISION_CONTINUE;
    }

    drained = (snapshot->left_stream_bytes == 0 &&
        snapshot->left_stream_frames == 0 &&
        snapshot->left_decoded_frames == 0) ? 1 : 0;

    if (state->initialized == 0) {
        state->initialized = 1;
        state->stable_polls = drained ? 1U : 0U;
        state->idle_elapsed_ms = 0;
        state->last_left_stream_bytes = snapshot->left_stream_bytes;
        state->last_left_stream_frames = snapshot->left_stream_frames;
        state->last_left_decoded_frames = snapshot->left_decoded_frames;
        state->last_processed_frame_count = snapshot->processed_frame_count;
        return state->stable_polls >= stable_polls_required ?
            ELEVATOR_FILE_DRAIN_DECISION_READY :
            ELEVATOR_FILE_DRAIN_DECISION_CONTINUE;
    }

    progress = (snapshot->left_stream_bytes != state->last_left_stream_bytes ||
        snapshot->left_stream_frames != state->last_left_stream_frames ||
        snapshot->left_decoded_frames != state->last_left_decoded_frames ||
        snapshot->processed_frame_count != state->last_processed_frame_count) ? 1 : 0;

    if (progress != 0) {
        state->idle_elapsed_ms = 0;
    } else {
        state->idle_elapsed_ms += poll_ms;
    }

    if (drained && progress == 0) {
        state->stable_polls++;
    } else if (drained) {
        state->stable_polls = 0;
    } else {
        state->stable_polls = 0;
    }

    state->last_left_stream_bytes = snapshot->left_stream_bytes;
    state->last_left_stream_frames = snapshot->left_stream_frames;
    state->last_left_decoded_frames = snapshot->left_decoded_frames;
    state->last_processed_frame_count = snapshot->processed_frame_count;

    if (state->stable_polls >= stable_polls_required) {
        return ELEVATOR_FILE_DRAIN_DECISION_READY;
    }
    if (progress == 0 && state->idle_elapsed_ms >= idle_timeout_ms) {
        return ELEVATOR_FILE_DRAIN_DECISION_TIMED_OUT;
    }
    return ELEVATOR_FILE_DRAIN_DECISION_CONTINUE;
}

#endif
