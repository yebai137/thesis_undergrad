#include "elevator_panel_text.h"

#include <stdio.h>

static char elevator_panel_surface_code(elevator_review_surface surface)
{
    if (surface == ELEVATOR_REVIEW_SURFACE_DEBUG) {
        return 'D';
    }
    if (surface == ELEVATOR_REVIEW_SURFACE_PUBLIC) {
        return 'P';
    }
    return 'C';
}

static uint32_t elevator_panel_rendered_ebike_count(const elevator_parse_result *render_result,
    const elevator_count_stats *stats)
{
    size_t idx;
    uint32_t count = 0U;

    if (render_result != NULL) {
        for (idx = 0; idx < render_result->detection_count; ++idx) {
            if (render_result->detections[idx].class_id == 1U) {
                count++;
            }
        }
        return count;
    }
    return stats != NULL ? stats->ebike_count : 0U;
}

int elevator_osd_format_panel_text(char *text, size_t text_size,
    const elevator_count_stats *stats, const elevator_parse_result *render_result,
    elevator_review_surface surface)
{
    int written;
    uint32_t panel_ebike_count;

    if (text == NULL || text_size == 0U || stats == NULL) {
        return -1;
    }

    panel_ebike_count = elevator_panel_rendered_ebike_count(render_result, stats);
    written = snprintf(text, text_size, "%c P:%02u E:%02u F:%02u",
        elevator_panel_surface_code(surface),
        stats->smoothed_person_count,
        panel_ebike_count,
        (uint32_t)(stats->fps + 0.5f));
    if (written < 0 || (size_t)written >= text_size) {
        return -1;
    }
    return 0;
}
