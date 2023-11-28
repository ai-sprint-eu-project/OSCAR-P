# processing that take place right after collecting the logs

import csv
import pickle
import os
import shutil

from termcolor import colored
from zipfile import ZipFile, ZIP_DEFLATED

# given a run, it creates a CSV file containing all the jobs of every service (as red from the timelists)
# todo can probably be split into sub-functions
# todo out of order until updated to include SCAR
def make_csv_table(working_dir, services, clusters, current_run_index):
    print(colored("Processing logs...", "yellow"))

    services = []  # todo this whole thing is being skipped, just kept the zip
    for service in services:

        service_name = service["name"]
        # cluster = get_active_cluster(service, clusters)

        nodes_used = cluster["nodes"][current_run_index]

        cores_total, memory_total = cluster["max_cpu_cores"], cluster["max_memory_mb"]
        total_nodes = cluster["total_nodes"]
        # print(cores_total, total_nodes, memory_total)

        with open(working_dir + "/time_table_" + service_name + ".pkl", "rb") as file:
            timed_job_list = pickle.load(file)

        header = ["job_name", "service", "cluster", "node",
                  "cores_container", "cores_total", "memory_container", "memory_total", "nodes_used", "nodes_total",
                  "full_time", "wait", "pod_creation", "overhead", "compute_time", "write_back"
                  ]

        data = []

        if len(timed_job_list) != 0:

            cores_container = service["cpu"]
            memory_container = service["memory"]

            for job_name in timed_job_list.keys():
                job = timed_job_list[job_name]

                node = job["node"]
                full_time = (job["job_finish"] - job["job_create"]).total_seconds()
                # wait = (job["pod_create"] - job["job_create"]).total_seconds()
                wait = 2  # todo shouldn't this be fixed?
                # pod_creation = (job["job_start"] - job["pod_create"]).total_seconds()
                pod_creation = 5
                overhead = (job["bash_script_start"] - job["job_start"]).total_seconds()
                compute_time = (job["bash_script_end"] - job["bash_script_start"]).total_seconds()
                write_back = (job["job_finish"] - job["bash_script_end"]).total_seconds()

                row = [job_name, service_name, node,
                       cores_container, cores_total, memory_container, memory_total, nodes_used, total_nodes,
                       full_time, wait, pod_creation, overhead, compute_time, write_back]

                data.append(row)

        with open(working_dir + "/" + service_name + "_jobs.csv", "w", encoding="UTF8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(header)
            writer.writerows(data)

    # zip_logs(working_dir)

    print(colored("Done!", "green"))
    return


def zip_logs(working_dir):
    with ZipFile(working_dir + "/logs.zip", "w", ZIP_DEFLATED) as zip_file:
        for file in os.listdir(working_dir + "/logs_kubectl"):
            zip_file.write(working_dir + "/logs_kubectl/" + file)
        for file in os.listdir(working_dir + "/logs_oscar"):
            zip_file.write(working_dir + "/logs_oscar/" + file)
    delete_logs_folder(working_dir)
    return


def delete_logs_folder(working_dir):
    shutil.rmtree(working_dir + "/logs_kubectl")
    shutil.rmtree(working_dir + "/logs_oscar")
    return


def make_done_file(target_dir):
    open(target_dir + "/done", "a").close()
