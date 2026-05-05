#include "elevator_batch.h"
#include "elevator_panel_text.h"
#include "elevator_postprocess.h"
#include "elevator_yolo.h"

#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int expect_true(int condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "test failed: %s\n", message);
        return 1;
    }
    return 0;
}

static int test_cli_defaults(void)
{
    elevator_runtime_config cfg;
    char *argv[] = {"elevator_yolo", "file"};
    char errbuf[256];

    if (elevator_parse_cli(2, argv, &cfg, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected cli parse error: %s\n", errbuf);
        return 1;
    }

    if (expect_true(cfg.mode == ELEVATOR_RUN_MODE_FILE, "file mode selected") != 0) {
        return 1;
    }
    if (expect_true(strstr(cfg.input_path, "dolls_video.h264") != NULL, "default input path") != 0) {
        return 1;
    }
    if (expect_true(strstr(cfg.model_path, "yolov8.om") != NULL, "default model path") != 0) {
        return 1;
    }
    if (expect_true(cfg.score_threshold == 0.15f, "default score threshold") != 0) {
        return 1;
    }
    if (expect_true(cfg.nms_threshold == 0.45f, "default nms threshold") != 0) {
        return 1;
    }
    if (expect_true(cfg.review_surface == ELEVATOR_REVIEW_SURFACE_CLEAN, "default review surface is clean") != 0) {
        return 1;
    }
    if (expect_true(cfg.ebike_cleanup_mode == ELEVATOR_EBIKE_CLEANUP_CLI_AUTO,
            "default ebike cleanup mode is auto") != 0) {
        return 1;
    }
    if (expect_true(cfg.timing_mode == ELEVATOR_PLAYBACK_TIMING_SOURCE, "default playback timing is source") != 0) {
        return 1;
    }
    if (expect_true(cfg.single_shot != 0, "file mode defaults to single-shot playback") != 0) {
        return 1;
    }
    return 0;
}

static int test_cli_file_surface_and_timing_options(void)
{
    elevator_runtime_config cfg;
    char *argv[] = {
        "elevator_yolo",
        "file",
        "--surface", "debug",
        "--ebike-cleanup", "off",
        "--timing", "source",
        "--single-shot",
        "--source-fps", "30",
        "--source-frame-count", "437",
        "--source-duration-ms", "14567",
    };
    char errbuf[256];

    if (elevator_parse_cli((int)(sizeof(argv) / sizeof(argv[0])), argv, &cfg, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected file cli parse error: %s\n", errbuf);
        return 1;
    }

    if (expect_true(cfg.mode == ELEVATOR_RUN_MODE_FILE, "file mode selected for source-timed playback") != 0) {
        return 1;
    }
    if (expect_true(cfg.review_surface == ELEVATOR_REVIEW_SURFACE_DEBUG, "debug review surface parsed") != 0) {
        return 1;
    }
    if (expect_true(cfg.ebike_cleanup_mode == ELEVATOR_EBIKE_CLEANUP_CLI_OFF,
            "ebike cleanup off parsed") != 0) {
        return 1;
    }
    if (expect_true(cfg.timing_mode == ELEVATOR_PLAYBACK_TIMING_SOURCE, "source timing mode parsed") != 0) {
        return 1;
    }
    if (expect_true(cfg.single_shot != 0, "single-shot flag parsed") != 0) {
        return 1;
    }
    if (expect_true(cfg.source_fps == 30.0f, "source fps parsed") != 0) {
        return 1;
    }
    if (expect_true(cfg.source_frame_count == 437U, "source frame count parsed") != 0) {
        return 1;
    }
    if (expect_true(cfg.source_duration_ms == 14567U, "source duration parsed") != 0) {
        return 1;
    }
    if (expect_true(elevator_file_mode_prefers_frame_feed(&cfg) != 0,
            "source-timed single-shot file playback prefers frame feed") != 0) {
        return 1;
    }
    if (expect_true(elevator_file_mode_prefers_playback_display(&cfg) != 0,
            "source-timed single-shot file playback prefers playback display mode") != 0) {
        return 1;
    }
    return 0;
}

static int test_smoother(void)
{
    elevator_smoother smoother;
    elevator_count_stats stats;

    elevator_smoother_reset(&smoother, 5);
    elevator_smoother_update(&smoother, 1, 0, 1000, &stats);
    elevator_smoother_update(&smoother, 3, 0, 1100, &stats);
    elevator_smoother_update(&smoother, 2, 1, 1200, &stats);
    elevator_smoother_update(&smoother, 4, 1, 1300, &stats);
    elevator_smoother_update(&smoother, 2, 1, 1400, &stats);

    if (expect_true(stats.smoothed_person_count == 2, "median smooth person count") != 0) {
        return 1;
    }
    if (expect_true(stats.smoothed_ebike_count == 1, "median smooth ebike count") != 0) {
        return 1;
    }
    if (expect_true((stats.fps > 9.9f) && (stats.fps < 10.1f), "fps calculation") != 0) {
        return 1;
    }

    elevator_smoother_update(&smoother, 7, 0, 1500, &stats);
    elevator_smoother_update(&smoother, 9, 2, 1600, &stats);
    if (expect_true(stats.smoothed_person_count == 4, "median smooth after wrap") != 0) {
        return 1;
    }
    if (expect_true(stats.smoothed_ebike_count == 1, "ebike median after wrap") != 0) {
        return 1;
    }
    return 0;
}

static int test_temporal_hold(void)
{
    elevator_temporal_hold hold;
    elevator_parse_result result;
    const uint32_t frame_width = 1000;
    const uint32_t frame_height = 1000;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.95f;
    result.detections[0].rect.x1 = 100;
    result.detections[0].rect.y1 = 100;
    result.detections[0].rect.x2 = 220;
    result.detections[0].rect.y2 = 320;
    result.detections[1].class_id = 0;
    result.detections[1].score = 0.90f;
    result.detections[1].rect.x1 = 500;
    result.detections[1].rect.y1 = 120;
    result.detections[1].rect.x2 = 600;
    result.detections[1].rect.y2 = 320;
    result.stats.person_count = 2;
    elevator_temporal_hold_reset(&hold, 2, 250);
    elevator_temporal_hold_apply(&hold, &result, 1000, frame_width, frame_height);

    memset(&result, 0, sizeof(result));
    result.detection_count = 2;
    result.detections[0].class_id = 0;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.95f;
    result.detections[0].rect.x1 = 102;
    result.detections[0].rect.y1 = 102;
    result.detections[0].rect.x2 = 222;
    result.detections[0].rect.y2 = 322;
    result.detections[1].class_id = 0;
    result.detections[1].score = 0.89f;
    result.detections[1].rect.x1 = 498;
    result.detections[1].rect.y1 = 122;
    result.detections[1].rect.x2 = 598;
    result.detections[1].rect.y2 = 322;
    result.stats.person_count = 2;
    elevator_temporal_hold_apply(&hold, &result, 1100, frame_width, frame_height);

    memset(&result, 0, sizeof(result));
    result.detection_count = 2;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.94f;
    result.detections[0].rect.x1 = 104;
    result.detections[0].rect.y1 = 104;
    result.detections[0].rect.x2 = 224;
    result.detections[0].rect.y2 = 324;
    result.detections[1].class_id = 0;
    result.detections[1].score = 0.88f;
    result.detections[1].rect.x1 = 496;
    result.detections[1].rect.y1 = 124;
    result.detections[1].rect.x2 = 596;
    result.detections[1].rect.y2 = 324;
    result.stats.person_count = 2;
    elevator_temporal_hold_apply(&hold, &result, 1200, frame_width, frame_height);

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.94f;
    result.detections[0].rect.x1 = 106;
    result.detections[0].rect.y1 = 106;
    result.detections[0].rect.x2 = 226;
    result.detections[0].rect.y2 = 326;
    result.stats.person_count = 1;
    elevator_temporal_hold_apply(&hold, &result, 1300, frame_width, frame_height);
    if (expect_true(result.stats.person_count == 2, "temporal hold restores one missing stable person") != 0) {
        return 1;
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.94f;
    result.detections[0].rect.x1 = 108;
    result.detections[0].rect.y1 = 108;
    result.detections[0].rect.x2 = 228;
    result.detections[0].rect.y2 = 328;
    result.stats.person_count = 1;
    elevator_temporal_hold_apply(&hold, &result, 1400, frame_width, frame_height);
    if (expect_true(result.stats.person_count == 2, "temporal hold allows second short carry") != 0) {
        return 1;
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.94f;
    result.detections[0].rect.x1 = 110;
    result.detections[0].rect.y1 = 110;
    result.detections[0].rect.x2 = 230;
    result.detections[0].rect.y2 = 330;
    result.stats.person_count = 1;
    elevator_temporal_hold_apply(&hold, &result, 1500, frame_width, frame_height);
    if (expect_true(result.stats.person_count == 1, "temporal hold expires after configured hold frames") != 0) {
        return 1;
    }
    return 0;
}

static int test_cli_batch(void)
{
    elevator_runtime_config cfg;
    char *argv[] = {
        "elevator_yolo",
        "batch",
        "--images-dir", "/tmp/images",
        "--labels-dir", "/tmp/labels",
        "--output-dir", "/tmp/out",
        "--offset", "5",
        "--limit", "10",
        "--score", "0.25",
        "--nms", "0.55",
        "--ebike-cleanup", "full",
    };
    char errbuf[256];

    if (elevator_parse_cli((int)(sizeof(argv) / sizeof(argv[0])), argv, &cfg, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected batch cli parse error: %s\n", errbuf);
        return 1;
    }
    if (expect_true(cfg.mode == ELEVATOR_RUN_MODE_BATCH, "batch mode selected") != 0) {
        return 1;
    }
    if (expect_true(strcmp(cfg.images_dir, "/tmp/images") == 0, "batch images dir parsed") != 0) {
        return 1;
    }
    if (expect_true(strcmp(cfg.labels_dir, "/tmp/labels") == 0, "batch labels dir parsed") != 0) {
        return 1;
    }
    if (expect_true(strcmp(cfg.output_dir, "/tmp/out") == 0, "batch output dir parsed") != 0) {
        return 1;
    }
    if (expect_true(cfg.offset == 5, "batch offset parsed") != 0) {
        return 1;
    }
    if (expect_true(cfg.limit == 10, "batch limit parsed") != 0) {
        return 1;
    }
    if (expect_true(cfg.score_threshold == 0.25f, "batch score parsed") != 0) {
        return 1;
    }
    if (expect_true(cfg.nms_threshold == 0.55f, "batch nms parsed") != 0) {
        return 1;
    }
    if (expect_true(cfg.ebike_cleanup_mode == ELEVATOR_EBIKE_CLEANUP_CLI_FULL,
            "batch ebike cleanup full parsed") != 0) {
        return 1;
    }
    return 0;
}

static int test_parser(void)
{
    float counts[] = {2.0f, 1.0f};
    float roi[6][8] = {
        {10.0f, 120.0f, 240.0f},
        {20.0f, 100.0f, 140.0f},
        {110.0f, 300.0f, 400.0f},
        {220.0f, 320.0f, 360.0f},
        {0.91f, 0.83f, 0.76f},
        {0.0f, 1.0f, 0.0f},
    };
    elevator_parse_result result;
    char errbuf[256];

    if (elevator_parse_raw_outputs(counts, 2, &roi[0][0], 8, 6, 8,
            640, 640, 1280, 720, 0.80f, 0.45f, ELEVATOR_EBIKE_FP_CLEANUP_FULL,
            &result, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected parser error: %s\n", errbuf);
        return 1;
    }

    if (expect_true(result.detection_count == 2, "detection count after score filter") != 0) {
        return 1;
    }
    if (expect_true(result.stats.person_count == 1, "person count after score filter") != 0) {
        return 1;
    }
    if (expect_true(result.stats.ebike_count == 1, "ebike count") != 0) {
        return 1;
    }
    if (expect_true(result.detections[1].class_id == 1, "class id parsing") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].score_percent == 91, "score percent parsing") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].rect.x1 == 20, "bbox scaling and even align") != 0) {
        return 1;
    }
    return 0;
}

static int test_parser_drops_invalid_rect(void)
{
    float counts[] = {2.0f};
    float roi[6][4] = {
        {640.0f, 100.0f},
        {20.0f, 120.0f},
        {640.0f, 220.0f},
        {220.0f, 300.0f},
        {0.95f, 0.92f},
        {0.0f, 0.0f},
    };
    elevator_parse_result result;
    char errbuf[256];

    if (elevator_parse_raw_outputs(counts, 1, &roi[0][0], 4, 6, 4,
            640, 640, 1280, 720, 0.80f, 0.45f, ELEVATOR_EBIKE_FP_CLEANUP_FULL,
            &result, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected parser error: %s\n", errbuf);
        return 1;
    }

    if (expect_true(result.detection_count == 1, "invalid rect dropped after clamp") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].rect.x1 == 200, "remaining rect preserved") != 0) {
        return 1;
    }
    return 0;
}

static int test_parser_applies_nms(void)
{
    float counts[] = {2.0f};
    float roi[6][4] = {
        {100.0f, 110.0f},
        {100.0f, 110.0f},
        {220.0f, 218.0f},
        {320.0f, 318.0f},
        {0.95f, 0.90f},
        {0.0f, 0.0f},
    };
    elevator_parse_result result;
    char errbuf[256];

    if (elevator_parse_raw_outputs(counts, 1, &roi[0][0], 4, 6, 4,
            640, 640, 1280, 720, 0.80f, 0.45f, ELEVATOR_EBIKE_FP_CLEANUP_FULL,
            &result, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected parser error: %s\n", errbuf);
        return 1;
    }

    if (expect_true(result.detection_count == 1, "overlapping boxes suppressed by nms") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].score_percent == 95, "highest score survives nms") != 0) {
        return 1;
    }
    return 0;
}

