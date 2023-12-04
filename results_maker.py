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

import os
import json

import pandas as pd
import plotly.express as px
import plotly.graph_objs as go

from datetime import datetime, timedelta

from termcolor import colored

import global_parameters as gp
from classes.Component import get_alternative_containers
from classes.Service import Service
from oscarp.utils import auto_mkdir

global runs_folder, results_folder, graphs_folder, dataframes_folder


def make_results():
    """Main function that takes care of generating the final results for a deployment"""

    make_results_for_full()

    # if single service testing is set
    if gp.is_single_service_test:
        for unit in gp.current_deployment:
            make_results_for_unit(unit)
            make_results_for_alternatives(unit)

    return


def make_results_for_alternatives(unit):
    service = gp.current_services_dict[unit]

    for alternative_unit in get_alternative_containers(unit):
        name = gp.containers[alternative_unit].parent.name
        bucket_index = service.input_bucket_index
        gp.current_services_dict[alternative_unit] = Service(alternative_unit, name, bucket_index)
        make_results_for_unit(alternative_unit)

    return


def make_dataframe_sync(unit):
    """
    Makes a dataframe of the average response time for a given unit
    The dataframe contains the following: requested throughput, observed throughput, average response time, \
     requested parallelism, warm pods, cores, warm cores
    """

    service = gp.current_services_dict[unit]

    dataframes_list = []
    for run_name in sorted(os.listdir(runs_folder)):
        fix_time_table_interval(run_name, service.name)
        df = make_dataframe_sync_run(run_name, service)
        dataframes_list.append(df)

    df = pd.concat(dataframes_list, ignore_index=True)
    df.to_csv(dataframes_folder + service.name + "_response_time_dataframe.csv", index=False)
    return


def fix_time_table_interval(run_name, service_name):
    """If the timetable doesn't contain the intervals (happens for services after the first one that aren't tested \
    directly with Jmeter), they are added by this function (approximated)"""

    json_path = runs_folder + ("%s/time_table_%s.json" % (run_name, service_name))

    with open(json_path) as file:
        time_table = json.load(file)

    # if "interval" in list(time_table.values())[0]:
    #    return

    date_format = "%Y-%m-%d %H:%M:%S"
    first_job_create = get_first_job(time_table)
    interval_start = datetime.strptime(first_job_create, date_format)

    intervals = gp.run_parameters["synchronous"]["intervals"]
    for i in range(len(intervals)):
        interval = intervals[i]
        interval_index = i + 1

        duration = interval["duration_seconds"]
        interval_end = interval_start + timedelta(seconds=duration)

        for job_name in time_table:
            job = time_table[job_name]
            job_create = job["job_create"]
            job_create = datetime.strptime(job_create, date_format)

            if job_create < interval_end and "interval" not in job.keys():
                job["interval"] = str(interval_index)

        interval_start = interval_end

    for job_name in time_table:
        job = time_table[job_name]

        if "interval" not in job.keys():
            job["interval"] = str(interval_index)

    with open(json_path, "w") as file:
        json.dump(time_table, file, indent=4, sort_keys=False, default=str)

    return


