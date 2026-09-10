# Retrom SAME_CDI maintenance

The local maintenance baseline is EmulatorJS/same_cdi commit
`cfb05d803f54130adf94efef88edd816d01df7a3`, compatible with the EmulatorJS 4.2.3
linker and existing SAME_CDI state layout.

## CDIC audio timing

The core gives the guest six 75 Hz ticks to prepare a new disc read. A stopped
sound map releases its decoder on the following audio tick instead of waiting
another complete sound-map sector. The previous timing can put the guest audio
driver into repeated mute/restart cycles, causing sustained interruptions in
Nobelia Demo 1 even while rendering at its normal PAL 50 Hz.

These changes backport the CDIC timing corrections from MAME
[904d27ff43b0](https://github.com/mamedev/mame/commit/904d27ff43b01233c47fc4a0e75e462d9a695d24)
and [9c6c88b0697f](https://github.com/mamedev/mame/commit/9c6c88b0697fbe75f1df3017763fae17f3113d9d).
They do not disable guest mute commands, change CPU speed or alter state fields.
An old checkpoint also preserves the guest driver's execution state, so it may
continue the interrupted audio until the guest starts a new stream. A fresh boot
is required when comparing initialization timing.

## Checks

`python3 .github/rpg-runtime/test-cdic-timing.py` compiles the production CDIC
initialization and timer methods against a minimal device test double. It checks
read startup, subsequent sector cadence, cancellation, stop-marker handling and
sound-map restart without any game or BIOS. `--revision <commit>` runs the same
assertions against an earlier production implementation.

Manual product validation uses operator-supplied games and BIOS through Retrom's
PFB import, preview, launch, checkpoint and restore flows. Check fresh startup,
continuous music, movement/SFX, guest and host mute, exit and a new launch restored
from a checkpoint. Game files, BIOS, recordings and local evidence are not source
fixtures and must not be committed.
