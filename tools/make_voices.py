"""Writes app/voice_list.py from Microsoft's current list of neural voices. Run it when you want new voices:  py -3.12 tools/make_voices.py"""
import asyncio
import os

import edge_tts

OUT = os.path.join(os.path.dirname(__file__), "..", "app", "voice_list.py")


def person(short_name):
    """en-US-AndrewMultilingualNeural -> Andrew Multilingual"""
    name = short_name.rsplit("-", 1)[1].replace("Neural", "")
    return name.replace("Multilingual", " Multilingual").strip()


def language(row):
    friendly = row["FriendlyName"].rsplit(" - ", 1)[-1]
    return friendly.strip()


def main():
    voices = asyncio.run(edge_tts.list_voices())
    rows = sorted((language(v), person(v["ShortName"]), v["Gender"], v["ShortName"]) for v in voices)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write('"""Made by tools/make_voices.py. Do not edit by hand. Rows: language, name, gender, voice id."""\n')
        f.write("VOICE_ROWS = (\n")
        for row in rows:
            f.write("    %r,\n" % (row,))
        f.write(")\n")
    print("wrote %d voices" % len(rows))


if __name__ == "__main__":
    main()
