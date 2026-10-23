"""The names of a converted document's blocks and table cells, as the core writes them.

A block is ``p<page>-b<n>`` (``cur:blockId`` in cur-shapes.ttl), a table's cell ``T<n>:r<i>c<j>``
(``cur:tableCell``, "T4:r3c2"); the conversion gives them (app/conversion/base.py), anchors point
at them.
"""

import re

BLOCK_ID = re.compile(r"p[0-9]+-b[0-9]+")
CELL_ID = re.compile(r"T([0-9]+):r([0-9]+)c([0-9]+)")
