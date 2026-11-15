"""Map objects the host places: power-ups, target ships, navigation buoys and the trials."""
from aoa.host import turret_trial, warp_trial
from aoa.maps import navigation


def load_objects(args):
    """Every map object run() places: (warp gates, warp loads, turret loads, buoy loads).

    main() calls this before --print-config and before any socket opens, so
    validation covers the asset files, not only the flags.
    """
    warp_gates = warp_trial.placements(args.warp_trial) if args.warp_trial else []
    warp = warp_trial.loads(warp_gates)
    trial = turret_trial.loads(turret_trial.placements(args.turret_trial)) if args.turret_trial else []
    buoys = navigation.loads(navigation.placements(args.arena1a_buoys)) if args.arena1a_buoys else []
    if args.navigation_buoys:
        buoys = navigation.loads(navigation.map_placements(
            args.navigation_buoys, args.map, args.buoy_trn or args.key.parent / 'JRMAP.TRN'))
    if args.map_waypoints:
        buoys = navigation.loads(navigation.trn_placements(args.map_waypoints.read_bytes()))
    return warp_gates, warp, trial, buoys
