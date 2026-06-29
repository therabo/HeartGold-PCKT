```text
██╗  ██╗███████╗ █████╗ ██████╗ ████████╗ ██████╗  ██████╗ ██╗     ██████╗ 
██║  ██║██╔════╝██╔══██╗██╔══██╗╚══██╔══╝██╔════╝ ██╔═══██╗██║     ██╔══██╗    
███████║█████╗  ███████║██████╔╝   ██║   ██║  ███╗██║   ██║██║     ██║  ██║
██╔══██║██╔══╝  ██╔══██║██╔══██╗   ██║   ██║   ██║██║   ██║██║     ██║  ██║
██║  ██║███████╗██║  ██║██║  ██║   ██║   ╚██████╔╝╚██████╔╝███████╗██████╔╝
╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝╚═════╝
```

### Pokémon TCG Pocket Automation Suite

`HeartGold-PCKT` is an automation suite designed to interact with the API of the mobile game Pokémon TCG Pocket. Its
primary purpose is to automate processes to achieve specific in-game goals. The project is structured into two main
operational modes:

1. **Collector** 🕵️‍♂️: This mode focuses on creating new game accounts in a continuous cycle to open card packs. The
   goal is to find and isolate accounts that have received a "God Pack" (a pack with an exceptionally high number of
   rare cards). Successful accounts are saved to a MongoDB database.
2. **Leveler** 🚀: This mode takes the saved "God Pack" accounts from the database and increases their level by playing
   automated battles.

The project utilizes a multi-process architecture to maximize efficiency, orchestrated by a `Director` that manages
worker processes (Collector or Leveler) and a dedicated `DatabaseWriter` process for asynchronous data persistence.

---

## 🎯 Operational Strategy and Lifecycles

This section describes the high-level strategies and specific lifecycles implemented by the `Collector` and `Leveler`
modules to achieve their goals efficiently and discreetly.

### 1. Stealth and Anonymity Strategy

To operate at scale without being blocked, the bot employs several techniques:

* **Proxy Rotation** 🌐: The bot is designed to route traffic through a rotating proxy service. Each batch of operations
  or even each new process can use a different IP address, simulating connections from distinct and geographically
  distributed users.
* **Device Emulation** 📱: The `configuration/user_agent.ini` file contains a list of real-world user agents from various
  Android device models. Each worker process randomly selects a profile from this list, making each account appear as if
  it's being managed by a unique physical device.
* **Unique Device Identifiers** 🆔: For each new account, unique identifiers (`device_account` and `device_identifier`)
  are generated to reinforce the illusion of a new device registering for the service.

### 2. Collector Lifecycle

The `Collector` does more than just create an account and open a pack. It follows an optimized strategy to maximize the
chances of obtaining a "God Pack" with initial resources before deleting the account and starting over.

The full cycle for a single account is as follows:

1. **Account Creation**: A new account is created via the Nintendo BaaS authentication flow.
2. **Login and Authorization**: A `session_token` is obtained from the Takasho server.
3. **Initial Pack Purchase**: The first two free packs available to a new account are opened using
   the `PackShop/PurchaseV2` gRPC endpoint.
4. **First Check**: The content of the packs is analyzed. If a "God Pack" is found, the account credentials and pack
   data are saved to the database, and the cycle for this account ends successfully.
5. **Strategic Level-Up**: If no "God Pack" is found, the account is leveled up to level 2. This action unlocks 12 "
   chargers" (an in-game currency).
6. **Bonus Pack Purchase**: The 12 chargers are immediately spent to purchase an additional pack.
7. **Second Check**: This pack is also analyzed. If it's a "God Pack," the account is saved.
8. **Account Deletion**: If no "God Pack" has been found after all attempts, the account is permanently deleted via
   the `Player/DeleteAccountV1` endpoint to leave no trace. The process then restarts from step 1.

### 3. Leveler Lifecycle

The `Leveler` has a more complex task: to take an existing "God Pack" account (typically level 1 or 2) and raise it to a
high enough level and with enough cards to unlock pack sharing in Wonder Picks. The strategy is based on accumulating an
in-game currency ("chargers") to buy packs, which in turn provide the necessary experience.

