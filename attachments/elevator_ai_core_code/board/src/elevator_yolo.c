#include "elevator_yolo.h"

#include <time.h>
#include <errno.h>
#include <pthread.h>
#include <stdlib.h>
#include <stdio.h>
#include <strings.h>
#include <string.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <unistd.h>

#include "elevator_batch.h"
#include "elevator_osd.h"
#include "elevator_postprocess.h"
#include "rtsp_demo.h"
#include "sample_comm.h"
#include "sample_common_svp.h"
#include "sample_common_svp_npu.h"
#include "sample_common_svp_npu_model.h"
#include "ss_mpi_ive.h"
#include "ss_mpi_sys_mem.h"
#include "ss_mpi_vgs.h"
#include "svp_acl.h"
#include "svp_acl_mdl.h"

#define ELEVATOR_MODEL_INDEX 0
#define ELEVATOR_OUTPUT_COUNT_NAME "output0"
#define ELEVATOR_OUTPUT_ROI_NAME "output0_"
#define ELEVATOR_OUTPUT_COUNT_NAME_FALLBACK "output"
#define ELEVATOR_OUTPUT_ROI_NAME_FALLBACK "output_"
#define ELEVATOR_THRESHOLD_INPUT_NAME "rpn_data"
#define ELEVATOR_THREAD_TIMEOUT_MS 1000
#define ELEVATOR_FIRST_FRAME_LOG_INTERVAL 5
#define ELEVATOR_BATCH_FIRST_FRAME_MAX_RETRIES 30
#define ELEVATOR_FILE_DRAIN_POLL_US 100000
#define ELEVATOR_FILE_DRAIN_STABLE_POLLS 3
#define ELEVATOR_FILE_DRAIN_TIMEOUT_MS 15000
#define ELEVATOR_FILE_DRAIN_MAX_WAIT_MS 120000
#define ELEVATOR_OUTPUT_ROI_PLANES 6
#define ELEVATOR_DEFAULT_DEV_ID 0
#define ELEVATOR_ACTIVE_VPSS_CHN_NUM 2
#define ELEVATOR_MODEL_NMS_THRESHOLD 0.90f
#define ELEVATOR_BATCH_IOU_THRESHOLD 0.50f
#define ELEVATOR_JPEG_VENC_CHN 1
#define ELEVATOR_PERSON_HOLD_MAX_FRAMES 20U
#define ELEVATOR_PERSON_HOLD_MAX_MS 800ULL

typedef enum {
    ELEVATOR_OUTPUT_KIND_COUNT = 0,
    ELEVATOR_OUTPUT_KIND_ROI = 1,
} elevator_output_kind;

typedef struct {
    td_bool resolved;
    size_t output_idx;
    char requested_name[SAMPLE_SVP_NPU_MAX_NAME_LEN];
    char resolved_name[SAMPLE_SVP_NPU_MAX_NAME_LEN];
} elevator_output_binding;

typedef struct {
    td_bool active;
    td_bool jpeg_encoder_started;
    td_bool frame_saved;
    td_bool frame_loop_entered;
    td_bool used_fallback;
    td_s32 last_ret;
    td_u32 frame_width;
    td_u32 frame_height;
    char output_path[ELEVATOR_PATH_MAX];
    elevator_parse_result parse_result;
} elevator_batch_runtime;

typedef struct {
    td_bool active;
    FILE *counts_stream;
    FILE *detections_stream;
    char output_dir[ELEVATOR_PATH_MAX];
    char counts_path[ELEVATOR_PATH_MAX];
    char detections_path[ELEVATOR_PATH_MAX];
    char summary_path[ELEVATOR_PATH_MAX];
    uint64_t frame_count;
    uint64_t first_timestamp_ms;
    uint64_t last_timestamp_ms;
    uint32_t min_person_count;
    uint32_t max_person_count;
    uint32_t min_smoothed_person_count;
    uint32_t max_smoothed_person_count;
    uint32_t min_raw_person_count;
    uint32_t max_raw_person_count;
    uint32_t min_confirmed_track_person_count;
    uint32_t max_confirmed_track_person_count;
    uint32_t min_tentative_person_count;
    uint32_t max_tentative_person_count;
    uint32_t min_held_person_count;
    uint32_t max_held_person_count;
    uint32_t min_mature_confirmed_person_count;
    uint32_t max_mature_confirmed_person_count;
    uint32_t min_mature_held_person_count;
    uint32_t max_mature_held_person_count;
    uint32_t min_public_person_count_from_mature_carry;
    uint32_t max_public_person_count_from_mature_carry;
    uint32_t min_ebike_count;
    uint32_t max_ebike_count;
    double sum_person_count;
    double sum_smoothed_person_count;
    double sum_raw_person_count;
    double sum_confirmed_track_person_count;
    double sum_tentative_person_count;
    double sum_held_person_count;
    double sum_mature_confirmed_person_count;
    double sum_mature_held_person_count;
    double sum_public_person_count_from_mature_carry;
    double sum_ebike_count;
    double sum_smoothed_ebike_count;
    elevator_frame_timing sum_timing_ms;
} elevator_file_metrics_runtime;

static td_bool g_elevator_thread_stop = TD_FALSE;
static td_bool g_elevator_terminate_signal = TD_FALSE;
static pthread_t g_elevator_thread = 0;
static pthread_t g_elevator_vdec_thread = 0;
static td_s32 g_elevator_dev_id = ELEVATOR_DEFAULT_DEV_ID;
static td_void *g_elevator_vb_virt_addr = TD_NULL;
static ot_vb_pool_info g_elevator_vb_pool_info = {0};
static sample_svp_npu_task_info g_elevator_task = {0};
static elevator_runtime_config g_elevator_config;
static elevator_smoother g_elevator_smoother;
static elevator_temporal_hold g_elevator_temporal_hold;
static elevator_person_tracker g_elevator_person_tracker;
static elevator_ebike_tracker g_elevator_ebike_tracker;
static ot_sample_svp_rect_info g_elevator_rect_info = {0};
static td_u32 g_elevator_model_input_size = 0;
static td_u32 g_elevator_model_input_stride = 0;
static ot_svp_img g_elevator_bgr_input_image = {0};
static td_phys_addr_t g_elevator_bgr_storage_phys = 0;
static td_void *g_elevator_bgr_storage_virt = TD_NULL;
static td_u32 g_elevator_bgr_storage_size = 0;
static td_bool g_elevator_logged_frame_contract = TD_FALSE;
static elevator_output_binding g_elevator_output_binding[2] = {0};
static ot_payload_type g_elevator_input_payload_type = OT_PT_H264;
static sample_vi_user_frame_info g_elevator_scaled_infer_frame = {0};
static td_bool g_elevator_logged_jpeg_infer_fallback = TD_FALSE;
static elevator_batch_runtime g_elevator_batch_runtime = {0};
static elevator_file_metrics_runtime g_elevator_file_metrics_runtime = {0};
static elevator_parse_result g_elevator_render_result = {0};

static td_void elevator_deinit_task(td_void);
static td_s32 elevator_sync_input_contract(td_void);
static td_s32 elevator_setup_threshold(const elevator_runtime_config *config);
static td_void elevator_file_metrics_close(td_void);
static td_s32 elevator_write_runtime_contract(uint64_t processed_frame_count);

static sample_vo_cfg g_elevator_vo_cfg = {
    .vo_dev = SAMPLE_VO_DEV_UHD,
    .vo_layer = SAMPLE_VO_LAYER_VHD0,
    .vo_intf_type = OT_VO_INTF_BT1120,
    .intf_sync = OT_VO_OUT_1080P60,
    .bg_color = COLOR_RGB_BLACK,
    .pix_format = OT_PIXEL_FORMAT_YVU_SEMIPLANAR_420,
    .disp_rect = {0, 0, 1920, 1080},
    .image_size = {1920, 1080},
    .vo_part_mode = OT_VO_PARTITION_MODE_SINGLE,
    .dis_buf_len = 3,
    .dst_dynamic_range = OT_DYNAMIC_RANGE_SDR8,
    .vo_mode = VO_MODE_1MUX,
    .compress_mode = OT_COMPRESS_MODE_NONE,
};

static ot_sample_svp_media_cfg g_elevator_media_cfg = {
    .svp_switch = {TD_TRUE, TD_TRUE},
    .pic_type = {PIC_1080P, PIC_BUTT, PIC_BUTT},
    .pixel_format = {OT_PIXEL_FORMAT_YVU_SEMIPLANAR_420, OT_PIXEL_FORMAT_YUV_SEMIPLANAR_420,
        OT_PIXEL_FORMAT_YVU_SEMIPLANAR_420},
    .chn_num = ELEVATOR_ACTIVE_VPSS_CHN_NUM,
};

static sample_vdec_attr g_elevator_vdec_cfg = {
    .type = OT_PT_H264,
    .mode = OT_VDEC_SEND_MODE_FRAME,
    .width = _4K_WIDTH,
    .height = _4K_HEIGHT,
    .sample_vdec_video.dec_mode = OT_VIDEO_DEC_MODE_IP,
    .sample_vdec_video.bit_width = OT_DATA_BIT_WIDTH_8,
    .sample_vdec_video.ref_frame_num = 2,
    .display_frame_num = 2,
    .display_mode = OT_VIDEO_DISPLAY_MODE_PREVIEW,
    .frame_buf_cnt = 5,
};

static vdec_thread_param g_elevator_vdec_param = {
    .chn_id = 0,
    .type = OT_PT_H264,
    .stream_mode = OT_VDEC_SEND_MODE_FRAME,
    .interval_time = 1000,
    .pts_init = 0,
    .pts_increase = 0,
    .e_thread_ctrl = THREAD_CTRL_START,
    .circle_send = TD_TRUE,
    .milli_sec = 0,
    .min_buf_size = (_4K_WIDTH * _4K_HEIGHT * 3) >> 1,
    .c_file_path = "./data/input/",
    .c_file_name = "dolls_video.h264",
    .fps = 30,
};

static void elevator_reset_runtime_state(void)
{
    g_elevator_thread_stop = TD_FALSE;
    g_elevator_terminate_signal = TD_FALSE;
    g_elevator_vb_virt_addr = TD_NULL;
    g_elevator_model_input_size = 0;
    g_elevator_model_input_stride = 0;
    g_elevator_bgr_storage_phys = 0;
    g_elevator_bgr_storage_virt = TD_NULL;
    g_elevator_bgr_storage_size = 0;
    g_elevator_logged_frame_contract = TD_FALSE;
    g_elevator_input_payload_type = OT_PT_H264;
    g_elevator_logged_jpeg_infer_fallback = TD_FALSE;
    memset(&g_elevator_vb_pool_info, 0, sizeof(g_elevator_vb_pool_info));
    memset(&g_elevator_task, 0, sizeof(g_elevator_task));
    memset(&g_elevator_rect_info, 0, sizeof(g_elevator_rect_info));
    memset(&g_elevator_bgr_input_image, 0, sizeof(g_elevator_bgr_input_image));
    memset(&g_elevator_output_binding, 0, sizeof(g_elevator_output_binding));
    memset(&g_elevator_scaled_infer_frame, 0, sizeof(g_elevator_scaled_infer_frame));
    g_elevator_scaled_infer_frame.vb_blk = OT_VB_INVALID_HANDLE;
    g_elevator_scaled_infer_frame.frame_info.pool_id = OT_VB_INVALID_POOL_ID;
    memset(&g_elevator_batch_runtime, 0, sizeof(g_elevator_batch_runtime));
    elevator_file_metrics_close();
    memset(&g_elevator_file_metrics_runtime, 0, sizeof(g_elevator_file_metrics_runtime));
    memset(&g_elevator_render_result, 0, sizeof(g_elevator_render_result));
    memset(&g_elevator_temporal_hold, 0, sizeof(g_elevator_temporal_hold));
    memset(&g_elevator_person_tracker, 0, sizeof(g_elevator_person_tracker));
    g_elevator_media_cfg.svp_switch.is_venc_open = TD_TRUE;
    g_elevator_media_cfg.svp_switch.is_vo_open = TD_TRUE;
    g_elevator_media_cfg.chn_num = ELEVATOR_ACTIVE_VPSS_CHN_NUM;
    g_elevator_media_cfg.pic_type[0] = PIC_1080P;
    g_elevator_media_cfg.pic_type[1] = PIC_BUTT;
    g_elevator_media_cfg.pic_type[2] = PIC_BUTT;
    g_elevator_media_cfg.pixel_format[0] = OT_PIXEL_FORMAT_YVU_SEMIPLANAR_420;
    g_elevator_media_cfg.pixel_format[1] = OT_PIXEL_FORMAT_YUV_SEMIPLANAR_420;
    g_elevator_media_cfg.pixel_format[2] = OT_PIXEL_FORMAT_YVU_SEMIPLANAR_420;
    g_elevator_vdec_cfg.type = OT_PT_H264;
    g_elevator_vdec_cfg.mode = OT_VDEC_SEND_MODE_FRAME;
    g_elevator_vdec_cfg.width = _4K_WIDTH;
    g_elevator_vdec_cfg.height = _4K_HEIGHT;
    g_elevator_vdec_cfg.sample_vdec_video.dec_mode = OT_VIDEO_DEC_MODE_IP;
    g_elevator_vdec_cfg.sample_vdec_video.bit_width = OT_DATA_BIT_WIDTH_8;
    g_elevator_vdec_cfg.sample_vdec_video.ref_frame_num = 2;
    g_elevator_vdec_cfg.display_frame_num = 2;
    g_elevator_vdec_cfg.display_mode = OT_VIDEO_DISPLAY_MODE_PREVIEW;
    g_elevator_vdec_cfg.frame_buf_cnt = 5;
    g_elevator_vdec_param.type = OT_PT_H264;
    g_elevator_vdec_param.circle_send = TD_TRUE;
    g_elevator_vdec_param.min_buf_size = (_4K_WIDTH * _4K_HEIGHT * 3) >> 1;
    snprintf(g_elevator_vdec_param.c_file_path, sizeof(g_elevator_vdec_param.c_file_path), "./data/input/");
    snprintf(g_elevator_vdec_param.c_file_name, sizeof(g_elevator_vdec_param.c_file_name), "dolls_video.h264");
}

static const char *elevator_pixel_format_name(ot_pixel_format pixel_format)
{
    switch (pixel_format) {
        case OT_PIXEL_FORMAT_YVU_SEMIPLANAR_420:
            return "YVU420SP";
        case OT_PIXEL_FORMAT_YUV_SEMIPLANAR_420:
            return "YUV420SP";
        case OT_PIXEL_FORMAT_YVU_SEMIPLANAR_422:
            return "YVU422SP";
        case OT_PIXEL_FORMAT_YUV_SEMIPLANAR_422:
            return "YUV422SP";
        case OT_PIXEL_FORMAT_YUV_400:
            return "YUV400";
        case OT_PIXEL_FORMAT_BGR_888_PLANAR:
            return "BGR888P";
        default:
            return "UNKNOWN";
    }
}

static td_u32 elevator_get_stride_or_default(const td_u32 *stride, td_u32 idx, td_u32 fallback)
{
    if (stride == TD_NULL) {
        return fallback;
    }

    return stride[idx] != 0 ? stride[idx] : fallback;
}

static td_u32 elevator_align_up(td_u32 value, td_u32 align)
{
    if (align == 0) {
        return value;
    }
    return (value + align - 1U) / align * align;
}

static td_void elevator_release_scaled_infer_frame(td_void)
{
    if (g_elevator_scaled_infer_frame.vb_blk != OT_VB_INVALID_HANDLE &&
        g_elevator_scaled_infer_frame.frame_info.pool_id != OT_VB_INVALID_POOL_ID) {
        sample_comm_vi_release_frame_blk(&g_elevator_scaled_infer_frame, 1);
    }
    memset(&g_elevator_scaled_infer_frame, 0, sizeof(g_elevator_scaled_infer_frame));
    g_elevator_scaled_infer_frame.vb_blk = OT_VB_INVALID_HANDLE;
    g_elevator_scaled_infer_frame.frame_info.pool_id = OT_VB_INVALID_POOL_ID;
}

static td_void elevator_release_preprocess_buffer(td_void)
{
    if (g_elevator_bgr_storage_phys != 0 && g_elevator_bgr_storage_virt != TD_NULL) {
        (td_void)ss_mpi_sys_mmz_free(g_elevator_bgr_storage_phys, g_elevator_bgr_storage_virt);
    }
    g_elevator_bgr_storage_phys = 0;
    g_elevator_bgr_storage_virt = TD_NULL;
    g_elevator_bgr_storage_size = 0;
    memset(&g_elevator_bgr_input_image, 0, sizeof(g_elevator_bgr_input_image));
}

static td_s32 elevator_prepare_preprocess_buffer(td_u32 width, td_u32 height)
{
    td_u32 stride;
    td_u32 plane_size;
    td_void *virt_addr = TD_NULL;
    td_s32 ret;

    if (g_elevator_bgr_storage_virt != TD_NULL &&
        g_elevator_bgr_input_image.width == width &&
        g_elevator_bgr_input_image.height == height) {
        return TD_SUCCESS;
    }

    elevator_release_preprocess_buffer();

    stride = elevator_align_up(width, 16);
    plane_size = stride * height;
    g_elevator_bgr_storage_size = plane_size * 3;
    ret = ss_mpi_sys_mmz_alloc(&g_elevator_bgr_storage_phys, &virt_addr,
        "elevator_bgr_input", TD_NULL, g_elevator_bgr_storage_size);
    if (ret != TD_SUCCESS) {
        g_elevator_bgr_storage_phys = 0;
        g_elevator_bgr_storage_size = 0;
        return ret;
    }

    g_elevator_bgr_storage_virt = virt_addr;
    g_elevator_bgr_input_image.type = OT_SVP_IMG_TYPE_U8C3_PLANAR;
    g_elevator_bgr_input_image.width = width;
    g_elevator_bgr_input_image.height = height;
    g_elevator_bgr_input_image.stride[0] = stride;
    g_elevator_bgr_input_image.stride[1] = stride;
    g_elevator_bgr_input_image.stride[2] = stride;

    /* IVE CSC writes RGB planar. Reverse plane addresses so the storage layout becomes B, G, R. */
    g_elevator_bgr_input_image.phys_addr[0] = g_elevator_bgr_storage_phys + (td_phys_addr_t)(plane_size * 2);
    g_elevator_bgr_input_image.phys_addr[1] = g_elevator_bgr_storage_phys + plane_size;
    g_elevator_bgr_input_image.phys_addr[2] = g_elevator_bgr_storage_phys;
    g_elevator_bgr_input_image.virt_addr[0] =
        sample_svp_convert_ptr_to_addr(td_u64, (td_u8 *)g_elevator_bgr_storage_virt + plane_size * 2);
    g_elevator_bgr_input_image.virt_addr[1] =
        sample_svp_convert_ptr_to_addr(td_u64, (td_u8 *)g_elevator_bgr_storage_virt + plane_size);
    g_elevator_bgr_input_image.virt_addr[2] =
        sample_svp_convert_ptr_to_addr(td_u64, g_elevator_bgr_storage_virt);
    return TD_SUCCESS;
}

