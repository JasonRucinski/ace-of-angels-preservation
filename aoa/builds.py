"""Known client and installer hashes of the recovered builds, keyed by version.

One copy of the SHA-256 values that manifest/downloads.json records (and
config/client-2.9.2.json for the 2.9.2 installer); tests/test_builds.py
checks that they agree. Standard library only, so every layer may import it.
"""
import hashlib
from pathlib import Path

# The original client executable (AOACLIENT.EXE, or AoAClient.exe for 2.3.1).
CLIENT_SHA256 = {
    "2.0.0": "2faa8ab2161c2ef83a76627171692e95516b626590f1606b10d9192dace122bd",
    "2.3.1": "c80cd9f2998d326ffc0b6aa99ea4fdd1a5846411a84d26d12ab99216b7edc61a",
    "2.7.1": "b179c3c22e6426d55de52d57476aaa53b7e92622009daf754c5153be0b7503a7",
    "2.8.0": "809ecfc42c9b2cdb1b2dc54e0945160649f40c32e267d6a96ec7e207f44a9145",
    "2.8.2": "4783759e27e5ae64fcc554008037e6a191dba3488067ee945d95caeab000aaba",
    "2.9.2": "4b6c35e2b3ab473bd98c0afa6538079ee78678d85c28406c07bc27a08cc78c7e",
}
# The full installer executable (for 2.8.0 the EXE inside the RAR). 2.3.1 has
# none: it survives only as a replacement client.
INSTALLER_SHA256 = {
    "2.0.0": "7775e7ac7f4a30a5fb4c712061c704694926923de60004a5ae6f67b4f976f0d7",
    "2.7.1": "c3f041d08cfc812f346a8c64add585b3a9ac0297fb2cab11ec0fb0f05ff117c2",
    "2.8.0": "32f457c9b9891d231db2b2ae43735fe48c6a839f916392211e943672045b866d",
    "2.8.2": "9edcb5376d875188a6986067a3fd05952fb25086db0c456f01bfdfd84e840052",
    "2.9.2": "90c4a47e5df320171667209288edbe9899f957a397cb982bc459f17c785cbe38",
}


def require_build(data_or_path, version):
    """Return the bytes if they are the original `version` client, else raise ValueError.

    Takes the executable's bytes or a path to it. The message is one line.
    """
    if isinstance(data_or_path, (bytes, bytearray, memoryview)):
        data, name = bytes(data_or_path), "client"
    else:
        data, name = Path(data_or_path).read_bytes(), str(data_or_path)
    if version not in CLIENT_SHA256:
        raise ValueError(f"unknown client version {version!r}")
    digest = hashlib.sha256(data).hexdigest()
    if digest != CLIENT_SHA256[version]:
        raise ValueError(f"{name}: SHA-256 {digest} is not the original {version} client")
    return data
