#include "elevator_postprocess.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#define ELEVATOR_CONTAINMENT_MIN_AREA_RATIO 5ULL
#define ELEVATOR_CONTAINMENT_MIN_COVERAGE_PERCENT 92ULL
#define ELEVATOR_CONTAINMENT_MIN_SCORE_MARGIN 0.05f
#define ELEVATOR_LOW_SCORE_STRIP_MAX_RATIO 7ULL
#define ELEVATOR_LOW_SCORE_STRIP_SCORE_CEILING 0.55f
#define ELEVATOR_LOW_SCORE_LARGE_BOX_SCORE_CEILING 0.25f
#define ELEVATOR_LOW_SCORE_LARGE_BOX_EDGE_SCORE_CEILING 0.18f
#define ELEVATOR_LOW_SCORE_LARGE_BOX_PARTIAL_AREA_PERCENT 12ULL
#define ELEVATOR_LOW_SCORE_LARGE_BOX_ALWAYS_DROP_AREA_PERCENT 18ULL
#define ELEVATOR_LOW_SCORE_LARGE_BOX_SCORE_MARGIN 0.15f
#define ELEVATOR_LOW_SCORE_LARGE_BOX_SINGLE_COVERAGE_PERCENT 45ULL
#define ELEVATOR_LOW_SCORE_LARGE_BOX_MULTI_COVERAGE_PERCENT 25ULL
#define ELEVATOR_LOW_SCORE_LARGE_BOX_MULTI_COVER_COUNT 2U
#define ELEVATOR_LOW_SCORE_LARGE_BOX_CHILD_CONFLICT_MIN_AREA_PERCENT 6ULL
#define ELEVATOR_LOW_SCORE_LARGE_BOX_CHILD_CONFLICT_MIN_COVERAGE_PERCENT 60ULL
#define ELEVATOR_LOW_SCORE_LARGE_BOX_CHILD_CONFLICT_MAX_CENTER_DISTANCE_PERCENT 14ULL
#define ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_AREA_PERCENT 25ULL
#define ELEVATOR_EDGE_PERSON_UMBRELLA_LOW_SCORE_CEILING 0.35f
#define ELEVATOR_EDGE_PERSON_UMBRELLA_HIGH_SCORE_CEILING 0.85f
#define ELEVATOR_EDGE_PERSON_UMBRELLA_LARGE_AREA_PERCENT 35ULL
#define ELEVATOR_EDGE_PERSON_UMBRELLA_CHILD_AREA_PERCENT 14ULL
#define ELEVATOR_EDGE_PERSON_UMBRELLA_CHILD_SCORE_CEILING 0.60f
#define ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_SUPPORTER_AREA_PERCENT 3ULL
#define ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_SUPPORTER_SCORE 0.10f
#define ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_STRONG_SUPPORTER_SCORE 0.45f
#define ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_SUPPORTER_COUNT 2U
#define ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_COMBINED_AREA_PERCENT 25ULL
#define ELEVATOR_EDGE_PERSON_CORNER_UMBRELLA_MIN_AREA_PERCENT 24ULL
#define ELEVATOR_EDGE_PERSON_CORNER_UMBRELLA_SCORE_CEILING 0.40f
#define ELEVATOR_EDGE_PERSON_CORNER_UMBRELLA_MIN_WIDTH_PERCENT 30ULL
#define ELEVATOR_EDGE_PERSON_CORNER_UMBRELLA_MIN_HEIGHT_PERCENT 55ULL
#define ELEVATOR_EBIKE_HUGE_BOX_SCORE_CEILING 0.35f
#define ELEVATOR_EBIKE_HUGE_BOX_MIN_AREA_PERCENT 25ULL
#define ELEVATOR_EBIKE_TALL_HUMAN_SCORE_CEILING 0.82f
#define ELEVATOR_EBIKE_TALL_HUMAN_MIN_AREA_PERCENT 12ULL
#define ELEVATOR_EBIKE_TALL_HUMAN_MIN_HEIGHT_TO_WIDTH_PERCENT 160ULL
#define ELEVATOR_EBIKE_TALL_HUMAN_MIN_HEIGHT_PERCENT 55ULL
#define ELEVATOR_EBIKE_DUPLICATE_SCORE_CEILING 0.30f
#define ELEVATOR_EBIKE_DUPLICATE_MIN_COVERAGE_PERCENT 70ULL
#define ELEVATOR_EBIKE_DUPLICATE_SCORE_MARGIN 0.20f
#define ELEVATOR_EBIKE_TOP_STRIP_SCORE_CEILING 0.30f
#define ELEVATOR_EBIKE_TOP_STRIP_MAX_AREA_PERCENT 6ULL
#define ELEVATOR_EBIKE_TOP_STRIP_MAX_HEIGHT_PERCENT 16ULL
#define ELEVATOR_EBIKE_TOP_STRIP_MIN_WIDTH_TO_HEIGHT_PERCENT 180ULL
#define ELEVATOR_EBIKE_PERSON_CONTAINER_SCORE_CEILING 0.75f
#define ELEVATOR_EBIKE_PERSON_CONTAINER_MIN_AREA_PERCENT 20ULL
#define ELEVATOR_EBIKE_PERSON_CONTAINER_MIN_WIDTH_TO_HEIGHT_PERCENT 115ULL
#define ELEVATOR_EBIKE_PERSON_CONTAINER_MIN_PERSON_SCORE 0.55f
#define ELEVATOR_EBIKE_PERSON_CONTAINER_MIN_COVERAGE_PERCENT 85ULL
#define ELEVATOR_EBIKE_TOP_EDGE_PERSON_SCORE_CEILING 0.92f
#define ELEVATOR_EBIKE_TOP_EDGE_PERSON_MIN_AREA_PERCENT 12ULL
#define ELEVATOR_EBIKE_TOP_EDGE_PERSON_MIN_HEIGHT_PERCENT 45ULL
#define ELEVATOR_EBIKE_TOP_EDGE_PERSON_MIN_HEIGHT_TO_WIDTH_PERCENT 100ULL
#define ELEVATOR_EBIKE_PERSON_CLONE_SCORE_CEILING 0.90f
#define ELEVATOR_EBIKE_PERSON_CLONE_MIN_AREA_PERCENT 8ULL
#define ELEVATOR_EBIKE_PERSON_CLONE_MIN_PERSON_SCORE 0.45f
#define ELEVATOR_EBIKE_PERSON_CLONE_MIN_COVERAGE_PERCENT 92ULL
#define ELEVATOR_EBIKE_PERSON_CLONE_MAX_WIDTH_RATIO_PERCENT 145ULL
#define ELEVATOR_EBIKE_PERSON_CLONE_MAX_HEIGHT_RATIO_PERCENT 145ULL
#define ELEVATOR_EBIKE_TRACK_MATCH_MIN_IOU 0.18f
#define ELEVATOR_EBIKE_TRACK_CONFIRM_HITS 2U
#define ELEVATOR_PUBLIC_EBIKE_MIN_SCORE 0.75f
#define ELEVATOR_PUBLIC_EBIKE_RETAIN_MIN_SCORE 0.45f
#define ELEVATOR_PUBLIC_PERSON_EDGE_SCORE_CEILING 0.22f
#define ELEVATOR_PUBLIC_PERSON_TOP_EDGE_SCORE_CEILING 0.18f
#define ELEVATOR_PUBLIC_PERSON_TOP_EDGE_MIN_AREA_PERCENT 12ULL
#define ELEVATOR_PUBLIC_PERSON_TOP_EDGE_MIN_HEIGHT_PERCENT 35ULL
#define ELEVATOR_PUBLIC_PERSON_TENTATIVE_EDGE_MIN_AREA_PERCENT 18ULL
#define ELEVATOR_FRAME_EDGE_MARGIN_PX 8U
#define ELEVATOR_PUBLIC_PERSON_COLOR 0x00FF00
#define ELEVATOR_PUBLIC_EBIKE_COLOR 0xFF9C40
#define ELEVATOR_DEBUG_PERSON_TENTATIVE_COLOR 0xFFD848
#define ELEVATOR_DEBUG_PERSON_HELD_COLOR 0x60D2FF
#define ELEVATOR_DEBUG_PERSON_CHILD_COLOR 0xFF66CC
#define ELEVATOR_SINGLE_PERSON_HOLD_MIN_SCORE 0.35f
#define ELEVATOR_SINGLE_PERSON_HOLD_MIN_AREA_PERCENT 2ULL
#define ELEVATOR_SINGLE_PERSON_HOLD_MAX_AREA_PERCENT 18ULL
#define ELEVATOR_SINGLE_PERSON_HOLD_MIN_HISTORY_MATCHES 2U
#define ELEVATOR_SINGLE_PERSON_HOLD_IOU_THRESHOLD 0.45f
#define ELEVATOR_DUPLICATE_CLUSTER_IOU_THRESHOLD 0.22f
#define ELEVATOR_DUPLICATE_CLUSTER_EDGE_IOU_THRESHOLD 0.12f
#define ELEVATOR_DUPLICATE_CLUSTER_MAX_CENTER_DISTANCE_PERCENT 16ULL
#define ELEVATOR_DUPLICATE_CLUSTER_MIN_SIZE_RATIO_PERCENT 45ULL
#define ELEVATOR_DUPLICATE_CLUSTER_MAX_SIZE_RATIO_PERCENT 220ULL
#define ELEVATOR_CHILD_DUPLICATE_MIN_COVERAGE_PERCENT 60ULL
#define ELEVATOR_CHILD_DUPLICATE_MIXED_COVERAGE_PERCENT 78ULL
#define ELEVATOR_CHILD_DUPLICATE_MAX_CENTER_DISTANCE_PERCENT 12ULL
#define ELEVATOR_CHILD_DUPLICATE_MIN_SIZE_RATIO_PERCENT 35ULL
#define ELEVATOR_CHILD_DUPLICATE_MAX_SIZE_RATIO_PERCENT 240ULL
#define ELEVATOR_CHILD_DUPLICATE_MAX_NON_CHILD_AREA_PERCENT 15ULL
#define ELEVATOR_CHILD_DUPLICATE_MAX_SCORE_MARGIN 0.25f
#define ELEVATOR_CHILD_DUPLICATE_MAX_TOP_DELTA_PERCENT 35ULL
#define ELEVATOR_CHILD_DUPLICATE_LARGE_CHILD_MIN_COVERAGE_PERCENT 55ULL
#define ELEVATOR_CHILD_DUPLICATE_LARGE_CHILD_MIN_SCORE_MARGIN 0.15f
#define ELEVATOR_CHILD_DUPLICATE_LARGE_CHILD_MAX_TOP_DELTA_PERCENT 40ULL
#define ELEVATOR_TRACK_MATCH_MIN_IOU 0.15f
#define ELEVATOR_TRACK_MATCH_MIN_IOU_CHILD 0.08f
#define ELEVATOR_TRACK_CONFIRM_HITS 2U
#define ELEVATOR_TRACK_MATURE_HITS 4U
#define ELEVATOR_TRACK_ROBUST_MATURE_HITS 6U
#define ELEVATOR_MATURE_CARRY_MAX_AREA_PERCENT 18ULL
#define ELEVATOR_MATURE_CARRY_MAX_WIDTH_PERCENT 24ULL
#define ELEVATOR_MATURE_CARRY_MIN_SCORE 0.25f
#define ELEVATOR_ROBUST_MATURE_CARRY_MIN_SCORE 0.20f
#define ELEVATOR_TRACK_DUPLICATE_EDGE_COVERAGE_PERCENT 30ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_DUPLICATE_MIN_COVERAGE_PERCENT 92ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_DUPLICATE_MAX_CENTER_SHIFT_PERCENT 18ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_TOP_EDGE_ALIGNED_MAX_EDGE_DELTA_PERCENT 30ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_TOP_EDGE_ALIGNED_MAX_TOP_DELTA_PERCENT 8ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_UPPER_FRAGMENT_MIN_COVERAGE_PERCENT 85ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_UPPER_FRAGMENT_MAX_EDGE_DELTA_PERCENT 25ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_UPPER_FRAGMENT_MAX_TOP_DELTA_PERCENT 15ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_UPPER_FRAGMENT_MIN_BOTTOM_DELTA_PERCENT 25ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_UPPER_FRAGMENT_MAX_HEIGHT_RATIO_PERCENT 80ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_LOWER_FRAGMENT_MIN_VISIBLE_COVERAGE_PERCENT 40ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_LOWER_FRAGMENT_MIN_TOP_DELTA_PERCENT 35ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_TOP_EDGE_CONTAINER_MAX_EDGE_DELTA_PERCENT 12ULL
#define ELEVATOR_UNMATCHED_PUBLIC_CARRY_TOP_EDGE_CONTAINER_MAX_BOTTOM_DELTA_PERCENT 10ULL
#define ELEVATOR_TRACK_CHILD_MIN_AREA_PERCENT 1ULL
#define ELEVATOR_TRACK_CHILD_MAX_AREA_PERCENT 10ULL
#define ELEVATOR_TRACK_CHILD_MIN_HEIGHT_PERCENT 10ULL
#define ELEVATOR_TRACK_CHILD_MAX_HEIGHT_PERCENT 55ULL
#define ELEVATOR_TRACK_CHILD_MIN_SCORE 0.10f
#define ELEVATOR_TRACK_CHILD_REGRESSION_MIN_AREA_GROWTH_PERCENT 170ULL
#define ELEVATOR_TRACK_CHILD_REGRESSION_MIN_SCORE_DROP 0.08f

static uint32_t elevator_clip_u32(int64_t value)
{
    if (value < 0) {
        return 0;
    }
    if ((uint64_t)value > UINT32_MAX) {
        return UINT32_MAX;
    }
    return (uint32_t)value;
}

static uint32_t elevator_align_even_u32(uint32_t value)
{
    return value & (~1U);
}

static uint32_t elevator_clamp_to_frame_even_u32(uint32_t value, uint32_t frame_size)
{
    uint32_t max_value;

    if (frame_size <= 1U) {
        return 0;
    }

    max_value = frame_size - 1U;
    if ((max_value & 1U) != 0) {
        max_value -= 1U;
    }
    if (value > max_value) {
        value = max_value;
    }
    return elevator_align_even_u32(value);
}

static uint32_t elevator_round_u32(float value)
{
    if (!isfinite(value) || value <= 0.0f) {
        return 0;
    }
    return elevator_clip_u32((int64_t)lroundf(value));
}

static uint32_t elevator_rect_width(const elevator_rect *rect)
{
    if (rect == NULL || rect->x2 <= rect->x1) {
        return 0;
    }
    return rect->x2 - rect->x1;
}

static uint32_t elevator_rect_height(const elevator_rect *rect)
{
    if (rect == NULL || rect->y2 <= rect->y1) {
        return 0;
    }
    return rect->y2 - rect->y1;
}

static uint64_t elevator_rect_area(const elevator_rect *rect)
{
    return (uint64_t)elevator_rect_width(rect) * (uint64_t)elevator_rect_height(rect);
}

static int elevator_rect_is_geometry_valid(const elevator_rect *rect)
{
    uint32_t width = elevator_rect_width(rect);
    uint32_t height = elevator_rect_height(rect);

    if (width < 4U || height < 4U) {
        return 0;
    }
    if ((uint64_t)width * 8U < height || (uint64_t)height * 8U < width) {
        return 0;
    }
    return 1;
}

static int elevator_rect_is_low_score_strip_artifact(const elevator_rect *rect, float score)
{
    uint32_t width;
    uint32_t height;

    if (rect == NULL || !isfinite(score) || score >= ELEVATOR_LOW_SCORE_STRIP_SCORE_CEILING) {
        return 0;
    }

    width = elevator_rect_width(rect);
    height = elevator_rect_height(rect);
    if (width == 0 || height == 0) {
        return 1;
    }
    if ((uint64_t)width * ELEVATOR_LOW_SCORE_STRIP_MAX_RATIO < height) {
        return 1;
    }
    if ((uint64_t)height * ELEVATOR_LOW_SCORE_STRIP_MAX_RATIO < width) {
        return 1;
    }
    return 0;
}

static uint64_t elevator_rect_intersection_area(const elevator_rect *lhs, const elevator_rect *rhs)
{
    uint32_t inter_x1;
    uint32_t inter_y1;
    uint32_t inter_x2;
    uint32_t inter_y2;
    uint32_t inter_width;
    uint32_t inter_height;

    if (lhs == NULL || rhs == NULL) {
        return 0;
    }

    inter_x1 = (lhs->x1 > rhs->x1) ? lhs->x1 : rhs->x1;
    inter_y1 = (lhs->y1 > rhs->y1) ? lhs->y1 : rhs->y1;
    inter_x2 = (lhs->x2 < rhs->x2) ? lhs->x2 : rhs->x2;
    inter_y2 = (lhs->y2 < rhs->y2) ? lhs->y2 : rhs->y2;
    if (inter_x2 <= inter_x1 || inter_y2 <= inter_y1) {
        return 0;
    }

    inter_width = inter_x2 - inter_x1;
    inter_height = inter_y2 - inter_y1;
    return (uint64_t)inter_width * (uint64_t)inter_height;
}

static uint64_t elevator_rect_coverage_percent(const elevator_rect *cover, const elevator_rect *covered)
{
    uint64_t covered_area = elevator_rect_area(covered);
    uint64_t intersection_area = elevator_rect_intersection_area(cover, covered);

    if (covered_area == 0) {
        return 0;
    }
    return (intersection_area * 100ULL) / covered_area;
}