def make_dataframe_sync_run(run_name, service):
    """
    Makes and returns a dataframe of the average response time for a given service and run
    """

    response_times = {}
    real_throughput = {}

    # prepare dict, keys are intervals, values are array of response times
    for i in range(1, len(gp.run_parameters["synchronous"]["intervals"]) + 1):
        response_times[i] = []

    json_path = runs_folder + ("%s/time_table_%s.json" % (run_name, service.name))

    with open(json_path) as file:
        time_table = json.load(file)

    # for each job calculate response time and adds it in the right array
    for job in time_table.values():
        interval = int(job["interval"])

        date_format = "%Y-%m-%d %H:%M:%S"

        t1 = datetime.strptime(job["job_create"], date_format)
        t2 = datetime.strptime(job["job_finish"], date_format)
        delta = (t2 - t1).total_seconds()

        response_times[interval].append(delta)

        if interval not in real_throughput:
            real_throughput[interval] = {
                "start": t1,
                "end": t2,
                "count": 1
            }
        else:
            if t1 < real_throughput[interval]["start"]:
                real_throughput[interval]["start"] = t1
            if t2 > real_throughput[interval]["end"]:
                real_throughput[interval]["end"] = t2
            real_throughput[interval]["count"] += 1
    
    # makes a list with the requested throughput values
    requested_throughput_list = []
    for interval in gp.run_parameters["synchronous"]["intervals"]:
        requested_throughput_list.append(round(interval["throughput"] / 60, 2))

    intervals = list(response_times.keys())
    intervals.sort()

    # calculate the actual throughput
    observed_throughput_list = []
    for interval in intervals:
        t1 = real_throughput[interval]["start"]
        t2 = real_throughput[interval]["end"]
        delta = (t2 - t1).total_seconds()
        count = real_throughput[interval]["count"]
        observed_throughput_value = round(count / delta, 2)
        observed_throughput_list.append(observed_throughput_value)

    # calculate average response time for each interval
    avg_response_times_list = []

    for interval in intervals:
        average = 0
        response_times_array = response_times[interval]
        for response_time in response_times_array:
            average += response_time
        average /= len(response_times_array)
        average = round(average, 2)
        avg_response_times_list.append(average)
    
    # fill remaining columns
    number_of_intervals = len(gp.run_parameters["synchronous"]["intervals"])
    warm_pods = gp.run_parameters["synchronous"]["number_of_pre_allocated_pods"]
    parallelism = gp.current_services_dict[service.unit].parallelism[0]
    cpu_per_container = service.cpu
    cores = parallelism * cpu_per_container
    warm_cores = warm_pods * cpu_per_container

    parallelism_list = [parallelism] * number_of_intervals
    warm_pods_list = [warm_pods] * number_of_intervals
    cores_list = [cores] * number_of_intervals
    warm_cores_list = [warm_cores] * number_of_intervals
    
    # generate dataframe
    df = pd.DataFrame(dict(requested_throughput=requested_throughput_list, 
                           observed_throughput=observed_throughput_list, 
                           avg_response_time=avg_response_times_list, 
                           requested_parallelism=parallelism_list, 
                           warm_pods=warm_pods_list, 
                           cores=cores_list, 
                           warm_cores=warm_cores_list))

    return df


def make_dataframe_async(unit):
    """
    Generates and saves to file the dataframe of all the runs for a given unit, with the following fields: \
    observed_throughput, avg_response_time, requested_parallelism, cores
    """

    service = gp.current_services_dict[unit]
    dataframes_list = []
    for run_name in gp.scheduled_runs.keys():
        df = make_dataframe_async_run(run_name, service)
        dataframes_list.append(df)

    df = pd.concat(dataframes_list, ignore_index=True)
    df.to_csv(dataframes_folder + service.name + "_response_time_dataframe.csv", index=False)
    return


def make_dataframe_async_run(run_name, service):
    """Makes and returns a dataframe of the average response time for a given service and run"""

    # service_name = service.name.replace("_", "-")  # todo temporary
    service_name = service.name
    json_path = runs_folder + ("%s/time_table_%s.json" % (run_name, service_name))

    with open(json_path) as file:
        time_table = json.load(file)

    # calculate observed throughput
    date_format = "%Y-%m-%d %H:%M:%S"

    t1 = get_first_job(time_table)
    t2 = get_last_job(time_table)

    if service.is_lambda:
        t1 = t1.split(".")[0]
        t2 = t2.split(".")[0]

    t1 = datetime.strptime(t1, date_format)
    t2 = datetime.strptime(t2, date_format)

    delta = (t2 - t1).total_seconds()
    count = len(time_table)
    observed_throughput = round(count / delta, 2)

    # calculate average response time of all jobs
    average = 0
    for job in time_table.values():
        average += get_runtime_of_job(job)

    average /= count
    avg_response_time = round(average, 2)

    unit = service.unit

    # if alternate, read parallelism from main component
    if "A" in unit.split("@")[0]:
        a, b = unit.split("@")
        a = a.split("A")[0]
        unit = a + "@" + b

    # fill remaining values
    parallelism = gp.scheduled_runs[run_name]["services"][unit]["parallelism"]

    # todo add configurations

    # generate dataframe
    df = pd.DataFrame(dict(run_name=[run_name],
                           observed_throughput=[observed_throughput],
                           avg_response_time=[avg_response_time],
                           requested_parallelism=[parallelism],
                           cores=[parallelism * service.cpu],
                           ))
    return df