static int test_person_tracker_duplicate_cleanup_and_child_protection(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;
    int child_like_count = 0;

    memset(&result, 0, sizeof(result));
    result.detection_count = 4;

    result.detections[0].class_id = 0;
    result.detections[0].score = 0.78f;
    result.detections[0].score_percent = 78;
    result.detections[0].rect.x1 = 510;
    result.detections[0].rect.y1 = 180;
    result.detections[0].rect.x2 = 700;
    result.detections[0].rect.y2 = 820;

    result.detections[1].class_id = 0;
    result.detections[1].score = 0.54f;
    result.detections[1].score_percent = 54;
    result.detections[1].rect.x1 = 450;
    result.detections[1].rect.y1 = 120;
    result.detections[1].rect.x2 = 998;
    result.detections[1].rect.y2 = 998;

    result.detections[2].class_id = 0;
    result.detections[2].score = 0.42f;
    result.detections[2].score_percent = 42;
    result.detections[2].rect.x1 = 730;
    result.detections[2].rect.y1 = 420;
    result.detections[2].rect.x2 = 810;
    result.detections[2].rect.y2 = 650;

    result.detections[3].class_id = 0;
    result.detections[3].score = 0.36f;
    result.detections[3].score_percent = 36;
    result.detections[3].rect.x1 = 706;
    result.detections[3].rect.y1 = 390;
    result.detections[3].rect.x2 = 846;
    result.detections[3].rect.y2 = 760;

    result.stats.person_count = 4;
    elevator_person_tracker_reset(&tracker, 6, 600);
    elevator_person_tracker_apply(&tracker, &result, 1000, 1000, 1000);

    if (expect_true(result.detection_count == 2, "tracker duplicate cleanup removes umbrella and child duplicate") != 0) {
        return 1;
    }
    if (expect_true(result.stats.raw_person_count == 4, "raw person count preserved before tracker cleanup") != 0) {
        return 1;
    }
    if (expect_true(result.stats.person_count == 2, "track-aware person count prefers deduplicated occupancy") != 0) {
        return 1;
    }

    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].child_like != 0U) {
            child_like_count++;
        }
        if (expect_true(result.detections[idx].track_id != 0U, "remaining detections carry track ids") != 0) {
            return 1;
        }
    }

    if (expect_true(child_like_count == 1, "child-like detection survives duplicate cleanup") != 0) {
        return 1;
    }
    if (expect_true(result.stats.tentative_person_count == 2, "adult and child are both counted as tentative occupancy") != 0) {
        return 1;
    }
    return 0;
}

static int test_public_overlay_color_is_state_agnostic(void)
{
    elevator_detection_result clean_person;
    elevator_detection_result debug_person;
    elevator_detection_result clean_ebike;
    elevator_detection_result debug_ebike;

    memset(&clean_person, 0, sizeof(clean_person));
    clean_person.class_id = 0;
    memset(&debug_person, 0, sizeof(debug_person));
    debug_person.class_id = 0;
    debug_person.track_state = ELEVATOR_TRACK_STATE_HELD;
    debug_person.child_like = 1U;
    debug_person.synthetic = 1U;

    memset(&clean_ebike, 0, sizeof(clean_ebike));
    clean_ebike.class_id = 1;
    memset(&debug_ebike, 0, sizeof(debug_ebike));
    debug_ebike.class_id = 1;
    debug_ebike.track_state = ELEVATOR_TRACK_STATE_TENTATIVE;
    debug_ebike.child_like = 1U;
    debug_ebike.synthetic = 1U;

    if (expect_true(elevator_public_detection_color(&clean_person) ==
            elevator_public_detection_color(&debug_person),
            "public person overlay ignores internal states") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_color(&clean_ebike) ==
            elevator_public_detection_color(&debug_ebike),
            "public ebike overlay ignores internal states") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_color(&clean_person) !=
            elevator_public_detection_color(&clean_ebike),
            "person and ebike keep distinct public overlay colors") != 0) {
        return 1;
    }
    return 0;
}

static int test_public_overlay_visibility_separates_count_truth_from_clean_render(void)
{
    elevator_detection_result detection;

    memset(&detection, 0, sizeof(detection));
    detection.class_id = 0U;
    detection.score = 0.42f;
    detection.rect.x1 = 420U;
    detection.rect.y1 = 160U;
    detection.rect.x2 = 620U;
    detection.rect.y2 = 620U;
    detection.track_id = 8U;
    detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    detection.synthetic = 1U;
    if (expect_true(elevator_public_detection_should_render(&detection, 1280U, 720U) == 0,
            "synthetic held person stays off clean/public overlay") != 0) {
        return 1;
    }

    detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    detection.synthetic = 0U;
    if (expect_true(elevator_public_detection_should_render(&detection, 1280U, 720U) != 0,
            "confirmed person remains visible on clean/public overlay") != 0) {
        return 1;
    }

    detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    if (expect_true(elevator_public_detection_should_render(&detection, 1280U, 720U) != 0,
            "eligible held person remains visible on clean/public overlay") != 0) {
        return 1;
    }

    detection.track_state = ELEVATOR_TRACK_STATE_TENTATIVE;
    detection.score = 0.16f;
    detection.rect.x1 = 620U;
    detection.rect.y1 = 0U;
    detection.rect.x2 = 1180U;
    detection.rect.y2 = 420U;
    if (expect_true(elevator_public_detection_should_render(&detection, 1280U, 720U) == 0,
            "low-score top-edge umbrella person is display-only suppressed") != 0) {
        return 1;
    }

    detection.score = 0.58f;
    detection.rect.x1 = 360U;
    detection.rect.y1 = 120U;
    detection.rect.x2 = 560U;
    detection.rect.y2 = 620U;
    if (expect_true(elevator_public_detection_should_render(&detection, 1280U, 720U) != 0,
            "plausible tentative person still renders in clean/public output") != 0) {
        return 1;
    }

    memset(&detection, 0, sizeof(detection));
    detection.class_id = 1U;
    detection.score = 0.88f;
    detection.rect.x1 = 720U;
    detection.rect.y1 = 240U;
    detection.rect.x2 = 1020U;
    detection.rect.y2 = 680U;
    detection.track_state = ELEVATOR_TRACK_STATE_TENTATIVE;
    if (expect_true(elevator_public_detection_should_render(&detection, 1280U, 720U) == 0,
            "tentative ebike stays off public overlay") != 0) {
        return 1;
    }

    detection.track_id = 3U;
    detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    if (expect_true(elevator_public_detection_should_render(&detection, 1280U, 720U) != 0,
            "confirmed ebike remains visible on public overlay") != 0) {
        return 1;
    }

    detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    if (expect_true(elevator_public_detection_should_render(&detection, 1280U, 720U) != 0,
            "eligible held ebike remains visible on public overlay") != 0) {
        return 1;
    }

    return 0;
}

static int test_osd_panel_prefers_live_ebike_count_over_smoothed_ebike_count(void)
{
    elevator_count_stats stats;
    elevator_parse_result render_result;
    char text[64];

    memset(&stats, 0, sizeof(stats));
    memset(&render_result, 0, sizeof(render_result));
    stats.person_count = 1U;
    stats.smoothed_person_count = 1U;
    stats.ebike_count = 0U;
    stats.smoothed_ebike_count = 0U;
    stats.fps = 29.6f;
    render_result.detection_count = 1U;
    render_result.detections[0].class_id = 1U;
    render_result.detections[0].track_id = 3U;
    render_result.detections[0].track_state = ELEVATOR_TRACK_STATE_TENTATIVE;
    render_result.detections[0].score = 0.87f;

    if (elevator_osd_format_panel_text(text, sizeof(text), &stats, &render_result,
            ELEVATOR_REVIEW_SURFACE_CLEAN) != 0) {
        fprintf(stderr, "unexpected panel format failure\n");
        return 1;
    }
    if (expect_true(strcmp(text, "C P:01 E:01 F:30") == 0,
            "panel should show rendered clean-surface ebike count even when stats ebike count is zero") != 0) {
        return 1;
    }
    return 0;
}

static int test_review_surface_filters_match_server_signoff_contract(void)
{
    elevator_detection_result detection;

    memset(&detection, 0, sizeof(detection));
    detection.class_id = 0U;
    detection.score = 0.42f;
    detection.track_id = 8U;
    detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    detection.synthetic = 1U;
    if (expect_true(
            elevator_review_surface_detection_should_render(ELEVATOR_REVIEW_SURFACE_CLEAN, &detection, 1280U, 720U) == 0,
            "clean surface hides synthetic person carry") != 0) {
        return 1;
    }
    if (expect_true(
            elevator_review_surface_detection_should_render(ELEVATOR_REVIEW_SURFACE_PUBLIC, &detection, 1280U, 720U) == 0,
            "public surface hides synthetic person carry") != 0) {
        return 1;
    }
    if (expect_true(
            elevator_review_surface_detection_should_render(ELEVATOR_REVIEW_SURFACE_DEBUG, &detection, 1280U, 720U) != 0,
            "debug surface keeps synthetic person carry visible") != 0) {
        return 1;
    }

    detection.synthetic = 0U;
    detection.track_state = ELEVATOR_TRACK_STATE_TENTATIVE;
    if (expect_true(
            elevator_review_surface_detection_should_render(ELEVATOR_REVIEW_SURFACE_CLEAN, &detection, 1280U, 720U) != 0,
            "clean surface keeps non-synthetic person visible") != 0) {
        return 1;
    }
    if (expect_true(
            elevator_review_surface_detection_should_render(ELEVATOR_REVIEW_SURFACE_PUBLIC, &detection, 1280U, 720U) != 0,
            "public surface keeps non-synthetic person visible") != 0) {
        return 1;
    }

    memset(&detection, 0, sizeof(detection));
    detection.class_id = 1U;
    detection.score = 0.62f;
    detection.track_id = 4U;
    detection.track_state = ELEVATOR_TRACK_STATE_TENTATIVE;
    if (expect_true(
            elevator_review_surface_detection_should_render(ELEVATOR_REVIEW_SURFACE_CLEAN, &detection, 1280U, 720U) != 0,
            "clean surface keeps tentative tracked ebike visible") != 0) {
        return 1;
    }
    if (expect_true(
            elevator_review_surface_detection_should_render(ELEVATOR_REVIEW_SURFACE_PUBLIC, &detection, 1280U, 720U) == 0,
            "public surface hides tentative ebike") != 0) {
        return 1;
    }

    detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    detection.score = 0.56f;
    if (expect_true(
            elevator_review_surface_detection_should_render(ELEVATOR_REVIEW_SURFACE_PUBLIC, &detection, 1280U, 720U) != 0,
            "public surface keeps confirmed retained-score ebike visible") != 0) {
        return 1;
    }

    detection.score = 0.34f;
    if (expect_true(
            elevator_review_surface_detection_should_render(ELEVATOR_REVIEW_SURFACE_CLEAN, &detection, 1280U, 720U) == 0,
            "clean surface hides low-score ebike below review threshold") != 0) {
        return 1;
    }
    if (expect_true(
            elevator_review_surface_detection_should_render(ELEVATOR_REVIEW_SURFACE_PUBLIC, &detection, 1280U, 720U) == 0,
            "public surface hides low-score ebike below retain threshold") != 0) {
        return 1;
    }

    return 0;
}

static int test_child_like_false_positive_suppression(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.60f;
    result.detections[0].score_percent = 60;
    result.detections[0].rect.x1 = 120;
    result.detections[0].rect.y1 = 120;
    result.detections[0].rect.x2 = 440;
    result.detections[0].rect.y2 = 540;
    result.stats.person_count = 1;

    elevator_person_tracker_reset(&tracker, 6, 600);
    elevator_person_tracker_apply(&tracker, &result, 1000, 1000, 1000);

    if (expect_true(result.detection_count == 1, "single adult-like detection preserved") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].child_like == 0U, "adult-like detection not marked child-like") != 0) {
        return 1;
    }
    if (expect_true(result.stats.person_count == 1, "adult-like detection remains counted") != 0) {
        return 1;
    }
    return 0;
}

static int test_parser_suppresses_low_score_large_box_over_child(void)
{
    elevator_parse_result result;
    float counts[] = {2.0f};
    float roi[6][8] = {
        {984.0f,  984.0f},
        {362.0f,  342.0f},
        {1322.0f, 1526.0f},
        {934.0f,  1010.0f},
        {0.248047f, 0.182617f},
        {0.0f, 0.0f},
    };
    char errbuf[256];

    if (elevator_parse_raw_outputs(counts, 1, &roi[0][0], 8, 6, 8,
            1920, 1080, 1920, 1080, 0.10f, 0.55f, ELEVATOR_EBIKE_FP_CLEANUP_FULL,
            &result, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected parser cleanup error: %s\n", errbuf);
        return 1;
    }

    if (expect_true(result.detection_count == 1, "low-score large box over child is suppressed") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].rect.x2 - result.detections[0].rect.x1 < 400U,
            "tighter child box remains after large-box suppression") != 0) {
        return 1;
    }
    if (expect_true(result.stats.person_count == 1, "public occupancy keeps only the tight child box") != 0) {
        return 1;
    }
    return 0;
}

