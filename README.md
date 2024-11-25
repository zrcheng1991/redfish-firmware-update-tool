# Redfish Firmware Update Tool

This is a tool to publish firmware to OpenBMC for firmware updates via Redfish's Restful API.

## Table of Contents
- [Release Note](#release-note)
- [Features](#features)
- [Limitations](#limitations)
- [Usage](#usage)
  - [Overview of the options](#overview-of-the-options)
  - [Posting Firmware](#posting-firmware)
  - [Tracking Update Status](#tracking-update-status)
- [Reference Documents](#reference-documents)
  
---

## Release Note
| Date | Version | Comment |
| :--- | :--- | :--- |
| 2024/11/25 | 0.1 | Initial release. |
  
## Features
- Simple firmware update
- Multipart firmware update with flexible target selection
- Visual update status tracking

## Limitations
- Supports HTTPS only.
- Supports basic authentication only.
- Supports tracking firmware update tasks only.

## Usage
### Overview of the options
The following is the text of the description exported by `argparse`:
```bash
usage: RedfishFirmwareUpdate.py [-h] --bmc-ip BMC_IP [--port PORT] [--username USERNAME] [--password PASSWORD] (--file-path FILE_PATH | --task-id TASK_ID)

options:
  -h, --help            show this help message and exit
  --bmc-ip BMC_IP       The IPv4 address of the BMC on the target server platform.
  --port PORT           The port number for HTTPS connection. (Default is 443)
  --username USERNAME   The username for logging into the BMC. (Default is "root")
  --password PASSWORD   The password for logging into the BMC. (Default is "0penBmc")
  --file-path FILE_PATH
                        Path to the firmware package used for the update.
  --task-id TASK_ID     ID of the task to be tracked.
```

### Posting Firmware
Assume that the IPv4 address of the BMC is `192.168.10.15`, and the path to the firmware file is `cec1736-apfw-20307.bin`.  
You can initiate the firmware update by using following command:
```bash
python RedfishFirmwareUpdate.py --bmc-ip 192.168.10.15 --file-path cec1736-apfw-20307.bin
```
  
> [!NOTE]
> Before starting to post the firmware, it checks if the server is reachable by attempting an HTTP GET from the URI `/redfish/v1/UpdateService`.
> The GET method used by the tool has a timeout of 3 seconds and 3 repeated attempts. If the above attempt fails, error messages are displayed.
  
If the BMC supports Multipart HTTP Push method, it will retrieves available targets from the URI `/redfish/v1/UpdateService/FirmwareInventory`  
and list all the targets on the screen and number them. For example:
```bash
Update Service on this server supports Multipart HTTP PUSH.
Available firmware inventories are listed below:
1       /redfish/v1/UpdateService/FirmwareInventory/BMC_Firmware
2       /redfish/v1/UpdateService/FirmwareInventory/CPLD_0
3       /redfish/v1/UpdateService/FirmwareInventory/CPU_0
4       /redfish/v1/UpdateService/FirmwareInventory/ERoT_CPU_0
5       /redfish/v1/UpdateService/FirmwareInventory/ERoT_GPU_0
6       /redfish/v1/UpdateService/FirmwareInventory/FW_FPGA_0
7       /redfish/v1/UpdateService/FirmwareInventory/FW_GPU_0
8       /redfish/v1/UpdateService/FirmwareInventory/InfoROM_GPU_0
9       /redfish/v1/UpdateService/FirmwareInventory/firmware0

Please enter numbers to select multiple targets, separated by spaces,
or 0 to indicate that Multipart HTTP PUSH is not used.
>>
```
Users can select multiple targets by simply providing space-separated numbers, or enter `0` to use the original PUSH method.  

> [!Note]  
> By default, the URI for posting firmware is `/redfish/v1/UpdateService`.
> If the BMC server supports Multipart HTTP PUSH, the URI is replaced with the path indicated by `MultipartHttpPushUri` in the JSON data.
> Normally, the URI for Multipart HTTP PUSH should be `/redfish/v1/UpdateService/update-multipart`.
  
Then the update process will begin:
```
Posting firmware  (100%)|██████████████████████████████████████████████████| 25.9M/25.9M [00:04<00:00, 6.64MB/s]
Finish posting the firmware! (Task Id = 12)
Firmware update has started! (Task Id = 12)
Updating firmware (  0%)|                                                  | [00:07]
```
  
After the firmware is posted to the BMC, it will start tracking the progress of the update task.
```
Firmware update has started! (Task Id = 12)
Updating firmware (  0%)|                                                  | [00:07]
```
  
If the update task completes successfully, the message is displayed as follows:
```
Firmware update has started! (Task Id = 12)
Updating firmware (100%)|██████████████████████████████████████████████████| [05:58]
Firmware update completed!
```
  
If the update task fails, critical messages collected from server will be displayed:
```
Firmware update has started! (Task Id = 13)
Updating firmware (100%)|██████████████████████████████████████████████████| [00:01]
Firmware update failed!

Critical messages from the server:
The task with id 13 has been aborted.
Verification of image 'cec1736ApFw-20307' at 'CPU_0' failed.
The resource property 'CPU_0' has detected errors of type 'Component image is identical'.
```

### Tracking Update Status
Assume that the IPv4 address of the BMC is `192.168.10.15`, and the Task ID is `13`.  
You can track the firmware update status by using following command:
```bash
python RedfishFirmwareUpdate.py --bmc-ip 192.168.10.15 --task-id 13
```
  
> [!Note]  
> By default, the URI for tracking task status is `/redfish/v1/TaskService/Tasks/{task_id}`.
  
If the task is in progress, a progress bar is displayed to give a visual indication of its progress.
```
Firmware update has started! (Task Id = 12)
Updating firmware (  0%)|                                                  | [00:07]
```

> [!NOTE]
> The progress percentage depends on the BMC report. So the progress bar may not look like a linear growth.
  
Otherwise, if the task is completed, only the result message will be displayed in the terminal.
```
Firmware update completed!
```
Or when it has failed:
```
Firmware update failed!

Critical messages from the server:
The task with id 13 has been aborted.
Verification of image 'cec1736ApFw-20307' at 'CPU_0' failed.
The resource property 'CPU_0' has detected errors of type 'Component image is identical'.
```

> [!NOTE]
> Since the time on the server may not be synchronized with the real world, there is no way to calculate how long a task has been in progress.
> So if you use this method to track tasks, the time shown at the end of the progress bar will be calculated from the moment the command is executed, not the actual start time of the task.

> [!CAUTION]
> In general, firmware upgrade should be completed within 10 minutes, depending on system design.
> If not completed within this time, the tool will stop tracking its progress and prompt the user with following message:  
> ```This task has taken longer than expected! (Time elapsed: 10:00)```

## Reference Documents
- <a href="https://www.dmtf.org/sites/default/files/standards/documents/DSP0266_1.21.0.pdf">DMTF Redfish Specification</a>
