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

import json
import time

import paramiko
import requests
import yaml
from datetime import datetime, timedelta

from classes.Component import generalize_unit_id, generalize_name
from toscarizer.utils import (DEPLOYMENTS_FILE,
                              RESOURCES_FILE,
                              BASE_DAG_FILE,
                              PHYSICAL_NODES_FILE,
                              CONTAINERS_FILE,
                              QOS_CONSTRAINTS_FILE,
                              parse_dag,
                              parse_resources)

from toscarizer.im_tosca import gen_tosca_yamls

from termcolor import colored
from oscarp.utils import get_ssh_output, auto_mkdir, show_fatal_error, get_command_output_wrapped, \
    delete_file, read_json, configure_ssh_client

import global_parameters as gp

import oscarp.oscarp as oscarp


# # # # # # # # # # # #
# Virtual infrastructures
# # # # # # # # # # # #


def deploy_all_needed_resources():

    if gp.is_dry:
        return

    create_virtual_infrastructures()
    ensure_correct_number_of_nodes()
    configure_jmeter_cluster()

    gp.resources_deployed = True

    return


def create_virtual_infrastructures():
    """
    Scenario 1: starting from zero, assumes "virtual_infrastructures.json" not present, or present but the \
     infrastructures no longer exist on IM; in both cases, reset virtual_infrastructures as {}, then delete all on IM \
     with delete_unused_virtual_infrastructures.
    Scenario 2: resuming interrupted, checks that "virtual_infrastructures.json" is present and its infrastructures \
     are still on IM: if yes, delete_unused_virtual_infrastructures anyway, nothing bad should happen, if not, proceed \
     as for scenario 1.
    Scenario 3: changing deployment, "virtual_infrastructures.json" will be loaded but it won't change anything, \
     proceed as usual.
    """

    gp.virtual_infrastructures = read_json(gp.oscarp_dir + "virtual_infrastructures.json")
    # if file doesn't exist, read_json returns an empty dict

    delete_unused_virtual_infrastructures()

    # virtual is the list of the infrastructures that need to be deployed
    # an infrastructure is added as long as: 1_ it's not physical, 2_ it's not already deployed
    to_deploy = {}

    for c in gp.current_deployment:
        c, r = c.split('@')
        if not gp.resources[r].is_physical() and r not in gp.virtual_infrastructures.keys():
            to_deploy[r] = c
    
    # print("to_deploy A: ", to_deploy)

    ensure_correct_number_of_nodes()

    if to_deploy:
        print(colored("Deploying virtual infrastructures...", "yellow"))
    else:
        configure_executables()
        return

    auto_mkdir(gp.application_dir + "oscarp/.toscarizer")
    to_deploy = _generate_modified_candidate_files(to_deploy)
    _generate_modified_dag()
    
    # print("to_deploy B: ", to_deploy)

    tosca_files = generate_tosca()

    # print("tosca_files: ", tosca_files)

    cleaned_tosca_files = clean_and_rename_tosca_files(to_deploy, tosca_files)

    # print("cleaned_tosca_files: ", cleaned_tosca_files)

    for tosca_file in cleaned_tosca_files:
        resource = tosca_file.split('/')[-1].split('.')[0]
        inf_url = deploy_virtual_infrastructure(tosca_file, resource, None)
        gp.virtual_infrastructures[resource] = {
            "inf_url": inf_url,
            "inf_id": inf_url.split('/')[-1],
            "tosca_file_path": tosca_file,
            "oscar_endpoint": "",
            "oscar_password": "",
            "minio_endpoint": "",
            "minio_password": ""
        }

    wait_for_infrastructure_deployment()

    # time.sleep(60 * 10)  # todo temporary, to circumvent issue with IM

    get_infrastructures_outputs()
    configure_executables()  # todo this needs to be moved, since it'll be done for physical too

    print(colored("Done", "green"))
    return


def ensure_correct_number_of_nodes():
    resources_requirements = gp.scheduled_runs[gp.current_run_id]["resources"]
    for resource, value in gp.virtual_infrastructures.items():
        if resource != "jmeter" and not gp.resources[resource].is_lambda():
            required_nodes = resources_requirements[resource]["nodes"]
            actual_nodes = get_number_of_worker_nodes(value["inf_url"])

            if required_nodes != actual_nodes:
                update_virtual_infrastructures(resources_requirements)

    return


