# Sharper ship and station skins (optional)

This replaces 104 of the game's textures with versions at twice the
resolution and in full 32-bit colour: every fighter, the capital ships,
docks, stations, asteroids, turrets, window strips and faction logos. The
space backgrounds stay as they were.

The project never ships these images. They are derived from Flying Rock's
art, so your PC makes them from your own game files, using the free AI
upscaler Real-ESRGAN. It changes only what you see. Other players don't need
it, and it doesn't affect hit boxes, physics or the server.

## Before you start

- Finish steps 1–3 of [play.md](play.md), so `game\2.9.2` exists and runs.
- A graphics card with Vulkan support (most cards and integrated graphics
  from 2016 on).
- About 500 MB of free disk space.
- About half an hour, mostly unattended: 20–30 minutes to build the skins
  (23 on integrated AMD graphics) and a few minutes to install them.

Run everything from a PowerShell window at the repository root, with the
game closed.

## 1. Update the project

```powershell
git pull
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

This adds the Pillow image library that the build step uses.

## 2. Download Real-ESRGAN

Download
[realesrgan-ncnn-vulkan-20220424-windows.zip](https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip)
(45 MB), from the official Real-ESRGAN releases page. Make its folder and
move the zip there, **without unzipping it**:

```powershell
New-Item -ItemType Directory -Force originals\tools\realesrgan-ncnn-vulkan-20220424
Move-Item $HOME\Downloads\realesrgan-ncnn-vulkan-20220424-windows.zip originals\tools\realesrgan-ncnn-vulkan-20220424\
```

The build step checks the file's fingerprint (SHA-256) and accepts only this
exact release.

## 3. Turn on 32-bit textures

The game normally squeezes textures down to 16-bit colour, which would throw
the extra detail away. This client fix stops that:

```powershell
.venv\Scripts\python.exe -I tools\texture32.py game\2.9.2\AOACLIENT.EXE
```

It's worth having even without the new skins: it removes colour banding from
the original art too.

## 4. Build the skins

```powershell
.venv\Scripts\python.exe -I tools\build_texture_pack.py game\2.9.2
```

It prints one line per skin, `[1/104]` to `[104/104]`, and saves them in
`work\texture-pack\build`. If you stop it or it fails part-way, run the same
command again: finished skins are kept.

To try it on the 26 fighters first (about 6 minutes), add `--group fighters`.
Running the full command later adds the rest.

## 5. Install them

```powershell
.venv\Scripts\python.exe -I tools\texture_pack.py game\2.9.2 --from-dir work\texture-pack\build
```

This rebuilds the game's `TEXTURES.AOA` and `DATA.AOA` with the new skins.
The originals are kept beside them as `*.before-texture-pack`. When it
finishes it prints a summary that lists the two archives.

## 6. Check and fly

```powershell
.venv\Scripts\python.exe -I tools\prepare_client.py launch game\2.9.2\AOACLIENT.EXE
```

`launch` checks the game folder first and refuses to start if anything is
wrong.

To confirm a skin really loaded at the new size, close the game and search
the graphics log for your ship's skin. For the Ym Khtat:

```powershell
Select-String "Load Texture.. .*YmKhtat" game\2.9.2\Logs\DxGfx1.log
```

You should see `(512 512 24) Format(8888)`. The old size is `(256 256 24)`.

## Removing it

With the game closed:

```powershell
.venv\Scripts\python.exe -I tools\texture_pack.py game\2.9.2 --undo
.venv\Scripts\python.exe -I tools\texture32.py game\2.9.2\AOACLIENT.EXE --undo
```

The first command puts back the original archives exactly. The second
removes the 32-bit fix; you can keep that one if you like.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `missing originals\tools\...zip` | Step 2: the zip isn't in that folder, or it has a different name. |
| `does not match the expected SHA-256` | The download is incomplete or a different release. Download it again from the link in step 2. |
| Real-ESRGAN fails with a Vulkan error | Update your graphics driver. Without Vulkan support it can't run. |
| `is not the pinned original` | `TEXTURES.AOA` or `DATA.AOA` was changed some other way. Delete `game\2.9.2` and run step 3 of [play.md](play.md) again. |
| `changed outside the recorded texture pack` | An archive was edited after installing. Run `--undo`, then install again. |
| A ship or object looks black, white or garbled | Run the two removal commands above, then open an issue with the object's name and a screenshot. |
| `prepare_client.py undo` | This restores the executable from before setup, which also removes the 32-bit fix. Run step 3 again if you want it back. |

What the build does, how it was checked, and which textures were left out
and why: [client-setup.md](client-setup.md#optional-replacement-texture-pack).
The skin list is [`config/texture-pack.json`](../config/texture-pack.json).
