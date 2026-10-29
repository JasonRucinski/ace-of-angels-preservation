"""Profile coverage, layout clearances and malformed-input checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import classic_haze as haze
from online_terrain import MAP_NAMES


class HazeTests(unittest.TestCase):
    def setUp(self):
        self.data = haze.load()
        self.profiles = {p['map']: p for p in self.data['profiles']}

    def test_all_recovered_maps_have_explicit_policy(self):
        self.assertEqual(set(self.profiles), set(MAP_NAMES) | {'Curt3'})
        haze.verify_generated()

    def test_combat_routes_and_base_components_clear(self):
        for name, points in {
            'Arena1a': [(0,0,0),(0,0,-80000),(-45336,95404,-122072),(45007,95404,-122072)],
            'newterrain': [(0,0,0),(0,0,-80000)],
            'CTF_arena': [(0,0,0),(5737,0,-198170),(3243,0,199019)],
            'CTF_arena_b': [(45396,4633,80000)],
            'Curt3': [(0,0,0)],
            'JRMAP': [(-6000,-6000,-112000)],
        }.items():
            for cloud in self.profiles[name]['pockets']:
                for point in points:
                    distance = sum(((p-c)/r)**2 for p,c,r in zip(point,cloud['center'],cloud['radii']))
                    self.assertGreater(distance,1,name)
        for name in ('CTF_base','hu_base_a','hu_base_b','hy_base_test','hy_winga','HyBase2Lay','irrosa01','ze_winga','ze_wingb','Hittest'):
            self.assertEqual(self.profiles[name]['pockets'],[],name)

    def test_invalid_profiles_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'profiles.json'
            for field,value in [('radii',[0,100,100]),('color',[float('nan'),0,0]),('density',-1)]:
                data=copy.deepcopy(self.data)
                data['profiles'][0]['pockets'][0][field]=value
                path.write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaises(ValueError):haze.load(path)
            data=copy.deepcopy(self.data)
            data['profiles'].append(copy.deepcopy(data['profiles'][0]))
            path.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(ValueError):haze.load(path)


if __name__ == '__main__':
    unittest.main()
