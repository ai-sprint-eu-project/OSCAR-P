"""
Copyright 2023 AI-SPRINT

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from datetime import datetime

import global_parameters as gp


# todo once done testing, move this stuff to logs processing or similar


def calculate_throughput(timed_job_list):
    date_format = "%Y-%m-%d %H:%M:%S"

    start = list(timed_job_list.values())[0]["start_time"]
    end = list(timed_job_list.values())[-1]["end_time"]

    start = datetime.strptime(start, date_format)
    end = datetime.strptime(end, date_format)

    test_duration = end - start
    test_duration = test_duration.total_seconds()

    requests_count = len(timed_job_list)

    throughput_second = round(requests_count / test_duration, 3)
    throughput_minute = round(requests_count * 60 / test_duration, 3)

    print("Throughput: ", throughput_second, "req/s")
    print("Throughput: ", throughput_minute, "req/min")

    return throughput_second


def main(service_name):
    print(gp.current_work_dir)

    date_format = "%Y-%m-%d %H:%M:%S"

    with open("results.csv", "r") as file:
        data = file.readlines()

    timed_job_list = {}

    for line in data[1:]:
        timestamp, elapsed = line.split(",")[:2]

        thread_name = line.split(",")[5]
        interval = thread_name.split()[2]

        if interval != "1":
            key = timestamp

            timed_job_list[key] = {
                "name": service_name
            }

            dt = datetime.fromtimestamp(int(timestamp[:-3]))
            start_time = datetime.strftime(dt, date_format)

            timestamp = str(int(timestamp) + int(elapsed))
            dt = datetime.fromtimestamp(int(timestamp[:-3]))
            end_time = datetime.strftime(dt, date_format)

            timed_job_list[key]["start_time"] = start_time
            timed_job_list[key]["end_time"] = end_time
            timed_job_list[key]["interval"] = interval

    if not gp.is_single_service_test:
        gp.throughput = calculate_throughput(timed_job_list)

    # todo save this to file, use it for the graphs and shit


if __name__ == '__main__':
    main("blurry")
