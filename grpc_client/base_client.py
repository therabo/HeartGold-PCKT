from __future__ import annotations

import uuid
import grpc
import logging
from encryption.packer import Packer
from configuration.manger_config import config

logger = logging.getLogger(__name__)


class BaseClient:
    SERVER_ADDRESS = config.endpoints['TakashoGRPC']['ServerAddress']

    def __init__(self, api_key: bytes, device_profile: dict, proxy_config: dict | None = None):
        if not api_key or len(api_key) != 32:
            raise ValueError("A valid 32-byte API key must be provided.")
        self.api_key = api_key
        self.packer = Packer(self.api_key)
        self.device_profile = device_profile
        self.proxy_config = proxy_config
        self._channel = self._create_channel()

    def _create_channel(self):
        credentials = grpc.ssl_channel_credentials()
        channel_options = []
        if self.proxy_config and "full_proxy_url" in self.proxy_config:
            proxy_url = self.proxy_config['full_proxy_url']
            logger.info("Creating gRPC channel with proxy: %s", proxy_url)
            channel_options.append(('grpc.http_proxy', proxy_url))
        else:
            logger.info("Creating standard gRPC channel (no proxy).")
        return grpc.secure_channel(self.SERVER_ADDRESS, credentials, options=channel_options)

    def close_channel(self):
        if self._channel:
            self._channel.close()

    def _make_grpc_call(self, method_path: str, request_proto, response_proto_class, session_token: str = "",
                        include_master_hash: bool = False):

        packed_body = self.packer.pack(request_proto.SerializeToString())

        headers = [
            ("x-takasho-request-id", str(uuid.uuid4())),
            ("x-takasho-session-token", session_token),
            ("x-takasho-sdk-version", config.profile['AppInfo']['TakashoSdkVersion']),
            ("x-takasho-protocol-version", config.profile['AppInfo']['ProtocolVersion']),
            ("x-takasho-platform", "Google"),
            ("x-takasho-app-version", config.profile['AppInfo']['AppVersion']),
            ("x-takasho-build-version", config.profile['AppInfo']['BuildVersion']),
            ("x-takasho-os", config.profile['DeviceInfo']['OsType']),
            ("x-takasho-user-agent", self.device_profile['takasho_user_agent']),
            ("x-takasho-idempotency-key", str(uuid.uuid4())),
            ("x-takasho-request-asset-aladdin-hash", config.headers['StaticHashes']['AssetAladdinHash'])
        ]

        if include_master_hash:
            headers.append(("x-takasho-request-master-memory-aladdin-hash",
                            config.headers['StaticHashes']['MasterMemoryAladdinHash']))

        headers.append(("x-takasho-app-version-hash-key", config.headers['StaticHashes']['AppVersionHashKey']))

        try:
            raw_response = self._channel.unary_unary(
                method=method_path,
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )(packed_body, metadata=headers, timeout=15)

            response_body_bytes = self.packer.unpack(raw_response)
            response_proto = response_proto_class()
            response_proto.ParseFromString(response_body_bytes)
            return response_proto



        except grpc.RpcError as e:
            logger.error("gRPC call to %s failed: %s", method_path, e)
        except Exception as e:
            logger.error("Unpacking/parsing failed for %s response: %s", method_path, e)

        return None