def make_results_for_unit(unit):  # todo what about lambdas?
    """Main function to generates the result for service (in the case of single service testing)"""
    global runs_folder, results_folder, graphs_folder, dataframes_folder

    print()
    print(colored("Making results for %s" % unit, "blue"))

    set_up_results_folder(unit)

    if os.path.exists(results_folder + "done"):
        print("Results exist, skipping...")
        return

    if gp.is_sync:
        make_dataframe_sync(unit)
        generate_response_throughput_graphs(unit)
    else:
        make_dataframe_async(unit)

    df = ready_dataframes_of_component(unit)
    make_loads(unit)
    make_gantts(unit)
    make_runtime_runs_parallelism_graph(df)

    with open(results_folder + "done", "w") as file:
        file.write("")

    print(colored("Done!", "green"))
    return


def make_results_for_full():
    """Main function to generates the result for the full workflow, for both sync and async testing"""
    print()
    print(colored("Making results for full workflow", "blue"))

    set_up_results_folder("Full_workflow")

    if os.path.exists(results_folder + "done"):
        print("Results exist, skipping...")
        return

    for unit in gp.current_deployment:
        if gp.is_sync:
            make_dataframe_sync(unit)
            generate_response_throughput_graphs(unit)
        else:
            make_dataframe_async(unit)

        make_gantts(unit)

    df = ready_dataframes_of_full_workflow()

    # df = pd.read_csv(dataframes_folder + "runtime_dataframe.csv")

    make_runtime_runs_parallelism_graph_full(df)

    with open(results_folder + "done", "w") as file:
        file.write("")

    print(colored("Done!", "green"))
    return


def set_up_results_folder(parent_directory):
    """Sets up the results folder given a certain parent directory, """
    global runs_folder, results_folder, graphs_folder, dataframes_folder

    runs_folder = "%s%s/runs/" % (gp.current_deployment_dir, parent_directory)
    results_folder = "%s%s/results/" % (gp.current_deployment_dir, parent_directory)
    auto_mkdir(results_folder)

    graphs_folder = results_folder + "Graphs/"
    auto_mkdir(graphs_folder)
    dataframes_folder = results_folder + "Dataframes/"
    auto_mkdir(dataframes_folder)
    return


"""
def make_results_for_jmeter():
    if not gp.is_sync:
        return

    global runs_folder, results_folder

    first_unit = gp.current_deployment[0]
    first_component = gp.containers[first_unit].parent

    # single services

    runs_folder = gp.current_deployment_dir + first_unit + "/" + "runs/"
    results_folder = gp.current_deployment_dir + first_unit + "/" + "results/"

    runs_list = os.listdir(runs_folder)

    for run_name in runs_list:
        generate_throughput_graph(run_name, first_component)

    # full workflow

    runs_folder = gp.current_deployment_dir + "Full_workflow/runs/"
    results_folder = gp.current_deployment_dir + "Full_workflow/results/"

    runs_list = os.listdir(runs_folder)

    for run_name in runs_list:
        generate_throughput_graph(run_name, first_component)

    return
"""


def generate_response_throughput_graphs(unit):
    """Generates the graphs of the average response time against the throughput for a given unit"""

    service = gp.current_services_dict[unit]
    df = pd.read_csv(dataframes_folder + service.name + "_response_time_dataframe.csv")

    # generate graphs
    fig = px.scatter(df, x="observed_throughput", y="avg_response_time",
                     color="cores", template="simple_white",
                     labels={"avg_response_time": "Average response time (seconds)",
                             "observed_throughput": "Observed throughput (req/sec)",
                             "cores": "Cores"})

    for c in list(df["cores"].unique()):
        df_c = df[df["cores"] == c]
        adf = df_c.groupby(["cores", "requested_throughput"], sort=False).mean().reset_index()

        fig.add_trace(go.Scatter(x=adf["observed_throughput"],
                                 y=adf["avg_response_time"],
                                 mode="lines", showlegend=False))

    fig.write_image(results_folder + "Graphs/%s_real_throughput_avg_response.png" % service.name)

    fig = px.scatter(df, x="requested_throughput", y="observed_throughput",
                     color="cores", template="simple_white",
                     labels={"requested_throughput": "Requested throughput (req/sec)",
                             "observed_throughput": "Observed throughput (req/sec)",
                             "cores": "Cores"})

    fig.update_layout(showlegend=False)

    min_range = min(list(df["requested_throughput"])[0], list(df["observed_throughput"])[0])
    min_range -= 1
    min_range = round(min_range)

    max_range = max(list(df["requested_throughput"])[-1], list(df["observed_throughput"])[-1])
    max_range += 1
    max_range = round(max_range)

    fig.add_trace(go.Scatter(x=[min_range, max_range], y=[min_range, max_range], mode='lines',
                             line=dict(color="black"), name="Requested throughput"))

    fig.update_xaxes(range=[min_range, max_range])
    fig.update_yaxes(range=[min_range, max_range])

    fig.write_image(results_folder + "Graphs/%s_real_expected_throughput.png" % service.name)
    return


