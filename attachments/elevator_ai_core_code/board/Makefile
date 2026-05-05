ROOT_DIR := $(CURDIR)
SDK_ROOT ?= /home/ywj/resource/hi3519dv500/smp/a55_linux/source
PARAM_FILE := $(SDK_ROOT)/Makefile.param
SAMPLE_PARAM := /home/ywj/elevator_ai/deployment/02_sample/Makefile.param

include $(PARAM_FILE)
include $(SAMPLE_PARAM)

TARGET := elevator_yolo
HOST_TEST := tests/test_host
HOST_CC ?= cc

APP_SRCS := \
	src/main.c \
	src/elevator_batch.c \
	src/elevator_cli.c \
	src/elevator_panel_text.c \
	src/elevator_postprocess.c \
	src/elevator_osd.c \
	src/elevator_runtime_policy.c \
	src/elevator_yolo.c \
	src/sample_common_svp.c \
	src/sample_common_svp_npu.c \
	src/sample_common_svp_npu_model.c \
	src/sample_comm_sys.c \
	src/sample_comm_isp.c \
	src/sample_comm_mipi_tx.c \
	src/sample_comm_vdec.c \
	src/sample_comm_venc.c \
	src/sample_comm_vi.c \
	src/sample_comm_vo.c \
	src/sample_comm_vpss.c \
	src/rtsp_demo.c \
	src/rtsp_msg.c \
	src/rtp_enc.c \
	src/stream_queue.c \
	src/utils.c

APP_OBJS := $(APP_SRCS:.c=.o)
HOST_TEST_SRCS := tests/test_host.c src/elevator_cli.c src/elevator_panel_text.c src/elevator_postprocess.c src/elevator_batch.c \
	src/elevator_runtime_policy.c

CFLAGS += -I$(ROOT_DIR)/include
CFLAGS += -O2 -Wall -ffunction-sections
LDFLAGS += -Wl,--gc-sections

.PHONY: all clean test-host package check-sdk

all: $(TARGET)

check-sdk:
	@test -d "$(SDK_ROOT)/out/include" || { echo "missing $(SDK_ROOT)/out/include"; \
		echo "run: bash /home/ywj/resource/hi3519dv500/sdk.unpack"; exit 1; }
	@test -d "$(SDK_ROOT)/out/lib" || { echo "missing $(SDK_ROOT)/out/lib"; \
		echo "run: bash /home/ywj/resource/hi3519dv500/sdk.unpack"; exit 1; }
	@command -v aarch64-linux-gnu-gcc >/dev/null 2>&1 || { \
		echo "missing aarch64-linux-gnu-gcc in PATH"; \
		echo "run: source /home/ywj/hi3516dv500_toolchain/env_setup.sh"; exit 1; }

$(TARGET): check-sdk $(APP_OBJS)
	$(CC) $(CFLAGS) -o $@ $(APP_OBJS) $(LDFLAGS) \
		-Wl,--start-group $(MPI_LIBS) $(SENSOR_LIBS) $(AUDIO_LIBA) $(REL_LIB)/libsecurec.a -Wl,--end-group

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

test-host:
	$(HOST_CC) -I$(ROOT_DIR)/include -O2 -Wall $(HOST_TEST_SRCS) -lm -o $(HOST_TEST)
	./$(HOST_TEST)

package: $(TARGET)
	bash ./scripts/deploy.sh --package

clean:
	rm -f $(APP_OBJS) $(TARGET) $(HOST_TEST)