1. **Account Loading**: An account with `level < 10` is retrieved from the database.
2. **Resource Calculation**: The bot calculates the number of cards needed to reach a target (e.g., 230 cards). From
   this, it deduces the number of packs to buy and, consequently, the total number of "chargers" required.
3. **Battle Farming**: To accumulate chargers, the bot begins playing single-player battles.
    * It uses a predefined battle playlist, defined in `battle/battle_lookup.json`. This playlist is sorted by
      difficulty to maximize rewards in the shortest amount of time.
    * Each battle is won automatically by sequentially calling the `SoloBattle/StartStepupBattleV1`
      and `SoloBattle/FinishStepupBattleV1` endpoints.
4. **Level-Up Bonus Management**: The bot tracks the levels gained. Each level-up provides a charger bonus, which is
   subtracted from the total required, optimizing the number of battles that need to be fought.
5. **Bulk Pack Purchase**: Once enough chargers have been accumulated, the bot executes a series of calls
   to `PackShop/PurchaseV2` to buy all the necessary packs in a single session.
6. **Final Update**: After the purchase, the account's new level is calculated based on the experience gained and is
   updated in the database. The process for that account is now complete.

---

## ⚙️ Key Concepts and Internal Workings

This section describes the fundamental technical mechanisms that allow the project to function.

### 1. Authentication and Session Flow

Authentication is a two-step process that first involves Nintendo's BaaS (Backend-as-a-Service) servers and then the
game's gRPC servers (Takasho).

#### a. Nintendo BaaS Authentication and Assertion Generation

The first step is to obtain an `id_token` from Nintendo. This is not a standard login; it requires generating a JWT
assertion token signed with a dynamic key.

1. **Key Generation (Custom TOTP)**: A secret code is generated to serve as the key for signing the JWT. This process,
   implemented in `nintendo_baas/baas_login.py`, is a variant of TOTP (Time-based One-Time Password):
    * The current time is divided by 600, creating a counter that changes every 10 minutes.
    * This counter is hashed via HMAC-SHA1 using a static key (`hotp_key` from the `config.ini` file).
    * The hash result is dynamically truncated (as in HOTP) to produce an 8-digit numerical code.

2. **Assertion Creation (JWT)**: The generated 8-digit code is used as the secret to sign a JWT with the `HS256`
   algorithm. The JWT payload contains information about the issuer (`iss`), audience (`aud`), and creation
   timestamp (`iat`).
   ```json
   {
     "iss": "jp.pokemon.pokemontcgp:c50b2f056cc84fcf8752e6c23bd3819128b923a2",
     "iat": 1722749183,
     "aud": "https://1c04691f14f85ad285ebb3d2ffa4aef0.baas.nintendo.com"
   }
   ```

3. **Login Request**: The JWT assertion is sent to the Nintendo BaaS endpoint along with device details. The response
   contains an `id_token` and, for a new account, the server-generated credentials (`nintendo_id`, `nintendo_password`).

#### b. Authorization with the Game Server (Takasho)

The `id_token` obtained from Nintendo is used to authenticate with the game's gRPC API.

1. The `System/AuthorizeV1` gRPC call is made, sending the `id_token`.
2. If authorization is successful, the server responds with a `session_token`. This token is required for all subsequent
   authenticated gRPC calls.

### 2. Encryption Layer

All communication with the Takasho gRPC API is protected by a custom encryption layer. This layer is implemented in
the `encryption` module.

#### a. CcbCipher: The Custom Stream Cipher

The core of the encryption is `CcbCipher`, a custom stream cipher based on the ChaCha family of algorithms.

* **State**: It operates on a 512-bit internal state (16 32-bit integers).
* **Input**: It uses a 256-bit key and a 96-bit nonce.
* **Unique Characteristic**: Unlike standard ChaCha20, the number of transformation rounds is not fixed (20). It is
  calculated dynamically upon cipher initialization based on a value derived from the key, nonce, and a static lookup
  table (`RoundGaps` in `config.ini`). This makes the implementation non-standard and application-specific.
