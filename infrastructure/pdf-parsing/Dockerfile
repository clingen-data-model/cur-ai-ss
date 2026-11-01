# The pdf-parsing service image: docling-serve's own CUDA image, plus the
# layout override the worker applies when it runs Docling in-process
# (lib/misc/pdf/layout.py: a multi-panel figure stays one picture). Stock
# docling-serve cuts such a figure down to its best-scoring panel; three of
# the thirteen papers in the local stack lose a figure that way.
#
# The override is installed by a sitecustomize.py, which Python imports at
# interpreter start from any directory on PYTHONPATH, so it is in place
# before docling-serve loads its models, whatever the entrypoint.
#
# Built by .github/workflows/pdf-parsing-image.yml on every push to main
# that touches these inputs: it stages this file, layout.py and
# sitecustomize.py, runs Cloud Build (no docker is needed anywhere but
# there) and rolls the service onto the result. The base tag, in base-tag
# beside this file, is the docling-serve release that bundles the docling
# version pyproject.toml pins; the built tag is the base tag and the short
# commit.

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

COPY layout.py /opt/caa/caa_layout.py
COPY sitecustomize.py /opt/caa/sitecustomize.py
ENV PYTHONPATH=/opt/caa${PYTHONPATH:+:$PYTHONPATH}
