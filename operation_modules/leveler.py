import os
import requests
import queue
import time
import random
import math
import logging

from operation_modules.document_builder import build_level_update_message
from configuration.language_config import LANGUAGE_CONFIGS
from configuration.manger_config import config
from encryption.token_parser import parse_server_token
from nintendo_baas.baas_login import NintendoBaasLogin
from nintendo_baas.device_manager import generate_takasho_identifier
from grpc_client.player_api import PlayerApiClient
from network.proxy_manager import (
    set_ssl_cert_for_process,
    get_proxy_session_config,
    create_requests_session
)
from protobuf.generated.takasho.schema.lettuce_server.resource.item import pack_power_charger_pb2

logger = logging.getLogger(__name__)
shared_data = {}

EXP_THRESHOLDS = {
    1: 25, 2: 175, 3: 325, 4: 505, 5: 715, 6: 955, 7: 1225, 8: 1525, 9: 1855,
    10: 2215, 11: 2605, 12: 3025, 13: 3475, 14: 3955, 15: 4465, 16: 5005, 17: 5575,
    18: 6175, 19: 6810, 20: 7480, 21: 8190, 22: 8940, 23: 9735, 24: 10575, 25: 11465,
    26: 12405, 27: 13395, 28: 14435, 29: 15525, 30: 16670, 31: 17875, 32: 19145,
    33: 20485, 34: 21900, 35: 23395, 36: 24975, 37: 26645, 38: 28410, 39: 30275,
    40: 32250, 41: 34345, 42: 36570, 43: 38935, 44: 41450, 45: 44125, 46: 46970,
    47: 49995, 48: 53210, 49: 56625
}


