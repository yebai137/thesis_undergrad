#include "elevator_osd.h"
#include "elevator_panel_text.h"

#include <stdio.h>
#include <string.h>

#include "ss_mpi_region.h"
#include "ss_mpi_vgs.h"

#define ELEVATOR_PANEL_RGN_HANDLE 200
#define ELEVATOR_PANEL_BASE_WIDTH 192
#define ELEVATOR_PANEL_BASE_HEIGHT 24
#define ELEVATOR_PANEL_BASE_PADDING_X 4
#define ELEVATOR_PANEL_BASE_PADDING_Y 5
#define ELEVATOR_FONT_MIN_SCALE 2
#define ELEVATOR_FONT_MAX_SCALE 4
#define ELEVATOR_FONT_WIDTH 5
#define ELEVATOR_FONT_HEIGHT 7
#define ELEVATOR_FONT_BASE_SPACING 2
#define ELEVATOR_PANEL_TEXT_CAPACITY 18
#define ELEVATOR_PANEL_BG_COLOR 0x0000
#define ELEVATOR_PANEL_FG_COLOR 0xFFFF

static uint32_t g_elevator_frame_width = 0;
static uint32_t g_elevator_frame_height = 0;
static uint32_t g_elevator_panel_width = ELEVATOR_PANEL_BASE_WIDTH;
static uint32_t g_elevator_panel_height = ELEVATOR_PANEL_BASE_HEIGHT;
static uint32_t g_elevator_panel_padding_x = ELEVATOR_PANEL_BASE_PADDING_X;
static uint32_t g_elevator_panel_padding_y = ELEVATOR_PANEL_BASE_PADDING_Y;
static uint32_t g_elevator_font_scale = ELEVATOR_FONT_MIN_SCALE;
static uint32_t g_elevator_font_spacing = ELEVATOR_FONT_BASE_SPACING;
static td_bool g_elevator_panel_created = TD_FALSE;
static ot_vgs_osd g_elevator_score_osd[ELEVATOR_MAX_DETECTIONS];

static uint32_t elevator_max_u32(uint32_t lhs, uint32_t rhs)
{
    return lhs > rhs ? lhs : rhs;
}

static uint32_t elevator_align_even_u32(uint32_t value)
{
    if (value <= 2U) {
        return 2U;
    }
    return value & ~1U;
}

static uint32_t elevator_osd_char_advance(td_void)
{
    return (ELEVATOR_FONT_WIDTH * g_elevator_font_scale) + g_elevator_font_spacing;
}

static void elevator_osd_reset_layout(td_void)
{
    g_elevator_panel_width = ELEVATOR_PANEL_BASE_WIDTH;
    g_elevator_panel_height = ELEVATOR_PANEL_BASE_HEIGHT;
    g_elevator_panel_padding_x = ELEVATOR_PANEL_BASE_PADDING_X;
    g_elevator_panel_padding_y = ELEVATOR_PANEL_BASE_PADDING_Y;
    g_elevator_font_scale = ELEVATOR_FONT_MIN_SCALE;
    g_elevator_font_spacing = ELEVATOR_FONT_BASE_SPACING;
}

static void elevator_osd_configure_layout(uint32_t frame_width)
{
    uint32_t text_width;

    elevator_osd_reset_layout();
    if (frame_width >= 3840U) {
        g_elevator_font_scale = ELEVATOR_FONT_MAX_SCALE;
    } else if (frame_width >= 1920U) {
        g_elevator_font_scale = 3U;
    }

    g_elevator_font_spacing = ELEVATOR_FONT_BASE_SPACING + (g_elevator_font_scale - ELEVATOR_FONT_MIN_SCALE);
    g_elevator_panel_padding_x = ELEVATOR_PANEL_BASE_PADDING_X + ((g_elevator_font_scale - ELEVATOR_FONT_MIN_SCALE) * 2U);
    g_elevator_panel_padding_y = ELEVATOR_PANEL_BASE_PADDING_Y + (g_elevator_font_scale - ELEVATOR_FONT_MIN_SCALE);
    text_width = (ELEVATOR_PANEL_TEXT_CAPACITY * elevator_osd_char_advance()) + (g_elevator_panel_padding_x * 2U);
    g_elevator_panel_width = elevator_max_u32(ELEVATOR_PANEL_BASE_WIDTH, text_width);
    g_elevator_panel_height = elevator_max_u32(ELEVATOR_PANEL_BASE_HEIGHT,
        (ELEVATOR_FONT_HEIGHT * g_elevator_font_scale) + (g_elevator_panel_padding_y * 2U));
    if (frame_width != 0 && g_elevator_panel_width > frame_width) {
        g_elevator_panel_width = frame_width;
    }

    g_elevator_panel_width = elevator_align_even_u32(g_elevator_panel_width);
    g_elevator_panel_height = elevator_align_even_u32(g_elevator_panel_height);
}