def ready_dataframes_of_component(unit):
    """Makes the runtime dataframe for a certain service"""

    service = gp.current_services_dict[unit]

    repetitions = gp.run_parameters["run"]["repetitions"]

    configurations_list = ["Configuration #%s" % i
                           for i in range(1, len(service.parallelism) + 1)
                           for j in range(repetitions)]

    target_parallelism_list = [p for p in service.parallelism for i in range(repetitions)]
    run_list = ["Run #%s" % i for i in range(1, repetitions + 1)] * len(service.parallelism)

    cores = []
    for p in service.parallelism:
        for r in range(repetitions):
            cores.append(p * service.cpu)

    runtime_list = []
    actual_parallelism_list = []
    for run_name in gp.scheduled_runs.keys():
        runtime_list.append(get_run_runtime(run_name, service.name))
        actual_parallelism_list.append(find_actual_parallelism_run(run_name, service.name))

    df = pd.DataFrame(dict(runs=run_list, configurations=configurations_list,
                           runtime=runtime_list,
                           actual_parallelism=actual_parallelism_list,
                           target_parallelism=target_parallelism_list,
                           cores=cores))

    df.to_csv(dataframes_folder + "runtime_dataframe.csv", index=False)

    return df


def ready_dataframes_of_full_workflow():
    """Makes the runtime dataframe for the full workflow"""

    total_cores = []

    for run in gp.scheduled_runs.values():
        services = run["services"]
        total_cores.append(0)
        for unit in services:
            total_cores[-1] += services[unit]["parallelism"] * gp.current_services_dict[unit].cpu

    repetitions = gp.run_parameters["run"]["repetitions"]
    parallelism = gp.current_services_list[0].parallelism

    configurations_list = ["Configuration #%s" % i
                           for i in range(1, len(parallelism) + 1)
                           for j in range(repetitions)]

    run_list = ["Run #%s" % i for i in range(1, repetitions + 1)] * len(parallelism)

    runtime_list = []
    for run_name in gp.scheduled_runs.keys():
        runtime_list.append(get_run_runtime_full(run_name))

    df = pd.DataFrame(dict(runs=run_list, runtime=runtime_list,
                           configurations=configurations_list, total_cores=total_cores))

    df.to_csv(dataframes_folder + "runtime_dataframe.csv", index=False)

    return df


def make_loads(unit):
    service = gp.current_services_dict[unit]

    load_directory = graphs_folder + "Loads/"
    auto_mkdir(load_directory)

    for run_name in os.listdir(runs_folder):
        df = get_actual_parallelism_list(run_name, service.name)

        fig = px.line(df, x="Marker", y="Load", template="simple_white",
                      labels={"Load": "Parallel Instances", "Marker": "Timestamp"})
        fig.write_image(load_directory + service.name + "_" + run_name + ".png")

    return


def make_runtime_runs_parallelism_graph(df):
    """Generates the runtime against runs graph, while also showin for each run the actual achieved parallelism"""

    adf = df.groupby("configurations", as_index=False, sort=False).mean()

    fig = px.scatter(df, x="cores", y="runtime", color="actual_parallelism", template="simple_white",
                     labels={"runtime": "Runtime (seconds)", "runs": "Runs",
                             "actual_parallelism": "Actual parallelism"})
    fig.add_trace(go.Scatter(x=adf["cores"], y=adf["runtime"], mode="lines", showlegend=False))

    fig.write_image(graphs_folder + "runtime_runs_parallelism.png")
    return