static td_s32 elevator_build_ive_src_image(const ot_video_frame_info *frame, ot_svp_src_img *src_img)
{
    td_u32 stride1;
    td_u8 *virt0;
    td_u8 *virt1;
    td_uintptr_t offset0;
    td_uintptr_t offset1;

    if (frame == TD_NULL || src_img == TD_NULL) {
        return TD_FAILURE;
    }

    if (frame->video_frame.pixel_format != OT_PIXEL_FORMAT_YUV_SEMIPLANAR_420 &&
        frame->video_frame.pixel_format != OT_PIXEL_FORMAT_YVU_SEMIPLANAR_420) {
        fprintf(stderr, "unsupported preprocess source pixel format: %s(%d)\n",
            elevator_pixel_format_name(frame->video_frame.pixel_format), frame->video_frame.pixel_format);
        return TD_FAILURE;
    }

    memset(src_img, 0, sizeof(*src_img));
    stride1 = elevator_get_stride_or_default(frame->video_frame.stride, 1, frame->video_frame.stride[0]);
    if (frame->video_frame.virt_addr[0] != 0 && frame->video_frame.virt_addr[1] != 0) {
        virt0 = sample_svp_convert_addr_to_ptr(td_u8, frame->video_frame.virt_addr[0]);
        virt1 = sample_svp_convert_addr_to_ptr(td_u8, frame->video_frame.virt_addr[1]);
    } else {
        if (g_elevator_vb_virt_addr == TD_NULL) {
            fprintf(stderr, "video frame virt addr unavailable and vb pool is not mapped\n");
            return TD_FAILURE;
        }
        offset0 = (td_uintptr_t)(frame->video_frame.phys_addr[0] - g_elevator_vb_pool_info.pool_phy_addr);
        offset1 = (td_uintptr_t)(frame->video_frame.phys_addr[1] - g_elevator_vb_pool_info.pool_phy_addr);
        virt0 = (td_u8 *)g_elevator_vb_virt_addr + offset0;
        virt1 = (td_u8 *)g_elevator_vb_virt_addr + offset1;
    }

    src_img->type = OT_SVP_IMG_TYPE_YUV420SP;
    src_img->width = frame->video_frame.width;
    src_img->height = frame->video_frame.height;
    src_img->stride[0] = frame->video_frame.stride[0];
    src_img->stride[1] = stride1;
    src_img->phys_addr[0] = frame->video_frame.phys_addr[0];
    src_img->phys_addr[1] = frame->video_frame.phys_addr[1];
    src_img->virt_addr[0] = sample_svp_convert_ptr_to_addr(td_u64, virt0);
    src_img->virt_addr[1] = sample_svp_convert_ptr_to_addr(td_u64, virt1);
    return TD_SUCCESS;
}

static td_s32 elevator_prepare_scaled_infer_frame(const ot_video_frame_info *src_frame, td_u32 width, td_u32 height)
{
    sample_vi_get_frame_vb_cfg vb_cfg;
    ot_pixel_format pixel_format;

    if (src_frame == TD_NULL || width == 0 || height == 0) {
        return TD_FAILURE;
    }

    pixel_format = src_frame->video_frame.pixel_format;
    if (pixel_format != OT_PIXEL_FORMAT_YVU_SEMIPLANAR_420 &&
        pixel_format != OT_PIXEL_FORMAT_YUV_SEMIPLANAR_420) {
        fprintf(stderr, "unsupported scaled infer pixel format: %s(%d)\n",
            elevator_pixel_format_name(pixel_format), pixel_format);
        return TD_FAILURE;
    }

    if (g_elevator_scaled_infer_frame.vb_blk != OT_VB_INVALID_HANDLE &&
        g_elevator_scaled_infer_frame.frame_info.video_frame.width == width &&
        g_elevator_scaled_infer_frame.frame_info.video_frame.height == height &&
        g_elevator_scaled_infer_frame.frame_info.video_frame.pixel_format == pixel_format) {
        return TD_SUCCESS;
    }

    elevator_release_scaled_infer_frame();
    memset(&vb_cfg, 0, sizeof(vb_cfg));
    vb_cfg.size.width = width;
    vb_cfg.size.height = height;
    vb_cfg.pixel_format = pixel_format;
    vb_cfg.video_format = OT_VIDEO_FORMAT_LINEAR;
    vb_cfg.compress_mode = OT_COMPRESS_MODE_NONE;
    vb_cfg.dynamic_range = src_frame->video_frame.dynamic_range;
    return sample_comm_vi_get_frame_blk(&vb_cfg, &g_elevator_scaled_infer_frame, 1);
}

static td_s32 elevator_scale_video_frame(const ot_video_frame_info *src_frame, ot_video_frame_info *dst_frame)
{
    ot_vgs_handle handle;
    ot_vgs_task_attr task_attr;
    td_s32 ret;

    if (src_frame == TD_NULL || dst_frame == TD_NULL) {
        return TD_FAILURE;
    }

    ret = ss_mpi_vgs_begin_job(&handle);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    memset(&task_attr, 0, sizeof(task_attr));
    if (memcpy_s(&task_attr.img_in, sizeof(task_attr.img_in), src_frame, sizeof(*src_frame)) != EOK ||
        memcpy_s(&task_attr.img_out, sizeof(task_attr.img_out), dst_frame, sizeof(*dst_frame)) != EOK) {
        (td_void)ss_mpi_vgs_cancel_job(handle);
        return TD_FAILURE;
    }

    ret = ss_mpi_vgs_add_scale_task(handle, &task_attr, OT_VGS_SCALE_COEF_NORM);
    if (ret != TD_SUCCESS) {
        (td_void)ss_mpi_vgs_cancel_job(handle);
        return ret;
    }

    ret = ss_mpi_vgs_end_job(handle);
    if (ret != TD_SUCCESS) {
        (td_void)ss_mpi_vgs_cancel_job(handle);
    }
    return ret;
}

static td_s32 elevator_prepare_infer_frame(const ot_video_frame_info *ext_frame,
    const ot_video_frame_info *base_frame, const ot_video_frame_info **infer_frame)
{
    td_s32 ret;

    if (infer_frame == TD_NULL) {
        return TD_FAILURE;
    }

    if (ext_frame != TD_NULL) {
        *infer_frame = ext_frame;
        return TD_SUCCESS;
    }

    if (base_frame == TD_NULL) {
        return TD_FAILURE;
    }

    ret = elevator_prepare_scaled_infer_frame(base_frame,
        g_elevator_media_cfg.pic_size[1].width, g_elevator_media_cfg.pic_size[1].height);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "scaled infer frame alloc failed: %#x\n", ret);
        return ret;
    }

    ret = elevator_scale_video_frame(base_frame, &g_elevator_scaled_infer_frame.frame_info);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "jpeg infer fallback scale failed: %#x\n", ret);
        return ret;
    }

    if (g_elevator_logged_jpeg_infer_fallback == TD_FALSE) {
        printf("jpeg infer fallback active: scale base frame %ux%u -> %ux%u for inference\n",
            base_frame->video_frame.width, base_frame->video_frame.height,
            g_elevator_scaled_infer_frame.frame_info.video_frame.width,
            g_elevator_scaled_infer_frame.frame_info.video_frame.height);
        fflush(stdout);
        g_elevator_logged_jpeg_infer_fallback = TD_TRUE;
    }

    *infer_frame = &g_elevator_scaled_infer_frame.frame_info;
    return TD_SUCCESS;
}

static td_s32 elevator_preprocess_frame_to_bgr(const ot_video_frame_info *frame)
{
    ot_ive_handle handle;
    ot_svp_src_img src_img;
    ot_ive_csc_ctrl ctrl = {OT_IVE_CSC_MODE_PIC_BT601_YUV_TO_RGB};
    td_bool is_finish = TD_FALSE;
    td_s32 ret;

    ret = elevator_prepare_preprocess_buffer(frame->video_frame.width, frame->video_frame.height);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "preprocess buffer alloc failed: %#x\n", ret);
        return ret;
    }

    ret = elevator_build_ive_src_image(frame, &src_img);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    ret = ss_mpi_ive_csc(&handle, &src_img, &g_elevator_bgr_input_image, &ctrl, TD_TRUE);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "ive csc failed: %#x\n", ret);
        return ret;
    }

    ret = ss_mpi_ive_query(handle, &is_finish, TD_TRUE);
    while (ret == OT_ERR_IVE_QUERY_TIMEOUT) {
        usleep(100);
        ret = ss_mpi_ive_query(handle, &is_finish, TD_TRUE);
    }
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "ive query failed: %#x\n", ret);
        return ret;
    }
    return TD_SUCCESS;
}

static int elevator_detect_payload_type(const char *path, ot_payload_type *payload_type)
{
    const char *ext = strrchr(path, '.');

    if (payload_type == NULL) {
        return TD_FAILURE;
    }

    *payload_type = OT_PT_H264;
    if (ext == NULL) {
        return TD_SUCCESS;
    }
    if (strcasecmp(ext, ".jpg") == 0 || strcasecmp(ext, ".jpeg") == 0) {
        *payload_type = OT_PT_JPEG;
        return TD_SUCCESS;
    }
    if (strcasecmp(ext, ".mjpg") == 0 || strcasecmp(ext, ".mjpeg") == 0) {
        *payload_type = OT_PT_MJPEG;
        return TD_SUCCESS;
    }
    if (strcasecmp(ext, ".265") == 0 || strcasecmp(ext, ".h265") == 0 || strcasecmp(ext, ".hevc") == 0) {
        *payload_type = OT_PT_H265;
    }
    return TD_SUCCESS;
}

static td_bool elevator_is_jpeg_payload(ot_payload_type payload_type)
{
    return (payload_type == OT_PT_JPEG || payload_type == OT_PT_MJPEG) ? TD_TRUE : TD_FALSE;
}

static int elevator_parse_jpeg_dimensions(const char *path, td_u32 *width, td_u32 *height)
{
    FILE *stream = NULL;
    int marker_prefix;
    int marker;

    if (path == NULL || width == NULL || height == NULL) {
        return TD_FAILURE;
    }

    stream = fopen(path, "rb");
    if (stream == NULL) {
        return TD_FAILURE;
    }

    if (fgetc(stream) != 0xFF || fgetc(stream) != 0xD8) {
        fclose(stream);
        return TD_FAILURE;
    }

    while ((marker_prefix = fgetc(stream)) != EOF) {
        td_u32 segment_len;
        td_u32 parsed_width;
        td_u32 parsed_height;

        if (marker_prefix != 0xFF) {
            continue;
        }

        do {
            marker = fgetc(stream);
        } while (marker == 0xFF);

        if (marker == EOF) {
            break;
        }

        if (marker == 0xD9 || marker == 0xDA) {
            break;
        }

        if ((marker >= 0xD0 && marker <= 0xD7) || marker == 0x01) {
            continue;
        }

        segment_len = ((td_u32)fgetc(stream) << 8) | (td_u32)fgetc(stream);
        if (segment_len < 2) {
            break;
        }

        if ((marker >= 0xC0 && marker <= 0xCF) && marker != 0xC4 && marker != 0xC8 && marker != 0xCC) {
            (void)fgetc(stream); /* precision */
            parsed_height = ((td_u32)fgetc(stream) << 8) | (td_u32)fgetc(stream);
            parsed_width = ((td_u32)fgetc(stream) << 8) | (td_u32)fgetc(stream);
            fclose(stream);
            if (parsed_width == 0 || parsed_height == 0) {
                return TD_FAILURE;
            }
            *width = parsed_width;
            *height = parsed_height;
            return TD_SUCCESS;
        }

        if (fseek(stream, (long)segment_len - 2L, SEEK_CUR) != 0) {
            break;
        }
    }

    fclose(stream);
    return TD_FAILURE;
}

static int elevator_split_input_path(const char *path, char *dirbuf, size_t dirbuf_size,
    char *filebuf, size_t filebuf_size)
{
    const char *slash;
    size_t dirlen;
    size_t filelen;

    if (path == NULL || dirbuf == NULL || filebuf == NULL) {
        return TD_FAILURE;
    }

    slash = strrchr(path, '/');
    if (slash == NULL) {
        filelen = strlen(path);
        if (filelen + 1 > filebuf_size) {
            return TD_FAILURE;
        }
        snprintf(dirbuf, dirbuf_size, "./");
        snprintf(filebuf, filebuf_size, "%s", path);
        return TD_SUCCESS;
    }

    dirlen = (size_t)(slash - path) + 1;
    if (dirlen >= dirbuf_size) {
        return TD_FAILURE;
    }
    filelen = strlen(slash + 1);
    if (filelen + 1 > filebuf_size) {
        return TD_FAILURE;
    }
    memcpy(dirbuf, path, dirlen);
    dirbuf[dirlen] = '\0';
    snprintf(filebuf, filebuf_size, "%s", slash + 1);
    return TD_SUCCESS;
}

static td_void elevator_request_media_stop(td_void)
{
    g_elevator_thread_stop = TD_TRUE;
}

void elevator_request_stop(void)
{
    g_elevator_terminate_signal = TD_TRUE;
    elevator_request_media_stop();
}

static td_bool elevator_is_batch_mode(td_void)
{
    return g_elevator_config.mode == ELEVATOR_RUN_MODE_BATCH ? TD_TRUE : TD_FALSE;
}

static td_bool elevator_should_log_first_frame_wait(td_bool batch_mode)
{
    return (batch_mode == TD_TRUE || g_elevator_config.mode == ELEVATOR_RUN_MODE_FILE) ? TD_TRUE : TD_FALSE;
}

static td_bool elevator_path_is_readable_file(const char *path)
{
    struct stat st;

    if (path == TD_NULL || path[0] == '\0') {
        return TD_FALSE;
    }
    if (access(path, R_OK) != 0) {
        return TD_FALSE;
    }
    if (stat(path, &st) != 0) {
        return TD_FALSE;
    }
    return S_ISREG(st.st_mode) ? TD_TRUE : TD_FALSE;
}

static td_s32 elevator_get_executable_dir(char *dirbuf, size_t dirbuf_size)
{
    ssize_t len;
    char exe_path[ELEVATOR_PATH_MAX];
    char *slash;

    if (dirbuf == TD_NULL || dirbuf_size == 0) {
        return TD_FAILURE;
    }

    len = readlink("/proc/self/exe", exe_path, sizeof(exe_path) - 1);
    if (len <= 0 || (size_t)len >= sizeof(exe_path)) {
        return TD_FAILURE;
    }
    exe_path[len] = '\0';
    slash = strrchr(exe_path, '/');
    if (slash == TD_NULL) {
        return TD_FAILURE;
    }
    *slash = '\0';
    if (snprintf(dirbuf, dirbuf_size, "%s", exe_path) >= (int)dirbuf_size) {
        return TD_FAILURE;
    }
    return TD_SUCCESS;
}

static td_s32 elevator_join_path(char *dst, size_t dst_size, const char *base, const char *suffix)
{
    const int needs_slash = (base != TD_NULL && base[0] != '\0' && base[strlen(base) - 1] != '/') ? 1 : 0;

    if (dst == TD_NULL || base == TD_NULL || suffix == TD_NULL) {
        return TD_FAILURE;
    }
    if (snprintf(dst, dst_size, "%s%s%s", base, needs_slash ? "/" : "", suffix) >= (int)dst_size) {
        return TD_FAILURE;
    }
    return TD_SUCCESS;
}

static td_s32 elevator_resolve_model_path(const char *configured_path, char *resolved_path,
    size_t resolved_path_size)
{
    char exe_dir[ELEVATOR_PATH_MAX];
    char candidate[ELEVATOR_PATH_MAX];
    size_t idx;
    const char *fallback_suffixes[] = {
        "yolov8.om",
        "data/model/yolov8.om",
    };

    if (resolved_path == TD_NULL || resolved_path_size == 0 || configured_path == TD_NULL || configured_path[0] == '\0') {
        return TD_FAILURE;
    }

    if (elevator_path_is_readable_file(configured_path) == TD_TRUE) {
        if (snprintf(resolved_path, resolved_path_size, "%s", configured_path) >= (int)resolved_path_size) {
            return TD_FAILURE;
        }
        return TD_SUCCESS;
    }

    if (elevator_get_executable_dir(exe_dir, sizeof(exe_dir)) == TD_SUCCESS) {
        for (idx = 0; idx < sizeof(fallback_suffixes) / sizeof(fallback_suffixes[0]); ++idx) {
            if (elevator_join_path(candidate, sizeof(candidate), exe_dir, fallback_suffixes[idx]) != TD_SUCCESS) {
                continue;
            }
            if (elevator_path_is_readable_file(candidate) == TD_TRUE) {
                if (snprintf(resolved_path, resolved_path_size, "%s", candidate) >= (int)resolved_path_size) {
                    return TD_FAILURE;
                }
                return TD_SUCCESS;
            }
        }
    }

    if (snprintf(resolved_path, resolved_path_size, "%s", configured_path) >= (int)resolved_path_size) {
        return TD_FAILURE;
    }
    return TD_FAILURE;
}

static double elevator_now_ms(td_void)
{
    struct timespec ts;

    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        return 0.0;
    }
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
}

static double elevator_elapsed_since_ms(double started_ms)
{
    double now_ms = elevator_now_ms();

    return now_ms >= started_ms ? now_ms - started_ms : 0.0;
}

