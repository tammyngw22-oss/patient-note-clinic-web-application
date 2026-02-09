from cryptography.fernet import Fernet
import os

# 1. Generate Key
key_file = 'backend/secret.key'
if not os.path.exists(key_file):
    key = Fernet.generate_key()
    with open(key_file, 'wb') as kf:
        kf.write(key)
    print(f"Generated {key_file}")
else:
    with open(key_file, 'rb') as kf:
        key = kf.read()
    print(f"Loaded {key_file}")

cipher = Fernet(key)

# 2. Encrypt note.json if it exists and is not already encrypted
note_file = 'backend/note.json'
if os.path.exists(note_file):
    with open(note_file, 'rb') as f:
        data = f.read()
    
    try:
        cipher.decrypt(data)
        print(f"{note_file} is already encrypted.")
    except:
        print(f"Encrypting {note_file}...")
        encrypted_data = cipher.encrypt(data)
        with open(note_file, 'wb') as f:
            f.write(encrypted_data)
        print("Encryption complete.")