* **Operation**: For each 64-byte block of data, it generates a keystream block by repeatedly applying add-rotate-xor
  functions. The keystream is then XORed with the plaintext data to produce the ciphertext (or vice versa for
  decryption).

#### b. Server Token Decryption

Before communication can begin, the client must decrypt a static, server-provided token (`ServerTokenString`
in `config.ini`) to obtain the communication key.

1. The token is a Base64URL-encoded string composed of two parts, separated by a dot.
2. The `token_parser.py` module uses `CcbCipher` with a static decryption key and nonce (also present in `config.ini`).
3. The two parts of the token are decrypted to yield:
    * `pinned_cert_fingerprint`: A 32-byte key that acts as the session's "API key".
    * `common_key`: A 32-byte key used to encrypt gRPC payloads.

#### c. Packing and Unpacking gRPC Payloads

Every gRPC message (request and response) is processed by the `Packer` (`encryption/packer.py`) before transmission.

**`pack` process (sending):**

1. **Integrity (HMAC)**: An HMAC-SHA256 hash of the Protobuf message body is calculated. The key for the HMAC is the
   concatenation of the `common_key` and a 12-byte nonce.
2. **Concatenation**: The HMAC hash is prepended to the message body.
3. **Compression**: The combined data (HMAC + body) is compressed using the DEFLATE algorithm (raw, without a zlib
   header).
4. **Encryption**: The compressed block is encrypted using `CcbCipher` with the `common_key` and the same 12-byte nonce
   used for the HMAC.
5. **Final Payload**: The 12-byte nonce is prepended to the ciphertext. The result (`nonce + ciphertext`) is the final
   payload sent over the network.

**`unpack` process (receiving):**
The process is the exact inverse:

1. Separate the nonce from the ciphertext.
2. Decrypt the ciphertext using `CcbCipher` with the `common_key` and nonce.
3. Decompress the result.
4. Separate the received HMAC from the message body.
5. Recalculate the HMAC on the message body and compare it in constant time (`hmac.compare_digest`) with the received
   one to ensure integrity and authenticity.

### 3. gRPC Communication

All interactions with the game's API occur via gRPC. The `BaseClient` class (`grpc_client/base_client.py`) abstracts the
communication logic.

* **Call Wrapper**: The `_make_grpc_call` method manages the entire lifecycle of a request.
* **Serialization**: The Protobuf request body is first serialized into bytes, then processed by the `Packer` as
  described above.
* **Custom Headers**: Each gRPC request includes a series of custom HTTP/2 headers, which are crucial for acceptance by
  the server. The most important ones are:
    * `x-takasho-request-id`: A unique UUID for the request.
    * `x-takasho-session-token`: The session token obtained from `AuthorizeV1`.
    * `x-takasho-sdk-version`, `x-takasho-app-version`, `x-takasho-build-version`: Specific versions of the application
      and SDK.
    * `x-takasho-request-asset-aladdin-hash`, `x-takasho-request-master-memory-aladdin-hash`: Static hashes that likely
      serve to validate the client's game asset version.
* **Deserialization**: The raw response received from the server is passed to the `Packer` for unpacking. The resulting
  plaintext bytes are finally parsed into the corresponding Protobuf response object.

---

## 📂 Project Structure

A brief overview of the main directories:

* `configuration/`: Contains all configuration files, including secrets, endpoints, module settings, and device user
  agents.
* `encryption/`: Implements the custom encryption logic (`CcbCipher`), the payload packer (`Packer`), and the server
  token parser.
* `grpc_client/`: Contains the base gRPC client and the implementation of specific player API
  methods (`PlayerApiClient`).
* `nintendo_baas/`: Manages authentication with Nintendo's servers and the generation of device identities.
* `operation_modules/`: Contains the high-level business logic. `Director` orchestrates the processes, `Collector`
  and `Leveler` execute the tasks, and `DatabaseWriter` handles data persistence.
* `ui/`: Implements the command-line user interface based on `rich` and `questionary`.
* `director_main.py`: The application's entry point, which starts the `Director` and manages the program's lifecycle.