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

import global_parameters as gp
from classes.Component import generalize_unit_id, get_parent_component_from_unit
from oscarp.utils import ensure_slash_end, show_fatal_error


class Service:
    """
    Service class, a service is the object that is actually deployed, this class contains the necessary information

    :param str self.unit: unit id of the service (e.g. C1@VM2, C1P1.1@VM2, ...)
    :param str self.name: name of the service (e.g. blurry-faces, ...)
    :param str self.resource: resource of the service (e.g. VM1, RasPi, ...)
    :param str self.image: URL of the docker image of the service
    :param int self.input_bucket_index: index of the input bucket, numbered in increasing order (e.g. 0 for the first \
    service, 1 for the second...)
    :param str self.input_bucket: name of the input bucket, numbered in increasing order (e.g. bucket0 for the first \
    service, bucket1 for the second...)
    :param str self.output_bucket: name of the output bucket
    :param str self.storage_provider_alias: storage provider alias, the dash is replaced with a dot (e.g. minio-VM1 \
    -> minio.VM1) so that it be written in the correct format to the FDL file
    :param str self.oscarcli_alias: oscarcli alias of the service, as copied by the correct resource
    :param float self.cpu: number of cpu cores required by the service
    :param int self.memory: memory size in MB required by the service
    :param bool self.is_lambda: True if the service is a lambda, False otherwise
    :param [int] self.parallelism: parallelism array as copied by the parent component

    """

    def __init__(self, unit, name, input_bucket_index):
        self.unit = unit
        self.name = name
        self.resource = unit.split("@")[1]

        resource_class = gp.resources[self.resource]
        container_class = gp.containers[generalize_unit_id(unit)]

        self.image = container_class.image

        self.input_bucket_index = input_bucket_index
        self.input_bucket = "bucket" + str(self.input_bucket_index)
        self.output_bucket = "bucket" + str(self.input_bucket_index + 1)
        self.storage_provider_input = resource_class.storage_provider_alias
        self.storage_provider_output = self.storage_provider_input

        self.oscarcli_alias = resource_class.oscarcli_alias
        self.cpu = container_class.cpu
        self.memory = container_class.memory
        self.is_lambda = resource_class.is_lambda()

        self.input_bucket_full_workflow = "bucket" + str(self.input_bucket_index)
        self.output_bucket_full_workflow = "bucket" + str(self.input_bucket_index + 1)
        self.input_bucket_single_testing = "temp" + str(self.input_bucket_index)
        self.output_bucket_single_testing = "trash" + str(self.input_bucket_index)

        self.parallelism = get_parent_component_from_unit(unit).parallelism
        self.time_distribution = gp.components_names[self.name].time_distribution

        if input_bucket_index == 0:
            self.time_distribution = None
        elif self.time_distribution is None:
            show_fatal_error("Time distribution not specified for Service %s" % self.name)

        self.name = self.name.replace("_", "-")

    def __str__(self):
        return "%s, %s, Cores: %s, Memory: %s MB" % (self.name, self.unit, self.cpu, self.memory)

    def connect_to_previous_service(self, previous_service):
        if not self.is_lambda:
            return

        # self.storage_provider_input = "s3"
        # self.storage_provider_output = self.storage_provider_input

        bucket_name = gp.resources[self.resource].bucket_name

        self.input_bucket_full_workflow = bucket_name + "/" + previous_service.name + "/output"
        self.output_bucket_full_workflow = bucket_name + "/" + self.name + "/output"

        self.input_bucket_single_testing = bucket_name + "/" + self.name + "/temp" + str(self.input_bucket_index)
        self.output_bucket_single_testing = bucket_name + "/" + self.name + "/trash" + str(self.input_bucket_index)

        self.set_buckets_full_workflow()

    def connect_to_next_service(self, next_service):

        self.output_bucket_full_workflow = next_service.input_bucket
        self.storage_provider_output = next_service.storage_provider_input
        self.set_buckets_full_workflow()

    def set_buckets_full_workflow(self):
        """
        Sets the input and output buckets for the test in the full workflow

        xx

        :return: None
        """

        self.input_bucket = self.input_bucket_full_workflow
        self.output_bucket = self.output_bucket_full_workflow
        return

    def set_buckets_single_testing(self):
        """
        Sets the input and output buckets for the test in the single testing, the index is the same, the input bucket \
        is named "temp" and the output bucket is named "trash"

        :return: None
        """

        self.input_bucket = self.input_bucket_single_testing
        self.output_bucket = self.output_bucket_single_testing
        return
