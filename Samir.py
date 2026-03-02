#Комментарии в Python

#test = 'abc'
print("Hello World!")
"""
 test1 = 'abc'
 test2 = '123'
 test3 = 123
"""
#Переменные в Python
#Вывод переменной в консоль в Python(print)

a = 'abc'
print(a)

a = 17
print(a)

#Математические операции с числами в Python

test = 1 + 2 + 3
print(test)

test = 6 - 4
print(test)

test = (1 + 2 + 3) * (6 - 4)
print(test)

test = 8 / 3
print(test)

test = 8 // 3
print(test)

test = 8 % 3
print(test)

#Математические операции с переменными в Python

num1 = 5
num2 = 3
sum = num1 + num2
print("sum=", sum)

num1 = 10
num2 = 6
raz = num1 - num2
print("raz=", raz)

num1 = 7
num2 = 3
proiz = num1 * num2
print("proiz=", proiz)

num1 = 15
num2 = 6
chast = num1 / num2
print("chast=", chast)

num1 = 15
num2 = 6
chast = num1 // num2
print("chast=", chast)

#Сокращенные операции в Python
"""
Переделайте этот код так, чтобы в нем были операции инкремента и декремента:
num = 4
num = num + 1
num = num - 1
num = num + 2
"""

num = 4
num += 1
num -= 1
num += 2
print("num:", num)

#Приоритет математических операций в Python

res = 2 + 3 * 4
print(res)
# 3 * 4 = 12 -> 12 + 2 = 14

res = 10 - 6 / 3
print(res)
# 6 / 3 = 2 -> 10 - 2 = 8

res = 10 - 6 * 3 - 5
print(res)
# 6 * 3 = 18 -> 10 - 18 = -8 -> -8 - 5 = -13

#Равный приоритет в Python

res = 6 * 2 / 4
print(res)
# 12 / 4 = 3

res = 6 / 2 * 3
print(res)
# 3 * 3 = 9

res = 18 / 2 / 3 * 2
print(res)
# 3 * 2 = 6

#Группирующие скобки в Python

res = (2 + 3) * 4
print(res)
# 5 * 4 = 20

res = (10 - 6) / 3
print(res)
# 4 / 3 = 1.3333333333333333

res = 10 - 6 * (3 - 5)
print(res)
# 6 * (-2) = -12 -> 10 - -12 = 22

res = 4 - 1 + (5 + 6 * (2 + 7))
print(res)
# 6 * 9 = 54 -> 5 + 54 = 59 -> 4 - 1 = 3 -> 3 + 59 = 62

#Нюансы группировки в Python

res = 2 * 3 / 2
print(res)
# 3

res = (6 / 2) + 5
print(res)
# 8

#Длина числа в Python

tst = 1342453547656758678993553453 ** 5
print(tst)

num1 = 200 ** 500
num2 = 3000
print("proiz=", num1 * num2)

num1 = 67 ** 50
num2 = 45 ** 60
print("raznost= ", num1 - num2)

#Числа с плавающей точкой в Python

num1 = 1.5
num2 = 0.75
print(num1 + num2)

num1 = 3.4
num2 = 8.27
num3 = 1.5
print((num2 - num1) * num3)

#Отрицательные числа в Python

test = -100
print(test)

test1 = 54
test2 = -62
print(-test1)
print(-test2)

test = -20
a = test - -20
print(a)

#Остаток от деления в Python

num1 = 13
num2 = 3
print(num1 % num2)

num1 = 26
num2 = 8
print(num1 % num2)

a1 = -5
a2 = 12
c = a2 % a1
print(c)

#Возведение в степень в Python

num1 = 2
num2 = 5
print(num1 ** num2)

num1 = 1
num2 = 3
print(5 ** (num1 + num2))

#Приоритет возведения в степень в Python

res = 2 * 3 ** 2
print(res)

res = (7 + 4) * (3 - 1) ** 3
print(res)

#Строки в Python

txt = 'abc'
print(txt) # выведет 'abc'

txt = "abc"
print(txt) # выведет 'abc'

#Сложение строк в Python

txt1 = 'abc'
txt2 = 'def'
txt3 = txt1 + txt2
print(txt3) # выведет 'abcdef'

txt1 = '12'
txt2 = '+'
txt3 = '5'
txt4 = '17'
txt5 = txt1 + txt2 + txt3 + '=' + txt4
print(txt5) # выведет '12+5=17'

#Умножение строк в Python

txt1 = 'a1b2'
txt2 = txt1 * 4
print(txt2) # выведет 'a1b2a1b2a1b2a1b2'

txt1 = 'ab'
txt2 = '1213'
txt3 = txt1 * 2 + txt2
print(txt3) # выведет 'abab1213'

#Символы строки в Python

txt = 'abcdef'
print(txt[0])
print(txt[1])
print(txt[5])
print(txt[4])

#Экранирование символов строки в Python

tst = "abcd\"fr'23"
print(tst)