static void elevator_timing_add(elevator_frame_timing *dst, const elevator_frame_timing *src)
{
    if (dst == TD_NULL || src == TD_NULL) {
        return;
    }

    dst->frame_proc_ms += src->frame_proc_ms;
    dst->prepare_ms += src->prepare_ms;
    dst->preprocess_ms += src->preprocess_ms;
    dst->input_update_ms += src->input_update_ms;
    dst->model_execute_ms += src->model_execute_ms;
    dst->output_fetch_ms += src->output_fetch_ms;
    dst->postprocess_ms += src->postprocess_ms;
    dst->temporal_ms += src->temporal_ms;
    dst->render_prepare_ms += src->render_prepare_ms;
    dst->render_ms += src->render_ms;
    dst->osd_ms += src->osd_ms;
}

static void elevator_timing_average(elevator_frame_timing *dst, const elevator_frame_timing *src, uint64_t count)
{
    if (dst == TD_NULL || src == TD_NULL || count == 0) {
        return;
    }

    dst->frame_proc_ms = src->frame_proc_ms / (double)count;
    dst->prepare_ms = src->prepare_ms / (double)count;
    dst->preprocess_ms = src->preprocess_ms / (double)count;
    dst->input_update_ms = src->input_update_ms / (double)count;
    dst->model_execute_ms = src->model_execute_ms / (double)count;
    dst->output_fetch_ms = src->output_fetch_ms / (double)count;
    dst->postprocess_ms = src->postprocess_ms / (double)count;
    dst->temporal_ms = src->temporal_ms / (double)count;
    dst->render_prepare_ms = src->render_prepare_ms / (double)count;
    dst->render_ms = src->render_ms / (double)count;
    dst->osd_ms = src->osd_ms / (double)count;
}

static int elevator_write_timing_json(FILE *stream, const elevator_frame_timing *timing)
{
    if (stream == TD_NULL || timing == TD_NULL) {
        return -1;
    }

    return fprintf(stream,
        "{\"frame_proc_ms\":%.3f,\"prepare_ms\":%.3f,\"preprocess_ms\":%.3f,"
        "\"input_update_ms\":%.3f,\"model_execute_ms\":%.3f,\"output_fetch_ms\":%.3f,"
        "\"postprocess_ms\":%.3f,\"temporal_ms\":%.3f,\"render_prepare_ms\":%.3f,"
        "\"render_ms\":%.3f,\"osd_ms\":%.3f}",
        timing->frame_proc_ms, timing->prepare_ms, timing->preprocess_ms,
        timing->input_update_ms, timing->model_execute_ms, timing->output_fetch_ms,
        timing->postprocess_ms, timing->temporal_ms, timing->render_prepare_ms,
        timing->render_ms, timing->osd_ms) < 0 ? -1 : 0;
}

static td_s32 elevator_mkdir_p(const char *path)
{
    char buffer[ELEVATOR_PATH_MAX];
    size_t idx;

    if (path == TD_NULL || path[0] == '\0') {
        return TD_FAILURE;
    }
    if (snprintf(buffer, sizeof(buffer), "%s", path) >= (int)sizeof(buffer)) {
        return TD_FAILURE;
    }

    for (idx = 1; buffer[idx] != '\0'; ++idx) {
        if (buffer[idx] != '/') {
            continue;
        }
        buffer[idx] = '\0';
        if (mkdir(buffer, 0755) != 0 && errno != EEXIST) {
            return TD_FAILURE;
        }
        buffer[idx] = '/';
    }

    if (mkdir(buffer, 0755) != 0 && errno != EEXIST) {
        return TD_FAILURE;
    }
    return TD_SUCCESS;
}

static td_s32 elevator_file_metrics_open(const char *output_dir)
{
    elevator_file_metrics_runtime *metrics = &g_elevator_file_metrics_runtime;

    if (output_dir == TD_NULL || output_dir[0] == '\0') {
        return TD_SUCCESS;
    }
    if (snprintf(metrics->output_dir, sizeof(metrics->output_dir), "%s", output_dir) >= (int)sizeof(metrics->output_dir)) {
        return TD_FAILURE;
    }
    if (elevator_mkdir_p(metrics->output_dir) != TD_SUCCESS) {
        return TD_FAILURE;
    }
    if (snprintf(metrics->counts_path, sizeof(metrics->counts_path), "%s/frame_counts.csv", metrics->output_dir) >=
            (int)sizeof(metrics->counts_path) ||
        snprintf(metrics->detections_path, sizeof(metrics->detections_path), "%s/frame_detections.jsonl",
            metrics->output_dir) >= (int)sizeof(metrics->detections_path) ||
        snprintf(metrics->summary_path, sizeof(metrics->summary_path), "%s/video_metrics_summary.json",
            metrics->output_dir) >= (int)sizeof(metrics->summary_path)) {
        return TD_FAILURE;
    }

    metrics->counts_stream = fopen(metrics->counts_path, "w");
    metrics->detections_stream = fopen(metrics->detections_path, "w");
    if (metrics->counts_stream == TD_NULL || metrics->detections_stream == TD_NULL) {
        elevator_file_metrics_close();
        return TD_FAILURE;
    }

    fputs("frame_index,timestamp_ms,elapsed_ms,person_count,raw_person_count,confirmed_track_person_count,"
          "tentative_person_count,held_person_count,mature_confirmed_person_count,mature_held_person_count,"
          "public_person_count_from_mature_carry,ebike_count,smoothed_person_count,"
          "smoothed_ebike_count,fps,detection_count,frame_proc_ms,prepare_ms,preprocess_ms,input_update_ms,"
          "model_execute_ms,output_fetch_ms,postprocess_ms,temporal_ms,render_prepare_ms,render_ms,osd_ms\n",
          metrics->counts_stream);
    fflush(metrics->counts_stream);
    metrics->active = TD_TRUE;
    return TD_SUCCESS;
}

static td_void elevator_file_metrics_note_frame(const elevator_parse_result *result, uint64_t timestamp_ms)
{
    elevator_file_metrics_runtime *metrics = &g_elevator_file_metrics_runtime;
    size_t idx;
    double elapsed_ms;

    if (metrics->active == TD_FALSE || result == TD_NULL ||
        metrics->counts_stream == TD_NULL || metrics->detections_stream == TD_NULL) {
        return;
    }

    if (metrics->frame_count == 0) {
        metrics->first_timestamp_ms = timestamp_ms;
        metrics->min_person_count = result->stats.person_count;
        metrics->max_person_count = result->stats.person_count;
        metrics->min_smoothed_person_count = result->stats.smoothed_person_count;
        metrics->max_smoothed_person_count = result->stats.smoothed_person_count;
        metrics->min_raw_person_count = result->stats.raw_person_count;
        metrics->max_raw_person_count = result->stats.raw_person_count;
        metrics->min_confirmed_track_person_count = result->stats.confirmed_track_person_count;
        metrics->max_confirmed_track_person_count = result->stats.confirmed_track_person_count;
        metrics->min_tentative_person_count = result->stats.tentative_person_count;
        metrics->max_tentative_person_count = result->stats.tentative_person_count;
        metrics->min_held_person_count = result->stats.held_person_count;
        metrics->max_held_person_count = result->stats.held_person_count;
        metrics->min_mature_confirmed_person_count = result->stats.mature_confirmed_person_count;
        metrics->max_mature_confirmed_person_count = result->stats.mature_confirmed_person_count;
        metrics->min_mature_held_person_count = result->stats.mature_held_person_count;
        metrics->max_mature_held_person_count = result->stats.mature_held_person_count;
        metrics->min_public_person_count_from_mature_carry = result->stats.public_person_count_from_mature_carry;
        metrics->max_public_person_count_from_mature_carry = result->stats.public_person_count_from_mature_carry;
        metrics->min_ebike_count = result->stats.ebike_count;
        metrics->max_ebike_count = result->stats.ebike_count;
    } else {
        if (result->stats.person_count < metrics->min_person_count) {
            metrics->min_person_count = result->stats.person_count;
        }
        if (result->stats.person_count > metrics->max_person_count) {
            metrics->max_person_count = result->stats.person_count;
        }
        if (result->stats.smoothed_person_count < metrics->min_smoothed_person_count) {
            metrics->min_smoothed_person_count = result->stats.smoothed_person_count;
        }
        if (result->stats.smoothed_person_count > metrics->max_smoothed_person_count) {
            metrics->max_smoothed_person_count = result->stats.smoothed_person_count;
        }
        if (result->stats.raw_person_count < metrics->min_raw_person_count) {
            metrics->min_raw_person_count = result->stats.raw_person_count;
        }
        if (result->stats.raw_person_count > metrics->max_raw_person_count) {
            metrics->max_raw_person_count = result->stats.raw_person_count;
        }
        if (result->stats.confirmed_track_person_count < metrics->min_confirmed_track_person_count) {
            metrics->min_confirmed_track_person_count = result->stats.confirmed_track_person_count;
        }
        if (result->stats.confirmed_track_person_count > metrics->max_confirmed_track_person_count) {
            metrics->max_confirmed_track_person_count = result->stats.confirmed_track_person_count;
        }
        if (result->stats.tentative_person_count < metrics->min_tentative_person_count) {
            metrics->min_tentative_person_count = result->stats.tentative_person_count;
        }
        if (result->stats.tentative_person_count > metrics->max_tentative_person_count) {
            metrics->max_tentative_person_count = result->stats.tentative_person_count;
        }
        if (result->stats.held_person_count < metrics->min_held_person_count) {
            metrics->min_held_person_count = result->stats.held_person_count;
        }
        if (result->stats.held_person_count > metrics->max_held_person_count) {
            metrics->max_held_person_count = result->stats.held_person_count;
        }
        if (result->stats.mature_confirmed_person_count < metrics->min_mature_confirmed_person_count) {
            metrics->min_mature_confirmed_person_count = result->stats.mature_confirmed_person_count;
        }
        if (result->stats.mature_confirmed_person_count > metrics->max_mature_confirmed_person_count) {
            metrics->max_mature_confirmed_person_count = result->stats.mature_confirmed_person_count;
        }
        if (result->stats.mature_held_person_count < metrics->min_mature_held_person_count) {
            metrics->min_mature_held_person_count = result->stats.mature_held_person_count;
        }
        if (result->stats.mature_held_person_count > metrics->max_mature_held_person_count) {
            metrics->max_mature_held_person_count = result->stats.mature_held_person_count;
        }
        if (result->stats.public_person_count_from_mature_carry <
            metrics->min_public_person_count_from_mature_carry) {
            metrics->min_public_person_count_from_mature_carry = result->stats.public_person_count_from_mature_carry;
        }
        if (result->stats.public_person_count_from_mature_carry >
            metrics->max_public_person_count_from_mature_carry) {
            metrics->max_public_person_count_from_mature_carry = result->stats.public_person_count_from_mature_carry;
        }
        if (result->stats.ebike_count < metrics->min_ebike_count) {
            metrics->min_ebike_count = result->stats.ebike_count;
        }
        if (result->stats.ebike_count > metrics->max_ebike_count) {
            metrics->max_ebike_count = result->stats.ebike_count;
        }
    }

    elapsed_ms = metrics->frame_count == 0 ? 0.0 : (double)(timestamp_ms - metrics->first_timestamp_ms);
    fprintf(metrics->counts_stream,
        "%llu,%llu,%.3f,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%.6f,%zu,"
        "%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f\n",
        (unsigned long long)metrics->frame_count,
        (unsigned long long)timestamp_ms,
        elapsed_ms,
        result->stats.person_count,
        result->stats.raw_person_count,
        result->stats.confirmed_track_person_count,
        result->stats.tentative_person_count,
        result->stats.held_person_count,
        result->stats.mature_confirmed_person_count,
        result->stats.mature_held_person_count,
        result->stats.public_person_count_from_mature_carry,
        result->stats.ebike_count,
        result->stats.smoothed_person_count,
        result->stats.smoothed_ebike_count,
        result->stats.fps,
        result->detection_count,
        result->timing_ms.frame_proc_ms,
        result->timing_ms.prepare_ms,
        result->timing_ms.preprocess_ms,
        result->timing_ms.input_update_ms,
        result->timing_ms.model_execute_ms,
        result->timing_ms.output_fetch_ms,
        result->timing_ms.postprocess_ms,
        result->timing_ms.temporal_ms,
        result->timing_ms.render_prepare_ms,
        result->timing_ms.render_ms,
        result->timing_ms.osd_ms);
    fflush(metrics->counts_stream);

    fprintf(metrics->detections_stream,
        "{\"frame_index\":%llu,\"timestamp_ms\":%llu,\"elapsed_ms\":%.3f,"
        "\"person_count\":%u,\"raw_person_count\":%u,\"confirmed_track_person_count\":%u,"
        "\"tentative_person_count\":%u,\"held_person_count\":%u,"
        "\"mature_confirmed_person_count\":%u,\"mature_held_person_count\":%u,"
        "\"public_person_count_from_mature_carry\":%u,\"ebike_count\":%u,"
        "\"smoothed_person_count\":%u,\"smoothed_ebike_count\":%u,\"fps\":%.6f,"
        "\"detection_count\":%zu,\"timing_ms\":",
        (unsigned long long)metrics->frame_count,
        (unsigned long long)timestamp_ms,
        elapsed_ms,
        result->stats.person_count,
        result->stats.raw_person_count,
        result->stats.confirmed_track_person_count,
        result->stats.tentative_person_count,
        result->stats.held_person_count,
        result->stats.mature_confirmed_person_count,
        result->stats.mature_held_person_count,
        result->stats.public_person_count_from_mature_carry,
        result->stats.ebike_count,
        result->stats.smoothed_person_count,
        result->stats.smoothed_ebike_count,
        result->stats.fps,
        result->detection_count);
    (void)elevator_write_timing_json(metrics->detections_stream, &result->timing_ms);
    fputs(",\"detections\":[", metrics->detections_stream);
    for (idx = 0; idx < result->detection_count; ++idx) {
        const elevator_detection_result *det = &result->detections[idx];
        if (idx != 0) {
            fputc(',', metrics->detections_stream);
        }
        fprintf(metrics->detections_stream,
            "{\"class_id\":%u,\"score\":%.6f,\"score_percent\":%u,\"track_id\":%u,"
            "\"track_state\":%u,\"child_like\":%u,\"synthetic\":%u,"
            "\"x1\":%u,\"y1\":%u,\"x2\":%u,\"y2\":%u}",
            det->class_id, det->score, det->score_percent,
            det->track_id, det->track_state, det->child_like, det->synthetic,
            det->rect.x1, det->rect.y1, det->rect.x2, det->rect.y2);
    }
    fputs("]}\n", metrics->detections_stream);
    fflush(metrics->detections_stream);

    metrics->sum_person_count += (double)result->stats.person_count;
    metrics->sum_smoothed_person_count += (double)result->stats.smoothed_person_count;
    metrics->sum_raw_person_count += (double)result->stats.raw_person_count;
    metrics->sum_confirmed_track_person_count += (double)result->stats.confirmed_track_person_count;
    metrics->sum_tentative_person_count += (double)result->stats.tentative_person_count;
    metrics->sum_held_person_count += (double)result->stats.held_person_count;
    metrics->sum_mature_confirmed_person_count += (double)result->stats.mature_confirmed_person_count;
    metrics->sum_mature_held_person_count += (double)result->stats.mature_held_person_count;
    metrics->sum_public_person_count_from_mature_carry +=
        (double)result->stats.public_person_count_from_mature_carry;
    metrics->sum_ebike_count += (double)result->stats.ebike_count;
    metrics->sum_smoothed_ebike_count += (double)result->stats.smoothed_ebike_count;
    elevator_timing_add(&metrics->sum_timing_ms, &result->timing_ms);
    metrics->frame_count++;
    metrics->last_timestamp_ms = timestamp_ms;
}

