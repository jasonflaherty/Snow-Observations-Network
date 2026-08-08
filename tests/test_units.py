from son_core.units import fahrenheit_to_celsius, inches_to_cm, inches_to_mm


def test_inches_to_mm():
    assert inches_to_mm(1.0) == 25.4


def test_inches_to_cm():
    assert inches_to_cm(1.0) == 2.54


def test_fahrenheit_to_celsius():
    assert abs(fahrenheit_to_celsius(32.0) - 0.0) < 1e-9
    assert abs(fahrenheit_to_celsius(212.0) - 100.0) < 1e-9
