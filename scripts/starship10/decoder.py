import json
import re
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import argparse
import os

# Load combined poem from file
def load_poem(file_path="poem.txt"):
    try:
        with open(file_path, 'r') as f:
            lines = [line.strip() for line in f.readlines()]
            non_empty_lines = [line for line in lines if line]
        if len(non_empty_lines) != 16:
            print(f"Error: {file_path} should have exactly 16 non-empty lines, found {len(non_empty_lines)}")
            return []
        if len(lines) != 19:
            print(f"Error: {file_path} should have exactly 19 lines (16 poem + 3 blanks), found {len(lines)}")
            return []
        return lines
    except FileNotFoundError:
        print(f"Error: {file_path} not found in starship10 directory!")
        return []

# Derive Fernet key from passphrase
def derive_key(passphrase: str) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"salt_", iterations=100000, backend=default_backend())
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))

# Decrypt file (key.enc or prompt.enc)
def decrypt_file(enc_file: str, passphrase: str) -> str:
    key = derive_key(passphrase)
    fernet = Fernet(key)
    try:
        with open(enc_file, 'rb') as f:
            encrypted_data = f.read()
        decrypted = fernet.decrypt(encrypted_data)
        return decrypted.decode()
    except InvalidToken:
        raise ValueError("Invalid passphrase! Try solving the riddle in readme.md.")

# Decode poem for SFW (1) or NSFW (2)
def decode_poem(merged_lines: list, keys: list, poem_type: int) -> str:
    decoded = []
    key_index = 0
    for i, line in enumerate(merged_lines, 1):
        if not line.strip():  # Skip blank lines
            decoded.append('')
            key_index += 1
            continue
        if key_index >= len(keys):
            print(f"Warning: Ran out of keys at line {i} '{line}'")
            decoded.append('')
            continue
        key_dict = keys[key_index]
        if not key_dict:  # Skip empty dict for blank lines
            decoded.append('')
            key_index += 1
            continue
        key = key_dict['key']
        words = re.split(r'\s+', line.strip())
        if len(words) != len(key):
            print(f"Warning: Line {i} '{line}' has {len(words)} words but key has {len(key)} entries: {key}")
            decoded.append('')
            key_index += 1
            continue
        extracted = [words[j] for j in range(len(words)) if key[j] == poem_type]
        reorder = key_dict['sfw_reorder'] if poem_type == 1 else key_dict['nsfw_reorder']
        if reorder is not None:
            if len(reorder) != len(extracted):
                print(f"Warning: Line {i} reorder {reorder} has {len(reorder)} entries but extracted has {len(extracted)} words")
                decoded.append('')
            else:
                poem_words = [extracted[j] for j in reorder]
                decoded.append(' '.join(poem_words))
        else:
            decoded.append(' '.join(extracted))
        key_index += 1
    return '\n'.join(decoded)

# Main script
parser = argparse.ArgumentParser(description="Decode the Starship Flight Test 10 poem puzzle! 🚀")
parser.add_argument('--view', choices=['nsfw', 'sfw', 'key', 'prompt'], help="Unlock with passphrase to view: nsfw (cheeky), sfw (safe), key (decoding map), or prompt (Starship visual)")
args = parser.parse_args()

merged_poem = load_poem("poem.txt")
if not merged_poem:
    exit(1)

print("Starship Flight Test 10 Poem (Public Teaser):\n")
print('\n'.join(merged_poem))
print("\nEnjoy Starship’s thrust! Know the cosmic secret? Use --view=nsfw, --view=sfw, --view=key, or --view=prompt to unlock the vibes. 😘🚀")

if args.view:
    passphrase = input("\nEnter the cosmic passphrase (hint: see readme.md): ")
    try:
        if args.view == 'prompt':
            prompt = decrypt_file('prompt.enc', passphrase)
            print("\nGrok Imagine Prompt (Starship Visual):\n")
            print(prompt)
        else:
            keys = json.loads(decrypt_file('key.enc', passphrase))
#           print(f"Debug: Decrypted keys: {keys}")
            if len(keys) != 19:
                print(f"Error: key.enc should have 19 entries, found {len(keys)}")
                exit(1)
            if args.view == 'sfw':
                print("\nSFW Poem (Safe for Orbit):\n")
                print(decode_poem(merged_lines=merged_poem, keys=keys, poem_type=1))
            elif args.view == 'nsfw':
                print("\nNSFW Poem (Cheeky Thrust Prize):\n")
                print(decode_poem(merged_lines=merged_poem, keys=keys, poem_type=2))
            elif args.view == 'key':
                print("\nDecoding Keys (Line-by-Line Map):\n")
                non_empty_lines = [1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19]
                print('\n'.join([f"Line {non_empty_lines[i]}: {keys[j]['key']}" for i, j in enumerate([0,1,2,3,5,6,7,8,10,11,12,13,15,16,17,18])]))
    except ValueError as e:
        print(f"\n{e}")