import os
import tempfile
import certifi
import requests
import uuid
import logging
from configuration.manger_config import config

logger = logging.getLogger(__name__)


def create_shared_ca_bundle() -> str | None:
    try:
        ca_file_path = "certs/brightdata_proxy.crt"
        if not os.path.exists(ca_file_path):
            raise FileNotFoundError(f"Proxy CA certificate not found at: {ca_file_path}")

        standard_ca_bundle = certifi.contents()
        with open(ca_file_path, 'r', encoding='utf-8') as f:
            custom_ca_cert = f.read()

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pem', encoding='utf-8') as temp_ca_file:
            temp_ca_file.write(standard_ca_bundle)
            temp_ca_file.write("\n")
            temp_ca_file.write(custom_ca_cert)
            shared_ca_path = temp_ca_file.name

        return shared_ca_path
    except Exception as e:
        logger.error("Failed to create shared CA bundle: %s", e)
        return None


def set_ssl_cert_for_process(ca_bundle_path: str | None):
    if ca_bundle_path and os.path.exists(ca_bundle_path):
        os.environ['SSL_CERT_FILE'] = ca_bundle_path
    else:
        logger.warning("Shared CA bundle path '%s' is invalid. SSL connections may fail.", ca_bundle_path)


def cleanup_shared_ca_bundle(ca_bundle_path: str | None):
    if ca_bundle_path and os.path.exists(ca_bundle_path):
        try:
            os.remove(ca_bundle_path)
        except OSError as e:
            logger.error("Failed to clean up shared CA bundle at '%s': %s", ca_bundle_path, e)


def get_proxy_session_config() -> dict | None:
    proxy_conf = config.proxy
    if not proxy_conf.getboolean('Enabled', fallback=False):
        return None

    session_id = uuid.uuid4().hex
    proxy_user = f"{proxy_conf['Username']}-session-{session_id}"

    full_proxy_url = f"http://{proxy_user}:{proxy_conf['Password']}@{proxy_conf['Host']}:{proxy_conf['Port']}"

    return {
        "full_proxy_url": full_proxy_url
    }


def create_requests_session(proxy_config: dict | None) -> requests.Session:
    session = requests.Session()
    if proxy_config and "full_proxy_url" in proxy_config:
        session.proxies = {
            "http": proxy_config["full_proxy_url"],
            "https": proxy_config["full_proxy_url"]
        }
    return session
