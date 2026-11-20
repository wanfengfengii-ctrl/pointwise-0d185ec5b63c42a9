from fractions import Fraction


def exact_mean(first: int, second: int) -> Fraction:
    if type(first) is not int or type(second) is not int:
        raise ValueError('the mean requires two integer deviations in μm')
    return Fraction(first + second, 2)
