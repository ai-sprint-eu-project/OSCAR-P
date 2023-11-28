import copy
import os
import time

import requests
from termcolor import colored

from infrastructure_manager import create_virtual_infrastructures, adjust_physical_infrastructures_configuration, \
    update_virtual_infrastructures, delete_all_virtual_infrastructures, delete_unused_virtual_infrastructures, \
    get_outputs, configure_jmeter_cluster, deploy_all_needed_resources
from input_files_parser import get_resources, get_run_parameters, get_components, set_testing_parameters
from deployment_generator import get_testing_units, get_deployments, reorder_deployments, \
    make_deployments_summary, make_resources_requirements, get_services_to_test
from lambda_manager import setup_scar, remove_all_lambdas
from oscarp.mllibrary_manager import run_mllibrary
from results_maker import make_results
from run_coordinator import make_current_services, run_scheduler, is_run_already_done
from oscarp.utils import auto_mkdir, show_fatal_error, show_warning, get_command_output_wrapped, write_json
from oscarp.gui import show_runs, show_workflow


import oscarp.oscarp as oscarp
import global_parameters as gp


def main(input_dir, is_dry, is_debug, is_development=False):

    try:
        gp.is_debug = is_debug
        gp.is_dry = is_dry
        gp.is_development = is_development
        gp.set_application_dir(input_dir)

        if gp.is_development:
            oscarp.executables.init("oscarp/executables/")
        else:
            oscarp.executables.init("/bin/oscarp_executables/")
        
        # get the necessary info from the different input file
        get_resources()  # uses common_config/candidate_resources.yaml
        
        get_run_parameters()  # uses oscarp/run_parameters
   
        get_components()  # uses common_config/candidate_deployments.yaml
        
        set_testing_parameters()  # adds the parallelism field to the components
        
        # create list of deployments, rearrange them as necessary
        get_deployments()
        # deployments = reorder_deployments(deployments, resources)  # todo fix or remove
        
        # set the stage for the campaign
        gp.make_campaign_dir()
        make_deployments_summary()

        gp.is_first_launch = True  # todo rename it, this is used by the GUI to print the summary

        if gp.run_parameters["other"]["clean_infrastructures_before_testing"]:
            delete_all_virtual_infrastructures()

        # # # # # # # # # # #
        # DEPLOYMENTS LOOP  #
        # # # # # # # # # # #

        for deployment_index in range(0, len(gp.deployments)):

            # deployment_index = 1

            print("\nTesting deployment_" + str(deployment_index) + ":")

            gp.set_current_deployment(deployment_index)
            make_resources_requirements()  # makes list of resources in use and their requirements

            # print("Cluster requirements: ", gp.resources_node_requirements)  # todo keep this, and improve it

            gp.run_parameters["run"]["main_dir"] = gp.application_dir
            gp.run_parameters["run"]["campaign_dir"] = gp.campaign_dir
            gp.run_parameters["run"]["run_name"] = "deployment_" + str(deployment_index)

            make_current_services()

            """
            print("\nServices")
            for service in gp.current_services_list:
                if service.is_lambda:
                    gp.has_active_lambdas = True
                    gp.has_lambdas = True
                print("\t ", service)
            """

            run_scheduler()
            show_workflow()
            # show_runs()

            gp.resources_deployed = False

            # # # # # # #
            # RUNS LOOP #
            # # # # # # #

            indexed_runs = list(enumerate(gp.scheduled_runs.values()))

            # entry index: index of the list, from 0; run index: index of the run, from 1
            for entry_index, run in indexed_runs:

                print()
                gp.set_current_work_dir("Full_workflow")
                gp.current_run_index = entry_index + 1
                gp.current_run_id = "Run #%s" % (entry_index + 1)
                gp.has_active_lambdas = gp.has_lambdas

                gp.is_single_service_test = False
                auto_mkdir(gp.runs_dir)

                if not is_run_already_done(run):
                    auto_mkdir(gp.runs_dir + gp.current_run_id)

                    # if the resources are deployed at this stage, the correct configurations is ensured
                    if not gp.resources_deployed:
                        deploy_all_needed_resources()

                    # if the resources were already up and their requirements changed from the previous run, update them
                    elif entry_index != 0:  # never update on the first run
                        prev_run = indexed_runs[entry_index - 1][1]
                        if run["resources"] != prev_run["resources"]:
                            # adjust_physical_infrastructures_configuration()
                            update_virtual_infrastructures(run["resources"])

                    oscarp.main()
                    write_json(gp.runs_dir + gp.current_run_id + "/run_configuration.json", run)

                # # # # # # # # #
                # SERVICES LOOP #
                # # # # # # # # #

                if gp.run_parameters["run"]["test_single_services"]:
                    current_services_backup = gp.current_services_list
                    services_to_test = get_services_to_test()

                    for service in services_to_test:
                        gp.set_current_work_dir(service.unit)

                        service.set_buckets_single_testing()

                        gp.current_services_list = [service]
                        gp.is_single_service_test = True
                        auto_mkdir(gp.runs_dir)

                        gp.has_active_lambdas = service.is_lambda

                        if gp.overwrite_runs:
                            oscarp.main()
                        service.set_buckets_full_workflow()

                    gp.current_services_list = current_services_backup

            # at the end of the deployment testing, generate dataframes
            make_results()

        if gp.run_parameters["other"]["clean_infrastructures_after_testing"]:
            delete_all_virtual_infrastructures()

        if gp.run_parameters["run"]["train_models"]:
            run_mllibrary()
            
    except:
        if gp.run_parameters["other"]["clean_infrastructures_if_crash"]:
            delete_all_virtual_infrastructures()

if __name__ == '__main__':
    main("popnas_compss_degraded_performance", True, True, False)
    #main("oscarp/recipe-transcriber", False, False, False)