def _generate_modified_candidate_files(to_deploy):
    """
    Generate a modified version of candidate_deployments, containing (only) the components that are needed for the \
     current test; this file is needed by the Toscarizer to generate the correct TOSCA files.
    Additionally, it returns the names of the components that need to be deployed.
    """

    with open("%s%s" % (gp.application_dir, DEPLOYMENTS_FILE), 'r') as f:
        components = yaml.safe_load(f)["Components"]

    modified_components = {}
    
    for unit in gp.current_deployment:
        c, r = unit.split('@')
        if "P" in c:
            c = c.replace("P", "_partition")
            a, b = c.split(".")
            c = a[:-1] + "X_" + b

        c = c.replace("C", "component")

        if r in to_deploy.keys():
            to_deploy[r] = components[c]["name"]
        
        for container in components[c]["Containers"].values():
            if r in container["candidateExecutionResources"]:  # found the right container
                components[c]["name"] = gp.current_services_dict[unit].name
                components[c]["Containers"]["container1"] = container
                components[c]["Containers"]["container1"]["candidateExecutionResources"] = [r]
                components[c]["candidateExecutionLayers"] = [gp.resources[r].execution_layer]
                break

        modified_components[c] = components[c]

    with open("%soscarp/.toscarizer/modified_candidate_deployments.yaml" % gp.application_dir, 'w') as file:
        yaml.dump({"Components": modified_components}, file, sort_keys=False)

    return to_deploy


def _generate_modified_dag():
    """
    Similar to the previous function, it creates a customized version of the application_dag containing whatever needs \
     to be tested; the file is used by the Toscarizer.
    """

    with open("%scommon_config/application_dag.yaml" % gp.application_dir, 'r') as file:
        dag = yaml.load(file, Loader=yaml.Loader)

    name = dag["System"]["name"]

    components = []
    for unit in gp.current_deployment:
        component_name = gp.current_services_dict[unit].name
        components.append(component_name)
    
    dependencies = []
    for i in range(len(components)):
        if i + 1 == len(components):
            break

        c1 = components[i]
        c2 = components[i + 1]

        dependencies.append([c1, c2, 1])

    dag = {
        "name": name,
        "components": components,
        "dependencies": dependencies
    }

    with open("%s.toscarizer/modified_application_dag.yaml" % gp.oscarp_dir, 'w') as file:
        yaml.dump({"System": dag}, file, sort_keys=False)

    return


def generate_tosca():
    """
    Given the original of modified files, this function uses the Toscarizer to generate the required Tosca files.
    """

    domain_name = gp.run_parameters["other"]["domain_name"]

    elastic = 0
    auth_data = None

    application_dir = gp.application_dir[:-1]

    app_name, dag = parse_dag("%s.toscarizer/modified_application_dag.yaml" % gp.oscarp_dir)
    deployments_file = "%s.toscarizer/modified_candidate_deployments.yaml" % gp.oscarp_dir
    resources_file = "%s/%s" % (application_dir, RESOURCES_FILE)
    qos_contraints_file = "%s/%s" % (application_dir, QOS_CONSTRAINTS_FILE)

    toscas = gen_tosca_yamls(app_name, dag, resources_file, deployments_file,
                             "%s/%s" % (application_dir, PHYSICAL_NODES_FILE),
                             elastic, auth_data, domain_name, "https://influx.oncloudandheat.com/",
                             "notEmptyString", qos_contraints_file, "%s/%s" % (application_dir, CONTAINERS_FILE))

    tosca_files = []

    for cl, tosca in toscas.items():
        tosca_file = "%s/.toscarizer/%s.yaml" % (gp.application_dir + "oscarp", cl)
        tosca_files.append(tosca_file)
        with open(tosca_file, 'w+') as f:
            yaml.safe_dump(tosca, f, indent=2)
        # print(colored("TOSCA file has been generated for component %s." % cl, "green"))

    return tosca_files


