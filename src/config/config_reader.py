import os

from azure.appconfiguration.provider import (
    # AzureAppConfigurationKeyVaultOptions,
    SettingSelector,
    load,
)
from azure.identity import DefaultAzureCredential


class AppConfigReader:
    def __init__(self):
        self.endpoint = os.getenv("AZURE_APPCONFIG_ENDPOINT")
        self.app_name = os.getenv("APP_NAME", "jira-mcp")
        self.environment = os.getenv("ENVIRONMENT", "dev")

    def load(self) -> dict:
        # Local development:
        # If Azure App Configuration is not configured,
        # return an empty dictionary.
        if not self.endpoint:
            return {}

        credential = DefaultAzureCredential()

        prefix = f"{self.app_name}:"

        config = load(
            endpoint=self.endpoint,
            credential=credential,
            selects=[
                SettingSelector(
                    key_filter=f"{prefix}*",
                    label_filter=self.environment,
                    # label_filter="\0",
                )
            ],
            trim_prefixes=[prefix],
            # keyvault_options=AzureAppConfigurationKeyVaultOptions(
            #     credential=credential
            # ),
            keyvault_credential=credential,
        )

        return dict(config)