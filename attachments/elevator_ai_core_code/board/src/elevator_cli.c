#include "elevator_yolo.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int elevator_parse_u32(const char *text, uint32_t *value)
{
    char *end = NULL;
    unsigned long parsed;

    if (text == NULL || value == NULL || text[0] == '\0') {
        return -1;
    }

    parsed = strtoul(text, &end, 10);
    if (end == NULL || *end != '\0') {
        return -1;
    }
    *value = (uint32_t)parsed;
    return 0;
}

static int elevator_parse_float(const char *text, float *value)
{
    char *end = NULL;

    if (text == NULL || value == NULL || text[0] == '\0') {
        return -1;
    }

    *value = strtof(text, &end);
    if (end == NULL || *end != '\0') {
        return -1;
    }
    return 0;
}

static int elevator_parse_surface(const char *text, elevator_review_surface *surface)
{
    if (text == NULL || surface == NULL || text[0] == '\0') {
        return -1;
    }
    if (strcmp(text, "clean") == 0) {
        *surface = ELEVATOR_REVIEW_SURFACE_CLEAN;
        return 0;
    }
    if (strcmp(text, "public") == 0) {
        *surface = ELEVATOR_REVIEW_SURFACE_PUBLIC;
        return 0;
    }
    if (strcmp(text, "debug") == 0) {
        *surface = ELEVATOR_REVIEW_SURFACE_DEBUG;
        return 0;
    }
    return -1;
}

static int elevator_parse_timing_mode(const char *text, elevator_playback_timing_mode *timing_mode)
{
    if (text == NULL || timing_mode == NULL || text[0] == '\0') {
        return -1;
    }
    if (strcmp(text, "source") == 0) {
        *timing_mode = ELEVATOR_PLAYBACK_TIMING_SOURCE;
        return 0;
    }
    return -1;
}

static int elevator_parse_ebike_cleanup_mode(const char *text, int *cleanup_mode)
{
    if (text == NULL || cleanup_mode == NULL || text[0] == '\0') {
        return -1;
    }
    if (strcmp(text, "auto") == 0) {
        *cleanup_mode = ELEVATOR_EBIKE_CLEANUP_CLI_AUTO;
        return 0;
    }
    if (strcmp(text, "off") == 0) {
        *cleanup_mode = ELEVATOR_EBIKE_CLEANUP_CLI_OFF;
        return 0;
    }
    if (strcmp(text, "safe") == 0) {
        *cleanup_mode = ELEVATOR_EBIKE_CLEANUP_CLI_SAFE;
        return 0;
    }
    if (strcmp(text, "full") == 0) {
        *cleanup_mode = ELEVATOR_EBIKE_CLEANUP_CLI_FULL;
        return 0;
    }
    return -1;
}

void elevator_config_init(elevator_runtime_config *config)
{
    if (config == NULL) {
        return;
    }

    memset(config, 0, sizeof(*config));
    config->mode = ELEVATOR_RUN_MODE_HELP;
    snprintf(config->input_path, sizeof(config->input_path), "./data/input/dolls_video.h264");
    config->images_dir[0] = '\0';
    config->labels_dir[0] = '\0';
    config->output_dir[0] = '\0';
    snprintf(config->model_path, sizeof(config->model_path), "./data/model/yolov8.om");
    config->score_threshold = 0.15f;
    config->nms_threshold = 0.45f;
    config->smooth_window = 5;
    config->rtsp_port = 554;
    config->offset = 0;
    config->limit = 0;
    config->ebike_cleanup_mode = ELEVATOR_EBIKE_CLEANUP_CLI_AUTO;
    config->review_surface = ELEVATOR_REVIEW_SURFACE_CLEAN;
    config->timing_mode = ELEVATOR_PLAYBACK_TIMING_SOURCE;
    config->single_shot = 1;
    config->source_fps = 0.0f;
    config->source_frame_count = 0;
    config->source_duration_ms = 0;
    config->osd_enable = 1;
}

