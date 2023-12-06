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

import yaml

from classes.Component import Component
from classes.Resource import Resource
from oscarp.utils import show_fatal_error, read_yaml, show_warning

import global_parameters as gp


def get_resources():
    """
    Reads the resources from the candidate_resources.yaml file and reorganizes them as Resource classes.

    :return: None
    """

    physical_nodes = _get_physical_nodes()
    
    with open(gp.application_dir + "common_config/candidate_resources.yaml") as file:
        candidate_resources = yaml.load(file, Loader=yaml.Loader)
    
    gp.resources = {}
    for _, nd in candidate_resources["System"]["NetworkDomains"].items():
        if "ComputationalLayers" in nd:
            for cl_name, cl in nd["ComputationalLayers"].items():
                for resource in list(cl["Resources"].values()):
                    name = resource["name"]

                    gp.resources[name] = Resource(
                        name=name,
                        resource_type=cl["type"],
                        physical_nodes=physical_nodes,
                        execution_layer=cl["number"]  # needed for modified candidate deployments file
                    )
                    
                    if cl["type"] != "NativeCloudFunction":
                        processor = list(resource["processors"].values())[0]
                        gp.resources[name].total_nodes = resource["totalNodes"]
                        gp.resources[name].max_cpu_cores = float(processor["computingUnits"])
                        gp.resources[name].max_memory_mb = resource["memorySize"]
                        gp.resources[name].set_storage_provider_alias("minio")

                    else:
                        gp.resources[name].total_nodes = 1
                        gp.resources[name].max_cpu_cores = 1000
                        gp.resources[name].max_memory_mb = 1000 * 3008
                        gp.resources[name].bucket_name = _get_bucket_name_for_lambda(name)
                        gp.resources[name].set_storage_provider_alias("s3")
    
    if gp.is_debug:
        print("Resources:")
        for resource in gp.resources.values():
            print("\t", resource)
        print()
    
    return


def _get_physical_nodes():
    """
    Parses the physical_nodes.yaml file and extracts the info related to the SSH front node access, so IP, port and \
     user.

    :return: dictionary with the parsed information
    """

    physical_nodes_file = read_yaml(gp.application_dir + "common_config/physical_nodes.yaml")

    if physical_nodes_file == {}:
        show_warning("physical_nodes.yaml is empty or missing")
        return {}

    physical_nodes = {}
    for _, cl in physical_nodes_file["ComputationalLayers"].items():
        for _, resource in cl["Resources"].items():
            name = resource["name"]
            physical_nodes[name] = {}
            if "fe_node" in resource.keys():
                fn = resource["fe_node"]
                physical_nodes[name]["ssh"] = "%s@%s/%s" % (fn["ssh_user"], fn["public_ip"], fn["ssh_port"])
                file = open(gp.application_dir + "oscarp/.toscarizer/" + name + "_SSH_key.pem", "w")
                file.write(fn["ssh_key"])
                file.close()
            if "minio" in resource.keys():
                minio = resource["minio"]
                physical_nodes[name]["minio"] = {"endpoint": minio["endpoint"], 
                                                 "access_key": minio["access_key"], 
                                                 "secret_key": minio["secret_key"]}
            if "oscar" in resource.keys():
                oscar = resource["oscar"]
                physical_nodes[name]["oscar"] = {"endpoint": oscar["endpoint"], 
                                                 "access_key": oscar["access_key"], 
                                                 "secret_key": oscar["secret_key"]}

    return physical_nodes


def _get_bucket_name_for_lambda(resource_name):
    """
    Reads the name of the bucket of the AWS resource from the physical_nodes.yaml file.

    :param str resource_name: name of the AWS resource
    :return: None
    """

    physical_nodes_file = read_yaml(gp.application_dir + "common_config/physical_nodes.yaml")

    if physical_nodes_file == {}:
        show_fatal_error("physical_nodes.yaml is empty or missing")
        return

    for _, cl in physical_nodes_file["ComputationalLayers"].items():
        for _, resource in cl["Resources"].items():
            if resource["name"] == resource_name:
                aws = resource["aws"]
                return aws["bucket"]

    show_fatal_error("Couldn't find resource %s in physical_nodes.yaml" % resource_name)
    return


