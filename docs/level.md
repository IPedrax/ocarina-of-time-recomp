# The level's picture

Hand-off for what keeps the first level (Kokiri Forest) from looking right, written 2026-11-08. It gathers the day's
measurements, the fixes, what two other projects on this game do, and the plan. Update the Status section as it
moves. The pointer design is `docs/pointers.md`, the mesh work `docs/mesh.md` and `docs/mesh-tracker.md`.

## Where it stands (2026-11-08, main at 8535fb7)

On the level route (`python3 tools/run.py --seconds 150 --replay build/logs/a-spam.txt --skip-movies`, no other
settings) the game reaches the level, runs at about 59-60 fps there, and draws its geometry: the wooden structures,
bark and moss, the ground, Navi. 0 validation errors, 0 shader failures in the boot summary (but see "Translator
failures" below). What is wrong:

1. **White areas.** Large regions are blown out white (`build/logs/fix4-level.png`, `merge-level-side.png`).
2. **Stretched triangles.** Long white slivers and spikes cross the view.
3. **Two kernels skipped by default** (`vk_exec_draw.c skip_cs`, `SKIP_CS_DEFAULT`, from #12's ee54468):
   `ace1cec0` (the level's background, 64x64 groups, six uniform slots: black and white blocks when it runs) and
   `3f15911a` (bit masks, see below). `OOT_SKIP_CS=none` runs them; every skip is logged once.
4. **Some mesh records still zero.** The shadow pass's (1600x1600) indirect mesh records read 0 0 0 0 in frame dumps
   455 and 456, so part of the culling chain still counts nothing (`docs/mesh-tracker.md`, log of 2026-11-08).

Before #12 the level was all black (the mesh draws drew nothing, `docs/mesh-tracker.md`).

## What was measured

**The white is unmapped HDR.** The end-of-frame kernel `3ce2b98c` (200 instructions, 128x1x1, writes R11G11B10F
through an R32UI view, 120x68 groups) works in place on the scene's HDR target. In frame dump 456 (frame 4500,
`3f15911a` skipped) its output equals the HDR buffer of pass 144 almost exactly (same minimum, max 34.5, 413,533
against 413,532 distinct values): it changed almost nothing, and values above 1 show as white. In dump 455
(`3f15911a` running, `OOT_SKIP_CS=ace1cec0`) its output still reaches 35.5. So `3ce2b98c` processes only what a mask
selects, and the mask it reads is nearly empty.

**The mask.** `3f15911a` (1304 instructions, 96x1x1, indirect dispatch between the histogram kernel `745220f3` and
`3ce2b98c`) builds bit masks (FLO, POPC, BREV) and ORs them with SURED into an RGBA8 image (tex 295, 1920x1080, at
0x1502ee0e00) that it views as R32UI (`nvnTextureViewSetFormat`, NVN format 0xB); `3ce2b98c` samples the same
address. Its output in dump 455 is almost all zero, a few speckles along the top edge and at the top right. It was
skipped (it did not lower) until main's LEA with a negated addend let it through, which is when the flickering
white patches appeared (#12, ee54468). Checked, all correct for the words in this kernel:
- the only negated LEA, at 0x4b50: `LEA.HI R1, R1, -R0, RZ, 30`, that is (R1 >> 2) - R0 (Lichii, Fritchii and
  Hookshot read bit 63 as negating Rb too, and lower it the same way);
- the FLO (unsigned, no .SH), the IADD3 31 - x, the SHF.R.U32.HI around it;
- the three SURED (0x59f): 2D, U32, OR, handle c[0][0x210];
- the translation: no dropped global access (empty notes), both LD resolve to storage buffers (c0+0x130, c0+0x1c0),
  the image is R32UI with an atomic OR;
- the binding: `reinterpret_format` should give the R32UI view (none of its exclusions applies to tex 295).
So the lowering of `3f15911a` is not where the bug is; its inputs, or what feeds the indirect dispatch, are next.

**Translator failures since #12.** 45 compute programs fail in the translator with "InvalidOperationException:
Invalid storage kind GlobalMemory" (runs 455, 456; none before the merge): a global access reached the SPIR-V
back end unreplaced. Their dispatches are skipped ("its shader did not translate"). The boot summary's "shader
failures 0" does not count them. Since 8535fb7 the cache keeps each refused program (`<key>.xfail.code`,
`<key>.xfail.json`) and the log names the stage; one reproduces offline (`oot_xlate` on the job with its `code`
pointed at the .xfail.code). Suspect: the GlobalToStorage changes of patches 0022/0023 (#12). Not yet found.

**A crash that was memory.** Twice `FATAL: rt_dispatch: no function at guest pc main+0x1661690` near frame 2830, with
"the system 84718 of 85781 MB" committed: another emulator (Lichii) was open. With it closed the same route ran 200
s. The game commits about 20 GB on the level; leave room.

## Fixed today

- **F2IP** (112df06, GuiFlam's from #7): 0x243 with a destination register is F2IP.U8.F32 (two floats clamped to
  bytes); it was lowered as FCHK, which dropped the result and cleared P0 (2 compute and 2 mesh programs of the cache).
- **HMNMX2** (cb3eed5): bits 73 and 62 are |a| and |b|, as every other half-precision decoder of ours reads that field
  and as Lichii, Fritchii, Hookshot and Mesa NAK do; the merge of #12 had put back the reading as negations. The
  histogram kernel `745220f3` uses them 31 times.
- **IMAD** (9e0fed1): the addend's negate is bit 63 in forms 3 and 7 (constant or uniform register in the wide slot),
  not 75 (`-UR4` became `+UR4`; 6 instances). The census of 14,363 programs refuses none for it.
- **SHF** (1eeae88): Ryujinx's MaxShift is 0 for 32-bit and 2 for U64; we wrote them swapped (wrong for shifts >= 32).
Probes pass, the title is unchanged (noise 0.55), the level looks the same: these were real, not the main cause.

## What the other projects on this game do

Both are GPL-3.0: read for behaviour only, no code taken. Local checkouts: see `CLAUDE.local.md`.

**Fritchii** (Frizti/Fritchii, a Lichii fork; commit c9ebb5c3 is its work on this game): instruction fixes (the
four above came from comparing with it), arbitration type 3 for WaitIfEqual64, compute storage bindings sized
min(layout, 8 MiB). It skips no program of this game by default (`EDEN_NX2_REJECT_HASH` is opt-in).

**Hookshot** (NotRexed/Hookshot, a native recompilation of this game; GPL-3.0 since 1720815, 2026-11-07, MIT before:
`vk_exec_draw.c` cites its `gpu/vk/vk_bank.cpp` for the task/mesh bank 0 and the compute uniform table, behaviour only).
It runs `3ce2b98c`, `3f15911a` and `ace1cec0` unmodified (its keys for them: 6637ac1d052d22d4, 685adb41edc19de7,
6f2a263dfafb02fe; FNV-1a-64 over the control's first 0xd8 bytes, then the code up to control+0x44,
`gpu/vk/vk_shader.cpp code_key`); `3ce2b98c`'s output averages about 0.7 there. What it does that we do not:
- **A pointer-pool table at c0+0x880** for task, mesh and compute stages (`vk_bank.cpp pointer_table`): the host scans
  the stage's small bound storage buffers (up to 256 bytes) for words that are GPU addresses outside every binding
  and binds up to three whole pools there. Its note: without it "skinned and instanced models lost their bones and
  collapsed into spikes". Ours: `vk_c0_fill` returns early for task and mesh stages; #12's `ptr_targets_add` binds
  pointer targets into free storage slots for vs, fs and cs only.
- **The mesh stage buffer zeroed** at the start of a mesh program (ae4fb30): the epilogue copies every vertex slot
  and index byte below the primitive count, so bytes never written were leftovers, "hundreds of long thin
  triangles". Our patch 0020 does not zero it.
- **Bare pointers bound to the end of their pool** (ffcdb71, 3858629): a table entry whose size word is 0; the fog
  reads light probes up to ~130 MB past such a pointer. A read-only bare entry is bound to the end of its pool (up
  to 1 GB), a written one with 1 MB, of which only the first 64 bytes are written back (copying back the guessed
  1 MB overwrote the CPU's data). Reads past the binding gave 0 and the fog went overbright: white haze.
- **Exposure meter coherence** (98563eb, e84d467, 8c28ed7): a GPU pass sums the frame's brightness into a small buffer
  that the CPU reads and resets; the CPU's read waits on the work that writes it, and pages the CPU reads back are
  copied again from guest memory at the start of each submission. Wrong, the exposure stays wrong.
- **Finite colour outputs** (`docs/design.md` section 10, `GuardFragmentOutputs`): one NaN spreads through bloom into a
  white frame.
- **Pointer page table**: flat, 4 KiB pages over two windows, PhysicalStorageBuffer reads, its address in a push
  constant; stores through it off by default (they faulted a GPU), task and mesh behind a switch. Close to our P1/P2.
- Smaller: HMNMX2's immediate form 0x840 (we refuse it: fragment program 7132f633); signed and SHF.R.HI funnel
  shifts (we refuse them); point topology for mesh programs (control 0x5f = 1; all 42 of our mesh stages are 3,
  triangles); 8- and 16-bit global loads in the fallback search; storage tables for tessellation and geometry
  stages; point size 2047.9375 (ours 2047.0). It skips draws of one program (53509044401d78d2, not in our cache)
  and replaces the TAAU network with a linear upscale only where matrix multiplies are emulated.

## Plan

1. **The pointer-pool table at c0+0x880 for task, mesh and compute** (the spikes). What each stage's program reads
   there, how many entries, their layout; then the host side, reusing #12's pointer scan (`ptr_targets_add`).
2. **Zero the mesh stage buffer** at the start of a mesh program (translator patch 0020 or a new one).
3. **Bare pointers bound to the end of their pool, and the exposure readback** (the white).
4. **The 45 translator failures** ("Invalid storage kind GlobalMemory").
5. **P2** of `docs/pointers.md`, the page-table fallback (my edits saved before #12, to be rebuilt on its 0022/0023).
After each change that alters what a shader computes: the `verify-shader-change` skill.

## Open questions and loose ends

- `3f15911a`'s inputs: its indirect dispatch's group count (which kernel writes it), tex 14608 (rg16ui 480x270) and
  tex 292 (rg8 192x128) that it reads.
- HMNMX2 is lowered as `m * (a - b) + b`, which gives NaN when an operand is infinite or |a - b| overflows half
  precision; Fritchii widens to f32 and uses FMNMX. The same in `h2_relu` with -inf. A NaN source for white areas.
- ISETP.EX restores its saved predicate under the instruction's own guard; Fritchii unconditionally (no program of
  the cache is affected).
- Ryujinx's funnel shift `(A >> B) | (C << (32 - B))` shifts by 32 when B is 0, which SPIR-V leaves undefined; NVIDIA
  gives the right answer, other GPUs may not (#9 is an AMD card).
- RED.ADD.F32 offsets are cut to 20 bits silently (Fritchii range-checks them).
- `tools/xlate/wip/0025` (#12, numbered 0024 there before main took 0024) was written for the branch's page-table layout, which the merge left out; it does not
  match P1's table at support-buffer byte 1408.

## Status

- 2026-11-08: written; next is item 1 of the plan.
- 2026-11-08: item 1, as it turned out. No program of the game reads bank 0 at 0x880 or above (a scan of the
  14,363 census programs: the highest offsets are the task and mesh tables at 0x670 and 0x770): Hookshot's table there
  is its own, an area its fallback searches. Ours is #12's: 0022 searches the stage's storage table, ptr_targets_add
  fills its free slots. What was missing, now done:
  - translator patch 0024: 32 storage-buffer slots instead of 16 (0022's sixteen table targets crowded out the
    shader's own buffers: "Failed to reserve storage buffer", 624 dropped loads and 12 atomics in 33 compute programs,
    72 loads and 12 atomics in 9 mesh programs, 6 loads in 3 task programs; and the 45 "Invalid storage kind
    GlobalMemory" failures, all 86 refused jobs kept so far now translate and pass spirv-val), and the task and mesh
    tables (0x670, 0x770) for 0022's search, where those stages searched compute's 0x310;
  - `op_draw_mesh_ptr`: pointer targets bound for the task, mesh and fragment stages of mesh draws (run 463 logs them,
    e.g. a 64 MiB target for mesh storage slot 1).
  Level route: 0 InvalidOperation failures (19 lowering refusals left), ~54-59 fps; the picture still has the white
  areas and the spikes (`build/logs/item1-level.png`, a different moment of the route), the title is unchanged
  (noise 0.54), and the chain's indirect records still read 0 from frame 4000 (`OOT_MESH_IND_LOG=4000`). Next: item 2.
