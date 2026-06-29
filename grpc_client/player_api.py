from __future__ import annotations
import random
import uuid
from datetime import datetime

from .base_client import BaseClient
from protobuf.generated.takasho.schema.lettuce_server.resource.system import device_info_pb2, platform_type_pb2
from protobuf.generated.takasho.schema.lettuce_server.resource.player_settings import info_pb2
from protobuf.generated.takasho.schema.lettuce_server.resource.item import pack_power_charger_pb2
from protobuf.generated.takasho.schema.lettuce_server.resource.pokemon import energy_type_pb2
from protobuf.generated.takasho.schema.lettuce_server.resource.card import card_instance_pb2
from protobuf.generated.takasho.schema.lettuce_server.resource.language import language_pb2

from protobuf.generated.takasho.schema.lettuce_server.player_api import (
    save_my_profile_v1_pb2,
    player_delete_account_v1_pb2,
    system_authorize_v1_pb2,
    system_login_v1_pb2,
    pack_shop_purchase_v2_pb2,
    pack_get_detail_v2_pb2,
    player_level_may_level_up_v1_pb2,
    deck_save_v1_pb2,
    solo_battle_start_stepup_battle_v1_pb2,
    solo_battle_finish_stepup_battle_v1_pb2,
    player_resources_sync_v1_pb2,
    my_profile_v1_pb2
)
from protobuf.generated.takasho.schema.lettuce_server.resource.pack import (
    pack_power_to_use_pb2,
    pack_power_heal_items_pb2,
)
from protobuf.generated.takasho.schema.lettuce_server.resource.deck import (
    deck_pb2,
    deck_slot_pb2,
    deck_main_card_type_pb2,
    deck_case_type_pb2
)

from protobuf.generated.takasho.schema.lettuce_server.resource.solo_battle import (
    solo_battle_deck_pb2,
    solo_battle_result_type_pb2,
    solo_battle_try_progress_pb2,
    solo_battle_in_game_statistics_pb2
)