def make_runtime_runs_parallelism_graph_full(df):
    """Generates the runtime against runs graph for the full workflow"""

    adf = df.groupby("configurations", as_index=False, sort=False).mean()

    fig = px.scatter(df, x="total_cores", y="runtime", color="runs", template="simple_white",
                     labels={"runtime": "Runtime (seconds)", "runs": "Runs",
                             "configurations": "Configurations",
                             "total_cores": "Total cores"})
    fig.add_trace(go.Scatter(x=adf["total_cores"], y=adf["runtime"], mode="lines", showlegend=False))

    fig.write_image(graphs_folder + "runtime_runs_parallelism.png")
    return


def make_gantts(unit):
    """Generates the gantts charts for a given unit, makes a small and a 4K version"""

    service = gp.current_services_dict[unit]
    df_list = ready_data_for_gantt(service)
    gantt_directory = results_folder + "Graphs/Gantts/"
    auto_mkdir(gantt_directory)

    df_list = zip(df_list, os.listdir(runs_folder))

    for df, run_name in df_list:
        df = df.sort_values(by="Start", ascending=True)

        fig = px.timeline(df, x_start="Start", x_end="Finish", y="Job", color="Tag", template="simple_white")
        fig.update_yaxes(autorange="reversed")
        fig.write_image(gantt_directory + service.name + "_" + run_name + ".png")

        fig.update_layout(
            autosize=False,
            width=3840,
            height=2160)
        fig.write_image(gantt_directory + service.name + "_" + run_name + "_big.png")

    return


# Secondary functions #
def get_first_job(timelist):
    """Returns the creation time of the first job in a time table"""

    start_list = []

    for k in timelist.keys():
        start_list.append(timelist[k]["job_create"])

    first = start_list[0]

    for s in start_list:
        if s < first:
            first = s
    return first


def get_last_job(timelist):
    """Returns the finish time of the last job in a time table"""

    finish_list = []

    for k in timelist.keys():
        finish_list.append(timelist[k]["job_finish"])

    last = finish_list[0]

    for f in finish_list:
        if f > last:
            last = f
    return last


def get_run_runtime(run_name, service_name):
    """Returns the runtime of a given run for a certain service"""

    service_name = service_name.replace("_", "-")  # todo temporary
    json_path = runs_folder + ("%s/time_table_%s.json" % (run_name, service_name))

    with open(json_path) as file:
        time_table = json.load(file)

    date_format = "%Y-%m-%d %H:%M:%S"

    t1 = datetime.strptime(get_first_job(time_table), date_format)
    t2 = datetime.strptime(get_last_job(time_table), date_format)

    delta = (t2 - t1).total_seconds()
    return delta


def get_run_runtime_full(run_name):
    """Returns the runtime of a given run for the full workflow"""

    first_service = gp.current_services_list[0]
    first_service_name = first_service.name.replace("_", "-")  # todo temporary

    json_path = runs_folder + ("%s/time_table_%s.json" % (run_name, first_service_name))

    with open(json_path) as file:
        time_table = json.load(file)

    start_time = get_first_job(time_table)

    last_service = gp.current_services_list[-1]
    last_service_name = last_service.name.replace("_", "-")  # todo temporary

    json_path = runs_folder + ("%s/time_table_%s.json" % (run_name, last_service_name))

    with open(json_path) as file:
        time_table = json.load(file)

    end_time = get_last_job(time_table)
    end_time = end_time.split(".")[0]  # todo temp last service may be a lambda, but this will be done in postprocessing

    date_format = "%Y-%m-%d %H:%M:%S"

    t1 = datetime.strptime(start_time, date_format)
    t2 = datetime.strptime(end_time, date_format)



    delta = (t2 - t1).total_seconds()
    return delta


