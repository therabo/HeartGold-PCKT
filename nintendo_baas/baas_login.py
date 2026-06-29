from __future__ import annotations

from typing import Dict, Any, Optional

import requests
import json
import time
import hmac
import hashlib
import base64
import struct
import logging

from configuration.manger_config import config

logger = logging.getLogger(__name__)

class NintendoBaasLogin:

    def __init__(self, device_profile: dict) -> dict | None:
        self.device_profile = device_profile
        self.app_version = config.profile['AppInfo']['AppVersion']
        self.url = config.endpoints['NintendoBaaS']['Url']
        self.audience = config.endpoints['NintendoBaaS']['Audience']
        self.hotp_key = config.secrets['NintendoBaaS']['HotpKey'].encode('utf-8')
        self.issuer = self.hotp_key.decode('utf-8')

    def _b64url_with_padding(self, b: bytes) -> str:
        return base64.urlsafe_b64encode(b).decode()

    def _generate_totp_secret(self) -> str:
        time_counter = int(time.time()) // 600
        time_bytes = struct.pack('>Q', time_counter)
        hmac_sha1 = hmac.new(self.hotp_key, time_bytes, hashlib.sha1).digest()
        offset = hmac_sha1[-1] & 0x0F
        four_bytes = hmac_sha1[offset: offset + 4]
        large_integer = struct.unpack('>I', four_bytes)[0]
        truncated_integer = large_integer & 0x7FFFFFFF
        code = truncated_integer % 100_000_000
        return f"{code:08d}"

    def _make_assertion(self, iat: int, jwt_signing_key: str) -> str:
        header = self._b64url_with_padding(b'{"alg":"HS256"}')
        payload = self._b64url_with_padding(json.dumps(
            {"iss": self.issuer,
             "iat": iat,
             "aud": self.audience},
            separators=(',', ':')
        ).encode())
        signing_input = f"{header}.{payload}".encode()
        signature = self._b64url_with_padding(hmac.new(jwt_signing_key.encode('utf-8'),
                                                       signing_input,
                                                       hashlib.sha256).digest())
        return f"{header}.{payload}.{signature}"

    def _format_accept_language(self, locale: str) -> str:
        primary_lang = locale.split('-')[0]
        return f"{locale}; q=1, {primary_lang}; q=0.5, *; q=0.001"

    def login(
            self,
            session: requests.Session,
            locale: str,
            time_zone: str,
            nintendo_id: Optional[str] = None,
            nintendo_password: Optional[str] = None
    ) -> dict[str, Any] | None:

        iat = int(time.time())
        jwt_signing_key = self._generate_totp_secret()
        assertion = self._make_assertion(iat, jwt_signing_key)

        bnpf_user_agent = (
            f"jp.pokemon.pokemontcgp/{self.app_version} "
            f"{self.device_profile['device_name']}/{self.device_profile['os_version']} "
            f"NPFSDK/{config.profile['AppInfo']['SdkVersion']}"
        )

        headers = {
            "Accept-Encoding": "gzip",
            "Accept-Language": self._format_accept_language(locale),
            "Connection": "Keep-Alive",
            "Content-Type": "application/json",
            "User-Agent": bnpf_user_agent,
            "Host": "1c04691f14f85ad285ebb3d2ffa4aef0.baas.nintendo.com"
        }

        payload = {
            "locale": locale,
            "timeZone": time_zone,
            "timeZoneOffset": int(config.profile['LocaleInfo']['TimeZoneOffset']),
            "manufacturer": "Samsung",
            "deviceName": self.device_profile['device_name'],
            "osType": config.profile['DeviceInfo']['OsType'],
            "osVersion": self.device_profile['os_version'],
            "networkType": config.profile['NetworkInfo']['NetworkType'],
            "carrier": config.profile['NetworkInfo']['Carrier'],
            "appVersion": self.app_version,
            "sdkVersion": config.profile['AppInfo']['SdkVersion'],
            "assertion": assertion
        }

        if nintendo_id and nintendo_password:
            payload["deviceAccount"] = {"id": nintendo_id, "password": nintendo_password}

        resp = session.post(self.url, headers=headers, json=payload, timeout=15)
        resp_json = resp.json()

        try:
            id_token = resp_json["idToken"]

            created_account_details = resp_json.get("createdDeviceAccount")

            if created_account_details:
                return {
                    "id_token": id_token,
                    "nintendo_id": created_account_details.get("id"),
                    "nintendo_password": created_account_details.get("password")
                }
            else:
                return {
                    "id_token": id_token
                }

        except KeyError as e:
            logger.critical("Missing key '%s' in BaaS login response. Response content: %s", e, resp_json)
            return None
