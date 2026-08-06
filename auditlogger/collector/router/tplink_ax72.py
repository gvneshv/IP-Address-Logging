"""TplinkRouter variant for firmware that signs login requests with nested RSA-OAEP chunking instead of the flat PKCS1v1.5 chunking tplinkrouterc6u's TplinkRouter class assumes.

Confirmed against a real Archer AX72 by capturing and replaying a live login (see project history for the full derivation):
the device's login-signature RSA key is 512-bit, and RSA-OAEP's max plaintext per block for that key size (22 bytes) is smaller than PKCS1v1.5's (53 bytes).
tplinkrouterc6u's flat 53-char chunking - sized for PKCS1v1.5 - silently produces the wrong number of RSA blocks against this firmware,
and the router rejects the resulting signature with 403.
Everything else about the login flow (password RSA key, AES wrapping, response format) matches TplinkRouter exactly,
so this only overrides the three pieces confirmed to differ:
  1. Signature chunking: nested 53-char outer / OAEP-max-size inner, instead of flat 53-char PKCS1v1.5.
  2. Password hash: SHA-256(username+password), instead of MD5.
  3. Login body: no trailing '&confirm=true'.

Assumption not yet stress-tested: AES key/iv generation is inherited unchanged from EncryptionWrapper (16 random hex chars).
The live-fire test that confirmed this scheme used 16 decimal digits instead and worked;
hex chars are still just 16 raw ASCII bytes used consistently for both encrypting the AES payload and signing the 'k=/i=' string,
so there's no known reason hex wouldn't work too - but if login ever fails specifically at the signature step, this generation strategy is the first thing to revisit.
"""

from __future__ import annotations
from binascii import hexlify
from hashlib import sha256

from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey.RSA import construct
from tplinkrouterc6u.client.c6u import TplinkRouter
from tplinkrouterc6u.common.encryption import EncryptionWrapper


class _OAEPEncryptionWrapper(EncryptionWrapper):
    """AES/password handling is unchanged from the base wrapper - only the RSA signature chunking differs, since that's the piece confirmed wrong for this firmware."""

    @staticmethod
    def _oaep_chunk_bytes(nn: str, hash_len_bytes: int = 20) -> int:
        # SHA-1 (hash_len_bytes=20) is the only hash that fits this 512-bit key's OAEP overhead (2*hash_len+2 <= modulus_bytes);
        # computed from the actual modulus so this keeps working if the key size changes.
        modulus_bytes = len(nn) // 2
        return modulus_bytes - 2 * hash_len_bytes - 2

    @staticmethod
    def _rsa_encrypt_oaep(data: bytes, nn: str, ee: str) -> str:
        key = construct((int(nn, 16), int(ee, 16)))
        return hexlify(PKCS1_OAEP.new(key).encrypt(data)).decode()

    def get_signature(self, seq: int, is_login: bool, hash: str, nn: str, ee: str) -> str:
        if is_login:
            s = '{}&h={}&s={}'.format(self._get_aes_string(), hash, seq)
        else:
            s = 'h={}&s={}'.format(hash, seq)

        chunk_len = self._oaep_chunk_bytes(nn)
        sign = ''
        pos = 0
        while pos < len(s):
            outer_piece = s[pos:pos + 53].encode()
            pos += 53
            inner_pos = 0
            while inner_pos < len(outer_piece):
                sub = outer_piece[inner_pos:inner_pos + chunk_len]
                sign += self._rsa_encrypt_oaep(sub, nn, ee)
                inner_pos += chunk_len
        return sign


class TplinkRouterAX72(TplinkRouter):
    """TplinkRouter for firmware using RSA-OAEP signing and SHA-256 password hashing (confirmed on an Archer AX72),
    instead of the PKCS1v1.5/MD5 scheme TplinkRouter assumes."""

    _encryption = _OAEPEncryptionWrapper()

    @staticmethod
    def _get_login_data(crypted_pwd: str) -> str:
        return 'operation=login&password={}'.format(crypted_pwd)

    def _prepare_data(self, data: str) -> dict:
        encrypted_data = self._encryption.aes_encrypt(data)
        data_len = len(encrypted_data)
        hash = sha256((self.username + self.password).encode()).hexdigest()

        sign = self._encryption.get_signature(
            int(self._seq) + data_len,
            True if self._logged is False else False,
            hash, self.nn, self.ee)

        return {'sign': sign, 'data': encrypted_data}