static int test_parser_suppresses_low_score_medium_box_over_child(void)
{
    elevator_parse_result result;
    float counts[] = {2.0f};
    float roi[6][8] = {
        {1016.0f, 1016.0f},
        {420.0f,  266.0f},
        {1254.0f, 1322.0f},
        {762.0f,  762.0f},
        {0.710938f, 0.166992f},
        {0.0f, 0.0f},
    };
    char errbuf[256];

    if (elevator_parse_raw_outputs(counts, 1, &roi[0][0], 8, 6, 8,
            1920, 1080, 1920, 1080, 0.10f, 0.55f, ELEVATOR_EBIKE_FP_CLEANUP_FULL,
            &result, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected parser medium child cleanup error: %s\n", errbuf);
        return 1;
    }

    if (expect_true(result.detection_count == 1, "medium low-score box over child is suppressed") != 0) {
        return 1;
    }
    if (expect_true((result.detections[0].rect.x2 - result.detections[0].rect.x1) <= 260U,
            "tight child box remains after medium child conflict suppression") != 0) {
        return 1;
    }
    return 0;
}

static int test_parser_suppresses_partial_large_box_with_high_score_support(void)
{
    elevator_parse_result result;
    float counts[] = {2.0f};
    float roi[6][8] = {
        {950.0f, 914.0f},
        {514.0f, 514.0f},
        {1220.0f, 1390.0f},
        {838.0f, 1068.0f},
        {0.753906f, 0.119141f},
        {0.0f, 0.0f},
    };
    char errbuf[256];

    if (elevator_parse_raw_outputs(counts, 1, &roi[0][0], 8, 6, 8,
            1920, 1080, 1920, 1080, 0.10f, 0.55f, ELEVATOR_EBIKE_FP_CLEANUP_FULL,
            &result, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected parser partial large-box cleanup error: %s\n", errbuf);
        return 1;
    }

    if (expect_true(result.detection_count == 1, "partial large box with strong smaller support is suppressed") != 0) {
        return 1;
    }
    if (expect_true((result.detections[0].rect.x2 - result.detections[0].rect.x1) <= 320U,
            "smaller supported box remains after partial large-box cleanup") != 0) {
        return 1;
    }
    return 0;
}

static int test_parser_suppresses_top_right_corner_umbrella_box(void)
{
    elevator_parse_result result;
    float counts[] = {4.0f};
    float roi[6][16] = {
        {678.0f, 1084.0f, 338.0f, 1220.0f},
        {286.0f, 666.0f, 304.0f, 0.0f},
        {1052.0f, 1424.0f, 644.0f, 1918.0f},
        {914.0f, 934.0f, 934.0f, 820.0f},
        {0.902344f, 0.890625f, 0.882812f, 0.355469f},
        {0.0f, 0.0f, 0.0f, 0.0f},
    };
    char errbuf[256];
    size_t idx;

    if (elevator_parse_raw_outputs(counts, 1, &roi[0][0], 16, 6, 16,
            1920, 1080, 1920, 1080, 0.10f, 0.55f, ELEVATOR_EBIKE_FP_CLEANUP_FULL,
            &result, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected parser top-right umbrella cleanup error: %s\n", errbuf);
        return 1;
    }

    if (expect_true(result.detection_count == 3, "top-right corner umbrella person box is suppressed") != 0) {
        return 1;
    }
    if (expect_true(result.stats.person_count == 3, "public occupancy keeps only the three supported person boxes") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (expect_true(!(result.detections[idx].rect.y1 <= 8U && result.detections[idx].rect.x2 >= 1912U),
                "suppressed corner umbrella box does not survive parser cleanup") != 0) {
            return 1;
        }
    }
    return 0;
}

static int test_person_tracker_prefers_tighter_box_over_large_child_duplicate(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;

    elevator_person_tracker_reset(&tracker, 8, 800);

    memset(&result, 0, sizeof(result));
    result.detection_count = 2;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.804688f;
    result.detections[0].score_percent = 80;
    result.detections[0].rect.x1 = 950;
    result.detections[0].rect.y1 = 458;
    result.detections[0].rect.x2 = 1254;
    result.detections[0].rect.y2 = 800;
    result.detections[1].class_id = 0;
    result.detections[1].score = 0.523438f;
    result.detections[1].score_percent = 52;
    result.detections[1].rect.x1 = 950;
    result.detections[1].rect.y1 = 304;
    result.detections[1].rect.x2 = 1322;
    result.detections[1].rect.y2 = 820;
    result.stats.person_count = 2;
    elevator_person_tracker_apply(&tracker, &result, 1000, 1920, 1080);

    if (expect_true(result.detection_count == 1, "oversized child duplicate is removed in favor of tighter box") != 0) {
        return 1;
    }
    if (expect_true((result.detections[0].rect.x2 - result.detections[0].rect.x1) <= 320U,
            "remaining box stays close to the tighter child box width") != 0) {
        return 1;
    }
    if (expect_true(result.stats.person_count == 1, "duplicate cleanup preserves a single public child box") != 0) {
        return 1;
    }
    return 0;
}

static int test_person_tracker_preserves_child_box_against_one_frame_regression(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;

    elevator_person_tracker_reset(&tracker, 8, 800);

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.376953f;
    result.detections[0].score_percent = 38;
    result.detections[0].rect.x1 = 984;
    result.detections[0].rect.y1 = 362;
    result.detections[0].rect.x2 = 1254;
    result.detections[0].rect.y2 = 878;
    result.stats.person_count = 1;
    elevator_person_tracker_apply(&tracker, &result, 1000, 1920, 1080);

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.310547f;
    result.detections[0].score_percent = 31;
    result.detections[0].rect.x1 = 1016;
    result.detections[0].rect.y1 = 362;
    result.detections[0].rect.x2 = 1254;
    result.detections[0].rect.y2 = 914;
    result.stats.person_count = 1;
    elevator_person_tracker_apply(&tracker, &result, 1040, 1920, 1080);

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.211914f;
    result.detections[0].score_percent = 21;
    result.detections[0].rect.x1 = 1016;
    result.detections[0].rect.y1 = 476;
    result.detections[0].rect.x2 = 1560;
    result.detections[0].rect.y2 = 1068;
    result.stats.person_count = 1;
    elevator_person_tracker_apply(&tracker, &result, 1080, 1920, 1080);

    if (expect_true(result.detection_count == 1, "single child track remains through one-frame regression") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].child_like != 0U, "regressed frame keeps child-like state") != 0) {
        return 1;
    }
    if (expect_true((result.detections[0].rect.x2 - result.detections[0].rect.x1) < 320U,
            "regressed frame reuses tighter previous child box") != 0) {
        return 1;
    }
    return 0;
}

static int test_person_tracker_hold_carry_keeps_single_person_tail(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;

    elevator_person_tracker_reset(&tracker, 8, 800);

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.82f;
    result.detections[0].score_percent = 82;
    result.detections[0].rect.x1 = 820;
    result.detections[0].rect.y1 = 240;
    result.detections[0].rect.x2 = 1240;
    result.detections[0].rect.y2 = 860;
    result.stats.person_count = 1;
    elevator_person_tracker_apply(&tracker, &result, 1000, 1920, 1080);

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 0;
    result.detections[0].score = 0.81f;
    result.detections[0].score_percent = 81;
    result.detections[0].rect.x1 = 822;
    result.detections[0].rect.y1 = 242;
    result.detections[0].rect.x2 = 1242;
    result.detections[0].rect.y2 = 862;
    result.stats.person_count = 1;
    elevator_person_tracker_apply(&tracker, &result, 1040, 1920, 1080);

    memset(&result, 0, sizeof(result));
    result.stats.person_count = 0;
    elevator_person_tracker_apply(&tracker, &result, 1120, 1920, 1080);

    if (expect_true(result.stats.person_count == 1, "held confirmed track keeps public occupancy at 1 during short dropout") != 0) {
        return 1;
    }
    if (expect_true(result.stats.held_person_count == 1, "held person count tracks carried occupancy") != 0) {
        return 1;
    }
    return 0;
}

static int test_person_tracker_keeps_mature_track_over_fresh_overlap_reacquire(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    uint32_t mature_track_id = 0U;
    uint32_t frame_idx;

    elevator_person_tracker_reset(&tracker, 8, 800);

    for (frame_idx = 0; frame_idx < 4U; ++frame_idx) {
        memset(&result, 0, sizeof(result));
        result.detection_count = 1;
        result.detections[0].class_id = 0U;
        result.detections[0].score = 0.58f;
        result.detections[0].score_percent = 58U;
        result.detections[0].rect.x1 = 780U;
        result.detections[0].rect.y1 = 0U;
        result.detections[0].rect.x2 = 1140U;
        result.detections[0].rect.y2 = 724U;
        result.stats.person_count = 1U;
        elevator_person_tracker_apply(&tracker, &result, 1000U + (uint64_t)frame_idx * 40U, 1920U, 1080U);
    }

    mature_track_id = result.detections[0].track_id;
    if (expect_true(mature_track_id != 0U, "warmup track acquires a reusable id") != 0) {
        return 1;
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 2;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.55f;
    result.detections[0].score_percent = 55U;
    result.detections[0].rect.x1 = 772U;
    result.detections[0].rect.y1 = 0U;
    result.detections[0].rect.x2 = 1142U;
    result.detections[0].rect.y2 = 724U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.43f;
    result.detections[1].score_percent = 43U;
    result.detections[1].rect.x1 = 760U;
    result.detections[1].rect.y1 = 120U;
    result.detections[1].rect.x2 = 1090U;
    result.detections[1].rect.y2 = 820U;
    result.stats.person_count = 2U;
    elevator_person_tracker_apply(&tracker, &result, 1160U, 1920U, 1080U);

    if (expect_true(result.detection_count == 1U, "overlap cleanup still resolves to one occupant") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].track_id == mature_track_id,
            "mature confirmed track survives ambiguous overlap against a fresher box") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].track_state == ELEVATOR_TRACK_STATE_CONFIRMED,
            "surviving mature overlap track stays confirmed") != 0) {
        return 1;
    }
    return 0;
}

static int test_person_tracker_carries_mature_low_quality_neighbor_during_partial_dropout(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    uint32_t frame_idx;

    elevator_person_tracker_reset(&tracker, 8, 800);

    for (frame_idx = 0; frame_idx < 4U; ++frame_idx) {
        memset(&result, 0, sizeof(result));
        result.detection_count = 2;
        result.detections[0].class_id = 0U;
        result.detections[0].score = 0.88f;
        result.detections[0].score_percent = 88U;
        result.detections[0].rect.x1 = 240U;
        result.detections[0].rect.y1 = 220U;
        result.detections[0].rect.x2 = 520U;
        result.detections[0].rect.y2 = 920U;
        result.detections[1].class_id = 0U;
        result.detections[1].score = 0.26f;
        result.detections[1].score_percent = 26U;
        result.detections[1].rect.x1 = 780U;
        result.detections[1].rect.y1 = 0U;
        result.detections[1].rect.x2 = 1140U;
        result.detections[1].rect.y2 = 724U;
        result.stats.person_count = 2U;
        elevator_person_tracker_apply(&tracker, &result, 1000U + (uint64_t)frame_idx * 40U, 1920U, 1080U);
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.89f;
    result.detections[0].score_percent = 89U;
    result.detections[0].rect.x1 = 244U;
    result.detections[0].rect.y1 = 224U;
    result.detections[0].rect.x2 = 524U;
    result.detections[0].rect.y2 = 924U;
    result.stats.person_count = 1U;
    elevator_person_tracker_apply(&tracker, &result, 1160U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "mature low-quality neighbor still contributes to public occupancy during short dropout") != 0) {
        return 1;
    }
    if (expect_true(result.stats.held_person_count == 1U,
            "dropout still reports one held neighbor for debug") != 0) {
        return 1;
    }
    if (expect_true(result.stats.mature_confirmed_person_count == 2U,
            "mature confirmed counter reports both established occupants") != 0) {
        return 1;
    }
    if (expect_true(result.stats.mature_held_person_count == 1U,
            "mature held counter exposes the carried dropout occupant") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 1U,
            "public count reports one mature-carry contribution") != 0) {
        return 1;
    }
    if (expect_true(result.detection_count == 2U,
            "mature carry appends a public-visible held person box") != 0) {
        return 1;
    }
    if (expect_true(result.detections[1].track_state == ELEVATOR_TRACK_STATE_HELD,
            "carried mature neighbor is exposed as a held track") != 0) {
        return 1;
    }
    if (expect_true(result.detections[1].synthetic == 0U,
            "mature public carry uses a real overlay box rather than debug-only synthetic carry") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_should_render(&result.detections[1], 1920U, 1080U) != 0,
            "mature public carry box remains visible on the public overlay") != 0) {
        return 1;
    }
    return 0;
}

static int test_person_tracker_carries_robust_mature_low_score_neighbor_during_partial_dropout(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    uint32_t frame_idx;

    elevator_person_tracker_reset(&tracker, 8, 800);

    for (frame_idx = 0; frame_idx < 6U; ++frame_idx) {
        memset(&result, 0, sizeof(result));
        result.detection_count = 2U;
        result.detections[0].class_id = 0U;
        result.detections[0].score = 0.88f;
        result.detections[0].score_percent = 88U;
        result.detections[0].rect.x1 = 240U;
        result.detections[0].rect.y1 = 220U;
        result.detections[0].rect.x2 = 520U;
        result.detections[0].rect.y2 = 920U;
        result.detections[1].class_id = 0U;
        result.detections[1].score = 0.21f;
        result.detections[1].score_percent = 21U;
        result.detections[1].rect.x1 = 170U;
        result.detections[1].rect.y1 = 0U;
        result.detections[1].rect.x2 = 576U;
        result.detections[1].rect.y2 = 438U;
        result.stats.person_count = 2U;
        elevator_person_tracker_apply(&tracker, &result, 1000U + (uint64_t)frame_idx * 40U, 1920U, 1080U);
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 1U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.89f;
    result.detections[0].score_percent = 89U;
    result.detections[0].rect.x1 = 244U;
    result.detections[0].rect.y1 = 224U;
    result.detections[0].rect.x2 = 524U;
    result.detections[0].rect.y2 = 924U;
    result.stats.person_count = 1U;
    elevator_person_tracker_apply(&tracker, &result, 1240U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "robust mature low-score neighbor still contributes to public occupancy during short dropout") != 0) {
        return 1;
    }
    if (expect_true(result.stats.held_person_count == 1U,
            "robust low-score dropout still reports one held neighbor for debug") != 0) {
        return 1;
    }
    if (expect_true(result.stats.mature_confirmed_person_count == 2U,
            "robust mature confirmed counter reports both established occupants") != 0) {
        return 1;
    }
    if (expect_true(result.stats.mature_held_person_count == 1U,
            "robust mature held counter exposes the low-score carried occupant") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 1U,
            "public count reports one robust mature-carry contribution") != 0) {
        return 1;
    }
    return 0;
}

static int test_person_tracker_promotes_mature_synthetic_hold_to_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    uint32_t frame_idx;

    elevator_person_tracker_reset(&tracker, 8, 800);

    for (frame_idx = 0; frame_idx < 4U; ++frame_idx) {
        memset(&result, 0, sizeof(result));
        result.detection_count = 2U;
        result.detections[0].class_id = 0U;
        result.detections[0].score = 0.88f;
        result.detections[0].score_percent = 88U;
        result.detections[0].rect.x1 = 240U;
        result.detections[0].rect.y1 = 220U;
        result.detections[0].rect.x2 = 520U;
        result.detections[0].rect.y2 = 920U;
        result.detections[1].class_id = 0U;
        result.detections[1].score = 0.64f;
        result.detections[1].score_percent = 64U;
        result.detections[1].rect.x1 = 270U;
        result.detections[1].rect.y1 = 20U;
        result.detections[1].rect.x2 = 610U;
        result.detections[1].rect.y2 = 515U;
        result.stats.person_count = 2U;
        elevator_person_tracker_apply(&tracker, &result, 1000U + (uint64_t)frame_idx * 40U, 1920U, 1080U);
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.89f;
    result.detections[0].score_percent = 89U;
    result.detections[0].rect.x1 = 244U;
    result.detections[0].rect.y1 = 224U;
    result.detections[0].rect.x2 = 524U;
    result.detections[0].rect.y2 = 924U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.64f;
    result.detections[1].score_percent = 64U;
    result.detections[1].rect.x1 = 272U;
    result.detections[1].rect.y1 = 18U;
    result.detections[1].rect.x2 = 608U;
    result.detections[1].rect.y2 = 514U;
    result.detections[1].track_state = ELEVATOR_TRACK_STATE_HELD;
    result.detections[1].synthetic = 1U;
    result.stats.person_count = 2U;
    elevator_person_tracker_apply(&tracker, &result, 1160U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "mature synthetic hold still contributes to public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 1U,
            "mature synthetic hold is reported as public carry") != 0) {
        return 1;
    }
    if (expect_true(result.detection_count == 2U,
            "mature synthetic hold reuses the existing carried box without duplicating it") != 0) {
        return 1;
    }
    if (expect_true(result.detections[1].track_state == ELEVATOR_TRACK_STATE_HELD,
            "mature synthetic hold remains a held track") != 0) {
        return 1;
    }
    if (expect_true(result.detections[1].synthetic == 0U,
            "mature synthetic hold is promoted to a public-visible carried box") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_should_render(&result.detections[1], 1920U, 1080U) != 0,
            "promoted mature synthetic hold renders on the public overlay") != 0) {
        return 1;
    }

    return 0;
}