void elevator_print_usage(const char *prog_name)
{
    const char *name = (prog_name != NULL) ? prog_name : "elevator_yolo";

    printf("Usage:\n");
    printf("  %s file [--input <media>] [--model <om>] [--score <f>] [--nms <f>]\n", name);
    printf("  %s file [--smooth-window <n>] [--rtsp-port <n>] [--surface clean|public|debug]\n", name);
    printf("  %s file [--ebike-cleanup auto|full|safe|off]\n", name);
    printf("  %s file [--timing source] [--single-shot] [--source-fps <f>] [--source-frame-count <n>]\n", name);
    printf("  %s file [--source-duration-ms <n>] [--no-osd]\n", name);
    printf("  %s batch --images-dir <dir> --labels-dir <dir> [--output-dir <dir>]\n", name);
    printf("  %s batch [--model <om>] [--score <f>] [--nms <f>] [--offset <n>] [--limit <n>] [--ebike-cleanup auto|full|safe|off] [--no-osd]\n", name);
    printf("  %s camera\n", name);
    printf("\n");
    printf("Notes:\n");
    printf("  file mode supports .h264/.h265 and single-frame .jpg/.jpeg inputs.\n");
    printf("  batch mode supports non-recursive .jpg/.jpeg directories with YOLO labels.\n");
    printf("  camera mode is reserved for a future phase and returns an error in v1.\n");
}

