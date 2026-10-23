"""Typed boundary failures with no external data in their messages."""


class Unauthenticated(Exception):
    pass


class Forbidden(Exception):
    pass


class DependencyUnavailable(Exception):
    pass


class InvalidEvent(ValueError):
    pass
