#
#  Copyright (c) 2024, zrcheng1991. All rights reserved.
#
#  SPDX-License-Identifier: BSD-2-Clause-Patent
#

import json
import os
import requests
import time
import urllib3

from argparse import ArgumentParser
from datetime import datetime
from enum import Enum
from io import BytesIO
from requests import Request, Response, Session
from requests.auth import AuthBase, HTTPBasicAuth
from threading import Thread
from tqdm import tqdm
from tqdm.utils import CallbackIOWrapper
from typing import List
from urllib.parse import urlparse


class ActionStatus(Enum):
    Success = 0
    Failure = 1
    Unsupported = 2


def refresh_pbar(pbar: tqdm) -> None:
    """
    Constantly refreshes a given progress bar.
    """
    while pbar.disable == False:
        time.sleep(0.5)
        pbar.refresh()


def select_multipart_target(members: List[any]) -> List[str]:
    """
    Print and number the available targets on the terminal and ask the user to select the target.
    """
    print("Available firmware inventories are listed below:")
    for index, member in enumerate(members, start=1):
        print(f'{index}\t{member["@odata.id"]}')

    multipart_targets = []
    while True:
        print("\nPlease enter numbers to select multiple targets, separated by spaces,")
        print("or 0 to indicate that Multipart HTTP PUSH is not used.")
        selection = input(">> ")

        if selection == "0":
            break
        else:
            indicies = selection.split()
            for index in indicies:
                try:
                    multipart_targets.append(members[int(index) - 1]["@odata.id"])
                except IndexError:
                    print(f"Index {index} is not valid.")
                    multipart_targets.clear()

        if len(multipart_targets) != 0:
            print("\nSelected targets are listed below:")
            for target in multipart_targets:
                print(target)
            print()
            break

    return multipart_targets


def get_from_url(url: str, auth: AuthBase = None) -> Response:
    """
    Perform a HTTP GET from given URL.
    """
    response = None
    json_data = None

    try:
        urllib3.disable_warnings()
        response = requests.get(url=url, auth=auth, verify=False, timeout=3)
        json_data = response.json()
    except Exception as e:
        if json_data is not None:
            message = json_data.get("error").get("message")
            if message is not None:
                print(f"{response.status_code}: {message}")
            else:
                print(f"Status Code: {response.status_code}")
                print(f"Response in JSON:")
                print(json.dumps(json_data, indent=4))
        elif response is not None:
            print(f"Status Code: {response.status_code}")
        else:
            print(e)

    return response


def push_firmware(
    url: str, file_path: str, auth: AuthBase = None
) -> tuple[ActionStatus, str]:
    """
    Pushes a firmware file to given URL.
    """
    response = get_from_url(url, auth)
    if response is None or response.status_code != 200:
        return ActionStatus.Failure, None

    multipart_uri = response.json().get("MultipartHttpPushUri")
    file_size = os.stat(file_path).st_size
    firmware_file = open(file_path, "rb")
    prepared_req = None
    task_id = None

    if multipart_uri is not None:
        print("Update Service on this server supports Multipart HTTP PUSH.")

        # Get Firmware Inventories
        firmware_inventory_url = (
            urlparse(url)
            ._replace(path="/redfish/v1/UpdateService/FirmwareInventory")
            .geturl()
        )
        response = get_from_url(firmware_inventory_url, auth)

        if response.status_code == 200:
            # Ask the user to select targets
            multipart_targets = select_multipart_target(response.json().get("Members"))

            if len(multipart_targets) > 0:
                files = {
                    "UpdateParameters": (
                        None,
                        json.dumps({"Targets": multipart_targets}),
                        "application/json",
                    ),
                    "UpdateFile": (None, firmware_file, "application/octet-stream"),
                }
                req = Request(
                    "post",
                    url=urlparse(url)._replace(path=multipart_uri).geturl(),
                    auth=auth,
                    files=files,
                )
                prepared_req = req.prepare()
                file_size = int(prepared_req.headers.get("Content-Length"))
            else:
                print("Continue to update with default method.\n")

    with tqdm(
        desc="Posting firmware",
        total=file_size,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        bar_format="Posting firmware  ({percentage:3.0f}%)|{bar:50}{r_bar}",
    ) as pbar:
        if prepared_req is None:
            wrapped_file = CallbackIOWrapper(pbar.update, firmware_file, "read")
            req = Request("post", url=url, auth=auth, data=wrapped_file)
            prepared_req = req.prepare()
        else:
            body_stream = BytesIO(prepared_req.body)
            prepared_req.body = CallbackIOWrapper(pbar.update, body_stream, "read")

        try:
            s = Session()
            response = s.send(prepared_req, verify=False)
            task_id = response.json().get("Id")
        except Exception as e:
            print(e)
            return ActionStatus.Failure, None

        pbar.close()

    firmware_file.close()

    if task_id is None:
        print("Cannot get the task ID, please check the BMC.")
        return ActionStatus.Failure, None

    print(f"Finish posting the firmware! (Task Id = {task_id})")

    return ActionStatus.Success, task_id