static td_void elevator_file_metrics_close(td_void)
{
    elevator_file_metrics_runtime *metrics = &g_elevator_file_metrics_runtime;
    FILE *summary_stream;
    double duration_ms;
    double avg_person_count = 0.0;
    double avg_smoothed_person_count = 0.0;
    double avg_raw_person_count = 0.0;
    double avg_confirmed_track_person_count = 0.0;
    double avg_tentative_person_count = 0.0;
    double avg_held_person_count = 0.0;
    double avg_mature_confirmed_person_count = 0.0;
    double avg_mature_held_person_count = 0.0;
    double avg_public_person_count_from_mature_carry = 0.0;
    double avg_ebike_count = 0.0;
    double avg_smoothed_ebike_count = 0.0;
    elevator_frame_timing avg_timing_ms;

    memset(&avg_timing_ms, 0, sizeof(avg_timing_ms));

    if (metrics->frame_count != 0) {
        avg_person_count = metrics->sum_person_count / (double)metrics->frame_count;
        avg_smoothed_person_count = metrics->sum_smoothed_person_count / (double)metrics->frame_count;
        avg_raw_person_count = metrics->sum_raw_person_count / (double)metrics->frame_count;
        avg_confirmed_track_person_count = metrics->sum_confirmed_track_person_count / (double)metrics->frame_count;
        avg_tentative_person_count = metrics->sum_tentative_person_count / (double)metrics->frame_count;
        avg_held_person_count = metrics->sum_held_person_count / (double)metrics->frame_count;
        avg_mature_confirmed_person_count =
            metrics->sum_mature_confirmed_person_count / (double)metrics->frame_count;
        avg_mature_held_person_count = metrics->sum_mature_held_person_count / (double)metrics->frame_count;
        avg_public_person_count_from_mature_carry =
            metrics->sum_public_person_count_from_mature_carry / (double)metrics->frame_count;
        avg_ebike_count = metrics->sum_ebike_count / (double)metrics->frame_count;
        avg_smoothed_ebike_count = metrics->sum_smoothed_ebike_count / (double)metrics->frame_count;
        elevator_timing_average(&avg_timing_ms, &metrics->sum_timing_ms, metrics->frame_count);
    }
    duration_ms = metrics->frame_count > 1 && metrics->last_timestamp_ms >= metrics->first_timestamp_ms ?
        (double)(metrics->last_timestamp_ms - metrics->first_timestamp_ms) : 0.0;

    if (metrics->summary_path[0] != '\0') {
        summary_stream = fopen(metrics->summary_path, "w");
        if (summary_stream != TD_NULL) {
            fprintf(summary_stream,
                "{\n"
                "  \"output_dir\": \"%s\",\n"
                "  \"frame_count\": %llu,\n"
                "  \"first_timestamp_ms\": %llu,\n"
                "  \"last_timestamp_ms\": %llu,\n"
                "  \"duration_ms\": %.3f,\n"
                "  \"avg_person_count\": %.6f,\n"
                "  \"avg_raw_person_count\": %.6f,\n"
                "  \"avg_confirmed_track_person_count\": %.6f,\n"
                "  \"avg_tentative_person_count\": %.6f,\n"
                "  \"avg_held_person_count\": %.6f,\n"
                "  \"avg_mature_confirmed_person_count\": %.6f,\n"
                "  \"avg_mature_held_person_count\": %.6f,\n"
                "  \"avg_public_person_count_from_mature_carry\": %.6f,\n"
                "  \"avg_smoothed_person_count\": %.6f,\n"
                "  \"avg_ebike_count\": %.6f,\n"
                "  \"avg_smoothed_ebike_count\": %.6f,\n"
                "  \"min_person_count\": %u,\n"
                "  \"max_person_count\": %u,\n"
                "  \"min_raw_person_count\": %u,\n"
                "  \"max_raw_person_count\": %u,\n"
                "  \"min_confirmed_track_person_count\": %u,\n"
                "  \"max_confirmed_track_person_count\": %u,\n"
                "  \"min_tentative_person_count\": %u,\n"
                "  \"max_tentative_person_count\": %u,\n"
                "  \"min_held_person_count\": %u,\n"
                "  \"max_held_person_count\": %u,\n"
                "  \"min_mature_confirmed_person_count\": %u,\n"
                "  \"max_mature_confirmed_person_count\": %u,\n"
                "  \"min_mature_held_person_count\": %u,\n"
                "  \"max_mature_held_person_count\": %u,\n"
                "  \"min_public_person_count_from_mature_carry\": %u,\n"
                "  \"max_public_person_count_from_mature_carry\": %u,\n"
                "  \"min_smoothed_person_count\": %u,\n"
                "  \"max_smoothed_person_count\": %u,\n"
                "  \"min_ebike_count\": %u,\n"
                "  \"max_ebike_count\": %u,\n"
                "  \"timing_ms_average\": ",
                metrics->output_dir,
                (unsigned long long)metrics->frame_count,
                (unsigned long long)metrics->first_timestamp_ms,
                (unsigned long long)metrics->last_timestamp_ms,
                duration_ms,
                avg_person_count,
                avg_raw_person_count,
                avg_confirmed_track_person_count,
                avg_tentative_person_count,
                avg_held_person_count,
                avg_mature_confirmed_person_count,
                avg_mature_held_person_count,
                avg_public_person_count_from_mature_carry,
                avg_smoothed_person_count,
                avg_ebike_count,
                avg_smoothed_ebike_count,
                metrics->min_person_count,
                metrics->max_person_count,
                metrics->min_raw_person_count,
                metrics->max_raw_person_count,
                metrics->min_confirmed_track_person_count,
                metrics->max_confirmed_track_person_count,
                metrics->min_tentative_person_count,
                metrics->max_tentative_person_count,
                metrics->min_held_person_count,
                metrics->max_held_person_count,
                metrics->min_mature_confirmed_person_count,
                metrics->max_mature_confirmed_person_count,
                metrics->min_mature_held_person_count,
                metrics->max_mature_held_person_count,
                metrics->min_public_person_count_from_mature_carry,
                metrics->max_public_person_count_from_mature_carry,
                metrics->min_smoothed_person_count,
                metrics->max_smoothed_person_count,
                metrics->min_ebike_count,
                metrics->max_ebike_count);
            (void)elevator_write_timing_json(summary_stream, &avg_timing_ms);
            fputs("\n}\n", summary_stream);
            fclose(summary_stream);
        }
    }

    if (metrics->counts_stream != TD_NULL) {
        fclose(metrics->counts_stream);
        metrics->counts_stream = TD_NULL;
    }
    if (metrics->detections_stream != TD_NULL) {
        fclose(metrics->detections_stream);
        metrics->detections_stream = TD_NULL;
    }
    metrics->active = TD_FALSE;
}

static td_void elevator_batch_prepare_image(const char *output_path)
{
    td_bool jpeg_encoder_started = g_elevator_batch_runtime.jpeg_encoder_started;

    memset(&g_elevator_batch_runtime, 0, sizeof(g_elevator_batch_runtime));
    g_elevator_batch_runtime.active = TD_TRUE;
    g_elevator_batch_runtime.jpeg_encoder_started = jpeg_encoder_started;
    g_elevator_batch_runtime.last_ret = TD_FAILURE;
    if (output_path != TD_NULL) {
        snprintf(g_elevator_batch_runtime.output_path, sizeof(g_elevator_batch_runtime.output_path), "%s", output_path);
    }
}

static td_s32 elevator_batch_start_jpeg_encoder(td_void)
{
    ot_size size;

    if (g_elevator_batch_runtime.jpeg_encoder_started == TD_TRUE) {
        return TD_SUCCESS;
    }

    size.width = g_elevator_vo_cfg.image_size.width;
    size.height = g_elevator_vo_cfg.image_size.height;
    if (sample_comm_venc_photo_start(ELEVATOR_JPEG_VENC_CHN, &size, TD_FALSE) != TD_SUCCESS) {
        return TD_FAILURE;
    }
    g_elevator_batch_runtime.jpeg_encoder_started = TD_TRUE;
    return TD_SUCCESS;
}

static td_void elevator_batch_stop_jpeg_encoder(td_void)
{
    if (g_elevator_batch_runtime.jpeg_encoder_started == TD_TRUE) {
        (td_void)sample_comm_venc_snap_stop(ELEVATOR_JPEG_VENC_CHN);
        g_elevator_batch_runtime.jpeg_encoder_started = TD_FALSE;
    }
}

static td_s32 elevator_batch_save_stream_to_path(ot_venc_chn venc_chn, const char *path)
{
    td_s32 ret;
    ot_venc_chn_status status;
    ot_venc_stream stream;
    FILE *output = TD_NULL;

    if (path == TD_NULL || path[0] == '\0') {
        return TD_FAILURE;
    }

    memset(&status, 0, sizeof(status));
    memset(&stream, 0, sizeof(stream));
    ret = ss_mpi_venc_query_status(venc_chn, &status);
    if (ret != TD_SUCCESS || status.cur_packs == 0) {
        return TD_FAILURE;
    }

    stream.pack = (ot_venc_pack *)malloc(sizeof(ot_venc_pack) * status.cur_packs);
    if (stream.pack == TD_NULL) {
        return TD_FAILURE;
    }
    stream.pack_cnt = status.cur_packs;

    ret = ss_mpi_venc_get_stream(venc_chn, &stream, -1);
    if (ret != TD_SUCCESS) {
        free(stream.pack);
        return ret;
    }

    output = fopen(path, "wb");
    if (output == TD_NULL) {
        (td_void)ss_mpi_venc_release_stream(venc_chn, &stream);
        free(stream.pack);
        return TD_FAILURE;
    }

    ret = sample_comm_venc_save_stream(output, &stream);
    (td_void)fclose(output);
    (td_void)ss_mpi_venc_release_stream(venc_chn, &stream);
    free(stream.pack);
    return ret;
}

static td_s32 elevator_batch_save_frame_as_jpeg(const ot_video_frame_info *frame, const char *path)
{
    fd_set read_fds;
    struct timeval timeout_val;
    td_s32 venc_fd;
    td_s32 ret;

    if (frame == TD_NULL || path == TD_NULL) {
        return TD_FAILURE;
    }

    ret = ss_mpi_venc_send_frame(ELEVATOR_JPEG_VENC_CHN, frame, OT_SVP_TIMEOUT);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "batch jpeg save send_frame failed: %#x\n", ret);
        return ret;
    }

    venc_fd = ss_mpi_venc_get_fd(ELEVATOR_JPEG_VENC_CHN);
    if (venc_fd < 0) {
        return TD_FAILURE;
    }

    FD_ZERO(&read_fds);
    FD_SET(venc_fd, &read_fds);
    timeout_val.tv_sec = 10;
    timeout_val.tv_usec = 0;
    ret = select(venc_fd + 1, &read_fds, TD_NULL, TD_NULL, &timeout_val);
    if (ret <= 0 || FD_ISSET(venc_fd, &read_fds) == 0) {
        fprintf(stderr, "batch jpeg save select timeout or invalid fd state: ret=%d\n", ret);
        return TD_FAILURE;
    }

    return elevator_batch_save_stream_to_path(ELEVATOR_JPEG_VENC_CHN, path);
}

static td_s32 elevator_init_acl(td_void)
{
    td_s32 ret;

    if (sample_common_svp_check_sys_init() != TD_TRUE) {
        fprintf(stderr, "mpi init failed\n");
        return TD_FAILURE;
    }

    ret = sample_common_svp_npu_acl_init(TD_NULL, g_elevator_dev_id);
    if (ret == TD_SUCCESS) {
        printf("acl init success\n");
    }
    return ret;
}

static td_void elevator_deinit_acl(td_void)
{
    sample_common_svp_npu_acl_deinit(g_elevator_dev_id);
    sample_common_svp_check_sys_exit();
}

static td_void elevator_set_task_info(td_void)
{
    g_elevator_task.cfg.max_batch_num = 1;
    g_elevator_task.cfg.dynamic_batch_num = 1;
    g_elevator_task.cfg.total_t = 0;
    g_elevator_task.cfg.is_cached = TD_TRUE;
    g_elevator_task.cfg.model_idx = ELEVATOR_MODEL_INDEX;
}

static td_s32 elevator_init_task(td_void)
{
    td_s32 ret;

    ret = sample_common_svp_npu_create_input(&g_elevator_task);
    if (ret != TD_SUCCESS) {
        return ret;
    }
    ret = sample_common_svp_npu_create_output(&g_elevator_task);
    if (ret != TD_SUCCESS) {
        sample_common_svp_npu_destroy_input(&g_elevator_task);
        return ret;
    }
    ret = sample_common_svp_npu_create_task_buf(&g_elevator_task);
    if (ret != TD_SUCCESS) {
        sample_common_svp_npu_destroy_output(&g_elevator_task);
        sample_common_svp_npu_destroy_input(&g_elevator_task);
        return ret;
    }
    ret = sample_common_svp_npu_create_work_buf(&g_elevator_task);
    if (ret != TD_SUCCESS) {
        sample_common_svp_npu_destroy_task_buf(&g_elevator_task);
        sample_common_svp_npu_destroy_output(&g_elevator_task);
        sample_common_svp_npu_destroy_input(&g_elevator_task);
        return ret;
    }
    return TD_SUCCESS;
}

static td_bool elevator_task_resources_ready(td_void)
{
    return (g_elevator_task.input_dataset != TD_NULL &&
        g_elevator_task.output_dataset != TD_NULL &&
        g_elevator_task.task_buf_ptr != TD_NULL &&
        g_elevator_task.work_buf_ptr != TD_NULL) ? TD_TRUE : TD_FALSE;
}

static td_s32 elevator_batch_ensure_task_ready(td_void)
{
    sample_svp_npu_model_info *model_info;
    td_bool cfg_drifted;
    td_bool resources_ready;
    td_s32 ret;

    model_info = sample_common_svp_npu_get_model_info(ELEVATOR_MODEL_INDEX);
    if (model_info == TD_NULL || model_info->model_desc == TD_NULL) {
        fprintf(stderr, "batch task guard: model %u is not loaded\n", ELEVATOR_MODEL_INDEX);
        return TD_FAILURE;
    }

    cfg_drifted = (g_elevator_task.cfg.max_batch_num != 1 ||
        g_elevator_task.cfg.dynamic_batch_num != 1 ||
        g_elevator_task.cfg.total_t != 0 ||
        g_elevator_task.cfg.is_cached != TD_TRUE ||
        g_elevator_task.cfg.model_idx != ELEVATOR_MODEL_INDEX) ? TD_TRUE : TD_FALSE;
    if (cfg_drifted == TD_TRUE) {
        fprintf(stderr,
            "batch task cfg drift detected: max_batch=%u dynamic_batch=%u total_t=%u cached=%u model_idx=%u; restoring\n",
            g_elevator_task.cfg.max_batch_num, g_elevator_task.cfg.dynamic_batch_num,
            g_elevator_task.cfg.total_t, g_elevator_task.cfg.is_cached, g_elevator_task.cfg.model_idx);
        elevator_set_task_info();
    }

    resources_ready = elevator_task_resources_ready();
    if (resources_ready == TD_TRUE) {
        return TD_SUCCESS;
    }

    fprintf(stderr, "batch task resources missing before image start; rebuilding task state\n");
    elevator_deinit_task();
    elevator_set_task_info();
    ret = elevator_init_task();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "batch task rebuild init failed: %#x\n", ret);
        return ret;
    }
    ret = elevator_sync_input_contract();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "batch task rebuild input sync failed: %#x\n", ret);
        elevator_deinit_task();
        return ret;
    }
    ret = elevator_setup_threshold(&g_elevator_config);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "batch task rebuild threshold failed: %#x\n", ret);
        elevator_deinit_task();
        return ret;
    }
    return TD_SUCCESS;
}

static td_void elevator_deinit_task(td_void)
{
    sample_svp_npu_model_info *model_info = sample_common_svp_npu_get_model_info(ELEVATOR_MODEL_INDEX);

    if (model_info != TD_NULL && model_info->model_desc != TD_NULL) {
        elevator_set_task_info();
        sample_common_svp_npu_destroy_work_buf(&g_elevator_task);
        sample_common_svp_npu_destroy_task_buf(&g_elevator_task);
        sample_common_svp_npu_destroy_output(&g_elevator_task);
        sample_common_svp_npu_destroy_input(&g_elevator_task);
    }
    memset(&g_elevator_task, 0, sizeof(g_elevator_task));
}

static td_s32 elevator_configure_input_stream(const elevator_runtime_config *config)
{
    ot_payload_type payload_type;
    td_s32 ret;
    td_u32 jpeg_width = 0;
    td_u32 jpeg_height = 0;

    ret = elevator_split_input_path(config->input_path, g_elevator_vdec_param.c_file_path,
        sizeof(g_elevator_vdec_param.c_file_path), g_elevator_vdec_param.c_file_name,
        sizeof(g_elevator_vdec_param.c_file_name));
    if (ret != TD_SUCCESS) {
        return ret;
    }

    ret = elevator_detect_payload_type(config->input_path, &payload_type);
    if (ret != TD_SUCCESS) {
        return ret;
    }
    g_elevator_vdec_cfg.type = payload_type;
    g_elevator_vdec_param.type = payload_type;
    g_elevator_input_payload_type = payload_type;
    g_elevator_vdec_param.e_thread_ctrl = THREAD_CTRL_START;
    g_elevator_vdec_param.fps = config->source_fps > 0.0f ? (td_u64)(config->source_fps + 0.5f) : 30U;
    g_elevator_vdec_cfg.mode = OT_VDEC_SEND_MODE_FRAME;
    g_elevator_vdec_param.stream_mode = OT_VDEC_SEND_MODE_FRAME;
    g_elevator_vdec_cfg.width = _4K_WIDTH;
    g_elevator_vdec_cfg.height = _4K_HEIGHT;
    g_elevator_vdec_param.min_buf_size = (_4K_WIDTH * _4K_HEIGHT * 3) >> 1;
    if (payload_type == OT_PT_JPEG) {
        if (elevator_parse_jpeg_dimensions(config->input_path, &jpeg_width, &jpeg_height) == TD_SUCCESS) {
            g_elevator_vdec_cfg.width = jpeg_width;
            g_elevator_vdec_cfg.height = jpeg_height;
            g_elevator_vdec_param.min_buf_size = (jpeg_width * jpeg_height * 3) >> 1;
            printf("jpeg input header detected: %ux%u\n", jpeg_width, jpeg_height);
        } else {
            fprintf(stderr, "warning: failed to parse jpeg header, keep default vdec max size %ux%u\n",
                g_elevator_vdec_cfg.width, g_elevator_vdec_cfg.height);
        }
    }
    if (payload_type == OT_PT_JPEG || payload_type == OT_PT_MJPEG) {
        g_elevator_vdec_cfg.sample_vdec_picture.pixel_format = OT_PIXEL_FORMAT_YVU_SEMIPLANAR_420;
        g_elevator_vdec_cfg.sample_vdec_picture.alpha = 255;
        g_elevator_vdec_cfg.frame_buf_cnt = g_elevator_vdec_cfg.display_frame_num + 1;
    } else {
        /* sample_vdec_video and sample_vdec_picture share a union; keep H.264/H.265
         * configuration strictly on the video side or create_chn sees corrupted attrs. */
        g_elevator_vdec_cfg.sample_vdec_video.dec_mode = OT_VIDEO_DEC_MODE_IP;
        g_elevator_vdec_cfg.sample_vdec_video.bit_width = OT_DATA_BIT_WIDTH_8;
        g_elevator_vdec_cfg.sample_vdec_video.ref_frame_num = 2;
        g_elevator_vdec_cfg.frame_buf_cnt = 5;
        if (config->mode == ELEVATOR_RUN_MODE_FILE &&
            (payload_type == OT_PT_H264 || payload_type == OT_PT_H265)) {
            const char *payload_name = payload_type == OT_PT_H265 ? "h265" : "h264";
            if (elevator_file_mode_prefers_frame_feed(config) != 0) {
                g_elevator_vdec_cfg.mode = OT_VDEC_SEND_MODE_FRAME;
                g_elevator_vdec_param.stream_mode = OT_VDEC_SEND_MODE_FRAME;
                g_elevator_vdec_cfg.display_mode = elevator_file_mode_prefers_playback_display(config) != 0 ?
                    OT_VIDEO_DISPLAY_MODE_PLAYBACK : OT_VIDEO_DISPLAY_MODE_PREVIEW;
                printf("file-mode %s decode config: send_mode=FRAME dec_mode=IP display_mode=%s ref_frame_num=%u display_frame_num=%u frame_buf_cnt=%u fps=%llu\n",
                    payload_name,
                    g_elevator_vdec_cfg.display_mode == OT_VIDEO_DISPLAY_MODE_PLAYBACK ? "PLAYBACK" : "PREVIEW",
                    g_elevator_vdec_cfg.sample_vdec_video.ref_frame_num,
                    g_elevator_vdec_cfg.display_frame_num, g_elevator_vdec_cfg.frame_buf_cnt,
                    (unsigned long long)g_elevator_vdec_param.fps);
            } else {
                /* Stream feed stays as the fallback for non-source-timed or looser file playback cases,
                 * because it is more tolerant of long GOP/B-frame material. */
                g_elevator_vdec_cfg.mode = OT_VDEC_SEND_MODE_STREAM;
                g_elevator_vdec_param.stream_mode = OT_VDEC_SEND_MODE_STREAM;
                g_elevator_vdec_cfg.display_mode = OT_VIDEO_DISPLAY_MODE_PLAYBACK;
                printf("file-mode %s decode config: send_mode=STREAM dec_mode=IP display_mode=PLAYBACK ref_frame_num=%u display_frame_num=%u frame_buf_cnt=%u\n",
                    payload_name, g_elevator_vdec_cfg.sample_vdec_video.ref_frame_num,
                    g_elevator_vdec_cfg.display_frame_num, g_elevator_vdec_cfg.frame_buf_cnt);
            }
        }
    }
    if (elevator_is_batch_mode() == TD_TRUE) {
        g_elevator_vdec_param.circle_send = TD_FALSE;
    } else if (config->mode == ELEVATOR_RUN_MODE_FILE) {
        g_elevator_vdec_param.circle_send = config->single_shot != 0 ? TD_FALSE : TD_TRUE;
    } else {
        g_elevator_vdec_param.circle_send = TD_TRUE;
    }
    return TD_SUCCESS;
}

