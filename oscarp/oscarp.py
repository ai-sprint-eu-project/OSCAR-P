# this file calls all methods needed for the whole campaign
# tried to keep it as slim as possible for easier reading (failed miserably)

import os
import shutil

import executables
import global_parameters as gp

from termcolor import colored

from cluster_manager import remove_all_buckets, generate_fdl_configuration, \
    remove_all_services, apply_fdl_configuration_wrapped, clean_s3_buckets, upload_input_files_to_storage, \
    clean_aws_logs
from gui import show_runs
from postprocessing import prepare_runtime_data, plot_runtime_core_graphs, make_runtime_core_csv, save_dataframes
from process_logs import make_csv_table, make_done_file
from retrieve_logs import pull_logs, pull_lambda_logs, get_data_size
from run_manager import move_input_files_to_input_bucket, wait_services_completion, move_input_files_to_s3_bucket
from mllibrary_manager import run_mllibrary
from utils import auto_mkdir, show_warning, delete_directory, get_command_output_wrapped, ensure_slash_end

global runs, run, repetitions, current_run_dir, banner_name


def prepare_clusters():
    """
    Prepares the cluster for the new test by removing the leftover services and bucket, then generating and applying
    the new FDL configuration. It also uploads the input files to the storage bucket on the resource of the first
    service, if the test is asynchronous.

    :return: None
    """

    remove_all_services()
    clean_aws_logs()
    if not gp.is_single_service_test:
        remove_all_buckets()
        clean_s3_buckets()
    generate_fdl_configuration()
    apply_fdl_configuration_wrapped()
    if not gp.is_single_service_test and not gp.is_sync:
        upload_input_files_to_storage()
    return


def start_run_full():
    move_input_files_to_input_bucket()
    wait_services_completion(gp.current_services_list)


def end_run_full():
    pull_logs()
    get_data_size()
    make_done_file(gp.current_run_dir)
    return


def copy_test_single_lambda():
    service = gp.current_services_list[0]

    shutil.copyfile(gp.current_run_dir.replace(service.unit, "Full_workflow") + "time_table_%s.json" % service.name,
                    gp.current_run_dir + "time_table_%s.json" % service.name)

    make_done_file(gp.current_run_dir)
    return


def process_run_results():
    df, adf = prepare_runtime_data(repetitions, runs, gp.current_services_list)
    # make_statistics(campaign_dir, results_dir, subfolder, services)
    plot_runtime_core_graphs(gp.results_dir, gp.run_name, df, adf)
    make_runtime_core_csv(gp.results_dir, gp.run_name, df)

    # no longer needed, the full runtime_core is generated elsewhere and the models are no longer tested
    """
    if get_train_ml_models():
        make_runtime_core_csv_for_ml(results_dir, df, adf, "Interpolation")
        make_runtime_core_csv_for_ml(results_dir, df, adf, "Extrapolation")
    """

    save_dataframes(gp.results_dir, gp.run_name, df, adf)


def main():
    gp.current_run_dir = ensure_slash_end(gp.runs_dir + gp.current_run_id)
    auto_mkdir(gp.current_run_dir)

    global banner_name
    if gp.run_name == "Full_workflow":
        banner_name = "(full workflow)"
    else:
        service_name = gp.current_services_list[0].name
        banner_name = "(" + service_name + ")"

    print(colored("\nStarting %s of %s %s" % (gp.current_run_id, len(gp.scheduled_runs), banner_name), "blue"))

    if gp.is_dry:
        exit()

    # if not clean_buckets and len(run["services"]) == 1 and run["services"][0]["cluster"] == "AWS Lambda":
    if gp.is_single_service_test and gp.has_active_lambdas:
        copy_test_single_lambda()
        return
    else:
        prepare_clusters()
        start_run_full()

    end_run_full()

    return


if __name__ == '__main__':
    main()
