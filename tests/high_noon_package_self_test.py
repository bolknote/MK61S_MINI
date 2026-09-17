#!/usr/bin/env python3
"""Offline completeness and layout checks for the split High Noon port."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def quoted_payload(path: Path) -> str:
    return compact("".join(re.findall(r'"([^"]*)"', path.read_text(encoding="utf-8"))))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
game = root / "programs" / "games" / "High Noon"
parts = [game / name for name in ("intro.tbi", "player.tbi", "bart.tbi", "reward.tbi")]
driver = game / "autoexec.m61"
manual = game / "manual.md"

require(driver.is_file(), "High Noon autoexec.m61 is missing")
require(driver.stat().st_size <= 1536, "High Noon M61 dispatcher exceeds 1536 bytes")
require(manual.is_file() and manual.stat().st_size <= 1536,
        "High Noon manual exceeds the Markdown quota")
for path in parts:
    require(path.is_file(), f"High Noon part is missing: {path.name}")
    data = path.read_bytes()
    require(len(data) <= 3584, f"{path.name} exceeds the TinyBASIC quota")
    require(len(data) + data.count(b"\n") <= 3584,
            f"{path.name} would exceed the quota after LF-to-CRLF conversion")

driver_text = driver.read_text(encoding="utf-8")
for line in (
    "reinit",
    "open intro.tbi",
    "if re==1 run :player",
    "if re==2 run :bart",
    "if re==3 run :bart",
    "if re==80 run :reward",
    "open player.tbi",
    "open bart.tbi",
    "open reward.tbi",
):
    require(line in driver_text, f"High Noon dispatcher lost: {line}")

# These are the complete player-visible string literals of HIGHNOON.F90.
# Whitespace is ignored because the 192x64 display needs deterministic 40-cell
# wrapping and page breaks; wording, punctuation and even upstream typos stay.
required_text = (
    "H I G H  N O O N",
    "----------------",
    "DO YOU WANT INSTRUCTIONS?",
    "YOU HAVE BEEN CHALLENGED TO A SHOWDOWN BY BLACK BART, ONE OF",
    "THE MEANEST DESPERADOES WEST OF THE ALLEGHENY MOUNTAINS.",
    "WHILE YOU ARE WALKING DOWN A DUSTY, DESERTED SIDE STREET,",
    "BLACK BART EMERGES FROM A SALOON ONE HUNDRED PACES AWAY. BY",
    "AGREEMENT, YOU EACH HAVE FOUR CARTRIDGES IN YOUR SIX-GUNS.",
    "YOUR MARKSMANSHIP EQUALS HIS. AT THE START OF THE WALKM NEI-",
    "THER OF YOU CAN POSSIBLY HIT THE OTHER, AND AT THE END OF",
    "THE WALK, NEITHER CAN MISS. THE CLOSER YOU GET, THE BETTER",
    "YOUR CHANCES OF HITTING BART, BUT HE ALSO HAS BETER CHANCES",
    "OF HITTING YOU.",
    "DO YOU STILL WANT TO CONTINUE?",
    "THE MOVES ARE AS FOLLOWS:",
    "*M O V E S*",
    "===========",
    "1. ADVANCE",
    "2. STAND STILL",
    "3. FIRE",
    "4. JUMP BEHIND THE WATERING TROUGH",
    "5. GIVE UP",
    "6. TURN TAIL AND RUN",
    "WHAT IS YOUR STRATEGY?",
    "HOW MANY PACES DO YOU ADVANCE:",
    "YOU ARE NOW",
    "PACES APART.",
    "NICE GOING, ACE, YOU'VE RUN OUT OF SHELLS.",
    "NOW BART WON'T SHOOT UNTIL YOU TOUCH NOSES.",
    "YOU BETTER THINK OF SOMETHING FAST. (LIKE RUN)",
    "WHAT A LOUSY SHOT.",
    "WHAT A SHOT, YOU GOT BLACK BART RIGHT BETWEEN THE EYES.",
    "AS MAYOR OF DODGE CITY, AND ON BEHALF OF ITS CITIZENS,",
    "I EXTEND TO YOU OUR THANKS, AND PRESENT YOU WITH THIS",
    "REWARD, A CHECK FOR $20,000, FOR KILLING BLACK BART.",
    "******************************************************",
    "CHECK NO.",
    "AUG.",
    "TH. 1889",
    "CASHIER'S RECEIT---BANK OF DODsGE CITY",
    "PAY TO THE BEARER ON DEMAND",
    "THE SUM OF",
    "TWENTY THOUSAND DOLLARS-------------------$20,000",
    "DON'T SPEND IT ALL IN ONE PLACE.",
    "BLACK BART MOVES",
    "NOW IS YOUR CHANCE, BART IS OUT OF SHELLS",
    "BART FIRES . . . . . .",
    "A MISS . . . .",
    "WHEW, WERE YOU LUCKY. THAT BULLET JUST MISSED YOUR HEAD.",
    "BART SHOT YOU RIGHT THROUGH THE HEART THAT TIME.",
    "YOU WENT KICKIN' WITH YOUR BOOTS ON.",
    "YOU SURE AREN'T GOING TO LIVE VERY LONG IF YOU CAN'T EVEN",
    "FOLLOW DIRECTIONS",
    "GREENHORN.",
    "THAT MOVE MADE YOU A PERFECT STATIONARY TARGET",
    "NOT A BAD MANEUVER, YOU THREW BART'S STRATEGY OFF",
    "YOU NOW HAVE",
    "SHELLS TO BART'S",
    "SHELLS.",
    "BLACK BART ACCEPTS. THE CONDITIONS ARE THAT HE WON'T SHOOT YOU",
    "IF YOU TAKE THE FIRST STAGE OUT OF TOWN AND NEVER COME BACK",
    "AGREED?",
    "A VERY WISE DECISION.",
    "OH WELL, BACK TO THE SHOWDOWN",
    "HOW FAR DID YOU RUN?",
    "MAN, DID HE RUN. HE RAN SO FAST EVEN DOGS COULDN'T",
    "CATCH HIM",
    "BLACK BART FIRES",
    "SHELLS.......",
    "HE GOT YOU RIGHT IN THE BACK. THATS WHAT YOU DESERVE",
    "FOR RUNNING",
    "BLACK BART UNLOADED HIS GUN, ONCE IN YOUR BACK",
    "TIMES IN YOUR A**. NOW YOU CAN'T EVEN REST IN",
    "PEACE.",
    "YOU WERE LUCKY, BART CAN ONLY THROW HIS GUN AT YOU, HE",
    "DOESN'T HAVE ANY SHELLS LEFT. YOU SHOULD REALLY BE DEAD.",
    "GRAZED BART IN THE RIGHT ARM",
    "HE'S HIT IN THE LEFT SHOULDER, FORCING HIM TO USE HIS RIGHT",
    "HAND TO SHOOT WITH",
    "THAT WAS YOUR LAST SHOT, YOU MISSED",
    "BUT BART GOT YOU IN THE RIGHT SHIN.",
    "THAT TRICK JUST SAVED YOUT LIFE. BART'S BULLET",
    "WAS STOPPED BY THE WOOD SIDES OF THE TROUGH.",
    "THOUGH BART GOT YOU ON THE LEFT SIDE OF YOUR JAW.",
    "BURT MUST HAVE JERKED THE TRIGGER",
    "NOBODY CAN WALK THAT FAST",
    "NONE OF THIS NEGATIVE STUFF PARTNER, ONLY POSITIVE NUMBERS",
    "BART JUST HI-TAILED IT OUT OF TOWN RATHER THAN FACE YOU WITH-",
    "OUT A LOADED GUN. YOU CAN REST ASSURED THAT BART WON'T EVER",
    "SHOW HIS FACE AROUND THIS TOWN AGAIN.",
    "HOW MANY WATERING TROUGHS DO YOU THINK ARE ON THIS STREET",
    "C.G. INC.",
)
payloads = [quoted_payload(path) for path in parts]
for phrase in required_text:
    needle = compact(phrase)
    require(any(needle in payload for payload in payloads),
            f"High Noon lost upstream text: {phrase}")

player = (game / "player.tbi").read_text(encoding="utf-8")
bart = (game / "bart.tbi").read_text(encoding="utf-8")
for fragment in (
    "G.1000+B*100",
    ".R0=X:.R2=C:.R3=P:.R4=T",
    "W>SGN(X)*INT(ABS(X)/10)",
    "IF P>4 N=3",
):
    require(fragment in player, f"High Noon player logic lost: {fragment}")
for fragment in (
    "X=.R0:B=.R1:C=.R2:P=.R3",
    "A=.RE:X=.R0:B=.R1:C=.R2:P=.R3",
    "IF A=3 G.1050",
    "R>SGN(X)*INT(ABS(X)/10)",
    ".R0=X:.R2=C:.R3=P",
):
    require(fragment in bart, f"High Noon Bart logic lost: {fragment}")

print("high_noon_package_self_test: ok")
