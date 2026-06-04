#!/usr/bin/env bash

#!/usr/bin/env bash
shopt -s nullglob

for f in jsons/Core*; do
    other="../dc_ahtcg-plugin/jsons/$(basename "$f")"

    if [[ -f "$other" ]]; then
        diff -u "$f" "$other"
    else
        echo "Missing: $other"
    fi
done