static const uint8_t *elevator_glyph_for_char(char ch)
{
    static const uint8_t space[7] = {0, 0, 0, 0, 0, 0, 0};
    static const uint8_t colon[7] = {0x00, 0x04, 0x04, 0x00, 0x04, 0x04, 0x00};
    static const uint8_t letter_c[7] = {0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E};
    static const uint8_t letter_d[7] = {0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C};
    static const uint8_t digit_0[7] = {0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E};
    static const uint8_t digit_1[7] = {0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E};
    static const uint8_t digit_2[7] = {0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F};
    static const uint8_t digit_3[7] = {0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E};
    static const uint8_t digit_4[7] = {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02};
    static const uint8_t digit_5[7] = {0x1F, 0x10, 0x10, 0x1E, 0x01, 0x01, 0x1E};
    static const uint8_t digit_6[7] = {0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E};
    static const uint8_t digit_7[7] = {0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08};
    static const uint8_t digit_8[7] = {0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E};
    static const uint8_t digit_9[7] = {0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C};
    static const uint8_t letter_e[7] = {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F};
    static const uint8_t letter_f[7] = {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10};
    static const uint8_t letter_p[7] = {0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10};
    static const uint8_t letter_s[7] = {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E};

    switch (ch) {
        case '0':
            return digit_0;
        case '1':
            return digit_1;
        case '2':
            return digit_2;
        case '3':
            return digit_3;
        case '4':
            return digit_4;
        case '5':
            return digit_5;
        case '6':
            return digit_6;
        case '7':
            return digit_7;
        case '8':
            return digit_8;
        case '9':
            return digit_9;
        case 'C':
            return letter_c;
        case 'D':
            return letter_d;
        case 'E':
            return letter_e;
        case 'F':
            return letter_f;
        case 'P':
            return letter_p;
        case 'S':
            return letter_s;
        case ':':
            return colon;
        case ' ':
        default:
            return space;
    }
}

static void elevator_osd_clear_canvas(uint16_t *pixels, uint32_t stride_pixels,
    uint32_t width, uint32_t height)
{
    uint32_t y;
    uint32_t x;

    for (y = 0; y < height; ++y) {
        uint16_t *row = pixels + (y * stride_pixels);
        for (x = 0; x < width; ++x) {
            row[x] = ELEVATOR_PANEL_BG_COLOR;
        }
    }
}

static void elevator_osd_draw_char(uint16_t *pixels, uint32_t stride_pixels, uint32_t panel_width,
    uint32_t panel_height, uint32_t x, uint32_t y, char ch)
{
    const uint8_t *glyph = elevator_glyph_for_char(ch);
    uint32_t row;
    uint32_t col;
    uint32_t dy;
    uint32_t dx;

    for (row = 0; row < ELEVATOR_FONT_HEIGHT; ++row) {
        for (col = 0; col < ELEVATOR_FONT_WIDTH; ++col) {
            if ((glyph[row] & (1U << (ELEVATOR_FONT_WIDTH - 1U - col))) == 0) {
                continue;
            }

            for (dy = 0; dy < g_elevator_font_scale; ++dy) {
                uint32_t py = y + (row * g_elevator_font_scale) + dy;
                if (py >= panel_height) {
                    continue;
                }

                for (dx = 0; dx < g_elevator_font_scale; ++dx) {
                    uint32_t px = x + (col * g_elevator_font_scale) + dx;
                    if (px >= panel_width) {
                        continue;
                    }
                    pixels[py * stride_pixels + px] = ELEVATOR_PANEL_FG_COLOR;
                }
            }
        }
    }
}

static void elevator_osd_draw_string(uint16_t *pixels, uint32_t stride_pixels,
    uint32_t panel_width, uint32_t panel_height, uint32_t x, uint32_t y, const char *text)
{
    uint32_t cursor = x;
    const uint32_t advance = elevator_osd_char_advance();

    while (text != NULL && *text != '\0') {
        elevator_osd_draw_char(pixels, stride_pixels, panel_width, panel_height, cursor, y, *text);
        cursor += advance;
        ++text;
    }
}

int elevator_osd_init(uint32_t frame_width, uint32_t frame_height)
{
    ot_rgn_attr region_attr;
    int ret;

    elevator_osd_deinit();
    g_elevator_frame_width = frame_width;
    g_elevator_frame_height = frame_height;
    elevator_osd_configure_layout(frame_width);

    memset(&region_attr, 0, sizeof(region_attr));
    region_attr.type = OT_RGN_OVERLAYEX;
    region_attr.attr.overlayex.pixel_format = OT_PIXEL_FORMAT_ARGB_1555;
    region_attr.attr.overlayex.bg_color = ELEVATOR_PANEL_BG_COLOR;
    region_attr.attr.overlayex.size.width = g_elevator_panel_width;
    region_attr.attr.overlayex.size.height = g_elevator_panel_height;
    region_attr.attr.overlayex.canvas_num = 1;

    ret = ss_mpi_rgn_create(ELEVATOR_PANEL_RGN_HANDLE, &region_attr);
    if (ret != TD_SUCCESS) {
        g_elevator_frame_width = 0;
        g_elevator_frame_height = 0;
        elevator_osd_reset_layout();
        return ret;
    }

    g_elevator_panel_created = TD_TRUE;
    return TD_SUCCESS;
}

