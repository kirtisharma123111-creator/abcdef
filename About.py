def sum_numbers(num1, num2):
    """Return the sum of two numbers."""
    return num1 + num2


if __name__ == "__main__":
    num1 = 13.54
    num2 = 64.34

    result = sum_numbers(num1, num2)
    print("The sum of {0} and {1} is {2}".format(num1, num2, result))