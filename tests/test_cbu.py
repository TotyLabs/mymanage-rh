import re

CBU_REGEX = re.compile(r"^\d{22}$")
user_cbu = "0170342120000014859369"

def validate(cbu):
    print(f"Original: '{cbu}'")
    clean_cbu = re.sub(r"\D", "", cbu.strip())
    print(f"Cleaned:  '{clean_cbu}'")
    print(f"Length:   {len(clean_cbu)}")
    match = CBU_REGEX.match(clean_cbu)
    print(f"Match:    {bool(match)}")
    return bool(match)

validate(user_cbu)
