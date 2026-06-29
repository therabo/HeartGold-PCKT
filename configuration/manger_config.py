import configparser
from pathlib import Path


class ConfigManager:
    def __init__(self, base_path: Path = Path(__file__).resolve().parent):
        config_file_path = base_path / "config.ini"

        self.master_config = self._load_config(config_file_path)

        self.log_to_console = self.master_config.getboolean('Logging', 'LogToConsole', fallback=False)

        self.proxy_enabled = self.master_config.getboolean('Proxy', 'Enabled', fallback=False)
        self.proxy = self.master_config['Proxy']

        self.collector_settings = self.master_config['Collector']
        self.leveler_settings = self.master_config['Leveler']

        self.profile = {
            'AppInfo': self.master_config['AppInfo'],
            'NetworkInfo': self.master_config['NetworkInfo'],
            'LocaleInfo': self.master_config['LocaleInfo'],
            'DeviceInfo': self.master_config['DeviceInfo']
        }

        self.endpoints = {
            'NintendoBaaS': self.master_config['NintendoBaaS_Endpoints'],
            'TakashoGRPC': self.master_config['TakashoGRPC_Endpoints']
        }

        self.secrets = {
            'NintendoBaaS': self.master_config['NintendoBaaS_Secrets'],
            'TakashoGRPC': self.master_config['TakashoGRPC_Secrets'],
            'CcbCipher': self.master_config['CcbCipher_Secrets']
        }

        self.database = self.master_config['MongoDB']

        self.headers = {
            'StaticHashes': self.master_config['StaticHashes']
        }

        self.user_agents_path = base_path / "user_agent.ini"

    def _load_config(self, path: Path) -> configparser.ConfigParser:
        if not path.exists():
            raise FileNotFoundError(f"File di configurazione non trovato: {path}")

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(path)
        return config


config = ConfigManager()
