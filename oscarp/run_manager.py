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

# all methods related to starting and finishing the runs go in here
import os
import time
import shutil
import numpy as np

import executables

from termcolor import colored
from tqdm import tqdm

from cluster_manager import set_default_oscar_cluster_from_alias
from oscarp.retrieve_logs import get_job_info, save_timelist_to_file
from utils import get_command_output_wrapped, auto_mkdir, get_ssh_output, configure_ssh_client, configure_aws_cli

from jmeterLoadInjector.make_test_file import make_test_file

import global_parameters as gp


# wait between the upload of two files, to emulate arrival rate
# not a boolean to allow adding new distributions
def wait_interval(distribution, inter_upload_time):
    wait = 0
    if distribution == "exponential":
        wait = round(float(max(inter_upload_time, np.random.exponential(inter_upload_time, 1))), 2)
    elif distribution == "deterministic":
        wait = inter_upload_time
    return wait


# move files to the input bucket, starting the workflow execution
def move_input_files_to_input_bucket():
    print(colored("Moving input files...", "yellow"))
    # storage_bucket = gp.run_parameters["input_files"]["storage_bucket"]

    service = gp.current_services_list[0]

    if not gp.is_single_service_test:
        if gp.is_sync:  # full_workflow, synchronous
            use_jmeter(service)
            return
        else:  # full_workflow, asynchronous
            move_from_storage(service)
            # get_input_files_count(service)

    else:
        if gp.is_sync:
            if service.time_distribution is None:  # single service test, synchronous, first service
                use_jmeter(service)
            else:  # single service test, synchronous, not first service
                duplicate_bucket_sync(service, service.time_distribution,
                                      source_bucket=service.input_bucket_full_workflow,
                                      destination_bucket=service.input_bucket_single_testing)
        else:  # single service test, asynchronous
            duplicate_bucket(service, source_bucket=service.input_bucket_full_workflow,
                             destination_bucket=service.input_bucket_single_testing)

    return


"""
def get_input_files_count(service):
    minio_alias = service.storage_provider_input
    source = minio_alias + "/" + service.input_bucket
    set_default_oscar_cluster_from_alias(service.oscarcli_alias)
    command = executables.mc.get_command("ls " + source + "/")
    file_list = get_command_output_wrapped(command)
    gp.input_files_count = len(file_list)
    print(gp.input_files_count, "input files found")
    return
"""


def move_from_storage(service):
    filename = gp.run_parameters["input_files"]["filename"]
    batch_size = gp.run_parameters["asynchronous"]["batch_size"]
    number_of_batches = gp.run_parameters["asynchronous"]["number_of_batches"]
    distribution = gp.run_parameters["asynchronous"]["distribution"]
    inter_upload_time = gp.run_parameters["asynchronous"]["inter_upload_time"]
    input_bucket = service.storage_provider_input + "/" + service.input_bucket
    storage_bucket = gp.run_parameters["input_files"]["storage_bucket"]
    storage_bucket = service.storage_provider_input + "/" + storage_bucket

    if filename is None or filename == "":  # in this case we move all the files in the storage bucket
        file_list = os.listdir(gp.oscarp_dir + "input_files/")
        counter = 0
        for filename in file_list:
            move_file_between_buckets(origin_file=filename, origin_bucket=storage_bucket,
                                      destination_file=filename, destination_bucket=input_bucket)
            counter += 1
            if counter == batch_size:
                counter = 0
                wait = wait_interval(distribution, inter_upload_time)
                time.sleep(wait)

    else:  # in this other case, we move only one file multiple time, renaming it to avoid overwriting
        for i in range(0, number_of_batches):
            for j in range(0, batch_size):
                stripped_filename, extension = filename.split(".")
                destination_file = stripped_filename + "_" + str(i * batch_size + j) + "." + extension
                move_file_between_buckets(origin_file=filename, origin_bucket=storage_bucket,
                                          destination_file=destination_file, destination_bucket=input_bucket)

            wait = wait_interval(distribution, inter_upload_time)
            time.sleep(wait)

    print(colored("Done!", "green"))
    return