def get_components():
    """
    TLDR: get all the components and their docker images from candidate_deployments.yaml.
    This functions reads the components from candidate_deployments.yaml, saves them in Component objects, and then \
    saves them as dictionary indexed by group and by name.
    As an example, components_groups is organized as follows: [ component1 -> blurry-faces-onnx -> \
     blurry-faces-onnx.containers -> C1@VM1 -> image: blurry-faces-onnx_base_amd641_amd64:latest ].
    Basically it's groups -> ACTUAL components -> containers -> appropriate (single) docker image.
    Component_names instead skips a step and indexes them directly by name (e.g. blurry-faces-onnx, \
     blurry-faces-onnx_partition1_1, ...)
    Finally, containers is a dictionary indexed by unit (e.g. C1@VM2, C1PX.1@VM2, ...).
    """

    with open(gp.application_dir + "common_config/candidate_deployments.yaml") as file:
        candidate_deployments = yaml.load(file, Loader=yaml.Loader)

    gp.components_groups = {"alternatives": {}}
    gp.components_names = {}
    gp.containers = {}

    for component_key in candidate_deployments["Components"]:  # component1, component1_partitionX_1...

        # section extracted from candidate_deployments.yaml
        component_section = candidate_deployments["Components"][component_key]

        # base component and partitions alike are all collected under the same group, for example "component1"
        component_group = component_key.split("_partition")[0]  # component1

        # base component name is the component name without "partitions"
        component_name = component_section["name"]  # blurry-faces-onnx_partitionX_1

        # if the component_group key doesn't exist, create the entry
        if component_group not in gp.components_groups and "alternative" not in component_key:
            gp.components_groups[component_group] = {}

        matching_partition_groups = _get_actual_partitions(component_name)

        # creates a Component object for each actual partition (X_1 -> 1_1, 2_1, 3_1, etc.)
        for partition_group in matching_partition_groups:

            new_component = Component(
                name=component_name,
                component_key=component_key,
                partition_group=partition_group
                )

            _set_containers(new_component, component_key, component_section["Containers"])

            if "alternative" in component_key:
                gp.components_groups["alternatives"][new_component.name] = new_component
            else:
                gp.components_groups[component_group][new_component.name] = new_component
            gp.components_names[new_component.name] = new_component

    # set the following partition for each component, if any
    # base components don't have a following partition
    for group in gp.components_groups:  # component1, component2, etc.
        for component in gp.components_groups[group].values():  # Component classes
            component.set_following_partition(gp.components_groups[group])

    if gp.is_debug:
        print("Components:")
        for component in gp.components_names.values():
            print("\t", component)
        print()

    return


def _check_device_constraints(base_component_name, memory_size, gpu_requirement):
    """
    Ensures that the memory and GPU constraints between the annotations.yaml and the candidate_deployments.yaml are \
     consistent.
    """

    with open(gp.application_dir + "common_config/annotations.yaml") as file:
        annotations = yaml.load(file, Loader=yaml.Loader)

    for component in annotations.values():
        if base_component_name == component["component_name"]["name"]:
            if "device_constraints" in component.keys():
                if "ram" in component["device_constraints"].keys():
                    ram_constraint = component["device_constraints"]["ram"] * 1024  # converts from GB to MB
                    if ram_constraint > memory_size:
                        show_fatal_error("Memory size in candidate_deployments is less than what specified"
                                         " in the annotations for component %s" % base_component_name)
                if "vram" in component["device_constraints"].keys() and gpu_requirement is False:
                    show_fatal_error("Component %s requires a GPU, but the requirement is not set "
                                     "in candidate_deployments" % base_component_name)
    return


def _set_containers(parent_component, component_key, containers):
    """
    Given a component, it adds a Container class to it for each of the containers listed under that component in \
     candidate_deployments.yaml.

    :param Component parent_component: component to add containers to
    :param str component_key: component key (e.g. component1)
    :param dict containers: containers dictionary as extracted from candidate_deployments.yaml

    :return: None
    """

    for container in containers.values():
        resources = container["candidateExecutionResources"]

        base_component_name = parent_component.name.split("_partition")[0]  # blurry-faces-onnx

        for r in resources:
            _check_device_constraints(base_component_name, container["memorySize"], container["GPURequirement"])

            parent_component.add_container(
                parent=parent_component,
                unit_id=shorten_key(component_key) + "@" + r,  # C1@VM1,
                computing_units=container["computingUnits"],
                memory_size=container["memorySize"],
                docker_image=container["image"],
                gpu_requirement=container["GPURequirement"]
            )

    return


