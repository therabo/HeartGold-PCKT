import random
import os
import time
import logging
import grpc
import requests

from operation_modules.document_builder import build_god_pack_document
from configuration.language_config import LANGUAGE_CONFIGS
from configuration.manger_config import config
from encryption.token_parser import parse_server_token
from nintendo_baas.baas_login import NintendoBaasLogin
from nintendo_baas.device_manager import generate_takasho_device_account, generate_takasho_identifier
from grpc_client.player_api import PlayerApiClient
from cards.card_filter import filter_god_pack

from network.proxy_manager import (
    set_ssl_cert_for_process,
    get_proxy_session_config,
    create_requests_session
)

logger = logging.getLogger(__name__)
shared_data = {}


class Collector:
    def __init__(self, child_id, pack_id, product_id, language_code, device_profile_data: dict):
        self.child_id = child_id
        self.assigned_pack_id = pack_id
        self.assigned_product_id = product_id
        self.language_code = language_code
        self.pid = os.getpid()
        self.device_profile = device_profile_data
        self.card_lookup = shared_data.get('card_lookup_data', {})
        self.results_queue = shared_data.get('results_queue')
        self.shutdown_event = shared_data.get('shutdown_event')
        self.use_proxy = shared_data.get('use_proxy', False)
        self.start_event = shared_data.get('start_event')
        self.account_credentials = {}
        self.account_details = {}
        self.api_client = None
        self.packs_opened_counter = shared_data.get('packs_opened_counter')
        self.god_packs_found_counter = shared_data.get('god_packs_found_counter')
        self.counter_lock = shared_data.get('counter_lock')

    def _get_new_clients(self):
        proxy_config = get_proxy_session_config() if self.use_proxy else None

        http_session = create_requests_session(proxy_config)

        baas_client = NintendoBaasLogin(self.device_profile)

        secrets = parse_server_token(config.secrets['TakashoGRPC']['ServerTokenString'])
        api_key = secrets["pinned_cert_fingerprint"]
        api_client = PlayerApiClient(api_key, self.device_profile, proxy_config)

        return http_session, baas_client, api_client

    def _handle_god_pack_found(self, god_pack_data: dict, session_token: str, dynamic_nickname: str):

        if self.god_packs_found_counter and self.counter_lock:
            with self.counter_lock:
                self.god_packs_found_counter.value += 1

        profile_response = self.api_client.save_profile(
            session_token=session_token,
            nickname=dynamic_nickname,
            icon_id="PROFILE_ICON_100140_KABIGON",
            message_id="PROFILE_MESSAGE_1"
        )

        if profile_response and profile_response.profile and profile_response.profile.profile_spine:
            self.account_details['friend_id'] = profile_response.profile.profile_spine.friend_id
            self.account_details['nickname'] = profile_response.profile.profile_spine.nickname
        else:
            self.account_details['friend_id'] = None
            self.account_details['nickname'] = dynamic_nickname

        final_document = build_god_pack_document(
            account_credentials=self.account_credentials,
            account_details=self.account_details,
            pack_data=god_pack_data
        )

        self.results_queue.put(final_document)

    def perform_single_cycle(self, http_session: requests.Session, baas_client: NintendoBaasLogin,
                             api_client: PlayerApiClient):

        self.api_client = api_client

        lang_config = LANGUAGE_CONFIGS[self.language_code]
        self.account_credentials = {}
        self.account_details = {'language': self.language_code}

        device_account = generate_takasho_device_account()
        device_identifier = generate_takasho_identifier(device_model=self.device_profile['device_name'])
        self.account_credentials['device_account'] = device_account

        login_response = baas_client.login(
            session=http_session,
            locale=lang_config["locale"],
            time_zone=lang_config["time_zone"]
        )
        if not login_response:
            raise RuntimeError("BaaS Login Failed. Response was empty.")

        self.account_credentials.update({
            "nintendo_id": login_response["nintendo_id"],
            "nintendo_password": login_response["nintendo_password"]
        })
        id_token = login_response["id_token"]

        session_token = api_client.authorize_v1(id_token, device_account, device_identifier)
        if not session_token:
            raise RuntimeError("AuthorizeV1 Failed (session_token was None).")

        api_client.login_v1(
            session_token=session_token,
            language_type=lang_config["language_type"],
            country_code=lang_config["country_code"],
            account_details=self.account_details
        )

        random_suffix = random.randint(10000000, 99999999)
        dynamic_nickname = f"HG{random_suffix}"

        self.account_details['lv_account'] = 1

        for attempt in range(2):
            pack_token = api_client.get_detail_v2(session_token, self.assigned_pack_id)
            if pack_token:
                purchase_response = api_client.purchase_v2(session_token, pack_token, self.assigned_product_id)
                if purchase_response:
                    if self.packs_opened_counter and self.counter_lock:
                        with self.counter_lock:
                            self.packs_opened_counter.value += 1

                    god_pack_data = filter_god_pack(purchase_response, self.card_lookup)
                    if god_pack_data:
                        self._handle_god_pack_found(god_pack_data, session_token, dynamic_nickname)
                        return

        session_token_reauth = api_client.authorize_v1(id_token, device_account, device_identifier)
        if not session_token_reauth:
            raise RuntimeError("Re-authorization failed.")
        session_token = session_token_reauth

        api_client.may_level_up_v1(session_token)
        self.account_details['lv_account'] = 2

        pack_token = api_client.get_detail_v2(session_token, self.assigned_pack_id)
        if pack_token:
            purchase_response = api_client.purchase_v2(
                session_token=session_token,
                pack_consistent_token=pack_token,
                product_id=self.assigned_product_id,
                charger_amount=12
            )
            if purchase_response:
                if self.packs_opened_counter and self.counter_lock:
                    with self.counter_lock:
                        self.packs_opened_counter.value += 1

                god_pack_data = filter_god_pack(purchase_response, self.card_lookup)
                if god_pack_data:
                    self._handle_god_pack_found(god_pack_data, session_token, dynamic_nickname)
                    return

        api_client.delete_account_v1(session_token)