static int elevator_rect_touches_frame_edge(const elevator_rect *rect, uint32_t frame_width, uint32_t frame_height)
{
    uint32_t max_x;
    uint32_t max_y;

    if (rect == NULL || frame_width == 0 || frame_height == 0) {
        return 0;
    }

    max_x = frame_width > ELEVATOR_FRAME_EDGE_MARGIN_PX ? frame_width - ELEVATOR_FRAME_EDGE_MARGIN_PX : 0;
    max_y = frame_height > ELEVATOR_FRAME_EDGE_MARGIN_PX ? frame_height - ELEVATOR_FRAME_EDGE_MARGIN_PX : 0;
    if (rect->x1 <= ELEVATOR_FRAME_EDGE_MARGIN_PX || rect->y1 <= ELEVATOR_FRAME_EDGE_MARGIN_PX) {
        return 1;
    }
    if (rect->x2 >= max_x || rect->y2 >= max_y) {
        return 1;
    }
    return 0;
}

static int elevator_rect_touches_top_edge(const elevator_rect *rect)
{
    if (rect == NULL) {
        return 0;
    }
    return rect->y1 <= (ELEVATOR_FRAME_EDGE_MARGIN_PX * 3U);
}

static int elevator_rect_touches_right_edge(const elevator_rect *rect, uint32_t frame_width)
{
    uint32_t max_x;

    if (rect == NULL || frame_width == 0U) {
        return 0;
    }

    max_x = frame_width > ELEVATOR_FRAME_EDGE_MARGIN_PX ? frame_width - ELEVATOR_FRAME_EDGE_MARGIN_PX : 0U;
    return rect->x2 >= max_x;
}

static int elevator_rect_contains_point(const elevator_rect *rect, uint32_t x, uint32_t y)
{
    if (rect == NULL) {
        return 0;
    }
    return x >= rect->x1 && x < rect->x2 && y >= rect->y1 && y < rect->y2;
}

static uint32_t elevator_rect_center_x(const elevator_rect *rect)
{
    if (rect == NULL) {
        return 0;
    }
    return rect->x1 + elevator_rect_width(rect) / 2U;
}

static uint32_t elevator_rect_center_y(const elevator_rect *rect)
{
    if (rect == NULL) {
        return 0;
    }
    return rect->y1 + elevator_rect_height(rect) / 2U;
}

static uint64_t elevator_rect_center_distance_sq(const elevator_rect *lhs, const elevator_rect *rhs)
{
    int64_t dx;
    int64_t dy;

    if (lhs == NULL || rhs == NULL) {
        return UINT64_MAX;
    }

    dx = (int64_t)elevator_rect_center_x(lhs) - (int64_t)elevator_rect_center_x(rhs);
    dy = (int64_t)elevator_rect_center_y(lhs) - (int64_t)elevator_rect_center_y(rhs);
    return (uint64_t)(dx * dx + dy * dy);
}

static uint64_t elevator_max_u64(uint64_t lhs, uint64_t rhs)
{
    return lhs > rhs ? lhs : rhs;
}

static uint64_t elevator_min_u64(uint64_t lhs, uint64_t rhs)
{
    return lhs < rhs ? lhs : rhs;
}

static float elevator_rect_iou(const elevator_rect *lhs, const elevator_rect *rhs)
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
    lhs_area = (uint64_t)elevator_rect_width(lhs) * (uint64_t)elevator_rect_height(lhs);
    rhs_area = (uint64_t)elevator_rect_width(rhs) * (uint64_t)elevator_rect_height(rhs);
    union_area = lhs_area + rhs_area - inter_area;
    if (union_area == 0) {
        return 0.0f;
    }
    return (float)inter_area / (float)union_area;
}

static int elevator_detection_is_child_like(const elevator_detection_result *detection,
    uint32_t frame_width, uint32_t frame_height)
{
    uint64_t frame_area;
    uint64_t area_percent;
    uint64_t height_percent;
    uint64_t width_percent;
    uint64_t area;
    uint32_t width;
    uint32_t height;

    if (detection == NULL || detection->class_id != 0U || !isfinite(detection->score) ||
        detection->score < ELEVATOR_TRACK_CHILD_MIN_SCORE || frame_width == 0 || frame_height == 0) {
        return 0;
    }

    width = elevator_rect_width(&detection->rect);
    height = elevator_rect_height(&detection->rect);
    area = elevator_rect_area(&detection->rect);
    frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    if (width == 0 || height == 0 || area == 0 || frame_area == 0) {
        return 0;
    }

    area_percent = (area * 100ULL) / frame_area;
    height_percent = ((uint64_t)height * 100ULL) / (uint64_t)frame_height;
    width_percent = ((uint64_t)width * 100ULL) / (uint64_t)frame_width;
    if (detection->score < 0.20f) {
        return 0;
    }
    if (area_percent < ELEVATOR_TRACK_CHILD_MIN_AREA_PERCENT ||
        area_percent > 12ULL) {
        return 0;
    }
    if (height_percent < ELEVATOR_TRACK_CHILD_MIN_HEIGHT_PERCENT ||
        height_percent > ELEVATOR_TRACK_CHILD_MAX_HEIGHT_PERCENT) {
        return 0;
    }
    if (width_percent > 28ULL) {
        return 0;
    }
    if ((uint64_t)height * 100ULL < (uint64_t)width * 130ULL) {
        return 0;
    }
    if (elevator_rect_touches_frame_edge(&detection->rect, frame_width, frame_height) != 0 &&
        area_percent >= 8ULL) {
        return 0;
    }
    return 1;
}

static float elevator_detection_quality_score(const elevator_detection_result *detection,
    uint32_t frame_width, uint32_t frame_height)
{
    float quality;
    uint64_t frame_area;
    uint64_t area_percent;

    if (detection == NULL || !isfinite(detection->score)) {
        return -1.0f;
    }

    quality = detection->score;
    frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    if (frame_area != 0) {
        area_percent = (elevator_rect_area(&detection->rect) * 100ULL) / frame_area;
        if (detection->class_id == 0U && area_percent >= ELEVATOR_LOW_SCORE_LARGE_BOX_PARTIAL_AREA_PERCENT) {
            quality -= 0.08f;
        }
        if (detection->class_id == 0U && elevator_detection_is_child_like(detection, frame_width, frame_height) != 0) {
            quality += 0.04f;
        }
    }
    if (elevator_rect_touches_frame_edge(&detection->rect, frame_width, frame_height) != 0) {
        quality -= 0.18f;
    }
    if (elevator_rect_touches_top_edge(&detection->rect) != 0) {
        quality -= 0.05f;
    }
    return quality;
}

static int elevator_person_boxes_look_like_duplicate(const elevator_detection_result *lhs,
    const elevator_detection_result *rhs, uint32_t frame_width, uint32_t frame_height)
{
    float iou;
    uint64_t lhs_area;
    uint64_t rhs_area;
    uint64_t min_area;
    uint64_t max_area;
    uint64_t size_ratio_percent;
    uint64_t smaller_coverage_percent;
    uint64_t frame_diag_sq;
    uint64_t center_dist_sq;
    uint64_t max_center_distance_sq;
    uint32_t min_frame_side;

    if (lhs == NULL || rhs == NULL || lhs->class_id != 0U || rhs->class_id != 0U) {
        return 0;
    }
    if (elevator_detection_is_child_like(lhs, frame_width, frame_height) != 0 ||
        elevator_detection_is_child_like(rhs, frame_width, frame_height) != 0) {
        return 0;
    }

    lhs_area = elevator_rect_area(&lhs->rect);
    rhs_area = elevator_rect_area(&rhs->rect);
    min_area = elevator_min_u64(lhs_area, rhs_area);
    max_area = elevator_max_u64(lhs_area, rhs_area);
    if (min_area == 0 || max_area == 0) {
        return 0;
    }

    size_ratio_percent = (min_area * 100ULL) / max_area;
    if (size_ratio_percent < ELEVATOR_DUPLICATE_CLUSTER_MIN_SIZE_RATIO_PERCENT ||
        size_ratio_percent > ELEVATOR_DUPLICATE_CLUSTER_MAX_SIZE_RATIO_PERCENT) {
        if (elevator_rect_touches_frame_edge(&lhs->rect, frame_width, frame_height) == 0 &&
            elevator_rect_touches_frame_edge(&rhs->rect, frame_width, frame_height) == 0) {
            return 0;
        }
    }

    iou = elevator_rect_iou(&lhs->rect, &rhs->rect);
    smaller_coverage_percent = elevator_rect_coverage_percent(
        lhs_area >= rhs_area ? &lhs->rect : &rhs->rect,
        lhs_area < rhs_area ? &lhs->rect : &rhs->rect);

    min_frame_side = frame_width < frame_height ? frame_width : frame_height;
    frame_diag_sq = (uint64_t)min_frame_side * (uint64_t)min_frame_side;
    center_dist_sq = elevator_rect_center_distance_sq(&lhs->rect, &rhs->rect);
    max_center_distance_sq = (frame_diag_sq * ELEVATOR_DUPLICATE_CLUSTER_MAX_CENTER_DISTANCE_PERCENT *
        ELEVATOR_DUPLICATE_CLUSTER_MAX_CENTER_DISTANCE_PERCENT) / 10000ULL;

    if (iou >= ELEVATOR_DUPLICATE_CLUSTER_IOU_THRESHOLD) {
        return 1;
    }
    if (smaller_coverage_percent >= 42ULL &&
        center_dist_sq <= max_center_distance_sq &&
        iou >= ELEVATOR_DUPLICATE_CLUSTER_EDGE_IOU_THRESHOLD) {
        return 1;
    }
    return 0;
}

static int elevator_person_boxes_look_like_child_duplicate(const elevator_detection_result *lhs,
    const elevator_detection_result *rhs, uint32_t frame_width, uint32_t frame_height)
{
    int lhs_child;
    int rhs_child;
    uint64_t lhs_area;
    uint64_t rhs_area;
    uint64_t min_area;
    uint64_t max_area;
    uint64_t size_ratio_percent;
    uint64_t smaller_coverage_percent;
    uint64_t center_dist_sq;
    uint64_t frame_diag_sq;
    uint64_t max_center_distance_sq;
    uint64_t frame_area;
    uint64_t other_area_percent;
    const elevator_detection_result *child_box;
    const elevator_detection_result *other_box;
    uint32_t child_height;
    uint32_t top_delta;
    uint32_t min_frame_side;

    if (lhs == NULL || rhs == NULL || lhs->class_id != 0U || rhs->class_id != 0U ||
        frame_width == 0U || frame_height == 0U) {
        return 0;
    }

    lhs_child = elevator_detection_is_child_like(lhs, frame_width, frame_height);
    rhs_child = elevator_detection_is_child_like(rhs, frame_width, frame_height);
    if (lhs_child == 0 && rhs_child == 0) {
        return 0;
    }

    lhs_area = elevator_rect_area(&lhs->rect);
    rhs_area = elevator_rect_area(&rhs->rect);
    min_area = elevator_min_u64(lhs_area, rhs_area);
    max_area = elevator_max_u64(lhs_area, rhs_area);
    if (min_area == 0U || max_area == 0U) {
        return 0;
    }

    size_ratio_percent = (min_area * 100ULL) / max_area;
    if (size_ratio_percent < ELEVATOR_CHILD_DUPLICATE_MIN_SIZE_RATIO_PERCENT ||
        size_ratio_percent > ELEVATOR_CHILD_DUPLICATE_MAX_SIZE_RATIO_PERCENT) {
        return 0;
    }

    smaller_coverage_percent = elevator_rect_coverage_percent(
        lhs_area >= rhs_area ? &lhs->rect : &rhs->rect,
        lhs_area < rhs_area ? &lhs->rect : &rhs->rect);
    min_frame_side = frame_width < frame_height ? frame_width : frame_height;
    frame_diag_sq = (uint64_t)min_frame_side * (uint64_t)min_frame_side;
    center_dist_sq = elevator_rect_center_distance_sq(&lhs->rect, &rhs->rect);
    max_center_distance_sq = (frame_diag_sq * ELEVATOR_CHILD_DUPLICATE_MAX_CENTER_DISTANCE_PERCENT *
        ELEVATOR_CHILD_DUPLICATE_MAX_CENTER_DISTANCE_PERCENT) / 10000ULL;
    if (center_dist_sq > max_center_distance_sq) {
        return 0;
    }

    if (lhs_child != 0 && rhs_child != 0) {
        return smaller_coverage_percent >= ELEVATOR_CHILD_DUPLICATE_MIN_COVERAGE_PERCENT ? 1 : 0;
    }

    child_box = lhs_child != 0 ? lhs : rhs;
    other_box = lhs_child != 0 ? rhs : lhs;
    child_height = elevator_rect_height(&child_box->rect);
    frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    other_area_percent = frame_area == 0U ? 0U : (elevator_rect_area(&other_box->rect) * 100ULL) / frame_area;
    top_delta = child_box->rect.y1 > other_box->rect.y1 ?
        child_box->rect.y1 - other_box->rect.y1 : other_box->rect.y1 - child_box->rect.y1;

    if (other_area_percent > ELEVATOR_CHILD_DUPLICATE_MAX_NON_CHILD_AREA_PERCENT) {
        return 0;
    }
    if (elevator_rect_area(&child_box->rect) > elevator_rect_area(&other_box->rect) &&
        smaller_coverage_percent >= ELEVATOR_CHILD_DUPLICATE_LARGE_CHILD_MIN_COVERAGE_PERCENT &&
        other_box->score >= child_box->score + ELEVATOR_CHILD_DUPLICATE_LARGE_CHILD_MIN_SCORE_MARGIN &&
        child_height != 0U &&
        top_delta * 100U <= child_height * ELEVATOR_CHILD_DUPLICATE_LARGE_CHILD_MAX_TOP_DELTA_PERCENT &&
        elevator_rect_contains_point(&child_box->rect,
            elevator_rect_center_x(&other_box->rect),
            elevator_rect_center_y(&other_box->rect)) != 0) {
        return 1;
    }
    if (smaller_coverage_percent < ELEVATOR_CHILD_DUPLICATE_MIXED_COVERAGE_PERCENT) {
        return 0;
    }
    if (child_height == 0U || top_delta * 100U > child_height * ELEVATOR_CHILD_DUPLICATE_MAX_TOP_DELTA_PERCENT) {
        return 0;
    }
    if (other_box->score > child_box->score + ELEVATOR_CHILD_DUPLICATE_MAX_SCORE_MARGIN) {
        return 0;
    }
    if (elevator_rect_contains_point(&other_box->rect,
            elevator_rect_center_x(&child_box->rect),
            elevator_rect_center_y(&child_box->rect)) == 0) {
        return 0;
    }
    return 1;
}

static int elevator_low_score_large_box_has_high_score_coverage(const elevator_detection_result *candidate,
    const elevator_detection_result *detections, size_t count, size_t candidate_idx)
{
    uint32_t multi_coverage_hits = 0;
    uint64_t candidate_area;
    size_t idx;

    if (candidate == NULL || detections == NULL || candidate_idx >= count) {
        return 0;
    }

    candidate_area = elevator_rect_area(&candidate->rect);
    if (candidate_area == 0) {
        return 0;
    }

    for (idx = 0; idx < count; ++idx) {
        uint64_t other_area;
        uint64_t coverage_percent;

        if (idx == candidate_idx) {
            continue;
        }
        if (detections[idx].class_id != candidate->class_id) {
            continue;
        }
        if (detections[idx].score < candidate->score + ELEVATOR_LOW_SCORE_LARGE_BOX_SCORE_MARGIN) {
            continue;
        }

        other_area = elevator_rect_area(&detections[idx].rect);
        if (other_area == 0 || other_area >= candidate_area) {
            continue;
        }

        coverage_percent = elevator_rect_coverage_percent(&candidate->rect, &detections[idx].rect);
        if (coverage_percent >= ELEVATOR_LOW_SCORE_LARGE_BOX_SINGLE_COVERAGE_PERCENT) {
            return 1;
        }
        if (coverage_percent >= ELEVATOR_LOW_SCORE_LARGE_BOX_MULTI_COVERAGE_PERCENT) {
            multi_coverage_hits++;
            if (multi_coverage_hits >= ELEVATOR_LOW_SCORE_LARGE_BOX_MULTI_COVER_COUNT) {
                return 1;
            }
        }
    }

    return 0;
}

