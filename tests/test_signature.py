"""
Standalone signature-verification harness for the TP-Link Archer AX72 login bug.

Purpose: test *hash* + *chunking* hypotheses against a real, captured browser
login without touching tplinkrouterc6u or the project code. Fill in CAPTURE
below with values pulled from a fresh DevTools capture of a real (cold)
login, then run this file.

Confirmed this session (see project recap): the device signs with RSA-OAEP,
not classic PKCS1v1.5, despite tplinkrouterc6u's SIGNATURE_OFFSET=53 constant
being sized for PKCS1v1.5. Message format:
    k=<AES key>&i=<AES iv>&h=<SHA-256 hex of username+password>&s=<seq+cipherLen>
Chunking is nested:
  1. Split the full message into 53-char outer pieces (last may be shorter) -
     this is the protocol-level convention, shared with tplinkrouterc6u's own
     EncryptionWrapper (common/encryption.py) and TplinkRouterSG
     (client/sg.py), both PKCS1v1.5-only. NOTE: TplinkRouterSG's own
     _build_login_signature has the same bug this script used to have - it
     OAEP-encrypts each 53-char piece directly, without the inner split
     below, so it likely 403s on OAEP devices too.
  2. Under OAEP, each outer piece is split *again* into RSA-OAEP's true max
     input size: modulus_bytes - 2*hash_len_bytes - 2 (SHA-1 -> 20 bytes).
     For a 512-bit/64-byte modulus that's 64 - 40 - 2 = 22 bytes, e.g. a
     53-byte piece becomes 22 + 22 + 9. Each sub-piece is RSA-encrypted
     individually - that's the real, atomic RSA operation - and every
     resulting hex block is concatenated in order to form the final `sign`.
  3. If the device instead uses classic PKCS1v1.5 (no OAEP), step 2 is
     skipped: each 53-byte piece is RSA-encrypted directly, one block per
     piece - reusing tplinkrouterc6u's own EncryptionWrapper.rsa_encrypt for
     that branch since PKCS1v1.5 chunking really is a solved problem there.
"""
from hashlib import md5, sha256
from binascii import hexlify
from Crypto.PublicKey.RSA import construct
from Crypto.Cipher import PKCS1_OAEP
from tplinkrouterc6u.common.encryption import EncryptionWrapper

# --- Fill these in from a real DevTools capture -----------------------------
CAPTURE = {
    "username": "",                # confirmed empty in the /login?form=keys response
    "password": "",                # the real router password
    "nn": "",
    "ee": "",
    "seq": "",              # from this session's /login?form=auth # 283809079
    "aes_key": "",                 # 16-digit AES key from the real request (see note below)
    "aes_iv": "",                  # 16-digit AES iv, same source
    "real_sign": "",               # the actual 'sign' field from the captured POST body
    "real_data": "",                # the actual 'data' (AES ciphertext) field from the capture
    "server_hash_candidate": "",   # any other field from /login?form=auth besides seq/key
    "use_oaep": True,              # confirmed True for the AX72 this session
}


def block_count(sign_hex: str, nn: str) -> int:
    rsa_block_hex_len = len(nn)  # nn is hex; RSA modulus byte-length * 2 == this
    return len(sign_hex) // rsa_block_hex_len if rsa_block_hex_len else 0


def oaep_chunk_bytes(nn: str, hash_len_bytes: int = 20) -> int:
    """Max plaintext bytes per OAEP block for this modulus (SHA-1 -> 20)."""
    modulus_bytes = len(nn) // 2
    return modulus_bytes - 2 * hash_len_bytes - 2


def rsa_encrypt_oaep(data: bytes, nn: str, ee: str) -> str:
    key = construct((int(nn, 16), int(ee, 16)))
    return hexlify(PKCS1_OAEP.new(key).encrypt(data)).decode()


def build_signature(message: str, nn: str, ee: str, use_oaep: bool) -> str:
    sign = ''
    pos = 0
    while pos < len(message):
        outer_piece = message[pos:pos + 53]
        pos += 53

        if use_oaep:
            chunk_len = oaep_chunk_bytes(nn)
            piece_bytes = outer_piece.encode()
            inner_pos = 0
            while inner_pos < len(piece_bytes):
                sub = piece_bytes[inner_pos:inner_pos + chunk_len]
                sign += rsa_encrypt_oaep(sub, nn, ee)
                inner_pos += chunk_len
        else:
            # One RSA block per 53-byte piece - library's existing behavior.
            sign += EncryptionWrapper.rsa_encrypt(outer_piece, nn, ee)

    return sign


def try_hash(label: str, hash_value: str, cap: dict) -> None:
    if not hash_value:
        print(f"[skip] {label}: no value provided")
        return

    data_len = len(cap["real_data"]) if cap["real_data"] else 0
    # s = seq + data_len is a numeric sum (see TplinkRouterSG._build_login_signature
    # and CVE-2022-30075's tplink.py: `self.seq + len(encrypted_data)`), NOT string
    # concatenation - concatenating here silently produces a wrong-but-plausible s
    # value instead of erroring, which is what made seq look inconsistent.
    seq_plus_len = str(int(cap["seq"]) + data_len)
    message = 'k={}&i={}&h={}&s={}'.format(
        cap["aes_key"], cap["aes_iv"], hash_value, seq_plus_len)

    sign = build_signature(message, cap["nn"], cap["ee"], cap["use_oaep"])

    print(f"\n--- {label} ---")
    print(f"hash used        : {hash_value!r} (len={len(hash_value)})")
    print(f"message          : {message!r} (len={len(message)})")
    print(f"computed sign len: {len(sign)} hex chars "
          f"({block_count(sign, cap['nn'])} blocks, given {len(cap['nn'])}-hex-char modulus)")
    if cap["real_sign"]:
        match = sign == cap["real_sign"]
        print(f"real sign len    : {len(cap['real_sign'])} hex chars "
              f"({block_count(cap['real_sign'], cap['nn'])} blocks)")
        print(f"EXACT MATCH      : {match}")
    print(f"computed sign    : {sign}")


if __name__ == "__main__":
    cap = CAPTURE
    if not (cap["nn"] and cap["ee"] and cap["seq"] and cap["aes_key"] and cap["aes_iv"]):
        print("Fill in nn / ee / seq / aes_key / aes_iv (and ideally real_data/real_sign) "
              "from a real capture before running this.")
        raise SystemExit(1)

    # Hypothesis 1: confirmed scheme for OAEP/SG devices - SHA-256.
    sha_hash = sha256((cap["username"] + cap["password"]).encode()).hexdigest()
    try_hash("Confirmed OAEP scheme: sha256(username+password)", sha_hash, cap)

    # Hypothesis 2: the library's older, PKCS1v1.5-only assumption - MD5.
    md5_hash = md5((cap["username"] + cap["password"]).encode()).hexdigest()
    try_hash("Legacy library assumption: md5(username+password)", md5_hash, cap)

    # Hypothesis 3: whatever extra field you found in the /login?form=auth response.
    try_hash("Server-issued value from /login?form=auth", cap["server_hash_candidate"], cap)