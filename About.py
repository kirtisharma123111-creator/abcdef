num1 = float(input("Enter first positive number: "))
num2 = float(input("Enter second positive number: "))

if num1 > 0 and num2 > 0:
    total = num1 + num2
    print("The sum of {0} and {1} is {2}".format(num1, num2, total))
else:
    print("Both numbers must be positive.")
