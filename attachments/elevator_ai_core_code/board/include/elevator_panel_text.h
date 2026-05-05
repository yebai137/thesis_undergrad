#ifndef ELEVATOR_PANEL_TEXT_H
#define ELEVATOR_PANEL_TEXT_H

#include "elevator_postprocess.h"

#include <stddef.h>

int elevator_osd_format_panel_text(char *text, size_t text_size,
    const elevator_count_stats *stats, const elevator_parse_result *render_result,
    elevator_review_surface surface);

#endif
