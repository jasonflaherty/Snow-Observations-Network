"""Unit conversion helpers. Canonical SON units are metric."""


def inches_to_mm(value: float) -> float:
    return value * 25.4


def inches_to_cm(value: float) -> float:
    return value * 2.54


def fahrenheit_to_celsius(value: float) -> float:
    return (value - 32.0) * 5.0 / 9.0


def mph_to_ms(value: float) -> float:
    return value * 0.44704
