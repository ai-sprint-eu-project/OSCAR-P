# this file includes functions that print out content
import os.path

from termcolor import colored

from utils import append_string_to_file, strip_ansi_from_string, create_new_file

import global_parameters as gp


def runs_diff_services(run_name1, run_name2):
    """
    Given two runs, it shows the difference in the parallelism level for each service.

    :param str run_name1: name of the first run (e.g. "Run #1")
    :param str run_name2: name of the second run
    :return: None
    """

    show_and_save_to_summary("\t\tServices:")

    services1 = gp.scheduled_runs[run_name1]["services"]
    services2 = gp.scheduled_runs[run_name2]["services"]

    units = list(services1.keys())

    for unit in units:
        s1 = services1[unit]
        s2 = services2[unit]

        service_name = gp.containers[unit].parent.name
        service_name = "{:<35}".format(service_name)

        output = ""
        if s1["parallelism"] != s2["parallelism"]:
            output += "parallelism: " \
                      + colored(s1["parallelism"], "green") \
                      + " -> " \
                      + colored(s2["parallelism"], "green")

        if output != "":
            show_and_save_to_summary("\t\t\t" + colored(service_name, "blue") + output)
        else:
            show_and_save_to_summary("\t\t\t" + colored(service_name, "blue") + colored("unchanged", "green"))

    return


def runs_diff_resources(run_name1, run_name2):
    """
    Given two runs, it shows the difference in the number of nodes for each resource.

    :param str run_name1: name of the first run (e.g. "Run #1")
    :param str run_name2: name of the second run
    :return: None
    """

    show_and_save_to_summary("\t\tResources:")

    resources1 = gp.scheduled_runs[run_name1]["resources"]
    resources2 = gp.scheduled_runs[run_name2]["resources"]

    resources = list(resources1.keys())

    for r in resources:
        resource = gp.resources[r]
        if not resource.is_lambda():
            nodes1 = resources1[r]["nodes"]
            nodes2 = resources2[r]["nodes"]

            resource_name = "{:<35}".format(r)

            output = ""
            if nodes1 != nodes2:
                output += "nodes: " + colored(nodes1, "green") + " -> " + colored(nodes2, "green")

            if output != "":
                show_and_save_to_summary("\t\t\t" + colored(resource_name, "blue") + output)
            else:
                show_and_save_to_summary("\t\t\t" + colored(resource_name, "blue") + colored("unchanged", "green"))

    return


def show_all_services(run_index, repetitions):
    """
    For a given run, it shows for each service their cpu, memory, parallelism level and resource; it's called \
     for the first run only.

    :param int run_index: run index
    :param int repetitions: number of repetitions
    :return: None
    """

    start_index = run_index
    if repetitions > 1:
        end_index = run_index + repetitions - 1
        show_and_save_to_summary("\tRun #%s to #%s:" % (start_index, end_index))
    else:
        show_and_save_to_summary("\tRun #%s:" % start_index)

    show_and_save_to_summary("\t\tServices:")

    run_name = "Run #" + str(start_index)
    services = gp.scheduled_runs[run_name]["services"]

    for unit in services:
        s = gp.containers[unit]
        parallelism = services[unit]["parallelism"]
        service_name = "{:<35}".format(s.parent.name)
        show_and_save_to_summary("\t\t\t" + colored(service_name, "blue")
                                 + "cpu: " + colored(s.cpu, "green")
                                 + " , memory: " + colored(s.memory, "green") + " mb"
                                 + " , parallelism: " + colored(parallelism, "green")
                                 + " , cluster: " + colored(s.resource, "green"))

    return


def show_all_resources(run_index):
    """
    For a given run, it shows for each resource the required number of nodes; it's called for the first run only.

    :param int run_index: run index
    :return: None
    """

    show_and_save_to_summary("\t\tResources:")
    run_name = "Run #" + str(run_index)
    resources = gp.scheduled_runs[run_name]["resources"]

    for r in resources:
        nodes = resources[r]["nodes"]
        if not gp.resources[r].is_lambda():
            resource_name = "{:<35}".format(r)
            show_and_save_to_summary("\t\t\t" + colored(resource_name, "blue") + "nodes: "
                                     + colored(str(nodes), "green"))

    return


def show_runs():
    """
    It combines the previous functions to show all the scheduled runs.

    :return: None
    """

    repetitions = gp.run_parameters["run"]["repetitions"]
    show_and_save_to_summary("\nScheduler:")
    show_all_services(run_index=1, repetitions=repetitions)
    show_all_resources(run_index=1)
    show_and_save_to_summary("")

    for i in range(1*repetitions, len(gp.scheduled_runs), repetitions):
        if repetitions > 1:
            run_name = "Run #%s to #%s:" % (i + 1, i + repetitions)
        else:
            run_name = "Run #%s:" % (i + 1)

        show_and_save_to_summary("\t" + run_name)

        runs_diff_services("Run #" + str(i), "Run #" + str(i + 1))
        runs_diff_resources("Run #" + str(i), "Run #" + str(i + 1))
        show_and_save_to_summary("")

    # todo re-enable this after testing!
    # value = get_valid_input("Do you want to proceed? (y/n)\t", ["y", "n"])
    print()  # just for spacing
    value = "y"

    if value == "n":
        print(colored("Exiting...", "red"))
        quit()

    return


def show_workflow():  # todo this should be moved to GUI
    """
    From the list of the current services, it prints the workflow.

    :return: None
    """

    first_service = gp.current_services_list[0]
    first_provider = first_service.storage_provider_input
    storage_bucket = gp.run_parameters["input_files"]["storage_bucket"]

    summary_filepath = os.path.join(gp.current_deployment_dir, "campaign_summary.txt")
    create_new_file(summary_filepath)

    print()
    show_and_save_to_summary("Workflow:\n\t%s/%s -> %s/%s" % (first_provider, storage_bucket,
                                                                first_provider, first_service.input_bucket))

    for s in gp.current_services_list:
        input_bucket = s.storage_provider_input + "/" + s.input_bucket  # .split('/')[-1]
        output_bucket = s.storage_provider_output + "/" + s.output_bucket  # .split('/')[-1]
        show_and_save_to_summary("\t" + colored(input_bucket) + " -> |" + colored(s.name, "blue") + "| -> " + colored(output_bucket))

    show_and_save_to_summary("")
    return


def show_and_save_to_summary(string):
    """
    Receives a line, prints it and then appends it to the campaign summary.

    :param str string: Output line
    :return: None
    """
    print(string)
    append_to_deployment_summary(strip_ansi_from_string(string))
    return


def append_to_deployment_summary(string):
    """
    Receives a line and appends it to the summary.

    :param str string: Output line, stripped of ANSI
    :return: None
    """

    summary_filepath = os.path.join(gp.current_deployment_dir, "campaign_summary.txt")
    append_string_to_file(string, summary_filepath)
    return