def get_actual_parallelism_list(run_name, service_name):
    """Returns a dataframe showcasing the load of a certain service in a specific run, by calculating the actual \
     number of jobs running at the same time (the actual parallelism)"""

    service_name = service_name.replace("_", "-")  # todo temporary
    json_path = runs_folder + ("%s/time_table_%s.json" % (run_name, service_name))
    with open(json_path) as file:
        time_table = json.load(file)

    intervals_markers = []

    for job_name in time_table.keys():
        job = time_table[job_name]

        if "job_start" in job.keys():
            job_start = job["job_start"]
        else:
            job_start = job["job_create"]

        intervals_markers.append((job_start, "start"))
        intervals_markers.append((job["job_finish"], "end"))

    ordered_markers = sorted(intervals_markers)

    parallelism_counter = 0
    parallelism_counter_list = [0]
    plain_markers = [str(datetime.strptime(ordered_markers[0][0], '%Y-%m-%d %H:%M:%S') - timedelta(seconds=10))]

    for i in range(len(ordered_markers)):
        marker_type = ordered_markers[i][1]
        if marker_type == "start":
            parallelism_counter += 1
        elif marker_type == "end":
            parallelism_counter -= 1
        parallelism_counter_list.append(parallelism_counter)
        plain_markers.append(ordered_markers[i][0])

    data = dict(Load=parallelism_counter_list, Marker=plain_markers)
    return pd.DataFrame(data)


def find_actual_parallelism_run(run_name, service_name):
    """Returns the maximum actual parallelism achieved in a run for a certain service"""

    return max(get_actual_parallelism_list(run_name, service_name)["Load"])


"""
def remove_outliers_iqr(df):
    q1 = df.quantile(0.25)
    q3 = df.quantile(0.75)

    iqr = q3 - q1

    not_outliers = df[~((df < (q1 - 1.5 * iqr)) | (df > (q3 + 1.5 * iqr)))]

    cleaned_df = not_outliers.dropna().reset_index()

    return cleaned_df
"""


def get_runtime_of_job(job):
    """Returns the runtime of a certain job"""

    start_time = job["job_create"].split('.')[0]
    end_time = job["job_finish"].split('.')[0]

    date_format = "%Y-%m-%d %H:%M:%S"

    t1 = datetime.strptime(start_time, date_format)
    t2 = datetime.strptime(end_time, date_format)
    delta = (t2 - t1).total_seconds()
    return delta


def ready_data_for_gantt(service):
    """Returns a list of dataframes, each containing the data formatted for the gantt chart of a certain run"""

    dataframe_list = []

    for run_name in os.listdir(runs_folder):
        # service_name = service.name.replace("_", "-")  # todo temporary
        json_path = runs_folder + ("%s/time_table_%s.json" % (run_name, service.name))

        with open(json_path) as file:
            time_table = json.load(file)

        jobs_list = []
        for job_name in time_table.keys():
            job = time_table[job_name]

            if "node" not in job.keys():
                jobs_list.append(dict(Job=job_name[:5], Tag="Job",
                                      Start=job["job_create"], Finish=job["job_finish"]))
            else:
                jobs_list.append(dict(Job=job_name[:5], Tag="Wait",
                                      Start=job["job_create"], Finish=job["pod_create"]))

                jobs_list.append(dict(Job=job_name[:5], Tag="Pod creation",
                                      Start=job["pod_create"], Finish=job["job_start"]))

                jobs_list.append(dict(Job=job_name[:5], Tag="Overhead",
                                      Start=job["job_start"], Finish=job["bash_script_start"]))

                jobs_list.append(dict(Job=job_name[:5], Tag="Compute",
                                      Start=job["bash_script_start"], Finish=job["bash_script_end"]))

                jobs_list.append(dict(Job=job_name[:5], Tag="Write back",
                                      Start=job["bash_script_end"], Finish=job["job_finish"]))

        dataframe_list.append(pd.DataFrame(jobs_list))

    return dataframe_list


def ready_data_for_histogram(component, number_of_runs):
    all_runtimes = []
    runs = []
    parallelism = []

    for run_letter in sorted(os.listdir(component[0])):
        for i in range(1, number_of_runs + 1):
            runs_folder = component[0]
            run_name = ("Run #%s" % i)
            p = find_actual_parallelism_run(component, i, run_letter)
            json_path = runs_folder + ("/%s/%s/time_table_%s.json" % (run_letter, run_name, component[1]))

            with open(json_path) as file:
                time_table = json.load(file)

            for job_name in time_table.keys():
                job = time_table[job_name]
                all_runtimes.append(get_runtime_of_job(job))
                runs.append("Run #%s%s" % (run_letter, i))
                parallelism.append(p)

    data = dict(Runtime=all_runtimes, Run=runs, Parallelism=parallelism)
    return pd.DataFrame(data)
