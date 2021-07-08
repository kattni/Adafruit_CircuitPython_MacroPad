# SPDX-FileCopyrightText: Copyright (c) 2021 Kattni Rembor for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
`adafruit_macropad`
================================================================================

A helper library for the Adafruit MacroPad RP2040.


* Author(s): Kattni Rembor

Implementation Notes
--------------------

**Hardware:**

* `Adafruit MacroPad RP2040 Bare Bones <https://www.adafruit.com/product/5100>`_
* `Adafruit MacroPad RP2040 Starter Kit <https://www.adafruit.com/product/5128>`_

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads

* Adafruit's CircuitPython NeoPixel library:
  https://github.com/adafruit/Adafruit_CircuitPython_NeoPixel

"""

import array
import math
import time
import board
import digitalio
import rotaryio
import keypad
import neopixel
import displayio
import audiopwmio
import audiocore
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode
from adafruit_hid.mouse import Mouse
import usb_midi
import adafruit_midi
from adafruit_midi.note_on import NoteOn
from adafruit_midi.note_off import NoteOff
from adafruit_midi.pitch_bend import PitchBend
from adafruit_midi.control_change import ControlChange
from adafruit_midi.program_change import ProgramChange
from adafruit_simple_text_display import SimpleTextDisplay


__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_MacroPad.git"


class MacroPad:
    """
    Class representing a single MacroPad.

    :param int rotation: The rotational position of the MacroPad. Allows for rotating the MacroPad
                         in 90 degree increments to four different positions and rotates the keypad
                         layout and display orientation to match. Keypad layout is always left to
                         right, top to bottom, beginning with key number 0 in the top left, and
                         ending with key number 11 in the bottom right. Supports ``0``, ``90``,
                         ``180``, and ``270`` degree rotations. ``0`` is when the USB port is at
                         the top, ``90`` is when the USB port is to the left, ``180`` is when the
                         USB port is at the bottom, and ``270`` is when the USB port is to the
                         right. Defaults to ``0``.
    :param int or tuple midi_in_channel: The MIDI input channel. This can either be an integer for
                                         one channel, or a tuple of integers to listen on multiple
                                         channels. Defaults to 0.
    :param int midi_out_channel: The MIDI output channel. Defaults to 0.

    The following shows how to initialise the MacroPad library with the board rotated 90 degrees,
    and the MIDI channels both set to 1.

    .. code-block:: python

        from adafruit_macropad import MacroPad

        macropad = MacroPad(rotation=90, midi_in_channel=1, midi_out_channel=1)
    """

    # pylint: disable=invalid-name, too-many-instance-attributes, too-many-public-methods
    def __init__(self, rotation=0, midi_in_channel=0, midi_out_channel=0):
        if rotation not in (0, 90, 180, 270):
            raise ValueError("Only 90 degree rotations are supported.")

        # Define keys:
        if rotation == 0:
            self._key_pins = (
                board.KEY1,
                board.KEY2,
                board.KEY3,
                board.KEY4,
                board.KEY5,
                board.KEY6,
                board.KEY7,
                board.KEY8,
                board.KEY9,
                board.KEY10,
                board.KEY11,
                board.KEY12,
            )

        if rotation == 90:
            self._key_pins = (
                board.KEY3,
                board.KEY6,
                board.KEY9,
                board.KEY12,
                board.KEY2,
                board.KEY5,
                board.KEY8,
                board.KEY11,
                board.KEY1,
                board.KEY4,
                board.KEY7,
                board.KEY10,
            )

        if rotation == 180:
            self._key_pins = (
                board.KEY12,
                board.KEY11,
                board.KEY10,
                board.KEY9,
                board.KEY8,
                board.KEY7,
                board.KEY6,
                board.KEY5,
                board.KEY4,
                board.KEY3,
                board.KEY2,
                board.KEY1,
            )

        if rotation == 270:
            self._key_pins = (
                board.KEY10,
                board.KEY7,
                board.KEY4,
                board.KEY1,
                board.KEY11,
                board.KEY8,
                board.KEY5,
                board.KEY2,
                board.KEY12,
                board.KEY9,
                board.KEY6,
                board.KEY3,
            )

        self._keys = keypad.Keys(self._key_pins, value_when_pressed=False, pull=True)

        # Define rotary encoder:
        self._encoder = rotaryio.IncrementalEncoder(board.ROTA, board.ROTB)
        self._encoder_switch = digitalio.DigitalInOut(board.BUTTON)
        self._encoder_switch.switch_to_input(pull=digitalio.Pull.UP)

        # Define display:
        self._display = board.DISPLAY
        self._display.rotation = rotation

        # Define audio:
        self._speaker_enable = digitalio.DigitalInOut(board.SPEAKER_SHUTDOWN)
        self._speaker_enable.switch_to_output(value=False)
        self._sample = None
        self._sine_wave = None
        self._sine_wave_sample = None

        # Define LEDs:
        self._pixels = neopixel.NeoPixel(board.NEOPIXEL, 12, brightness=0.5)
        self._led = digitalio.DigitalInOut(board.LED)
        self._led.switch_to_output()

        # Define HID:
        self._keyboard = Keyboard(usb_hid.devices)
        # This will need to be updated if we add more keyboard layouts. Currently there is only US.
        self._keyboard_layout = KeyboardLayoutUS(self._keyboard)
        self._consumer_control = ConsumerControl(usb_hid.devices)
        self._mouse = Mouse(usb_hid.devices)

        # Define MIDI:
        self._midi = adafruit_midi.MIDI(
            midi_in=usb_midi.ports[0],
            # MIDI uses channels 1-16. CircuitPython uses 0-15. Ergo -1.
            in_channel=midi_in_channel - 1,
            midi_out=usb_midi.ports[1],
            out_channel=midi_out_channel - 1,
        )

    Keycode = Keycode
    """
    The contents of the Keycode module are available as a property of MacroPad. This includes all
    keycode constants available within the Keycode module, which includes all the keys on a
    regular PC or Mac keyboard.

    Remember that keycodes are the names for key _positions_ on a US keyboard, and may not
    correspond to the character that you mean to send if you want to emulate non-US keyboard.
    """

    ConsumerControlCode = ConsumerControlCode
    """
    The contents of the ConsumerControlCode module are available as a property of MacroPad.
    This includes the available USB HID Consumer Control Device constants. This list is not
    exhaustive.
    """

    Mouse = Mouse
    """
    The contents of the Mouse module are available as a property of MacroPad. This includes the
    ``LEFT_BUTTON``, ``MIDDLE_BUTTON``, and ``RIGHT_BUTTON`` constants. The rest of the
    functionality of the ``Mouse`` module should be used through ``macropad.mouse``.
    """

    @property
    def pixels(self):
        """Sequence-like object representing the twelve NeoPixel LEDs in a 3 x 4 grid on the
        MacroPad. Each pixel is at a certain index in the sequence, numbered 0-11. Colors can be an
        RGB tuple like (255, 0, 0) where (R, G, B), or an RGB hex value like 0xFF0000 for red where
        each two digits are a color (0xRRGGBB). Set the global brightness using any number from 0
        to 1 to represent a percentage, i.e. 0.3 sets global brightness to 30%. Brightness defaults
        to 1.

        See `neopixel.NeoPixel` for more info.

        The following example turns all the pixels green at 50% brightness.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            macropad.pixels.brightness = 0.5

            while True:
                macropad.pixels.fill((0, 255, 0))

        The following example sets the first pixel red and the twelfth pixel blue.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                macropad.pixels[0] = (255, 0, 0)
                macropad.pixels[11] = (0, 0, 255)
        """
        return self._pixels

    @property
    def red_led(self):
        """The red led next to the USB port.

        The following example blinks the red LED every 0.5 seconds.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
              macropad.red_led = True
              time.sleep(0.5)
              macropad.red_led = False
              time.sleep(0.5)
        """
        return self._led.value

    @red_led.setter
    def red_led(self, value):
        self._led.value = value

    @property
    def keys(self):
        """
        The keys on the MacroPad. Uses events to track key number and state, e.g. pressed or
        released. You must fetch the events using ``keys.event.get()`` and then the events are
        available for usage in your code. Each event has three properties:
            * ``key_number``: the number of the key that changed. Keys are numbered starting at 0.
            * ``pressed``: ``True`` if the event is a transition from released to pressed.
            * ``released``: ``True`` if the event is a transition from pressed to released.
                            ``released`` is always the opposite of ``pressed``; it's provided
                            for convenience and clarity, in case you want to test for
                            key-release events explicitly.

        The following example prints the key press and release events to the serial console.

        .. code-block:: python


            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                event = macropad.keys.event.get()
                if event:
                    print(event)
        """
        return self._keys

    @property
    def encoder(self):
        """
        The rotary encoder relative rotation position. Always begins at 0 when the code is run, so
        the value returned is relative to the initial location.

        The following example prints the relative position to the serial console.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                print(macropad.encoder)
        """
        return self._encoder.position * -1

    @property
    def encoder_switch(self):
        """
        The rotary encoder switch. Returns ``True`` when pressed.

        The following example prints the status of the rotary encoder switch to the serial console.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                print(macropad.encoder_switch)
        """
        return not self._encoder_switch.value

    @property
    def keyboard(self):
        """
        A keyboard object used to send HID reports. For details, see the ``Keyboard`` documentation
        in CircuitPython HID: https://circuitpython.readthedocs.io/projects/hid/en/latest/index.html

        The following example types out the letter "a" when the first key is pressed.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:

        """
        return self._keyboard

    @property
    def keyboard_layout(self):
        """
        Map ASCII characters to the appropriate key presses on a standard US PC keyboard.
        Non-ASCII characters and most control characters will raise an exception.

        """
        return self._keyboard_layout

    @property
    def consumer_control(self):
        """
        Send ConsumerControl code reports, used by multimedia keyboards, remote controls, etc.

        The following
        """
        return self._consumer_control

    @property
    def mouse(self):
        """
        Send USB HID mouse reports.
        """
        return self._mouse

    @property
    def midi(self):
        """
        The MIDI object. Used to send and receive MIDI messages. For more details, see the
        ``adafruit_midi`` documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/

        """
        return self._midi

    @staticmethod
    def NoteOn(note, velocity=127, *, channel=None):
        """
        Note On Change MIDI message. For more details, see the ``adafruit_midi.note_on``
        documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/

        :param note: The note (key) number either as an int (0-127) or a str which is parsed, e.g.
                     “C4” (middle C) is 60, “A4” is 69.
        :param velocity: The strike velocity, 0-127, 0 is equivalent to a Note Off, defaults to
                         127.
        :param channel: The channel number of the MIDI message where appropriate. This is updated
                        by MIDI.send() method.
        """
        return NoteOn(note=note, velocity=velocity, channel=channel)

    @staticmethod
    def NoteOff(note, velocity=127, *, channel=None):
        """
        Note Off Change MIDI message. For more details, see the ``adafruit_midi.note_off``
        documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/

        :param note: The note (key) number either as an int (0-127) or a str which is parsed, e.g.
                     “C4” (middle C) is 60, “A4” is 69.
        :param velocity: The release velocity, 0-127, defaults to 0.
        :param channel: The channel number of the MIDI message where appropriate. This is updated
                        by MIDI.send() method.

        """
        return NoteOff(note=note, velocity=velocity, channel=channel)

    @staticmethod
    def PitchBend(pitch_bend, *, channel=None):
        """
        Pitch Bend Change MIDI message. For more details, see the ``adafruit_midi.pitch_bend``
        documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/
        :param pitch_bend: A 14bit unsigned int representing the degree of bend from 0 through 8192
                           (midpoint, no bend) to 16383.
        :param channel: The channel number of the MIDI message where appropriate. This is updated
                        by MIDI.send() method.

        """
        return PitchBend(pitch_bend=pitch_bend, channel=channel)

    @staticmethod
    def ControlChange(control, value, *, channel=None):
        """
        Control Change MIDI message. For more details, see the ``adafruit_midi.control_change``
        documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/

        :param control: The control number, 0-127.
        :param value: The 7bit value of the control, 0-127.
        :param channel: The channel number of the MIDI message where appropriate. This is updated
                        by MIDI.send() method.

        """
        return ControlChange(control=control, value=value, channel=channel)

    @staticmethod
    def ProgramChange(patch, *, channel=None):
        """
        Program Change MIDI message. For more details, see the ``adafruit_midi.program_change``
        documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/

        :param patch: The note (key) number either as an int (0-127) or a str which is parsed,
                      e.g. “C4” (middle C) is 60, “A4” is 69.
        :param channel: The channel number of the MIDI message where appropriate. This is updated
                        by MIDI.send() method.
        :return:
        """
        return ProgramChange(patch=patch, channel=channel)

    def display_image(self, file_name=None, position=None):
        """
        Display an image on the built-in display.

        :param str file_name: The path to a compatible bitmap image, e.g. ``"/image.bmp"``. Must be
                              a string.
        :param tuple position: Optional ``(x, y)`` coordinates to place the image.

        The following example displays an image called "image.bmp" located in / on the CIRCUITPY
        drive on the display.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            macropad.display_image("image.bmp")

            while True:
                pass
        """
        if not file_name:
            return
        if not position:
            position = (0, 0)
        group = displayio.Group(scale=1)
        self._display.show(group)
        with open(file_name, "rb") as image_file:
            background = displayio.OnDiskBitmap(image_file)
            sprite = displayio.TileGrid(
                background,
                pixel_shader=background.pixel_shader,
                x=position[0],
                y=position[1],
            )
            group.append(sprite)
            self._display.refresh()

    @staticmethod
    def display_text(
        title=None, title_scale=1, title_length=80, text_scale=1, font=None
    ):
        """
        Display lines of text on the built-in display.

        :param str title: The title displayed above the data. Set ``title="Title text"`` to provide
                          a title. Defaults to None.
        :param int title_scale: Scale the size of the title. Not necessary if no title is provided.
                                Defaults to 1.
        :param int title_length: The maximum number of characters allowed in the title. Only
                                 necessary if the title is longer than the default 80 characters.
                                 Defaults to 80.
        :param int text_scale: Scale the size of the data lines. Scales the title as well.
                               Defaults to 1.
        :param font: The font or the path to the custom font file to use to display the text.
                     Defaults to the built-in ``terminalio.FONT``. Custom font files must be
                     provided as a string, e.g. ``"/Arial12.bdf"``.

        The following example displays a title and lines of text indicating which key is pressed,
        the relative position of the rotary encoder, and whether the encoder switch is pressed.
        Note that the key press line does not show up until a key is pressed.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            text_lines = macropad.display_text(title="MacroPad Info")

            while True:
                event = macropad.keys.events.get()
                if event:
                    text_lines[0].text = "Key {} pressed!".format(event.key_number)
                text_lines[1].text = "Rotary encoder {}".format(macropad.encoder)
                text_lines[2].text = "Encoder switch: {}".format(macropad.encoder_switch)
                text_lines.show()
        """
        return SimpleTextDisplay(
            title=title,
            title_color=SimpleTextDisplay.WHITE,
            title_scale=title_scale,
            title_length=title_length,
            text_scale=text_scale,
            font=font,
            colors=(SimpleTextDisplay.WHITE,),
            display=board.DISPLAY,
        )

    @staticmethod
    def _sine_sample(length):
        tone_volume = (2 ** 15) - 1
        shift = 2 ** 15
        for i in range(length):
            yield int(tone_volume * math.sin(2 * math.pi * (i / length)) + shift)

    def _generate_sample(self, length=100):
        if self._sample is not None:
            return
        self._sine_wave = array.array("H", self._sine_sample(length))
        self._sample = audiopwmio.PWMAudioOut(board.SPEAKER)
        self._sine_wave_sample = audiocore.RawSample(self._sine_wave)

    def play_tone(self, frequency, duration):
        """Produce a tone using the speaker.

        :param int frequency: The frequency of the tone in Hz
        :param float duration: The duration of the tone in seconds

        """
        # Play a tone of the specified frequency (hz).
        self.start_tone(frequency)
        time.sleep(duration)
        self.stop_tone()

    def start_tone(self, frequency):
        """Produce a tone using the speaker.

        :param int frequency: The frequency of the tone in Hz

        """
        self._speaker_enable.value = True
        length = 100
        if length * frequency > 350000:
            length = 350000 // frequency
        self._generate_sample(length)
        # Start playing a tone of the specified frequency (hz).
        self._sine_wave_sample.sample_rate = int(len(self._sine_wave) * frequency)
        if not self._sample.playing:
            self._sample.play(self._sine_wave_sample, loop=True)

    def stop_tone(self):
        """Use with ``start_tone`` to stop the tone produced."""
        # Stop playing any tones.
        if self._sample is not None and self._sample.playing:
            self._sample.stop()
            self._sample.deinit()
            self._sample = None
        self._speaker_enable.value = False

    def play_file(self, file_name):
        """Play a .wav file using the onboard speaker.

        :param file_name: The name of your .wav file in quotation marks including .wav

        """
        # Play a specified file.
        self.stop_tone()
        self._speaker_enable.value = True
        with audiopwmio.PWMAudioOut(
            board.SPEAKER
        ) as audio:  # pylint: disable=not-callable
            wavefile = audiocore.WaveFile(open(file_name, "rb"))
            audio.play(wavefile)
            while audio.playing:
                pass
        self._speaker_enable.value = False