static int test_person_tracker_keeps_child_like_mature_synthetic_hold_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;
    elevator_detection_result *carried_hold = NULL;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 33U;
    tracker.last_public_person_count = 2U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 1120U;
    tracker.tracks[0].child_like = 1U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.644531f;
    tracker.tracks[0].detection.score_percent = 64U;
    tracker.tracks[0].detection.track_id = 1U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.child_like = 1U;
    tracker.tracks[0].detection.rect.x1 = 876U;
    tracker.tracks[0].detection.rect.y1 = 476U;
    tracker.tracks[0].detection.rect.x2 = 1090U;
    tracker.tracks[0].detection.rect.y2 = 886U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 32U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 1120U;
    tracker.tracks[1].child_like = 1U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.453125f;
    tracker.tracks[1].detection.score_percent = 45U;
    tracker.tracks[1].detection.track_id = 32U;
    tracker.tracks[1].detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    tracker.tracks[1].detection.synthetic = 1U;
    tracker.tracks[1].detection.child_like = 1U;
    tracker.tracks[1].detection.rect.x1 = 780U;
    tracker.tracks[1].detection.rect.y1 = 496U;
    tracker.tracks[1].detection.rect.x2 = 1118U;
    tracker.tracks[1].detection.rect.y2 = 1048U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.644531f;
    result.detections[0].score_percent = 64U;
    result.detections[0].rect.x1 = 876U;
    result.detections[0].rect.y1 = 476U;
    result.detections[0].rect.x2 = 1090U;
    result.detections[0].rect.y2 = 886U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.453125f;
    result.detections[1].score_percent = 45U;
    result.detections[1].rect.x1 = 780U;
    result.detections[1].rect.y1 = 496U;
    result.detections[1].rect.x2 = 1118U;
    result.detections[1].rect.y2 = 1048U;
    result.detections[1].track_state = ELEVATOR_TRACK_STATE_HELD;
    result.detections[1].synthetic = 1U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 1160U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "child-like matched mature synthetic hold still contributes to public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 1U,
            "child-like matched mature synthetic hold is reported as public carry") != 0) {
        return 1;
    }
    if (expect_true(result.detection_count == 2U,
            "child-like matched mature synthetic hold reuses the carried box without duplicating it") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].track_id == 32U) {
            carried_hold = &result.detections[idx];
            break;
        }
    }
    if (expect_true(carried_hold != NULL, "child-like matched mature synthetic hold remains addressable after apply") != 0) {
        return 1;
    }
    if (expect_true(carried_hold->synthetic == 0U,
            "child-like matched mature synthetic hold becomes public-visible instead of staying synthetic") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_should_render(carried_hold, 1920U, 1080U) != 0,
            "child-like matched mature synthetic hold renders on the public overlay") != 0) {
        return 1;
    }

    return 0;
}

static int test_person_tracker_keeps_exact_tail_child_like_matched_synthetic_hold_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    elevator_detection_result *carried_hold = NULL;
    size_t idx;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 33U;
    tracker.last_public_person_count = 2U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 30241U;
    tracker.tracks[0].child_like = 1U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.644531f;
    tracker.tracks[0].detection.score_percent = 64U;
    tracker.tracks[0].detection.track_id = 1U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.child_like = 1U;
    tracker.tracks[0].detection.rect.x1 = 876U;
    tracker.tracks[0].detection.rect.y1 = 476U;
    tracker.tracks[0].detection.rect.x2 = 1090U;
    tracker.tracks[0].detection.rect.y2 = 886U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 32U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 30241U;
    tracker.tracks[1].child_like = 1U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.453125f;
    tracker.tracks[1].detection.score_percent = 45U;
    tracker.tracks[1].detection.track_id = 32U;
    tracker.tracks[1].detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    tracker.tracks[1].detection.synthetic = 1U;
    tracker.tracks[1].detection.child_like = 1U;
    tracker.tracks[1].detection.rect.x1 = 780U;
    tracker.tracks[1].detection.rect.y1 = 496U;
    tracker.tracks[1].detection.rect.x2 = 1118U;
    tracker.tracks[1].detection.rect.y2 = 1048U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.644531f;
    result.detections[0].score_percent = 64U;
    result.detections[0].track_id = 1U;
    result.detections[0].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[0].child_like = 1U;
    result.detections[0].rect.x1 = 876U;
    result.detections[0].rect.y1 = 476U;
    result.detections[0].rect.x2 = 1090U;
    result.detections[0].rect.y2 = 886U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.453125f;
    result.detections[1].score_percent = 45U;
    result.detections[1].track_id = 32U;
    result.detections[1].track_state = ELEVATOR_TRACK_STATE_HELD;
    result.detections[1].synthetic = 1U;
    result.detections[1].child_like = 1U;
    result.detections[1].rect.x1 = 780U;
    result.detections[1].rect.y1 = 496U;
    result.detections[1].rect.x2 = 1118U;
    result.detections[1].rect.y2 = 1048U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 30281U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "exact tail child-like matched synthetic hold still contributes to public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 1U,
            "exact tail child-like matched synthetic hold is reported as public carry") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].track_id == 32U) {
            carried_hold = &result.detections[idx];
            break;
        }
    }
    if (expect_true(carried_hold != NULL, "exact tail child-like hold remains visible in detections") != 0) {
        return 1;
    }
    if (expect_true(carried_hold->synthetic == 0U,
            "exact tail child-like matched synthetic hold is promoted to public-visible carry") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_should_render(carried_hold, 1920U, 1080U) != 0,
            "exact tail child-like matched synthetic hold renders on public overlay") != 0) {
        return 1;
    }

    return 0;
}

static int test_person_tracker_keeps_tail_child_like_reconfirm_synthetic_hold_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    elevator_detection_result *carried_hold = NULL;
    size_t idx;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 32U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 30241U;
    tracker.tracks[0].child_like = 1U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.621094f;
    tracker.tracks[0].detection.score_percent = 62U;
    tracker.tracks[0].detection.track_id = 1U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.child_like = 1U;
    tracker.tracks[0].detection.rect.x1 = 866U;
    tracker.tracks[0].detection.rect.y1 = 476U;
    tracker.tracks[0].detection.rect.x2 = 1104U;
    tracker.tracks[0].detection.rect.y2 = 886U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.730469f;
    result.detections[0].score_percent = 73U;
    result.detections[0].child_like = 1U;
    result.detections[0].rect.x1 = 872U;
    result.detections[0].rect.y1 = 476U;
    result.detections[0].rect.x2 = 1096U;
    result.detections[0].rect.y2 = 882U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.453125f;
    result.detections[1].score_percent = 45U;
    result.detections[1].synthetic = 1U;
    result.detections[1].child_like = 1U;
    result.detections[1].rect.x1 = 780U;
    result.detections[1].rect.y1 = 496U;
    result.detections[1].rect.x2 = 1118U;
    result.detections[1].rect.y2 = 1048U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 30265U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 1U,
            "first tail reconfirm frame still keeps the synthetic child-like hold out of public count") != 0) {
        return 1;
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.644531f;
    result.detections[0].score_percent = 64U;
    result.detections[0].child_like = 1U;
    result.detections[0].rect.x1 = 876U;
    result.detections[0].rect.y1 = 476U;
    result.detections[0].rect.x2 = 1090U;
    result.detections[0].rect.y2 = 886U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.453125f;
    result.detections[1].score_percent = 45U;
    result.detections[1].synthetic = 1U;
    result.detections[1].child_like = 1U;
    result.detections[1].rect.x1 = 780U;
    result.detections[1].rect.y1 = 496U;
    result.detections[1].rect.x2 = 1118U;
    result.detections[1].rect.y2 = 1048U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 30281U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "tail child-like synthetic hold should count once it reconfirms on the next frame") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 1U,
            "tail child-like synthetic hold reconfirm should be reported as public carry") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].track_id == 32U) {
            carried_hold = &result.detections[idx];
            break;
        }
    }
    if (expect_true(carried_hold != NULL, "tail child-like reconfirm hold remains visible in detections") != 0) {
        return 1;
    }
    if (expect_true(carried_hold->synthetic == 0U,
            "tail child-like reconfirm hold becomes public-visible on the second frame") != 0) {
        return 1;
    }

    return 0;
}

static int test_person_tracker_skips_duplicate_mature_synthetic_hold_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;
    elevator_detection_result *duplicate_hold = NULL;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 4U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 1120U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.89f;
    tracker.tracks[0].detection.score_percent = 89U;
    tracker.tracks[0].detection.track_id = 1U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.rect.x1 = 1220U;
    tracker.tracks[0].detection.rect.y1 = 350U;
    tracker.tracks[0].detection.rect.x2 = 1726U;
    tracker.tracks[0].detection.rect.y2 = 1074U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 2U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 1120U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.35f;
    tracker.tracks[1].detection.score_percent = 35U;
    tracker.tracks[1].detection.rect.x1 = 746U;
    tracker.tracks[1].detection.rect.y1 = 0U;
    tracker.tracks[1].detection.rect.x2 = 1016U;
    tracker.tracks[1].detection.rect.y2 = 704U;

    tracker.tracks[2].active = 1U;
    tracker.tracks[2].track_id = 3U;
    tracker.tracks[2].hits = 6U;
    tracker.tracks[2].last_timestamp_ms = 1120U;
    tracker.tracks[2].detection.class_id = 0U;
    tracker.tracks[2].detection.score = 0.27f;
    tracker.tracks[2].detection.score_percent = 27U;
    tracker.tracks[2].detection.rect.x1 = 746U;
    tracker.tracks[2].detection.rect.y1 = 0U;
    tracker.tracks[2].detection.rect.x2 = 950U;
    tracker.tracks[2].detection.rect.y2 = 686U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 3U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.90f;
    result.detections[0].score_percent = 90U;
    result.detections[0].rect.x1 = 1220U;
    result.detections[0].rect.y1 = 352U;
    result.detections[0].rect.x2 = 1726U;
    result.detections[0].rect.y2 = 1074U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.36f;
    result.detections[1].score_percent = 36U;
    result.detections[1].rect.x1 = 746U;
    result.detections[1].rect.y1 = 0U;
    result.detections[1].rect.x2 = 1016U;
    result.detections[1].rect.y2 = 704U;
    result.detections[2].class_id = 0U;
    result.detections[2].score = 0.27f;
    result.detections[2].score_percent = 27U;
    result.detections[2].rect.x1 = 746U;
    result.detections[2].rect.y1 = 0U;
    result.detections[2].rect.x2 = 950U;
    result.detections[2].rect.y2 = 686U;
    result.detections[2].track_state = ELEVATOR_TRACK_STATE_HELD;
    result.detections[2].synthetic = 1U;
    result.stats.person_count = 3U;

    elevator_person_tracker_apply(&tracker, &result, 1160U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "duplicate synthetic hold does not inflate public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 0U,
            "duplicate synthetic hold is not reported as public carry") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].track_id == 3U) {
            duplicate_hold = &result.detections[idx];
            break;
        }
    }
    if (expect_true(duplicate_hold != NULL, "duplicate synthetic hold remains present for debug review") != 0) {
        return 1;
    }
    if (expect_true(duplicate_hold->synthetic != 0U,
            "duplicate synthetic hold stays synthetic when it overlaps a visible confirmed track") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_should_render(duplicate_hold, 1920U, 1080U) == 0,
            "duplicate synthetic hold stays off the public overlay") != 0) {
        return 1;
    }

    return 0;
}

static int test_person_tracker_keeps_overlapping_unmatched_mature_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;
    elevator_detection_result *carried_hold = NULL;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 4U;
    tracker.last_public_person_count = 3U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 1120U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.89f;
    tracker.tracks[0].detection.score_percent = 89U;
    tracker.tracks[0].detection.rect.x1 = 1220U;
    tracker.tracks[0].detection.rect.y1 = 350U;
    tracker.tracks[0].detection.rect.x2 = 1726U;
    tracker.tracks[0].detection.rect.y2 = 1074U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 2U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 1120U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.80f;
    tracker.tracks[1].detection.score_percent = 80U;
    tracker.tracks[1].detection.track_id = 2U;
    tracker.tracks[1].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[1].detection.rect.x1 = 814U;
    tracker.tracks[1].detection.rect.y1 = 0U;
    tracker.tracks[1].detection.rect.x2 = 1186U;
    tracker.tracks[1].detection.rect.y2 = 724U;

    tracker.tracks[2].active = 1U;
    tracker.tracks[2].track_id = 3U;
    tracker.tracks[2].hits = 6U;
    tracker.tracks[2].last_timestamp_ms = 1120U;
    tracker.tracks[2].detection.class_id = 0U;
    tracker.tracks[2].detection.score = 0.27f;
    tracker.tracks[2].detection.score_percent = 27U;
    tracker.tracks[2].detection.track_id = 3U;
    tracker.tracks[2].detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    tracker.tracks[2].detection.rect.x1 = 780U;
    tracker.tracks[2].detection.rect.y1 = 0U;
    tracker.tracks[2].detection.rect.x2 = 1016U;
    tracker.tracks[2].detection.rect.y2 = 666U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.90f;
    result.detections[0].score_percent = 90U;
    result.detections[0].rect.x1 = 1220U;
    result.detections[0].rect.y1 = 352U;
    result.detections[0].rect.x2 = 1726U;
    result.detections[0].rect.y2 = 1074U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.81f;
    result.detections[1].score_percent = 81U;
    result.detections[1].rect.x1 = 814U;
    result.detections[1].rect.y1 = 0U;
    result.detections[1].rect.x2 = 1186U;
    result.detections[1].rect.y2 = 724U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 1160U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 3U,
            "overlapping unmatched mature carry still contributes to public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 1U,
            "overlapping unmatched mature carry is reported as one public carry") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].track_id == 3U) {
            carried_hold = &result.detections[idx];
            break;
        }
    }
    if (expect_true(carried_hold != NULL, "overlapping unmatched mature carry appends a held public box") != 0) {
        return 1;
    }
    if (expect_true(carried_hold->synthetic == 0U,
            "overlapping unmatched mature carry uses a public-visible held box") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_should_render(carried_hold, 1920U, 1080U) != 0,
            "overlapping unmatched mature carry remains visible on the public overlay") != 0) {
        return 1;
    }

    return 0;
}

