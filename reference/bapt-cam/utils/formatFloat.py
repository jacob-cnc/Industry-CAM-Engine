def format_float(value, max_decimals=4):
    return str(round(value, max_decimals)).rstrip("0").rstrip(".")