def clean_and_rename_tosca(tosca_file, component_name, resource, node_requirements):
    """
    This function "cleans" the Tosca file by removing the section related to OSCAR and its services, since those will \
     be deployed by OSCAR-P instead.
    It also selects the correct number of nodes, sets the domain name, and renames the file as its associated resource \
     (e.g. VM1.yaml).
    """

    with open(tosca_file, 'r') as file:
        content = yaml.safe_load(file)

    if not gp.resources[resource].is_lambda():
        # todo disabling yunikorn since it gives issues with sync testing
        # content["topology_template"]["node_templates"]["oscar"]["properties"]["yunikorn_enable"] = True
        # content["topology_template"]["node_templates"]["lrms_front_end"]["properties"]["install_yunikorn"] = True

        del (content["topology_template"]["node_templates"]["oscar_service_" + component_name])
        del (content["topology_template"]["outputs"]["oscar_service_url"])
        del (content["topology_template"]["outputs"]["oscar_service_cred"])

        key = "wn_resource1"
        for key in content["topology_template"]["node_templates"].keys():
            if "wn_resource" in key:
                break

        content["topology_template"]["node_templates"][key]["capabilities"]["scalable"]["properties"]["count"] = \
            node_requirements[resource]["nodes"]

    filename = gp.application_dir + "oscarp/.toscarizer/" + resource + ".yaml"

    with open(filename, 'w') as file:
        yaml.dump(content, file, sort_keys=False)

    return filename


def clean_and_rename_tosca_files(to_deploy, tosca_files):
    """
    Calls clean_and_rename_tosca() for each tosca_files.
    """

    cleaned_tosca_files = []

    for tosca_file in tosca_files:
        for r, c in to_deploy.items():
            if c in tosca_file:
                filename = clean_and_rename_tosca(tosca_file, c, r, gp.scheduled_runs[gp.current_run_id]["resources"])
                cleaned_tosca_files.append(filename)

    for tosca_file in tosca_files:
        if tosca_file not in cleaned_tosca_files:
            delete_file(tosca_file)

    return cleaned_tosca_files


def deploy_virtual_infrastructure(tosca_file, resource, inf_id):
    """This function calls the IM API to deploy (or update) all the virtual infrastructure."""

    im_url = "https://im.egi.eu/im/"
    #im_url = "https://appsgrycap.i3m.upv.es/im-dev/"

    tosca_dir = "%sim" % gp.application_dir
    im_auth = "%s/auth.dat" % tosca_dir

    with open(im_auth, 'r') as f:
        auth_data = f.read().replace("\n", "\\n")

    headers = {"Authorization": auth_data, 'Content-Type': 'text/yaml'}

    with open(tosca_file, 'rb') as f:
        data = f.read()
        # print(data)
    try:
        if inf_id is None:
            resp = requests.request("POST", "%s/infrastructures?async=1" % im_url, headers=headers, data=data)
            print(colored("Resource %s is being deployed..." % resource, "yellow"))
        else:
            resp = requests.request("POST", "%s/infrastructures/%s" % (im_url, inf_id), headers=headers, data=data)
            print(colored("Resource %s is being updated..." % resource, "yellow"))
        return resp.text
    except Exception as ex:
        print("Exception:")
        print(str(ex))
        return


def wait_for_infrastructure_deployment(is_update=False):
    """
    This function waits for the deployment of the virtual infrastructure, checking on their status periodically.
    If an error is detected, the execution stops.
    """

    if not is_update:
        print(colored("Waiting for infrastructure deployment (this may take up to 15 minutes)...", "yellow"))
    else:
        print(colored("Waiting for infrastructure update (this should take only a minute)...", "yellow"))

    completed = False
    while not completed:
        completed = True
        for resource in gp.virtual_infrastructures.keys():
            if resource != "jmeter" and not gp.resources[resource].is_lambda():
                inf_url = gp.virtual_infrastructures[resource]["inf_url"]
                state = get_state(inf_url)
                if state != "configured":
                    completed = False
                if state == "failed" or state == "unconfigured":
                    show_fatal_error("The deployment of infrastructure %s failed." % resource)

        if is_update:
            time.sleep(10)
        else:
            time.sleep(60)

    with open(gp.application_dir + "/oscarp/virtual_infrastructures.json", "w") as file:
        json.dump(gp.virtual_infrastructures, file, indent=4)

    return


