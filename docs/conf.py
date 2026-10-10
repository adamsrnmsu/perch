"""Sphinx config. Build with `make docs`; PYTHONPATH=. documents this checkout."""

from importlib.metadata import version as _version

project = "perch"
author = "Ryan Adams"
version = release = _version("perch")

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_click",
]

myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 2
exclude_patterns = ["_build", "superpowers"]  # specs and plans, not user docs
suppress_warnings = ["misc.highlighting_failure"]  # README's ```csv: no lexer, plain text is fine

html_theme = "shibuya"
html_static_path = ["_static"]
html_css_files = ["landing.css"]
html_theme_options = {
    "github_url": "https://github.com/adamsrnmsu/perch",
    "accent_color": "blue",
    "color_mode": "auto",
    "nav_links": [
        {"title": "Install", "url": "install"},
        {"title": "Guide", "url": "guide"},
        {"title": "Reference", "url": "reference"},
    ],
}