static int test_person_tracker_skips_near_identical_unmatched_mature_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 4U;
    tracker.last_public_person_count = 3U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 1120U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.89f;
    tracker.tracks[0].detection.score_percent = 89U;
    tracker.tracks[0].detection.track_id = 1U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.rect.x1 = 1220U;
    tracker.tracks[0].detection.rect.y1 = 350U;
    tracker.tracks[0].detection.rect.x2 = 1726U;
    tracker.tracks[0].detection.rect.y2 = 1074U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 2U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 1120U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.71f;
    tracker.tracks[1].detection.score_percent = 71U;
    tracker.tracks[1].detection.track_id = 2U;
    tracker.tracks[1].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[1].detection.rect.x1 = 914U;
    tracker.tracks[1].detection.rect.y1 = 0U;
    tracker.tracks[1].detection.rect.x2 = 1186U;
    tracker.tracks[1].detection.rect.y2 = 724U;

    tracker.tracks[2].active = 1U;
    tracker.tracks[2].track_id = 3U;
    tracker.tracks[2].hits = 6U;
    tracker.tracks[2].last_timestamp_ms = 1120U;
    tracker.tracks[2].detection.class_id = 0U;
    tracker.tracks[2].detection.score = 0.60f;
    tracker.tracks[2].detection.score_percent = 60U;
    tracker.tracks[2].detection.track_id = 3U;
    tracker.tracks[2].detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    tracker.tracks[2].detection.rect.x1 = 950U;
    tracker.tracks[2].detection.rect.y1 = 0U;
    tracker.tracks[2].detection.rect.x2 = 1186U;
    tracker.tracks[2].detection.rect.y2 = 724U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.90f;
    result.detections[0].score_percent = 90U;
    result.detections[0].track_id = 1U;
    result.detections[0].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[0].rect.x1 = 1220U;
    result.detections[0].rect.y1 = 352U;
    result.detections[0].rect.x2 = 1726U;
    result.detections[0].rect.y2 = 1074U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.72f;
    result.detections[1].score_percent = 72U;
    result.detections[1].track_id = 2U;
    result.detections[1].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[1].rect.x1 = 914U;
    result.detections[1].rect.y1 = 0U;
    result.detections[1].rect.x2 = 1186U;
    result.detections[1].rect.y2 = 724U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 1160U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "near-identical unmatched mature carry does not inflate public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 0U,
            "near-identical unmatched mature carry is not reported as public carry") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].track_id == 3U) {
            fprintf(stderr, "unexpected near-identical unmatched carry track in public output at index %zu\n", idx);
            return 1;
        }
    }

    return 0;
}

static int test_person_tracker_keeps_offset_nested_unmatched_mature_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;
    elevator_detection_result *carried_hold = NULL;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 4U;
    tracker.last_public_person_count = 6U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 1120U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.89f;
    tracker.tracks[0].detection.score_percent = 89U;
    tracker.tracks[0].detection.track_id = 1U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.rect.x1 = 1220U;
    tracker.tracks[0].detection.rect.y1 = 350U;
    tracker.tracks[0].detection.rect.x2 = 1726U;
    tracker.tracks[0].detection.rect.y2 = 1074U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 2U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 1120U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.83f;
    tracker.tracks[1].detection.score_percent = 83U;
    tracker.tracks[1].detection.track_id = 2U;
    tracker.tracks[1].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[1].detection.rect.x1 = 780U;
    tracker.tracks[1].detection.rect.y1 = 18U;
    tracker.tracks[1].detection.rect.x2 = 1152U;
    tracker.tracks[1].detection.rect.y2 = 742U;

    tracker.tracks[2].active = 1U;
    tracker.tracks[2].track_id = 3U;
    tracker.tracks[2].hits = 6U;
    tracker.tracks[2].last_timestamp_ms = 1120U;
    tracker.tracks[2].detection.class_id = 0U;
    tracker.tracks[2].detection.score = 0.55f;
    tracker.tracks[2].detection.score_percent = 55U;
    tracker.tracks[2].detection.track_id = 3U;
    tracker.tracks[2].detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    tracker.tracks[2].detection.rect.x1 = 780U;
    tracker.tracks[2].detection.rect.y1 = 0U;
    tracker.tracks[2].detection.rect.x2 = 984U;
    tracker.tracks[2].detection.rect.y2 = 742U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.90f;
    result.detections[0].score_percent = 90U;
    result.detections[0].track_id = 1U;
    result.detections[0].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[0].rect.x1 = 1220U;
    result.detections[0].rect.y1 = 352U;
    result.detections[0].rect.x2 = 1726U;
    result.detections[0].rect.y2 = 1074U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.84f;
    result.detections[1].score_percent = 84U;
    result.detections[1].track_id = 2U;
    result.detections[1].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[1].rect.x1 = 780U;
    result.detections[1].rect.y1 = 18U;
    result.detections[1].rect.x2 = 1152U;
    result.detections[1].rect.y2 = 742U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 1160U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 3U,
            "offset nested unmatched mature carry still contributes to public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 1U,
            "offset nested unmatched mature carry is reported as one public carry") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].track_id == 3U) {
            carried_hold = &result.detections[idx];
            break;
        }
    }
    if (expect_true(carried_hold != NULL, "offset nested unmatched carry appends a held public box") != 0) {
        return 1;
    }
    if (expect_true(carried_hold->synthetic == 0U,
            "offset nested unmatched carry remains public-visible rather than synthetic") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_should_render(carried_hold, 1920U, 1080U) != 0,
            "offset nested unmatched carry stays visible on the public overlay") != 0) {
        return 1;
    }

    return 0;
}

static int test_person_tracker_skips_top_edge_contained_unmatched_mature_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 15U;
    tracker.last_public_person_count = 3U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 5520U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.83f;
    tracker.tracks[0].detection.score_percent = 83U;
    tracker.tracks[0].detection.track_id = 1U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.rect.x1 = 1250U;
    tracker.tracks[0].detection.rect.y1 = 234U;
    tracker.tracks[0].detection.rect.x2 = 1656U;
    tracker.tracks[0].detection.rect.y2 = 1036U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 4U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 5520U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.69f;
    tracker.tracks[1].detection.score_percent = 69U;
    tracker.tracks[1].detection.track_id = 4U;
    tracker.tracks[1].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[1].detection.rect.x1 = 710U;
    tracker.tracks[1].detection.rect.y1 = 0U;
    tracker.tracks[1].detection.rect.x2 = 1220U;
    tracker.tracks[1].detection.rect.y2 = 704U;

    tracker.tracks[2].active = 1U;
    tracker.tracks[2].track_id = 14U;
    tracker.tracks[2].hits = 6U;
    tracker.tracks[2].last_timestamp_ms = 5520U;
    tracker.tracks[2].detection.class_id = 0U;
    tracker.tracks[2].detection.score = 0.57f;
    tracker.tracks[2].detection.score_percent = 57U;
    tracker.tracks[2].detection.track_id = 14U;
    tracker.tracks[2].detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    tracker.tracks[2].detection.rect.x1 = 950U;
    tracker.tracks[2].detection.rect.y1 = 18U;
    tracker.tracks[2].detection.rect.x2 = 1220U;
    tracker.tracks[2].detection.rect.y2 = 704U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.83f;
    result.detections[0].score_percent = 83U;
    result.detections[0].track_id = 1U;
    result.detections[0].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[0].rect.x1 = 1250U;
    result.detections[0].rect.y1 = 234U;
    result.detections[0].rect.x2 = 1656U;
    result.detections[0].rect.y2 = 1036U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.69f;
    result.detections[1].score_percent = 69U;
    result.detections[1].track_id = 4U;
    result.detections[1].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[1].rect.x1 = 710U;
    result.detections[1].rect.y1 = 0U;
    result.detections[1].rect.x2 = 1220U;
    result.detections[1].rect.y2 = 704U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 5632U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "top-edge-contained unmatched mature carry does not inflate public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 0U,
            "top-edge-contained unmatched mature carry is not reported as public carry") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].track_id == 14U) {
            fprintf(stderr,
                "unexpected top-edge-contained unmatched carry track in public output at index %zu\n", idx);
            return 1;
        }
    }

    return 0;
}

static int test_person_tracker_skips_top_edge_aligned_unmatched_mature_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 8U;
    tracker.last_public_person_count = 3U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 3720U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.87f;
    tracker.tracks[0].detection.score_percent = 87U;
    tracker.tracks[0].detection.track_id = 1U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.rect.x1 = 1052U;
    tracker.tracks[0].detection.rect.y1 = 154U;
    tracker.tracks[0].detection.rect.x2 = 1390U;
    tracker.tracks[0].detection.rect.y2 = 1010U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 4U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 3720U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.69f;
    tracker.tracks[1].detection.score_percent = 69U;
    tracker.tracks[1].detection.track_id = 4U;
    tracker.tracks[1].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[1].detection.rect.x1 = 678U;
    tracker.tracks[1].detection.rect.y1 = 0U;
    tracker.tracks[1].detection.rect.x2 = 1052U;
    tracker.tracks[1].detection.rect.y2 = 782U;

    tracker.tracks[2].active = 1U;
    tracker.tracks[2].track_id = 7U;
    tracker.tracks[2].hits = 6U;
    tracker.tracks[2].last_timestamp_ms = 3720U;
    tracker.tracks[2].detection.class_id = 0U;
    tracker.tracks[2].detection.score = 0.80f;
    tracker.tracks[2].detection.score_percent = 80U;
    tracker.tracks[2].detection.track_id = 7U;
    tracker.tracks[2].detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    tracker.tracks[2].detection.rect.x1 = 644U;
    tracker.tracks[2].detection.rect.y1 = 0U;
    tracker.tracks[2].detection.rect.x2 = 1016U;
    tracker.tracks[2].detection.rect.y2 = 838U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.87f;
    result.detections[0].score_percent = 87U;
    result.detections[0].track_id = 1U;
    result.detections[0].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[0].rect.x1 = 1052U;
    result.detections[0].rect.y1 = 154U;
    result.detections[0].rect.x2 = 1390U;
    result.detections[0].rect.y2 = 1010U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.69f;
    result.detections[1].score_percent = 69U;
    result.detections[1].track_id = 4U;
    result.detections[1].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[1].rect.x1 = 678U;
    result.detections[1].rect.y1 = 0U;
    result.detections[1].rect.x2 = 1052U;
    result.detections[1].rect.y2 = 782U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 3761U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "top-edge-aligned unmatched mature carry does not inflate public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 0U,
            "top-edge-aligned unmatched mature carry is not reported as public carry") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].track_id == 7U) {
            fprintf(stderr,
                "unexpected top-edge-aligned unmatched carry track in public output at index %zu\n", idx);
            return 1;
        }
    }

    return 0;
}

static int test_person_tracker_skips_near_top_aligned_unmatched_mature_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 8U;
    tracker.last_public_person_count = 3U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 3760U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.86f;
    tracker.tracks[0].detection.score_percent = 86U;
    tracker.tracks[0].detection.track_id = 1U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.rect.x1 = 1052U;
    tracker.tracks[0].detection.rect.y1 = 150U;
    tracker.tracks[0].detection.rect.x2 = 1384U;
    tracker.tracks[0].detection.rect.y2 = 1004U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 4U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 3760U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.67f;
    tracker.tracks[1].detection.score_percent = 67U;
    tracker.tracks[1].detection.track_id = 4U;
    tracker.tracks[1].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[1].detection.rect.x1 = 678U;
    tracker.tracks[1].detection.rect.y1 = 38U;
    tracker.tracks[1].detection.rect.x2 = 1052U;
    tracker.tracks[1].detection.rect.y2 = 800U;

    tracker.tracks[2].active = 1U;
    tracker.tracks[2].track_id = 7U;
    tracker.tracks[2].hits = 6U;
    tracker.tracks[2].last_timestamp_ms = 3760U;
    tracker.tracks[2].detection.class_id = 0U;
    tracker.tracks[2].detection.score = 0.80f;
    tracker.tracks[2].detection.score_percent = 80U;
    tracker.tracks[2].detection.track_id = 7U;
    tracker.tracks[2].detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    tracker.tracks[2].detection.rect.x1 = 644U;
    tracker.tracks[2].detection.rect.y1 = 0U;
    tracker.tracks[2].detection.rect.x2 = 1016U;
    tracker.tracks[2].detection.rect.y2 = 838U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.86f;
    result.detections[0].score_percent = 86U;
    result.detections[0].track_id = 1U;
    result.detections[0].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[0].rect.x1 = 1052U;
    result.detections[0].rect.y1 = 150U;
    result.detections[0].rect.x2 = 1384U;
    result.detections[0].rect.y2 = 1004U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.67f;
    result.detections[1].score_percent = 67U;
    result.detections[1].track_id = 4U;
    result.detections[1].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[1].rect.x1 = 678U;
    result.detections[1].rect.y1 = 38U;
    result.detections[1].rect.x2 = 1052U;
    result.detections[1].rect.y2 = 800U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 3761U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "near-top aligned unmatched mature carry does not inflate public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 0U,
            "near-top aligned unmatched mature carry is not reported as public carry") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].track_id == 7U) {
            fprintf(stderr,
                "unexpected near-top aligned unmatched carry track in public output at index %zu\n", idx);
            return 1;
        }
    }

    return 0;
}

static int test_person_tracker_skips_upper_fragment_unmatched_mature_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 10U;
    tracker.last_public_person_count = 3U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 3760U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.86f;
    tracker.tracks[0].detection.score_percent = 86U;
    tracker.tracks[0].detection.track_id = 1U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.rect.x1 = 1052U;
    tracker.tracks[0].detection.rect.y1 = 150U;
    tracker.tracks[0].detection.rect.x2 = 1384U;
    tracker.tracks[0].detection.rect.y2 = 1004U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 6U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 3760U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.82f;
    tracker.tracks[1].detection.score_percent = 82U;
    tracker.tracks[1].detection.track_id = 6U;
    tracker.tracks[1].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[1].detection.rect.x1 = 468U;
    tracker.tracks[1].detection.rect.y1 = 214U;
    tracker.tracks[1].detection.rect.x2 = 818U;
    tracker.tracks[1].detection.rect.y2 = 924U;

    tracker.tracks[2].active = 1U;
    tracker.tracks[2].track_id = 9U;
    tracker.tracks[2].hits = 6U;
    tracker.tracks[2].last_timestamp_ms = 3760U;
    tracker.tracks[2].detection.class_id = 0U;
    tracker.tracks[2].detection.score = 0.38f;
    tracker.tracks[2].detection.score_percent = 38U;
    tracker.tracks[2].detection.track_id = 9U;
    tracker.tracks[2].detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    tracker.tracks[2].detection.rect.x1 = 440U;
    tracker.tracks[2].detection.rect.y1 = 208U;
    tracker.tracks[2].detection.rect.x2 = 746U;
    tracker.tracks[2].detection.rect.y2 = 534U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.86f;
    result.detections[0].score_percent = 86U;
    result.detections[0].track_id = 1U;
    result.detections[0].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[0].rect.x1 = 1052U;
    result.detections[0].rect.y1 = 150U;
    result.detections[0].rect.x2 = 1384U;
    result.detections[0].rect.y2 = 1004U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.82f;
    result.detections[1].score_percent = 82U;
    result.detections[1].track_id = 6U;
    result.detections[1].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[1].rect.x1 = 468U;
    result.detections[1].rect.y1 = 214U;
    result.detections[1].rect.x2 = 818U;
    result.detections[1].rect.y2 = 924U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 3761U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "upper-fragment unmatched mature carry does not inflate public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 0U,
            "upper-fragment unmatched mature carry is not reported as public carry") != 0) {
        return 1;
    }
    for (idx = 0; idx < result.detection_count; ++idx) {
        if (result.detections[idx].track_id == 9U) {
            fprintf(stderr,
                "unexpected upper-fragment unmatched carry track in public output at index %zu\n", idx);
            return 1;
        }
    }

    return 0;
}