void elevator_osd_deinit(void)
{
    if (g_elevator_panel_created == TD_TRUE) {
        (td_void)ss_mpi_rgn_destroy(ELEVATOR_PANEL_RGN_HANDLE);
        g_elevator_panel_created = TD_FALSE;
    }
    g_elevator_frame_width = 0;
    g_elevator_frame_height = 0;
    elevator_osd_reset_layout();
}

int elevator_osd_render_panel(const ot_video_frame_info *frame, const elevator_count_stats *stats,
    const elevator_parse_result *render_result, elevator_review_surface surface)
{
    ot_rgn_canvas_info canvas_info;
    ot_vgs_task_attr task_attr;
    ot_vgs_osd osd_attr;
    ot_vgs_handle handle = -1;
    uint16_t *pixels;
    uint32_t stride_pixels;
    char text[64];
    int ret;

    if (frame == NULL || stats == NULL || g_elevator_panel_created == TD_FALSE) {
        return TD_FAILURE;
    }

    memset(&canvas_info, 0, sizeof(canvas_info));
    ret = ss_mpi_rgn_get_canvas_info(ELEVATOR_PANEL_RGN_HANDLE, &canvas_info);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    pixels = (uint16_t *)canvas_info.virt_addr;
    stride_pixels = canvas_info.stride / sizeof(uint16_t);
    elevator_osd_clear_canvas(pixels, stride_pixels, g_elevator_panel_width, g_elevator_panel_height);
    if (elevator_osd_format_panel_text(text, sizeof(text), stats, render_result, surface) != 0) {
        return TD_FAILURE;
    }
    elevator_osd_draw_string(pixels, stride_pixels, g_elevator_panel_width,
        g_elevator_panel_height, g_elevator_panel_padding_x, g_elevator_panel_padding_y, text);

    ret = ss_mpi_rgn_update_canvas(ELEVATOR_PANEL_RGN_HANDLE);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    memset(&task_attr, 0, sizeof(task_attr));
    memcpy(&task_attr.img_in, frame, sizeof(*frame));
    memcpy(&task_attr.img_out, frame, sizeof(*frame));

    memset(&osd_attr, 0, sizeof(osd_attr));
    osd_attr.rect.x = 0;
    osd_attr.rect.y = 0;
    osd_attr.rect.width = g_elevator_panel_width;
    osd_attr.rect.height = g_elevator_panel_height;
    osd_attr.bg_color = ELEVATOR_PANEL_BG_COLOR;
    osd_attr.pixel_format = OT_PIXEL_FORMAT_ARGB_1555;
    osd_attr.phys_addr = canvas_info.phys_addr;
    osd_attr.stride = canvas_info.stride;
    osd_attr.fg_alpha = 255;
    osd_attr.bg_alpha = 255;
    osd_attr.osd_inverted_color = OT_VGS_OSD_INVERTED_COLOR_NONE;

    ret = ss_mpi_vgs_begin_job(&handle);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    ret = ss_mpi_vgs_add_osd_task(handle, &task_attr, &osd_attr, 1);
    if (ret == TD_SUCCESS) {
        ret = ss_mpi_vgs_end_job(handle);
    } else {
        ss_mpi_vgs_cancel_job(handle);
    }
    return ret;
}

int elevator_osd_render_scores(const ot_video_frame_info *frame,
    ot_sample_svp_rect_info *rect_info, const elevator_parse_result *result)
{
    td_u16 saved_num;
    uint32_t width;
    uint32_t height;
    size_t idx;
    size_t limit;
    int ret;

    if (frame == NULL || rect_info == NULL || result == NULL) {
        return TD_FAILURE;
    }
    if (rect_info->num == 0 || result->detection_count == 0) {
        return TD_SUCCESS;
    }

    width = g_elevator_frame_width != 0 ? g_elevator_frame_width : frame->video_frame.width;
    height = g_elevator_frame_height != 0 ? g_elevator_frame_height : frame->video_frame.height;
    limit = rect_info->num < result->detection_count ? rect_info->num : result->detection_count;
    if (limit > ELEVATOR_MAX_DETECTIONS) {
        limit = ELEVATOR_MAX_DETECTIONS;
    }

    memset(g_elevator_score_osd, 0, limit * sizeof(g_elevator_score_osd[0]));
    for (idx = 0; idx < limit; ++idx) {
        uint32_t score_percent = result->detections[idx].score_percent;
        rect_info->ids[idx] = score_percent > 99U ? 99U : score_percent;
    }

    saved_num = rect_info->num;
    rect_info->num = (td_u16)limit;
    ret = sample_common_svp_vgs_fill_tracker_id(frame, rect_info, width, height, g_elevator_score_osd);
    rect_info->num = saved_num;
    return ret;
}
