import math
import os
from itertools import combinations

from termcolor import colored

from classes.Component import generalize_unit_id, get_alternative_containers
from classes.Service import Service
from oscarp.utils import show_fatal_error, show_warning, delete_directory

import global_parameters as gp


# # # # # # # # # # # #
# Main functions
# # # # # # # # # # # #

def get_testing_units():
    """
    This function lists all the available containers, divided in groups, BUT partitions are grouped together.
    Component_groups contains a list for each group (component1, component2, ...), and each list contains all the \
     testing_units for that group; a testing_unit is just a way to keep together all the correlated partitions.
    An example of testing unit for a base component is ['C1@VM1'], an example for a partitioned component \
     is ['C1P1.1@VM1', 'C1P1.2@VM1']

    :return: container_groups, list of lists
    """

    containers_groups = []

    for group in gp.components_groups:

        # create a new "testing_units" column for the current group
        testing_units = []

        if group == "alternatives":
            continue

        for component in gp.components_groups[group].values():

            if component.is_partition():
                if component.partition_number == "1":

                    for container in component.containers:
                        testing_units.append([container.unit])

                    # it is assumed that the first partitions always have a next component
                    # this isn't recursive, it only considers the first partition and its next component
                    next_component = gp.components_names[component.next]
                    for container in next_component.containers:
                        testing_units[-1].append(container.unit)

            else:
                for container in component.containers:
                    testing_units.append([container.unit])

        # add the testing units for the current group to the list
        containers_groups.append(testing_units)

    return containers_groups


def get_deployments():
    """
    From the testing units, generates all the possible combinations of them; these are the possible deployments.

    :return: None
    """

    import itertools

    gp.deployments = []

    iterables = get_testing_units()

    for t in list(itertools.product(*iterables)):
        deployment = []
        for unit in t:
            for component in unit:
                deployment.append(component)
        gp.deployments.append(deployment)

    return


def reorder_deployments(deployments, resources):  # todo fix or remove
    reordered_deployments = []

    combined_resources = get_resources_combinations(resources)

    for c in combined_resources:
        for d in deployments:
            used_resources = get_used_resources(d)
            if check_match_combined_used_resources(c, used_resources):
                reordered_deployments.append(d)

        for r in reordered_deployments:
            if r in deployments:
                deployments.remove(r)

    return reordered_deployments


def get_services_to_test():
    """
    Returns a list of services to test given the current deployment, skipping the ones already tested in previous \
     deployments, and adding in the alternative versions, if any.

    :return: list of services (Service class)
    """

    services_to_test = []
    tested_services = []

    # step one, checks what was tested in previous deployments
    for i in range(gp.current_deployment_index):
        tested_services.extend(gp.deployments[i])

    # step two, add services only if they haven't been tested already AND they aren't lambdas
    for service in gp.current_services_list:
        if service.unit not in tested_services:  # and not service.is_lambda:
            services_to_test.append(service)

    # step three, create and add alternatives services
    alternative_services_to_test = []
    for service in services_to_test:
        alternative_containers = get_alternative_containers(service.unit)

        for alternative_container_key in alternative_containers:
            name = gp.containers[alternative_container_key].parent.name
            bucket_index = service.input_bucket_index
            alternative_services_to_test.append(Service(alternative_container_key, name, bucket_index))

    services_to_test.extend(alternative_services_to_test)

    return services_to_test


def make_deployments_summary():
    """
    Prints the list of the deployments, and also writes it to a file.

    :return: None
    """

    print("\nDeployments:")
    with open(gp.campaign_dir + "/deployments_summary.txt", "w") as file:
        for i in range(len(gp.deployments)):
            deployment = "deployment_" + str(i) + ": " + str(gp.deployments[i])
            print("\t" + deployment)
            file.write(deployment + "\n")
    return


def make_resources_requirements():
    """
    Calculates the requirements of each resource in terms of nodes, given the hardware of the resource, the \
     requirements of the containers, and the number of parallel instances to be supported.
    The calculations are done taking into account a 10% headroom for the OS in terms of both CPU and RAM.

    :return: None
    """

    print(colored("Calculating hardware requirements...", "yellow"))

    gp.current_resources = []
    gp.resources_node_requirements = {}

    for component in gp.current_deployment:
        group, resource_id = component.split('@')

        # container requirements
        container = gp.containers[generalize_unit_id(component)]
        parallelism = container.parent.parallelism
        cpu = container.cpu
        memory = container.memory

        # node resources (minus 10% headroom for OS)
        resource = gp.resources[resource_id]
        node_cpu = resource.max_cpu_cores * 0.9
        node_memory = resource.max_memory_mb * 0.9
        total_nodes = resource.total_nodes

        # make sure that a node can fit at least one container
        if cpu > node_cpu or memory > node_memory:
            show_fatal_error("Container requires more resources than available on a node")

        if resource.type == "lambda" and memory > 3008:
            show_fatal_error("Memory for Lambda functions can't exceed 3008 MB")

        # calculate how many containers can a node accommodate
        container_per_node = math.floor(min(node_cpu / cpu, node_memory / memory))
        node_per_container = 1 / container_per_node

        if resource.type != "lambda":
            print("Component %s can fit %s container(s) on every node" % (component, container_per_node))
            if node_cpu / cpu < node_memory / memory:
                new_cpu = node_cpu / (container_per_node + 1)
                print("\tCPU needs to be decreased to (at least) %s to fit more" % new_cpu)
            else:
                new_memory = node_memory / (container_per_node + 1)
                print("\tMemory needs to be decreased to (at least) %s to fit more" % new_memory)

        if resource_id not in gp.current_resources:
            gp.current_resources.append(resource_id)

        node_requirements = []

        if resource_id not in gp.resources_node_requirements.keys():
            for x in parallelism:
                nr = math.ceil(x * node_per_container)
                node_requirements.append(nr)
        else:
            prev_node_requirements = gp.resources_node_requirements[resource_id]
            for x in range(len(parallelism)):
                nr = math.ceil(parallelism[x] * node_per_container)  # node requirement for current parallelism
                nr += prev_node_requirements[x]  # node requirement for current parallelism, for all services up to now
                node_requirements.append(nr)

        if nr > total_nodes and resource.type != "lambda":
            show_fatal_error("Resource {} has {} nodes, but {} are needed for testing"
                             .format(resource_id, total_nodes, nr))

        gp.resources_node_requirements[resource_id] = node_requirements

    return


# # # # # # # # # # # #
# Secondary functions
# # # # # # # # # # # #

def get_resources_combinations(resources):
    resources = list(resources.keys())

    combined_resources = []

    for i in range(1, len(resources) + 1):
        combined_resources += list(combinations(resources, i))

    return combined_resources


def check_match_combined_used_resources(combined_resources, used_resources):
    # if they have different sizes they're not identical
    if len(combined_resources) != len(used_resources):
        return False

    # if they have the same size, check that every item in combined appears in used
    for c in combined_resources:
        if c not in used_resources:
            return False

    return True


def has_completes_results(deployment_dir, service_dir):
    results_dir = os.path.join(gp.campaign_dir, deployment_dir, service_dir, "results")

    if os.path.exists(results_dir):
        done_path = os.path.join(results_dir, "done")
        if os.path.exists(done_path):
            return True

    return False