static int test_person_tracker_caps_public_carry_to_last_visible_count(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;

    elevator_person_tracker_reset(&tracker, 8, 800);
    tracker.next_track_id = 4U;
    tracker.last_public_person_count = 2U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 1U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 1120U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.89f;
    tracker.tracks[0].detection.score_percent = 89U;
    tracker.tracks[0].detection.track_id = 1U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.rect.x1 = 1220U;
    tracker.tracks[0].detection.rect.y1 = 350U;
    tracker.tracks[0].detection.rect.x2 = 1726U;
    tracker.tracks[0].detection.rect.y2 = 1074U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 2U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 1120U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.64f;
    tracker.tracks[1].detection.score_percent = 64U;
    tracker.tracks[1].detection.track_id = 2U;
    tracker.tracks[1].detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    tracker.tracks[1].detection.rect.x1 = 272U;
    tracker.tracks[1].detection.rect.y1 = 18U;
    tracker.tracks[1].detection.rect.x2 = 608U;
    tracker.tracks[1].detection.rect.y2 = 514U;

    tracker.tracks[2].active = 1U;
    tracker.tracks[2].track_id = 3U;
    tracker.tracks[2].hits = 6U;
    tracker.tracks[2].last_timestamp_ms = 1120U;
    tracker.tracks[2].detection.class_id = 0U;
    tracker.tracks[2].detection.score = 0.62f;
    tracker.tracks[2].detection.score_percent = 62U;
    tracker.tracks[2].detection.track_id = 3U;
    tracker.tracks[2].detection.track_state = ELEVATOR_TRACK_STATE_HELD;
    tracker.tracks[2].detection.rect.x1 = 746U;
    tracker.tracks[2].detection.rect.y1 = 0U;
    tracker.tracks[2].detection.rect.x2 = 950U;
    tracker.tracks[2].detection.rect.y2 = 686U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 1U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.90f;
    result.detections[0].score_percent = 90U;
    result.detections[0].rect.x1 = 1220U;
    result.detections[0].rect.y1 = 352U;
    result.detections[0].rect.x2 = 1726U;
    result.detections[0].rect.y2 = 1074U;
    result.stats.person_count = 1U;

    elevator_person_tracker_apply(&tracker, &result, 1160U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "public carry does not raise occupancy above the last visible count during dropout") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 1U,
            "only one mature carry is emitted when last visible count is two") != 0) {
        return 1;
    }

    return 0;
}

static int test_person_tracker_keeps_top_edge_reacquire_public_carry_eligible(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    uint32_t frame_idx;

    elevator_person_tracker_reset(&tracker, 8, 800);

    for (frame_idx = 0; frame_idx < 6U; ++frame_idx) {
        memset(&result, 0, sizeof(result));
        result.detection_count = 2U;
        result.detections[0].class_id = 0U;
        result.detections[0].score = 0.88f;
        result.detections[0].score_percent = 88U;
        result.detections[0].rect.x1 = 1220U;
        result.detections[0].rect.y1 = 360U;
        result.detections[0].rect.x2 = 1726U;
        result.detections[0].rect.y2 = 1074U;
        result.detections[1].class_id = 0U;
        result.detections[1].score = 0.25f;
        result.detections[1].score_percent = 25U;
        result.detections[1].rect.x1 = 420U;
        result.detections[1].rect.y1 = 56U;
        result.detections[1].rect.x2 = 672U;
        result.detections[1].rect.y2 = 420U;
        result.stats.person_count = 2U;
        elevator_person_tracker_apply(&tracker, &result, 1000U + (uint64_t)frame_idx * 40U, 1920U, 1080U);
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.88f;
    result.detections[0].score_percent = 88U;
    result.detections[0].rect.x1 = 1220U;
    result.detections[0].rect.y1 = 360U;
    result.detections[0].rect.x2 = 1726U;
    result.detections[0].rect.y2 = 1074U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.21f;
    result.detections[1].score_percent = 21U;
    result.detections[1].rect.x1 = 170U;
    result.detections[1].rect.y1 = 0U;
    result.detections[1].rect.x2 = 576U;
    result.detections[1].rect.y2 = 438U;
    result.stats.person_count = 2U;
    elevator_person_tracker_apply(&tracker, &result, 1240U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "top-edge mature reacquire remains countable before dropout") != 0) {
        return 1;
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 1U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.89f;
    result.detections[0].score_percent = 89U;
    result.detections[0].rect.x1 = 1220U;
    result.detections[0].rect.y1 = 360U;
    result.detections[0].rect.x2 = 1726U;
    result.detections[0].rect.y2 = 1074U;
    result.stats.person_count = 1U;
    elevator_person_tracker_apply(&tracker, &result, 1280U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "top-edge mature reacquire remains public-carry eligible during the next short dropout") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 1U,
            "top-edge mature reacquire contributes one public carry after dropout") != 0) {
        return 1;
    }

    return 0;
}

static int test_person_tracker_does_not_carry_low_quality_stale_false_track(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;
    static const elevator_rect good_rects[3] = {
        {320, 300, 620, 930},
        {680, 280, 1020, 920},
        {1080, 650, 1420, 935},
    };

    elevator_person_tracker_reset(&tracker, 8, 800);

    memset(&result, 0, sizeof(result));
    result.detection_count = 4;
    for (idx = 0; idx < 3; ++idx) {
        result.detections[idx].class_id = 0;
        result.detections[idx].score = 0.88f;
        result.detections[idx].score_percent = 88;
        result.detections[idx].rect = good_rects[idx];
    }
    result.detections[3].class_id = 0;
    result.detections[3].score = 0.35f;
    result.detections[3].score_percent = 35;
    result.detections[3].rect.x1 = 1220;
    result.detections[3].rect.y1 = 0;
    result.detections[3].rect.x2 = 1918;
    result.detections[3].rect.y2 = 820;
    result.stats.person_count = 4;
    elevator_person_tracker_apply(&tracker, &result, 1000, 1920, 1080);

    memset(&result, 0, sizeof(result));
    result.detection_count = 4;
    for (idx = 0; idx < 3; ++idx) {
        result.detections[idx].class_id = 0;
        result.detections[idx].score = 0.89f;
        result.detections[idx].score_percent = 89;
        result.detections[idx].rect = good_rects[idx];
    }
    result.detections[3].class_id = 0;
    result.detections[3].score = 0.36f;
    result.detections[3].score_percent = 36;
    result.detections[3].rect.x1 = 1220;
    result.detections[3].rect.y1 = 0;
    result.detections[3].rect.x2 = 1918;
    result.detections[3].rect.y2 = 820;
    result.stats.person_count = 4;
    elevator_person_tracker_apply(&tracker, &result, 1040, 1920, 1080);

    memset(&result, 0, sizeof(result));
    result.detection_count = 3;
    for (idx = 0; idx < 3; ++idx) {
        result.detections[idx].class_id = 0;
        result.detections[idx].score = 0.90f;
        result.detections[idx].score_percent = 90;
        result.detections[idx].rect = good_rects[idx];
    }
    result.stats.person_count = 3;
    elevator_person_tracker_apply(&tracker, &result, 1080, 1920, 1080);

    if (expect_true(result.stats.person_count == 3, "low-quality stale track does not inflate public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.held_person_count == 1, "held counter still reports the stale track for debug") != 0) {
        return 1;
    }
    return 0;
}

static int test_person_tracker_does_not_carry_mature_low_quality_stale_false_track(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;
    size_t idx;
    uint32_t frame_idx;
    static const elevator_rect good_rects[3] = {
        {320, 300, 620, 930},
        {680, 280, 1020, 920},
        {1080, 650, 1420, 935},
    };

    elevator_person_tracker_reset(&tracker, 8, 800);

    for (frame_idx = 0; frame_idx < 4U; ++frame_idx) {
        memset(&result, 0, sizeof(result));
        result.detection_count = 4;
        for (idx = 0; idx < 3; ++idx) {
            result.detections[idx].class_id = 0U;
            result.detections[idx].score = 0.88f;
            result.detections[idx].score_percent = 88U;
            result.detections[idx].rect = good_rects[idx];
        }
        result.detections[3].class_id = 0U;
        result.detections[3].score = 0.35f;
        result.detections[3].score_percent = 35U;
        result.detections[3].rect.x1 = 1220U;
        result.detections[3].rect.y1 = 0U;
        result.detections[3].rect.x2 = 1918U;
        result.detections[3].rect.y2 = 820U;
        result.stats.person_count = 4U;
        elevator_person_tracker_apply(&tracker, &result, 1000U + (uint64_t)frame_idx * 40U, 1920U, 1080U);
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 3;
    for (idx = 0; idx < 3; ++idx) {
        result.detections[idx].class_id = 0U;
        result.detections[idx].score = 0.90f;
        result.detections[idx].score_percent = 90U;
        result.detections[idx].rect = good_rects[idx];
    }
    result.stats.person_count = 3U;
    elevator_person_tracker_apply(&tracker, &result, 1160U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 3U,
            "mature stale false track still does not inflate public occupancy") != 0) {
        return 1;
    }
    if (expect_true(result.stats.held_person_count == 1U,
            "mature stale false track remains visible only in held debug counters") != 0) {
        return 1;
    }
    if (expect_true(result.stats.mature_held_person_count == 0U,
            "mature held counter excludes stale false-track carry candidates") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 0U,
            "no mature carry contribution is emitted for stale false tracks") != 0) {
        return 1;
    }
    return 0;
}

static int test_person_tracker_skips_tail_lower_fragment_stale_public_carry(void)
{
    elevator_person_tracker tracker;
    elevator_parse_result result;

    elevator_person_tracker_reset(&tracker, 8U, 800U);
    tracker.next_track_id = 37U;
    tracker.last_public_person_count = 3U;

    tracker.tracks[0].active = 1U;
    tracker.tracks[0].track_id = 33U;
    tracker.tracks[0].hits = 6U;
    tracker.tracks[0].last_timestamp_ms = 31615U;
    tracker.tracks[0].detection.class_id = 0U;
    tracker.tracks[0].detection.score = 0.933594f;
    tracker.tracks[0].detection.score_percent = 93U;
    tracker.tracks[0].detection.track_id = 33U;
    tracker.tracks[0].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[0].detection.rect.x1 = 440U;
    tracker.tracks[0].detection.rect.y1 = 0U;
    tracker.tracks[0].detection.rect.x2 = 950U;
    tracker.tracks[0].detection.rect.y2 = 704U;

    tracker.tracks[1].active = 1U;
    tracker.tracks[1].track_id = 1U;
    tracker.tracks[1].hits = 6U;
    tracker.tracks[1].last_timestamp_ms = 31615U;
    tracker.tracks[1].child_like = 1U;
    tracker.tracks[1].detection.class_id = 0U;
    tracker.tracks[1].detection.score = 0.211914f;
    tracker.tracks[1].detection.score_percent = 21U;
    tracker.tracks[1].detection.track_id = 1U;
    tracker.tracks[1].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[1].detection.child_like = 1U;
    tracker.tracks[1].detection.rect.x1 = 850U;
    tracker.tracks[1].detection.rect.y1 = 488U;
    tracker.tracks[1].detection.rect.x2 = 1160U;
    tracker.tracks[1].detection.rect.y2 = 958U;

    tracker.tracks[2].active = 1U;
    tracker.tracks[2].track_id = 36U;
    tracker.tracks[2].hits = 6U;
    tracker.tracks[2].last_timestamp_ms = 31615U;
    tracker.tracks[2].detection.class_id = 0U;
    tracker.tracks[2].detection.score = 0.546875f;
    tracker.tracks[2].detection.score_percent = 55U;
    tracker.tracks[2].detection.track_id = 36U;
    tracker.tracks[2].detection.track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    tracker.tracks[2].detection.rect.x1 = 814U;
    tracker.tracks[2].detection.rect.y1 = 728U;
    tracker.tracks[2].detection.rect.x2 = 1324U;
    tracker.tracks[2].detection.rect.y2 = 1078U;

    memset(&result, 0, sizeof(result));
    result.detection_count = 2U;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.902344f;
    result.detections[0].score_percent = 90U;
    result.detections[0].track_id = 33U;
    result.detections[0].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[0].rect.x1 = 440U;
    result.detections[0].rect.y1 = 0U;
    result.detections[0].rect.x2 = 984U;
    result.detections[0].rect.y2 = 704U;
    result.detections[1].class_id = 0U;
    result.detections[1].score = 0.404297f;
    result.detections[1].score_percent = 40U;
    result.detections[1].track_id = 1U;
    result.detections[1].track_state = ELEVATOR_TRACK_STATE_CONFIRMED;
    result.detections[1].child_like = 1U;
    result.detections[1].rect.x1 = 822U;
    result.detections[1].rect.y1 = 460U;
    result.detections[1].rect.x2 = 1156U;
    result.detections[1].rect.y2 = 954U;
    result.stats.person_count = 2U;

    elevator_person_tracker_apply(&tracker, &result, 31648U, 1920U, 1080U);

    if (expect_true(result.stats.person_count == 2U,
            "tail lower-fragment stale hold must not inflate public occupancy back to three") != 0) {
        return 1;
    }
    if (expect_true(result.stats.public_person_count_from_mature_carry == 0U,
            "tail lower-fragment stale hold must not be reported as mature public carry") != 0) {
        return 1;
    }

    return 0;
}

