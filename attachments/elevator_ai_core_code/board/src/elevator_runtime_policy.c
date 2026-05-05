#include "elevator_yolo.h"

int elevator_file_mode_prefers_frame_feed(const elevator_runtime_config *config)
{
    if (config == 0) {
        return 0;
    }
    if (config->mode != ELEVATOR_RUN_MODE_FILE) {
        return 0;
    }
    if (config->timing_mode != ELEVATOR_PLAYBACK_TIMING_SOURCE) {
        return 0;
    }
    if (config->single_shot == 0) {
        return 0;
    }
    if (config->source_fps <= 0.0f) {
        return 0;
    }
    if (config->source_frame_count == 0U) {
        return 0;
    }
    return 1;
}

int elevator_file_mode_prefers_playback_display(const elevator_runtime_config *config)
{
    return elevator_file_mode_prefers_frame_feed(config);
}
