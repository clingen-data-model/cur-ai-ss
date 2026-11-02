"""Imported by Python at interpreter start (it is on PYTHONPATH, see the
Dockerfile): install the layout override before docling-serve loads anything.
``caa_layout`` is lib/misc/pdf/layout.py, copied in beside this file."""

import caa_layout

caa_layout.install()