def collector_main_logic(child_id, assigned_pack_id, assigned_product_id, language_code, device_profile_data):
    collector_instance = Collector(child_id, assigned_pack_id, assigned_product_id, language_code, device_profile_data)

    if collector_instance.use_proxy:
        shared_ca_path = shared_data.get('shared_ca_path')
        set_ssl_cert_for_process(shared_ca_path)

    try:
        collector_instance.start_event.wait()
        startup_delay = random.uniform(0, 120.0)
        time.sleep(startup_delay)
        logger.info("(PID %d) Received START signal. Entering main loop.", os.getpid())

        cycles_per_ip = config.collector_settings.getint('CyclesPerIp', 80)

        while not collector_instance.shutdown_event.is_set():
            http_session, baas_client, api_client = None, None, None
            try:
                logger.info("Setting up new connection for a batch of %d cycles.", cycles_per_ip)
                http_session, baas_client, api_client = collector_instance._get_new_clients()

                for cycle_num in range(cycles_per_ip):
                    if collector_instance.shutdown_event.is_set():
                        break
                    try:
                        collector_instance.perform_single_cycle(http_session, baas_client, api_client)
                    except (grpc.RpcError, requests.exceptions.RequestException, RuntimeError) as e:
                        logger.error("Initial client setup failed: %s. Retrying connection.", str(e)[:150])
                        break

            except (grpc.RpcError, requests.exceptions.RequestException, RuntimeError) as e:
                logger.warning("Cycle failed, breaking batch. Reason: %s", str(e)[:150])
                continue

            finally:
                if api_client:
                    api_client.close_channel()
                if http_session:
                    http_session.close()

    except Exception as e:
        logger.exception("Unhandled FATAL error in main loop.")

    finally:
        logger.info("(PID %d) has terminated.", os.getpid())