static int test_parser_applies_ebike_false_positive_cleanup(void)
{
    float counts[] = {5.0f};
    float roi[6][8] = {
        {510.0f, 608.0f, 644.0f, 678.0f, 914.0f},
        {286.0f, 266.0f,   0.0f, 362.0f, 496.0f},
        {1118.0f, 914.0f, 1052.0f, 1628.0f, 1730.0f},
        {1078.0f, 1068.0f, 132.0f, 1068.0f, 1068.0f},
        {0.574219f, 0.140625f, 0.287109f, 0.691406f, 0.691406f},
        {1.0f, 1.0f, 1.0f, 1.0f, 0.0f},
    };
    elevator_parse_result result;
    char errbuf[256];

    if (elevator_parse_raw_outputs(counts, 1, &roi[0][0], 8, 6, 8,
            1920, 1080, 1920, 1080, 0.10f, 0.55f, ELEVATOR_EBIKE_FP_CLEANUP_FULL,
            &result, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected ebike cleanup parser error: %s\n", errbuf);
        return 1;
    }

    if (expect_true(result.detection_count == 2, "ebike cleanup keeps only one ebike and one person") != 0) {
        return 1;
    }
    if (expect_true(result.stats.ebike_count == 1, "ebike false positives removed") != 0) {
        return 1;
    }
    if (expect_true(result.stats.person_count == 1, "person preserved while ebike cleanup runs") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].class_id == 1 || result.detections[1].class_id == 1,
            "one ebike remains after cleanup") != 0) {
        return 1;
    }

    if (elevator_parse_raw_outputs(counts, 1, &roi[0][0], 8, 6, 8,
            1920, 1080, 1920, 1080, 0.10f, 0.55f, ELEVATOR_EBIKE_FP_CLEANUP_SAFE,
            &result, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "unexpected batch-style parser error: %s\n", errbuf);
        return 1;
    }
    if (expect_true(result.detection_count == 3, "batch/raw path keeps overlap candidates but still removes safe duplicates") != 0) {
        return 1;
    }
    if (expect_true(result.stats.ebike_count == 2, "batch/raw path keeps raw ebike recall without obvious duplicate strips") != 0) {
        return 1;
    }
    return 0;
}

static int test_ebike_tracker_requires_confirmation_for_public_output(void)
{
    elevator_ebike_tracker tracker;
    elevator_parse_result result;

    elevator_ebike_tracker_reset(&tracker, 1U, 250U);

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 1U;
    result.detections[0].score = 0.72f;
    result.detections[0].score_percent = 72U;
    result.detections[0].rect.x1 = 800U;
    result.detections[0].rect.y1 = 300U;
    result.detections[0].rect.x2 = 1100U;
    result.detections[0].rect.y2 = 760U;
    result.stats.ebike_count = 1U;
    elevator_ebike_tracker_apply(&tracker, &result, 1000U, 1280U, 720U);
    if (expect_true(result.stats.ebike_count == 0U, "single-frame ebike stays out of public count") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].track_state == ELEVATOR_TRACK_STATE_TENTATIVE,
            "first ebike hit stays tentative") != 0) {
        return 1;
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 1U;
    result.detections[0].score = 0.82f;
    result.detections[0].score_percent = 82U;
    result.detections[0].rect.x1 = 804U;
    result.detections[0].rect.y1 = 302U;
    result.detections[0].rect.x2 = 1102U;
    result.detections[0].rect.y2 = 758U;
    result.stats.ebike_count = 1U;
    elevator_ebike_tracker_apply(&tracker, &result, 1040U, 1280U, 720U);
    if (expect_true(result.stats.ebike_count == 1U, "second ebike hit becomes public") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].track_state == ELEVATOR_TRACK_STATE_CONFIRMED,
            "second ebike hit becomes confirmed") != 0) {
        return 1;
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 0;
    result.stats.ebike_count = 0U;
    elevator_ebike_tracker_apply(&tracker, &result, 1080U, 1280U, 720U);
    if (expect_true(result.stats.ebike_count == 1U, "confirmed ebike lingers briefly in public count") != 0) {
        return 1;
    }
    if (expect_true(result.detection_count == 1U, "confirmed ebike dropout appends a held public box") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].track_state == ELEVATOR_TRACK_STATE_HELD,
            "missing confirmed ebike becomes a held track during short dropout") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].synthetic == 0U,
            "held ebike overlay remains public-visible rather than debug-only synthetic") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_should_render(&result.detections[0], 1280U, 720U) != 0,
            "held confirmed ebike remains visible on public overlay") != 0) {
        return 1;
    }
    return 0;
}

static int test_ebike_tracker_keeps_confirmed_public_output_through_score_dip(void)
{
    elevator_ebike_tracker tracker;
    elevator_parse_result result;

    elevator_ebike_tracker_reset(&tracker, 1U, 250U);

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 1U;
    result.detections[0].score = 0.78f;
    result.detections[0].score_percent = 78U;
    result.detections[0].rect.x1 = 820U;
    result.detections[0].rect.y1 = 260U;
    result.detections[0].rect.x2 = 1090U;
    result.detections[0].rect.y2 = 710U;
    result.stats.ebike_count = 1U;
    elevator_ebike_tracker_apply(&tracker, &result, 1000U, 1280U, 720U);

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 1U;
    result.detections[0].score = 0.84f;
    result.detections[0].score_percent = 84U;
    result.detections[0].rect.x1 = 824U;
    result.detections[0].rect.y1 = 262U;
    result.detections[0].rect.x2 = 1094U;
    result.detections[0].rect.y2 = 708U;
    result.stats.ebike_count = 1U;
    elevator_ebike_tracker_apply(&tracker, &result, 1040U, 1280U, 720U);
    if (expect_true(result.stats.ebike_count == 1U, "confirmed ebike becomes public before score dip") != 0) {
        return 1;
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 1U;
    result.detections[0].score = 0.56f;
    result.detections[0].score_percent = 56U;
    result.detections[0].rect.x1 = 828U;
    result.detections[0].rect.y1 = 264U;
    result.detections[0].rect.x2 = 1098U;
    result.detections[0].rect.y2 = 706U;
    result.stats.ebike_count = 1U;
    elevator_ebike_tracker_apply(&tracker, &result, 1080U, 1280U, 720U);
    if (expect_true(result.stats.ebike_count == 1U,
            "confirmed ebike stays public through a moderate score dip") != 0) {
        return 1;
    }
    if (expect_true(result.detections[0].track_state == ELEVATOR_TRACK_STATE_CONFIRMED,
            "confirmed ebike stays confirmed through a moderate score dip") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_should_render(&result.detections[0], 1280U, 720U) != 0,
            "moderate score dip still renders the confirmed ebike publicly") != 0) {
        return 1;
    }

    memset(&result, 0, sizeof(result));
    result.detection_count = 1;
    result.detections[0].class_id = 1U;
    result.detections[0].score = 0.34f;
    result.detections[0].score_percent = 34U;
    result.detections[0].rect.x1 = 832U;
    result.detections[0].rect.y1 = 266U;
    result.detections[0].rect.x2 = 1100U;
    result.detections[0].rect.y2 = 704U;
    result.stats.ebike_count = 1U;
    elevator_ebike_tracker_apply(&tracker, &result, 1120U, 1280U, 720U);
    if (expect_true(result.stats.ebike_count == 0U,
            "very low score ebike still drops out of public output") != 0) {
        return 1;
    }
    if (expect_true(elevator_public_detection_should_render(&result.detections[0], 1280U, 720U) == 0,
            "very low score ebike stays off the public overlay") != 0) {
        return 1;
    }
    return 0;
}

static int test_ebike_tracker_suppresses_lower_body_person_container(void)
{
    elevator_ebike_tracker tracker;
    elevator_parse_result result;

    elevator_ebike_tracker_reset(&tracker, 1U, 250U);

    memset(&result, 0, sizeof(result));
    result.detection_count = 2;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.86f;
    result.detections[0].score_percent = 86U;
    result.detections[0].rect.x1 = 1052U;
    result.detections[0].rect.y1 = 286U;
    result.detections[0].rect.x2 = 1424U;
    result.detections[0].rect.y2 = 820U;
    result.detections[1].class_id = 1U;
    result.detections[1].score = 0.85f;
    result.detections[1].score_percent = 85U;
    result.detections[1].rect.x1 = 882U;
    result.detections[1].rect.y1 = 476U;
    result.detections[1].rect.x2 = 1560U;
    result.detections[1].rect.y2 = 1010U;
    result.stats.ebike_count = 1U;
    elevator_ebike_tracker_apply(&tracker, &result, 1000U, 1920U, 1080U);

    memset(&result, 0, sizeof(result));
    result.detection_count = 2;
    result.detections[0].class_id = 0U;
    result.detections[0].score = 0.87f;
    result.detections[0].score_percent = 87U;
    result.detections[0].rect.x1 = 1060U;
    result.detections[0].rect.y1 = 286U;
    result.detections[0].rect.x2 = 1428U;
    result.detections[0].rect.y2 = 820U;
    result.detections[1].class_id = 1U;
    result.detections[1].score = 0.86f;
    result.detections[1].score_percent = 86U;
    result.detections[1].rect.x1 = 890U;
    result.detections[1].rect.y1 = 476U;
    result.detections[1].rect.x2 = 1564U;
    result.detections[1].rect.y2 = 1010U;
    result.stats.ebike_count = 1U;
    elevator_ebike_tracker_apply(&tracker, &result, 1040U, 1920U, 1080U);

    if (expect_true(result.stats.ebike_count == 0U,
            "lower-body person container never becomes public ebike") != 0) {
        return 1;
    }
    if (expect_true(result.detections[1].track_state != ELEVATOR_TRACK_STATE_CONFIRMED,
            "lower-body person container stays non-confirmed") != 0) {
        return 1;
    }
    return 0;
}

static int write_text_file(const char *path, const char *text)
{
    FILE *stream = fopen(path, "w");

    if (stream == NULL) {
        return -1;
    }
    fputs(text, stream);
    fclose(stream);
    return 0;
}

static int file_contains_text(const char *path, const char *needle)
{
    FILE *stream = fopen(path, "r");
    char buf[4096];
    size_t len;

    if (stream == NULL) {
        return 0;
    }
    len = fread(buf, 1, sizeof(buf) - 1, stream);
    fclose(stream);
    buf[len] = '\0';
    return strstr(buf, needle) != NULL ? 1 : 0;
}

static int join_path(char *dst, size_t dst_size, const char *dir, const char *name)
{
    if (snprintf(dst, dst_size, "%s/%s", dir, name) >= (int)dst_size) {
        return -1;
    }
    return 0;
}

static int test_batch_metrics_and_outputs(void)
{
    char tempdir[] = "/tmp/elevator_batch_hostXXXXXX";
    char labels_path[512];
    char summary_path[512];
    char configured_output_root[512];
    char output_root[512];
    char jsonl_path[512];
    char csv_path[512];
    elevator_batch_gt_box gt_boxes[ELEVATOR_BATCH_MAX_LABELS];
    size_t gt_count = 0;
    elevator_detection_result detections[3];
    elevator_batch_image_report report;
    elevator_batch_eval_context *ctx = NULL;
    elevator_batch_summary summary;
    FILE *csv_stream = NULL;
    FILE *jsonl_stream = NULL;

    if (mkdtemp(tempdir) == NULL) {
        fprintf(stderr, "failed to create tempdir\n");
        return 1;
    }

    snprintf(labels_path, sizeof(labels_path), "%s/labels.txt", tempdir);
    snprintf(configured_output_root, sizeof(configured_output_root), "%s/out", tempdir);
    snprintf(summary_path, sizeof(summary_path), "%s/summary.json", tempdir);
    snprintf(csv_path, sizeof(csv_path), "%s/per_image.csv", tempdir);
    snprintf(jsonl_path, sizeof(jsonl_path), "%s/detections.jsonl", tempdir);

    if (write_text_file(labels_path, "0 0.5 0.5 0.2 0.4\n1 0.25 0.5 0.1 0.2\n") != 0) {
        fprintf(stderr, "failed to write temp labels\n");
        return 1;
    }
    if (elevator_batch_make_output_dir(configured_output_root, output_root, sizeof(output_root), NULL, 0) != 0) {
        fprintf(stderr, "failed to create temp output dir\n");
        return 1;
    }

    if (elevator_batch_load_yolo_labels(labels_path, 1000, 500, gt_boxes, ELEVATOR_BATCH_MAX_LABELS,
            &gt_count, NULL, 0) != 0) {
        fprintf(stderr, "failed to parse temp labels\n");
        return 1;
    }
    if (expect_true(gt_count == 2, "gt count parsed") != 0) {
        return 1;
    }
    if (expect_true(gt_boxes[0].rect.x1 == 400 && gt_boxes[0].rect.y1 == 150,
            "gt rect 0 converted to pixels") != 0) {
        return 1;
    }
    if (expect_true(gt_boxes[1].rect.x2 == 300 && gt_boxes[1].rect.y2 == 300,
            "gt rect 1 converted to pixels") != 0) {
        return 1;
    }

    memset(detections, 0, sizeof(detections));
    detections[0].class_id = 0;
    detections[0].score = 0.95f;
    detections[0].score_percent = 95;
    detections[0].rect = gt_boxes[0].rect;
    detections[1].class_id = 1;
    detections[1].score = 0.90f;
    detections[1].score_percent = 90;
    detections[1].rect.x1 = 10;
    detections[1].rect.y1 = 10;
    detections[1].rect.x2 = 90;
    detections[1].rect.y2 = 90;
    detections[2].class_id = 1;
    detections[2].score = 0.80f;
    detections[2].score_percent = 80;
    detections[2].rect = gt_boxes[1].rect;

    memset(&report, 0, sizeof(report));
    snprintf(report.image_name, sizeof(report.image_name), "%s", "sample.jpg");
    snprintf(report.image_path, sizeof(report.image_path), "%s", "/dataset/sample.jpg");
    snprintf(report.label_path, sizeof(report.label_path), "%s", labels_path);
    snprintf(report.output_path, sizeof(report.output_path), "%s", "/out/sample.jpg");
    report.frame_width = 1000;
    report.frame_height = 500;
    report.fallback_used = 1;
    report.elapsed_ms = 12.5;
    report.timing_ms.frame_proc_ms = 8.0;
    report.timing_ms.prepare_ms = 0.5;
    report.timing_ms.preprocess_ms = 1.0;
    report.timing_ms.input_update_ms = 0.2;
    report.timing_ms.model_execute_ms = 3.5;
    report.timing_ms.output_fetch_ms = 0.3;
    report.timing_ms.postprocess_ms = 1.5;
    report.timing_ms.temporal_ms = 0.4;
    report.timing_ms.render_prepare_ms = 0.1;
    report.timing_ms.render_ms = 0.8;
    report.timing_ms.osd_ms = 0.7;

    ctx = elevator_batch_eval_create();
    if (ctx == NULL) {
        fprintf(stderr, "failed to create batch eval ctx\n");
        return 1;
    }
    if (elevator_batch_eval_image(ctx, gt_boxes, gt_count, detections, 3, 0.5f, &report) != 0) {
        fprintf(stderr, "failed to evaluate synthetic detections\n");
        elevator_batch_eval_destroy(ctx);
        return 1;
    }
    elevator_batch_eval_note_run(ctx, report.elapsed_ms, report.fallback_used);
    elevator_batch_eval_note_timing(ctx, &report.timing_ms);
    elevator_batch_eval_finalize(ctx, &summary);

    if (expect_true(summary.success_count == 1, "batch success count") != 0) {
        elevator_batch_eval_destroy(ctx);
        return 1;
    }
    if (expect_true(summary.fallback_count == 1, "batch fallback count") != 0) {
        elevator_batch_eval_destroy(ctx);
        return 1;
    }
    if (expect_true(summary.average_timing_ms.model_execute_ms > 3.49 &&
            summary.average_timing_ms.model_execute_ms < 3.51,
            "batch timing model execute average") != 0) {
        elevator_batch_eval_destroy(ctx);
        return 1;
    }
    if (expect_true(summary.classes[0].tp == 1 && summary.classes[0].fp == 0, "class0 tp/fp") != 0) {
        elevator_batch_eval_destroy(ctx);
        return 1;
    }
    if (expect_true(summary.classes[1].tp == 1 && summary.classes[1].fp == 1, "class1 tp/fp") != 0) {
        elevator_batch_eval_destroy(ctx);
        return 1;
    }
    if (expect_true(summary.classes[0].ap50 > 0.99 && summary.classes[0].ap50 <= 1.0, "class0 ap50") != 0) {
        elevator_batch_eval_destroy(ctx);
        return 1;
    }
    if (expect_true(summary.classes[1].ap50 > 0.49 && summary.classes[1].ap50 < 0.51, "class1 ap50") != 0) {
        elevator_batch_eval_destroy(ctx);
        return 1;
    }
    if (expect_true(summary.map50 > 0.74 && summary.map50 < 0.76, "map50 synthetic case") != 0) {
        elevator_batch_eval_destroy(ctx);
        return 1;
    }

    csv_stream = fopen(csv_path, "w");
    jsonl_stream = fopen(jsonl_path, "w");
    if (csv_stream == NULL || jsonl_stream == NULL) {
        fprintf(stderr, "failed to open temp output files\n");
        elevator_batch_eval_destroy(ctx);
        return 1;
    }
    if (elevator_batch_write_per_image_header(csv_stream) != 0 ||
        elevator_batch_write_per_image_row(csv_stream, &report) != 0 ||
        elevator_batch_write_detections_jsonl(jsonl_stream, &report, gt_boxes, gt_count, detections, 3) != 0) {
        fprintf(stderr, "failed to write temp batch outputs\n");
        fclose(csv_stream);
        fclose(jsonl_stream);
        elevator_batch_eval_destroy(ctx);
        return 1;
    }
    fclose(csv_stream);
    fclose(jsonl_stream);

    if (elevator_batch_write_summary_json(summary_path, "/images", "/labels", "/output",
            10, 0.15f, 0.45f, &summary) != 0) {
        fprintf(stderr, "failed to write temp summary json\n");
        elevator_batch_eval_destroy(ctx);
        return 1;
    }
    elevator_batch_eval_destroy(ctx);

    if (expect_true(file_contains_text(summary_path, "\"map50\""), "summary json contains map50") != 0) {
        return 1;
    }
    if (expect_true(file_contains_text(summary_path, "\"timing_ms_average\""),
            "summary json contains timing average") != 0) {
        return 1;
    }
    if (expect_true(file_contains_text(summary_path, "\"class_name\": \"person\""),
            "summary json contains class names") != 0) {
        return 1;
    }
    if (expect_true(file_contains_text(csv_path, "sample.jpg"), "per_image csv contains row") != 0) {
        return 1;
    }
    if (expect_true(file_contains_text(csv_path, "model_execute_ms"),
            "per_image csv contains timing header") != 0) {
        return 1;
    }
    if (expect_true(file_contains_text(jsonl_path, "\"detections\""), "jsonl contains detections") != 0) {
        return 1;
    }
    if (expect_true(file_contains_text(jsonl_path, "\"timing_ms\""), "jsonl contains timing object") != 0) {
        return 1;
    }
    if (expect_true(file_contains_text(jsonl_path, "\"model_execute_ms\""),
            "jsonl contains model execute timing") != 0) {
        return 1;
    }
    return 0;
}