def get_state(inf_url):
    """This function returns the state of the deployment of a virtual infrastructure."""

    tosca_dir = "%sim" % gp.application_dir
    im_auth = "%s/auth.dat" % tosca_dir

    with open(im_auth, 'r') as f:
        auth_data = f.read().replace("\n", "\\n")

    headers = {"Authorization": auth_data, "Content-Type": "application/json"}
    try:
        resp = requests.get("%s/state" % inf_url, verify=True, headers=headers)
        success = resp.status_code == 200
        if success:
            return resp.json()["state"]["state"]
        else:
            return resp.text
    except Exception as ex:
        print(str(ex))
        return str(ex)


def configure_executables():
    """This function configures the executables (MC and oscar_cli) used by OSCAR-P according to the credentials \
     retrieved from IM."""

    gp.SSH_clients_info = {}

    for resource in gp.virtual_infrastructures.keys():

        if not resource == "jmeter" and not gp.resources[resource].is_lambda():
            # set for oscar_cli
            oscar_endpoint = gp.virtual_infrastructures[resource]["oscar_endpoint"]
            oscar_password = gp.virtual_infrastructures[resource]["oscar_password"]
            command = "cluster add oscar-%s %s oscar %s  --disable-ssl" % (resource, oscar_endpoint, oscar_password)
            command = oscarp.executables.oscar_cli.get_command(command)
            # print(command)
            get_command_output_wrapped(command)

            # set for mc
            minio_endpoint = gp.virtual_infrastructures[resource]["minio_endpoint"]
            minio_password = gp.virtual_infrastructures[resource]["minio_password"]
            command = "alias set minio-%s %s minio %s" % (resource, minio_endpoint, minio_password)
            command = oscarp.executables.mc.get_command(command)
            # print(command)
            get_command_output_wrapped(command)

            cluster_user = gp.virtual_infrastructures[resource]["user"]
            cluster_ip = gp.virtual_infrastructures[resource]["ip"]
            key_path = "%soscarp/.toscarizer/%s_SSH_key.pem" % (gp.application_dir, resource)
            gp.SSH_clients_info[resource] = {
                "user": cluster_user,
                "ip": cluster_ip,
                "key_path": key_path
            }
            # configure_ssh_client(cluster_user, cluster_ip, key_path)

    for resource in gp.current_resources:
        if gp.resources[resource].is_physical():
            oscar_endpoint = gp.resources[resource].oscar["endpoint"]
            oscar_password = gp.resources[resource].oscar["secret_key"]
            command = "cluster add oscar-%s %s oscar %s  --disable-ssl" % (resource, oscar_endpoint, oscar_password)
            command = oscarp.executables.oscar_cli.get_command(command)
            get_command_output_wrapped(command)

            minio_endpoint = gp.resources[resource].minio["endpoint"]
            minio_password = gp.resources[resource].minio["secret_key"]
            command = "alias set minio-%s %s minio %s" % (resource, minio_endpoint, minio_password)
            command = oscarp.executables.mc.get_command(command)
            get_command_output_wrapped(command)

            cluster_user = gp.resources[resource].ssh.split("@")[0]         
            cluster_ip = gp.resources[resource].ssh.split("@")[1].split("/")[0]
            cluster_port = gp.resources[resource].ssh.split("@")[1].split("/")[1]
            key_path = "%soscarp/.toscarizer/%s_SSH_key.pem" % (gp.application_dir, resource)
            gp.SSH_clients_info[resource] = {
                "user": cluster_user,
                "ip": cluster_ip,
                "port": cluster_port,
                "key_path": key_path
            }

    return