static td_s32 elevator_init_media(td_void)
{
    if (sample_comm_vo_get_vo_intf_type() == OT_VO_INTF_MIPI) {
        g_elevator_vo_cfg.vo_intf_type = OT_VO_INTF_MIPI;
    }

    printf("media cfg: chn_num=%u base=%ux%u(%s) infer=%ux%u(%s) vo=%ux%u\n",
        g_elevator_media_cfg.chn_num,
        g_elevator_media_cfg.pic_size[0].width, g_elevator_media_cfg.pic_size[0].height,
        elevator_pixel_format_name(g_elevator_media_cfg.pixel_format[OT_VPSS_CHN0]),
        g_elevator_media_cfg.pic_size[1].width, g_elevator_media_cfg.pic_size[1].height,
        elevator_pixel_format_name(g_elevator_media_cfg.pixel_format[OT_VPSS_CHN1]),
        g_elevator_vo_cfg.image_size.width, g_elevator_vo_cfg.image_size.height);

    return sample_common_svp_create_vb_start_vdec_vpss_vo(&g_elevator_vdec_cfg, &g_elevator_vdec_param,
        &g_elevator_vdec_thread, &g_elevator_media_cfg, &g_elevator_vo_cfg);
}

static td_void elevator_deinit_media(td_void)
{
    sample_common_svp_destroy_vb_stop_vdec_vpss_vo(&g_elevator_vdec_param, &g_elevator_vdec_thread,
        &g_elevator_media_cfg, &g_elevator_vo_cfg);
}

static td_s32 elevator_vb_map(td_u32 vb_pool_idx)
{
    td_s32 ret;

    if (g_elevator_vb_virt_addr != TD_NULL) {
        return TD_SUCCESS;
    }

    ret = ss_mpi_vb_get_pool_info(g_elevator_media_cfg.vb_pool[vb_pool_idx], &g_elevator_vb_pool_info);
    if (ret != TD_SUCCESS) {
        return ret;
    }
    g_elevator_vb_virt_addr = ss_mpi_sys_mmap(g_elevator_vb_pool_info.pool_phy_addr, g_elevator_vb_pool_info.pool_size);
    return g_elevator_vb_virt_addr == TD_NULL ? TD_FAILURE : TD_SUCCESS;
}

static td_void elevator_vb_unmap(td_void)
{
    if (g_elevator_vb_virt_addr != TD_NULL) {
        ss_mpi_sys_munmap(g_elevator_vb_virt_addr, g_elevator_vb_pool_info.pool_size);
        g_elevator_vb_virt_addr = TD_NULL;
    }
}

static void elevator_log_waiting_for_first_frame(const char *stage, td_s32 ret, td_u32 timeout_count)
{
    ot_vdec_chn_status status = {0};
    td_s32 query_ret;

    if (stage == NULL) {
        return;
    }

    query_ret = ss_mpi_vdec_query_status(g_elevator_vdec_param.chn_id, &status);
    if (query_ret == TD_SUCCESS) {
        printf("waiting for first frame: stage=%s ret=%#x timeout_count=%u payload=%d "
               "decode_frames=%u left_pics=%u left_bytes=%u left_frames=%u recv_frames=%u "
               "stream_size=%ux%u pic_size_err=%d pic_buf_err=%d format_err=%d stream_unsupport=%d\n",
            stage, ret, timeout_count, g_elevator_input_payload_type, status.dec_stream_frames,
            status.left_decoded_frames, status.left_stream_bytes, status.left_stream_frames, status.recv_stream_frames,
            status.width, status.height, status.dec_err.set_pic_size_err, status.dec_err.set_pic_buf_size_err,
            status.dec_err.format_err, status.dec_err.stream_unsupport);
    } else {
        printf("waiting for first frame: stage=%s ret=%#x timeout_count=%u payload=%d "
               "vdec_query_failed=%#x\n",
            stage, ret, timeout_count, g_elevator_input_payload_type, query_ret);
    }
    fflush(stdout);
}

static void elevator_probe_base_channel_when_infer_empty(td_s32 vpss_grp, td_s32 base_chn)
{
    ot_video_frame_info probe_frame;
    td_s32 ret;

    memset(&probe_frame, 0, sizeof(probe_frame));
    ret = ss_mpi_vpss_get_chn_frame(vpss_grp, base_chn, &probe_frame, 0);
    if (ret == TD_SUCCESS) {
        printf("base channel probe while infer empty: ret=%#x size=%ux%u pixel_format=%s(%d) stride=[%u,%u]\n",
            ret, probe_frame.video_frame.width, probe_frame.video_frame.height,
            elevator_pixel_format_name(probe_frame.video_frame.pixel_format), probe_frame.video_frame.pixel_format,
            probe_frame.video_frame.stride[0], probe_frame.video_frame.stride[1]);
        (td_void)ss_mpi_vpss_release_chn_frame(vpss_grp, base_chn, &probe_frame);
    } else {
        printf("base channel probe while infer empty: ret=%#x\n", ret);
    }
    fflush(stdout);
}

static void elevator_log_dims(FILE *stream, const char *name, const svp_acl_mdl_io_dims *dims)
{
    size_t idx;

    if (stream == NULL || name == NULL || dims == NULL) {
        return;
    }

    fprintf(stream, "%s dims=[", name);
    for (idx = 0; idx < dims->dim_count; ++idx) {
        fprintf(stream, "%zu%s", dims->dims[idx], (idx + 1U) == dims->dim_count ? "" : ",");
    }
    fprintf(stream, "]\n");
}

static void elevator_log_model_outputs(td_void)
{
    sample_svp_npu_model_info *model_info;
    size_t idx;

    model_info = sample_common_svp_npu_get_model_info(ELEVATOR_MODEL_INDEX);
    if (model_info == TD_NULL || model_info->model_desc == TD_NULL) {
        return;
    }

    for (idx = 0; idx < model_info->output_num; ++idx) {
        svp_acl_mdl_io_dims dims = {0};
        const char *output_name = svp_acl_mdl_get_output_name_by_index(model_info->model_desc, idx);
        svp_acl_error ret = svp_acl_mdl_get_output_dims(model_info->model_desc, idx, &dims);

        if (ret == SVP_ACL_SUCCESS) {
            elevator_log_dims(stdout, output_name != NULL ? output_name : "(unnamed)", &dims);
        } else {
            printf("%s output[%zu] dims unavailable\n", output_name != NULL ? output_name : "(unnamed)", idx);
        }
    }
    fflush(stdout);
}

static td_void elevator_log_model_input_contract(td_void)
{
    sample_svp_npu_model_info *model_info;
    svp_acl_mdl_io_dims dims = {0};
    svp_acl_aipp_info aipp_info = {0};
    const char *input_name;
    svp_acl_data_type input_type;
    svp_acl_mdl_aipp_type aipp_type = SVP_ACL_DATA_WITHOUT_AIPP;
    size_t attached_index = 0;
    svp_acl_error ret;

    model_info = sample_common_svp_npu_get_model_info(ELEVATOR_MODEL_INDEX);
    if (model_info == TD_NULL || model_info->model_desc == TD_NULL) {
        return;
    }

    input_name = svp_acl_mdl_get_input_name_by_index(model_info->model_desc, 0);
    ret = svp_acl_mdl_get_input_dims(model_info->model_desc, 0, &dims);
    if (ret == SVP_ACL_SUCCESS) {
        elevator_log_dims(stdout, input_name != NULL ? input_name : "input[0]", &dims);
    }

    input_type = svp_acl_mdl_get_input_data_type(model_info->model_desc, 0);
    ret = svp_acl_mdl_get_input_aipp_type(model_info->model_id, 0, &aipp_type, &attached_index);
    if (ret == SVP_ACL_SUCCESS) {
        printf("model input[0]: name=%s data_type=%d aipp_type=%d attached_index=%zu\n",
            input_name != NULL ? input_name : "(unnamed)", input_type, aipp_type, attached_index);
    } else {
        printf("model input[0]: name=%s data_type=%d aipp_type=query_failed(%d)\n",
            input_name != NULL ? input_name : "(unnamed)", input_type, ret);
    }

    ret = svp_acl_mdl_get_first_aipp_info(model_info->model_id, 0, &aipp_info);
    if (ret == SVP_ACL_SUCCESS) {
        printf("model first aipp: format=%d src_format=%d src_data_type=%d src_dim_num=%zu shape_count=%zu\n",
            aipp_info.aipp_format, aipp_info.src_format, aipp_info.src_data_type,
            aipp_info.src_dim_num, aipp_info.shape_count);
    }
}

static td_s32 elevator_sync_input_contract(td_void)
{
    td_s32 ret;
    td_u8 *input_data = TD_NULL;

    ret = sample_common_svp_npu_get_input_data_buffer_info(&g_elevator_task, 0, &input_data,
        &g_elevator_model_input_size, &g_elevator_model_input_stride);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    printf("model input buffer: size=%u stride=%u target_pixel_format=%s\n",
        g_elevator_model_input_size, g_elevator_model_input_stride,
        elevator_pixel_format_name(OT_PIXEL_FORMAT_BGR_888_PLANAR));
    return TD_SUCCESS;
}

static elevator_output_binding *elevator_get_output_binding(elevator_output_kind kind)
{
    if ((size_t)kind >= (sizeof(g_elevator_output_binding) / sizeof(g_elevator_output_binding[0]))) {
        return TD_NULL;
    }
    return &g_elevator_output_binding[kind];
}

static td_void elevator_cache_output_binding(elevator_output_kind kind, size_t output_idx, const char *primary_name,
    const char *resolved_name)
{
    elevator_output_binding *binding = elevator_get_output_binding(kind);

    if (binding == TD_NULL) {
        return;
    }

    binding->resolved = TD_TRUE;
    binding->output_idx = output_idx;
    snprintf(binding->requested_name, sizeof(binding->requested_name), "%s", primary_name != TD_NULL ? primary_name : "");
    snprintf(binding->resolved_name, sizeof(binding->resolved_name), "%s",
        resolved_name != TD_NULL ? resolved_name : "(unnamed)");
}

static td_bool elevator_output_dims_match_kind(const svp_acl_mdl_io_dims *dims, elevator_output_kind kind)
{
    size_t idx;
    size_t total = 1;

    if (dims == TD_NULL || dims->dim_count == 0) {
        return TD_FALSE;
    }

    if (kind == ELEVATOR_OUTPUT_KIND_ROI) {
        return dims->dim_count >= 2 && dims->dims[dims->dim_count - 2] == ELEVATOR_OUTPUT_ROI_PLANES;
    }

    for (idx = 0; idx < dims->dim_count; ++idx) {
        total *= dims->dims[idx];
    }
    return total == 1;
}

static td_s32 elevator_find_output_index_by_name(sample_svp_npu_model_info *model_info, const char *name, size_t *output_idx)
{
    size_t idx;

    if (model_info == TD_NULL || model_info->model_desc == TD_NULL || name == TD_NULL || output_idx == TD_NULL) {
        return TD_FAILURE;
    }

    for (idx = 0; idx < model_info->output_num; ++idx) {
        const char *output_name = svp_acl_mdl_get_output_name_by_index(model_info->model_desc, idx);

        if (output_name != TD_NULL && strcmp(output_name, name) == 0) {
            *output_idx = idx;
            return TD_SUCCESS;
        }
    }

    return TD_FAILURE;
}

static td_s32 elevator_try_output_name(sample_svp_npu_model_info *model_info, const char *name,
    elevator_output_kind kind, size_t *output_idx, svp_acl_mdl_io_dims *dims, const char **resolved_name)
{
    svp_acl_error ret;

    if (model_info == TD_NULL || model_info->model_desc == TD_NULL || name == TD_NULL || name[0] == '\0') {
        return TD_FAILURE;
    }

    if (elevator_find_output_index_by_name(model_info, name, output_idx) != TD_SUCCESS) {
        return TD_FAILURE;
    }
    ret = svp_acl_mdl_get_output_dims(model_info->model_desc, *output_idx, dims);
    if (ret != SVP_ACL_SUCCESS || elevator_output_dims_match_kind(dims, kind) == TD_FALSE) {
        return TD_FAILURE;
    }

    *resolved_name = svp_acl_mdl_get_output_name_by_index(model_info->model_desc, *output_idx);
    return TD_SUCCESS;
}

static td_s32 elevator_resolve_output(sample_svp_npu_model_info *model_info, const char *primary_name,
    const char *fallback_name, elevator_output_kind kind, size_t *output_idx, svp_acl_mdl_io_dims *dims,
    const char **resolved_name)
{
    elevator_output_binding *binding = elevator_get_output_binding(kind);
    size_t idx;

    if (model_info == TD_NULL || model_info->model_desc == TD_NULL || output_idx == TD_NULL ||
        dims == TD_NULL || resolved_name == TD_NULL) {
        return TD_FAILURE;
    }

    if (binding != TD_NULL && binding->resolved == TD_TRUE) {
        *output_idx = binding->output_idx;
        *resolved_name = binding->resolved_name;
        return svp_acl_mdl_get_output_dims(model_info->model_desc, *output_idx, dims) == SVP_ACL_SUCCESS ?
            TD_SUCCESS : TD_FAILURE;
    }

    if (elevator_try_output_name(model_info, primary_name, kind, output_idx, dims, resolved_name) == TD_SUCCESS) {
        elevator_cache_output_binding(kind, *output_idx, primary_name, *resolved_name);
        return TD_SUCCESS;
    }
    if (fallback_name != TD_NULL && strcmp(primary_name, fallback_name) != 0 &&
        elevator_try_output_name(model_info, fallback_name, kind, output_idx, dims, resolved_name) == TD_SUCCESS) {
        printf("resolved output tensor: requested=%s actual=%s\n", primary_name, *resolved_name);
        fflush(stdout);
        elevator_cache_output_binding(kind, *output_idx, primary_name, *resolved_name);
        return TD_SUCCESS;
    }

    for (idx = 0; idx < model_info->output_num; ++idx) {
        const char *output_name;
        svp_acl_error ret = svp_acl_mdl_get_output_dims(model_info->model_desc, idx, dims);

        if (ret != SVP_ACL_SUCCESS || elevator_output_dims_match_kind(dims, kind) == TD_FALSE) {
            continue;
        }

        *output_idx = idx;
        output_name = svp_acl_mdl_get_output_name_by_index(model_info->model_desc, idx);
        *resolved_name = output_name != TD_NULL ? output_name : "(unnamed)";
        printf("resolved output tensor by shape: requested=%s actual=%s\n", primary_name, *resolved_name);
        fflush(stdout);
        elevator_cache_output_binding(kind, *output_idx, primary_name, *resolved_name);
        return TD_SUCCESS;
    }

    return TD_FAILURE;
}

static td_s32 elevator_resolve_model_outputs(td_void)
{
    sample_svp_npu_model_info *model_info;
    svp_acl_mdl_io_dims dims = {0};
    size_t output_idx = 0;
    const char *resolved_name = TD_NULL;
    td_s32 ret;

    model_info = sample_common_svp_npu_get_model_info(ELEVATOR_MODEL_INDEX);
    if (model_info == TD_NULL || model_info->model_desc == TD_NULL) {
        return TD_FAILURE;
    }

    ret = elevator_resolve_output(model_info, ELEVATOR_OUTPUT_COUNT_NAME, ELEVATOR_OUTPUT_COUNT_NAME_FALLBACK,
        ELEVATOR_OUTPUT_KIND_COUNT, &output_idx, &dims, &resolved_name);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "failed to resolve count output tensor\n");
        return ret;
    }

    memset(&dims, 0, sizeof(dims));
    output_idx = 0;
    resolved_name = TD_NULL;
    ret = elevator_resolve_output(model_info, ELEVATOR_OUTPUT_ROI_NAME, ELEVATOR_OUTPUT_ROI_NAME_FALLBACK,
        ELEVATOR_OUTPUT_KIND_ROI, &output_idx, &dims, &resolved_name);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "failed to resolve roi output tensor\n");
        return ret;
    }

    return TD_SUCCESS;
}

static td_s32 elevator_get_output_buffer(const char *primary_name, const char *fallback_name,
    elevator_output_kind kind, td_u8 **virt_addr,
    size_t *stride_floats, svp_acl_mdl_io_dims *dims)
{
    sample_svp_npu_model_info *model_info;
    size_t output_idx;
    td_u8 *buffer = TD_NULL;
    td_u32 size = 0;
    td_u32 stride = 0;
    const char *resolved_name = primary_name;

    model_info = sample_common_svp_npu_get_model_info(ELEVATOR_MODEL_INDEX);
    if (model_info == TD_NULL || model_info->model_desc == TD_NULL) {
        return TD_FAILURE;
    }

    if (elevator_resolve_output(model_info, primary_name, fallback_name, kind,
            &output_idx, dims, &resolved_name) != TD_SUCCESS) {
        fprintf(stderr, "missing output tensor: %s\n", primary_name);
        elevator_log_model_outputs();
        return TD_FAILURE;
    }
    if (sample_common_svp_npu_get_output_data_buffer_info(&g_elevator_task, (td_u32)output_idx,
            &buffer, &size, &stride) != TD_SUCCESS) {
        fprintf(stderr, "failed to map output buffer: %s\n", resolved_name);
        return TD_FAILURE;
    }

    (void)size;
    *virt_addr = buffer;
    *stride_floats = stride / sizeof(float);
    return TD_SUCCESS;
}

