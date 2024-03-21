terraform {
  required_providers {
    azapi = {
      source  = "azure/azapi"
      # known to work with 1.13.1
      version = "~>1.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      # known to work with 3.105.0
      version = "~>3.0"
    }
    random = {
      source  = "hashicorp/random"
      # known to work with 3.6.2
      version = "~>3.6"
    }
  }
}