def get_infrastructures_outputs():
    """This function retrieves the outputs (endpoints and credentials) from IM for every virtual resource and \
     stores them in the virtual_infrastructures.json file."""

    for resource in gp.virtual_infrastructures.keys():
        if not resource == "jmeter" and not gp.resources[resource].is_lambda():
            # get outputs from IM
            inf_url = gp.virtual_infrastructures[resource]["inf_url"]
            outputs = get_outputs(inf_url)

            gp.virtual_infrastructures[resource]["oscar_endpoint"] = outputs["oscarui_endpoint"]
            gp.virtual_infrastructures[resource]["oscar_password"] = outputs["oscar_password"]

            gp.virtual_infrastructures[resource]["minio_endpoint"] = outputs["minio_endpoint"]
            gp.virtual_infrastructures[resource]["minio_password"] = outputs["minio_password"]

            gp.virtual_infrastructures[resource]["user"] = outputs["fe_node_creds"]["user"]
            gp.virtual_infrastructures[resource]["ip"] = outputs["fe_node_ip"]

            key_path = "%soscarp/.toscarizer/%s_SSH_key.pem" % (gp.application_dir, resource)

            with open(key_path, "w") as file:
                file.write(outputs["fe_node_creds"]["token"])

    with open(gp.application_dir + "/oscarp/virtual_infrastructures.json", "w") as file:
        json.dump(gp.virtual_infrastructures, file, indent=4)

    return


def get_outputs(inf_url):
    """This function retrieves the outputs (endpoints and credentials) from IM for a single virtual resource."""

    tosca_dir = "%sim" % gp.application_dir
    im_auth = "%s/auth.dat" % tosca_dir

    with open(im_auth, 'r') as f:
        auth_data = f.read().replace("\n", "\\n")

    headers = {"Authorization": auth_data, "Accept": "application/json"}

    try:
        resp = requests.get("%s/outputs" % inf_url, headers=headers, verify=True)
        return resp.json()["outputs"]
    except Exception as ex:
        show_fatal_error("Error: %s" % str(ex))

    return None


def get_number_of_worker_nodes(inf_url):
    """This function returns the number of worker nodes (number of nodes minus 1, the master) from IM."""

    tosca_dir = "%sim" % gp.application_dir
    im_auth = "%s/auth.dat" % tosca_dir

    with open(im_auth, 'r') as f:
        auth_data = f.read().replace("\n", "\\n")

    headers = {"Authorization": auth_data, "Accept": "application/json"}

    try:
        resp = requests.get("%s" % inf_url, headers=headers, verify=True)
        return len(resp.json()["uri-list"]) - 1
    except Exception as ex:
        show_fatal_error("Error: %s" % str(ex))

    return None


def update_virtual_infrastructures(new_resource_requirements):
    """This function updates the virtual infrastructures, usually by reducing its nodes."""

    if gp.is_dry:
        return

    if not gp.virtual_infrastructures:  # if empty return
        return

    t1 = datetime.now()
    for resource in gp.virtual_infrastructures.keys():
        if resource != "jmeter" and not gp.resources[resource].is_lambda():
            tosca_file_path = gp.virtual_infrastructures[resource]["tosca_file_path"]
            inf_id = gp.virtual_infrastructures[resource]["inf_id"]
            update_tosca(tosca_file_path, resource, new_resource_requirements[resource]["nodes"])
            deploy_virtual_infrastructure(tosca_file_path, resource, inf_id)

    wait_for_infrastructure_deployment(is_update=True)
    t2 = datetime.now()
    delta = round((t2 - t1).total_seconds(), 2)
    print("Update time: %s seconds" % delta)
    return


def update_tosca(tosca_file, resource, node_count):
    """This function updates the Tosca file of a virtual infrastructure by setting the correct number of nodes."""

    with open(tosca_file, 'r') as file:
        content = yaml.safe_load(file)

    if gp.resources[resource].is_lambda():
        return False

    key = "wn_resource1"
    for key in content["topology_template"]["node_templates"].keys():
        if "wn_resource" in key:
            break

    content["topology_template"]["node_templates"][key]["capabilities"]["scalable"]["properties"]["count"] = node_count

    with open(tosca_file, 'w') as file:
        yaml.dump(content, file, sort_keys=False)

    return


