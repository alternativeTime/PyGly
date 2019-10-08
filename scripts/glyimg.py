#!/bin/env python27
import sys, os
import findpygly
from pygly.GlycanImage import GlycanImage
from pygly.GlyTouCan import GlyTouCan

if len(sys.argv) <= 1:
    print >>sys.stderr, "GlyDbImage.py [ image options ] <gtc-accession> [ <gtc-accession> ... ]"
    print >>sys.stderr, """
    Image options:
    scale        <float>                               [4.0]
    reducing_end (true|false)                          [true]
    orientation  (RL|LR|TB|BT)                         [RL]
    notation     (cfg|cfgbw|cfglink|uoxf|text|uoxfcol) [cfg]
    display      (normal|normalinfo|compact)           [normalinfo]
    """.strip()
    sys.exit(1)

gtc = GlyTouCan(usecache=True)

imageWriter = GlycanImage()
lastopt = 0
for i in range(1,len(sys.argv),2):
    if sys.argv[i].startswith('G'):
	break
    key = sys.argv[i]
    value = sys.argv[i+1]
    imageWriter.set(key,value)
    lastopt = i+1

for acc in sys.argv[(lastopt+1):]:
    outfile = acc + ".png"
    g = gtc.getGlycan(acc)
    imageWriter.writeImage(g,outfile)
