"""
Parses and decrypts the server-provided authentication token.

This function handles the proprietary token format used by the Takasho gRPC
server. The token is expected to be a string composed of two Base64URL-encoded
parts, separated by a dot.

The process involves:
1.  Loading a static, hardcoded decryption key and nonce from the application
    configuration.
2.  Initializing the `CcbCipher` with this key and nonce.
3.  Splitting the input token string into its two constituent parts.
4.  Decoding each Base64URL-encoded part into its raw encrypted byte representation.
5.  Using the initialized cipher to decrypt both parts. The first part
    decrypts to the `pinned_cert_fingerprint`, and the second part decrypts
    to the `common_key` used for subsequent gRPC payload encryption.

:param token_string: The dot-separated, Base64URL-encoded server token.
:return: A dictionary containing the decrypted `common_key` and `pinned_cert_fingerprint`.

"""

import base64
from configuration.manger_config import config

from .ccb_cipher import CcbCipher


def parse_base64_url(b64url_string: str) -> bytes:
    b64_string = b64url_string.replace('-', '+').replace('_', '/')
    padding_needed = 4 - (len(b64_string) % 4)
    if padding_needed != 4:
        b64_string += "=" * padding_needed
    return base64.b64decode(b64_string)


def parse_server_token(token_string: str) -> dict:
    key = bytes.fromhex(config.secrets['TakashoGRPC']['ServerTokenDecryptionKey'])
    nonce = bytes.fromhex(config.secrets['TakashoGRPC']['ServerTokenDecryptionNonce'])

    cipher = CcbCipher(key, nonce)

    parts = token_string.split('.')
    if len(parts) != 2:
        raise ValueError("Invalid serverToken format.")

    pinned_cert_encrypted = parse_base64_url(parts[0])
    common_key_encrypted = parse_base64_url(parts[1])

    pinned_cert_decrypted = cipher.transform(pinned_cert_encrypted)
    common_key_decrypted = cipher.transform(common_key_encrypted)

    return {
        "common_key": common_key_decrypted,
        "pinned_cert_fingerprint": pinned_cert_decrypted
    }
