# Ocarina of Time PC Recomp

Research project: static recompilation of *The Legend of Zelda: Ocarina of Time* (title id `04004860224DEC00`) into a
native Windows program, by the method of [totk-pc-recomp](https://github.com/valentderah/totk-pc-recomp) as carried
to further games by [fe3h-pc-recomp](https://github.com/jaigner-hub/fe3h-pc-recomp) and
[metroid-prime-4-recomp](https://github.com/jaigner-hub/metroid-prime-4-recomp). The game's code is lifted to C,
compiled for x86-64 and linked with a host runtime that stands in for the console's OS and graphics API on Vulkan.

This is the fourth game on that code and the first Switch 2 title, so the project also tests how much of the shared
core survives a new console generation.

## Status

As of 2026-11-08 the game is playable from the title through its opening into Kokiri Forest, at about 50-60 fps on an
RTX 4070, but it doesn't look right yet. Details and dates are in [docs/plan.md](docs/plan.md), the shader work in
[docs/phase3.md](docs/phase3.md), and the state of the level picture in [docs/level.md](docs/level.md).

What works:

- The dump extracts (`tools/extract_nup.py`, the Switch 2's `.nup` container and zbic-compressed NSOs), the three
  game modules lift to C and `oot.exe` builds and links. Start-up runs without a crash: audio, saves, the online
  services offline.
- Shaders: the Switch 2's are SM86 (Ampere) code, which the Maxwell translator from the earlier ports can't read.
  `runtime/sm86_lower.c` lowers them to Maxwell in front of the translator; 14,334 of the game's 14,363 programs
  lower. The game's neural upscaler runs on the host GPU's tensor cores (Vulkan cooperative matrices).
- The title screen and menu render correctly at 60 fps; the opening cinematic plays (AV1, decoded with dav1d).
- In the game: mesh and task shaders, bindless textures, pointers that shaders load from memory, occlusion queries,
  and the game's embedded Lua (its error handling uses `setjmp`/`longjmp`, which the runtime now supports).

What doesn't work yet:

- The level draws most of its geometry, but some is still missing. Where it's missing, the bright sky shows through
  as white areas, and long white triangles cross the view. The game's culling pass still counts nothing, so its
  mesh draws draw nothing; finding why is the current work (`docs/level.md`).
- Two compute kernels are skipped by default because they write wrong values (`OOT_SKIP_CS=none` runs them).
- Not yet tested beyond the first area. Only checked on NVIDIA; an AMD RX 9060 XT hangs after the title (#9).

Contributors' work landed in #2, #4, #5, #10, #12 and #13 (and a cherry-pick from #7); thank you.

This repository contains no game content. You need your own dump of the game and the keys from your own console. The
content check (`tools/check_content.py`, run by the pre-commit hook and CI) keeps it that way.

## Building

The game runs into the first area with rendering faults (see Status). Commands are shown for Windows; from WSL the same
scripts run (the build itself still uses Windows Python and MSYS2 through interop).

Needs:

- Python 3.14 or later for the extraction (its standard library reads zstd), and a Python 3.12 or later venv with
  `tools/requirements.txt` for the generator and the build.
- MSYS2 with the UCRT64 toolchain and the libraries the runtime builds against. The tools look for it in
  `OOT_MSYS2`, then `toolchain/msys64` in the repository, then `C:\msys64`. In the MSYS2 UCRT64 shell:

  ```
  pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-clang mingw-w64-ucrt-x86_64-lld \
      mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-sdl3 mingw-w64-ucrt-x86_64-vulkan-headers \
      mingw-w64-ucrt-x86_64-vulkan-loader mingw-w64-ucrt-x86_64-vulkan-memory-allocator mingw-w64-ucrt-x86_64-opus \
      mingw-w64-ucrt-x86_64-libvpx mingw-w64-ucrt-x86_64-dav1d mingw-w64-ucrt-x86_64-openh264 \
      mingw-w64-ucrt-x86_64-shaderc mingw-w64-ucrt-x86_64-spirv-tools
  ```

  (gcc for `tools/build_zbic.py`; openh264 because the movie code includes its headers and the build copies its DLL;
  shaderc and spirv-tools for `tools/build_shaders.py` and checking translated shaders.)
- The .NET 10 SDK and the MSVC build tools for the shader translator.
- A Vulkan GPU; the title screen's upscaler is fastest with `VK_KHR_cooperative_matrix` (recent NVIDIA, AMD or Intel).
- About 30 GB free for the extracted RomFS, besides the dump.
- Memory: the game commits about 21 GB on the level, so Windows needs that much free commit (RAM plus page file).

Steps:

1. Copy `config.example.toml` to `config.local.toml` and point `base` at your `.nup`.
2. `python tools/build_zbic.py` builds the decoder for the Switch 2's compressed executables.
3. `py -3.14 tools/extract_nup.py` extracts the ExeFS and RomFS to `build/extracted/v131072/` and checks every file
   against the hash in the container. `tools/build_game.py` takes only a checked RomFS, so do not pass
   `--no-verify`; to redo only the RomFS, add `--romfs-only`.
4. `python recomp/gen.py --exefs build/extracted/v131072/exefs --out generated/v131072` lifts the game's code to C
   (about a gigabyte of it).
5. `python tools/build_xlate.py` builds the shader translator, then `python tools/build_game.py` compiles and links
   `build/v131072/oot.exe`.
6. Run `build\v131072\oot.exe`, or `python3 tools/run.py` from WSL, which also sets the environment and keeps the
   window's focus (the game pauses without it).

## License

MIT, see [LICENSE](LICENSE). Code from other projects is listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
