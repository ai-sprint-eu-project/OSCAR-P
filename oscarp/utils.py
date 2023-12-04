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

# collection of utils for CLI, GUI and SSH
import os
import subprocess
import time
import json
import csv
import shutil
import re

import yaml
from paramiko import SSHClient, AutoAddPolicy, RSAKey
from termcolor import colored

import executables


# CLI utils


def get_command_output(command):
    """
    Execute a command as an OS subprocess, returns the output lines and eventual errors.
    """

    output = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines = []
    for line in output.stdout.readlines():
        line = line.decode('utf-8')
        lines.append(line)

    errors = []
    for e in output.stderr.readlines():
        e = e.decode('utf-8')
        errors.append(e)

    return lines, errors


def get_command_output_wrapped(command):
    """
    Execute a command as an OS subprocess, if there are errors they are printed and the command is retried.
    """

    import global_parameters as gp
    if gp.is_debug:
        print(colored("\t>_ " + command, "magenta"))

    for t in [5, 5, 10, 15, 30, 60, 120, 5*60, 10*60]:
        lines, errors = get_command_output(command)
        if errors:  # empty list equals to False
            show_warning("Errors encountered, retrying in " + str(t) + " seconds")
            for e in errors:
                show_external_error(e)
            time.sleep(t)
        else:
            return lines
    show_fatal_error("Errors encountered, cannot proceed. Exiting.")


def show_external_error(message):
    """
    Receives a string, prints it in red.

    :return: None
    """

    print(colored(message, "red"))
    return


def show_warning(message):
    """
    Receives a string, prints it in yellow.

    :return: None
    """

    print(colored("\nWarning: " + message, "yellow"))
    return


def show_error(message):
    """
    Receives a string, prints it in red.

    :return: None
    """

    print(colored("\nError: " + message, "red"))
    return


def show_fatal_error(message):
    """
    Prints an unrecoverable error message in red and exits.

    :param str message: error message
    """

    show_error(message)
    quit()


def show_debug_info(message):
    """
    Receives a string, prints it in cyan.

    :return: None
    """
    print(colored("\nInfo: " + message, "cyan"))


def get_valid_input(message, allowed_values):
    """
    Receives a message and an array of values, keeps asking for an input that is among the allowed values.
    """

    value = input("\n" + message)
    while value not in allowed_values:
        print("Answer not valid")
        value = input("\n" + message)
    return value


# SSH utils
def configure_ssh_client(client_info):

    user = client_info["user"] 
    ip = client_info["ip"]
    key_path = client_info["key_path"]

    if "port" in client_info:
        port = client_info["port"]
    else:
        port = 22

    client = SSHClient()
    client.set_missing_host_key_policy(AutoAddPolicy())
    client.connect(ip, port=port, username=user, key_filename=key_path)
    return client


def get_private_key():
    with open(executables.ssh, "r") as file:
        data = json.load(file)

    private_key = RSAKey.from_private_key_file(executables.ssh_key, data["password"])
    # private_key = RSAKey.from_private_key_file(data["path_to_key"], data["password"])
    return private_key


def get_ssh_output(client, command):
    """Returns output of a command executed via ssh as a list of lines"""

    import global_parameters as gp
    if gp.is_debug:
        print(colored("\t>_ " + command, "magenta"))

    stdin, stdout, stderr = client.exec_command(command)
    lines = stdout.readlines()
    if not lines:  # if empty
        lines = stderr.readlines()
    stdin.close()
    stdout.close()
    stderr.close()
    return lines


# FILE UTILS

def write_list_of_strings_to_file(list_of_strings, filepath):
    """Writes a list of strings to a file"""

    with open(filepath, "w") as file:
        for s in list_of_strings:
            file.write(s + "\n")


def append_string_to_file(string, filepath):
    """Appends a string to a file"""

    with open(filepath, "a") as file:
        file.write(string + "\n")


def create_new_file(filepath):
    """Creates a new file"""

    with open(filepath, "w"):
        pass


def auto_mkdir(new_dir):
    """Automatically creates a directory if it does not exist"""

    if not os.path.exists(new_dir):
        os.mkdir(new_dir)


def delete_directory(dir_path):
    """Deletes a directory"""

    shutil.rmtree(dir_path)


def delete_file(file_path):
    """Deletes a file"""

    os.remove(file_path)


def ensure_slash_end(path):
    """Ensures that a path ends with a slash"""

    if not path.endswith("/"):
        path += "/"
    return path


def read_json(path):
    """Reads a json file, returns an empty dict if it does not exist"""

    if not os.path.exists(path):
        return {}

    with open(path, 'r') as file:
        return json.load(file)


def write_json(path, output):
    """Writes to a json file"""

    with open(path, "w+") as file:
        json.dump(output, file, indent=4)


def read_yaml(path):
    """Reads a yaml file, returns an empty dict if it does not exist"""

    if not os.path.exists(path):
        return {}

    with open(path) as file:
        return yaml.load(file, Loader=yaml.FullLoader)


def write_yaml(path, output):
    """Writes to a yaml file"""

    with open(path, "w+") as file:
        yaml.dump(output, file, sort_keys=False)


# OTHER UTILS

def strip_ansi_from_string(string):
    """Strips ANSI escape sequences from a string"""

    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', string)


def configure_aws_cli(access_key, secret_key, region):
    command = f"aws configure set aws_access_key_id {access_key} && " \
              f"aws configure set aws_secret_access_key {secret_key} && " \
              f"aws configure set region {region}"

    try:
        subprocess.run(command, shell=True, check=True)
        print("AWS CLI configuration completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error configuring AWS CLI: {e}")
