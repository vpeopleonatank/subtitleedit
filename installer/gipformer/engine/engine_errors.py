"""Errors shared by caption_engine and the backends.

Kept out of caption_engine.py: when the engine runs as ``python caption_engine.py`` that module is ``__main__``, and a
backend importing it would get a second copy of the class that ``except EngineError`` in ``main`` would not match.
"""


class EngineError(Exception):
    """A failure whose message is safe to show to the user."""
