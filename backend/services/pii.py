def get_pii_flags(pii_result):
    pii_flags = {
        "Name": False,
        "Phone": False,
        "Email": False,
        "Credit Card": False,
        "Aadhaar": False,
        "PAN": False,
        "IP Address": False,
    }

    for item in pii_result:
        pii_type = item.get("type")
        if pii_type in pii_flags:
            pii_flags[pii_type] = True

    return pii_flags


def summarize_pii_instances(pii_result):
    counts = {}

    for item in pii_result:
        pii_type = item.get("type", "Unknown")
        counts[pii_type] = counts.get(pii_type, 0) + 1

    return [
        {"type": pii_type, "count": count}
        for pii_type, count in sorted(counts.items())
    ]


def build_pii_summary(pii_result):
    instances = summarize_pii_instances(pii_result)

    return {
        "pii": get_pii_flags(pii_result),
        "pii_instances": instances,
        "pii_instance_count": sum(item["count"] for item in instances),
    }
