from oscarp.utils import show_fatal_error

import global_parameters as gp


class Component:
    """
    Component class, contains components parsed from candidate_deployments.yaml

    :param str self.name: name of the component (e.g. blurry-faces, blurry-faces-onnx_partition1_1, ...)
    :param str self.component_key: (e.g. component1, component1_partitionX_1, ...)
    :param [Container] self.containers: list of the Containers of the component
    :param str self.next: if the component is partitioned, and there is a following partition, this will contain the
        name of the next component, otherwise is None
    :param [int] self.parallelism: parallelism array as copied from run_parameters.yaml
    :param str self.time_distribution: time distribution (deterministic or exponential), copied from run_parameters.yaml
    :param int self.partition_group: the first value in the partition id, e.g. the X in X_1
    :param int self.partition_number: inside a group, identify the position of the partition (first, second, ...)

    """

    def __init__(self, name, component_key, partition_group):

        self.name = name
        self.component_key = component_key
        self.containers = []
        self.next = None
        self.parallelism = None
        self.time_distribution = None

        if self.is_partition():
            self._update_name(partition_group)
        else:
            self.partition_group = None
            self.partition_number = None

    def __str__(self):
        container_string = ""
        for container in self.containers:
            container_string += "\n\t\t" + container.__str__()

        if self.partition_group is not None:
            partition_id = "PartitionID: %s_%s, " % (self.partition_group, self.partition_number)
        else:
            partition_id = ""

        return "Name: %s, %sNext: %s, Containers: %s" % (self.name, partition_id, self.next, container_string)

    def _update_name(self, partition_group):
        """
        Transforms the name of a partitioned component from the general version (e.g. X_1), to a specific one (e.g. 1_1)

        :return: None
        """

        # the marker is the letter that we want to replace with the partition group
        marker = self.name.split("_partition")[1].split("_")[0]
        self.name = self.name.replace(marker, partition_group, -1)
        self.partition_number = self.name.split("_", -1)[-1]
        self.partition_group = partition_group
        return

    def add_container(self, parent, unit_id, computing_units, memory_size, docker_image, gpu_requirement):
        """
        Adds a Container to the component, see class Container for more details

        :return: None
        """

        new_container = Container(
            parent=parent,
            unit=unit_id,
            image=self._get_correct_image(docker_image),
            computing_units=computing_units,
            memory_size=memory_size,
            gpu_requirement=gpu_requirement,
            is_partition=self.is_partition(),
            partition_group=self.partition_group
        )

        self.containers.append(new_container)
        gp.containers[unit_id] = new_container
        return

    def _get_correct_image(self, docker_image):  # todo what happens with Lambda?
        """
        Selects the correct image for a given container, if there are multiple available

        :param docker_image: this could be a str or a list of str
        :return: the correct image
        """

        # if we have only one image that's already the correct one
        if isinstance(docker_image, str):
            if self.name in docker_image:
                return docker_image
            else:
                show_fatal_error("Mismatch in image naming for component %s" % self.name)

        for image in docker_image:  # todo does this even work?
            if self.name in image:
                return image

        show_fatal_error("No docker image found for component %s" % self.name)

    def is_partition(self):
        """
        :return: True if the component is partitioned, False otherwise
        """
        return "partition" in self.component_key

    def set_parallelism(self, parallelism):
        """
        Sets the parallelism of the component to the value received

        :return: None
        """
        self.parallelism = parallelism
        return

    def set_time_distribution(self, time_distribution):
        """
        Sets the time distribution of the component to the value received

        :return: None
        """
        self.time_distribution = time_distribution
        return

    def set_following_partition(self, components):
        """
        This function looks for components that have the same partition group and partition number + 1; if found, \
        "self.next" is set to the name of that component

        :param components: list of Components, only those in the same group of the one being called (e.g. only the one
            that fall under component1 and its partitions)
        :return: None
        """
        if not self.is_partition():
            return

        target_partition_group = self.partition_group
        target_partition_number = str(int(self.partition_number) + 1)

        for component in components.values():  # Component classes
            if component.is_partition():  # base components are skipped
                if component.partition_group == target_partition_group and \
                        component.partition_number == target_partition_number:
                    self.next = component.name
                    return
        return


class Container:
    """
    Container class, contains containers parsed from candidate_deployments.yaml

    :param str self.parent: parent Component, actual class not just the name
    :param str self.unit: unit id of the container, e.g. C1@VM2, C1P1.1@VM2, ...
    :param str self.image: URL of the image of the container
    :param float self.computing_units: number of computing units required by the container
    :param int self.memory_size: memory size of the container, in MB
    :param bool self.gpu_requirement: True if the container requires a GPU, False otherwise

    """

    def __init__(self, parent, unit, image, computing_units, memory_size, gpu_requirement,
                 is_partition, partition_group):

        self.parent = parent
        self.unit = unit
        self.resource = unit.split("@")[1]
        self.image = image
        self.cpu = computing_units
        self.memory = memory_size
        self.gpu_requirement = gpu_requirement

        if is_partition:
            self._update_id(partition_group)

    def __str__(self):
        return "ID: %s, Resource: %s, Computing Units: %s, Memory Size: %s, Image: %s" % (
            self.unit, self.resource, self.cpu, self.memory, self.image
        )

    def _update_id(self, partition_group):
        """
        Transforms the unit ID of the container from the general version (e.g. X_1), to a specific one (e.g. 1_1)

        :return: None
        """

        # the marker is the letter that we want to replace with the partition group
        marker = self.unit.split("P")[1].split(".")[0]
        self.unit = self.unit.replace(marker, partition_group, -1)
        return


def generalize_unit_id(unit_id):
    """
    Receives a specific unit ID and returns a generalized one (e.g. C1P1.1@VM1 -> C1PX.1@VM1)

    :return str: generalized unit ID
    """

    if '.' in unit_id:
        a, b = unit_id.split('.')
        generalized_key = a[:-1] + 'X.' + b
        return generalized_key

    return unit_id


def generalize_name(component_name):
    """
    Receives a specific component_name, and returns a generalized one \
    (e.g. blurry-faces-onnx_partitionX_1 -> blurry-faces-onnx_partition1_1)

    :return str: generalized component name
    """

    if "partition" not in component_name:
        return component_name

    a, b = component_name.split('partition')
    b, c = b.split('_')

    component_name = a + "partitionX_" + c

    return component_name


def get_alternative_containers(unit):
    """
    Returns the list of alternative CONTAINERS keys of a base component, if the resource matches

    :return [str]: list of alternative containers keys
    """

    matching_alternatives = []

    component_key, resource = unit.split('@')

    for component in gp.components_groups["alternatives"].values():
        for container in component.containers:
            if component_key in container.unit and resource in container.unit:
                matching_alternatives.append(container.unit)

    return matching_alternatives


def get_parent_component_from_unit(unit):
    return gp.containers[generalize_unit_id(unit)].parent