static int elevator_low_score_large_box_has_child_like_support(const elevator_detection_result *candidate,
    const elevator_detection_result *detections, size_t count, size_t candidate_idx,
    uint32_t frame_width, uint32_t frame_height)
{
    uint64_t candidate_area;
    uint64_t frame_area;
    uint64_t area_percent;
    uint64_t frame_diag_sq;
    uint64_t max_center_distance_sq;
    size_t idx;

    if (candidate == NULL || detections == NULL || candidate_idx >= count ||
        candidate->class_id != 0U || !isfinite(candidate->score) ||
        frame_width == 0U || frame_height == 0U) {
        return 0;
    }

    candidate_area = elevator_rect_area(&candidate->rect);
    frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    if (candidate_area == 0U || frame_area == 0U ||
        elevator_detection_is_child_like(candidate, frame_width, frame_height) != 0) {
        return 0;
    }

    area_percent = (candidate_area * 100ULL) / frame_area;
    if (area_percent < ELEVATOR_LOW_SCORE_LARGE_BOX_CHILD_CONFLICT_MIN_AREA_PERCENT) {
        return 0;
    }

    frame_diag_sq = (uint64_t)frame_width * (uint64_t)frame_width +
        (uint64_t)frame_height * (uint64_t)frame_height;
    max_center_distance_sq = (frame_diag_sq *
        ELEVATOR_LOW_SCORE_LARGE_BOX_CHILD_CONFLICT_MAX_CENTER_DISTANCE_PERCENT *
        ELEVATOR_LOW_SCORE_LARGE_BOX_CHILD_CONFLICT_MAX_CENTER_DISTANCE_PERCENT) / 10000ULL;

    for (idx = 0; idx < count; ++idx) {
        uint64_t child_area;
        uint64_t coverage_percent;
        uint64_t center_dist_sq;

        if (idx == candidate_idx || detections[idx].class_id != 0U ||
            !isfinite(detections[idx].score) ||
            elevator_detection_is_child_like(&detections[idx], frame_width, frame_height) == 0) {
            continue;
        }

        child_area = elevator_rect_area(&detections[idx].rect);
        if (child_area == 0U || child_area >= candidate_area) {
            continue;
        }

        coverage_percent = elevator_rect_coverage_percent(&candidate->rect, &detections[idx].rect);
        if (coverage_percent < ELEVATOR_LOW_SCORE_LARGE_BOX_CHILD_CONFLICT_MIN_COVERAGE_PERCENT) {
            continue;
        }

        center_dist_sq = elevator_rect_center_distance_sq(&candidate->rect, &detections[idx].rect);
        if (center_dist_sq > max_center_distance_sq) {
            continue;
        }
        if (elevator_rect_contains_point(&candidate->rect,
                elevator_rect_center_x(&detections[idx].rect),
                elevator_rect_center_y(&detections[idx].rect)) == 0) {
            continue;
        }
        return 1;
    }

    return 0;
}

static int elevator_is_edge_person_umbrella_box(const elevator_detection_result *candidate,
    const elevator_detection_result *detections, size_t count, size_t candidate_idx,
    uint32_t frame_width, uint32_t frame_height)
{
    uint64_t frame_area;
    uint64_t candidate_area;
    uint64_t area_percent;
    uint64_t combined_supporter_area = 0;
    uint32_t strong_supporter_count = 0;
    uint32_t supporter_count = 0;
    size_t idx;

    if (candidate == NULL || detections == NULL || candidate_idx >= count) {
        return 0;
    }
    if (candidate->class_id != 0U || !isfinite(candidate->score) ||
        elevator_rect_touches_frame_edge(&candidate->rect, frame_width, frame_height) == 0) {
        return 0;
    }

    frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    candidate_area = elevator_rect_area(&candidate->rect);
    if (frame_area == 0 || candidate_area == 0) {
        return 0;
    }

    area_percent = (candidate_area * 100ULL) / frame_area;
    if (area_percent < ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_AREA_PERCENT) {
        return 0;
    }
    if (candidate->score <= ELEVATOR_EDGE_PERSON_CORNER_UMBRELLA_SCORE_CEILING &&
        area_percent >= ELEVATOR_EDGE_PERSON_CORNER_UMBRELLA_MIN_AREA_PERCENT &&
        elevator_rect_touches_top_edge(&candidate->rect) != 0 &&
        elevator_rect_touches_right_edge(&candidate->rect, frame_width) != 0 &&
        elevator_rect_width(&candidate->rect) * 100ULL >=
            (uint64_t)frame_width * ELEVATOR_EDGE_PERSON_CORNER_UMBRELLA_MIN_WIDTH_PERCENT &&
        elevator_rect_height(&candidate->rect) * 100ULL >=
            (uint64_t)frame_height * ELEVATOR_EDGE_PERSON_CORNER_UMBRELLA_MIN_HEIGHT_PERCENT) {
        return 1;
    }
    if (candidate->score <= ELEVATOR_EDGE_PERSON_UMBRELLA_LOW_SCORE_CEILING) {
        return 1;
    }
    if (area_percent < ELEVATOR_EDGE_PERSON_UMBRELLA_LARGE_AREA_PERCENT ||
        candidate->score > ELEVATOR_EDGE_PERSON_UMBRELLA_HIGH_SCORE_CEILING) {
        return 0;
    }

    for (idx = 0; idx < count; ++idx) {
        uint64_t other_area;
        uint32_t center_x;
        uint32_t center_y;

        if (idx == candidate_idx) {
            continue;
        }
        if (detections[idx].class_id != candidate->class_id || !isfinite(detections[idx].score) ||
            detections[idx].score < ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_SUPPORTER_SCORE) {
            continue;
        }

        other_area = elevator_rect_area(&detections[idx].rect);
        if (other_area == 0 || other_area >= candidate_area) {
            continue;
        }

        center_x = detections[idx].rect.x1 + elevator_rect_width(&detections[idx].rect) / 2U;
        center_y = detections[idx].rect.y1 + elevator_rect_height(&detections[idx].rect) / 2U;
        if (elevator_rect_contains_point(&candidate->rect, center_x, center_y) == 0) {
            continue;
        }

        if (elevator_detection_is_child_like(&detections[idx], frame_width, frame_height) != 0 &&
            area_percent >= ELEVATOR_EDGE_PERSON_UMBRELLA_CHILD_AREA_PERCENT &&
            candidate->score <= ELEVATOR_EDGE_PERSON_UMBRELLA_CHILD_SCORE_CEILING) {
            return 1;
        }
        if ((other_area * 100ULL) / frame_area < ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_SUPPORTER_AREA_PERCENT) {
            continue;
        }

        supporter_count++;
        combined_supporter_area += other_area;
        if (detections[idx].score >= ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_STRONG_SUPPORTER_SCORE) {
            strong_supporter_count++;
        }
        if (strong_supporter_count >= 1U &&
            supporter_count >= ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_SUPPORTER_COUNT &&
            combined_supporter_area * 100ULL >=
                candidate_area * ELEVATOR_EDGE_PERSON_UMBRELLA_MIN_COMBINED_AREA_PERCENT) {
            return 1;
        }
    }

    return 0;
}

static int elevator_ebike_has_stronger_sibling_coverage(const elevator_detection_result *candidate,
    const elevator_detection_result *detections, size_t count, size_t candidate_idx)
{
    size_t idx;

    if (candidate == NULL || detections == NULL || candidate->class_id != 1U ||
        !isfinite(candidate->score) || candidate->score > ELEVATOR_EBIKE_DUPLICATE_SCORE_CEILING) {
        return 0;
    }

    for (idx = 0; idx < count; ++idx) {
        uint64_t coverage_percent;

        if (idx == candidate_idx) {
            continue;
        }
        if (detections[idx].class_id != 1U ||
            detections[idx].score < candidate->score + ELEVATOR_EBIKE_DUPLICATE_SCORE_MARGIN) {
            continue;
        }

        coverage_percent = elevator_rect_coverage_percent(&detections[idx].rect, &candidate->rect);
        if (coverage_percent >= ELEVATOR_EBIKE_DUPLICATE_MIN_COVERAGE_PERCENT) {
            return 1;
        }
    }

    return 0;
}

static int elevator_ebike_looks_like_person_container(const elevator_detection_result *candidate,
    const elevator_detection_result *detections, size_t count, size_t candidate_idx,
    uint32_t frame_width, uint32_t frame_height)
{
    uint64_t frame_area;
    uint64_t candidate_area;
    uint64_t area_percent;
    uint32_t width;
    uint32_t height;
    size_t idx;

    if (candidate == NULL || detections == NULL || candidate->class_id != 1U ||
        !isfinite(candidate->score) || candidate->score > ELEVATOR_EBIKE_PERSON_CONTAINER_SCORE_CEILING) {
        return 0;
    }

    frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    candidate_area = elevator_rect_area(&candidate->rect);
    width = elevator_rect_width(&candidate->rect);
    height = elevator_rect_height(&candidate->rect);
    if (frame_area == 0U || candidate_area == 0U || width == 0U || height == 0U) {
        return 0;
    }

    area_percent = (candidate_area * 100ULL) / frame_area;
    if (area_percent < ELEVATOR_EBIKE_PERSON_CONTAINER_MIN_AREA_PERCENT ||
        width * 100ULL < (uint64_t)height * ELEVATOR_EBIKE_PERSON_CONTAINER_MIN_WIDTH_TO_HEIGHT_PERCENT) {
        return 0;
    }

    for (idx = 0; idx < count; ++idx) {
        uint64_t coverage_percent;

        if (idx == candidate_idx) {
            continue;
        }
        if (detections[idx].class_id != 0U ||
            detections[idx].score < ELEVATOR_EBIKE_PERSON_CONTAINER_MIN_PERSON_SCORE) {
            continue;
        }

        coverage_percent = elevator_rect_coverage_percent(&candidate->rect, &detections[idx].rect);
        if (coverage_percent >= ELEVATOR_EBIKE_PERSON_CONTAINER_MIN_COVERAGE_PERCENT) {
            return 1;
        }
    }

    return 0;
}

static int elevator_ebike_looks_like_top_edge_person(const elevator_detection_result *candidate,
    uint32_t frame_width, uint32_t frame_height)
{
    uint64_t frame_area;
    uint64_t candidate_area;
    uint64_t area_percent;
    uint64_t height_percent;
    uint32_t width;
    uint32_t height;

    if (candidate == NULL || candidate->class_id != 1U || !isfinite(candidate->score) ||
        frame_width == 0U || frame_height == 0U) {
        return 0;
    }

    frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    candidate_area = elevator_rect_area(&candidate->rect);
    width = elevator_rect_width(&candidate->rect);
    height = elevator_rect_height(&candidate->rect);
    if (frame_area == 0ULL || candidate_area == 0ULL || width == 0U || height == 0U) {
        return 0;
    }

    area_percent = (candidate_area * 100ULL) / frame_area;
    height_percent = ((uint64_t)height * 100ULL) / (uint64_t)frame_height;
    if (candidate->score <= ELEVATOR_EBIKE_TOP_EDGE_PERSON_SCORE_CEILING &&
        area_percent >= ELEVATOR_EBIKE_TOP_EDGE_PERSON_MIN_AREA_PERCENT &&
        height_percent >= ELEVATOR_EBIKE_TOP_EDGE_PERSON_MIN_HEIGHT_PERCENT &&
        candidate->rect.y1 <= ((frame_height / 9U) > (ELEVATOR_FRAME_EDGE_MARGIN_PX * 3U) ?
            (frame_height / 9U) : (ELEVATOR_FRAME_EDGE_MARGIN_PX * 3U)) &&
        (uint64_t)height * 100ULL >= (uint64_t)width * ELEVATOR_EBIKE_TOP_EDGE_PERSON_MIN_HEIGHT_TO_WIDTH_PERCENT) {
        return 1;
    }
    return 0;
}

static int elevator_ebike_looks_like_person_clone(const elevator_detection_result *candidate,
    const elevator_detection_result *detections, size_t count, size_t candidate_idx,
    uint32_t frame_width, uint32_t frame_height)
{
    uint64_t frame_area;
    uint64_t candidate_area;
    uint64_t area_percent;
    size_t idx;

    if (candidate == NULL || candidate->class_id != 1U || !isfinite(candidate->score) ||
        frame_width == 0U || frame_height == 0U) {
        return 0;
    }

    frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    candidate_area = elevator_rect_area(&candidate->rect);
    if (frame_area == 0ULL || candidate_area == 0ULL) {
        return 0;
    }
    area_percent = (candidate_area * 100ULL) / frame_area;
    if (candidate->score > ELEVATOR_EBIKE_PERSON_CLONE_SCORE_CEILING ||
        area_percent < ELEVATOR_EBIKE_PERSON_CLONE_MIN_AREA_PERCENT) {
        return 0;
    }

    for (idx = 0; idx < count; ++idx) {
        uint64_t coverage_percent;
        uint32_t candidate_width;
        uint32_t candidate_height;
        uint32_t person_width;
        uint32_t person_height;

        if (idx == candidate_idx) {
            continue;
        }
        if (detections[idx].class_id != 0U ||
            detections[idx].score < ELEVATOR_EBIKE_PERSON_CLONE_MIN_PERSON_SCORE) {
            continue;
        }

        coverage_percent = elevator_rect_coverage_percent(&candidate->rect, &detections[idx].rect);
        if (coverage_percent < ELEVATOR_EBIKE_PERSON_CLONE_MIN_COVERAGE_PERCENT) {
            continue;
        }

        candidate_width = elevator_rect_width(&candidate->rect);
        candidate_height = elevator_rect_height(&candidate->rect);
        person_width = elevator_rect_width(&detections[idx].rect);
        person_height = elevator_rect_height(&detections[idx].rect);
        if (candidate_width == 0U || candidate_height == 0U || person_width == 0U || person_height == 0U) {
            continue;
        }
        if ((uint64_t)candidate_width * 100ULL <=
                (uint64_t)person_width * ELEVATOR_EBIKE_PERSON_CLONE_MAX_WIDTH_RATIO_PERCENT &&
            (uint64_t)candidate_height * 100ULL <=
                (uint64_t)person_height * ELEVATOR_EBIKE_PERSON_CLONE_MAX_HEIGHT_RATIO_PERCENT) {
            return 1;
        }
    }

    return 0;
}

static int elevator_should_suppress_ebike_false_positive(const elevator_detection_result *candidate,
    const elevator_detection_result *detections, size_t count, size_t candidate_idx,
    uint32_t frame_width, uint32_t frame_height)
{
    uint64_t frame_area;
    uint64_t candidate_area;
    uint64_t area_percent;
    uint64_t height_percent;
    uint32_t width;
    uint32_t height;

    if (candidate == NULL || candidate->class_id != 1U || !isfinite(candidate->score)) {
        return 0;
    }

    frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    candidate_area = elevator_rect_area(&candidate->rect);
    width = elevator_rect_width(&candidate->rect);
    height = elevator_rect_height(&candidate->rect);
    if (frame_area == 0 || candidate_area == 0 || width == 0 || height == 0) {
        return 0;
    }

    area_percent = (candidate_area * 100ULL) / frame_area;
    height_percent = ((uint64_t)height * 100ULL) / frame_height;
    if (candidate->score <= ELEVATOR_EBIKE_HUGE_BOX_SCORE_CEILING &&
        area_percent >= ELEVATOR_EBIKE_HUGE_BOX_MIN_AREA_PERCENT) {
        return 1;
    }
    if (candidate->score <= ELEVATOR_EBIKE_TALL_HUMAN_SCORE_CEILING &&
        area_percent >= ELEVATOR_EBIKE_TALL_HUMAN_MIN_AREA_PERCENT &&
        height * 100ULL >= (uint64_t)width * ELEVATOR_EBIKE_TALL_HUMAN_MIN_HEIGHT_TO_WIDTH_PERCENT &&
        height_percent >= ELEVATOR_EBIKE_TALL_HUMAN_MIN_HEIGHT_PERCENT &&
        elevator_rect_touches_top_edge(&candidate->rect) != 0) {
        return 1;
    }
    if (candidate->score <= ELEVATOR_EBIKE_TOP_STRIP_SCORE_CEILING &&
        area_percent <= ELEVATOR_EBIKE_TOP_STRIP_MAX_AREA_PERCENT &&
        height_percent <= ELEVATOR_EBIKE_TOP_STRIP_MAX_HEIGHT_PERCENT &&
        elevator_rect_touches_top_edge(&candidate->rect) != 0 &&
        width * 100ULL >= (uint64_t)height * ELEVATOR_EBIKE_TOP_STRIP_MIN_WIDTH_TO_HEIGHT_PERCENT) {
        return 1;
    }
    if (elevator_ebike_has_stronger_sibling_coverage(candidate, detections, count, candidate_idx) != 0) {
        return 1;
    }
    if (elevator_ebike_looks_like_person_container(candidate, detections, count, candidate_idx,
            frame_width, frame_height) != 0) {
        return 1;
    }
    if (elevator_ebike_looks_like_top_edge_person(candidate, frame_width, frame_height) != 0) {
        return 1;
    }
    if (elevator_ebike_looks_like_person_clone(candidate, detections, count, candidate_idx,
            frame_width, frame_height) != 0) {
        return 1;
    }

    return 0;
}

static size_t elevator_apply_low_score_large_box_cleanup(elevator_detection_result *detections, size_t count,
    uint32_t frame_width, uint32_t frame_height)
{
    size_t write_idx = 0;
    uint64_t frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    size_t idx;

    if (detections == NULL || count == 0 || frame_area == 0) {
        return count;
    }

    for (idx = 0; idx < count; ++idx) {
        uint64_t area_percent;
        uint64_t detection_area;
        int suppress = 0;

        if (detections[idx].class_id != 0U || !isfinite(detections[idx].score) ||
            detections[idx].score > ELEVATOR_LOW_SCORE_LARGE_BOX_SCORE_CEILING) {
            if (write_idx != idx) {
                detections[write_idx] = detections[idx];
            }
            write_idx++;
            continue;
        }

        detection_area = elevator_rect_area(&detections[idx].rect);
        area_percent = (detection_area * 100ULL) / frame_area;
        if (area_percent >= ELEVATOR_LOW_SCORE_LARGE_BOX_ALWAYS_DROP_AREA_PERCENT) {
            suppress = 1;
        } else if (detections[idx].score <= ELEVATOR_LOW_SCORE_LARGE_BOX_EDGE_SCORE_CEILING &&
            elevator_rect_touches_frame_edge(&detections[idx].rect, frame_width, frame_height)) {
            suppress = 1;
        } else if (elevator_low_score_large_box_has_child_like_support(&detections[idx], detections, count, idx,
                frame_width, frame_height) != 0) {
            suppress = 1;
        } else if (area_percent >= ELEVATOR_LOW_SCORE_LARGE_BOX_PARTIAL_AREA_PERCENT &&
            elevator_low_score_large_box_has_high_score_coverage(&detections[idx], detections, count, idx)) {
            suppress = 1;
        }

        if (suppress == 0) {
            if (write_idx != idx) {
                detections[write_idx] = detections[idx];
            }
            write_idx++;
        }
    }

    return write_idx;
}

