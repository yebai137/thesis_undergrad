#include "elevator_yolo.h"

#include <signal.h>
#include <stdio.h>

static void elevator_signal_handler(int signo)
{
    (void)signo;
    elevator_request_stop();
}

int main(int argc, char **argv)
{
    elevator_runtime_config config;
    char errbuf[256];
    int ret;

    ret = elevator_parse_cli(argc, argv, &config, errbuf, sizeof(errbuf));
    if (ret != 0) {
        fprintf(stderr, "argument error: %s\n", errbuf);
        elevator_print_usage(argc > 0 ? argv[0] : "elevator_yolo");
        return 1;
    }

    if (config.mode == ELEVATOR_RUN_MODE_HELP) {
        elevator_print_usage(argc > 0 ? argv[0] : "elevator_yolo");
        return 0;
    }

    signal(SIGINT, elevator_signal_handler);
    signal(SIGTERM, elevator_signal_handler);

    if (config.mode == ELEVATOR_RUN_MODE_CAMERA) {
        return elevator_run_camera(&config);
    }
    if (config.mode == ELEVATOR_RUN_MODE_BATCH) {
        return elevator_run_batch(&config);
    }
    return elevator_run_file(&config);
}