class PlayerApiClient(BaseClient):

    def authorize_v1(self, id_token: str, device_account: str, device_identifier: str) -> str | None:
        request = system_authorize_v1_pb2.SystemAuthorizeV1.Types.Request(
            device_account=device_account,
            device_info=device_info_pb2.DeviceInfo(
                platform=platform_type_pb2.PLATFORM_TYPE_GOOGLE,
                identifier=device_identifier,
            ),
            id_token=id_token,
        )
        response = self._make_grpc_call(
            method_path="/takasho.schema.lettuce_server.player_api.System/AuthorizeV1",
            request_proto=request,
            response_proto_class=system_authorize_v1_pb2.SystemAuthorizeV1.Types.Response
        )
        return response.session_token if response else None

    def login_v1(self, session_token: str, language_type, country_code: str, account_details: dict):
        random_year = random.randint(1990, 2004)
        random_month = random.randint(1, 12)

        birth_date_obj = datetime(random_year, random_month, 1)
        account_details['birth_date'] = birth_date_obj

        request = system_login_v1_pb2.SystemLoginV1.Types.Request(
            language_type=language_type,
            third_party_data_provision_version_approved="1.0.0",
            privacy_policy_consent_version_approved="1.0.0",
            terms_of_service_consent_version_approved="1.0.0",
            country_region_code=country_code,
            year_num_of_birth=random_year,
            month_num_of_birth=random_month,
            age_gate_type=info_pb2.Info.Types.AGE_GATE_TYPE_A
        )
        self._make_grpc_call(
            method_path="/takasho.schema.lettuce_server.player_api.System/LoginV1",
            request_proto=request,
            response_proto_class=system_login_v1_pb2.SystemLoginV1.Types.Response,
            session_token=session_token,
            include_master_hash=True
        )

    def my_profile_v1(self, session_token: str) -> tuple[int, int] | None:

        request = my_profile_v1_pb2.MyProfileV1.Types.Request()

        response = self._make_grpc_call(
            method_path="/takasho.schema.lettuce_server.player_api.PlayerProfile/MyProfileV1",
            request_proto=request,
            response_proto_class=my_profile_v1_pb2.MyProfileV1.Types.Response,
            session_token=session_token,
            include_master_hash=True
        )

        if response:
            player_exp = response.required_experience
            num_cards = int(response.profile.number_of_cards)
            return player_exp, num_cards

        return None

    def save_profile(self, session_token: str, nickname: str, icon_id: str, message_id: str):
        request = save_my_profile_v1_pb2.SaveMyProfileV1.Types.Request(
            nickname=nickname,
            icon_id=icon_id,
            message_id=message_id
        )
        response = self._make_grpc_call(
            method_path="/takasho.schema.lettuce_server.player_api.PlayerProfile/SaveMyProfileV1",
            request_proto=request,
            response_proto_class=save_my_profile_v1_pb2.SaveMyProfileV1.Types.Response,
            session_token=session_token,
            include_master_hash=True
        )

        return response

    def delete_account_v1(self, session_token: str):
        request = player_delete_account_v1_pb2.PlayerDeleteAccountV1.Types.Request()

        method_path = "/takasho.schema.lettuce_server.player_api.Player/DeleteAccountV1"

        response = self._make_grpc_call(
            method_path=method_path,
            request_proto=request,
            response_proto_class=player_delete_account_v1_pb2.PlayerDeleteAccountV1.Types.Response,
            session_token=session_token,
            include_master_hash=True
        )

        return response is not None

    def get_detail_v2(self, session_token: str, pack_id: str) -> str | None:
        request = pack_get_detail_v2_pb2.PackGetDetailV2.Types.Request(
            pack_id=pack_id
        )
        response = self._make_grpc_call(
            method_path="/takasho.schema.lettuce_server.player_api.Pack/GetDetailV2",
            request_proto=request,
            response_proto_class=pack_get_detail_v2_pb2.PackGetDetailV2.Types.Response,
            session_token=session_token,
            include_master_hash=True
        )
        return response.pack_consistent_token if response else None

    def purchase_v2(
            self,
            session_token: str,
            pack_consistent_token: str,
            product_id: str,
            charger_amount: int | None = None,
            pack_power_to_use_amount: int = 1,
            purchase_quantity_type: str = "AMOUNT_ONE",
            do_share: bool = True
    ):

        amount_enum_value = pack_shop_purchase_v2_pb2.PackShopPurchaseV2.Types.Request.Types.AMOUNT_ONE
        if purchase_quantity_type == "AMOUNT_TEN":
            amount_enum_value = pack_shop_purchase_v2_pb2.PackShopPurchaseV2.Types.Request.Types.AMOUNT_TEN

        use_powers_payload = [
            pack_power_to_use_pb2.PackPowerToUse(
                power_id="PACK_POWER_NORMAL",
                amount=pack_power_to_use_amount
            )
        ]

        request_params = {
            'pack_consistent_token': pack_consistent_token,
            'transaction_id': str(uuid.uuid4()),
            'product_id': product_id,
            'amount': amount_enum_value,
            'use_powers': use_powers_payload,
            'do_share': do_share
        }

        if charger_amount is not None and charger_amount > 0:
            charger = pack_power_charger_pb2.PackPowerCharger(
                type=pack_power_charger_pb2.PackPowerCharger.Types.TYPE_LARGE,
                amount=charger_amount
            )
            heal_items_payload = pack_power_heal_items_pb2.PackPowerHealItems(
                chargers=[charger],
                vc_amount=0
            )
            request_params['heal_items'] = heal_items_payload

        request = pack_shop_purchase_v2_pb2.PackShopPurchaseV2.Types.Request(**request_params)

        response = self._make_grpc_call(
            method_path="/takasho.schema.lettuce_server.player_api.PackShop/PurchaseV2",
            request_proto=request,
            response_proto_class=pack_shop_purchase_v2_pb2.PackShopPurchaseV2.Types.Response,
            session_token=session_token,
            include_master_hash=True
        )

        return response

    def may_level_up_v1(self,
                        session_token: str) -> player_level_may_level_up_v1_pb2.PlayerLevelMayLevelUpV1.Types.Response | None:
        request = player_level_may_level_up_v1_pb2.PlayerLevelMayLevelUpV1.Types.Request()

        response = self._make_grpc_call(
            method_path="/takasho.schema.lettuce_server.player_api.PlayerLevel/MayLevelUpV1",
            request_proto=request,
            response_proto_class=player_level_may_level_up_v1_pb2.PlayerLevelMayLevelUpV1.Types.Response,
            session_token=session_token,
            include_master_hash=True
        )

        return response

    def _build_default_deck(self, deck_id: int, deck_name: str) -> deck_pb2.Deck:
        card_data_definitiva = [
            # card_id, expansion_id
            ("PK_10_007260_00", "L1"),
            ("PK_10_007500_00", "L1"),
            ("PK_10_000840_00", "L1"),
            ("PK_10_007580_00", "L1"),
            ("PK_10_007270_00", "L1"),
            ("PK_10_001600_00", "L1"),
            ("PK_10_007670_00", "L1"),
            ("PK_10_001610_00", "L1"),
            ("PK_10_007680_00", "L1"),
            ("PK_10_001890_00", "L1"),
            ("PK_10_001890_00", "L1"),
            ("PK_10_001900_00", "L1"),
            ("PK_10_001900_00", "L1"),
            ("PK_10_001980_00", "L1"),
            ("PK_10_007930_00", "L1"),
            ("TR_90_000030_00", "L1"),
            ("TR_90_000030_00", "L1"),
            ("TR_90_000040_00", "L1"),
            ("TR_90_000040_00", "L1"),
            ("TR_10_000650_00", "L1")
        ]

        slots_list = []
        for i, (card_id, expansion_id) in enumerate(card_data_definitiva):
            slot_number = i + 1

            card_inst = card_instance_pb2.CardInstance(
                card_id=card_id,
                lang=language_pb2.LANGUAGE_IT,
                expansion_id=expansion_id
            )

            slot = deck_slot_pb2.DeckSlot(
                slot_number=slot_number,
                card_instance=card_inst
            )

            if slot_number == 1:
                slot.main_card_type = deck_main_card_type_pb2.DECK_MAIN_CARD_TYPE_MAIN
            elif slot_number == 2:
                slot.main_card_type = deck_main_card_type_pb2.DECK_MAIN_CARD_TYPE_SUB1
            elif slot_number == 3:
                slot.main_card_type = deck_main_card_type_pb2.DECK_MAIN_CARD_TYPE_SUB2

            slots_list.append(slot)

        deck_to_save = deck_pb2.Deck(
            deck_id=deck_id,
            deck_name=deck_name,
            slots=slots_list,
            energy_types=[energy_type_pb2.ENERGY_TYPE_FIRE],
            deck_case_type=deck_case_type_pb2.DECK_CASE_TYPE_GRASS,
            deck_shield_id="",
            coin_skin_id="COIN_100160_MONSTERBALL",
            play_mat_id=""
        )
        return deck_to_save

    def deck_save_v1(self, session_token: str, deck_proto: deck_pb2.Deck):
        request = deck_save_v1_pb2.DeckSaveV1.Types.Request(deck=deck_proto)

        endpoint = "/takasho.schema.lettuce_server.player_api.Deck/SaveV1"

        response = self._make_grpc_call(
            endpoint,
            request,
            deck_save_v1_pb2.DeckSaveV1.Types.Response,
            session_token,
            include_master_hash=True
        )

        return response

    def start_stepup_battle_v1(self, session_token: str,
                               battle_id: str) -> solo_battle_start_stepup_battle_v1_pb2.SoloBattleStartStepupBattleV1.Types.Response | None:
        deck_payload = solo_battle_deck_pb2.SoloBattleDeck(
            type=solo_battle_deck_pb2.SoloBattleDeck.Types.DECK_TYPE_MY_DECK,
            my_deck_id=1
        )
        request = solo_battle_start_stepup_battle_v1_pb2.SoloBattleStartStepupBattleV1.Types.Request(
            solo_stepup_battle_id=battle_id,
            deck=deck_payload
        )
        response = self._make_grpc_call(
            method_path="/takasho.schema.lettuce_server.player_api.SoloBattle/StartStepupBattleV1",
            request_proto=request,
            response_proto_class=solo_battle_start_stepup_battle_v1_pb2.SoloBattleStartStepupBattleV1.Types.Response,
            session_token=session_token,
            include_master_hash=True
        )
        return response

    def finish_stepup_battle_v1(self, session_token: str, battle_id: str, battle_try_id: str,
                                battle_session_token: str) -> solo_battle_finish_stepup_battle_v1_pb2.SoloBattleFinishStepupBattleV1.Types.Response | None:

        deck_obj = solo_battle_deck_pb2.SoloBattleDeck(
            type=solo_battle_deck_pb2.SoloBattleDeck.Types.DECK_TYPE_MY_DECK,
            my_deck_id=1
        )

        stats_obj = solo_battle_in_game_statistics_pb2.SoloBattleInGameStatistics(
            turn_num=10, pre=True, player_point=6, target_player_point=0, is_concede=False, auto_flg=False
        )

        result_type_enum_val = solo_battle_result_type_pb2.SOLO_BATTLE_RESULT_TYPE_RESULT_TYPE_WIN

        progress_obj = solo_battle_try_progress_pb2.SoloBattleTryProgress(
            battle_try_id=battle_try_id,
            current_count=4
        )
        progresses_list = [progress_obj]

        request_proto = solo_battle_finish_stepup_battle_v1_pb2.SoloBattleFinishStepupBattleV1.Types.Request(
            battle_id=battle_id,
            result_type=result_type_enum_val,
            battle_try_progresses=progresses_list,
            battle_session_token=battle_session_token,
            deck=deck_obj,
            battle_stats=stats_obj
        )

        response = self._make_grpc_call(
            method_path="/takasho.schema.lettuce_server.player_api.SoloBattle/FinishStepupBattleV1",
            request_proto=request_proto,
            response_proto_class=solo_battle_finish_stepup_battle_v1_pb2.SoloBattleFinishStepupBattleV1.Types.Response,
            session_token=session_token,
            include_master_hash=True
        )
        return response

    def sync_v1(self, session_token: str) -> player_resources_sync_v1_pb2.PlayerResourcesSyncV1.Types.Response | None:

        request = player_resources_sync_v1_pb2.PlayerResourcesSyncV1.Types.Request()

        response = self._make_grpc_call(
            method_path="/takasho.schema.lettuce_server.player_api.PlayerResources/SyncV1",
            request_proto=request,
            response_proto_class=player_resources_sync_v1_pb2.PlayerResourcesSyncV1.Types.Response,
            session_token=session_token,
            include_master_hash=True
        )

        return response
