"""
Main classifier orchestrator — takes an assembled record and returns
a fully classified record.

Calls each section classifier in order and combines the results.

Reference: schema/engine_reference.md — IMPLEMENTATION PLAN
"""

from classifier.header import classify_header
from classifier.parties import classify_parties
from classifier.contacts import classify_contacts
from classifier.site import classify_site
from classifier.consideration import classify_consideration
from classifier.broker import classify_broker
from classifier.description import classify_description


def classify_record(assembled):
    """Classify an assembled record into structured fields.

    Args:
        assembled: dict from assembler output (has 'detail', 'export', 'results' keys)

    Returns:
        dict with all classified fields
    """
    detail = assembled['detail']

    # Header
    header = classify_header(detail['header'])

    # Transferor (seller)
    seller_parties = classify_parties(
        detail['transferor']['party_lines'],
        detail['transferor']['trade_name']
    )
    seller_contacts = classify_contacts(
        detail['transferor']['contact_lines']
    )

    # Transferee (buyer)
    buyer_parties = classify_parties(
        detail['transferee']['party_lines'],
        detail['transferee']['trade_name']
    )
    buyer_contacts = classify_contacts(
        detail['transferee']['contact_lines']
    )

    # If phone was found in contact lines but not in party lines, use it
    if not seller_parties['phone'] and seller_contacts.get('phone'):
        seller_parties['phone'] = seller_contacts.pop('phone')
    else:
        seller_contacts.pop('phone', None)

    if not buyer_parties['phone'] and buyer_contacts.get('phone'):
        buyer_parties['phone'] = buyer_contacts.pop('phone')
    else:
        buyer_contacts.pop('phone', None)

    # Site
    site = classify_site(detail['site_lines'])

    # ARN
    arn = detail['arn_text'].strip()

    # Description
    desc = classify_description(
        detail['description_lines'],
        detail.get('more_info_url', '')
    )

    # Consideration
    consideration = classify_consideration(detail['consideration_lines'])

    # Broker
    broker = classify_broker(detail['broker_lines'])

    # Photos (pass through from structural)
    photos = detail.get('photos', {})

    # Export data (pass through)
    export = assembled.get('export')

    # Results data (pass through)
    results = assembled.get('results')

    return {
        'rt_id': assembled['rt_id'],
        'source_folder': assembled['source_folder'],
        'position': assembled['position'],
        'join_verified': assembled['join_verified'],

        'header': header,

        'seller': {
            **seller_parties,
            **seller_contacts,
        },

        'buyer': {
            **buyer_parties,
            **buyer_contacts,
        },

        'site': site,
        'arn': arn,
        'description': desc,
        'consideration': consideration,
        'broker': broker,
        'photos': photos,

        'export': export,
        'results': results,
    }
