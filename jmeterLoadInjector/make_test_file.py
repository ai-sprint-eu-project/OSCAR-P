from termcolor import colored

def get_start():
    with open("jmeter_blocks/1_start.xml", "r") as file:
        lines = file.readlines()

    return lines


def set_generic_variables(cluster_endpoint, oscar_service, token, connect_timeout_seconds, request_timeout_seconds):
    with open("jmeter_blocks/2_generic_variables.xml", "r") as file:
        lines = file.readlines()

    connect_timeout = int(connect_timeout_seconds) * 1000
    request_timeout = int(request_timeout_seconds) * 1000

    line = lines[4]
    lines[4] = line.replace("x_replace_x", cluster_endpoint)

    line = lines[9]
    lines[9] = line.replace("x_replace_x", oscar_service)

    line = lines[14]
    lines[14] = line.replace("x_replace_x", token)

    line = lines[19]
    lines[19] = line.replace("x_replace_x", str(connect_timeout))

    line = lines[24]
    lines[24] = line.replace("x_replace_x", str(request_timeout))

    return lines


def set_thread_group(group_index):
    with open("jmeter_blocks/3_thread_group.xml", "r") as file:
        lines = file.readlines()

    for i in range(0, len(lines)):
        line = lines[i]
        if "X" in line:
            lines[i] = line.replace("X", str(group_index))

    return lines


def set_thread_variables(group_index, throughput, users, ramp_up, duration):
    duration += (ramp_up + 1)

    with open("jmeter_blocks/4_thread_variables.xml", "r") as file:
        lines = file.readlines()

    line = lines[4]
    lines[4] = line.replace("x_replace_x", str(throughput))

    line = lines[9]
    lines[9] = line.replace("x_replace_x", str(users))

    line = lines[14]
    lines[14] = line.replace("x_replace_x", str(ramp_up))

    line = lines[19]
    lines[19] = line.replace("x_replace_x", str(duration))

    for i in range(0, len(lines)):
        line = lines[i]
        if "X" in line:
            lines[i] = line.replace("X", str(group_index))

    return lines


def set_samplers(group_index, work_dir, distribution):
    encoded_input_file_path = work_dir + "encoded_input"
    
    if distribution == "exponential":
        with open("jmeter_blocks/5_samplers_exponential.xml", "r") as file:
            lines = file.readlines()
    else:
        if distribution != "constant":
            print(colored("Wrong specification of distribution (constant/exponential), using the constant one", "red"))
        with open("jmeter_blocks/5_samplers_constant.xml", "r") as file:
            lines = file.readlines()

    for i in range(0, len(lines)):
        line = lines[i]
        if "X" in line:
            lines[i] = line.replace("X", str(group_index))

    for i in range(0, len(lines)):
        line = lines[i]
        if "x_replace_x" in line:
            lines[i] = line.replace("x_replace_x", encoded_input_file_path)

    return lines


def get_end():
    with open("jmeter_blocks/6_end.xml", "r") as file:
        lines = file.readlines()

    return lines


def make_test_file(configuration, work_dir):
    content = get_start()

    content += set_generic_variables(configuration["cluster_endpoint"],
                                     configuration["oscar_service"],
                                     configuration["token"],
                                     configuration["connect_timeout_seconds"],
                                     configuration["request_timeout_seconds"]
                                     )

    group_index = 1
    for test in configuration["tests"]:

        throughput = round(test["throughput"] / configuration["worker_nodes"], 2)
        number_of_threads = int(round(test["number_of_threads"] / configuration["worker_nodes"], 0))
        if number_of_threads == 0:
            number_of_threads = 1

        content += set_thread_group(group_index)
        content += set_thread_variables(group_index,
                                        throughput, number_of_threads,
                                        test["ramp_up_seconds"], test["duration_seconds"])
        content += set_samplers(group_index, work_dir, configuration["distribution"])
        group_index += 1

    content += get_end()

    with open(work_dir + "test.jmx", "w") as file:
        file.writelines(content)

    return
