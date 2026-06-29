from __future__ import annotations
import traceback
from protobuf.generated.takasho.schema.lettuce_server.player_api import pack_shop_purchase_v2_pb2
from protobuf.generated.takasho.schema.lettuce_server.resource.language import language_pb2
from operation_modules.document_builder import build_pack_data_object

LANGUAGE_TO_PACK_TYPE_MAP = {
    language_pb2.LANGUAGE_IT: "GodPackIT",
    language_pb2.LANGUAGE_EN: "GodPackEN",
    language_pb2.LANGUAGE_JA: "GodPackJP",
    language_pb2.LANGUAGE_CN: "GodPackCN",
    language_pb2.LANGUAGE_FR: "GodPackFR",
    language_pb2.LANGUAGE_DE: "GodPackDE",
    language_pb2.LANGUAGE_ES: "GodPackES",
    language_pb2.LANGUAGE_BR: "GodPackBR",
    language_pb2.LANGUAGE_KR: "GodPackKR",
    language_pb2.LANGUAGE_UNSPECIFIED: "GodPack"
}


def filter_god_pack(
        response_proto: pack_shop_purchase_v2_pb2.PackShopPurchaseV2.Types.Response,
        card_lookup: dict
) -> dict | None:
    try:

        unpack_order = response_proto.unpack_orders[0]
        card_instances = unpack_order.produces.card_instances

        pack_type = LANGUAGE_TO_PACK_TYPE_MAP.get(unpack_order.lang, "GodPackUnknown")

        validated_cards_data = []
        for item in card_instances:
            card_id = item.card_instance.card_id

            if card_id not in card_lookup:
                return None

            rarity = card_lookup[card_id]
            validated_cards_data.append({"cardId": card_id, "rarity": rarity})

        special_card_count = sum(1 for card in validated_cards_data if card["rarity"] == "SR_AND_SAR")

        pack_data_to_save = build_pack_data_object(
            pack_type=pack_type,
            expansion_id=response_proto.purchase_order.expansion_id,
            transaction_id=response_proto.purchase_order.transaction_id,
            validated_cards=validated_cards_data,
            special_card_count=special_card_count
        )

        return pack_data_to_save

    except (AttributeError, IndexError, TypeError) as e:
        print(f"  [FILTER] UNEXPECTED STRUCTURE ERROR: The server response format may have changed. Error: {e}.")
        traceback.print_exc()
        return None