def delete_virtual_infrastructure(inf_url):
    """This function deletes a virtual infrastructure."""

    # inf_url = "https://appsgrycap.i3m.upv.es:31443/im/infrastructures/5aad513e-8120-11ed-9ece-ca414e79af22"

    tosca_dir = "%sim" % gp.application_dir
    im_auth = "%s/auth.dat" % tosca_dir

    with open(im_auth, 'r') as f:
        auth_data = f.read().replace("\n", "\\n")

    headers = {"Authorization": auth_data, "Accept": "application/json"}

    try:
        resp = requests.delete(inf_url, headers=headers, verify=True)
        print(resp)
    except Exception as ex:
        show_fatal_error(str(ex))


def delete_unused_virtual_infrastructures():
    """
    This function deletes unused virtual infrastructures; first it checks if there are infrastructures deployed on \
     IM but not tracked by gp.virtual_infrastructures, then checks if there are non-existing infrastructures still \
     tracked in gp.virtual_infrastructures, and finally checks if there are deployed and tracked infrastructures \
     that are no longer needed.
    """

    print(colored("Deleting unused infrastructures...", "yellow"))

    # part one checks if there are deployed infrastructures not tracked by gp.virtual_infrastructures
    for inf_url in get_all_infrastructures():
        if inf_url == '':  # nothing is deployed
            break

        is_in_use = False

        for r in gp.virtual_infrastructures.keys():
            if inf_url == gp.virtual_infrastructures[r]["inf_url"]:
                is_in_use = True
                break

        if not is_in_use:
            print(colored("Deleting untracked infrastructure...", "magenta"))
            delete_virtual_infrastructure(inf_url)

    # part two checks if there are non-existing infrastructures still tracked in gp.virtual_infrastructures
    existing_infrastructures = get_all_infrastructures()

    # keys of infrastructures present in virtual_infrastructures but not on IM
    keys_to_delete = []

    for r in gp.virtual_infrastructures.keys():
        if gp.virtual_infrastructures[r]["inf_url"] not in existing_infrastructures:
            print(colored("Untracking missing infrastructure...", "magenta"))
            keys_to_delete.append(r)

    for r in keys_to_delete:
        del gp.virtual_infrastructures[r]

    # part three checks if there are deployed and tracked infrastructures no longer needed
    resources_in_use = []

    for c in gp.current_deployment:
        c, r = c.split('@')
        resources_in_use.append(r)

    if gp.run_parameters["run"]["test_synchronously"]:
        resources_in_use.append("jmeter")

    keys_to_delete = []

    for r in gp.virtual_infrastructures.keys():
        if r not in resources_in_use:
            inf_url = gp.virtual_infrastructures[r]["inf_url"]
            print(colored("Deleting infrastructure no longer needed...", "magenta"))
            delete_virtual_infrastructure(inf_url)
            keys_to_delete.append(r)

    for r in keys_to_delete:
        del gp.virtual_infrastructures[r]

    with open(gp.oscarp_dir + "virtual_infrastructures.json", "w") as file:
        json.dump(gp.virtual_infrastructures, file, indent=4)

    return


def get_all_infrastructures():
    """This function returns a list of all infrastructures deployed on IM."""

    im_url = "https://im.egi.eu/im"
    #im_url = "https://appsgrycap.i3m.upv.es/im-dev/"

    tosca_dir = "%sim" % gp.application_dir
    im_auth = "%s/auth.dat" % tosca_dir

    with open(im_auth, 'r') as f:
        auth_data = f.read().replace("\n", "\\n")

    headers = {"Authorization": auth_data}

    try:
        resp = requests.request("GET", "%s/infrastructures" % im_url, headers=headers)
        return resp.text.split("\n")
    except Exception as ex:
        print(str(ex))
        return False, str(ex)


def delete_all_virtual_infrastructures():
    """This function deletes ALL virtual infrastructures, without checks."""

    infrastructures = get_all_infrastructures()

    if infrastructures == ['']:  # if list is empty
        return
    else:
        print(colored("Deleting all infrastructures...", "yellow"))
        for inf_url in infrastructures:
            delete_virtual_infrastructure(inf_url)
    return


