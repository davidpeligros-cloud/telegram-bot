import logging
import re
from typing import List

logger = logging.getLogger(__name__)

HOT_MODELS = {
    "jordan 4": 40,
    "jordan 1": 35,
    "black cat": 50,
    "military black": 45,
    "dunk": 30,
    "sb dunk": 35,
    "air force": 20,
    "yeezy": 35,
    "9060": 40,
    "2002r": 30,
    "samba": 35,
    "asics": 25,
    "travis scott": 45,
    "off white": 40,
    "bape": 30,
    
    # Nuevos modelos añadidos
    "adidas samba": 35, "adidas gazelle": 35, "adidas spezial": 35, "adidas campus 00s": 35, 
    "adidas sl72": 35, "adidas tokyo": 35, "adidas taekwondo": 35, "adidas bw army": 35, 
    "adidas forum low": 35, "adidas rivalry low": 35, "adidas superstar": 35, "adidas response cl": 35, 
    "adidas ozweego": 35, "adidas handball spezial": 35,
    
    "nike shox tl": 35, "nike vomero 5": 35, "nike p-6000": 35, "nike air max plus tn": 35, 
    "nike air max dn": 35, "nike air max 95": 35, "nike air max 97": 35, "nike cortez": 35, 
    "nike dunk low": 35, "nike sb dunk": 35, "nike v2k run": 35, "nike initiator": 35, 
    "nike pegasus 2k5": 35, "nike zoom spiridon": 35, "nike nocta glide": 35, "nike air rift": 35,
    
    "new balance 9060": 35, "new balance 2002r": 35, "new balance 1906r": 35, "new balance 530": 35, 
    "new balance 327": 35, "new balance 740": 35, "new balance 725": 35, "new balance 610": 35, 
    "new balance 1000": 35, "new balance 990v4": 35, "new balance 990v6": 35, "new balance wrpd runner": 35, 
    "new balance 204l": 35,
    
    "asics gel-kayano 14": 35, "asics gel-nyc": 35, "asics gt-2160": 35, "asics gel-1130": 35, 
    "asics gel-quantum": 35, "asics gel-lyte iii": 35, "asics kayano 20": 35, "asics gel venture 6": 35,
    
    "puma speedcat": 35, "puma palermo": 35, "puma suede xl": 35, "puma mostro": 35, 
    "puma rs-x": 35, "puma easy rider": 35, "puma velophasis": 35, "puma ca pro": 35,
    
    "vans knu skool": 35, "vans old skool": 35, "vans upland": 35, "vans hylane": 35, 
    "vans half cab": 35, "vans rowley": 35, "vans skate mixxa": 35, "vans slip-on chunky": 35,
    
    "salomon xt-6": 35, "salomon acs pro": 35, "salomon xt-4": 35, "salomon xt-wings 2": 35, 
    "salomon rx slide": 35, "salomon rx mary jane": 35, "salomon speedcross 3": 35,
    
    "converse run star hike": 35, "converse chuck 70": 35, "converse weapon": 35, "converse one star": 35, 
    "converse aero jam": 35, "converse lugged": 35,
    
    "mizuno wave rider 10": 35, "mizuno wave prophecy": 35, "mizuno mxr": 35, "mizuno sky medal": 35,
    
    "reebok club c": 35, "reebok classic leather": 35, "reebok premier road": 35, "reebok zig kinetica": 35,
    
    "onitsuka tiger mexico 66": 35,
    "veja campo": 35,
    "axel arigato clean 90": 35,
    "common projects achilles": 35,
    "maison margiela replica": 35,
    "autry medalist": 35,
    "golden goose super-star": 35,
    "balenciaga runner": 35, "balenciaga track": 35,
    "rick owens geobasket": 35,
    "dior b35": 35,
    "prada america's cup": 35,
    "prada america’s cup": 35,
    "isabel marant bekett": 35,
}

HOT_TERMS = {
    "deadstock": 20,
    "limited": 15,
    "exclusive": 15,
    "rare": 10,
    "resale": 10,
    "brand new": 10,
    "new in box": 10,
    "hype": 15,
    "promo": 10,
}

PRICE_REGEX = re.compile(
    r"(?:(?:€|\$|£|GBP|USD|EUR)\s*(\d+(?:[.,]\d{1,2})?)\b)|"
    r"(?:\b(\d+(?:[.,]\d{1,2})?)\s*(?:€|\$|£|GBP|USD|EUR))",
    re.IGNORECASE
)

LINK_PATTERN = re.compile(r"https?://[^\s\)\]\}]+")


def extract_links(text: str) -> List[str]:
    """Extraer enlaces únicos de un mensaje."""
    if not text:
        return []

    matches = LINK_PATTERN.findall(text)
    return list(dict.fromkeys(matches))


def extract_prices(text: str) -> List[str]:
    """Extraer precios en múltiples formatos sin duplicados de decimales."""
    if not text:
        return []

    matches = PRICE_REGEX.findall(text)
    # Extraer el valor no vacío de cada tupla de coincidencia
    prices = [m[0] or m[1] for m in matches]
    return list(dict.fromkeys(prices))


def normalize_price(price_text: str) -> float:
    """Convertir un precio detectado a número flotante manejando comas y puntos decimales."""
    # Reemplazar coma por punto para soporte decimal europeo
    cleaned = price_text.replace(",", ".")
    # Quitar símbolos y letras de monedas
    cleaned = re.sub(r"[€$£\s]|GBP|USD|EUR", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("..", ".")
    
    # Manejar múltiples puntos (ej: miles 1.250.50 -> 1250.50)
    if cleaned.count(".") > 1:
        parts = cleaned.split(".")
        cleaned = "".join(parts[:-1]) + "." + parts[-1]

    try:
        return float(cleaned)
    except ValueError as exc:
        raise ValueError(f"No se pudo normalizar el precio: {price_text}") from exc


def calculate_score(text: str, prices: List[str]) -> int:
    """Calcular score de una deal basándose en texto y precio."""
    score = 0
    normalized = text.lower()

    for model, weight in HOT_MODELS.items():
        if model in normalized:
            score += weight
            logger.debug(f"Modelo detectado: {model} (+{weight})")

    for term, weight in HOT_TERMS.items():
        if term in normalized:
            score += weight
            logger.debug(f"Término valioso detectado: {term} (+{weight})")

    if "http" in normalized:
        score += 10

    if any(currency in normalized for currency in ["€", "$", "£", "usd", "eur", "gbp"]):
        score += 5

    for price_text in prices:
        try:
            price_value = normalize_price(price_text)
            if price_value <= 30:
                score += 40
            elif price_value <= 50:
                score += 25
            elif price_value <= 80:
                score += 10
            elif price_value <= 120:
                score += 5
            elif price_value <= 200:
                score += 2
            else:
                score -= 5

            logger.debug(f"Precio normalizado: {price_value} (+score)")
        except ValueError:
            continue

    score = max(score, 0)
    score = min(score, 200)
    return score