static size_t elevator_apply_class_specific_false_positive_cleanup(elevator_detection_result *detections, size_t count,
    uint32_t frame_width, uint32_t frame_height, int ebike_fp_cleanup_mode)
{
    size_t write_idx = 0;
    size_t idx;

    if (detections == NULL || count == 0) {
        return 0;
    }

    for (idx = 0; idx < count; ++idx) {
        if (detections[idx].class_id == 0U &&
            elevator_is_edge_person_umbrella_box(&detections[idx], detections, count, idx,
                frame_width, frame_height) != 0) {
            continue;
        }
        if (detections[idx].class_id == 1U) {
            if (ebike_fp_cleanup_mode >= ELEVATOR_EBIKE_FP_CLEANUP_SAFE) {
                if (elevator_ebike_has_stronger_sibling_coverage(&detections[idx], detections, count, idx) != 0) {
                    continue;
                }
                if (detections[idx].score <= ELEVATOR_EBIKE_TOP_STRIP_SCORE_CEILING) {
                    uint64_t frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
                    uint64_t candidate_area = elevator_rect_area(&detections[idx].rect);
                    uint64_t area_percent = frame_area == 0ULL ? 0ULL : (candidate_area * 100ULL) / frame_area;
                    uint64_t height_percent = frame_height == 0U ? 0ULL :
                        ((uint64_t)elevator_rect_height(&detections[idx].rect) * 100ULL) / (uint64_t)frame_height;
                    uint32_t width = elevator_rect_width(&detections[idx].rect);
                    uint32_t height = elevator_rect_height(&detections[idx].rect);
                    if (width != 0U && height != 0U &&
                        area_percent <= ELEVATOR_EBIKE_TOP_STRIP_MAX_AREA_PERCENT &&
                        height_percent <= ELEVATOR_EBIKE_TOP_STRIP_MAX_HEIGHT_PERCENT &&
                        elevator_rect_touches_top_edge(&detections[idx].rect) != 0 &&
                        width * 100ULL >= (uint64_t)height * ELEVATOR_EBIKE_TOP_STRIP_MIN_WIDTH_TO_HEIGHT_PERCENT) {
                        continue;
                    }
                }
            }
            if (ebike_fp_cleanup_mode >= ELEVATOR_EBIKE_FP_CLEANUP_FULL &&
                elevator_should_suppress_ebike_false_positive(&detections[idx],
                    detections, count, idx,
                    frame_width, frame_height) != 0) {
                continue;
            }
        }

        if (write_idx != idx) {
            detections[write_idx] = detections[idx];
        }
        write_idx++;
    }

    return write_idx;
}

static size_t elevator_apply_duplicate_cluster_cleanup(elevator_detection_result *detections, size_t count,
    uint32_t frame_width, uint32_t frame_height)
{
    unsigned char suppressed[ELEVATOR_MAX_DETECTIONS];
    size_t write_idx = 0;
    size_t i;
    size_t j;

    if (detections == NULL || count == 0) {
        return 0;
    }

    memset(suppressed, 0, sizeof(suppressed));
    for (i = 0; i < count; ++i) {
        if (suppressed[i] != 0 || detections[i].class_id != 0U) {
            continue;
        }

        for (j = i + 1; j < count; ++j) {
            float lhs_quality;
            float rhs_quality;

            if (suppressed[j] != 0 || detections[j].class_id != detections[i].class_id) {
                continue;
            }
            if (elevator_person_boxes_look_like_duplicate(&detections[i], &detections[j],
                    frame_width, frame_height) == 0) {
                continue;
            }

            lhs_quality = elevator_detection_quality_score(&detections[i], frame_width, frame_height);
            rhs_quality = elevator_detection_quality_score(&detections[j], frame_width, frame_height);
            if (rhs_quality > lhs_quality + 0.02f) {
                suppressed[i] = 1;
                break;
            }
            suppressed[j] = 1;
        }
    }

    for (i = 0; i < count; ++i) {
        if (suppressed[i] != 0) {
            continue;
        }
        if (write_idx != i) {
            detections[write_idx] = detections[i];
        }
        write_idx++;
    }

    return write_idx;
}

static size_t elevator_apply_containment_cleanup(elevator_detection_result *detections, size_t count,
    uint32_t frame_width, uint32_t frame_height)
{
    unsigned char suppressed[ELEVATOR_MAX_DETECTIONS];
    size_t write_idx = 0;
    size_t i;
    size_t j;

    if (detections == NULL || count == 0) {
        return 0;
    }

    memset(suppressed, 0, sizeof(suppressed));
    for (i = 0; i < count; ++i) {
        uint64_t anchor_area;

        if (suppressed[i] != 0) {
            continue;
        }
        anchor_area = elevator_rect_area(&detections[i].rect);
        if (anchor_area == 0) {
            continue;
        }

        for (j = i + 1; j < count; ++j) {
            uint64_t candidate_area;
            uint64_t intersection_area;

            if (suppressed[j] != 0) {
                continue;
            }
            if (detections[j].class_id != detections[i].class_id) {
                continue;
            }
            if (detections[i].score < detections[j].score + ELEVATOR_CONTAINMENT_MIN_SCORE_MARGIN) {
                continue;
            }

            candidate_area = elevator_rect_area(&detections[j].rect);
            if (candidate_area == 0) {
                continue;
            }
            if (detections[j].class_id == 0U &&
                elevator_detection_is_child_like(&detections[j], frame_width, frame_height) != 0 &&
                elevator_detection_is_child_like(&detections[i], frame_width, frame_height) == 0) {
                continue;
            }
            if (anchor_area < candidate_area * ELEVATOR_CONTAINMENT_MIN_AREA_RATIO) {
                continue;
            }

            intersection_area = elevator_rect_intersection_area(&detections[i].rect, &detections[j].rect);
            if (intersection_area * 100ULL < candidate_area * ELEVATOR_CONTAINMENT_MIN_COVERAGE_PERCENT) {
                continue;
            }

            suppressed[j] = 1;
        }

        if (write_idx != i) {
            detections[write_idx] = detections[i];
        }
        write_idx++;
    }

    return write_idx;
}

static void elevator_sort_detections_by_score(elevator_detection_result *detections, size_t count)
{
    size_t i;
    size_t j;

    for (i = 1; i < count; ++i) {
        elevator_detection_result key = detections[i];
        j = i;
        while (j > 0 && detections[j - 1].score < key.score) {
            detections[j] = detections[j - 1];
            --j;
        }
        detections[j] = key;
    }
}

static size_t elevator_apply_nms(elevator_detection_result *detections, size_t count, float nms_threshold)
{
    unsigned char suppressed[ELEVATOR_MAX_DETECTIONS];
    size_t write_idx = 0;
    size_t i;
    size_t j;

    if (detections == NULL || count == 0) {
        return 0;
    }

    memset(suppressed, 0, sizeof(suppressed));
    elevator_sort_detections_by_score(detections, count);

    for (i = 0; i < count; ++i) {
        if (suppressed[i] != 0) {
            continue;
        }

        if (write_idx != i) {
            detections[write_idx] = detections[i];
        }
        for (j = i + 1; j < count; ++j) {
            if (suppressed[j] != 0) {
                continue;
            }
            if (detections[j].class_id != detections[i].class_id) {
                continue;
            }
            if (elevator_rect_iou(&detections[i].rect, &detections[j].rect) > nms_threshold) {
                suppressed[j] = 1;
            }
        }
        write_idx++;
    }

    return write_idx;
}

static uint32_t elevator_find_median(const uint32_t *values, uint32_t count)
{
    uint32_t sorted[ELEVATOR_MAX_SMOOTH_WINDOW];
    uint32_t i;
    uint32_t j;

    if (count == 0) {
        return 0;
    }

    memcpy(sorted, values, count * sizeof(sorted[0]));
    for (i = 1; i < count; ++i) {
        uint32_t key = sorted[i];
        j = i;
        while (j > 0 && sorted[j - 1] > key) {
            sorted[j] = sorted[j - 1];
            --j;
        }
        sorted[j] = key;
    }
    return sorted[count / 2];
}

static void elevator_collect_history_window(const uint32_t *history, uint32_t window_size,
    uint32_t filled, uint32_t next_index, uint32_t *values)
{
    uint32_t idx;

    if (history == NULL || values == NULL || filled == 0) {
        return;
    }

    if (filled < window_size) {
        memcpy(values, history, filled * sizeof(values[0]));
        return;
    }

    for (idx = 0; idx < window_size; ++idx) {
        values[idx] = history[(next_index + idx) % window_size];
    }
}

void elevator_smoother_reset(elevator_smoother *smoother, uint32_t window_size)
{
    if (smoother == NULL) {
        return;
    }

    memset(smoother, 0, sizeof(*smoother));
    if (window_size == 0) {
        smoother->window_size = 1;
    } else if (window_size > ELEVATOR_MAX_SMOOTH_WINDOW) {
        smoother->window_size = ELEVATOR_MAX_SMOOTH_WINDOW;
    } else {
        smoother->window_size = window_size;
    }
}

void elevator_smoother_update(elevator_smoother *smoother, uint32_t person_count,
    uint32_t ebike_count, uint64_t timestamp_ms, elevator_count_stats *stats)
{
    uint32_t person_values[ELEVATOR_MAX_SMOOTH_WINDOW];
    uint32_t ebike_values[ELEVATOR_MAX_SMOOTH_WINDOW];
    uint32_t valid_count;

    if (smoother == NULL || stats == NULL) {
        return;
    }

    smoother->person_history[smoother->index] = person_count;
    smoother->ebike_history[smoother->index] = ebike_count;

    smoother->index = (smoother->index + 1) % smoother->window_size;
    if (smoother->filled < smoother->window_size) {
        smoother->filled++;
    }
    valid_count = smoother->filled;
    memset(person_values, 0, sizeof(person_values));
    memset(ebike_values, 0, sizeof(ebike_values));
    elevator_collect_history_window(smoother->person_history, smoother->window_size,
        valid_count, smoother->index, person_values);
    elevator_collect_history_window(smoother->ebike_history, smoother->window_size,
        valid_count, smoother->index, ebike_values);

    stats->person_count = person_count;
    stats->ebike_count = ebike_count;
    stats->smoothed_person_count = elevator_find_median(person_values, valid_count);
    stats->smoothed_ebike_count = elevator_find_median(ebike_values, valid_count);

    if (smoother->last_timestamp_ms == 0 || timestamp_ms <= smoother->last_timestamp_ms) {
        stats->fps = 0.0f;
    } else {
        stats->fps = 1000.0f / (float)(timestamp_ms - smoother->last_timestamp_ms);
    }
    smoother->last_timestamp_ms = timestamp_ms;
}

static size_t elevator_collect_class_detection_indices(const elevator_parse_result *result, uint32_t class_id,
    size_t *indices)
{
    size_t count = 0;
    size_t idx;

    if (result == NULL || indices == NULL) {
        return 0;
    }

    for (idx = 0; idx < result->detection_count && count < ELEVATOR_MAX_DETECTIONS; ++idx) {
        if (result->detections[idx].class_id == class_id) {
            indices[count++] = idx;
        }
    }
    return count;
}

static size_t elevator_match_detection_indices(const elevator_parse_result *lhs, const size_t *lhs_indices,
    size_t lhs_count, const elevator_parse_result *rhs, const size_t *rhs_indices, size_t rhs_count,
    float iou_threshold, unsigned char *lhs_matched, unsigned char *rhs_matched)
{
    size_t matches = 0;

    if (lhs == NULL || lhs_indices == NULL || rhs == NULL || rhs_indices == NULL ||
        lhs_matched == NULL || rhs_matched == NULL) {
        return 0;
    }

    memset(lhs_matched, 0, lhs_count * sizeof(lhs_matched[0]));
    memset(rhs_matched, 0, rhs_count * sizeof(rhs_matched[0]));
    while (1) {
        float best_iou = iou_threshold;
        size_t best_lhs = (size_t)-1;
        size_t best_rhs = (size_t)-1;
        size_t lhs_idx;
        size_t rhs_idx;

        for (lhs_idx = 0; lhs_idx < lhs_count; ++lhs_idx) {
            size_t det_lhs;

            if (lhs_matched[lhs_idx] != 0) {
                continue;
            }
            det_lhs = lhs_indices[lhs_idx];
            for (rhs_idx = 0; rhs_idx < rhs_count; ++rhs_idx) {
                float iou;

                if (rhs_matched[rhs_idx] != 0) {
                    continue;
                }
                iou = elevator_rect_iou(&lhs->detections[det_lhs].rect,
                    &rhs->detections[rhs_indices[rhs_idx]].rect);
                if (iou > best_iou) {
                    best_iou = iou;
                    best_lhs = lhs_idx;
                    best_rhs = rhs_idx;
                }
            }
        }

        if (best_lhs == (size_t)-1 || best_rhs == (size_t)-1) {
            break;
        }

        lhs_matched[best_lhs] = 1;
        rhs_matched[best_rhs] = 1;
        matches++;
    }

    return matches;
}

static int elevator_history_contains_matching_person(const elevator_parse_result *result,
    const elevator_detection_result *candidate)
{
    size_t idx;

    if (result == NULL || candidate == NULL) {
        return 0;
    }

    for (idx = 0; idx < result->detection_count; ++idx) {
        if (result->detections[idx].class_id != 0U) {
            continue;
        }
        if (elevator_rect_iou(&result->detections[idx].rect, &candidate->rect) >=
            ELEVATOR_SINGLE_PERSON_HOLD_IOU_THRESHOLD) {
            return 1;
        }
    }
    return 0;
}

static void elevator_temporal_hold_note_history(elevator_temporal_hold *hold,
    const elevator_parse_result *result, uint64_t timestamp_ms)
{
    if (hold == NULL || result == NULL) {
        return;
    }

    hold->history[hold->history_index] = *result;
    hold->history_timestamp_ms[hold->history_index] = timestamp_ms;
    hold->history_index = (hold->history_index + 1U) % ELEVATOR_TEMPORAL_HISTORY_FRAMES;
    if (hold->history_filled < ELEVATOR_TEMPORAL_HISTORY_FRAMES) {
        hold->history_filled++;
    }
}

static void elevator_temporal_hold_clear_carry(elevator_temporal_hold *hold)
{
    if (hold == NULL) {
        return;
    }

    hold->carry_active = 0;
    hold->carry_frames = 0;
    hold->carry_started_ms = 0;
    hold->consecutive_holds = 0;
    memset(&hold->carry_detection, 0, sizeof(hold->carry_detection));
}

static int elevator_temporal_hold_carry_is_valid(elevator_temporal_hold *hold, uint64_t timestamp_ms)
{
    if (hold == NULL || hold->carry_active == 0) {
        return 0;
    }
    if (hold->carry_frames >= hold->max_hold_frames) {
        elevator_temporal_hold_clear_carry(hold);
        return 0;
    }
    if (hold->carry_started_ms != 0 &&
        (timestamp_ms < hold->carry_started_ms ||
            timestamp_ms - hold->carry_started_ms > hold->max_hold_ms)) {
        elevator_temporal_hold_clear_carry(hold);
        return 0;
    }
    return 1;
}

static int elevator_temporal_hold_current_matches_carry(const elevator_temporal_hold *hold,
    const elevator_parse_result *result)
{
    size_t idx;

    if (hold == NULL || result == NULL || hold->carry_active == 0) {
        return 0;
    }

    for (idx = 0; idx < result->detection_count; ++idx) {
        if (result->detections[idx].class_id != 0U) {
            continue;
        }
        if (elevator_rect_iou(&result->detections[idx].rect, &hold->carry_detection.rect) >=
            ELEVATOR_SINGLE_PERSON_HOLD_IOU_THRESHOLD) {
            return 1;
        }
    }
    return 0;
}

static int elevator_temporal_hold_candidate_is_stable(const elevator_temporal_hold *hold,
    const elevator_detection_result *candidate, uint32_t frame_width, uint32_t frame_height)
{
    uint64_t frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    uint64_t candidate_area;
    uint64_t area_percent;
    uint32_t history_matches = 0;
    uint32_t idx;

    if (hold == NULL || candidate == NULL || frame_area == 0 || !isfinite(candidate->score) ||
        candidate->score < ELEVATOR_SINGLE_PERSON_HOLD_MIN_SCORE) {
        return 0;
    }

    candidate_area = elevator_rect_area(&candidate->rect);
    if (candidate_area == 0) {
        return 0;
    }
    area_percent = (candidate_area * 100ULL) / frame_area;
    if (area_percent < ELEVATOR_SINGLE_PERSON_HOLD_MIN_AREA_PERCENT ||
        area_percent > ELEVATOR_SINGLE_PERSON_HOLD_MAX_AREA_PERCENT) {
        return 0;
    }

    for (idx = 0; idx < hold->history_filled; ++idx) {
        if (elevator_history_contains_matching_person(&hold->history[idx], candidate) != 0) {
            history_matches++;
        }
    }
    return history_matches >= ELEVATOR_SINGLE_PERSON_HOLD_MIN_HISTORY_MATCHES ? 1 : 0;
}

