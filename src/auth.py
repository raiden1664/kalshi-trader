import base64, time, requests, os
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from .config import BASE_URL, REQUEST_TIMEOUT, KALSHI_KEY_ID, KALSHI_KEY_PATH

class AuthError(Exception):
    pass

def load_private_key():
    path = os.path.expanduser(KALSHI_KEY_PATH)
    if not os.path.exists(path):
        raise AuthError(f"Private key not found at {path}. Set KALSHI_KEY_PATH or place key at ~/.kalshi/kalshi.key")
    with open(path, "rb") as f:
        data = f.read()
    try:
        return serialization.load_pem_private_key(data, password=None, backend=default_backend())
    except Exception as e:
        raise AuthError(f"Could not parse private key: {e}")

def get_headers(method: str, path: str) -> dict:
    key = load_private_key()
    ts  = int(time.time() * 1000)
    msg = f"{ts}{method.upper()}{path}".encode()
    sig = key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256.digest_size), hashes.SHA256())
    return {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": KALSHI_KEY_ID,
        "KALSHI-ACCESS-TIMESTAMP": str(ts),
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
    }

def verify_auth():
    path = "/trade-api/v2/portfolio/balance"
    try:
        r = requests.get(f"{BASE_URL}/portfolio/balance", headers=get_headers("GET", path), timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except requests.HTTPError as e:
        raise AuthError(f"{e.response.status_code}: {e.response.text}")
    except requests.RequestException as e:
        raise AuthError(str(e))