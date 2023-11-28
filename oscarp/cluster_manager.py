# all methods related to the initial cluster configuration (before run start)
import time

import yaml
import json
import os
import random
import shutil

from tqdm import tqdm

import executables

from termcolor import colored
from datetime import date

from utils import get_ssh_output, get_command_output_wrapped, show_debug_info, show_warning, show_fatal_error, \
    read_json, auto_mkdir, get_command_output, configure_aws_cli

import global_parameters as gp

# todo should all this functions be moved elsewhere?


def remove_all_services():
    """
    Removes all the services from all resources that are not lambdas.

    :return: None
    """

    print(colored("Removing services...", "yellow"))
    for r in gp.current_resources:
        resource = gp.resources[r]
        if not resource.is_lambda():
            set_default_oscar_cluster_from_alias(resource.oscarcli_alias)
            command = executables.oscar_cli.get_command("service ls")
            services = get_command_output_wrapped(command)
            services.pop(0)
            for service in services:
                service = service.split()[0]
                command = executables.oscar_cli.get_command("service remove " + service)
                get_command_output_wrapped(command)
                print("Removed service " + service + " from resource " + r)
    print(colored("Done!", "green"))
    return


def remove_all_buckets():
    """
    Removes all the buckets (aside from the storage bucket) for all resources that are not lambdas.

    :return: None
    """

    print(colored("Removing buckets...", "yellow"))
    for r in gp.current_resources:
        resource = gp.resources[r]
        if not resource.is_lambda():
            minio_alias = resource.storage_provider_alias
            command = executables.mc.get_command("ls " + minio_alias)
            buckets = get_command_output_wrapped(command)
            for bucket in buckets:
                bucket = bucket.split()[-1]
                if bucket != "storage/":  # todo read name of storage bucket from config file
                    bucket = minio_alias + "/" + bucket
                    command = executables.mc.get_command("rb " + bucket + " --force")
                    get_command_output_wrapped(command)
                    print("Removed bucket " + bucket + " from resource " + r)
    print(colored("Done!", "green"))
    return


def clean_s3_buckets():
    """
    Cleans the S3 buckets used by the lambda functions, if any are present.
    Updated 17/07/2023 after moving from SCAR to IM deployment.

    :return: None
    """

    if not gp.has_active_lambdas:
        return
    
    auth_file = gp.application_dir + "aisprint/deployments/base/im/auth.dat"

    if os.path.exists(auth_file):
        with open(auth_file, "r") as file:
            lines = file.readlines()
            for line in lines:
                if "id = lambda" in line:
                    for segment in line.split("; "):
                        if "username" in segment:
                            access_key_id = segment.strip("username = ")
                        elif "password" in segment:
                            secret_access_key = segment.strip("password = ")

    aws_region = "us-east-1"

    configure_aws_cli(access_key_id, secret_access_key, aws_region)

    print(colored("Cleaning S3 buckets...", "yellow"))

    for resource in gp.current_resources:
        if gp.resources[resource].is_lambda():
            b = gp.resources[resource].bucket_name
            command = "aws s3 ls s3://%s/" % b
            folders = get_command_output_wrapped(command)
            for f in folders:
                f = f.split()[1]
                command = "aws s3 ls s3://%s/%soutput/" % (b, f)
                files = get_command_output_wrapped(command)
                for file in files[1:]:
                    command = "aws s3 rm s3://%s/%soutput/%s" % (b, f, file.split()[-1])
                    get_command_output_wrapped(command)
            print("Cleaned bucket " + b)

    print(colored("Done!", "green"))
    return


def clean_aws_logs():
    if not gp.has_active_lambdas:
        return

    print(colored("Cleaning old lambda logs...", "yellow"))
    for service in gp.current_services_list:
        if service.is_lambda:
            command = "aws logs describe-log-streams --log-group-name /aws/lambda/%s" % service.name
            log_streams, errors = get_command_output(command)  # if the log group doesn't exist it will throw an error

            if errors:
                return

            log_stream_names = [line for line in log_streams if "logStreamName" in line]
            log_stream_names = [line.split()[1].replace("\"", "")[:-1] for line in log_stream_names]

            for log_stream_name in log_stream_names:
                command = "aws logs delete-log-stream --log-group-name /aws/lambda/%s --log-stream-name %s" \
                          % (service.name, log_stream_name)
                get_command_output_wrapped(command)
    print(colored("Done!", "green"))
    return


