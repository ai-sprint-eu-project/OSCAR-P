# oscar and kubectl logs are saved as txts and processed in dictionaries saved as pickle files
import json
import pickle
import os

from tqdm import tqdm

import executables

from termcolor import colored
from datetime import datetime, timedelta

import jmeterLoadInjector
from cluster_manager import set_default_oscar_cluster_from_alias
from utils import configure_ssh_client, get_ssh_output, get_command_output_wrapped, show_debug_info, read_yaml, \
    write_yaml, show_error, auto_mkdir

import global_parameters as gp

# todo must comment more everywhere


def pull_logs():

    if gp.has_active_lambdas:
        auto_mkdir(gp.current_run_dir + "logs_lambda")
        pull_lambda_logs()

    pull_jmeter_logs(gp.current_services_list[0].name)

    print(colored("Done!", "green"))


def calculate_throughput(timed_job_list):
    date_format = "%Y-%m-%d %H:%M:%S"

    start = list(timed_job_list.values())[0]["job_create"]
    end = list(timed_job_list.values())[-1]["job_finish"]

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


def pull_jmeter_logs(service_name):
    date_format = "%Y-%m-%d %H:%M:%S"

    filepath = "%sRun #%s/%s" % (gp.runs_dir, gp.current_run_index, "jmeter_results.csv")

    if not os.path.exists(filepath):
        return False

    with open(filepath, "r") as file:
        data = file.readlines()

    timed_job_list = {}
    rejected_counter = 0

    for line in data[1:]:
        timestamp, elapsed = line.split(",")[:2]

        thread_name = line.split(",")[5]
        interval = thread_name.split()[2]

        response_code = line.split(",")[3]
        # print(response_code)

        if response_code != "200":
            rejected_counter += 1
            continue

        # if interval != "1":  todo ?
        key = timestamp[-5:]

        while key in timed_job_list.keys():
            key = int(key) + 1
            key = str(key)

        timed_job_list[key] = {
            "name": service_name
        }

        dt = datetime.fromtimestamp(int(timestamp[:-3]))
        start_time = datetime.strftime(dt, date_format)

        timestamp = str(int(timestamp) + int(elapsed))
        dt = datetime.fromtimestamp(int(timestamp[:-3]))
        end_time = datetime.strftime(dt, date_format)

        t1 = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        t2 = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        delta = (t2 - t1).total_seconds()

        # if delta < 0.9 * gp.run_parameters["synchronous"]["request_timeout_seconds"]:
        timed_job_list[key]["job_create"] = start_time
        timed_job_list[key]["job_finish"] = end_time
        timed_job_list[key]["interval"] = interval
        timed_job_list[key]["response_code"] = response_code
        """
        else:
            # urgent, write this to file
            print("Warning: job in interval", interval, "took", delta, "seconds and was discarded")
        """

    if not gp.is_single_service_test:
        gp.input_files_count = len(timed_job_list)
        print("INPUT FILES COUNT: ", gp.input_files_count)
        # gp.real_throughput = calculate_throughput(timed_job_list)

    print("Rejected requests: ", rejected_counter)
    print("Total requests: ", len(timed_job_list))
    save_timelist_to_file_jmeter(timed_job_list, service_name)

    return True


# for a given service, it saves as text file a copy of the logs from OSCAR and kubectl, and also returns a timelist
# todo explain better in comment
def get_timed_jobs_list(service, oscarcli_alias, resource):

    client = gp.SSH_clients_info[resource]
    client = configure_ssh_client(client)

    pod_list = get_kubernetes_pod_list(client)

    # set_default_oscar_cluster_from_alias(oscarcli_alias)

    command = executables.oscar_cli.get_command("service logs list " + service.replace("_", "-"))
    logs_list = get_command_output_wrapped(command)

    if logs_list:
        logs_list.pop(0)

    timed_job_list = {}

    for line in tqdm(logs_list):
        segments = line.split('\t')
        job_name = segments[0]
        job_status = segments[1]

        if job_status != "Succeeded":
            if job_status == "Failed":
                show_error("Job " + job_name + " failed")
            elif job_status == "Pending":
                show_error("Job " + job_name + " is stuck")
            else:
                show_error("Job " + job_name + " is in status " + job_status)
            continue

        job_create = datetime.strptime(segments[2], date_format)
        job_start = datetime.strptime(segments[3], date_format)
        job_finish = datetime.strptime(segments[4].rstrip('\n'), date_format)

        pod_node = ""
        pod_creation = ""

        for pod in pod_list:
            if job_name in pod:
                pod_name = pod.split()[1]
                pod_creation, pod_node = get_kubectl_log(client, pod_name)

        bash_script_start, bash_script_end = get_oscar_log(service, job_name)

        timed_job_list[job_name] = {"service": service,
                                    "resource": resource,
                                    "node": pod_node.strip(".localdomain"),
                                    "job_create": job_create,
                                    "pod_create": pod_creation,
                                    "job_start": job_start,
                                    "bash_script_start": bash_script_start,
                                    "bash_script_end": bash_script_end,
                                    "job_finish": job_finish
                                    }

    client.close()

    return timed_job_list


