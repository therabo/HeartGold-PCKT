"""
Provides utility functions for generating device-specific identifiers
required for authenticating with the Takasho API.

This module contains two key functions:
- `generate_takasho_identifier`: Creates a deterministic, repeatable hardware
  fingerprint by hashing device properties (model, platform, type). This is
  used to consistently identify a specific device configuration.
- `generate_takasho_device_account`: Generates a random, non-deterministic
  32-character alphanumeric string for use as a unique account ID during new
  device registrations, leveraging a cryptographically secure random source.

"""

import os
import hashlib

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_DEVICE_ACCOUNT_LENGTH = 32


def generate_takasho_identifier(
        device_model: str,
        platform: str = "Android",
        device_type: str = "Handheld"
) -> str:
    seed_string = f"{device_model}:{platform}:{device_type}"
    seed_bytes = seed_string.encode('utf-8')
    hashed_bytes = hashlib.sha256(seed_bytes).digest()
    return hashed_bytes.hex()


def generate_takasho_device_account() -> str:
    random_bytes = os.urandom(_DEVICE_ACCOUNT_LENGTH)

    device_account_chars = [
        _ALPHABET[byte_val % len(_ALPHABET)]
        for byte_val in random_bytes
    ]

    return "".join(device_account_chars)
