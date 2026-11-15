"""Decode the Arena1a warp-gate routes (gate, destination node, positions).

Used by the opt-in warp-gate trial of the host (aoa/host/warp_trial.py),
with the hierarchy from aoa/maps/turret_hierarchy.py. Pure Python: the
audit that checks the routes in original client code is
archive/analysis/audit_warp_gates.py.
"""


def routes(nodes):
    result = []
    for gate in nodes:
        if gate['category'] != 6:
            continue
        children = [n for n in nodes if n['parent_id'] == gate['node_id']]
        if len(children) != 1:
            raise ValueError(f"{gate['name']}: expected exactly one destination child")
        child = children[0]
        result.append({'name': gate['name'], 'node_id': gate['node_id'],
                       'destination_node': child['name'], 'destination_id': child['node_id'],
                       'position': gate['world_position'],
                       'destination': child['world_position']})
    if len(result) != 9:
        raise ValueError('expected nine Arena1a warp gates')
    return result
