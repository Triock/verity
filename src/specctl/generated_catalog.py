# Generated from the Software Specification. Attribution: Richard Hillman <triock@gmail.com>.
"""Read-only component catalog generated from the resolved specification."""
import json as _json

_CATALOG = _json.loads('{"component-catalog":{"data_sets":[],"depends_on":["spec-model"],"id":"component-catalog","implements":["query-catalog"],"kind":"library","language":"python","provides":[{"contract_id":"catalog-query","revision":"1"}],"requires":[{"accepted_revisions":["1"],"contract_id":"validated-spec"}]},"spec-model":{"data_sets":[],"depends_on":[],"id":"spec-model","implements":["validate-model"],"kind":"library","language":"python","provides":[{"contract_id":"validated-spec","revision":"1"}],"requires":[]},"specctl":{"data_sets":[],"depends_on":["component-catalog","spec-model"],"id":"specctl","implements":["inspect-model"],"kind":"application","language":"python","provides":[],"requires":[{"accepted_revisions":["1"],"contract_id":"catalog-query"},{"accepted_revisions":["1"],"contract_id":"validated-spec"}]}}')

def list_components():
    """Return stable component identifiers."""
    return sorted(_CATALOG)

def get_component(component_id):
    """Return a declared component record, or None when absent."""
    record = _CATALOG.get(component_id)
    return None if record is None else _json.loads(_json.dumps(record))
