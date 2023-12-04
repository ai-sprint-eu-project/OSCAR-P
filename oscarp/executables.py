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

global mc, oscar_cli, ssh, ssh_key, script, amllibrary_dummy


class Mc:
    def __init__(self, mc_dir):
        self.mc = mc_dir + "mc --insecure "  # todo add insecure as option
        self.config = mc_dir + "mc_config"

    def get_command(self, command):
        return self.mc + " " + command


class Oscarcli:
    def __init__(self, oscar_cli_dir):
        self.oscar = oscar_cli_dir + "oscar-cli "
        self.config = oscar_cli_dir + "config.yaml"

    def get_command(self, command):
        return self.oscar + command


def init(executables_dir):
    global mc, oscar_cli, ssh, ssh_key, script, amllibrary_dummy

    mc = Mc(executables_dir)
    oscar_cli = Oscarcli(executables_dir)
    ssh = executables_dir + "ssh_private_key.json"
    ssh_key = executables_dir + "id_rsa"
    script = executables_dir + "script.sh"
    # amllibrary_no_sfs = executables_dir + "aMLLibrary-config-noSFS.ini"
    # amllibrary_sfs = executables_dir + "aMLLibrary-config-SFS.ini"
    amllibrary_dummy = executables_dir + "aMLLibrary-config-dummy.ini"