def _get_actual_partitions(component_key):
    """
    This function returns an array containing the partition groups that match the component name, which  is needed to \
     turn "partitionX_1" into "partition1_1".
    The candidate_deployments.yaml file has no knowledge about the actual generated partitions, so we need to get this \
     information from the component_partitions.yaml file.
    """

    with open(gp.application_dir + "aisprint/designs/component_partitions.yaml") as file:
        component_partitions = yaml.load(file, Loader=yaml.Loader)["components"]

    if "_partition" not in component_key:
        return ["1"]

    name, partition_code = component_key.split("_partition")  # blurry-faces-onnx, X_1

    available_partitions = component_partitions[name]["partitions"]  # ['base', 'partition1_1', 'partition1_2']

    # we need to make sure that we get the right partitions, e.g. if we're looking for partitionX_1,
    # (the first partition), we need to ensure that we get return partitions that end with _1

    target_partition_number = partition_code.split("_", -1)[-1]  # X_1 --> 1

    matching_partition_groups = []
    for partition in available_partitions:
        partition_number = partition.split("_", -1)[-1]  # partition2_1 --> 1

        if partition_number == target_partition_number:
            # in the end we only care about the partition group of the matches
            partition_group = partition.split("_", -1)[0].strip("partition")  # partition2_1 --> 2
            matching_partition_groups.append(partition_group)

    return matching_partition_groups


def get_run_parameters():  # todo we should also check that the required files exist at some point near the start
    """
    Reads the run_parameters.yaml file and sets the run_parameters and component_parallelism global variables.
    Additionally, it makes sure that the parallelism lists are of the same length and in decreasing order.
    """

    with open(gp.application_dir + "oscarp/run_parameters.yaml") as file:
        run_parameters = yaml.load(file, Loader=yaml.Loader)

    # to make sure that the parallelism lists are of the same length, we start by getting the length of the first
    length = len(list(run_parameters["components"].values())[0]["parallelism"])

    for component in run_parameters["components"].items():
        p = len(component[1]["parallelism"])
        if p != length:
            show_fatal_error("Parallelism lists of different length in file \"run_parameters.yaml\"")
        check_parallelism_is_in_decreasing_order(component[1]["parallelism"])

    # urgent also check that the parallelism array is listed in decreasing order

    gp.base_length = length
    gp.is_sync = run_parameters["run"]["test_synchronously"]
    gp.run_parameters = run_parameters
    return


def check_parallelism_is_in_decreasing_order(parallelism):
    """
    Ensures that the parallelism array is listed in decreasing order, if not it interrupts the execution and shows \
     an error.
    If the parallelism is listed in increasing order, the testing takes more time because the VMs need to be created \
     as needed, and that takes 15 minutes.

    :param list parallelism: parallelism array
    :return: None
    """

    if len(parallelism) == 0:
        show_fatal_error("Parallelism array must contain at least one value")

    if len(parallelism) == 1:
        return

    last_value = parallelism[0]

    for i in range(1, len(parallelism)):
        # print(last_value, parallelism[i])
        if last_value < parallelism[i]:
            show_fatal_error("Parallelism array must be listed in decreasing order")
        last_value = parallelism[i]
    return


def set_testing_parameters():
    """
    Adds the parallelism field and the time distribution (the latter needed for single service testing) to the \
     Component classes.

    :return: None
    """

    for group in gp.components_groups:  # component1, component2, etc.
        for component in gp.components_groups[group].values():
            
            if "alternative" in component.component_key:
                component_parameters = gp.run_parameters["components"][component.component_key.split("_alternative")[0]]
            else:
                component_parameters = gp.run_parameters["components"][component.component_key]

            component.set_parallelism(component_parameters["parallelism"])

            if "distribution" in component_parameters:
                component.set_time_distribution(component_parameters["distribution"])
            else:
                component.set_time_distribution(None)

    return


def shorten_key(component_key):
    """
    Receives a component key and returns a shortened version (e.g. component1 -> C1, component1_partitionX_1 -> C1P1.1).

    :param str component_key: component key
    :return: shortened component key
    """

    if "partition" in component_key:
        c, p, i = component_key.split("_")
        c = c.strip("component")
        p = p.strip("partition")
        return "C" + str(c) + "P" + str(p) + "." + str(i)
    elif "alternative" in component_key:
        c, a = component_key.split("_")
        c = c.strip("component")
        a = a.strip("alternative")
        return "C" + str(c) + "A" + str(a)
    else:
        c = component_key.strip("component")
        return "C" + str(c)
