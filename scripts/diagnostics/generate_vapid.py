import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

def generate_vapid():
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_bytes = private_key.private_numbers().private_value.to_bytes(32, byteorder='big')
    
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    
    priv_b64 = base64.urlsafe_b64encode(private_bytes).decode().rstrip("=")
    pub_b64 = base64.urlsafe_b64encode(public_bytes).decode().rstrip("=")
    
    print(f"VAPID_PRIVATE_KEY={priv_b64}")
    print(f"VAPID_PUBLIC_KEY={pub_b64}")

if __name__ == "__main__":
    generate_vapid()