static int elevator_temporal_hold_try_activate_single_person_carry(elevator_temporal_hold *hold,
    const elevator_parse_result *result, uint64_t timestamp_ms, uint32_t frame_width, uint32_t frame_height)
{
    size_t previous_indices[ELEVATOR_MAX_DETECTIONS];
    size_t current_indices[ELEVATOR_MAX_DETECTIONS];
    unsigned char previous_matched[ELEVATOR_MAX_DETECTIONS];
    unsigned char current_matched[ELEVATOR_MAX_DETECTIONS];
    size_t previous_count;
    size_t current_count;
    size_t unmatched_previous_idx = (size_t)-1;
    size_t previous_idx;

    if (hold == NULL || result == NULL || hold->has_previous == 0 || hold->carry_active != 0) {
        return 0;
    }
    if (hold->last_timestamp_ms != 0 &&
        (timestamp_ms < hold->last_timestamp_ms || timestamp_ms - hold->last_timestamp_ms > hold->max_hold_ms)) {
        return 0;
    }
    if (hold->previous_result.stats.person_count != result->stats.person_count + 1U) {
        return 0;
    }

    previous_count = elevator_collect_class_detection_indices(&hold->previous_result, 0U, previous_indices);
    current_count = elevator_collect_class_detection_indices(result, 0U, current_indices);
    if (previous_count == 0 || current_count + 1U != previous_count) {
        return 0;
    }

    (void)elevator_match_detection_indices(&hold->previous_result, previous_indices, previous_count,
        result, current_indices, current_count, ELEVATOR_SINGLE_PERSON_HOLD_IOU_THRESHOLD,
        previous_matched, current_matched);

    for (previous_idx = 0; previous_idx < previous_count; ++previous_idx) {
        if (previous_matched[previous_idx] == 0) {
            if (unmatched_previous_idx != (size_t)-1) {
                return 0;
            }
            unmatched_previous_idx = previous_idx;
        }
    }

    if (unmatched_previous_idx == (size_t)-1) {
        return 0;
    }

    hold->carry_detection = hold->previous_result.detections[previous_indices[unmatched_previous_idx]];
    if (elevator_temporal_hold_candidate_is_stable(hold, &hold->carry_detection,
            frame_width, frame_height) == 0) {
        memset(&hold->carry_detection, 0, sizeof(hold->carry_detection));
        return 0;
    }

    hold->carry_active = 1;
    hold->carry_frames = 0;
    hold->carry_started_ms = timestamp_ms;
    hold->consecutive_holds = 0;
    return 1;
}

static void elevator_temporal_hold_append_carry(elevator_temporal_hold *hold, elevator_parse_result *result)
{
    if (hold == NULL || result == NULL || hold->carry_active == 0 ||
        result->detection_count >= ELEVATOR_MAX_DETECTIONS) {
        return;
    }

    hold->carry_detection.synthetic = 1U;
    hold->carry_detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    result->detections[result->detection_count++] = hold->carry_detection;
    result->stats.person_count += 1U;
}

void elevator_temporal_hold_reset(elevator_temporal_hold *hold, uint32_t max_hold_frames, uint64_t max_hold_ms)
{
    if (hold == NULL) {
        return;
    }

    memset(hold, 0, sizeof(*hold));
    hold->max_hold_frames = max_hold_frames;
    hold->max_hold_ms = max_hold_ms;
}

void elevator_temporal_hold_apply(elevator_temporal_hold *hold, elevator_parse_result *result, uint64_t timestamp_ms,
    uint32_t frame_width, uint32_t frame_height)
{
    if (hold == NULL || result == NULL) {
        return;
    }

    if (hold->carry_active != 0 && elevator_temporal_hold_current_matches_carry(hold, result) != 0) {
        elevator_temporal_hold_clear_carry(hold);
    }
    if (hold->carry_active == 0) {
        (void)elevator_temporal_hold_try_activate_single_person_carry(hold, result, timestamp_ms,
            frame_width, frame_height);
    }
    if (elevator_temporal_hold_carry_is_valid(hold, timestamp_ms) != 0 &&
        elevator_temporal_hold_current_matches_carry(hold, result) == 0) {
        elevator_temporal_hold_append_carry(hold, result);
        hold->carry_frames++;
        hold->consecutive_holds = hold->carry_frames;
    } else if (hold->carry_active == 0) {
        hold->consecutive_holds = 0;
    }

    hold->previous_result = *result;
    hold->last_timestamp_ms = timestamp_ms;
    hold->has_previous = 1;
    elevator_temporal_hold_note_history(hold, result, timestamp_ms);
}

static float elevator_tracker_match_score(const elevator_person_track *track,
    const elevator_detection_result *detection, uint32_t frame_width, uint32_t frame_height)
{
    float iou;
    uint64_t center_dist_sq;
    uint64_t min_side;
    uint64_t max_center_distance_sq;
    float min_iou;

    if (track == NULL || detection == NULL || track->active == 0) {
        return -1.0f;
    }

    iou = elevator_rect_iou(&track->detection.rect, &detection->rect);
    min_iou = (track->child_like != 0 || detection->child_like != 0) ?
        ELEVATOR_TRACK_MATCH_MIN_IOU_CHILD : ELEVATOR_TRACK_MATCH_MIN_IOU;
    center_dist_sq = elevator_rect_center_distance_sq(&track->detection.rect, &detection->rect);
    min_side = frame_width < frame_height ? frame_width : frame_height;
    max_center_distance_sq = (min_side * min_side * 18ULL * 18ULL) / 10000ULL;
    if (iou < min_iou && center_dist_sq > max_center_distance_sq) {
        return -1.0f;
    }

    return iou + ((float)track->hits * 0.02f) - ((float)center_dist_sq / (float)(max_center_distance_sq + 1ULL) * 0.15f);
}

static int elevator_should_preserve_child_like_track_box(const elevator_person_track *track,
    const elevator_detection_result *detection)
{
    uint64_t prev_area;
    uint64_t curr_area;

    if (track == NULL || detection == NULL || track->active == 0U ||
        track->hits < ELEVATOR_TRACK_CONFIRM_HITS || track->child_like == 0U ||
        detection->child_like != 0U || !isfinite(track->detection.score) || !isfinite(detection->score)) {
        return 0;
    }

    prev_area = elevator_rect_area(&track->detection.rect);
    curr_area = elevator_rect_area(&detection->rect);
    if (prev_area == 0U || curr_area == 0U) {
        return 0;
    }
    if (curr_area * 100ULL < prev_area * ELEVATOR_TRACK_CHILD_REGRESSION_MIN_AREA_GROWTH_PERCENT) {
        return 0;
    }
    if (detection->score + ELEVATOR_TRACK_CHILD_REGRESSION_MIN_SCORE_DROP > track->detection.score) {
        return 0;
    }
    return 1;
}

static void elevator_person_tracker_mark_detection_defaults(elevator_parse_result *result,
    uint32_t frame_width, uint32_t frame_height)
{
    size_t idx;

    if (result == NULL) {
        return;
    }

    for (idx = 0; idx < result->detection_count; ++idx) {
        uint8_t synthetic = result->detections[idx].synthetic;
        result->detections[idx].track_id = 0U;
        result->detections[idx].track_state = ELEVATOR_TRACK_STATE_NONE;
        result->detections[idx].synthetic = synthetic;
        result->detections[idx].child_like = (uint8_t)elevator_detection_is_child_like(
            &result->detections[idx], frame_width, frame_height);
    }
}

void elevator_person_tracker_reset(elevator_person_tracker *tracker, uint32_t max_lost_frames, uint64_t max_lost_ms)
{
    if (tracker == NULL) {
        return;
    }

    memset(tracker, 0, sizeof(*tracker));
    tracker->next_track_id = 1U;
    tracker->max_lost_frames = max_lost_frames;
    tracker->max_lost_ms = max_lost_ms;
}

static elevator_person_track *elevator_person_tracker_find_track(elevator_person_tracker *tracker, uint32_t track_id)
{
    size_t idx;

    if (tracker == NULL || track_id == 0U) {
        return NULL;
    }

    for (idx = 0; idx < ELEVATOR_MAX_PERSON_TRACKS; ++idx) {
        if (tracker->tracks[idx].active != 0U && tracker->tracks[idx].track_id == track_id) {
            return &tracker->tracks[idx];
        }
    }
    return NULL;
}

static const elevator_person_track *elevator_person_tracker_find_track_const(const elevator_person_tracker *tracker,
    uint32_t track_id)
{
    size_t idx;

    if (tracker == NULL || track_id == 0U) {
        return NULL;
    }

    for (idx = 0; idx < ELEVATOR_MAX_PERSON_TRACKS; ++idx) {
        if (tracker->tracks[idx].active != 0U && tracker->tracks[idx].track_id == track_id) {
            return &tracker->tracks[idx];
        }
    }
    return NULL;
}

static int elevator_person_track_is_mature(const elevator_person_track *track)
{
    if (track == NULL || track->active == 0U || track->detection.class_id != 0U) {
        return 0;
    }
    return track->hits >= ELEVATOR_TRACK_MATURE_HITS ? 1 : 0;
}

static int elevator_person_track_has_mature_carry_geometry_with_min_score(const elevator_person_track *track,
    uint32_t frame_width, uint32_t frame_height, float min_score)
{
    uint64_t frame_area;
    uint64_t area_percent;
    uint64_t width_percent;
    uint64_t area;

    if (track == NULL || frame_width == 0U || frame_height == 0U) {
        return 0;
    }
    if (track->detection.score < min_score) {
        return 0;
    }
    if (elevator_rect_touches_right_edge(&track->detection.rect, frame_width) != 0) {
        return 0;
    }
    if (elevator_rect_touches_top_edge(&track->detection.rect) == 0) {
        return 0;
    }

    frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
    area = elevator_rect_area(&track->detection.rect);
    if (frame_area == 0U || area == 0U) {
        return 0;
    }

    area_percent = (area * 100ULL) / frame_area;
    width_percent = ((uint64_t)elevator_rect_width(&track->detection.rect) * 100ULL) / (uint64_t)frame_width;
    if (area_percent > ELEVATOR_MATURE_CARRY_MAX_AREA_PERCENT) {
        return 0;
    }
    if (width_percent > ELEVATOR_MATURE_CARRY_MAX_WIDTH_PERCENT) {
        return 0;
    }
    return 1;
}

static int elevator_person_track_has_safe_mature_carry_geometry(const elevator_person_track *track,
    uint32_t frame_width, uint32_t frame_height)
{
    return elevator_person_track_has_mature_carry_geometry_with_min_score(track,
        frame_width, frame_height, ELEVATOR_MATURE_CARRY_MIN_SCORE);
}

static int elevator_person_track_has_relaxed_robust_mature_carry_geometry(const elevator_person_track *track,
    uint32_t frame_width, uint32_t frame_height)
{
    if (track == NULL || track->hits < ELEVATOR_TRACK_ROBUST_MATURE_HITS) {
        return 0;
    }
    return elevator_person_track_has_mature_carry_geometry_with_min_score(track,
        frame_width, frame_height, ELEVATOR_ROBUST_MATURE_CARRY_MIN_SCORE);
}

static int elevator_person_track_is_mature_public_carry_eligible(const elevator_person_track *track,
    uint32_t frame_width, uint32_t frame_height)
{
    float quality;

    if (elevator_person_track_is_mature(track) == 0) {
        return 0;
    }
    if (track->detection.synthetic != 0U || track->child_like != 0U) {
        return 1;
    }

    quality = elevator_detection_quality_score(&track->detection, frame_width, frame_height);
    if (quality >= 0.35f) {
        return 1;
    }
    if (elevator_person_track_has_safe_mature_carry_geometry(track, frame_width, frame_height) != 0) {
        return 1;
    }
    return elevator_person_track_has_relaxed_robust_mature_carry_geometry(track, frame_width, frame_height);
}

static int elevator_detection_belongs_to_mature_track(const elevator_person_tracker *tracker,
    const elevator_detection_result *detection)
{
    const elevator_person_track *track;

    if (tracker == NULL || detection == NULL || detection->class_id != 0U || detection->track_id == 0U) {
        return 0;
    }
    track = elevator_person_tracker_find_track_const(tracker, detection->track_id);
    return elevator_person_track_is_mature(track);
}

static float elevator_track_aware_detection_quality(const elevator_person_tracker *tracker,
    const elevator_detection_result *detection, uint32_t frame_width, uint32_t frame_height)
{
    float quality;
    size_t idx;

    if (detection == NULL) {
        return -1.0f;
    }

    quality = elevator_detection_quality_score(detection, frame_width, frame_height);
    switch (detection->track_state) {
        case ELEVATOR_TRACK_STATE_CONFIRMED:
            quality += 0.10f;
            break;
        case ELEVATOR_TRACK_STATE_HELD:
            quality += 0.07f;
            break;
        case ELEVATOR_TRACK_STATE_TENTATIVE:
            quality += 0.03f;
            break;
        default:
            break;
    }

    if (tracker == NULL || detection->track_id == 0U) {
        return quality;
    }
    for (idx = 0; idx < ELEVATOR_MAX_PERSON_TRACKS; ++idx) {
        const elevator_person_track *track = &tracker->tracks[idx];
        if (track->active == 0U || track->track_id != detection->track_id) {
            continue;
        }
        if (track->hits > ELEVATOR_TRACK_CONFIRM_HITS) {
            uint32_t extra_hits = track->hits - ELEVATOR_TRACK_CONFIRM_HITS;
            if (extra_hits > 4U) {
                extra_hits = 4U;
            }
            quality += (float)extra_hits * 0.02f;
        }
        break;
    }
    return quality;
}

static elevator_rect elevator_blend_mature_track_rect(elevator_rect previous_rect, elevator_rect current_rect)
{
    elevator_rect blended;

    blended.x1 = (uint32_t)(((uint64_t)previous_rect.x1 * 3ULL + (uint64_t)current_rect.x1 * 2ULL) / 5ULL);
    blended.y1 = (uint32_t)(((uint64_t)previous_rect.y1 * 3ULL + (uint64_t)current_rect.y1 * 2ULL) / 5ULL);
    blended.x2 = (uint32_t)(((uint64_t)previous_rect.x2 * 3ULL + (uint64_t)current_rect.x2 * 2ULL) / 5ULL);
    blended.y2 = (uint32_t)(((uint64_t)previous_rect.y2 * 3ULL + (uint64_t)current_rect.y2 * 2ULL) / 5ULL);

    blended.x1 &= ~1U;
    blended.y1 &= ~1U;
    blended.x2 &= ~1U;
    blended.y2 &= ~1U;
    if (blended.x2 <= blended.x1) {
        blended.x2 = current_rect.x2;
    }
    if (blended.y2 <= blended.y1) {
        blended.y2 = current_rect.y2;
    }
    return blended;
}

static int elevator_should_blend_mature_track_rect(elevator_rect previous_rect, elevator_rect current_rect)
{
    if (elevator_rect_area(&previous_rect) == 0ULL || elevator_rect_area(&current_rect) == 0ULL) {
        return 0;
    }
    if (elevator_rect_touches_top_edge(&previous_rect) != 0 ||
        elevator_rect_touches_top_edge(&current_rect) != 0) {
        return 0;
    }
    return elevator_rect_iou(&previous_rect, &current_rect) >= 0.20f ? 1 : 0;
}

static int elevator_promote_matched_synthetic_hold_for_public(elevator_parse_result *result,
    const elevator_person_track *track)
{
    size_t idx;

    if (result == NULL || track == NULL || track->track_id == 0U || track->matched_in_frame == 0U ||
        track->detection.synthetic == 0U) {
        return 0;
    }

    for (idx = 0; idx < result->detection_count; ++idx) {
        elevator_detection_result *detection = &result->detections[idx];
        if (detection->class_id == 0U &&
            detection->track_id == track->track_id &&
            detection->track_state == ELEVATOR_TRACK_STATE_HELD &&
            detection->synthetic != 0U) {
            detection->synthetic = 0U;
            return 1;
        }
    }
    return 0;
}

static int elevator_person_boxes_look_like_near_identical_child_duplicate(
    const elevator_detection_result *lhs, const elevator_detection_result *rhs,
    uint32_t frame_width, uint32_t frame_height);

static int elevator_track_conflicts_with_visible_public_person(const elevator_person_track *track,
    const elevator_parse_result *result, uint32_t frame_width, uint32_t frame_height)
{
    size_t idx;

    if (track == NULL || result == NULL || track->active == 0U || track->detection.class_id != 0U) {
        return 0;
    }

    for (idx = 0; idx < result->detection_count; ++idx) {
        const elevator_detection_result *visible = &result->detections[idx];

        if (visible->class_id != 0U || visible->synthetic != 0U) {
            continue;
        }
        if (visible->track_id != 0U && visible->track_id == track->track_id) {
            continue;
        }
        if (elevator_public_detection_should_render(visible, frame_width, frame_height) == 0) {
            continue;
        }
        if (elevator_person_boxes_look_like_duplicate(&track->detection, visible, frame_width, frame_height) != 0 ||
            elevator_person_boxes_look_like_near_identical_child_duplicate(
                &track->detection, visible, frame_width, frame_height) != 0) {
            return 1;
        }
    }

    return 0;
}