def generate_fdl_configuration():
    """
    Generates the FDL configuration file containing all the OSCAR services needed for the current test Lambda \
     functions (old SCAR) are no longer included as they are deployed together with the infrastructures by IM.

    :return: None
    """

    with open("FDL_configuration.yaml", "w") as file:

        fdl_services = []

        is_first_service = ([ii for ii in gp.components_names.keys()][0] == gp.current_services_list[0].name)

        for current_service in gp.current_services_list:

            unit = current_service.unit

            # if alternate, read parallelism from main component
            if "A" in unit.split("@")[0]:
                a, b = unit.split("@")
                a = a.split("A")[0]
                unit = a + "@" + b

            current_parallelism = gp.scheduled_runs[gp.current_run_id]["services"][unit]["parallelism"]
            script_path = generate_service_script(current_service.name)
            # script_path = "/opt/script.sh"

            fdl_service = {
                "name": current_service.name,
                "input": [{"path": "", "storage_provider": ""}],
                "output": [{"path": "", "storage_provider": ""}]
            }

            if is_first_service and gp.run_parameters["run"]["test_synchronously"]:
                fdl_service["synchronous"] = {}
                pods = gp.run_parameters["synchronous"]["number_of_pre_allocated_pods"]
                fdl_service["synchronous"]["min_scale"] = pods
            else:
                fdl_service["synchronous"] = {}
                fdl_service["synchronous"]["min_scale"] = 0

            if not current_service.is_lambda:
                if "minio" in current_service.storage_provider_input:
                    if gp.resources[current_service.resource].is_physical():
                        fdl_service["input"][0]["storage_provider"] = "minio.default"
                    else:
                        fdl_service["input"][0]["storage_provider"] = "minio." + current_service.storage_provider_input
                else:
                    fdl_service["input"][0]["storage_provider"] = current_service.storage_provider_input
                fdl_service["input"][0]["path"] = current_service.input_bucket
                if "minio" in current_service.storage_provider_output:
                    fdl_service["output"][0]["storage_provider"] = "minio." + current_service.storage_provider_output
                else:
                    fdl_service["output"][0]["storage_provider"] = current_service.storage_provider_output
                fdl_service["output"][0]["path"] = current_service.output_bucket
                fdl_service["cpu"] = float(current_service.cpu)
                fdl_service["memory"] = "%sMi" % current_service.memory
                fdl_service["total_cpu"] = current_service.cpu * current_parallelism
                fdl_service["total_memory"] = "%sMi" % (current_service.memory * current_parallelism)
                fdl_service["image"] = current_service.image
                fdl_service["script"] = script_path
                oscarcli_alias = current_service.oscarcli_alias
                fdl_service = {oscarcli_alias: fdl_service}
                fdl_services.append(fdl_service)

            is_first_service = False

        fdl_config = {"functions": {},
                      "storage_providers": generate_fdl_storage_providers()}

        fdl_config["functions"]["oscar"] = fdl_services

        yaml.dump(fdl_config, file)
        return


def generate_fdl_storage_providers():
    """
    Services deployed on different resources need to know the location of input bucket of the next service; \
     this is done by including the used storage providers in the FDL configuration file.
    This info is extracted by the MinIO configuration file, which is filled after the resources are created.

    :return: a dictionary containing the providers, ready to be added in the FDL file
    """

    region = "us-east-1"  # todo should this be hardcoded like this?

    providers = {
        "minio": {}
    }

    if gp.is_development:
        minio_aliases = read_json(os.path.join("/home/scrapjack/.mc/", "config.json"))["aliases"]
    else:
        minio_aliases = read_json(os.path.join("/root/.mc/", "config.json"))["aliases"]

    for alias in minio_aliases:
        if "minio" in alias:
            providers["minio"][alias] = {
                "access_key": minio_aliases[alias]["accessKey"],
                "endpoint": minio_aliases[alias]["url"],
                "secret_key": minio_aliases[alias]["secretKey"],
                "region": region
            }

    auth_file = gp.application_dir + "aisprint/deployments/base/im/auth.dat"

    if os.path.exists(gp.application_dir + "im/auth.dat") and not os.path.exists(auth_file):
        shutil.copyfile(gp.application_dir + "im/auth.dat", auth_file)

    if gp.has_lambdas:

        if os.path.exists(auth_file):
            with open(auth_file, "r") as file:
                lines = file.readlines()
                for line in lines:
                    if "id = lambda" in line:
                        for segment in line.split("; "):
                            if "username" in segment:
                                access_key = segment.strip("username = ")
                            elif "password" in segment:
                                secret_key = segment.strip("password = ")

            providers["s3"] = {}
            providers["s3"]["aws"] = {
                "access_key": access_key,
                "region": region,
                "secret_key": secret_key
            }

    return providers