static int test_batch_collect_images(void)
{
    char tempdir[] = "/tmp/elevator_batch_listXXXXXX";
    char images_dir[512];
    char labels_dir[512];
    char image_a[512];
    char image_b[512];
    char image_skip[512];
    char label_a[512];
    char label_b[512];
    elevator_batch_image_list list;
    char errbuf[256];

    if (mkdtemp(tempdir) == NULL) {
        fprintf(stderr, "failed to create image tempdir\n");
        return 1;
    }

    snprintf(images_dir, sizeof(images_dir), "%s/images", tempdir);
    snprintf(labels_dir, sizeof(labels_dir), "%s/labels", tempdir);
    if (mkdir(images_dir, 0755) != 0 || mkdir(labels_dir, 0755) != 0) {
        fprintf(stderr, "failed to create batch collect dirs\n");
        return 1;
    }

    if (join_path(image_a, sizeof(image_a), images_dir, "b.jpg") != 0 ||
        join_path(image_b, sizeof(image_b), images_dir, "a.jpeg") != 0 ||
        join_path(image_skip, sizeof(image_skip), images_dir, "ignore.txt") != 0 ||
        join_path(label_a, sizeof(label_a), labels_dir, "b.txt") != 0 ||
        join_path(label_b, sizeof(label_b), labels_dir, "a.txt") != 0) {
        fprintf(stderr, "failed to build batch collect paths\n");
        return 1;
    }
    if (write_text_file(image_a, "jpg") != 0 || write_text_file(image_b, "jpeg") != 0 ||
        write_text_file(image_skip, "txt") != 0 || write_text_file(label_a, "") != 0 ||
        write_text_file(label_b, "") != 0) {
        fprintf(stderr, "failed to write batch collect files\n");
        return 1;
    }

    memset(&list, 0, sizeof(list));
    if (elevator_batch_collect_images(images_dir, labels_dir, 0, 0, &list, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "collect images failed: %s\n", errbuf);
        return 1;
    }
    if (expect_true(list.count == 2, "jpeg file filtering") != 0) {
        elevator_batch_free_image_list(&list);
        return 1;
    }
    if (expect_true(strcmp(list.items[0].image_name, "a.jpeg") == 0, "batch image sort order") != 0) {
        elevator_batch_free_image_list(&list);
        return 1;
    }
    if (expect_true(strstr(list.items[1].label_path, "/labels/b.txt") != NULL, "label path pairing") != 0) {
        elevator_batch_free_image_list(&list);
        return 1;
    }
    elevator_batch_free_image_list(&list);

    memset(&list, 0, sizeof(list));
    if (elevator_batch_collect_images(images_dir, labels_dir, 1, 1, &list, errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "collect images with offset failed: %s\n", errbuf);
        return 1;
    }
    if (expect_true(list.count == 1, "offset and limit slice image list") != 0) {
        elevator_batch_free_image_list(&list);
        return 1;
    }
    if (expect_true(strcmp(list.items[0].image_name, "b.jpg") == 0, "offset starts from sorted index") != 0) {
        elevator_batch_free_image_list(&list);
        return 1;
    }
    elevator_batch_free_image_list(&list);
    return 0;
}

static int test_file_drain_wait_extends_while_frames_continue(void)
{
    elevator_file_drain_state state;
    elevator_file_drain_snapshot snapshot;
    elevator_file_drain_decision decision;
    uint32_t poll_ms = 100;
    uint32_t idle_timeout_ms = 500;
    uint32_t stable_polls_required = 3;
    uint64_t frame_count = 100;
    int idx;

    memset(&state, 0, sizeof(state));
    memset(&snapshot, 0, sizeof(snapshot));
    snapshot.left_stream_bytes = 128;
    snapshot.left_stream_frames = 1;
    snapshot.left_decoded_frames = 1;
    snapshot.processed_frame_count = frame_count;

    decision = elevator_file_drain_step(&state, &snapshot, poll_ms, idle_timeout_ms, stable_polls_required);
    if (expect_true(decision == ELEVATOR_FILE_DRAIN_DECISION_CONTINUE,
            "initial nonzero drain state should continue") != 0) {
        return 1;
    }

    for (idx = 0; idx < 10; ++idx) {
        frame_count += 5;
        snapshot.processed_frame_count = frame_count;
        decision = elevator_file_drain_step(&state, &snapshot, poll_ms, idle_timeout_ms, stable_polls_required);
        if (expect_true(decision == ELEVATOR_FILE_DRAIN_DECISION_CONTINUE,
                "continued frame progress must reset idle timeout") != 0) {
            return 1;
        }
    }

    for (idx = 0; idx < 4; ++idx) {
        decision = elevator_file_drain_step(&state, &snapshot, poll_ms, idle_timeout_ms, stable_polls_required);
        if (expect_true(decision == ELEVATOR_FILE_DRAIN_DECISION_CONTINUE,
                "idle timeout should not trigger before configured budget is exhausted") != 0) {
            return 1;
        }
    }

    decision = elevator_file_drain_step(&state, &snapshot, poll_ms, idle_timeout_ms, stable_polls_required);
    if (expect_true(decision == ELEVATOR_FILE_DRAIN_DECISION_TIMED_OUT,
            "stale drain state should eventually time out after progress stops") != 0) {
        return 1;
    }

    return 0;
}

static int test_file_drain_ready_after_stable_zero_status(void)
{
    elevator_file_drain_state state;
    elevator_file_drain_snapshot snapshot;
    elevator_file_drain_decision decision;
    uint32_t poll_ms = 100;
    uint32_t idle_timeout_ms = 500;
    uint32_t stable_polls_required = 3;

    memset(&state, 0, sizeof(state));
    memset(&snapshot, 0, sizeof(snapshot));
    snapshot.processed_frame_count = 42;

    decision = elevator_file_drain_step(&state, &snapshot, poll_ms, idle_timeout_ms, stable_polls_required);
    if (expect_true(decision == ELEVATOR_FILE_DRAIN_DECISION_CONTINUE,
            "first zero-status poll seeds drain state") != 0) {
        return 1;
    }

    decision = elevator_file_drain_step(&state, &snapshot, poll_ms, idle_timeout_ms, stable_polls_required);
    if (expect_true(decision == ELEVATOR_FILE_DRAIN_DECISION_CONTINUE,
            "stable zero-status polls should wait until threshold") != 0) {
        return 1;
    }

    decision = elevator_file_drain_step(&state, &snapshot, poll_ms, idle_timeout_ms, stable_polls_required);
    if (expect_true(decision == ELEVATOR_FILE_DRAIN_DECISION_READY,
            "stable zero-status polls should declare drain ready") != 0) {
        return 1;
    }

    return 0;
}

int main(void)
{
    if (test_cli_defaults() != 0) {
        return 1;
    }
    if (test_cli_file_surface_and_timing_options() != 0) {
        return 1;
    }
    if (test_cli_batch() != 0) {
        return 1;
    }
    if (test_smoother() != 0) {
        return 1;
    }
    if (test_temporal_hold() != 0) {
        return 1;
    }
    if (test_parser() != 0) {
        return 1;
    }
    if (test_parser_drops_invalid_rect() != 0) {
        return 1;
    }
    if (test_parser_applies_nms() != 0) {
        return 1;
    }
    if (test_person_tracker_duplicate_cleanup_and_child_protection() != 0) {
        return 1;
    }
    if (test_public_overlay_color_is_state_agnostic() != 0) {
        return 1;
    }
    if (test_public_overlay_visibility_separates_count_truth_from_clean_render() != 0) {
        return 1;
    }
    if (test_review_surface_filters_match_server_signoff_contract() != 0) {
        return 1;
    }
    if (test_child_like_false_positive_suppression() != 0) {
        return 1;
    }
    if (test_parser_suppresses_low_score_large_box_over_child() != 0) {
        return 1;
    }
    if (test_parser_suppresses_low_score_medium_box_over_child() != 0) {
        return 1;
    }
    if (test_parser_suppresses_partial_large_box_with_high_score_support() != 0) {
        return 1;
    }
    if (test_parser_suppresses_top_right_corner_umbrella_box() != 0) {
        return 1;
    }
    if (test_person_tracker_prefers_tighter_box_over_large_child_duplicate() != 0) {
        return 1;
    }
    if (test_person_tracker_preserves_child_box_against_one_frame_regression() != 0) {
        return 1;
    }
    if (test_person_tracker_hold_carry_keeps_single_person_tail() != 0) {
        return 1;
    }
    if (test_person_tracker_keeps_mature_track_over_fresh_overlap_reacquire() != 0) {
        return 1;
    }
    if (test_person_tracker_carries_mature_low_quality_neighbor_during_partial_dropout() != 0) {
        return 1;
    }
    if (test_person_tracker_carries_robust_mature_low_score_neighbor_during_partial_dropout() != 0) {
        return 1;
    }
    if (test_person_tracker_promotes_mature_synthetic_hold_to_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_keeps_child_like_mature_synthetic_hold_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_keeps_exact_tail_child_like_matched_synthetic_hold_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_keeps_tail_child_like_reconfirm_synthetic_hold_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_skips_duplicate_mature_synthetic_hold_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_keeps_overlapping_unmatched_mature_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_skips_near_identical_unmatched_mature_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_keeps_offset_nested_unmatched_mature_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_skips_top_edge_contained_unmatched_mature_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_skips_top_edge_aligned_unmatched_mature_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_skips_near_top_aligned_unmatched_mature_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_skips_upper_fragment_unmatched_mature_public_carry() != 0) {
        return 1;
    }
    if (test_person_tracker_caps_public_carry_to_last_visible_count() != 0) {
        return 1;
    }
    if (test_person_tracker_keeps_top_edge_reacquire_public_carry_eligible() != 0) {
        return 1;
    }
    if (test_person_tracker_does_not_carry_low_quality_stale_false_track() != 0) {
        return 1;
    }
    if (test_person_tracker_does_not_carry_mature_low_quality_stale_false_track() != 0) {
        return 1;
    }
    if (test_person_tracker_skips_tail_lower_fragment_stale_public_carry() != 0) {
        return 1;
    }
    if (test_parser_applies_ebike_false_positive_cleanup() != 0) {
        return 1;
    }
    if (test_ebike_tracker_requires_confirmation_for_public_output() != 0) {
        return 1;
    }
    if (test_ebike_tracker_keeps_confirmed_public_output_through_score_dip() != 0) {
        return 1;
    }
    if (test_ebike_tracker_suppresses_lower_body_person_container() != 0) {
        return 1;
    }
    if (test_osd_panel_prefers_live_ebike_count_over_smoothed_ebike_count() != 0) {
        return 1;
    }
    if (test_batch_metrics_and_outputs() != 0) {
        return 1;
    }
    if (test_batch_collect_images() != 0) {
        return 1;
    }
    if (test_file_drain_wait_extends_while_frames_continue() != 0) {
        return 1;
    }
    if (test_file_drain_ready_after_stable_zero_status() != 0) {
        return 1;
    }

    puts("host tests passed");
    return 0;
}
