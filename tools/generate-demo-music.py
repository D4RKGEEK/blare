"""
Generate an original backing track for the blare demo.

Synthesised from scratch rather than sourced, so there is no licence and no
Content ID risk on YouTube or Product Hunt. Written against the video's actual
cut points: title at 0s, terminal at 3.2s, counter at 10.8s, result at 17.2s,
end card at 21.8s.
"""

import array
import math
import random
import wave

SR = 44100
DUR = 25.0
N = int(SR * DUR)

# 100 BPM. The counter section lands on the beat.
BEAT = 60.0 / 100.0

left = [0.0] * N
right = [0.0] * N
random.seed(7)


def env(t, start, attack, hold, release):
    """Simple AHR envelope in seconds."""
    x = t - start
    if x < 0:
        return 0.0
    if x < attack:
        return x / attack
    if x < attack + hold:
        return 1.0
    r = x - attack - hold
    if r < release:
        return 1.0 - r / release
    return 0.0


def add(buf_l, buf_r, start, dur, fn, gain, pan=0.0):
    i0 = int(start * SR)
    i1 = min(N, i0 + int(dur * SR))
    gl = gain * (1.0 - max(0.0, pan))
    gr = gain * (1.0 + min(0.0, pan))
    for i in range(max(0, i0), i1):
        t = (i - i0) / SR
        v = fn(t)
        buf_l[i] += v * gl
        buf_r[i] += v * gr


def note(freq, dur, attack=0.004, release=None, detune=0.0, harmonics=(1.0, 0.35, 0.16)):
    rel = release if release is not None else dur * 0.9

    def f(t):
        if t > dur:
            return 0.0
        e = env(t, 0.0, attack, max(0.0, dur - attack - rel), rel)
        s = 0.0
        for k, amp in enumerate(harmonics, start=1):
            s += amp * math.sin(2 * math.pi * freq * k * t + detune * k)
        return s * e / sum(harmonics)

    return f


def pad(freqs, dur):
    def f(t):
        e = env(t, 0.0, 1.6, max(0.0, dur - 3.4), 1.8)
        s = 0.0
        for fr in freqs:
            # Two slightly detuned voices per note gives it some width.
            s += math.sin(2 * math.pi * fr * t)
            s += 0.8 * math.sin(2 * math.pi * fr * 1.004 * t + 0.6)
        return s * e / (len(freqs) * 2)

    return f


def kick(t):
    if t > 0.38:
        return 0.0
    # Pitch sweep from 110Hz down to 42Hz.
    f = 42 + 68 * math.exp(-t * 26)
    return math.sin(2 * math.pi * f * t) * math.exp(-t * 7.5)


def hat(t):
    if t > 0.06:
        return 0.0
    return (random.random() * 2 - 1) * math.exp(-t * 90)


# ---- A minor: Am - F - C - G -------------------------------------------
A2, C3, E3, F2, A3, C4, G2, B3, D4, E4, G4 = (
    110.00, 130.81, 164.81, 87.31, 220.00, 261.63, 98.00, 246.94, 293.66, 329.63, 392.00
)
CHORDS = [
    (0.0, [A2, C3, E3]),
    (6.0, [F2, A3, C4]),
    (12.0, [C3, E3, G4 / 2]),
    (18.0, [G2, B3, D4]),
]
for start, freqs in CHORDS:
    add(left, right, start, 7.4, pad(freqs, 7.4), 0.20)

# ---- arpeggio: enters with the terminal, pentatonic, 1/8 notes ---------
ARP = [A3, C4, E4, G4, E4, C4]
step = BEAT / 2
t = 3.2
idx = 0
while t < 21.6:
    # Swells with the counter section, then backs off for the result.
    if t < 10.8:
        g = 0.055
    elif t < 17.2:
        g = 0.055 + 0.055 * ((t - 10.8) / 6.4)
    else:
        g = 0.05
    f = ARP[idx % len(ARP)]
    if idx % 12 == 6:
        f *= 1.5  # a lift every bar and a half
    add(left, right, t, step * 1.6, note(f, step * 1.5, attack=0.003),
        g, pan=0.35 * math.sin(idx * 0.7))
    t += step
    idx += 1

# ---- drums: only while the counter runs --------------------------------
t = 10.8
while t < 21.4:
    add(left, right, t, 0.4, kick, 0.52)
    add(left, right, t + BEAT / 2, 0.07, hat, 0.085, pan=0.25)
    t += BEAT

# ---- riser into the result ---------------------------------------------
def riser(t):
    span = 6.0
    if t > span:
        return 0.0
    p = t / span
    n = random.random() * 2 - 1
    return n * (p ** 3) * 0.6 + math.sin(2 * math.pi * (200 + 900 * p ** 2) * t) * (p ** 4) * 0.3

add(left, right, 11.2, 6.0, riser, 0.30)

# ---- impact on the result reveal ---------------------------------------
def impact(t):
    if t > 1.6:
        return 0.0
    body = math.sin(2 * math.pi * (55 + 30 * math.exp(-t * 18)) * t) * math.exp(-t * 3.2)
    air = (random.random() * 2 - 1) * math.exp(-t * 14) * 0.35
    return body + air

add(left, right, 17.2, 1.8, impact, 0.55)

# ---- resolve chord on the end card -------------------------------------
add(left, right, 21.8, 3.2, pad([A2, C3, E3, A3], 3.2), 0.26)

# ---- master: soft clip, global fades -----------------------------------
frames = array.array("h")
fade_in = int(0.8 * SR)
fade_out_start = int(23.4 * SR)
for i in range(N):
    g = 1.0
    if i < fade_in:
        g = i / fade_in
    elif i > fade_out_start:
        g = max(0.0, 1.0 - (i - fade_out_start) / (N - fade_out_start))
    for buf in (left, right):
        pass
    l = math.tanh(left[i] * 1.25) * 0.82 * g
    r = math.tanh(right[i] * 1.25) * 0.82 * g
    frames.append(int(max(-1.0, min(1.0, l)) * 32767))
    frames.append(int(max(-1.0, min(1.0, r)) * 32767))

with wave.open("music.wav", "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(frames.tobytes())
print("wrote music.wav", round(DUR, 1), "seconds")