def generate_service_script(component_name):
    """
    The bash script of the services is included inside their docker image (01/03/2023). The bash script supplied to \
     OSCAR just needs to call said "real" script.
    These simple scripts are generated locally in an hidden folder called ".scripts", and their path is added to the \
     FDL file.

    :return: path to the service script
    """

    scripts_folder = gp.current_deployment_dir + ".scripts/"
    auto_mkdir(scripts_folder)
    service_script_path = scripts_folder + component_name + "_script.sh"

    if "-partition" in component_name:
        component_name = component_name.split("-partition")[0]

    with open(service_script_path, "w") as file:
        lines = ["#!/bin/bash\n", "sh /opt/%s/script.sh\n" % component_name]
        file.writelines(lines)

    return service_script_path


def apply_fdl_configuration_wrapped():
    """
    Applies the FDL configuration file, then verifies that all the required services have actually been deployed.

    :return: None
    """

    print(colored("Adjusting OSCAR configuration...", "yellow"))
    _apply_fdl_configuration_oscar()
    verify_correct_oscar_deployment()
    print(colored("Done!", "green"))
    return


def _apply_fdl_configuration_oscar():
    """
    Applies the FDL configuration file through the OSCAR cli binary

    :return: None
    """

    #os.system("cat FDL_configuration.yaml")
    
    command = executables.oscar_cli.get_command("apply " + "FDL_configuration.yaml")
    get_command_output_wrapped(command)
    return


def verify_correct_oscar_deployment():
    """
    Starting from the list of active services, it makes sure that all of them are deployed.

    :return: None
    """

    print(colored("Checking correct OSCAR deployment...", "yellow"))

    for s in gp.current_services_list:
        if not s.is_lambda:
            deployed_services = get_deployed_services(s.oscarcli_alias)

            if s.name not in deployed_services:
                show_fatal_error("Service " + s.name + " not deployed")
            else:
                print("Service " + s.name + " deployed on resource " + s.resource)
    return


def get_deployed_services(oscarcli_alias):
    """
    Gets the OSCAR services deployed on a certain resource.

    :return: list of deployed services
    """

    set_default_oscar_cluster_from_alias(oscarcli_alias)
    command = executables.oscar_cli.get_command("service list")
    output = get_command_output_wrapped(command)

    deployed_services = []

    output.pop(0)

    for o in output:
        deployed_services.append(o.split('\t')[0])

    return deployed_services


def set_default_oscar_cluster_from_alias(oscarcli_alias):
    """
    Sets a cluster as default for the OSCAR CLI binary; in this way the commands don't need to specify on which \
     cluster they need to be executed.

    :return: None
    """

    command = executables.oscar_cli.get_command("cluster default -s " + oscarcli_alias)
    get_command_output_wrapped(command)
    return


def upload_input_files_to_storage():
    """
    Uploads the input files to the MinIO storage bucket on the resource of the first service.

    :return: None
    """

    service = gp.current_services_list[0]
    filename = gp.run_parameters["input_files"]["filename"]
    storage_bucket = gp.run_parameters["input_files"]["storage_bucket"]
    # storage_bucket = "minio-%s/%s" % (service.resource, storage_bucket)

    # check if the storage bucket exists
    storage_bucket_found = False
    command = executables.mc.get_command("ls minio-%s/" % service.resource)
    lines = get_command_output_wrapped(command)
    for line in lines:
        if storage_bucket in line:
            storage_bucket_found = True
            break

    # if it exists, check if the file is already there
    if not storage_bucket_found:
        command = executables.mc.get_command("mb minio-%s/%s" % (service.resource, storage_bucket))
        get_command_output_wrapped(command)

    if filename is None or filename == "":  # in this case the whole folder is uploaded
        files_to_upload = os.listdir(gp.oscarp_dir + "input_files/")
    else:
        files_to_upload = [filename]

    for filename in files_to_upload:
        input_file_path = gp.oscarp_dir + "input_files/" + filename
        command = executables.mc.get_command("cp %s minio-%s/%s" % (input_file_path, service.resource, storage_bucket))
        print(colored("Uploading input file %s to %s storage bucket" % (filename, service.resource), "yellow"))
        get_command_output_wrapped(command)
    print(colored("Done!", "green"))
    return