class Leveler:
    def __init__(self, child_id: int, device_profile_data: dict):
        self.child_id = child_id
        self.pid = os.getpid()
        self.device_profile = device_profile_data

        self.accounts_queue = shared_data.get('accounts_queue')
        self.shutdown_event = shared_data.get('shutdown_event')
        self.use_proxy = shared_data.get('use_proxy', False)
        self.battle_playlist = shared_data.get('battle_playlist', [])
        self.writer_queue = shared_data.get('writer_queue')
        self.progress_queue = shared_data.get('progress_queue')

    def _get_new_clients(self):
        proxy_config = get_proxy_session_config() if self.use_proxy else None

        http_session = create_requests_session(proxy_config)

        baas_client = NintendoBaasLogin(self.device_profile)

        secrets = parse_server_token(config.secrets['TakashoGRPC']['ServerTokenString'])
        api_key = secrets["pinned_cert_fingerprint"]
        api_client = PlayerApiClient(api_key, self.device_profile, proxy_config)

        return http_session, baas_client, api_client

    def perform_leveling_cycle(self, account_doc: dict, http_session: requests.Session, baas_client: NintendoBaasLogin,
                               api_client: PlayerApiClient):

        TARGET_CARDS = 230
        CARDS_PER_PACK = 5
        CHARGERS_PER_PACK = 12
        LEVEL_UP_CHARGER_BONUS = 12
        REFRESH_TOKEN_LIMIT = 3
        pack_id, product_id = "AN008_0010_00_000", "PC_PS_2506000_01_01_01"
        nickname = account_doc.get('nickname', 'N/A')

        lang_code = account_doc.get("language", "en")
        lang_config = LANGUAGE_CONFIGS.get(lang_code, LANGUAGE_CONFIGS["en"])
        login_response = baas_client.login(
            session=http_session, locale=lang_config["locale"], time_zone=lang_config["time_zone"],
            nintendo_id=account_doc["nintendo_id"], nintendo_password=account_doc["nintendo_password"]
        )
        if not login_response or "id_token" not in login_response:
            raise RuntimeError("BaaS Login Failed.")

        id_token = login_response["id_token"]
        device_account = account_doc["device_info"]["id"]
        device_identifier = generate_takasho_identifier(device_model=self.device_profile['device_name'])
        session_token = api_client.authorize_v1(id_token, device_account, device_identifier)
        if not session_token:
            raise RuntimeError("Initial AuthorizeV1 Failed.")

        profile_data = api_client.my_profile_v1(session_token)
        if not profile_data:
            raise RuntimeError("Failed to fetch player profile (my_profile_v1 returned None).")

        current_player_exp, num_cards = profile_data

        true_start_level = 1
        for lvl, exp_req in sorted(EXP_THRESHOLDS.items()):
            if current_player_exp >= exp_req:
                true_start_level = lvl + 1
            else:
                break

        logger.info("Profile check for '%s': Level=%d, Cards=%d, EXP=%d.", nickname, true_start_level, num_cards,
                    current_player_exp)

        if num_cards >= TARGET_CARDS:
            logger.info("Account '%s' already has %d/%d cards. Target met. Skipping.", nickname, num_cards,
                        TARGET_CARDS)
            update_message = build_level_update_message(account_doc["_id"], true_start_level)
            self.writer_queue.put(update_message)
            return

        cards_needed = TARGET_CARDS - num_cards
        packs_needed = math.ceil(cards_needed / CARDS_PER_PACK)
        chargers_needed = packs_needed * CHARGERS_PER_PACK

        claimed_level_up_bonuses = {lvl for lvl in range(1, true_start_level)}

        deck_proto = api_client._build_default_deck(1, "Default Deck")
        if not api_client.deck_save_v1(session_token, deck_proto):
            raise RuntimeError("DeckSaveV1 Failed.")

        current_chargers = 0
        for battle_count, (battle_id_key, battle_try_id_value) in enumerate(self.battle_playlist):
            if current_chargers >= chargers_needed or self.shutdown_event.is_set():
                break

            if battle_count > 0 and battle_count % REFRESH_TOKEN_LIMIT == 0:
                new_token = api_client.authorize_v1(id_token, device_account, device_identifier)
                if new_token: session_token = new_token

            start_res = api_client.start_stepup_battle_v1(session_token, battle_id_key)
            if not (start_res and start_res.battle_session_token):
                continue

            finish_res = api_client.finish_stepup_battle_v1(session_token, battle_id_key, battle_try_id_value,
                                                            start_res.battle_session_token)
            if not finish_res:
                continue

            if finish_res.HasField("item_acquisition_result"):
                for charger in finish_res.item_acquisition_result.item_state.pack_power_chargers:
                    if charger.type == pack_power_charger_pb2.PackPowerCharger.Types.TYPE_LARGE:
                        current_chargers = charger.amount
                        break

                current_player_exp = int(finish_res.item_acquisition_result.item_state.exp_stock.exp)

                for level, exp_required in EXP_THRESHOLDS.items():
                    if current_player_exp >= exp_required and level not in claimed_level_up_bonuses:
                        chargers_needed -= LEVEL_UP_CHARGER_BONUS
                        claimed_level_up_bonuses.add(level)
                        logger.info("Bonus for level %d applied for '%s'! New target: %d chargers.", level + 1,
                                    nickname, chargers_needed)

        api_client.may_level_up_v1(session_token)

        last_purchase_response = None
        num_ten_packs = packs_needed // 10
        num_one_packs = packs_needed % 10
        total_purchases_made = 0

        if num_ten_packs > 0:
            logger.info("Purchasing %d x 10-pack bundles for '%s'.", num_ten_packs, nickname)
            for _ in range(num_ten_packs):
                if total_purchases_made > 0 and total_purchases_made % 2 == 0:
                    session_token = api_client.authorize_v1(id_token, device_account, device_identifier)
                    if not session_token: raise RuntimeError("Re-auth failed during 10-pack purchase.")
                pack_token = api_client.get_detail_v2(session_token, pack_id)
                if not pack_token: raise RuntimeError("GetDetailV2 failed during 10-pack purchase.")
                response = api_client.purchase_v2(session_token, pack_token, product_id, charger_amount=120,
                                                  pack_power_to_use_amount=10, purchase_quantity_type='AMOUNT_TEN')
                if not response: raise RuntimeError("PurchaseV2 (10-pack) failed.")
                last_purchase_response = response
                total_purchases_made += 1

        if num_one_packs > 0:
            logger.info("Purchasing %d x 1-pack bundles for '%s'.", num_one_packs, nickname)
            for _ in range(num_one_packs):
                if total_purchases_made > 0 and total_purchases_made % 2 == 0:
                    session_token = api_client.authorize_v1(id_token, device_account, device_identifier)
                    if not session_token: raise RuntimeError("Re-auth failed during 1-pack purchase.")
                pack_token = api_client.get_detail_v2(session_token, pack_id)
                if not pack_token: raise RuntimeError("GetDetailV2 failed during 1-pack purchase.")
                response = api_client.purchase_v2(session_token, pack_token, product_id, charger_amount=12,
                                                  pack_power_to_use_amount=1, purchase_quantity_type='AMOUNT_ONE')
                if not response: raise RuntimeError("PurchaseV2 (1-pack) failed.")
                last_purchase_response = response
                total_purchases_made += 1

        if last_purchase_response:
            new_level = int(last_purchase_response.item_acquisition_result.item_state.exp_stock.current_level)
            update_message = build_level_update_message(account_doc["_id"], new_level)
            self.writer_queue.put(update_message)
        else:
            final_level = max(claimed_level_up_bonuses) + 1 if claimed_level_up_bonuses else true_start_level
            update_message = build_level_update_message(account_doc["_id"], final_level)
            self.writer_queue.put(update_message)


