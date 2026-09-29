#!/bin/sh
# Seed the writable models directory from the models baked into the image.
#
# compose mounts the named volume ml_models at /app/models and that directory
# has to stay WRITABLE — the scheduler's POST /retrain saves into it. So the
# real artifacts cannot sit in the read-only image layer at /app/models: they
# are baked to /app/models-baked instead and copied here on first start.
#
# An existing artifact is never overwritten, so a retrained model survives a
# container restart. With no models baked in (e.g. a fresh clone, where
# ml-service/models/ holds only .gitkeep) this is a no-op and the service
# reports the missing models instead of inventing one.
set -eu

baked="${LCT_BAKED_MODELS_DIR:-/app/models-baked}"
live="${LCT_MODELS_DIR:-/app/models}"

if [ ! -d "$baked" ]; then
    echo "models: nothing baked at $baked, using $live as-is" >&2
elif [ ! -w "$live" ]; then
    echo "models: $live is not writable, skipping seed (volume not mounted?)" >&2
else
    for src in "$baked"/*/; do
        [ -d "$src" ] || continue
        name="$(basename "$src")"
        if [ -e "$live/$name/meta.json" ]; then
            echo "models: $name already present in $live, keeping it"
            continue
        fi
        mkdir -p "$live/$name"
        cp -a "$src/." "$live/$name/"
        echo "models: seeded $name from the image"
    done
fi

exec "$@"