static int elevator_person_boxes_look_like_near_identical_child_duplicate(
    const elevator_detection_result *lhs, const elevator_detection_result *rhs,
    uint32_t frame_width, uint32_t frame_height)
{
    uint64_t lhs_area;
    uint64_t rhs_area;
    uint64_t smaller_coverage_percent;
    uint64_t min_side;
    uint64_t center_dist_sq;
    uint64_t max_center_distance_sq;

    if (lhs == NULL || rhs == NULL || lhs->class_id != 0U || rhs->class_id != 0U) {
        return 0;
    }
    if (elevator_person_boxes_look_like_child_duplicate(lhs, rhs, frame_width, frame_height) == 0) {
        return 0;
    }

    lhs_area = elevator_rect_area(&lhs->rect);
    rhs_area = elevator_rect_area(&rhs->rect);
    if (lhs_area == 0U || rhs_area == 0U) {
        return 0;
    }

    smaller_coverage_percent = elevator_rect_coverage_percent(
        lhs_area >= rhs_area ? &lhs->rect : &rhs->rect,
        lhs_area < rhs_area ? &lhs->rect : &rhs->rect);
    if (smaller_coverage_percent < ELEVATOR_UNMATCHED_PUBLIC_CARRY_DUPLICATE_MIN_COVERAGE_PERCENT) {
        return 0;
    }

    min_side = elevator_rect_width(&lhs->rect);
    if (elevator_rect_height(&lhs->rect) < min_side) {
        min_side = elevator_rect_height(&lhs->rect);
    }
    if (elevator_rect_width(&rhs->rect) < min_side) {
        min_side = elevator_rect_width(&rhs->rect);
    }
    if (elevator_rect_height(&rhs->rect) < min_side) {
        min_side = elevator_rect_height(&rhs->rect);
    }
    if (min_side == 0U) {
        return 0;
    }

    center_dist_sq = elevator_rect_center_distance_sq(&lhs->rect, &rhs->rect);
    max_center_distance_sq = (min_side * min_side *
        ELEVATOR_UNMATCHED_PUBLIC_CARRY_DUPLICATE_MAX_CENTER_SHIFT_PERCENT *
        ELEVATOR_UNMATCHED_PUBLIC_CARRY_DUPLICATE_MAX_CENTER_SHIFT_PERCENT) / 10000ULL;
    return center_dist_sq <= max_center_distance_sq ? 1 : 0;
}

static int elevator_track_has_near_identical_visible_public_person(const elevator_person_track *track,
    const elevator_parse_result *result, uint32_t frame_width, uint32_t frame_height)
{
    size_t idx;
    uint64_t track_area;

    if (track == NULL || result == NULL || track->active == 0U || track->detection.class_id != 0U) {
        return 0;
    }

    track_area = elevator_rect_area(&track->detection.rect);
    if (track_area == 0U) {
        return 0;
    }

    for (idx = 0; idx < result->detection_count; ++idx) {
        const elevator_detection_result *visible = &result->detections[idx];
        uint64_t visible_area;
        uint64_t smaller_coverage_percent;
        uint64_t min_side;
        uint32_t min_width;
        uint32_t min_height;
        uint64_t center_dist_sq;
        uint64_t max_center_distance_sq;

        if (visible->class_id != 0U || visible->synthetic != 0U) {
            continue;
        }
        if (visible->track_id != 0U && visible->track_id == track->track_id) {
            continue;
        }
        if (elevator_public_detection_should_render(visible, frame_width, frame_height) == 0) {
            continue;
        }

        visible_area = elevator_rect_area(&visible->rect);
        if (visible_area == 0U) {
            continue;
        }
        min_width = elevator_rect_width(&track->detection.rect);
        if (elevator_rect_width(&visible->rect) < min_width) {
            min_width = elevator_rect_width(&visible->rect);
        }
        min_height = elevator_rect_height(&track->detection.rect);
        if (elevator_rect_height(&visible->rect) < min_height) {
            min_height = elevator_rect_height(&visible->rect);
        }
        if (min_width == 0U || min_height == 0U) {
            continue;
        }

        if (elevator_person_boxes_look_like_child_duplicate(&track->detection, visible, frame_width, frame_height) != 0) {
            return 1;
        }

        if (visible_area > track_area) {
            uint64_t track_coverage_in_visible = elevator_rect_coverage_percent(
                &visible->rect, &track->detection.rect);
            uint32_t left_delta = track->detection.rect.x1 > visible->rect.x1 ?
                track->detection.rect.x1 - visible->rect.x1 :
                visible->rect.x1 - track->detection.rect.x1;
            uint32_t right_delta = track->detection.rect.x2 > visible->rect.x2 ?
                track->detection.rect.x2 - visible->rect.x2 :
                visible->rect.x2 - track->detection.rect.x2;
            uint32_t top_delta = track->detection.rect.y1 > visible->rect.y1 ?
                track->detection.rect.y1 - visible->rect.y1 :
                visible->rect.y1 - track->detection.rect.y1;
            uint32_t bottom_delta = track->detection.rect.y2 > visible->rect.y2 ?
                track->detection.rect.y2 - visible->rect.y2 :
                visible->rect.y2 - track->detection.rect.y2;
            uint32_t track_height = elevator_rect_height(&track->detection.rect);
            uint32_t visible_height = elevator_rect_height(&visible->rect);

            if (visible_height != 0U &&
                track_coverage_in_visible >=
                    ELEVATOR_UNMATCHED_PUBLIC_CARRY_UPPER_FRAGMENT_MIN_COVERAGE_PERCENT &&
                (uint64_t)left_delta * 100ULL <=
                    (uint64_t)min_width *
                        ELEVATOR_UNMATCHED_PUBLIC_CARRY_UPPER_FRAGMENT_MAX_EDGE_DELTA_PERCENT &&
                (uint64_t)right_delta * 100ULL <=
                    (uint64_t)min_width *
                        ELEVATOR_UNMATCHED_PUBLIC_CARRY_UPPER_FRAGMENT_MAX_EDGE_DELTA_PERCENT &&
                (uint64_t)top_delta * 100ULL <=
                    (uint64_t)min_height *
                        ELEVATOR_UNMATCHED_PUBLIC_CARRY_UPPER_FRAGMENT_MAX_TOP_DELTA_PERCENT &&
                (uint64_t)bottom_delta * 100ULL >=
                    (uint64_t)min_height *
                        ELEVATOR_UNMATCHED_PUBLIC_CARRY_UPPER_FRAGMENT_MIN_BOTTOM_DELTA_PERCENT &&
                (uint64_t)track_height * 100ULL <=
                    (uint64_t)visible_height *
                        ELEVATOR_UNMATCHED_PUBLIC_CARRY_UPPER_FRAGMENT_MAX_HEIGHT_RATIO_PERCENT) {
                return 1;
            }
        }

        if (track_area > visible_area) {
            uint64_t visible_coverage_in_track = elevator_rect_coverage_percent(
                &track->detection.rect, &visible->rect);
            uint32_t top_delta;

            if (visible_coverage_in_track >=
                    ELEVATOR_UNMATCHED_PUBLIC_CARRY_LOWER_FRAGMENT_MIN_VISIBLE_COVERAGE_PERCENT &&
                track->detection.rect.y1 > visible->rect.y1 &&
                track->detection.rect.y2 > visible->rect.y2 &&
                elevator_rect_contains_point(&visible->rect,
                    elevator_rect_center_x(&track->detection.rect),
                    elevator_rect_center_y(&track->detection.rect)) != 0) {
                top_delta = track->detection.rect.y1 - visible->rect.y1;
                if ((uint64_t)top_delta * 100ULL >=
                        (uint64_t)min_height *
                            ELEVATOR_UNMATCHED_PUBLIC_CARRY_LOWER_FRAGMENT_MIN_TOP_DELTA_PERCENT) {
                    return 1;
                }
            }
        }

        if (elevator_person_boxes_look_like_duplicate(&track->detection, visible, frame_width, frame_height) == 0) {
            continue;
        }

        if (elevator_rect_touches_top_edge(&track->detection.rect) != 0) {
            uint32_t left_delta = track->detection.rect.x1 > visible->rect.x1 ?
                track->detection.rect.x1 - visible->rect.x1 :
                visible->rect.x1 - track->detection.rect.x1;
            uint32_t right_delta = track->detection.rect.x2 > visible->rect.x2 ?
                track->detection.rect.x2 - visible->rect.x2 :
                visible->rect.x2 - track->detection.rect.x2;
            uint32_t top_delta = track->detection.rect.y1 > visible->rect.y1 ?
                track->detection.rect.y1 - visible->rect.y1 :
                visible->rect.y1 - track->detection.rect.y1;
            uint32_t bottom_delta = track->detection.rect.y2 > visible->rect.y2 ?
                track->detection.rect.y2 - visible->rect.y2 :
                visible->rect.y2 - track->detection.rect.y2;

            if ((uint64_t)left_delta * 100ULL <=
                    (uint64_t)min_width *
                        ELEVATOR_UNMATCHED_PUBLIC_CARRY_TOP_EDGE_ALIGNED_MAX_EDGE_DELTA_PERCENT &&
                (uint64_t)right_delta * 100ULL <=
                    (uint64_t)min_width *
                        ELEVATOR_UNMATCHED_PUBLIC_CARRY_TOP_EDGE_ALIGNED_MAX_EDGE_DELTA_PERCENT &&
                (uint64_t)top_delta * 100ULL <=
                    (uint64_t)min_height *
                        ELEVATOR_UNMATCHED_PUBLIC_CARRY_TOP_EDGE_ALIGNED_MAX_TOP_DELTA_PERCENT &&
                (uint64_t)bottom_delta * 100ULL <=
                    (uint64_t)min_height *
                        ELEVATOR_UNMATCHED_PUBLIC_CARRY_TOP_EDGE_CONTAINER_MAX_BOTTOM_DELTA_PERCENT) {
                return 1;
            }
        }

        smaller_coverage_percent = elevator_rect_coverage_percent(
            track_area >= visible_area ? &track->detection.rect : &visible->rect,
            track_area < visible_area ? &track->detection.rect : &visible->rect);
        if (smaller_coverage_percent <
            ELEVATOR_UNMATCHED_PUBLIC_CARRY_DUPLICATE_MIN_COVERAGE_PERCENT) {
            continue;
        }

        min_side = elevator_rect_width(&track->detection.rect);
        if (elevator_rect_height(&track->detection.rect) < min_side) {
            min_side = elevator_rect_height(&track->detection.rect);
        }
        if (elevator_rect_width(&visible->rect) < min_side) {
            min_side = elevator_rect_width(&visible->rect);
        }
        if (elevator_rect_height(&visible->rect) < min_side) {
            min_side = elevator_rect_height(&visible->rect);
        }
        if (min_side == 0U) {
            continue;
        }

        center_dist_sq = elevator_rect_center_distance_sq(&track->detection.rect, &visible->rect);
        max_center_distance_sq = (min_side * min_side *
            ELEVATOR_UNMATCHED_PUBLIC_CARRY_DUPLICATE_MAX_CENTER_SHIFT_PERCENT *
            ELEVATOR_UNMATCHED_PUBLIC_CARRY_DUPLICATE_MAX_CENTER_SHIFT_PERCENT) / 10000ULL;
        if (center_dist_sq <= max_center_distance_sq) {
            return 1;
        }

        if (visible_area > track_area &&
            elevator_rect_touches_top_edge(&visible->rect) != 0 &&
            track->detection.rect.x1 > visible->rect.x1 &&
            elevator_rect_contains_point(&visible->rect,
                elevator_rect_center_x(&track->detection.rect),
                elevator_rect_center_y(&track->detection.rect)) != 0) {
            uint32_t right_delta = track->detection.rect.x2 > visible->rect.x2 ?
                track->detection.rect.x2 - visible->rect.x2 :
                visible->rect.x2 - track->detection.rect.x2;
            uint32_t bottom_delta = track->detection.rect.y2 > visible->rect.y2 ?
                track->detection.rect.y2 - visible->rect.y2 :
                visible->rect.y2 - track->detection.rect.y2;

            if ((uint64_t)right_delta * 100ULL <=
                    (uint64_t)min_width *
                        ELEVATOR_UNMATCHED_PUBLIC_CARRY_TOP_EDGE_CONTAINER_MAX_EDGE_DELTA_PERCENT &&
                (uint64_t)bottom_delta * 100ULL <=
                    (uint64_t)min_height *
                        ELEVATOR_UNMATCHED_PUBLIC_CARRY_TOP_EDGE_CONTAINER_MAX_BOTTOM_DELTA_PERCENT) {
                return 1;
            }
        }
    }

    return 0;
}

static uint32_t elevator_append_public_hold_detections(elevator_person_tracker *tracker,
    elevator_parse_result *result, uint32_t carry_count, uint32_t frame_width, uint32_t frame_height,
    uint32_t *mature_carry_count)
{
    unsigned char selected[ELEVATOR_MAX_PERSON_TRACKS];
    uint32_t appended = 0U;
    uint32_t mature_appended = 0U;

    if (tracker == NULL || result == NULL || carry_count == 0U) {
        return 0U;
    }

    memset(selected, 0, sizeof(selected));
    while (appended < carry_count) {
        float best_quality = -1.0f;
        size_t best_track_idx = (size_t)-1;

        for (size_t track_idx = 0; track_idx < ELEVATOR_MAX_PERSON_TRACKS; ++track_idx) {
            elevator_person_track *track = &tracker->tracks[track_idx];
            float quality;
            int mature_eligible;
            int matched_synthetic_hold;

            matched_synthetic_hold = (track->matched_in_frame != 0U &&
                track->detection.synthetic != 0U &&
                track->detection.track_state == ELEVATOR_TRACK_STATE_HELD) ? 1 : 0;
            if (selected[track_idx] != 0U || track->active == 0U ||
                (track->matched_in_frame != 0U && matched_synthetic_hold == 0)) {
                continue;
            }
            if (track->hits < ELEVATOR_TRACK_CONFIRM_HITS) {
                continue;
            }
            if (matched_synthetic_hold != 0 &&
                elevator_track_conflicts_with_visible_public_person(track, result, frame_width, frame_height) != 0) {
                continue;
            }
            if (matched_synthetic_hold == 0 &&
                elevator_track_has_near_identical_visible_public_person(track, result, frame_width, frame_height) != 0) {
                continue;
            }

            mature_eligible = elevator_person_track_is_mature_public_carry_eligible(track, frame_width, frame_height);
            if (track->detection.synthetic != 0U && mature_eligible == 0 &&
                (matched_synthetic_hold == 0 || track->child_like == 0U ||
                    track->hits < ELEVATOR_TRACK_CONFIRM_HITS)) {
                continue;
            }
            quality = elevator_track_aware_detection_quality(tracker, &track->detection, frame_width, frame_height);
            if (mature_eligible == 0 && track->child_like == 0U && quality < 0.35f) {
                continue;
            }
            if (mature_eligible != 0) {
                quality += 0.50f;
            }
            if (quality > best_quality) {
                best_quality = quality;
                best_track_idx = track_idx;
            }
        }

        if (best_track_idx == (size_t)-1) {
            break;
        }

        {
            elevator_person_track *track = &tracker->tracks[best_track_idx];
            int mature_eligible = elevator_person_track_is_mature_public_carry_eligible(
                track, frame_width, frame_height);
            int reconfirm_child_like_carry = (
                track->matched_in_frame != 0U &&
                track->detection.synthetic != 0U &&
                track->child_like != 0U &&
                track->hits >= ELEVATOR_TRACK_CONFIRM_HITS
            ) ? 1 : 0;
            if (elevator_promote_matched_synthetic_hold_for_public(result, track) == 0) {
                elevator_detection_result held_detection;
                if (result->detection_count >= ELEVATOR_MAX_DETECTIONS) {
                    break;
                }
                held_detection = track->detection;
                held_detection.track_state = ELEVATOR_TRACK_STATE_HELD;
                held_detection.synthetic = 0U;
                result->detections[result->detection_count++] = held_detection;
            }
            if (mature_eligible != 0 || reconfirm_child_like_carry != 0) {
                mature_appended++;
            }
        }
        selected[best_track_idx] = 1U;
        appended++;
    }

    if (mature_carry_count != NULL) {
        *mature_carry_count = mature_appended;
    }
    return appended;
}

