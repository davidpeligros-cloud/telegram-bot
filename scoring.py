HOT_MODELS = {
    "jordan 4": 40,
    "black cat": 50,
    "military black": 45,
    "dunk": 30,
    "sb dunk": 35,
    "air force": 20,
    "yeezy": 35,
    "9060": 40,
    "2002r": 30,
    "samba": 35,
    "asics": 25
}

def calculate_score(text, prices):

    score = 0
    text = text.lower()

    # modelos populares
    for model, value in HOT_MODELS.items():
        if model in text:
            score += value

    # links
    if "http" in text:
        score += 10

    # precios baratos
    for p in prices:

        try:
            price = int(
                ''.join(filter(str.isdigit, p))
            )

            if price <= 30:
                score += 40

            elif price <= 50:
                score += 25

            elif price <= 80:
                score += 10

        except:
            pass

    return score