static const char *elevator_review_surface_name(elevator_review_surface surface)
{
    if (surface == ELEVATOR_REVIEW_SURFACE_DEBUG) {
        return "debug";
    }
    if (surface == ELEVATOR_REVIEW_SURFACE_PUBLIC) {
        return "public";
    }
    return "clean";
}

static const char *elevator_playback_timing_name(elevator_playback_timing_mode timing_mode)
{
    if (timing_mode == ELEVATOR_PLAYBACK_TIMING_SOURCE) {
        return "source";
    }
    return "source";
}

static double elevator_effective_source_fps(const elevator_runtime_config *config)
{
    if (config != TD_NULL && config->source_fps > 0.0f) {
        return (double)config->source_fps;
    }
    return (double)g_elevator_vdec_param.fps;
}

static double elevator_effective_source_duration_seconds(const elevator_runtime_config *config)
{
    double fps;

    if (config != TD_NULL && config->source_duration_ms > 0U) {
        return (double)config->source_duration_ms / 1000.0;
    }
    if (config == TD_NULL || config->source_frame_count == 0U) {
        return 0.0;
    }
    fps = elevator_effective_source_fps(config);
    if (fps <= 0.0) {
        return 0.0;
    }
    return (double)config->source_frame_count / fps;
}

static td_u32 elevator_review_surface_label_id(const elevator_detection_result *detection)
{
    if (detection == TD_NULL) {
        return 0U;
    }
    if (g_elevator_config.review_surface == ELEVATOR_REVIEW_SURFACE_DEBUG &&
        detection->class_id == 0U && detection->track_id != 0U) {
        return detection->track_id > 99U ? 99U : detection->track_id;
    }
    return detection->score_percent > 99U ? 99U : detection->score_percent;
}

static td_s32 elevator_write_runtime_contract(uint64_t processed_frame_count)
{
    char manifest_path[ELEVATOR_PATH_MAX];
    FILE *stream;
    double fps;
    double duration_seconds;

    if (g_elevator_config.output_dir[0] == '\0') {
        return TD_SUCCESS;
    }
    if (snprintf(manifest_path, sizeof(manifest_path), "%s/review_surface_run_manifest.json",
            g_elevator_config.output_dir) >= (int)sizeof(manifest_path)) {
        return TD_FAILURE;
    }

    stream = fopen(manifest_path, "w");
    if (stream == TD_NULL) {
        return TD_FAILURE;
    }

    fps = elevator_effective_source_fps(&g_elevator_config);
    duration_seconds = elevator_effective_source_duration_seconds(&g_elevator_config);
    fprintf(stream,
        "{\n"
        "  \"input_path\": \"%s\",\n"
        "  \"surface\": \"%s\",\n"
        "  \"timing\": \"%s\",\n"
        "  \"single_shot\": %s,\n"
        "  \"loop\": false,\n"
        "  \"fps\": %.6f,\n"
        "  \"frame_count\": %u,\n"
        "  \"duration_seconds\": %.6f,\n"
        "  \"processed_frame_count\": %llu,\n"
        "  \"osd_enable\": %s\n"
        "}\n",
        g_elevator_config.input_path,
        elevator_review_surface_name(g_elevator_config.review_surface),
        elevator_playback_timing_name(g_elevator_config.timing_mode),
        g_elevator_config.single_shot != 0 ? "true" : "false",
        fps,
        g_elevator_config.source_frame_count,
        duration_seconds,
        (unsigned long long)processed_frame_count,
        g_elevator_config.osd_enable != 0 ? "true" : "false");
    fclose(stream);
    return TD_SUCCESS;
}

static td_void elevator_build_render_result(const elevator_parse_result *source,
    elevator_parse_result *render_result, td_u32 frame_width, td_u32 frame_height)
{
    size_t idx;

    if (render_result == TD_NULL) {
        return;
    }
    memset(render_result, 0, sizeof(*render_result));
    if (source == TD_NULL) {
        return;
    }

    render_result->stats = source->stats;
    for (idx = 0; idx < source->detection_count && render_result->detection_count < ELEVATOR_MAX_DETECTIONS; ++idx) {
        const elevator_detection_result *detection = &source->detections[idx];
        if (elevator_review_surface_detection_should_render(g_elevator_config.review_surface,
                detection, frame_width, frame_height) == 0) {
            continue;
        }
        render_result->detections[render_result->detection_count++] = *detection;
    }
}

static td_void elevator_result_to_rect_info(const elevator_parse_result *result,
    ot_sample_svp_rect_info *rect_info)
{
    size_t idx;
    size_t limit;

    memset(rect_info, 0, sizeof(*rect_info));
    if (result == TD_NULL) {
        return;
    }

    limit = result->detection_count;
    if (limit > OT_SVP_RECT_NUM) {
        limit = OT_SVP_RECT_NUM;
    }

    rect_info->num = (td_u16)limit;
    for (idx = 0; idx < limit; ++idx) {
        rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_LEFT_TOP].x = result->detections[idx].rect.x1;
        rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_LEFT_TOP].y = result->detections[idx].rect.y1;
        rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_RIGHT_TOP].x = result->detections[idx].rect.x2;
        rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_RIGHT_TOP].y = result->detections[idx].rect.y1;
        rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_RIGHT_BOTTOM].x = result->detections[idx].rect.x2;
        rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_RIGHT_BOTTOM].y = result->detections[idx].rect.y2;
        rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_LEFT_BOTTOM].x = result->detections[idx].rect.x1;
        rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_LEFT_BOTTOM].y = result->detections[idx].rect.y2;
        rect_info->ids[idx] = elevator_review_surface_label_id(&result->detections[idx]);
    }
}

static td_void elevator_append_rect(ot_sample_svp_rect_info *rect_info, const elevator_detection_result *detection)
{
    size_t idx;

    if (rect_info == TD_NULL || detection == TD_NULL || rect_info->num >= OT_SVP_RECT_NUM) {
        return;
    }

    idx = rect_info->num;
    rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_LEFT_TOP].x = detection->rect.x1;
    rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_LEFT_TOP].y = detection->rect.y1;
    rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_RIGHT_TOP].x = detection->rect.x2;
    rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_RIGHT_TOP].y = detection->rect.y1;
    rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_RIGHT_BOTTOM].x = detection->rect.x2;
    rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_RIGHT_BOTTOM].y = detection->rect.y2;
    rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_LEFT_BOTTOM].x = detection->rect.x1;
    rect_info->rect[idx].point[SAMPLE_SVP_NPU_RECT_LEFT_BOTTOM].y = detection->rect.y2;
    rect_info->ids[idx] = elevator_review_surface_label_id(detection);
    rect_info->num++;
}

static td_s32 elevator_render_rects_with_state(const ot_video_frame_info *frame, const elevator_parse_result *result)
{
    ot_sample_svp_rect_info person_rects;
    ot_sample_svp_rect_info tentative_rects;
    ot_sample_svp_rect_info held_rects;
    ot_sample_svp_rect_info child_rects;
    ot_sample_svp_rect_info ebike_rects;
    elevator_detection_result person_color_probe = {0};
    elevator_detection_result tentative_color_probe = {0};
    elevator_detection_result held_color_probe = {0};
    elevator_detection_result child_color_probe = {0};
    elevator_detection_result ebike_color_probe = {0};
    size_t idx;
    td_s32 ret = TD_SUCCESS;

    if (frame == TD_NULL || result == TD_NULL) {
        return TD_FAILURE;
    }

    memset(&person_rects, 0, sizeof(person_rects));
    memset(&tentative_rects, 0, sizeof(tentative_rects));
    memset(&held_rects, 0, sizeof(held_rects));
    memset(&child_rects, 0, sizeof(child_rects));
    memset(&ebike_rects, 0, sizeof(ebike_rects));
    person_color_probe.class_id = 0U;
    tentative_color_probe.class_id = 0U;
    tentative_color_probe.track_state = ELEVATOR_TRACK_STATE_TENTATIVE;
    held_color_probe.class_id = 0U;
    held_color_probe.track_state = ELEVATOR_TRACK_STATE_HELD;
    child_color_probe.class_id = 0U;
    child_color_probe.child_like = 1U;
    ebike_color_probe.class_id = 1U;

    for (idx = 0; idx < result->detection_count; ++idx) {
        const elevator_detection_result *detection = &result->detections[idx];
        if (detection->class_id == 1U) {
            elevator_append_rect(&ebike_rects, detection);
            continue;
        }
        if (detection->class_id != 0U) {
            continue;
        }
        if (g_elevator_config.review_surface == ELEVATOR_REVIEW_SURFACE_DEBUG &&
            detection->child_like != 0U) {
            elevator_append_rect(&child_rects, detection);
            continue;
        }
        if (g_elevator_config.review_surface == ELEVATOR_REVIEW_SURFACE_DEBUG &&
            detection->track_state == ELEVATOR_TRACK_STATE_TENTATIVE) {
            elevator_append_rect(&tentative_rects, detection);
            continue;
        }
        if (g_elevator_config.review_surface == ELEVATOR_REVIEW_SURFACE_DEBUG &&
            detection->track_state == ELEVATOR_TRACK_STATE_HELD) {
            elevator_append_rect(&held_rects, detection);
            continue;
        }
        elevator_append_rect(&person_rects, detection);
    }

    if (person_rects.num > 0) {
        ret = sample_common_svp_vgs_fill_rect(frame, &person_rects,
            elevator_review_surface_detection_color(g_elevator_config.review_surface, &person_color_probe));
        if (ret != TD_SUCCESS) {
            return ret;
        }
    }
    if (tentative_rects.num > 0) {
        ret = sample_common_svp_vgs_fill_rect(frame, &tentative_rects,
            elevator_review_surface_detection_color(g_elevator_config.review_surface, &tentative_color_probe));
        if (ret != TD_SUCCESS) {
            return ret;
        }
    }
    if (held_rects.num > 0) {
        ret = sample_common_svp_vgs_fill_rect(frame, &held_rects,
            elevator_review_surface_detection_color(g_elevator_config.review_surface, &held_color_probe));
        if (ret != TD_SUCCESS) {
            return ret;
        }
    }
    if (child_rects.num > 0) {
        ret = sample_common_svp_vgs_fill_rect(frame, &child_rects,
            elevator_review_surface_detection_color(g_elevator_config.review_surface, &child_color_probe));
        if (ret != TD_SUCCESS) {
            return ret;
        }
    }
    if (ebike_rects.num > 0) {
        ret = sample_common_svp_vgs_fill_rect(frame, &ebike_rects,
            elevator_review_surface_detection_color(g_elevator_config.review_surface, &ebike_color_probe));
        if (ret != TD_SUCCESS) {
            return ret;
        }
    }
    return TD_SUCCESS;
}

static td_s32 elevator_frame_proc(const ot_video_frame_info *ext_frame,
    const ot_video_frame_info *base_frame, elevator_parse_result *out_parse_result)
{
    const ot_video_frame_info *infer_frame = TD_NULL;
    td_s32 ret;
    td_u32 input_size;
    td_u8 *count_buffer = TD_NULL;
    td_u8 *roi_buffer = TD_NULL;
    size_t count_stride_floats = 0;
    size_t roi_stride_floats = 0;
    svp_acl_mdl_io_dims count_dims;
    svp_acl_mdl_io_dims roi_dims;
    size_t count_len;
    size_t roi_plane_count;
    size_t max_rois;
    uint64_t timestamp_ms;
    elevator_parse_result parse_result;
    elevator_frame_timing timing_ms;
    double frame_started_ms;
    double section_started_ms;
    int ebike_cleanup_mode;
    char errbuf[256];

    memset(&count_dims, 0, sizeof(count_dims));
    memset(&roi_dims, 0, sizeof(roi_dims));
    memset(&parse_result, 0, sizeof(parse_result));
    memset(&timing_ms, 0, sizeof(timing_ms));
    frame_started_ms = elevator_now_ms();

    section_started_ms = elevator_now_ms();
    ret = elevator_prepare_infer_frame(ext_frame, base_frame, &infer_frame);
    timing_ms.prepare_ms = elevator_elapsed_since_ms(section_started_ms);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    section_started_ms = elevator_now_ms();
    ret = elevator_preprocess_frame_to_bgr(infer_frame);
    timing_ms.preprocess_ms = elevator_elapsed_since_ms(section_started_ms);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    input_size = g_elevator_bgr_storage_size;
    if (g_elevator_logged_frame_contract == TD_FALSE) {
        printf("inference frame contract: source_pixel_format=%s(%d) size=%ux%u stride=[%u,%u] "
            "preprocess_output=%s preprocess_stride=%u actual_size=%u expected_size=%u expected_stride=%u\n",
            elevator_pixel_format_name(infer_frame->video_frame.pixel_format), infer_frame->video_frame.pixel_format,
            infer_frame->video_frame.width, infer_frame->video_frame.height,
            infer_frame->video_frame.stride[0], infer_frame->video_frame.stride[1],
            elevator_pixel_format_name(OT_PIXEL_FORMAT_BGR_888_PLANAR), g_elevator_bgr_input_image.stride[0],
            g_elevator_bgr_storage_size, g_elevator_model_input_size, g_elevator_model_input_stride);
        fflush(stdout);
        g_elevator_logged_frame_contract = TD_TRUE;
    }
    if (g_elevator_model_input_size != 0 && input_size < g_elevator_model_input_size) {
        fprintf(stderr,
            "frame/input mismatch: source_pixel_format=%s(%d) preprocess_output=%s actual_size=%u expected_size=%u "
            "frame_stride=[%u,%u] preprocess_stride=%u expected_stride=%u\n",
            elevator_pixel_format_name(infer_frame->video_frame.pixel_format), infer_frame->video_frame.pixel_format,
            elevator_pixel_format_name(OT_PIXEL_FORMAT_BGR_888_PLANAR), input_size, g_elevator_model_input_size,
            infer_frame->video_frame.stride[0], infer_frame->video_frame.stride[1],
            g_elevator_bgr_input_image.stride[0],
            g_elevator_model_input_stride);
        return TD_FAILURE;
    }
    section_started_ms = elevator_now_ms();
    ret = sample_common_svp_npu_update_input_data_buffer_info((td_u8 *)g_elevator_bgr_storage_virt, input_size,
        g_elevator_bgr_input_image.stride[0], 0, &g_elevator_task);
    timing_ms.input_update_ms = elevator_elapsed_since_ms(section_started_ms);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    section_started_ms = elevator_now_ms();
    ret = sample_common_svp_npu_model_execute(&g_elevator_task);
    timing_ms.model_execute_ms = elevator_elapsed_since_ms(section_started_ms);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    section_started_ms = elevator_now_ms();
    ret = elevator_get_output_buffer(ELEVATOR_OUTPUT_COUNT_NAME, ELEVATOR_OUTPUT_COUNT_NAME_FALLBACK,
        ELEVATOR_OUTPUT_KIND_COUNT, &count_buffer, &count_stride_floats, &count_dims);
    if (ret != TD_SUCCESS) {
        return ret;
    }
    ret = elevator_get_output_buffer(ELEVATOR_OUTPUT_ROI_NAME, ELEVATOR_OUTPUT_ROI_NAME_FALLBACK,
        ELEVATOR_OUTPUT_KIND_ROI, &roi_buffer, &roi_stride_floats, &roi_dims);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    if (count_dims.dim_count == 0 || roi_dims.dim_count < 2) {
        fprintf(stderr, "unexpected output dims\n");
        elevator_log_dims(stderr, ELEVATOR_OUTPUT_COUNT_NAME, &count_dims);
        elevator_log_dims(stderr, ELEVATOR_OUTPUT_ROI_NAME, &roi_dims);
        return TD_FAILURE;
    }

    count_len = count_dims.dims[count_dims.dim_count - 1];
    roi_plane_count = roi_dims.dims[roi_dims.dim_count - 2];
    max_rois = roi_dims.dims[roi_dims.dim_count - 1];
    timing_ms.output_fetch_ms = elevator_elapsed_since_ms(section_started_ms);
    if (roi_plane_count != ELEVATOR_OUTPUT_ROI_PLANES) {
        fprintf(stderr, "unexpected roi plane count: %zu\n", roi_plane_count);
        elevator_log_dims(stderr, ELEVATOR_OUTPUT_ROI_NAME, &roi_dims);
        return TD_FAILURE;
    }

    section_started_ms = elevator_now_ms();
    ebike_cleanup_mode = g_elevator_config.ebike_cleanup_mode;
    if (ebike_cleanup_mode == ELEVATOR_EBIKE_CLEANUP_CLI_AUTO) {
        ebike_cleanup_mode = out_parse_result == TD_NULL ?
            ELEVATOR_EBIKE_FP_CLEANUP_FULL : ELEVATOR_EBIKE_FP_CLEANUP_SAFE;
    }
    ret = elevator_parse_raw_outputs((const float *)count_buffer, count_len,
        (const float *)roi_buffer, roi_stride_floats, roi_plane_count, max_rois,
        infer_frame->video_frame.width, infer_frame->video_frame.height,
        base_frame->video_frame.width, base_frame->video_frame.height,
        g_elevator_config.score_threshold, g_elevator_config.nms_threshold,
        ebike_cleanup_mode, &parse_result, errbuf, sizeof(errbuf));
    timing_ms.postprocess_ms = elevator_elapsed_since_ms(section_started_ms);
    if (ret != 0) {
        fprintf(stderr, "postprocess failed: %s\n", errbuf);
        return TD_FAILURE;
    }

    section_started_ms = elevator_now_ms();
    timestamp_ms = sample_common_svp_npu_get_timestamp();
    elevator_temporal_hold_apply(&g_elevator_temporal_hold, &parse_result, timestamp_ms,
        base_frame->video_frame.width, base_frame->video_frame.height);
    elevator_person_tracker_apply(&g_elevator_person_tracker, &parse_result, timestamp_ms,
        base_frame->video_frame.width, base_frame->video_frame.height);
    elevator_ebike_tracker_apply(&g_elevator_ebike_tracker, &parse_result, timestamp_ms,
        base_frame->video_frame.width, base_frame->video_frame.height);
    elevator_smoother_update(&g_elevator_smoother, parse_result.stats.person_count,
        parse_result.stats.ebike_count, timestamp_ms, &parse_result.stats);
    timing_ms.temporal_ms = elevator_elapsed_since_ms(section_started_ms);

    section_started_ms = elevator_now_ms();
    elevator_build_render_result(&parse_result, &g_elevator_render_result,
        base_frame->video_frame.width, base_frame->video_frame.height);
    elevator_result_to_rect_info(&g_elevator_render_result, &g_elevator_rect_info);
    timing_ms.render_prepare_ms = elevator_elapsed_since_ms(section_started_ms);

    section_started_ms = elevator_now_ms();
    ret = elevator_render_rects_with_state(base_frame, &g_elevator_render_result);
    timing_ms.render_ms = elevator_elapsed_since_ms(section_started_ms);
    if (ret != TD_SUCCESS) {
        return ret;
    }

    if (g_elevator_config.osd_enable) {
        section_started_ms = elevator_now_ms();
        ret = elevator_osd_render_panel(base_frame, &parse_result.stats, &g_elevator_render_result,
            g_elevator_config.review_surface);
        if (ret != TD_SUCCESS) {
            return ret;
        }
        ret = elevator_osd_render_scores(base_frame, &g_elevator_rect_info, &g_elevator_render_result);
        if (ret != TD_SUCCESS) {
            return ret;
        }
        timing_ms.osd_ms = elevator_elapsed_since_ms(section_started_ms);
    }

    timing_ms.frame_proc_ms = elevator_elapsed_since_ms(frame_started_ms);
    parse_result.timing_ms = timing_ms;
    elevator_file_metrics_note_frame(&parse_result, timestamp_ms);

    if (out_parse_result != TD_NULL) {
        *out_parse_result = parse_result;
    }

    return TD_SUCCESS;
}