static size_t elevator_apply_track_aware_duplicate_cleanup(elevator_person_tracker *tracker,
    elevator_parse_result *result, uint32_t frame_width, uint32_t frame_height)
{
    unsigned char suppressed[ELEVATOR_MAX_DETECTIONS];
    size_t write_idx = 0;
    size_t i;
    size_t j;

    if (result == NULL || result->detection_count == 0U) {
        return 0U;
    }

    memset(suppressed, 0, sizeof(suppressed));
    for (i = 0; i < result->detection_count; ++i) {
        if (suppressed[i] != 0U) {
            continue;
        }
        if (result->detections[i].class_id != 0U || result->detections[i].synthetic != 0U) {
            continue;
        }

        for (j = i + 1; j < result->detection_count; ++j) {
            float lhs_quality;
            float rhs_quality;
            uint64_t lhs_area;
            uint64_t rhs_area;
            uint64_t smaller_coverage_percent;
            int lhs_edge;
            int rhs_edge;

            if (suppressed[j] != 0U) {
                continue;
            }
            if (result->detections[j].class_id != 0U || result->detections[j].synthetic != 0U) {
                continue;
            }
            {
                int looks_like_duplicate = elevator_person_boxes_look_like_duplicate(
                    &result->detections[i], &result->detections[j], frame_width, frame_height);
                int looks_like_child_duplicate = elevator_person_boxes_look_like_child_duplicate(
                    &result->detections[i], &result->detections[j], frame_width, frame_height);

                if (looks_like_duplicate == 0 && looks_like_child_duplicate == 0) {
                    continue;
                }

                lhs_quality = elevator_track_aware_detection_quality(tracker, &result->detections[i],
                    frame_width, frame_height);
                rhs_quality = elevator_track_aware_detection_quality(tracker, &result->detections[j],
                    frame_width, frame_height);
                lhs_area = elevator_rect_area(&result->detections[i].rect);
                rhs_area = elevator_rect_area(&result->detections[j].rect);
                smaller_coverage_percent = elevator_rect_coverage_percent(
                    lhs_area >= rhs_area ? &result->detections[i].rect : &result->detections[j].rect,
                    lhs_area < rhs_area ? &result->detections[i].rect : &result->detections[j].rect);
                lhs_edge = elevator_rect_touches_frame_edge(&result->detections[i].rect, frame_width, frame_height);
                rhs_edge = elevator_rect_touches_frame_edge(&result->detections[j].rect, frame_width, frame_height);

                if (elevator_detection_belongs_to_mature_track(tracker, &result->detections[i]) != 0 &&
                    elevator_detection_belongs_to_mature_track(tracker, &result->detections[j]) == 0 &&
                    result->detections[j].track_state == ELEVATOR_TRACK_STATE_TENTATIVE) {
                    suppressed[j] = 1U;
                } else if (elevator_detection_belongs_to_mature_track(tracker, &result->detections[j]) != 0 &&
                    elevator_detection_belongs_to_mature_track(tracker, &result->detections[i]) == 0 &&
                    result->detections[i].track_state == ELEVATOR_TRACK_STATE_TENTATIVE) {
                    suppressed[i] = 1U;
                } else if (looks_like_child_duplicate != 0 &&
                    result->detections[i].child_like != 0U && result->detections[j].child_like == 0U &&
                    lhs_area > rhs_area &&
                    smaller_coverage_percent >= ELEVATOR_CHILD_DUPLICATE_LARGE_CHILD_MIN_COVERAGE_PERCENT &&
                    result->detections[j].score >=
                        result->detections[i].score + ELEVATOR_CHILD_DUPLICATE_LARGE_CHILD_MIN_SCORE_MARGIN) {
                    suppressed[i] = 1U;
                } else if (looks_like_child_duplicate != 0 &&
                    result->detections[j].child_like != 0U && result->detections[i].child_like == 0U &&
                    rhs_area > lhs_area &&
                    smaller_coverage_percent >= ELEVATOR_CHILD_DUPLICATE_LARGE_CHILD_MIN_COVERAGE_PERCENT &&
                    result->detections[i].score >=
                        result->detections[j].score + ELEVATOR_CHILD_DUPLICATE_LARGE_CHILD_MIN_SCORE_MARGIN) {
                    suppressed[j] = 1U;
                } else if (result->detections[i].child_like != 0U && result->detections[j].child_like == 0U &&
                    looks_like_child_duplicate != 0) {
                    suppressed[j] = 1U;
                } else if (result->detections[j].child_like != 0U && result->detections[i].child_like == 0U &&
                    looks_like_child_duplicate != 0) {
                    suppressed[i] = 1U;
                } else if (lhs_edge != 0 && rhs_edge == 0 &&
                    smaller_coverage_percent >= ELEVATOR_TRACK_DUPLICATE_EDGE_COVERAGE_PERCENT &&
                    lhs_quality <= rhs_quality + 0.10f) {
                    suppressed[i] = 1U;
                } else if (rhs_edge != 0 && lhs_edge == 0 &&
                    smaller_coverage_percent >= ELEVATOR_TRACK_DUPLICATE_EDGE_COVERAGE_PERCENT &&
                    rhs_quality <= lhs_quality + 0.10f) {
                    suppressed[j] = 1U;
                } else if (rhs_quality > lhs_quality + 0.02f) {
                    suppressed[i] = 1U;
                } else {
                    suppressed[j] = 1U;
                }
            }

            if (suppressed[i] != 0U) {
                elevator_person_track *track = elevator_person_tracker_find_track(tracker, result->detections[i].track_id);
                if (track != NULL) {
                    track->active = 0U;
                }
                break;
            }
            if (suppressed[j] != 0U) {
                elevator_person_track *track = elevator_person_tracker_find_track(tracker, result->detections[j].track_id);
                if (track != NULL) {
                    track->active = 0U;
                }
            }
        }
    }

    for (i = 0; i < result->detection_count; ++i) {
        if (suppressed[i] != 0U) {
            continue;
        }
        if (write_idx != i) {
            result->detections[write_idx] = result->detections[i];
        }
        write_idx++;
    }
    result->detection_count = write_idx;
    return write_idx;
}

void elevator_person_tracker_apply(elevator_person_tracker *tracker, elevator_parse_result *result, uint64_t timestamp_ms,
    uint32_t frame_width, uint32_t frame_height)
{
    unsigned char detection_matched[ELEVATOR_MAX_DETECTIONS];
    uint32_t confirmed_count = 0;
    uint32_t matched_confirmed_count = 0;
    uint32_t tentative_count = 0;
    uint32_t held_count = 0;
    uint32_t held_eligible_count = 0;
    uint32_t mature_confirmed_count = 0;
    uint32_t mature_held_count = 0;
    uint32_t mature_public_carry_count = 0;
    uint32_t raw_person_count;
    uint32_t public_person_count;
    size_t best_track_idx;
    size_t best_det_idx;

    if (tracker == NULL || result == NULL) {
        return;
    }

    elevator_person_tracker_mark_detection_defaults(result, frame_width, frame_height);
    raw_person_count = result->stats.person_count;
    memset(detection_matched, 0, sizeof(detection_matched));

    for (size_t track_idx = 0; track_idx < ELEVATOR_MAX_PERSON_TRACKS; ++track_idx) {
        tracker->tracks[track_idx].matched_in_frame = 0U;
    }

    while (1) {
        float best_score = -1.0f;

        best_track_idx = (size_t)-1;
        best_det_idx = (size_t)-1;
        for (size_t track_idx = 0; track_idx < ELEVATOR_MAX_PERSON_TRACKS; ++track_idx) {
            elevator_person_track *track = &tracker->tracks[track_idx];
            if (track->active == 0) {
                continue;
            }
            if (track->last_timestamp_ms != 0 && timestamp_ms >= track->last_timestamp_ms &&
                timestamp_ms - track->last_timestamp_ms > tracker->max_lost_ms) {
                track->active = 0U;
                continue;
            }
            if (track->matched_in_frame != 0U) {
                continue;
            }
            for (size_t det_idx = 0; det_idx < result->detection_count; ++det_idx) {
                float match_score;
                elevator_detection_result *detection = &result->detections[det_idx];

                if (detection_matched[det_idx] != 0U || detection->class_id != 0U) {
                    continue;
                }
                match_score = elevator_tracker_match_score(track, detection, frame_width, frame_height);
                if (match_score > best_score) {
                    best_score = match_score;
                    best_track_idx = track_idx;
                    best_det_idx = det_idx;
                }
            }
        }

        if (best_track_idx == (size_t)-1 || best_det_idx == (size_t)-1) {
            break;
        }

        {
            elevator_person_track *track = &tracker->tracks[best_track_idx];
            elevator_detection_result *detection = &result->detections[best_det_idx];
            uint32_t next_hits = track->hits + 1U;
            elevator_rect previous_rect = track->detection.rect;
            int preserve_child_box = elevator_should_preserve_child_like_track_box(track, detection);

            detection_matched[best_det_idx] = 1U;
            track->matched_in_frame = 1U;
            track->lost_frames = 0U;
            track->last_timestamp_ms = timestamp_ms;
            track->hits = next_hits;
            track->detection = *detection;
            if (preserve_child_box != 0) {
                track->detection.rect = previous_rect;
                detection->rect = previous_rect;
                track->detection.child_like = 1U;
                detection->child_like = 1U;
            } else if (next_hits >= ELEVATOR_TRACK_MATURE_HITS &&
                elevator_should_blend_mature_track_rect(previous_rect, detection->rect) != 0) {
                elevator_rect blended_rect = elevator_blend_mature_track_rect(previous_rect, detection->rect);
                track->detection.rect = blended_rect;
                detection->rect = blended_rect;
            }
            track->child_like = track->detection.child_like;
            track->detection.track_id = track->track_id;
            track->detection.track_state = detection->synthetic != 0U ? ELEVATOR_TRACK_STATE_HELD :
                (next_hits >= ELEVATOR_TRACK_CONFIRM_HITS ? ELEVATOR_TRACK_STATE_CONFIRMED :
                    ELEVATOR_TRACK_STATE_TENTATIVE);
            detection->track_id = track->track_id;
            detection->track_state = track->detection.track_state;
        }
    }

    for (size_t det_idx = 0; det_idx < result->detection_count; ++det_idx) {
        size_t free_track_idx;
        elevator_detection_result *detection = &result->detections[det_idx];

        if (detection->class_id != 0U || detection_matched[det_idx] != 0U) {
            continue;
        }

        free_track_idx = (size_t)-1;
        for (size_t track_idx = 0; track_idx < ELEVATOR_MAX_PERSON_TRACKS; ++track_idx) {
            if (tracker->tracks[track_idx].active == 0U) {
                free_track_idx = track_idx;
                break;
            }
        }
        if (free_track_idx == (size_t)-1) {
            continue;
        }

        tracker->tracks[free_track_idx].active = 1U;
        tracker->tracks[free_track_idx].track_id = tracker->next_track_id++;
        tracker->tracks[free_track_idx].detection = *detection;
        tracker->tracks[free_track_idx].hits = 1U;
        tracker->tracks[free_track_idx].lost_frames = 0U;
        tracker->tracks[free_track_idx].last_timestamp_ms = timestamp_ms;
        tracker->tracks[free_track_idx].matched_in_frame = 1U;
        tracker->tracks[free_track_idx].child_like = detection->child_like;
        detection->track_id = tracker->tracks[free_track_idx].track_id;
        detection->track_state = ELEVATOR_TRACK_STATE_TENTATIVE;
    }

    (void)elevator_apply_track_aware_duplicate_cleanup(tracker, result, frame_width, frame_height);

    for (size_t track_idx = 0; track_idx < ELEVATOR_MAX_PERSON_TRACKS; ++track_idx) {
        elevator_person_track *track = &tracker->tracks[track_idx];
        float detection_quality = elevator_detection_quality_score(&track->detection, frame_width, frame_height);
        int mature_track = elevator_person_track_is_mature(track);

        if (track->active == 0U) {
            continue;
        }
        if (track->matched_in_frame == 0U) {
            if (track->hits >= ELEVATOR_TRACK_CONFIRM_HITS &&
                track->lost_frames < tracker->max_lost_frames &&
                track->last_timestamp_ms != 0 &&
                timestamp_ms >= track->last_timestamp_ms &&
                timestamp_ms - track->last_timestamp_ms <= tracker->max_lost_ms) {
                track->lost_frames++;
                held_count++;
            } else {
                track->active = 0U;
                continue;
            }
        } else if (track->detection.synthetic != 0U) {
            held_count++;
        }

        if (track->hits >= ELEVATOR_TRACK_CONFIRM_HITS) {
            confirmed_count++;
            if (mature_track != 0) {
                mature_confirmed_count++;
            }
            if (track->matched_in_frame != 0U && track->detection.synthetic == 0U) {
                matched_confirmed_count++;
            } else if (track->detection.synthetic != 0U || track->child_like != 0U || detection_quality >= 0.35f) {
                held_eligible_count++;
            }
            if (track->matched_in_frame == 0U &&
                elevator_person_track_is_mature_public_carry_eligible(track, frame_width, frame_height) != 0) {
                mature_held_count++;
            }
        } else if (track->matched_in_frame != 0U && track->detection.synthetic == 0U &&
            (track->detection.score >= 0.55f || track->child_like != 0U)) {
            tentative_count++;
        }
    }

    result->stats.raw_person_count = raw_person_count;
    result->stats.confirmed_track_person_count = confirmed_count;
    result->stats.tentative_person_count = tentative_count;
    result->stats.held_person_count = held_count;
    result->stats.mature_confirmed_person_count = mature_confirmed_count;
    result->stats.mature_held_person_count = mature_held_count;
    public_person_count = matched_confirmed_count + tentative_count;
    if (held_count > 0U || mature_confirmed_count > public_person_count) {
        uint32_t carry_target = raw_person_count;
        uint32_t visible_cap = raw_person_count;
        uint32_t available_held = held_eligible_count;
        if (mature_confirmed_count > carry_target) {
            carry_target = mature_confirmed_count;
        }
        if (carry_target == 0U && tracker->last_public_person_count > carry_target) {
            carry_target = tracker->last_public_person_count;
        }
        if (tracker->last_public_person_count > visible_cap) {
            visible_cap = tracker->last_public_person_count;
        }
        if (carry_target > visible_cap) {
            carry_target = visible_cap;
        }
        if (mature_held_count > available_held) {
            available_held = mature_held_count;
        }
        if (public_person_count == 0U && held_count > available_held) {
            available_held = held_count;
        }
        if (public_person_count < carry_target) {
            uint32_t shortage = carry_target - public_person_count;
            uint32_t requested = available_held < shortage ? available_held : shortage;
            uint32_t appended = elevator_append_public_hold_detections(
                tracker, result, requested, frame_width, frame_height, &mature_public_carry_count);
            public_person_count += appended;
        }
    }
    result->stats.person_count = public_person_count;
    result->stats.public_person_count_from_mature_carry = mature_public_carry_count;
    tracker->last_public_person_count = public_person_count;
}

void elevator_ebike_tracker_reset(elevator_ebike_tracker *tracker, uint32_t max_lost_frames, uint64_t max_lost_ms)
{
    if (tracker == NULL) {
        return;
    }

    memset(tracker, 0, sizeof(*tracker));
    tracker->next_track_id = 1U;
    tracker->max_lost_frames = max_lost_frames;
    tracker->max_lost_ms = max_lost_ms;
}

static float elevator_ebike_tracker_match_score(const elevator_ebike_track *track,
    const elevator_detection_result *detection)
{
    float iou;
    uint64_t center_dist_sq;
    uint64_t min_side;
    uint64_t max_center_distance_sq;

    if (track == NULL || detection == NULL) {
        return -1.0f;
    }

    iou = elevator_rect_iou(&track->detection.rect, &detection->rect);
    center_dist_sq = elevator_rect_center_distance_sq(&track->detection.rect, &detection->rect);
    min_side = elevator_rect_width(&track->detection.rect);
    if (elevator_rect_height(&track->detection.rect) < min_side) {
        min_side = elevator_rect_height(&track->detection.rect);
    }
    if (elevator_rect_width(&detection->rect) < min_side) {
        min_side = elevator_rect_width(&detection->rect);
    }
    if (elevator_rect_height(&detection->rect) < min_side) {
        min_side = elevator_rect_height(&detection->rect);
    }
    if (min_side == 0ULL) {
        min_side = 1ULL;
    }
    max_center_distance_sq = (min_side * min_side * 24ULL * 24ULL) / 10000ULL;
    if (iou < ELEVATOR_EBIKE_TRACK_MATCH_MIN_IOU && center_dist_sq > max_center_distance_sq) {
        return -1.0f;
    }
    return iou + ((float)track->hits * 0.03f) -
        ((float)center_dist_sq / (float)(max_center_distance_sq + 1ULL) * 0.10f);
}

static int elevator_ebike_meets_public_score(const elevator_detection_result *candidate, int was_confirmed_public)
{
    if (candidate == NULL || candidate->class_id != 1U) {
        return 0;
    }
    if (candidate->score >= ELEVATOR_PUBLIC_EBIKE_MIN_SCORE) {
        return 1;
    }
    return was_confirmed_public != 0 && candidate->score >= ELEVATOR_PUBLIC_EBIKE_RETAIN_MIN_SCORE;
}

static int elevator_ebike_is_publicworthy(const elevator_parse_result *result,
    const elevator_detection_result *candidate, size_t candidate_idx,
    uint32_t frame_width, uint32_t frame_height, int was_confirmed_public)
{
    size_t idx;

    (void)frame_width;
    (void)frame_height;

    if (result == NULL || candidate == NULL ||
        elevator_ebike_meets_public_score(candidate, was_confirmed_public) == 0) {
        return 0;
    }

    for (idx = 0; idx < result->detection_count; ++idx) {
        const elevator_detection_result *person = &result->detections[idx];
        uint64_t coverage_percent;
        uint32_t person_height;
        uint32_t person_width;
        uint32_t candidate_height;
        uint32_t candidate_width;

        if (idx == candidate_idx || person->class_id != 0U || person->score < 0.35f) {
            continue;
        }

        coverage_percent = elevator_rect_coverage_percent(&candidate->rect, &person->rect);
        if (coverage_percent < 60ULL) {
            continue;
        }

        person_height = elevator_rect_height(&person->rect);
        person_width = elevator_rect_width(&person->rect);
        candidate_height = elevator_rect_height(&candidate->rect);
        candidate_width = elevator_rect_width(&candidate->rect);
        if (person_height == 0U || person_width == 0U || candidate_height == 0U || candidate_width == 0U) {
            continue;
        }

        if (candidate->rect.y1 >= person->rect.y1 + (person_height / 5U) &&
            (uint64_t)candidate_width * 100ULL <= (uint64_t)person_width * 220ULL &&
            (uint64_t)candidate_height * 100ULL <= (uint64_t)person_height * 130ULL) {
            return 0;
        }
    }

    return 1;
}

