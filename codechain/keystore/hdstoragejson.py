import binascii
import os
import uuid

from Crypto.Cipher import AES
from Crypto.Util import Counter

from ..crypto import blake256
from .errors import ErrorCode
from .errors import KeystoreError
from .pbkdf2 import pbkdf2


def encode(seed: str, passphrase: str, meta: str):
    seed_hash = blake256(seed)
    salt = os.urandom(32)
    iv = os.urandom(16)

    kdf = "pbkdf2"
    kdf_params = {
        "dklen": 32,
        "salt": binascii.hexlify(salt).decode("ascii"),
        "c": 262144,
        "prf": "hmac-sha256",
    }
    derived_key = pbkdf2(
        passphrase.encode("utf-8"), salt, kdf_params["c"], kdf_params["dklen"], "sha256"
    )
    ctr = Counter.new(128, initial_value=int.from_bytes(iv, byteorder="big"))
    cipher = AES.new(derived_key[:16], AES.MODE_CTR, counter=ctr)
    ciphertext = cipher.encrypt(seed)
    mac = blake256(derived_key[16:32] + ciphertext)

    return {
        "crypto": {
            "ciphertext": binascii.hexlify(ciphertext).decode("ascii"),
            "cipherparams": {"iv": binascii.hexlify(iv).decode("ascii")},
            "cipher": "aes-128-ctr",
            "kdf": kdf,
            "kdfparams": kdf_params,
            "mac": mac,
        },
        "id": str(uuid.uuid4()),
        "version": 3,
        "seedHash": binascii.hexlify(seed_hash).decode("ascii"),
        "meta": meta,
    }


def decode(json, passphrase: str) -> str:
    kdfparams = json["crypto"]["kdfparams"]
    derivedKey = pbkdf2(
        passphrase.encode("utf-8"),
        bytes.fromhex(kdfparams["salt"]),
        kdfparams["c"],
        kdfparams["dklen"],
        "sha256",
    )
    ciphertext = bytes.fromhex(json["crypto"]["ciphertext"])
    mac = blake256(derivedKey[16:32] + ciphertext)

    if mac != json["crypto"]["mac"]:
        raise KeystoreError(ErrorCode.DECRYPTIONFAILED)

    if json["crypto"]["cipher"] != "aes-128-ctr":
        raise KeystoreError(ErrorCode.DECRYPTIONFAILED)

    iv = int(json["crypto"]["cipherparams"]["iv"], 16)
    ctr = Counter.new(128, initial_value=iv)
    decipher = AES.new(derivedKey[0:16], AES.MODE_CTR, counter=ctr)
    seed = decipher.decrypt(ciphertext)

    seed_hash = binascii.hexlify(blake256(seed)).decode("ascii")
    if seed_hash != json["seedHash"]:
        raise KeystoreError(ErrorCode.DECRYPTIONFAILED)

    return binascii.hexlify(seed).decode("ascii")
