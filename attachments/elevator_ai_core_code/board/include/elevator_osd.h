#ifndef ELEVATOR_OSD_H
#define ELEVATOR_OSD_H

#include "elevator_postprocess.h"
#include "sample_common_svp.h"

int elevator_osd_init(uint32_t frame_width, uint32_t frame_height);
void elevator_osd_deinit(void);
int elevator_osd_render_panel(const ot_video_frame_info *frame,
    const elevator_count_stats *stats, const elevator_parse_result *render_result,
    elevator_review_surface surface);
int elevator_osd_render_scores(const ot_video_frame_info *frame,
    ot_sample_svp_rect_info *rect_info, const elevator_parse_result *result);

#endif