def get_job_info(line, client, service, resource):
    date_format = "%Y-%m-%d %H:%M:%S"

    segments = line.split('\t')
    job_name = segments[0]
    job_status = segments[1]

    job_create = datetime.strptime(segments[2], date_format)
    job_start = datetime.strptime(segments[3], date_format)
    job_finish = datetime.strptime(segments[4].rstrip('\n'), date_format)

    pod_node = ""
    pod_creation = ""

    pod_list = get_kubernetes_pod_list(client)

    for pod in pod_list:
        if job_name in pod:
            pod_name = pod.split()[1]
            pod_creation, pod_node = get_kubectl_log(client, pod_name)

    bash_script_start, bash_script_end = get_oscar_log(service, job_name)

    return {"service": service,
            "resource": resource,
            "node": pod_node.strip(".localdomain"),
            "job_create": job_create,
            "pod_create": pod_creation,
            "job_start": job_start,
            "bash_script_start": bash_script_start,
            "bash_script_end": bash_script_end,
            "job_finish": job_finish
            }


# retrieve the content of the log of a given job
def get_oscar_log(service_name, job_name):
    # command = oscar_cli + "service logs get " + service_name + " " + job_name
    command = executables.oscar_cli.get_command("service logs get " + service_name.replace("_", "-") + " " + job_name)
    output = get_command_output_wrapped(command)

    # date_format_precise = "%d-%m-%Y %H:%M:%S.%f"
    date_format_precise = "%Y-%m-%d %H:%M:%S,%f"

    time_correction = gp.run_parameters["other"]["time_correction"]

    bash_script_start = ""
    bash_script_end = ""

    with open(gp.current_run_dir + "logs_oscar/" + job_name + ".txt", "w") as file:
        for line in output:
            # nanoseconds after finding the script it is executed
            if "Script file found in '/oscar/config/script.sh'" in line:
                bash_script_start = line.split(" - ")[0]
                bash_script_start = datetime.strptime(bash_script_start, date_format_precise) \
                                    + timedelta(hours=time_correction)
            # this happens immediately after the bash script exits
            if "Searching for files to upload in folder" in line:
                bash_script_end = line.split(" - ")[0]
                bash_script_end = datetime.strptime(bash_script_end, date_format_precise) \
                                  + timedelta(hours=time_correction)
            file.write(line)

    return bash_script_start, bash_script_end


def get_kubernetes_pod_list(client):
    command = "sudo kubectl get pods -A"
    return get_ssh_output(client, command)


# downloads and save to file the log for the specified pod, returns pod creation time and node
# the pod creation time is the only time not gathered from OSCAR, so it's easier to apply the time correction here
def get_kubectl_log(client, pod_name):
    command = "sudo kubectl describe pods " + pod_name + " -n oscar-svc"
    output = get_ssh_output(client, command)
    with open(gp.current_run_dir + "logs_kubectl/" + pod_name + ".txt", "w") as file:
        for line in output:
            file.write(line)

    create_time = ""
    node = ""

    time_correction = gp.run_parameters["other"]["time_correction"]
    # show_debug_info("Time correction: " + str(time_correction))

    for line in output:
        if "Start Time:" in line:
            create_time = line.split(", ", 1)[1].split(" +")[0]
            create_time = datetime.strptime(create_time, "%d %b %Y %H:%M:%S") + timedelta(hours=time_correction)
        if "Node:" in line:
            node = line.split(" ")[-1].split("/")[0]

    return create_time, node


