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

from termcolor import colored

from oscarp.utils import auto_mkdir, ensure_slash_end, get_command_output_wrapped

global application_dir, oscarp_dir, campaign_dir, current_deployment_dir, current_work_dir, runs_dir, results_dir, run_name

"""
* application_dir: directory of the whole project
* oscarp_dir: directory reserved for oscarp (eg. Project/oscarp/)
* campaign_dir: directory containing the directories of the deployments (eg. oscarp/Test/)
* current_deployment_dir: directory of the current deployment (eg. deployment_0/)
* current_work_dir: directory containing runs/ and results/ (eg. full_workflow/, C1@VM1/)
* has_lambdas: True if in general the deployment includes a Lambda
* has_active_lambdas: True if a Lambda is being tested, either in the full workflow or alone
"""

global current_run_dir  # points to /runs/Run #1
global overwrite_runs  # set to True once done skipping completed runs

global resources, components_groups, components_names, containers, run_parameters

"""
* resources: dictionary with all the resources as parsed from candidate_resources.yaml
* components_groups: dictionary with all the components groups i.e. component1, component2, alternatives...
* components_names: dictionary with all the components by their names i.e. blurry_faces, mask_detector...
* containers: dictionary with all the containers by their unit i.e. C1@VM1, C1P1.1@VM1...
* run_parameters: dictionary version of the run_parameters.yaml file
"""

global deployments
global scheduled_runs
global current_deployment, virtual_infrastructures
global current_deployment_index, current_run_index, current_run_id
global current_services_list, current_services_dict
global SSH_clients_info  # dicts of SSH clients info (user, ip, port, key_path), by resource id (eg. VM1, jmeter...)
global resources_deployed  # boolean, False if resources have not yet been deployed

"""
* current_services_list: a list of the services currently being tested, it's updated for every deployment or during 
    single service testing, it contains all the information necessary to deploy on OSCAR i.e. buckets, endpoints... 
* current_services_dict: same as above but the services are in a dictionary with the unit as key
"""

global current_resources, resources_node_requirements

"""
* current_resources: resources in use for the current deployment, and the nodes required for the current run
* current_node_requirements: nodes required for resources in use for all runs
"""

global scar_logs_end_indexes, real_throughput, input_files_count, is_first
global is_single_service_test, has_lambdas, has_active_lambdas, is_last_run, is_first_launch, is_sync
global is_debug, is_dry, is_development

global base_length


def set_application_dir(directory):
    global application_dir, oscarp_dir
    application_dir = ensure_slash_end(directory)
    oscarp_dir = application_dir + "oscarp/"
    return


def make_campaign_dir():
    global campaign_dir, overwrite_runs
    campaign_dir = application_dir + "oscarp/" + run_parameters["run"]["campaign_dir"]
    campaign_dir = ensure_slash_end(campaign_dir)

    auto_mkdir(campaign_dir)
    get_command_output_wrapped("cp %s/oscarp/run_parameters.yaml %srun_parameters.yaml" %
                               (application_dir, campaign_dir))
    overwrite_runs = False
    return


def set_current_deployment(deployment_index):
    global current_deployment, current_deployment_dir, current_deployment_index
    current_deployment = deployments[deployment_index]
    current_deployment_index = deployment_index
    current_deployment_dir = campaign_dir + "deployment_" + str(deployment_index)
    current_deployment_dir = ensure_slash_end(current_deployment_dir)
    auto_mkdir(current_deployment_dir)


def set_current_work_dir(name):
    global current_deployment_dir, current_work_dir, runs_dir, results_dir, run_name
    run_name = name
    current_work_dir = ensure_slash_end(current_deployment_dir + run_name)
    auto_mkdir(current_work_dir)
    runs_dir = current_work_dir + "runs/"
    results_dir = current_work_dir + "results/"
