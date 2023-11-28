import os

import yaml
import copy
import random

from datetime import date

from termcolor import colored

import global_parameters as gp
from classes.Component import generalize_unit_id
from classes.Service import Service
from oscarp.utils import read_json, show_fatal_error, write_json


def make_current_services():
    """
    transforms the unit into sequential services, by adding aptly named buckets and other useful info
    """

    gp.current_services_list = []
    gp.current_services_dict = {}

    i = 0

    for unit in gp.current_deployment:  # single components in deployments

        container = gp.containers[generalize_unit_id(unit)]
        name = container.parent.name

        current_service = Service(unit, name, i)

        gp.has_lambdas = current_service.is_lambda

        gp.current_services_list.append(current_service)
        gp.current_services_dict[unit] = current_service

        i += 1

    # now needs to cycle over the services and connect the buckets in the right way between OSCAR and lambdas

    # lambdas needs also the previous service
    for i in range(1, len(gp.current_services_list)):
        current_service = gp.current_services_list[i]
        previous_service = gp.current_services_list[i - 1]

        current_service.connect_to_previous_service(previous_service)

    # oscar services needs to know only the next service
    for i in range(len(gp.current_services_list) - 1):
        current_service = gp.current_services_list[i]
        next_service = gp.current_services_list[i + 1]

        current_service.connect_to_next_service(next_service)

    return


def run_scheduler():
    """Comment!"""
    repetitions = gp.run_parameters["run"]["repetitions"]

    # create empty skeletons for runs
    run_names = ["Run #%s" % (i + 1) for i in range(gp.base_length * repetitions)]
    gp.scheduled_runs = dict.fromkeys(run_names, None)
    for key in gp.scheduled_runs:
        gp.scheduled_runs[key] = {"services": {}, "resources": {}}

    # add in services
    for service in gp.current_services_list:
        expanded_parallelism = [item for item in service.parallelism for i in range(repetitions)]

        for index, element in enumerate(expanded_parallelism):
            run_name = "Run #%s" % (index + 1)
            gp.scheduled_runs[run_name]["services"][service.unit] = {"parallelism": element}

    # add in resources
    for key, value in gp.resources_node_requirements.items():
        expanded_nodes = [item for item in value for i in range(repetitions)]

        for index, element in enumerate(expanded_nodes):
            run_name = "Run #%s" % (index + 1)
            gp.scheduled_runs[run_name]["resources"][key] = {"nodes": element}

    # print("\nRuns")
    # print(gp.scheduled_runs)
    return


def is_run_already_done(run):
    """
    Checks if a run is already done and matches the current run.
    This is called for the full workflow, and checked for its services as well; if a service is incomplete, redo all.
    Once the first incomplete run is found, sets a flag and overwrites from there on
    """

    if gp.overwrite_runs:
        return False

    if os.path.exists(gp.runs_dir + gp.current_run_id + "/done"):
        run_configuration = read_json(gp.runs_dir + gp.current_run_id + "/run_configuration.json")

        if run != run_configuration:
            show_fatal_error("Run configurations mismatch, you may be running in the wrong campaign")
        else:
            print("%s (Full workflow) exists, skipping..." % gp.current_run_id)

            if not gp.run_parameters["run"]["test_single_services"]:
                return True
            for unit in run["services"].keys():
                if not _is_run_already_done_service(unit):
                    gp.overwrite_runs = True
                    return False

            return True

    gp.overwrite_runs = True
    return False


def _is_run_already_done_service(unit):

    if os.path.exists(gp.runs_dir.replace("Full_workflow", unit) + gp.current_run_id + "/done"):

        print("%s (%s) exists, skipping..." % (gp.current_run_id, unit))
        return True

    print(colored("%s (%s) is missing or incomplete, repeating %s from scratch..."
                  % (gp.current_run_id, unit, gp.current_run_id), "yellow"))
    return False