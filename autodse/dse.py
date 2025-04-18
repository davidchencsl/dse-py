import inspect
import os
import requests
import json
import time
import ast
import itertools
import socket
import traceback
import gzip
import base64
import traceback
from collections import ChainMap

from tqdm import tqdm
import numpy as np
import multiprocess as mp

API_URL = "https://dse.davidchen.page/api/"

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, float):
            return float(obj)
        if isinstance(obj, Float):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super(NpEncoder, self).default(obj)


def start(fn, api_key, output_path="results", NUM_CORES=mp.cpu_count()):
    # analyze the function fn and send the results to the server
    output_path += ".json.gz"
    signature = inspect.signature(fn)
    function_info = {
        "fn_name": fn.__name__,
        "parameters": [
            {
                "name": p.name,
                "type": (
                    type(p.default).__name__
                    if p.default is not inspect.Parameter.empty
                    else "None"
                ),
                "default": repr(p.default),
            }
            for p in signature.parameters.values()
        ],
    }
    function_info["full_signature"] = (
        function_info["fn_name"]
        + "("
        + ", ".join(
            [
                f"{p['name']}: {p['type']} = {p['default']}"
                for p in function_info["parameters"]
            ]
        )
        + ")"
    )
    # print(function_info)
    # print(api_key)

    function_info = json.dumps(function_info)

    # send the function_info to the server
    response = requests.post(
        API_URL + "experiment/create",
        json=function_info,
        params={"api_key": api_key, "hostname": socket.gethostname()},
    )
    response_json = response.json()
    # print(response_json)

    # Wait for server to start the experiment
    print("Waiting for server to start the experiment")
    status = "CREATED"
    while status == "CREATED":
        response = requests.get(
            API_URL + "experiment",
            params={"api_key": api_key, "id": response_json["data"][0]["id"]},
        )
        response_json = response.json()
        status = response_json["data"][0]["status"]
        time.sleep(5)
        # print(f"Experiment status: {status}")

    # print(f"Experiment status: {status}")
    experiment = response_json["data"][0]

    explorations = json.loads(experiment["explorations"])
    # print(explorations)
    converted_explorations = {}
    for arg in explorations:
        if explorations[arg]:
            values = f"[{explorations[arg]}]"
            converted_explorations[arg] = ast.literal_eval(values)
    # print(converted_explorations)

    args = [
        dict(zip(converted_explorations.keys(), values))
        for values in itertools.product(*converted_explorations.values())
    ]
    # print(args)
    # Call the function with the generated arguments

    print(f"Experiment started. Running with NUM_CORES={NUM_CORES}")
    REPORT_INTERVAL = 10
    times = np.zeros(20)
    def proxy_fn(kwargs):
        results = fn(**kwargs)
        return {"inputs": kwargs, "outputs": results} if results else None
    try:
        results_list = []
        with mp.Pool(NUM_CORES) as p:
            iter_start_time = time.time()
            start_iter = 0
            for i, partial_result in enumerate(p.imap(proxy_fn, args), 1):
                if partial_result:
                    results_list.append(partial_result)
                    print(f"Progress: {i}/{len(args)}                                      \r", end="")
                iter_end_time = time.time()
                iter_total_time = iter_end_time - iter_start_time
                
                if iter_total_time > REPORT_INTERVAL:
                    iter_start_time = iter_end_time
                    times = np.roll(times, 1)
                    times[0] = iter_total_time
                    # weighted average
                    iter_total_time = np.mean(times)
                    response = requests.post(
                        API_URL + "experiment/progress",
                        json=json.dumps(
                            {
                                "progress": {
                                    "index": i,
                                    "total": len(args),
                                    "time_per_interval": iter_total_time,
                                    "interval": i - start_iter,
                                },
                                "id": experiment["id"],
                            },
                            cls=NpEncoder,
                        ),
                        params={"api_key": api_key},
                    )
                    start_iter = i
    except Exception as e:
        print(e)
        response = requests.post(
            API_URL + "experiment/error",
            json=json.dumps({"error": traceback.format_exc(), "id": experiment["id"]}),
            params={"api_key": api_key},
        )
        return
    
    print("")
    # print(results_list)
    results = {"inputs": {}, "outputs": {}}
    for result in results_list:
        # inputs or outputs
        for kind in result:
            # each key in inputs or outputs
            for k in result[kind]:
                if k not in results[kind]:
                    results[kind][k] = []
                results[kind][k].append(result[kind][k])
    with gzip.open(output_path, 'wt', encoding='UTF-8') as zf:
        json.dump(results, zf, cls=NpEncoder, default=str)

    if  get_uncompressed_size(output_path) > 1024 * 1024 * 1024:
        print(f"Output file {output_path} is too large. Not uploading to server.")
        return
    
    print("Sending results to the server.")
    results_str = base64.b64encode(open(output_path, "rb").read()).decode("utf-8")
    # print(results)
    # Send the results to the server
    response = requests.post(
        API_URL + "experiment/result",
        json=json.dumps({"data": results_str, "id": experiment["id"]}, cls=NpEncoder),
        params={"api_key": api_key},
    )
    print(response.json())

