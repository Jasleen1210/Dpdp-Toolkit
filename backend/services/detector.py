import re
import spacy

nlp = spacy.load("en_core_web_sm")

# name 
def detect_names(text):
    doc = nlp(text)
    names = []

    blacklist = {
        "email", "phone", "contact", "address", "aadhar number", "pan number", "credit card", "card number", "ltd", "pvt", "company"
    }

    for ent in doc.ents:
        if ent.label_ == "PERSON":
            name = ent.text.strip()

            name_lower = name.lower()

            if any(char.isdigit() for char in name):
                continue

            if not name.replace(" ", "").isalpha():
                continue

            if len(name.split()) < 2:
                continue

            if any(word in name_lower for word in blacklist):
                continue

            if name.isupper():
                continue

            names.append({"type": "Name", "value": name})

    return names

# luhn algo for credit card validation
def luhn_check(card_number):
    digits = [int(d) for d in card_number if d.isdigit()]
    checksum = 0
    reverse = digits[::-1]

    for i, d in enumerate(reverse):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d

    return checksum % 10 == 0

def detect_pii(text):
    pii = []

    phones = re.findall(r'\b[6-9]\d{9}\b', text)
    for p in phones:
        pii.append({"type": "Phone", "value": p})

    emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    for e in emails:
        pii.append({"type": "Email", "value": e})

    cards = re.findall(r'\b(?:\d{4}[-\s]?){3}\d{4}\b', text)

    valid_cards = []
    for c in cards:
        clean = re.sub(r'\D', '', c)
        if len(clean) == 16 and luhn_check(clean):
            valid_cards.append(c)

    for c in valid_cards:
        pii.append({"type": "Credit Card", "value": c})

    text_no_cards = text
    for c in valid_cards:
        text_no_cards = text_no_cards.replace(c, "")

    aadhaar = re.findall(r'\b\d{4}\s?\d{4}\s?\d{4}\b', text_no_cards)
    for a in aadhaar:
        pii.append({"type": "Aadhaar", "value": a})

    pan = re.findall(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b', text)
    for p in pan:
        pii.append({"type": "PAN", "value": p})

    ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text)
    for ip in ips:
        pii.append({"type": "IP Address", "value": ip})

    return pii


def detect_pii_full(input_json):
    text = input_json["content"]

    pii = []

    pii.extend(detect_pii(text))
    pii.extend(detect_names(text))

    return {"pii": pii}