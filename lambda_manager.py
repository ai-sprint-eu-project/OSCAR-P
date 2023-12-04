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

import time
import yaml

from termcolor import colored


import oscarp.oscarp as oscarp
from oscarp.cluster_manager import generate_service_script
from oscarp.utils import get_command_output_wrapped, show_fatal_error

import global_parameters as gp


def setup_scar():
    if gp.is_dry:
        return

    if gp.has_lambdas:
        remove_all_lambdas()
        remove_s3_buckets()
        print(colored("Adjusting SCAR configuration (this may take up to 15 minutes)...", "yellow"))
        generate_scar_fdl_configuration()
        _apply_fdl_configuration_scar()
        verify_correct_scar_deployment()
        gp.scar_logs_end_indexes = {}
        print(colored("Done!", "green"))

    return


def remove_all_lambdas():
    print(colored("Removing lambda functions...", "yellow"))
    command = "scar rm -a"
    output = get_command_output_wrapped(command)
    # for line in output:
    #     print(line)
    print(colored("Done!", "green"))
    return


def remove_s3_buckets():
    # only SCAR/Lambda functions use s3
    print(colored("Removing S3 buckets...", "yellow"))
    command = "aws s3 ls"
    buckets = get_command_output_wrapped(command)
    for b in buckets:
        b = b.split()[2]
        if "scar-bucket" in b:
            command = "aws s3 rb s3://" + b + " --force"
            get_command_output_wrapped(command)
            print("Removed bucket " + b)
    print(colored("Done!", "green"))
    return


def generate_scar_fdl_configuration():

    with open(gp.current_deployment_dir + "SCAR_FDL_configuration.yaml", "w") as file:

        fdl_lambdas = []

        for service in gp.current_services_list:

            if service["is_lambda"]:

                script_path = oscarp.executables.script  # todo replace with script inside images

                fdl_lambda = {"lambda": {
                    "name": service["name"],
                    "input": [{"path": service["input_bucket"], "storage_provider": "s3"}],
                    "output": [{"path": service["output_bucket"], "storage_provider": "s3"}],
                    "memory": int(service["memory"]),
                    "container": {"image": service["image"]},
                    "runtime": "image",
                    "log_level": "DEBUG",
                    "region": "us-east-1",
                    "init_script": generate_script_lambda(script_path, service["name"])
                    # "init_script": generate_service_script(service["name"]),
                }}

                if "amazonaws" in service["image"]:
                    fdl_lambda["lambda"]["container"]["create_image"] = False
                    fdl_lambda["lambda"]["ecr"] = {"delete_image": False}

                fdl_lambdas.append(fdl_lambda)

        fdl_config = {"functions": {},}
        fdl_config["functions"]["aws"] = fdl_lambdas

        yaml.dump(fdl_config, file)
        return


def _apply_fdl_configuration_scar():
    command = "scar init -f " + gp.current_deployment_dir + "SCAR_FDL_configuration.yaml"
    output = get_command_output_wrapped(command)

    for line in output:
        # print(line)
        if "Error getting docker client. Check if current user has the correct permissions (docker group)." in line:
            show_fatal_error(line[:-1])

    return


def verify_correct_scar_deployment():
    """
    after applying the FDL file, makes sure that all the required services are deployed
    """

    print(colored("Checking correct SCAR deployment...", "yellow"))

    deployed_functions = get_command_output_wrapped("scar ls")[3:]
    for s in gp.current_services_list:
        if s["is_lambda"]:
            match_found = False

            for d in deployed_functions:
                function_name = d.split()[0]
                if s["name"] == function_name:
                    match_found = True
                    print("Function " + s["name"] + " deployed on " + s["cluster"])
                    break

            if not match_found:
                show_fatal_error("Function " + s["name"] + " not deployed")

    return


# todo temporary
def generate_script_lambda(script_path, name):
    if "-partition" in name:
        name = name.split("-partition")[0]

    name = name.replace('-', '_')

    with open(script_path) as file:
        lines = file.readlines()
        lines.insert(17, "cd /opt/" + name + "\n")
        # for i in range(len(lines)): print(i, lines[i])

    new_script_name = "script-lambda-" + name + ".sh"
    new_script_path = gp.current_deployment_dir + new_script_name
    with open(new_script_path, "w") as file:
        file.writelines(lines)

    return new_script_name