static td_void *elevator_process_thread(td_void *args)
{
    const td_s32 milli_sec = ELEVATOR_THREAD_TIMEOUT_MS;
    const ot_vo_layer vo_layer = 0;
    const ot_vo_chn vo_chn = 0;
    const td_s32 vpss_grp = 0;
    td_s32 vpss_chn[] = {OT_VPSS_CHN0, OT_VPSS_CHN1};
    td_s32 ret;
    ot_video_frame_info base_frame;
    ot_video_frame_info ext_frame;
    td_u32 input_size = 0;
    td_u32 input_stride = 0;
    td_u8 *input_data = TD_NULL;
    td_bool logged_once = TD_FALSE;
    td_u32 ext_timeout_count = 0;
    td_u32 base_timeout_count = 0;
    td_bool jpeg_infer_fallback = TD_FALSE;
    td_bool batch_mode = elevator_is_batch_mode();
    td_bool jpeg_payload = TD_FALSE;
    elevator_parse_result batch_parse_result;

    (void)args;
    memset(&base_frame, 0, sizeof(base_frame));
    memset(&ext_frame, 0, sizeof(ext_frame));
    memset(&batch_parse_result, 0, sizeof(batch_parse_result));

    ret = svp_acl_rt_set_device(g_elevator_dev_id);
    if (ret != TD_SUCCESS) {
        if (batch_mode == TD_TRUE) {
            g_elevator_batch_runtime.last_ret = ret;
        }
        elevator_request_stop();
        return TD_NULL;
    }

    ret = elevator_vb_map(OT_VPSS_CHN1);
    if (ret != TD_SUCCESS) {
        if (batch_mode == TD_TRUE) {
            g_elevator_batch_runtime.last_ret = ret;
        }
        elevator_request_stop();
        svp_acl_rt_reset_device(g_elevator_dev_id);
        return TD_NULL;
    }

    ret = sample_common_svp_npu_get_input_data_buffer_info(&g_elevator_task, 0, &input_data, &input_size, &input_stride);
    if (ret != TD_SUCCESS) {
        if (batch_mode == TD_TRUE) {
            g_elevator_batch_runtime.last_ret = ret;
        }
        elevator_request_stop();
        elevator_vb_unmap();
        svp_acl_rt_reset_device(g_elevator_dev_id);
        return TD_NULL;
    }

    while (g_elevator_thread_stop == TD_FALSE && g_elevator_terminate_signal == TD_FALSE) {
        jpeg_payload = elevator_is_jpeg_payload(g_elevator_input_payload_type);
        if (jpeg_infer_fallback == TD_FALSE) {
            ret = ss_mpi_vpss_get_chn_frame(vpss_grp, vpss_chn[1], &ext_frame, milli_sec);
            if (ret != TD_SUCCESS) {
                if (logged_once == TD_FALSE && elevator_should_log_first_frame_wait(batch_mode) == TD_TRUE) {
                    ext_timeout_count++;
                    if (ext_timeout_count == 1 || (ext_timeout_count % ELEVATOR_FIRST_FRAME_LOG_INTERVAL) == 0) {
                        elevator_log_waiting_for_first_frame("infer", ret, ext_timeout_count);
                        if (batch_mode != TD_TRUE) {
                            elevator_probe_base_channel_when_infer_empty(vpss_grp, vpss_chn[0]);
                        }
                    }
                }

                if (jpeg_payload == TD_TRUE) {
                    ret = ss_mpi_vpss_get_chn_frame(vpss_grp, vpss_chn[0], &base_frame, 0);
                    if (ret == TD_SUCCESS) {
                        jpeg_infer_fallback = TD_TRUE;
                        if (logged_once == TD_FALSE) {
                            printf("jpeg infer fallback engaged after %u infer wait retries\n", ext_timeout_count);
                            fflush(stdout);
                        }

                        if (logged_once == TD_FALSE) {
                            printf("frame loop entered\n");
                            logged_once = TD_TRUE;
                            if (batch_mode == TD_TRUE) {
                                g_elevator_batch_runtime.frame_loop_entered = TD_TRUE;
                            }
                        }

                        ret = elevator_frame_proc(TD_NULL, &base_frame,
                            batch_mode == TD_TRUE ? &batch_parse_result : TD_NULL);
                        if (ret == TD_SUCCESS) {
                            if (batch_mode == TD_TRUE) {
                                g_elevator_batch_runtime.used_fallback = TD_TRUE;
                                g_elevator_batch_runtime.frame_width = base_frame.video_frame.width;
                                g_elevator_batch_runtime.frame_height = base_frame.video_frame.height;
                                g_elevator_batch_runtime.parse_result = batch_parse_result;
                                ret = elevator_batch_save_frame_as_jpeg(&base_frame,
                                    g_elevator_batch_runtime.output_path);
                                if (ret == TD_SUCCESS) {
                                    g_elevator_batch_runtime.frame_saved = TD_TRUE;
                                    g_elevator_batch_runtime.last_ret = TD_SUCCESS;
                                }
                            } else {
                                ret = sample_common_svp_venc_vo_send_stream(&g_elevator_media_cfg.svp_switch, 0,
                                    vo_layer, vo_chn, &base_frame);
                            }
                        }
                        ss_mpi_vpss_release_chn_frame(vpss_grp, vpss_chn[0], &base_frame);
                        if (ret != TD_SUCCESS) {
                            fprintf(stderr, "frame process failed: %#x\n", ret);
                            if (batch_mode == TD_TRUE) {
                                g_elevator_batch_runtime.last_ret = ret;
                            }
                            elevator_request_stop();
                            break;
                        }
                        if (batch_mode == TD_TRUE) {
                            elevator_request_media_stop();
                            break;
                        }
                    }
                }
                if (logged_once == TD_FALSE && batch_mode == TD_TRUE && jpeg_payload == TD_TRUE &&
                    ext_timeout_count >= ELEVATOR_BATCH_FIRST_FRAME_MAX_RETRIES) {
                    g_elevator_batch_runtime.last_ret = ret;
                    elevator_request_media_stop();
                    break;
                }
                continue;
            }
            if (logged_once == TD_FALSE && ext_timeout_count != 0) {
                printf("first inference frame acquired after %u wait retries\n", ext_timeout_count);
                fflush(stdout);
                ext_timeout_count = 0;
            }
        }

        ret = ss_mpi_vpss_get_chn_frame(vpss_grp, vpss_chn[0], &base_frame, milli_sec);
        if (ret != TD_SUCCESS) {
            if (jpeg_infer_fallback == TD_FALSE) {
                ss_mpi_vpss_release_chn_frame(vpss_grp, vpss_chn[1], &ext_frame);
            }
            if (logged_once == TD_FALSE && elevator_should_log_first_frame_wait(batch_mode) == TD_TRUE) {
                base_timeout_count++;
                if (base_timeout_count == 1 || (base_timeout_count % ELEVATOR_FIRST_FRAME_LOG_INTERVAL) == 0) {
                    elevator_log_waiting_for_first_frame("base", ret, base_timeout_count);
                }
                if (batch_mode == TD_TRUE && base_timeout_count >= ELEVATOR_BATCH_FIRST_FRAME_MAX_RETRIES) {
                    g_elevator_batch_runtime.last_ret = ret;
                    elevator_request_media_stop();
                    break;
                }
            }
            continue;
        }
        if (logged_once == TD_FALSE && base_timeout_count != 0) {
            printf("first base frame acquired after %u wait retries\n", base_timeout_count);
            fflush(stdout);
            base_timeout_count = 0;
        }

        if (logged_once == TD_FALSE) {
            printf("frame loop entered\n");
            logged_once = TD_TRUE;
            if (batch_mode == TD_TRUE) {
                g_elevator_batch_runtime.frame_loop_entered = TD_TRUE;
            }
        }

        ret = elevator_frame_proc(jpeg_infer_fallback == TD_TRUE ? TD_NULL : &ext_frame, &base_frame,
            batch_mode == TD_TRUE ? &batch_parse_result : TD_NULL);
        if (ret == TD_SUCCESS) {
            if (batch_mode == TD_TRUE) {
                g_elevator_batch_runtime.used_fallback = jpeg_infer_fallback;
                g_elevator_batch_runtime.frame_width = base_frame.video_frame.width;
                g_elevator_batch_runtime.frame_height = base_frame.video_frame.height;
                g_elevator_batch_runtime.parse_result = batch_parse_result;
                ret = elevator_batch_save_frame_as_jpeg(&base_frame, g_elevator_batch_runtime.output_path);
                if (ret == TD_SUCCESS) {
                    g_elevator_batch_runtime.frame_saved = TD_TRUE;
                    g_elevator_batch_runtime.last_ret = TD_SUCCESS;
                }
            } else {
                ret = sample_common_svp_venc_vo_send_stream(&g_elevator_media_cfg.svp_switch, 0,
                    vo_layer, vo_chn, &base_frame);
            }
        }

        ss_mpi_vpss_release_chn_frame(vpss_grp, vpss_chn[0], &base_frame);
        if (jpeg_infer_fallback == TD_FALSE) {
            ss_mpi_vpss_release_chn_frame(vpss_grp, vpss_chn[1], &ext_frame);
        }
        if (ret != TD_SUCCESS) {
            fprintf(stderr, "frame process failed: %#x\n", ret);
            if (batch_mode == TD_TRUE) {
                g_elevator_batch_runtime.last_ret = ret;
            }
            elevator_request_stop();
            break;
        }
        if (batch_mode == TD_TRUE) {
            elevator_request_media_stop();
            break;
        }
    }

    if (input_data != TD_NULL && input_size != 0 && input_stride != 0) {
        (td_void)sample_common_svp_npu_update_input_data_buffer_info(input_data, input_size, input_stride, 0,
            &g_elevator_task);
    }
    if (batch_mode == TD_TRUE && g_elevator_batch_runtime.frame_saved == TD_FALSE &&
        g_elevator_batch_runtime.last_ret == TD_SUCCESS) {
        g_elevator_batch_runtime.last_ret = TD_FAILURE;
    }
    elevator_vb_unmap();
    svp_acl_rt_reset_device(g_elevator_dev_id);
    return TD_NULL;
}

static td_s32 elevator_setup_threshold(const elevator_runtime_config *config)
{
    sample_svp_npu_threshold threshold = {
        .nms_threshold = ELEVATOR_MODEL_NMS_THRESHOLD,
        .score_threshold = config->score_threshold,
        .min_height = 1.0f,
        .min_width = 1.0f,
        .name = ELEVATOR_THRESHOLD_INPUT_NAME,
    };

    return sample_common_svp_npu_set_threshold(&threshold, 1, &g_elevator_task);
}

static td_void elevator_wait_for_exit(td_void)
{
    const int stdin_fd = STDIN_FILENO;
    const int interactive_stdin = isatty(stdin_fd);

    if (interactive_stdin != 0) {
        printf("---------------press Enter key to exit!---------------\n");
    } else {
        printf("stdin is not interactive; waiting for stop signal\n");
    }
    fflush(stdout);

    while (g_elevator_terminate_signal == TD_FALSE && g_elevator_thread_stop == TD_FALSE) {
        if (interactive_stdin == 0) {
            usleep(200000);
            continue;
        }

        fd_set read_fds;
        struct timeval timeout;
        int ret;

        FD_ZERO(&read_fds);
        FD_SET(stdin_fd, &read_fds);
        timeout.tv_sec = 0;
        timeout.tv_usec = 200000;
        ret = select(stdin_fd + 1, &read_fds, NULL, NULL, &timeout);
        if (ret == 0) {
            continue;
        }
        if (ret < 0) {
            if (errno == EINTR) {
                continue;
            }
            break;
        }
        if (FD_ISSET(stdin_fd, &read_fds)) {
            char ch = '\0';
            ssize_t read_len = read(stdin_fd, &ch, 1);

            if (read_len <= 0) {
                continue;
            }
            if (ch == '\n') {
                break;
            }
        }
    }
}

static td_bool elevator_should_auto_stop_after_eof(td_void)
{
    return g_elevator_config.mode == ELEVATOR_RUN_MODE_FILE && isatty(STDIN_FILENO) == 0;
}

static td_s32 elevator_wait_for_file_decoder_drain(td_void)
{
    elevator_file_drain_state drain_state;
    elevator_file_drain_snapshot snapshot;
    td_u32 elapsed_ms = 0;
    ot_vdec_chn_status status;
    elevator_file_drain_decision decision;
    td_s32 ret;

    memset(&drain_state, 0, sizeof(drain_state));
    memset(&snapshot, 0, sizeof(snapshot));

    while (elapsed_ms < ELEVATOR_FILE_DRAIN_MAX_WAIT_MS) {
        ret = ss_mpi_vdec_query_status(g_elevator_vdec_param.chn_id, &status);
        if (ret != TD_SUCCESS) {
            fprintf(stderr, "file-mode decoder drain query failed: %#x\n", ret);
            return ret;
        }

        snapshot.left_stream_bytes = status.left_stream_bytes;
        snapshot.left_stream_frames = status.left_stream_frames;
        snapshot.left_decoded_frames = status.left_decoded_frames;
        snapshot.processed_frame_count = g_elevator_file_metrics_runtime.frame_count;

        decision = elevator_file_drain_step(
            &drain_state,
            &snapshot,
            ELEVATOR_FILE_DRAIN_POLL_US / 1000,
            ELEVATOR_FILE_DRAIN_TIMEOUT_MS,
            ELEVATOR_FILE_DRAIN_STABLE_POLLS);
        if (decision == ELEVATOR_FILE_DRAIN_DECISION_READY) {
            return TD_SUCCESS;
        }
        if (decision == ELEVATOR_FILE_DRAIN_DECISION_TIMED_OUT) {
            break;
        }
        usleep(ELEVATOR_FILE_DRAIN_POLL_US);
        elapsed_ms += (ELEVATOR_FILE_DRAIN_POLL_US / 1000);
    }

    fprintf(stderr,
        "warning: file-mode decoder drain timed out after %u ms idle (%u ms total, processed_frames=%llu, left_bytes=%u, left_frames=%u, left_decoded=%u)\n",
        drain_state.idle_elapsed_ms,
        elapsed_ms,
        (unsigned long long)snapshot.processed_frame_count,
        snapshot.left_stream_bytes,
        snapshot.left_stream_frames,
        snapshot.left_decoded_frames);
    return TD_FAILURE;
}

static td_s32 elevator_wait_for_file_completion(td_void)
{
    td_s32 ret;

    if (g_elevator_vdec_thread != 0) {
        printf("decoding..............");
        fflush(stdout);
        if (pthread_join(g_elevator_vdec_thread, TD_NULL) == 0) {
            g_elevator_vdec_thread = 0;
            printf("file-mode send stream joined after EOF\n");
            fflush(stdout);
        } else {
            fprintf(stderr, "warning: file-mode send stream join failed\n");
            g_elevator_vdec_thread = 0;
        }
    }
    ret = elevator_wait_for_file_decoder_drain();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "warning: file-mode decoder did not report fully drained; continuing after EOF join\n");
    }
    return TD_SUCCESS;
}

