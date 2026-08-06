"""
Live login test for the TP-Link Archer AX72 - the real test, not sign-matching.

Why this replaces test_signature.py's approach: RSA-OAEP is randomized
(a fresh random seed is mixed into the padding on every single encryption -
that's what makes it IND-CCA2 secure). This means no implementation, however
correct, can ever reproduce a previously captured `sign` byte-for-byte. The
only valid test is building a fresh request and seeing whether the router
actually accepts it.

Confirmed / high-confidence findings this session (see prior chat for detail):
- Real login flow uses TWO separate RSA keypairs (confirmed from the actual
  tplinkrouterc6u source, tplinkrouterc6u/client/c6u.py):
    * `pwdNN`/`pwdEE` - from POST {host}/cgi-bin/luci/;stok=/login?form=keys
      (JSON field "password") - used ONLY to RSA-encrypt the password itself,
      one shot, PKCS1v1.5 (EncryptionWrapper.rsa_encrypt), no chunking needed
      since the password is short enough to fit one block.
    * `nn`/`ee` - from POST {host}/cgi-bin/luci/;stok=/login?form=auth
      (JSON field "key", alongside "seq") - used ONLY for the request `sign`.
- `sign` is built from message 'k=<aes_key>&i=<aes_iv>&h=<hash>&s=<seq+len>',
  RSA-OAEP-encrypted with nested chunking: split into 53-char outer pieces,
  then (OAEP only) each piece into modulus_bytes-2*hash_len-2 byte inner
  pieces (22 bytes for this 512-bit key + SHA-1 OAEP), each RSA-OAEP'd
  individually, all hex concatenated. Verified structurally: this is the
  ONLY scheme (of OAEP-nested / classic-PKCS1v1.5-53 / MR-series-NOPADDING)
  that reproduces the observed 7-block / 896-hex-char signature length
  across every real capture so far.
- `h` = sha256(username+password) hex - confirmed by the same value
  reappearing identically across independent captures with the same
  credentials.
- The decrypted plaintext `data` field observed was exactly
  'operation=login&password=<hex>' with NO '&confirm=true' suffix - unlike
  the library's default TplinkEncryption._get_login_data(). This script
  tries the no-confirm form first (matches your capture) and falls back to
  the with-confirm form if the router rejects it.

USAGE: fill in HOST / USERNAME / PASSWORD below and run. This makes a real
request against your real router - only run it against hardware you own.
"""
from base64 import b64encode
from binascii import hexlify
from hashlib import sha256
from random import randint
from time import time

import requests
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey.RSA import construct
from tplinkrouterc6u.common.encryption import EncryptionWrapper

# --- Fill these in ----------------------------------------------------------
HOST = "https://192.168.0.1"     # your router's base URL
USERNAME = ""                    # confirmed empty in /login?form=keys response
PASSWORD = ""                   # the real router password
VERIFY_SSL = False               # router's cert is normally self-signed


def oaep_chunk_bytes(nn: str, hash_len_bytes: int = 20) -> int:
    modulus_bytes = len(nn) // 2
    return modulus_bytes - 2 * hash_len_bytes - 2


def rsa_encrypt_oaep(data: bytes, nn: str, ee: str) -> str:
    key = construct((int(nn, 16), int(ee, 16)))
    return hexlify(PKCS1_OAEP.new(key).encrypt(data)).decode()


def build_signature(message: str, nn: str, ee: str) -> str:
    """Nested OAEP chunking: 53-char outer pieces, then 22-byte inner pieces."""
    sign = ''
    pos = 0
    chunk_len = oaep_chunk_bytes(nn)
    while pos < len(message):
        outer_piece = message[pos:pos + 53].encode()
        pos += 53
        inner_pos = 0
        while inner_pos < len(outer_piece):
            sub = outer_piece[inner_pos:inner_pos + chunk_len]
            sign += rsa_encrypt_oaep(sub, nn, ee)
            inner_pos += chunk_len
    return sign


def aes_encrypt(plaintext: str, key: str, iv: str) -> str:
    pad_len = AES.block_size - len(plaintext) % AES.block_size
    padded = plaintext + chr(pad_len) * pad_len
    cipher = AES.new(key.encode(), AES.MODE_CBC, iv.encode())
    return b64encode(cipher.encrypt(padded.encode())).decode()


