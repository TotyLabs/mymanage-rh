import re

# New regex from core.py
TOKEN_REGEX = re.compile(r"^[a-zA-Z0-9\-_]{32,128}$")
user_token = "QPvj_Vae4A-PvbfFpC37snHEBR8QVvPKl_vocM08s3o"

def test_pattern(token):
    print(f"Token: {token}")
    match = TOKEN_REGEX.match(token)
    print(f"Match: {bool(match)}")
    return bool(match)

test_pattern(user_token)
