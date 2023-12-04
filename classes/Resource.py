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

from oscarp.utils import show_fatal_error


class Resource:
    """
    Resource class, contains resources parsed from candidate_resources.yaml

    :param str self.name: name of the resource (e.g. VM1, RasPi, ...)
    :param str self.type: type of resource, physical, virtual or lambda
    :param str self.oscarcli_alias: oscarcli alias of the resource (e.g. oscar-VM1)
    :param str self.storage_provider: storage provider of the resource, usually minio, s3 for lambdas
    :param str self.storage_provider_alias: storage provider alias (e.g. minio-VM1), always "aws" for lambdas
    :param str self.ssh: ssh address of the resource, if physical, saved as user@host:port
    :param int self.total_nodes: max number of nodes of the resource
    :param float self.max_cpu_cores: max number of cpu cores of the resource (node resource times the number of nodes)
    :param int self.max_memory_mb: max memory size in MB of the resource (node resource times the number of nodes)
    :param str self.bucket_name: name of the s3 bucket of the resource (if lambda, None otherwise)
    :param int self.execution_layer: execution layer of the resource
    """

    def __init__(self, name, resource_type, physical_nodes, execution_layer):

        self.name = name
        self._set_type(resource_type)  # physical, virtual or lambda

        self.oscarcli_alias = "oscar-" + name
        self.storage_provider = None
        self.storage_provider_alias = None
        self._set_ssh(physical_nodes)
        self._set_minio(physical_nodes)
        self._set_oscar(physical_nodes)

        self.total_nodes = None
        self.max_cpu_cores = None
        self.max_memory_mb = None
        self.bucket_name = None
        self.execution_layer = execution_layer

    def __str__(self):
        return "%s, Type: %s, Nodes: %s, Cores: %s, Memory: %s MB" % \
            (self.name, self.type, self.total_nodes, self.max_cpu_cores, self.max_memory_mb)

    def _set_type(self, resource_type):
        """
        Sets the type of the resource as physical, virtual or lambda

        :return: None
        """

        if resource_type == "PhysicalAlreadyProvisioned":
            self.type = "physical"
        elif resource_type == "Virtual":
            self.type = "virtual"
        elif resource_type == "NativeCloudFunction":
            self.type = "lambda"

    def set_storage_provider_alias(self, storage_provider):
        """
        Sets the storage provider alias of the resource

        :param str storage_provider: either minio or s3
        :return: None
        """

        self.storage_provider = storage_provider
        if self.storage_provider == "minio":
            self.storage_provider_alias = "minio-" + self.name
        elif self.storage_provider == "s3":
            self.storage_provider_alias = "s3.aws"
        return

    def _set_ssh(self, physical_nodes):
        """
        Sets the ssh address of the resource from the physical_nodes.yaml file if the resource is physical, otherwise \
        sets it to None.

        :return: None
        """

        if self.type == "physical":
            #print(self.name, physical_nodes)
            if self.name not in list(physical_nodes.keys()):
                show_fatal_error("Physical node " + self.name + " not found in physical_nodes.yaml")
            self.ssh = physical_nodes[self.name]["ssh"]
        else:
            self.ssh = None
        return None
    
    def _set_minio(self, physical_nodes):

        if self.type == "physical":
            if self.name not in list(physical_nodes.keys()):
                show_fatal_error("Physical node " + self.name + " not found in physical_nodes.yaml")
            self.minio = physical_nodes[self.name]["minio"]
        else:
            self.minio = None
        return None
    
    def _set_oscar(self, physical_nodes):

        if self.type == "physical":
            if self.name not in list(physical_nodes.keys()):
                show_fatal_error("Physical node " + self.name + " not found in physical_nodes.yaml")
            self.oscar = physical_nodes[self.name]["oscar"]
        else:
            self.oscar = None
        return None

    def is_physical(self):
        """:return: True if the resource is physical, False otherwise"""

        return self.type == "physical"

    def is_lambda(self):
        """:return: True if the resource is on a lambda, False otherwise"""

        return self.type == "lambda"
