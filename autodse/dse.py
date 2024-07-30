import inspect
import requests
import json
import time
import ast
import itertools
import multiprocessing as mp
import socket
import traceback

API_URL = "https://dse.davidchen.page/api/"


def proxy_fn(kwargs):
    results = target_fn(**kwargs)
    return {"inputs": kwargs, "outputs": results} if results else None


def start(fn, api_key, NUM_CORES=mp.cpu_count()):
    # analyze the function fn and send the results to the server
    global target_fn
    target_fn = fn
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
    REPORT_INTERVAL = 100
    try:
        results_list = []
        with mp.Pool(NUM_CORES) as p:
            iter_start_time = time.time()
            for i, partial_result in enumerate(p.imap_unordered(proxy_fn, args), 1):
                if partial_result:
                    results_list.append(partial_result)
                if i % REPORT_INTERVAL == 0:
                    # print(f"Progress: {i}/{len(args)}")
                    iter_end_time = time.time()
                    iter_total_time = iter_end_time - iter_start_time
                    iter_start_time = iter_end_time
                    response = requests.post(
                        API_URL + "experiment/progress",
                        json=json.dumps(
                            {
                                "progress": {
                                    "index": i,
                                    "total": len(args),
                                    "time_per_interval": iter_total_time,
                                    "interval": REPORT_INTERVAL,
                                },
                                "id": experiment["id"],
                            }
                        ),
                        params={"api_key": api_key},
                    )

    except Exception:
        response = requests.post(
            API_URL + "experiment/error",
            json=json.dumps({"error": traceback.format_exc(), "id": experiment["id"]}),
            params={"api_key": api_key},
        )
        return
    # print(results_list)
    results = {k: {} for k in results_list[0].keys()}
    for result in results_list:
        # inputs or outputs
        for kind in result:
            # each key in inputs or outputs
            for k in result[kind]:
                if k not in results[kind]:
                    results[kind][k] = []
                results[kind][k].append(result[kind][k])

    # print(results)
    # Send the results to the server
    response = requests.post(
        API_URL + "experiment/result",
        json=json.dumps({"data": results, "id": experiment["id"]}),
        params={"api_key": api_key},
    )


def test(a=1, b=[1, 2], c=("hello", 10), d="a", e=0.5):
    return {"output": a + sum(b) + c[1] + ord(d) * e}
