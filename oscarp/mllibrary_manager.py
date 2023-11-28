import os
import configparser

import executables

from termcolor import colored

from utils import auto_mkdir, read_json, write_json

from aMLLibrary import sequence_data_processing
# from aMLLibrary.model_building.predictor import Predictor

import global_parameters as gp


def run_mllibrary():
    print(colored("\nGenerating models...", "blue"))

    for i in range(len(gp.deployments)):
        deployment = gp.deployments[i]
        deployment.append("Full_workflow")
        print("Deployment: %s" % i)
        for unit in deployment:
            results_dir = "%sdeployment_%s/%s/results/" % (gp.campaign_dir, i, unit)

            if os.path.exists(results_dir):
                # sets directories
                dataframes_dir = results_dir + "Dataframes/"
                models_dir = results_dir + "Models/"
                auto_mkdir(models_dir)

                train_and_predict(dataframes_dir, models_dir, gp.run_name)
                add_to_performance_models_json()

    print(colored("Done!", "green"))


def train_and_predict(dataframes_dir, models_dir, run_name):
    """
    this function trains the regressors, both with and without SFS, and then makes the predictions
    :param dataframes_dir: points to either CSVs/Interpolation or CSVs/Extrapolation and makes this function reusable
    :param models_dir: points to either Models/Interpolation or Models/Extrapolation
    :param run_name:
    """

    # training_set = csvs_dir + "training_set.csv"
    # test_set = csvs_dir + "test_set.csv"
    # training_set = dataframes_dir + "dataframe.csv"

    if not gp.has_active_lambdas:
        for dataframe in os.listdir(dataframes_dir):
            config_file = os.path.join(gp.application_dir, "oscarp", "aMLLibrary-config.ini")
            output_dir = models_dir + dataframe.strip("_dataframe.csv") + "_model"
            train_models(config_file, dataframes_dir + dataframe, output_dir)

    else:
        # dummy
        pass  # todo fill

    """
    # prediction
    config_file = "aMLLibrary/aMLLibrary-predict.ini"
    set_mllibrary_predict_path(config_file, test_set)
    make_prediction(config_file, output_dir_sfs)
    make_prediction(config_file, output_dir_no_sfs)
    """


def train_models(config_file, filepath, output_dir):
    """
    this function train the four regressors, either with or without SFS depending on the parameters
    :param config_file: path to the configuration file
    :param filepath: path to the test set csv
    :param output_dir: output directory for the four regressors (i.e. "Models/Extrapolation/full_model_noSFS")
    :return:
    """
    set_mllibrary_config_path(config_file, filepath)
    sequence_data_processor = sequence_data_processing.SequenceDataProcessing(config_file, output=output_dir)
    sequence_data_processor.process()


def set_mllibrary_config_path(config_file, filepath):
    """
    this function sets the correct path to the train set in the SFS or noSFS configuration file
    :param config_file: path to the configuration file
    :param filepath: path to the test set csv
    """

    parser = configparser.ConfigParser()
    parser.read(config_file)
    parser.set("DataPreparation", "input_path", filepath)

    with open(config_file, "w") as file:
        parser.write(file)


def set_mllibrary_predict_path(config_file, filepath):
    """
    this function sets the correct path to the test set in the "predict" configuration file
    :param config_file: path to the configuration file
    :param filepath: path to the test set csv
    """

    parser = configparser.ConfigParser()
    parser.read(config_file)
    parser.set("DataPreparation", "input_path", filepath)

    with open(config_file, "w") as file:
        parser.write(file)


def make_prediction(config_file, workdir):
    """
    this functions makes predictions by using the trained models
    :param config_file: points to aMLLibrary-predict.ini
    :param workdir: points to the currently considered model (e.g. Models/Interpolation/full_model_noSFS)
    """

    regressors_list = ["DecisionTree", "RandomForest", "XGBoost"]
    for regressor_name in regressors_list:
        regressor_path = workdir + "/" + regressor_name + ".pickle"
        output_dir = workdir + "/output_predict_" + regressor_name
        predictor_obj = Predictor(regressor_file=regressor_path, output_folder=output_dir, debug=False)
        predictor_obj.predict(config_file=config_file, mape_to_file=True)


def add_to_performance_models_json():
    filepath = gp.application_dir + "oscarp/performance_models.json"
    performance_models = read_json(filepath)

    component_name, resource = gp.run_name.split('@')
    component_name = component_name.replace("C", "component")

    if "P" in component_name:
        component_name = component_name.replace("P", "_partition")
        component_name = component_name.replace(".", "_")
        partition_name = gp.components[component_name]["name"]
        component_name = partition_name.split("_partition")[0]
    else:
        component_name = gp.components[component_name]["name"]
        partition_name = component_name

    model_type = "CoreBasedPredictor"
    model_path = gp.results_dir + "Models/" + gp.run_name + "_model/best.pickle"

    if component_name not in performance_models.keys():
        performance_models[component_name] = {}

    if partition_name not in performance_models[component_name].keys():
        performance_models[component_name][partition_name] = {}

    performance_models[component_name][partition_name][resource] = {
        "model": model_type,
        "regressor_file": model_path
    }

    write_json(filepath, performance_models)


