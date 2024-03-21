# Copyright 2021 Agnostiq Inc.
#
# This file is part of Covalent.
#
# Licensed under the Apache License 2.0 (the "License"). A copy of the
# License may be obtained with this software package or at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Use of this file is prohibited except in compliance with the License.
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

variable "name" {
  description = "The Name which should be used for the Azure Resource Group"
  default     = "covalent-executor-azure"
}

variable "cluster_size" {
  description = "The number of Virtual Machines in the cluster"
  type        = number
  default     = 1
}

variable "username" {
  description = "The username of the local administrator used for the Virtual Machine"
  default     = "ubuntu"
}

variable "location" {
  description = "The Azure Region where the Resource Group should exist"
  default     = "East US 2"
}

variable "size" {
  description = "The SKU which should be used for the Virtual Machine"
  default     = "Standard_B2ats_v2"
}

variable "storage_account_type" {
  description = "The Type of Storage Account which should back the Internal OS Disk"
  default     = "StandardSSD_LRS"
}

variable "disk_size_gb" {
  description = "The Size of the Internal OS Disk in GB"
  default     = 64
}

variable "python3_version" {
  description = "Python version to install"
  default     = "3.9"
}

variable "covalent_version" {
  description = "Covalent version to install on the cloud instance"
  default     = ""
}

# # variable "ubuntu_version" {
# #   default     = "22.04"
# #   description = "Ubuntu LTS version"
# # }