def use_jmeter(service):
    service_name = service.name

    # get cluster endpoint
    command = executables.oscar_cli.get_command("cluster list")
    data = get_command_output_wrapped(command)
    for line in data:
        if service.resource in line:
            endpoint = line.split()[1][1:-1]

    # get auth token for the first service
    command = executables.oscar_cli.get_command("cluster default -s oscar-%s" % service.resource)
    get_command_output_wrapped(command)

    command = executables.oscar_cli.get_command("service get %s" % service.name)
    data = get_command_output_wrapped(command)
    for line in data:
        if "token" in line:
            token = line.split()[-1]

    client = gp.SSH_clients_info["jmeter"]
    client = configure_ssh_client(client)

    # generate test file
    os.chdir("jmeterLoadInjector")

    jmeter_dir = "/tmp/jmeter_files/"
    auto_mkdir(jmeter_dir)

    configuration = {
        'worker_nodes': gp.run_parameters["synchronous"]["worker_nodes"],
        'cluster_endpoint': endpoint,
        'oscar_service': service_name,
        'token': token,
        'connect_timeout_seconds': gp.run_parameters["synchronous"]["connect_timeout_seconds"],
        'request_timeout_seconds': gp.run_parameters["synchronous"]["request_timeout_seconds"],
        'tests': gp.run_parameters["synchronous"]["intervals"],
        'distribution': gp.run_parameters["synchronous"]["distribution"]
    }

    make_test_file(configuration, jmeter_dir)

    # delete old test file, if any
    get_ssh_output(client, "rm test.jmx")

    # push test file to jmeter cluster
    with open(jmeter_dir + "test.jmx", "rb") as local_file:
        with client.open_sftp().file("test.jmx", "wb") as remote_file:
            remote_file.write(local_file.read())

    # delete old result file, if any
    get_ssh_output(client, "rm results.csv")

    # delete old input file, if any
    get_ssh_output(client, "rm encoded_input")
    get_ssh_output(client, "sudo rm /home/jmeter/encoded_input")

    # upload input file to jmeter cluster
    input_file_name = gp.run_parameters["input_files"]["filename"]
    input_file_path = "%sinput_files/%s" % (gp.oscarp_dir, input_file_name)

    with open("../" + input_file_path, "rb") as local_file:
        with client.open_sftp().file(input_file_name, "wb") as remote_file:
            remote_file.write(local_file.read())

    # encode input file
    get_ssh_output(client, "base64 %s > encoded_input" % input_file_name)
    get_ssh_output(client, "sudo cp encoded_input /home/jmeter/encoded_input")

    # launch jmeter on worker nodes
    for i in range(0, gp.run_parameters["synchronous"]["worker_nodes"]):
        j = i + 1
        print("Launching jmeter on worker node %s" % j)
        inner_command = "nohup /opt/apache-jmeter-5.4.1/bin/jmeter.sh -s -Jserver.rmi.ssl.disable=true &> /dev/null &"
        command = "sudo su jmeter -c \'ssh vnode-%s \"%s\"\'" % (j, inner_command)
        get_ssh_output(client, command)

    remote_hosts = ""
    for i in range(0, gp.run_parameters["synchronous"]["worker_nodes"]):
        remote_hosts += "vnode-%s," % (i + 1)

    # run test
    print(colored("Launching Jmeter test...", "yellow"))
    command = (("/opt/apache-jmeter-5.4.1/bin/jmeter.sh -n -Jserver.rmi.ssl.disable=true -t test.jmx -R "
                + remote_hosts[:-1]))
    for line in get_ssh_output(client, command):
        print(line.strip("/n"))

    # get results
    with client.open_sftp().file("results.csv", "rb") as remote_file:
        with open(jmeter_dir + "results.csv", "wb") as local_file:
            local_file.write(remote_file.read())

    # get log
    with client.open_sftp().file("jmeter.log", "rb") as remote_file:
        with open(jmeter_dir + "jmeter.log", "wb") as local_file:
            local_file.write(remote_file.read())

    client.close()
    os.chdir("..")

    # copy result and log under Run #i
    destination = "%sRun #%s/jmeter_results.csv" % (gp.runs_dir, gp.current_run_index)
    shutil.copyfile(jmeter_dir + "results.csv", destination)

    destination = "%sRun #%s/jmeter.log" % (gp.runs_dir, gp.current_run_index)
    shutil.copyfile(jmeter_dir + "jmeter.log", destination)

    print(colored("Done!", "green"))
    return


# origin and destination bucket must already include the minio_alias, i.e. "minio-vm/storage"
def move_file_between_buckets(origin_file, origin_bucket, destination_file, destination_bucket):
    origin = origin_bucket + "/" + origin_file
    destination = destination_bucket + "/" + destination_file
    command = executables.mc.get_command("cp " + origin + " " + destination)
    get_command_output_wrapped(command)
    return


def duplicate_bucket(service, source_bucket, destination_bucket):
    print(colored("Duplicating bucket...", "yellow"))

    distribution = service.time_distribution
    inter_upload_time = gp.run_parameters["asynchronous"]["inter_upload_time"]

    minio_alias = service.storage_provider_input
    source = minio_alias + "/" + source_bucket
    destination = minio_alias + "/" + destination_bucket
    set_default_oscar_cluster_from_alias(service.oscarcli_alias)
    command = executables.mc.get_command("ls " + source + "/")
    file_list = get_command_output_wrapped(command)
    batch_size = int(len(file_list) / gp.run_parameters["asynchronous"]["number_of_batches"])

    print("batch_size: %s" % batch_size)

    counter = 0
    for file in file_list:

        filename = file.split()[5]
        command = executables.mc.get_command("cp %s/%s %s/%s" % (source, filename, destination, filename))
        get_command_output_wrapped(command)

        counter += 1

        if counter >= batch_size:
            counter = 0

            wait = wait_interval(distribution, inter_upload_time)
            time.sleep(wait)

    print(colored("Done!", "green"))
    return


