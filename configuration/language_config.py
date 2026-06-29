from protobuf.generated.takasho.schema.lettuce_server.resource.language import language_pb2

LANGUAGE_CONFIGS = {
    "it": {
        "name": "Italiano",
        "locale": "it-IT",
        "time_zone": "Europe/Rome",
        "country_code": "IT",
        "language_type": language_pb2.LANGUAGE_IT
    },
    "en": {
        "name": "English",
        "locale": "en-US",
        "time_zone": "Europe/Rome",
        "country_code": "US",
        "language_type": language_pb2.LANGUAGE_EN
    },
    "jp": {
        "name": "Japanese",
        "locale": "ja-JP",
        "time_zone": "Europe/Rome",
        "country_code": "JP",
        "language_type": language_pb2.LANGUAGE_JA
    }
}

AVAILABLE_LANGUAGES = list(LANGUAGE_CONFIGS.keys())
