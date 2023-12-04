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

import os

import yaml
import subprocess

from make_test_file import make_test_file


def load_configuration(configuration_file):
    with open(configuration_file, "r") as file:
        return yaml.safe_load(file)


def execute_command(command):
    p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
    for line in p.stdout.readlines():
        print(line.rstrip())
    return


def encode_input_file(input_file, work_dir):
    command = "base64 %s > %sencoded_input" % (input_file, work_dir)
    execute_command(command)


def pull_image():
    print("Pulling Jmeter image")
    command = "docker pull justb4/jmeter"
    execute_command(command)


def start_test(work_dir):
    print("Running test")

    command = "docker run -i -v /tmp:/tmp -v %s:/home -w /home -p 1099:1099 justb4/jmeter" \
              " --nongui --testfile test.jmx" % work_dir
    execute_command(command)
    return


def main(work_dir, configuration=None, configuration_file="configuration.yaml"):
    if configuration is None:
        configuration = load_configuration(configuration_file)

    make_test_file(configuration, work_dir)

    encode_input_file(configuration["input_file"], work_dir)

    pull_image()
    start_test(work_dir)


if __name__ == '__main__':
    main(work_dir=os.getcwd())
