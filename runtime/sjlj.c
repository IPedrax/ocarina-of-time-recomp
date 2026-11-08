// Written for ocarina-of-time-recomp (MIT, Copyright (c) 2026 Jeff Aigner).
// The guest's setjmp and longjmp across lifted code (docs/level.md). The game embeds Lua, which reports a script
// error by longjmp to the setjmp of its protected call (main+0x1661670 and two more sites; #13 found it). The guest
// longjmp restores the registers and returns to the saved x30, the instruction after the BL to setjmp: the middle
// of a lifted function, which rt_dispatch cannot enter ("not a function start"), so the game died at the first Lua
// error. recomp/gen.py now wraps each call to the setjmp PLT stub as
//     if (!RT_SETJMP(c)) <call setjmp>;   then every local register reloaded from the Cpu
// so a host setjmp sits in the generated function's own frame, keyed by the guest jmp_buf (x0). The observer of
// longjmp below finds that record, sets the Cpu as the guest longjmp would (SDK layout, sdk+0xaec40 / +0xaed50:
// x19-x28 at 0x00-0x48, x29 and x30 at 0x50, sp at 0x68, d8-d15 at 0x70-0xa8; x30 stored as pacib(lr ^ 1), and
// PACIB lifts as an identity), x0 = the value (1 for 0), the thread's host depth as it was at the setjmp, and
// longjmps the host there. The lifted frames in between are plain C frames, and the non-SEH longjmp (cpu.h)
// unwinds none of them. A longjmp whose jmp_buf no RT_SETJMP recorded runs the guest's own, as before.
#include <setjmp.h>
#include <stdint.h>
#include <string.h>

#include "platform/platform.h"
#include "cpu.h"
#include "host.h"

enum { SJ_N = 256 };
typedef struct {
    uint64_t buf;        // the guest jmp_buf, 0: free
    void *thread;        // the guest thread that took it
    int depth;           // its host depth then (hostfn.c kern_host_depth)
    jmp_buf host;
} SjRec;
static SjRec sj[SJ_N];
static PlatMutex sj_lock = PLAT_MUTEX_INIT;
static unsigned sj_next;
static int32_t sj_jumps, sj_misses;

jmp_buf *rt_sj_enter(Cpu *c) {
    uint64_t buf = c->x[0];
    SjRec *e = NULL;
    plat_mutex_lock(&sj_lock);
    for (int i = 0; i < SJ_N && !e; i++)   // the same jmp_buf again (Lua reuses its frame's): the newest setjmp wins
        if (sj[i].buf == buf && sj[i].thread == c->thread) e = &sj[i];
    for (int i = 0; i < SJ_N && !e; i++)
        if (!sj[i].buf) e = &sj[i];
    if (!e) e = &sj[sj_next++ % SJ_N];     // full: the oldest slot (a stale record, as the frames are nested)
    e->buf = buf, e->thread = c->thread, e->depth = c->thread ? *kern_host_depth(c->thread) : 0;
    plat_mutex_unlock(&sj_lock);
    return &e->host;
}

static void ov_longjmp(Cpu *c) {
    uint64_t buf = c->x[0];
    uint32_t val = (uint32_t)c->x[1];
    SjRec *e = NULL;
    plat_mutex_lock(&sj_lock);
    for (int i = 0; i < SJ_N && !e; i++)
        if (sj[i].buf == buf && sj[i].thread == c->thread) e = &sj[i];
    plat_mutex_unlock(&sj_lock);
    if (!e) {
        if (__atomic_add_fetch(&sj_misses, 1, __ATOMIC_SEQ_CST) <= 4)
            rt_log("sjlj: longjmp to %#llx, which no RT_SETJMP recorded: the guest's own longjmp", (unsigned long long)buf);
        rt_original(c);
        return;
    }
    const uint64_t *jb = (const uint64_t *)(uintptr_t)buf;
    for (int r = 19; r <= 29; r++) c->x[r] = jb[r - 19];
    c->x[30] = jb[11] ^ 1;
    c->sp = jb[13];
    for (int d = 8; d <= 15; d++) c->v[d] = jb[14 + (d - 8)];   // D registers: the upper halves read as zero
    c->x[0] = val ? val : 1;
    if (c->thread) __atomic_store_n(kern_host_depth(c->thread), e->depth, __ATOMIC_RELAXED);
    if (__atomic_add_fetch(&sj_jumps, 1, __ATOMIC_SEQ_CST) <= 8)
        rt_log("sjlj: longjmp to %#llx with %u: back to its setjmp (x30 %#llx, sp %#llx)", (unsigned long long)buf, val,
               (unsigned long long)c->x[30], (unsigned long long)c->sp);
    longjmp(e->host, 1);
}
HOST_OBSERVER("longjmp", ov_longjmp);
