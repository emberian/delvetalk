"""Retained native preparations. No client-side operational language."""
import source_offers

FORMAT = source_offers.FORMAT
validate = source_offers.validate
action = source_offers.action
request = source_offers.request


def wire(offer, values):
    result = request(offer, 'preview', 'preview', values)
    result = {key: value for key, value in result.items() if key not in ('principal', 'intent')}
    result['reads'] = {key: {'expected': root} for key, root in result['reads'].items()}
    return result