def duplicate_bucket_sync(service, distribution, source_bucket, destination_bucket):
    print(colored("Duplicating bucket...", "yellow"))
    minio_alias = service.storage_provider_input
    source = minio_alias + "/" + source_bucket
    destination = minio_alias + "/" + destination_bucket
    set_default_oscar_cluster_from_alias(service.oscarcli_alias)
    command = executables.mc.get_command("ls " + source + "/")
    file_list = get_command_output_wrapped(command)
    batch_size = int(len(file_list) / gp.input_files_count)

    for interval in gp.run_parameters["synchronous"]["intervals"]:
        throughput = interval["throughput"]
        duration = interval["duration_seconds"]

        #print("throughput: %s, duration: %s" % (throughput, duration))

        inter_upload_time = 1 / (throughput / 60)
        batch_number_counter = int(round(duration / inter_upload_time, 0)) * batch_size

        #print("inter_upload_time: %s, batch_number_counter: %s" % (inter_upload_time, batch_number_counter))

        batch_size_counter = 0

        for file in file_list[:batch_number_counter]:
            filename = file.split()[5]
            command = executables.mc.get_command("cp %s/%s %s/%s" % (source, filename, destination, filename))
            # print(command)
            get_command_output_wrapped(command)

            batch_size_counter += 1

            if batch_size_counter >= batch_size:
                batch_size_counter = 0
                wait = wait_interval(distribution, inter_upload_time)
                time.sleep(wait)

        file_list = file_list[batch_number_counter:]

    print(colored("Done!", "green"))
    return


def move_input_files_to_s3_bucket(input_bucket):
    print(colored("Duplicating bucket...", "yellow"))
    base_bucket = input_bucket.split('/')[0]
    temp_bucket = base_bucket + "/temp_bucket/"
    input_bucket += "/"

    command = "aws s3 cp s3://" + input_bucket + " s3://" + temp_bucket
    get_command_output_wrapped(command)

    command = "aws s3 mv s3://" + input_bucket + " s3://" + temp_bucket + " --recursive"
    get_command_output_wrapped(command)

    command = "aws s3 mv s3://" + temp_bucket + " s3://" + input_bucket + " --recursive"
    get_command_output_wrapped(command)

    print(colored("Done!", "green"))


# given a service, returns the list of jobs with their status
def get_jobs_list(service_name, oscarcli_alias):
    # set_default_oscar_cluster_from_alias(oscarcli_alias)

    # command = oscar_cli + "service logs list " + service_name
    command = executables.oscar_cli.get_command("service logs list " + service_name)
    logs_list = get_command_output_wrapped(command)

    if logs_list:
        logs_list.pop(0)

    job_list = []

    for line in logs_list:
        segments = line.split('\t')
        job_name = segments[0]
        job_status = segments[1]

        job_list.append({
            "name": job_name,
            "status": job_status
        })

    return job_list


def increment_sleep(sleep):
    max_wait = 300
    sleep += round(sleep / 2)
    if sleep > max_wait:
        return max_wait
    return sleep


# awaits the completion of all the jobs before passing to processing
def wait_services_completion(services):
    for service in services:
        if service.is_lambda:
            wait_lambda_completion(service)
        else:
            wait_oscar_service_completion(service)

    return