def start_local(fn, prod_args, zip_args, output_path="results", NUM_CORES=mp.cpu_count()):
    # analyze the function fn and send the results to the server
    output_path += ".json.gz"
    signature = inspect.signature(fn)
    function_info = {
        "fn_name": fn.__name__,
        "parameters": [
            {
                "name": p.name,
                "type": (
                    type(p.default).__name__
                    if p.default is not inspect.Parameter.empty
                    else "None"
                ),
                "default": repr(p.default),
            }
            for p in signature.parameters.values()
        ],
    }
    function_info["full_signature"] = (
        function_info["fn_name"]
        + "("
        + ", ".join(
            [
                f"{p['name']}: {p['type']} = {p['default']}"
                for p in function_info["parameters"]
            ]
        )
        + ")"
    )
    if isinstance(zip_args, dict):
        zip_args = [zip_args]

    prod_args = {k: v if isinstance(v, list) else v.tolist() for k, v in prod_args.items()}
    zip_args = [{k: v if isinstance(v, list) else v.tolist() for k, v in entry.items()} for entry in zip_args]

    function_info = json.dumps(function_info)

    for key, value in prod_args.items():
        if not isinstance(value, list):
            prod_args[key] = [value]

    prod_args = [
        dict(zip(prod_args.keys(), values))
        for values in itertools.product(*prod_args.values())
    ]

    zip_args = [
        [
        dict(zip(zip_arg.keys(), values))
        for values in zip(*zip_arg.values())
        ] for zip_arg in zip_args
    ]

    temp = []
    for sublist in itertools.product(*zip_args):
        temp.append(dict(ChainMap(*sublist)))
    zip_args = temp

    args = [
        {**prod_arg, **zip_arg}
        for prod_arg in prod_args
        for zip_arg in zip_args
    ]

    # for i in args:
    #     print(i)
    # exit()
    # Call the function with the generated arguments

    print(f"Experiment started. Running with NUM_CORES={NUM_CORES}")
    def proxy_fn(kwargs):
        results = fn(**kwargs)
        return {"inputs": kwargs, "outputs": results} if results else None
    try:
        results_list = []
        with mp.Pool(NUM_CORES, initializer=tqdm.set_lock, initargs=(tqdm.get_lock(),)) as p:
            for partial_result in tqdm(p.imap_unordered(proxy_fn, args), total=len(args)):
                if partial_result:
                    results_list.append(partial_result)
    except Exception as e:
        print(e)
        traceback.print_exc()
        return
    
    print("")
    # print(results_list)
    results = {"inputs": {}, "outputs": {}}
    for result in results_list:
        # inputs or outputs
        for kind in result:
            # each key in inputs or outputs
            for k in result[kind]:
                if k not in results[kind]:
                    results[kind][k] = []
                results[kind][k].append(result[kind][k])
    with gzip.open(output_path, 'wt', encoding='UTF-8') as zf:
        json.dump(results, zf, cls=NpEncoder, default=str)
    print(f"Results saved to {output_path}. Uncompressed size: {get_uncompressed_size(output_path)} bytes")

def get_uncompressed_size(file_path):
    import subprocess
    output = subprocess.run(["gzip", "-l", file_path], capture_output=True)
    output = output.stdout.decode("utf-8").split("\n")[1].split()
    return int(output[1])

def dse_tqdm(*args, **kwargs):
    idx = mp.current_process()._identity[0]-1 if mp.current_process()._identity else 0
    return tqdm(*args, **kwargs, position=idx+1, desc=f"Process {idx}", leave=False)