static td_s32 elevator_run_single_batch_image(const char *image_path, const char *output_path,
    elevator_batch_image_report *report)
{
    td_bool osd_initialized = TD_FALSE;
    td_bool jpeg_encoder_started = TD_FALSE;
    td_s32 ret;

    if (image_path == TD_NULL || output_path == TD_NULL || report == TD_NULL) {
        return TD_FAILURE;
    }

    g_elevator_thread_stop = TD_FALSE;
    g_elevator_terminate_signal = TD_FALSE;
    g_elevator_logged_frame_contract = TD_FALSE;
    g_elevator_logged_jpeg_infer_fallback = TD_FALSE;
    g_elevator_vb_virt_addr = TD_NULL;
    memset(&g_elevator_vb_pool_info, 0, sizeof(g_elevator_vb_pool_info));
    snprintf(g_elevator_config.input_path, sizeof(g_elevator_config.input_path), "%s", image_path);
    elevator_batch_prepare_image(output_path);

    ret = elevator_configure_input_stream(&g_elevator_config);
    if (ret != TD_SUCCESS) {
        g_elevator_batch_runtime.last_ret = ret;
        return ret;
    }

    ret = elevator_batch_ensure_task_ready();
    if (ret != TD_SUCCESS) {
        g_elevator_batch_runtime.last_ret = ret;
        return ret;
    }

    g_elevator_media_cfg.svp_switch.is_venc_open = TD_FALSE;
    g_elevator_media_cfg.pic_type[1] = PIC_BUTT;
    ret = elevator_init_media();
    if (ret != TD_SUCCESS) {
        g_elevator_batch_runtime.last_ret = ret;
        return ret;
    }

    ret = elevator_batch_start_jpeg_encoder();
    if (ret != TD_SUCCESS) {
        g_elevator_batch_runtime.last_ret = ret;
        goto batch_end0;
    }
    jpeg_encoder_started = TD_TRUE;

    if (g_elevator_config.osd_enable) {
        ret = elevator_osd_init(g_elevator_vo_cfg.image_size.width, g_elevator_vo_cfg.image_size.height);
        if (ret != TD_SUCCESS) {
            g_elevator_batch_runtime.last_ret = ret;
            goto batch_end0;
        }
        osd_initialized = TD_TRUE;
    }

    ret = pthread_create(&g_elevator_thread, TD_NULL, elevator_process_thread, TD_NULL);
    if (ret != 0) {
        g_elevator_batch_runtime.last_ret = TD_FAILURE;
        ret = TD_FAILURE;
        goto batch_end1;
    }

    pthread_join(g_elevator_thread, TD_NULL);
    g_elevator_thread = 0;
    ret = g_elevator_batch_runtime.last_ret;
    report->timing_ms = g_elevator_batch_runtime.parse_result.timing_ms;
    if (ret == TD_SUCCESS && g_elevator_batch_runtime.frame_saved == TD_TRUE) {
        report->success = 1;
        report->fallback_used = g_elevator_batch_runtime.used_fallback;
        report->frame_width = g_elevator_batch_runtime.frame_width;
        report->frame_height = g_elevator_batch_runtime.frame_height;
        snprintf(report->output_path, sizeof(report->output_path), "%s", output_path);
    }

batch_end1:
    if (osd_initialized == TD_TRUE) {
        elevator_osd_deinit();
    }
    if (jpeg_encoder_started == TD_TRUE) {
        elevator_batch_stop_jpeg_encoder();
    }
batch_end0:
    elevator_release_scaled_infer_frame();
    elevator_release_preprocess_buffer();
    elevator_deinit_media();
    return ret;
}

static td_void elevator_cleanup_rtsp(td_void)
{
    if (session_h264 != NULL) {
        rtsp_del_session(session_h264);
        session_h264 = NULL;
    }
    if (g_rtsplive != NULL) {
        rtsp_del_demo(g_rtsplive);
        g_rtsplive = NULL;
    }
}

int elevator_run_file(const elevator_runtime_config *config)
{
    td_bool osd_initialized = TD_FALSE;
    td_bool file_metrics_initialized = TD_FALSE;
    td_s32 ret;
    char resolved_model_path[ELEVATOR_PATH_MAX];

    if (config == NULL) {
        return 1;
    }

    elevator_reset_runtime_state();
    memcpy(&g_elevator_config, config, sizeof(g_elevator_config));
    elevator_smoother_reset(&g_elevator_smoother, config->smooth_window);
    elevator_temporal_hold_reset(&g_elevator_temporal_hold,
        ELEVATOR_PERSON_HOLD_MAX_FRAMES, ELEVATOR_PERSON_HOLD_MAX_MS);
    elevator_person_tracker_reset(&g_elevator_person_tracker,
        ELEVATOR_PERSON_HOLD_MAX_FRAMES, ELEVATOR_PERSON_HOLD_MAX_MS);
    elevator_ebike_tracker_reset(&g_elevator_ebike_tracker, 1U, 250U);
    ret = elevator_file_metrics_open(config->output_dir);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "file metrics init failed for %s\n", config->output_dir);
        return 1;
    }
    file_metrics_initialized = (config->output_dir[0] != '\0');

    ret = elevator_configure_input_stream(config);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "failed to configure input stream\n");
        if (file_metrics_initialized == TD_TRUE) {
            elevator_file_metrics_close();
        }
        return 1;
    }
    (td_void)elevator_write_runtime_contract(0);

    g_rtsplive = create_rtsp_demo((int)config->rtsp_port);
    session_h264 = create_rtsp_session(g_rtsplive, RTSP_CODEC_ID_VIDEO_H264, "/live.h264");
    printf("rtsp session created\n");

    ret = elevator_init_acl();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "acl init failed: %#x\n", ret);
        elevator_cleanup_rtsp();
        return 1;
    }

    if (elevator_resolve_model_path(config->model_path, resolved_model_path, sizeof(resolved_model_path)) != TD_SUCCESS) {
        fprintf(stderr, "failed to resolve model path from %s\n", config->model_path);
        ret = TD_FAILURE;
        goto process_end0;
    }
    printf("using model path: %s\n", resolved_model_path);

    g_elevator_media_cfg.pic_type[1] = PIC_BUTT;
    ret = sample_common_svp_npu_load_model(resolved_model_path, ELEVATOR_MODEL_INDEX, TD_FALSE);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "load model failed: %#x\n", ret);
        goto process_end0;
    }
    printf("load model success\n");
    elevator_log_model_input_contract();
    elevator_log_model_outputs();
    ret = elevator_resolve_model_outputs();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "resolve model outputs failed: %#x\n", ret);
        goto process_end1;
    }

    ret = sample_common_svp_npu_get_input_resolution(ELEVATOR_MODEL_INDEX, 0, &g_elevator_media_cfg.pic_size[1]);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "get input resolution failed: %#x\n", ret);
        goto process_end1;
    }
    printf("input resolution detected: %ux%u\n",
        g_elevator_media_cfg.pic_size[1].width, g_elevator_media_cfg.pic_size[1].height);

    ret = elevator_init_media();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "media init failed: %#x\n", ret);
        goto process_end1;
    }

    elevator_set_task_info();
    ret = elevator_init_task();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "task init failed: %#x\n", ret);
        goto process_end2;
    }
    ret = elevator_sync_input_contract();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "get model input buffer info failed: %#x\n", ret);
        goto process_end3;
    }

    ret = elevator_setup_threshold(config);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "set threshold failed: %#x\n", ret);
        goto process_end3;
    }

    if (config->osd_enable) {
        ret = elevator_osd_init(g_elevator_vo_cfg.image_size.width, g_elevator_vo_cfg.image_size.height);
        if (ret != TD_SUCCESS) {
            fprintf(stderr, "osd init failed: %#x\n", ret);
            goto process_end4;
        }
        osd_initialized = TD_TRUE;
    }
    ret = pthread_create(&g_elevator_thread, NULL, elevator_process_thread, NULL);
    if (ret != 0) {
        fprintf(stderr, "process thread create failed: %d\n", ret);
        ret = TD_FAILURE;
        goto process_end4;
    }

    if (elevator_should_auto_stop_after_eof() == TD_TRUE) {
        printf("stdin is not interactive; waiting for file EOF and pipeline drain\n");
        fflush(stdout);
        ret = elevator_wait_for_file_completion();
        if (ret != TD_SUCCESS) {
            fprintf(stderr, "warning: file-mode EOF completion returned %#x\n", ret);
        }
    } else {
        elevator_wait_for_exit();
    }
    elevator_request_media_stop();
    pthread_join(g_elevator_thread, NULL);
    g_elevator_thread = 0;
    if (file_metrics_initialized == TD_TRUE) {
        (td_void)elevator_write_runtime_contract(g_elevator_file_metrics_runtime.frame_count);
    }

process_end4:
    if (osd_initialized == TD_TRUE) {
        elevator_osd_deinit();
    }
process_end3:
    elevator_deinit_task();
    elevator_release_preprocess_buffer();
    elevator_release_scaled_infer_frame();
process_end2:
    elevator_deinit_media();
process_end1:
    sample_common_svp_npu_unload_model(ELEVATOR_MODEL_INDEX);
process_end0:
    if (file_metrics_initialized == TD_TRUE) {
        elevator_file_metrics_close();
    }
    elevator_deinit_acl();
    elevator_cleanup_rtsp();
    return ret == TD_SUCCESS ? 0 : 1;
}

int elevator_run_batch(const elevator_runtime_config *config)
{
    elevator_batch_image_list image_list;
    elevator_batch_eval_context *eval_ctx = TD_NULL;
    elevator_batch_summary summary;
    FILE *per_image_stream = TD_NULL;
    FILE *detections_stream = TD_NULL;
    char output_dir[ELEVATOR_PATH_MAX];
    char annotated_dir[ELEVATOR_PATH_MAX];
    char summary_path[ELEVATOR_PATH_MAX];
    char per_image_path[ELEVATOR_PATH_MAX];
    char detections_path[ELEVATOR_PATH_MAX];
    char resolved_model_path[ELEVATOR_PATH_MAX];
    char errbuf[256];
    td_s32 ret;
    size_t idx;
    int exit_code = 1;

    if (config == TD_NULL) {
        return 1;
    }

    memset(&image_list, 0, sizeof(image_list));
    memset(&summary, 0, sizeof(summary));
    output_dir[0] = '\0';
    annotated_dir[0] = '\0';
    summary_path[0] = '\0';
    per_image_path[0] = '\0';
    detections_path[0] = '\0';
    errbuf[0] = '\0';

    if (elevator_batch_make_output_dir(config->output_dir, output_dir, sizeof(output_dir),
            errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "batch output dir error: %s\n", errbuf);
        return 1;
    }
    if (snprintf(annotated_dir, sizeof(annotated_dir), "%s/annotated", output_dir) >= (int)sizeof(annotated_dir) ||
        ((mkdir(annotated_dir, 0755) != 0) && errno != EEXIST)) {
        fprintf(stderr, "failed to create annotated output dir: %s\n", annotated_dir);
        return 1;
    }
    if (snprintf(summary_path, sizeof(summary_path), "%s/summary.json", output_dir) >= (int)sizeof(summary_path) ||
        snprintf(per_image_path, sizeof(per_image_path), "%s/per_image.csv", output_dir) >= (int)sizeof(per_image_path) ||
        snprintf(detections_path, sizeof(detections_path), "%s/detections.jsonl", output_dir) >=
            (int)sizeof(detections_path)) {
        fprintf(stderr, "batch output path is too long\n");
        return 1;
    }

    if (elevator_batch_collect_images(config->images_dir, config->labels_dir, config->offset, config->limit, &image_list,
            errbuf, sizeof(errbuf)) != 0) {
        fprintf(stderr, "batch input discovery failed: %s\n", errbuf);
        return 1;
    }
    if (image_list.count == 0) {
        fprintf(stderr, "batch mode found no jpeg images in %s\n", config->images_dir);
        goto batch_cleanup0;
    }

    per_image_stream = fopen(per_image_path, "w");
    detections_stream = fopen(detections_path, "w");
    if (per_image_stream == TD_NULL || detections_stream == TD_NULL) {
        fprintf(stderr, "failed to open batch output files under %s\n", output_dir);
        goto batch_cleanup1;
    }
    if (elevator_batch_write_per_image_header(per_image_stream) != 0) {
        fprintf(stderr, "failed to initialize per_image.csv\n");
        goto batch_cleanup2;
    }

    eval_ctx = elevator_batch_eval_create();
    if (eval_ctx == TD_NULL) {
        fprintf(stderr, "failed to allocate batch evaluator\n");
        goto batch_cleanup2;
    }

    elevator_reset_runtime_state();
    memcpy(&g_elevator_config, config, sizeof(g_elevator_config));
    snprintf(g_elevator_config.output_dir, sizeof(g_elevator_config.output_dir), "%s", output_dir);
    g_elevator_media_cfg.svp_switch.is_venc_open = TD_FALSE;

    ret = elevator_init_acl();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "acl init failed: %#x\n", ret);
        goto batch_cleanup3;
    }

    if (elevator_resolve_model_path(config->model_path, resolved_model_path, sizeof(resolved_model_path)) != TD_SUCCESS) {
        fprintf(stderr, "failed to resolve model path from %s\n", config->model_path);
        ret = TD_FAILURE;
        goto batch_cleanup4;
    }
    printf("using model path: %s\n", resolved_model_path);

    ret = sample_common_svp_npu_load_model(resolved_model_path, ELEVATOR_MODEL_INDEX, TD_FALSE);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "load model failed: %#x\n", ret);
        goto batch_cleanup4;
    }
    printf("load model success\n");
    elevator_log_model_input_contract();
    elevator_log_model_outputs();

    ret = elevator_resolve_model_outputs();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "resolve model outputs failed: %#x\n", ret);
        goto batch_cleanup5;
    }

    ret = sample_common_svp_npu_get_input_resolution(ELEVATOR_MODEL_INDEX, 0, &g_elevator_media_cfg.pic_size[1]);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "get input resolution failed: %#x\n", ret);
        goto batch_cleanup5;
    }
    printf("input resolution detected: %ux%u\n",
        g_elevator_media_cfg.pic_size[1].width, g_elevator_media_cfg.pic_size[1].height);

    elevator_set_task_info();
    ret = elevator_init_task();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "task init failed: %#x\n", ret);
        goto batch_cleanup5;
    }
    ret = elevator_sync_input_contract();
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "get model input buffer info failed: %#x\n", ret);
        goto batch_cleanup6;
    }
    ret = elevator_setup_threshold(config);
    if (ret != TD_SUCCESS) {
        fprintf(stderr, "set threshold failed: %#x\n", ret);
        goto batch_cleanup6;
    }
    for (idx = 0; idx < image_list.count; ++idx) {
        elevator_batch_image_report report;
        elevator_batch_gt_box gt_boxes[ELEVATOR_BATCH_MAX_LABELS];
        size_t gt_count = 0;
        const elevator_detection_result *detections = TD_NULL;
        size_t detection_count = 0;
        char annotated_path[ELEVATOR_PATH_MAX];
        double started_ms;
        double elapsed_ms;

        memset(&report, 0, sizeof(report));
        memset(gt_boxes, 0, sizeof(gt_boxes));
        snprintf(report.image_name, sizeof(report.image_name), "%s", image_list.items[idx].image_name);
        snprintf(report.image_path, sizeof(report.image_path), "%s", image_list.items[idx].image_path);
        snprintf(report.label_path, sizeof(report.label_path), "%s", image_list.items[idx].label_path);
        if (snprintf(annotated_path, sizeof(annotated_path), "%s/%s", annotated_dir,
                image_list.items[idx].image_name) >= (int)sizeof(annotated_path)) {
            fprintf(stderr, "annotated output path too long for %s\n", image_list.items[idx].image_name);
            goto batch_cleanup7;
        }

        if (elevator_batch_load_yolo_labels(image_list.items[idx].label_path,
                g_elevator_vo_cfg.image_size.width, g_elevator_vo_cfg.image_size.height,
                gt_boxes, ELEVATOR_BATCH_MAX_LABELS, &gt_count, errbuf, sizeof(errbuf)) != 0) {
            fprintf(stderr, "failed to load labels for %s: %s\n", image_list.items[idx].image_name, errbuf);
            goto batch_cleanup7;
        }

        started_ms = elevator_now_ms();
        ret = elevator_run_single_batch_image(image_list.items[idx].image_path, annotated_path, &report);
        elapsed_ms = elevator_now_ms() - started_ms;
        report.elapsed_ms = elapsed_ms;
        report.frame_width = report.frame_width != 0 ? report.frame_width : g_elevator_vo_cfg.image_size.width;
        report.frame_height = report.frame_height != 0 ? report.frame_height : g_elevator_vo_cfg.image_size.height;
        if (report.success == 0) {
            snprintf(report.output_path, sizeof(report.output_path), "%s", annotated_path);
            report.fallback_used = g_elevator_batch_runtime.used_fallback;
            elevator_batch_eval_mark_failure(eval_ctx, &report);
            elevator_batch_eval_note_run(eval_ctx, elapsed_ms, report.fallback_used);
        } else {
            detections = g_elevator_batch_runtime.parse_result.detections;
            detection_count = g_elevator_batch_runtime.parse_result.detection_count;
            if (elevator_batch_eval_image(eval_ctx, gt_boxes, gt_count, detections, detection_count,
                    ELEVATOR_BATCH_IOU_THRESHOLD, &report) != 0) {
                fprintf(stderr, "batch metric evaluation failed for %s\n", image_list.items[idx].image_name);
                goto batch_cleanup7;
            }
            report.elapsed_ms = elapsed_ms;
            report.fallback_used = g_elevator_batch_runtime.used_fallback;
            elevator_batch_eval_note_run(eval_ctx, elapsed_ms, report.fallback_used);
            elevator_batch_eval_note_timing(eval_ctx, &report.timing_ms);
        }

        if (elevator_batch_write_per_image_row(per_image_stream, &report) != 0 ||
            elevator_batch_write_detections_jsonl(detections_stream, &report, gt_boxes, gt_count,
                detections != TD_NULL ? detections : g_elevator_batch_runtime.parse_result.detections,
                detections != TD_NULL ? detection_count : 0) != 0) {
            fprintf(stderr, "failed to write batch structured outputs\n");
            goto batch_cleanup7;
        }
        fflush(per_image_stream);
        fflush(detections_stream);
    }

    elevator_batch_eval_finalize(eval_ctx, &summary);
    if (elevator_batch_write_summary_json(summary_path, config->images_dir, config->labels_dir, output_dir,
            config->limit, config->score_threshold, config->nms_threshold, &summary) != 0) {
        fprintf(stderr, "failed to write summary.json\n");
        goto batch_cleanup7;
    }
    printf("batch run complete: images=%zu success=%llu failure=%llu map50=%.6f output_dir=%s\n",
        image_list.count, (unsigned long long)summary.success_count,
        (unsigned long long)summary.failure_count, summary.map50, output_dir);
    exit_code = 0;

batch_cleanup7:
batch_cleanup6:
    elevator_deinit_task();
    elevator_release_preprocess_buffer();
    elevator_release_scaled_infer_frame();
batch_cleanup5:
    sample_common_svp_npu_unload_model(ELEVATOR_MODEL_INDEX);
batch_cleanup4:
    elevator_deinit_acl();
batch_cleanup3:
    elevator_batch_eval_destroy(eval_ctx);
batch_cleanup2:
    if (detections_stream != TD_NULL) {
        fclose(detections_stream);
    }
    if (per_image_stream != TD_NULL) {
        fclose(per_image_stream);
    }
batch_cleanup1:
    elevator_batch_free_image_list(&image_list);
batch_cleanup0:
    return exit_code;
}

int elevator_run_camera(const elevator_runtime_config *config)
{
    (void)config;
    fprintf(stderr, "camera mode is not implemented in v1\n");
    return 2;
}
