#!/usr/bin/env python3
"""Exercise the production CDIC timer methods without a disc or BIOS."""
import argparse
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--revision', help='read production methods from this Git revision')
args = parser.parse_args()

def source(path):
    if args.revision:
        return subprocess.check_output(['git', '-C', str(ROOT), 'show', args.revision + ':' + path], text=True)
    return (ROOT / path).read_text()

def method(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

cpp = source('src/mame/machine/cdicdic.cpp')
header = source('src/mame/machine/cdicdic.h')
enums = header[header.index('\tenum : uint8_t'):header.index('\tdevcb_write_line m_intreq_callback')]
methods = '\n'.join(method(cpp, signature) for signature in (
    'void cdicdic_device::init_disc_read(', 'void cdicdic_device::cancel_disc_read(',
    'TIMER_CALLBACK_MEMBER( cdicdic_device::sector_tick )',
    'TIMER_CALLBACK_MEMBER( cdicdic_device::audio_tick )',
    'void cdicdic_device::process_audio_map(',
    'uint8_t cdicdic_device::get_sector_count_for_coding(',
))
stub = r'''
#include <array>
#include <cstdint>
#include <cstdio>
#define TIMER_CALLBACK_MEMBER(name) void name()
class cdicdic_device {
public:
ENUMS
    uint16_t m_command = 0x29, m_disc_command = 0, m_audio_buffer = 0;
    uint8_t m_disc_mode = 0, m_disc_spinup_counter = 0;
    uint32_t m_curr_lba = 0;
    uint16_t m_decode_addr = 0;
    uint8_t m_audio_sector_counter = 0, m_audio_format_sectors = 0;
    bool m_decoding_audio_map = false;
    std::array<uint8_t, 0x4000> m_ram{};
    int sectors = 0, audio_sectors = 0, interrupts = 0;
    bool end_of_disc = false;
    uint32_t lba_from_time() { return 123; }
    void process_disc_sector() { ++sectors; if (end_of_disc) m_disc_command = 0; }
    void play_audio_sector(uint8_t, const uint8_t *) { ++audio_sectors; }
    void update_interrupt_state() { ++interrupts; }
    void init_disc_read(uint8_t);
    void cancel_disc_read();
    void sector_tick();
    void audio_tick();
    void process_audio_map();
    static uint8_t get_sector_count_for_coding(uint8_t);
};
'''.replace('ENUMS', enums)
tests = r'''
int failures = 0;
void check(bool condition, const char *message) {
    if (!condition) { std::fprintf(stderr, "FAIL: %s\n", message); ++failures; }
}
int main() {
    cdicdic_device disc;
    disc.init_disc_read(cdicdic_device::DISC_MODE2);
    for (int tick = 0; tick < 6; ++tick) disc.sector_tick();
    check(disc.sectors == 0, "read must allow six 75 Hz spin-up ticks before transferring data");
    disc.sector_tick();
    check(disc.sectors == 1 && disc.m_curr_lba == 124, "first sector transfers after spin-up");
    disc.sector_tick();
    check(disc.sectors == 2, "subsequent sectors retain the 75 Hz cadence");
    disc.end_of_disc = true;
    disc.sector_tick();
    disc.sector_tick();
    check(disc.sectors == 3 && disc.m_disc_command == 0, "end of disc cancels subsequent reads");

    cdicdic_device audio;
    audio.m_decoding_audio_map = true;
    audio.m_audio_format_sectors = 8;
    constexpr int coding = (cdicdic_device::SECTOR_CODING2 - cdicdic_device::SECTOR_HEADER) ^ 1;
    audio.m_ram[coding] = 0xff;
    audio.audio_tick();
    check(audio.m_decode_addr == 0xffff && audio.audio_sectors == 0 && audio.interrupts == 1,
          "stop marker interrupts the previous stream without decoding it");
    audio.audio_tick();
    check(!audio.m_decoding_audio_map && audio.m_audio_format_sectors == 0,
          "stop marker must release decoding on the next tick, not wait another audio sector");
    // A guest can now start a new sound map, as regs_w permits only when decoding is idle.
    if (!audio.m_decoding_audio_map) {
        audio.m_decode_addr = 0;
        audio.m_ram[coding] = 0x05;
        audio.m_decoding_audio_map = true;
        audio.m_audio_sector_counter = 1;
    }
    audio.audio_tick();
    check(audio.audio_sectors == 1, "replacement sound map starts on its first tick");
    audio.m_ram[0x1a00 + coding] = 0x05;
    for (int tick = 0; tick < 7; ++tick) audio.audio_tick();
    check(audio.audio_sectors == 1, "stereo 18.9 kHz map does not consume the next sector early");
    audio.audio_tick();
    check(audio.audio_sectors == 2, "stereo 18.9 kHz map advances every eight ticks");
    if (!failures) std::puts("CDIC timing: PASS");
    return failures ? 1 : 0;
}
'''
with tempfile.TemporaryDirectory(prefix='retrom-cdic-test-') as temporary:
    path = pathlib.Path(temporary)
    (path / 'timing.cpp').write_text(stub + methods + tests)
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    str(path / 'timing.cpp'), '-o', str(path / 'timing')], check=True)
    subprocess.run([str(path / 'timing')], check=True)
