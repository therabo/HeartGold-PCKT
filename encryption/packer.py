"""
Handles the serialization pipeline for gRPC message bodies, applying a
sequence of integrity, compression, and encryption transformations.

This class encapsulates the logic required to prepare a raw Protobuf message
for transmission over the wire and to reverse the process upon reception,
ensuring data integrity and confidentiality.

The `pack` operation follows these steps:
1.  **Integrity**: A 32-byte HMAC-SHA256 tag is computed. The HMAC key is
    derived from the concatenation of the `common_key` and a 12-byte nonce.
2.  **Concatenation**: The HMAC tag is prepended to the raw Protobuf body.
3.  **Compression**: The combined data (HMAC + body) is compressed using
    raw DEFLATE.
4.  **Encryption**: The compressed data is encrypted using the `CcbCipher`
    stream cipher, keyed with the same `common_key` and nonce.
5.  **Final Payload**: The 12-byte nonce is prepended to the ciphertext to
    form the final payload.

The `unpack` operation reverses this pipeline, performing decryption,
decompression, and finally, a constant-time verification of the HMAC tag
to protect against timing attacks.

:param common_key: A 32-byte secret key used for both HMAC and encryption.

"""

import os
import hmac
import hashlib
import zlib
from .ccb_cipher import CcbCipher


class Packer:
    def __init__(self, common_key: bytes):
        if len(common_key) != 32:
            raise ValueError("CommonKey must be 32 bytes.")
        self.common_key = common_key

    def _compute_hash(self, nonce: bytes, body: bytes) -> bytes:
        return hmac.new(self.common_key + nonce, body, hashlib.sha256).digest()

    def _compress_block(self, data_to_compress: bytes) -> bytes:

        compress_obj = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)

        compressed = compress_obj.compress(data_to_compress)
        compressed += compress_obj.flush()

        return compressed

    def pack_with_nonce(self, nonce: bytes, protobuf_body: bytes) -> bytes:
        if len(nonce) != 12:
            raise ValueError("Nonce must be 12 bytes")

        integrity_hash = self._compute_hash(nonce, protobuf_body)
        data_to_compress = integrity_hash + protobuf_body

        compressed_data = self._compress_block(data_to_compress)

        cipher = CcbCipher(self.common_key, nonce)
        encrypted_data = cipher.transform(compressed_data)

        return nonce + encrypted_data

    def pack(self, protobuf_body: bytes) -> bytes:
        nonce = os.urandom(12)
        return self.pack_with_nonce(nonce, protobuf_body)

    def unpack(self, packed_payload: bytes) -> bytes:
        assert len(packed_payload) >= 12 + 32, "Payload too short to be valid."

        nonce, encrypted_data = packed_payload[:12], packed_payload[12:]
        cipher = CcbCipher(self.common_key, nonce)
        compressed_data = cipher.transform(encrypted_data)
        decompressed_data = zlib.decompress(compressed_data, wbits=-15)

        assert len(decompressed_data) >= 32, "Unpacked data too short, missing hash."
        received_hash = decompressed_data[:32]
        protobuf_body = decompressed_data[32:]

        expected_hash = self._compute_hash(nonce, protobuf_body)
        assert hmac.compare_digest(received_hash, expected_hash), "Integrity verification (HMAC) failed!"

        return protobuf_body