void elevator_ebike_tracker_apply(elevator_ebike_tracker *tracker, elevator_parse_result *result, uint64_t timestamp_ms,
    uint32_t frame_width, uint32_t frame_height)
{
    unsigned char detection_matched[ELEVATOR_MAX_DETECTIONS];
    size_t best_track_idx;
    size_t best_det_idx;
    uint32_t public_count = 0U;
    size_t idx;

    (void)frame_width;
    (void)frame_height;

    if (tracker == NULL || result == NULL) {
        return;
    }

    memset(detection_matched, 0, sizeof(detection_matched));
    for (idx = 0; idx < result->detection_count; ++idx) {
        if (result->detections[idx].class_id != 1U) {
            continue;
        }
        result->detections[idx].track_id = 0U;
        result->detections[idx].track_state = ELEVATOR_TRACK_STATE_NONE;
    }
    for (idx = 0; idx < ELEVATOR_MAX_EBIKE_TRACKS; ++idx) {
        tracker->tracks[idx].matched_in_frame = 0U;
    }

    while (1) {
        float best_score = -1.0f;

        best_track_idx = (size_t)-1;
        best_det_idx = (size_t)-1;
        for (idx = 0; idx < ELEVATOR_MAX_EBIKE_TRACKS; ++idx) {
            elevator_ebike_track *track = &tracker->tracks[idx];
            if (track->active == 0U) {
                continue;
            }
            if (track->last_timestamp_ms != 0U && timestamp_ms >= track->last_timestamp_ms &&
                timestamp_ms - track->last_timestamp_ms > tracker->max_lost_ms) {
                track->active = 0U;
                continue;
            }
            if (track->matched_in_frame != 0U) {
                continue;
            }
            for (size_t det_idx = 0; det_idx < result->detection_count; ++det_idx) {
                float match_score;
                elevator_detection_result *detection = &result->detections[det_idx];

                if (detection_matched[det_idx] != 0U || detection->class_id != 1U) {
                    continue;
                }
                match_score = elevator_ebike_tracker_match_score(track, detection);
                if (match_score > best_score) {
                    best_score = match_score;
                    best_track_idx = idx;
                    best_det_idx = det_idx;
                }
            }
        }

        if (best_track_idx == (size_t)-1 || best_det_idx == (size_t)-1) {
            break;
        }

        {
            elevator_ebike_track *track = &tracker->tracks[best_track_idx];
            elevator_detection_result *detection = &result->detections[best_det_idx];
            int publicworthy;
            int was_confirmed_public = (track->hits >= ELEVATOR_EBIKE_TRACK_CONFIRM_HITS &&
                track->detection.track_state == ELEVATOR_TRACK_STATE_CONFIRMED);

            detection_matched[best_det_idx] = 1U;
            track->matched_in_frame = 1U;
            track->lost_frames = 0U;
            track->last_timestamp_ms = timestamp_ms;
            track->hits++;
            track->detection = *detection;
            track->detection.track_id = track->track_id;
            publicworthy = elevator_ebike_is_publicworthy(
                result,
                detection,
                best_det_idx,
                frame_width,
                frame_height,
                was_confirmed_public
            );
            track->detection.track_state = (track->hits >= ELEVATOR_EBIKE_TRACK_CONFIRM_HITS && publicworthy != 0) ?
                ELEVATOR_TRACK_STATE_CONFIRMED : ELEVATOR_TRACK_STATE_TENTATIVE;
            detection->track_id = track->track_id;
            detection->track_state = track->detection.track_state;
        }
    }

    for (idx = 0; idx < result->detection_count; ++idx) {
        size_t free_track_idx;
        elevator_detection_result *detection = &result->detections[idx];

        if (detection->class_id != 1U || detection_matched[idx] != 0U) {
            continue;
        }
        free_track_idx = (size_t)-1;
        for (size_t track_idx = 0; track_idx < ELEVATOR_MAX_EBIKE_TRACKS; ++track_idx) {
            if (tracker->tracks[track_idx].active == 0U) {
                free_track_idx = track_idx;
                break;
            }
        }
        if (free_track_idx == (size_t)-1) {
            continue;
        }

        tracker->tracks[free_track_idx].active = 1U;
        tracker->tracks[free_track_idx].track_id = tracker->next_track_id++;
        tracker->tracks[free_track_idx].detection = *detection;
        tracker->tracks[free_track_idx].hits = 1U;
        tracker->tracks[free_track_idx].lost_frames = 0U;
        tracker->tracks[free_track_idx].last_timestamp_ms = timestamp_ms;
        tracker->tracks[free_track_idx].matched_in_frame = 1U;
        detection->track_id = tracker->tracks[free_track_idx].track_id;
        detection->track_state = ELEVATOR_TRACK_STATE_TENTATIVE;
    }

    for (idx = 0; idx < ELEVATOR_MAX_EBIKE_TRACKS; ++idx) {
        elevator_ebike_track *track = &tracker->tracks[idx];

        if (track->active == 0U) {
            continue;
        }
        if (track->matched_in_frame == 0U) {
            int keep_public_hold = (track->detection.track_state == ELEVATOR_TRACK_STATE_CONFIRMED &&
                track->hits >= ELEVATOR_EBIKE_TRACK_CONFIRM_HITS &&
                track->detection.score >= ELEVATOR_PUBLIC_EBIKE_RETAIN_MIN_SCORE);
            if (track->hits >= ELEVATOR_EBIKE_TRACK_CONFIRM_HITS &&
                track->lost_frames < tracker->max_lost_frames &&
                track->last_timestamp_ms != 0U &&
                timestamp_ms >= track->last_timestamp_ms &&
                timestamp_ms - track->last_timestamp_ms <= tracker->max_lost_ms) {
                track->lost_frames++;
                if (keep_public_hold != 0 && result->detection_count < ELEVATOR_MAX_DETECTIONS) {
                    elevator_detection_result held_detection = track->detection;
                    held_detection.track_state = ELEVATOR_TRACK_STATE_HELD;
                    held_detection.synthetic = 0U;
                    result->detections[result->detection_count++] = held_detection;
                    public_count++;
                }
            } else {
                track->active = 0U;
                continue;
            }
        } else if (track->detection.track_state == ELEVATOR_TRACK_STATE_CONFIRMED &&
            track->hits >= ELEVATOR_EBIKE_TRACK_CONFIRM_HITS &&
            track->detection.score >= ELEVATOR_PUBLIC_EBIKE_RETAIN_MIN_SCORE) {
            public_count++;
        }
    }

    result->stats.ebike_count = public_count;
    result->stats.smoothed_ebike_count = public_count;
}

uint32_t elevator_public_detection_color(const elevator_detection_result *detection)
{
    if (detection == NULL) {
        return ELEVATOR_PUBLIC_PERSON_COLOR;
    }
    if (detection->class_id == 1U) {
        return ELEVATOR_PUBLIC_EBIKE_COLOR;
    }
    return ELEVATOR_PUBLIC_PERSON_COLOR;
}

int elevator_review_surface_detection_should_render(elevator_review_surface surface,
    const elevator_detection_result *detection, uint32_t frame_width, uint32_t frame_height)
{
    (void)frame_width;
    (void)frame_height;

    if (detection == NULL) {
        return 0;
    }
    if (surface == ELEVATOR_REVIEW_SURFACE_DEBUG) {
        return (detection->class_id == 0U || detection->class_id == 1U) ? 1 : 0;
    }
    if (detection->class_id == 1U) {
        if (detection->synthetic != 0U || detection->track_id == 0U) {
            return 0;
        }
        if (surface == ELEVATOR_REVIEW_SURFACE_CLEAN) {
            return (detection->track_state == ELEVATOR_TRACK_STATE_TENTATIVE ||
                detection->track_state == ELEVATOR_TRACK_STATE_CONFIRMED ||
                detection->track_state == ELEVATOR_TRACK_STATE_HELD) &&
                detection->score >= 0.35f;
        }
        return (detection->track_state == ELEVATOR_TRACK_STATE_CONFIRMED ||
            detection->track_state == ELEVATOR_TRACK_STATE_HELD) &&
            detection->score >= ELEVATOR_PUBLIC_EBIKE_RETAIN_MIN_SCORE;
    }
    if (detection->class_id == 0U) {
        return detection->synthetic == 0U;
    }
    return 0;
}

uint32_t elevator_review_surface_detection_color(elevator_review_surface surface,
    const elevator_detection_result *detection)
{
    if (detection == NULL) {
        return ELEVATOR_PUBLIC_PERSON_COLOR;
    }
    if (detection->class_id == 1U) {
        return ELEVATOR_PUBLIC_EBIKE_COLOR;
    }
    if (surface != ELEVATOR_REVIEW_SURFACE_DEBUG) {
        return ELEVATOR_PUBLIC_PERSON_COLOR;
    }
    if (detection->child_like != 0U) {
        return ELEVATOR_DEBUG_PERSON_CHILD_COLOR;
    }
    if (detection->track_state == ELEVATOR_TRACK_STATE_TENTATIVE) {
        return ELEVATOR_DEBUG_PERSON_TENTATIVE_COLOR;
    }
    if (detection->track_state == ELEVATOR_TRACK_STATE_HELD) {
        return ELEVATOR_DEBUG_PERSON_HELD_COLOR;
    }
    return ELEVATOR_PUBLIC_PERSON_COLOR;
}

int elevator_public_detection_should_render(const elevator_detection_result *detection,
    uint32_t frame_width, uint32_t frame_height)
{
    uint32_t width;
    uint32_t height;

    if (detection == NULL) {
        return 0;
    }
    if (detection->class_id == 1U) {
        return detection->score >= ELEVATOR_PUBLIC_EBIKE_RETAIN_MIN_SCORE &&
            detection->track_id != 0U &&
            (detection->track_state == ELEVATOR_TRACK_STATE_CONFIRMED ||
                (detection->track_state == ELEVATOR_TRACK_STATE_HELD && detection->synthetic == 0U));
    }
    if (detection->class_id != 0U) {
        return 0;
    }

    if (detection->synthetic != 0U) {
        return 0;
    }

    width = elevator_rect_width(&detection->rect);
    height = elevator_rect_height(&detection->rect);
    if (width == 0U || height == 0U) {
        return 0;
    }

    if (frame_width > 0U && frame_height > 0U) {
        uint64_t frame_area = (uint64_t)frame_width * (uint64_t)frame_height;
        uint64_t candidate_area = elevator_rect_area(&detection->rect);
        uint64_t area_percent = frame_area == 0ULL ? 0ULL : (candidate_area * 100ULL) / frame_area;
        uint64_t height_percent = ((uint64_t)height * 100ULL) / (uint64_t)frame_height;

        if (detection->score <= ELEVATOR_PUBLIC_PERSON_TOP_EDGE_SCORE_CEILING &&
            elevator_rect_touches_top_edge(&detection->rect) != 0 &&
            area_percent >= ELEVATOR_PUBLIC_PERSON_TOP_EDGE_MIN_AREA_PERCENT &&
            height_percent >= ELEVATOR_PUBLIC_PERSON_TOP_EDGE_MIN_HEIGHT_PERCENT) {
            return 0;
        }

        if (detection->track_state == ELEVATOR_TRACK_STATE_TENTATIVE &&
            detection->score <= ELEVATOR_PUBLIC_PERSON_EDGE_SCORE_CEILING &&
            elevator_rect_touches_frame_edge(&detection->rect, frame_width, frame_height) != 0 &&
            area_percent >= ELEVATOR_PUBLIC_PERSON_TENTATIVE_EDGE_MIN_AREA_PERCENT) {
            return 0;
        }
    }

    return 1;
}

int elevator_parse_raw_outputs(const float *count_data, size_t count_len,
    const float *roi_data, size_t roi_stride_floats, size_t roi_plane_count, size_t max_rois,
    uint32_t proc_width, uint32_t proc_height, uint32_t show_width, uint32_t show_height,
    float score_threshold, float nms_threshold, int ebike_fp_cleanup_mode,
    elevator_parse_result *result, char *errbuf, size_t errbuf_size)
{
    size_t det_count = 0;
    size_t idx;
    size_t write_idx = 0;
    const float *x_min;
    const float *y_min;
    const float *x_max;
    const float *y_max;
    const float *score_plane;
    const float *class_plane;
    uint32_t person_count;
    uint32_t ebike_count;

    if (result == NULL) {
        return -1;
    }

    memset(result, 0, sizeof(*result));
    if (errbuf != NULL && errbuf_size > 0) {
        errbuf[0] = '\0';
    }

    if (count_data == NULL || roi_data == NULL) {
        if (errbuf != NULL && errbuf_size > 0) {
            snprintf(errbuf, errbuf_size, "null output buffer");
        }
        return -1;
    }
    if (count_len == 0 || roi_stride_floats == 0 || roi_plane_count < 6 || max_rois == 0) {
        if (errbuf != NULL && errbuf_size > 0) {
            snprintf(errbuf, errbuf_size, "invalid output metadata");
        }
        return -1;
    }
    if (proc_width == 0 || proc_height == 0 || show_width == 0 || show_height == 0) {
        if (errbuf != NULL && errbuf_size > 0) {
            snprintf(errbuf, errbuf_size, "invalid frame size");
        }
        return -1;
    }
    if (!isfinite(score_threshold) || score_threshold < 0.0f || score_threshold > 1.0f) {
        if (errbuf != NULL && errbuf_size > 0) {
            snprintf(errbuf, errbuf_size, "invalid score threshold");
        }
        return -1;
    }
    if (!isfinite(nms_threshold) || nms_threshold < 0.0f || nms_threshold > 1.0f) {
        if (errbuf != NULL && errbuf_size > 0) {
            snprintf(errbuf, errbuf_size, "invalid nms threshold");
        }
        return -1;
    }

    for (idx = 0; idx < count_len; ++idx) {
        det_count += elevator_round_u32(count_data[idx]);
    }
    if (det_count > max_rois) {
        det_count = max_rois;
    }
    if (det_count > ELEVATOR_MAX_DETECTIONS) {
        det_count = ELEVATOR_MAX_DETECTIONS;
    }

    x_min = roi_data;
    y_min = x_min + roi_stride_floats;
    x_max = y_min + roi_stride_floats;
    y_max = x_max + roi_stride_floats;
    score_plane = y_max + roi_stride_floats;
    class_plane = score_plane + roi_stride_floats;

    for (idx = 0; idx < det_count; ++idx) {
        float clamped_score = score_plane[idx];
        elevator_detection_result *det;
        float scaled_x1;
        float scaled_y1;
        float scaled_x2;
        float scaled_y2;

        if (!isfinite(clamped_score) || clamped_score < 0.0f) {
            clamped_score = 0.0f;
        } else if (clamped_score > 1.0f) {
            clamped_score = 1.0f;
        }
        if (clamped_score < score_threshold) {
            continue;
        }

        scaled_x1 = (x_min[idx] / (float)proc_width) * (float)show_width;
        scaled_y1 = (y_min[idx] / (float)proc_height) * (float)show_height;
        scaled_x2 = (x_max[idx] / (float)proc_width) * (float)show_width;
        scaled_y2 = (y_max[idx] / (float)proc_height) * (float)show_height;
        det = &result->detections[write_idx];
        det->rect.x1 = elevator_clamp_to_frame_even_u32(elevator_round_u32(scaled_x1), show_width);
        det->rect.y1 = elevator_clamp_to_frame_even_u32(elevator_round_u32(scaled_y1), show_height);
        det->rect.x2 = elevator_clamp_to_frame_even_u32(elevator_round_u32(scaled_x2), show_width);
        det->rect.y2 = elevator_clamp_to_frame_even_u32(elevator_round_u32(scaled_y2), show_height);
        if (det->rect.x2 < det->rect.x1) {
            uint32_t tmp = det->rect.x1;
            det->rect.x1 = det->rect.x2;
            det->rect.x2 = tmp;
        }
        if (det->rect.y2 < det->rect.y1) {
            uint32_t tmp = det->rect.y1;
            det->rect.y1 = det->rect.y2;
            det->rect.y2 = tmp;
        }
        if ((det->rect.x2 <= det->rect.x1) || (det->rect.y2 <= det->rect.y1)) {
            continue;
        }
        if (!elevator_rect_is_geometry_valid(&det->rect)) {
            continue;
        }
        if (elevator_rect_is_low_score_strip_artifact(&det->rect, clamped_score)) {
            continue;
        }

        det->score = clamped_score;
        det->score_percent = elevator_round_u32(clamped_score * 100.0f);
        det->class_id = elevator_round_u32(class_plane[idx]);
        write_idx++;
    }

    if (write_idx > 0) {
        if (write_idx > 1) {
            write_idx = elevator_apply_nms(result->detections, write_idx, nms_threshold);
            /* Keep this narrower than NMS: only drop low-score same-class boxes that
             * are almost fully covered by a much larger higher-score box. */
            write_idx = elevator_apply_containment_cleanup(result->detections, write_idx,
                show_width, show_height);
        }
        write_idx = elevator_apply_low_score_large_box_cleanup(result->detections, write_idx,
            show_width, show_height);
        write_idx = elevator_apply_class_specific_false_positive_cleanup(result->detections, write_idx,
            show_width, show_height, ebike_fp_cleanup_mode);
        if (write_idx > 1) {
            write_idx = elevator_apply_duplicate_cluster_cleanup(result->detections, write_idx,
                show_width, show_height);
        }
    }

    person_count = 0;
    ebike_count = 0;
    for (idx = 0; idx < write_idx; ++idx) {
        if (result->detections[idx].class_id == 0) {
            person_count++;
        } else if (result->detections[idx].class_id == 1) {
            ebike_count++;
        }
    }

    result->detection_count = write_idx;
    result->stats.person_count = person_count;
    result->stats.ebike_count = ebike_count;
    result->stats.smoothed_person_count = person_count;
    result->stats.smoothed_ebike_count = ebike_count;
    result->stats.raw_person_count = person_count;
    result->stats.confirmed_track_person_count = person_count;
    result->stats.tentative_person_count = 0U;
    result->stats.held_person_count = 0U;
    result->stats.mature_confirmed_person_count = 0U;
    result->stats.mature_held_person_count = 0U;
    result->stats.public_person_count_from_mature_carry = 0U;
    result->stats.fps = 0.0f;
    return 0;
}