def leveler_main_logic(child_id, device_profile_data):
    leveler_instance = Leveler(child_id, device_profile_data)
    if leveler_instance.use_proxy:
        set_ssl_cert_for_process(shared_data.get('shared_ca_path'))

    logger.info("Process started (PID: %d). Waiting for accounts...", os.getpid())

    leveler_conf = config.leveler_settings
    ACCOUNTS_PER_IP = leveler_conf.getint('AccountsPerIp', 8)

    try:
        startup_delay = random.uniform(0, 30.0)
        time.sleep(startup_delay)

        while not leveler_instance.shutdown_event.is_set():
            http_session, baas_client, api_client = None, None, None
            accounts_processed_in_batch = 0

            try:
                logger.info("--- Starting new batch for up to %d accounts ---", ACCOUNTS_PER_IP)
                http_session, baas_client, api_client = leveler_instance._get_new_clients()

                for i in range(ACCOUNTS_PER_IP):
                    if leveler_instance.shutdown_event.is_set():
                        break

                    account_document = None
                    try:
                        account_document = leveler_instance.accounts_queue.get(timeout=1)
                        nickname = account_document.get('nickname', 'N/A')
                        logger.info("Processing account %d/%d: %s", i + 1, ACCOUNTS_PER_IP, nickname)

                        leveler_instance.perform_leveling_cycle(account_document, http_session, baas_client, api_client)

                        logger.info("SUCCESS: Full cycle complete for account '%s'.", nickname)
                        accounts_processed_in_batch += 1

                        if leveler_instance.progress_queue:
                            leveler_instance.progress_queue.put(1)

                    except queue.Empty:
                        logger.info("Account queue is empty. Worker has finished its job.")
                        raise StopIteration

                    except (requests.exceptions.RequestException, RuntimeError) as e:
                        nickname_on_fail = account_document.get('nickname', 'N/A') if account_document else "Unknown"
                        logger.error("CRITICAL ERROR on account '%s': %s. Re-queuing and forcing IP rotation.",
                                     nickname_on_fail, str(e)[:150])
                        if account_document:
                            leveler_instance.accounts_queue.put(account_document)
                        break

            except (requests.exceptions.RequestException, RuntimeError) as e:
                logger.error("Client setup for batch failed: %s. Retrying connection.", str(e)[:150])
                continue

            finally:
                if api_client: api_client.close_channel()
                if http_session: http_session.close()
                if accounts_processed_in_batch > 0:
                    logger.info("--- Batch finished. Processed %d accounts on this IP. ---",
                                accounts_processed_in_batch)

    except StopIteration:
        pass

    finally:
        logger.info("Work complete. Notifying writer and terminating.")
        if leveler_instance.writer_queue:
            leveler_instance.writer_queue.put(None)
