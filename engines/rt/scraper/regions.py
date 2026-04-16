"""
Realtrack region definitions.

Region IDs map to the <select> option values on the Realtrack search form.
These were extracted from the original scraper manifest.
"""

# region_id → (label, folder_name)
# folder_name matches the existing raw-data/rt/pages/ directory names
REGIONS = {
    "01": ("ALGOMA", "Algoma"),
    "02": ("BRANT", "Brant"),
    "03": ("BRUCE", "Bruce"),
    "04": ("COCHRANE", "Cochrane"),
    "05": ("DUFFERIN COUNTY", "Dufferin_County"),
    "06": ("DUNDAS COUNTY", "Dundas_County"),
    "07": ("DURHAM REGION", "Durham_Region"),
    "08": ("ELGIN COUNTY", "Elgin_County"),
    "09": ("ESSEX COUNTY", "Essex_County"),
    "10": ("FRONTENAC COUNTY", "Frontenac_County"),
    "11": ("GLENGARRY COUNTY", "Glengarry_County"),
    "12": ("GRENVILLE COUNTY", "Grenville_County"),
    "13": ("GREY COUNTY", "Grey_County"),
    "14": ("HALDIMAND COUNTY", "Haldimand_County"),
    "15": ("HALIBURTON", "Haliburton"),
    "16": ("HALTON REGION", "Halton_Region"),
    "17": ("HAMILTON-WENTWORTH", "Hamilton-Wentworth"),
    "18": ("HASTINGS COUNTY", "Hastings_County"),
    "19": ("HURON COUNTY", "Huron_County"),
    "20": ("KENORA", "Kenora"),
    "21": ("KENT COUNTY", "Kent_County"),
    "22": ("KITCHENER-WATERLOO", "Kitchener-Waterloo"),
    "23": ("LAMBTON", "Lambton"),
    "24": ("LANARK COUNTY", "Lanark_County"),
    "25": ("LEEDS", "Leeds"),
    "26": ("LENNOX COUNTY", "Lennox_County"),
    "27": ("METRO TORONTO", "Metro_Toronto"),
    "28": ("MUSKOKA", "Muskoka"),
    "29": ("NIPISSING DISTRICT", "Nipissing_District"),
    "30": ("NORFOLK", "Norfolk"),
    "31": ("NORTHUMBERLAND", "Northumberland"),
    "32": ("OTTAWA-CARLETON", "Ottawa-Carleton"),
    "33": ("OXFORD COUNTY", "Oxford_County"),
    "34": ("PARRY SOUND", "Parry_Sound"),
    "35": ("PEEL REGION", "Peel_Region"),
    "36": ("PERTH COUNTY", "Perth_County"),
    "37": ("PETERBOROUGH COUNTY", "Peterborough_County"),
    "38": ("PRESCOTT", "Prescott"),
    "39": ("PRINCE EDWARD", "Prince_Edward"),
    "40": ("RENFREW", "Renfrew"),
    "41": ("RUSSELL TOWNSHIP", "Russell_Township"),
    "42": ("SIMCOE COUNTY", "Simcoe_County"),
    "43": ("STORMONT", "Stormont"),
    "44": ("SUDBURY", "Sudbury"),
    "45": ("THUNDER BAY", "Thunder_Bay"),
    "46": ("TIMISKAMING", "Timiskaming"),
    "47": ("VICTORIA", "Victoria"),
    "48": ("WATERLOO REGION", "Waterloo_Region"),
    "49": ("WELLINGTON", "Wellington"),
    "50": ("YORK REGION", "York_Region"),
    # Some regions may have been added after the original scrape — these IDs
    # came from the manifest. If the search form has more options, we'll
    # discover them during the initial login step.
}