int elevator_parse_cli(int argc, char **argv, elevator_runtime_config *config,
    char *errbuf, size_t errbuf_size)
{
    int idx;

    if (errbuf != NULL && errbuf_size > 0) {
        errbuf[0] = '\0';
    }
    if (config == NULL) {
        return -1;
    }

    elevator_config_init(config);
    if (argc <= 1 || argv == NULL || argv[1] == NULL) {
        return 0;
    }
    if (strcmp(argv[1], "help") == 0 || strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0) {
        return 0;
    }
    if (strcmp(argv[1], "file") == 0) {
        config->mode = ELEVATOR_RUN_MODE_FILE;
    } else if (strcmp(argv[1], "batch") == 0) {
        config->mode = ELEVATOR_RUN_MODE_BATCH;
    } else if (strcmp(argv[1], "camera") == 0) {
        config->mode = ELEVATOR_RUN_MODE_CAMERA;
    } else {
        if (errbuf != NULL && errbuf_size > 0) {
            snprintf(errbuf, errbuf_size, "unknown mode: %s", argv[1]);
        }
        return -1;
    }

    for (idx = 2; idx < argc; ++idx) {
        const char *arg = argv[idx];

        if (strcmp(arg, "--input") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            snprintf(config->input_path, sizeof(config->input_path), "%s", argv[++idx]);
        } else if (strcmp(arg, "--images-dir") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            snprintf(config->images_dir, sizeof(config->images_dir), "%s", argv[++idx]);
        } else if (strcmp(arg, "--labels-dir") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            snprintf(config->labels_dir, sizeof(config->labels_dir), "%s", argv[++idx]);
        } else if (strcmp(arg, "--output-dir") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            snprintf(config->output_dir, sizeof(config->output_dir), "%s", argv[++idx]);
        } else if (strcmp(arg, "--model") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            snprintf(config->model_path, sizeof(config->model_path), "%s", argv[++idx]);
        } else if (strcmp(arg, "--score") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_float(argv[++idx], &config->score_threshold) != 0) {
                goto invalid_float;
            }
        } else if (strcmp(arg, "--nms") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_float(argv[++idx], &config->nms_threshold) != 0) {
                goto invalid_float;
            }
        } else if (strcmp(arg, "--smooth-window") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_u32(argv[++idx], &config->smooth_window) != 0) {
                goto invalid_uint;
            }
        } else if (strcmp(arg, "--rtsp-port") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_u32(argv[++idx], &config->rtsp_port) != 0) {
                goto invalid_uint;
            }
        } else if (strcmp(arg, "--surface") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_surface(argv[++idx], &config->review_surface) != 0) {
                if (errbuf != NULL && errbuf_size > 0) {
                    snprintf(errbuf, errbuf_size, "invalid surface value: %s", argv[idx]);
                }
                return -1;
            }
        } else if (strcmp(arg, "--ebike-cleanup") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_ebike_cleanup_mode(argv[++idx], &config->ebike_cleanup_mode) != 0) {
                if (errbuf != NULL && errbuf_size > 0) {
                    snprintf(errbuf, errbuf_size, "invalid ebike cleanup value: %s", argv[idx]);
                }
                return -1;
            }
        } else if (strcmp(arg, "--timing") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_timing_mode(argv[++idx], &config->timing_mode) != 0) {
                if (errbuf != NULL && errbuf_size > 0) {
                    snprintf(errbuf, errbuf_size, "invalid timing mode: %s", argv[idx]);
                }
                return -1;
            }
        } else if (strcmp(arg, "--single-shot") == 0) {
            config->single_shot = 1;
        } else if (strcmp(arg, "--source-fps") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_float(argv[++idx], &config->source_fps) != 0) {
                goto invalid_float;
            }
        } else if (strcmp(arg, "--source-frame-count") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_u32(argv[++idx], &config->source_frame_count) != 0) {
                goto invalid_uint;
            }
        } else if (strcmp(arg, "--source-duration-ms") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_u32(argv[++idx], &config->source_duration_ms) != 0) {
                goto invalid_uint;
            }
        } else if (strcmp(arg, "--offset") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_u32(argv[++idx], &config->offset) != 0) {
                goto invalid_uint;
            }
        } else if (strcmp(arg, "--limit") == 0) {
            if (idx + 1 >= argc) {
                goto missing_value;
            }
            if (elevator_parse_u32(argv[++idx], &config->limit) != 0) {
                goto invalid_uint;
            }
        } else if (strcmp(arg, "--no-osd") == 0) {
            config->osd_enable = 0;
        } else if (strcmp(arg, "--help") == 0 || strcmp(arg, "-h") == 0) {
            config->mode = ELEVATOR_RUN_MODE_HELP;
            return 0;
        } else {
            if (errbuf != NULL && errbuf_size > 0) {
                snprintf(errbuf, errbuf_size, "unknown option: %s", arg);
            }
            return -1;
        }
    }

    if (config->score_threshold < 0.0f || config->score_threshold > 1.0f ||
        config->nms_threshold < 0.0f || config->nms_threshold > 1.0f) {
        if (errbuf != NULL && errbuf_size > 0) {
            snprintf(errbuf, errbuf_size, "score/nms thresholds must be between 0 and 1");
        }
        return -1;
    }
    if (config->smooth_window == 0) {
        config->smooth_window = 1;
    }
    if (config->mode == ELEVATOR_RUN_MODE_BATCH &&
        (config->images_dir[0] == '\0' || config->labels_dir[0] == '\0')) {
        if (errbuf != NULL && errbuf_size > 0) {
            snprintf(errbuf, errbuf_size, "batch mode requires --images-dir and --labels-dir");
        }
        return -1;
    }
    return 0;

missing_value:
    if (errbuf != NULL && errbuf_size > 0) {
        snprintf(errbuf, errbuf_size, "missing value for option: %s", argv[idx]);
    }
    return -1;

invalid_float:
    if (errbuf != NULL && errbuf_size > 0) {
        snprintf(errbuf, errbuf_size, "invalid float value for option: %s", argv[idx - 1]);
    }
    return -1;

invalid_uint:
    if (errbuf != NULL && errbuf_size > 0) {
        snprintf(errbuf, errbuf_size, "invalid integer value for option: %s", argv[idx - 1]);
    }
    return -1;
}