def get_keys(session: requests.Session) -> tuple[str, str]:
    """POST /login?form=keys -> (pwdNN, pwdEE), the password-encryption key."""
    r = session.post(
        f"{HOST}/cgi-bin/luci/;stok=/login?form=keys",
        params={"operation": "read"}, verify=VERIFY_SSL, timeout=10)
    r.raise_for_status()
    args = r.json()["data"]["password"]
    return args[0], args[1]


def get_seq_and_signkey(session: requests.Session) -> tuple[str, str, str]:
    """POST /login?form=auth -> (seq, nn, ee), the signature key."""
    r = session.post(
        f"{HOST}/cgi-bin/luci/;stok=/login?form=auth",
        params={"operation": "read"}, verify=VERIFY_SSL, timeout=10)
    r.raise_for_status()
    data = r.json()["data"]
    args = data["key"]
    return data["seq"], args[0], args[1]


def aes_decrypt(b64_ciphertext: str, key: str, iv: str) -> str:
    from base64 import b64decode
    cipher = AES.new(key.encode(), AES.MODE_CBC, iv.encode())
    raw = cipher.decrypt(b64decode(b64_ciphertext))
    return raw[:-raw[-1]].decode()  # strip PKCS7/custom pad byte


def try_login(login_data: str, seq: str, nn: str, ee: str):
    session = requests.Session()

    # Our own fresh AES key/iv for this request - 16 ASCII digits each,
    # matching what these routers commonly expect (EncryptionWrapperMR uses
    # timestamp+random digits truncated to length; EncryptionWrapper uses
    # random hex; use digits here since the capture showed decimal-looking
    # k=/i= values).
    ts = str(round(time() * 1000))
    aes_key = (ts + str(randint(10**8, 10**9 - 1)))[:16]
    aes_iv = (ts + str(randint(10**8, 10**9 - 1)))[:16]

    encrypted_data = aes_encrypt(login_data, aes_key, aes_iv)
    data_len = len(encrypted_data)
    hash_value = sha256((USERNAME + PASSWORD).encode()).hexdigest()

    message = f"k={aes_key}&i={aes_iv}&h={hash_value}&s={int(seq) + data_len}"
    sign = build_signature(message, nn, ee)

    body = {"sign": sign, "data": encrypted_data}
    resp = session.post(
        f"{HOST}/cgi-bin/luci/;stok=/login?form=login",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        verify=VERIFY_SSL, timeout=10)
    return resp, aes_key, aes_iv, session


if __name__ == "__main__":
    session = requests.Session()
    pwd_nn, pwd_ee = get_keys(session)
    seq, nn, ee = get_seq_and_signkey(session)

    encrypted_pwd = EncryptionWrapper.rsa_encrypt(PASSWORD, pwd_nn, pwd_ee)

    print(f"pwdNN len={len(pwd_nn)} ({len(pwd_nn) * 4}-bit)  "
          f"nn len={len(nn)} ({len(nn) * 4}-bit)  seq={seq}")

    for label, login_data in [
        ("no confirm=true (matches your capture)",
         f"operation=login&password={encrypted_pwd}"),
        ("with confirm=true (library default)",
         f"operation=login&password={encrypted_pwd}&confirm=true"),
    ]:
        print(f"\n--- trying: {label} ---")
        resp, aes_key, aes_iv, session = try_login(login_data, seq, nn, ee)
        print(f"status : {resp.status_code}")
        print(f"cookies: {dict(session.cookies)}")

        decrypted = None
        try:
            import json
            body = resp.json()
            if "data" in body:
                decrypted = aes_decrypt(body["data"], aes_key, aes_iv)
                print(f"decrypted body: {decrypted}")
        except Exception as e:
            print(f"raw body (couldn't decrypt/parse): {resp.text[:500]}")
            print(f"  (decrypt error: {e})")

        # A real success carries a stok token and/or a sysauth cookie; an
        # encrypted error still returns HTTP 200 but its decrypted JSON has
        # an errorcode/success:false instead.
        if resp.status_code == 200 and decrypted and (
                '"stok"' in decrypted or "sysauth" in session.cookies):
            print(">>> LOGIN SUCCESSFUL - stok/session present.")
            break
        elif resp.status_code != 403:
            print(">>> not a 403, but no stok/session found yet - check the "
                  "decrypted body above for an error message.")
