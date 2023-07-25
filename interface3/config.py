import json
import sys

with open("config.json") as f:
    data = json.load(f)

    myself = sys.modules[__name__]
    for key in data:
        setattr(myself, key, data[key])
