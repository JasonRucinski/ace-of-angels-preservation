"""Bounded original-x86 rendering probes; no client launch, GUI, or network.

Only _CIasin/_CIacos are substituted, with Python math. Their input values
are recorded before substitution; domain findings do not depend on a CRT stub.
This is not a GPU or complete-frame test.
"""
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emulate_codec import Emu, SCRATCH, STUBS, STOP
from patch_client import PRISTINE_292
from pe_util import PE
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_FPCW, UC_X86_REG_ESP


def matrix(angle=0, position=(0, 0, 0)):
    c, s = math.cos(angle), math.sin(angle)
    return [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, *position, 1]


def multiply(a, b):
    return [sum(a[r*4+k]*b[k*4+c] for k in range(4)) for r in range(4) for c in range(4)]


def run(source, corrected=False, fpcw=0x7F, patch=None):
    """`patch`: module with regions() (default: the offline culling experiment).
    A patch with CENTER_VISIBLE = False keeps the original hidden result for a
    node at exactly the camera position (the player's own ship, findings 9.36)."""
    pe = PE(source)
    if hashlib.sha256(pe.data).hexdigest() != PRISTINE_292:
        raise ValueError('requires pristine 2.9.2 executable')
    emu = Emu(pe)
    center_visible = True
    if corrected:
        if patch is None:
            import render_culling_experiment as patch
        center_visible = getattr(patch, 'CENTER_VISIBLE', True)
        for offset, old, new in patch.regions():
            emu.write(offset+0x400000,new)
    emu.uc.reg_write(UC_X86_REG_FPCW, fpcw)
    def call(fn, this, *args):
        result = emu.thiscall(fn, this, *args)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == STOP, hex(fn)
        return result
    def floats(address, values):
        emu.write(address, struct.pack('<'+'f'*len(values), *values))
        return struct.unpack('<'+'f'*len(values), emu.read(address, len(values)*4))
    def readfloats(address, n):
        return struct.unpack('<'+'f'*n, emu.read(address, n*4))

    # Three-level hierarchy, varied rotations/translations, including large
    # world coordinates. Explicit invalidation is a fixture precondition.
    nodes = [SCRATCH+i*0x1000 for i in range(3)]
    worst = 0
    for frame in range(120):
        local = []
        for i, node in enumerate(nodes):
            emu.write(node, bytes(0x300))
            local.append(floats(node+0x7C, matrix(frame*0.01*(i+1), (10000*i+frame, i*17, -frame*i))))
            emu.write(node+0x144, struct.pack('<I', nodes[i-1] if i else 0))
        expected = multiply(multiply(local[2], local[1]), local[0])
        pointer = call(0x542C80, nodes[2])
        observed = readfloats(pointer, 16)
        error = max(abs(a-b) for a,b in zip(expected, observed))
        worst = max(worst, error)
        assert error < 0.02, (frame, error)
        assert emu.read(nodes[2]+0x1E8, 1) == b'\1'
        before = emu.read(pointer, 64)
        assert emu.read(call(0x542C80, nodes[2]), 64) == before
        # The exact original copy used before the world-matrix device call.
        out = SCRATCH+0x4000
        call(0x56CEE0, 0, out, pointer)
        assert emu.read(out, 64) == before

    # Characterize cache contract, rather than claiming that direct memory
    # writes reproduce the game's normal mutation/notification path.
    cached = emu.read(nodes[2]+0x1A8, 64)
    bits = [struct.unpack('<I', struct.pack('<f', v))[0] for v in (500, 600, 700)]
    call(0x542F00, nodes[0], *bits)
    assert emu.read(nodes[0]+0x1E8, 1) == b'\0'
    assert emu.read(nodes[2]+0x1E8, 1) == b'\1'
    assert emu.read(call(0x542C80, nodes[2]), 64) == cached

    # Small x87 adapters preserve the stack ABI of MSVCRT _CI* functions.
    # fstp qword[input]; fld qword[output]; ret. Python writes output at fld.
    math_calls = []
    input_addr, output_addr = SCRATCH+0x9000, SCRATCH+0x9010
    funcs = {}
    for index, (iat, name, fn) in enumerate(((0x58C368, 'asin', math.asin), (0x58C364, 'acos', math.acos))):
        stub = STUBS+0x400+index*0x20
        emu.write(iat, struct.pack('<I', stub))
        emu.write(stub, b'\xdd\x1d'+struct.pack('<I', input_addr)+b'\xdd\x05'+struct.pack('<I', output_addr)+b'\xc3')
        funcs[stub+6] = (name, fn)
    def math_hook(uc, address, size, _):
        if address not in funcs:
            return
        name, fn = funcs[address]
        value = struct.unpack('<d', emu.read(input_addr, 8))[0]
        math_calls.append({'function':name, 'input':value})
        try:
            result = fn(value)
        except ValueError:
            result = float('nan')
        emu.write(output_addr, struct.pack('<d', result))
    emu.uc.hook_add(UC_HOOK_CODE, math_hook, begin=STUBS+0x400, end=STUBS+0x440)
    node, camera, context = SCRATCH, SCRATCH+0x5000, SCRATCH+0x6000
    def cull(position, radius=100, eye=(0,0,0), yaw=0, enabled=True):
        emu.write(node, bytes(0x300))
        emu.write(camera, bytes(0x100))
        floats(node+0xAC, position)
        floats(node+0x164, [radius])
        floats(node+0x180, [5,4096])
        emu.write(node+0x150, bytes([enabled]))
        floats(camera+0x70, [math.sin(yaw),0,math.cos(yaw)])
        floats(camera+0x80, eye)
        floats(context+8, [960])
        math_calls.clear()
        call(0x543000, node, camera, context)
        assert emu.uc.reg_read(UC_X86_REG_FPCW) == fpcw
        return {'visible':bool(emu.read(node+0x151,1)[0]),
                'direction_finite':all(map(math.isfinite, readfloats(node+0x158,3))),
                'angular_bound_finite':math.isfinite(readfloats(node+0x170,1)[0]),
                'size':readfloats(node+0x17C,1)[0],
                'math_calls':list(math_calls)}

    # Objects comfortably within/outside the cone, repeated while moving and
    # turning together: visibility must be invariant in camera-relative space.
    cases = 0
    angular_domain_cases = []
    visibility_mismatches = []
    motion_samples = []
    for frame in range(120):
        yaw = frame*0.02
        eye = (frame*80., frame*2., -frame*3.)
        for angle, visible in ((0, True), (0.6, True), (1.2, False), (math.pi, False)):
            pos = (eye[0]+1000*math.sin(yaw+angle),eye[1],eye[2]+1000*math.cos(yaw+angle))
            result = cull(pos, eye=eye, yaw=yaw)
            assert result['direction_finite'], (frame, angle, result)
            if any(abs(c['input']) > 1 for c in result['math_calls']):
                angular_domain_cases.append({'frame':frame,'angle':angle,**result})
            else:
                assert result['angular_bound_finite'], (frame, angle, result)
            if result['visible'] != visible:
                visibility_mismatches.append({'frame':frame,'angle':angle,'expected_visible':visible,**result})
            motion_samples.append([result['visible'],result['angular_bound_finite'],result['size']])
            cases += 1
    boundary = {str(distance):cull((0,0,distance)) for distance in (101,100,99,1,0)}
    assert (not angular_domain_cases if corrected else angular_domain_cases), angular_domain_cases[:2]
    assert all(any(abs(c['input']) > 1 for c in case['math_calls']) for case in visibility_mismatches)
    if corrected:
        assert not visibility_mismatches
        assert all(c['visible'] and c['direction_finite'] and c['angular_bound_finite']
                   for d, c in boundary.items() if center_visible or d != '0')
        assert not boundary['99']['math_calls']
        if not center_visible:
            assert not boundary['0']['visible'] and not boundary['0']['math_calls']
    else:
        assert boundary['99']['math_calls'][-1]['input'] > 1
        assert not boundary['0']['direction_finite']
        assert not boundary['0']['visible']
    # Literal size cutoff is strictly >5 in the final visibility gate, unlike
    # the inclusive minimum in the LOD selector.
    cutoff = {str(distance):cull((0,0,distance), radius=1) for distance in (383,384,385)}
    assert cutoff['383']['visible'] and not cutoff['384']['visible'] and not cutoff['385']['visible']
    inside_cases = 0
    if corrected:
        for radius in (1,100,10000):
            for fraction in (0,0.001,0.5,0.999):
                for angle in (0,0.5,math.pi/2,math.pi):
                    distance = radius*fraction
                    pos = (distance*math.sin(angle),0,distance*math.cos(angle))
                    case = cull(pos,radius=radius)
                    if distance == 0 and not center_visible:
                        assert not case['visible'] and not case['math_calls'], case
                    else:
                        assert case['visible'] and case['direction_finite'] and case['angular_bound_finite'], case
                    assert not cull(pos,radius=radius,enabled=False)['visible']
                    inside_cases += 1

    # Capture submission arguments at a fake device vtable. Only the original
    # CPU dispatcher runs; returning S_OK does not test rasterization.
    device, vtable, buffer = SCRATCH+0xA000, SCRATCH+0xA100, SCRATCH+0xB000
    emu.write(device, struct.pack('<I', vtable))
    submissions = []
    draw_stubs = {STUBS+0x500:6, STUBS+0x520:8}
    for offset, stub in ((0x64, STUBS+0x500), (0x68, STUBS+0x520)):
        emu.write(vtable+offset, struct.pack('<I',stub))
        emu.write(stub, b'\x31\xc0\xc2'+struct.pack('<H', draw_stubs[stub]*4))
    def draw_hook(uc, address, size, _):
        if address in draw_stubs:
            count = draw_stubs[address]
            sp = uc.reg_read(UC_X86_REG_ESP)
            submissions.append(list(struct.unpack('<'+'I'*count, emu.read(sp+4,count*4))))
    emu.uc.hook_add(UC_HOOK_CODE, draw_hook, begin=STUBS+0x500, end=STUBS+0x520)
    draw_cases = 0
    for indexed in (False,True):
        for vertices in (0,3,300):
            for flags in (0,0xFFFFFFFF):
                emu.write(buffer, bytes(0x100))
                for offset,value in ((4,vertices*32),(0x44,32),(0x10,SCRATCH+0xC000),
                                     (0x40,0x112),(0x78,4),(0x18,6 if indexed else 0),
                                     (0x24,SCRATCH+0xD000)):
                    emu.write(buffer+offset,struct.pack('<I',value))
                submissions.clear()
                call(0x562210,buffer,device,flags)
                expected = [device,4,0x112,SCRATCH+0xC000,vertices]
                if indexed:
                    expected += [SCRATCH+0xD000,6]
                expected += [0]
                assert submissions == ([expected] if vertices else []), submissions
                draw_cases += 1

    # Failure injection at the device boundary, without a driver. The original
    # state wrapper discards HRESULT; report this separately from visual bugs.
    state_context, state_table = SCRATCH+0xE000, SCRATCH+0xF000
    emu.write(state_context,bytes(0x100))
    emu.write(state_context,struct.pack('<I',device))
    emu.write(state_context+0x10,struct.pack('<I',state_table))
    emu.write(state_table+7*8+4,struct.pack('<I',1))
    state_stub = STUBS+0x560
    draw_stubs[state_stub] = 3
    emu.uc.hook_add(UC_HOOK_CODE, draw_hook, begin=state_stub, end=state_stub)
    emu.write(vtable+0x50,struct.pack('<I',state_stub))
    state_results = []
    for hresult in (0,0x80004005):
        emu.write(state_stub,b'\xb8'+struct.pack('<I',hresult)+b'\xc2\x0c\x00')
        submissions.clear()
        result = call(0x566DF0,state_context,7,1)
        assert submissions == [[device,7,1]]
        assert result == 1
        state_results.append({'device_hresult':hex(hresult),'wrapper_result':result})

    # Compare the exact audited code spans, not whole-client equivalence.
    spans = {'world_transform':(0x542C80,0x542CD4), 'visibility':(0x543000,0x5432A1),
             'view_builder':(0x569880,0x569A00),'primitive_dispatch':(0x562210,0x5622DE),
             'state_wrapper':(0x566DF0,0x566F04),'flip':(0x556220,0x55627C)}
    comparisons = []
    root = Path(__file__).resolve().parents[1]
    for relative in ('game/offline-baseline-2.9.2/AOACLIENT.EXE','game/2.9.2/AOACLIENT.EXE'):
        path = root/relative
        if path.exists():
            candidate = PE(path)
            comparisons.append({'path':relative,'sha256':hashlib.sha256(candidate.data).hexdigest(),
                                'matches_original':{name:candidate.read_va(lo,hi-lo)==pe.read_va(lo,hi-lo) for name,(lo,hi) in spans.items()}})
    return {'source_sha256':PRISTINE_292,
            'culling_patch_enabled':corrected,
            'fpcw':hex(fpcw),
            'inside_sphere_cases':inside_cases,
            'scope':'original CPU routines with synthetic scene nodes; CRT trig substituted; no GPU or full scene traversal',
            'nested_transform_cases':120, 'maximum_matrix_error':worst,
            'world_submission_matrix_copy_cases':120,
            'primitive_dispatch_cases_with_mock_device':draw_cases,
            'state_failure_injection':state_results,
            'audited_code_comparisons':comparisons,
            'cache_contract':'position setter invalidates only the changed node; descendants require a separate notification/update path',
            'moving_turning_culling_cases':cases,
            'motion_samples':motion_samples,
            'angular_domain_cases':angular_domain_cases,
            'visibility_mismatches_with_nan_math_stub':visibility_mismatches,
            'near_center_cases':boundary, 'small_object_cutoff_cases':cutoff,
            'findings':['Single-precision normalized direction dot products can exceed [-1,1] before _CIacos.',
                        'Inside a bounding sphere, original code passes radius/distance > 1 to _CIasin.',
                        'At coincident camera/object origins, original x87 normalization creates nonfinite direction and final visibility is false.',
                        'Render-state wrapper returns 1 even when the mocked device returns E_FAIL.',
                        'Final visibility requires projected size strictly greater than 5.'],
            'unverified':['Whether normal update traversal invalidates every changed descendant.',
                          'Actual MSVCRT domain-error behavior and downstream use of nonfinite angular bounds.',
                          'Device transforms, depth, textures, draw calls, surface recovery and presentation.',
                          'Causality for the reported large-scale jumping; localhost host/client parity.']}


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    report = run(root/'game/2.9.2/AOACLIENT.EXE.orig')
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ('nested_transform_cases','maximum_matrix_error','moving_turning_culling_cases','findings')},indent=2))