def track_update_status(url: str, task_id: str, auth: AuthBase = None) -> ActionStatus:
    """
    Tracks an firmware update task from URL.
    """
    response = get_from_url(url, auth)
    if response is None:
        return ActionStatus.Failure

    json_data = response.json()
    if json_data is None:
        return ActionStatus.Failure

    payload = json_data.get("Payload")
    if (
        payload.get("HttpOperation") != "POST"
        or str(payload.get("TargetUri")).find("UpdateService") == -1
    ):
        print("This function only supports tracking the status of update tasks.")
        return ActionStatus.Unsupported
    task_state = json_data.get("TaskState")
    task_status = json_data.get("TaskStatus")

    start_time = datetime.now()
    exception = None

    if task_state == "Running" and task_status == "OK":
        print(f"Firmware update has started! (Task Id = {task_id})")

        with tqdm(
            total=100,
            bar_format="Updating firmware ({percentage:3.0f}%)|{bar:50}| [{elapsed}]",
        ) as pbar:

            t = Thread(target=refresh_pbar, args=(pbar,), daemon=True)
            t.start()

            time.sleep(1)  # sleep for 1 second before retrieving status

            end_time = None
            while end_time is None:
                response = get_from_url(url, auth)
                if response is None:
                    return ActionStatus.Failure

                json_data = response.json()
                if json_data is None:
                    exception = Exception(f"Cannot get JSON data in the response!")
                    break

                task_state = json_data.get("TaskState")
                task_status = json_data.get("TaskStatus")
                percentage = json_data.get("PercentComplete")
                end_time = json_data.get("EndTime")

                pbar.n = int(percentage) if percentage is not None else pbar.n
                delta_time = datetime.now() - start_time

                if end_time is None:
                    if delta_time.seconds > 600:
                        minutes = delta_time.seconds // 60
                        seconds = delta_time.seconds % 60
                        exception = Exception(
                            f"This task has taken longer than expected! (Time elapsed: {minutes:02}:{seconds:02})"
                        )
                        break
                    time.sleep(5)
                else:
                    break

            pbar.close()  # the while loop in refresh_pbar() should be broken
            t.join()

    if task_state == "Completed" and task_status == "OK":
        print("Firmware update completed!\n")
        return ActionStatus.Success

    if task_state == "Running":
        if exception is not None:
            print(exception)

        print(f"\nException occurs when getting the status of a task (ID: {task_id}).")
        print(f"Please use other tools to continue tracking the status.\n")
    else:
        print("Firmware update failed!\n")
        messages = response.json().get("Messages")
        if len(messages) > 0:
            print("Critical messages from the server:")
            for message in messages:
                if message.get("Severity") == "Critical":
                    print(message.get("Message"))

    return ActionStatus.Failure


def main():
    parser = ArgumentParser(
        prog="redfish-firmware-update-tool",
        description="This is a tool for publishing firmware to OpenBMC for firmware updates via Redfish's Restful API.",
    )
    parser.add_argument(
        "--bmc-ip",
        type=str,
        help="The IPv4 address of the BMC on the target server platform.",
        required=True,
    )
    parser.add_argument(
        "--port",
        type=int,
        help="The port number for HTTPS connection. (Default is 443)",
        default=443,
    )
    parser.add_argument(
        "--username",
        type=str,
        help='The username for logging into the BMC. (Default is "root")',
        default="root",
    )
    parser.add_argument(
        "--password",
        type=str,
        help='The password for logging into the BMC. (Default is "0penBmc")',
        default="0penBmc",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="%(prog)s v0.1 (Author: github.com/zrcheng1991)",
    )
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--file-path",
        type=str,
        help="Path to the firmware package used for the update.",
    )
    action_group.add_argument(
        "--task-id",
        type=str,
        help="ID of the task to be tracked.",
    )

    args = parser.parse_args()

    base_url = f"https://{args.bmc_ip}:{args.port}"
    auth = HTTPBasicAuth(args.username, args.password)

    if args.file_path:
        url = urlparse(base_url)._replace(path="/redfish/v1/UpdateService/").geturl()
        status, task_id = push_firmware(url, args.file_path, auth)

    task_id = args.task_id if args.task_id is not None else task_id

    url = (
        urlparse(base_url)
        ._replace(path=f"/redfish/v1/TaskService/Tasks/{task_id}")
        .geturl()
    )
    status = track_update_status(url, task_id, auth)


if __name__ == "__main__":
    main()
