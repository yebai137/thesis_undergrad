import traceback
import sys
import runpy

print("Running quantize_yolov8.py through wrapper...")
try:
    runpy.run_path("quantize_yolov8.py", run_name="__main__")
    print("Execution finished normally.")
except BaseException as e:
    print("Caught exception:")
    traceback.print_exc()
    print("Exception Type:", type(e))
print("Wrapper exiting.")
