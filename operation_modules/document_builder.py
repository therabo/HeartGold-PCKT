from typing import Dict, Any, List
from bson import ObjectId


def build_pack_data_object(
        pack_type: str,
        expansion_id: str,
        transaction_id: str,
        validated_cards: List[Dict[str, str]],
        special_card_count: int
) -> Dict[str, Any]:
    return {
        "packType": pack_type,
        "expansionId": expansion_id,
        "transactionId": transaction_id,
        "cards": validated_cards,
        "specialCardCount": special_card_count
    }


def build_god_pack_document(
        account_credentials: Dict[str, Any],
        account_details: Dict[str, Any],
        pack_data: Dict[str, Any]
) -> Dict[str, Any]:
    final_document = {
        "nintendo_id": account_credentials.get("nintendo_id"),
        "nintendo_password": account_credentials.get("nintendo_password"),
        "device_info": {
            "id": account_credentials.get("device_account")
        },

        "nickname": account_details.get("nickname"),
        "friend_id": account_details.get("friend_id"),
        "birth_date": account_details.get("birth_date"),
        "language": account_details.get("language"),
        "level": account_details.get("lv_account"),
        "last_share_date": None,
        "pack": pack_data
    }
    return final_document


def build_level_update_message(doc_id: ObjectId, new_level: int) -> Dict[str, Any]:
    return {
        "type": "update_level",
        "doc_id": doc_id,
        "new_level": new_level
    }