def pull_lambda_logs():
    """
    pulls the log for every lambda function, start time is the first "storage event found", end is last "uploading file"
    :return:
    """

    if not gp.has_active_lambdas:
        return

    print(colored("Collecting Lambda logs...", "yellow"))

    for service in gp.current_services_list:
        if service.is_lambda:

            timed_job_list = {}

            command = "aws logs describe-log-streams --log-group-name /aws/lambda/%s" % service.name
            log_streams = get_command_output_wrapped(command)

            log_stream_names = [line for line in log_streams if "logStreamName" in line]
            log_stream_names = [line.split()[1].replace("\"", "")[:-1] for line in log_stream_names]

            for log_stream_name in log_stream_names:

                command = "aws logs get-log-events --log-group-name /aws/lambda/%s --log-stream-name %s" % (service.name, log_stream_name)

                log = get_command_output_wrapped(command)

                for i in range(len(log)):
                    if "START" in log[i]:
                        request_id = log[i].split()[3]
                        timestamp = log[i - 1].split()[1][:-1]
                        start_time = datetime.fromtimestamp(int(timestamp[:-3]))

                        timed_job_list[request_id] = {
                            "service": service.name,
                            "resource": service.resource,
                            "job_create": start_time,
                            "job_finish": None
                        }

                    if "END" in log[i]:
                        request_id = log[i].split()[3].rstrip("\\n\",")
                        timestamp = log[i - 1].split()[1][:-1]
                        end_time = datetime.fromtimestamp(int(timestamp[:-3]))

                        timed_job_list[request_id]["job_finish"] = end_time

                with open(gp.current_run_dir + "logs_lambda/" + log_stream_name.replace("/", "_") + ".txt", "w") as file:
                    for line in log:
                        file.write(line)

            save_timelist_to_file(timed_job_list, service.name)

    print(colored("Done!", "green"))
    return


def get_scar_log(function, update_marker=False):
    command = "scar log -n " + function
    log = get_command_output_wrapped(command)

    cropped_log = log

    if function in gp.scar_logs_end_indexes.keys():
        index_last_line = gp.scar_logs_end_indexes[function]
        cropped_log = log[index_last_line:]

    if update_marker:
        gp.scar_logs_end_indexes[function] = len(log) - 1

        with open(gp.current_run_dir + "logs_lambda/" + function + ".txt", "w") as file:
            file.writelines(cropped_log)

    return cropped_log


# dumps a timelist to file
def save_timelist_to_file(timed_job_list, service_name):
    with open(gp.current_run_dir + "time_table_" + service_name + ".json", "w") as file:
        json.dump(timed_job_list, file, indent=4, sort_keys=False, default=str)

    with open(gp.current_run_dir + "time_table_" + service_name + ".pkl", "wb") as file:
        pickle.dump(timed_job_list, file, pickle.HIGHEST_PROTOCOL)
    return


def save_timelist_to_file_jmeter(timed_job_list, service_name):
    with open(gp.current_run_dir + "time_table_" + service_name + ".json", "w") as file:
        json.dump(timed_job_list, file, indent=4, sort_keys=False, default=str)

    with open(gp.current_run_dir + "time_table_" + service_name + ".pkl", "wb") as file:
        pickle.dump(timed_job_list, file, pickle.HIGHEST_PROTOCOL)
    return


def get_data_size():
    for service in gp.current_services_list:

        filepath = gp.application_dir + "oscarp/components_data_size.yaml"
        components_data_sizes = read_yaml(filepath)

        name = service.name

        if name in components_data_sizes.keys():
            return

        if "-partition" in service.name:
            a, b = service.name.split("-partition")
            name = a + "_partition" + b
            print(name)
            name = list(name)
            name[-2] = '_'
            name = "".join(name)

        if "minio" in service.storage_provider_output:
            command = executables.mc.get_command("ls %s/%s" % (service.storage_provider_output, service.output_bucket))
            lines = get_command_output_wrapped(command)

            data_size = 0

            for line in lines:
                size = line.split()[3]
                if "MiB" in size:
                    size = float(size.strip("MiB")) * 1000
                elif "GiB" in size:
                    size = float(size.strip("GiB")) * 1000000
                elif "KiB" in size:
                    size = float(size.strip("KiB"))
                elif "B" in size:
                    size = float(size.strip("B")) / 1000

                # print(size, type(size))
                data_size += size

        else:
            command = "aws s3 ls s3://%s/" % service.output_bucket
            lines = get_command_output_wrapped(command)

            data_size = 0

            for line in lines[1:]:
                size = line.split()[2]
                size = float(size) / 1000

            data_size += size

        components_data_sizes[name] = data_size
        write_yaml(filepath, components_data_sizes)

    return
