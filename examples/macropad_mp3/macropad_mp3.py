# SPDX-FileCopyrightText: Copyright (c) 2021 Kattni Rembor for Adafruit Industries
#
# SPDX-License-Identifier: Unlicense
"""
MacroPad MP3 playback demo. Plays one of four different MP3 files when one of the first four keys
is pressed. All keys light up a color of the rainbow when pressed, but no audio is played for the
rest of the keys.
"""
from rainbowio import colorwheel
from adafruit_macropad import MacroPad

macropad = MacroPad()

# To include more MP3 files, add the names to this list in the same manner as the others.
# Then, add more key numbers below.
audio_files = ["slow.mp3", "happy.mp3", "beats.mp3", "upbeats.mp3"]

while True:
    key_event = macropad.keys.events.get()

    if key_event:
        if key_event.pressed:
            macropad.pixels[key_event.key_number] = colorwheel(
                int(255 / 12) * key_event.key_number
            )
            # If adding more MP3 files, add the appropriate key numbers to the tuple below.
            if key_event.key_number in (0, 1, 2, 3):
                macropad.play_file(audio_files[key_event.key_number])

        else:
            macropad.pixels.fill((0, 0, 0))
            macropad.stop_tone()