def wait_oscar_service_completion(service):

    if service.time_distribution is None and gp.is_sync:  # first sync service
        return

    # sleep_interval = 10
    completed = False
    # cluster = get_active_cluster(service, clusters)
    print(colored("Waiting for service " + service.name + " completion...", "yellow"))

    # before considering the service completed it'll wait for a bit more
    retries_counter = 3
    sleep_timer_seconds = 10
    stack_counter = 10  # if doesn't change in 10 mins, it is stack

    pbar = tqdm()
    old_pending_jobs = -1
    completed_jobs = -1

    timed_job_list = {}

    auto_mkdir(gp.current_run_dir + "logs_kubectl")
    auto_mkdir(gp.current_run_dir + "logs_oscar")

    client_info = gp.SSH_clients_info[service.resource]
    client = configure_ssh_client(client_info)
    
    set_default_oscar_cluster_from_alias(service.oscarcli_alias)

    while not completed:
        job_list = get_jobs_list(service.name, service.oscarcli_alias)
        # print(service.name, service.oscarcli_alias)
        # print(job_list)

        pbar.total = len(job_list)
        pbar.refresh()

        time.sleep(sleep_timer_seconds)
        sleep_timer_seconds = 60

        pending_jobs = 0
        running_jobs = 0
        old_completed_jobs = completed_jobs

        i = len(job_list)
        if job_list:  # if list not empty
            completed = True
            for j in job_list:
                if j["status"] == "Running":
                    completed = False
                    running_jobs += 1
                    i -= 1
                elif j["status"] == "Pending":
                    pending_jobs += 1
                    i -= 1

        pbar.n = i
        pbar.refresh()

        # completed is true if there are no jobs running, everything is either completed or pending
        if not completed:
            retries_counter = 3
        else:
            # if there are no running jobs and the number of pending is under 5%,
            # and it stays the same (meaning every job is either finished or stuck)
            if pending_jobs == 0:
                if gp.is_debug:
                    print(colored("Service completed", "magenta"))
            elif len(job_list) / 100 * 5 >= pending_jobs == old_pending_jobs:
                retries_counter -= 1
                if retries_counter > 0:
                    completed = False
            else:
                retries_counter = 3
                completed = False

        completed_jobs = i

        if completed_jobs == old_completed_jobs and pending_jobs == old_pending_jobs:
            stack_counter -= 1
            if stack_counter == 0:
                if gp.is_debug:
                    print(colored("Service is stack", "magenta"))
                if completed_jobs < 0.95*len(job_list):
                    if gp.is_debug:
                        print(colored("Less than 95% of jobs completed", "magenta"))
                    raise NameError('StackService')
        else:
            stack_counter = 3

        if gp.is_debug:
            print(colored("\tPending jobs: %s, Running jobs: %s, Completed jobs: %s, Retries counter: %s, Stack counter: %s" % (pending_jobs, running_jobs, completed_jobs, retries_counter, stack_counter), "magenta"))
            #print(colored("\tOld pending jobs: %s, Old completed jobs: %s" % (old_pending_jobs, old_completed_jobs), "magenta"))

        old_pending_jobs = pending_jobs

        # download logs
        command = executables.oscar_cli.get_command("service logs list " + service.name)
        logs_list = get_command_output_wrapped(command)

        if logs_list:
            logs_list.pop(0)

        for line in logs_list:

            segments = line.split('\t')

            if segments[1] == "Succeeded":
                job_name = segments[0]
                if job_name not in timed_job_list.keys():
                    timed_job_list[job_name] = get_job_info(line, client, service.name, service.resource)

    save_timelist_to_file(timed_job_list, service.name)
    pbar.close()

    print(colored("\nService " + service.name + " completed!", "green"))
    return


# todo this isn't done yet, finish it
def wait_lambda_completion(service):
    print(colored("Waiting for service " + service.name + " completion...", "yellow"))

    completed = False

    retries_counter = 3
    sleep_timer_seconds = 10
    #old_log_length = 0
    actual_lastIngestionTime = -1.0

    while not completed:

        time.sleep(sleep_timer_seconds)

        command = "aws logs describe-log-streams --log-group-name /aws/lambda/%s" % service.name
        log_streams = get_command_output_wrapped(command)

        log_lastIngestionTime = [line for line in log_streams if "lastIngestionTime" in line]
        log_lastIngestionTime = [int(line.split(": ")[1].split(",")[0]) for line in log_lastIngestionTime]

        """
        log_stream_names = [line for line in log_streams if "logStreamName" in line]
        log_stream_names = [line.split()[1].replace("\"", "")[:-1] for line in log_stream_names]

        total_length = 0

        for log_stream_name in log_stream_names:
            command = "aws logs get-log-events --log-group-name /aws/lambda/%s --log-stream-name %s" % (service.name, log_stream_name)

            log = get_command_output_wrapped(command)
            total_length += len(log)

        print(colored("\tTotal length: %s" % total_length, "magenta"))

        if total_length == old_log_length and total_length > 0:
            if retries_counter != 0:
                completed = False
                retries_counter -= 1
            else:
                completed = True

        old_log_length = total_length
        """

        lastIngetionTime = max(log_lastIngestionTime)

        if lastIngetionTime > actual_lastIngestionTime:
            retries_counter = 3
            actual_lastIngestionTime = lastIngetionTime
        else: 
            retries_counter -= 1

        if retries_counter == 0:
            completed = True

    print(colored("Service " + service.name + " completed!", "green"))
    return


"""
def download_bucket(destination, bucket_name):
    print(colored("Downloading bucket...", "yellow"))
    mc_alias = get_mc_alias()
    origin = mc_alias + "/" + bucket_name
    auto_mkdir(destination)
    command = "oscar-p/mc cp " + origin + " " + destination + " -r"
    get_command_output_wrapped(command)
    print(colored("Done!", "green"))
"""