def configure_jmeter_cluster():
    if not gp.run_parameters["run"]["test_synchronously"]:
        return

    # set the correct number of nodes
    jmeter_tosca_file = "jmeterLoadInjector/jmeter_cluster.yml"

    with open(jmeter_tosca_file, 'r') as file:
        jmeter_tosca = yaml.safe_load(file)

    jmeter_tosca["topology_template"]["inputs"]["wn_num"]["default"] = gp.run_parameters["synchronous"]["worker_nodes"]

    with open(jmeter_tosca_file, 'w') as file:
        yaml.dump(jmeter_tosca, file, sort_keys=False)

    # deploy jmeter
    if "jmeter" in gp.virtual_infrastructures:
        inf_url = gp.virtual_infrastructures["jmeter"]["inf_url"]
    else:
        print(colored("Deploying Jmeter cluster...", "yellow"))
        tosca_file = "jmeterLoadInjector/jmeter_cluster.yml"
        inf_url = deploy_virtual_infrastructure(tosca_file, "Jmeter", None)

        state = None

        while state != "configured":
            time.sleep(30)
            state = get_state(inf_url)
            if state == "failed" or state == "unconfigured":
                show_fatal_error("The deployment of infrastructure Jmeter cluster failed.")

        print(colored("Jmeter cluster deployed successfully.", "green"))

        gp.virtual_infrastructures["jmeter"] = {
            "inf_url": inf_url,
            "inf_id": inf_url.split('/')[-1]
        }

        with open(gp.application_dir + "/oscarp/virtual_infrastructures.json", "w") as file:
            json.dump(gp.virtual_infrastructures, file, indent=4)

    # configure jmeter client
    print(colored("Configuring Jmeter cluster...", "yellow"))

    outputs = get_outputs(inf_url)

    cluster_ip = outputs["cluster_ip"]
    cluster_user = outputs["cluster_creds"]["user"]
    key_path = gp.oscarp_dir + ".toscarizer/jmeter_SSH_key.pem"

    with open(key_path, "w") as file:
        file.write(outputs["cluster_creds"]["token"])

    gp.SSH_clients_info["jmeter"] = {
        "user": cluster_user,
        "ip": cluster_ip,
        "key_path": key_path
    }
    # configure_ssh_client(cluster_user, cluster_ip, key_path)

    print(colored("Done!", "green"))
    return


# # # # # # # # # # # #
# Physical infrastructures
# # # # # # # # # # # #

# returns a list of nodes, with status = off if cordoned or on otherwise
# doesn't return master nodes
def get_node_list(client):
    lines = get_ssh_output(client, "sudo kubectl get nodes")

    lines.pop(0)

    node_list = []

    for line in lines:
        node_name = line.split()[0]
        node_status = line.split()[1]
        node_role = line.split()[2]
        if "SchedulingDisabled" in node_status:
            node_status = "off"
        else:
            node_status = "on"

        # doesn't include master node
        if "master" not in node_role:
            node_list.append({
                "name": node_name,
                "status": node_status,
            })

    return node_list


# cordons or un-cordons the nodes of the cluster to obtain the number requested for the current run
def adjust_physical_infrastructures_configuration():
    has_printed_message = False

    for r in gp.resources_node_requirements:
        cluster = gp.resources[r]

        if cluster.ssh is not None:

            if not has_printed_message:
                print(colored("Adjusting physical infrastructures configuration...", "yellow"))
                has_printed_message = True

            client = configure_ssh_client(cluster)
            node_list = get_node_list(client)

            requested_number_of_nodes = gp.resources_node_requirements[r][gp.current_base_index]

            # show_debug_info(make_debug_info(["Cluster configuration BEFORE:"] + node_list))

            for i in range(1, len(node_list) + 1):
                node = node_list[i - 1]
                if i <= requested_number_of_nodes and node["status"] == "off":
                    get_ssh_output(client, "sudo kubectl uncordon " + node["name"])
                if i > requested_number_of_nodes and node["status"] == "on":
                    get_ssh_output(client, "sudo kubectl cordon " + node["name"])

            # show_debug_info(make_debug_info(["Cluster configuration AFTER:"] + get_node_list(client)))

    if has_printed_message:
        print(colored("Done!", "green"))

    return
