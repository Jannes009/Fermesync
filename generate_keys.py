from pywebpush import generate_vapid_key_pair
private_key, public_key = generate_vapid_key_pair()
print("VAPID_PRIVATE_KEY=", private_key)
print("VAPID_PUBLIC_KEY=", public_key)